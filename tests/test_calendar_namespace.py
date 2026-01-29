"""
Unit tests for CalendarNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import CalendarNamespace, FrankAPI


class TestCalendarNamespaceEvents:
    """Tests for CalendarNamespace.events()."""

    def test_events_with_day_parameter(self) -> None:
        """Events method passes day parameter correctly."""
        mock_result = {
            "message": "Found 2 event(s) on 'primary':",
            "calendar": {"id": "primary", "label": "primary"},
            "time_window": {
                "time_min": "2024-01-15T00:00:00-06:00",
                "time_max": "2024-01-16T00:00:00-06:00",
                "time_zone": "America/Chicago",
            },
            "count": 2,
            "events": [
                {"summary": "Meeting", "start": {"dateTime": "2024-01-15T10:00:00-06:00"}},
                {"summary": "Lunch", "start": {"dateTime": "2024-01-15T12:00:00-06:00"}},
            ],
        }

        with patch("actions.calendar.get_events_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.events(day="2024-01-15")

            # Verify action was called with correct arguments
            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["day"] == "2024-01-15"
            assert call_args["max_results"] == 10  # default

            # Verify result is passed through
            assert result == mock_result
            assert result["count"] == 2
            assert len(result["events"]) == 2

    def test_events_with_time_range(self) -> None:
        """Events method passes time_min and time_max correctly."""
        mock_result = {
            "message": "Found 1 event(s)",
            "calendar": {"id": "primary", "label": "primary"},
            "time_window": {
                "time_min": "2024-01-15T09:00:00Z",
                "time_max": "2024-01-15T17:00:00Z",
                "time_zone": "America/Chicago",
            },
            "count": 1,
            "events": [{"summary": "Event"}],
        }

        with patch("actions.calendar.get_events_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.events(
                time_min="2024-01-15T09:00:00Z",
                time_max="2024-01-15T17:00:00Z",
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["time_min"] == "2024-01-15T09:00:00Z"
            assert call_args["time_max"] == "2024-01-15T17:00:00Z"
            assert result == mock_result

    def test_events_with_all_parameters(self) -> None:
        """Events method passes all parameters correctly."""
        mock_result = {"message": "Events", "count": 0, "events": []}

        with patch("actions.calendar.get_events_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            namespace.events(
                day="2024-01-15",
                time_min="2024-01-15T00:00:00Z",
                time_max="2024-01-16T00:00:00Z",
                max_results=25,
                time_zone="America/New_York",
                calendar_id="test-calendar@group.calendar.google.com",
                calendar_name="Work Calendar",
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["day"] == "2024-01-15"
            assert call_args["time_min"] == "2024-01-15T00:00:00Z"
            assert call_args["time_max"] == "2024-01-16T00:00:00Z"
            assert call_args["max_results"] == 25
            assert call_args["time_zone"] == "America/New_York"
            assert call_args["calendar_id"] == "test-calendar@group.calendar.google.com"
            assert call_args["calendar_name"] == "Work Calendar"

    def test_events_defaults(self) -> None:
        """Events method uses correct default values."""
        mock_result = {"message": "Events", "count": 0, "events": []}

        with patch("actions.calendar.get_events_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            namespace.events()

            call_args = mock_action.call_args[0][0]
            assert call_args["day"] is None
            assert call_args["time_min"] is None
            assert call_args["time_max"] is None
            assert call_args["max_results"] == 10
            assert call_args["time_zone"] is None
            assert call_args["calendar_id"] is None
            assert call_args["calendar_name"] is None


class TestCalendarNamespaceCreate:
    """Tests for CalendarNamespace.create()."""

    def test_create_with_required_parameters(self) -> None:
        """Create method passes required parameters correctly."""
        mock_result = {
            "message": "Created event 'Team Meeting' from 2024-01-15T10:00:00 to 2024-01-15T11:00:00",
            "event": {
                "id": "event123",
                "summary": "Team Meeting",
                "start": {"dateTime": "2024-01-15T10:00:00-06:00"},
                "end": {"dateTime": "2024-01-15T11:00:00-06:00"},
            },
            "calendar": {"id": "primary", "label": "primary"},
        }

        with patch("actions.calendar.create_event_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.create(
                summary="Team Meeting",
                start="2024-01-15T10:00:00-06:00",
                end="2024-01-15T11:00:00-06:00",
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["summary"] == "Team Meeting"
            assert call_args["start"] == "2024-01-15T10:00:00-06:00"
            assert call_args["end"] == "2024-01-15T11:00:00-06:00"
            assert result == mock_result

    def test_create_with_all_parameters(self) -> None:
        """Create method passes all parameters correctly."""
        mock_result = {
            "message": "Created event",
            "event": {"id": "event123"},
            "calendar": {"id": "work", "label": "Work"},
        }

        with patch("actions.calendar.create_event_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            namespace.create(
                summary="Team Meeting",
                start="2024-01-15T10:00:00-06:00",
                end="2024-01-15T11:00:00-06:00",
                description="Weekly sync",
                location="Conference Room A",
                attendees=["alice@example.com", "bob@example.com"],
                time_zone="America/Chicago",
                calendar_id="work@group.calendar.google.com",
                calendar_name="Work",
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["summary"] == "Team Meeting"
            assert call_args["start"] == "2024-01-15T10:00:00-06:00"
            assert call_args["end"] == "2024-01-15T11:00:00-06:00"
            assert call_args["description"] == "Weekly sync"
            assert call_args["location"] == "Conference Room A"
            assert call_args["attendees"] == ["alice@example.com", "bob@example.com"]
            assert call_args["time_zone"] == "America/Chicago"
            assert call_args["calendar_id"] == "work@group.calendar.google.com"
            assert call_args["calendar_name"] == "Work"

    def test_create_defaults(self) -> None:
        """Create method uses correct default values for optional parameters."""
        mock_result = {"message": "Created event", "event": {}, "calendar": {}}

        with patch("actions.calendar.create_event_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            namespace.create(
                summary="Event",
                start="2024-01-15T10:00:00Z",
                end="2024-01-15T11:00:00Z",
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["description"] is None
            assert call_args["location"] is None
            assert call_args["attendees"] is None
            assert call_args["time_zone"] is None
            assert call_args["calendar_id"] is None
            assert call_args["calendar_name"] is None


class TestCalendarNamespaceList:
    """Tests for CalendarNamespace.list()."""

    def test_list_defaults(self) -> None:
        """List method uses correct default values."""
        mock_result = {
            "message": "Available calendars:",
            "count": 2,
            "calendars": [
                {"id": "primary", "summary": "Personal", "timeZone": "America/Chicago"},
                {"id": "work@group.calendar.google.com", "summary": "Work", "timeZone": "America/Chicago"},
            ],
        }

        with patch("actions.calendar.get_calendars_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.list()

            call_args = mock_action.call_args[0][0]
            assert call_args["include_access_role"] is False
            assert call_args["primary_only"] is False
            assert result == mock_result
            assert result["count"] == 2

    def test_list_with_include_access_role(self) -> None:
        """List method passes include_access_role parameter correctly."""
        mock_result = {
            "message": "Available calendars:",
            "count": 1,
            "calendars": [
                {
                    "id": "primary",
                    "summary": "Personal",
                    "timeZone": "America/Chicago",
                    "accessRole": "owner",
                },
            ],
        }

        with patch("actions.calendar.get_calendars_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.list(include_access_role=True)

            call_args = mock_action.call_args[0][0]
            assert call_args["include_access_role"] is True
            assert result["calendars"][0]["accessRole"] == "owner"

    def test_list_with_primary_only(self) -> None:
        """List method passes primary_only parameter correctly."""
        mock_result = {
            "message": "Available calendars:",
            "count": 1,
            "calendars": [
                {"id": "primary", "summary": "Personal", "timeZone": "America/Chicago", "primary": True},
            ],
        }

        with patch("actions.calendar.get_calendars_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = CalendarNamespace()
            result = namespace.list(primary_only=True)

            call_args = mock_action.call_args[0][0]
            assert call_args["primary_only"] is True
            assert len(result["calendars"]) == 1
            assert result["calendars"][0]["primary"] is True


class TestFrankAPICalendarIntegration:
    """Tests for FrankAPI.calendar namespace access."""

    def test_frank_api_has_calendar_namespace(self) -> None:
        """FrankAPI provides access to CalendarNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "calendar")
        assert isinstance(api.calendar, CalendarNamespace)

    def test_frank_api_calendar_is_same_instance(self) -> None:
        """FrankAPI returns the same CalendarNamespace instance."""
        api = FrankAPI()
        assert api.calendar is api.calendar

    def test_frank_api_calendar_events_works(self) -> None:
        """FrankAPI.calendar.events() works correctly."""
        mock_result = {"message": "Events", "count": 0, "events": []}

        with patch("actions.calendar.get_events_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.calendar.events(day="2024-01-15")

            assert result == mock_result
            mock_action.assert_called_once()
