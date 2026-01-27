"""Tests for F7 protocol command building."""

from keypad6160.f7_protocol import (
    SerialCommand,
    build_backlight_command,
    build_message,
    build_raw_message,
    shorten,
)


class TestShorten:
    def test_short_text_unchanged(self):
        assert shorten("Front Door") == "Front Door"

    def test_window_abbreviated(self):
        assert shorten("Basement Window Open") == "Bsmt Win Open"

    def test_office_abbreviated(self):
        assert shorten("Upstairs Office Rm") == "Upstairs Offc Rm"

    def test_garage_abbreviated(self):
        # "Right Garage Door" (17 chars) -> "Right Grg Door" (14 chars), fits
        assert shorten("Right Garage Door") == "Right Grg Door"

    def test_left_abbreviated(self):
        # "Left Basement Window" (20) -> "Left Bsmt Win" (13), fits after Basement+Window
        assert shorten("Left Basement Window") == "Left Bsmt Win"

    def test_already_fits(self):
        assert shorten("1234567890123456") == "1234567890123456"


class TestBuildMessage:
    def test_armed_away(self):
        cmd = build_message(1, "Armed Away")
        assert len(cmd.payloads) == 2
        assert "a=1" in cmd.payloads[0]
        assert "t=2" in cmd.payloads[0]
        assert "1=Armed Away" in cmd.payloads[0]
        assert cmd.payloads[1] == "F7 t=0\n"
        assert cmd.delays == [1.5]

    def test_armed_stay(self):
        cmd = build_message(1, "Armed Stay")
        assert len(cmd.payloads) == 2
        assert "s=1" in cmd.payloads[0]
        assert "t=2" in cmd.payloads[0]

    def test_disarmed(self):
        cmd = build_message(1, "Disarmed")
        assert len(cmd.payloads) == 2
        assert "r=1" in cmd.payloads[0]
        assert "t=1" in cmd.payloads[0]
        assert cmd.payloads[1] == "F7 t=0\n"

    def test_raspberry_pi_ok_no_tone(self):
        cmd = build_message(1, "Raspberry Pi OK")
        assert len(cmd.payloads) == 1
        assert "t=0" in cmd.payloads[0]

    def test_generic_text(self):
        cmd = build_message(2, "Hello World")
        assert len(cmd.payloads) == 1
        assert "b=1 c=1" in cmd.payloads[0]
        assert "2=Hello World" in cmd.payloads[0]

    def test_quiet_flag(self):
        cmd = build_message(2, "test", quiet=True)
        assert cmd.quiet is True

    def test_line_number_as_string(self):
        cmd = build_message("2", "Clock Text")
        assert "2=Clock Text" in cmd.payloads[0]


class TestBuildRawMessage:
    def test_basic(self):
        cmd = build_raw_message(1, "Hello")
        assert len(cmd.payloads) == 1
        assert "b=1" in cmd.payloads[0]
        assert "1=Hello" in cmd.payloads[0]

    def test_backlight_off(self):
        cmd = build_raw_message(1, "Msg", backlight="0")
        assert "b=0" in cmd.payloads[0]

    def test_long_text_shortened(self):
        cmd = build_raw_message(1, "Left Basement Window")
        assert "Left Bsmt Win" in cmd.payloads[0]

    def test_text_truncated_to_16(self):
        cmd = build_raw_message(1, "1234567890ABCDEFXYZ")
        # The format spec :16.16 truncates to 16 chars
        payload = cmd.payloads[0]
        # Extract the text after "1="
        idx = payload.index("1=") + 2
        text_part = payload[idx:].rstrip("\n")
        assert len(text_part) == 16


class TestBuildBacklightCommand:
    def test_on(self):
        cmd = build_backlight_command(True)
        assert cmd.payloads == ["F7 b=1\n"]

    def test_off(self):
        cmd = build_backlight_command(False)
        assert cmd.payloads == ["F7 b=0\n"]
