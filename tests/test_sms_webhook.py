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


class TestSmsWebhookComplianceHandling:
    """Tests for compliance keyword handling in webhook."""

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

    def test_handles_stop_keyword_for_unknown_contact(self, client):
        """STOP keyword from unknown contact records opt-out and sends response."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "STOP",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                        mock_sms = MagicMock()
                        mock_sms.is_configured = True
                        mock_sms.send_sms.return_value = MagicMock(success=True)
                        mock_sms_cls.return_value = mock_sms

                        response = client.post("/webhook/sms", json=payload)

                        # Verify opt-out SMS was sent
                        mock_sms.send_sms.assert_called_once()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["compliance"] is True
        assert data["compliance_type"] == "opt_out"

    def test_handles_help_keyword_for_unknown_contact(self, client):
        """HELP keyword from unknown contact sends help response."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "HELP",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                        mock_sms = MagicMock()
                        mock_sms.is_configured = True
                        mock_sms.send_sms.return_value = MagicMock(success=True)
                        mock_sms_cls.return_value = mock_sms

                        response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["compliance"] is True
        assert data["compliance_type"] == "help"

    def test_handles_start_keyword_for_unknown_contact(self, client):
        """START keyword from unknown contact records opt-in."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "START",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                        mock_sms = MagicMock()
                        mock_sms.is_configured = True
                        mock_sms.send_sms.return_value = MagicMock(success=True)
                        mock_sms_cls.return_value = mock_sms

                        response = client.post("/webhook/sms", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["compliance"] is True
        assert data["compliance_type"] == "opt_in"

    def test_known_contacts_bypass_compliance(self, client):
        """Known contacts should NOT trigger compliance handling."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "STOP",  # compliance keyword
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    # Return a contact (known sender)
                    mock_lookup.lookup.return_value = Contact(
                        name="Mom",
                        googleContactId="people/c123",
                    )
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                        mock_sms = MagicMock()
                        mock_sms_cls.return_value = mock_sms

                        response = client.post("/webhook/sms", json=payload)

                        # Verify NO compliance SMS was sent
                        mock_sms.send_sms.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["contact"] == "Mom"
        # Should NOT have compliance flag
        assert "compliance" not in data


class TestSmsWebhookTelegramNotification:
    """Tests for Telegram notification of unknown SMS senders."""

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

    def test_sends_telegram_notification_for_unknown_sender(self, client):
        """Unknown sender (non-compliance) triggers Telegram notification."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello there, this is a regular message",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                        mock_bot = MagicMock()
                        mock_bot.is_configured = True
                        mock_bot.notify_unknown_sms = AsyncMock(
                            return_value=MagicMock(success=True)
                        )
                        mock_bot_cls.return_value = mock_bot

                        response = client.post("/webhook/sms", json=payload)

                        # Verify Telegram notification was sent
                        mock_bot.notify_unknown_sms.assert_called_once_with(
                            from_number="+15551234567",
                            message="Hello there, this is a regular message",
                            attachment_count=0,
                        )

        assert response.status_code == 200
        data = response.json()
        assert data["telegram_notified"] is True

    def test_no_telegram_notification_for_known_contacts(self, client):
        """Known contacts should NOT receive Telegram notifications."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello from a known person",
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

                    with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                        mock_bot = MagicMock()
                        mock_bot_cls.return_value = mock_bot

                        response = client.post("/webhook/sms", json=payload)

                        # Verify Telegram notification was NOT sent
                        mock_bot.notify_unknown_sms.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert "telegram_notified" not in data

    def test_no_telegram_notification_for_compliance_messages(self, client):
        """Compliance messages should NOT receive Telegram notifications."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "STOP",  # compliance keyword
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                        mock_sms = MagicMock()
                        mock_sms.is_configured = True
                        mock_sms.send_sms.return_value = MagicMock(success=True)
                        mock_sms_cls.return_value = mock_sms

                        with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                            mock_bot = MagicMock()
                            mock_bot_cls.return_value = mock_bot

                            response = client.post("/webhook/sms", json=payload)

                            # Verify Telegram notification was NOT sent for compliance
                            mock_bot.notify_unknown_sms.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert data["compliance"] is True
        assert "telegram_notified" not in data

    def test_handles_telegram_api_failure_gracefully(self, client):
        """Telegram API failure should not fail webhook processing."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello there",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                        mock_bot = MagicMock()
                        mock_bot.is_configured = True
                        # Simulate API failure
                        mock_bot.notify_unknown_sms = AsyncMock(
                            return_value=MagicMock(success=False, error="API error")
                        )
                        mock_bot_cls.return_value = mock_bot

                        response = client.post("/webhook/sms", json=payload)

        # Webhook should still succeed even if Telegram fails
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        # telegram_notified should be absent since notification failed
        assert "telegram_notified" not in data

    def test_includes_attachment_count_in_notification(self, client):
        """Telegram notification includes attachment count for MMS."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Photo message",
                    "media": [
                        {"url": "https://telnyx.com/1.jpg", "content_type": "image/jpeg", "size": 1000},
                        {"url": "https://telnyx.com/2.jpg", "content_type": "image/jpeg", "size": 2000},
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

                    with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                        mock_bot = MagicMock()
                        mock_bot.is_configured = True
                        mock_bot.notify_unknown_sms = AsyncMock(
                            return_value=MagicMock(success=True)
                        )
                        mock_bot_cls.return_value = mock_bot

                        # Mock attachment downloads
                        with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                            mock_response = MagicMock()
                            mock_response.content = b"fake image"
                            mock_response.raise_for_status = MagicMock()
                            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                                return_value=mock_response
                            )

                            response = client.post("/webhook/sms", json=payload)

                        # Verify attachment count was passed
                        mock_bot.notify_unknown_sms.assert_called_once_with(
                            from_number="+15551234567",
                            message="Photo message",
                            attachment_count=2,
                        )

        assert response.status_code == 200


class TestSmsWebhookJorbRouting:
    """Tests for SMS routing to jorb message processing."""

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

    def test_routes_known_contact_to_jorb_buffer(self, client):
        """Known contacts should be routed to jorb message buffer."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15551234567"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Hello from a known contact",
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

                    with patch("server.sms_webhook._get_message_buffer") as mock_buffer_fn:
                        mock_buffer = MagicMock()
                        mock_buffer.buffer_message = AsyncMock(return_value=True)
                        mock_buffer_fn.return_value = mock_buffer

                        response = client.post("/webhook/sms", json=payload)

                        # Verify message was buffered
                        mock_buffer.buffer_message.assert_called_once()
                        call_kwargs = mock_buffer.buffer_message.call_args.kwargs
                        assert call_kwargs["channel"] == "sms"
                        assert call_kwargs["sender"] == "+15551234567"
                        assert call_kwargs["sender_name"] == "Mom"

        assert response.status_code == 200
        data = response.json()
        assert data["jorb_routed"] is True

    def test_routes_jorb_participant_to_buffer(self, client):
        """Jorb participants should be routed to message buffer."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15559876543"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Reply from jorb contact",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None  # Not in Google Contacts
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook._is_jorb_contact", new_callable=AsyncMock) as mock_jorb_check:
                        mock_jorb_check.return_value = True  # Is a jorb participant

                        with patch("server.sms_webhook._get_message_buffer") as mock_buffer_fn:
                            mock_buffer = MagicMock()
                            mock_buffer.buffer_message = AsyncMock(return_value=True)
                            mock_buffer_fn.return_value = mock_buffer

                            response = client.post("/webhook/sms", json=payload)

                            # Verify message was buffered
                            mock_buffer.buffer_message.assert_called_once()

        assert response.status_code == 200
        data = response.json()
        assert data["jorb_routed"] is True
        assert "telegram_notified" not in data  # No notification for jorb participants

    def test_unknown_sender_not_jorb_routed(self, client):
        """Unknown senders who aren't jorb participants should not be routed."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15559999999"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "Random stranger message",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook._is_jorb_contact", new_callable=AsyncMock) as mock_jorb_check:
                        mock_jorb_check.return_value = False

                        with patch("server.sms_webhook._get_message_buffer") as mock_buffer_fn:
                            mock_buffer = MagicMock()
                            mock_buffer.buffer_message = AsyncMock(return_value=True)
                            mock_buffer_fn.return_value = mock_buffer

                            with patch("server.sms_webhook.TelegramBot") as mock_bot_cls:
                                mock_bot = MagicMock()
                                mock_bot.is_configured = True
                                mock_bot.notify_unknown_sms = AsyncMock(
                                    return_value=MagicMock(success=True)
                                )
                                mock_bot_cls.return_value = mock_bot

                                response = client.post("/webhook/sms", json=payload)

                                # Buffer should NOT be called
                                mock_buffer.buffer_message.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert "jorb_routed" not in data
        assert data["telegram_notified"] is True

    def test_compliance_messages_not_jorb_routed(self, client):
        """Compliance messages should not be routed to jorb processing."""
        payload = {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "direction": "inbound",
                    "from": {"phone_number": "+15559999999"},
                    "to": [{"phone_number": "+12148170664"}],
                    "text": "STOP",
                    "media": [],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("server.sms_webhook.ContactLookup") as mock_lookup_cls:
                    mock_lookup = MagicMock()
                    mock_lookup.lookup.return_value = None
                    mock_lookup_cls.return_value = mock_lookup

                    with patch("server.sms_webhook._get_message_buffer") as mock_buffer_fn:
                        mock_buffer = MagicMock()
                        mock_buffer_fn.return_value = mock_buffer

                        with patch("server.sms_webhook.TelnyxSMSService") as mock_sms_cls:
                            mock_sms = MagicMock()
                            mock_sms.is_configured = True
                            mock_sms.send_sms.return_value = MagicMock(success=True)
                            mock_sms_cls.return_value = mock_sms

                            response = client.post("/webhook/sms", json=payload)

                            # Buffer should NOT be called for compliance messages
                            mock_buffer.buffer_message.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert data["compliance"] is True
        assert "jorb_routed" not in data


@pytest.mark.asyncio
class TestSmsJorbContactCheck:
    """Tests for _is_jorb_contact function."""

    async def test_phone_in_active_jorb(self):
        """Returns True if phone is in an active jorb's contacts."""
        from server.sms_webhook import _is_jorb_contact
        from services.jorb_storage import JorbContact

        with patch("server.sms_webhook.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="+15551234567", channel="sms", name="Test"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("+15551234567")
            assert result is True

    async def test_phone_not_in_any_jorb(self):
        """Returns False if phone is not in any jorb's contacts."""
        from server.sms_webhook import _is_jorb_contact
        from services.jorb_storage import JorbContact

        with patch("server.sms_webhook.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            mock_jorb.contacts = [
                JorbContact(identifier="+15559999999", channel="sms", name="Other"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("+15551234567")
            assert result is False

    async def test_no_open_jorbs(self):
        """Returns False if there are no open jorbs."""
        from server.sms_webhook import _is_jorb_contact

        with patch("server.sms_webhook.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.list_jorbs = AsyncMock(return_value=[])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("+15551234567")
            assert result is False

    async def test_only_checks_sms_channel(self):
        """Only matches phone numbers in SMS channel contacts."""
        from server.sms_webhook import _is_jorb_contact
        from services.jorb_storage import JorbContact

        with patch("server.sms_webhook.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_jorb = MagicMock()
            # Same identifier but on Telegram channel
            mock_jorb.contacts = [
                JorbContact(identifier="+15551234567", channel="telegram", name="Test"),
            ]
            mock_storage.list_jorbs = AsyncMock(return_value=[mock_jorb])
            mock_storage_cls.return_value = mock_storage

            result = await _is_jorb_contact("+15551234567")
            assert result is False
