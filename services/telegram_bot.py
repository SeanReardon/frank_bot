"""
Telegram Bot Service for notification messages and getUpdates long-polling.

Uses the Telegram Bot API (via httpx) to send notifications and receive
incoming messages via long-polling. This is separate from the Telethon
user client (telegram_client.py).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import httpx

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)

TELEGRAM_BOT_API_BASE = "https://api.telegram.org"


@dataclass
class NotificationResult:
    """Result of a notification send operation."""

    success: bool
    message_id: int | None = None
    error: str | None = None


class TelegramBot:
    """
    Service for sending notifications via Telegram Bot API.

    Uses a bot token (not Telethon user auth) to send messages.
    """

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ):
        """
        Initialize the Telegram bot service.

        Args:
            token: Telegram bot token. If None, reads from settings.
            chat_id: Default chat ID to send to. If None, reads from settings.
        """
        settings = get_settings()
        self._token = token or settings.telegram_bot_token
        self._chat_id = chat_id or settings.telegram_bot_chat_id

    @property
    def is_configured(self) -> bool:
        """Check if the bot is configured."""
        return bool(self._token and self._chat_id)

    @property
    def chat_id(self) -> str | None:
        """Return the configured chat ID."""
        return self._chat_id

    async def send_notification(
        self,
        text: str,
        *,
        parse_mode: str = "HTML",
        chat_id: str | None = None,
    ) -> NotificationResult:
        """
        Send a notification message to Telegram.

        Args:
            text: The message text to send
            parse_mode: Message format (HTML, Markdown, or MarkdownV2)
            chat_id: Override chat ID (uses default if not specified)

        Returns:
            NotificationResult with success status
        """
        if not self._token:
            return NotificationResult(
                success=False,
                error="Telegram bot token not configured",
            )

        target_chat = chat_id or self._chat_id
        if not target_chat:
            return NotificationResult(
                success=False,
                error="Telegram bot chat_id not configured",
            )

        bot_stats = stats.get_service_stats("telegram_bot")
        start = time.time()

        try:
            url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/sendMessage"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": target_chat,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )

            elapsed_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    message_id = data.get("result", {}).get("message_id")
                    bot_stats.record_request(elapsed_ms, success=True)
                    logger.info(
                        "Telegram notification sent, message_id=%s",
                        message_id,
                    )
                    return NotificationResult(
                        success=True,
                        message_id=message_id,
                    )
                else:
                    error = data.get("description", "Unknown error")
                    bot_stats.record_request(elapsed_ms, success=False, error=error)
                    logger.error("Telegram API error: %s", error)
                    return NotificationResult(
                        success=False,
                        error=error,
                    )
            else:
                error = f"HTTP {response.status_code}: {response.text}"
                bot_stats.record_request(elapsed_ms, success=False, error=error)
                stats.record_error(
                    "telegram_bot",
                    error,
                    {"method": "send_notification"},
                )
                logger.error("Telegram API HTTP error: %s", error)
                return NotificationResult(
                    success=False,
                    error=error,
                )

        except httpx.TimeoutException as exc:
            elapsed_ms = (time.time() - start) * 1000
            error = f"Request timeout: {exc}"
            bot_stats.record_request(elapsed_ms, success=False, error=error)
            stats.record_error(
                "telegram_bot",
                error,
                {"method": "send_notification"},
            )
            logger.error("Telegram notification timeout: %s", exc)
            return NotificationResult(
                success=False,
                error=error,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error = str(exc)
            bot_stats.record_request(elapsed_ms, success=False, error=error)
            stats.record_error(
                "telegram_bot",
                error,
                {"method": "send_notification"},
            )
            logger.exception("Telegram notification failed: %s", exc)
            return NotificationResult(
                success=False,
                error=error,
            )

    async def notify_unknown_sms(
        self,
        from_number: str,
        message: str,
        attachment_count: int = 0,
    ) -> NotificationResult:
        """
        Send an alert about an SMS from an unknown sender.

        Args:
            from_number: The sender's phone number
            message: The message text (will be truncated at 500 chars)
            attachment_count: Number of MMS attachments

        Returns:
            NotificationResult with success status
        """
        # Truncate message preview
        preview = message[:500] + "..." if len(message) > 500 else message

        # Format notification
        parts = [
            "📱 <b>Unknown SMS Sender</b>",
            "",
            f"<b>From:</b> <code>{from_number}</code>",
            "",
            f"<b>Message:</b>\n{_escape_html(preview)}",
        ]

        if attachment_count > 0:
            parts.append("")
            parts.append(f"📎 <b>{attachment_count} attachment(s)</b>")

        text = "\n".join(parts)
        return await self.send_notification(text, parse_mode="HTML")

    async def notify_spam(
        self,
        from_number: str,
        message: str,
        reason: str,
    ) -> NotificationResult:
        """
        Send an alert about a spam SMS.

        Args:
            from_number: The sender's phone number
            message: The message text
            reason: Why it was classified as spam

        Returns:
            NotificationResult with success status
        """
        preview = message[:500] + "..." if len(message) > 500 else message

        text = "\n".join([
            "🚫 <b>Spam SMS Detected</b>",
            "",
            f"<b>From:</b> <code>{from_number}</code>",
            f"<b>Reason:</b> {_escape_html(reason)}",
            "",
            f"<b>Message:</b>\n{_escape_html(preview)}",
        ])

        return await self.send_notification(text, parse_mode="HTML")


class TelegramBotListener:
    """
    Long-polling listener for incoming Telegram Bot API messages.

    Uses getUpdates with long-polling to receive messages from the bot.
    Only processes messages from senders in the telegram_allowlist.
    """

    def __init__(
        self,
        on_message: Callable[
            [str, str, str, str],
            Coroutine[Any, Any, None],
        ],
        token: str | None = None,
    ):
        """
        Initialize the listener.

        Args:
            on_message: Async callback(text, username, chat_id, sender_name)
                        called for each valid incoming message.
            token: Bot token. If None, reads from settings.
        """
        settings = get_settings()
        self._token = token or settings.telegram_bot_token
        self._on_message = on_message
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._offset: int | None = None

    @property
    def is_configured(self) -> bool:
        """Check if the listener is configured."""
        return bool(self._token)

    @property
    def is_running(self) -> bool:
        """Check if the listener is currently polling."""
        return self._running

    async def start_polling(self) -> None:
        """Start the long-polling loop as an asyncio task."""
        if self._running:
            logger.debug("Bot listener already running")
            return

        if not self._token:
            logger.warning("Bot listener not configured (no token)")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot listener started polling")

    async def stop_polling(self) -> None:
        """Stop the long-polling loop."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        logger.info("Telegram bot listener stopped polling")

    async def _poll_loop(self) -> None:
        """Main polling loop — calls getUpdates in a loop."""
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._process_update(update)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Bot polling error: %s", exc)
                # Back off on errors to avoid tight loops
                await asyncio.sleep(5)

    async def _get_updates(self) -> list[dict[str, Any]]:
        """
        Call getUpdates with long-polling.

        Returns:
            List of update dicts from the Telegram API.
        """
        url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/getUpdates"
        params: dict[str, Any] = {"timeout": 3}
        if self._offset is not None:
            params["offset"] = self._offset

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

        if response.status_code != 200:
            logger.error("getUpdates HTTP %s: %s", response.status_code, response.text)
            return []

        data = response.json()
        if not data.get("ok"):
            logger.error("getUpdates API error: %s", data.get("description"))
            return []

        updates = data.get("result", [])
        if updates:
            # Advance offset past the highest update_id
            max_id = max(u["update_id"] for u in updates)
            self._offset = max_id + 1

        return updates

    async def _process_update(self, update: dict[str, Any]) -> None:
        """
        Process a single update from getUpdates.

        Extracts message text, sender username, and chat_id.
        Checks the sender against the telegram_allowlist.
        """
        message = update.get("message")
        if not message:
            return

        text = message.get("text")
        if not text:
            return

        sender = message.get("from", {})
        username = sender.get("username", "")
        first_name = sender.get("first_name", "")
        last_name = sender.get("last_name", "")
        sender_name = f"{first_name} {last_name}".strip() or username
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not chat_id:
            return

        # Check allowlist
        from services.telegram_allowlist import is_allowed_username

        if not is_allowed_username(username):
            logger.debug(
                "Dropping bot message from non-allowlisted user: %s",
                username,
            )
            return

        logger.info(
            "Bot message from %s (@%s) in chat %s: %s",
            sender_name,
            username,
            chat_id,
            text[:50],
        )

        try:
            await self._on_message(text, username, chat_id, sender_name)
        except Exception as exc:
            logger.error(
                "Error in bot message callback for @%s: %s", username, exc
            )


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


__all__ = ["TelegramBot", "TelegramBotListener", "NotificationResult"]
