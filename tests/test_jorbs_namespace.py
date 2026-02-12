"""
Unit tests for JorbsNamespace in meta/api.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import actions.jorbs  # noqa: F401 - ensure module is importable for patch()

from meta.api import JorbsNamespace, FrankAPI


class TestJorbsNamespaceList:
    """Tests for JorbsNamespace.list()."""

    def test_list_default_open(self) -> None:
        mock_result = {"count": 2, "status_filter": "open", "jorbs": []}

        with patch(
            "actions.jorbs.list_jorbs_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.list()
            mock_action.assert_called_once_with({"status": "open"})
            assert result["status_filter"] == "open"

    def test_list_with_status_filter(self) -> None:
        mock_result = {"count": 5, "status_filter": "all", "jorbs": []}

        with patch(
            "actions.jorbs.list_jorbs_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.list(status="all")
            mock_action.assert_called_once_with({"status": "all"})
            assert result["count"] == 5


class TestJorbsNamespaceGet:
    """Tests for JorbsNamespace.get()."""

    def test_get_jorb(self) -> None:
        mock_result = {"jorb_id": "j123", "name": "Test", "status": "running"}

        with patch(
            "actions.jorbs.get_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.get("j123")
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "include_messages": False,
                "message_limit": 50,
            })
            assert result["jorb_id"] == "j123"

    def test_get_with_messages(self) -> None:
        mock_result = {"jorb_id": "j123", "messages": []}

        with patch(
            "actions.jorbs.get_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.get("j123", include_messages=True, message_limit=10)
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "include_messages": True,
                "message_limit": 10,
            })


class TestJorbsNamespaceCreate:
    """Tests for JorbsNamespace.create()."""

    def test_create_jorb(self) -> None:
        mock_result = {"jorb_id": "j456", "name": "Book dinner", "status": "running"}

        with patch(
            "actions.jorbs.create_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.create(name="Book dinner", plan="Find a restaurant")
            mock_action.assert_called_once_with({
                "name": "Book dinner",
                "plan": "Find a restaurant",
                "contacts": None,
                "personality": "default",
                "start_immediately": True,
            })
            assert result["name"] == "Book dinner"

    def test_create_with_all_params(self) -> None:
        contacts = [{"identifier": "@SeanReardon", "channel": "telegram"}]
        mock_result = {"jorb_id": "j789", "status": "planning"}

        with patch(
            "actions.jorbs.create_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.create(
                name="Test",
                plan="Plan",
                contacts=contacts,
                personality="concierge",
                start_immediately=False,
            )
            mock_action.assert_called_once_with({
                "name": "Test",
                "plan": "Plan",
                "contacts": contacts,
                "personality": "concierge",
                "start_immediately": False,
            })


class TestJorbsNamespaceApprove:
    """Tests for JorbsNamespace.approve()."""

    def test_approve_jorb(self) -> None:
        mock_result = {"jorb_id": "j123", "status": "running", "decision": "go ahead"}

        with patch(
            "actions.jorbs.approve_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.approve("j123", "go ahead")
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "decision": "go ahead",
            })
            assert result["decision"] == "go ahead"


class TestJorbsNamespaceCancel:
    """Tests for JorbsNamespace.cancel()."""

    def test_cancel_jorb(self) -> None:
        mock_result = {"jorb_id": "j123", "status": "cancelled"}

        with patch(
            "actions.jorbs.cancel_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.cancel("j123", reason="no longer needed")
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "reason": "no longer needed",
            })
            assert result["status"] == "cancelled"


class TestJorbsNamespaceStats:
    """Tests for JorbsNamespace.stats()."""

    def test_stats_default(self) -> None:
        mock_result = {"total_jorbs": 10, "by_status": {"running": 3}}

        with patch(
            "actions.jorbs.get_jorbs_stats_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.stats()
            mock_action.assert_called_once_with({"status": "all"})
            assert result["total_jorbs"] == 10

    def test_stats_with_filter(self) -> None:
        mock_result = {"total_jorbs": 3, "status_filter": "open"}

        with patch(
            "actions.jorbs.get_jorbs_stats_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.stats(status="open")
            mock_action.assert_called_once_with({"status": "open"})


class TestJorbsNamespaceBrief:
    """Tests for JorbsNamespace.brief()."""

    def test_brief_default(self) -> None:
        mock_result = {"needs_attention": 1, "activity_summary": []}

        with patch(
            "actions.jorbs.brief_me_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.brief()
            mock_action.assert_called_once_with({"hours": 24})
            assert result["needs_attention"] == 1

    def test_brief_custom_hours(self) -> None:
        mock_result = {"needs_attention": 0}

        with patch(
            "actions.jorbs.brief_me_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            ns.brief(hours=48)
            mock_action.assert_called_once_with({"hours": 48})


class TestJorbsNamespaceMessages:
    """Tests for JorbsNamespace.messages()."""

    def test_messages_default(self) -> None:
        mock_result = {"jorb_id": "j123", "count": 5, "messages": []}

        with patch(
            "actions.jorbs.get_jorb_messages_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            result = ns.messages("j123")
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "limit": 50,
                "offset": 0,
            })
            assert result["count"] == 5

    def test_messages_with_pagination(self) -> None:
        mock_result = {"jorb_id": "j123", "count": 10, "messages": []}

        with patch(
            "actions.jorbs.get_jorb_messages_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = JorbsNamespace()
            ns.messages("j123", limit=10, offset=20)
            mock_action.assert_called_once_with({
                "jorb_id": "j123",
                "limit": 10,
                "offset": 20,
            })


class TestFrankAPIJorbsIntegration:
    """Tests for FrankAPI.jorbs namespace access."""

    def test_frank_api_has_jorbs_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "jorbs")
        assert isinstance(api.jorbs, JorbsNamespace)

    def test_frank_api_jorbs_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.jorbs is api.jorbs

    def test_frank_api_jorbs_list_works(self) -> None:
        with patch(
            "actions.jorbs.list_jorbs_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"count": 0, "jorbs": []}
            api = FrankAPI()
            result = api.jorbs.list()
            assert result["count"] == 0
            mock_action.assert_called_once()

    def test_frank_api_jorbs_create_works(self) -> None:
        with patch(
            "actions.jorbs.create_jorb_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"jorb_id": "j1", "status": "running"}
            api = FrankAPI()
            result = api.jorbs.create(name="Test", plan="Do stuff")
            assert result["jorb_id"] == "j1"
            mock_action.assert_called_once()

    def test_frank_api_jorbs_brief_works(self) -> None:
        with patch(
            "actions.jorbs.brief_me_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"needs_attention": 0}
            api = FrankAPI()
            result = api.jorbs.brief(hours=24)
            assert result["needs_attention"] == 0
            mock_action.assert_called_once()
