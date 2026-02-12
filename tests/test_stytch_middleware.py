"""
Unit tests for Stytch session validation middleware.

Tests verify session validation logic with mocked Stytch API.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from server.stytch_middleware import (
    StytchSessionValidator,
    require_stytch_session,
)


class TestStytchSessionValidator:
    """Tests for StytchSessionValidator class."""

    def test_test_project_uses_test_api(self) -> None:
        """Test projects use the test API base URL."""
        validator = StytchSessionValidator(
            "project-test-abc123",
            "secret-test-xyz789",
        )
        assert validator._is_test is True
        assert "test.stytch.com" in validator._api_base

    def test_live_project_uses_live_api(self) -> None:
        """Live projects use the production API base URL."""
        validator = StytchSessionValidator(
            "project-live-abc123",
            "secret-live-xyz789",
        )
        assert validator._is_test is False
        assert "api.stytch.com" in validator._api_base

    @pytest.mark.asyncio
    async def test_validate_session_success(self) -> None:
        """Valid session returns session data."""
        validator = StytchSessionValidator(
            "project-test-abc123",
            "secret-test-xyz789",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session": {
                "session_id": "session-test-123",
                "user_id": "user-test-456",
                "started_at": "2026-01-29T10:00:00Z",
                "expires_at": "2026-01-29T22:00:00Z",
            }
        }

        with patch("server.stytch_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await validator.validate_session("valid-token")

            assert result is not None
            assert result["session_id"] == "session-test-123"
            assert result["user_id"] == "user-test-456"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_session_invalid(self) -> None:
        """Invalid session returns None."""
        validator = StytchSessionValidator(
            "project-test-abc123",
            "secret-test-xyz789",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Session not found"

        with patch("server.stytch_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await validator.validate_session("invalid-token")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_session_network_error(self) -> None:
        """Network error returns None."""
        import httpx

        validator = StytchSessionValidator(
            "project-test-abc123",
            "secret-test-xyz789",
        )

        with patch("server.stytch_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )
            MockClient.return_value.__aenter__.return_value = mock_client

            result = await validator.validate_session("some-token")

            assert result is None


class TestRequireStytchSession:
    """Tests for require_stytch_session decorator."""

    def _make_mock_request(
        self,
        cookies: dict | None = None,
    ) -> MagicMock:
        """Create a mock Starlette Request."""
        request = MagicMock(spec=Request)
        request.cookies = cookies or {}
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_missing_stytch_config(self) -> None:
        """Returns 500 when Stytch is not configured."""
        mock_settings = MagicMock()
        mock_settings.stytch_project_id = None
        mock_settings.stytch_secret = None

        @require_stytch_session
        async def handler(request: Request) -> JSONResponse:
            return JSONResponse({"message": "success"})

        with patch("server.stytch_middleware.get_settings", return_value=mock_settings):
            request = self._make_mock_request()
            response = await handler(request)

            assert response.status_code == 500
            assert b"not configured" in response.body.lower()

    @pytest.mark.asyncio
    async def test_missing_session_cookie(self) -> None:
        """Returns 401 when session cookie is missing."""
        mock_settings = MagicMock()
        mock_settings.stytch_project_id = "project-test-123"
        mock_settings.stytch_secret = "secret-test-456"

        @require_stytch_session
        async def handler(request: Request) -> JSONResponse:
            return JSONResponse({"message": "success"})

        with patch("server.stytch_middleware.get_settings", return_value=mock_settings):
            request = self._make_mock_request(cookies={})
            response = await handler(request)

            assert response.status_code == 401
            assert b"missing" in response.body.lower()

    @pytest.mark.asyncio
    async def test_invalid_session_token(self) -> None:
        """Returns 401 when session token is invalid."""
        mock_settings = MagicMock()
        mock_settings.stytch_project_id = "project-test-123"
        mock_settings.stytch_secret = "secret-test-456"

        @require_stytch_session
        async def handler(request: Request) -> JSONResponse:
            return JSONResponse({"message": "success"})

        with patch("server.stytch_middleware.get_settings", return_value=mock_settings):
            with patch.object(
                StytchSessionValidator,
                "validate_session",
                new_callable=AsyncMock,
                return_value=None,
            ):
                request = self._make_mock_request(
                    cookies={"stytch_session_token": "invalid-token"}
                )
                response = await handler(request)

                assert response.status_code == 401
                assert b"invalid or expired" in response.body.lower()

    @pytest.mark.asyncio
    async def test_valid_session_token(self) -> None:
        """Allows request through when session is valid."""
        mock_settings = MagicMock()
        mock_settings.stytch_project_id = "project-test-123"
        mock_settings.stytch_secret = "secret-test-456"

        @require_stytch_session
        async def handler(request: Request) -> JSONResponse:
            # Verify session data was attached to request
            assert hasattr(request.state, "stytch_session")
            return JSONResponse({"message": "success"})

        session_data = {
            "session_id": "session-test-123",
            "user_id": "user-test-456",
            "started_at": "2026-01-29T10:00:00Z",
            "expires_at": "2026-01-29T22:00:00Z",
            "member_email": "sean@contrived.com",
        }

        with patch("server.stytch_middleware.get_settings", return_value=mock_settings):
            with patch.object(
                StytchSessionValidator,
                "validate_session",
                new_callable=AsyncMock,
                return_value=session_data,
            ):
                request = self._make_mock_request(
                    cookies={"stytch_session_token": "valid-token"}
                )
                response = await handler(request)

                assert response.status_code == 200
                assert request.state.stytch_session == session_data
