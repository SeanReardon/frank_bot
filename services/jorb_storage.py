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
    personality: str = "default"  # Personality ID for LLM sessions
    progress_summary: str | None = None
    created_at: str = ""  # ISO 8601 timestamp
    updated_at: str = ""  # ISO 8601 timestamp
    paused_reason: str | None = None
    needs_approval_for: str | None = None
    awaiting: str | None = None
    # Metrics fields
    messages_in: int = 0
    messages_out: int = 0
    tokens_used: int = 0
    estimated_cost: float = 0.0
    context_resets: int = 0
    # Outcome fields (populated when complete/failed)
    outcome_result: str | None = None
    outcome_completed_at: str | None = None
    outcome_failure_reason: str | None = None
    # Script results field for tracking executed scripts
    script_results: list[dict] = field(default_factory=list)
    # Optional metadata blob for routing/transports (JSON dict)
    metadata_json: str = "{}"
    # Optional wake schedule for worker tick loop (ISO 8601)
    wake_at: str | None = None

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

    @property
    def metrics(self) -> dict[str, Any]:
        """Return metrics as a dictionary."""
        return {
            "messages_in": self.messages_in,
            "messages_out": self.messages_out,
            "tokens_used": self.tokens_used,
            "estimated_cost": self.estimated_cost,
            "context_resets": self.context_resets,
        }

    @property
    def metadata(self) -> dict[str, Any]:
        """Parse routing/transport metadata from JSON."""
        try:
            data = json.loads(self.metadata_json or "{}")
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @metadata.setter
    def metadata(self, value: dict[str, Any]) -> None:
        """Serialize routing/transport metadata to JSON."""
        self.metadata_json = json.dumps(value or {})

    @property
    def outcome(self) -> dict[str, Any] | None:
        """Return outcome as a dictionary if present."""
        if self.status not in ("complete", "failed"):
            return None
        return {
            "result": self.outcome_result,
            "completed_at": self.outcome_completed_at,
            "failure_reason": self.outcome_failure_reason,
        }


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
    personality TEXT DEFAULT 'default',
    progress_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    paused_reason TEXT,
    needs_approval_for TEXT,
    awaiting TEXT,
    -- Metrics columns (added in v2)
    messages_in INTEGER DEFAULT 0,
    messages_out INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0.0,
    context_resets INTEGER DEFAULT 0,
    -- Outcome columns (added in v2)
    outcome_result TEXT,
    outcome_completed_at TEXT,
    outcome_failure_reason TEXT,
    -- Script results column (added in v4)
    script_results TEXT DEFAULT '[]',
    -- Metadata blob for routing/transports (added in v5)
    metadata_json TEXT DEFAULT '{}',
    -- Wake schedule for background worker tick loop (added in v5)
    wake_at TEXT
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

# Migration SQL to add metrics and outcome columns to existing databases
_MIGRATION_V2_SQL = """
-- Add metrics columns if they don't exist
ALTER TABLE jorbs ADD COLUMN messages_in INTEGER DEFAULT 0;
ALTER TABLE jorbs ADD COLUMN messages_out INTEGER DEFAULT 0;
ALTER TABLE jorbs ADD COLUMN tokens_used INTEGER DEFAULT 0;
ALTER TABLE jorbs ADD COLUMN estimated_cost REAL DEFAULT 0.0;
ALTER TABLE jorbs ADD COLUMN context_resets INTEGER DEFAULT 0;
-- Add outcome columns if they don't exist
ALTER TABLE jorbs ADD COLUMN outcome_result TEXT;
ALTER TABLE jorbs ADD COLUMN outcome_completed_at TEXT;
ALTER TABLE jorbs ADD COLUMN outcome_failure_reason TEXT;
"""


def _row_to_jorb(row: aiosqlite.Row) -> Jorb:
    """Convert a database row to a Jorb object."""
    # Parse script_results JSON (may be None in older databases before migration)
    script_results_json = row["script_results"]
    script_results: list[dict] = []
    if script_results_json:
        try:
            script_results = json.loads(script_results_json)
        except (json.JSONDecodeError, TypeError):
            script_results = []

    return Jorb(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        original_plan=row["original_plan"],
        contacts_json=row["contacts_json"],
        personality=row["personality"] or "default",
        progress_summary=row["progress_summary"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        paused_reason=row["paused_reason"],
        needs_approval_for=row["needs_approval_for"],
        awaiting=row["awaiting"],
        # Metrics fields (may be None in older databases before migration)
        messages_in=row["messages_in"] or 0,
        messages_out=row["messages_out"] or 0,
        tokens_used=row["tokens_used"] or 0,
        estimated_cost=row["estimated_cost"] or 0.0,
        context_resets=row["context_resets"] or 0,
        # Outcome fields
        outcome_result=row["outcome_result"],
        outcome_completed_at=row["outcome_completed_at"],
        outcome_failure_reason=row["outcome_failure_reason"],
        # Script results field
        script_results=script_results,
        metadata_json=(row["metadata_json"] or "{}") if "metadata_json" in row.keys() else "{}",  # type: ignore[attr-defined]
        wake_at=(row["wake_at"] if "wake_at" in row.keys() else None),  # type: ignore[attr-defined]
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

            # Run migration for existing databases (adds new columns if missing)
            await self._run_migrations(conn)

        self._initialized = True
        logger.info("Initialized jorb storage schema at %s", self._db_path)

    async def _run_migrations(self, conn: aiosqlite.Connection) -> None:
        """Run database migrations for schema updates."""
        # Check if metrics columns exist
        cursor = await conn.execute("PRAGMA table_info(jorbs)")
        columns = {row[1] for row in await cursor.fetchall()}

        # Migration v2: Add metrics and outcome columns
        # Migration v3: Add personality column
        # Migration v4: Add script_results column
        # Migration v5: Add metadata_json + wake_at columns
        new_columns = [
            ("messages_in", "INTEGER DEFAULT 0"),
            ("messages_out", "INTEGER DEFAULT 0"),
            ("tokens_used", "INTEGER DEFAULT 0"),
            ("estimated_cost", "REAL DEFAULT 0.0"),
            ("context_resets", "INTEGER DEFAULT 0"),
            ("outcome_result", "TEXT"),
            ("outcome_completed_at", "TEXT"),
            ("outcome_failure_reason", "TEXT"),
            ("personality", "TEXT DEFAULT 'default'"),
            ("script_results", "TEXT DEFAULT '[]'"),
            ("metadata_json", "TEXT DEFAULT '{}'"),
            ("wake_at", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                try:
                    await conn.execute(f"ALTER TABLE jorbs ADD COLUMN {col_name} {col_type}")
                    logger.info("Added column %s to jorbs table", col_name)
                except Exception as e:
                    # Column might already exist from previous partial migration
                    logger.debug("Column %s migration skipped: %s", col_name, e)

        await conn.commit()

    async def create_jorb(
        self,
        name: str,
        plan: str,
        contacts: list[JorbContact] | None = None,
        personality: str = "default",
    ) -> Jorb:
        """
        Create a new jorb.

        Args:
            name: Human-readable name for the jorb
            plan: The full plan text
            contacts: List of contacts involved in the jorb
            personality: Personality ID for this jorb's LLM sessions (default: "default")

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
            personality=personality,
            created_at=now,
            updated_at=now,
        )

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO jorbs (
                    id, name, status, original_plan, contacts_json, personality,
                    progress_summary, created_at, updated_at,
                    paused_reason, needs_approval_for, awaiting,
                    messages_in, messages_out, tokens_used, estimated_cost, context_resets,
                    outcome_result, outcome_completed_at, outcome_failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    jorb.id,
                    jorb.name,
                    jorb.status,
                    jorb.original_plan,
                    jorb.contacts_json,
                    jorb.personality,
                    jorb.progress_summary,
                    jorb.created_at,
                    jorb.updated_at,
                    jorb.paused_reason,
                    jorb.needs_approval_for,
                    jorb.awaiting,
                    jorb.messages_in,
                    jorb.messages_out,
                    jorb.tokens_used,
                    jorb.estimated_cost,
                    jorb.context_resets,
                    jorb.outcome_result,
                    jorb.outcome_completed_at,
                    jorb.outcome_failure_reason,
                ),
            )
            await conn.commit()

        logger.info("Created jorb %s: %s (personality: %s)", jorb.id, jorb.name, jorb.personality)
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
            "personality",
            "progress_summary",
            "paused_reason",
            "needs_approval_for",
            "awaiting",
            # Metrics fields
            "messages_in",
            "messages_out",
            "tokens_used",
            "estimated_cost",
            "context_resets",
            # Outcome fields
            "outcome_result",
            "outcome_completed_at",
            "outcome_failure_reason",
            # Script results field
            "script_results",
            # Metadata + scheduling fields
            "metadata_json",
            "wake_at",
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

    async def list_due_jorbs(
        self,
        now_iso: str | None = None,
        limit: int = 50,
    ) -> list[Jorb]:
        """
        List running jorbs that are due for a worker tick.

        A jorb is due when:
        - status == 'running'
        - wake_at is set
        - wake_at <= now

        Args:
            now_iso: Current time in ISO 8601 (defaults to now UTC)
            limit: Max number of jorbs to return

        Returns:
            List of due jorbs ordered by wake_at ascending
        """
        await self._ensure_initialized()

        if now_iso is None:
            now_iso = datetime.now(timezone.utc).isoformat()

        limit = max(1, min(500, int(limit)))

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT * FROM jorbs
                WHERE status = 'running'
                AND wake_at IS NOT NULL
                AND wake_at <= ?
                ORDER BY wake_at ASC
                LIMIT ?
                """,
                (now_iso, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_jorb(row) for row in rows]

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

        # Increment context_resets counter
        await self.increment_metrics(jorb_id, context_resets=1)

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

    # Metrics helper methods

    async def increment_metrics(
        self,
        jorb_id: str,
        messages_in: int = 0,
        messages_out: int = 0,
        tokens_used: int = 0,
        estimated_cost: float = 0.0,
        context_resets: int = 0,
    ) -> None:
        """
        Atomically increment metrics counters for a jorb.

        Args:
            jorb_id: The jorb ID
            messages_in: Inbound messages to add
            messages_out: Outbound messages to add
            tokens_used: Tokens to add
            estimated_cost: Cost to add (in USD)
            context_resets: Context resets to add
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE jorbs SET
                    messages_in = messages_in + ?,
                    messages_out = messages_out + ?,
                    tokens_used = tokens_used + ?,
                    estimated_cost = estimated_cost + ?,
                    context_resets = context_resets + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    messages_in,
                    messages_out,
                    tokens_used,
                    estimated_cost,
                    context_resets,
                    datetime.now(timezone.utc).isoformat(),
                    jorb_id,
                ),
            )
            await conn.commit()

    async def set_outcome(
        self,
        jorb_id: str,
        result: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """
        Set the outcome fields for a completed or failed jorb.

        Args:
            jorb_id: The jorb ID
            result: Summary of what was achieved
            failure_reason: Why the jorb failed (if applicable)
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE jorbs SET
                    outcome_result = ?,
                    outcome_completed_at = ?,
                    outcome_failure_reason = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    result,
                    datetime.now(timezone.utc).isoformat(),
                    failure_reason,
                    datetime.now(timezone.utc).isoformat(),
                    jorb_id,
                ),
            )
            await conn.commit()

    async def get_all_contacts_from_jorbs(self) -> set[str]:
        """
        Get all unique contact identifiers across all jorbs (any status).

        This is used for trusted sender detection - if a sender has previously
        been associated with any jorb, they are considered a known contact.

        Returns:
            Set of normalized contact identifiers (phone numbers, usernames, emails)
        """
        await self._ensure_initialized()

        contacts: set[str] = set()

        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute("SELECT contacts_json FROM jorbs")
            rows = await cursor.fetchall()

            for row in rows:
                contacts_json = row[0]
                if contacts_json:
                    try:
                        contact_list = json.loads(contacts_json)
                        for contact in contact_list:
                            identifier = contact.get("identifier", "")
                            if identifier:
                                # Normalize the identifier
                                normalized = self._normalize_identifier(identifier)
                                contacts.add(normalized)
                    except (json.JSONDecodeError, TypeError):
                        continue

        logger.debug("Found %d unique contacts across all jorbs", len(contacts))
        return contacts

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        """
        Normalize a contact identifier for comparison.

        Handles:
        - Phone numbers: strips +1, normalizes to 10-digit
        - Usernames: lowercases, strips @ prefix
        - Emails: lowercases

        Args:
            identifier: The raw contact identifier

        Returns:
            Normalized identifier string
        """
        identifier = identifier.strip()

        # Check if it looks like a phone number
        digits = "".join(c for c in identifier if c.isdigit())
        if len(digits) >= 10:
            # Phone number - normalize to last 10 digits
            return digits[-10:]

        # Check if it looks like a username (starts with @)
        if identifier.startswith("@"):
            return identifier[1:].lower()

        # Check if it looks like an email
        if "@" in identifier and "." in identifier:
            return identifier.lower()

        # Default: just lowercase
        return identifier.lower()

    async def is_frank_bot_message(
        self,
        content: str,
        timestamp: datetime | str,
        time_window_seconds: int = 5,
    ) -> bool:
        """
        Check if a message was sent by frank_bot (exists in jorb_messages).

        Used to distinguish between Sean's direct messages and frank_bot's messages.
        A message is considered from frank_bot if there's a matching outbound message
        in jorb_messages within the time window.

        Args:
            content: The message content to check
            timestamp: The message timestamp (datetime or ISO string)
            time_window_seconds: How many seconds to look around the timestamp

        Returns:
            True if a matching message exists in jorb_messages, False otherwise
        """
        await self._ensure_initialized()

        # Convert timestamp to datetime if needed
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Calculate time bounds
        from datetime import timedelta

        time_lower = (timestamp - timedelta(seconds=time_window_seconds)).isoformat()
        time_upper = (timestamp + timedelta(seconds=time_window_seconds)).isoformat()

        async with aiosqlite.connect(self._db_path) as conn:
            # Look for outbound messages with similar content within time window
            cursor = await conn.execute(
                """
                SELECT id, content FROM jorb_messages
                WHERE direction = 'outbound'
                AND timestamp >= ?
                AND timestamp <= ?
                """,
                (time_lower, time_upper),
            )
            rows = await cursor.fetchall()

            # Check for content similarity (substring match)
            content_lower = content.lower().strip()
            for row in rows:
                db_content = row[1].lower().strip() if row[1] else ""
                # Match if content is a substring or vice versa
                if content_lower in db_content or db_content in content_lower:
                    logger.debug(
                        "Message matches frank_bot message (id=%s): %s...",
                        row[0],
                        content[:30],
                    )
                    return True

        return False

    async def get_aggregate_metrics(
        self,
        status_filter: Literal["open", "closed", "all"] = "all",
    ) -> dict[str, Any]:
        """
        Get aggregate metrics across all jorbs.

        Args:
            status_filter: Filter by status category

        Returns:
            Dict with totals for messages, tokens, cost, and counts by status
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row

            # Build WHERE clause based on filter
            if status_filter == "open":
                where_clause = "WHERE status IN ('planning', 'running', 'paused')"
            elif status_filter == "closed":
                where_clause = "WHERE status IN ('complete', 'failed', 'cancelled')"
            else:
                where_clause = ""

            # Get aggregate metrics
            cursor = await conn.execute(
                f"""
                SELECT
                    COUNT(*) as total_jorbs,
                    SUM(messages_in) as total_messages_in,
                    SUM(messages_out) as total_messages_out,
                    SUM(tokens_used) as total_tokens,
                    SUM(estimated_cost) as total_cost,
                    SUM(context_resets) as total_context_resets
                FROM jorbs
                {where_clause}
                """
            )
            row = await cursor.fetchone()

            # Get counts by status
            cursor = await conn.execute(
                f"""
                SELECT status, COUNT(*) as count
                FROM jorbs
                {where_clause}
                GROUP BY status
                """
            )
            status_rows = await cursor.fetchall()
            status_counts = {r["status"]: r["count"] for r in status_rows}

            return {
                "total_jorbs": row["total_jorbs"] or 0,
                "total_messages_in": row["total_messages_in"] or 0,
                "total_messages_out": row["total_messages_out"] or 0,
                "total_messages": (row["total_messages_in"] or 0) + (row["total_messages_out"] or 0),
                "total_tokens": row["total_tokens"] or 0,
                "total_cost": row["total_cost"] or 0.0,
                "total_context_resets": row["total_context_resets"] or 0,
                "by_status": {
                    "planning": status_counts.get("planning", 0),
                    "running": status_counts.get("running", 0),
                    "paused": status_counts.get("paused", 0),
                    "complete": status_counts.get("complete", 0),
                    "failed": status_counts.get("failed", 0),
                    "cancelled": status_counts.get("cancelled", 0),
                },
            }

    # Script results methods (frank_bot-00111)

    async def add_script_result(self, jorb_id: str, result_dict: dict) -> bool:
        """
        Add a script result to a jorb's history.

        Args:
            jorb_id: The jorb ID
            result_dict: Dictionary containing:
                - script: str - name of the script executed
                - result: any - the result/output of the script
                - success: bool - whether execution succeeded
                - timestamp: str - ISO 8601 timestamp (optional, defaults to now)

        Returns:
            True if added successfully, False if jorb not found
        """
        await self._ensure_initialized()

        # Validate required fields
        required_fields = {"script", "result", "success"}
        if not required_fields.issubset(result_dict.keys()):
            missing = required_fields - result_dict.keys()
            raise ValueError(f"Missing required fields: {missing}")

        # Ensure timestamp exists
        if "timestamp" not in result_dict:
            result_dict["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Get current script results
        jorb = await self.get_jorb(jorb_id)
        if jorb is None:
            return False

        # Append new result to the list
        updated_results = jorb.script_results + [result_dict]

        # Update the jorb with new script results (serialize to JSON)
        await self.update_jorb(jorb_id, script_results=json.dumps(updated_results))

        logger.debug("Added script result to jorb %s: %s", jorb_id, result_dict["script"])
        return True

    async def get_script_results(
        self,
        jorb_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get script results for a jorb, most recent first.

        Args:
            jorb_id: The jorb ID
            limit: Maximum number of results to return (default 20)

        Returns:
            List of script result dictionaries, sorted by timestamp descending
            (most recent first). Each dict contains: script, result, success, timestamp.

        Raises:
            ValueError: If jorb not found
        """
        await self._ensure_initialized()

        jorb = await self.get_jorb(jorb_id)
        if jorb is None:
            raise ValueError(f"Jorb not found: {jorb_id}")

        # Sort by timestamp descending (most recent first)
        sorted_results = sorted(
            jorb.script_results,
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )

        # Return limited number of results
        return sorted_results[:limit]


__all__ = [
    "JorbStorage",
    "Jorb",
    "JorbMessage",
    "JorbCheckpoint",
    "JorbContact",
    "JorbWithMessages",
    "JorbStatus",
]
