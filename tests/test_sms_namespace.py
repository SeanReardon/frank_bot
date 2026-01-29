"""
Unit tests for SMSNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import SMSNamespace, FrankAPI


class TestSMSNamespaceSend:
    """Tests for SMSNamespace.send()."""

    def test_send_to_contact_name(self) -> None:
        """Send method works with contact name."""
        mock_result = {
            "message": "SMS sent to John Doe (+15551234567)",
            "success": True,
            "recipient": "John Doe",
            "to_number": "+15551234567",
            "from_number": "+15559876543",
            "message_id": "msg_123abc",
            "text_preview": "Hello, this is a test message.",
        }

        with patch("actions.sms.send_sms_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SMSNamespace()
            result = namespace.send("John Doe", "Hello, this is a test message.")

            # Verify action was called with correct arguments
            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["recipient"] == "John Doe"
            assert call_args["message"] == "Hello, this is a test message."

            # Verify result is passed through
            assert result == mock_result
            assert result["success"] is True
            assert result["recipient"] == "John Doe"

    def test_send_to_phone_number(self) -> None:
        """Send method works with phone number."""
        mock_result = {
            "message": "SMS sent to +15551234567",
            "success": True,
            "recipient": "+15551234567",
            "to_number": "+15551234567",
            "from_number": "+15559876543",
            "message_id": "msg_456def",
            "text_preview": "Direct message.",
        }

        with patch("actions.sms.send_sms_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SMSNamespace()
            result = namespace.send("+15551234567", "Direct message.")

            call_args = mock_action.call_args[0][0]
            assert call_args["recipient"] == "+15551234567"
            assert call_args["message"] == "Direct message."
            assert result == mock_result

    def test_send_long_message_truncated_preview(self) -> None:
        """Send method handles long messages with truncated preview."""
        long_message = "A" * 150
        mock_result = {
            "message": "SMS sent to Jane (+15551234567)",
            "success": True,
            "recipient": "Jane",
            "to_number": "+15551234567",
            "from_number": "+15559876543",
            "message_id": "msg_789ghi",
            "text_preview": "A" * 100 + "...",
        }

        with patch("actions.sms.send_sms_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            namespace = SMSNamespace()
            result = namespace.send("Jane", long_message)

            call_args = mock_action.call_args[0][0]
            assert call_args["message"] == long_message
            assert result["text_preview"].endswith("...")


class TestFrankAPISMSIntegration:
    """Tests for FrankAPI.sms namespace access."""

    def test_frank_api_has_sms_namespace(self) -> None:
        """FrankAPI provides access to SMSNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "sms")
        assert isinstance(api.sms, SMSNamespace)

    def test_frank_api_sms_is_same_instance(self) -> None:
        """FrankAPI returns the same SMSNamespace instance."""
        api = FrankAPI()
        assert api.sms is api.sms

    def test_frank_api_sms_send_works(self) -> None:
        """FrankAPI.sms.send() works correctly."""
        mock_result = {
            "message": "SMS sent",
            "success": True,
            "recipient": "Bob",
            "to_number": "+15551234567",
            "from_number": "+15559876543",
            "message_id": "msg_test",
            "text_preview": "Test",
        }

        with patch("actions.sms.send_sms_action", new_callable=AsyncMock) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.sms.send("Bob", "Test")

            assert result == mock_result
            mock_action.assert_called_once()
