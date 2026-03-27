"""HomeAssistant MQTT auto-discovery configuration messages."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from keypad6160 import __version__

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

    # Status binary sensor (uses LWT)
    messages.append((
        "homeassistant/binary_sensor/keypad_6160_status/config",
        json.dumps({
            "name": "Keypad Status",
            "unique_id": "keypad_6160_status",
            "state_topic": f"{prefix}/status",
            "payload_on": "online",
            "payload_off": "offline",
            "device_class": "connectivity",
            "device": device_info,
        }),
    ))

    # Version sensor
    messages.append((
        "homeassistant/sensor/keypad_6160_version/config",
        json.dumps({
            "name": "Keypad Version",
            "unique_id": "keypad_6160_version",
            "state_topic": f"{prefix}/version/state",
            "availability_topic": f"{prefix}/status",
            "entity_category": "diagnostic",
            "icon": "mdi:tag",
            "device": device_info,
        }),
    ))

    # Uptime sensor (publishes start time as ISO timestamp;
    # HA renders timestamp sensors as "X hours ago" automatically)
    messages.append((
        "homeassistant/sensor/keypad_6160_uptime/config",
        json.dumps({
            "name": "Keypad Uptime",
            "unique_id": "keypad_6160_uptime",
            "state_topic": f"{prefix}/uptime/state",
            "device_class": "timestamp",
            "availability_topic": f"{prefix}/status",
            "device": device_info,
        }),
    ))

    # Firmware update
    messages.append((
        "homeassistant/update/keypad_6160_firmware/config",
        json.dumps({
            "name": "Firmware",
            "unique_id": "keypad_6160_firmware",
            "state_topic": f"{prefix}/update/state",
            "availability_topic": f"{prefix}/status",
            "device": device_info,
            "entity_picture": "https://brands.home-assistant.io/_/mqtt/icon.png",
            "release_url": "https://github.com/brianegge/6160-st-device/releases",
        }),
    ))

    return messages
