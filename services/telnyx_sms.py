"""
Telnyx SMS service for sending text messages.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import telnyx

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)


@dataclass
class SMSResult:
    """Result of an SMS send operation."""

    success: bool
    message_id: str | None
    to_number: str
    from_number: str
    error: str | None = None


class TelnyxSMSService:
    """Service for sending SMS messages via Telnyx."""

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.telnyx_api_key
        self._from_number = settings.telnyx_phone_number
        self._notify_numbers = settings.notify_numbers

        if self._api_key:
            telnyx.api_key = self._api_key

    @property
    def is_configured(self) -> bool:
        """Check if the service has required configuration."""
        return bool(self._api_key and self._from_number)

    @property
    def from_number(self) -> str | None:
        """Return the configured Telnyx phone number."""
        return self._from_number

    @property
    def notify_numbers(self) -> tuple[str, ...]:
        """Return the configured notification numbers."""
        return self._notify_numbers

    def send_sms(
        self,
        to_number: str,
        message: str,
        *,
        from_number: str | None = None,
    ) -> SMSResult:
        """
        Send an SMS message to the specified number.

        Args:
            to_number: The recipient's phone number (E.164 format preferred).
            message: The text message content.
            from_number: Optional override for the sender number.

        Returns:
            SMSResult with success status and message details.
        """
        if not self.is_configured:
            return SMSResult(
                success=False,
                message_id=None,
                to_number=to_number,
                from_number="",
                error="Telnyx SMS is not configured. Check TELNYX_LET_FOOD_INTO_CIVIC_KEY and TELNYX_PHONE_NUMBER.",
            )

        sender = from_number or self._from_number
        sms_stats = stats.get_service_stats("telnyx_sms")
        start = time.time()

        try:
            logger.info("Sending SMS to %s from %s", to_number, sender)
            response = telnyx.Message.create(
                from_=sender,
                to=to_number,
                text=message,
            )
            elapsed_ms = (time.time() - start) * 1000
            sms_stats.record_request(elapsed_ms, success=True)

            message_id = getattr(response, "id", None)
            logger.info("SMS sent successfully, message_id=%s", message_id)

            return SMSResult(
                success=True,
                message_id=message_id,
                to_number=to_number,
                from_number=sender,
            )

        except telnyx.error.TelnyxError as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            sms_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telnyx_sms",
                error_msg,
                {"method": "send_sms", "to": to_number},
            )
            logger.error("Failed to send SMS to %s: %s", to_number, error_msg)

            return SMSResult(
                success=False,
                message_id=None,
                to_number=to_number,
                from_number=sender,
                error=error_msg,
            )

        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            error_msg = str(exc)
            sms_stats.record_request(elapsed_ms, success=False, error=error_msg)
            stats.record_error(
                "telnyx_sms",
                error_msg,
                {"method": "send_sms", "to": to_number},
            )
            logger.exception("Unexpected error sending SMS to %s", to_number)

            return SMSResult(
                success=False,
                message_id=None,
                to_number=to_number,
                from_number=sender,
                error=error_msg,
            )

    def notify_owner(self, message: str) -> list[SMSResult]:
        """
        Send an SMS to all configured notification numbers.

        Useful for alerting the owner about important events.
        """
        results = []
        for number in self._notify_numbers:
            result = self.send_sms(number.strip(), message)
            results.append(result)
        return results


__all__ = ["TelnyxSMSService", "SMSResult"]



