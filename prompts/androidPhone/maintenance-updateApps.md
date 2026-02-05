# App Update Task

## Goal
Navigate the Google Play Store to check for and install available app updates.

## App Information
- **Package**: com.android.vending (Google Play Store)
- **App Name**: Play Store

## Entry Point Workflow

The Play Store app will be launched for you before this task begins.
Wait for the home screen to fully load before proceeding.

## Step-by-Step Workflow

### Phase 1: Navigate to My Apps
1. Look for the profile icon (usually top-right corner, circular with letter or photo)
2. Tap the profile icon
3. Wait for the profile menu to appear
4. Look for "Manage apps & device" or "Manage apps and device"
5. Tap "Manage apps & device"

### Phase 2: Check for Updates
1. Wait for the app management screen to load
2. Look for "Updates available" section or indicator
3. If you see a number badge (e.g., "5 updates available"), note the count
4. Tap on "Updates available" or "See details" to view the list
5. If no updates are available, the task is complete

### Phase 3: Install Updates
1. On the updates screen, look for "Update all" button
2. If "Update all" is visible, tap it
3. Wait for downloads and installations to begin
4. You may see a progress indicator or download progress for each app
5. Wait for all updates to complete (may take several minutes)
6. Verify the updates are complete - the "Update all" button should disappear or become disabled

### Phase 4: Verify Completion
1. Check that the updates screen shows "All apps up to date" or similar message
2. If individual apps still show "Update" buttons, those may have failed
3. Note any apps that failed to update

## Success Criteria
- Successfully navigated to app updates section
- Either "Update all" was tapped and completed, or confirmed no updates available
- Return done with update status:
```json
{
  "action": "done",
  "params": {
    "updates_available": <number of updates found>,
    "updates_installed": <number successfully installed>,
    "failed_updates": [],
    "all_apps_current": true
  },
  "done": true,
  "reasoning": "Successfully updated all apps"
}
```

## Known UI Patterns

### Play Store Home Screen
- Bottom navigation with: Games, Apps, Search
- Profile icon in top-right
- Search bar at top

### Profile Menu
- Shows account name/email
- "Manage apps & device" near top
- "Help & feedback" near bottom
- "Play Protect" option

### Manage Apps & Device Screen
- "Overview" tab showing update count
- "Manage" tab for individual app management
- Device status indicators

### Updates Screen
- "Update all" button at top
- List of apps with "Update" button for each
- App size shown
- "What's new" expandable sections

## Error Handling

### "No network connection"
Return error indicating device needs WiFi/data connection.

### "Insufficient storage"
Return error indicating storage is full. Suggest running cache clearing first.

### "Download pending"
Wait for download queue to process. Google Play limits concurrent downloads.

### "Update failed" for specific app
Continue with other updates. Report the failed app in the result.

### "Play Store not responding"
Press home key and re-launch Play Store. Try again from Phase 1.

### "Sign in required"
Return error - user needs to sign in to Google account manually.

## Tips

1. The UI varies by Play Store version - adapt to what you see
2. Updates may auto-start downloading in the background
3. Large updates over 100MB may require WiFi
4. Some updates need device restart to complete
5. If an app is in use, its update may be delayed until next app restart
