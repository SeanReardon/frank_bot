"""
Tests for api_learn_action documenting FrankAPI namespaces.

Uses importlib to load actions/scripts.py directly, bypassing
actions/__init__.py eager imports that need google/telnyx modules.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Load actions/scripts.py directly without triggering actions/__init__.py
_scripts_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "actions", "scripts.py"
)
_spec = importlib.util.spec_from_file_location("actions.scripts", _scripts_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("actions.scripts", _mod)
_spec.loader.exec_module(_mod)

api_learn_action = _mod.api_learn_action


class TestApiLearnAction:
    """Tests for api_learn_action namespace documentation."""

    @pytest.mark.asyncio
    async def test_returns_all_expected_namespaces(self):
        """api_learn_action should document all FrankAPI namespaces."""
        result = await api_learn_action()

        namespaces = result["namespaces"]

        # Original namespaces
        assert "calendar" in namespaces
        assert "contacts" in namespaces
        assert "sms" in namespaces
        assert "swarm" in namespaces
        assert "telegram" in namespaces
        assert "ups" in namespaces
        assert "time" in namespaces

        # New namespaces
        assert "diagnostics" in namespaces
        assert "system" in namespaces
        assert "jorbs" in namespaces
        assert "claudia" in namespaces
        assert "style" in namespaces

    @pytest.mark.asyncio
    async def test_diagnostics_namespace_methods(self):
        """Diagnostics namespace should document full and health methods."""
        result = await api_learn_action()
        diag = result["namespaces"]["diagnostics"]

        method_names = [m["name"] for m in diag["methods"]]
        assert "full" in method_names
        assert "health" in method_names
        assert "description" in diag

    @pytest.mark.asyncio
    async def test_system_namespace_methods(self):
        """System namespace should document status, server, hello methods."""
        result = await api_learn_action()
        sys_ns = result["namespaces"]["system"]

        method_names = [m["name"] for m in sys_ns["methods"]]
        assert "status" in method_names
        assert "server" in method_names
        assert "hello" in method_names

    @pytest.mark.asyncio
    async def test_jorbs_namespace_methods(self):
        """Jorbs namespace should document all jorb management methods."""
        result = await api_learn_action()
        jorbs = result["namespaces"]["jorbs"]

        method_names = [m["name"] for m in jorbs["methods"]]
        for expected in ["list", "get", "create", "approve", "cancel", "stats", "brief", "messages"]:
            assert expected in method_names, f"Missing method: {expected}"

    @pytest.mark.asyncio
    async def test_claudia_namespace_methods(self):
        """Claudia namespace should document all AI assistant methods."""
        result = await api_learn_action()
        claudia = result["namespaces"]["claudia"]

        method_names = [m["name"] for m in claudia["methods"]]
        for expected in [
            "repos", "chat_create", "chat_get", "chat_send", "chat_end",
            "prompts", "prompt_get", "prompt_execute",
            "queue", "executions", "execution_get",
        ]:
            assert expected in method_names, f"Missing method: {expected}"

    @pytest.mark.asyncio
    async def test_style_namespace_methods(self):
        """Style namespace should document generate method."""
        result = await api_learn_action()
        style = result["namespaces"]["style"]

        method_names = [m["name"] for m in style["methods"]]
        assert "generate" in method_names

    @pytest.mark.asyncio
    async def test_each_namespace_has_examples(self):
        """Each new namespace should have usage examples."""
        result = await api_learn_action()
        namespaces = result["namespaces"]

        for ns_name in ["diagnostics", "system", "jorbs", "claudia", "style"]:
            ns = namespaces[ns_name]
            assert "examples" in ns, f"Missing examples for {ns_name}"
            assert len(ns["examples"]) > 0, f"Empty examples for {ns_name}"

    @pytest.mark.asyncio
    async def test_existing_namespaces_unchanged(self):
        """Original namespace documentation should remain unchanged."""
        result = await api_learn_action()
        namespaces = result["namespaces"]

        # Calendar should still have its examples
        cal = namespaces["calendar"]
        assert "examples" in cal
        assert any("events" in ex for ex in cal["examples"])

        # SMS should still have its examples
        sms = namespaces["sms"]
        assert "examples" in sms
        assert any("send" in ex for ex in sms["examples"])

    @pytest.mark.asyncio
    async def test_overview_mentions_new_namespaces(self):
        """Overview text should mention the new namespaces."""
        result = await api_learn_action()
        overview = result["overview"]

        assert "diagnostics" in overview
        assert "jorbs" in overview
        assert "claudia" in overview
        assert "style" in overview
