"""Tests for Telnyx SMS service."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.telnyx_sms import TelnyxSMSService, SMSResult, _generate_outbound_message_id


class TestGenerateOutboundMessageId:
    """Tests for outbound message ID generation."""

    def test_generates_unique_id(self):
        """Message ID includes timestamp and phone number."""
        ts = datetime(2026, 1, 30, 14, 30, 0, tzinfo=timezone.utc)
        message_id = _generate_outbound_message_id(ts, "+15551234567")
        assert message_id.startswith("sms_")
        assert "+15551234567" in message_id


class TestTelnyxSMSServiceOutboundStorage:
    """Tests for outbound message storage."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with configured Telnyx."""
        mock = MagicMock()
        mock.telnyx_api_key = "test-api-key"
        mock.telnyx_phone_number = "+12148170664"
        mock.notify_numbers = ()
        return mock

    def test_stores_outbound_message_on_successful_send(self, mock_settings):
        """Outbound message is stored after successful send."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("services.telnyx_sms.get_settings", return_value=mock_settings):
                    # Mock the telnyx module at import time
                    mock_message = MagicMock()
                    mock_response = MagicMock()
                    mock_response.id = "telnyx-msg-123"
                    mock_message.create.return_value = mock_response

                    with patch("services.telnyx_sms.telnyx") as mock_telnyx:
                        mock_telnyx.Message = mock_message
                        mock_telnyx.error = MagicMock()
                        mock_telnyx.error.TelnyxError = Exception

                        with patch("services.contact_lookup.ContactLookup") as mock_lookup_cls:
                            mock_lookup = MagicMock()
                            mock_lookup.lookup.return_value = None
                            mock_lookup_cls.return_value = mock_lookup

                            service = TelnyxSMSService()
                            result = service.send_sms("+15551234567", "Hello from Frank Bot")

                        assert result.success is True
                        assert result.message_id == "telnyx-msg-123"

                        # Verify message was stored
                        sms_dir = Path(tmpdir) / "sms" / "12148170664"
                        assert sms_dir.exists()
                        json_files = list(sms_dir.glob("*.json"))
                        assert len(json_files) == 1

                        # Verify message content
                        with open(json_files[0]) as f:
                            stored = json.load(f)
                            assert stored["direction"] == "outbound"
                            assert stored["localNumber"] == "+12148170664"
                            assert stored["remoteNumber"] == "+15551234567"
                            assert stored["content"] == "Hello from Frank Bot"
                            assert stored["processed"] is True
                            assert stored["telnyxMessageId"] == "telnyx-msg-123"

    def test_stores_outbound_message_with_contact(self, mock_settings):
        """Outbound message includes contact info when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("services.telnyx_sms.get_settings", return_value=mock_settings):
                    mock_message = MagicMock()
                    mock_response = MagicMock()
                    mock_response.id = "telnyx-msg-456"
                    mock_message.create.return_value = mock_response

                    with patch("services.telnyx_sms.telnyx") as mock_telnyx:
                        mock_telnyx.Message = mock_message
                        mock_telnyx.error = MagicMock()
                        mock_telnyx.error.TelnyxError = Exception

                        with patch("services.contact_lookup.ContactLookup") as mock_lookup_cls:
                            from services.contact_lookup import Contact as LookupContact
                            mock_lookup = MagicMock()
                            mock_lookup.lookup.return_value = LookupContact(
                                name="Mom",
                                googleContactId="people/c123",
                            )
                            mock_lookup_cls.return_value = mock_lookup

                            service = TelnyxSMSService()
                            result = service.send_sms("+15551234567", "Hi Mom!")

                        assert result.success is True

                        # Verify contact info was stored
                        sms_dir = Path(tmpdir) / "sms" / "12148170664"
                        json_files = list(sms_dir.glob("*.json"))
                        assert len(json_files) == 1

                        with open(json_files[0]) as f:
                            stored = json.load(f)
                            assert stored["contact"]["name"] == "Mom"
                            assert stored["contact"]["googleContactId"] == "people/c123"

    def test_does_not_store_on_failed_send(self, mock_settings):
        """No message stored when send fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("services.telnyx_sms.get_settings", return_value=mock_settings):
                    mock_message = MagicMock()

                    # Create a custom exception class for TelnyxError
                    class MockTelnyxError(Exception):
                        pass

                    mock_message.create.side_effect = MockTelnyxError("API error")

                    with patch("services.telnyx_sms.telnyx") as mock_telnyx:
                        mock_telnyx.Message = mock_message
                        mock_telnyx.error = MagicMock()
                        mock_telnyx.error.TelnyxError = MockTelnyxError

                        service = TelnyxSMSService()
                        result = service.send_sms("+15551234567", "Hello")

                        assert result.success is False

                        # Verify no message was stored
                        sms_dir = Path(tmpdir) / "sms" / "12148170664"
                        if sms_dir.exists():
                            json_files = list(sms_dir.glob("*.json"))
                            assert len(json_files) == 0

    def test_send_succeeds_even_if_storage_fails(self, mock_settings):
        """SMS send still succeeds if storage fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("services.telnyx_sms.get_settings", return_value=mock_settings):
                    mock_message = MagicMock()
                    mock_response = MagicMock()
                    mock_response.id = "telnyx-msg-789"
                    mock_message.create.return_value = mock_response

                    with patch("services.telnyx_sms.telnyx") as mock_telnyx:
                        mock_telnyx.Message = mock_message
                        mock_telnyx.error = MagicMock()
                        mock_telnyx.error.TelnyxError = Exception

                        # Make storage fail
                        with patch("services.sms_storage.SMSStorage.store_message") as mock_store:
                            mock_store.side_effect = Exception("Storage error")

                            with patch("services.contact_lookup.ContactLookup") as mock_lookup_cls:
                                mock_lookup = MagicMock()
                                mock_lookup.lookup.return_value = None
                                mock_lookup_cls.return_value = mock_lookup

                                service = TelnyxSMSService()
                                result = service.send_sms("+15551234567", "Hello")

                        # SMS should still succeed
                        assert result.success is True
                        assert result.message_id == "telnyx-msg-789"

    def test_contact_lookup_failure_does_not_prevent_storage(self, mock_settings):
        """Message is still stored even if contact lookup fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"DATA_DIR": tmpdir}):
                with patch("services.telnyx_sms.get_settings", return_value=mock_settings):
                    mock_message = MagicMock()
                    mock_response = MagicMock()
                    mock_response.id = "telnyx-msg-999"
                    mock_message.create.return_value = mock_response

                    with patch("services.telnyx_sms.telnyx") as mock_telnyx:
                        mock_telnyx.Message = mock_message
                        mock_telnyx.error = MagicMock()
                        mock_telnyx.error.TelnyxError = Exception

                        with patch("services.contact_lookup.ContactLookup") as mock_lookup_cls:
                            mock_lookup = MagicMock()
                            mock_lookup.lookup.side_effect = Exception("Lookup error")
                            mock_lookup_cls.return_value = mock_lookup

                            service = TelnyxSMSService()
                            result = service.send_sms("+15551234567", "Hello")

                        assert result.success is True

                        # Verify message was still stored (without contact)
                        sms_dir = Path(tmpdir) / "sms" / "12148170664"
                        json_files = list(sms_dir.glob("*.json"))
                        assert len(json_files) == 1

                        with open(json_files[0]) as f:
                            stored = json.load(f)
                            assert stored["contact"] is None
