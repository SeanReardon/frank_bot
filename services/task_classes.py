from __future__ import annotations

import re

TaskClass = str

FREEFORM_TASK_CLASS = "freeform"


def classify_task_class(*parts: str | None) -> TaskClass:
    """Best-effort task class classifier for common structured runs."""
    text = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip()).lower()
    if not text:
        return FREEFORM_TASK_CLASS

    if any(token in text for token in ("screenshot", "android screen", "phone screen", "screen capture")):
        return "android_capture"

    if any(token in text for token in ("calendar", "meeting", "invite", "reschedule", "event")):
        return "calendar_edit"

    if any(token in text for token in ("contact", "phone number", "email address", "lookup", "find person")):
        return "contact_lookup"

    if any(token in text for token in ("draft", "compose", "write a message", "reply to", "text ", "email ")) and not re.search(r"\b(send|sent|sending)\b", text):
        return "message_draft"

    if any(token in text for token in ("debug", "diagnostic", "health", "status", "why did", "what happened", "logs")):
        return "diagnostic_probe"

    return FREEFORM_TASK_CLASS
