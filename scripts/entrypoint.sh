#!/bin/sh
# Frank Bot container entrypoint
#
# Starts the gnirehtet reverse-tether relay (if ANDROID_DEVICE_SERIAL
# is set) before launching the Python application. The relay provides
# internet to the Android phone through the USB connection.

set -e

GNIREHTET_BIN="/usr/local/bin/gnirehtet"
GNIREHTET_LOG="/app/logs/gnirehtet.log"

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
    if ! adb -s "$ANDROID_DEVICE_SERIAL" shell pm list packages 2>/dev/null | grep -q gnirehtet; then
        echo "[entrypoint] Installing gnirehtet APK..."
        adb -s "$ANDROID_DEVICE_SERIAL" install -r /app/gnirehtet.apk 2>/dev/null || true
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
