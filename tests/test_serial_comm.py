"""Tests for serial communication (writer and reader)."""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, call, patch

from keypad6160.f7_protocol import SerialCommand
from keypad6160.serial_comm import SerialReader, SerialWriter


class TestSerialWriter:
    def test_single_payload(self):
        port = MagicMock()
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        cmd = SerialCommand(payloads=["F7 b=1 1=Hello\n"])
        writer.enqueue(cmd)
        writer.shutdown()
        writer.join(timeout=2)
        port.write.assert_called_once_with(b"F7 b=1 1=Hello\n")
        port.flush.assert_called_once()

    def test_multi_payload_with_delay(self):
        port = MagicMock()
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        cmd = SerialCommand(
            payloads=["F7 t=2 1=Armed\n", "F7 t=0\n"],
            delays=[0.01],  # Use tiny delay for test speed
        )
        writer.enqueue(cmd)
        writer.shutdown()
        writer.join(timeout=2)
        assert port.write.call_count == 2
        port.write.assert_any_call(b"F7 t=2 1=Armed\n")
        port.write.assert_any_call(b"F7 t=0\n")

    def test_shutdown_sentinel(self):
        port = MagicMock()
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        writer.shutdown()
        writer.join(timeout=2)
        assert not writer.is_alive()

    def test_quiet_does_not_crash(self):
        port = MagicMock()
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        cmd = SerialCommand(payloads=["F7 b=1 2=time\n"], quiet=True)
        writer.enqueue(cmd)
        writer.shutdown()
        writer.join(timeout=2)
        port.write.assert_called_once()

    def test_write_error_does_not_stop_loop(self):
        port = MagicMock()
        port.write.side_effect = [OSError("write failed"), None]
        port.flush.return_value = None
        writer = SerialWriter(port, min_delay=0.0)
        writer.start()
        writer.enqueue(SerialCommand(payloads=["bad\n"]))
        writer.enqueue(SerialCommand(payloads=["good\n"]))
        writer.shutdown()
        writer.join(timeout=2)
        assert not writer.is_alive()


class TestSerialReader:
    def test_initialized_triggers_callback(self):
        port = MagicMock()
        port.readline.side_effect = [
            b"Arduino initialized\n",
            b"",  # timeout
            OSError("stop"),  # break the loop
        ]
        writer = MagicMock()
        callback = MagicMock()
        reader = SerialReader(port, writer, on_initialized=callback)
        reader.daemon = True
        reader.start()
        time.sleep(0.2)
        callback.assert_called_once()
        # Writer should have been given a "Raspberry Pi OK" command
        writer.enqueue.assert_called()
        cmd = writer.enqueue.call_args_list[0][0][0]
        assert "Raspberry Pi OK" in cmd.payloads[0]

    def test_clock_update_on_timeout(self):
        port = MagicMock()
        # Return empty bytes (simulating timeout), then error to stop
        port.readline.side_effect = [b"", b"", OSError("stop")]
        writer = MagicMock()
        reader = SerialReader(port, writer)
        reader.daemon = True
        reader.start()
        time.sleep(0.3)
        # At least one clock update should have been enqueued
        assert writer.enqueue.call_count >= 1
