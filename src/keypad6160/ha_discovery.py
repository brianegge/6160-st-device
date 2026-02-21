"""HomeAssistant MQTT auto-discovery configuration messages."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keypad6160.config import Config


def build_discovery_messages(config: Config) -> list[tuple[str, str]]:
    """Return a list of (topic, json_payload) for HA MQTT discovery."""
    prefix = config.mqtt_topic_prefix
    device_info = {
        "identifiers": ["keypad_6160"],
        "name": "6160 Keypad",
        "manufacturer": "Honeywell",
        "model": "6160",
    }
    messages: list[tuple[str, str]] = []

    # Mode selector
    messages.append((
        "homeassistant/select/keypad_6160_mode/config",
        json.dumps({
            "name": "Keypad Mode",
            "unique_id": "keypad_6160_mode",
            "command_topic": f"{prefix}/mode/set",
            "state_topic": f"{prefix}/mode/state",
            "options": ["Armed Away", "Armed Stay", "Disarmed"],
            "availability_topic": f"{prefix}/status",
            "device": device_info,
        }),
    ))

    # Backlight
    messages.append((
        "homeassistant/light/keypad_6160_backlight/config",
        json.dumps({
            "name": "Keypad Backlight",
            "unique_id": "keypad_6160_backlight",
            "command_topic": f"{prefix}/backlight/set",
            "state_topic": f"{prefix}/backlight/state",
            "availability_topic": f"{prefix}/status",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": device_info,
        }),
    ))

    # Text message input
    messages.append((
        "homeassistant/text/keypad_6160_message/config",
        json.dumps({
            "name": "Keypad Message",
            "unique_id": "keypad_6160_message",
            "command_topic": f"{prefix}/message/1/set",
            "availability_topic": f"{prefix}/status",
            "max": 16,
            "device": device_info,
        }),
    ))

    # Reset button
    messages.append((
        "homeassistant/button/keypad_6160_reset/config",
        json.dumps({
            "name": "Keypad Reset",
            "unique_id": "keypad_6160_reset",
            "command_topic": f"{prefix}/reset/set",
            "availability_topic": f"{prefix}/status",
            "device_class": "restart",
            "device": device_info,
        }),
    ))

    # Keypress event
    messages.append((
        "homeassistant/event/keypad_6160_keypress/config",
        json.dumps({
            "name": "Keypress",
            "unique_id": "keypad_6160_keypress",
            "state_topic": f"{prefix}/key/event",
            "event_types": ["key_press"],
            "availability_topic": f"{prefix}/status",
            "device": device_info,
        }),
    ))

    return messages
