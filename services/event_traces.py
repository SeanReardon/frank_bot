from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.file_store import (
    ensure_directory,
    newest_first,
    read_json_file,
    to_thread,
    write_json_atomic,
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventTraceStore:
    """Durable JSON traces for replaying event routing and execution."""

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, data_dir: str | None = None) -> None:
        base_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._events_dir = base_dir / "events"
        self._traces_dir = base_dir / "traces"
        ensure_directory(self._events_dir)
        ensure_directory(self._traces_dir)
        lock_key = str(self._traces_dir.resolve())
        if lock_key not in self._locks:
            self._locks[lock_key] = asyncio.Lock()
        self._lock = self._locks[lock_key]

    def _event_path(self, event_id: str) -> Path:
        return self._events_dir / f"{event_id}.json"

    def _trace_path(self, trace_id: str) -> Path:
        return self._traces_dir / f"{trace_id}.json"

    async def record_event(self, payload: dict[str, Any]) -> tuple[str, str]:
        event_id = str(payload.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}")
        trace_id = str(payload.get("trace_id") or f"trace_{uuid.uuid4().hex[:12]}")
        now = _utc_now()

        event_payload = {
            **payload,
            "event_id": event_id,
            "trace_id": trace_id,
            "recorded_at": payload.get("recorded_at") or now,
        }
        trace_payload = {
            "trace_id": trace_id,
            "event_id": event_id,
            "status": "received",
            "started_at": now,
            "updated_at": now,
            "event": event_payload,
            "routing": None,
            "steps": [],
            "result": None,
            "errors": [],
        }

        async with self._lock:
            await to_thread(write_json_atomic, self._event_path(event_id), event_payload)
            await to_thread(write_json_atomic, self._trace_path(trace_id), trace_payload)
        return event_id, trace_id

    async def append_step(self, trace_id: str, phase: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            trace = await self._read_trace(trace_id)
            if trace is None:
                return
            steps = list(trace.get("steps") or [])
            steps.append(
                {
                    "timestamp": _utc_now(),
                    "phase": phase,
                    "payload": payload,
                }
            )
            trace["steps"] = steps
            trace["updated_at"] = _utc_now()
            await to_thread(write_json_atomic, self._trace_path(trace_id), trace)

    async def set_routing(self, trace_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            trace = await self._read_trace(trace_id)
            if trace is None:
                return
            trace["routing"] = {
                **payload,
                "timestamp": _utc_now(),
            }
            trace["updated_at"] = _utc_now()
            await to_thread(write_json_atomic, self._trace_path(trace_id), trace)

    async def finalize(self, trace_id: str, result: dict[str, Any], *, status: str) -> None:
        async with self._lock:
            trace = await self._read_trace(trace_id)
            if trace is None:
                return
            trace["status"] = status
            trace["result"] = {
                **result,
                "timestamp": _utc_now(),
            }
            trace["updated_at"] = _utc_now()
            await to_thread(write_json_atomic, self._trace_path(trace_id), trace)

    async def record_error(self, trace_id: str, subsystem: str, error: str) -> None:
        async with self._lock:
            trace = await self._read_trace(trace_id)
            if trace is None:
                return
            errors = list(trace.get("errors") or [])
            errors.append(
                {
                    "timestamp": _utc_now(),
                    "subsystem": subsystem,
                    "error": error,
                }
            )
            trace["errors"] = errors
            trace["status"] = "error"
            trace["updated_at"] = _utc_now()
            await to_thread(write_json_atomic, self._trace_path(trace_id), trace)

    async def list_recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        paths = newest_first(self._traces_dir.glob("*.json"))
        results: list[dict[str, Any]] = []
        for path in paths[: max(1, limit)]:
            payload = await to_thread(read_json_file, path, None)
            if isinstance(payload, dict):
                results.append(payload)
        return results

    async def list_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        paths = newest_first(self._events_dir.glob("*.json"))
        results: list[dict[str, Any]] = []
        for path in paths[: max(1, limit)]:
            payload = await to_thread(read_json_file, path, None)
            if isinstance(payload, dict):
                results.append(payload)
        return results

    async def _read_trace(self, trace_id: str) -> dict[str, Any] | None:
        payload = await to_thread(read_json_file, self._trace_path(trace_id), None)
        return payload if isinstance(payload, dict) else None


_trace_store: EventTraceStore | None = None


def get_event_trace_store() -> EventTraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = EventTraceStore()
    return _trace_store
