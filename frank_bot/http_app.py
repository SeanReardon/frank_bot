"""
Factory helpers for the Starlette HTTP application (Streamable HTTP transport).
"""

from __future__ import annotations

import json
import logging
import time
from asyncio import CancelledError
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from frank_bot.config import get_settings

logger = logging.getLogger(__name__)


def _normalise_endpoint(path: str) -> str:
    """Ensure the MCP endpoint always starts with a slash and has no trailing slash."""
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def create_starlette_app(mcp_server: Server) -> Starlette:
    """Create and configure the Starlette application using Streamable HTTP."""

    settings = get_settings()
    mcp_endpoint = _normalise_endpoint(settings.mcp_endpoint)
    session_manager = StreamableHTTPSessionManager(
        mcp_server,
        json_response=settings.streamable_json_response,
        stateless=settings.streamable_stateless,
    )

    async def streamable_http_asgi(scope, receive, send):
        """Delegate HTTP traffic to the MCP Streamable HTTP session manager."""
        await session_manager.handle_request(scope, receive, send)

    async def health_check(_request):
        return JSONResponse({"status": "healthy", "server": "frank-bot"})

    async def root_endpoint(request):
        """Root endpoint - handle discovery and log unexpected traffic."""
        body = None
        body_json = None
        if request.method == "POST":
            try:
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        body = body.decode("utf-8", errors="replace")
            except Exception as exc:
                logger.warning("Could not read request body: %s", exc)

        request_data = {
            "method": request.method,
            "path": str(request.url.path),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
            "body": body_json or body,
        }
        logger.info("=== ChatGPT Request: Root Endpoint ===")
        logger.info(
            "=== Request Details (JSON) ===\n%s",
            json.dumps(request_data, indent=2, default=str),
        )

        return JSONResponse(
            {
                "server": "frank-bot",
                "mcp_server": True,
                "endpoints": {
                    mcp_endpoint: "Streamable HTTP endpoint for MCP protocol",
                    "/health": "Health check endpoint",
                },
                "status": "running",
            }
        )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with session_manager.run():
            yield

    mcp_mounts = [
        Mount(mcp_endpoint, app=streamable_http_asgi),
    ]
    if mcp_endpoint != "/":
        mcp_mounts.append(Mount(f"{mcp_endpoint}/", app=streamable_http_asgi))

    routes = mcp_mounts + [
        Route("/health", health_check, methods=["GET"]),
        Route("/", root_endpoint, methods=["GET", "POST"]),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.shutting_down = False
    app.state.session_manager = session_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        app.state.shutting_down = False
        logger.info("Starlette app started - routes configured")
        logger.info("Streamable HTTP endpoint available at %s", mcp_endpoint)

    @app.on_event("shutdown")
    async def shutdown_event():
        app.state.shutting_down = True
        logger.info("Shutdown signal received - terminating Streamable HTTP sessions")

    @app.exception_handler(404)
    async def not_found_handler(request, _exc):
        logger.warning(
            "404 Not Found - method=%s path=%s query=%s headers=%s",
            request.method,
            request.url.path,
            dict(request.query_params),
            dict(request.headers),
        )
        return Response("Not Found", status_code=404)

    @app.middleware("http")
    async def log_all_requests(request, call_next):
        start_time = time.time()
        request_id = id(request)
        logger.info("=" * 80)
        logger.info("=== HTTP REQUEST #%s ===", request_id)
        logger.info("Method: %s", request.method)
        logger.info("Path: %s", request.url.path)
        logger.info("Full URL: %s", request.url)
        logger.info("Query Params: %s", dict(request.query_params))
        logger.info("Headers: %s", dict(request.headers))
        if request.client:
            logger.info(
                "Client: %s:%s",
                request.client.host,
                request.client.port,
            )

        body_logging_allowed = not request.url.path.startswith(mcp_endpoint)
        if request.method in ("POST", "PUT", "PATCH"):
            if body_logging_allowed:
                try:
                    body = await request.body()
                    if body:
                        try:
                            body_json = json.loads(body.decode())
                            logger.info(
                                "Request Body (JSON):\n%s",
                                json.dumps(body_json, indent=2, default=str),
                            )
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            body_str = body.decode("utf-8", errors="replace")
                            if len(body_str) > 1000:
                                logger.info(
                                    "Request Body (text, truncated):\n%s... (%s chars)",
                                    body_str[:1000],
                                    len(body_str),
                                )
                            else:
                                logger.info(
                                    "Request Body (text):\n%s",
                                    body_str,
                                )
                except Exception as exc:
                    logger.warning("Could not read request body: %s", exc)
            else:
                logger.info(
                    "Request body logging skipped to avoid draining MCP streams"
                )

        try:
            response = await call_next(request)
        except CancelledError:
            elapsed_time = time.time() - start_time
            logger.info("=== HTTP REQUEST #%s CANCELLED ===", request_id)
            logger.info("Request cancelled during shutdown")
            logger.info("Elapsed Time: %.4fs", elapsed_time)
            logger.info("=" * 80)
            return Response("Server shutting down", status_code=503)
        except Exception:
            elapsed_time = time.time() - start_time
            logger.error(
                "=== HTTP REQUEST #%s ERROR ===",
                request_id,
                exc_info=True,
            )
            logger.error("Elapsed Time: %.4fs", elapsed_time)
            logger.error("=" * 80)
            raise
        else:
            elapsed_time = time.time() - start_time
            logger.info("=== HTTP RESPONSE #%s ===", request_id)
            logger.info("Status Code: %s", response.status_code)
            logger.info("Response Headers: %s", dict(response.headers))
            logger.info("Elapsed Time: %.4fs", elapsed_time)
            logger.info("=" * 80)
            return response

    return app

