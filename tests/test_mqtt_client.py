"""Tests for MQTT client callbacks."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from keypad6160.config import Config
from keypad6160.f7_protocol import SerialCommand
from keypad6160.mqtt_client import KeypadMqttClient
from keypad6160.notice_manager import NoticeManager


@pytest.fixture
def config():
    return Config(mqtt_host="localhost", mqtt_topic_prefix="test/6160")


@pytest.fixture
def writer():
    return MagicMock()


@pytest.fixture
def notices():
    return NoticeManager()


@pytest.fixture
def mqtt_client(config, writer, notices):
    with patch("keypad6160.mqtt_client.mqtt.Client"):
        client = KeypadMqttClient(config, writer, notices=notices)
    return client


class TestMqttCallbacks:
    def test_handle_mode_armed_away(self, mqtt_client, writer):
        mqtt_client._handle_mode("Armed Away")
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "Armed Away" in cmd.payloads[0]
        assert "a=1" in cmd.payloads[0]

    def test_handle_mode_publishes_state(self, mqtt_client):
        mqtt_client._handle_mode("Disarmed")
        mqtt_client._client.publish.assert_called()
        # Find the state publish call
        calls = mqtt_client._client.publish.call_args_list
        state_call = [c for c in calls if "mode/state" in str(c)]
        assert len(state_call) == 1

    def test_handle_json_message(self, mqtt_client, writer):
        payload = json.dumps({"text": "Hello", "line_no": "1", "backlight": "1"})
        mqtt_client._handle_json_message(payload)
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "1=Hello" in cmd.payloads[0]

    def test_handle_json_message_defaults(self, mqtt_client, writer):
        payload = json.dumps({"text": "Hi"})
        mqtt_client._handle_json_message(payload)
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "b=1" in cmd.payloads[0]
        assert "1=Hi" in cmd.payloads[0]

    def test_handle_line_message(self, mqtt_client, writer):
        mqtt_client._handle_line_message(2, "Clock Text")
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "2=Clock Text" in cmd.payloads[0]

    def test_on_message_dispatches_mode(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/mode/set"
        msg.payload = b"Armed Away"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_called_once()

    def test_on_message_dispatches_line(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/message/2/set"
        msg.payload = b"Some text"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_called_once()

    def test_on_message_dispatches_reset(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/reset/set"
        msg.payload = b"PRESS"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert cmd.reset is True

    def test_on_message_dispatches_backlight(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/backlight/set"
        msg.payload = b"ON"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "b=1" in cmd.payloads[0]

    def test_handle_backlight_off(self, mqtt_client, writer):
        mqtt_client._handle_backlight("OFF")
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "b=0" in cmd.payloads[0]

    def test_handle_backlight_publishes_state(self, mqtt_client):
        mqtt_client._handle_backlight("ON")
        calls = mqtt_client._client.publish.call_args_list
        state_call = [c for c in calls if "backlight/state" in str(c)]
        assert len(state_call) == 1

    def test_on_message_dispatches_tone(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/tone/set"
        msg.payload = b"1"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert "t=1" in cmd.payloads[0]
        assert len(cmd.payloads) == 2  # tone + reset
        assert cmd.payloads[1] == "F7 t=0\n"

    def test_handle_tone_zero(self, mqtt_client, writer):
        mqtt_client._handle_tone("0")
        writer.enqueue.assert_called_once()
        cmd = writer.enqueue.call_args[0][0]
        assert len(cmd.payloads) == 1
        assert "t=0" in cmd.payloads[0]

    def test_on_message_handles_error(self, mqtt_client, writer):
        msg = MagicMock()
        msg.topic = "test/6160/message/set"
        msg.payload = b"not json"
        # Should not raise
        mqtt_client._on_message(mqtt_client._client, None, msg)
        writer.enqueue.assert_not_called()

    def test_publish_key_event(self, mqtt_client):
        mqtt_client.publish_key_event("5")
        mqtt_client._client.publish.assert_called_once()
        call_args = mqtt_client._client.publish.call_args
        assert call_args[0][0] == "test/6160/key/event"
        payload = json.loads(call_args[0][1])
        assert payload == {"event_type": "key_press", "key": "5"}


    def test_on_message_dispatches_notice_set_plain(self, mqtt_client, notices):
        msg = MagicMock()
        msg.topic = "test/6160/notice/set"
        msg.payload = b"Washer Done"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        assert notices.active_count == 1

    def test_on_message_dispatches_notice_set_json(self, mqtt_client, notices):
        msg = MagicMock()
        msg.topic = "test/6160/notice/set"
        msg.payload = json.dumps({"id": "washer", "message": "Washer Done"}).encode()
        mqtt_client._on_message(mqtt_client._client, None, msg)
        assert notices.active_count == 1

    def test_on_message_dispatches_notice_clear(self, mqtt_client, notices):
        notices.set("Washer Done", notice_id="washer", ttl=0)
        msg = MagicMock()
        msg.topic = "test/6160/notice/clear"
        msg.payload = b"washer"
        mqtt_client._on_message(mqtt_client._client, None, msg)
        assert notices.active_count == 0

    def test_on_message_dispatches_notice_clear_json(self, mqtt_client, notices):
        notices.set("Washer Done", notice_id="washer", ttl=0)
        msg = MagicMock()
        msg.topic = "test/6160/notice/clear"
        msg.payload = json.dumps({"id": "washer"}).encode()
        mqtt_client._on_message(mqtt_client._client, None, msg)
        assert notices.active_count == 0

    def test_notice_set_json_with_ttl(self, mqtt_client, notices):
        msg = MagicMock()
        msg.topic = "test/6160/notice/set"
        msg.payload = json.dumps({"id": "timer", "message": "Timer Done", "ttl": 120}).encode()
        mqtt_client._on_message(mqtt_client._client, None, msg)
        assert notices.active_count == 1

    def test_notice_set_json_without_id_defaults_transient(self, mqtt_client, notices):
        """JSON payload without 'id' should default to 60s TTL."""
        mqtt_client._handle_notice_set(json.dumps({"message": "Quick Note"}))
        assert notices.active_count == 1


class TestOnConnect:
    def _make_rc(self, failure=False):
        rc = MagicMock()
        rc.is_failure = failure
        return rc

    def test_first_connect_does_not_republish_discovery(self, mqtt_client):
        """First _on_connect should NOT republish discovery (avoids double-publish)."""
        mqtt_client._discovery_messages = [("ha/sensor/config", '{"name":"x"}')]
        mqtt_client._client.publish.reset_mock()

        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc())

        # Should publish status + version + uptime, but NOT discovery
        topics = [c[0][0] for c in mqtt_client._client.publish.call_args_list]
        assert "ha/sensor/config" not in topics
        assert "test/6160/status" in topics

    def test_reconnect_republishes_discovery(self, mqtt_client):
        """Subsequent _on_connect (reconnect) should republish stored discovery."""
        mqtt_client._discovery_messages = [("ha/sensor/config", '{"name":"x"}')]

        # First connect — consumes the flag
        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc())
        mqtt_client._client.publish.reset_mock()

        # Second connect — should republish discovery
        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc())

        topics = [c[0][0] for c in mqtt_client._client.publish.call_args_list]
        assert "ha/sensor/config" in topics

    def test_reconnect_without_discovery_messages_is_noop(self, mqtt_client):
        """Reconnect with empty discovery list should not error."""
        # First connect
        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc())
        mqtt_client._client.publish.reset_mock()

        # Reconnect with no stored messages
        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc())

        topics = [c[0][0] for c in mqtt_client._client.publish.call_args_list]
        # Only status/version/uptime, no discovery
        assert all("config" not in t for t in topics)

    def test_ha_status_online_republishes_discovery(self, mqtt_client):
        """HA birth message should republish discovery and online status."""
        mqtt_client._discovery_messages = [("ha/sensor/config", '{"name":"x"}')]
        mqtt_client._client.publish.reset_mock()

        mqtt_client._handle_ha_status("online")

        topics = [c[0][0] for c in mqtt_client._client.publish.call_args_list]
        assert "ha/sensor/config" in topics
        assert "test/6160/status" in topics

    def test_ha_status_offline_ignored(self, mqtt_client):
        """HA offline message should not trigger republish."""
        mqtt_client._discovery_messages = [("ha/sensor/config", '{"name":"x"}')]
        mqtt_client._client.publish.reset_mock()

        mqtt_client._handle_ha_status("offline")

        mqtt_client._client.publish.assert_not_called()

    def test_connect_failure_returns_early(self, mqtt_client):
        """Failed connection should not publish anything."""
        mqtt_client._on_connect(mqtt_client._client, None, MagicMock(), self._make_rc(failure=True))
        mqtt_client._client.publish.assert_not_called()


class TestHaDiscovery:
    def test_discovery_messages(self):
        from keypad6160.ha_discovery import build_discovery_messages

        config = Config(mqtt_topic_prefix="test/6160")
        messages = build_discovery_messages(config)
        assert len(messages) == 8
        topics = [t for t, _ in messages]
        assert "homeassistant/select/keypad_6160_mode/config" in topics
        assert "homeassistant/light/keypad_6160_backlight/config" in topics
        assert "homeassistant/text/keypad_6160_message/config" in topics
        assert "homeassistant/button/keypad_6160_reset/config" in topics
        assert "homeassistant/event/keypad_6160_keypress/config" in topics
        assert "homeassistant/binary_sensor/keypad_6160_status/config" in topics
        assert "homeassistant/sensor/keypad_6160_version/config" in topics
        assert "homeassistant/sensor/keypad_6160_uptime/config" in topics

        # Verify JSON payloads are valid
        for _, payload in messages:
            data = json.loads(payload)
            assert "device" in data
            assert data["device"]["identifiers"] == ["keypad_6160"]

    def test_discovery_uses_prefix(self):
        from keypad6160.ha_discovery import build_discovery_messages

        config = Config(mqtt_topic_prefix="custom/prefix")
        messages = build_discovery_messages(config)
        for _, payload in messages:
            data = json.loads(payload)
            # All command/state topics should use the custom prefix
            for key in ("command_topic", "state_topic", "availability_topic"):
                if key in data:
                    assert data[key].startswith("custom/prefix/")
