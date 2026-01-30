"""
Context Reset Service (Ralph Loop) for long-running jorbs.

Implements periodic context compression to prevent token overflow in
long-running autonomous tasks. Creates handoff summaries and maintains
a persistent progress log.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import get_settings
from services.jorb_storage import (
    Jorb,
    JorbMessage,
    JorbStorage,
    JorbWithMessages,
)

logger = logging.getLogger(__name__)

# Default values
DEFAULT_CONTEXT_RESET_DAYS = 3
DEFAULT_PROGRESS_LOG_PATH = "./data/jorbs_progress.txt"
STATE_FILE_PATH = "./data/context_reset_state.json"

# Model for handoff generation
AGENT_MODEL = "gpt-5.2"


@dataclass
class JorbHandoff:
    """Handoff summary for a single jorb."""

    jorb_id: str
    jorb_name: str
    status: str
    progress_summary: str
    recent_activity: str
    next_steps: str | None = None


@dataclass
class ContextResetState:
    """State tracking for context resets."""

    last_reset_at: str | None = None  # ISO 8601 timestamp
    reset_count: int = 0
    last_activity_at: str | None = None  # ISO 8601 timestamp

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_reset_at": self.last_reset_at,
            "reset_count": self.reset_count,
            "last_activity_at": self.last_activity_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextResetState:
        """Create from dictionary."""
        return cls(
            last_reset_at=data.get("last_reset_at"),
            reset_count=data.get("reset_count", 0),
            last_activity_at=data.get("last_activity_at"),
        )


@dataclass
class HandoffSummary:
    """Complete handoff summary for context reset."""

    session_summary: str
    jorb_handoffs: list[JorbHandoff] = field(default_factory=list)
    generated_at: str = ""
    token_count_before: int = 0


def _get_context_reset_days() -> int:
    """Get the context reset interval from environment."""
    try:
        return int(os.getenv("CONTEXT_RESET_DAYS", str(DEFAULT_CONTEXT_RESET_DAYS)))
    except ValueError:
        return DEFAULT_CONTEXT_RESET_DAYS


def _get_progress_log_path() -> str:
    """Get the progress log file path."""
    data_dir = os.getenv("DATA_DIR", ".")
    return os.path.join(data_dir, "jorbs_progress.txt")


def _get_state_file_path() -> str:
    """Get the state file path."""
    data_dir = os.getenv("DATA_DIR", ".")
    return os.path.join(data_dir, "context_reset_state.json")


class ContextResetService:
    """
    Service for managing context resets in long-running jorbs.

    Implements the "Ralph Loop" pattern: periodically compress conversation
    context to prevent token overflow while maintaining task continuity.
    """

    def __init__(
        self,
        storage: JorbStorage | None = None,
        openai_api_key: str | None = None,
    ):
        """
        Initialize the context reset service.

        Args:
            storage: JorbStorage instance. Creates one if not provided.
            openai_api_key: OpenAI API key. Uses OPENAI_API_KEY env var if not provided.
        """
        self._storage = storage or JorbStorage()
        settings = get_settings()
        self._api_key = openai_api_key or settings.openai_api_key
        self._reset_days = _get_context_reset_days()
        self._progress_log_path = _get_progress_log_path()
        self._state_file_path = _get_state_file_path()

    @property
    def is_configured(self) -> bool:
        """Check if the service has required configuration."""
        return bool(self._api_key)

    def _load_state(self) -> ContextResetState:
        """Load context reset state from file."""
        try:
            if os.path.exists(self._state_file_path):
                with open(self._state_file_path, "r") as f:
                    data = json.load(f)
                    return ContextResetState.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load context reset state: %s", e)

        return ContextResetState()

    def _save_state(self, state: ContextResetState) -> None:
        """Save context reset state to file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self._state_file_path), exist_ok=True)

            with open(self._state_file_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
        except OSError as e:
            logger.error("Failed to save context reset state: %s", e)

    def record_activity(self) -> None:
        """Record that activity has occurred (for reset timing)."""
        state = self._load_state()
        state.last_activity_at = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    def maybe_reset_context(self) -> bool:
        """
        Check if a context reset is needed.

        Returns True if:
        1. At least CONTEXT_RESET_DAYS have elapsed since last reset
        2. Activity has occurred since the last reset

        Returns:
            True if context reset should be performed
        """
        state = self._load_state()
        now = datetime.now(timezone.utc)

        # If never reset, check if we have any activity
        if state.last_reset_at is None:
            # Only reset if there's been activity
            return state.last_activity_at is not None

        # Parse last reset time
        try:
            last_reset = datetime.fromisoformat(
                state.last_reset_at.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            return True  # Invalid timestamp, trigger reset

        # Check if enough days have elapsed
        days_since_reset = (now - last_reset).days
        if days_since_reset < self._reset_days:
            return False

        # Check if there's been activity since last reset
        if state.last_activity_at is None:
            return False

        try:
            last_activity = datetime.fromisoformat(
                state.last_activity_at.replace("Z", "+00:00")
            )
            return last_activity > last_reset
        except (ValueError, AttributeError):
            return True

    async def _generate_handoff_with_llm(
        self,
        jorbs_with_messages: list[JorbWithMessages],
    ) -> HandoffSummary:
        """
        Use LLM to generate a structured handoff summary.

        Args:
            jorbs_with_messages: Open jorbs with their message history

        Returns:
            HandoffSummary with session summary and per-jorb handoffs
        """
        if not self._api_key:
            raise ValueError("OpenAI API key not configured")

        # Build context for the LLM
        jorb_contexts = []
        for jwm in jorbs_with_messages:
            # Get recent messages (last 50)
            recent_msgs = jwm.messages[-50:]
            msg_text = "\n".join(
                f"[{m.timestamp}] {m.direction}: {m.content[:200]}"
                for m in recent_msgs
            )

            jorb_contexts.append({
                "id": jwm.jorb.id,
                "name": jwm.jorb.name,
                "status": jwm.jorb.status,
                "plan": jwm.jorb.original_plan,
                "current_progress": jwm.jorb.progress_summary or "",
                "awaiting": jwm.jorb.awaiting or "",
                "recent_messages": msg_text,
            })

        prompt = f"""You are creating a handoff summary for context compression.
Review the following active tasks (jorbs) and create a structured summary.

TASKS:
{json.dumps(jorb_contexts, indent=2)}

Create a JSON response with:
1. "session_summary": A 2-3 sentence overview of overall progress
2. "jorb_handoffs": Array of objects, one per jorb, each with:
   - "jorb_id": The task ID
   - "jorb_name": The task name
   - "status": Current status
   - "progress_summary": Comprehensive summary of what's been done (1-3 sentences)
   - "recent_activity": What happened recently (1-2 sentences)
   - "next_steps": What should happen next (1 sentence, can be null if complete/cancelled)

Focus on preserving critical context that would be needed to continue the task.
"""

        try:
            import openai

            client = openai.OpenAI(api_key=self._api_key)

            response = client.chat.completions.create(
                model=AGENT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You generate structured JSON handoff summaries for context compression.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")

            data = json.loads(content)

            # Parse response
            handoffs = []
            for h in data.get("jorb_handoffs", []):
                handoffs.append(JorbHandoff(
                    jorb_id=h.get("jorb_id", ""),
                    jorb_name=h.get("jorb_name", ""),
                    status=h.get("status", ""),
                    progress_summary=h.get("progress_summary", ""),
                    recent_activity=h.get("recent_activity", ""),
                    next_steps=h.get("next_steps"),
                ))

            return HandoffSummary(
                session_summary=data.get("session_summary", ""),
                jorb_handoffs=handoffs,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        except ImportError:
            raise ValueError("openai package not installed")
        except Exception as e:
            logger.error("Failed to generate handoff summary: %s", e)
            raise

    def _append_to_progress_log(self, handoff: HandoffSummary) -> None:
        """
        Append handoff summary to the progress log file.

        Uses Claudia-inspired markdown format.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(self._progress_log_path), exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            "",
            f"## Context Reset - {timestamp}",
            "",
            "### Session Summary",
            handoff.session_summary,
            "",
        ]

        if handoff.jorb_handoffs:
            lines.append("### Task Handoffs")
            lines.append("")

            for h in handoff.jorb_handoffs:
                lines.append(f"#### {h.jorb_name} ({h.jorb_id})")
                lines.append(f"**Status:** {h.status}")
                lines.append("")
                lines.append(f"**Progress:** {h.progress_summary}")
                lines.append("")
                if h.recent_activity:
                    lines.append(f"**Recent:** {h.recent_activity}")
                    lines.append("")
                if h.next_steps:
                    lines.append(f"**Next:** {h.next_steps}")
                    lines.append("")

        lines.append("---")
        lines.append("")

        try:
            with open(self._progress_log_path, "a") as f:
                f.write("\n".join(lines))
            logger.info("Appended context reset to progress log")
        except OSError as e:
            logger.error("Failed to write to progress log: %s", e)

    async def perform_context_reset(self) -> HandoffSummary:
        """
        Perform a context reset.

        1. Fetches all open jorbs with messages
        2. Calls LLM to generate handoff summary
        3. Appends to progress log
        4. Updates jorb progress_summary fields
        5. Saves checkpoints
        6. Updates reset state

        Returns:
            The generated HandoffSummary
        """
        if not self.is_configured:
            raise ValueError("Context reset service not configured (no API key)")

        logger.info("Starting context reset...")

        # Get open jorbs
        jorbs_with_messages = await self._storage.get_open_jorbs_with_messages()

        if not jorbs_with_messages:
            logger.info("No active jorbs, skipping context reset")
            # Still record the reset
            state = self._load_state()
            state.last_reset_at = datetime.now(timezone.utc).isoformat()
            state.reset_count += 1
            self._save_state(state)
            return HandoffSummary(
                session_summary="No active tasks during this period.",
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Generate handoff summary
        handoff = await self._generate_handoff_with_llm(jorbs_with_messages)

        # Append to progress log
        self._append_to_progress_log(handoff)

        # Update jorb progress summaries
        for h in handoff.jorb_handoffs:
            await self._storage.update_jorb(
                h.jorb_id,
                progress_summary=h.progress_summary,
            )

            # Add checkpoint
            await self._storage.add_checkpoint(
                h.jorb_id,
                summary=h.progress_summary,
            )

        # Update state
        state = self._load_state()
        state.last_reset_at = datetime.now(timezone.utc).isoformat()
        state.reset_count += 1
        self._save_state(state)

        logger.info(
            "Context reset complete: %d jorbs processed, reset #%d",
            len(handoff.jorb_handoffs),
            state.reset_count,
        )

        return handoff

    def get_progress_log_tail(self, lines: int = 100) -> str:
        """
        Get the last N lines of the progress log.

        Args:
            lines: Number of lines to return (default 100)

        Returns:
            Last N lines of the progress log, or empty string if not found
        """
        if not os.path.exists(self._progress_log_path):
            return ""

        try:
            with open(self._progress_log_path, "r") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except OSError as e:
            logger.error("Failed to read progress log: %s", e)
            return ""

    async def build_fresh_context(self) -> dict[str, Any]:
        """
        Build a fresh context for resuming after context reset.

        Includes:
        - Original plans for all open jorbs
        - Current states
        - Last 100 lines of progress log

        Returns:
            Context dict suitable for agent initialization
        """
        # Get open jorbs
        jorbs = await self._storage.list_jorbs(status_filter="open")

        # Build context
        context: dict[str, Any] = {
            "context_type": "fresh_start_after_reset",
            "reset_count": self._load_state().reset_count,
            "active_tasks": [],
            "progress_history": self.get_progress_log_tail(100),
        }

        for jorb in jorbs:
            context["active_tasks"].append({
                "id": jorb.id,
                "name": jorb.name,
                "status": jorb.status,
                "original_plan": jorb.original_plan,
                "progress_summary": jorb.progress_summary or "",
                "awaiting": jorb.awaiting or "",
                "contacts": [c.to_dict() for c in jorb.contacts],
            })

        return context

    def get_reset_status(self) -> dict[str, Any]:
        """
        Get the current context reset status.

        Returns:
            Dict with state information and next reset timing
        """
        state = self._load_state()
        now = datetime.now(timezone.utc)

        next_reset_at = None
        days_until_reset = None

        if state.last_reset_at:
            try:
                last_reset = datetime.fromisoformat(
                    state.last_reset_at.replace("Z", "+00:00")
                )
                next_reset = last_reset + timedelta(days=self._reset_days)
                next_reset_at = next_reset.isoformat()
                days_until_reset = max(0, (next_reset - now).days)
            except (ValueError, AttributeError):
                pass

        return {
            "last_reset_at": state.last_reset_at,
            "reset_count": state.reset_count,
            "last_activity_at": state.last_activity_at,
            "reset_interval_days": self._reset_days,
            "next_reset_at": next_reset_at,
            "days_until_reset": days_until_reset,
            "needs_reset": self.maybe_reset_context(),
        }


__all__ = [
    "ContextResetService",
    "ContextResetState",
    "HandoffSummary",
    "JorbHandoff",
]
