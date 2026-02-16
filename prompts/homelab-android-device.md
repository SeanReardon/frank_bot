# Android Automation Device - Homelab Network Device

## Device Information

- **USB Serial**: 48151FDKD001UD
- **Device**: Google Pixel 9 Pro Fold
- **Android Version**: 16
- **Build**: BP3A.251005.004.B3
- **Purpose**: Dedicated automation phone for Frank Bot

## What This Device Is

This is a rooted Android phone dedicated to automation tasks. Frank Bot controls it via ADB (Android Debug Bridge) — **over USB by default**, with optional wireless debugging as a fallback.

The phone is:
- **Rooted with Magisk** - Enables persistent ADB TCP mode
- **No lock screen PIN** - Swipe-only unlock for automation access
- **Always powered** - Connected to charger
- **USB-attached** - Plugged into `onlogic-closet` and controlled via ADB over USB
- **Network optional** - Wi‑Fi/cellular may be disabled; when so, USB reverse-tethering (`gnirehtet`) provides internet

## ADB Configuration (Primary)

```
Protocol: ADB over USB
Serial: 48151FDKD001UD
Connection: adb -s 48151FDKD001UD shell getprop ro.product.model
```

## ADB Configuration (Optional: Wireless Debugging Fallback)

If the phone is on Wi‑Fi and you prefer TCP/IP:

```
Host: 10.0.0.95
Port: 5555
Connection: adb connect 10.0.0.95:5555
```

## Installed Apps (Automation Targets)

| App | Package | Use Case |
|-----|---------|----------|
| Uber | com.ubercab | Ride requests |
| Uber Eats | com.ubercab.eats | Food delivery |
| American Airlines | com.aa.android | Flight status |
| OpenTable | com.opentable | Restaurant reservations |
| Zillow | com.zillow.android.zillowmap | Property lookups |
| Twitter/X | com.twitter.android | Social media |
| Telegram | org.telegram.messenger | Messaging |
| Netflix | com.netflix.mediaclient | Streaming control |
| Fitbit | com.fitbit.FitbitMobile | Health data |

## How Frank Bot Controls It

Frank Bot (running in Docker) connects to this device over USB (preferred) and can:
- Wake the device screen
- Launch apps
- Read UI elements (accessibility tree)
- Tap, swipe, type text
- Take screenshots

The control flow is LLM-driven: Frank Bot uses an AI agent loop to interpret what's on screen and decide what actions to take, similar to browser automation but for mobile apps.

## Firewall / Security Notes

- If using wireless debugging: ADB port 5555 should NOT be exposed to the internet
- USB mode avoids exposing ADB on the network entirely

## Troubleshooting

If Frank Bot can't connect to the phone:

1. **USB passthrough**: Ensure `docker-compose.yml` mounts `/dev/bus/usb` into the container and persists `./adb-keys:/root/.android`

2. **ADB authorization**: If `adb devices` shows `unauthorized`, re-authorize the host key on the phone and/or remove stale keys in `./adb-keys/`

3. **Wireless debugging (if using TCP/IP)**: confirm the phone is on Wi‑Fi and reachable at the configured host/port

4. **Test connectivity**:
   ```bash
   adb devices
   adb -s 48151FDKD001UD shell echo ping
   ```

## Related Frank Bot Components

- `services/android_client.py` - ADB command wrapper
- `actions/android.py` - High-level Android actions
- `prompts/androidPhone*.md` - Prompts for specific app workflows
