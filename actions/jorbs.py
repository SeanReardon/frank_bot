"""
Jorb actions: create, list, get, and manage long-lived autonomous tasks.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from services.agent_runner import AgentRunner
from services.jorb_storage import JorbContact, JorbStorage

logger = logging.getLogger(__name__)


def _parse_contacts(contacts_arg: Any) -> list[JorbContact]:
    """
    Parse contacts from action arguments.

    Accepts either a JSON string or a list of contact dicts.
    Each contact must have:
        - identifier: str (phone number, username, email)
        - channel: str (sms, telegram, email)
        - name: str (optional)
    """
    if not contacts_arg:
        return []

    # If it's a string, try to parse as JSON
    if isinstance(contacts_arg, str):
        try:
            contacts_data = json.loads(contacts_arg)
        except json.JSONDecodeError as e:
            raise ValueError(f"contacts must be valid JSON: {e}")
    else:
        contacts_data = contacts_arg

    if not isinstance(contacts_data, list):
        raise ValueError("contacts must be an array of contact objects")

    contacts = []
    for i, c in enumerate(contacts_data):
        if not isinstance(c, dict):
            raise ValueError(f"contact[{i}] must be an object")
        if "identifier" not in c:
            raise ValueError(f"contact[{i}] missing 'identifier' field")
        if "channel" not in c:
            raise ValueError(f"contact[{i}] missing 'channel' field")
        if c["channel"] not in ("sms", "telegram", "email"):
            raise ValueError(f"contact[{i}] has invalid channel: {c['channel']}")

        contacts.append(JorbContact(
            identifier=c["identifier"],
            channel=c["channel"],
            name=c.get("name"),
        ))

    return contacts


async def create_jorb_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a new jorb (long-lived autonomous task).

    Args:
        arguments: Dict with keys:
            - name: str (required) - Human-readable name for the task
            - plan: str (required) - Full plan text describing what to do
            - contacts: JSON array (optional) - Contacts involved in the task
                Each contact: {identifier, channel, name?}
            - start_immediately: bool (optional, default True) - Whether to kick off immediately

    Returns:
        Dict with created jorb details
    """
    args = arguments or {}
    name = (args.get("name") or "").strip()
    plan = (args.get("plan") or "").strip()
    contacts_arg = args.get("contacts")
    start_immediately = args.get("start_immediately", True)

    # Handle string "false" / "true" values
    if isinstance(start_immediately, str):
        start_immediately = start_immediately.lower() not in ("false", "0", "no")

    if not name:
        raise ValueError("name is required")
    if not plan:
        raise ValueError("plan is required")

    # Parse contacts
    contacts = _parse_contacts(contacts_arg)

    # Create the jorb
    storage = JorbStorage()
    jorb = await storage.create_jorb(
        name=name,
        plan=plan,
        contacts=contacts,
    )

    logger.info("Created jorb %s: %s", jorb.id, jorb.name)

    # Kick off if requested
    kickoff_result = None
    if start_immediately:
        runner = AgentRunner(storage=storage)
        if runner.is_configured:
            result = await runner.kickoff_jorb(jorb)
            kickoff_result = {
                "success": result.success,
                "action_taken": result.action_taken,
                "message_sent": result.message_sent,
            }
            if result.error:
                kickoff_result["error"] = result.error

            # Refresh jorb to get updated status
            jorb = await storage.get_jorb(jorb.id)
        else:
            kickoff_result = {
                "success": False,
                "error": "AgentRunner not configured (missing OPENAI_API_KEY)",
            }

    response = {
        "jorb_id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "plan": jorb.original_plan,
        "contacts": [c.to_dict() for c in jorb.contacts],
        "created_at": jorb.created_at,
    }

    if kickoff_result:
        response["kickoff"] = kickoff_result

    return response


async def list_jorbs_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List jorbs with optional status filter.

    Args:
        arguments: Dict with optional keys:
            - status: str - Filter by "open", "closed", or "all" (default "open")

    Returns:
        Dict with count and jorbs array
    """
    args = arguments or {}
    status_filter = args.get("status", "open")

    if status_filter not in ("open", "closed", "all"):
        raise ValueError("status must be 'open', 'closed', or 'all'")

    storage = JorbStorage()
    jorbs = await storage.list_jorbs(status_filter=status_filter)

    result_jorbs = []
    for jorb in jorbs:
        jorb_data = {
            "jorb_id": jorb.id,
            "name": jorb.name,
            "status": jorb.status,
            "created_at": jorb.created_at,
            "updated_at": jorb.updated_at,
        }
        if jorb.progress_summary:
            jorb_data["progress"] = jorb.progress_summary
        if jorb.awaiting:
            jorb_data["awaiting"] = jorb.awaiting
        if jorb.paused_reason:
            jorb_data["paused_reason"] = jorb.paused_reason

        result_jorbs.append(jorb_data)

    return {
        "count": len(result_jorbs),
        "status_filter": status_filter,
        "jorbs": result_jorbs,
    }


async def get_jorb_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get full details for a specific jorb.

    Args:
        arguments: Dict with keys:
            - jorb_id: str (required) - The jorb ID
            - include_messages: bool (optional) - Include message history
            - message_limit: int (optional) - Max messages to include (default 50)

    Returns:
        Dict with full jorb details and optionally messages
    """
    args = arguments or {}
    jorb_id = (args.get("jorb_id") or "").strip()
    include_messages = args.get("include_messages", False)
    message_limit = args.get("message_limit", 50)

    if isinstance(include_messages, str):
        include_messages = include_messages.lower() in ("true", "1", "yes")

    if isinstance(message_limit, str):
        try:
            message_limit = int(message_limit)
        except ValueError:
            message_limit = 50

    message_limit = max(1, min(1000, message_limit))

    if not jorb_id:
        raise ValueError("jorb_id is required")

    storage = JorbStorage()
    jorb = await storage.get_jorb(jorb_id)

    if not jorb:
        raise ValueError(f"Jorb not found: {jorb_id}")

    response = {
        "jorb_id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "plan": jorb.original_plan,
        "progress_summary": jorb.progress_summary,
        "contacts": [c.to_dict() for c in jorb.contacts],
        "created_at": jorb.created_at,
        "updated_at": jorb.updated_at,
        "paused_reason": jorb.paused_reason,
        "needs_approval_for": jorb.needs_approval_for,
        "awaiting": jorb.awaiting,
    }

    if include_messages:
        messages = await storage.get_messages(jorb_id, limit=message_limit)
        response["messages"] = [
            {
                "id": msg.id,
                "timestamp": msg.timestamp,
                "direction": msg.direction,
                "channel": msg.channel,
                "sender": msg.sender,
                "sender_name": msg.sender_name,
                "recipient": msg.recipient,
                "content": msg.content,
                "agent_reasoning": msg.agent_reasoning,
            }
            for msg in messages
        ]
        response["message_count"] = len(messages)

    return response


async def get_jorb_messages_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get message history for a jorb.

    Args:
        arguments: Dict with keys:
            - jorb_id: str (required) - The jorb ID
            - limit: int (optional) - Max messages (default 50)
            - offset: int (optional) - Skip first N messages (default 0)

    Returns:
        Dict with messages array
    """
    args = arguments or {}
    jorb_id = (args.get("jorb_id") or "").strip()
    limit = args.get("limit", 50)
    offset = args.get("offset", 0)

    if isinstance(limit, str):
        try:
            limit = int(limit)
        except ValueError:
            limit = 50

    if isinstance(offset, str):
        try:
            offset = int(offset)
        except ValueError:
            offset = 0

    limit = max(1, min(1000, limit))
    offset = max(0, offset)

    if not jorb_id:
        raise ValueError("jorb_id is required")

    storage = JorbStorage()
    jorb = await storage.get_jorb(jorb_id)

    if not jorb:
        raise ValueError(f"Jorb not found: {jorb_id}")

    # Fetch messages with offset+limit to allow pagination
    # Note: JorbStorage.get_messages doesn't have offset, so we fetch more and slice
    all_messages = await storage.get_messages(jorb_id, limit=offset + limit)
    messages = all_messages[offset:offset + limit]

    return {
        "jorb_id": jorb_id,
        "jorb_name": jorb.name,
        "count": len(messages),
        "offset": offset,
        "limit": limit,
        "messages": [
            {
                "id": msg.id,
                "timestamp": msg.timestamp,
                "direction": msg.direction,
                "channel": msg.channel,
                "sender": msg.sender,
                "sender_name": msg.sender_name,
                "recipient": msg.recipient,
                "content": msg.content,
                "agent_reasoning": msg.agent_reasoning,
            }
            for msg in messages
        ],
    }


__all__ = [
    "create_jorb_action",
    "list_jorbs_action",
    "get_jorb_action",
    "get_jorb_messages_action",
]
