# Speedtest Run Task

## Goal
Run a new Speedtest by Ookla test using the installed Android app and report the final results.

## App Information
- **Package**: org.zwanoo.android.speedtest
- **App Name**: Speedtest by Ookla

## Entry Point Workflow
1. The app will be launched for you before you start.
2. Verify you are in the Speedtest app, not a browser, Google search results, or the Play Store.
3. If you are not in the Speedtest app, recover first. Use `press_key: home` only if needed to reset, then return an error instead of improvising a web search.

## Main Workflow

### Phase 1: Get to the test screen
1. Dismiss or accept one-time prompts only when they are needed to reach the main test UI.
2. Handle permission dialogs sensibly:
   - Allow location permission if it is needed for server selection or the app blocks progress.
   - Dismiss upgrade, rating, account, VPN, or ad surfaces if possible.
3. Wait for the main screen with the large **GO** button or the results screen from a recent test.

### Phase 2: Start a fresh test
1. If a completed result is already visible, look for a way to start a new test.
2. Tap **GO** (or the equivalent start control) to begin a new test.
3. While the test is running, prefer `wait` over unnecessary taps.
4. Do not leave the app during the test.

### Phase 3: Wait for completion
1. Wait until the final results screen is fully visible.
2. Confirm that Ping, Download, and Upload values are present before returning `done`.
3. Capture the selected server or location if shown.

### Phase 4: Report results
Return `done` with this exact schema:

```json
{
  "action": "done",
  "params": {
    "ping_ms": 12.3,
    "download_mbps": 242.8,
    "upload_mbps": 18.4,
    "server": "San Francisco, CA",
    "result_summary": "Ping 12.3 ms, Download 242.8 Mbps, Upload 18.4 Mbps via San Francisco, CA"
  },
  "done": true,
  "reasoning": "Successfully ran a fresh Speedtest and extracted the final results"
}
```

## Strict Rules
- Use the installed **Speedtest by Ookla** app only.
- Never use Google search, Chrome, the Play Store, or a website to run the test.
- Do not return `done` until a fresh test has completed and the final results are visible.
- If the app is missing or you cannot reach the real app UI, return `error`.
- If values are partially visible, wait or adjust within the app before giving up.

## Output Format
- **ping_ms**: numeric ping latency in milliseconds
- **download_mbps**: numeric download speed in Mbps
- **upload_mbps**: numeric upload speed in Mbps
- **server**: server name, city, or location string if shown, otherwise null
- **result_summary**: short human-readable summary

## Error Handling
Return `error` with a concise message if:
- The Speedtest app is not installed
- You are stuck outside the Speedtest app
- The test cannot be started after reasonable recovery
- The test never reaches a final result screen
