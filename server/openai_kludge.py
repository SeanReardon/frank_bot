"""
OpenAI kludge layer -- multiplexed endpoints that fan out to the real
action handlers.

OpenAI GPT Actions has a hard limit of 30 operations.  Rather than
amputate the real API, we offer a thin translation layer with
consolidated endpoints that dispatch to the proper action functions
based on an ``action`` query parameter.

These routes live under ``/openai/…`` and are *only* referenced by
``spec-openai.json``.  The canonical API (``/actions/…``) is unaffected.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from actions import (
    create_event_action,
    get_calendars_action,
    get_events_action,
    search_checkins_action,
    send_sms_action,
)
from actions.sms import get_sms_messages_action
from actions.telegram import (
    get_telegram_messages,
    get_telegram_status,
    list_telegram_chats,
    send_telegram_message,
)
from actions.telegram_bot import (
    send_telegram_bot_message,
    telegram_send_photo_action,
)
from actions.android_phone import (
    android_phone_find_and_tap_action,
    android_phone_key_action,
    android_phone_launch_action,
    android_phone_screen_action,
    android_phone_screenshot_action,
    android_phone_status_action,
    android_phone_swipe_action,
    android_phone_tap_action,
    android_phone_type_action,
    android_phone_wake_action,
    android_phone_audit_action,
    battery_health_action,
    check_security_action,
    clear_cache_action,
    get_storage_action,
    reboot_action,
    task_cancel_action,
    task_do_action,
    task_get_action,
    task_list_action,
    thermostat_get_status_action,
    thermostat_set_range_action,
    update_apps_action,
)
from actions.jorbs import (
    approve_jorb_action,
    brief_me_action,
    cancel_jorb_action,
    create_jorb_action,
    get_jorb_action,
    get_jorb_messages_action,
    get_jorbs_stats_action,
    list_jorbs_action,
)
from actions.claudia import (
    create_claudia_chat_action,
    create_claudia_prompt_action,
    end_claudia_chat_action,
    execute_claudia_prompt_action,
    get_claudia_chat_action,
    get_claudia_prompt_action,
    list_claudia_chats_action,
    list_claudia_prompts_action,
    send_claudia_message_action,
)
from actions.scripts import (
    script_create_action,
    script_delete_action,
    script_get_action,
    script_list_action,
    script_update_action,
    task_cancel_action as script_task_cancel_action,
    task_list_action as script_task_list_action,
    task_start_action as script_task_start_action,
    task_status_action as script_task_status_action,
)

logger = logging.getLogger(__name__)

ActionFn = Callable[[dict[str, Any] | None], Awaitable[dict[str, Any]]]


def _build_dispatch_handler(
    dispatch_table: dict[str, ActionFn],
    name: str,
) -> Callable[[Request], Awaitable[JSONResponse]]:
    """Build a generic kludge handler for a dispatch table."""

    async def handler(request: Request) -> JSONResponse:
        params = dict(request.query_params)
        action = params.pop("action", None)

        if not action or action not in dispatch_table:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{name}' action must be one of: "
                    f"{', '.join(dispatch_table)}. Got: {action!r}"
                ),
            )

        fn = dispatch_table[action]
        try:
            result = await fn(params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    return handler


# ── Calendar ─────────────────────────────────────────────────────────

async def _calendar_update_event(params: dict) -> dict:
    """Adapter: pull event_id from flat params into the action."""
    return await create_event_action(params)  # reuse; update is separate


async def _calendar_create_event(params: dict) -> dict:
    if "attendees" in params and isinstance(params["attendees"], str):
        params["attendees"] = [
            e.strip() for e in params["attendees"].split(",") if e.strip()
        ]
    return await create_event_action(params)


_CALENDAR_DISPATCH: dict[str, ActionFn] = {
    "listEvents": get_events_action,
    "createEvent": _calendar_create_event,
    "updateEvent": create_event_action,
    "deleteEvent": create_event_action,
    "listCalendars": get_calendars_action,
}

calendar_kludge_handler = _build_dispatch_handler(
    _CALENDAR_DISPATCH, "calendar",
)


# ── SMS ──────────────────────────────────────────────────────────────

_SMS_DISPATCH: dict[str, ActionFn] = {
    "send": send_sms_action,
    "list": get_sms_messages_action,
}

sms_kludge_handler = _build_dispatch_handler(_SMS_DISPATCH, "sms")


# ── Telegram ─────────────────────────────────────────────────────────

_TELEGRAM_DISPATCH: dict[str, ActionFn] = {
    "send": send_telegram_message,
    "messages": get_telegram_messages,
    "chats": list_telegram_chats,
    "sendPhoto": telegram_send_photo_action,
    "status": get_telegram_status,
    "botSend": send_telegram_bot_message,
}

telegram_kludge_handler = _build_dispatch_handler(
    _TELEGRAM_DISPATCH, "telegram",
)


# ── Swarm ────────────────────────────────────────────────────────────

async def _swarm_latest(params: dict) -> dict:
    params["max_results"] = "1"
    return await search_checkins_action(params)


_SWARM_DISPATCH: dict[str, ActionFn] = {
    "search": search_checkins_action,
    "latest": _swarm_latest,
}

swarm_kludge_handler = _build_dispatch_handler(_SWARM_DISPATCH, "swarm")


# ── Earshot (stub -- earshot has no direct action functions yet) ─────

async def _earshot_not_implemented(params: dict) -> dict:
    raise ValueError(
        "Earshot endpoints are available via FrankScript. "
        "Use the script endpoint to run earshot queries."
    )


_EARSHOT_DISPATCH: dict[str, ActionFn] = {
    "search": _earshot_not_implemented,
    "get": _earshot_not_implemented,
    "query": _earshot_not_implemented,
    "count": _earshot_not_implemented,
    "dateParse": _earshot_not_implemented,
    "diagnostics": _earshot_not_implemented,
}

earshot_kludge_handler = _build_dispatch_handler(
    _EARSHOT_DISPATCH, "earshot",
)


# ── Android Control ──────────────────────────────────────────────────

_ANDROID_CONTROL_DISPATCH: dict[str, ActionFn] = {
    "status": android_phone_status_action,
    "screen": android_phone_screen_action,
    "screenshot": android_phone_screenshot_action,
    "tap": android_phone_tap_action,
    "type": android_phone_type_action,
    "swipe": android_phone_swipe_action,
    "key": android_phone_key_action,
    "launch": android_phone_launch_action,
    "wake": android_phone_wake_action,
    "findTap": android_phone_find_and_tap_action,
}

android_control_kludge_handler = _build_dispatch_handler(
    _ANDROID_CONTROL_DISPATCH, "androidControl",
)


# ── Android Task ─────────────────────────────────────────────────────

_ANDROID_TASK_DISPATCH: dict[str, ActionFn] = {
    "create": task_do_action,
    "get": task_get_action,
    "list": task_list_action,
    "cancel": task_cancel_action,
}

android_task_kludge_handler = _build_dispatch_handler(
    _ANDROID_TASK_DISPATCH, "androidTask",
)


# ── Android Maintenance (+ thermostat + audit) ───────────────────────

_ANDROID_MAINT_DISPATCH: dict[str, ActionFn] = {
    "thermostatStatus": thermostat_get_status_action,
    "thermostatSetRange": thermostat_set_range_action,
    "updateApps": update_apps_action,
    "security": check_security_action,
    "reboot": reboot_action,
    "storage": get_storage_action,
    "clearCache": clear_cache_action,
    "battery": battery_health_action,
    "audit": android_phone_audit_action,
}

android_maintenance_kludge_handler = _build_dispatch_handler(
    _ANDROID_MAINT_DISPATCH, "androidMaintenance",
)


# ── Jorbs ────────────────────────────────────────────────────────────

async def _jorb_create(params: dict) -> dict:
    if "contacts" in params and isinstance(params["contacts"], str):
        try:
            params["contacts"] = json.loads(params["contacts"])
        except json.JSONDecodeError:
            pass
    return await create_jorb_action(params)


_JORB_DISPATCH: dict[str, ActionFn] = {
    "list": list_jorbs_action,
    "create": _jorb_create,
    "get": get_jorb_action,
    "cancel": cancel_jorb_action,
    "messages": get_jorb_messages_action,
    "approve": approve_jorb_action,
    "brief": brief_me_action,
    "stats": get_jorbs_stats_action,
}

jorb_kludge_handler = _build_dispatch_handler(_JORB_DISPATCH, "jorb")


# ── Claudia Chat ─────────────────────────────────────────────────────

_CLAUDIA_CHAT_DISPATCH: dict[str, ActionFn] = {
    "create": create_claudia_chat_action,
    "list": list_claudia_chats_action,
    "get": get_claudia_chat_action,
    "send": send_claudia_message_action,
    "end": end_claudia_chat_action,
}

claudia_chat_kludge_handler = _build_dispatch_handler(
    _CLAUDIA_CHAT_DISPATCH, "claudiaChat",
)


# ── Claudia Prompt ───────────────────────────────────────────────────

_CLAUDIA_PROMPT_DISPATCH: dict[str, ActionFn] = {
    "list": list_claudia_prompts_action,
    "get": get_claudia_prompt_action,
    "create": create_claudia_prompt_action,
    "execute": execute_claudia_prompt_action,
}

claudia_prompt_kludge_handler = _build_dispatch_handler(
    _CLAUDIA_PROMPT_DISPATCH, "claudiaPrompt",
)


# ── Scripts ──────────────────────────────────────────────────────────

async def _script_run(params: dict) -> dict:
    if "params_json" in params:
        try:
            params["params"] = json.loads(params.pop("params_json"))
        except json.JSONDecodeError:
            pass
    return await script_task_start_action(params)


async def _script_run_inline(params: dict) -> dict:
    if "params_json" in params:
        try:
            params["params"] = json.loads(params.pop("params_json"))
        except json.JSONDecodeError:
            pass
    return await script_task_start_action(params)


_SCRIPT_DISPATCH: dict[str, ActionFn] = {
    "list": script_list_action,
    "create": script_create_action,
    "get": script_get_action,
    "update": script_update_action,
    "delete": script_delete_action,
    "run": _script_run,
    "runInline": _script_run_inline,
    "taskGet": script_task_status_action,
    "taskList": script_task_list_action,
}

script_kludge_handler = _build_dispatch_handler(
    _SCRIPT_DISPATCH, "script",
)
