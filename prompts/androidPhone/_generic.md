# Generic Task - Goal-Based Automation

## Goal
{{GOAL}}

## Task Type
This is a flexible, goal-based task. You must analyze the goal description and determine the appropriate app, workflow, and actions needed.

## General Approach

### Phase 1: Understand the Goal
1. Parse the natural language goal
2. Identify which app is needed (if not already specified)
3. Determine what information to extract or actions to take
4. Plan a logical sequence of steps

### Phase 2: Navigate to Target
1. If an app needs to be launched, it will be done for you
2. Navigate through the app to reach the relevant screen
3. Look for UI elements that match your goal

### Phase 3: Execute Actions
1. Perform the necessary interactions (tap, type, swipe)
2. Verify each action had the expected effect
3. Continue until goal is achieved

### Phase 4: Report Results
Return done with extracted data or confirmation:
```json
{
  "action": "done",
  "params": {
    "result": "Description of what was accomplished",
    "extracted_data": { ... any data read from the screen ... }
  },
  "done": true,
  "reasoning": "Task completed successfully"
}
```

## Common Task Patterns

### Reading Information
- Navigate to where the information is displayed
- Extract text/values from screen elements
- Return the data in params

### Setting Values
- Navigate to the settings/control screen
- Adjust values using available controls
- Verify the new values are displayed
- Return confirmation with final values

### Ordering/Requesting Services
- Open the service app
- Navigate through the ordering flow
- Fill in required fields
- STOP before final confirmation/payment
- Return the order details for human review

### Controlling Smart Home Devices
- Open Google Home or device-specific app
- Find the device
- Adjust settings as requested
- Verify and return new status

## App Recognition

Based on the goal, recognize which app to use:
- **Thermostat/Temperature/HVAC**: Google Home (com.google.android.apps.chromecast.app)
- **Uber/Ride**: Uber (com.ubercab)
- **Lyft**: Lyft (com.lyft.android)
- **DoorDash/Food Delivery**: DoorDash (com.dd.doordash)
- **Uber Eats**: Uber Eats (com.ubercab.eats)
- **Lights/Smart Home**: Google Home
- **Browser/Search**: Chrome (com.android.chrome)
- **Maps/Directions**: Google Maps (com.google.android.apps.maps)

## Safety Rules

### Always Stop Before
1. Confirming a purchase or payment
2. Submitting financial transactions
3. Deleting important data
4. Sending messages to strangers
5. Making reservations/bookings
6. Any irreversible action

### When in Doubt
Return the current state and ask for confirmation:
```json
{
  "action": "done",
  "params": {
    "status": "needs_confirmation",
    "current_state": "...",
    "next_action": "What would happen next",
    "question": "Should I proceed with X?"
  },
  "done": true,
  "reasoning": "Stopping for human confirmation before irreversible action"
}
```

## Success Criteria
- Goal has been achieved OR
- Necessary information has been extracted OR
- Process has been completed up to confirmation step OR
- An error condition has been clearly identified

## Error Handling
If the goal cannot be achieved:
```json
{
  "action": "error",
  "params": {"message": "Why the goal couldn't be achieved"},
  "done": true,
  "reasoning": "Detailed explanation"
}
```

## Output Format
Always return structured data when possible:
- For status queries: return the values read
- For actions: return confirmation of what was done
- For orders: return order details ready for review
