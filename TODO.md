# Future Enhancements

## Display & Feedback

- [ ] Show HA entity states on the LCD — door/window sensor names when zones open
- [ ] The second line can show all events in the past minute, like door closed, motion detected, etc..
- [ ] Notification display — push HA notifications (doorbell, washer done) to LCD

## Tones & Alerts

- [x] play single chime (tone 1) on vehicle detected when vehicle detector on
- [x] play two chime (tone 2) on person detected when person detector on

## Presence & Automation

- [ ] Auto-backlight — turn on backlight via motion sensor, off after timeout
- [ ] Presence-based greeting — show personalized message when someone arrives home

## Operational

- [x] Health check endpoint — expose HTTP /health for container monitoring
- [x] Uptime sensor — publish keypad uptime as an HA sensor
- [x] Serial reconnect — auto-reconnect if USB serial disconnects and reattaches

---

# HA Automation Prompts

The following items need HA automations. Each section is a self-contained prompt you can give to your HA agent.

## 1. Door/window sensor names on LCD line 1

> Create an automation that shows which doors/windows are currently open on the keypad LCD.
>
> **Trigger:** Any binary_sensor with device_class "door" or "window" changes state.
>
> **Action:** Collect all binary_sensors with device_class door/window that are currently "on" (open). Join their friendly names (truncated to fit) into a string. Publish via MQTT:
> - Topic: `homeassistant/6160/message/1/set`
> - Payload: the joined string (max 16 chars), or "All Secure" if none are open
>
> Example payloads: "Front Door", "Front Dr,Garage", "All Secure"

## 2. Events on LCD line 2

> Create an automation that shows recent events on the keypad LCD second line.
>
> **Trigger:** State change on any binary_sensor with device_class "door", "window", "motion", or "occupancy".
>
> **Action:** Publish the event to MQTT:
> - Topic: `homeassistant/6160/message/2/set`
> - Payload: friendly_name + " " + new state (e.g. "Front Door Open", "Hall Motion On"), truncated to 16 chars
>
> Note: The keypad service auto-updates line 2 with the clock every minute, so events naturally expire after ~60 seconds.

## 3. Notification display on LCD line 1

> Create an automation that pushes HA notifications to the keypad LCD.
>
> **Trigger:** Event type `mobile_app_notification_action` or state change on specific notification entities (doorbell ring, washer/dryer done, etc.).
>
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/message/1/set`
> - Payload: short notification text, max 16 chars (e.g. "Doorbell Ring", "Washer Done")

## 4. Vehicle detected chime (tone 1)

> Create an automation that plays a single chime on the keypad when a vehicle is detected.
>
> **Trigger:** A vehicle detection binary_sensor (e.g. from Frigate or a driveway sensor) turns "on".
>
> **Condition:** Only trigger when a vehicle detection toggle/input_boolean is enabled (so chimes can be silenced).
>
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/tone/set`
> - Payload: `1`

## 5. Person detected chime (tone 2)

> Create an automation that plays a double chime on the keypad when a person is detected.
>
> **Trigger:** A person detection binary_sensor (e.g. from Frigate) turns "on".
>
> **Condition:** Only trigger when a person detection toggle/input_boolean is enabled.
>
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/tone/set`
> - Payload: `2`

## 6. Auto-backlight via motion sensor

> Create an automation that turns on the keypad backlight when motion is detected nearby, and turns it off after a timeout.
>
> **Trigger:** A motion sensor near the keypad (e.g. hallway motion) turns "on".
>
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/backlight/set`
> - Payload: `ON`
>
> **Second automation (off after timeout):**
> **Trigger:** The same motion sensor turns "off".
> **Delay:** Wait 2 minutes (configurable).
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/backlight/set`
> - Payload: `OFF`

## 7. Presence-based greeting

> Create an automation that shows a personalized greeting when someone arrives home.
>
> **Trigger:** A person entity (e.g. `person.brian`) changes to "home".
>
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/message/1/set`
> - Payload: "Welcome Brian" (use the person's name, max 16 chars)
>
> **Follow-up (clear after 30s):**
> **Delay:** 30 seconds.
> **Action:** Publish to MQTT:
> - Topic: `homeassistant/6160/message/1/set`
> - Payload: "" (empty to clear)
