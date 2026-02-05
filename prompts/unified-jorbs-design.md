# Unified Jorbs: Script-Generating Agent Loops

## Overview

Redesign jorbs from "messaging-only agents" to "universal script-generating agents" that can use ANY frank_bot capability while preserving the event-driven nature needed for human interactions.

## Current State

### Current Jorb Actions
```json
{
  "action": {
    "type": "send_message|pause|complete|update_status|no_action",
    "channel": "telegram|sms|email",
    "recipient": "who",
    "content": "message"
  }
}
```

Limited to messaging. Can't use calendar, swarm, Android phone, etc.

### Current Flow
1. ChatGPT or user creates jorb with plan
2. Jorb LLM decides: send message, pause, or complete
3. If message sent → awaiting reply
4. Incoming message triggers next LLM invocation
5. Repeat until complete

## Proposed Design

### New Jorb Output Format
```json
{
  "reasoning": "Thought process",
  "script": "frank.telegram.send('@magic', 'Hotels in Paris?')",
  "await_reply": true,
  "done": false,
  "pause": false,
  "pause_reason": null,
  "result": null
}
```

Or for non-messaging tasks:
```json
{
  "reasoning": "Checking current thermostat state",
  "script": "return frank.android.task_do('Check thermostat')",
  "await_reply": false,
  "done": false
}
```

Or completion:
```json
{
  "reasoning": "Thermostat confirmed at 65-69°F",
  "script": null,
  "done": true,
  "result": {"thermostat": "65-69°F", "status": "confirmed"}
}
```

### Jorb LLM Context

The jorb LLM receives:

```markdown
# Jorb Agent

You are an autonomous agent with access to frank_bot's full capabilities.
Your job is to accomplish the task by generating Python scripts.

## Available Capabilities (frank.* namespace)

### frank.calendar
- frank.calendar.events(day='YYYY-MM-DD') - Get events
- frank.calendar.create(summary, start, end, attendees) - Create event

### frank.contacts  
- frank.contacts.search('query') - Search contacts

### frank.sms
- frank.sms.send('recipient', 'message') - Send SMS

### frank.telegram
- frank.telegram.send('recipient', 'message') - Send Telegram
- frank.telegram.messages('chat', limit=N) - Get recent messages

### frank.swarm
- frank.swarm.checkins(year, category, with_companion) - Location history

### frank.android
- frank.android.task_do('goal') - Phone automation (returns task_id)
- frank.android.task_get(task_id) - Check task status

### frank.time
- frank.time.now() - Current time

### frank.ups
- frank.ups.status() - UPS battery status

## Your Task

{{TASK_PROMPT}}

## Conversation History

{{MESSAGE_HISTORY}}

## Script Results History

{{SCRIPT_RESULTS}}

## Current Event

{{CURRENT_EVENT}}

## Response Format

Output JSON:
{
  "reasoning": "Your thought process (1-2 sentences)",
  "script": "Python expression using frank.* (or null if done/pausing)",
  "await_reply": true/false (set true if script sends a message to human),
  "done": true/false,
  "pause": true/false,
  "pause_reason": "Why pausing (if pause=true)",
  "result": {} (final result if done=true)
}
```

### Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        JORB CREATED                             │
│  - Task prompt from ChatGPT                                     │
│  - Status: "planning"                                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     JORB LLM INVOKED                            │
│  Context: capabilities + task + history                         │
│  Output: {script: "frank.telegram.send(...)", await_reply: true}│
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SCRIPT EXECUTED                              │
│  frank_bot runs the script, captures result                     │
│  Result stored in jorb's script_results history                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────┐
│  await_reply = true     │     │  await_reply = false            │
│  Status: "awaiting"     │     │  Immediately invoke LLM again   │
│  Wait for human reply   │     │  with script result             │
└───────────┬─────────────┘     └─────────────────┬───────────────┘
            │                                     │
            │ (message arrives)                   │
            └─────────────────┬───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 CHECK COMPLETION                                │
│  If done=true → jorb complete, result stored                    │
│  If pause=true → jorb paused, awaiting approval                 │
│  Else → loop back to LLM INVOKED                                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Script Execution Environment
Scripts run in a sandboxed FrankAPI context (same as frankScriptTaskStart).
The `frank` object is injected, scripts are `exec()`ed.

#### 2. Synchronous vs Asynchronous
- **Sync scripts** (calendar, swarm, contacts): Execute, get result, immediately invoke LLM again
- **Async human interaction** (telegram, sms, email): Execute, set `await_reply=true`, wait for incoming message
- **Async phone tasks**: Execute `frank.android.task_do()`, get task_id, LLM can poll with `frank.android.task_get()`

#### 3. Rate Limiting
Max LLM invocations per jorb per time period to prevent runaway loops.
Suggest: 20 invocations per hour, 100 per day.

#### 4. Script Result History
Each script execution result is stored:
```json
{
  "step": 3,
  "script": "frank.swarm.checkins(max_results=1)",
  "result": {"checkins": [{"venue": {"name": "Blue Bottle"}}]},
  "timestamp": "2026-02-05T20:30:00Z"
}
```

LLM sees this history to understand progress.

#### 5. Error Handling
If script throws exception:
- Error captured in result
- LLM invoked with error info
- LLM can retry or decide to fail

#### 6. Android Phone Tasks
For phone automation, jorb generates:
```python
task = frank.android.task_do("Set thermostat to 65-69")
return {"task_id": task["task_id"], "status": task["status"]}
```

Next iteration, LLM can check:
```python
result = frank.android.task_get("task-123")
return result
```

And interpret the result to decide if done or needs retry.

## Implementation Changes

### 1. Update jorb_session_system.md
New prompt template with full frank_bot capabilities.

### 2. Update agent_runner.py
- Change action parsing from message-only to script execution
- Add script execution via FrankAPI
- Handle `await_reply` flag for async human interactions

### 3. Add frank.android namespace to FrankAPI
Expose `task_do()` and `task_get()` so scripts can use phone automation.

### 4. Update JorbStorage
Add `script_results: list[dict]` field to track execution history.

### 5. Update jorb response schema
New JSON format with `script`, `await_reply`, `done`, `pause`, `result`.

## Migration

Existing jorbs (messaging-only) continue to work - the new format is a superset.
The LLM can still output `frank.telegram.send(...)` for human interactions.

## Benefits

1. **Unified model** - One pattern for all autonomous tasks
2. **Full capability access** - Jorbs can use calendar, Android, swarm, everything
3. **Preserved async** - Human interactions still event-driven
4. **Composable** - Jorb can mix messaging with other actions
5. **ChatGPT as prompt engineer** - Crafts the task, jorb LLM solves it

## Example: Hotel Booking via Magic

**ChatGPT creates jorb:**
```
jorbCreate(
  name="Book Paris hotel via Magic",
  plan="Contact Magic on Telegram to find hotels in Paris for March 15-20, 
        2 guests, under $200/night. Get at least 3 options with prices.
        Pause before confirming any booking."
)
```

**Jorb LLM iteration 1:**
```json
{
  "reasoning": "Starting by contacting Magic with the hotel request",
  "script": "frank.telegram.send('@magicapp', 'Hi! Looking for hotels in Paris, March 15-20, 2 guests, budget under $200/night. Can you find some options?')",
  "await_reply": true,
  "done": false
}
```

**Hours later, Magic replies...**

**Jorb LLM iteration 2:**
```json
{
  "reasoning": "Magic found 3 options. Summarizing for Sean and pausing for approval.",
  "script": null,
  "done": false,
  "pause": true,
  "pause_reason": "Magic found 3 hotels:\n1. Hotel Le Marais - $175/night\n2. Hotel Bastille - $165/night\n3. Boutique Saint-Germain - $195/night\n\nWhich should I book?"
}
```

**Sean approves Hotel Le Marais via jorbApprove...**

**Jorb LLM iteration 3:**
```json
{
  "reasoning": "Sean approved Hotel Le Marais. Confirming with Magic.",
  "script": "frank.telegram.send('@magicapp', 'Please book Hotel Le Marais for March 15-20. Confirm when done!')",
  "await_reply": true,
  "done": false
}
```

**Magic confirms booking...**

**Jorb LLM iteration 4:**
```json
{
  "reasoning": "Booking confirmed! Task complete.",
  "script": null,
  "done": true,
  "result": {
    "hotel": "Hotel Le Marais",
    "dates": "March 15-20, 2026",
    "price": "$175/night ($875 total)",
    "confirmation": "Booked via Magic"
  }
}
```

## Example: Thermostat via Android

**ChatGPT creates jorb:**
```
jorbCreate(
  name="Set thermostat 65-69",
  plan="Use the Android phone to set the Nest thermostat to heat range 65-69°F.
        Verify the change took effect."
)
```

**Jorb LLM iteration 1:**
```json
{
  "reasoning": "Starting phone automation to check current thermostat state",
  "script": "frank.android.task_do('Open Google Home and check the Nest thermostat current temperature and settings')",
  "await_reply": false,
  "done": false
}
```

**Script returns task_id, LLM polls...**

**Jorb LLM iteration 2:**
```json
{
  "reasoning": "Checking phone task status",
  "script": "frank.android.task_get('task-abc123')",
  "await_reply": false,
  "done": false
}
```

**Task complete with result...**

**Jorb LLM iteration 3:**
```json
{
  "reasoning": "Current temp is 68°F, range is 66-72. Need to change to 65-69.",
  "script": "frank.android.task_do('Set the Nest thermostat heat range to 65-69 degrees')",
  "await_reply": false,
  "done": false
}
```

**... polling and verification ...**

**Jorb LLM final:**
```json
{
  "reasoning": "Verified thermostat now set to 65-69°F",
  "script": null,
  "done": true,
  "result": {
    "previous_range": "66-72°F",
    "new_range": "65-69°F",
    "current_temp": "68°F",
    "status": "confirmed"
  }
}
```
