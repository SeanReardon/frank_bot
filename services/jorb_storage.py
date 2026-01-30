"""
Jorb Storage Service for SQLite persistence.

Stores jorbs and their message history in a SQLite database.
Supports CRUD operations and checkpoint management for long-running tasks.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import aiosqlite

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "./data/jorbs.db"

# Status type for type checking
JorbStatus = Literal["planning", "running", "paused", "complete", "failed", "cancelled"]
Direction = Literal["inbound", "outbound"]
Channel = Literal["telegram", "sms", "email"]


@dataclass
class JorbContact:
    """A contact associated with a jorb."""

    identifier: str
    channel: Channel
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "identifier": self.identifier,
            "channel": self.channel,
        }
        if self.name:
            result["name"] = self.name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JorbContact:
        """Create from dictionary."""
        return cls(
            identifier=data["identifier"],
            channel=data["channel"],
            name=data.get("name"),
        )


@dataclass
class Jorb:
    """
    A long-lived autonomous task.

    Fields match schemas/jorb.schema.json.
    """

    id: str
    name: str
    status: JorbStatus
    original_plan: str
    contacts_json: str = "[]"  # JSON array of JorbContact dicts
    progress_summary: str | None = None
    created_at: str = ""  # ISO 8601 timestamp
    updated_at: str = ""  # ISO 8601 timestamp
    paused_reason: str | None = None
    needs_approval_for: str | None = None
    awaiting: str | None = None

    def __post_init__(self) -> None:
        """Set default timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @property
    def contacts(self) -> list[JorbContact]:
        """Parse contacts from JSON."""
        try:
            data = json.loads(self.contacts_json)
            return [JorbContact.from_dict(c) for c in data]
        except (json.JSONDecodeError, KeyError):
            return []

    @contacts.setter
    def contacts(self, value: list[JorbContact]) -> None:
        """Serialize contacts to JSON."""
        self.contacts_json = json.dumps([c.to_dict() for c in value])


@dataclass
class JorbMessage:
    """
    A message in a jorb's conversation history.

    Fields match schemas/jorb.schema.json $defs/JorbMessage.
    """

    id: str
    jorb_id: str
    timestamp: str  # ISO 8601
    direction: Direction
    channel: Channel
    sender: str | None = None
    sender_name: str | None = None
    recipient: str | None = None
    content: str = ""
    agent_reasoning: str | None = None

    def __post_init__(self) -> None:
        """Set default timestamp if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class JorbCheckpoint:
    """A context reset checkpoint for a jorb."""

    id: str
    jorb_id: str
    timestamp: str  # ISO 8601
    summary: str
    token_count: int | None = None


@dataclass
class JorbWithMessages:
    """A jorb with its full message history."""

    jorb: Jorb
    messages: list[JorbMessage] = field(default_factory=list)


def _generate_jorb_id() -> str:
    """Generate a unique jorb ID."""
    short_uuid = uuid.uuid4().hex[:8]
    return f"jorb_{short_uuid}"


def _generate_message_id() -> str:
    """Generate a unique message ID."""
    return f"msg_{uuid.uuid4().hex[:12]}"


def _generate_checkpoint_id() -> str:
    """Generate a unique checkpoint ID."""
    return f"ckpt_{uuid.uuid4().hex[:8]}"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jorbs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(
        status IN ('planning', 'running', 'paused', 'complete', 'failed', 'cancelled')
    ),
    original_plan TEXT NOT NULL,
    contacts_json TEXT DEFAULT '[]',
    progress_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    paused_reason TEXT,
    needs_approval_for TEXT,
    awaiting TEXT
);

CREATE TABLE IF NOT EXISTS jorb_messages (
    id TEXT PRIMARY KEY,
    jorb_id TEXT NOT NULL REFERENCES jorbs(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
    channel TEXT NOT NULL CHECK(channel IN ('telegram', 'sms', 'email')),
    sender TEXT,
    sender_name TEXT,
    recipient TEXT,
    content TEXT NOT NULL,
    agent_reasoning TEXT
);

CREATE TABLE IF NOT EXISTS jorb_checkpoints (
    id TEXT PRIMARY KEY,
    jorb_id TEXT NOT NULL REFERENCES jorbs(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    summary TEXT NOT NULL,
    token_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_jorb_messages_jorb_id
    ON jorb_messages(jorb_id);
CREATE INDEX IF NOT EXISTS idx_jorb_messages_timestamp
    ON jorb_messages(jorb_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_jorbs_status
    ON jorbs(status);
CREATE INDEX IF NOT EXISTS idx_jorb_checkpoints_jorb_id
    ON jorb_checkpoints(jorb_id);
"""


def _row_to_jorb(row: aiosqlite.Row) -> Jorb:
    """Convert a database row to a Jorb object."""
    return Jorb(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        original_plan=row["original_plan"],
        contacts_json=row["contacts_json"],
        progress_summary=row["progress_summary"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        paused_reason=row["paused_reason"],
        needs_approval_for=row["needs_approval_for"],
        awaiting=row["awaiting"],
    )


def _row_to_message(row: aiosqlite.Row) -> JorbMessage:
    """Convert a database row to a JorbMessage object."""
    return JorbMessage(
        id=row["id"],
        jorb_id=row["jorb_id"],
        timestamp=row["timestamp"],
        direction=row["direction"],
        channel=row["channel"],
        sender=row["sender"],
        sender_name=row["sender_name"],
        recipient=row["recipient"],
        content=row["content"],
        agent_reasoning=row["agent_reasoning"],
    )


class JorbStorage:
    """
    Service for storing and retrieving jorbs and their messages.

    Uses SQLite via aiosqlite for async persistence.
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize the jorb storage service.

        Args:
            db_path: Path to SQLite database. Defaults to JORBS_DB_PATH env var or ./data/jorbs.db
        """
        self._db_path = db_path or os.getenv("JORBS_DB_PATH", DEFAULT_DB_PATH)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Initialize the database schema if needed."""
        if self._initialized:
            return

        # Ensure directory exists
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA_SQL)
            await conn.commit()

        self._initialized = True
        logger.info("Initialized jorb storage schema at %s", self._db_path)

    async def create_jorb(
        self,
        name: str,
        plan: str,
        contacts: list[JorbContact] | None = None,
    ) -> Jorb:
        """
        Create a new jorb.

        Args:
            name: Human-readable name for the jorb
            plan: The full plan text
            contacts: List of contacts involved in the jorb

        Returns:
            The created Jorb with generated ID
        """
        await self._ensure_initialized()

        jorb_id = _generate_jorb_id()
        now = datetime.now(timezone.utc).isoformat()

        contacts_json = "[]"
        if contacts:
            contacts_json = json.dumps([c.to_dict() for c in contacts])

        jorb = Jorb(
            id=jorb_id,
            name=name,
            status="planning",
            original_plan=plan,
            contacts_json=contacts_json,
            created_at=now,
            updated_at=now,
        )

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO jorbs (
                    id, name, status, original_plan, contacts_json,
                    progress_summary, created_at, updated_at,
                    paused_reason, needs_approval_for, awaiting
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    jorb.id,
                    jorb.name,
                    jorb.status,
                    jorb.original_plan,
                    jorb.contacts_json,
                    jorb.progress_summary,
                    jorb.created_at,
                    jorb.updated_at,
                    jorb.paused_reason,
                    jorb.needs_approval_for,
                    jorb.awaiting,
                ),
            )
            await conn.commit()

        logger.info("Created jorb %s: %s", jorb.id, jorb.name)
        return jorb

    async def get_jorb(self, jorb_id: str) -> Jorb | None:
        """
        Retrieve a jorb by ID.

        Args:
            jorb_id: The unique jorb identifier

        Returns:
            The Jorb if found, None otherwise
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM jorbs WHERE id = ?",
                (jorb_id,),
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            return _row_to_jorb(row)

    async def list_jorbs(
        self,
        status_filter: Literal["open", "closed", "all"] = "all",
    ) -> list[Jorb]:
        """
        List jorbs with optional status filter.

        Args:
            status_filter: Filter by status category
                - "open": planning, running, paused
                - "closed": complete, failed, cancelled
                - "all": all jorbs

        Returns:
            List of Jorb objects sorted by updated_at descending
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row

            if status_filter == "open":
                cursor = await conn.execute(
                    """
                    SELECT * FROM jorbs
                    WHERE status IN ('planning', 'running', 'paused')
                    ORDER BY updated_at DESC
                    """
                )
            elif status_filter == "closed":
                cursor = await conn.execute(
                    """
                    SELECT * FROM jorbs
                    WHERE status IN ('complete', 'failed', 'cancelled')
                    ORDER BY updated_at DESC
                    """
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM jorbs ORDER BY updated_at DESC"
                )

            rows = await cursor.fetchall()
            return [_row_to_jorb(row) for row in rows]

    async def update_jorb(self, jorb_id: str, **updates: Any) -> Jorb | None:
        """
        Update jorb fields.

        Args:
            jorb_id: The unique jorb identifier
            **updates: Fields to update. Valid fields:
                - name, status, original_plan, contacts_json
                - progress_summary, paused_reason, needs_approval_for, awaiting

        Returns:
            The updated Jorb if found, None otherwise
        """
        # Validate field names
        valid_fields = {
            "name",
            "status",
            "original_plan",
            "contacts_json",
            "progress_summary",
            "paused_reason",
            "needs_approval_for",
            "awaiting",
        }
        invalid_fields = set(updates.keys()) - valid_fields
        if invalid_fields:
            raise ValueError(f"Invalid fields for update: {invalid_fields}")

        if not updates:
            return await self.get_jorb(jorb_id)

        await self._ensure_initialized()

        # Always update updated_at
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [jorb_id]

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                f"UPDATE jorbs SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()

        updated_jorb = await self.get_jorb(jorb_id)
        if updated_jorb:
            logger.info("Updated jorb %s: %s", jorb_id, list(updates.keys()))
        return updated_jorb

    # Message tracking methods (frank_bot-00052)

    async def add_message(self, jorb_id: str, message: JorbMessage) -> str:
        """
        Add a message to a jorb's conversation history.

        Args:
            jorb_id: The jorb ID
            message: The message to add

        Returns:
            The message ID
        """
        await self._ensure_initialized()

        # Generate ID if not provided
        if not message.id:
            message.id = _generate_message_id()

        # Ensure jorb_id matches
        message.jorb_id = jorb_id

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO jorb_messages (
                    id, jorb_id, timestamp, direction, channel,
                    sender, sender_name, recipient, content, agent_reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.jorb_id,
                    message.timestamp,
                    message.direction,
                    message.channel,
                    message.sender,
                    message.sender_name,
                    message.recipient,
                    message.content,
                    message.agent_reasoning,
                ),
            )
            await conn.commit()

        logger.debug("Added message %s to jorb %s", message.id, jorb_id)
        return message.id

    async def get_messages(
        self,
        jorb_id: str,
        limit: int = 50,
    ) -> list[JorbMessage]:
        """
        Get messages for a jorb.

        Args:
            jorb_id: The jorb ID
            limit: Maximum number of messages to return

        Returns:
            List of messages sorted by timestamp ascending (oldest first)
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT * FROM jorb_messages
                WHERE jorb_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (jorb_id, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_message(row) for row in rows]

    async def get_open_jorbs_with_messages(self) -> list[JorbWithMessages]:
        """
        Get all open jorbs (running/paused) with their full message history.

        Returns:
            List of JorbWithMessages for all running and paused jorbs
        """
        jorbs = await self.list_jorbs(status_filter="open")

        # Filter to only running and paused (not planning)
        active_jorbs = [j for j in jorbs if j.status in ("running", "paused")]

        results = []
        for jorb in active_jorbs:
            messages = await self.get_messages(jorb.id, limit=1000)
            results.append(JorbWithMessages(jorb=jorb, messages=messages))

        return results

    async def add_checkpoint(
        self,
        jorb_id: str,
        summary: str,
        token_count: int | None = None,
    ) -> str:
        """
        Create a context reset checkpoint for a jorb.

        Args:
            jorb_id: The jorb ID
            summary: The agent's summary at checkpoint time
            token_count: Optional token count used in session before reset

        Returns:
            The checkpoint ID
        """
        await self._ensure_initialized()

        checkpoint_id = _generate_checkpoint_id()
        timestamp = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO jorb_checkpoints (id, jorb_id, timestamp, summary, token_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (checkpoint_id, jorb_id, timestamp, summary, token_count),
            )
            await conn.commit()

        logger.info("Added checkpoint %s for jorb %s", checkpoint_id, jorb_id)
        return checkpoint_id

    async def get_checkpoints(self, jorb_id: str) -> list[JorbCheckpoint]:
        """
        Get all checkpoints for a jorb.

        Args:
            jorb_id: The jorb ID

        Returns:
            List of checkpoints sorted by timestamp ascending
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT * FROM jorb_checkpoints
                WHERE jorb_id = ?
                ORDER BY timestamp ASC
                """,
                (jorb_id,),
            )
            rows = await cursor.fetchall()

            return [
                JorbCheckpoint(
                    id=row["id"],
                    jorb_id=row["jorb_id"],
                    timestamp=row["timestamp"],
                    summary=row["summary"],
                    token_count=row["token_count"],
                )
                for row in rows
            ]


__all__ = [
    "JorbStorage",
    "Jorb",
    "JorbMessage",
    "JorbCheckpoint",
    "JorbContact",
    "JorbWithMessages",
    "JorbStatus",
]
