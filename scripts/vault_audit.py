#!/usr/bin/env python3
"""
Audit Concordia Vault secrets required by frank_bot.

This script verifies that Vault is configured (AppRole) and that the expected
KV v2 secret paths under `secret/frank-bot/*` exist with the required keys.

It intentionally DOES NOT print secret values.

Usage:
  poetry run python scripts/vault_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.vault_client import get_secret, vault_enabled  # noqa: E402


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _check_secret(
    path: str,
    *,
    required_keys: list[str],
    optional_keys: list[str] | None = None,
    key_aliases: dict[str, list[str]] | None = None,
) -> tuple[bool, list[str]]:
    """
    Check that a Vault secret exists and contains required keys.

    Args:
      path: KV path relative to mount (e.g., "frank-bot/openai")
      required_keys: keys that must exist and be non-empty
      optional_keys: keys that may exist (checked only for presence if provided)
      key_aliases: map of required_key -> acceptable alternative key names

    Returns:
      (ok, problems)
    """
    problems: list[str] = []
    data = get_secret(path)
    if data is None:
        return False, [f"missing secret: secret/{path}"]

    aliases = key_aliases or {}

    for key in required_keys:
        candidates = [key] + aliases.get(key, [])
        if not any(_is_present(data.get(k)) for k in candidates):
            problems.append(
                f"missing key: {path} ({' or '.join(candidates)})"
            )

    # Optional keys: if present but empty, call it out (helps catch half-config)
    for key in optional_keys or []:
        if key in data and not _is_present(data.get(key)):
            problems.append(f"empty optional key: {path} ({key})")

    return len(problems) == 0, problems


def main() -> int:
    if not vault_enabled():
        print("Vault is not configured (set VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID).")
        return 2

    checks = [
        ("frank-bot/stytch", ["project_id", "secret"]),
        ("frank-bot/telegram", ["api_id", "api_hash", "phone"]),
        ("frank-bot/telnyx", ["api_key", "phone_number"]),
        ("frank-bot/google", ["client_id", "client_secret"]),
        (
            "frank-bot/swarm",
            ["oauth_token", "api_key"],
        ),
        ("frank-bot/openai", ["api_key"]),
        ("frank-bot/email", ["smtp_host", "smtp_user", "smtp_password", "digest_email_to"]),
        ("frank-bot/actions", ["api_key"]),
        # Optional integrations
        ("frank-bot/telegram-bot", [],),
        ("frank-bot/claudia", ["api_url"],),
        ("frank-bot/android", [],),
    ]

    all_ok = True
    problems: list[str] = []

    for path, required in checks:
        key_aliases: dict[str, list[str]] | None = None
        if path == "frank-bot/swarm":
            # Older terraform wrote `foursquare_key`; newer uses `api_key`.
            key_aliases = {"api_key": ["foursquare_key"]}

        ok, errs = _check_secret(
            path,
            required_keys=required,
            key_aliases=key_aliases,
        )
        if ok:
            print(f"✅ {path}")
        else:
            all_ok = False
            print(f"❌ {path}")
            problems.extend(errs)

    if problems:
        print("\nProblems:")
        for p in problems:
            print(f"- {p}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

