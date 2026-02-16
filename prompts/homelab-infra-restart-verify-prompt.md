# Homelab-Infra: Restart Frank Bot and Verify Android Integration

## Context

Vault secrets for Android phone automation and Actions API have been applied. Frank-bot needs to be restarted to pick up the new configuration.

## Task

Restart the frank-bot container and verify the Android phone integration is working.

## Steps

1. **Restart frank-bot**:
   ```bash
   cd ~/dev/frank_bot  # or wherever frank-bot is deployed
   docker-compose restart frank-bot
   # or if using standalone docker:
   # docker restart frank-bot
   ```

2. **Wait for startup** (10-15 seconds):
   ```bash
   sleep 15
   docker logs frank-bot --tail 50
   ```
   Look for successful startup messages and no Vault connection errors.

3. **Test Android health endpoint**:
   ```bash
   curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/health" | jq .
   ```

4. **Expected response** (success):
   ```json
   {
     "connected": true,
     "transport": "usb",
     "device_serial": "48151FDKD001UD",
     "device_model": "Pixel 9 Pro Fold",
     "android_version": "15",
     "battery_level": 85,
      "wifi_enabled": false,
      "wifi_ssid": null
   }
   ```

5. **If `connected: false`**, check:
   - USB mode:
     - Is the phone still physically plugged in?
     - Does the container see it? `docker exec frank-bot adb devices -l`
     - If it shows `unauthorized`, re-authorize ADB on the phone (ADB keys are persisted via `./adb-keys`)
   - Wireless debugging mode (fallback):
     - Is the phone on Wi‑Fi and reachable at the configured host/port?
     - Can you run `adb connect <host>:<port>` from the host?

## Verification

Once health returns `connected: true`, test the thermostat:
```bash
curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/thermostat/getStatus" \
  -H "X-API-Key: <ACTIONS_API_KEY>" | jq .
```

This will take 10-30 seconds as the LLM navigates the Google Home app.
