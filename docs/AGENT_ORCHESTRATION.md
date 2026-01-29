# Agent Orchestration System

## Overview

Frank_bot evolves from a simple actions server into a **personal agent runtime** - capable of executing long-running, autonomous tasks that span hours or days, interacting with the real world on your behalf.

## The Three Parties

```
┌─────────────────────────────────────────────────────────────────┐
│  1. SEAN (human, via any LLM chat interface)                    │
│     - Design plans collaboratively                              │
│     - Approve thresholds and checkpoints                        │
│     - Check in on progress                                      │
│     - Make decisions when agent pauses                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ /jorbs, /jorbs/{id}, /jorbs/brief
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. FRANK_BOT (orchestration hub)                               │
│     - Task storage and state management                         │
│     - Multi-channel message routing (SMS, Telegram, Email)      │
│     - Context window management ("Ralph loop")                  │
│     - Policy enforcement (spending limits, approvals)           │
│     - Daily digest generation                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ LLM API calls (swappable provider)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. LLM (the reasoning brain)                                   │
│     - Receives: incoming events + all active jorb contexts      │
│     - Disambiguates: which jorb does this message belong to?    │
│     - Decides: what action to take next                         │
│     - Knows when to pause for human approval                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Tool execution
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. WORLD (external services)                                   │
│     - Telegram (Telethon) → Magic, company bots                 │
│     - SMS (Telnyx) → Any business phone number                  │
│     - Email (SMTP) → Businesses, daily digest                   │
│     - Frank_bot APIs → Calendar, contacts, Swarm, etc.          │
│     - (Future) WhatsApp → Additional reach                      │
└─────────────────────────────────────────────────────────────────┘
```

## Task Lifecycle

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ PLANNING │ -> │ RUNNING  │ -> │ PAUSED   │ -> │ COMPLETE │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │
     │               │               │               │
  Sean + LLM      LLM            Awaiting         Results
  design the      executing       Sean's           ready for
  plan            autonomously    decision         review
```

### States

| State | Description |
|-------|-------------|
| `planning` | Task created but not yet started |
| `running` | Agent actively working on task |
| `paused` | Waiting for human input (approval, decision, clarification) |
| `complete` | Task finished successfully |
| `failed` | Task encountered unrecoverable error |
| `cancelled` | User cancelled the task |

## Policy & Guardrails

```python
class TaskPolicy:
    # Spending
    max_spend_without_approval: float = 100.00
    
    # Rate limiting
    max_messages_per_hour: int = 20
    max_messages_per_task_per_day: int = 50
    
    # Approval requirements
    require_approval_for: list = [
        "purchase",
        "commit",      # Confirm reservation, accept offer
        "cancel",      # Cancel existing booking
        "share_info",  # Share personal info (address, etc.)
    ]
    
    # Timeouts
    stale_task_hours: int = 48          # Pause if no activity
    max_task_duration_days: int = 14    # Hard limit
    
    # Notifications
    notify_human_via: str = "email"
    notify_on: list = ["pause", "complete", "error", "daily_digest"]
```

## Daily Digest

**From:** frank_bot@contrived.com  
**To:** sean.reard@gmail.com  
**Subject:** Frank Bot Daily Summary - {date}

### Contents

1. **Active Jorbs Summary**
   - Jorb name, status, last activity
   - Pending decisions needed

2. **Completed Jorbs**
   - What was accomplished
   - Final outcomes

3. **All Interactions Log**
   - Chronological list of all messages sent/received
   - Grouped by jorb
   - Channel indicated (SMS, Telegram, etc.)

4. **Agent Reasoning Highlights**
   - Key decisions the agent made
   - Why it paused (if applicable)

5. **Costs**
   - LLM token usage
   - SMS messages sent
   - Any purchases made via Magic

## "Brief Me" Endpoint

For interactive check-ins via any LLM chat interface, the `/jorbs/brief` endpoint provides:

```
Sean: "Hey, what's been going on with my jorbs?"

LLM: [calls GET /jorbs/brief]

LLM: "Here's what's happened since yesterday:

📬 Activity: 12 messages received, 8 sent

🏨 GDC Hotel (jorb_47) - NEEDS YOUR DECISION
Magic got quotes: Nikko $289/night, Marriott sold out.
Ready to book?

✈️ Flight Monitor (jorb_52) - Still running
Prices still above $400. Will alert when it drops."
```

The endpoint returns:
- **needs_attention**: Jorbs that are paused, failed, or complete
- **activity_summary**: Message counts, jorbs created/completed since last briefing
- **highlights**: Last 5 significant events
- **pending_decisions**: What the user needs to decide

The briefing timestamp updates after each call, so subsequent briefings show only new activity.

## Context Management ("Ralph Loop")

Instead of guessing when context is full, we use a simple rule:

**Hard reset every 3 days, but only if there's been activity.**

If nothing has happened (no messages from user or outside world), the agent state stays the same.

### Reset Process

```python
async def maybe_reset_context():
    """Called daily. Checks if 3 days passed AND there's activity."""
    if days_since_last_reset() >= 3 and has_activity_since_last_reset():
        await perform_context_reset()

async def perform_context_reset():
    # Ask agent to produce structured handoff
    handoff = await agent.generate_handoff()
    
    # Append to progress log (Claudia-inspired format)
    await append_to_progress_log(handoff.progress_entry)
    
    # Update task states
    for task_state in handoff.task_states:
        await storage.update_task(task_state.id, summary=task_state.summary)
    
    # Record reset for next cycle
    record_reset_timestamp()
```

### Progress Log Format

File: `data/jorbs_progress.txt`

```markdown
## 2026-01-28: Session handoff (3-day reset)

### Active Jorbs

**jorb_47 - GDC Hotel Search** (PAUSED)
- Status: Awaiting user approval to book Hotel Nikko
- Progress: Contacted Magic, got quotes for 3 hotels
- Next steps: Once approved, confirm booking with Magic

### Session Summary
- Processed 23 incoming messages across 4 channels
- Made 8 outbound messages (5 Telegram, 3 SMS)
- No purchases made (1 awaiting approval)

### Learnings
- Magic responds faster in morning hours (PST)
- Hotel Zetta doesn't respond to SMS, only phone calls
```

### Fresh Session Context

When starting after reset, agent receives:
- Original plans for all active jorbs
- Current jorb states (from handoff summaries)
- Last 100 lines of progress log
- Current policy settings

## Message Debouncing

Humans (and services like Magic) often send multiple messages in quick succession to express a single thought:

```
Magic: "Hi!"
Magic: "So I checked on the hotels"
Magic: "Nikko has availability"
Magic: "at $289/night"
Magic: "Want me to book it?"
```

Without debouncing, each message would trigger a separate LLM API call, causing chaos and wasted tokens.

**Solution: Per-conversation debounce timer**

```python
class MessageBuffer:
    def __init__(self, debounce_seconds: int = 60):
        self.debounce_seconds = debounce_seconds
        self.buffers: dict[str, ConversationBuffer] = {}
    
    async def on_message(self, event: IncomingEvent):
        key = f"{event.channel}:{event.sender}"
        
        if key not in self.buffers:
            self.buffers[key] = ConversationBuffer()
        
        buffer = self.buffers[key]
        buffer.messages.append(event)
        buffer.reset_timer(self.debounce_seconds)
    
    async def on_timer_expired(self, key: str):
        buffer = self.buffers.pop(key)
        
        # Combine all messages into one event
        combined_event = IncomingEvent(
            channel=buffer.messages[0].channel,
            sender=buffer.messages[0].sender,
            content="\n".join(m.content for m in buffer.messages),
            timestamp=buffer.messages[-1].timestamp,
            message_count=len(buffer.messages),
        )
        
        # NOW send to LLM
        await route_incoming_event(combined_event)
```

**Timer behavior:**
- Default: 60 seconds
- Each new message from the same sender resets the timer
- When timer expires, all accumulated messages are bundled and sent to LLM
- Timer is per-conversation (channel + sender), so different senders don't block each other

**Configurable per channel:**

```python
DEBOUNCE_SECONDS = {
    "telegram": 60,    # People tend to send multiple messages
    "sms": 30,         # SMS tends to be more complete per message
    "email": 0,        # Emails are already complete thoughts
}
```

## Event Routing

When a message arrives (SMS, Telegram, etc.), frank_bot packages it for the agent:

```python
async def route_incoming_event(event: IncomingEvent):
    context = {
        "event": {
            "channel": event.channel,      # "telegram", "sms", etc.
            "sender": event.sender,         # Phone number, username, etc.
            "content": event.content,
            "timestamp": event.timestamp,
        },
        "active_tasks": [
            {
                "task_id": t.id,
                "name": t.name,
                "plan": t.original_plan,
                "progress": t.progress_summary,
                "recent": t.recent_messages[-10],
                "status": t.status,
                "awaiting": t.awaiting,  # What we're waiting for
            }
            for t in get_active_tasks()
        ],
        "policy": current_policy,
    }
    
    response = await agent.process(context)
    
    # Execute the agent's decision
    await execute_action(response.action)
    
    # Log everything
    log_interaction(event, response)
```

## File Structure

```
frank_bot/
├── services/
│   ├── telegram_client.py    # Telethon wrapper
│   ├── email_service.py      # SMTP for digest + notifications
│   ├── agent_runner.py       # LLM API wrapper + context mgmt
│   └── task_storage.py       # SQLite persistence
├── actions/
│   ├── tasks.py              # create_task, get_task, list_tasks, etc.
│   └── agent.py              # process_event, checkpoint, etc.
├── prompts/
│   └── agent_system.md       # System prompt for autonomous agent
└── data/
    └── tasks.db              # Task state, history, logs
```

## Environment Variables

```bash
# Existing
TELNYX_API_KEY=...

# LLM Provider (swappable)
LLM_PROVIDER=openai              # or "anthropic", "local", etc.
LLM_API_KEY=sk-...               # Provider-specific key

# New for agent orchestration
TELEGRAM_API_ID=...           # From my.telegram.org
TELEGRAM_API_HASH=...         # From my.telegram.org
TELEGRAM_SESSION_NAME=frank_bot

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=frank_bot@contrived.com
SMTP_PASSWORD=...
DIGEST_EMAIL_TO=sean.reard@gmail.com

AGENT_SPEND_LIMIT=100.00
AGENT_MODEL=gpt-5.2
DEBOUNCE_TELEGRAM_SECONDS=60
DEBOUNCE_SMS_SECONDS=30

CONTEXT_RESET_DAYS=3
JORBS_PROGRESS_LOG=./data/jorbs_progress.txt
```

## Security Considerations

1. **Credential isolation** - Telegram session, SMTP creds stored securely
2. **Action logging** - Every action logged with full context for audit
3. **Approval gates** - Spending and commitments require explicit approval
4. **Rate limiting** - Prevent runaway message loops
5. **Session management** - Telegram session can be revoked if compromised

## Example: GDC Hotel Task

### Planning Phase (Sean + LLM chat)

```
Sean: I need to book a hotel for GDC in SF, March 17-21.

LLM: Let me check your Swarm history for SF hotels...
[calls /swarm/checkins?city=San+Francisco]

Found 8 hotels you've stayed at. Ranked by GDC proximity + repeat visits:
1. Hotel Nikko (stayed 3x, 0.2mi from Moscone)
2. Marriott Union Square (stayed 2x, 0.3mi)
...

Want me to create a jorb to contact Magic and get availability/pricing 
for the top 4?

Sean: Yes, go ahead. Budget max $350/night.

LLM: [calls /jorbs/create with plan]
Jorb #47 created. I'll check availability via Magic on Telegram and 
text the hotels directly for current rates. I'll pause before any 
booking and report back within 48 hours.
```

### Execution Phase (Autonomous Agent)

```
[Agent sends Telegram to Magic]
"Hi! Can you check availability at Hotel Nikko SF for March 17-21, 
1 king room? Also Marriott Union Square same dates. Budget up to 
$350/night. Thanks!"

[12 hours later, Magic replies]
"Hotel Nikko has a king for $289/night. Marriott is sold out. 
Want me to book Nikko?"

[Agent updates task, sends SMS to Hotel Zetta as backup]
[Agent pauses task - booking requires approval]
```

### Review Phase (Sean + LLM chat)

```
Sean: Check on my hotel jorb.

LLM: [calls /jorbs/47]
Jorb #47 - GDC Hotel - PAUSED (awaiting approval)

Results so far:
- Hotel Nikko: $289/night - AVAILABLE ✓
- Marriott Union Square: SOLD OUT
- Hotel Zetta: $315/night - AVAILABLE ✓
- Proper Hotel: No response yet

Magic is ready to book Nikko. Approve?

Sean: Yes, book Nikko.

LLM: [calls /jorbs/47/approve?decision=book+nikko]
Done! Magic is booking Hotel Nikko for March 17-21.
```
