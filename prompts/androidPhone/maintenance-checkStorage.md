# Check Storage Task

## Goal
Open the Settings app and navigate to storage settings to read current storage usage.

## App Information
- **Package**: com.android.settings
- **App Name**: Settings

## Entry Point Workflow

The Settings app will be launched for you before this task begins.
Wait for the main settings screen to fully load before proceeding.

## Step-by-Step Workflow

### Phase 1: Navigate to Storage Settings
1. On the main Settings screen, scroll to find "Storage" option
2. It may also be under "Battery and device care" or "Device care"
3. Tap on "Storage" or the section containing storage
4. Wait for the storage screen to load

### Phase 2: Read Storage Information
1. Look for the main storage usage display
2. Note the following values:
   - Total storage capacity
   - Used storage amount
   - Free/available storage
3. Look for the percentage or visual bar showing usage
4. Note any category breakdowns (Apps, Images, Videos, etc.)

### Phase 3: Identify Space Consumers
1. Look for "Categories" or breakdown section
2. Note the top storage consumers:
   - Apps and app data
   - Images and photos
   - Videos
   - Audio/music
   - Documents
   - Other/System
3. Some devices show individual large apps

### Phase 4: Record Final Values
1. Confirm you have captured:
   - Total storage
   - Used storage
   - Available storage
   - Top categories consuming space

## Success Criteria
- Successfully navigated to storage settings
- Read and recorded storage values
- Return done with storage information:
```json
{
  "action": "done",
  "params": {
    "total_storage_gb": <total in GB>,
    "used_storage_gb": <used in GB>,
    "free_storage_gb": <free in GB>,
    "used_percent": <percentage>,
    "top_categories": [
      {"name": "Apps", "size_gb": <value>},
      {"name": "Images", "size_gb": <value>}
    ]
  },
  "done": true,
  "reasoning": "Successfully read storage information"
}
```

## Known UI Patterns

### Settings Main Screen
- Search bar at top
- Sections grouped by category
- Storage often has a mini indicator showing usage

### Storage Screen Variants

#### Stock Android / Pixel
- Circular or bar graph at top
- "Manage storage" button
- Category breakdown below
- "Free up space" button

#### Samsung One UI
- Under "Device care" or "Battery and device care"
- Shows storage with ring diagram
- "Clean now" optimization button
- Detailed breakdown by type

#### Other Android Skins
- May be under "Device" section
- Often shows bar graph
- May have "Analyze storage" option

### Storage Categories
- Internal storage vs SD card (if applicable)
- System storage (usually not clearable)
- App data
- Media files
- Cache (often clearable)

## Error Handling

### "Storage not found"
Scroll through all settings. Try searching for "Storage" using the search function.

### "Can't read values"
If numeric values aren't clear, describe what you see on screen.

### "Multiple storage types"
Focus on "Internal storage" or "Phone storage", not SD card.

### "Settings crashed"
Press home and re-launch Settings. Navigate again from the beginning.

## Tips

1. Storage calculation may take a moment - wait for numbers to stabilize
2. "Other" category often includes system files and can't be reduced
3. Cache is usually safe to clear and doesn't affect app data
4. Some devices show "Calculating..." while analyzing - wait for it to complete
5. Screenshots can help verify you captured the right values
