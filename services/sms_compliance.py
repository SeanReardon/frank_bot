"""
SMS Compliance Service for handling STOP/HELP/START keywords.

Manages opt-outs.json file tracking phone numbers that have opted out of messages.
Handles regulatory compliance keywords (STOP, HELP, START, etc.) for unknown contacts.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ComplianceKeyword(Enum):
    """Standard SMS compliance keywords."""

    STOP = "stop"  # Opt-out keywords
    STOPALL = "stopall"
    UNSUBSCRIBE = "unsubscribe"
    CANCEL = "cancel"
    END = "end"
    QUIT = "quit"

    HELP = "help"  # Help keywords
    INFO = "info"

    START = "start"  # Opt-in keywords
    YES = "yes"
    OPTIN = "optin"
    SUBSCRIBE = "subscribe"
    UNSTOP = "unstop"


# Keyword groups
OPT_OUT_KEYWORDS = {
    ComplianceKeyword.STOP,
    ComplianceKeyword.STOPALL,
    ComplianceKeyword.UNSUBSCRIBE,
    ComplianceKeyword.CANCEL,
    ComplianceKeyword.END,
    ComplianceKeyword.QUIT,
}

HELP_KEYWORDS = {
    ComplianceKeyword.HELP,
    ComplianceKeyword.INFO,
}

OPT_IN_KEYWORDS = {
    ComplianceKeyword.START,
    ComplianceKeyword.YES,
    ComplianceKeyword.OPTIN,
    ComplianceKeyword.SUBSCRIBE,
    ComplianceKeyword.UNSTOP,
}


def detect_compliance_keyword(message: str) -> ComplianceKeyword | None:
    """
    Detect if a message is a compliance keyword.

    Args:
        message: The message text to check

    Returns:
        ComplianceKeyword if detected, None otherwise
    """
    if not message:
        return None

    # Normalize message: strip whitespace and convert to lowercase
    normalized = message.strip().lower()

    # Try to match against all keywords
    for keyword in ComplianceKeyword:
        if normalized == keyword.value:
            return keyword

    return None


def get_keyword_type(keyword: ComplianceKeyword) -> str:
    """
    Get the type of compliance keyword.

    Returns:
        "opt_out", "help", or "opt_in"
    """
    if keyword in OPT_OUT_KEYWORDS:
        return "opt_out"
    elif keyword in HELP_KEYWORDS:
        return "help"
    elif keyword in OPT_IN_KEYWORDS:
        return "opt_in"
    return "unknown"


class SMSComplianceService:
    """
    Service for managing SMS compliance (opt-outs, help, start).

    Stores opt-out status in ./data/opt_outs.json file.
    """

    def __init__(self, data_dir: str | None = None):
        """
        Initialize the compliance service.

        Args:
            data_dir: Base data directory. Defaults to DATA_DIR env var or ./data
        """
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._opt_outs_file = self._data_dir / "opt_outs.json"
        self._opt_outs: dict[str, dict] | None = None

    def _ensure_dir(self) -> None:
        """Create data directory if it doesn't exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _load_opt_outs(self) -> dict[str, dict]:
        """
        Load opt-outs from file.

        Returns:
            Dict mapping phone numbers to opt-out info
        """
        if self._opt_outs is not None:
            return self._opt_outs

        if self._opt_outs_file.exists():
            try:
                with open(self._opt_outs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._opt_outs = data.get("opt_outs", {})
                    return self._opt_outs
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load opt_outs.json: %s", exc)
                self._opt_outs = {}
                return self._opt_outs

        self._opt_outs = {}
        return self._opt_outs

    def _save_opt_outs(self) -> None:
        """Save opt-outs to file."""
        self._ensure_dir()
        data = {
            "opt_outs": self._opt_outs or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._opt_outs_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved opt_outs.json with %d entries", len(self._opt_outs or {}))

    def is_opted_out(self, phone_number: str) -> bool:
        """
        Check if a phone number has opted out.

        Args:
            phone_number: The phone number to check (E.164 format preferred)

        Returns:
            True if opted out, False otherwise
        """
        opt_outs = self._load_opt_outs()
        return phone_number in opt_outs

    def record_opt_out(self, phone_number: str) -> None:
        """
        Record a phone number opting out.

        Args:
            phone_number: The phone number that opted out (E.164 format)
        """
        opt_outs = self._load_opt_outs()
        opt_outs[phone_number] = {
            "opted_out_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_opt_outs()
        logger.info("Recorded opt-out for %s", phone_number)

    def record_opt_in(self, phone_number: str) -> bool:
        """
        Record a phone number opting back in (removes from opt-out list).

        Args:
            phone_number: The phone number that opted in (E.164 format)

        Returns:
            True if the number was previously opted out, False otherwise
        """
        opt_outs = self._load_opt_outs()
        was_opted_out = phone_number in opt_outs
        if was_opted_out:
            del opt_outs[phone_number]
            self._save_opt_outs()
            logger.info("Recorded opt-in for %s (removed from opt-out list)", phone_number)
        return was_opted_out

    def get_opt_out_count(self) -> int:
        """Get the total number of opted-out phone numbers."""
        return len(self._load_opt_outs())


# Response messages for compliance keywords
STOP_RESPONSE = (
    "You have been unsubscribed and will no longer receive messages. "
    "Reply START to re-subscribe."
)

HELP_RESPONSE = (
    "This is Frank Bot, a personal assistant. "
    "Reply STOP to unsubscribe. "
    "For assistance, contact the owner directly."
)

OPT_IN_RESPONSE = (
    "You have been re-subscribed and may now receive messages. "
    "Reply STOP to unsubscribe."
)


__all__ = [
    "SMSComplianceService",
    "ComplianceKeyword",
    "detect_compliance_keyword",
    "get_keyword_type",
    "OPT_OUT_KEYWORDS",
    "HELP_KEYWORDS",
    "OPT_IN_KEYWORDS",
    "STOP_RESPONSE",
    "HELP_RESPONSE",
    "OPT_IN_RESPONSE",
]
