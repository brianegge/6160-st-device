"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # Serial
    serial_device: str = "/dev/ttyACM0"
    serial_baudrate: int = 115200
    serial_timeout: float = 1.0
    serial_min_delay: float = 0.1

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "keypad6160"
    mqtt_topic_prefix: str = "homeassistant/6160"

    # Logging
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Config:
        """Build Config from KEYPAD_* environment variables."""
        return cls(
            serial_device=os.environ.get("KEYPAD_SERIAL_DEVICE", cls.serial_device),
            serial_baudrate=int(os.environ.get("KEYPAD_SERIAL_BAUDRATE", cls.serial_baudrate)),
            serial_timeout=float(os.environ.get("KEYPAD_SERIAL_TIMEOUT", cls.serial_timeout)),
            serial_min_delay=float(os.environ.get("KEYPAD_SERIAL_MIN_DELAY", cls.serial_min_delay)),
            mqtt_host=os.environ.get("KEYPAD_MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("KEYPAD_MQTT_PORT", cls.mqtt_port)),
            mqtt_username=os.environ.get("KEYPAD_MQTT_USERNAME", cls.mqtt_username),
            mqtt_password=os.environ.get("KEYPAD_MQTT_PASSWORD", cls.mqtt_password),
            mqtt_client_id=os.environ.get("KEYPAD_MQTT_CLIENT_ID", cls.mqtt_client_id),
            mqtt_topic_prefix=os.environ.get("KEYPAD_MQTT_TOPIC_PREFIX", cls.mqtt_topic_prefix),
            log_level=os.environ.get("KEYPAD_LOG_LEVEL", cls.log_level),
        )
