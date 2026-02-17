"""
Telegram Bot Service for notification messages and getUpdates long-polling.

Uses the Telegram Bot API (via httpx) to send notifications and receive
incoming messages via long-polling. This is separate from the Telethon
user client (telegram_client.py).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
    # When a long message is chunked, all resulting message IDs are captured here.
    message_ids: list[int] | None = None
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
        parse_mode: str | None = "HTML",
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

            from services.telegram_text import TELEGRAM_MAX_TEXT_LEN, chunk_telegram_text

            chunked = chunk_telegram_text(
                text,
                max_len=TELEGRAM_MAX_TEXT_LEN,
                add_part_headers=True,
                max_chunks=50,
            )

            message_ids: list[int] = []
            async with httpx.AsyncClient(timeout=30.0) as client:
                for chunk in chunked.chunks:
                    payload: dict[str, Any] = {
                        "chat_id": target_chat,
                        "text": chunk,
                    }
                    # Telegram parse_mode is optional; omit when None to send plain text.
                    if parse_mode:
                        payload["parse_mode"] = parse_mode
                    response = await client.post(url, json=payload)

                    # Handle response per chunk; if any chunk fails, stop.
                    if response.status_code != 200:
                        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

                    data = response.json()
                    if not data.get("ok"):
                        raise RuntimeError(str(data.get("description", "Unknown error")))

                    msg_id = data.get("result", {}).get("message_id")
                    if isinstance(msg_id, int):
                        message_ids.append(msg_id)

            elapsed_ms = (time.time() - start) * 1000

            bot_stats.record_request(elapsed_ms, success=True)
            last_id = message_ids[-1] if message_ids else None
            logger.info("Telegram notification sent (%d parts), last_id=%s", len(message_ids), last_id)
            return NotificationResult(
                success=True,
                message_id=last_id,
                message_ids=message_ids or None,
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

    async def send_photo(
        self,
        photo_path: str,
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
        chat_id: str | None = None,
    ) -> NotificationResult:
        """
        Send a photo to Telegram via the Bot API.

        Used for Android screenshots and other binary artifacts that should not
        go through the LLM path.
        """
        if not self._token:
            return NotificationResult(success=False, error="Telegram bot token not configured")

        target_chat = chat_id or self._chat_id
        if not target_chat:
            return NotificationResult(success=False, error="Telegram bot chat_id not configured")

        if not photo_path or not os.path.exists(photo_path):
            return NotificationResult(success=False, error=f"Photo not found: {photo_path}")

        bot_stats = stats.get_service_stats("telegram_bot")
        start = time.time()

        # Telegram captions have a smaller limit than messages; keep it conservative.
        if caption and len(caption) > 900:
            caption = caption[:900] + "..."

        try:
            url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/sendPhoto"
            data: dict[str, Any] = {"chat_id": target_chat}
            if caption:
                data["caption"] = caption
            if parse_mode:
                data["parse_mode"] = parse_mode

            filename = os.path.basename(photo_path) or "photo.png"
            with open(photo_path, "rb") as f:
                files = {"photo": (filename, f, "image/png")}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, data=data, files=files)

            elapsed_ms = (time.time() - start) * 1000

            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}: {resp.text}"
                bot_stats.record_request(elapsed_ms, success=False, error=error)
                stats.record_error("telegram_bot", error, {"method": "send_photo"})
                return NotificationResult(success=False, error=error)

            payload = resp.json()
            if not payload.get("ok"):
                error = str(payload.get("description", "Unknown error"))
                bot_stats.record_request(elapsed_ms, success=False, error=error)
                stats.record_error("telegram_bot", error, {"method": "send_photo"})
                return NotificationResult(success=False, error=error)

            message_id = payload.get("result", {}).get("message_id")
            bot_stats.record_request(elapsed_ms, success=True)
            return NotificationResult(success=True, message_id=message_id if isinstance(message_id, int) else None)

        except httpx.TimeoutException as exc:
            elapsed_ms = (time.time() - start) * 1000
            error = f"Request timeout: {exc}"
            bot_stats.record_request(elapsed_ms, success=False, error=error)
            stats.record_error("telegram_bot", error, {"method": "send_photo"})
            return NotificationResult(success=False, error=error)
        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error = str(exc)
            bot_stats.record_request(elapsed_ms, success=False, error=error)
            stats.record_error("telegram_bot", error, {"method": "send_photo"})
            logger.exception("Telegram send_photo failed: %s", exc)
            return NotificationResult(success=False, error=error)

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
        # Diagnostics
        self._last_poll_at: str | None = None
        self._last_poll_error: str | None = None
        self._webhook_url: str | None = None
        self._last_update_at: str | None = None
        self._last_update_id: int | None = None
        self._last_update_username: str | None = None
        self._last_update_chat_id: str | None = None
        self._last_message_preview: str | None = None

    @property
    def is_configured(self) -> bool:
        """Check if the listener is configured."""
        return bool(self._token)

    @property
    def is_running(self) -> bool:
        """Check if the listener is currently polling."""
        return self._running

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status for monitoring endpoints."""
        return {
            "configured": self.is_configured,
            "running": self._running,
            "offset": self._offset,
            "webhook_url": self._webhook_url,
            "last_poll_at": self._last_poll_at,
            "last_poll_error": self._last_poll_error,
            "last_update_at": self._last_update_at,
            "last_update_id": self._last_update_id,
            "last_update_username": self._last_update_username,
            "last_update_chat_id": self._last_update_chat_id,
            "last_message_preview": self._last_message_preview,
        }

    async def start_polling(self) -> None:
        """Start the long-polling loop as an asyncio task."""
        if self._running:
            logger.debug("Bot listener already running")
            return

        if not self._token:
            logger.warning("Bot listener not configured (no token)")
            return

        # Best-effort: clear any configured webhook so polling works.
        # If a webhook is set, Telegram will not deliver updates via getUpdates.
        try:
            await self._ensure_polling_mode()
        except Exception as exc:
            # Don't block startup; keep status for diagnostics.
            self._last_poll_error = f"ensure_polling_mode_failed: {exc}"
            logger.warning("Failed to ensure Telegram polling mode: %s", exc)

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

    async def _ensure_polling_mode(self) -> None:
        """
        Ensure the bot is configured for getUpdates polling.

        Telegram bots can be configured for either webhooks or getUpdates.
        If a webhook URL is present, getUpdates will not work.
        """
        info = await self._get_webhook_info()
        url = str(info.get("url") or "").strip()
        self._webhook_url = url or None

        if url:
            logger.warning(
                "Telegram bot webhook is set (%s). Deleting webhook for polling.",
                url,
            )
            await self._delete_webhook(drop_pending_updates=False)
            info2 = await self._get_webhook_info()
            url2 = str(info2.get("url") or "").strip()
            self._webhook_url = url2 or None

    async def _get_webhook_info(self) -> dict[str, Any]:
        """Call Telegram getWebhookInfo and return the result object."""
        if not self._token:
            raise ValueError("Bot token not configured")

        url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/getWebhookInfo"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            raise RuntimeError(f"getWebhookInfo HTTP {resp.status_code}")

        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"getWebhookInfo error: {data.get('description')}")

        result = data.get("result") or {}
        return result if isinstance(result, dict) else {}

    async def _delete_webhook(self, *, drop_pending_updates: bool = False) -> None:
        """Call Telegram deleteWebhook."""
        if not self._token:
            raise ValueError("Bot token not configured")

        url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/deleteWebhook"
        params = {
            "drop_pending_updates": "true" if drop_pending_updates else "false",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, params=params)

        if resp.status_code != 200:
            raise RuntimeError(f"deleteWebhook HTTP {resp.status_code}")

        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"deleteWebhook error: {data.get('description')}")

    async def _get_updates(self) -> list[dict[str, Any]]:
        """
        Call getUpdates with long-polling.

        Returns:
            List of update dicts from the Telegram API.
        """
        self._last_poll_at = datetime.now(timezone.utc).isoformat()

        url = f"{TELEGRAM_BOT_API_BASE}/bot{self._token}/getUpdates"
        params: dict[str, Any] = {"timeout": 3}
        if self._offset is not None:
            params["offset"] = self._offset

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

        if response.status_code != 200:
            self._last_poll_error = f"http_{response.status_code}"
            logger.error("getUpdates HTTP %s: %s", response.status_code, response.text)
            return []

        data = response.json()
        if not data.get("ok"):
            desc = str(data.get("description") or "unknown_error")
            self._last_poll_error = desc
            logger.error("getUpdates API error: %s", desc)
            return []

        # Successful poll clears error
        self._last_poll_error = None

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
        update_id = update.get("update_id")
        try:
            if update_id is not None:
                self._last_update_id = int(update_id)
        except (TypeError, ValueError):
            pass

        message = update.get("message")
        if not message:
            return

        text = message.get("text")
        if not text:
            return

        self._last_update_at = datetime.now(timezone.utc).isoformat()

        sender = message.get("from", {})
        username = sender.get("username", "")
        first_name = sender.get("first_name", "")
        last_name = sender.get("last_name", "")
        sender_name = f"{first_name} {last_name}".strip() or username
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not chat_id:
            return

        self._last_update_username = username or None
        self._last_update_chat_id = chat_id

        preview = str(text).strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "..."
        self._last_message_preview = preview

        # Check allowlist
        from services.telegram_allowlist import is_allowed_username

        if not is_allowed_username(username):
            # Username can be empty (Telegram users without a public username).
            # For bot control-plane, allow the configured chat_id even if the
            # username isn't allowlisted.
            allowed_by_chat_id = False
            try:
                settings = get_settings()
                allowed_chat_id = str(settings.telegram_bot_chat_id or "").strip()
                allowed_by_chat_id = bool(allowed_chat_id and allowed_chat_id == chat_id)
            except Exception:
                allowed_by_chat_id = False

            if not allowed_by_chat_id:
                logger.info(
                    "Dropping bot message from non-allowlisted sender: @%s chat_id=%s",
                    username or "",
                    chat_id,
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
