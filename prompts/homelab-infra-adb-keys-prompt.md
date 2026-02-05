# Homelab-Infra: Setup Persistent ADB Keys

## Context

The frank_bot container needs persistent ADB keys so the Android phone stays authorized across container rebuilds. The docker-compose has been updated to mount `./adb-keys:/root/.android`.

## Task

Set up the ADB keys directory and restart frank_bot.

## Steps

1. **Pull latest code**:
   ```bash
   cd ~/dev/frank_bot
   git pull origin main
   ```

2. **Create the adb-keys directory**:
   ```bash
   mkdir -p adb-keys
   ```

3. **If container is running, copy existing keys** (so we don't need to re-authorize):
   ```bash
   docker cp frank-bot:/root/.android/. ./adb-keys/ 2>/dev/null || echo "No existing keys to copy"
   ```

4. **Recreate the container** with the new volume mount:
   ```bash
   docker compose pull
   docker compose up -d --force-recreate frank-bot
   ```

5. **Verify the volume mount**:
   ```bash
   docker exec frank-bot ls -la /root/.android/
   ```
   Should show `adbkey` and `adbkey.pub` files.

6. **Test the connection**:
   ```bash
   curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/health" \
     -H "X-API-Key: f04ad182983a4361f95119cd8508034d2a604b623d45c0083c93eb736f2a9b78"
   ```

## If Phone Needs Re-authorization

If the phone prompts for authorization one more time:
1. On the phone, tap "Allow" and check "Always allow from this computer"
2. The keys will now be saved in `./adb-keys/` and persist forever

## Expected Outcome

After this setup:
- ADB keys persist in `./adb-keys/` directory
- Android phone stays authorized across container rebuilds
- No more "Allow USB debugging?" popups
