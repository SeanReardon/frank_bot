#!/usr/bin/env bash
#
# Production Smoke Test
#
# Verifies the app starts and /health returns a healthy response
# with the background loop running.
#
# Usage:
#   ./scripts/smoke_test.sh                  # Test localhost:8000 (default)
#   ./scripts/smoke_test.sh http://host:port # Test a specific URL
#   SMOKE_TIMEOUT=60 ./scripts/smoke_test.sh # Custom timeout (seconds)
#
# With docker-compose (local build):
#   docker compose up -d --build
#   ./scripts/smoke_test.sh
#   docker compose down
#
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
HEALTH_URL="${BASE_URL}/health"
TIMEOUT="${SMOKE_TIMEOUT:-45}"
POLL_INTERVAL=2

echo "Smoke test: ${HEALTH_URL} (timeout=${TIMEOUT}s)"

elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    # Attempt to hit /health
    if response=$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null); then
        status=$(echo "$response" | jq -r '.status // empty' 2>/dev/null || true)
        loop_running=$(echo "$response" | jq -r '.background_loop.running // empty' 2>/dev/null || true)

        if [ "$status" = "healthy" ] && [ "$loop_running" = "true" ]; then
            echo "PASS: status=${status}, background_loop.running=${loop_running}"
            echo "$response" | jq . 2>/dev/null || echo "$response"
            exit 0
        fi

        # App is up but not fully healthy yet
        echo "  Waiting... status=${status:-?} loop_running=${loop_running:-?} (${elapsed}s)"
    else
        echo "  Waiting... /health not reachable yet (${elapsed}s)"
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "FAIL: /health did not return healthy with running background loop within ${TIMEOUT}s"
# Print last response for debugging
if [ -n "${response:-}" ]; then
    echo "Last response:"
    echo "$response" | jq . 2>/dev/null || echo "$response"
fi
exit 1
