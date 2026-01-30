"""
SMS Webhook Handler for inbound Telnyx messages.

Handles POST /webhook/sms from Telnyx when SMS/MMS messages arrive.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from services.contact_lookup import ContactLookup
from services.sms_storage import (
    Attachment,
    Contact,
    SMSMessage,
    SMSStorage,
)

logger = logging.getLogger(__name__)


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
        processed=False,
        classification="unknown" if contact is None else None,
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

    return JSONResponse({
        "status": "processed",
        "message_id": message_id,
        "contact": contact.name if contact else None,
    })


__all__ = ["sms_webhook_handler"]
