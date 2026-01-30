# Disable SMS Webhook in let-food-into-civic

## Context

SMS handling is moving from let-food-into-civic to frank_bot. The Telnyx phone number `+12148170664` is shared:

- **Voice calls**: Still handled by let-food-into-civic (call box → DTMF unlock)
- **SMS**: Now handled by frank_bot (this change)

## What to Do

### Option A: Comment out the webhook (Recommended)

In `src/main.py`, comment out the `/webhook/sms` route and handler (lines 872-997). This preserves the code for reference but disables it.

```python
# =============================================================================
# SMS Webhook - DISABLED: SMS now handled by frank_bot
# See: https://github.com/contrived/frank_bot/blob/main/prompts/sms-receive-and-mms.json
# =============================================================================

# @app.route("/webhook/sms", methods=["POST", "GET"])
# def handle_incoming_sms():
#     ... (comment out entire function)
```

### Option B: Remove entirely

Delete the `/webhook/sms` route and `handle_incoming_sms` function entirely.

## Keep These

- `/webhook/voice` - Still handles call box calls
- `/health` - Container health check
- `/sms-consent` - CTIA compliance page (still needed for legal reasons)
- `/status` - Status page
- `/admin/*` - Admin endpoints

## After This Change

1. Update Telnyx portal: Change messaging profile webhook URL to `https://frank-bot-api.contrived.com/webhook/sms`
2. The voice webhook remains at `https://let-food-into-civic.contrived.com/webhook/voice`
3. Test by sending an SMS to `+12148170664` - should be received by frank_bot

## Notes

- The opt-in/opt-out tracking in `/app/data/opt-in-flow/` can be deleted or archived
- The snooze functionality stays (it's for voice notification snoozing, not SMS)
