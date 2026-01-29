"""
Unit tests for TimeNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import TimeNamespace, FrankAPI


class TestTimeNamespaceNow:
    """Tests for TimeNamespace.now()."""

    def test_now_with_swarm_derived_time(self) -> None:
        """Now method returns time derived from Swarm check-in."""
        mock_result = {
            "message": "Derived from your latest Swarm check-in at Coffee Shop, Dallas, TX, US.",
            "iso_time": "2024-01-15T10:30:00-06:00",
            "timezone": "UTC-06:00",
            "offset_minutes": -360,
        }

        with patch("actions.system.get_time_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = TimeNamespace()
            result = namespace.now()

            # Verify action was called
            mock_action.assert_called_once()

            # Verify result is passed through
            assert result == mock_result
            assert result["iso_time"] == "2024-01-15T10:30:00-06:00"
            assert result["timezone"] == "UTC-06:00"
            assert result["offset_minutes"] == -360

    def test_now_with_default_timezone_fallback(self) -> None:
        """Now method returns time from default timezone when Swarm unavailable."""
        mock_result = {
            "message": "Using your configured DEFAULT_TIMEZONE (America/Chicago).",
            "iso_time": "2024-01-15T10:30:00-06:00",
            "timezone": "America/Chicago",
            "offset_minutes": -360,
        }

        with patch("actions.system.get_time_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = TimeNamespace()
            result = namespace.now()

            assert result == mock_result
            assert result["timezone"] == "America/Chicago"

    def test_now_with_timezone_parameter_ignored(self) -> None:
        """Now method accepts timezone parameter (for future compatibility)."""
        mock_result = {
            "message": "Using your configured DEFAULT_TIMEZONE (America/Chicago).",
            "iso_time": "2024-01-15T10:30:00-06:00",
            "timezone": "America/Chicago",
            "offset_minutes": -360,
        }

        with patch("actions.system.get_time_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = TimeNamespace()
            # The timezone parameter is accepted but not currently used by the underlying action
            result = namespace.now(timezone="America/New_York")

            # Action should still be called (timezone param not passed to action currently)
            mock_action.assert_called_once()
            assert result == mock_result

    def test_now_different_timezones(self) -> None:
        """Now method handles various timezone offsets."""
        mock_result = {
            "message": "Derived from your latest Swarm check-in.",
            "iso_time": "2024-01-15T19:30:00+09:00",
            "timezone": "UTC+09:00",
            "offset_minutes": 540,
        }

        with patch("actions.system.get_time_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = TimeNamespace()
            result = namespace.now()

            assert result["offset_minutes"] == 540
            assert result["timezone"] == "UTC+09:00"


class TestFrankAPITimeIntegration:
    """Tests for FrankAPI.time namespace access."""

    def test_frank_api_has_time_namespace(self) -> None:
        """FrankAPI provides access to TimeNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "time")
        assert isinstance(api.time, TimeNamespace)

    def test_frank_api_time_is_same_instance(self) -> None:
        """FrankAPI returns the same TimeNamespace instance."""
        api = FrankAPI()
        assert api.time is api.time

    def test_frank_api_time_now_works(self) -> None:
        """FrankAPI.time.now() works correctly."""
        mock_result = {
            "message": "Current time",
            "iso_time": "2024-01-15T12:00:00-06:00",
            "timezone": "America/Chicago",
            "offset_minutes": -360,
        }

        with patch("actions.system.get_time_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.time.now()

            assert result == mock_result
            mock_action.assert_called_once()
