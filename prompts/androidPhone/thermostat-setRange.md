# Thermostat Set Range Task

## Goal
Set the thermostat to a specific temperature range (heat/cool setpoints).

## Parameters
- **low_temp**: Target low temperature (heating setpoint) in Fahrenheit. Value: {low_temp}
- **high_temp**: Target high temperature (cooling setpoint) in Fahrenheit. Value: {high_temp}

## App Information
- **Package**: com.google.android.apps.chromecast.app (Google Home)
- **App Name**: Google Home
- **Thermostat Name**: The Nest thermostat may appear as "Thermostat" or "Living Room" or similar

## Entry Point Workflow

If Google Home app is not already open on the thermostat screen:
1. The app will be launched for you
2. Wait for the home screen to load
3. Find the thermostat device card/tile (may show current temperature)
4. Tap the thermostat to open its detail view

## Step-by-Step Workflow

### Phase 1: Navigate to Thermostat
1. Look for a device showing a temperature (e.g., "72°" or "Thermostat")
2. Tap the thermostat device card
3. Wait for the thermostat detail view to load
4. Verify you can see temperature controls

### Phase 2: Access Temperature Range Controls
1. Look for the current temperature setpoints
2. Find controls to adjust the range:
   - May be a slider with two handles (heat and cool)
   - May be +/- buttons for each setpoint
   - May be a "Schedule" or "Temperature" section to tap
3. If in "Heat only" or "Cool only" mode, you may need to switch to "Heat/Cool" (auto) mode first

### Phase 3: Set Low Temperature (Heat Setpoint)
1. Find the heat setpoint control (usually orange/red colored or labeled "Heat to")
2. Current value should be visible
3. Adjust to {low_temp}°F:
   - If using +/- buttons, tap repeatedly until target reached
   - If using slider, drag to approximate position
4. Verify the displayed value matches {low_temp}

### Phase 4: Set High Temperature (Cool Setpoint)
1. Find the cool setpoint control (usually blue colored or labeled "Cool to")
2. Current value should be visible
3. Adjust to {high_temp}°F:
   - If using +/- buttons, tap repeatedly until target reached
   - If using slider, drag to approximate position
4. Verify the displayed value matches {high_temp}

### Phase 5: Save and Verify
1. Look for a "Save", "Done", "Apply", or back button
2. Tap to confirm the changes
3. The thermostat view should now show:
   - Heat to: {low_temp}°F
   - Cool to: {high_temp}°F
4. If the values don't match, retry adjustment

## Success Criteria
- The thermostat detail view shows heat setpoint = {low_temp}°F
- The thermostat detail view shows cool setpoint = {high_temp}°F
- No error messages are displayed
- Return done with the final confirmed temperatures:
```json
{
  "action": "done",
  "params": {
    "final_low_temp": <actual low temp set>,
    "final_high_temp": <actual high temp set>,
    "mode": "heat_cool"
  },
  "done": true,
  "reasoning": "Successfully set thermostat range"
}
```

## Known UI Patterns

### Google Home Thermostat Card
- Shows current temperature prominently
- May show "Heating" or "Cooling" indicator
- Device name below the temperature
- Tap anywhere on card to open detail

### Thermostat Detail View
- Large temperature display in center
- Circular or arc dial for adjustment
- Mode buttons (Heat, Cool, Heat/Cool, Off)
- Schedule button
- Settings gear icon

### Temperature Adjustment Methods
- **Circular dial**: Drag around the circle to adjust
- **Arc slider**: Two handles for heat/cool range
- **Direct tap**: Tap temperature numbers to edit
- **+/- buttons**: Increment/decrement buttons

### Mode Switching
- If only one temperature is settable, check if mode is "Heat only" or "Cool only"
- Switch to "Heat & Cool" or "Auto" mode to set a range
- Mode selector may be at top or bottom of screen

## Error Handling

### "App not installed"
Return error - Google Home app must be installed.

### "Thermostat offline"
Return error with message indicating device is offline.

### "Cannot find thermostat"
Swipe to scroll through devices. If still not found after full scroll, return error.

### "Mode doesn't support range"
If thermostat is in Heat-only or Cool-only mode:
1. Find mode selector
2. Switch to "Heat & Cool" or "Auto"
3. Then proceed with setting range

### "Temperature out of range"
If the app won't accept the temperature:
- Return error indicating the valid range
- Don't force an invalid value

### "Screen navigation failed"
1. Press back button
2. Try again from thermostat card
3. If still failing after 3 attempts, return error

## Tips

1. Google Home UI may vary by version - adapt to what you see
2. Temperature controls may be touch-sensitive - precise taps help
3. After adjusting, the value may take a moment to update
4. If you see a "Hold" option, that's for temporary override - use it
5. The thermostat may round to nearest whole degree
