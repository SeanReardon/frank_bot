"""
Shared utilities for action implementations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


def resolve_timezone(name: str) -> ZoneInfo:
    """Return a ZoneInfo instance, falling back to UTC when needed."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s'; falling back to UTC", name)
        return ZoneInfo("UTC")


def format_datetime(value: str) -> str:
    """Best-effort ISO8601 formatter for human readability."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO8601 datetimes while allowing trailing Z."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO8601 datetime: {value}") from exc


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def coerce_int(
    value: Any,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        converted = default
    if minimum is not None:
        converted = max(minimum, converted)
    if maximum is not None:
        converted = min(maximum, converted)
    return converted


def fuzzy_name_match(query: str, target: str, threshold: int = 73) -> bool:
    """
    Check if query fuzzy-matches target name using rapidfuzz.

    Uses multiple matching strategies to balance catching typos/nicknames
    while avoiding false positives like "ekaterina" matching "linda".
    """
    query = query.lower().strip()
    target = target.lower().strip()

    if not query or not target:
        return False

    # Exact substring match (fast path)
    if query in target or target in query:
        return True

    # Check each word in target separately (for "Lauren Reiter" etc.)
    target_words = target.split()

    for word in target_words:
        # Prefix match - "laur" matches "lauren"
        if word.startswith(query) or query.startswith(word):
            return True

        # Same first char + decent partial AND ratio = likely same name
        # This catches "mike" → "michael" (partial=67, ratio=55)
        # But rejects "lauren" → "lisa" (partial=67, ratio=40)
        if query[0] == word[0]:
            partial = fuzz.partial_ratio(query, word)
            ratio = fuzz.ratio(query, word)
            if partial >= 65 and ratio >= 50:
                return True

        # High-confidence standard ratio (catches typos like "jacksen" → "jackson")
        if fuzz.ratio(query, word) >= threshold:
            return True

    # For multi-word targets, also check overall similarity
    if len(target_words) > 1:
        if fuzz.ratio(query, target) >= threshold:
            return True

    return False
