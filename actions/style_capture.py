"""
Style capture actions: generate and send SEAN.md documentation via Telegram.

This module provides actions for analyzing Sean's communication style from
Telegram message history and generating a style guide document.
"""

from __future__ import annotations

import logging
from typing import Any

from services.style_analyzer import StyleAnalyzer
from services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)

# Telegram message limit (4096 characters)
TELEGRAM_MESSAGE_LIMIT = 4096

# Default chat to analyze
DEFAULT_CHAT_ID = "@MagicConciergeBot"

# Default recipient for the generated SEAN.md
DEFAULT_RECIPIENT = "@SeanReardon"


def _split_message(content: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """
    Split content into chunks that fit within Telegram's message limit.

    Tries to split at paragraph boundaries for better readability.

    Args:
        content: The full content to split.
        limit: Maximum characters per message.

    Returns:
        List of message chunks.
    """
    if len(content) <= limit:
        return [content]

    chunks = []
    current_chunk = ""

    # Split by paragraphs first (double newlines)
    paragraphs = content.split("\n\n")

    for para in paragraphs:
        # If adding this paragraph would exceed limit
        if len(current_chunk) + len(para) + 2 > limit:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # If single paragraph is too long, split by lines
            if len(para) > limit:
                lines = para.split("\n")
                for line in lines:
                    if len(current_chunk) + len(line) + 1 > limit:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""

                        # If single line is too long, hard split
                        if len(line) > limit:
                            while len(line) > limit:
                                chunks.append(line[:limit])
                                line = line[limit:]
                            if line:
                                current_chunk = line
                        else:
                            current_chunk = line
                    else:
                        if current_chunk:
                            current_chunk += "\n" + line
                        else:
                            current_chunk = line
            else:
                current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


async def generate_sean_md_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generate SEAN.md from message analysis and send via Telegram.

    This action fetches Sean's message history from the Magic conversation,
    analyzes communication patterns, generates the SEAN.md style guide,
    and sends it to the specified recipient via Telegram.

    Args (in arguments dict):
        chat_id: Chat to fetch messages from (default: @MagicConciergeBot).
        recipient: Telegram user to send the result to (default: @SeanReardon).
        before_date: Only analyze messages before this date (ISO 8601, default: 2026-01-01).
        dry_run: If true, generate but don't send (default: false).

    Returns:
        Dict with success status, message count, and content preview.
    """
    args = arguments or {}
    chat_id = (args.get("chat_id") or DEFAULT_CHAT_ID).strip()
    recipient = (args.get("recipient") or DEFAULT_RECIPIENT).strip()
    before_date_str = args.get("before_date")
    dry_run = str(args.get("dry_run", "")).lower() in ("true", "1", "yes")

    # Parse before_date if provided
    before_date = None
    if before_date_str:
        from datetime import datetime, timezone

        try:
            # Try parsing ISO format
            before_date = datetime.fromisoformat(before_date_str.replace("Z", "+00:00"))
        except ValueError:
            # Try parsing date only
            try:
                before_date = datetime.strptime(before_date_str, "%Y-%m-%d")
                before_date = before_date.replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(
                    f"Invalid before_date format: {before_date_str}. "
                    "Use ISO 8601 format (e.g., 2026-01-01 or 2026-01-01T00:00:00Z)."
                )

    telegram = TelegramClientService()

    if not telegram.is_configured:
        raise ValueError(
            "Telegram is not configured. "
            "Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE."
        )

    # Step 1: Initialize style analyzer and fetch messages
    logger.info("Fetching messages from %s for style analysis", chat_id)
    analyzer = StyleAnalyzer(telegram_service=telegram)

    messages = await analyzer.fetch_authentic_messages(
        chat_id=chat_id,
        before_date=before_date,
    )

    if not messages:
        raise ValueError(
            f"No outgoing messages found in {chat_id}. "
            "Make sure the chat exists and has outgoing messages."
        )

    logger.info("Analyzing %d messages", len(messages))

    # Step 2: Analyze patterns
    analysis_result = analyzer.analyze_patterns(messages)

    # Step 3: Generate SEAN.md content
    sean_md_content = analyzer.generate_sean_md(analysis_result)

    logger.info(
        "Generated SEAN.md: %d characters, %d messages analyzed",
        len(sean_md_content),
        analysis_result.total_messages_analyzed,
    )

    # Step 4: Send via Telegram (unless dry run)
    message_count = 0
    if not dry_run:
        # Split content if it exceeds Telegram's limit
        chunks = _split_message(sean_md_content)
        message_count = len(chunks)

        logger.info(
            "Sending SEAN.md to %s in %d message(s)",
            recipient,
            message_count,
        )

        for i, chunk in enumerate(chunks, 1):
            # Add part indicator if multiple chunks
            if message_count > 1:
                prefix = f"[SEAN.md Part {i}/{message_count}]\n\n"
                chunk = prefix + chunk

            result = await telegram.send_message(recipient, chunk)

            if not result.success:
                raise ValueError(
                    f"Failed to send message {i}/{message_count}: {result.error}"
                )

            logger.debug("Sent part %d/%d to %s", i, message_count, recipient)

    # Return result
    return {
        "success": True,
        "messages_analyzed": analysis_result.total_messages_analyzed,
        "date_range": {
            "start": analysis_result.date_range_start,
            "end": analysis_result.date_range_end,
        },
        "content_length": len(sean_md_content),
        "message_count": message_count,
        "recipient": recipient if not dry_run else None,
        "dry_run": dry_run,
        "preview": sean_md_content[:500] + "..." if len(sean_md_content) > 500 else sean_md_content,
        "patterns_found": {
            cat.name: len(cat.patterns)
            for cat in analysis_result.all_categories()
        },
    }


__all__ = [
    "generate_sean_md_action",
]
