"""
Unit tests for ContactsNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import ContactsNamespace, FrankAPI


class TestContactsNamespaceSearch:
    """Tests for ContactsNamespace.search()."""

    def test_search_with_query(self) -> None:
        """Search method passes query parameter correctly."""
        mock_result = {
            "message": "Top 2 contact match(es) for 'John':",
            "query": "John",
            "count": 2,
            "contacts": [
                {
                    "resource_name": "people/123",
                    "display_name": "John Doe",
                    "emails": ["john.doe@example.com"],
                    "phones": ["+15551234567"],
                },
                {
                    "resource_name": "people/456",
                    "display_name": "John Smith",
                    "emails": ["john.smith@example.com"],
                    "phones": [],
                },
            ],
        }

        with patch("actions.contacts.search_contacts_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = ContactsNamespace()
            result = namespace.search("John")

            # Verify action was called with correct arguments
            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["query"] == "John"
            assert call_args["max_results"] == 10  # default

            # Verify result is passed through
            assert result == mock_result
            assert result["count"] == 2
            assert len(result["contacts"]) == 2

    def test_search_with_max_results(self) -> None:
        """Search method passes max_results parameter correctly."""
        mock_result = {
            "message": "Top 5 contact match(es) for 'Jane':",
            "query": "Jane",
            "count": 5,
            "contacts": [],
        }

        with patch("actions.contacts.search_contacts_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = ContactsNamespace()
            result = namespace.search("Jane", max_results=5)

            call_args = mock_action.call_args[0][0]
            assert call_args["query"] == "Jane"
            assert call_args["max_results"] == 5
            assert result == mock_result

    def test_search_no_results(self) -> None:
        """Search method handles no results correctly."""
        mock_result = {
            "message": "No contacts matched 'Unknown'.",
            "query": "Unknown",
            "count": 0,
            "contacts": [],
        }

        with patch("actions.contacts.search_contacts_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = ContactsNamespace()
            result = namespace.search("Unknown")

            assert result["count"] == 0
            assert result["contacts"] == []


class TestFrankAPIContactsIntegration:
    """Tests for FrankAPI.contacts namespace access."""

    def test_frank_api_has_contacts_namespace(self) -> None:
        """FrankAPI provides access to ContactsNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "contacts")
        assert isinstance(api.contacts, ContactsNamespace)

    def test_frank_api_contacts_is_same_instance(self) -> None:
        """FrankAPI returns the same ContactsNamespace instance."""
        api = FrankAPI()
        assert api.contacts is api.contacts

    def test_frank_api_contacts_search_works(self) -> None:
        """FrankAPI.contacts.search() works correctly."""
        mock_result = {"message": "Results", "query": "Alice", "count": 1, "contacts": []}

        with patch("actions.contacts.search_contacts_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.contacts.search("Alice")

            assert result == mock_result
            mock_action.assert_called_once()
