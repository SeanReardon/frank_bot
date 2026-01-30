"""Unit tests for contact lookup service."""

from unittest.mock import MagicMock

import pytest

from services.contact_lookup import (
    Contact,
    ContactLookup,
    _extract_digits,
    _normalize_phone,
    _phones_match,
)


class TestNormalizePhone:
    """Tests for phone number normalization."""

    def test_removes_spaces(self):
        """Spaces are removed."""
        result = _normalize_phone("+1 555 123 4567")
        assert result == "+15551234567"

    def test_removes_dashes(self):
        """Dashes are removed."""
        result = _normalize_phone("+1-555-123-4567")
        assert result == "+15551234567"

    def test_removes_parentheses(self):
        """Parentheses are removed."""
        result = _normalize_phone("(555) 123-4567")
        assert result == "5551234567"

    def test_removes_dots(self):
        """Dots are removed."""
        result = _normalize_phone("555.123.4567")
        assert result == "5551234567"

    def test_empty_string(self):
        """Empty string returns empty."""
        result = _normalize_phone("")
        assert result == ""

    def test_preserves_plus(self):
        """Plus sign is preserved."""
        result = _normalize_phone("+15551234567")
        assert result == "+15551234567"


class TestExtractDigits:
    """Tests for digit extraction."""

    def test_extracts_digits_only(self):
        """Only digits are extracted."""
        result = _extract_digits("+1 (555) 123-4567")
        assert result == "15551234567"

    def test_empty_returns_empty(self):
        """Empty string returns empty."""
        result = _extract_digits("")
        assert result == ""


class TestPhonesMatch:
    """Tests for phone number matching."""

    def test_exact_match(self):
        """Identical numbers match."""
        assert _phones_match("+15551234567", "+15551234567")

    def test_formatting_difference(self):
        """Different formatting still matches."""
        assert _phones_match("+1-555-123-4567", "(555) 123-4567")

    def test_with_country_code(self):
        """Numbers with and without country code match."""
        assert _phones_match("+15551234567", "5551234567")

    def test_different_numbers_dont_match(self):
        """Different numbers don't match."""
        assert not _phones_match("+15551234567", "+15559999999")

    def test_short_numbers_dont_false_match(self):
        """Short numbers don't falsely match longer ones."""
        assert not _phones_match("1234567", "+15551234567")

    def test_empty_strings_dont_match(self):
        """Empty strings don't match."""
        assert not _phones_match("", "+15551234567")
        assert not _phones_match("+15551234567", "")

    def test_both_empty_dont_match(self):
        """Two empty strings don't match."""
        assert not _phones_match("", "")


class TestContactLookup:
    """Tests for ContactLookup service."""

    def test_lookup_found(self):
        """Contact is found by phone number."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)
        contact = lookup.lookup("+15551234567")

        assert contact is not None
        assert contact.name == "Mom"
        assert contact.googleContactId == "people/c123"

    def test_lookup_not_found(self):
        """None returned when contact not found."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)
        contact = lookup.lookup("+19999999999")

        assert contact is None

    def test_lookup_empty_number(self):
        """Empty number returns None without API call."""
        mock_service = MagicMock()
        lookup = ContactLookup(contacts_service=mock_service)

        contact = lookup.lookup("")

        assert contact is None
        mock_service.list_contacts.assert_not_called()

    def test_lookup_caches_result(self):
        """Repeated lookups use cache."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)

        # First lookup
        contact1 = lookup.lookup("+15551234567")
        # Second lookup (should use cache)
        contact2 = lookup.lookup("+15551234567")

        assert contact1 is not None
        assert contact2 is not None
        assert contact1.name == contact2.name

        # list_contacts should only be called once (to load all contacts)
        assert mock_service.list_contacts.call_count == 1

    def test_lookup_caches_misses(self):
        """Cache also stores misses to avoid repeated lookups."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)

        # First lookup (miss)
        contact1 = lookup.lookup("+19999999999")
        # Second lookup (should use cached miss)
        contact2 = lookup.lookup("+19999999999")

        assert contact1 is None
        assert contact2 is None

        # list_contacts should only be called once
        assert mock_service.list_contacts.call_count == 1

    def test_lookup_with_formatting_variations(self):
        """Contact found regardless of phone format."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [{"value": "(555) 123-4567"}],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)

        # Search with E.164 format
        contact = lookup.lookup("+15551234567")

        assert contact is not None
        assert contact.name == "Mom"

    def test_lookup_multiple_phone_numbers(self):
        """Contact with multiple phones can be found by any."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [
                        {"value": "+15551234567"},
                        {"value": "+15559999999"},
                    ],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)

        contact1 = lookup.lookup("+15551234567")
        lookup.clear_cache()  # Force re-lookup
        contact2 = lookup.lookup("+15559999999")

        assert contact1 is not None
        assert contact2 is not None
        assert contact1.name == "Mom"
        assert contact2.name == "Mom"

    def test_lookup_uses_unstructured_name(self):
        """Falls back to unstructuredName if displayName missing."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [{"unstructuredName": "John Doe"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                }
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)
        contact = lookup.lookup("+15551234567")

        assert contact is not None
        assert contact.name == "John Doe"

    def test_lookup_skips_contacts_without_name(self):
        """Contacts without names are skipped."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [
                {
                    "resourceName": "people/c123",
                    "names": [],  # No names
                    "phoneNumbers": [{"value": "+15551234567"}],
                },
                {
                    "resourceName": "people/c456",
                    "names": [{"displayName": "Mom"}],
                    "phoneNumbers": [{"value": "+15551234567"}],
                },
            ],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)
        contact = lookup.lookup("+15551234567")

        assert contact is not None
        # Should find the second contact (with name)
        assert contact.name == "Mom"
        assert contact.googleContactId == "people/c456"

    def test_lookup_pagination(self):
        """Lookup handles pagination correctly."""
        mock_service = MagicMock()
        mock_service.list_contacts.side_effect = [
            {
                "connections": [
                    {
                        "resourceName": "people/c123",
                        "names": [{"displayName": "Alice"}],
                        "phoneNumbers": [{"value": "+15551111111"}],
                    }
                ],
                "nextPageToken": "page2",
            },
            {
                "connections": [
                    {
                        "resourceName": "people/c456",
                        "names": [{"displayName": "Bob"}],
                        "phoneNumbers": [{"value": "+15552222222"}],
                    }
                ],
                "nextPageToken": None,
            },
        ]

        lookup = ContactLookup(contacts_service=mock_service)

        # Should find contact from second page
        contact = lookup.lookup("+15552222222")

        assert contact is not None
        assert contact.name == "Bob"
        assert mock_service.list_contacts.call_count == 2

    def test_clear_cache(self):
        """Clear cache resets state."""
        mock_service = MagicMock()
        mock_service.list_contacts.return_value = {
            "connections": [],
            "nextPageToken": None,
        }

        lookup = ContactLookup(contacts_service=mock_service)

        # First lookup
        lookup.lookup("+15551234567")

        # Clear cache
        lookup.clear_cache()

        # Second lookup should trigger new API call
        lookup.lookup("+15551234567")

        assert mock_service.list_contacts.call_count == 2


class TestContact:
    """Tests for Contact dataclass."""

    def test_contact_with_id(self):
        """Contact can be created with ID."""
        contact = Contact(name="Mom", googleContactId="people/c123")
        assert contact.name == "Mom"
        assert contact.googleContactId == "people/c123"

    def test_contact_without_id(self):
        """Contact can be created without ID."""
        contact = Contact(name="Mom", googleContactId=None)
        assert contact.name == "Mom"
        assert contact.googleContactId is None
