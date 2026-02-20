# AGENTS.md

## Project overview

MQTT service (`keypad6160`) that bridges a Honeywell 6160 alarm keypad to HomeAssistant via MQTT auto-discovery. A Raspberry Pi Zero W communicates over USB serial with an Arduino Mega running [Arduino2keypad](https://github.com/TomVickers/Arduino2keypad), which handles the proprietary 4800 baud keypad bus protocol.

## Source layout

```
src/keypad6160/
  __main__.py      - Entry point: wires config, serial, and MQTT; runs the event loop
  config.py        - Dataclass config loaded from KEYPAD_* environment variables
  f7_protocol.py   - Builds F7 serial commands (alarm states, text, backlight, tones, reset)
  mqtt_client.py   - Paho MQTT client: subscriptions, HA command dispatch, state publishing
  serial_comm.py   - SerialWriter (queue-based) and SerialReader (clock + "initialized" detect) threads
  ha_discovery.py  - Builds HomeAssistant MQTT auto-discovery JSON payloads
tests/             - pytest tests (run with `pytest`)
```

## Deployment

The service runs on `pi@raspberrypi-zerow` (Raspbian Bookworm, Python 3.11, armv6l).

**Current production deployment** uses a systemd system service (not containers):

- Service file: `/etc/systemd/system/keypad6160.service`
- Executable: `/home/pi/.local/bin/keypad6160` (pip-installed)
- Environment: `/home/pi/6160-st-device/quadlet/keypad6160.env`
- Runs as user `pi`, auto-restarts with 30s delay
- The repo is cloned to `/home/pi/6160-st-device` on the Pi

Deploy updates:

```bash
ssh pi@raspberrypi-zerow 'cd ~/6160-st-device && git pull && pip install --user . && sudo systemctl restart keypad6160'
```

View logs:

```bash
ssh pi@raspberrypi-zerow 'journalctl -u keypad6160 -f'
```

The repo also contains a Containerfile and Podman quadlet config (`quadlet/`) for container-based deployment, but these are not currently in use on the Pi.

## Hardware

- Serial device: `/dev/ttyACM0` (USB serial to Arduino Mega)
- The `pi` user must be in the `dialout` group for serial access
- The Arduino sends "initialized" on reset; the service responds with "Raspberry Pi OK"
- The Arduino can be reset remotely by toggling DTR on the serial port (exposed as an HA button entity via `reset/set` MQTT topic)

## Development

```bash
pip install -e ".[dev]"
git config core.hooksPath .githooks
pytest
```

- Build system: hatchling
- Pre-commit hook blocks direct commits to `master`; use feature branches with PRs
- CI: GitHub Actions runs `pytest` on PRs and pushes to master

## MQTT

Broker is at `mqtt.home:1883`. All topics are under the prefix configured by `KEYPAD_MQTT_TOPIC_PREFIX` (default `homeassistant/6160`). The service publishes HA auto-discovery messages on connect and maintains an LWT `status` topic.

## Key conventions

- All config is via `KEYPAD_*` environment variables with sensible defaults
- Serial writes go through a single `SerialWriter` queue thread; reads happen on a separate `SerialReader` thread
- F7 commands with a non-zero tone automatically send a follow-up reset after 1.5s
- The clock on LCD line 2 updates on every serial read timeout (~1s)
