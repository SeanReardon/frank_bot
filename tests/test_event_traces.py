from __future__ import annotations

from pathlib import Path

import pytest

from services.event_traces import EventTraceStore
from services.incoming_events import create_incoming_event


@pytest.mark.asyncio
async def test_create_incoming_event_records_durable_event_and_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    trace_store = EventTraceStore(data_dir=str(tmp_path))
    monkeypatch.setattr("services.event_traces._trace_store", trace_store)

    event = await create_incoming_event(
        channel="telegram",
        sender="@sean",
        sender_name="Sean",
        content="please take a screenshot of the phone screen",
        transport="telegram_bot",
        transport_message_id="42",
        attachments=[{"kind": "image", "path": "./data/test.png"}],
    )

    assert event.task_class == "android_capture"
    assert event.transport == "telegram_bot"
    assert event.trace_id is not None
    assert event.event_id is not None

    events = await trace_store.list_recent_events(limit=5)
    traces = await trace_store.list_recent_traces(limit=5)

    assert len(events) == 1
    assert len(traces) == 1
    assert events[0]["event_id"] == event.event_id
    assert events[0]["trace_id"] == event.trace_id
    assert events[0]["transport_message_id"] == "42"
    assert traces[0]["event"]["task_class"] == "android_capture"
    assert traces[0]["status"] == "received"
    assert traces[0]["routing"] is None
