"""
Android Task Storage Service.

In-memory storage for short-lived Android phone automation tasks.
Tracks task lifecycle: pending → running → completed/failed/cancelled.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Task status types
TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

# Maximum tasks to keep in memory (rolling window)
MAX_TASKS = 100


@dataclass
class AndroidTask:
    """An Android phone automation task."""

    id: str
    goal: str
    status: TaskStatus
    app: str | None = None
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
            "created_at": self.created_at,
            "steps_taken": self.steps_taken,
            "estimated_cost": self.estimated_cost,
        }


class AndroidTaskStorage:
    """In-memory storage for Android tasks with automatic cleanup."""

    def __init__(self) -> None:
        self._tasks: dict[str, AndroidTask] = {}
        self._task_futures: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, goal: str, app: str | None = None) -> AndroidTask:
        """Create a new task in pending state."""
        task_id = str(uuid.uuid4())[:8]  # Short ID for convenience

        task = AndroidTask(
            id=task_id,
            goal=goal,
            status="pending",
            app=app,
        )

        async with self._lock:
            # Cleanup old tasks if we have too many
            await self._cleanup_old_tasks()
            self._tasks[task_id] = task

        logger.info("Created Android task %s: %s", task_id, goal[:50])
        return task

    async def get_task(self, task_id: str) -> AndroidTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[AndroidTask]:
        """List tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())

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
    ) -> AndroidTask | None:
        """Update a task's fields."""
        task = self._tasks.get(task_id)
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

        return task

    async def cancel_task(self, task_id: str) -> AndroidTask | None:
        """Request cancellation of a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if task.status in ("completed", "failed", "cancelled"):
            # Already finished, can't cancel
            return task

        task._cancel_requested = True

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
        task = self._tasks.get(task_id)
        return task._cancel_requested if task else False

    def register_future(self, task_id: str, future: asyncio.Task[Any]) -> None:
        """Register the asyncio Task for a running task."""
        self._task_futures[task_id] = future

    def unregister_future(self, task_id: str) -> None:
        """Unregister the asyncio Task when done."""
        self._task_futures.pop(task_id, None)

    async def _cleanup_old_tasks(self) -> None:
        """Remove oldest completed tasks if we have too many."""
        if len(self._tasks) < MAX_TASKS:
            return

        # Get completed tasks sorted by completion time
        completed = [
            t for t in self._tasks.values()
            if t.status in ("completed", "failed", "cancelled")
        ]
        completed.sort(key=lambda t: t.completed_at or t.created_at)

        # Remove oldest completed tasks to get under limit
        to_remove = len(self._tasks) - MAX_TASKS + 10  # Leave some headroom
        for task in completed[:to_remove]:
            del self._tasks[task.id]
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
