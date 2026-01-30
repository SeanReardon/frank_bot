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
from server.sms_webhook import sms_webhook_handler
from server.stytch_middleware import require_stytch_session
from config import Settings
from services.stats import stats

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
            "/actions/sms/send",
            send_sms_handler,
            methods=["GET"],
        ),
        Route(
            "/actions/sms/messages",
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
        Route("/actions/telegram/send", telegram_send_handler, methods=["GET"]),
        Route("/actions/telegram/messages", telegram_messages_handler, methods=["GET"]),
        Route("/actions/telegram/chats", telegram_chats_handler, methods=["GET"]),
        # Telegram dashboard endpoints (public - no API key required)
        Route("/telegram/status", telegram_status_handler, methods=["GET"]),
        Route("/telegram/test", telegram_test_handler, methods=["GET"]),
        # Telegram auth endpoints (protected by Stytch session)
        Route("/telegram/auth/start", telegram_auth_start_handler, methods=["POST"]),
        Route("/telegram/auth/verify", telegram_auth_verify_handler, methods=["POST"]),
        Route("/telegram/auth/2fa", telegram_auth_2fa_handler, methods=["POST"]),
        # SMS webhook endpoint (no API key - called by Telnyx)
        Route("/webhook/sms", sms_webhook_handler, methods=["POST"]),
    ]

    return routes


__all__ = ["build_action_routes"]
