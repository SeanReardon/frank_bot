"""
Starlette routes that expose Frank Bot functionality as OpenAI Actions.

All endpoints use GET to minimize ChatGPT confirmation prompts.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from actions import (
    create_event_action,
    get_calendars_action,
    get_diagnostics_action,
    get_events_action,
    get_server_status_action,
    get_time_action,
    get_ups_status_action,
    hello_world_action,
    search_checkins_action,
    search_contacts_action,
    send_sms_action,
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
from actions.sms import get_sms_messages_action
from actions.telegram import (
    get_telegram_messages,
    get_telegram_status,
    list_telegram_chats,
    send_telegram_message,
    start_telegram_auth,
    test_telegram_connection,
    verify_telegram_2fa,
    verify_telegram_code,
)
from actions.telegram_bot import get_telegram_bot_status, test_telegram_bot
from actions.style_capture import generate_sean_md_action
from actions.system_status import get_system_status_action
from actions.android_phone import (
    get_screen_action,
    android_phone_health_action,
    android_phone_status_action,
    android_phone_screen_action,
    android_phone_tap_action,
    android_phone_type_action,
    android_phone_swipe_action,
    android_phone_key_action,
    android_phone_launch_action,
    android_phone_wake_action,
    android_phone_screenshot_action,
    android_phone_find_and_tap_action,
    thermostat_set_range_action,
    thermostat_get_status_action,
    android_phone_audit_action,
    update_apps_action,
    check_security_action,
    reboot_action,
    get_storage_action,
    clear_cache_action,
    battery_health_action,
    do_task_action,
    api_get_action,
)
from actions.claudia import (
    list_claudia_repos_action,
    create_claudia_chat_action,
    list_claudia_chats_action,
    get_claudia_chat_action,
    send_claudia_message_action,
    end_claudia_chat_action,
    list_claudia_prompts_action,
    get_claudia_prompt_action,
    create_claudia_prompt_action,
    execute_claudia_prompt_action,
    list_claudia_executions_action,
    get_claudia_execution_action,
    get_claudia_queue_action,
)
from server.sms_webhook import sms_webhook_handler
from server.stytch_middleware import require_stytch_session
from config import Settings
from services.stats import stats
from services.rate_limiter import get_android_rate_limiter

HandlerFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _build_responder(
    handler: HandlerFn,
) -> Callable[[dict[str, Any]], Awaitable[JSONResponse]]:
    async def _inner(payload: dict[str, Any]) -> JSONResponse:
        try:
            result = await handler(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    return _inner


def build_action_routes(settings: Settings) -> list[Route]:
    """
    Return a list of Starlette Routes implementing the Actions HTTP surface.
    """

    async def _require_api_key(request: Request) -> None:
        if not settings.actions_api_key:
            return
        provided = request.headers.get("x-api-key")
        if provided != settings.actions_api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid X-API-Key header",
            )

    async def _check_android_rate_limit(
        request: Request,
        is_long_running: bool = False,
    ) -> None:
        """
        Check rate limit for Android phone endpoints.

        Raises HTTPException 429 if rate limit exceeded.
        """
        api_key = request.headers.get("x-api-key")
        rate_limiter = get_android_rate_limiter()

        allowed, info = rate_limiter.check_rate_limit(
            api_key=api_key,
            is_long_running=is_long_running,
        )

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit_type": info.get("limit_type", "unknown"),
                    "retry_after": info["retry_after"],
                    "minute_remaining": info["minute_remaining"],
                    "hour_remaining": info["hour_remaining"],
                },
                headers={"Retry-After": str(info["retry_after"])},
            )

    async def _read_body(request: Request) -> dict[str, Any]:
        try:
            body = await request.body()
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not body:
            return {}
        try:
            return json.loads(body.decode())
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON payload",
            ) from exc

    # Read-only GET endpoints
    async def hello_get(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("sayHello").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(hello_world_action)
        return await responder(payload)

    async def get_events_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getEvents").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_events_action)
        return await responder(payload)

    async def get_calendars_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getCalendars").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_calendars_action)
        return await responder(payload)

    async def search_contacts_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("searchContacts").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(search_contacts_action)
        return await responder(payload)

    async def search_checkins_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("searchCheckins").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(search_checkins_action)
        return await responder(payload)

    async def get_time_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getTime").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_time_action)
        return await responder(payload)

    async def get_server_status_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getServerStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_server_status_action)
        return await responder(payload)

    async def get_diagnostics_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getDiagnostics").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_diagnostics_action)
        return await responder(payload)

    async def get_ups_status_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getUpsStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_ups_status_action)
        return await responder(payload)

    async def send_sms_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("sendSMS").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(send_sms_action)
        return await responder(payload)

    async def get_sms_messages_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("getSmsMessages").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_sms_messages_action)
        return await responder(payload)

    # Telegram endpoints
    async def telegram_send_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("telegramSend").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(send_telegram_message)
        return await responder(payload)

    async def telegram_messages_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("telegramMessages").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_telegram_messages)
        return await responder(payload)

    async def telegram_chats_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("telegramChats").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(list_telegram_chats)
        return await responder(payload)

    # Telegram status endpoint (public - no API key required for web dashboard)
    async def telegram_status_handler(request: Request):
        stats.get_endpoint_stats("telegramStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_telegram_status)
        return await responder(payload)

    # Telegram test endpoint (public - allows testing from ChatGPT)
    async def telegram_test_handler(request: Request):
        stats.get_endpoint_stats("telegramTest").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(test_telegram_connection)
        return await responder(payload)

    # Calendar event creation (disguised as GET for fewer confirmations)
    async def schedule_time_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("scheduleTime").record_call()
        payload = dict(request.query_params)
        # Handle comma-separated attendees
        if "attendees" in payload and isinstance(payload["attendees"], str):
            payload["attendees"] = [
                e.strip() for e in payload["attendees"].split(",") if e.strip()
            ]
        responder = _build_responder(create_event_action)
        return await responder(payload)

    # Telegram auth endpoints (protected by Stytch session)
    @require_stytch_session
    async def telegram_auth_start_handler(request: Request):
        stats.get_endpoint_stats("telegramAuthStart").record_call()
        payload = await _read_body(request)
        responder = _build_responder(start_telegram_auth)
        return await responder(payload)

    @require_stytch_session
    async def telegram_auth_verify_handler(request: Request):
        stats.get_endpoint_stats("telegramAuthVerify").record_call()
        payload = await _read_body(request)
        responder = _build_responder(verify_telegram_code)
        return await responder(payload)

    @require_stytch_session
    async def telegram_auth_2fa_handler(request: Request):
        stats.get_endpoint_stats("telegramAuth2FA").record_call()
        payload = await _read_body(request)
        responder = _build_responder(verify_telegram_2fa)
        return await responder(payload)

    # Telegram Bot status endpoint (public - no API key required for web dashboard)
    async def telegram_bot_status_handler(request: Request):
        stats.get_endpoint_stats("telegramBotStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_telegram_bot_status)
        return await responder(payload)

    # Telegram Bot test endpoint (protected by Stytch session - sends real message)
    @require_stytch_session
    async def telegram_bot_test_handler(request: Request):
        stats.get_endpoint_stats("telegramBotTest").record_call()
        payload = await _read_body(request)
        responder = _build_responder(test_telegram_bot)
        return await responder(payload)

    # SMS messages endpoint for web dashboard (public - no API key required)
    async def sms_messages_web_handler(request: Request):
        stats.get_endpoint_stats("smsMessagesWeb").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_sms_messages_action)
        return await responder(payload)

    # Jorb endpoints - read-only endpoints are public for web dashboard
    # Write operations (approve, cancel) require Stytch session
    async def jorbs_list_handler(request: Request):
        stats.get_endpoint_stats("jorbsList").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(list_jorbs_action)
        return await responder(payload)

    async def jorbs_create_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("jorbsCreate").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(create_jorb_action)
        return await responder(payload)

    async def jorbs_get_handler(request: Request):
        stats.get_endpoint_stats("jorbsGet").record_call()
        jorb_id = request.path_params.get("id", "")
        payload = dict(request.query_params)
        payload["jorb_id"] = jorb_id
        responder = _build_responder(get_jorb_action)
        return await responder(payload)

    async def jorbs_messages_handler(request: Request):
        stats.get_endpoint_stats("jorbsMessages").record_call()
        jorb_id = request.path_params.get("id", "")
        payload = dict(request.query_params)
        payload["jorb_id"] = jorb_id
        responder = _build_responder(get_jorb_messages_action)
        return await responder(payload)

    async def jorbs_approve_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("jorbsApprove").record_call()
        jorb_id = request.path_params.get("id", "")
        payload = dict(request.query_params)
        payload["jorb_id"] = jorb_id
        responder = _build_responder(approve_jorb_action)
        return await responder(payload)

    async def jorbs_cancel_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("jorbsCancel").record_call()
        jorb_id = request.path_params.get("id", "")
        payload = dict(request.query_params)
        payload["jorb_id"] = jorb_id
        responder = _build_responder(cancel_jorb_action)
        return await responder(payload)

    async def jorbs_brief_handler(request: Request):
        stats.get_endpoint_stats("jorbsBrief").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(brief_me_action)
        return await responder(payload)

    async def jorbs_stats_handler(request: Request):
        stats.get_endpoint_stats("jorbsStats").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_jorbs_stats_action)
        return await responder(payload)

    # Style capture endpoint (protected by API key)
    async def style_generate_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("styleGenerate").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(generate_sean_md_action)
        return await responder(payload)

    # System status endpoint (public - for web dashboard)
    async def system_status_handler(request: Request):
        stats.get_endpoint_stats("systemStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_system_status_action)
        return await responder(payload)

    # Claudia integration endpoints (protected by API key)
    async def claudia_repos_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaRepos").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(list_claudia_repos_action)
        return await responder(payload)

    async def claudia_chat_create_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaChatCreate").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(create_claudia_chat_action)
        return await responder(payload)

    async def claudia_chats_list_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaChatsList").record_call()
        repo_id = request.path_params.get("repo_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        responder = _build_responder(list_claudia_chats_action)
        return await responder(payload)

    async def claudia_chat_get_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaChatGet").record_call()
        repo_id = request.path_params.get("repo_id", "")
        chat_id = request.path_params.get("chat_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        payload["chat_id"] = chat_id
        responder = _build_responder(get_claudia_chat_action)
        return await responder(payload)

    async def claudia_chat_message_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaChatMessage").record_call()
        repo_id = request.path_params.get("repo_id", "")
        chat_id = request.path_params.get("chat_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        payload["chat_id"] = chat_id
        responder = _build_responder(send_claudia_message_action)
        return await responder(payload)

    async def claudia_chat_end_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaChatEnd").record_call()
        repo_id = request.path_params.get("repo_id", "")
        chat_id = request.path_params.get("chat_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        payload["chat_id"] = chat_id
        responder = _build_responder(end_claudia_chat_action)
        return await responder(payload)

    async def claudia_prompts_list_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaPromptsList").record_call()
        repo_id = request.path_params.get("repo_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        responder = _build_responder(list_claudia_prompts_action)
        return await responder(payload)

    async def claudia_prompt_get_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaPromptGet").record_call()
        repo_id = request.path_params.get("repo_id", "")
        prompt_id = request.path_params.get("prompt_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        payload["prompt_id"] = prompt_id
        responder = _build_responder(get_claudia_prompt_action)
        return await responder(payload)

    async def claudia_prompt_create_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaPromptCreate").record_call()
        repo_id = request.path_params.get("repo_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        responder = _build_responder(create_claudia_prompt_action)
        return await responder(payload)

    async def claudia_prompt_execute_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaPromptExecute").record_call()
        repo_id = request.path_params.get("repo_id", "")
        prompt_id = request.path_params.get("prompt_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        payload["prompt_id"] = prompt_id
        responder = _build_responder(execute_claudia_prompt_action)
        return await responder(payload)

    async def claudia_executions_list_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaExecutionsList").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(list_claudia_executions_action)
        return await responder(payload)

    async def claudia_execution_get_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaExecutionGet").record_call()
        execution_id = request.path_params.get("execution_id", "")
        payload = dict(request.query_params)
        payload["execution_id"] = execution_id
        responder = _build_responder(get_claudia_execution_action)
        return await responder(payload)

    async def claudia_queue_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("claudiaQueue").record_call()
        repo_id = request.path_params.get("repo_id", "")
        payload = dict(request.query_params)
        payload["repo_id"] = repo_id
        responder = _build_responder(get_claudia_queue_action)
        return await responder(payload)

    # Android phone control endpoints (new naming convention: androidPhone)
    # All androidPhone endpoints are rate-limited
    async def android_phone_get_screen_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneGetScreen").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_screen_action)
        return await responder(payload)

    # Android phone health check (public - no API key required for status monitoring)
    async def android_phone_health_handler(request: Request):
        stats.get_endpoint_stats("androidPhoneHealth").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_health_action)
        return await responder(payload)

    async def android_status_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_status_action)
        return await responder(payload)

    async def android_screen_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidScreen").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_screen_action)
        return await responder(payload)

    async def android_tap_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidTap").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_tap_action)
        return await responder(payload)

    async def android_type_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidType").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_type_action)
        return await responder(payload)

    async def android_swipe_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidSwipe").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_swipe_action)
        return await responder(payload)

    async def android_key_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidKey").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_key_action)
        return await responder(payload)

    async def android_launch_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidLaunch").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_launch_action)
        return await responder(payload)

    async def android_wake_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidWake").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_wake_action)
        return await responder(payload)

    async def android_screenshot_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidScreenshot").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_screenshot_action)
        return await responder(payload)

    async def android_find_tap_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidFindTap").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_find_and_tap_action)
        return await responder(payload)

    # Android phone thermostat control (LLM-in-the-loop)
    # Long-running tasks: exempt from per-minute limit, still count toward hourly
    async def android_phone_thermostat_set_range_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request, is_long_running=True)
        stats.get_endpoint_stats("androidPhoneThermostatSetRange").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(thermostat_set_range_action)
        return await responder(payload)

    async def android_phone_thermostat_get_status_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request, is_long_running=True)
        stats.get_endpoint_stats("androidPhoneThermostatGetStatus").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(thermostat_get_status_action)
        return await responder(payload)

    # Android phone audit endpoint (protected by API key)
    async def android_phone_audit_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("androidPhoneAudit").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(android_phone_audit_action)
        return await responder(payload)

    # Android phone maintenance endpoints (protected by API key)
    async def android_phone_maintenance_update_apps_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request, is_long_running=True)
        stats.get_endpoint_stats("androidPhoneMaintenanceUpdateApps").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(update_apps_action)
        return await responder(payload)

    async def android_phone_maintenance_check_security_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneMaintenanceCheckSecurity").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(check_security_action)
        return await responder(payload)

    async def android_phone_maintenance_reboot_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneMaintenanceReboot").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(reboot_action)
        return await responder(payload)

    async def android_phone_maintenance_storage_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneMaintenanceStorage").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(get_storage_action)
        return await responder(payload)

    async def android_phone_maintenance_clear_cache_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneMaintenanceClearCache").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(clear_cache_action)
        return await responder(payload)

    async def android_phone_maintenance_battery_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request)
        stats.get_endpoint_stats("androidPhoneMaintenanceBattery").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(battery_health_action)
        return await responder(payload)

    # Android phone do task - universal goal-based endpoint
    async def android_phone_do_task_handler(request: Request):
        await _require_api_key(request)
        await _check_android_rate_limit(request, is_long_running=True)
        stats.get_endpoint_stats("androidPhoneTaskDo").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(do_task_action)
        return await responder(payload)

    # Android phone API documentation endpoint
    async def android_phone_api_get_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("androidPhoneApiGet").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(api_get_action)
        return await responder(payload)

    routes = [
        # All endpoints use GET for minimal confirmation prompts
        Route("/actions/hello", hello_get, methods=["GET"]),
        Route(
            "/actions/calendar/events",
            get_events_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/calendar/calendars",
            get_calendars_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/calendar/schedule",
            schedule_time_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/contacts/search",
            search_contacts_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/messages/sms/send",
            send_sms_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/messages/sms/get",
            get_sms_messages_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/swarm/checkins",
            search_checkins_handler,
            methods=["GET"],
        ),
        Route("/actions/me/time", get_time_handler, methods=["GET"]),
        Route("/actions/server/status", get_server_status_handler, methods=["GET"]),
        Route(
            "/actions/server/diagnostics",
            get_diagnostics_handler,
            methods=["GET"],
        ),
        Route("/actions/ups/status", get_ups_status_handler, methods=["GET"]),
        # Telegram endpoints
        Route("/actions/messages/telegram/send", telegram_send_handler, methods=["GET"]),
        Route("/actions/messages/telegram/get", telegram_messages_handler, methods=["GET"]),
        Route("/actions/chats/telegram/list", telegram_chats_handler, methods=["GET"]),
        # Telegram dashboard endpoints (public - no API key required)
        Route("/telegram/status", telegram_status_handler, methods=["GET"]),
        Route("/telegram/test", telegram_test_handler, methods=["GET"]),
        # Telegram auth endpoints (protected by Stytch session)
        Route("/telegram/auth/start", telegram_auth_start_handler, methods=["POST"]),
        Route("/telegram/auth/verify", telegram_auth_verify_handler, methods=["POST"]),
        Route("/telegram/auth/2fa", telegram_auth_2fa_handler, methods=["POST"]),
        # SMS webhook endpoint (no API key - called by Telnyx)
        Route("/webhook/sms", sms_webhook_handler, methods=["POST"]),
        # Telegram Bot status and test endpoints
        Route("/telegram-bot/status", telegram_bot_status_handler, methods=["GET"]),
        Route("/telegram-bot/test", telegram_bot_test_handler, methods=["POST"]),
        # SMS messages endpoint for web dashboard (no API key required)
        Route("/sms/messages", sms_messages_web_handler, methods=["GET"]),
        # Jorb endpoints
        Route("/actions/jorbs/list", jorbs_list_handler, methods=["GET"]),
        Route("/actions/jorbs/create", jorbs_create_handler, methods=["GET"]),
        Route("/actions/jorbs/brief", jorbs_brief_handler, methods=["GET"]),
        Route("/actions/jorbs/stats", jorbs_stats_handler, methods=["GET"]),
        Route("/actions/jorbs/{id}/get", jorbs_get_handler, methods=["GET"]),
        Route("/actions/jorbs/{id}/messages/get", jorbs_messages_handler, methods=["GET"]),
        Route("/actions/jorbs/{id}/approve", jorbs_approve_handler, methods=["GET"]),
        Route("/actions/jorbs/{id}/cancel", jorbs_cancel_handler, methods=["GET"]),
        # Style capture endpoint (SEAN.md generation)
        Route("/actions/style/generate", style_generate_handler, methods=["GET"]),
        # System status endpoint (orchestration machinery health)
        Route("/system/status", system_status_handler, methods=["GET"]),
        # Claudia integration endpoints
        Route("/actions/claudia/repos", claudia_repos_handler, methods=["GET"]),
        Route("/actions/claudia/chat/create", claudia_chat_create_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/chats", claudia_chats_list_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/chats/{chat_id}", claudia_chat_get_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/chats/{chat_id}/message", claudia_chat_message_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/chats/{chat_id}/end", claudia_chat_end_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/prompts", claudia_prompts_list_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/prompts/create", claudia_prompt_create_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/prompts/{prompt_id}", claudia_prompt_get_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/prompts/{prompt_id}/execute", claudia_prompt_execute_handler, methods=["GET"]),
        Route("/actions/claudia/repos/{repo_id}/queue", claudia_queue_handler, methods=["GET"]),
        Route("/actions/claudia/executions", claudia_executions_list_handler, methods=["GET"]),
        Route("/actions/claudia/executions/{execution_id}", claudia_execution_get_handler, methods=["GET"]),
        # Android device control endpoints (legacy paths)
        Route("/actions/android/status", android_status_handler, methods=["GET"]),
        Route("/actions/android/screen", android_screen_handler, methods=["GET"]),
        Route("/actions/android/tap", android_tap_handler, methods=["GET"]),
        Route("/actions/android/type", android_type_handler, methods=["GET"]),
        Route("/actions/android/swipe", android_swipe_handler, methods=["GET"]),
        Route("/actions/android/key", android_key_handler, methods=["GET"]),
        Route("/actions/android/launch", android_launch_handler, methods=["GET"]),
        Route("/actions/android/wake", android_wake_handler, methods=["GET"]),
        Route("/actions/android/screenshot", android_screenshot_handler, methods=["GET"]),
        Route("/actions/android/find-tap", android_find_tap_handler, methods=["GET"]),
        # Android phone endpoints (new naming convention for LLM-in-the-loop)
        Route("/actions/androidPhone/getScreen", android_phone_get_screen_handler, methods=["GET"]),
        Route("/actions/androidPhone/health", android_phone_health_handler, methods=["GET"]),
        # Universal goal-based endpoint - describe what you want in natural language
        Route("/actions/androidPhone/task/do", android_phone_do_task_handler, methods=["GET"]),
        # API documentation for androidPhoneTaskDo
        Route("/actions/androidPhone/api/get", android_phone_api_get_handler, methods=["GET"]),
        # Android phone thermostat control
        Route("/actions/androidPhone/thermostat/setRange", android_phone_thermostat_set_range_handler, methods=["GET"]),
        Route("/actions/androidPhone/thermostat/getStatus", android_phone_thermostat_get_status_handler, methods=["GET"]),
        # Android phone audit endpoint
        Route("/actions/androidPhone/audit", android_phone_audit_handler, methods=["GET"]),
        # Android phone maintenance endpoints
        Route("/actions/androidPhone/maintenance/updateApps", android_phone_maintenance_update_apps_handler, methods=["GET"]),
        Route("/actions/androidPhone/maintenance/checkSecurity", android_phone_maintenance_check_security_handler, methods=["GET"]),
        Route("/actions/androidPhone/maintenance/reboot", android_phone_maintenance_reboot_handler, methods=["GET"]),
        Route("/actions/androidPhone/maintenance/storage", android_phone_maintenance_storage_handler, methods=["GET"]),
        Route("/actions/androidPhone/maintenance/clearCache", android_phone_maintenance_clear_cache_handler, methods=["GET"]),
        Route("/actions/androidPhone/maintenance/battery", android_phone_maintenance_battery_handler, methods=["GET"]),
    ]

    return routes


__all__ = ["build_action_routes"]
