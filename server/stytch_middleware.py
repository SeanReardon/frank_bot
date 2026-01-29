"""
Stytch session validation middleware for protected routes.

Validates the stytch_session_token cookie by calling the Stytch API.
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_settings

logger = logging.getLogger(__name__)

# Stytch API base URLs
STYTCH_API_BASE = "https://api.stytch.com"
STYTCH_TEST_API_BASE = "https://test.stytch.com"


class StytchSessionValidator:
    """
    Validates Stytch session tokens.

    Uses the Stytch API to verify session validity. Supports both
    test and live environments based on project ID prefix.
    """

    def __init__(self, project_id: str, secret: str):
        self._project_id = project_id
        self._secret = secret
        # Test projects start with "project-test-"
        self._is_test = project_id.startswith("project-test-")
        self._api_base = STYTCH_TEST_API_BASE if self._is_test else STYTCH_API_BASE

    async def validate_session(self, session_token: str) -> dict | None:
        """
        Validate a session token with the Stytch API.

        Args:
            session_token: The stytch_session_token cookie value.

        Returns:
            Session data dict if valid, None if invalid.
        """
        url = f"{self._api_base}/v1/sessions/authenticate"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"session_token": session_token},
                    auth=(self._project_id, self._secret),
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "session_id": data.get("session", {}).get("session_id"),
                        "user_id": data.get("session", {}).get("user_id"),
                        "started_at": data.get("session", {}).get("started_at"),
                        "expires_at": data.get("session", {}).get("expires_at"),
                    }
                else:
                    logger.warning(
                        "Stytch session validation failed: %s %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return None

            except httpx.RequestError as exc:
                logger.error("Stytch API request failed: %s", exc)
                return None


def require_stytch_session(
    handler: Callable[[Request], Awaitable[JSONResponse]],
) -> Callable[[Request], Awaitable[JSONResponse]]:
    """
    Decorator that requires a valid Stytch session.

    Reads the stytch_session_token cookie and validates it against
    the Stytch API. Returns 401 Unauthorized if invalid/missing.

    Usage:
        @require_stytch_session
        async def protected_handler(request: Request):
            return JSONResponse({"data": "protected"})
    """
    async def wrapper(request: Request) -> JSONResponse:
        settings = get_settings()

        # Check if Stytch is configured
        if not settings.stytch_project_id or not settings.stytch_secret:
            logger.warning("Stytch not configured - rejecting protected request")
            return JSONResponse(
                {"error": "Authentication not configured"},
                status_code=500,
            )

        # Get session token from cookie
        session_token = request.cookies.get("stytch_session_token")

        if not session_token:
            return JSONResponse(
                {"error": "Unauthorized - missing session token"},
                status_code=401,
            )

        # Validate with Stytch
        validator = StytchSessionValidator(
            settings.stytch_project_id,
            settings.stytch_secret,
        )

        session_data = await validator.validate_session(session_token)

        if not session_data:
            return JSONResponse(
                {"error": "Unauthorized - invalid or expired session"},
                status_code=401,
            )

        # Store session data on request state for downstream handlers
        request.state.stytch_session = session_data

        return await handler(request)

    return wrapper


__all__ = [
    "StytchSessionValidator",
    "require_stytch_session",
]
