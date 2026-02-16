#!/bin/sh
# Frank Bot container entrypoint
#
# Starts the gnirehtet reverse-tether relay (if ANDROID_DEVICE_SERIAL
# is set) before launching the Python application. The relay provides
# internet to the Android phone through the USB connection.

set -e

GNIREHTET_BIN="/usr/local/bin/gnirehtet"
GNIREHTET_LOG="/app/logs/gnirehtet.log"

# Timeout (seconds) for ADB commands that could hang on missing devices
ADB_TIMEOUT="${ADB_TIMEOUT:-10}"
# Timeout (seconds) for the Vault-backed Python config lookup
VAULT_TIMEOUT="${VAULT_TIMEOUT:-15}"

maybe_set_android_serial() {
    # If ANDROID_DEVICE_SERIAL isn't set, try to load it from Vault-backed config.
    # This keeps docker-compose clean (Vault-first) while still enabling USB ADB
    # and gnirehtet on the host-attached device.
    if [ -n "$ANDROID_DEVICE_SERIAL" ]; then
        return
    fi

    SERIAL="$(timeout "$VAULT_TIMEOUT" python - <<'PY' 2>/dev/null || true
from config import get_settings
print((get_settings().android_device_serial or "").strip())
PY
)"
    if [ -n "$SERIAL" ]; then
        export ANDROID_DEVICE_SERIAL="$SERIAL"
        echo "[entrypoint] Loaded ANDROID_DEVICE_SERIAL from settings: $ANDROID_DEVICE_SERIAL"
        return
    fi

    # Fallback: if exactly one USB-connected device is present, auto-select it.
    # (We intentionally ignore tcpip serials like 10.0.0.95:5555 here.)
    USB_SERIALS="$(timeout "$ADB_TIMEOUT" adb devices 2>/dev/null | awk 'NR>1 && $2==\"device\" && $1 !~ /:/ {print $1}' || true)"
    USB_COUNT="$(printf \"%s\" \"$USB_SERIALS\" | grep -c . || true)"
    if [ "$USB_COUNT" -eq 1 ]; then
        export ANDROID_DEVICE_SERIAL="$USB_SERIALS"
        echo "[entrypoint] Auto-detected USB ANDROID_DEVICE_SERIAL: $ANDROID_DEVICE_SERIAL"
        return
    fi
}

maybe_set_android_serial || true

start_gnirehtet() {
    if [ -z "$ANDROID_DEVICE_SERIAL" ]; then
        echo "[entrypoint] ANDROID_DEVICE_SERIAL not set, skipping gnirehtet"
        return
    fi

    if [ ! -x "$GNIREHTET_BIN" ]; then
        echo "[entrypoint] gnirehtet binary not found, skipping"
        return
    fi

    echo "[entrypoint] Starting gnirehtet reverse tether (USB internet)..."

    # Ensure log directory exists
    mkdir -p "$(dirname "$GNIREHTET_LOG")"

    # Install gnirehtet APK if not already installed
    if ! timeout "$ADB_TIMEOUT" adb -s "$ANDROID_DEVICE_SERIAL" shell pm list packages 2>/dev/null | grep -q gnirehtet; then
        echo "[entrypoint] Installing gnirehtet APK..."
        timeout 30 adb -s "$ANDROID_DEVICE_SERIAL" install -r /app/gnirehtet.apk 2>/dev/null || true
    fi

    # Use 'gnirehtet run' which handles everything:
    #   - starts the relay server
    #   - sets up adb reverse tunnel (abstract socket)
    #   - starts the client on the phone
    # Run in background so the app can start
    "$GNIREHTET_BIN" run "$ANDROID_DEVICE_SERIAL" \
        -d 1.1.1.1,8.8.8.8 > "$GNIREHTET_LOG" 2>&1 &
    GNIREHTET_PID=$!

    # Wait for relay + client to initialize
    sleep 3

    if ! kill -0 "$GNIREHTET_PID" 2>/dev/null; then
        echo "[entrypoint] WARNING: gnirehtet failed to start"
        cat "$GNIREHTET_LOG" 2>/dev/null || true
        return
    fi

    echo "[entrypoint] gnirehtet running (PID $GNIREHTET_PID)"
}

# Start gnirehtet (non-fatal if it fails)
start_gnirehtet || echo "[entrypoint] gnirehtet setup failed (non-fatal)"

# Launch the main application
echo "[entrypoint] Starting frank_bot..."
exec python app.py
