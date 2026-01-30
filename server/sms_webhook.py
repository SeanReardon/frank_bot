"""
SMS Webhook Handler for inbound Telnyx messages.

Handles POST /webhook/sms from Telnyx when SMS/MMS messages arrive.
Includes compliance keyword handling for unknown contacts (STOP/HELP/START).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from services.contact_lookup import ContactLookup
from services.sms_compliance import (
    HELP_RESPONSE,
    OPT_IN_RESPONSE,
    STOP_RESPONSE,
    SMSComplianceService,
    detect_compliance_keyword,
    get_keyword_type,
)
from services.sms_storage import (
    Attachment,
    Contact,
    SMSMessage,
    SMSStorage,
)
from services.telegram_bot import TelegramBot
from services.telnyx_sms import TelnyxSMSService

logger = logging.getLogger(__name__)


async def _send_unknown_sender_notification(
    from_number: str,
    message: str,
    attachment_count: int,
) -> bool:
    """
    Send a Telegram notification about an unknown SMS sender.

    Failures are logged but do not fail the webhook processing.

    Args:
        from_number: The sender's phone number
        message: The message content
        attachment_count: Number of attachments

    Returns:
        True if notification was sent successfully, False otherwise
    """
    telegram_bot = TelegramBot()

    if not telegram_bot.is_configured:
        logger.debug("Telegram Bot not configured, skipping unknown sender notification")
        return False

    try:
        result = await telegram_bot.notify_unknown_sms(
            from_number=from_number,
            message=message,
            attachment_count=attachment_count,
        )
        if result.success:
            logger.info(
                "Sent Telegram notification for unknown SMS from %s",
                from_number,
            )
            return True
        else:
            logger.warning(
                "Failed to send Telegram notification: %s",
                result.error,
            )
            return False
    except Exception as exc:
        logger.error(
            "Error sending Telegram notification for unknown SMS: %s",
            exc,
        )
        return False


async def _handle_compliance_keyword(
    keyword_type: str,
    from_number: str,
    to_number: str,
) -> str:
    """
    Handle a compliance keyword (STOP/HELP/START) for an unknown contact.

    Args:
        keyword_type: The type of keyword ("opt_out", "help", or "opt_in")
        from_number: The sender's phone number (where to send the response)
        to_number: Our Telnyx number (where to send the response from)

    Returns:
        A status message describing what was done
    """
    compliance_service = SMSComplianceService()
    sms_service = TelnyxSMSService()

    if keyword_type == "opt_out":
        # Record opt-out
        compliance_service.record_opt_out(from_number)
        response_text = STOP_RESPONSE
        status = "opted_out"
    elif keyword_type == "opt_in":
        # Record opt-in (remove from opt-out list)
        was_opted_out = compliance_service.record_opt_in(from_number)
        response_text = OPT_IN_RESPONSE
        status = "opted_in" if was_opted_out else "already_subscribed"
    elif keyword_type == "help":
        # Send help message (no state change)
        response_text = HELP_RESPONSE
        status = "help_sent"
    else:
        logger.warning("Unknown compliance keyword type: %s", keyword_type)
        return "unknown_keyword_type"

    # Send response SMS
    if sms_service.is_configured:
        try:
            result = await asyncio.to_thread(
                sms_service.send_sms,
                from_number,
                response_text,
                from_number=to_number,
            )
            if result.success:
                logger.info(
                    "Sent compliance response to %s: %s",
                    from_number,
                    status,
                )
            else:
                logger.error(
                    "Failed to send compliance response to %s: %s",
                    from_number,
                    result.error,
                )
                status = f"{status}_send_failed"
        except Exception as exc:
            logger.error(
                "Error sending compliance response to %s: %s",
                from_number,
                exc,
            )
            status = f"{status}_send_error"
    else:
        logger.warning("SMS service not configured, skipping compliance response")
        status = f"{status}_not_sent"

    return status


def _generate_message_id(timestamp: datetime, remote_number: str) -> str:
    """Generate a unique message ID."""
    ts = int(timestamp.timestamp())
    return f"sms_{ts}_{remote_number}"


def _parse_telnyx_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract message data from Telnyx webhook payload.

    Returns None if the message should be skipped (non-inbound, delivery receipt, etc).
    """
    # Telnyx wraps the event data
    event_data = data.get("data", {})
    event_type = event_data.get("event_type", "")
    payload = event_data.get("payload", {})

    # Only process inbound messages
    direction = payload.get("direction", "")
    if direction != "inbound":
        return None

    # Skip delivery receipts and other non-message events
    if event_type not in ("message.received", "message.finalized"):
        if "received" not in event_type.lower():
            return None

    # Extract message details
    from_info = payload.get("from", {})
    to_info = payload.get("to", [{}])

    # to can be a list in Telnyx payload
    if isinstance(to_info, list) and to_info:
        to_phone = to_info[0].get("phone_number", "")
    else:
        to_phone = to_info.get("phone_number", "") if isinstance(to_info, dict) else ""

    from_phone = from_info.get("phone_number", "")

    # If we don't have both phone numbers, skip
    if not from_phone or not to_phone:
        return None

    # Extract text content
    text = payload.get("text", "") or ""

    # Extract media (MMS attachments)
    media = payload.get("media", []) or []
    attachments = []
    for item in media:
        url = item.get("url", "")
        content_type = item.get("content_type", "application/octet-stream")
        size = item.get("size", 0) or 0
        if url:
            attachments.append({
                "url": url,
                "content_type": content_type,
                "size": size,
            })

    return {
        "from_number": from_phone,
        "to_number": to_phone,
        "text": text,
        "attachments": attachments,
        "telnyx_id": event_data.get("id") or payload.get("id"),
        "received_at": payload.get("received_at"),
    }


async def sms_webhook_handler(request: Request) -> JSONResponse:
    """
    Handle inbound SMS/MMS webhook from Telnyx.

    This endpoint is called by Telnyx when a message is received.
    It does NOT require API key authentication (Telnyx sends webhooks directly).

    Args:
        request: Starlette request with JSON body

    Returns:
        JSON response with status: 'processed' or 'skipped'
    """
    try:
        body = await request.json()
    except Exception as exc:
        logger.warning("Invalid JSON in SMS webhook: %s", exc)
        return JSONResponse(
            {"status": "error", "reason": "Invalid JSON payload"},
            status_code=400,
        )

    # Parse Telnyx payload
    parsed = _parse_telnyx_payload(body)

    if parsed is None:
        # Not an inbound message we should process
        logger.debug("Skipping non-inbound SMS webhook event")
        return JSONResponse({"status": "skipped", "reason": "not inbound message"})

    logger.info(
        "Processing inbound SMS from %s to %s",
        parsed["from_number"],
        parsed["to_number"],
    )

    # Look up contact for the sender
    contact_lookup = ContactLookup()
    try:
        contact_info = contact_lookup.lookup(parsed["from_number"])
    except Exception as exc:
        logger.warning("Contact lookup failed: %s", exc)
        contact_info = None

    # Determine timestamp
    if parsed.get("received_at"):
        try:
            timestamp = datetime.fromisoformat(
                parsed["received_at"].replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            timestamp = datetime.now(timezone.utc)
    else:
        timestamp = datetime.now(timezone.utc)

    # Create contact object if found
    contact = None
    if contact_info:
        contact = Contact(
            name=contact_info.name,
            googleContactId=contact_info.googleContactId,
        )

    # Check for compliance keywords ONLY for unknown contacts
    classification = None
    is_compliance_message = False
    if contact is None:
        classification = "unknown"
        keyword = detect_compliance_keyword(parsed["text"])
        if keyword:
            is_compliance_message = True
            classification = "compliance"
            keyword_type = get_keyword_type(keyword)

            # Handle compliance keyword
            compliance_response = await _handle_compliance_keyword(
                keyword_type=keyword_type,
                from_number=parsed["from_number"],
                to_number=parsed["to_number"],
            )
            logger.info(
                "Processed compliance keyword '%s' (%s) from %s: %s",
                keyword.value,
                keyword_type,
                parsed["from_number"],
                compliance_response,
            )

    # Create attachment objects
    attachments = [
        Attachment(
            filename="",  # Will be updated by store_message_async
            contentType=a["content_type"],
            size=a["size"],
            originalUrl=a["url"],
        )
        for a in parsed["attachments"]
    ]

    # Create SMS message
    message_id = _generate_message_id(timestamp, parsed["from_number"])
    message = SMSMessage(
        id=message_id,
        timestamp=timestamp.isoformat(),
        direction="inbound",
        localNumber=parsed["to_number"],
        remoteNumber=parsed["from_number"],
        content=parsed["text"],
        contact=contact,
        attachments=attachments,
        telnyxMessageId=parsed.get("telnyx_id"),
        processed=is_compliance_message,
        classification=classification,
    )

    # Store the message (with attachment downloads)
    storage = SMSStorage()
    try:
        filepath = await storage.store_message_async(message)
        logger.info("Stored SMS message at %s", filepath)
    except Exception as exc:
        logger.error("Failed to store SMS message: %s", exc)
        return JSONResponse(
            {"status": "error", "reason": str(exc)},
            status_code=500,
        )

    # Send Telegram notification for unknown senders (non-compliance messages only)
    telegram_notified = False
    if contact is None and not is_compliance_message:
        telegram_notified = await _send_unknown_sender_notification(
            from_number=parsed["from_number"],
            message=parsed["text"],
            attachment_count=len(parsed["attachments"]),
        )

    response_data = {
        "status": "processed",
        "message_id": message_id,
        "contact": contact.name if contact else None,
    }
    if is_compliance_message:
        response_data["compliance"] = True
        response_data["compliance_type"] = keyword_type
    if telegram_notified:
        response_data["telegram_notified"] = True

    return JSONResponse(response_data)


__all__ = ["sms_webhook_handler"]
