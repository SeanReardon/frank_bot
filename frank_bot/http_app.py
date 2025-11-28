"""
Factory helpers for the Starlette HTTP application (Actions transport only).
"""

from __future__ import annotations

import logging
import time

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from frank_bot.actions_api import build_action_routes
from frank_bot.config import get_settings
from frank_bot.manifests import (
    build_actions_manifest,
    build_ai_plugin_manifest,
)
from frank_bot.openapi import load_openapi_document

logger = logging.getLogger(__name__)


def create_starlette_app() -> Starlette:
    """Create and configure the Starlette application for Actions access."""

    settings = get_settings()
    action_routes = build_action_routes(settings)
    openapi_document = load_openapi_document(settings)
    ai_plugin_manifest = build_ai_plugin_manifest(settings)
    actions_manifest = build_actions_manifest(settings)

    async def health_check(_request):
        return JSONResponse({"status": "healthy", "server": "frank-bot"})

    async def root_endpoint(_request):
        return JSONResponse(
            {
                "server": "frank-bot",
                "status": "running",
                "actions_available": True,
                "endpoints": {
                    "/actions/openapi.json": "OpenAPI 3.1 schema",
                    "/.well-known/actions.json": "OpenAI Actions manifest",
                    "/.well-known/ai-plugin.json": "ChatGPT plugin manifest",
                    "/health": "Health check endpoint",
                },
            }
        )

    async def openapi_handler(_request):
        return JSONResponse(openapi_document)

    async def ai_plugin_handler(_request):
        return JSONResponse(ai_plugin_manifest)

    async def actions_manifest_handler(_request):
        return JSONResponse(actions_manifest)

    routes = action_routes + [
        Route("/actions/openapi.json", openapi_handler, methods=["GET"]),
        Route(
            "/.well-known/ai-plugin.json",
            ai_plugin_handler,
            methods=["GET"],
        ),
        Route(
            "/.well-known/actions.json",
            actions_manifest_handler,
            methods=["GET"],
        ),
        Route("/health", health_check, methods=["GET"]),
        Route("/", root_endpoint, methods=["GET"]),
    ]

    app = Starlette(routes=routes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        logger.info("Starlette app started - Actions endpoints configured")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutdown signal received - terminating HTTP server")

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

        try:
            response = await call_next(request)
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
