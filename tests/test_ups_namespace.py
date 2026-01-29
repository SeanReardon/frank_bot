"""
Unit tests for UPSNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import UPSNamespace, FrankAPI


class TestUPSNamespaceStatus:
    """Tests for UPSNamespace.status()."""

    def test_status_returns_ups_info(self) -> None:
        """Status method returns UPS status information."""
        mock_result = {
            "message": "UPS status placeholder until data source is wired.",
            "runtime": {
                "hours": 2,
                "mins": 30,
                "human": "2h 30m",
            },
            "charge_percent": 100,
            "temperature_f": 72.5,
        }

        with patch("actions.ups.get_ups_status_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = UPSNamespace()
            result = namespace.status()

            # Verify action was called (no arguments needed)
            mock_action.assert_called_once()

            # Verify result is passed through
            assert result == mock_result
            assert result["charge_percent"] == 100
            assert result["runtime"]["hours"] == 2
            assert result["runtime"]["mins"] == 30
            assert result["temperature_f"] == 72.5

    def test_status_with_low_battery(self) -> None:
        """Status method handles low battery scenario."""
        mock_result = {
            "message": "UPS status placeholder until data source is wired.",
            "runtime": {
                "hours": 0,
                "mins": 15,
                "human": "0h 15m",
            },
            "charge_percent": 25,
            "temperature_f": 75.0,
        }

        with patch("actions.ups.get_ups_status_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = UPSNamespace()
            result = namespace.status()

            assert result["charge_percent"] == 25
            assert result["runtime"]["mins"] == 15


class TestFrankAPIUPSIntegration:
    """Tests for FrankAPI.ups namespace access."""

    def test_frank_api_has_ups_namespace(self) -> None:
        """FrankAPI provides access to UPSNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "ups")
        assert isinstance(api.ups, UPSNamespace)

    def test_frank_api_ups_is_same_instance(self) -> None:
        """FrankAPI returns the same UPSNamespace instance."""
        api = FrankAPI()
        assert api.ups is api.ups

    def test_frank_api_ups_status_works(self) -> None:
        """FrankAPI.ups.status() works correctly."""
        mock_result = {
            "message": "UPS status",
            "runtime": {"hours": 1, "mins": 0, "human": "1h 0m"},
            "charge_percent": 95,
            "temperature_f": 70.0,
        }

        with patch("actions.ups.get_ups_status_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.ups.status()

            assert result == mock_result
            mock_action.assert_called_once()
