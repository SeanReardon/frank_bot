"""
Starlette routes that expose Frank Bot functionality as OpenAI Actions.

Read-only endpoints use GET only to signal to ChatGPT that they don't modify data.
Only createCalendarEvent uses POST since it's a write operation.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from frank_bot.actions_logic import (
    create_calendar_event_action,
    get_my_time_action,
    get_server_start_action,
    hello_world_action,
    list_calendar_events_action,
    list_calendars_action,
    list_my_swarm_checkins_action,
    search_contacts_action,
)
from frank_bot.config import Settings

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
        payload = dict(request.query_params)
        responder = _build_responder(hello_world_action)
        return await responder(payload)

    async def list_events_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(list_calendar_events_action)
        return await responder(payload)

    async def list_calendars_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(list_calendars_action)
        return await responder(payload)

    async def search_contacts_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(search_contacts_action)
        return await responder(payload)

    async def swarm_checkins_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(list_my_swarm_checkins_action)
        return await responder(payload)

    async def my_time_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(get_my_time_action)
        return await responder(payload)

    async def server_version_get(request: Request):
        await _require_api_key(request)
        payload = dict(request.query_params)
        responder = _build_responder(get_server_start_action)
        return await responder(payload)

    # Write endpoint (POST only)
    async def create_event_post(request: Request):
        await _require_api_key(request)
        payload = await _read_body(request)
        responder = _build_responder(create_calendar_event_action)
        return await responder(payload)

    routes = [
        # Read-only endpoints (GET only)
        Route("/actions/hello", hello_get, methods=["GET"]),
        Route("/actions/calendar/events", list_events_get, methods=["GET"]),
        Route("/actions/calendar/calendars", list_calendars_get, methods=["GET"]),
        Route("/actions/contacts/search", search_contacts_get, methods=["GET"]),
        Route("/actions/swarm/self", swarm_checkins_get, methods=["GET"]),
        Route("/actions/me/time", my_time_get, methods=["GET"]),
        Route("/actions/server/version", server_version_get, methods=["GET"]),
        # Write endpoint (POST only)
        Route("/actions/calendar/events:create", create_event_post, methods=["POST"]),
    ]

    return routes


__all__ = ["build_action_routes"]
