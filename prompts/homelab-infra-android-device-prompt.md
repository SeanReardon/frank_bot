# Prompt for homelab-infra Agent

Copy and paste this to your ~/dev/homelab-infra agent:

---

## New Network Device: Android Automation Phone

I've added a new device to the home network that frank_bot uses for mobile app automation.

### Device Details

```yaml
name: android-automation-phone
usb_serial: 48151FDKD001UD
protocol: ADB over USB (preferred)
wifi_debug_host: 10.0.0.95  # optional
wifi_debug_port: 5555       # optional
device: Google Pixel 9 Pro Fold
os: Android 16
purpose: Headless phone for Frank Bot to control mobile apps
```

### What It Does

This is a rooted, dedicated Android phone that Frank Bot controls via ADB (**USB by default**, optional wireless debugging fallback). It lets Frank interact with mobile apps that don't have APIs, like:
- Uber (request rides)
- Uber Eats (order food)
- OpenTable (make reservations)
- American Airlines (check flights)
- Zillow (property lookups)

The phone sits powered and connected to the `onlogic-closet` host over USB. Frank Bot can:
- Launch apps
- Read the screen (accessibility tree)
- Tap, type, swipe
- Take screenshots

### Network/Firewall Considerations

- USB mode avoids exposing ADB on the network entirely
- If wireless debugging is enabled: keep ADB on the local network only; **never** expose port 5555 publicly

### Please Update

1. **Inventory documentation** - Track this device + USB serial
2. **Host wiring** - Ensure it remains plugged into `onlogic-closet`
3. **Container access** - Ensure frank_bot has USB passthrough (`/dev/bus/usb`) and persistent ADB keys (`./adb-keys`)

### Troubleshooting Commands

```bash
# List attached devices
adb devices -l

# Get device info
adb -s 48151FDKD001UD shell getprop ro.product.model
```

If the phone becomes unreachable:
1. USB cable/passthrough may be disconnected
2. ADB authorization may have been revoked (device shows `unauthorized`)
3. If using wireless debugging: Wi‑Fi state / IP may have changed
