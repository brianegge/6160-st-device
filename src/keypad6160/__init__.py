"""MQTT service for Honeywell 6160 alarm keypad."""

import subprocess


def _get_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip().lstrip("v")
    except Exception:
        return "0.0.0"


__version__ = _get_version()
