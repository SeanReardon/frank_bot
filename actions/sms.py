"""
SMS actions: send and receive text messages via Telnyx.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

from services.google_contacts import GoogleContactsService
from services.sms_storage import SMSMessage, SMSStorage
from services.telnyx_sms import TelnyxSMSService

logger = logging.getLogger(__name__)

# Regex to detect if a string looks like a phone number
PHONE_PATTERN = re.compile(r"^[\d\s\-\+\(\)\.]+$")


def _normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format (or close to it).

    Strips common formatting and ensures US numbers have +1 prefix.
    """
    # Remove all non-digit characters except leading +
    digits = re.sub(r"[^\d+]", "", phone)

    # If it starts with +, keep it
    if digits.startswith("+"):
        return digits

    # If it's a 10-digit US number, add +1
    if len(digits) == 10:
        return f"+1{digits}"

    # If it's 11 digits starting with 1, add +
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # Otherwise return as-is with + prefix
    return f"+{digits}" if digits else phone


def _looks_like_phone(value: str) -> bool:
    """Check if the value looks like a phone number."""
    return bool(PHONE_PATTERN.match(value.strip()))


async def send_sms_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send an SMS to a contact from your contacts list.

    The recipient can be specified by name (will look up in Google Contacts)
    or by phone number directly.
    """
    args = arguments or {}
    recipient = (args.get("recipient") or "").strip()
    message = (args.get("message") or "").strip()

    if not recipient:
        raise ValueError("recipient is required (contact name or phone number).")
    if not message:
        raise ValueError("message is required.")

    sms_service = TelnyxSMSService()

    if not sms_service.is_configured:
        raise ValueError(
            "SMS service is not configured. "
            "Please set TELNYX_LET_FOOD_INTO_CIVIC_KEY and TELNYX_PHONE_NUMBER."
        )

    # Determine if recipient is a phone number or a contact name
    if _looks_like_phone(recipient):
        # Direct phone number provided
        to_number = _normalize_phone(recipient)
        contact_name = None
        logger.info("Sending SMS directly to phone number: %s", to_number)
    else:
        # Look up contact by name
        logger.info("Looking up contact: %s", recipient)

        def fetch_contact():
            service = GoogleContactsService()
            results = service.search_contacts(recipient)
            return results

        contacts = await asyncio.to_thread(fetch_contact)

        if not contacts:
            raise ValueError(f"No contact found matching '{recipient}'.")

        # Find the first contact with a phone number
        contact_with_phone = None
        phone_number = None

        for contact in contacts:
            phones = contact.get("phoneNumbers") or []
            if phones:
                contact_with_phone = contact
                phone_number = phones[0].get("value")
                break

        if not contact_with_phone or not phone_number:
            # List contacts found but without phone numbers
            names = []
            for c in contacts[:5]:
                for n in c.get("names") or []:
                    if n.get("displayName"):
                        names.append(n["displayName"])
                        break
            if names:
                raise ValueError(
                    f"Found contacts matching '{recipient}' but none have phone numbers: "
                    f"{', '.join(names)}"
                )
            raise ValueError(f"No contacts with phone numbers found for '{recipient}'.")

        # Get display name
        contact_name = "Unknown"
        for name in contact_with_phone.get("names") or []:
            if name.get("displayName"):
                contact_name = name["displayName"]
                break

        to_number = _normalize_phone(phone_number)
        logger.info("Found contact %s with phone %s", contact_name, to_number)

    # Send the SMS
    result = await asyncio.to_thread(
        sms_service.send_sms,
        to_number,
        message,
    )

    if result.success:
        if contact_name:
            summary = f"SMS sent to {contact_name} ({to_number})"
        else:
            summary = f"SMS sent to {to_number}"

        return {
            "message": summary,
            "success": True,
            "recipient": contact_name or to_number,
            "to_number": to_number,
            "from_number": result.from_number,
            "message_id": result.message_id,
            "text_preview": message[:100] + ("..." if len(message) > 100 else ""),
        }
    else:
        error_detail = result.error or "Unknown error"
        raise ValueError(f"Failed to send SMS: {error_detail}")


async def get_sms_messages_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get recent SMS messages from storage.

    Supports filtering by contact name (fuzzy match), phone number, and direction.

    Args:
        arguments: Dict with optional keys:
            - limit: Max messages to return (default 50, max 100)
            - contact: Filter by contact name (case-insensitive partial match)
            - phone: Filter by phone number
            - direction: Filter by 'inbound' or 'outbound'

    Returns:
        Dict with count and messages array
    """
    args = arguments or {}

    # Parse and validate limit
    limit = 50
    if "limit" in args:
        try:
            limit = int(args["limit"])
            limit = max(1, min(100, limit))  # Clamp to 1-100
        except (ValueError, TypeError):
            limit = 50

    # Get optional filters
    contact_name = args.get("contact")
    phone = args.get("phone")
    direction_filter = args.get("direction")

    # Validate direction if provided
    if direction_filter and direction_filter not in ("inbound", "outbound"):
        raise ValueError("direction must be 'inbound' or 'outbound'")

    # Fetch messages from storage
    storage = SMSStorage()

    def fetch_messages():
        return storage.get_recent_messages(
            remote_number=phone,
            contact_name=contact_name,
            limit=limit * 2 if direction_filter else limit,  # Fetch more if filtering by direction
        )

    messages = await asyncio.to_thread(fetch_messages)

    # Apply direction filter if specified
    if direction_filter:
        messages = [m for m in messages if m.direction == direction_filter][:limit]

    # Format messages for response
    result_messages = []
    for msg in messages:
        message_data = {
            "timestamp": msg.timestamp,
            "direction": msg.direction,
            "phone": msg.remoteNumber,
            "preview": msg.content[:100] + ("..." if len(msg.content) > 100 else ""),
            "hasAttachments": len(msg.attachments) > 0,
        }
        if msg.contact:
            message_data["contact"] = msg.contact.name
        if msg.jorbId:
            message_data["jorbId"] = msg.jorbId

        result_messages.append(message_data)

    return {
        "count": len(result_messages),
        "messages": result_messages,
    }


__all__ = ["send_sms_action", "get_sms_messages_action"]



