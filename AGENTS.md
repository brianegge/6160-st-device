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

The service runs on `pi@raspberrypi-zerow` (Raspbian Bookworm, Python 3.11, armv6l) as a
rootless **systemd user unit running from a git checkout + venv** — not a container.

- Unit: `~/.config/systemd/user/keypad6160.service` (`Type=simple`, `Restart=always`)
- Code: `/home/pi/6160-st-device`, a git checkout of `master`
- Entry point: `/home/pi/6160-st-device/venv/bin/keypad6160`. It is an *editable* install
  (`_editable_impl_keypad6160.pth` points at `src/`), so `git pull` really does change the
  running code — no reinstall step.
- Environment: `~/.config/containers/systemd/keypad6160.env`. The path is a leftover from the
  container era, but the unit genuinely reads it.

Deploy updates (merge to master, then pull on the Pi):

```bash
ssh pi@raspberrypi-zerow 'cd ~/6160-st-device && git pull && systemctl --user restart keypad6160'
```

**Verify a deploy by the Arduino's boot banner, never by systemd.** Restarting reopens the
serial port, which asserts DTR and resets the Mega into its STK500 bootloader. Both
`systemctl is-active` and the `/health` endpoint report perfectly healthy while the keypad is
dead, so neither is evidence. Confirm in the log:

1. `<< USB2keybus initialized` — can take 15-25 s to appear.
2. `Arduino application ready — keepalive armed`.
3. `>> [init] ... 1=Raspberry Pi OK`.

If the banner has not appeared within ~60 s, roll back. A keypad showing `Open Ckt` with a
dark backlight is the 6160's own panel-comm-loss message, meaning the Arduino is not driving
the keybus — it is not something this service prints.

### Legacy container deployment (not in use)

`quadlet/`, `Containerfile`, `ghcr.io/brianegge/keypad6160:latest` and
`.github/workflows/publish.yml` are left over from an earlier rootless-Podman deployment. CI
still builds and pushes the image, but nothing consumes it, and stale
`keypad6160.container`/`keypad6160.env` quadlet files remain on the Pi without a running
container. `podman auto-update` and `podman logs keypad6160` will not deploy or debug
anything here.

### Logs

The Pi keeps no durable local log: journald is `Storage=volatile`, `journalctl --user -u
keypad6160` returns "No journal files were found", and the service's output does not land in
the Pi's `/var/log/syslog` either. rsyslog forwards to LibreNMS on `ubuntu24`
(192.168.254.35:514), which holds the only usable history:

```bash
PW=$(sudo grep -oP 'MYSQL_PASSWORD=\K\S+' /etc/containers/systemd/librenms-db.container)
sudo podman exec librenms-db mariadb -u librenms -p"$PW" librenms -e \
  "SELECT timestamp, msg FROM syslog WHERE device_id=86 AND program='KEYPAD6160' \
   ORDER BY timestamp DESC LIMIT 50;"
```

Every line is stored **twice** — `/etc/rsyslog.d/50-librenms.conf` and `99-librenms.conf` both
forward to the same collector — so any count needs halving.

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
