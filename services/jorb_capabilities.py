"""
Capabilities reference generator for jorb prompts.

Generates markdown documentation of FrankAPI capabilities for use in jorb
system prompts. This ensures jorb prompts always reflect current API
capabilities without manual updates.
"""

from __future__ import annotations

from meta.introspection import generate_method_table
from meta.api import (
    AndroidNamespace,
    CalendarNamespace,
    ClaudiaNamespace,
    ContactsNamespace,
    DiagnosticsNamespace,
    JorbsNamespace,
    SMSNamespace,
    SwarmNamespace,
    TelegramNamespace,
    TelegramBotNamespace,
    SystemNamespace,
    TimeNamespace,
    UPSNamespace,
    StyleNamespace,
)


def generate_capabilities_reference() -> str:
    """
    Generate a capabilities reference document for jorb system prompts.

    Introspects FrankAPI and returns a markdown string documenting all
    frank.* namespaces, methods, parameters, and return types suitable
    for injection into LLM prompts.

    The output includes:
    - All available namespaces (calendar, contacts, sms, telegram, telegram_bot,
      swarm, time, ups, diagnostics, system, jorbs, claudia, style, android)
    - Method signatures with parameter names and types
    - Brief descriptions from docstrings
    - Usage examples for each namespace

    Returns:
        Markdown string suitable for embedding in jorb system prompts.

    Example:
        >>> ref = generate_capabilities_reference()
        >>> "frank.calendar" in ref
        True
        >>> "frank.telegram.send" in ref
        True
    """
    parts = []

    # Header
    parts.append("# Frank Bot Capabilities\n")
    parts.append(
        "You have access to the following capabilities through the `frank` API:\n"
    )

    # Calendar namespace
    parts.append("## frank.calendar - Calendar Operations\n")
    parts.append("Manage calendar events and schedules.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("calendar", CalendarNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Get events for today')
    parts.append('events = frank.calendar.events(day="2026-02-06")')
    parts.append('')
    parts.append('# Create a new event')
    parts.append('result = frank.calendar.create(')
    parts.append('    summary="Team Meeting",')
    parts.append('    start="2026-02-06T10:00:00",')
    parts.append('    end="2026-02-06T11:00:00",')
    parts.append('    location="Conference Room A"')
    parts.append(')')
    parts.append("```\n")

    # Contacts namespace
    parts.append("## frank.contacts - Contact Lookup\n")
    parts.append("Search for contacts by name, email, or phone.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("contacts", ContactsNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Search for a contact')
    parts.append('contacts = frank.contacts.search("John", max_results=5)')
    parts.append('if contacts["count"] > 0:')
    parts.append('    email = contacts["contacts"][0].get("email", "N/A")')
    parts.append('    print(f"Found: {email}")')
    parts.append("```\n")

    # SMS namespace
    parts.append("## frank.sms - SMS Messaging\n")
    parts.append("Send text messages to contacts.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("sms", SMSNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Send an SMS')
    parts.append('result = frank.sms.send(')
    parts.append('    recipient="John",')
    parts.append('    message="Running 10 minutes late!"')
    parts.append(')')
    parts.append("```\n")

    # Telegram namespace
    parts.append("## frank.telegram - Telegram Messaging\n")
    parts.append("Send and receive Telegram messages.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("telegram", TelegramNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Send a Telegram message')
    parts.append('result = frank.telegram.send(')
    parts.append('    recipient="@username",')
    parts.append('    text="Hello from Frank Bot!"')
    parts.append(')')
    parts.append('')
    parts.append('# Get recent messages')
    parts.append('messages = frank.telegram.messages("@username", limit=10)')
    parts.append("```\n")

    # Telegram Bot namespace
    parts.append("## frank.telegram_bot - Telegram Bot Messaging\n")
    parts.append("Send messages via the Telegram bot account (Bot API).\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("telegram_bot", TelegramBotNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append("# Send a Telegram message via the bot account")
    parts.append('result = frank.telegram_bot.send(text="Diagnostics look good ✅")')
    parts.append("```\n")

    # Swarm namespace
    parts.append("## frank.swarm - Location History\n")
    parts.append("Access Swarm/Foursquare check-in history.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("swarm", SwarmNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Find restaurants visited with someone')
    parts.append('checkins = frank.swarm.checkins(')
    parts.append('    year=2025,')
    parts.append('    category="restaurant",')
    parts.append('    with_companion="Jane",')
    parts.append('    max_results=20')
    parts.append(')')
    parts.append('')
    parts.append('# Get checkins from a date range')
    parts.append('recent = frank.swarm.checkins(')
    parts.append('    after_date="2026-01-01",')
    parts.append('    before_date="2026-02-01",')
    parts.append('    has_photos=True')
    parts.append(')')
    parts.append("```\n")

    # Time namespace
    parts.append("## frank.time - Current Time\n")
    parts.append("Get the current time with timezone awareness.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("time", TimeNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Get current time')
    parts.append('now = frank.time.now()')
    parts.append('print(f"Current time: {now[\'iso_time\']}")')
    parts.append('print(f"Timezone: {now[\'timezone\']}")')
    parts.append("```\n")

    # UPS namespace
    parts.append("## frank.ups - UPS Power Status\n")
    parts.append("Check UPS battery and power status.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("ups", UPSNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append('# Check UPS status')
    parts.append('status = frank.ups.status()')
    parts.append('print(f"Battery: {status[\'charge_percent\']}%")')
    parts.append('print(f"Runtime: {status[\'runtime_minutes\']} minutes")')
    parts.append("```\n")

    # Diagnostics namespace
    parts.append("## frank.diagnostics - Diagnostics\n")
    parts.append("Get system and service diagnostics.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("diagnostics", DiagnosticsNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append("# Full diagnostics bundle")
    parts.append("d = frank.diagnostics.full()")
    parts.append("print(d.get('message'))")
    parts.append("```\n")

    # System namespace
    parts.append("## frank.system - System Status\n")
    parts.append("Check orchestration machinery status.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("system", SystemNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append("# Orchestration status (telegram router, agent runner, etc.)")
    parts.append("s = frank.system.status()")
    parts.append("print(s.get('message'))")
    parts.append("```\n")

    # Jorbs namespace
    parts.append("## frank.jorbs - Jorb Management\n")
    parts.append("List and manage long-lived autonomous tasks.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("jorbs", JorbsNamespace))
    parts.append("\n### Example\n")
    parts.append("```python")
    parts.append("# List open jorbs")
    parts.append("jorbs = frank.jorbs.list(status='open')")
    parts.append("```")
    parts.append("")

    # Claudia namespace
    parts.append("## frank.claudia - Claudia Integration\n")
    parts.append("Interact with Claudia agent service.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("claudia", ClaudiaNamespace))
    parts.append("")

    # Style namespace
    parts.append("## frank.style - Style Capture\n")
    parts.append("Generate style guides (e.g. SEAN.md).\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("style", StyleNamespace))
    parts.append("")

    # Android namespace
    parts.append("## frank.android - Android Phone Automation\n")
    parts.append("Run LLM-in-the-loop tasks on an Android phone.\n")
    parts.append("### Methods\n")
    parts.append(generate_method_table("android", AndroidNamespace))
    parts.append("")

    # Usage Guidelines
    parts.append("## Usage Guidelines\n")
    parts.append("1. **All methods are synchronous** - they block until the operation completes\n")
    parts.append("2. **Return dicts** - All methods return dictionaries with results\n")
    parts.append("3. **Check the `message` field** - Contains human-readable status\n")
    parts.append("4. **Use keyword arguments** - Most methods accept keyword-only args after the first\n")
    parts.append("5. **Handle errors gracefully** - Methods may return error information in the dict\n")
    parts.append("\n## Return Format\n")
    parts.append("All methods return dictionaries with at minimum:\n")
    parts.append("- `message`: Human-readable status message\n")
    parts.append("- Additional fields specific to the operation\n")

    return "\n".join(parts)


__all__ = ["generate_capabilities_reference"]
