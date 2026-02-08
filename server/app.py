"""
Factory helpers for the Starlette HTTP application (Actions transport only).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from config import get_settings

# Git commit injected at build time
GIT_COMMIT = os.environ.get("GIT_COMMIT", "dev")
from server.manifests import (
    build_actions_manifest,
    build_ai_plugin_manifest,
)
from server.openapi import load_openapi_document, load_chatgpt_openapi_document
from server.meta_routes import build_meta_routes
from server.routes import build_action_routes
from services.background_loop import (
    start_background_loop,
    stop_background_loop,
)

logger = logging.getLogger(__name__)

# Favicon path - project root contains favicon.png
FAVICON_PATH = Path(__file__).parent.parent / "favicon.png"


def create_starlette_app() -> Starlette:
    """Create and configure the Starlette application for Actions access."""

    settings = get_settings()
    action_routes = build_action_routes(settings)
    meta_routes = build_meta_routes(settings)
    openapi_document = load_openapi_document(settings)
    chatgpt_openapi_document = load_chatgpt_openapi_document(settings)
    ai_plugin_manifest = build_ai_plugin_manifest(settings)
    actions_manifest = build_actions_manifest(settings)

    async def health_check(_request):
        return JSONResponse({
            "status": "healthy",
            "server": "frank-bot",
            "version": GIT_COMMIT,
        })

    async def version_endpoint(_request):
        return JSONResponse({
            "api": {
                "commit": GIT_COMMIT,
                "commit_url": f"https://github.com/SeanReardon/frank_bot/commit/{GIT_COMMIT}" if GIT_COMMIT != "dev" else None,
            },
        })

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

    async def chatgpt_openapi_handler(_request):
        """ChatGPT-specific OpenAPI spec with reduced operations (under 30)."""
        return JSONResponse(chatgpt_openapi_document)

    async def ai_plugin_handler(_request):
        return JSONResponse(ai_plugin_manifest)

    async def actions_manifest_handler(_request):
        return JSONResponse(actions_manifest)

    async def favicon_handler(_request):
        if FAVICON_PATH.exists():
            return FileResponse(FAVICON_PATH, media_type="image/png")
        return Response(status_code=404)

    routes = action_routes + meta_routes + [
        Route("/favicon.ico", favicon_handler, methods=["GET"]),
        Route("/actions/openapi.json", openapi_handler, methods=["GET"]),
        Route("/actions/openapi-chatgpt.json", chatgpt_openapi_handler, methods=["GET"]),
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
        Route("/version", version_endpoint, methods=["GET"]),
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

        # Store main event loop for FrankAPI script threads.
        # Scripts run in a ThreadPoolExecutor and need to submit coroutines
        # back to this loop (required for Telethon and other loop-bound clients).
        import asyncio
        from meta.api import set_main_loop
        set_main_loop(asyncio.get_running_loop())

        # Start the background event loop for jorb system
        try:
            await start_background_loop()
            logger.info("Background loop started")
        except Exception as e:
            logger.error("Failed to start background loop: %s", e)

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutdown signal received - terminating HTTP server")
        # Stop the background event loop
        try:
            await stop_background_loop()
            logger.info("Background loop stopped")
        except Exception as e:
            logger.error("Error stopping background loop: %s", e)

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

