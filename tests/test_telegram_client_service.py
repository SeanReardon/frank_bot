"""
Unit tests for TelegramClientService.

Tests verify session path construction and service configuration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

import base64
import tempfile

from services.telegram_client import _get_session_path, TelegramClientService, TelegramMessage
from telethon.tl.types import User

# Minimal 1x1 PNG for test fixtures
_MOCK_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


class TestGetAllMessages:
    """Tests for get_all_messages method."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.telegram_phone = "+15551234567"
        settings.telegram_session_name = "frank_bot"
        return settings

    @pytest.fixture
    def mock_user(self) -> MagicMock:
        """Create mock Telegram User."""
        user = MagicMock(spec=User)
        user.id = 123456
        user.first_name = "Test"
        user.last_name = "User"
        user.contact = True
        user.mutual_contact = True
        return user

    @pytest.fixture
    def sample_messages(self, mock_user: MagicMock) -> list[MagicMock]:
        """Create sample Telegram messages."""
        messages = []
        for i, (is_out, text) in enumerate([
            (True, "Hey, how's it going?"),
            (False, "Good thanks! You?"),
            (True, "All good here"),
            (False, "Great to hear"),
            (True, "Yep"),
        ]):
            msg = MagicMock()
            msg.id = i + 1
            msg.text = text
            msg.date = datetime(2025, 12, 15, 10, i, 0, tzinfo=timezone.utc)
            msg.out = is_out
            msg.sender = mock_user
            messages.append(msg)
        return messages

    @pytest.mark.asyncio
    async def test_get_all_messages_returns_all(
        self, mock_settings: MagicMock, sample_messages: list[MagicMock]
    ) -> None:
        """get_all_messages returns all messages when direction_filter is 'all'."""
        async def mock_iter_messages(*args, **kwargs):
            for msg in sample_messages:
                yield msg

        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            mock_client = AsyncMock()
            mock_client.iter_messages = mock_iter_messages

            with patch.object(service, "_ensure_connected", return_value=mock_client):
                result = await service.get_all_messages("@testuser")

        assert len(result) == 5
        assert all(isinstance(m, TelegramMessage) for m in result)

    @pytest.mark.asyncio
    async def test_get_all_messages_outgoing_filter(
        self, mock_settings: MagicMock, sample_messages: list[MagicMock]
    ) -> None:
        """get_all_messages with direction_filter='outgoing' returns only outgoing."""
        async def mock_iter_messages(*args, **kwargs):
            for msg in sample_messages:
                yield msg

        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            mock_client = AsyncMock()
            mock_client.iter_messages = mock_iter_messages

            with patch.object(service, "_ensure_connected", return_value=mock_client):
                result = await service.get_all_messages(
                    "@testuser", direction_filter="outgoing"
                )

        assert len(result) == 3
        assert all(m.is_outgoing for m in result)
        assert [m.text for m in result] == [
            "Hey, how's it going?",
            "All good here",
            "Yep",
        ]

    @pytest.mark.asyncio
    async def test_get_all_messages_incoming_filter(
        self, mock_settings: MagicMock, sample_messages: list[MagicMock]
    ) -> None:
        """get_all_messages with direction_filter='incoming' returns only incoming."""
        async def mock_iter_messages(*args, **kwargs):
            for msg in sample_messages:
                yield msg

        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            mock_client = AsyncMock()
            mock_client.iter_messages = mock_iter_messages

            with patch.object(service, "_ensure_connected", return_value=mock_client):
                result = await service.get_all_messages(
                    "@testuser", direction_filter="incoming"
                )

        assert len(result) == 2
        assert all(not m.is_outgoing for m in result)

    @pytest.mark.asyncio
    async def test_get_all_messages_before_date(
        self, mock_settings: MagicMock, sample_messages: list[MagicMock]
    ) -> None:
        """get_all_messages passes before_date to iter_messages as offset_date."""
        before_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        captured_kwargs = {}

        async def mock_iter_messages(*args, **kwargs):
            captured_kwargs.update(kwargs)
            for msg in sample_messages:
                yield msg

        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            mock_client = AsyncMock()
            mock_client.iter_messages = mock_iter_messages

            with patch.object(service, "_ensure_connected", return_value=mock_client):
                await service.get_all_messages("@testuser", before_date=before_date)

        assert captured_kwargs.get("offset_date") == before_date

    @pytest.mark.asyncio
    async def test_get_all_messages_extracts_metadata(
        self, mock_settings: MagicMock, mock_user: MagicMock
    ) -> None:
        """get_all_messages extracts full metadata from messages."""
        msg = MagicMock()
        msg.id = 42
        msg.text = "Test message"
        msg.date = datetime(2025, 12, 15, 10, 30, 0, tzinfo=timezone.utc)
        msg.out = True
        msg.sender = mock_user

        async def mock_iter_messages(*args, **kwargs):
            yield msg

        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()
            mock_client = AsyncMock()
            mock_client.iter_messages = mock_iter_messages

            with patch.object(service, "_ensure_connected", return_value=mock_client):
                result = await service.get_all_messages("@testuser")

        assert len(result) == 1
        m = result[0]
        assert m.id == 42
        assert m.text == "Test message"
        assert m.sender_id == 123456
        assert m.sender_name == "Test User"
        assert m.is_outgoing is True
        assert m.is_contact is True
        assert m.is_mutual_contact is True


class TestSendPhoto:
    """Tests for TelegramClientService.send_photo()."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        settings = MagicMock()
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.telegram_phone = "+15551234567"
        settings.telegram_session_name = "frank_bot"
        return settings

    @pytest.mark.asyncio
    async def test_send_photo_calls_send_file(self, mock_settings: MagicMock) -> None:
        """send_photo calls client.send_file with correct arguments."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="/tmp") as f:
            f.write(_MOCK_PNG_BYTES)
            photo_file = f.name

        try:
            mock_message = MagicMock()
            mock_message.id = 42

            mock_client = AsyncMock()
            mock_client.send_file = AsyncMock(return_value=mock_message)

            with patch("services.telegram_client.get_settings", return_value=mock_settings):
                service = TelegramClientService()
                # Override allowed prefixes for test
                service._PHOTO_ALLOWED_PREFIXES = ["/tmp/"]

                with patch.object(service, "_ensure_connected", return_value=mock_client):
                    result = await service.send_photo(
                        recipient="@sean",
                        photo_path=photo_file,
                        caption="Test caption",
                    )

            assert result.success is True
            assert result.message_id == 42
            mock_client.send_file.assert_called_once()
            call_kwargs = mock_client.send_file.call_args
            assert call_kwargs[0][0] == "@sean"
            assert call_kwargs[1]["caption"] == "Test caption"
        finally:
            os.unlink(photo_file)

    @pytest.mark.asyncio
    async def test_send_photo_flood_wait_handling(self, mock_settings: MagicMock) -> None:
        """send_photo handles FloodWaitError gracefully."""
        from telethon.errors import FloodWaitError

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="/tmp") as f:
            f.write(_MOCK_PNG_BYTES)
            photo_file = f.name

        try:
            mock_client = AsyncMock()
            exc = FloodWaitError("flood wait")
            exc.seconds = 30
            mock_client.send_file = AsyncMock(side_effect=exc)

            with patch("services.telegram_client.get_settings", return_value=mock_settings):
                service = TelegramClientService()
                service._PHOTO_ALLOWED_PREFIXES = ["/tmp/"]

                with patch.object(service, "_ensure_connected", return_value=mock_client):
                    result = await service.send_photo(
                        recipient="@sean",
                        photo_path=photo_file,
                    )

            assert result.success is False
            assert "Rate limited" in result.error
        finally:
            os.unlink(photo_file)

    @pytest.mark.asyncio
    async def test_send_photo_caption_passthrough(self, mock_settings: MagicMock) -> None:
        """Caption is passed through to send_file."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="/tmp") as f:
            f.write(_MOCK_PNG_BYTES)
            photo_file = f.name

        try:
            mock_message = MagicMock()
            mock_message.id = 99
            mock_client = AsyncMock()
            mock_client.send_file = AsyncMock(return_value=mock_message)

            with patch("services.telegram_client.get_settings", return_value=mock_settings):
                service = TelegramClientService()
                service._PHOTO_ALLOWED_PREFIXES = ["/tmp/"]

                with patch.object(service, "_ensure_connected", return_value=mock_client):
                    result = await service.send_photo(
                        recipient="@sean",
                        photo_path=photo_file,
                        caption="My caption here",
                    )

            assert result.success is True
            call_kwargs = mock_client.send_file.call_args
            assert call_kwargs[1]["caption"] == "My caption here"
        finally:
            os.unlink(photo_file)

    @pytest.mark.asyncio
    async def test_send_photo_rejects_disallowed_paths(self, mock_settings: MagicMock) -> None:
        """send_photo rejects paths outside the allowlist."""
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()

            result = await service.send_photo(
                recipient="@sean",
                photo_path="/etc/passwd",
            )

        assert result.success is False
        assert "not in allowed directories" in result.error

    @pytest.mark.asyncio
    async def test_send_photo_rejects_traversal(self, mock_settings: MagicMock) -> None:
        """send_photo rejects path traversal attacks."""
        with patch("services.telegram_client.get_settings", return_value=mock_settings):
            service = TelegramClientService()

            result = await service.send_photo(
                recipient="@sean",
                photo_path="./data/screenshots/../../etc/passwd",
            )

        assert result.success is False
        assert "not in allowed directories" in result.error
