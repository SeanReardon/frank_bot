"""
Audit logging for Android phone actions.

Provides JSON lines logging for Android phone automation actions with:
- Rotating daily log files (30 day retention)
- Structured JSON format for easy parsing
- Sensitive data sanitization (screenshots truncated)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default audit log location
DEFAULT_AUDIT_LOG_PATH = "./data/android_audit.log"

# How many days of logs to keep
AUDIT_LOG_RETENTION_DAYS = 30


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    result: str = "unknown"
    success: bool = True
    error: str | None = None
    tokens_used: int = 0
    duration_ms: int = 0
    api_key_prefix: str | None = None
    # Metadata only - actual content not logged
    screenshot_size_bytes: int | None = None
    element_count: int | None = None

    def to_json_line(self) -> str:
        """Convert to JSON line format."""
        data = asdict(self)
        # Remove None values for cleaner output
        data = {k: v for k, v in data.items() if v is not None}
        return json.dumps(data, default=str)


class AndroidAuditLogger:
    """
    Audit logger for Android phone actions.

    Uses rotating daily log files with JSON lines format.
    """

    def __init__(self, log_path: str | None = None):
        """
        Initialize the audit logger.

        Args:
            log_path: Path to the audit log file. Defaults to ./data/android_audit.log
        """
        self._log_path = log_path or DEFAULT_AUDIT_LOG_PATH
        self._file_handler: TimedRotatingFileHandler | None = None
        self._audit_logger: logging.Logger | None = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialization of the file handler."""
        if self._initialized:
            return

        # Ensure data directory exists
        log_dir = Path(self._log_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create a separate logger for audit entries
        self._audit_logger = logging.getLogger("android_audit")
        self._audit_logger.setLevel(logging.INFO)
        self._audit_logger.propagate = False  # Don't propagate to root logger

        # Rotating file handler - daily rotation, keep 30 days
        self._file_handler = TimedRotatingFileHandler(
            self._log_path,
            when="midnight",
            interval=1,
            backupCount=AUDIT_LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        # Custom suffix for rotated files
        self._file_handler.suffix = "%Y-%m-%d"

        # No formatter - we output raw JSON lines
        self._file_handler.setFormatter(logging.Formatter("%(message)s"))
        self._audit_logger.addHandler(self._file_handler)

        self._initialized = True

    def log_action(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        success: bool = True,
        error: str | None = None,
        tokens_used: int = 0,
        duration_ms: int = 0,
        api_key: str | None = None,
    ) -> None:
        """
        Log an Android phone action.

        Args:
            action: The action name (e.g., "thermostat_set_range")
            parameters: Input parameters (sanitized before logging)
            result: Action result (sanitized before logging)
            success: Whether the action succeeded
            error: Error message if action failed
            tokens_used: LLM tokens consumed
            duration_ms: Action duration in milliseconds
            api_key: API key used (only first 8 chars logged)
        """
        self._ensure_initialized()

        # Sanitize parameters - remove any sensitive data
        safe_params = self._sanitize_params(parameters or {})

        # Extract metadata from result
        screenshot_size = None
        element_count = None
        if result:
            if "screenshot_base64" in result:
                # Log only the size, not the actual data
                screenshot_size = len(result.get("screenshot_base64", ""))
            element_count = result.get("element_count")

        # Create audit entry
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat() + "Z",
            action=action,
            parameters=safe_params,
            result="success" if success else "failure",
            success=success,
            error=error,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            api_key_prefix=api_key[:8] + "..." if api_key and len(api_key) > 8 else api_key,
            screenshot_size_bytes=screenshot_size,
            element_count=element_count,
        )

        # Write to log
        if self._audit_logger:
            self._audit_logger.info(entry.to_json_line())

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize parameters for logging.

        Removes or truncates sensitive data like screenshots.
        """
        safe = {}
        for key, value in params.items():
            if key in ("screenshot", "screenshot_base64", "xml"):
                # Don't log full screenshots or XML
                if isinstance(value, str):
                    safe[key] = f"<{len(value)} chars>"
                else:
                    safe[key] = "<binary data>"
            elif key in ("api_key", "password", "secret"):
                # Never log credentials
                safe[key] = "<redacted>"
            else:
                safe[key] = value
        return safe

    def get_recent_entries(
        self,
        limit: int = 100,
        action_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get recent audit log entries.

        Args:
            limit: Maximum number of entries to return
            action_filter: Optional filter by action name

        Returns:
            List of audit entries (most recent first)
        """
        entries: list[dict[str, Any]] = []

        if not os.path.exists(self._log_path):
            return entries

        try:
            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Parse from the end (most recent)
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)

                    # Apply filter if specified
                    if action_filter and entry.get("action") != action_filter:
                        continue

                    entries.append(entry)

                    if len(entries) >= limit:
                        break

                except json.JSONDecodeError:
                    # Skip malformed entries
                    continue

        except IOError as e:
            logger.warning("Failed to read audit log: %s", e)

        return entries

    def get_stats(self) -> dict[str, Any]:
        """
        Get aggregate stats from the audit log.

        Returns:
            Dict with action counts, total tokens, error counts, etc.
        """
        stats: dict[str, Any] = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "total_tokens_used": 0,
            "actions_by_type": {},
        }

        if not os.path.exists(self._log_path):
            return stats

        try:
            with open(self._log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        stats["total_actions"] += 1

                        if entry.get("success", True):
                            stats["successful_actions"] += 1
                        else:
                            stats["failed_actions"] += 1

                        stats["total_tokens_used"] += entry.get("tokens_used", 0)

                        action = entry.get("action", "unknown")
                        if action not in stats["actions_by_type"]:
                            stats["actions_by_type"][action] = 0
                        stats["actions_by_type"][action] += 1

                    except json.JSONDecodeError:
                        continue

        except IOError as e:
            logger.warning("Failed to read audit log for stats: %s", e)

        return stats


# Module-level singleton
_audit_logger: AndroidAuditLogger | None = None


def get_android_audit_logger() -> AndroidAuditLogger:
    """Get the global Android audit logger instance."""
    global _audit_logger

    if _audit_logger is None:
        from config import get_settings

        # Could make the path configurable via settings
        _audit_logger = AndroidAuditLogger()

    return _audit_logger


def reset_audit_logger() -> None:
    """Reset the audit logger (for testing)."""
    global _audit_logger
    _audit_logger = None
