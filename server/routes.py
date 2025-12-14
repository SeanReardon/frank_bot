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
    hello_world_action,
    search_checkins_action,
    search_contacts_action,
    send_sms_action,
)
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

    async def send_sms_handler(request: Request):
        await _require_api_key(request)
        stats.get_endpoint_stats("sendSMS").record_call()
        payload = dict(request.query_params)
        responder = _build_responder(send_sms_action)
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

    routes = [
        # All endpoints use GET for minimal confirmation prompts
        Route("/actions/hello", hello_get, methods=["GET"]),
        Route("/actions/calendar/events", get_events_handler, methods=["GET"]),
        Route("/actions/calendar/calendars", get_calendars_handler, methods=["GET"]),
        Route("/actions/calendar/schedule", schedule_time_handler, methods=["GET"]),
        Route("/actions/contacts/search", search_contacts_handler, methods=["GET"]),
        Route("/actions/sms/send", send_sms_handler, methods=["GET"]),
        Route("/actions/swarm/checkins", search_checkins_handler, methods=["GET"]),
        Route("/actions/me/time", get_time_handler, methods=["GET"]),
        Route("/actions/server/status", get_server_status_handler, methods=["GET"]),
        Route("/actions/server/diagnostics", get_diagnostics_handler, methods=["GET"]),
    ]

    return routes


__all__ = ["build_action_routes"]

