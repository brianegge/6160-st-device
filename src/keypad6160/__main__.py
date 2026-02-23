"""Entry point for the keypad6160 MQTT service."""

from __future__ import annotations

import logging
import signal
import sys

from keypad6160.config import Config
from keypad6160.ha_discovery import build_discovery_messages
from keypad6160.health import start_health_server
from keypad6160.mqtt_client import KeypadMqttClient
from keypad6160.serial_comm import SerialIO, open_serial

log = logging.getLogger(__name__)


def main() -> None:
    config = Config.from_env()

    logging.basicConfig(
        format="%(name)s: %(message)s [%(threadName)s]",
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        stream=sys.stdout,
    )

    log.info("Opening serial port %s", config.serial_device)
    port = open_serial(config)

    serial_io = SerialIO(port, config=config)
    mqtt_client = KeypadMqttClient(config, serial_io)
    serial_io.on_keypress = mqtt_client.publish_key_event
    serial_io.start()

    # -- Signal handling ---------------------------------------------------
    def _shutdown(signum: int, frame: object) -> None:
        log.info("Received signal %s, shutting down", signum)
        mqtt_client.disconnect()
        serial_io.shutdown()
        port.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # -- Health check ------------------------------------------------------
    start_health_server(config.health_port)

    # -- Connect and publish discovery -------------------------------------
    mqtt_client.connect()
    mqtt_client.publish_discovery(build_discovery_messages(config))

    log.info("Entering MQTT loop")
    mqtt_client.loop_forever()


if __name__ == "__main__":
    main()
