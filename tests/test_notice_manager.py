"""Tests for the rotating notice manager."""

from __future__ import annotations

from unittest.mock import patch

from keypad6160.notice_manager import NoticeManager


class TestNoticeManager:
    def test_no_notices_returns_time(self):
        mgr = NoticeManager()
        with patch("keypad6160.notice_manager.strftime", return_value="Mon Feb 24 10:30"):
            assert mgr.get_current_display() == "Mon Feb 24 10:30"

    def test_single_notice_rotates_with_time(self):
        mgr = NoticeManager()
        mgr.set("Washer Done", notice_id="washer", ttl=0)
        with patch("keypad6160.notice_manager.strftime", return_value="Mon Feb 24 10:30"):
            assert mgr.get_current_display() == "Washer Done"
            assert mgr.get_current_display() == "Mon Feb 24 10:30"
            assert mgr.get_current_display() == "Washer Done"

    def test_multiple_notices_time_last(self):
        mgr = NoticeManager()
        mgr.set("Washer Done", notice_id="washer", ttl=0)
        mgr.set("Dryer Done", notice_id="dryer", ttl=0)
        with patch("keypad6160.notice_manager.strftime", return_value="Mon Feb 24 10:30"):
            assert mgr.get_current_display() == "Washer Done"
            assert mgr.get_current_display() == "Dryer Done"
            assert mgr.get_current_display() == "Mon Feb 24 10:30"
            # Wraps around
            assert mgr.get_current_display() == "Washer Done"

    def test_clear_by_id(self):
        mgr = NoticeManager()
        mgr.set("Washer Done", notice_id="washer", ttl=0)
        mgr.clear("washer")
        assert mgr.active_count == 0

    def test_clear_by_message_text(self):
        mgr = NoticeManager()
        mgr.set("Washer Done", notice_id="washer", ttl=0)
        mgr.clear("Washer Done")
        assert mgr.active_count == 0

    def test_clear_nonexistent_is_noop(self):
        mgr = NoticeManager()
        mgr.clear("nope")  # should not raise
        assert mgr.active_count == 0

    def test_set_plain_text_defaults_id_to_message(self):
        mgr = NoticeManager()
        mgr.set("Doorbell Ring")
        assert mgr.active_count == 1
        mgr.clear("Doorbell Ring")
        assert mgr.active_count == 0

    def test_transient_notice_expires(self):
        mgr = NoticeManager()
        with patch("keypad6160.notice_manager.time", return_value=1000.0):
            mgr.set("Timer Done", ttl=60)
            assert mgr.active_count == 1
        # Advance past expiry
        with patch("keypad6160.notice_manager.time", return_value=1061.0):
            assert mgr.active_count == 0

    def test_persistent_notice_does_not_expire(self):
        mgr = NoticeManager()
        with patch("keypad6160.notice_manager.time", return_value=1000.0):
            mgr.set("Washer Done", notice_id="washer", ttl=0)
        with patch("keypad6160.notice_manager.time", return_value=9999.0):
            assert mgr.active_count == 1

    def test_update_existing_notice(self):
        mgr = NoticeManager()
        mgr.set("Washer Running", notice_id="washer", ttl=0)
        mgr.set("Washer Done", notice_id="washer", ttl=0)
        assert mgr.active_count == 1
        with patch("keypad6160.notice_manager.strftime", return_value="time"):
            assert mgr.get_current_display() == "Washer Done"

    def test_expired_notices_pruned_during_rotation(self):
        mgr = NoticeManager()
        with patch("keypad6160.notice_manager.time", return_value=1000.0):
            mgr.set("Temp Notice", ttl=10)
            mgr.set("Permanent", notice_id="perm", ttl=0)
        with patch("keypad6160.notice_manager.time", return_value=1011.0):
            with patch("keypad6160.notice_manager.strftime", return_value="time"):
                # Only Permanent and time should be in rotation
                results = [mgr.get_current_display() for _ in range(3)]
                assert "Temp Notice" not in results
                assert "Permanent" in results
                assert "time" in results
