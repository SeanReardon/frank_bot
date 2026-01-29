"""
Unit tests for SwarmNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import SwarmNamespace, FrankAPI


class TestSwarmNamespaceCheckins:
    """Tests for SwarmNamespace.checkins()."""

    def test_checkins_with_defaults(self) -> None:
        """Checkins method uses correct default values."""
        mock_result = {
            "message": "Showing 2 most recent Swarm check-in(s).",
            "count": 2,
            "checkins": [
                {
                    "iso_time": "2024-01-15T12:00:00-06:00",
                    "venue": {"name": "Coffee Shop", "city": "Dallas"},
                    "categories": ["Coffee Shop"],
                },
                {
                    "iso_time": "2024-01-14T19:00:00-06:00",
                    "venue": {"name": "Restaurant", "city": "Dallas"},
                    "categories": ["Restaurant"],
                },
            ],
            "filters": {
                "year": None,
                "after_date": None,
                "before_date": None,
                "with_companion": None,
                "only_with_companions": False,
                "category": None,
                "has_photos": False,
                "include_photos": False,
            },
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins()

            # Verify action was called with correct default arguments
            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["year"] is None
            assert call_args["after_date"] is None
            assert call_args["before_date"] is None
            assert call_args["category"] is None
            assert call_args["with_companion"] is None
            assert call_args["companion_match"] == "any"
            assert call_args["only_with_companions"] is False
            assert call_args["has_photos"] is False
            assert call_args["include_photos"] is False
            assert call_args["max_results"] == 10
            assert call_args["stale_minutes"] == 180

            # Verify result is passed through
            assert result == mock_result
            assert result["count"] == 2

    def test_checkins_with_year_filter(self) -> None:
        """Checkins method passes year parameter correctly."""
        mock_result = {
            "message": "Found 5 check-in(s) in 2024.",
            "count": 5,
            "checkins": [],
            "filters": {"year": 2024},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(year=2024)

            call_args = mock_action.call_args[0][0]
            assert call_args["year"] == 2024
            assert result == mock_result

    def test_checkins_with_category_filter(self) -> None:
        """Checkins method passes category parameter correctly."""
        mock_result = {
            "message": "Found 3 check-in(s) in 'restaurant' venues.",
            "count": 3,
            "checkins": [],
            "filters": {"category": "restaurant"},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(category="restaurant")

            call_args = mock_action.call_args[0][0]
            assert call_args["category"] == "restaurant"
            assert result == mock_result

    def test_checkins_with_companion_filter(self) -> None:
        """Checkins method passes with_companion parameter correctly."""
        mock_result = {
            "message": "Found 2 check-in(s) with linda.",
            "count": 2,
            "checkins": [],
            "filters": {"with_companion": ["linda"]},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(with_companion="Linda")

            call_args = mock_action.call_args[0][0]
            assert call_args["with_companion"] == "Linda"
            assert result == mock_result

    def test_checkins_with_companion_list(self) -> None:
        """Checkins method passes list of companions correctly."""
        mock_result = {
            "message": "Found 1 check-in(s) with linda and jimmy.",
            "count": 1,
            "checkins": [],
            "filters": {"with_companion": ["linda", "jimmy"]},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(with_companion=["Linda", "Jimmy"], companion_match="all")

            call_args = mock_action.call_args[0][0]
            assert call_args["with_companion"] == ["Linda", "Jimmy"]
            assert call_args["companion_match"] == "all"
            assert result == mock_result

    def test_checkins_with_date_range(self) -> None:
        """Checkins method passes date range parameters correctly."""
        mock_result = {
            "message": "Found 10 check-in(s) between 2024-01-01 and 2024-01-31.",
            "count": 10,
            "checkins": [],
            "filters": {"after_date": "2024-01-01", "before_date": "2024-01-31"},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(after_date="2024-01-01", before_date="2024-01-31")

            call_args = mock_action.call_args[0][0]
            assert call_args["after_date"] == "2024-01-01"
            assert call_args["before_date"] == "2024-01-31"
            assert result == mock_result

    def test_checkins_with_photos_filter(self) -> None:
        """Checkins method passes photo-related parameters correctly."""
        mock_result = {
            "message": "Found 2 check-in(s) with photos.",
            "count": 2,
            "checkins": [],
            "filters": {"has_photos": True, "include_photos": True},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            result = namespace.checkins(has_photos=True, include_photos=True)

            call_args = mock_action.call_args[0][0]
            assert call_args["has_photos"] is True
            assert call_args["include_photos"] is True
            assert result == mock_result

    def test_checkins_with_all_parameters(self) -> None:
        """Checkins method passes all parameters correctly."""
        mock_result = {
            "message": "Complex query result",
            "count": 1,
            "checkins": [],
            "filters": {},
        }

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SwarmNamespace()
            namespace.checkins(
                year=2024,
                after_date="2024-06-01",
                before_date="2024-06-30",
                category="hotel",
                with_companion="Lauren",
                companion_match="any",
                only_with_companions=True,
                has_photos=True,
                include_photos=True,
                max_results=50,
                stale_minutes=60,
            )

            call_args = mock_action.call_args[0][0]
            assert call_args["year"] == 2024
            assert call_args["after_date"] == "2024-06-01"
            assert call_args["before_date"] == "2024-06-30"
            assert call_args["category"] == "hotel"
            assert call_args["with_companion"] == "Lauren"
            assert call_args["companion_match"] == "any"
            assert call_args["only_with_companions"] is True
            assert call_args["has_photos"] is True
            assert call_args["include_photos"] is True
            assert call_args["max_results"] == 50
            assert call_args["stale_minutes"] == 60


class TestFrankAPISwarmIntegration:
    """Tests for FrankAPI.swarm namespace access."""

    def test_frank_api_has_swarm_namespace(self) -> None:
        """FrankAPI provides access to SwarmNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "swarm")
        assert isinstance(api.swarm, SwarmNamespace)

    def test_frank_api_swarm_is_same_instance(self) -> None:
        """FrankAPI returns the same SwarmNamespace instance."""
        api = FrankAPI()
        assert api.swarm is api.swarm

    def test_frank_api_swarm_checkins_works(self) -> None:
        """FrankAPI.swarm.checkins() works correctly."""
        mock_result = {"message": "Checkins", "count": 0, "checkins": [], "filters": {}}

        with patch("actions.swarm.search_checkins_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.swarm.checkins(year=2024, category="restaurant")

            assert result == mock_result
            mock_action.assert_called_once()
