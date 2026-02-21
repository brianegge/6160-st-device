"""Tests for serial I/O (combined reader/writer)."""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, PropertyMock, call, patch

from keypad6160.f7_protocol import SerialCommand
from keypad6160.serial_comm import SerialIO


class TestSerialIO:
    def _make_io(self, port, **kwargs):
        kwargs.setdefault("min_delay", 0.0)
        port.timeout = kwargs.pop("timeout", 0.1)
        # Default: no bytes waiting (tests override via PropertyMock as needed)
        type(port).in_waiting = PropertyMock(return_value=0)
        io = SerialIO(port, **kwargs)
        io.start()
        return io

    def test_single_payload(self):
        port = MagicMock()
        io = self._make_io(port)
        cmd = SerialCommand(payloads=["F7 b=1 1=Hello\n"])
        io.enqueue(cmd)
        io.shutdown()
        io.join(timeout=2)
        port.write.assert_called_once_with(b"F7 b=1 1=Hello\n")
        port.flush.assert_called_once()

    def test_multi_payload_with_delay(self):
        port = MagicMock()
        io = self._make_io(port)
        cmd = SerialCommand(
            payloads=["F7 t=2 1=Armed\n", "F7 t=0\n"],
            delays=[0.01],
        )
        io.enqueue(cmd)
        io.shutdown()
        io.join(timeout=2)
        assert port.write.call_count == 2
        port.write.assert_any_call(b"F7 t=2 1=Armed\n")
        port.write.assert_any_call(b"F7 t=0\n")

    def test_shutdown_sentinel(self):
        port = MagicMock()
        io = self._make_io(port)
        io.shutdown()
        io.join(timeout=2)
        assert not io.is_alive()

    def test_quiet_does_not_crash(self):
        port = MagicMock()
        io = self._make_io(port)
        cmd = SerialCommand(payloads=["F7 b=1 2=time\n"], quiet=True)
        io.enqueue(cmd)
        io.shutdown()
        io.join(timeout=2)
        port.write.assert_called_once()

    def test_reset_toggles_dtr(self):
        port = MagicMock()
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        cmd = SerialCommand(reset=True)
        writer.enqueue(cmd)
        writer.shutdown()
        writer.join(timeout=2)
        # DTR should have been toggled: False then True
        assert port.dtr is True
        port.write.assert_not_called()

    def test_write_error_does_not_stop_loop(self):
        port = MagicMock()
        port.write.side_effect = [OSError("write failed"), None]
        port.flush.return_value = None
        io = self._make_io(port)
        io.enqueue(SerialCommand(payloads=["bad\n"]))
        io.enqueue(SerialCommand(payloads=["good\n"]))
        io.shutdown()
        io.join(timeout=2)
        assert not io.is_alive()

    def test_reads_response_after_write(self):
        port = MagicMock()
        port.readline.return_value = b"OK\n"
        io = self._make_io(port)
        # Override in_waiting: 5 bytes after write, then 0
        type(port).in_waiting = PropertyMock(side_effect=[5, 0])
        cmd = SerialCommand(payloads=["F7 b=1 1=Hello\n"], source="test")
        io.enqueue(cmd)
        io.shutdown()
        io.join(timeout=2)
        port.write.assert_called_once_with(b"F7 b=1 1=Hello\n")
        port.readline.assert_called_once()

    def test_initialized_triggers_callback(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"Arduino initialized\n"
        io = self._make_io(port, on_initialized=callback)
        # Override: bytes waiting after write, then 0 for the rest
        type(port).in_waiting = PropertyMock(side_effect=[6, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        callback.assert_called_once()
