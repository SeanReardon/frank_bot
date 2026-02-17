# Thermostat Get Status Task

## Goal
Read the current thermostat status including temperature, setpoints, mode, and humidity.

## Parameters
None required.

## App Information
- **Package**: com.google.android.apps.chromecast.app (Google Home)
- **App Name**: Google Home
- **Thermostat Name**: The Nest thermostat may appear as "Thermostat" or "Living Room" or similar

## Entry Point Workflow

If Google Home app is not already open on the thermostat screen:
1. The app will be launched for you
2. Wait for the home screen to load
3. Find the thermostat device card/tile (shows current temperature)
4. Tap the thermostat to open its detail view

## Step-by-Step Workflow

### Phase 1: Navigate to Thermostat
1. Look for a device showing a temperature (e.g., "72°" or "Thermostat")
2. Note: The home screen may already show current temp on the card
3. Tap the thermostat device card
4. Wait for the thermostat detail view to load

### Phase 2: Read Current Temperature
1. Find the large temperature display
2. This is the current ambient temperature (what the thermostat sensor reads)
3. Note the value in Fahrenheit

### Phase 3: Read Target Temperatures
1. Find the setpoint temperatures:
   - **Heat setpoint**: Usually labeled "Heat to" or shown in orange/red
   - **Cool setpoint**: Usually labeled "Cool to" or shown in blue
   - May be shown as a range (e.g., "68° - 72°")
2. If only one setpoint is shown, the mode may be Heat-only or Cool-only
3. Note both values

### Phase 4: Read Current Mode
1. Look for mode indicators:
   - "Heating" - Currently running heat
   - "Cooling" - Currently running AC
   - "Off" - System is off
   - "Idle" - System not actively heating/cooling
   - "Eco" - Energy saving mode
   - "Heat & Cool" / "Auto" - Range mode enabled
2. Note the current mode

### Phase 5: Read Humidity (if available)
1. Look for humidity reading (often shown as percentage)
2. May be in main display or in a secondary info area
3. If not visible, humidity may not be supported or displayed

### Phase 6: Report Results
Return done with all extracted data:
```json
{
  "action": "done",
  "params": {
    "current_temp": 72,
    "target_low": 68,
    "target_high": 74,
    "mode": "heat_cool",
    "humidity": 45,
    "status": "idle"
  },
  "done": true,
  "reasoning": "Successfully read thermostat status"
}
```

## Success Criteria
- Current temperature is read
- Target temperature(s) are identified
- Mode is determined
- Humidity is included if visible
- Return data in the specified JSON format

## Output Format

Return the following fields (use null if not available):
- **current_temp**: Current ambient temperature in °F (integer)
- **target_low**: Heat setpoint in °F (integer, null if heat-only not set)
- **target_high**: Cool setpoint in °F (integer, null if cool-only not set)
- **mode**: One of: "heat", "cool", "heat_cool", "eco", "off"
- **humidity**: Humidity percentage (integer, null if not shown)
- **status**: One of: "heating", "cooling", "idle", "off"

### IMPORTANT (strict schema)
- Use the exact key names above. Do not emit alternate keys like `current_temperature`, `setpoints`, `heat_setpoint`, etc.
- Values must be integers (or null). Do not include degree symbols, units, or explanatory strings in the values.
- Only return `"action": "done"` when you have at least:
  - `current_temp` (int)
  - `mode` (one of the allowed strings)
  - at least one of `target_low` / `target_high` (int)
- If you cannot read the numbers reliably, return `"action": "error"` with a concise message and stop.

## Known UI Patterns

### Temperature Display
- Large number in center of screen (current temp)
- Smaller numbers for setpoints
- Color coding: orange/red for heat, blue for cool
- Circle or arc showing range

### Status Indicators
- "Heating" text with flame icon
- "Cooling" text with snowflake icon
- "Eco" with leaf icon
- Color of display ring may indicate active heating/cooling

### Mode Display
- Mode name at top or bottom of screen
- Icons representing each mode
- May need to scroll to see all info

### Humidity Display
- Often shown as "XX%" near temperature
- May be in a separate "Indoor climate" section
- Some thermostats don't display humidity

## Error Handling

### "App not installed"
Return error - Google Home app must be installed.

### "Thermostat offline"
Return error with message:
```json
{
  "action": "error",
  "params": {"message": "Thermostat is offline or unreachable"},
  "done": true,
  "reasoning": "Device shows offline status"
}
```

### "Cannot find thermostat"
Swipe to scroll through devices. If still not found after full scroll, return error.

### "Cannot read values"
If temperature display is obscured or unclear:
1. Try tapping the display area to reveal more info
2. Look for alternative displays or settings
3. If values cannot be determined, return error

### "Screen navigation failed"
1. Press back button
2. Try again from thermostat card
3. If still failing after 3 attempts, return error

## Tips

1. The home screen card often shows current temp - can read it there
2. Detail view provides more information (setpoints, mode, humidity)
3. If display shows "- -" or "--", thermostat may be disconnected
4. Mode may determine which setpoints are shown (Heat-only shows only heat target)
5. Active heating/cooling may be indicated by animated elements
6. Don't confuse current temp with target temp - current is what sensor reads
