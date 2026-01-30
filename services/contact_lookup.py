"""
Contact Lookup Service for phone-to-contact reverse lookup.

Provides efficient phone number to Google Contact resolution with caching.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.google_contacts import GoogleContactsService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    """Contact information from Google Contacts."""

    name: str
    googleContactId: str | None


def _normalize_phone(phone: str) -> str:
    """
    Normalize a phone number for comparison.

    Strips spaces, dashes, parentheses, dots, and handles country codes.
    Returns just the digits (with potential leading + for E.164).
    """
    if not phone:
        return ""
    # Remove common formatting characters
    cleaned = re.sub(r"[\s\-().]+", "", phone)
    return cleaned


def _extract_digits(phone: str) -> str:
    """
    Extract just the digits from a phone number.

    Used for comparing numbers regardless of country code format.
    """
    return re.sub(r"\D", "", phone)


def _phones_match(phone1: str, phone2: str) -> bool:
    """
    Check if two phone numbers match.

    Handles various formats and country code differences.
    Example matches:
      +1-555-123-4567 matches (555) 123-4567
      +15551234567 matches 5551234567
    """
    digits1 = _extract_digits(phone1)
    digits2 = _extract_digits(phone2)

    if not digits1 or not digits2:
        return False

    # Exact match
    if digits1 == digits2:
        return True

    # Check if one has country code and one doesn't
    # This handles +1 prefix for US numbers
    # The longer one should have exactly 1 more digit (the country code)
    # OR the shorter one is 10 digits (US number without +1)
    shorter = min(digits1, digits2, key=len)
    longer = max(digits1, digits2, key=len)

    # Only consider matches where shorter has 10 digits (full US number)
    # and longer has 11 digits (with country code 1)
    if len(shorter) == 10 and len(longer) == 11 and longer.startswith("1"):
        if longer[1:] == shorter:
            return True

    return False


class ContactLookup:
    """
    Service for looking up contacts by phone number.

    Uses Google Contacts for data and caches results to prevent
    repeated API calls for the same number.
    """

    def __init__(self, contacts_service: GoogleContactsService | None = None):
        """
        Initialize the contact lookup service.

        Args:
            contacts_service: GoogleContactsService instance.
                            If None, creates a new one.
        """
        self._contacts_service = contacts_service
        self._cache: dict[str, Contact | None] = {}
        self._all_contacts_loaded = False
        self._all_contacts: list[dict] = []

    def _get_service(self) -> GoogleContactsService:
        """Get or create the contacts service."""
        if self._contacts_service is None:
            self._contacts_service = GoogleContactsService()
        return self._contacts_service

    def _load_all_contacts(self) -> None:
        """
        Load all contacts from Google Contacts.

        This is done once and cached for efficient lookups.
        """
        if self._all_contacts_loaded:
            return

        try:
            service = self._get_service()
            all_contacts = []
            page_token = None

            while True:
                result = service.list_contacts(
                    page_size=100,
                    person_fields=("names", "phoneNumbers"),
                    page_token=page_token,
                )
                all_contacts.extend(result.get("connections", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            self._all_contacts = all_contacts
            self._all_contacts_loaded = True
            logger.info("Loaded %d contacts for phone lookup", len(all_contacts))
        except Exception as exc:
            logger.error("Failed to load contacts: %s", exc)
            self._all_contacts = []
            self._all_contacts_loaded = True  # Don't retry on every lookup

    def lookup(self, phone_number: str) -> Contact | None:
        """
        Look up a contact by phone number.

        Args:
            phone_number: The phone number to search for (any format)

        Returns:
            Contact with name and googleContactId, or None if not found
        """
        if not phone_number:
            return None

        normalized = _normalize_phone(phone_number)

        # Check cache first
        if normalized in self._cache:
            return self._cache[normalized]

        # Load all contacts if not already loaded
        self._load_all_contacts()

        # Search through contacts
        for person in self._all_contacts:
            resource_name = person.get("resourceName")
            names = person.get("names", [])
            phone_numbers = person.get("phoneNumbers", [])

            # Get display name
            display_name = None
            for name in names:
                display_name = name.get("displayName") or name.get("unstructuredName")
                if display_name:
                    break

            if not display_name:
                continue

            # Check each phone number
            for phone_entry in phone_numbers:
                contact_phone = phone_entry.get("value", "")
                if _phones_match(phone_number, contact_phone):
                    contact = Contact(
                        name=display_name,
                        googleContactId=resource_name,
                    )
                    self._cache[normalized] = contact
                    logger.debug(
                        "Found contact %s for phone %s",
                        display_name,
                        phone_number,
                    )
                    return contact

        # Not found - cache the miss
        self._cache[normalized] = None
        logger.debug("No contact found for phone %s", phone_number)
        return None

    def clear_cache(self) -> None:
        """Clear the lookup cache."""
        self._cache.clear()
        self._all_contacts_loaded = False
        self._all_contacts = []


__all__ = ["ContactLookup", "Contact"]
