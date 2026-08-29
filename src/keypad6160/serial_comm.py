"""Serial I/O thread — single thread for both reading and writing.

A single thread owns the serial port for both directions, eliminating
the need for locks.  Outgoing commands are submitted via a thread-safe
queue.  Between commands the thread reads unsolicited data and updates
the clock.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
from time import monotonic, sleep
from typing import TYPE_CHECKING, Callable

import serial

from keypad6160.config import Config
from keypad6160.f7_protocol import SerialCommand, build_message

if TYPE_CHECKING:
    from keypad6160.notice_manager import NoticeManager

log = logging.getLogger(__name__)


class _CoalescingQueue:
    """Thread-safe queue that drops stale entries sharing a coalesce_key.

    When a new item with a non-empty coalesce_key is put(), any pending
    item with the same key is removed first.  This prevents rapid-fire
    updates (e.g. MQTT line-2 messages) from piling up and overwhelming
    the 4800-baud keybus.
    """

    def __init__(self) -> None:
        self._items: list[SerialCommand | None] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

    def put(self, item: SerialCommand | None) -> None:
        """Append *item*, dropping any pending item with the same coalesce_key."""
        with self._not_empty:
            if item is not None and item.coalesce_key:
                self._items = [
                    i for i in self._items
                    if i is None or i.coalesce_key != item.coalesce_key
                ]
            self._items.append(item)
            self._not_empty.notify()

    def get(self, timeout: float | None = None) -> SerialCommand | None:
        """Pop the oldest item, blocking up to *timeout* seconds."""
        with self._not_empty:
            while not self._items:
                if not self._not_empty.wait(timeout):
                    raise queue.Empty
            return self._items.pop(0)

# Matches a line-text field: space + line number (1 or 2) + = + 16 chars.
_LINE_RE = re.compile(r" ([12])=(.{16})")

# Pacing delay after each serial write, in seconds.  Must exceed the time the
# Arduino needs to relay a full F7 frame on the 4800-baud keybus (~100 ms) plus
# margin, so back-to-back writes don't overrun its 256-byte USB rx buffer.
_POST_WRITE_DELAY_S = 0.35

# Minimum interval between auto-resets triggered by Arduino error lines.
_AUTO_RESET_COOLDOWN_S = 60.0

# Two ERR_ lines within this window trigger a DTR reset.  An unbounded
# consecutive-error count is wrong in both directions: a wedge after one
# error persists for hours until a third stray garble arrives, while a
# stray garble hours later triggers an audible reset that wasn't needed.
_ERR_STRIKE_WINDOW_S = 120.0

_KEY_CODES: dict[int, str] = {
    **{i: str(i) for i in range(10)},
    0x0A: "*", 0x0B: "#",
    0x1C: "A", 0x1D: "B", 0x1E: "C", 0x1F: "D",
}


class SerialIO(threading.Thread):
    """Daemon thread that owns the serial port for reading and writing."""

    def __init__(
        self,
        port: serial.Serial,
        on_initialized: Callable[[], None] | None = None,
        config: Config | None = None,
    ) -> None:
        super().__init__(name="serial-io", daemon=True)
        self._port = port
        self._config = config
        self._on_initialized = on_initialized
        self.on_keypress: Callable[[str], None] | None = None
        self._queue: _CoalescingQueue = _CoalescingQueue()
        self._notice_manager: NoticeManager | None = None
        self._last_line2 = ""
        self._display: dict[int, str] = {1: " " * 16, 2: " " * 16}
        # Init far enough in the past that the first ERR_ always passes the
        # cooldown check.  monotonic() can be tiny (< 60s) on freshly-booted
        # hosts (e.g. CI runners), making 0.0 unsafe.
        self._last_auto_reset_monotonic: float = -_AUTO_RESET_COOLDOWN_S
        self._last_err_monotonic: float = -_ERR_STRIKE_WINDOW_S

    def enqueue(self, cmd: SerialCommand) -> None:
        """Thread-safe enqueue of a command."""
        self._queue.put(cmd)

    def shutdown(self) -> None:
        """Send sentinel to stop the loop."""
        self._queue.put(None)

    def run(self) -> None:
        """Thread entry point — runs the I/O loop with auto-reconnect on error."""
        while True:
            try:
                self._run_loop()
                break  # clean shutdown via sentinel
            except serial.SerialException:
                log.exception("Serial port error, attempting reconnect")
                self._reconnect()
            except OSError:
                log.exception("OS error on serial port, attempting reconnect")
                self._reconnect()

    def _reconnect(self) -> None:
        """Close the port and reopen it after a delay."""
        try:
            self._port.close()
        except Exception:
            pass
        if self._config is None:
            log.error("No config available for reconnect, giving up")
            return
        while True:
            sleep(5)
            try:
                self._port = serial.Serial(
                    port=self._config.serial_device,
                    baudrate=self._config.serial_baudrate,
                    timeout=self._config.serial_timeout,
                )
                log.info("Reconnected to %s", self._config.serial_device)
                return
            except (serial.SerialException, OSError):
                log.warning("Reconnect failed, retrying in 5s")

    def _run_loop(self) -> None:
        """Drain the command queue; between commands, read async data and tick the clock."""
        while True:
            try:
                cmd = self._queue.get(timeout=self._port.timeout)
            except queue.Empty:
                # No queued command — read unsolicited data and update clock
                self._read_unsolicited()
                self._update_line2()
                continue

            if cmd is None:
                log.info("SerialIO received shutdown sentinel")
                return
            try:
                self._execute(cmd)
            except (serial.SerialException, OSError):
                raise  # bubble up for reconnect
            except Exception:
                log.exception("Error writing serial command")

    # -- Writing -----------------------------------------------------------

    def _execute(self, cmd: SerialCommand) -> None:
        """Send each payload of *cmd* with pacing and per-payload response drain."""
        if cmd.reset:
            self._reset_device()
            return
        for i, payload in enumerate(cmd.payloads):
            payload = self._ensure_both_lines(payload)
            if not cmd.quiet:
                log.info(">> [%s] %s", cmd.source, payload.strip())
            else:
                log.debug(">> [%s] %s", cmd.source, payload.strip())
            self._port.write(payload.encode("ascii"))
            self._port.flush()
            # Delay between payloads (e.g. tone-reset needs 1.5 s)
            if i < len(cmd.delays):
                sleep(cmd.delays[i])
            self._read_response(cmd.source)

    def _ensure_both_lines(self, payload: str) -> str:
        """Rewrite an F7 payload to always include both 1= and 2= fields.

        The Arduino parser can misinterpret parameters like ``c=1`` as
        line-1 display text when only one line field is present.  By
        always sending both lines we eliminate the ambiguity.
        """
        if not payload.startswith("F7 "):
            return payload
        matches = list(_LINE_RE.finditer(payload))
        if not matches:
            # If the payload contains a short line field (e.g. "1=Hello")
            # that didn't match the 16-char regex, leave it unchanged.
            if " 1=" in payload or " 2=" in payload:
                return payload
            # Bare flag commands (e.g. tone set/reset) — attach current
            # display lines so the Arduino receives a complete F7 frame.
            args = payload[3:].rstrip()
            if args:
                return f"F7 {args} 1={self._display[1]} 2={self._display[2]}\n"
            return payload
        for m in matches:
            self._display[int(m.group(1))] = m.group(2)
        # Everything between "F7 " and the first line field is flags/args.
        args = payload[3:matches[0].start()].rstrip()
        return f"F7 {args} 1={self._display[1]} 2={self._display[2]}\n"

    def _reset_device(self) -> None:
        """Reset the Arduino by toggling the DTR line."""
        log.info("Resetting Arduino via DTR toggle")
        self._port.dtr = False
        sleep(0.1)
        self._port.dtr = True

    # -- Reading -----------------------------------------------------------

    def _read_response(self, source: str) -> None:
        """Wait briefly for data, then drain all available lines.

        The Arduino does not respond to valid F7 commands, so we use a
        fixed delay instead of a full blocking readline.  The delay must
        exceed the time the Arduino takes to relay on the 4800-baud
        keypad bus (~100 ms for a full frame).
        """
        sleep(_POST_WRITE_DELAY_S)
        while self._port.in_waiting:
            raw = self._port.readline()
            if raw:
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    log.info("<< [%s] %s", source, line)
                    self._handle_line(line)

    def _read_unsolicited(self) -> None:
        """Read any unsolicited data that arrived while idle."""
        while self._port.in_waiting:
            raw = self._port.readline()
            if raw:
                line = raw.decode("ascii", errors="replace").strip()
                log.info("<< %s", line)
                self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        """Dispatch an incoming line from the Arduino to the appropriate handler."""
        if "initialized" in line:
            self._last_err_monotonic = -_ERR_STRIKE_WINDOW_S
            self.enqueue(build_message(1, "Raspberry Pi OK", source="init"))
            if self._on_initialized:
                self._on_initialized()
        elif line.startswith("KEYS_"):
            self._handle_keys(line)
        elif line.startswith("ERR_"):
            self._handle_error_line(line)

    def _handle_error_line(self, line: str) -> None:
        """Arduino reported a parser error.

        Every error gets a quiet display refresh: the garbled frame may have
        latched a tone (t=4 is a continuous fast beep) or left stale text, and
        resending the current display with t=0 clears both within a second.

        An isolated error otherwise self-recovers on the Arduino, and a DTR
        reset audibly beeps the keypad, so only a second error within
        _ERR_STRIKE_WINDOW_S — a sign the Arduino is wedged rather than
        recovering — triggers a reset (rate-limited by the cooldown).
        """
        now = monotonic()
        prior_err = self._last_err_monotonic
        self._last_err_monotonic = now
        self._refresh_display()
        if now - prior_err >= _ERR_STRIKE_WINDOW_S:
            log.warning(
                "Arduino error %r — refreshing display (reset on 2nd error "
                "within %.0fs)", line, _ERR_STRIKE_WINDOW_S,
            )
            return
        if now - self._last_auto_reset_monotonic < _AUTO_RESET_COOLDOWN_S:
            log.warning("Arduino error %r (auto-reset in cooldown)", line)
            return
        log.warning("Arduino error %r — auto-resetting via DTR", line)
        self._last_auto_reset_monotonic = now
        # Don't pair a post-reset garble with a pre-reset one.
        self._last_err_monotonic = -_ERR_STRIKE_WINDOW_S
        self._reset_device()

    def _refresh_display(self) -> None:
        """Enqueue a quiet t=0 frame; _ensure_both_lines attaches the current
        display text, restoring whatever the garbled frame corrupted."""
        self.enqueue(SerialCommand(
            payloads=["F7 t=0\n"],
            quiet=True,
            source="err-refresh",
            coalesce_key="refresh",
        ))

    def _handle_keys(self, line: str) -> None:
        """Parse KEYS message and invoke callback for each key press."""
        for token in line.split()[1:]:  # skip "KEYS_16[02]"
            try:
                code = int(token, 16)
            except ValueError:
                continue
            key = _KEY_CODES.get(code)
            if key is not None:
                log.info("Key pressed: %s", key)
                if self.on_keypress:
                    self.on_keypress(key)

    def _update_line2(self) -> None:
        """Push the current notice text to keypad line 2 if it has changed."""
        if self._notice_manager is None:
            return
        text = self._notice_manager.get_current_display()
        if text != self._last_line2:
            self._last_line2 = text
            self.enqueue(build_message(2, text, quiet=True, source="notice"))


def open_serial(config: Config) -> serial.Serial:
    """Open the serial port described by *config*."""
    return serial.Serial(
        port=config.serial_device,
        baudrate=config.serial_baudrate,
        timeout=config.serial_timeout,
    )
