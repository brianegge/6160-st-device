"""MQTT service for Honeywell 6160 alarm keypad."""

import importlib.metadata
import subprocess


def _get_version() -> str:
    try:
        return importlib.metadata.version("keypad6160")
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip().lstrip("v")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "0.0.0"


__version__ = _get_version()
