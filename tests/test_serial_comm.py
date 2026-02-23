"""Tests for serial I/O (combined reader/writer)."""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, PropertyMock, call, patch

from keypad6160.config import Config
from keypad6160.f7_protocol import SerialCommand
from keypad6160.serial_comm import SerialIO


class TestSerialIO:
    def _make_io(self, port, **kwargs):
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
        port.timeout = 0.1
        io = SerialIO(port)
        io.start()
        cmd = SerialCommand(reset=True)
        io.enqueue(cmd)
        io.shutdown()
        io.join(timeout=2)
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
        # Bytes waiting after the short delay
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
        # Bytes waiting after the short delay
        type(port).in_waiting = PropertyMock(side_effect=[6, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        callback.assert_called_once()

    def test_handle_keys_single(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"KEYS_16[01] 0x02\n"
        io = self._make_io(port)
        io.on_keypress = callback
        type(port).in_waiting = PropertyMock(side_effect=[10, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        callback.assert_called_once_with("2")

    def test_handle_keys_multiple(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"KEYS_16[02] 0x01 0x05\n"
        io = self._make_io(port)
        io.on_keypress = callback
        type(port).in_waiting = PropertyMock(side_effect=[20, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        assert callback.call_count == 2
        callback.assert_any_call("1")
        callback.assert_any_call("5")

    def test_handle_keys_function_keys(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"KEYS_16[01] 0x1C\n"
        io = self._make_io(port)
        io.on_keypress = callback
        type(port).in_waiting = PropertyMock(side_effect=[10, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        callback.assert_called_once_with("A")

    def test_handle_keys_star_and_hash(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"KEYS_16[02] 0x0A 0x0B\n"
        io = self._make_io(port)
        io.on_keypress = callback
        type(port).in_waiting = PropertyMock(side_effect=[20, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        assert callback.call_count == 2
        callback.assert_any_call("*")
        callback.assert_any_call("#")

    def test_handle_keys_unknown_code_ignored(self):
        port = MagicMock()
        callback = MagicMock()
        port.readline.return_value = b"KEYS_16[01] 0xFF\n"
        io = self._make_io(port)
        io.on_keypress = callback
        type(port).in_waiting = PropertyMock(side_effect=[10, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        callback.assert_not_called()

    def test_handle_keys_no_callback(self):
        """KEYS message without callback set should not raise."""
        port = MagicMock()
        port.readline.return_value = b"KEYS_16[01] 0x02\n"
        io = self._make_io(port)
        type(port).in_waiting = PropertyMock(side_effect=[10, 0])
        io.enqueue(SerialCommand(payloads=["test\n"], source="test"))
        io.shutdown()
        io.join(timeout=2)
        assert not io.is_alive()

    @patch("keypad6160.serial_comm.serial.Serial")
    @patch("keypad6160.serial_comm.sleep")
    def test_reconnect_after_serial_error(self, mock_sleep, mock_serial_cls):
        """SerialIO reconnects when a SerialException occurs during write."""
        import serial as ser

        port = MagicMock()
        port.timeout = 0.1
        type(port).in_waiting = PropertyMock(return_value=0)
        # First write raises, triggering reconnect
        port.write.side_effect = ser.SerialException("disconnected")

        new_port = MagicMock()
        new_port.timeout = 0.1
        type(new_port).in_waiting = PropertyMock(return_value=0)
        mock_serial_cls.return_value = new_port

        config = Config(serial_device="/dev/ttyTest")
        io = SerialIO(port, config=config)
        io.start()

        io.enqueue(SerialCommand(payloads=["bad\n"]))
        # After reconnect, enqueue a good command and shutdown
        time.sleep(0.5)
        io.enqueue(SerialCommand(payloads=["good\n"]))
        io.shutdown()
        io.join(timeout=5)

        # Verify reconnect happened
        mock_serial_cls.assert_called_once()
        new_port.write.assert_called_with(b"good\n")
