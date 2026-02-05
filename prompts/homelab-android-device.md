# Android Automation Device - Homelab Network Device

## Device Information

- **IP Address**: 10.0.0.95 (static)
- **Port**: 5555 (ADB over TCP)
- **Device**: Google Pixel 9 Pro Fold
- **Android Version**: 16
- **Build**: BP3A.251005.004.B3
- **Purpose**: Dedicated automation phone for Frank Bot

## What This Device Is

This is a rooted Android phone dedicated to automation tasks. It runs headlessly on the home network, allowing Frank Bot to control mobile apps like Uber, Uber Eats, OpenTable, etc. via ADB (Android Debug Bridge) over WiFi.

The phone is:
- **Rooted with Magisk** - Enables persistent ADB TCP mode
- **No lock screen PIN** - Swipe-only unlock for automation access
- **Always powered** - Connected to charger
- **Static IP** - Always reachable at 10.0.0.95

## Network Configuration

```
Protocol: ADB over TCP/IP
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

Frank Bot (running in Docker) connects to this device over the network and can:
- Wake the device screen
- Launch apps
- Read UI elements (accessibility tree)
- Tap, swipe, type text
- Take screenshots

The control flow is LLM-driven: Frank Bot uses an AI agent loop to interpret what's on screen and decide what actions to take, similar to browser automation but for mobile apps.

## Firewall / Security Notes

- Only accessible from within the home network (10.0.0.0/24)
- ADB port 5555 should NOT be exposed to the internet
- The frank_bot container needs network access to 10.0.0.95:5555

## Troubleshooting

If Frank Bot can't connect to the phone:

1. **Phone screen off / WiFi sleeping**: The phone may disconnect from WiFi when screen is off for extended periods. Wake the phone physically or ensure "Keep WiFi on during sleep" is set to "Always"

2. **ADB TCP not running**: If the phone rebooted and the init script didn't run, reconnect via USB and run:
   ```bash
   adb tcpip 5555
   ```

3. **IP changed**: Verify the phone still has 10.0.0.95 in Settings → Network → WiFi → [network] → IP address

4. **Test connectivity**:
   ```bash
   ping 10.0.0.95
   adb connect 10.0.0.95:5555
   adb devices
   ```

## Related Frank Bot Components

- `services/android_client.py` - ADB command wrapper
- `actions/android.py` - High-level Android actions
- `prompts/androidPhone*.md` - Prompts for specific app workflows
