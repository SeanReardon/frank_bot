"""
Telegram allowlist helpers.

Policy:
- Telegram is treated as a control-plane interface.
- Only specific usernames are allowed to participate in jorb processing.

Defaults:
  @SeanReardon

Override (dev only) via:
  TELEGRAM_ALLOWED_USERNAMES="@SeanReardon"
"""

from __future__ import annotations

import os


DEFAULT_ALLOWED_USERNAMES = ("@SeanReardon",)


def normalize_username(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.startswith("@"):
        raw = raw[1:]
    raw = raw.strip().lower()
    return raw or None


def get_allowed_usernames() -> set[str]:
    raw = os.getenv(
        "TELEGRAM_ALLOWED_USERNAMES",
        ",".join(DEFAULT_ALLOWED_USERNAMES),
    )
    values = [v.strip() for v in raw.split(",") if v.strip()]
    normalized = {normalize_username(v) for v in values}
    return {v for v in normalized if v}


def is_allowed_username(value: str | None) -> bool:
    norm = normalize_username(value)
    if not norm:
        return False
    return norm in get_allowed_usernames()


__all__ = [
    "DEFAULT_ALLOWED_USERNAMES",
    "normalize_username",
    "get_allowed_usernames",
    "is_allowed_username",
]
