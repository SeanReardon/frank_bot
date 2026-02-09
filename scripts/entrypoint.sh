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

    echo "[entrypoint] Starting gnirehtet relay for USB reverse tethering..."

    # Ensure log directory exists
    mkdir -p "$(dirname "$GNIREHTET_LOG")"

    # Start relay in background
    "$GNIREHTET_BIN" relay > "$GNIREHTET_LOG" 2>&1 &
    RELAY_PID=$!

    # Wait for relay to start
    sleep 2

    if ! kill -0 "$RELAY_PID" 2>/dev/null; then
        echo "[entrypoint] WARNING: gnirehtet relay failed to start"
        cat "$GNIREHTET_LOG" 2>/dev/null || true
        return
    fi

    echo "[entrypoint] Relay started (PID $RELAY_PID)"

    # Install gnirehtet APK if not already installed
    if ! adb -s "$ANDROID_DEVICE_SERIAL" shell pm list packages 2>/dev/null | grep -q gnirehtet; then
        echo "[entrypoint] Installing gnirehtet APK..."
        adb -s "$ANDROID_DEVICE_SERIAL" install -r /app/gnirehtet.apk 2>/dev/null || true
    fi

    # Set up adb reverse tunnel
    adb -s "$ANDROID_DEVICE_SERIAL" reverse tcp:31416 tcp:31416 2>/dev/null || true

    # Start the gnirehtet client on the phone
    adb -s "$ANDROID_DEVICE_SERIAL" shell am start \
        -a com.genymobile.gnirehtet.START \
        -n com.genymobile.gnirehtet/.GnirehtetActivity 2>/dev/null || true

    echo "[entrypoint] gnirehtet reverse tether configured"
}

# Start gnirehtet (non-fatal if it fails)
start_gnirehtet || echo "[entrypoint] gnirehtet setup failed (non-fatal)"

# Launch the main application
echo "[entrypoint] Starting frank_bot..."
exec python app.py
