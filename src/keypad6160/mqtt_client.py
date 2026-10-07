"""Paho MQTT client wrapper with subscriptions and callbacks."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

import paho.mqtt.client as mqtt

from keypad6160 import __version__
from keypad6160.f7_protocol import (
    build_backlight_command,
    build_message,
    build_raw_message,
    build_reset_command,
    build_tone_command,
)

if TYPE_CHECKING:
    from keypad6160.config import Config
    from keypad6160.notice_manager import NoticeManager
    from keypad6160.serial_comm import SerialIO

log = logging.getLogger(__name__)


class KeypadMqttClient:
    """Manages MQTT connection, subscriptions, and dispatches serial commands."""

    def __init__(self, config: Config, writer: SerialIO, notices: NoticeManager | None = None) -> None:
        self._config = config
        self._discovery_messages: list[tuple[str, str]] = []
        self._first_connect = True
        self._ha_status_topic = "homeassistant/status"
        self._writer = writer
        self._notices = notices
        self._prefix = config.mqtt_topic_prefix
        # Backlight is restored from the retained backlight/state topic on
        # start; see _restore_backlight.
        self._desired_backlight: str | None = None
        self._backlight_restored = False
        self._arduino_ready = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.mqtt_client_id,
        )
        if config.mqtt_username:
            self._client.username_pw_set(config.mqtt_username, config.mqtt_password)

        # Last Will and Testament
        self._client.will_set(
            f"{self._prefix}/status",
            payload="offline",
            qos=1,
            retain=True,
        )

        self._start_time = time.monotonic()
        self._uptime_timer: threading.Timer | None = None

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    # -- Public API --------------------------------------------------------

    def connect(self) -> None:
        """Connect to the broker (non-blocking)."""
        self._client.connect(self._config.mqtt_host, self._config.mqtt_port)

    def loop_forever(self) -> None:
        """Blocking network loop.  Call after connect()."""
        self._client.loop_forever()

    def disconnect(self) -> None:
        """Publish offline status and disconnect."""
        if self._uptime_timer:
            self._uptime_timer.cancel()
        self._publish(f"{self._prefix}/status", "offline", retain=True)
        self._client.disconnect()

    def publish_discovery(self, discovery_messages: list[tuple[str, str]]) -> None:
        """Publish a list of (topic, json_payload) discovery messages."""
        self._discovery_messages = discovery_messages
        for topic, payload in discovery_messages:
            self._publish(topic, payload, retain=True)

    # -- Callbacks ---------------------------------------------------------

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        rc: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        if rc.is_failure:
            log.error("MQTT connect failed: %s", rc)
            return

        log.info("Connected to MQTT broker")

        # Re-publish discovery on reconnect (skip first connect —
        # __main__.py seeds discovery messages after connect()).
        if self._first_connect:
            self._first_connect = False
        elif self._discovery_messages:
            self.publish_discovery(self._discovery_messages)

        # Publish online status and version
        self._publish(f"{self._prefix}/status", "online", retain=True)
        self._publish(f"{self._prefix}/version/state", __version__, retain=True)

        self._start_uptime_publishing()

        # Display Home Assistant + version on keypad
        self._writer.enqueue(build_message(1, "Home Assistant", source="mqtt:connect"))
        self._writer.enqueue(build_raw_message(2, __version__, source="mqtt:connect"))

        # Subscribe to command topics
        topics = [
            (self._ha_status_topic, 1),
            (f"{self._prefix}/mode/set", 1),
            (f"{self._prefix}/message/set", 1),
            (f"{self._prefix}/message/1/set", 1),
            (f"{self._prefix}/message/2/set", 1),
            (f"{self._prefix}/backlight/set", 1),
            # Our own retained state, republished by the broker on connect:
            # this is how the backlight survives a restart.
            (f"{self._prefix}/backlight/state", 1),
            (f"{self._prefix}/reset/set", 1),
            (f"{self._prefix}/tone/set", 1),
            (f"{self._prefix}/notice/set", 1),
            (f"{self._prefix}/notice/clear", 1),
        ]
        client.subscribe(topics)
        log.info("Subscribed to %d topics", len(topics))

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        msg: mqtt.MQTTMessage,
    ) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        log.info("MQTT << %s: %s", topic, payload)

        try:
            if topic == self._ha_status_topic:
                self._handle_ha_status(payload)
            elif topic == f"{self._prefix}/mode/set":
                self._handle_mode(payload)
            elif topic == f"{self._prefix}/message/set":
                self._handle_json_message(payload)
            elif topic == f"{self._prefix}/message/1/set":
                self._handle_line_message(1, payload)
            elif topic == f"{self._prefix}/message/2/set":
                self._handle_line_message(2, payload)
            elif topic == f"{self._prefix}/backlight/set":
                self._handle_backlight(payload)
            elif topic == f"{self._prefix}/backlight/state":
                self._handle_backlight_state(payload, retained=bool(msg.retain))
            elif topic == f"{self._prefix}/tone/set":
                self._handle_tone(payload)
            elif topic == f"{self._prefix}/reset/set":
                self._handle_reset()
            elif topic == f"{self._prefix}/notice/set":
                self._handle_notice_set(payload)
            elif topic == f"{self._prefix}/notice/clear":
                self._handle_notice_clear(payload)
            else:
                log.warning("Unhandled topic: %s", topic)
        except Exception:
            log.exception("Error handling MQTT message on %s", topic)

    # -- Handlers ----------------------------------------------------------

    def _handle_ha_status(self, payload: str) -> None:
        """Re-publish discovery and state when Home Assistant comes online."""
        if payload == "online":
            log.info("Home Assistant birth message received, republishing discovery")
            self.publish_discovery(self._discovery_messages)
            self._publish(f"{self._prefix}/status", "online", retain=True)
            self._publish(f"{self._prefix}/version/state", __version__, retain=True)

    def _handle_mode(self, mode: str) -> None:
        cmd = build_message(1, mode, source="mqtt:mode")
        self._writer.enqueue(cmd)
        self._publish(f"{self._prefix}/mode/state", mode, retain=True)

    def _handle_json_message(self, raw: str) -> None:
        data = json.loads(raw)
        text = data.get("text", "")
        line_no = data.get("line_no", "1")
        backlight = data.get("backlight", "1")
        cmd = build_raw_message(line_no, text, backlight=backlight, source="mqtt:json")
        self._writer.enqueue(cmd)

    def _handle_line_message(self, line_no: int, text: str) -> None:
        cmd = build_message(line_no, text, source="mqtt:line")
        self._writer.enqueue(cmd)

    def _handle_tone(self, payload: str) -> None:
        tone = int(payload)
        cmd = build_tone_command(tone, source="mqtt:tone")
        self._writer.enqueue(cmd)

    def _handle_reset(self) -> None:
        cmd = build_reset_command()
        self._writer.enqueue(cmd)

    def _handle_backlight(self, payload: str) -> None:
        on = payload.upper() in ("ON", "1", "TRUE")
        # Record synchronously rather than waiting for our own state publish to
        # come back round: a command issued while the Arduino is still in its
        # bootloader is discarded, and if the banner beats the echo the restore
        # would run against the stale value and strand the keypad backwards.
        self._desired_backlight = "ON" if on else "OFF"
        cmd = build_backlight_command(on, source="mqtt:backlight")
        self._writer.enqueue(cmd)
        self._publish(
            f"{self._prefix}/backlight/state",
            "ON" if on else "OFF",
            retain=True,
        )

    def _handle_backlight_state(self, payload: str, retained: bool = False) -> None:
        """Seed the desired backlight from the broker's stored value.

        Only *retained* delivery counts.  MQTT sets the retain flag just on
        the copy replayed when we subscribe; the echo of our own publishes
        arrives with it clear.  Taking only the retained one means this
        never fights _handle_backlight, which already records live commands
        itself, and never drives the keypad from our own echo.
        """
        if not retained:
            return
        self._desired_backlight = payload.upper()
        self._restore_backlight()

    def on_arduino_ready(self) -> None:
        """Called on every Arduino boot banner.

        Re-arms the restore each time: a DTR auto-reset mid-run reboots the
        Arduino with the backlight back on, so the restore has to run again,
        not just once per process.
        """
        self._arduino_ready = True
        self._backlight_restored = False
        self._restore_backlight()

    def _restore_backlight(self) -> None:
        """Re-apply the backlight the broker remembers, once per Arduino boot.

        A restart resets the Arduino, which comes up with the backlight on,
        and the banner's "Raspberry Pi OK" frame carries b=1 -- so an
        operator's earlier "off" is silently undone on every restart.  The
        retained state topic is the only record of what was actually
        wanted.

        Must wait for the Arduino: during the ~15-25 s the bootloader owns
        the port, anything written is discarded, and the banner's own frame
        would overwrite it anyway.  The retained message normally arrives
        long before the banner, so in practice this fires from
        on_arduino_ready.
        """
        if self._backlight_restored or not self._arduino_ready:
            return
        if self._desired_backlight is None:
            return
        self._backlight_restored = True
        if self._desired_backlight == "ON":
            return  # already on after reset -- no frame needed
        log.info("Restoring backlight %s from retained state", self._desired_backlight)
        self._writer.enqueue(
            build_backlight_command(False, source="mqtt:restore")
        )

    def _handle_notice_set(self, payload: str) -> None:
        if self._notices is None:
            return
        try:
            data = json.loads(payload)
            message = data["message"]
            notice_id = data.get("id")
            ttl = data.get("ttl", 0 if notice_id is not None else 60)
        except (json.JSONDecodeError, KeyError, TypeError):
            message = payload
            notice_id = None
            ttl = 60
        self._notices.set(message, notice_id=notice_id, ttl=ttl)

    def _handle_notice_clear(self, payload: str) -> None:
        if self._notices is None:
            return
        try:
            data = json.loads(payload)
            notice_id = data.get("id", payload)
        except (json.JSONDecodeError, TypeError):
            notice_id = payload
        self._notices.clear(notice_id)

    def publish_key_event(self, key: str) -> None:
        """Publish a key press event to MQTT."""
        payload = json.dumps({"event_type": "key_press", "key": key})
        self._publish(f"{self._prefix}/key/event", payload)

    # -- Uptime ------------------------------------------------------------

    def _start_uptime_publishing(self) -> None:
        self._publish_uptime()

    def _publish_uptime(self) -> None:
        uptime = int(time.monotonic() - self._start_time)
        self._publish(f"{self._prefix}/uptime/state", str(uptime))
        self._uptime_timer = threading.Timer(60, self._publish_uptime)
        self._uptime_timer.daemon = True
        self._uptime_timer.start()

    # -- Helpers -----------------------------------------------------------

    def _publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self._client.publish(topic, payload, qos=1, retain=retain)
