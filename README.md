# 6160 Keypad MQTT Service

MQTT service for interfacing a Honeywell 6160 alarm keypad with HomeAssistant.

Requires an Arduino running [Arduino2keypad](https://github.com/TomVickers/Arduino2keypad) connected via USB serial.

![6160 keypad in ready state](images/keypad-ready.jpeg)

## Usage

The service exposes three HomeAssistant entities via MQTT auto-discovery:

- **Keypad Mode** (select) -- Controls the keypad indicator LEDs and displays the mode on line 1 of the LCD. Options:
  - `Disarmed` -- READY LED lit, one chime
  - `Armed Away` -- ARMED LED lit, backlight off, two chimes
  - `Armed Stay` -- ARMED STAY LED lit, two chimes
- **Keypad Backlight** (light) -- Toggles the LCD backlight on or off.
- **Keypad Message** (text) -- Sends arbitrary text (up to 16 characters) to LCD line 1.

The keypad automatically displays the current date and time on line 2.

## Hardware

![Raspberry Pi Zero W and Arduino Mega](images/hardware-setup.jpeg)

A Raspberry Pi Zero W connects over USB serial to an Arduino Mega running [Arduino2keypad](https://github.com/TomVickers/Arduino2keypad). The Arduino handles the non-standard 4800 baud keypad bus protocol and exposes an F7 command interface over 115200 baud serial.

## Architecture

```
HomeAssistant --> MQTT Broker --> keypad6160 --> serial --> Arduino --> 6160 keypad
```

## Configuration

All settings are controlled via `KEYPAD_*` environment variables. See `quadlet/keypad6160.env` for the full list.

## Development

```bash
pip install -e ".[dev]"
git config core.hooksPath .githooks
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
