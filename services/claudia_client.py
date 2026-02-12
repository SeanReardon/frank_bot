"""
Claudia Chat API Client for Frank Bot

Provides HTTP client for interacting with Claudia's conversational API
for discussing codebases and collaboratively designing features.

API endpoints (from ~/dev/claudia/openapi.yml):
- GET    /api/repos                              # List repos
- GET    /api/repos/{repoId}                     # Get repo details
- GET    /api/repos/{repoId}/queue               # Get queue state
- POST   /api/repos/{repoId}/chats               # Create a chat
- GET    /api/repos/{repoId}/chats               # List chats
- GET    /api/repos/{repoId}/chats/{chatId}      # Get chat with messages
- POST   /api/repos/{repoId}/chats/{chatId}/messages  # Add a message
- POST   /api/repos/{repoId}/chats/{chatId}/end  # End the chat
- GET    /api/repos/{repoId}/prompts             # List prompts
- GET    /api/repos/{repoId}/prompts/{promptId}  # Get prompt
- POST   /api/repos/{repoId}/prompts/{promptId}/queue  # Queue prompt
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


class ClaudiaAPIError(RuntimeError):
    """Raised when the Claudia API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ClaudiaConflictError(ClaudiaAPIError):
    """Raised on 409 conflict, e.g., prompt already queued."""

    def __init__(self, message: str):
        super().__init__(message, status_code=409)


@dataclass
class ClaudiaRepo:
    """Represents a Claudia-managed repository."""
    id: str
    name: str
    owner: str
    full_name: str
    status: str = "unknown"  # pending, bootstrapping, ready, paused, error
    model: str = ""
    blocked_task_count: int = 0
    queued_prompt_id: str | None = None
    prompt_status: str | None = None  # queued, executing


@dataclass
class ClaudiaChatMessage:
    """Represents a message in a Claudia chat."""
    id: str
    chat_id: str
    role: str  # "user" or "assistant"
    content: str
    created_at: str
    processed_at: str | None = None
    tokens_used: int | None = None


@dataclass
class ClaudiaChat:
    """Represents a chat session with Claudia."""
    id: str
    repo_id: str
    title: str
    status: str  # "active", "completed", "cancelled"
    created_at: str
    updated_at: str
    message_count: int = 0
    queue_position: int | None = None
    created_by: str | None = None
    prompt_id: str | None = None
    messages: list[ClaudiaChatMessage] = field(default_factory=list)


@dataclass
class ClaudiaPrompt:
    """Represents a prompt in a repository."""
    id: str
    title: str
    status: str  # "draft", "ready", "archived"
    created_at: str
    description: str | None = None
    content: str | None = None
    blocked_by: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ClaudiaQueueItem:
    """Represents an item in the queue."""
    id: str
    repo_id: str
    item_type: str  # prd_task, chat, prompt_generation, prompt_execution
    item_id: str
    position: int
    status: str  # "pending", "active", "completed", "failed", "cancelled"
    created_at: str
    title: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class ClaudiaQueueState:
    """Represents the queue state for a repository."""
    items: list[ClaudiaQueueItem]
    active_item: ClaudiaQueueItem | None
    depth: int
    estimated_wait_minutes: float | None = None


class ClaudiaClient:
    """HTTP client for Claudia's conversational API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_url = settings.claudia_api_url
        self.api_key = settings.claudia_api_key

        if not self.api_url:
            raise ValueError(
                "Claudia is not configured. "
                "Configure Vault secret `secret/frank-bot/claudia` "
                "(api_url, api_key)."
            )

        if not self.api_key:
            raise ValueError(
                "Claudia is not configured. "
                "Configure Vault secret `secret/frank-bot/claudia` (api_key)."
            )

        self.session = requests.Session()
        self.session.headers["X-API-Key"] = self.api_key
        self.session.headers["Content-Type"] = "application/json"

    # ------------------------------------------------------------------ #
    # Core request helpers
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | list[Any], int]:
        """
        Make an HTTP request to the Claudia API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            path: API path (e.g., "/api/repos")
            params: Query parameters
            json_data: JSON body data

        Returns:
            Tuple of (response_data, status_code)

        Raises:
            ClaudiaAPIError: On API errors
            ClaudiaConflictError: On 409 response
        """
        url = f"{self.api_url.rstrip('/')}/{path.lstrip('/')}"

        # Log request details
        logger.info("CLAUDIA_REQUEST: %s %s params=%s", method, path, params)

        last_error: Exception | None = None
        claudia_stats = stats.get_service_stats("claudia")

        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=30,
                )
                elapsed_ms = (time.time() - start_time) * 1000
                response_bytes = len(response.content)

                logger.info(
                    "CLAUDIA_RESPONSE: %s %s status=%d elapsed=%.0fms",
                    method, path, response.status_code, elapsed_ms
                )

                # Handle 204 No Content
                if response.status_code == 204:
                    claudia_stats.record_request(
                        elapsed_ms, success=True, bytes_received=0
                    )
                    return {}, 204

                # Parse JSON response
                try:
                    data = response.json() if response.content else {}
                except ValueError as exc:
                    logger.error("CLAUDIA_ERROR: %s invalid JSON", path)
                    claudia_stats.record_request(
                        elapsed_ms, success=False, error="Invalid JSON"
                    )
                    raise ClaudiaAPIError("Claudia API: invalid JSON") from exc

                if response.status_code == 409:
                    claudia_stats.record_request(
                        elapsed_ms, success=False, error="Conflict"
                    )
                    detail = data.get("detail", "Conflict") if isinstance(
                        data, dict
                    ) else "Conflict"
                    raise ClaudiaConflictError(detail)

                if response.status_code >= 400:
                    error_detail = "Unknown error"
                    if isinstance(data, dict):
                        error_detail = data.get(
                            "detail", f"HTTP {response.status_code}"
                        )
                    logger.warning(
                        "CLAUDIA_API_ERROR: %s code=%d detail=%s",
                        path, response.status_code, error_detail
                    )

                    # Retry on server errors (5xx) or rate limits (429)
                    if response.status_code in (429, 500, 502, 503, 504):
                        if attempt < MAX_RETRIES - 1:
                            sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                            logger.info("CLAUDIA_RETRY: %.1fs", sleep_time)
                            time.sleep(sleep_time)
                            continue

                    claudia_stats.record_request(
                        elapsed_ms,
                        success=False,
                        error=f"{response.status_code}: {error_detail}",
                    )
                    raise ClaudiaAPIError(
                        f"Claudia ({response.status_code}): {error_detail}",
                        status_code=response.status_code,
                    )

                # Success
                claudia_stats.record_request(
                    elapsed_ms, success=True, bytes_received=response_bytes
                )
                logger.info("CLAUDIA_SUCCESS: %s %s", method, path)
                return data, response.status_code

            except requests.RequestException as exc:
                elapsed_ms = (time.time() - start_time) * 1000
                last_error = exc
                logger.warning(
                    "CLAUDIA_NETWORK_ERROR: %s error=%s",
                    path, str(exc)
                )

                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.info("CLAUDIA_RETRY: sleep %.1fs", sleep_time)
                    time.sleep(sleep_time)
                    continue

                claudia_stats.record_request(
                    elapsed_ms, success=False, error=f"Network: {exc}"
                )
                raise ClaudiaAPIError(f"Network error: {exc}") from exc

        msg = f"Claudia API failed after {MAX_RETRIES} attempts: {last_error}"
        raise ClaudiaAPIError(msg)

    def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request."""
        data, _ = self._request("GET", path, params=params)
        return data

    def _post(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | list[Any], int]:
        """Make a POST request."""
        return self._request("POST", path, json_data=json_data)

    def _delete(self, path: str) -> None:
        """Make a DELETE request."""
        self._request("DELETE", path)

    # ------------------------------------------------------------------ #
    # Repository Operations
    # ------------------------------------------------------------------ #

    def list_repos(self) -> list[ClaudiaRepo]:
        """List all Claudia-managed repositories."""
        data = self._get("/api/repos")
        repos = []
        # API returns flat array
        items = data if isinstance(data, list) else []
        for item in items:
            repos.append(self._parse_repo(item))
        return repos

    def get_repo(self, repo_id: str) -> ClaudiaRepo:
        """Get a specific repository."""
        data = self._get(f"/api/repos/{repo_id}")
        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")
        return self._parse_repo(data)

    def _parse_repo(self, item: dict[str, Any]) -> ClaudiaRepo:
        """Parse a repo dict into a ClaudiaRepo."""
        return ClaudiaRepo(
            id=item.get("id", ""),
            name=item.get("name", ""),
            owner=item.get("owner", ""),
            full_name=item.get("fullName", ""),
            status=item.get("status", "unknown"),
            model=item.get("model", ""),
            blocked_task_count=item.get("blockedTaskCount", 0),
            queued_prompt_id=item.get("queuedPromptId"),
            prompt_status=item.get("promptStatus"),
        )

    def get_repo_by_name(self, name: str) -> ClaudiaRepo | None:
        """Find a repo by name (case-insensitive partial match)."""
        repos = self.list_repos()
        name_lower = name.lower()

        # Try exact match first
        for repo in repos:
            if repo.name.lower() == name_lower:
                return repo
            if repo.full_name.lower() == name_lower:
                return repo

        # Try partial match
        matches = [
            repo for repo in repos
            if name_lower in repo.name.lower()
            or name_lower in repo.full_name.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            options = ", ".join(r.full_name for r in matches[:5])
            raise ValueError(
                f"Multiple repos matched '{name}'. "
                f"Please be more specific: {options}"
            )
        return None

    # ------------------------------------------------------------------ #
    # Queue Operations
    # ------------------------------------------------------------------ #

    def get_queue_state(self, repo_id: str) -> ClaudiaQueueState:
        """Get the queue state for a repository."""
        data = self._get(f"/api/repos/{repo_id}/queue")
        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        items = []
        for item in data.get("items", []):
            items.append(self._parse_queue_item(item))

        active_item = None
        if data.get("activeItem"):
            active_item = self._parse_queue_item(data["activeItem"])

        return ClaudiaQueueState(
            items=items,
            active_item=active_item,
            depth=data.get("depth", 0),
            estimated_wait_minutes=data.get("estimatedWaitMinutes"),
        )

    def _parse_queue_item(self, item: dict[str, Any]) -> ClaudiaQueueItem:
        """Parse a queue item dict."""
        return ClaudiaQueueItem(
            id=item.get("id", ""),
            repo_id=item.get("repoId", ""),
            item_type=item.get("itemType", ""),
            item_id=item.get("itemId", ""),
            position=item.get("position", 0),
            status=item.get("status", "pending"),
            created_at=item.get("createdAt", ""),
            title=item.get("title"),
            started_at=item.get("startedAt"),
            completed_at=item.get("completedAt"),
        )

    # ------------------------------------------------------------------ #
    # Chat Operations
    # ------------------------------------------------------------------ #

    def create_chat(
        self,
        repo_id: str,
        title: str,
        initial_message: str | None = None,
    ) -> ClaudiaChat:
        """
        Create a new chat with Claudia about a repository.

        Args:
            repo_id: Repository ID
            title: Chat title/topic (required)
            initial_message: Optional initial message to start conversation

        Returns:
            ClaudiaChat object with queue position
        """
        payload: dict[str, Any] = {"title": title}
        if initial_message:
            payload["initialMessage"] = initial_message

        path = f"/api/repos/{repo_id}/chats"
        data, _ = self._post(path, json_data=payload)

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        # Response is ChatCreatedResponse with chat and queuePosition
        chat_data = data.get("chat", data)
        queue_position = data.get("queuePosition")

        chat = self._parse_chat(chat_data, repo_id)
        if queue_position is not None:
            chat.queue_position = queue_position
        return chat

    def list_chats(
        self, repo_id: str, status: str | None = None
    ) -> list[ClaudiaChat]:
        """List chats for a repository."""
        params = {}
        if status:
            params["status"] = status

        data = self._get(f"/api/repos/{repo_id}/chats", params=params or None)
        chats = []
        items = data if isinstance(data, list) else []
        for item in items:
            chats.append(self._parse_chat(item, repo_id))
        return chats

    def get_chat(self, repo_id: str, chat_id: str) -> ClaudiaChat:
        """Get a chat session with all messages."""
        data = self._get(f"/api/repos/{repo_id}/chats/{chat_id}")
        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")
        return self._parse_chat_detail(data, repo_id)

    def _parse_chat(
        self, item: dict[str, Any], repo_id: str
    ) -> ClaudiaChat:
        """Parse a Chat dict (without messages)."""
        return ClaudiaChat(
            id=item.get("id", ""),
            repo_id=item.get("repoId", repo_id),
            title=item.get("title", ""),
            status=item.get("status", "active"),
            created_at=item.get("createdAt", ""),
            updated_at=item.get("updatedAt", ""),
            message_count=item.get("messageCount", 0),
            queue_position=item.get("queuePosition"),
            created_by=item.get("createdBy"),
            prompt_id=item.get("promptId"),
        )

    def _parse_chat_detail(
        self, item: dict[str, Any], repo_id: str
    ) -> ClaudiaChat:
        """Parse a ChatDetail dict (with messages)."""
        messages = []
        for msg in item.get("messages", []):
            messages.append(ClaudiaChatMessage(
                id=msg.get("id", ""),
                chat_id=msg.get("chatId", ""),
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                created_at=msg.get("createdAt", ""),
                processed_at=msg.get("processedAt"),
                tokens_used=msg.get("tokensUsed"),
            ))

        return ClaudiaChat(
            id=item.get("id", ""),
            repo_id=item.get("repoId", repo_id),
            title=item.get("title", ""),
            status=item.get("status", "active"),
            created_at=item.get("createdAt", ""),
            updated_at=item.get("updatedAt", ""),
            message_count=len(messages),
            queue_position=item.get("queuePosition"),
            created_by=item.get("createdBy"),
            prompt_id=item.get("promptId"),
            messages=messages,
        )

    def add_message(
        self, repo_id: str, chat_id: str, content: str
    ) -> ClaudiaChatMessage:
        """
        Add a message to a chat.

        Args:
            repo_id: Repository ID
            chat_id: Chat ID
            content: Message content

        Returns:
            The created ChatMessage
        """
        path = f"/api/repos/{repo_id}/chats/{chat_id}/messages"
        data, _ = self._post(path, json_data={"content": content})

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        return ClaudiaChatMessage(
            id=data.get("id", ""),
            chat_id=data.get("chatId", chat_id),
            role=data.get("role", "user"),
            content=data.get("content", content),
            created_at=data.get("createdAt", ""),
            processed_at=data.get("processedAt"),
            tokens_used=data.get("tokensUsed"),
        )

    def end_chat(self, repo_id: str, chat_id: str) -> ClaudiaChat:
        """End a chat session."""
        path = f"/api/repos/{repo_id}/chats/{chat_id}/end"
        data, _ = self._post(path)

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        return self._parse_chat(data, repo_id)

    def delete_chat(self, repo_id: str, chat_id: str) -> None:
        """Delete a chat (must be ended first)."""
        self._delete(f"/api/repos/{repo_id}/chats/{chat_id}")

    # ------------------------------------------------------------------ #
    # Prompt Operations
    # ------------------------------------------------------------------ #

    def list_prompts(self, repo_id: str) -> list[ClaudiaPrompt]:
        """List all prompts for a repository."""
        data = self._get(f"/api/repos/{repo_id}/prompts")
        prompts = []
        items = data if isinstance(data, list) else []
        for item in items:
            prompts.append(self._parse_prompt(item))
        return prompts

    def get_prompt(self, repo_id: str, prompt_id: str) -> ClaudiaPrompt:
        """Get a specific prompt with full content."""
        data = self._get(f"/api/repos/{repo_id}/prompts/{prompt_id}")
        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")
        return self._parse_prompt(data)

    def _parse_prompt(self, item: dict[str, Any]) -> ClaudiaPrompt:
        """Parse a Prompt dict."""
        return ClaudiaPrompt(
            id=item.get("id", ""),
            title=item.get("title", ""),
            status=item.get("status", "draft"),
            created_at=item.get("createdAt", ""),
            description=item.get("description"),
            content=item.get("content"),
            blocked_by=item.get("blockedBy"),
            tags=item.get("tags", []),
        )

    def queue_prompt(self, repo_id: str, prompt_id: str) -> dict[str, Any]:
        """
        Queue a prompt for PRD generation (legacy).

        Args:
            repo_id: Repository ID
            prompt_id: Prompt ID to queue

        Returns:
            QueuePromptResponse with success, message, and queueState

        Raises:
            ClaudiaConflictError: If a prompt is already queued
            ClaudiaAPIError: If prompt cannot be queued (not ready, blocked)
        """
        path = f"/api/repos/{repo_id}/prompts/{prompt_id}/queue"
        data, _ = self._post(path)

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        return data

    def create_prompt_from_chat(
        self, repo_id: str, chat_id: str
    ) -> dict[str, Any]:
        """
        Create a prompt from a completed chat.

        Queues prompt generation from a completed chat conversation.

        Args:
            repo_id: Repository ID
            chat_id: ID of the completed chat to generate prompt from

        Returns:
            PromptGenerationQueued with queueItemId, queuePosition, chatId
        """
        path = f"/api/repos/{repo_id}/prompts"
        data, status = self._post(path, json_data={"chatId": chat_id})

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        return data

    def execute_prompt(self, repo_id: str, prompt_id: str) -> dict[str, Any]:
        """
        Queue a prompt for direct execution.

        The prompt content will be executed directly by Claude.

        Args:
            repo_id: Repository ID
            prompt_id: Prompt ID to execute

        Returns:
            ExecutionQueued with queueItemId, queuePosition, promptId
        """
        path = f"/api/repos/{repo_id}/prompts/{prompt_id}/execute"
        data, _ = self._post(path)

        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")

        return data

    # ------------------------------------------------------------------ #
    # Execution Tracking
    # ------------------------------------------------------------------ #

    def list_executions(
        self,
        repo_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List executions with optional filters.

        Args:
            repo_id: Filter by repository (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)

        Returns:
            List of execution summaries
        """
        params: dict[str, Any] = {"limit": limit}
        if repo_id:
            params["repoId"] = repo_id
        if status:
            params["status"] = status

        data = self._get("/api/executions", params=params)
        if isinstance(data, list):
            return data
        return data.get("executions", []) if isinstance(data, dict) else []

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        """
        Get execution details.

        Returns full details including prompt, output, git diff, and costs.

        Args:
            execution_id: Execution ID

        Returns:
            Execution details
        """
        data = self._get(f"/api/executions/{execution_id}")
        if not isinstance(data, dict):
            raise ClaudiaAPIError("Unexpected response format")
        return data


__all__ = [
    "ClaudiaClient",
    "ClaudiaAPIError",
    "ClaudiaConflictError",
    "ClaudiaRepo",
    "ClaudiaChat",
    "ClaudiaChatMessage",
    "ClaudiaPrompt",
    "ClaudiaQueueItem",
    "ClaudiaQueueState",
]
