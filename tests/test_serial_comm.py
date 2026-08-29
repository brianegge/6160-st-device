"""Tests for serial I/O (combined reader/writer)."""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

from keypad6160.config import Config
from keypad6160.f7_protocol import SerialCommand
from keypad6160.serial_comm import SerialIO, _CoalescingQueue


class TestSerialIO:
    @pytest.fixture(autouse=True)
    def _no_write_throttle(self, monkeypatch):
        """Disable the inter-write throttle by default so threaded tests
        don't slow down; throttle tests override it locally."""
        monkeypatch.setattr("keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 0.0)
        monkeypatch.setattr("keypad6160.serial_comm._THROTTLE_POLL_S", 0.01)
        monkeypatch.setattr("keypad6160.serial_comm._POST_RESET_HOLD_S", 0.0)
        monkeypatch.setattr("keypad6160.serial_comm._LINE2_TICK_INTERVAL_S", 0.0)

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
        # Bare flag command gets display lines attached
        second_write = port.write.call_args_list[1][0][0].decode()
        assert "t=0" in second_write
        assert "1=" in second_write
        assert "2=" in second_write

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

    def test_two_errs_within_window_trigger_reset(self):
        """Two ERR_ lines within the strike window should trigger one DTR
        auto-reset.

        monotonic is patched to a tiny value to verify the reset is never
        blocked by the cooldown sentinel (regression: 0.0 init blocked the
        first reset on freshly-booted hosts).
        """
        port = MagicMock()
        port.readline.side_effect = [
            b"ERR_FMT: garble 1\n",
            b"ERR_FMT: garble 2\n",
        ]
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0):
            io = self._make_io(port)
            type(port).in_waiting = PropertyMock(side_effect=[20, 0, 20, 0])
            with patch("keypad6160.serial_comm.monotonic", return_value=5.0):
                io.enqueue(SerialCommand(payloads=["a\n"], source="test"))
                io.enqueue(SerialCommand(payloads=["b\n"], source="test"))
                io.shutdown()
                io.join(timeout=5)
        # DTR toggled low then high (the auto-reset) — final state is True.
        assert port.dtr is True

    def test_isolated_err_line_does_not_reset(self):
        """A single ERR_ line should not trigger a reset; isolated garbles
        self-recover on the Arduino and the DTR reset itself causes the keypad
        to audibly beep during the reboot window."""
        port = MagicMock()
        port.readline.return_value = b"ERR_FMT: lonely\n"
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0):
            io = self._make_io(port)
            type(port).in_waiting = PropertyMock(side_effect=[20, 0])
            with patch.object(io, "_reset_device") as mock_reset:
                io.enqueue(SerialCommand(payloads=["a\n"], source="test"))
                io.shutdown()
                io.join(timeout=5)
                mock_reset.assert_not_called()

    def test_errs_outside_window_do_not_reset(self):
        """Two ERR_ lines further apart than the strike window are treated
        as independent isolated garbles and must not reset."""
        io = SerialIO(MagicMock())
        with patch(
            "keypad6160.serial_comm.monotonic",
            side_effect=[100.0, 300.0],
        ), patch.object(io, "_reset_device") as mock_reset:
            io._handle_line("ERR_FMT: first")
            io._handle_line("ERR_FMT: second")
            mock_reset.assert_not_called()

    def test_err_line_enqueues_display_refresh(self):
        """Every ERR_ line should enqueue a quiet t=0 refresh so a latched
        tone (t=4 is a continuous fast beep) or stale text clears without
        waiting for the next regular update."""
        port = MagicMock()
        io = SerialIO(port)  # not started — inspect the queue directly
        io._handle_line("ERR_FMT: garble")
        items = io._queue._items
        assert len(items) == 1
        cmd = items[0]
        assert cmd.payloads == ["F7 t=0\n"]
        assert cmd.quiet is True
        assert cmd.priority is True
        assert cmd.coalesce_key == "refresh"

    def test_err_line_auto_reset_has_cooldown(self):
        """A second ERR_ pair arriving within the 60 s cooldown after a reset
        should not trigger another reset."""
        io = SerialIO(MagicMock())
        with patch(
            "keypad6160.serial_comm.monotonic",
            side_effect=[100.0, 110.0, 120.0, 130.0],
        ), patch.object(io, "_reset_device") as mock_reset:
            io._handle_line("ERR_FMT: 1")
            io._handle_line("ERR_FMT: 2")  # pairs with 1 -> reset #1
            io._handle_line("ERR_FMT: 3")  # isolated (window cleared by reset)
            io._handle_line("ERR_FMT: 4")  # pairs with 3, but cooldown blocks
            assert mock_reset.call_count == 1

    def test_reset_clears_strike_window(self):
        """A garble after a reset must not pair with one from before the
        reset — a fresh pair is required."""
        io = SerialIO(MagicMock())
        with patch(
            "keypad6160.serial_comm.monotonic",
            side_effect=[100.0, 110.0, 200.0],
        ), patch.object(io, "_reset_device") as mock_reset:
            io._handle_line("ERR_FMT: 1")
            io._handle_line("ERR_FMT: 2")  # pairs with 1 -> reset #1
            io._handle_line("ERR_FMT: 3")  # past cooldown, but isolated
            assert mock_reset.call_count == 1

    def test_err_line_auto_reset_after_cooldown(self):
        """A fresh ERR_ pair after the cooldown elapses triggers a second
        reset."""
        io = SerialIO(MagicMock())
        with patch(
            "keypad6160.serial_comm.monotonic",
            side_effect=[100.0, 110.0, 200.0, 210.0],
        ), patch.object(io, "_reset_device") as mock_reset:
            io._handle_line("ERR_FMT: 1")
            io._handle_line("ERR_FMT: 2")  # pairs with 1 -> reset #1
            io._handle_line("ERR_FMT: 3")
            io._handle_line("ERR_FMT: 4")  # pairs with 3, past cooldown
            assert mock_reset.call_count == 2

    def test_throttle_spaces_out_writes(self):
        """Two back-to-back commands must be separated by at least the
        minimum write interval."""
        times: list[float] = []
        port = MagicMock()
        port.write.side_effect = lambda _b: times.append(time.monotonic())
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 0.3
        ):
            io = self._make_io(port)
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            io.enqueue(SerialCommand(payloads=["F7 2=Two\n"], coalesce_key="line:2"))
            io.shutdown()
            io.join(timeout=5)
        assert len(times) == 2
        assert times[1] - times[0] >= 0.29

    @staticmethod
    def _wait_until(predicate, timeout: float = 5.0) -> bool:
        """Poll *predicate* until it returns True or *timeout* elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def test_throttled_burst_coalesces_to_latest(self):
        """Same-key updates arriving during the throttle wait must collapse
        to the newest one instead of being sent frame by frame."""
        port = MagicMock()
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 0.5
        ):
            io = self._make_io(port)
            io.enqueue(SerialCommand(payloads=["F7 2=First\n"], coalesce_key="line:2"))
            # First is written; the throttle window is now active.
            assert self._wait_until(lambda: port.write.call_count == 1)
            io.enqueue(SerialCommand(payloads=["F7 2=Second\n"], coalesce_key="line:2"))
            io.enqueue(SerialCommand(payloads=["F7 2=Third\n"], coalesce_key="line:2"))
            # Window elapses; the latest survivor is written.
            assert self._wait_until(lambda: port.write.call_count == 2)
            io.shutdown()
            io.join(timeout=5)
        writes = [c[0][0].decode() for c in port.write.call_args_list]
        assert len(writes) == 2
        assert "First" in writes[0]
        assert "Third" in writes[1]

    def test_notice_updates_tick_during_throttle(self):
        """Clock/notice updates must not stall while commands are being
        throttled — during a sustained burst the queue never drains, so the
        idle-branch _update_line2 call alone would never run."""
        port = MagicMock()
        nm = MagicMock()
        nm.get_current_display.return_value = "Sat Aug 29 09:00"
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 0.3
        ):
            io = self._make_io(port)
            io._notice_manager = nm
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            assert self._wait_until(lambda: port.write.call_count == 1)
            io.enqueue(SerialCommand(payloads=["F7 1=Two\n"], coalesce_key="line:1"))
            # Both the held command and the notice update get written.
            assert self._wait_until(lambda: port.write.call_count == 3)
            io.shutdown()
            io.join(timeout=5)
        writes = [c[0][0].decode() for c in port.write.call_args_list]
        assert any("Sat Aug 29 09:00" in w for w in writes)

    def test_err_refresh_bypasses_throttle(self):
        """A garble during an active throttle window must be cleared
        immediately — the priority err-refresh cannot wait out the window,
        or a latched t=4 fast beep persists for seconds.  Runs with the
        throttle active and ERR handling through the real read path."""
        port = MagicMock()
        port.readline.return_value = b"ERR_FMT: garble\n"
        reads = iter([20])
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 5.0
        ):
            io = self._make_io(port)
            type(port).in_waiting = PropertyMock(
                side_effect=lambda *a: next(reads, 0)
            )
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            # The write garbles (ERR read in its response drain); the
            # refresh must be written well before the 5 s window expires.
            assert self._wait_until(lambda: port.write.call_count == 2, timeout=2)
            io.shutdown()
            io.join(timeout=5)
        assert "t=0" in port.write.call_args_list[1][0][0].decode()

    def test_reset_jumps_ahead_of_held_command(self):
        """A reset enqueued while a display command is being throttled must
        execute before that held command, not wait behind it."""
        port = MagicMock()
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 5.0
        ):
            io = self._make_io(port)
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            assert self._wait_until(lambda: port.write.call_count == 1)
            io.enqueue(SerialCommand(payloads=["F7 2=Two\n"], coalesce_key="line:2"))
            with patch.object(io, "_reset_device") as mock_reset:
                io.enqueue(SerialCommand(reset=True))
                assert self._wait_until(lambda: mock_reset.called, timeout=2)
                # The held display command must not have been written first.
                assert port.write.call_count == 1
            io._next_write_ok_monotonic = 0.0  # release the hold for a clean join
            io.shutdown()
            io.join(timeout=5)

    def test_reset_arms_post_reset_write_hold(self):
        """After a DTR reset the next write must wait out the bootloader
        window instead of being sent into it and lost."""
        port = MagicMock()
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._POST_RESET_HOLD_S", 0.4
        ):
            io = self._make_io(port)
            start = time.monotonic()
            io.enqueue(SerialCommand(reset=True))
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            assert self._wait_until(lambda: port.write.call_count == 1)
            elapsed = time.monotonic() - start
            io.shutdown()
            io.join(timeout=5)
        # 0.1 s DTR toggle + 0.4 s hold, minus scheduling slop.
        assert elapsed >= 0.45

    def test_multi_payload_respects_min_interval(self):
        """The minimum frame gap also applies between the payloads of one
        command (tone + tone-reset)."""
        times: list[float] = []
        port = MagicMock()
        port.write.side_effect = lambda _b: times.append(time.monotonic())
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 0.3
        ):
            io = self._make_io(port)
            io.enqueue(SerialCommand(
                payloads=["F7 t=2\n", "F7 t=0\n"],
                delays=[0.05],
                coalesce_key="tone",
            ))
            io.shutdown()
            io.join(timeout=5)
        assert len(times) == 2
        assert times[1] - times[0] >= 0.29

    def test_update_line2_skips_when_line2_pending(self):
        """A background clock tick must never coalesce away a pending
        explicit line-2 command (e.g. a throttled user MQTT message)."""
        io = SerialIO(MagicMock())  # not started
        nm = MagicMock()
        io._notice_manager = nm
        held = SerialCommand(payloads=["F7 2=User Msg\n"], coalesce_key="line:2")
        io._queue.put(held)
        io._update_line2()
        nm.get_current_display.assert_not_called()
        assert io._queue._items == [held]

    def test_update_line2_rate_limited(self):
        """get_current_display() advances the notice rotation per call, so
        rapid polling (the 10 Hz throttle wait) must not reach it more than
        once per tick interval."""
        io = SerialIO(MagicMock())  # not started
        nm = MagicMock()
        nm.get_current_display.return_value = "Sat Aug 29 09:00"
        io._notice_manager = nm
        with patch("keypad6160.serial_comm._LINE2_TICK_INTERVAL_S", 60.0):
            io._update_line2()
            io._update_line2()
            io._update_line2()
        assert nm.get_current_display.call_count == 1

    def test_reset_command_bypasses_throttle(self):
        """A DTR reset must not wait out the write interval."""
        port = MagicMock()
        with patch("keypad6160.serial_comm._POST_WRITE_DELAY_S", 0), patch(
            "keypad6160.serial_comm._MIN_WRITE_INTERVAL_S", 5.0
        ):
            io = self._make_io(port)
            io.enqueue(SerialCommand(payloads=["F7 1=One\n"], coalesce_key="line:1"))
            io.enqueue(SerialCommand(reset=True))
            io.shutdown()
            io.join(timeout=2)
        assert not io.is_alive()
        assert port.write.call_count == 1
        assert port.dtr is True

    def test_err_in_middle_of_line_ignored(self):
        """Only lines that *start* with ERR_ should trigger an auto-reset."""
        port = MagicMock()
        port.readline.return_value = b"<< some prefix ERR_FMT not at start\n"
        io = self._make_io(port)
        type(port).in_waiting = PropertyMock(side_effect=[40, 0])
        with patch.object(io, "_reset_device") as mock_reset:
            io.enqueue(SerialCommand(payloads=["F7 b=1 1=Hello\n"], source="test"))
            io.shutdown()
            io.join(timeout=2)
            mock_reset.assert_not_called()

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

    def test_coalescing_drops_stale_line_messages(self):
        """Rapid MQTT updates for the same line should coalesce to the latest."""
        port = MagicMock()
        io = self._make_io(port)
        # Enqueue three line-2 messages rapidly; only the last should be sent
        io.enqueue(SerialCommand(payloads=["F7 b=1 2=First\n"], coalesce_key="line:2"))
        io.enqueue(SerialCommand(payloads=["F7 b=1 2=Second\n"], coalesce_key="line:2"))
        io.enqueue(SerialCommand(payloads=["F7 b=1 2=Third\n"], coalesce_key="line:2"))
        io.shutdown()
        io.join(timeout=2)
        # Only "Third" should have been written
        port.write.assert_called_once_with(b"F7 b=1 2=Third\n")

    def test_coalescing_preserves_different_keys(self):
        """Commands with different coalesce_keys are not dropped."""
        port = MagicMock()
        io = self._make_io(port)
        io.enqueue(SerialCommand(payloads=["F7 b=1 1=Line1\n"], coalesce_key="line:1"))
        io.enqueue(SerialCommand(payloads=["F7 b=1 2=Line2\n"], coalesce_key="line:2"))
        io.shutdown()
        io.join(timeout=2)
        assert port.write.call_count == 2

    def test_ensure_both_lines_on_line2_only(self):
        """A line-2-only command should be rewritten to include line 1."""
        port = MagicMock()
        io = self._make_io(port)
        # Set line 1 first, then update line 2 only
        io.enqueue(SerialCommand(payloads=["F7 b=1 c=1 1=Raspberry Pi OK \n"]))
        io.enqueue(SerialCommand(payloads=["F7 b=1 c=1 2=Mon Feb 23  6:30\n"]))
        io.shutdown()
        io.join(timeout=2)
        # The second write should contain both 1= and 2=
        last_write = port.write.call_args_list[-1][0][0].decode()
        assert "1=Raspberry Pi OK " in last_write
        assert "2=Mon Feb 23  6:30" in last_write

    def test_ensure_both_lines_attaches_display_to_bare_flags(self):
        """Bare flag commands (e.g. tone reset) get current display lines attached."""
        port = MagicMock()
        io = self._make_io(port)
        io.enqueue(SerialCommand(payloads=["F7 t=0\n"]))
        io.shutdown()
        io.join(timeout=2)
        written = port.write.call_args[0][0].decode()
        assert "t=0" in written
        assert "1=" in written
        assert "2=" in written

    def test_coalescing_preserves_no_key_commands(self):
        """Commands without a coalesce_key are never dropped."""
        port = MagicMock()
        io = self._make_io(port)
        io.enqueue(SerialCommand(payloads=["F7 t=1\n"]))
        io.enqueue(SerialCommand(payloads=["F7 t=2\n"]))
        io.shutdown()
        io.join(timeout=2)
        assert port.write.call_count == 2

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
