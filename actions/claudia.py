"""
Claudia integration actions: chat with Claudia about codebases.

Enables natural conversations with Claudia to discuss features and
collaboratively design implementations before executing them.

Actions:
- list_claudia_repos: List Claudia-managed repositories
- create_claudia_chat: Start a conversation with Claudia about a repo
- list_claudia_chats: List chats for a repository
- get_claudia_chat: Get current chat state and messages
- send_claudia_message: Send a message in an active chat
- end_claudia_chat: End the chat session
- list_claudia_prompts: List prompts for a repository
- get_claudia_prompt: Get prompt details
- execute_claudia_prompt: Execute an existing prompt
- create_claudia_prompt: Generate prompt from a completed chat
- get_claudia_queue: See queue status for a repo
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_client():
    """Lazy import to avoid circular dependency and allow graceful failure."""
    from services.claudia_client import ClaudiaClient
    return ClaudiaClient()


def _claudia_error_response(
    exc: Exception,
    entity_type: str = "",
    entity_id: str = "",
) -> dict[str, Any]:
    """Convert a ClaudiaAPIError into a user-friendly response dict.

    Returns a dict with 'error' and optionally 'suggestion' keys,
    suitable for returning directly from action handlers.
    """
    from services.claudia_client import ClaudiaAPIError, ClaudiaConflictError

    detail = getattr(exc, "detail", str(exc))
    code = getattr(exc, "status_code", None)
    label = f"{entity_type} '{entity_id}'" if entity_id else entity_type

    if isinstance(exc, ClaudiaConflictError) or code == 409:
        return {
            "error": f"Conflict: {detail}",
            "suggestion": (
                f"This {entity_type or 'resource'} may already have an "
                "active operation. Check the queue status with claudiaQueueGet."
            ),
        }

    if code == 404:
        suggestions = {
            "chat": (
                "The chat may have been deleted or already converted to a "
                "prompt. You can create a new chat with claudiaChatCreate."
            ),
            "prompt": (
                "The prompt may have been removed. List available prompts "
                "with claudiaPromptList."
            ),
            "repo": (
                "Check available repositories with claudiaRepoList."
            ),
            "execution": (
                "The execution may have expired. List recent executions "
                "with claudiaExecutionList."
            ),
        }
        return {
            "error": f"{label or 'Resource'} not found: {detail}",
            "suggestion": suggestions.get(
                entity_type,
                "The resource was not found. It may have been deleted or expired.",
            ),
        }

    if code == 400:
        return {"error": f"Invalid request: {detail}"}

    if code and code >= 500:
        return {
            "error": f"Claudia is having trouble right now ({code}): {detail}",
            "suggestion": "Try again in a moment.",
        }

    return {"error": f"Claudia error: {detail}"}


async def list_claudia_repos_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List all Claudia-managed repositories.

    Returns repositories with their status and queue information.
    """
    from services.claudia_client import ClaudiaAPIError

    def fetch():
        client = _get_client()
        repos = client.list_repos()
        return [
            {
                "id": repo.id,
                "name": repo.name,
                "owner": repo.owner,
                "full_name": repo.full_name,
                "status": repo.status,
                "model": repo.model,
                "blocked_task_count": repo.blocked_task_count,
                "queued_prompt_id": repo.queued_prompt_id,
                "prompt_status": repo.prompt_status,
            }
            for repo in repos
        ]

    try:
        repos = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="repo")

    return {
        "message": f"Found {len(repos)} Claudia-managed repositories.",
        "count": len(repos),
        "repos": repos,
    }


async def create_claudia_chat_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start a conversation with Claudia about a repository.

    Args (in arguments dict):
        repo_name: Name of the repository (required)
        title: Chat title/topic (required)
        message: Initial message to start the conversation (optional)

    Returns:
        Chat session info including queue position.
    """
    args = arguments or {}
    repo_name = args.get("repo_name") or args.get("repo")
    title = args.get("title")
    initial_message = args.get("message")

    if not repo_name:
        raise ValueError("repo_name is required")
    if not title:
        raise ValueError("title is required")

    from services.claudia_client import ClaudiaAPIError

    def start():
        client = _get_client()

        # Find the repo by name
        repo = client.get_repo_by_name(repo_name)
        if not repo:
            repos = client.list_repos()
            available = ", ".join(r.name for r in repos[:10]) or "none"
            raise ValueError(
                f"Repository '{repo_name}' not found. "
                f"Available: {available}"
            )

        # Create the chat
        chat = client.create_chat(repo.id, title, initial_message)
        return repo, chat

    try:
        repo, chat = await asyncio.to_thread(start)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="repo", entity_id=repo_name)

    result: dict[str, Any] = {
        "repo": {
            "id": repo.id,
            "name": repo.name,
            "full_name": repo.full_name,
        },
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "status": chat.status,
            "queue_position": chat.queue_position,
            "created_at": chat.created_at,
        },
    }

    if chat.queue_position is not None and chat.queue_position > 0:
        result["message"] = (
            f"Started chat '{title}' about {repo.name}. "
            f"You're #{chat.queue_position} in the queue."
        )
    else:
        result["message"] = (
            f"Chat '{title}' about {repo.name} is active. "
            f"Claudia is ready to discuss."
        )

    return result


async def list_claudia_chats_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List chats for a repository.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        status: Filter by status (optional): active, completed, cancelled

    Returns:
        List of chats.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    status = args.get("status")

    if not repo_id:
        raise ValueError("repo_id is required")

    def fetch():
        client = _get_client()
        return client.list_chats(repo_id, status)

    try:
        chats = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="repo", entity_id=repo_id)

    return {
        "message": f"Found {len(chats)} chats.",
        "count": len(chats),
        "chats": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "message_count": c.message_count,
                "queue_position": c.queue_position,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in chats
        ],
    }


async def get_claudia_chat_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the current state of a chat with Claudia.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        chat_id: Chat ID (required)

    Returns:
        Chat session with all messages and current status.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    chat_id = args.get("chat_id")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not chat_id:
        raise ValueError("chat_id is required")

    def fetch():
        client = _get_client()
        return client.get_chat(repo_id, chat_id)

    try:
        chat = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="chat", entity_id=chat_id)

    status_messages = {
        "active": "Chat is active - Claudia is ready to respond.",
        "completed": "Chat has been completed.",
        "cancelled": "Chat was cancelled.",
    }

    return {
        "message": status_messages.get(
            chat.status, f"Chat status: {chat.status}"
        ),
        "chat": {
            "id": chat.id,
            "repo_id": chat.repo_id,
            "title": chat.title,
            "status": chat.status,
            "queue_position": chat.queue_position,
            "message_count": len(chat.messages),
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "prompt_id": chat.prompt_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                    "processed_at": m.processed_at,
                }
                for m in chat.messages
            ],
        },
    }


async def send_claudia_message_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send a message to Claudia in an active chat.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        chat_id: Chat ID (required)
        message: Message content to send (required)

    Returns:
        The created message.
    """
    args = arguments or {}
    repo_id = args.get("repo_id")
    chat_id = args.get("chat_id")
    message = args.get("message") or args.get("content")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not chat_id:
        raise ValueError("chat_id is required")
    if not message:
        raise ValueError("message is required")

    from services.claudia_client import ClaudiaAPIError

    def send():
        client = _get_client()
        return client.add_message(repo_id, chat_id, message)

    try:
        msg = await asyncio.to_thread(send)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="chat", entity_id=chat_id)

    return {
        "message": "Message sent. Claudia will process when chat is active.",
        "chat_message": {
            "id": msg.id,
            "chat_id": msg.chat_id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at,
        },
    }


async def end_claudia_chat_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    End a chat session with Claudia.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        chat_id: Chat ID (required)

    Returns:
        Final chat state.
    """
    args = arguments or {}
    repo_id = args.get("repo_id")
    chat_id = args.get("chat_id")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not chat_id:
        raise ValueError("chat_id is required")

    from services.claudia_client import ClaudiaAPIError

    def end():
        client = _get_client()
        return client.end_chat(repo_id, chat_id)

    try:
        chat = await asyncio.to_thread(end)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="chat", entity_id=chat_id)

    return {
        "message": f"Chat '{chat.title}' has been ended.",
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "status": chat.status,
            "message_count": chat.message_count,
            "updated_at": chat.updated_at,
        },
    }


async def list_claudia_prompts_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List all prompts for a repository.

    Args (in arguments dict):
        repo_id: Repository ID (required)

    Returns:
        List of prompts with their status.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")

    if not repo_id:
        raise ValueError("repo_id is required")

    def fetch():
        client = _get_client()
        return client.list_prompts(repo_id)

    try:
        prompts = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="repo", entity_id=repo_id)

    return {
        "message": f"Found {len(prompts)} prompts.",
        "count": len(prompts),
        "prompts": [
            {
                "id": p.id,
                "title": p.title,
                "status": p.status,
                "description": p.description,
                "blocked_by": p.blocked_by,
                "tags": p.tags,
                "created_at": p.created_at,
            }
            for p in prompts
        ],
    }


async def get_claudia_prompt_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get details of a specific prompt.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        prompt_id: Prompt ID (required)

    Returns:
        Prompt details including content.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    prompt_id = args.get("prompt_id")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not prompt_id:
        raise ValueError("prompt_id is required")

    def fetch():
        client = _get_client()
        return client.get_prompt(repo_id, prompt_id)

    try:
        prompt = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(
            exc, entity_type="prompt", entity_id=prompt_id,
        )

    return {
        "message": f"Prompt: {prompt.title}",
        "prompt": {
            "id": prompt.id,
            "title": prompt.title,
            "status": prompt.status,
            "description": prompt.description,
            "content": prompt.content,
            "blocked_by": prompt.blocked_by,
            "tags": prompt.tags,
            "created_at": prompt.created_at,
        },
    }


async def create_claudia_prompt_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Generate a NEW prompt from a completed chat conversation.

    This turns a chat discussion into a prompt file and queues execution.
    Requires chat_id. Do NOT use this to run an existing prompt — use
    execute_claudia_prompt_action for that.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        chat_id: ID of the completed chat (required)

    Returns:
        Queue item info for tracking.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    chat_id = args.get("chat_id")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not chat_id:
        raise ValueError("chat_id is required")

    def create():
        client = _get_client()

        try:
            chat = client.get_chat(repo_id, chat_id)
        except ClaudiaAPIError as exc:
            if exc.status_code == 404:
                return {
                    "error": (
                        f"Chat '{chat_id}' not found. It may have been "
                        "deleted or already converted to a prompt."
                    ),
                    "suggestion": (
                        "You can create a new chat with claudiaChatCreate."
                    ),
                }
            raise

        if chat.prompt_id:
            return {
                "error": (
                    f"A prompt was already generated from this chat: "
                    f"{chat.prompt_id}"
                ),
                "suggestion": (
                    f"Use claudiaPromptGet or claudiaPromptExecute with "
                    f"prompt_id '{chat.prompt_id}' instead."
                ),
            }

        if chat.status == "active":
            return {
                "error": (
                    "Chat is still active. End the chat first before "
                    "creating a prompt."
                ),
                "suggestion": (
                    "Call claudiaChatEnd to finish the conversation, then "
                    "retry claudiaPromptCreate."
                ),
            }

        return client.create_prompt_from_chat(repo_id, chat_id)

    try:
        result = await asyncio.to_thread(create)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="chat", entity_id=chat_id)

    if "error" in result:
        return result

    queue_pos = result.get("queuePosition", 0)
    return {
        "message": f"Prompt generation queued at position {queue_pos}.",
        "queue_item_id": result.get("queueItemId"),
        "queue_position": queue_pos,
        "chat_id": result.get("chatId"),
    }


async def execute_claudia_prompt_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute an existing prompt from the repo's prompts/ directory.

    Queues the prompt for direct execution by Claude. Call
    claudiaPromptList first to find available prompt IDs.

    Args (in arguments dict):
        repo_id: Repository ID (required)
        prompt_id: Prompt ID to execute (required)

    Returns:
        Queue item info for tracking.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    prompt_id = args.get("prompt_id")

    if not repo_id:
        raise ValueError("repo_id is required")
    if not prompt_id:
        raise ValueError("prompt_id is required")

    def execute():
        client = _get_client()

        try:
            prompt = client.get_prompt(repo_id, prompt_id)
        except ClaudiaAPIError as exc:
            if exc.status_code == 404:
                prompts = client.list_prompts(repo_id)
                available = ", ".join(
                    f"{p.id} ({p.title})" for p in prompts[:10]
                ) or "none"
                return {
                    "error": (
                        f"Prompt '{prompt_id}' not found in this repository."
                    ),
                    "available_prompts": available,
                    "suggestion": (
                        "List available prompts with claudiaPromptList."
                    ),
                }
            raise

        if prompt.status != "ready":
            return {
                "error": (
                    f"Prompt '{prompt.title}' has status '{prompt.status}'. "
                    f"Only 'ready' prompts can be executed."
                ),
            }
        if prompt.blocked_by:
            return {
                "error": (
                    f"Prompt '{prompt.title}' is blocked by "
                    f"'{prompt.blocked_by}'. Resolve that first."
                ),
            }

        return client.execute_prompt(repo_id, prompt_id)

    try:
        result = await asyncio.to_thread(execute)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(
            exc, entity_type="prompt", entity_id=prompt_id,
        )

    if "error" in result:
        return result

    queue_pos = result.get("queuePosition", 0)
    return {
        "message": f"Prompt execution queued at position {queue_pos}.",
        "queue_item_id": result.get("queueItemId"),
        "queue_position": queue_pos,
        "prompt_id": result.get("promptId"),
    }


async def list_claudia_executions_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List executions with optional filters.

    Args (in arguments dict):
        repo_id: Filter by repository (optional)
        status: Filter by status (optional)
        limit: Max results (optional, default 50)

    Returns:
        List of executions.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")
    status = args.get("status")
    limit = args.get("limit", 50)

    def fetch():
        client = _get_client()
        return client.list_executions(repo_id, status, limit)

    try:
        executions = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="execution")

    return {
        "message": f"Found {len(executions)} executions.",
        "count": len(executions),
        "executions": executions,
    }


async def get_claudia_execution_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get execution details.

    Returns full details including prompt, output, git diff, and costs.

    Args (in arguments dict):
        execution_id: Execution ID (required)

    Returns:
        Execution details.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    execution_id = args.get("execution_id")

    if not execution_id:
        raise ValueError("execution_id is required")

    def fetch():
        client = _get_client()
        return client.get_execution(execution_id)

    try:
        execution = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(
            exc, entity_type="execution", entity_id=execution_id,
        )

    status = execution.get("status", "unknown")
    return {
        "message": f"Execution status: {status}",
        "execution": execution,
    }


async def get_claudia_queue_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get the queue status for a repository.

    Shows pending and active tasks.

    Args (in arguments dict):
        repo_id: Repository ID (required)

    Returns:
        Queue status including pending tasks and active work.
    """
    from services.claudia_client import ClaudiaAPIError

    args = arguments or {}
    repo_id = args.get("repo_id")

    if not repo_id:
        raise ValueError("repo_id is required")

    def fetch():
        client = _get_client()
        return client.get_queue_state(repo_id)

    try:
        queue = await asyncio.to_thread(fetch)
    except ClaudiaAPIError as exc:
        return _claudia_error_response(exc, entity_type="repo", entity_id=repo_id)

    if queue.depth == 0 and not queue.active_item:
        message = "Queue is empty. Any new work will start immediately."
    else:
        parts = []
        if queue.active_item:
            parts.append(
                f"Active: {queue.active_item.item_type} "
                f"({queue.active_item.title or queue.active_item.item_id})"
            )
        if queue.depth > 0:
            parts.append(f"{queue.depth} items waiting")
        message = ". ".join(parts)

    return {
        "message": message,
        "queue": {
            "depth": queue.depth,
            "estimated_wait_minutes": queue.estimated_wait_minutes,
            "active_item": {
                "id": queue.active_item.id,
                "type": queue.active_item.item_type,
                "item_id": queue.active_item.item_id,
                "title": queue.active_item.title,
                "status": queue.active_item.status,
                "started_at": queue.active_item.started_at,
            } if queue.active_item else None,
            "items": [
                {
                    "id": item.id,
                    "type": item.item_type,
                    "item_id": item.item_id,
                    "title": item.title,
                    "position": item.position,
                    "status": item.status,
                    "created_at": item.created_at,
                }
                for item in queue.items
            ],
        },
    }


async def api_learn_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Learn how to use Claudia (AI coding assistant).

    Call this FIRST to understand how to have coding conversations with
    Claudia about repositories and execute prompts.
    """
    # Get available repos dynamically
    try:
        client = _get_client()
        repos = client.list_repos()
        repo_list = [
            {"name": r.name, "full_name": r.full_name, "id": r.id}
            for r in repos[:10]
        ]
    except Exception:
        repo_list = []

    return {
        "overview": (
            "Claudia is an AI coding assistant that can discuss features, "
            "review code, and implement changes across your repositories. "
            "Use chats for design discussions, then create prompts for "
            "actual code changes."
        ),
        "workflow_chat_to_code": [
            "1. claudiaRepoList - See available repositories",
            "2. claudiaChatCreate - Start a conversation about a feature",
            "3. claudiaChatSend - Discuss and refine the approach",
            "4. claudiaChatEnd - Finish the conversation",
            "5. claudiaPromptCreate - Generate prompt from chat (requires chat_id)",
            "6. claudiaExecutionGet - Monitor the result",
        ],
        "workflow_execute_existing_prompt": [
            "1. claudiaRepoList - Find the repo",
            "2. claudiaPromptList - See available prompts for that repo",
            "3. claudiaPromptGet - (optional) Inspect prompt content before executing",
            "4. claudiaPromptExecute - Execute the prompt (requires prompt_id)",
            "5. claudiaExecutionGet - Monitor the result",
        ],
        "operations": {
            "claudiaRepoList": "List all Claudia-managed repositories",
            "claudiaChatCreate": "Start chat (repo_name, title, message?)",
            "claudiaChatList": "List chats for a repo (repo_id, status?). Find active or completed chats.",
            "claudiaChatGet": "Get chat with all messages (repo_id, chat_id)",
            "claudiaChatSend": "Send message (repo_id, chat_id, message)",
            "claudiaChatEnd": "End chat (repo_id, chat_id)",
            "claudiaPromptList": "List prompts for a repo (repo_id)",
            "claudiaPromptGet": "Get prompt details + content (repo_id, prompt_id)",
            "claudiaPromptCreate": "Generate NEW prompt from completed chat (repo_id, chat_id)",
            "claudiaPromptExecute": "Execute EXISTING prompt file (repo_id, prompt_id)",
            "claudiaQueueGet": "Check queue status (repo_id)",
            "claudiaExecutionList": "List executions (repo_id?, status?, limit?). Find execution_ids to pass to claudiaExecutionGet.",
            "claudiaExecutionGet": "Get execution result (execution_id). Shows output, git diff, costs.",
        },
        "important": {
            "claudiaPromptCreate_vs_Execute": (
                "PromptCreate generates a NEW prompt from a chat conversation. "
                "PromptExecute runs an EXISTING prompt file from the repo. "
                "When user says 'execute prompt X', use PromptExecute. "
                "When user says 'turn this chat into code', use PromptCreate."
            ),
        },
        "available_repos": repo_list,
        "tips": [
            "Start with a clear feature description in the chat title",
            "Discuss edge cases and constraints before ending chat",
            "Check queue position - repos process one task at a time",
            "Executions include git diffs and cost tracking",
        ],
    }


__all__ = [
    "api_learn_action",
    "list_claudia_repos_action",
    "create_claudia_chat_action",
    "list_claudia_chats_action",
    "get_claudia_chat_action",
    "send_claudia_message_action",
    "end_claudia_chat_action",
    "list_claudia_prompts_action",
    "get_claudia_prompt_action",
    "create_claudia_prompt_action",
    "execute_claudia_prompt_action",
    "list_claudia_executions_action",
    "get_claudia_execution_action",
    "get_claudia_queue_action",
]
