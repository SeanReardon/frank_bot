from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import get_settings
from services.android_task_storage import get_android_task_storage
from services.background_loop import get_background_loop_status
from services.event_traces import get_event_trace_store
from services.jorb_storage import JorbMessage, JorbStorage
from services.stats import stats
from services.switchboard import SWITCHBOARD_MODEL
from services.telegram_bot_router import get_bot_router_status
from services.telegram_jorb_router import get_router_status


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_dict(
    message: JorbMessage,
    jorb_id: str,
    jorb_name: str,
    task_class: str,
) -> dict[str, Any]:
    return {
        "timestamp": message.timestamp,
        "jorb_id": jorb_id,
        "jorb_name": jorb_name,
        "task_class": task_class,
        "direction": message.direction,
        "channel": message.channel,
        "sender": message.sender,
        "sender_name": message.sender_name,
        "recipient": message.recipient,
        "content": message.content,
        "agent_reasoning": message.agent_reasoning,
    }


async def get_operator_debug_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured operator/debug snapshot optimized for humans and agents."""
    args = arguments or {}
    limit = max(1, min(100, int(args.get("limit", 20) or 20)))

    settings = get_settings()
    storage = JorbStorage()
    trace_store = get_event_trace_store()
    android_storage = get_android_task_storage()

    all_jorbs = await storage.list_jorbs(status_filter="all")
    recent_messages: list[dict[str, Any]] = []
    recent_script_results: list[dict[str, Any]] = []

    for jorb in all_jorbs[:limit]:
        for message in await storage.get_messages(jorb.id, limit=15):
            recent_messages.append(
                _message_dict(
                    message,
                    jorb.id,
                    jorb.name,
                    jorb.task_class,
                )
            )
        for result in (jorb.script_results or [])[-10:]:
            recent_script_results.append(
                {
                    "jorb_id": jorb.id,
                    "jorb_name": jorb.name,
                    "task_class": jorb.task_class,
                    "timestamp": result.get("timestamp"),
                    "script": result.get("script"),
                    "success": result.get("success"),
                    "result": result.get("result"),
                }
            )

    recent_messages.sort(
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )
    recent_script_results.sort(
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )

    android_tasks = [
        task.to_dict()
        for task in await android_storage.list_tasks(limit=limit)
    ]
    aggregate_metrics = await storage.get_aggregate_metrics(status_filter="all")
    recent_traces = await trace_store.list_recent_traces(limit=limit)
    recent_events = await trace_store.list_recent_events(limit=limit)
    all_stats = stats.get_all_stats()
    background = get_background_loop_status()
    telegram_router = get_router_status()
    telegram_bot_router = get_bot_router_status()

    last_errors = {
        "background_loop": background.get("crash_error"),
        "telegram_router": telegram_router.get("last_error"),
        "telegram_bot_router": telegram_bot_router.get("last_error"),
        "services": all_stats.get("recent_errors", [])[:10],
        "android_tasks": [
            {
                "task_id": task["id"],
                "error": task.get("error"),
                "updated_at": task.get("updated_at"),
            }
            for task in android_tasks
            if task.get("error")
        ][:10],
    }

    android_cost = round(
        sum(float(task.get("estimated_cost") or 0.0) for task in android_tasks),
        6,
    )
    jorb_summaries = [
        {
            "jorb_id": jorb.id,
            "name": jorb.name,
            "task_class": jorb.task_class,
            "status": jorb.status,
            "personality": jorb.personality,
            "progress_summary": jorb.progress_summary,
            "awaiting": jorb.awaiting,
            "updated_at": jorb.updated_at,
            "metrics": jorb.metrics,
            "metadata": jorb.metadata,
        }
        for jorb in all_jorbs[:limit]
    ]

    return {
        "generated_at": _utc_now(),
        "audience": "agentic_tooling",
        "message": (
            "Structured operator/debug snapshot for Frank. "
            "Designed for both humans and autonomous coding/debugging agents."
        ),
        "guidance": [
            (
                "Prefer traces first: they link normalized ingress, routing, "
                "session actions, and terminal outcomes."
            ),
            (
                "Use jorb task_class and Android task_class to distinguish "
                "structured runs from freeform work."
            ),
            (
                "Artifact paths are durable JSON-backed references under "
                "./data for replay/debug workflows."
            ),
        ],
        "models": {
            "switchboard": SWITCHBOARD_MODEL,
            "agent_runner": "gpt-5.2",
            "android_runner": settings.android_llm_model,
        },
        "token_cost_summary": {
            "jorbs": {
                "tokens_used": aggregate_metrics["total_tokens"],
                "estimated_cost": aggregate_metrics["total_cost"],
            },
            "android_tasks": {
                "estimated_cost": android_cost,
            },
            "combined_estimated_cost": round(
                aggregate_metrics["total_cost"] + android_cost,
                6,
            ),
        },
        "recent_messages": recent_messages[:limit],
        "recent_events": recent_events[:limit],
        "recent_traces": recent_traces[:limit],
        "jorbs": {
            "aggregate_metrics": aggregate_metrics,
            "recent": jorb_summaries,
        },
        "latest_script_results": recent_script_results[:limit],
        "android": {
            "tasks": android_tasks,
        },
        "subsystems": {
            "background_loop": background,
            "telegram_router": telegram_router,
            "telegram_bot_router": telegram_bot_router,
        },
        "last_error_by_subsystem": last_errors,
    }
