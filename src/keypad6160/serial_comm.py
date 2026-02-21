"""Serial I/O thread — single thread for both reading and writing.

A single thread owns the serial port for both directions, eliminating
the need for locks.  Outgoing commands are submitted via a thread-safe
queue.  Between commands the thread reads unsolicited data and updates
the clock.
"""

from __future__ import annotations

import logging
import queue
import threading
from time import localtime, sleep, strftime
from typing import TYPE_CHECKING, Callable

import serial

from keypad6160.f7_protocol import SerialCommand, build_message

if TYPE_CHECKING:
    from keypad6160.config import Config

log = logging.getLogger(__name__)

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
    ) -> None:
        super().__init__(name="serial-io", daemon=True)
        self._port = port
        self._on_initialized = on_initialized
        self.on_keypress: Callable[[str], None] | None = None
        self._queue: queue.Queue[SerialCommand | None] = queue.Queue()
        self._last_time = ""

    def enqueue(self, cmd: SerialCommand) -> None:
        """Thread-safe enqueue of a command."""
        self._queue.put(cmd)

    def shutdown(self) -> None:
        """Send sentinel to stop the loop."""
        self._queue.put(None)

    def run(self) -> None:
        while True:
            try:
                cmd = self._queue.get(timeout=self._port.timeout)
            except queue.Empty:
                # No queued command — read unsolicited data and update clock
                self._read_unsolicited()
                self._update_clock()
                continue

            if cmd is None:
                log.info("SerialIO received shutdown sentinel")
                break
            try:
                self._execute(cmd)
            except Exception:
                log.exception("Error writing serial command")

    # -- Writing -----------------------------------------------------------

    def _execute(self, cmd: SerialCommand) -> None:
        if cmd.reset:
            self._reset_device()
            return
        for i, payload in enumerate(cmd.payloads):
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
        sleep(0.2)
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
        if "initialized" in line:
            self.enqueue(build_message(1, "Raspberry Pi OK", source="init"))
            if self._on_initialized:
                self._on_initialized()
        elif line.startswith("KEYS_"):
            self._handle_keys(line)

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

    def _update_clock(self) -> None:
        out = strftime("%a %b %e %I:%M", localtime())
        if out != self._last_time:
            self._last_time = out
            self.enqueue(build_message(2, out, quiet=True, source="clock"))


def open_serial(config: Config) -> serial.Serial:
    """Open the serial port described by *config*."""
    return serial.Serial(
        port=config.serial_device,
        baudrate=config.serial_baudrate,
        timeout=config.serial_timeout,
    )
