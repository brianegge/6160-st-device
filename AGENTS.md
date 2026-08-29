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
  serial_comm.py   - SerialIO: single thread for reading and writing (queue-based commands, clock, "initialized" detect)
  ha_discovery.py  - Builds HomeAssistant MQTT auto-discovery JSON payloads
tests/             - pytest tests (run with `pytest`)
```

## Deployment

The service runs on `pi@raspberrypi-zerow` (Raspbian Bookworm, Python 3.11, armv6l) as a rootless Podman container managed by a quadlet.

- Image: `ghcr.io/brianegge/keypad6160:latest` (built for `linux/arm/v6` and `linux/amd64`)
- Quadlet: `~/.config/containers/systemd/keypad6160.container`
- Environment: `~/.config/containers/systemd/keypad6160.env`
- Auto-update: enabled via `io.containers.autoupdate=registry` label
- CI publishes to GHCR on every push to `master` (`.github/workflows/publish.yml`)

Deploy updates (merge to master, then pull on the Pi):

```bash
ssh pi@raspberrypi-zerow 'podman auto-update'
```

View logs:

```bash
ssh pi@raspberrypi-zerow 'podman logs -f keypad6160'
```

Restart the service:

```bash
ssh pi@raspberrypi-zerow 'systemctl --user restart keypad6160'
```

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
- A single `SerialIO` thread owns the serial port for both reading and writing; commands are submitted via a thread-safe queue
- F7 commands with a non-zero tone automatically send a follow-up reset after 1.5s
- The clock/notices on LCD line 2 tick at most once per second (idle reads and throttle waits both drive it), and never while an explicit line-2 command is pending
