"""
Jorb actions: create, list, get, and manage long-lived autonomous tasks.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from services.agent_runner import AgentRunner
from services.jorb_storage import Jorb, JorbContact, JorbMessage, JorbStorage

logger = logging.getLogger(__name__)

# State file path for tracking briefing timestamps
_BRIEFING_STATE_FILE = os.path.join(
    os.getenv("JORBS_DATA_DIR", "./data"),
    "briefing_state.json"
)


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
            - personality: str (optional, default "default") - Personality ID for LLM sessions
                Available: "default", "concierge", "researcher", "negotiator", "expeditor"
            - start_immediately: bool (optional, default True) - Whether to kick off immediately

    Returns:
        Dict with created jorb details
    """
    args = arguments or {}
    name = (args.get("name") or "").strip()
    plan = (args.get("plan") or "").strip()
    contacts_arg = args.get("contacts")
    personality = (args.get("personality") or "default").strip().lower()
    start_immediately = args.get("start_immediately", True)

    # Handle string "false" / "true" values
    if isinstance(start_immediately, str):
        start_immediately = start_immediately.lower() not in ("false", "0", "no")

    if not name:
        raise ValueError("name is required")
    if not plan:
        raise ValueError("plan is required")

    # Validate personality exists
    from services.personality_loader import get_personality_loader
    loader = get_personality_loader()
    available_personalities = loader.list_ids()
    if personality not in available_personalities and personality != "default":
        logger.warning(
            "Personality '%s' not found, available: %s. Using 'default'.",
            personality, available_personalities
        )
        personality = "default"

    # Parse contacts
    contacts = _parse_contacts(contacts_arg)

    # Create the jorb
    storage = JorbStorage()
    jorb = await storage.create_jorb(
        name=name,
        plan=plan,
        contacts=contacts,
        personality=personality,
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
        "personality": jorb.personality,
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
            "personality": jorb.personality,
            "created_at": jorb.created_at,
            "updated_at": jorb.updated_at,
            "metrics": jorb.metrics,
        }
        if jorb.progress_summary:
            jorb_data["progress"] = jorb.progress_summary
        if jorb.awaiting:
            jorb_data["awaiting"] = jorb.awaiting
        if jorb.paused_reason:
            jorb_data["paused_reason"] = jorb.paused_reason
        # Include outcome for completed/failed jorbs
        if jorb.outcome:
            jorb_data["outcome"] = jorb.outcome

        result_jorbs.append(jorb_data)

    # Get aggregate metrics for this filter
    aggregate_metrics = await storage.get_aggregate_metrics(status_filter=status_filter)

    return {
        "count": len(result_jorbs),
        "status_filter": status_filter,
        "jorbs": result_jorbs,
        "aggregate_metrics": aggregate_metrics,
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
        "personality": jorb.personality,
        "progress_summary": jorb.progress_summary,
        "contacts": [c.to_dict() for c in jorb.contacts],
        "created_at": jorb.created_at,
        "updated_at": jorb.updated_at,
        "paused_reason": jorb.paused_reason,
        "needs_approval_for": jorb.needs_approval_for,
        "awaiting": jorb.awaiting,
        "metrics": jorb.metrics,
    }

    # Include outcome for completed/failed jorbs
    if jorb.outcome:
        response["outcome"] = jorb.outcome

    # Include checkpoints
    checkpoints = await storage.get_checkpoints(jorb_id)
    if checkpoints:
        response["checkpoints"] = [
            {
                "id": cp.id,
                "timestamp": cp.timestamp,
                "summary": cp.summary,
                "token_count": cp.token_count,
            }
            for cp in checkpoints
        ]

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


async def approve_jorb_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Approve a paused or planning jorb to start/resume processing.

    For "planning" jorbs (created with start_immediately=False), this kicks off
    the jorb by sending its first message.

    For "paused" jorbs, this resumes processing with the provided decision.

    Args:
        arguments: Dict with keys:
            - jorb_id: str (required) - The jorb ID
            - decision: str (required) - The approval decision/instructions

    Returns:
        Dict with updated jorb status and kickoff result
    """
    args = arguments or {}
    jorb_id = (args.get("jorb_id") or "").strip()
    decision = (args.get("decision") or "").strip()

    if not jorb_id:
        raise ValueError("jorb_id is required")
    if not decision:
        raise ValueError("decision is required")

    storage = JorbStorage()
    jorb = await storage.get_jorb(jorb_id)

    if not jorb:
        raise ValueError(f"Jorb not found: {jorb_id}")

    if jorb.status not in ("paused", "planning"):
        raise ValueError(f"Jorb must be paused or planning to approve (current status: {jorb.status})")

    # Record the approval/start in progress summary
    previous_summary = jorb.progress_summary or ""
    was_planning = jorb.status == "planning"
    if was_planning:
        approval_note = f"Started with instructions: {decision}"
    else:
        approval_note = f"Approved: {decision}"
    new_summary = f"{previous_summary}\n{approval_note}".strip()

    # Update jorb: status to running, clear pause fields
    jorb = await storage.update_jorb(
        jorb_id,
        status="running",
        progress_summary=new_summary,
        paused_reason=None,
        needs_approval_for=None,
    )

    if was_planning:
        logger.info("Started jorb %s with instructions: %s", jorb_id, decision)
    else:
        logger.info("Approved jorb %s with decision: %s", jorb_id, decision)

    # Trigger the agent to process the approval
    kickoff_result = None
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

        # Refresh jorb to get latest status
        jorb = await storage.get_jorb(jorb_id)
    else:
        kickoff_result = {
            "success": False,
            "error": "AgentRunner not configured (missing OPENAI_API_KEY)",
        }

    response = {
        "jorb_id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "progress_summary": jorb.progress_summary,
        "decision": decision,
        "updated_at": jorb.updated_at,
    }

    if kickoff_result:
        response["agent_result"] = kickoff_result

    return response


async def cancel_jorb_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Cancel a jorb.

    Args:
        arguments: Dict with keys:
            - jorb_id: str (required) - The jorb ID
            - reason: str (optional) - Reason for cancellation

    Returns:
        Dict with updated jorb status
    """
    args = arguments or {}
    jorb_id = (args.get("jorb_id") or "").strip()
    reason = (args.get("reason") or "").strip()

    if not jorb_id:
        raise ValueError("jorb_id is required")

    storage = JorbStorage()
    jorb = await storage.get_jorb(jorb_id)

    if not jorb:
        raise ValueError(f"Jorb not found: {jorb_id}")

    # Cannot cancel already complete or cancelled jorbs
    if jorb.status in ("complete", "cancelled"):
        raise ValueError(f"Cannot cancel jorb with status: {jorb.status}")

    # Record cancellation in progress summary
    previous_summary = jorb.progress_summary or ""
    cancel_note = f"Cancelled: {reason}" if reason else "Cancelled by user"
    new_summary = f"{previous_summary}\n{cancel_note}".strip()

    # Update jorb status to cancelled
    jorb = await storage.update_jorb(
        jorb_id,
        status="cancelled",
        progress_summary=new_summary,
        paused_reason=None,
        needs_approval_for=None,
    )

    logger.info("Cancelled jorb %s: %s", jorb_id, reason or "no reason given")

    return {
        "jorb_id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "progress_summary": jorb.progress_summary,
        "reason": reason or None,
        "updated_at": jorb.updated_at,
    }


async def get_jorbs_stats_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get aggregate statistics for jorbs.

    Args:
        arguments: Dict with optional keys:
            - status: str - Filter by "open", "closed", or "all" (default "all")

    Returns:
        Dict with aggregate metrics and status counts
    """
    args = arguments or {}
    status_filter = args.get("status", "all")

    if status_filter not in ("open", "closed", "all"):
        raise ValueError("status must be 'open', 'closed', or 'all'")

    storage = JorbStorage()
    aggregate = await storage.get_aggregate_metrics(status_filter=status_filter)

    # Calculate success rate
    completed = aggregate["by_status"].get("complete", 0)
    failed = aggregate["by_status"].get("failed", 0)
    total_finished = completed + failed
    success_rate = (completed / total_finished * 100) if total_finished > 0 else 0

    return {
        "status_filter": status_filter,
        "total_jorbs": aggregate["total_jorbs"],
        "by_status": aggregate["by_status"],
        "metrics": {
            "total_messages": aggregate["total_messages"],
            "total_messages_in": aggregate["total_messages_in"],
            "total_messages_out": aggregate["total_messages_out"],
            "total_tokens": aggregate["total_tokens"],
            "total_cost": round(aggregate["total_cost"], 4),
            "total_context_resets": aggregate["total_context_resets"],
        },
        "success_rate": round(success_rate, 1),
    }


def _get_last_briefing_timestamp() -> str | None:
    """Read the last briefing timestamp from state file."""
    try:
        if os.path.exists(_BRIEFING_STATE_FILE):
            with open(_BRIEFING_STATE_FILE, "r") as f:
                state = json.load(f)
                return state.get("last_briefing_timestamp")
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Error reading briefing state: %s", e)
    return None


def _save_last_briefing_timestamp(timestamp: str) -> None:
    """Save the last briefing timestamp to state file."""
    try:
        os.makedirs(os.path.dirname(_BRIEFING_STATE_FILE), exist_ok=True)
        with open(_BRIEFING_STATE_FILE, "w") as f:
            json.dump({"last_briefing_timestamp": timestamp}, f)
    except OSError as e:
        logger.warning("Error saving briefing state: %s", e)


def _format_jorb_activity(
    jorb: Jorb,
    messages: list[JorbMessage],
    since: str | None,
) -> dict[str, Any]:
    """Format a jorb's activity since the given timestamp."""
    # Filter messages since last briefing
    if since:
        messages = [m for m in messages if m.timestamp > since]

    return {
        "jorb_id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "message_count": len(messages),
        "recent_messages": [
            {
                "timestamp": m.timestamp,
                "direction": m.direction,
                "content": m.content[:100] + "..." if len(m.content) > 100 else m.content,
            }
            for m in messages[-5:]  # Last 5 messages
        ],
        "awaiting": jorb.awaiting,
    }


async def brief_me_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Get an activity summary since the last briefing.

    This action is designed for ChatGPT to quickly catch up on jorb status.

    Args:
        arguments: Dict with optional keys:
            - hours: int (optional) - Only show activity from last N hours (default: 24)
            - update_timestamp: bool (optional) - Update last briefing timestamp (default: True)

    Returns:
        Dict with needs_attention, activity_summary, highlights, pending_decisions
    """
    args = arguments or {}
    hours = args.get("hours", 24)
    update_timestamp = args.get("update_timestamp", True)

    if isinstance(hours, str):
        try:
            hours = int(hours)
        except ValueError:
            hours = 24

    if isinstance(update_timestamp, str):
        update_timestamp = update_timestamp.lower() in ("true", "1", "yes")

    hours = max(1, min(168, hours))  # Between 1 hour and 1 week

    storage = JorbStorage()

    # Get the last briefing timestamp
    last_briefing = _get_last_briefing_timestamp()

    # Also consider the hours parameter for filtering
    hours_ago = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    since_timestamp = hours_ago
    if last_briefing and last_briefing > hours_ago:
        since_timestamp = last_briefing

    # Get all jorbs
    all_jorbs = await storage.list_jorbs(status_filter="all")

    # Separate by status
    paused_jorbs = [j for j in all_jorbs if j.status == "paused"]
    active_jorbs = [j for j in all_jorbs if j.status in ("running", "planning")]
    recently_completed = []
    for j in all_jorbs:
        if j.status == "complete" and j.updated_at > since_timestamp:
            recently_completed.append(j)

    # Build activity summary for each active/paused jorb
    activity_summary = []
    for jorb in active_jorbs + paused_jorbs:
        messages = await storage.get_messages(jorb.id, limit=100)
        activity = _format_jorb_activity(jorb, messages, since_timestamp)
        if activity["message_count"] > 0 or jorb.status == "paused":
            activity_summary.append(activity)

    # Build highlights
    highlights = []

    # Completed jorbs
    for jorb in recently_completed:
        highlights.append(f"Completed: {jorb.name}")

    # Count total messages in period
    total_messages = sum(a["message_count"] for a in activity_summary)
    if total_messages > 0:
        highlights.append(f"{total_messages} messages exchanged")

    # Build pending decisions
    pending_decisions = []
    for jorb in paused_jorbs:
        pending_decisions.append({
            "jorb_id": jorb.id,
            "name": jorb.name,
            "paused_reason": jorb.paused_reason,
            "needs_approval_for": jorb.needs_approval_for,
            "options": ["approve", "cancel"],
        })

    # Update briefing timestamp if requested
    current_time = datetime.now(timezone.utc).isoformat()
    if update_timestamp:
        _save_last_briefing_timestamp(current_time)

    # Get aggregate metrics
    aggregate = await storage.get_aggregate_metrics(status_filter="all")

    return {
        "briefing_time": current_time,
        "since": since_timestamp,
        "last_briefing": last_briefing,
        "needs_attention": len(paused_jorbs),
        "activity_summary": activity_summary,
        "highlights": highlights,
        "pending_decisions": pending_decisions,
        "total_open_jorbs": len(active_jorbs) + len(paused_jorbs),
        "recently_completed": len(recently_completed),
        "aggregate_metrics": {
            "total_jorbs": aggregate["total_jorbs"],
            "total_messages": aggregate["total_messages"],
            "total_cost": round(aggregate["total_cost"], 4),
            "by_status": aggregate["by_status"],
        },
    }


async def api_learn_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Learn how to use the Jorbs system.

    Call this FIRST to understand how jorbs (autonomous tasks) work.
    Returns comprehensive documentation about creating, managing, and
    monitoring long-running tasks that Frank executes autonomously.
    """
    return {
        "overview": (
            "Jorbs are long-running autonomous tasks Frank executes via "
            "SMS, Telegram, or email. Frank sends messages, waits for "
            "replies, and pauses for approval on spending or commitments."
        ),
        "lifecycle": {
            "planning": "Initial state after creation",
            "running": "Frank is actively working on the task",
            "paused": "Waiting for approval (spending, booking, etc.)",
            "complete": "Task finished successfully",
            "failed": "Task encountered an unrecoverable error",
            "cancelled": "You cancelled the task",
        },
        "create_jorb": {
            "description": "Start a new autonomous task",
            "required_params": {
                "name": "Human-readable task name",
                "plan": "Instructions with budget and pause rules",
            },
            "optional_params": {
                "contacts": "Array of people to contact",
                "personality": "LLM personality (default, concierge)",
                "start_immediately": "Begin right away (default: true)",
            },
            "contacts_format": [
                {"identifier": "@user", "channel": "telegram", "name": "Jo"},
                {"identifier": "+15551234567", "channel": "sms"},
                {"identifier": "email@example.com", "channel": "email"},
            ],
        },
        "personalities": {
            "default": "Balanced, helpful assistant",
            "concierge": "Luxury service, formal tone",
            "researcher": "Thorough, detail-oriented",
            "negotiator": "Deal-focused, persistent",
            "expeditor": "Fast, action-oriented",
            "sean-voice": "Sean's personal communication style",
        },
        "auto_pause_rules": [
            "Spending over $100 requires approval",
            "Making reservations or bookings",
            "Cancelling existing appointments",
            "Sharing sensitive information",
            "Any significant commitment",
        ],
        "plan_tips": [
            "Include clear budget limits: 'budget up to $200'",
            "Specify pause points: 'pause before booking anything'",
            "Define success criteria: 'done when reservation confirmed'",
            "List fallback options if first choice unavailable",
        ],
        "operations": {
            "jorbCreate": "Start a new task with name, plan, contacts",
            "jorbGet": "Get full details including messages, checkpoints",
            "jorbBriefGet": "Quick overview of all activity + pending decisions",
            "jorbApprove": "Approve/reject a paused task's pending action",
            "jorbCancel": "Stop a task (with optional reason)",
        },
        "example_plan": (
            "Book dinner for 4 at a nice Italian restaurant in Dallas "
            "for Saturday 7pm. Budget $50-80/person. Try Carbone first, "
            "then Lucia, then Filament. Pause before confirming any "
            "reservation. Text me the options you find."
        ),
    }


__all__ = [
    "api_learn_action",
    "create_jorb_action",
    "list_jorbs_action",
    "get_jorb_action",
    "get_jorb_messages_action",
    "approve_jorb_action",
    "cancel_jorb_action",
    "brief_me_action",
    "get_jorbs_stats_action",
]
