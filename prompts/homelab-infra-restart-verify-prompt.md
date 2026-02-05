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
   curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/health" \
     -H "X-API-Key: f04ad182983a4361f95119cd8508034d2a604b623d45c0083c93eb736f2a9b78" | jq .
   ```

4. **Expected response** (success):
   ```json
   {
     "connected": true,
     "device_model": "Pixel 9 Pro Fold",
     "android_version": "15",
     "battery_level": 85,
     "adb_host": "10.0.0.95",
     "adb_port": 5555
   }
   ```

5. **If `connected: false`**, check:
   - Is the Android phone on WiFi and awake?
   - Can you ping `10.0.0.95` from the frank-bot container?
   - Is ADB TCP still running on the phone? (port 5555)

## Verification

Once health returns `connected: true`, test the thermostat:
```bash
curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/thermostat/status" \
  -H "X-API-Key: f04ad182983a4361f95119cd8508034d2a604b623d45c0083c93eb736f2a9b78" | jq .
```

This will take 10-30 seconds as the LLM navigates the Google Home app.
