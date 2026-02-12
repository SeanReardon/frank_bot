"""
Unit tests for StyleNamespace in meta/api.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import StyleNamespace, FrankAPI


class TestStyleNamespaceGenerate:
    """Tests for StyleNamespace.generate()."""

    def test_generate_default(self) -> None:
        mock_result = {
            "success": True,
            "messages_analyzed": 100,
            "content_length": 5000,
        }

        with patch(
            "actions.style_capture.generate_sean_md_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = StyleNamespace()
            result = ns.generate()
            mock_action.assert_called_once_with({
                "chat_id": None,
                "dry_run": False,
                "before_date": None,
            })
            assert result["success"] is True

    def test_generate_dry_run(self) -> None:
        mock_result = {"success": True, "dry_run": True}

        with patch(
            "actions.style_capture.generate_sean_md_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = StyleNamespace()
            result = ns.generate(dry_run=True)
            mock_action.assert_called_once_with({
                "chat_id": None,
                "dry_run": True,
                "before_date": None,
            })
            assert result["dry_run"] is True

    def test_generate_with_all_params(self) -> None:
        mock_result = {"success": True}

        with patch(
            "actions.style_capture.generate_sean_md_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = StyleNamespace()
            ns.generate(
                chat_id="@TestBot",
                dry_run=True,
                before_date="2026-01-01",
            )
            mock_action.assert_called_once_with({
                "chat_id": "@TestBot",
                "dry_run": True,
                "before_date": "2026-01-01",
            })


class TestFrankAPIStyleIntegration:
    """Tests for FrankAPI.style namespace access."""

    def test_frank_api_has_style_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "style")
        assert isinstance(api.style, StyleNamespace)

    def test_frank_api_style_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.style is api.style

    def test_frank_api_style_generate_works(self) -> None:
        with patch(
            "actions.style_capture.generate_sean_md_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"success": True}
            api = FrankAPI()
            result = api.style.generate(dry_run=True)
            assert result["success"] is True
            mock_action.assert_called_once()
