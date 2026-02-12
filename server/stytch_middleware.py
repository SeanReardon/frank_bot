"""
Stytch session validation middleware for protected routes.

Validates the stytch_session_token cookie by calling the Stytch API.

Credentials are loaded from:
1. Vault (if configured) - secret/frank-bot/stytch
2. Environment variables (fallback) - STYTCH_PROJECT_ID, STYTCH_SECRET
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Awaitable

import httpx
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_settings

logger = logging.getLogger(__name__)


def _load_stytch_credentials() -> tuple[str | None, str | None]:
    """
    Load Stytch credentials from Settings (Vault-first).
    
    Returns:
        Tuple of (project_id, secret), or (None, None) if not configured.
    """
    settings = get_settings()
    if settings.stytch_project_id and settings.stytch_secret:
        return settings.stytch_project_id, settings.stytch_secret
    
    return None, None


def _extract_session_token(request: Request) -> str | None:
    """
    Extract a Stytch session token from the request.

    Web embed commonly passes this via:
    - Cookie: `stytch_session_token`
    - Header: `Authorization: Bearer <token>`
    """
    token = request.cookies.get("stytch_session_token")
    if isinstance(token, str) and token.strip():
        return token.strip()

    auth_header = request.headers.get("authorization")
    if not isinstance(auth_header, str):
        auth_header = ""
    if auth_header.lower().startswith("bearer "):
        candidate = auth_header[7:].strip()
        return candidate or None

    return None


def _allowed_email_domains() -> set[str]:
    raw = os.getenv("STYTCH_ALLOWED_EMAIL_DOMAINS", "contrived.com")
    domains = {d.strip().lower() for d in raw.split(",") if d.strip()}
    return domains or {"contrived.com"}


def _email_domain_ok(email: str | None) -> bool:
    if not email:
        return False
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain in _allowed_email_domains()


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
        Validate a session token with the Stytch B2B API.

        Args:
            session_token: The stytch_session_token cookie value.

        Returns:
            Session data dict if valid, None if invalid.
        """
        # Use B2B endpoint for organization-based auth
        url = f"{self._api_base}/v1/b2b/sessions/authenticate"

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
                    session = data.get("session") or {}
                    member = data.get("member") or {}
                    organization = data.get("organization") or {}
                    return {
                        "session_id": session.get("session_id"),
                        "user_id": session.get("user_id"),
                        "started_at": session.get("started_at"),
                        "expires_at": session.get("expires_at"),
                        "member_id": member.get("member_id") or session.get("member_id"),
                        "member_email": member.get("email_address") or member.get("email"),
                        "organization_id": organization.get("organization_id")
                        or session.get("organization_id"),
                        "organization_slug": organization.get("organization_slug"),
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


async def get_stytch_session(
    request: Request,
    *,
    project_id: str | None = None,
    secret: str | None = None,
) -> dict:
    """
    Authenticate the request with a valid Stytch session.

    On success, attaches the session to `request.state.stytch_session` and
    returns the session dict.

    Raises HTTPException on failure.
    """
    project_id = project_id or _load_stytch_credentials()[0]
    secret = secret or _load_stytch_credentials()[1]

    if not project_id or not secret:
        raise HTTPException(status_code=500, detail="Stytch authentication not configured")

    session_token = _extract_session_token(request)
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing Stytch session token")

    validator = StytchSessionValidator(project_id, secret)
    session_data = await validator.validate_session(session_token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired Stytch session")

    if not _email_domain_ok(session_data.get("member_email")):
        raise HTTPException(status_code=403, detail="Forbidden (not a contrived.com session)")

    request.state.stytch_session = session_data
    return session_data


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
        try:
            await get_stytch_session(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await handler(request)

    return wrapper


__all__ = [
    "StytchSessionValidator",
    "get_stytch_session",
    "require_stytch_session",
]
