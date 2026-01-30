"""
Unit tests for EmailService.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if aiosmtplib is available
try:
    import aiosmtplib
    HAS_AIOSMTPLIB = True
except ImportError:
    HAS_AIOSMTPLIB = False

from services.email_service import EmailService
from services.jorb_storage import Jorb


@pytest.fixture
def configured_service():
    """Create a configured EmailService."""
    return EmailService(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_password="secret",
        default_to="owner@example.com",
    )


@pytest.fixture
def unconfigured_service():
    """Create an unconfigured EmailService."""
    return EmailService(
        smtp_host=None,
        smtp_port=587,
        smtp_user=None,
        smtp_password=None,
    )


@pytest.fixture
def sample_jorb():
    """Create a sample Jorb for testing."""
    return Jorb(
        id="jorb_12345678",
        name="Hotel Booking",
        status="paused",
        original_plan="Book a hotel in SF for March 17-21",
        progress_summary="Contacted Magic, received quote for $289/night",
        paused_reason="Booking requires approval",
        needs_approval_for="commit",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


class TestEmailServiceConfig:
    """Tests for EmailService configuration."""

    def test_is_configured_with_all_settings(self, configured_service):
        """Test is_configured returns True with all settings."""
        assert configured_service.is_configured is True

    def test_is_configured_missing_host(self):
        """Test is_configured returns False without host."""
        service = EmailService(
            smtp_host=None,
            smtp_user="user",
            smtp_password="pass",
        )
        assert service.is_configured is False

    def test_is_configured_missing_user(self):
        """Test is_configured returns False without user."""
        service = EmailService(
            smtp_host="smtp.example.com",
            smtp_user=None,
            smtp_password="pass",
        )
        assert service.is_configured is False

    def test_is_configured_missing_password(self):
        """Test is_configured returns False without password."""
        service = EmailService(
            smtp_host="smtp.example.com",
            smtp_user="user",
            smtp_password=None,
        )
        assert service.is_configured is False

    def test_default_recipient(self, configured_service):
        """Test default_recipient returns configured value."""
        assert configured_service.default_recipient == "owner@example.com"


class TestSendEmail:
    """Tests for send method."""

    async def test_send_not_configured(self, unconfigured_service):
        """Test send returns False when not configured."""
        result = await unconfigured_service.send(
            to="test@example.com",
            subject="Test",
            body_text="Hello",
        )
        assert result is False

    async def test_send_no_body(self, configured_service):
        """Test send returns False with no body."""
        result = await configured_service.send(
            to="test@example.com",
            subject="Test",
        )
        assert result is False

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_send_with_text_only(self, configured_service):
        """Test sending email with text body only."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send(
                to="recipient@example.com",
                subject="Test Subject",
                body_text="Hello, this is a test.",
            )

            assert result is True
            mock_send.assert_called_once()

            # Check the message was constructed correctly
            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert msg["Subject"] == "Test Subject"
            assert msg["To"] == "recipient@example.com"
            assert msg["From"] == "test@example.com"

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_send_with_html_only(self, configured_service):
        """Test sending email with HTML body only (plain text auto-generated)."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send(
                to="recipient@example.com",
                subject="Test Subject",
                body_html="<h1>Hello</h1><p>This is a test.</p>",
            )

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_send_with_both_bodies(self, configured_service):
        """Test sending email with both HTML and text bodies."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send(
                to="recipient@example.com",
                subject="Test Subject",
                body_html="<h1>Hello</h1>",
                body_text="Hello (plain text)",
            )

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_send_smtp_error(self, configured_service):
        """Test send returns False on SMTP error."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP connection failed")

            result = await configured_service.send(
                to="recipient@example.com",
                subject="Test",
                body_text="Hello",
            )

            assert result is False


class TestNotifyJorbPaused:
    """Tests for notify_jorb_paused method."""

    async def test_notify_paused_no_recipient(self, sample_jorb):
        """Test notify_jorb_paused returns False without default recipient."""
        service = EmailService(
            smtp_host="smtp.example.com",
            smtp_user="user",
            smtp_password="pass",
            default_to=None,
        )

        result = await service.notify_jorb_paused(sample_jorb)
        assert result is False

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_notify_paused_success(self, configured_service, sample_jorb):
        """Test notify_jorb_paused sends email correctly."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.notify_jorb_paused(sample_jorb)

            assert result is True
            mock_send.assert_called_once()

            # Check the message
            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert "[Frank Bot] Jorb paused" in msg["Subject"]
            assert "Hotel Booking" in msg["Subject"]
            assert msg["To"] == "owner@example.com"

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_notify_paused_smtp_error(self, configured_service, sample_jorb):
        """Test notify_jorb_paused returns False on SMTP error."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP error")

            result = await configured_service.notify_jorb_paused(sample_jorb)
            assert result is False


class TestNotifyJorbComplete:
    """Tests for notify_jorb_complete method."""

    async def test_notify_complete_no_recipient(self, sample_jorb):
        """Test notify_jorb_complete returns False without default recipient."""
        service = EmailService(
            smtp_host="smtp.example.com",
            smtp_user="user",
            smtp_password="pass",
            default_to=None,
        )

        result = await service.notify_jorb_complete(sample_jorb)
        assert result is False

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_notify_complete_success(self, configured_service, sample_jorb):
        """Test notify_jorb_complete sends email correctly."""
        sample_jorb.status = "complete"

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.notify_jorb_complete(sample_jorb)

            assert result is True
            mock_send.assert_called_once()

            # Check the message
            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert "[Frank Bot] Jorb complete" in msg["Subject"]
            assert "Hotel Booking" in msg["Subject"]

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_notify_complete_smtp_error(self, configured_service, sample_jorb):
        """Test notify_jorb_complete returns False on SMTP error."""
        sample_jorb.status = "complete"

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP error")

            result = await configured_service.notify_jorb_complete(sample_jorb)
            assert result is False
