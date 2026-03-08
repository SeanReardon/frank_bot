from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from services.agent_runner import IncomingEvent
from services.event_traces import get_event_trace_store
from services.task_classes import classify_task_class


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_incoming_event(
    *,
    channel: str,
    sender: str,
    sender_name: str | None,
    content: str,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
    message_count: int = 1,
    raw_content: str | None = None,
    is_human_intervention: bool = False,
    transport: str | None = None,
    transport_message_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> IncomingEvent:
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    event_timestamp = timestamp or _now()
    event_metadata = dict(metadata or {})
    task_class = classify_task_class(content)

    payload = {
        "event_id": event_id,
        "trace_id": trace_id,
        "channel": channel,
        "sender": sender,
        "sender_name": sender_name,
        "content": content,
        "raw_content": raw_content if raw_content is not None else content,
        "timestamp": event_timestamp,
        "message_count": message_count,
        "metadata": event_metadata,
        "is_human_intervention": is_human_intervention,
        "transport": transport or channel,
        "transport_message_id": transport_message_id,
        "attachments": attachments or [],
        "task_class": task_class,
    }
    await get_event_trace_store().record_event(payload)

    return IncomingEvent(
        channel=channel,  # type: ignore[arg-type]
        sender=sender,
        sender_name=sender_name,
        content=content,
        timestamp=event_timestamp,
        raw_content=raw_content,
        metadata=event_metadata,
        message_count=message_count,
        is_human_intervention=is_human_intervention,
        event_id=event_id,
        trace_id=trace_id,
        transport=transport or channel,
        transport_message_id=transport_message_id,
        attachments=attachments or [],
        task_class=task_class,
    )
