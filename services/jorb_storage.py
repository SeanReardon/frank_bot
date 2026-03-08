"""
Jorb Storage Service using durable JSON records.

Each jorb lives in its own JSON file under `./data/jorbs/`, which keeps
conversation history, checkpoints, script results, and routing metadata
inspectable by humans and agentic tooling without SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from services.file_store import (
    derive_json_storage_dir,
    ensure_directory,
    newest_first,
    read_json_file,
    to_thread,
    write_json_atomic,
)
from services.task_classes import FREEFORM_TASK_CLASS, classify_task_class

logger = logging.getLogger(__name__)

# Legacy path hint retained for env/backwards compatibility. The actual JSON
# store lives in `./data/jorbs/`.
DEFAULT_DB_PATH = "./data/jorbs.db"
STORE_SCHEMA_VERSION = 2

JorbStatus = Literal["planning", "running", "paused", "complete", "failed", "cancelled"]
Direction = Literal["inbound", "outbound"]
Channel = Literal["telegram", "telegram_bot", "sms", "email"]


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
    task_class: str = FREEFORM_TASK_CLASS
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


def _parse_json_string(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


def _jorb_to_payload(jorb: Jorb) -> dict[str, Any]:
    payload = asdict(jorb)
    payload["script_results"] = list(jorb.script_results or [])
    return payload


def _payload_to_jorb(payload: dict[str, Any]) -> Jorb:
    script_results = _parse_json_string(payload.get("script_results"), [])
    if not isinstance(script_results, list):
        script_results = []
    return Jorb(
        id=payload["id"],
        name=payload["name"],
        status=payload["status"],
        original_plan=payload["original_plan"],
        contacts_json=str(payload.get("contacts_json") or "[]"),
        personality=str(payload.get("personality") or "default"),
        task_class=str(payload.get("task_class") or FREEFORM_TASK_CLASS),
        progress_summary=payload.get("progress_summary"),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        paused_reason=payload.get("paused_reason"),
        needs_approval_for=payload.get("needs_approval_for"),
        awaiting=payload.get("awaiting"),
        messages_in=int(payload.get("messages_in") or 0),
        messages_out=int(payload.get("messages_out") or 0),
        tokens_used=int(payload.get("tokens_used") or 0),
        estimated_cost=float(payload.get("estimated_cost") or 0.0),
        context_resets=int(payload.get("context_resets") or 0),
        outcome_result=payload.get("outcome_result"),
        outcome_completed_at=payload.get("outcome_completed_at"),
        outcome_failure_reason=payload.get("outcome_failure_reason"),
        script_results=script_results,
        metadata_json=str(payload.get("metadata_json") or "{}"),
        wake_at=payload.get("wake_at"),
    )


def _payload_to_message(payload: dict[str, Any]) -> JorbMessage:
    return JorbMessage(
        id=payload["id"],
        jorb_id=payload["jorb_id"],
        timestamp=payload["timestamp"],
        direction=payload["direction"],
        channel=payload["channel"],
        sender=payload.get("sender"),
        sender_name=payload.get("sender_name"),
        recipient=payload.get("recipient"),
        content=payload.get("content", ""),
        agent_reasoning=payload.get("agent_reasoning"),
    )


def _message_to_payload(message: JorbMessage) -> dict[str, Any]:
    return asdict(message)


def _checkpoint_to_payload(checkpoint: JorbCheckpoint) -> dict[str, Any]:
    return asdict(checkpoint)


def _payload_to_checkpoint(payload: dict[str, Any]) -> JorbCheckpoint:
    return JorbCheckpoint(
        id=payload["id"],
        jorb_id=payload["jorb_id"],
        timestamp=payload["timestamp"],
        summary=payload["summary"],
        token_count=payload.get("token_count"),
    )


class JorbStorage:
    """
    Service for storing and retrieving jorbs and their messages.

    Records are stored as durable JSON files so they can be inspected directly,
    replayed by agents, and migrated without a database runtime dependency.
    """

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, db_path: str | None = None):
        """
        Initialize the jorb storage service.

        Args:
            db_path: Legacy path hint. `.db`/`.json` suffixes are converted into a
                directory-backed JSON store beside the hint path.
        """
        self._path_hint = db_path or os.getenv("JORBS_DB_PATH", DEFAULT_DB_PATH)
        self._legacy_path = Path(self._path_hint)
        self._data_dir = derive_json_storage_dir(self._path_hint, "./data/jorbs")
        self._schema_path = self._data_dir / "_schema.json"
        self._db_path = str(self._data_dir)  # Backwards-compat for tests/introspection.
        self._initialized = False
        lock_key = str(self._data_dir.resolve())
        if lock_key not in self._locks:
            self._locks[lock_key] = asyncio.Lock()
        self._lock = self._locks[lock_key]

    def _jorb_path(self, jorb_id: str) -> Path:
        return self._data_dir / f"{jorb_id}.json"

    async def _read_record(self, jorb_id: str) -> dict[str, Any] | None:
        payload = await to_thread(read_json_file, self._jorb_path(jorb_id), None)
        return payload if isinstance(payload, dict) else None

    async def _write_record(self, jorb_id: str, payload: dict[str, Any]) -> None:
        await to_thread(write_json_atomic, self._jorb_path(jorb_id), payload)

    async def _ensure_initialized(self) -> None:
        """Initialize the JSON store and migrate legacy SQLite data if needed."""
        if self._initialized:
            return

        ensure_directory(self._data_dir)
        if not self._schema_path.exists():
            await to_thread(
                write_json_atomic,
                self._schema_path,
                {
                    "store": "jorbs",
                    "schema_version": STORE_SCHEMA_VERSION,
                    "backing": "json_files",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        if not any(self._data_dir.glob("jorb_*.json")):
            await self._maybe_migrate_legacy_sqlite()
        self._initialized = True
        logger.info("Initialized jorb JSON store at %s", self._data_dir)

    async def _maybe_migrate_legacy_sqlite(self) -> None:
        legacy_file = self._legacy_path
        if legacy_file.suffix != ".db" or not legacy_file.exists():
            return
        if legacy_file.stat().st_size < 100:
            return

        def _looks_like_sqlite(path: Path) -> bool:
            with path.open("rb") as handle:
                return handle.read(16).startswith(b"SQLite format 3")

        try:
            looks_like_sqlite = await to_thread(_looks_like_sqlite, legacy_file)
        except Exception:
            logger.debug("Legacy path %s is not a readable SQLite file", legacy_file)
            return
        if not looks_like_sqlite:
            return

        logger.info("Migrating legacy jorb SQLite store from %s", legacy_file)

        def _migrate() -> list[dict[str, Any]]:
            conn = sqlite3.connect(legacy_file)
            conn.row_factory = sqlite3.Row
            try:
                jorbs_rows = conn.execute("SELECT * FROM jorbs").fetchall()
                message_rows = conn.execute("SELECT * FROM jorb_messages ORDER BY timestamp ASC").fetchall()
                checkpoint_rows = conn.execute("SELECT * FROM jorb_checkpoints ORDER BY timestamp ASC").fetchall()
            finally:
                conn.close()

            messages_by_jorb: dict[str, list[dict[str, Any]]] = {}
            for row in message_rows:
                payload = dict(row)
                messages_by_jorb.setdefault(str(payload["jorb_id"]), []).append(payload)

            checkpoints_by_jorb: dict[str, list[dict[str, Any]]] = {}
            for row in checkpoint_rows:
                payload = dict(row)
                checkpoints_by_jorb.setdefault(str(payload["jorb_id"]), []).append(payload)

            records: list[dict[str, Any]] = []
            for row in jorbs_rows:
                payload = dict(row)
                script_results = _parse_json_string(payload.get("script_results"), [])
                if not isinstance(script_results, list):
                    script_results = []
                jorb_payload = {
                    "id": payload["id"],
                    "name": payload["name"],
                    "status": payload["status"],
                    "original_plan": payload["original_plan"],
                    "contacts_json": payload.get("contacts_json") or "[]",
                    "personality": payload.get("personality") or "default",
                    "task_class": classify_task_class(payload.get("name"), payload.get("original_plan")),
                    "progress_summary": payload.get("progress_summary"),
                    "created_at": payload.get("created_at") or "",
                    "updated_at": payload.get("updated_at") or "",
                    "paused_reason": payload.get("paused_reason"),
                    "needs_approval_for": payload.get("needs_approval_for"),
                    "awaiting": payload.get("awaiting"),
                    "messages_in": payload.get("messages_in") or 0,
                    "messages_out": payload.get("messages_out") or 0,
                    "tokens_used": payload.get("tokens_used") or 0,
                    "estimated_cost": payload.get("estimated_cost") or 0.0,
                    "context_resets": payload.get("context_resets") or 0,
                    "outcome_result": payload.get("outcome_result"),
                    "outcome_completed_at": payload.get("outcome_completed_at"),
                    "outcome_failure_reason": payload.get("outcome_failure_reason"),
                    "script_results": script_results,
                    "metadata_json": payload.get("metadata_json") or "{}",
                    "wake_at": payload.get("wake_at"),
                }
                records.append(
                    {
                        "schema_version": STORE_SCHEMA_VERSION,
                        "jorb": jorb_payload,
                        "messages": messages_by_jorb.get(str(payload["id"]), []),
                        "checkpoints": checkpoints_by_jorb.get(str(payload["id"]), []),
                    }
                )
            return records

        records = await to_thread(_migrate)
        for record in records:
            jorb_id = str(record["jorb"]["id"])
            await self._write_record(jorb_id, record)
        logger.info("Migrated %d jorbs from legacy SQLite store", len(records))

    async def create_jorb(
        self,
        name: str,
        plan: str,
        contacts: list[JorbContact] | None = None,
        personality: str = "default",
        task_class: str | None = None,
    ) -> Jorb:
        """
        Create a new jorb.

        Args:
            name: Human-readable name for the jorb
            plan: The full plan text
            contacts: List of contacts involved in the jorb
            personality: Personality ID for this jorb's LLM sessions (default: "default")
            task_class: Optional structured task class override

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
            task_class=task_class or classify_task_class(name, plan),
            created_at=now,
            updated_at=now,
        )

        record = {
            "schema_version": STORE_SCHEMA_VERSION,
            "jorb": _jorb_to_payload(jorb),
            "messages": [],
            "checkpoints": [],
        }
        async with self._lock:
            await self._write_record(jorb_id, record)

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

        record = await self._read_record(jorb_id)
        if record is None:
            return None
        return _payload_to_jorb(record.get("jorb") or {})

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

        records = []
        for path in newest_first(self._data_dir.glob("jorb_*.json")):
            payload = await to_thread(read_json_file, path, None)
            if isinstance(payload, dict) and isinstance(payload.get("jorb"), dict):
                records.append(_payload_to_jorb(payload["jorb"]))

        if status_filter == "open":
            records = [j for j in records if j.status in ("planning", "running", "paused")]
        elif status_filter == "closed":
            records = [j for j in records if j.status in ("complete", "failed", "cancelled")]

        records.sort(key=lambda j: j.updated_at, reverse=True)
        return records

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
            "task_class",
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
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            record = await self._read_record(jorb_id)
            if record is None or not isinstance(record.get("jorb"), dict):
                return None
            jorb_payload = dict(record["jorb"])
            normalized_updates = dict(updates)
            if "script_results" in normalized_updates:
                parsed = _parse_json_string(normalized_updates["script_results"], normalized_updates["script_results"])
                normalized_updates["script_results"] = parsed if isinstance(parsed, list) else []
            if "contacts_json" in normalized_updates:
                raw_contacts = normalized_updates["contacts_json"]
                if isinstance(raw_contacts, list):
                    normalized_updates["contacts_json"] = json.dumps(raw_contacts)
            if "metadata_json" in normalized_updates:
                raw_meta = normalized_updates["metadata_json"]
                if isinstance(raw_meta, dict):
                    normalized_updates["metadata_json"] = json.dumps(raw_meta)

            jorb_payload.update(normalized_updates)
            record["jorb"] = jorb_payload
            record["schema_version"] = STORE_SCHEMA_VERSION
            await self._write_record(jorb_id, record)

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

        jorbs = await self.list_jorbs(status_filter="open")
        due = [
            j for j in jorbs
            if j.status == "running" and j.wake_at is not None and j.wake_at <= now_iso
        ]
        due.sort(key=lambda j: str(j.wake_at or ""))
        return due[:limit]

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

        async with self._lock:
            record = await self._read_record(jorb_id)
            if record is None:
                raise ValueError(f"Jorb not found: {jorb_id}")
            messages = list(record.get("messages") or [])
            messages.append(_message_to_payload(message))
            record["messages"] = messages
            await self._write_record(jorb_id, record)

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

        record = await self._read_record(jorb_id)
        if record is None:
            return []
        messages = [
            _payload_to_message(payload)
            for payload in list(record.get("messages") or [])
            if isinstance(payload, dict)
        ]
        messages.sort(key=lambda msg: msg.timestamp)
        return messages[:limit]

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

        checkpoint = JorbCheckpoint(
            id=checkpoint_id,
            jorb_id=jorb_id,
            timestamp=timestamp,
            summary=summary,
            token_count=token_count,
        )

        async with self._lock:
            record = await self._read_record(jorb_id)
            if record is None:
                raise ValueError(f"Jorb not found: {jorb_id}")
            checkpoints = list(record.get("checkpoints") or [])
            checkpoints.append(_checkpoint_to_payload(checkpoint))
            record["checkpoints"] = checkpoints
            await self._write_record(jorb_id, record)

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

        record = await self._read_record(jorb_id)
        if record is None:
            return []
        checkpoints = [
            _payload_to_checkpoint(payload)
            for payload in list(record.get("checkpoints") or [])
            if isinstance(payload, dict)
        ]
        checkpoints.sort(key=lambda ckpt: ckpt.timestamp)
        return checkpoints

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

        async with self._lock:
            record = await self._read_record(jorb_id)
            if record is None or not isinstance(record.get("jorb"), dict):
                return
            jorb_payload = dict(record["jorb"])
            jorb_payload["messages_in"] = int(jorb_payload.get("messages_in") or 0) + messages_in
            jorb_payload["messages_out"] = int(jorb_payload.get("messages_out") or 0) + messages_out
            jorb_payload["tokens_used"] = int(jorb_payload.get("tokens_used") or 0) + tokens_used
            jorb_payload["estimated_cost"] = float(jorb_payload.get("estimated_cost") or 0.0) + estimated_cost
            jorb_payload["context_resets"] = int(jorb_payload.get("context_resets") or 0) + context_resets
            jorb_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            record["jorb"] = jorb_payload
            await self._write_record(jorb_id, record)

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

        await self.update_jorb(
            jorb_id,
            outcome_result=result,
            outcome_completed_at=datetime.now(timezone.utc).isoformat(),
            outcome_failure_reason=failure_reason,
        )

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
        for jorb in await self.list_jorbs(status_filter="all"):
            for contact in jorb.contacts:
                if contact.identifier:
                    contacts.add(self._normalize_identifier(contact.identifier))

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

        content_lower = content.lower().strip()
        for jorb in await self.list_jorbs(status_filter="all"):
            for row in await self.get_messages(jorb.id, limit=5000):
                if row.direction != "outbound":
                    continue
                if row.timestamp < time_lower or row.timestamp > time_upper:
                    continue
                db_content = row.content.lower().strip() if row.content else ""
                if content_lower in db_content or db_content in content_lower:
                    logger.debug(
                        "Message matches frank_bot message (id=%s): %s...",
                        row.id,
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

        jorbs = await self.list_jorbs(status_filter=status_filter)
        by_status = {
            "planning": 0,
            "running": 0,
            "paused": 0,
            "complete": 0,
            "failed": 0,
            "cancelled": 0,
        }
        total_messages_in = 0
        total_messages_out = 0
        total_tokens = 0
        total_cost = 0.0
        total_context_resets = 0

        for jorb in jorbs:
            by_status[jorb.status] = by_status.get(jorb.status, 0) + 1
            total_messages_in += jorb.messages_in
            total_messages_out += jorb.messages_out
            total_tokens += jorb.tokens_used
            total_cost += jorb.estimated_cost
            total_context_resets += jorb.context_resets

        return {
            "total_jorbs": len(jorbs),
            "total_messages_in": total_messages_in,
            "total_messages_out": total_messages_out,
            "total_messages": total_messages_in + total_messages_out,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "total_context_resets": total_context_resets,
            "by_status": by_status,
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

        updated_results = list(jorb.script_results) + [result_dict]
        await self.update_jorb(jorb_id, script_results=updated_results)

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
