"""
Progress Log Service for tracking learnings and gotchas.

Inspired by claudia's progress.txt pattern - tracks learnings, patterns, and
handoffs across sessions. This provides a durable record of what the agent
has learned over time.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Default path for progress log
DEFAULT_PROGRESS_PATH = "./data/progress.json"


@dataclass
class ProgressEntry:
    """A single progress log entry."""

    timestamp: str
    jorb_id: str | None
    jorb_name: str | None
    entry_type: str  # "task_progress", "learning", "handoff", "gotcha", "session_summary"
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "jorb_id": self.jorb_id,
            "jorb_name": self.jorb_name,
            "entry_type": self.entry_type,
            "summary": self.summary,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressEntry:
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            jorb_id=data.get("jorb_id"),
            jorb_name=data.get("jorb_name"),
            entry_type=data["entry_type"],
            summary=data["summary"],
            details=data.get("details", {}),
        )


@dataclass
class Learning:
    """A learned pattern or gotcha discovered during jorb execution."""

    id: str
    timestamp: str
    category: str  # "contact_behavior", "timing", "process", "gotcha", "tip"
    subject: str  # What/who this learning is about (e.g., "Magic", "Hotel Nikko")
    insight: str  # The actual learning
    jorb_id: str | None = None  # Jorb where this was discovered
    confidence: str = "medium"  # "low", "medium", "high"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "category": self.category,
            "subject": self.subject,
            "insight": self.insight,
            "jorb_id": self.jorb_id,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Learning:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            category=data["category"],
            subject=data["subject"],
            insight=data["insight"],
            jorb_id=data.get("jorb_id"),
            confidence=data.get("confidence", "medium"),
        )


class ProgressLog:
    """
    Service for tracking progress, learnings, and session handoffs.

    Maintains a JSON file with:
    - Progress entries (task updates, completions)
    - Learnings (patterns, gotchas discovered)
    - Session summaries (for context resets)

    This is inspired by claudia's progress.txt but uses JSON for structured data.
    """

    def __init__(self, path: str | None = None):
        """
        Initialize the progress log.

        Args:
            path: Path to the progress log file. Defaults to ./data/progress.json
        """
        self._path = path or os.getenv("PROGRESS_LOG_PATH", DEFAULT_PROGRESS_PATH)
        self._entries: list[ProgressEntry] = []
        self._learnings: list[Learning] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load the progress log from disk if not already loaded."""
        if self._loaded:
            return

        # Ensure directory exists
        log_dir = os.path.dirname(self._path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                    self._entries = [
                        ProgressEntry.from_dict(e) for e in data.get("entries", [])
                    ]
                    self._learnings = [
            Learning.from_dict(item)
            for item in data.get("learnings", [])
        ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load progress log: %s", e)
                self._entries = []
                self._learnings = []
        else:
            self._entries = []
            self._learnings = []

        self._loaded = True
        logger.debug("Loaded progress log with %d entries, %d learnings",
                    len(self._entries), len(self._learnings))

    def _save(self) -> None:
        """Save the progress log to disk."""
        # Ensure directory exists
        log_dir = os.path.dirname(self._path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        data = {
            "entries": [e.to_dict() for e in self._entries],
            "learnings": [l.to_dict() for l in self._learnings],
        }

        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def add_entry(
        self,
        entry_type: str,
        summary: str,
        jorb_id: str | None = None,
        jorb_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ProgressEntry:
        """
        Add a progress entry.

        Args:
            entry_type: Type of entry (task_progress, learning, handoff, gotcha, session_summary)
            summary: Brief summary of the entry
            jorb_id: Optional jorb ID this relates to
            jorb_name: Optional jorb name
            details: Optional additional details

        Returns:
            The created ProgressEntry
        """
        self._ensure_loaded()

        entry = ProgressEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            jorb_id=jorb_id,
            jorb_name=jorb_name,
            entry_type=entry_type,
            summary=summary,
            details=details or {},
        )

        self._entries.append(entry)
        self._save()

        logger.info("Added progress entry: %s - %s", entry_type, summary[:50])
        return entry

    def add_learning(
        self,
        category: str,
        subject: str,
        insight: str,
        jorb_id: str | None = None,
        confidence: str = "medium",
    ) -> Learning:
        """
        Add a learning/gotcha.

        Args:
            category: Category (contact_behavior, timing, process, gotcha, tip)
            subject: What/who this is about (e.g., "Magic", "Hotel Zetta")
            insight: The actual learning
            jorb_id: Optional jorb where this was discovered
            confidence: Confidence level (low, medium, high)

        Returns:
            The created Learning
        """
        self._ensure_loaded()

        # Generate a simple ID
        learning_id = f"learn_{len(self._learnings) + 1:05d}"

        learning = Learning(
            id=learning_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            subject=subject,
            insight=insight,
            jorb_id=jorb_id,
            confidence=confidence,
        )

        self._learnings.append(learning)
        self._save()

        logger.info("Added learning [%s]: %s - %s", category, subject, insight[:50])
        return learning

    def get_recent_entries(self, limit: int = 50) -> list[ProgressEntry]:
        """
        Get the most recent progress entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of entries, most recent first
        """
        self._ensure_loaded()
        return list(reversed(self._entries[-limit:]))

    def get_entries_for_jorb(self, jorb_id: str) -> list[ProgressEntry]:
        """
        Get all entries for a specific jorb.

        Args:
            jorb_id: The jorb ID

        Returns:
            List of entries for this jorb, oldest first
        """
        self._ensure_loaded()
        return [e for e in self._entries if e.jorb_id == jorb_id]

    def get_all_learnings(self) -> list[Learning]:
        """
        Get all learnings.

        Returns:
            List of all learnings
        """
        self._ensure_loaded()
        return self._learnings.copy()

    def get_learnings_for_subject(self, subject: str) -> list[Learning]:
        """
        Get learnings about a specific subject.

        Args:
            subject: The subject to search for (case-insensitive partial match)

        Returns:
            List of matching learnings
        """
        self._ensure_loaded()
        subject_lower = subject.lower()
        return [
            l for l in self._learnings
            if subject_lower in l.subject.lower()
        ]

    def get_learnings_by_category(self, category: str) -> list[Learning]:
        """
        Get learnings in a specific category.

        Args:
            category: The category to filter by

        Returns:
            List of learnings in this category
        """
        self._ensure_loaded()
        return [l for l in self._learnings if l.category == category]

    def format_recent_for_prompt(self, limit: int = 20) -> str:
        """
        Format recent entries for inclusion in a prompt.

        Returns a markdown-formatted string suitable for LLM context.

        Args:
            limit: Maximum number of entries to include

        Returns:
            Markdown-formatted progress summary
        """
        self._ensure_loaded()

        lines = ["## Recent Progress\n"]

        recent = self.get_recent_entries(limit)
        if not recent:
            lines.append("No recent progress entries.\n")
        else:
            for entry in recent:
                date = entry.timestamp[:10]  # Just the date
                jorb_ref = f" [{entry.jorb_name or entry.jorb_id}]" if entry.jorb_id else ""
                lines.append(f"- **{date}**{jorb_ref}: {entry.summary}")

        return "\n".join(lines)

    def format_learnings_for_prompt(self, subjects: list[str] | None = None) -> str:
        """
        Format learnings for inclusion in a prompt.

        Args:
            subjects: Optional list of subjects to filter to

        Returns:
            Markdown-formatted learnings summary
        """
        self._ensure_loaded()

        lines = ["## Learnings & Gotchas\n"]

        learnings = self._learnings
        if subjects:
            subject_lowers = [s.lower() for s in subjects]
            learnings = [
                l for l in learnings
                if any(s in l.subject.lower() for s in subject_lowers)
            ]

        if not learnings:
            lines.append("No relevant learnings recorded.\n")
        else:
            # Group by category
            by_category: dict[str, list[Learning]] = {}
            for l in learnings:
                if l.category not in by_category:
                    by_category[l.category] = []
                by_category[l.category].append(l)

            for category, cat_learnings in by_category.items():
                lines.append(f"\n### {category.replace('_', ' ').title()}\n")
                for l in cat_learnings:
                    confidence_marker = {"high": "✓", "medium": "~", "low": "?"}.get(
                        l.confidence, ""
                    )
                    lines.append(f"- {confidence_marker} **{l.subject}**: {l.insight}")

        return "\n".join(lines)

    def record_session_handoff(
        self,
        jorb_summaries: list[dict[str, Any]],
        session_stats: dict[str, Any] | None = None,
    ) -> ProgressEntry:
        """
        Record a session handoff (context reset).

        This is the "ralph loop" pattern - when context gets too long,
        we compress it to a summary for the next session.

        Args:
            jorb_summaries: List of jorb state summaries
            session_stats: Optional session statistics

        Returns:
            The created handoff entry
        """
        details = {
            "jorb_summaries": jorb_summaries,
            "session_stats": session_stats or {},
        }

        summary = f"Session handoff with {len(jorb_summaries)} active jorbs"
        if session_stats:
            msg_count = session_stats.get("messages_processed", 0)
            if msg_count:
                summary += f", {msg_count} messages processed"

        return self.add_entry(
            entry_type="handoff",
            summary=summary,
            details=details,
        )


# Singleton instance
_progress_log: ProgressLog | None = None


def get_progress_log() -> ProgressLog:
    """Get the global progress log instance."""
    global _progress_log
    if _progress_log is None:
        _progress_log = ProgressLog()
    return _progress_log


__all__ = [
    "ProgressLog",
    "ProgressEntry",
    "Learning",
    "get_progress_log",
]
