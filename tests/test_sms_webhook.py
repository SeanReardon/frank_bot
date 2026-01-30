"""Unit tests for SMS webhook handler."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from server.sms_webhook import (
    _generate_message_id,
    _parse_telnyx_payload,
    sms_webhook_handler,
)
from services.contact_lookup import Contact


class TestGenerateMessageId:
    """Tests for message ID generation."""

    def test_generates_unique_id(self):
        """Message ID includes timestamp and phone number."""
        ts = datetime(2026, 1, 29, 18, 45, 32, tzinfo=timezone.utc)
        message_id = _generate_message_id(ts, "+15551234567")
        assert message_id.startswith("sms_")
        assert "+15551234567" in message_id


class TestParseTelnyxPayload:
    """Tests for Telnyx payload parsing."""

    def test_parse_inbound_message(self):
        """Parses inbound message correctly."""
        payload = {
            "data": {
                "event_type": "message.received",
                "id": "telnyx-event-123",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello there!",
                    "media": [],
                    "received_at": "2026-01-29T18:45:32Z",
                },
            },
        }

        result = _parse_telnyx_payload(payload)

        assert result is not None
        assert result["from_number"] == "+15551234567"
        assert result["to_number"] == "+12148170664"
        assert result["text"] == "Hello there!"
        assert result["attachments"] == []

    def test_parse_mms_with_attachments(self):
        """Parses MMS with media attachments."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Photo",
                    "media": [
                        {
                            "url": "https://telnyx.com/media/123.jpg",
                            "content_type": "image/jpeg",
                            "size": 12345,
                        }
                    ],
                },
            },
        }

        result = _parse_telnyx_payload(payload)

        assert result is not None
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["url"] == "https://telnyx.com/media/123.jpg"
        assert result["attachments"][0]["content_type"] == "image/jpeg"
        assert result["attachments"][0]["size"] == 12345

    def test_skip_outbound_message(self):
        """Skips outbound messages."""
        payload = {
            "data": {
                "event_type": "message.sent",
                "payload": {
                    "direction": "outbound",
                    "from": {"phone_number": "+12148170664"},
                    "to": [{"phone_number": "+15551234567"}],
                    "text": "Response",
                },
            },
        }

        result = _parse_telnyx_payload(payload)
        assert result is None

    def test_skip_delivery_receipt(self):
        """Skips delivery receipt events."""
        payload = {
            "data": {
                "event_type": "message.delivered",
                "payload": {
                    "direction": "outbound",
                },
            },
        }

        result = _parse_telnyx_payload(payload)
        assert result is None

    def test_skip_missing_phone_numbers(self):
        """Skips messages without phone numbers."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {},
                    "to": [],
                    "text": "Hello",
                },
            },
        }

        result = _parse_telnyx_payload(payload)
        assert result is None

    def test_handles_to_as_dict(self):
        """Handles to field as dict instead of list."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": {"phone_number": "+12148170664"},  # dict, not list
                    "text": "Hello",
                },
            },
        }

        result = _parse_telnyx_payload(payload)

        assert result is not None
        assert result["to_number"] == "+12148170664"


class TestSmsWebhookHandler:
    """Tests for the SMS webhook handler endpoint."""

    @pytest.fixture
    def app(self):
        """Create a test application with the webhook route."""
        return Starlette(
            routes=[Route("/webhook/sms", sms_webhook_handler, methods=["POST"])]
        )

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_processes_inbound_message(self, client):
        """Inbound message is processed and stored."""
        payload = {
            "data": {
                "event_type": "message.received",
                "id": "telnyx-123",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello",
                    "media": [],
                    "received_at": "2026-01-29T18:45:32Z",
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["message_id"].startswith("sms_")
        assert data["contact"] is None

    def test_processes_message_with_contact(self, client):
        """Inbound message resolves contact."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = Contact(
                        name="Mom",
                        googleContactId="people/c123",
                    )
                    mock_lookup_cls.return_value = mock_lookup

                    response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["contact"] == "Mom"

    def test_skips_non_inbound(self, client):
        """Non-inbound messages are skipped."""
        payload = {
            "data": {
                "event_type": "message.sent",
                "payload": {
                    "direction": "outbound",
                },
            },
        }

        response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert "not inbound" in data["reason"]

    def test_invalid_json(self, client):
        """Invalid JSON returns error."""
        response = client.post(
            "/webhook/sms",
            content="not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"

    def test_contact_lookup_failure(self, client):
        """Contact lookup failure doesn't prevent processing."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.side_effect = Exception("API error")
                    mock_lookup_cls.return_value = mock_lookup

                    response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["contact"] is None

    def test_stores_message_with_mms(self, client):
        """MMS message with attachments is stored."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Photo",
                    "media": [
                        {
                            "url": "https://telnyx.com/media/123.jpg",
                            "content_type": "image/jpeg",
                            "size": 12345,
                        }
                    ],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    # Mock the attachment download
                    with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                        mock_response = MagicMock()
                        mock_response.content = b"fake image"
                        mock_response.raise_for_status = MagicMock()
                        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                            return_value=mock_response
                        )

                        response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
