"""Serial writer (queue consumer) and reader (background thread).

Thread safety: pyserial documents that concurrent read/write on separate
threads is safe. The writer thread is the sole consumer of a queue.Queue,
so no locks are needed.
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


class SerialWriter(threading.Thread):
    """Daemon thread that consumes SerialCommand items from a queue."""

    def __init__(self, port: serial.Serial, min_delay: float = 0.1) -> None:
        super().__init__(name="serial-writer", daemon=True)
        self._port = port
        self._min_delay = min_delay
        self._queue: queue.Queue[SerialCommand | None] = queue.Queue()

    def enqueue(self, cmd: SerialCommand) -> None:
        """Thread-safe enqueue of a command."""
        self._queue.put(cmd)

    def shutdown(self) -> None:
        """Send sentinel to stop the writer loop."""
        self._queue.put(None)

    def run(self) -> None:
        while True:
            cmd = self._queue.get()
            if cmd is None:
                log.info("Writer received shutdown sentinel")
                break
            try:
                self._execute(cmd)
            except Exception:
                log.exception("Error writing serial command")

    def _execute(self, cmd: SerialCommand) -> None:
        for i, payload in enumerate(cmd.payloads):
            if not cmd.quiet:
                log.info(">> %s", payload.strip())
            else:
                log.debug(">> %s", payload.strip())
            self._port.write(payload.encode("ascii"))
            self._port.flush()
            # Delay between payloads (e.g. tone-reset needs 1.5 s)
            if i < len(cmd.delays):
                sleep(cmd.delays[i])
            sleep(self._min_delay)


class SerialReader(threading.Thread):
    """Daemon thread that reads lines from the serial port."""

    def __init__(
        self,
        port: serial.Serial,
        writer: SerialWriter,
        on_initialized: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(name="serial-reader", daemon=True)
        self._port = port
        self._writer = writer
        self._on_initialized = on_initialized
        self._last_time = ""

    def run(self) -> None:
        while True:
            try:
                raw = self._port.readline()
                if raw:
                    line = raw.decode("ascii", errors="replace").strip()
                    log.info("<< %s", line)
                    if "initialized" in line:
                        self._writer.enqueue(build_message(1, "Raspberry Pi OK"))
                        if self._on_initialized:
                            self._on_initialized()
                    continue
                # No data received (timeout) -- update the clock
                self._update_clock()
            except Exception:
                log.exception("Error reading serial port")
                sleep(1)

    def _update_clock(self) -> None:
        out = strftime("%a %b %e %I:%M", localtime())
        if out != self._last_time:
            self._last_time = out
            self._writer.enqueue(build_message(2, out, quiet=True))


def open_serial(config: Config) -> serial.Serial:
    """Open the serial port described by *config*."""
    return serial.Serial(
        port=config.serial_device,
        baudrate=config.serial_baudrate,
        timeout=config.serial_timeout,
    )
