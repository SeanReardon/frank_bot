"""
Unit tests for TelegramClientService.

Tests verify session path construction and service configuration.
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from services.telegram_client import _get_session_path, TelegramClientService


class TestGetSessionPath:
    """Tests for _get_session_path helper function."""

    def test_default_current_directory(self) -> None:
        """Uses current directory when DATA_DIR not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATA_DIR if present
            os.environ.pop("DATA_DIR", None)
            result = _get_session_path("frank_bot")
            assert result == os.path.join(".", "frank_bot")

    def test_uses_data_dir_when_set(self) -> None:
        """Uses DATA_DIR environment variable when set."""
        with patch.dict(os.environ, {"DATA_DIR": "/app/data"}):
            result = _get_session_path("frank_bot")
            assert result == "/app/data/frank_bot"

    def test_empty_data_dir_uses_default(self) -> None:
        """Empty DATA_DIR falls back to current directory."""
        with patch.dict(os.environ, {"DATA_DIR": ""}):
            result = _get_session_path("frank_bot")
            # Empty string is falsy so falls back to "."
            assert result == os.path.join(".", "frank_bot")

    def test_custom_session_name(self) -> None:
        """Works with custom session names."""
        with patch.dict(os.environ, {"DATA_DIR": "/var/lib/telegram"}):
            result = _get_session_path("my_custom_session")
            assert result == "/var/lib/telegram/my_custom_session"


class TestTelegramClientServiceSessionPath:
    """Tests for TelegramClientService session path handling."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.telegram_phone = "+15551234567"
        settings.telegram_session_name = "frank_bot"
        return settings

    def test_session_file_path_default(self, mock_settings: MagicMock) -> None:
        """Session file path uses current directory by default."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATA_DIR", None)
            with patch("services.telegram_client.get_settings", return_value=mock_settings):
                service = TelegramClientService()
                assert service.session_file_path == os.path.join(".", "frank_bot.session")

    def test_session_file_path_with_data_dir(self, mock_settings: MagicMock) -> None:
        """Session file path uses DATA_DIR when set."""
        with patch.dict(os.environ, {"DATA_DIR": "/app/data"}):
            with patch("services.telegram_client.get_settings", return_value=mock_settings):
                service = TelegramClientService()
                assert service.session_file_path == "/app/data/frank_bot.session"

    def test_is_configured_with_all_vars(self, mock_settings: MagicMock) -> None:
        """is_configured returns True when all vars are set."""
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            assert service.is_configured is True

    def test_is_configured_missing_api_id(self, mock_settings: MagicMock) -> None:
        """is_configured returns False when api_id is missing."""
        mock_settings.telegram_api_id = None
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            assert service.is_configured is False

    def test_is_configured_missing_api_hash(self, mock_settings: MagicMock) -> None:
        """is_configured returns False when api_hash is missing."""
        mock_settings.telegram_api_hash = None
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            assert service.is_configured is False

    def test_is_configured_missing_phone(self, mock_settings: MagicMock) -> None:
        """is_configured returns False when phone is missing."""
        mock_settings.telegram_phone = None
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            assert service.is_configured is False
