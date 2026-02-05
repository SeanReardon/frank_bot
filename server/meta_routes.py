"""
Starlette routes for Frank Bot script API.

Clean API structure:
- frankScriptApiLearn - Learn FrankAPI capabilities
- frankScript{List,Create,Get,Update,Delete} - CRUD on scripts
- frankScriptTask{Start,Status,List,Cancel} - Async execution
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from actions.scripts import (
    api_learn_action,
    script_list_action,
    script_create_action,
    script_get_action,
    script_update_action,
    script_delete_action,
    task_start_action,
    task_status_action,
    task_list_action,
    task_cancel_action,
)
from config import Settings
from meta.introspection import generate_meta_documentation
from server.stytch_middleware import (
    StytchSessionValidator,
    _load_stytch_credentials,
)


def build_meta_routes(settings: Settings) -> list[Route]:
    """
    Return a list of Starlette Routes for the script API.
    """

    async def _require_auth(request: Request) -> JSONResponse | None:
        """Check authentication - accepts API key OR Stytch session."""
        if settings.actions_api_key:
            provided = request.headers.get("x-api-key")
            if provided == settings.actions_api_key:
                return None

        project_id, secret = _load_stytch_credentials()
        if project_id and secret:
            session_token = request.cookies.get("stytch_session_token")
            if session_token:
                validator = StytchSessionValidator(project_id, secret)
                session_data = await validator.validate_session(session_token)
                if session_data:
                    return None

        if not settings.actions_api_key and not project_id:
            return None

        return JSONResponse(
            {"detail": "Unauthorized - provide X-API-Key or session"},
            status_code=401,
        )

    async def _build_responder(action_func, request: Request, use_body: bool = False):
        """Build a response from an action function."""
        auth_error = await _require_auth(request)
        if auth_error:
            return auth_error

        try:
            if use_body:
                body = await request.body()
                payload = json.loads(body.decode()) if body else {}
            else:
                payload = dict(request.query_params)
                # Add path params
                payload.update(request.path_params)

            result = await action_func(payload)
            return JSONResponse(result)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=500)

    # frankScriptApiLearn - Learn FrankAPI capabilities
    async def api_learn_handler(request: Request):
        return await _build_responder(api_learn_action, request)

    # frankScriptList - List all scripts
    async def script_list_handler(request: Request):
        return await _build_responder(script_list_action, request)

    # frankScriptCreate - Create a new script (POST)
    async def script_create_handler(request: Request):
        action = script_create_action
        return await _build_responder(action, request, use_body=True)

    # frankScriptGet - Get script code
    async def script_get_handler(request: Request):
        return await _build_responder(script_get_action, request)

    # frankScriptUpdate - Update script (POST)
    async def script_update_handler(request: Request):
        action = script_update_action
        return await _build_responder(action, request, use_body=True)

    # frankScriptDelete - Delete script
    async def script_delete_handler(request: Request):
        return await _build_responder(script_delete_action, request)

    # frankScriptTaskStart - Start execution (POST)
    async def task_start_handler(request: Request):
        action = task_start_action
        return await _build_responder(action, request, use_body=True)

    # frankScriptTaskStatus - Get task status
    async def task_status_handler(request: Request):
        return await _build_responder(task_status_action, request)

    # frankScriptTaskList - List tasks
    async def task_list_handler(request: Request):
        return await _build_responder(task_list_action, request)

    # frankScriptTaskCancel - Cancel task
    async def task_cancel_handler(request: Request):
        return await _build_responder(task_cancel_action, request)

    # Legacy markdown docs endpoint (for backwards compat)
    async def meta_docs_handler(request: Request):
        auth_error = await _require_auth(request)
        if auth_error:
            return auth_error
        documentation = generate_meta_documentation()
        return PlainTextResponse(documentation, media_type="text/markdown")

    # Build routes
    api = "/frank/script"
    task = f"{api}/task"
    routes = [
        Route(f"{api}/api/learn", api_learn_handler, methods=["GET"]),
        Route(f"{api}/list", script_list_handler, methods=["GET"]),
        Route(f"{api}/create", script_create_handler, methods=["POST"]),
        Route(f"{api}/get", script_get_handler, methods=["GET"]),
        Route(f"{api}/update", script_update_handler, methods=["POST"]),
        Route(f"{api}/delete", script_delete_handler, methods=["GET"]),
        Route(f"{task}/start", task_start_handler, methods=["POST"]),
        Route(f"{task}/status", task_status_handler, methods=["GET"]),
        Route(f"{task}/list", task_list_handler, methods=["GET"]),
        Route(f"{task}/cancel", task_cancel_handler, methods=["GET"]),
        # Legacy endpoint for markdown docs
        Route("/frank/meta", meta_docs_handler, methods=["GET"]),
    ]

    return routes


__all__ = ["build_meta_routes"]
