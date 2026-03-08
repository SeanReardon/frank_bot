"""
Android Task Storage Service.

Persists Android task lifecycle records as JSON files in `./data/android_tasks/`
so active/debug inspection survives process restarts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from services.file_store import ensure_directory, newest_first, read_json_file, to_thread, write_json_atomic
from services.task_classes import classify_task_class

logger = logging.getLogger(__name__)

TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
MAX_TASKS = 200
STORE_SCHEMA_VERSION = 1


@dataclass
class AndroidTask:
    """An Android phone automation task."""

    id: str
    goal: str
    status: TaskStatus
    app: str | None = None
    task_class: str = "android_capture"
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    # Result fields
    result: dict[str, Any] | None = None
    error: str | None = None
    # Progress tracking
    steps_taken: int = 0
    current_step: str | None = None
    tokens_used: int = 0
    estimated_cost: float = 0.0
    step_history: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Internal
    _cancel_requested: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Set default timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "app": self.app,
            "task_class": self.task_class,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "steps_taken": self.steps_taken,
            "current_step": self.current_step,
            "tokens_used": self.tokens_used,
            "estimated_cost": self.estimated_cost,
            "step_history": list(self.step_history),
            "artifacts": list(self.artifacts),
            "metadata": dict(self.metadata),
        }

    def to_summary(self) -> dict[str, Any]:
        """Convert to summary dictionary for list view."""
        return {
            "id": self.id,
            "goal": (
                self.goal[:100] + "..." if len(self.goal) > 100 else self.goal
            ),
            "status": self.status,
            "app": self.app,
            "task_class": self.task_class,
            "created_at": self.created_at,
            "steps_taken": self.steps_taken,
            "estimated_cost": self.estimated_cost,
            "current_step": self.current_step,
        }


def _task_from_payload(payload: dict[str, Any]) -> AndroidTask:
    return AndroidTask(
        id=str(payload["id"]),
        goal=str(payload["goal"]),
        status=payload["status"],
        app=payload.get("app"),
        task_class=str(payload.get("task_class") or "android_capture"),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        started_at=payload.get("started_at"),
        completed_at=payload.get("completed_at"),
        result=payload.get("result"),
        error=payload.get("error"),
        steps_taken=int(payload.get("steps_taken") or 0),
        current_step=payload.get("current_step"),
        tokens_used=int(payload.get("tokens_used") or 0),
        estimated_cost=float(payload.get("estimated_cost") or 0.0),
        step_history=list(payload.get("step_history") or []),
        artifacts=list(payload.get("artifacts") or []),
        metadata=dict(payload.get("metadata") or {}),
        _cancel_requested=bool(payload.get("cancel_requested", False)),
    )


def _task_to_payload(task: AndroidTask) -> dict[str, Any]:
    payload = asdict(task)
    payload["cancel_requested"] = bool(task._cancel_requested)
    return payload


class AndroidTaskStorage:
    """Durable JSON storage for Android tasks with automatic cleanup."""

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self) -> None:
        base_dir = Path(os.getenv("DATA_DIR", "./data"))
        self._data_dir = base_dir / "android_tasks"
        self._schema_path = self._data_dir / "_schema.json"
        ensure_directory(self._data_dir)
        self._task_futures: dict[str, asyncio.Task[Any]] = {}
        lock_key = str(self._data_dir.resolve())
        if lock_key not in self._locks:
            self._locks[lock_key] = asyncio.Lock()
        self._lock = self._locks[lock_key]
        self._initialized = False

    def _task_path(self, task_id: str) -> Path:
        return self._data_dir / f"{task_id}.json"

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        if not self._schema_path.exists():
            await to_thread(
                write_json_atomic,
                self._schema_path,
                {
                    "store": "android_tasks",
                    "schema_version": STORE_SCHEMA_VERSION,
                    "backing": "json_files",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        await self._recover_incomplete_tasks()
        self._initialized = True

    async def _read_task(self, task_id: str) -> AndroidTask | None:
        payload = await to_thread(read_json_file, self._task_path(task_id), None)
        if not isinstance(payload, dict):
            return None
        return _task_from_payload(payload)

    async def _write_task(self, task: AndroidTask) -> None:
        await to_thread(write_json_atomic, self._task_path(task.id), _task_to_payload(task))

    async def _iter_tasks(self) -> list[AndroidTask]:
        await self._ensure_initialized()
        tasks: list[AndroidTask] = []
        for path in newest_first(self._data_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            payload = await to_thread(read_json_file, path, None)
            if isinstance(payload, dict):
                tasks.append(_task_from_payload(payload))
        return tasks

    async def _recover_incomplete_tasks(self) -> None:
        for path in newest_first(self._data_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            payload = await to_thread(read_json_file, path, None)
            if not isinstance(payload, dict):
                continue
            task = _task_from_payload(payload)
            if task.status in ("pending", "running"):
                task.status = "failed"
                task.error = "Service restarted while Android task was active."
                task.current_step = None
                task.completed_at = datetime.now(timezone.utc).isoformat()
                task.updated_at = task.completed_at
                await self._write_task(task)

    async def create_task(self, goal: str, app: str | None = None) -> AndroidTask:
        """Create a new task in pending state."""
        await self._ensure_initialized()
        task_id = str(uuid.uuid4())[:8]  # Short ID for convenience

        task = AndroidTask(
            id=task_id,
            goal=goal,
            status="pending",
            app=app,
            task_class=classify_task_class(goal, app),
        )

        async with self._lock:
            # Cleanup old tasks if we have too many
            await self._cleanup_old_tasks()
            await self._write_task(task)

        logger.info("Created Android task %s: %s", task_id, goal[:50])
        return task

    async def get_task(self, task_id: str) -> AndroidTask | None:
        """Get a task by ID."""
        await self._ensure_initialized()
        return await self._read_task(task_id)

    async def list_tasks(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[AndroidTask]:
        """List tasks, optionally filtered by status."""
        tasks = await self._iter_tasks()

        if status:
            if status == "active":
                tasks = [t for t in tasks if t.status in ("pending", "running")]
            else:
                tasks = [t for t in tasks if t.status == status]

        # Sort by created_at descending (newest first)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        steps_taken: int | None = None,
        current_step: str | None = None,
        tokens_used: int | None = None,
        estimated_cost: float | None = None,
        step_history: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AndroidTask | None:
        """Update a task's fields."""
        await self._ensure_initialized()
        async with self._lock:
            task = await self._read_task(task_id)
            if not task:
                return None

            now = datetime.now(timezone.utc).isoformat()
            task.updated_at = now

            if status is not None:
                task.status = status
                if status == "running" and task.started_at is None:
                    task.started_at = now
                elif status in ("completed", "failed", "cancelled"):
                    task.completed_at = now

            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if steps_taken is not None:
                task.steps_taken = steps_taken
            if current_step is not None:
                task.current_step = current_step
            if tokens_used is not None:
                task.tokens_used = tokens_used
            if estimated_cost is not None:
                task.estimated_cost = estimated_cost
            if step_history is not None:
                task.step_history = list(step_history)
            if artifacts is not None:
                task.artifacts = list(artifacts)
            if metadata is not None:
                task.metadata = dict(metadata)

            await self._write_task(task)
            return task

    async def cancel_task(self, task_id: str) -> AndroidTask | None:
        """Request cancellation of a task."""
        await self._ensure_initialized()
        task = await self._read_task(task_id)
        if not task:
            return None

        if task.status in ("completed", "failed", "cancelled"):
            # Already finished, can't cancel
            return task

        task._cancel_requested = True
        await self._write_task(task)

        # If there's a running future, cancel it
        if task_id in self._task_futures:
            future = self._task_futures[task_id]
            if not future.done():
                future.cancel()

        await self.update_task(task_id, status="cancelled", error="Cancelled by user")
        logger.info("Cancelled Android task %s", task_id)

        return task

    def is_cancel_requested(self, task_id: str) -> bool:
        """Check if cancellation was requested for a task."""
        task_path = self._task_path(task_id)
        payload = read_json_file(task_path, None)
        if not isinstance(payload, dict):
            return False
        return bool(payload.get("cancel_requested", False))

    def register_future(self, task_id: str, future: asyncio.Task[Any]) -> None:
        """Register the asyncio Task for a running task."""
        self._task_futures[task_id] = future

    def unregister_future(self, task_id: str) -> None:
        """Unregister the asyncio Task when done."""
        self._task_futures.pop(task_id, None)

    async def _cleanup_old_tasks(self) -> None:
        """Remove oldest completed task files if we have too many."""
        tasks = await self._iter_tasks()
        if len(tasks) < MAX_TASKS:
            return

        # Get completed tasks sorted by completion time
        completed = [
            t for t in tasks
            if t.status in ("completed", "failed", "cancelled")
        ]
        completed.sort(key=lambda t: t.completed_at or t.created_at)

        # Remove oldest completed tasks to get under limit
        to_remove = len(tasks) - MAX_TASKS + 10  # Leave some headroom
        for task in completed[:to_remove]:
            try:
                self._task_path(task.id).unlink(missing_ok=True)
            except TypeError:
                if self._task_path(task.id).exists():
                    self._task_path(task.id).unlink()
            self._task_futures.pop(task.id, None)

        if to_remove > 0:
            logger.debug("Cleaned up %d old Android tasks", to_remove)


# Singleton instance
_storage: AndroidTaskStorage | None = None


def get_android_task_storage() -> AndroidTaskStorage:
    """Get the singleton task storage instance."""
    global _storage
    if _storage is None:
        _storage = AndroidTaskStorage()
    return _storage
