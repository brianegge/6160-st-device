# 6160 Keypad MQTT Service

MQTT service for interfacing a Honeywell 6160 alarm keypad with HomeAssistant.

Requires an Arduino running [Arduino2keypad](https://github.com/TomVickers/Arduino2keypad) connected via USB serial.

## Architecture

```
HomeAssistant --> MQTT Broker --> keypad6160 --> serial --> Arduino --> 6160 keypad
                                  (Podman)
```

## Configuration

All settings are controlled via `KEYPAD_*` environment variables. See `quadlet/keypad6160.env` for the full list.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Container Build

```bash
podman build -t keypad6160:latest .
```

## Deploy (Podman Quadlet)

Copy the quadlet files and environment template:

```bash
mkdir -p ~/.config/containers/systemd
cp quadlet/keypad6160.container ~/.config/containers/systemd/
cp quadlet/keypad6160.env ~/.config/containers/systemd/
# Edit ~/.config/containers/systemd/keypad6160.env with your MQTT credentials
systemctl --user daemon-reload
systemctl --user start keypad6160
```

## MQTT Topics

All topics are under the configurable prefix (default `homeassistant/6160`):

| Topic | Direction | Description |
|-------|-----------|-------------|
| `status` | publish | LWT: `online`/`offline` (retained) |
| `mode/set` | subscribe | Set alarm mode (e.g. `Armed Away`) |
| `mode/state` | publish | Current mode (retained) |
| `backlight/set` | subscribe | `ON` or `OFF` to toggle LCD backlight |
| `backlight/state` | publish | Current backlight state (retained) |
| `message/set` | subscribe | JSON: `{"text", "line_no", "backlight"}` |
| `message/1/set` | subscribe | Plain text for LCD line 1 |
| `message/2/set` | subscribe | Plain text for LCD line 2 |

HomeAssistant auto-discovery entities are published on connect.
