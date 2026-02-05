# Prompt for homelab-infra Agent

Copy and paste this to your ~/dev/homelab-infra agent:

---

## New Network Device: Android Automation Phone

I've added a new device to the home network that frank_bot uses for mobile app automation.

### Device Details

```yaml
name: android-automation-phone
ip: 10.0.0.95
port: 5555
protocol: ADB over TCP/IP
device: Google Pixel 9 Pro Fold
os: Android 16
purpose: Headless phone for Frank Bot to control mobile apps
```

### What It Does

This is a rooted, dedicated Android phone that Frank Bot controls via ADB over WiFi. It lets Frank interact with mobile apps that don't have APIs, like:
- Uber (request rides)
- Uber Eats (order food)
- OpenTable (make reservations)
- American Airlines (check flights)
- Zillow (property lookups)

The phone sits powered and connected to WiFi. Frank Bot connects to `10.0.0.95:5555` and can:
- Launch apps
- Read the screen (accessibility tree)
- Tap, type, swipe
- Take screenshots

### Network/Firewall Considerations

- The phone should only be accessible from the local network
- ADB port 5555 should NOT be exposed to the internet
- The frank_bot Docker container needs network access to 10.0.0.95:5555

### Please Update

1. **Network documentation** - Add this device to the inventory
2. **DHCP reservation** - Ensure 10.0.0.95 stays reserved for this device's MAC
3. **Firewall rules** - If any, ensure frank_bot can reach 10.0.0.95:5555

### Troubleshooting Commands

```bash
# Test connectivity
ping 10.0.0.95

# Test ADB connection
adb connect 10.0.0.95:5555
adb devices

# Get device info
adb -s 10.0.0.95:5555 shell getprop ro.product.model
```

If the phone becomes unreachable:
1. It may have disconnected from WiFi while sleeping
2. The ADB TCP service may have stopped (rare with Magisk init script)
3. IP may have changed if DHCP reservation failed
