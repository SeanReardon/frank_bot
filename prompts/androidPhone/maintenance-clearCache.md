# Clear Cache Task

## Goal
Navigate to Settings and clear cached data for apps consuming the most space to free up storage.

## App Information
- **Package**: com.android.settings
- **App Name**: Settings

## Parameters
- **min_free_percent**: Target minimum free storage percentage. Value: {min_free_percent}

## Entry Point Workflow

The Settings app will be launched for you before this task begins.
Wait for the main settings screen to fully load before proceeding.

## Step-by-Step Workflow

### Phase 1: Navigate to Apps
1. On the main Settings screen, find "Apps" or "Applications"
2. It may be labeled "Apps & notifications" or just "Apps"
3. Tap on the Apps section
4. Wait for the app list to load

### Phase 2: Find Large Apps
1. Look for a sort/filter option (often three dots menu or filter icon)
2. If available, sort by "Size" or "Storage used"
3. If no sort option, scroll through the list
4. Identify apps using significant storage (>100MB cache)
5. Focus on apps you use regularly (these accumulate more cache)

### Phase 3: Clear Cache for Top Apps
For each large app (repeat 3-5 times):
1. Tap on the app name to open app info
2. Look for "Storage" or "Storage & cache" option
3. Tap on Storage
4. Look for "Clear cache" button (NOT "Clear data"!)
5. Tap "Clear cache"
6. Verify cache is cleared (should show 0 B or "0 MB" for cache)
7. Press back to return to app list
8. Move to the next large app

### Phase 4: Check Global Cache (if available)
Some devices have a global cache clear option:
1. Go back to main Settings
2. Navigate to Storage
3. Look for "Cached data" or "Cache" category
4. If there's an option to clear all cache, tap it
5. Confirm if prompted

### Phase 5: Verify Results
1. Navigate back to Storage settings
2. Check the new free storage amount
3. Confirm storage has improved

## Success Criteria
- Cleared cache for at least 3-5 large apps
- Did NOT clear app data (only cache)
- Storage improved
- Return done with clearing results:
```json
{
  "action": "done",
  "params": {
    "apps_cleared": ["App 1", "App 2", "App 3"],
    "space_freed_mb": <approximate MB freed>,
    "current_free_percent": <new free percentage>,
    "target_met": true
  },
  "done": true,
  "reasoning": "Successfully cleared cache for X apps"
}
```

## Known UI Patterns

### App List Screen
- Alphabetical list by default
- Three-dot menu often has sort options
- Shows app icon, name, and sometimes size
- "See all" may be needed to view full list

### App Info Screen
- Shows app name and icon at top
- "Force stop" button
- "Uninstall" or "Disable" button
- Multiple sections: Notifications, Permissions, Storage, etc.

### Storage Screen for App
- Shows "App size" (the APK itself)
- Shows "User data" (important - DO NOT clear!)
- Shows "Cache" (safe to clear)
- "Clear cache" button
- "Clear data" or "Clear storage" button (AVOID!)

### Common Large Cache Apps
- Chrome / Browsers (web page cache)
- Social media apps (images, videos)
- YouTube (video cache)
- Maps (offline maps, route cache)
- Streaming apps (Netflix, Spotify)
- News apps

## Error Handling

### "Clear cache button disabled"
Some system apps don't allow cache clearing. Skip and move to next app.

### "App info not loading"
Press back and tap the app again. If still failing, skip to next app.

### "Accidentally opened Clear Data"
DO NOT CONFIRM! Press back or cancel immediately. Clear data erases app settings and login info.

### "Storage not improving"
Cache clearing has diminishing returns. If you've cleared 5+ apps with minimal improvement, the remaining storage may be in non-cache files.

### "Cannot find sort option"
Manually scroll through the list. System apps are usually at the bottom. Focus on third-party apps.

## Safety Warnings

1. **NEVER tap "Clear data" or "Clear storage"** - this deletes app settings and login info
2. **Cache is always safe** - it's temporary files that can be recreated
3. **Some apps may need to re-download content** after cache clear (e.g., Spotify offline music)
4. **Browser cache clear will log you out of websites** in some cases

## Tips

1. Start with browsers - they usually have large caches
2. Social media apps (Instagram, Facebook, TikTok) accumulate huge caches
3. Streaming apps cache video content
4. Games often have large caches for assets
5. Clear cache doesn't uninstall the app or lose your progress
6. You may need to scroll within Storage screen to see Clear cache button
