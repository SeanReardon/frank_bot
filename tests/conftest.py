"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest


# Disable switchboard mode by default for tests that expect legacy behavior
# Individual tests can re-enable it if needed
@pytest.fixture(autouse=True)
def disable_switchboard_mode(monkeypatch):
    """Disable switchboard mode for tests to use legacy single-stage behavior."""
    monkeypatch.setenv("USE_SWITCHBOARD_MODE", "false")


# Mock telethon if not installed to allow tests to run
if "telethon" not in sys.modules:
    # Create mock telethon module
    telethon_mock = MagicMock()
    telethon_mock.TelegramClient = MagicMock()
    telethon_mock.errors = MagicMock()
    telethon_mock.errors.FloodWaitError = Exception
    telethon_mock.errors.UserNotMutualContactError = Exception
    telethon_mock.tl = MagicMock()
    telethon_mock.tl.types = MagicMock()
    telethon_mock.tl.types.Channel = type("Channel", (), {})
    telethon_mock.tl.types.Chat = type("Chat", (), {})
    telethon_mock.tl.types.User = type("User", (), {})

    sys.modules["telethon"] = telethon_mock
    sys.modules["telethon.errors"] = telethon_mock.errors
    sys.modules["telethon.tl"] = telethon_mock.tl
    sys.modules["telethon.tl.types"] = telethon_mock.tl.types
