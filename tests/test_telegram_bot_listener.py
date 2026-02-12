"""
Unit tests for TelegramBotListener in services/telegram_bot.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.telegram_bot import TelegramBotListener


class TestTelegramBotListenerInit:
    """Tests for TelegramBotListener initialization."""

    def test_init_with_token(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")
        assert listener.is_configured is True
        assert listener.is_running is False

    def test_init_without_token(self) -> None:
        callback = AsyncMock()
        with patch("services.telegram_bot.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                telegram_bot_token=None,
                telegram_bot_chat_id=None,
            )
            listener = TelegramBotListener(on_message=callback, token=None)
            assert listener.is_configured is False


class TestTelegramBotListenerStartStop:
    """Tests for start/stop polling."""

    @pytest.mark.asyncio
    async def test_start_polling_sets_running(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        with patch.object(listener, "_poll_loop", new_callable=AsyncMock):
            await listener.start_polling()
            assert listener.is_running is True
            assert listener._poll_task is not None
            await listener.stop_polling()

    @pytest.mark.asyncio
    async def test_stop_polling_clears_running(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        with patch.object(listener, "_poll_loop", new_callable=AsyncMock):
            await listener.start_polling()
            await listener.stop_polling()
            assert listener.is_running is False
            assert listener._poll_task is None

    @pytest.mark.asyncio
    async def test_start_polling_no_token(self) -> None:
        callback = AsyncMock()
        with patch("services.telegram_bot.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                telegram_bot_token=None,
                telegram_bot_chat_id=None,
            )
            listener = TelegramBotListener(on_message=callback, token=None)
            await listener.start_polling()
            assert listener.is_running is False


class TestTelegramBotListenerGetUpdates:
    """Tests for _get_updates()."""

    @pytest.mark.asyncio
    async def test_get_updates_success(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {"update_id": 100, "message": {"text": "hello", "from": {}, "chat": {"id": 123}}},
                {"update_id": 101, "message": {"text": "world", "from": {}, "chat": {"id": 123}}},
            ],
        }

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            updates = await listener._get_updates()
            assert len(updates) == 2
            # Offset should be max(update_id) + 1
            assert listener._offset == 102

    @pytest.mark.asyncio
    async def test_get_updates_with_offset(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")
        listener._offset = 50

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": []}

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            await listener._get_updates()
            # Verify offset was passed
            call_kwargs = mock_instance.get.call_args
            assert call_kwargs[1]["params"]["offset"] == 50

    @pytest.mark.asyncio
    async def test_get_updates_http_error(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("services.telegram_bot.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            updates = await listener._get_updates()
            assert updates == []


class TestTelegramBotListenerProcessUpdate:
    """Tests for _process_update()."""

    @pytest.mark.asyncio
    async def test_process_valid_update(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        update = {
            "update_id": 100,
            "message": {
                "text": "Hello bot!",
                "from": {
                    "username": "SeanReardon",
                    "first_name": "Sean",
                    "last_name": "Reardon",
                },
                "chat": {"id": 12345},
            },
        }

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=True,
        ):
            await listener._process_update(update)
            callback.assert_called_once_with(
                "Hello bot!", "SeanReardon", "12345", "Sean Reardon"
            )

    @pytest.mark.asyncio
    async def test_process_update_non_allowlisted_sender(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        update = {
            "update_id": 100,
            "message": {
                "text": "spam",
                "from": {"username": "spammer", "first_name": "Spam"},
                "chat": {"id": 999},
            },
        }

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=False,
        ):
            await listener._process_update(update)
            callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_update_no_message(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        await listener._process_update({"update_id": 100})
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_update_no_text(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        update = {
            "update_id": 100,
            "message": {
                "from": {"username": "SeanReardon"},
                "chat": {"id": 123},
            },
        }

        await listener._process_update(update)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_update_sender_name_fallback(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        update = {
            "update_id": 100,
            "message": {
                "text": "test",
                "from": {"username": "SeanReardon"},
                "chat": {"id": 123},
            },
        }

        with patch(
            "services.telegram_allowlist.is_allowed_username",
            return_value=True,
        ):
            await listener._process_update(update)
            # No first/last name — falls back to username
            callback.assert_called_once_with(
                "test", "SeanReardon", "123", "SeanReardon"
            )


class TestTelegramBotListenerPollLoop:
    """Tests for the polling loop."""

    @pytest.mark.asyncio
    async def test_poll_loop_processes_updates(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        call_count = 0

        async def fake_get_updates():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {
                        "update_id": 1,
                        "message": {
                            "text": "hi",
                            "from": {"username": "SeanReardon", "first_name": "Sean"},
                            "chat": {"id": 42},
                        },
                    }
                ]
            # Stop after first batch
            listener._running = False
            return []

        with patch.object(listener, "_get_updates", side_effect=fake_get_updates):
            with patch(
                "services.telegram_allowlist.is_allowed_username",
                return_value=True,
            ):
                listener._running = True
                await listener._poll_loop()

        callback.assert_called_once_with("hi", "SeanReardon", "42", "Sean")

    @pytest.mark.asyncio
    async def test_poll_loop_handles_errors(self) -> None:
        callback = AsyncMock()
        listener = TelegramBotListener(on_message=callback, token="test-token")

        call_count = 0

        async def failing_get_updates():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("network down")
            listener._running = False
            return []

        with patch.object(listener, "_get_updates", side_effect=failing_get_updates):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                listener._running = True
                await listener._poll_loop()

        # Should have recovered and continued
        assert call_count == 2
        callback.assert_not_called()
