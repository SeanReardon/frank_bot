"""
Unit tests for ClaudiaNamespace in meta/api.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import actions.claudia  # noqa: F401 - ensure module is importable for patch()

from meta.api import ClaudiaNamespace, FrankAPI


class TestClaudiaNamespaceRepos:
    """Tests for ClaudiaNamespace.repos()."""

    def test_repos_returns_list(self) -> None:
        mock_result = {"message": "Found 2 repos.", "count": 2, "repos": []}

        with patch(
            "actions.claudia.list_claudia_repos_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.repos()
            mock_action.assert_called_once()
            assert result["count"] == 2


class TestClaudiaNamespaceChatCreate:
    """Tests for ClaudiaNamespace.chat_create()."""

    def test_chat_create(self) -> None:
        mock_result = {"message": "Chat started", "chat": {"id": "c1"}}

        with patch(
            "actions.claudia.create_claudia_chat_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.chat_create("frank_bot", "Fix bug", message="Please fix")
            mock_action.assert_called_once_with({
                "repo_name": "frank_bot",
                "title": "Fix bug",
                "message": "Please fix",
            })
            assert result["chat"]["id"] == "c1"

    def test_chat_create_without_message(self) -> None:
        mock_result = {"message": "Chat started", "chat": {"id": "c2"}}

        with patch(
            "actions.claudia.create_claudia_chat_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            ns.chat_create("frank_bot", "Feature")
            mock_action.assert_called_once_with({
                "repo_name": "frank_bot",
                "title": "Feature",
                "message": None,
            })


class TestClaudiaNamespaceChatGet:
    """Tests for ClaudiaNamespace.chat_get()."""

    def test_chat_get(self) -> None:
        mock_result = {"message": "Chat active", "chat": {"id": "c1", "messages": []}}

        with patch(
            "actions.claudia.get_claudia_chat_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.chat_get("repo1", "c1")
            mock_action.assert_called_once_with({
                "repo_id": "repo1",
                "chat_id": "c1",
            })
            assert result["chat"]["id"] == "c1"


class TestClaudiaNamespaceChatSend:
    """Tests for ClaudiaNamespace.chat_send()."""

    def test_chat_send(self) -> None:
        mock_result = {"message": "Message sent.", "chat_message": {"id": "m1"}}

        with patch(
            "actions.claudia.send_claudia_message_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.chat_send("repo1", "c1", "Hello Claudia")
            mock_action.assert_called_once_with({
                "repo_id": "repo1",
                "chat_id": "c1",
                "message": "Hello Claudia",
            })
            assert result["chat_message"]["id"] == "m1"


class TestClaudiaNamespaceChatEnd:
    """Tests for ClaudiaNamespace.chat_end()."""

    def test_chat_end(self) -> None:
        mock_result = {"message": "Chat ended", "chat": {"id": "c1", "status": "completed"}}

        with patch(
            "actions.claudia.end_claudia_chat_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.chat_end("repo1", "c1")
            mock_action.assert_called_once_with({
                "repo_id": "repo1",
                "chat_id": "c1",
            })
            assert result["chat"]["status"] == "completed"


class TestClaudiaNamespacePrompts:
    """Tests for ClaudiaNamespace.prompts()."""

    def test_prompts(self) -> None:
        mock_result = {"count": 3, "prompts": []}

        with patch(
            "actions.claudia.list_claudia_prompts_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.prompts("repo1")
            mock_action.assert_called_once_with({"repo_id": "repo1"})
            assert result["count"] == 3


class TestClaudiaNamespacePromptGet:
    """Tests for ClaudiaNamespace.prompt_get()."""

    def test_prompt_get(self) -> None:
        mock_result = {"prompt": {"id": "p1", "title": "Test"}}

        with patch(
            "actions.claudia.get_claudia_prompt_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.prompt_get("repo1", "p1")
            mock_action.assert_called_once_with({
                "repo_id": "repo1",
                "prompt_id": "p1",
            })
            assert result["prompt"]["id"] == "p1"


class TestClaudiaNamespacePromptExecute:
    """Tests for ClaudiaNamespace.prompt_execute()."""

    def test_prompt_execute(self) -> None:
        mock_result = {"queue_item_id": "qi1", "queue_position": 0}

        with patch(
            "actions.claudia.execute_claudia_prompt_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.prompt_execute("repo1", "p1")
            mock_action.assert_called_once_with({
                "repo_id": "repo1",
                "prompt_id": "p1",
            })
            assert result["queue_position"] == 0


class TestClaudiaNamespaceQueue:
    """Tests for ClaudiaNamespace.queue()."""

    def test_queue(self) -> None:
        mock_result = {"message": "Queue empty", "queue": {"depth": 0}}

        with patch(
            "actions.claudia.get_claudia_queue_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.queue("repo1")
            mock_action.assert_called_once_with({"repo_id": "repo1"})
            assert result["queue"]["depth"] == 0


class TestClaudiaNamespaceExecutions:
    """Tests for ClaudiaNamespace.executions()."""

    def test_executions_default(self) -> None:
        mock_result = {"count": 5, "executions": []}

        with patch(
            "actions.claudia.list_claudia_executions_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.executions()
            mock_action.assert_called_once_with({
                "repo_id": None,
                "status": None,
                "limit": 50,
            })
            assert result["count"] == 5

    def test_executions_with_filters(self) -> None:
        mock_result = {"count": 2, "executions": []}

        with patch(
            "actions.claudia.list_claudia_executions_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            ns.executions(repo_id="r1", status="completed", limit=10)
            mock_action.assert_called_once_with({
                "repo_id": "r1",
                "status": "completed",
                "limit": 10,
            })


class TestClaudiaNamespaceExecutionGet:
    """Tests for ClaudiaNamespace.execution_get()."""

    def test_execution_get(self) -> None:
        mock_result = {"message": "Execution status: completed", "execution": {}}

        with patch(
            "actions.claudia.get_claudia_execution_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = ClaudiaNamespace()
            result = ns.execution_get("ex1")
            mock_action.assert_called_once_with({"execution_id": "ex1"})
            assert "Execution" in result["message"]


class TestFrankAPIClaudiaIntegration:
    """Tests for FrankAPI.claudia namespace access."""

    def test_frank_api_has_claudia_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "claudia")
        assert isinstance(api.claudia, ClaudiaNamespace)

    def test_frank_api_claudia_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.claudia is api.claudia

    def test_frank_api_claudia_repos_works(self) -> None:
        with patch(
            "actions.claudia.list_claudia_repos_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"count": 1, "repos": []}
            api = FrankAPI()
            result = api.claudia.repos()
            assert result["count"] == 1
            mock_action.assert_called_once()

    def test_frank_api_claudia_chat_create_works(self) -> None:
        with patch(
            "actions.claudia.create_claudia_chat_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"chat": {"id": "c1"}}
            api = FrankAPI()
            result = api.claudia.chat_create("frank_bot", "Fix bug", message="help")
            assert result["chat"]["id"] == "c1"
            mock_action.assert_called_once()
