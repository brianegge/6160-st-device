"""F7 command builder for the Arduino2keypad serial protocol.

F7 command format:
  F7[A] z=FC t=0 c=1 r=0 a=0 s=0 p=1 b=1 1=<16 chars> 2=<16 chars>

Parameters:
  z - zone             (byte)
  t - tone             (nibble) 0=Nothing, 1=One Chime+Disarmed, 2=Two Chimes+Armed,
                                3=Three Chimes, 4=Fast Beep (alarm), 5-6=Pulse Warning, 7=Constant
  c - chime/voice      (bool) 0=voice on, 1=voice off
  r - ready            (bool)
  a - arm-away         (bool)
  s - arm-stay         (bool)
  p - power-on         (bool)
  b - lcd-backlight-on (bool)
  1 - line1 text       (16 chars)
  2 - line2 text       (16 chars)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SerialCommand:
    """One or more serial payloads to send atomically."""

    payloads: list[str] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    quiet: bool = False
    reset: bool = False
    source: str = ""


# Maps well-known alarm text to F7 flag strings.
ALARM_STATES: dict[str, str] = {
    "Armed Away": "r=0 a=1 s=0 b=0 c=0 t=2 ",
    "Armed Stay": "r=0 a=0 s=1 b=1 c=0 t=2 ",
    "Disarmed": "r=1 a=0 s=0 b=1 c=0 t=1 ",
    "Raspberry Pi OK": "r=1 a=0 s=0 b=1 c=1 t=0 ",
}

_ABBREVIATIONS: list[tuple[str, str]] = [
    ("Window", "Win"),
    ("Office", "Offc"),
    ("Basement", "Bsmt"),
    ("Garage", "Grg"),
    ("Right", "Rt"),
    ("Left", "Lf"),
]


def shorten(msg: str) -> str:
    """Progressively abbreviate *msg* to fit a 16-character LCD line."""
    for long, short in _ABBREVIATIONS:
        if len(msg) <= 16:
            break
        msg = msg.replace(long, short)
    return msg


def build_message(line_no: int | str, text: str, quiet: bool = False, source: str = "") -> SerialCommand:
    """Build an F7 command for a known alarm state or generic text.

    If the text matches a known alarm state, the appropriate flags and tone
    are applied.  When a tone > 0 is set, a follow-up command resets the tone
    after a 1.5 s delay so the keypad doesn't beep indefinitely.
    """
    args = ALARM_STATES.get(text, "b=1 c=1 ")
    payload = f"F7 {args}{line_no}={text:<16}\n"

    # Check if a non-zero tone was set (t=1..9)
    has_tone = any(
        part.startswith("t=") and part[2:].isdigit() and int(part[2:]) > 0
        for part in args.split()
    )

    if has_tone:
        reset_payload = "F7 t=0\n"
        return SerialCommand(
            payloads=[payload, reset_payload],
            delays=[1.5],
            quiet=quiet,
            source=source,
        )
    return SerialCommand(payloads=[payload], quiet=quiet, source=source)


def build_raw_message(
    line_no: int | str,
    text: str,
    backlight: str = "1",
    source: str = "",
) -> SerialCommand:
    """Build an F7 command with explicit parameters (no alarm-state lookup)."""
    text = shorten(text)
    args = f"b={backlight} "
    payload = f"F7 {args}{line_no}={text:16.16}\n"
    return SerialCommand(payloads=[payload], source=source)


def build_backlight_command(on: bool, source: str = "") -> SerialCommand:
    """Build an F7 command that only toggles the LCD backlight."""
    payload = f"F7 b={1 if on else 0}\n"
    return SerialCommand(payloads=[payload], source=source)


def build_reset_command() -> SerialCommand:
    """Build a command that resets the Arduino by toggling DTR."""
    return SerialCommand(reset=True, source="reset")
