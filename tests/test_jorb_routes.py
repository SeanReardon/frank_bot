"""
Integration tests for jorb routes.
"""

import asyncio
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from config import Settings
from server.routes import build_action_routes
from services.jorb_storage import JorbStorage


def run_async(coro):
    """Helper to run coroutine in sync test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        app_version="test",
        host="localhost",
        port=8000,
        log_file="test.log",
        log_level="DEBUG",
        default_timezone="UTC",
        google_token_file="token.json",
        google_credentials_file=None,
        google_client_id=None,
        google_client_secret=None,
        google_calendar_scopes=(),
        google_contacts_scopes=(),
        public_base_url="http://localhost:8000",
        actions_api_key="test-api-key",
        actions_name_for_human="Test",
        actions_name_for_model="test",
        actions_description_for_human="Test",
        actions_description_for_model="Test",
        actions_logo_url=None,
        actions_contact_email=None,
        actions_legal_url=None,
        actions_openapi_path="openapi/spec.json",
        swarm_oauth_token=None,
        swarm_api_version="20240501",
        telnyx_api_key=None,
        telnyx_phone_number=None,
        notify_numbers=(),
        telegram_api_id=None,
        telegram_api_hash=None,
        telegram_phone=None,
        telegram_session_name="test",
        telegram_bot_token=None,
        telegram_bot_chat_id=None,
        stytch_project_id=None,
        stytch_secret=None,
        openai_api_key=None,
        jorbs_db_path="./test_jorbs.db",
        jorbs_progress_log="./test_progress.txt",
        agent_spend_limit=100.0,
        context_reset_days=3,
        debounce_telegram_seconds=60,
        debounce_sms_seconds=30,
        smtp_host=None,
        smtp_port=587,
        smtp_user=None,
        smtp_password=None,
        digest_email_to=None,
        digest_time="08:00",
    )


@pytest.fixture
def app(settings):
    """Create test application."""
    from starlette.applications import Starlette
    from starlette.routing import Router

    routes = build_action_routes(settings)
    return Starlette(routes=routes)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestJorbRoutes:
    """Tests for jorb HTTP routes."""

    def test_list_jorbs_public(self, client, temp_db_path):
        """Test that /jorbs is public (no API key required for web dashboard)."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Works without API key
            response = client.get("/jorbs")
            assert response.status_code == 200
            data = response.json()
            assert "count" in data
            assert "jorbs" in data

    def test_list_jorbs_with_api_key(self, client, temp_db_path):
        """Test listing jorbs also works with API key (for ChatGPT)."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            response = client.get(
                "/jorbs",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "count" in data
            assert "jorbs" in data

    def test_create_jorb(self, client, temp_db_path):
        """Test creating a jorb."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            response = client.get(
                "/jorbs/create",
                params={
                    "name": "Test Task",
                    "plan": "Do the thing",
                    "start_immediately": "false",
                },
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Test Task"
            assert data["plan"] == "Do the thing"
            assert data["jorb_id"].startswith("jorb_")

    def test_get_jorb(self, client, temp_db_path):
        """Test getting a specific jorb."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create a jorb first
            jorb = run_async(storage.create_jorb("Test", "Plan"))

            response = client.get(
                f"/jorbs/{jorb.id}",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["jorb_id"] == jorb.id
            assert data["name"] == "Test"

    def test_get_jorb_not_found(self, client, temp_db_path):
        """Test getting a non-existent jorb."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            response = client.get(
                "/jorbs/jorb_nonexistent",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 400
            assert "not found" in response.text.lower()

    def test_get_jorb_messages(self, client, temp_db_path):
        """Test getting jorb messages."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create a jorb first
            jorb = run_async(storage.create_jorb("Test", "Plan"))

            response = client.get(
                f"/jorbs/{jorb.id}/messages",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["jorb_id"] == jorb.id
            assert "messages" in data

    def test_approve_jorb(self, client, temp_db_path):
        """Test approving a paused jorb."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create and pause a jorb
            jorb = run_async(storage.create_jorb("Test", "Plan"))
            run_async(storage.update_jorb(jorb.id, status="paused"))

            with patch("actions.jorbs.AgentRunner") as mock_runner_class:
                mock_runner = MagicMock()
                mock_runner_class.return_value = mock_runner
                mock_runner.is_configured = False

                response = client.get(
                    f"/jorbs/{jorb.id}/approve",
                    params={"decision": "Go ahead"},
                    headers={"X-API-Key": "test-api-key"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "running"
            assert data["decision"] == "Go ahead"

    def test_approve_jorb_not_paused(self, client, temp_db_path):
        """Test approving a non-paused/non-planning jorb fails."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create a running jorb
            jorb = run_async(storage.create_jorb("Test", "Plan"))
            run_async(storage.update_jorb(jorb.id, status="running"))

            response = client.get(
                f"/jorbs/{jorb.id}/approve",
                params={"decision": "Go ahead"},
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 400
            # Jorb must be paused or planning to approve
            assert "paused or planning" in response.text.lower()

    def test_cancel_jorb(self, client, temp_db_path):
        """Test cancelling a jorb."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create a running jorb
            jorb = run_async(storage.create_jorb("Test", "Plan"))
            run_async(storage.update_jorb(jorb.id, status="running"))

            response = client.get(
                f"/jorbs/{jorb.id}/cancel",
                params={"reason": "No longer needed"},
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"
            assert data["reason"] == "No longer needed"

    def test_cancel_complete_jorb_fails(self, client, temp_db_path):
        """Test cancelling a complete jorb fails."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            # Create a complete jorb
            jorb = run_async(storage.create_jorb("Test", "Plan"))
            run_async(storage.update_jorb(jorb.id, status="complete"))

            response = client.get(
                f"/jorbs/{jorb.id}/cancel",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 400
            assert "cannot cancel" in response.text.lower()

    def test_brief_me(self, client, temp_db_path):
        """Test getting a briefing."""
        with patch("actions.jorbs.JorbStorage") as mock_class:
            storage = JorbStorage(db_path=temp_db_path)
            mock_class.return_value = storage

            response = client.get(
                "/jorbs/brief",
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "needs_attention" in data
            assert "activity_summary" in data
            assert "pending_decisions" in data
