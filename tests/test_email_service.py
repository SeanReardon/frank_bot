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

from services.email_service import EmailService, JorbCosts, JorbDigestSummary
from services.jorb_storage import Jorb, JorbMessage, JorbWithMessages


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


class TestBuildJorbSummary:
    """Tests for _build_jorb_summary method."""

    @pytest.fixture
    def sample_messages(self):
        """Create sample messages for testing."""
        return [
            JorbMessage(
                id="msg_1",
                jorb_id="jorb_12345678",
                timestamp="2026-01-30T10:00:00+00:00",
                direction="outbound",
                channel="sms",
                recipient="+15551234567",
                content="Hi, this is Frank Bot.",
                agent_reasoning="Initial outreach to contact.",
            ),
            JorbMessage(
                id="msg_2",
                jorb_id="jorb_12345678",
                timestamp="2026-01-30T10:05:00+00:00",
                direction="inbound",
                channel="sms",
                sender="+15551234567",
                sender_name="Magic Hotel",
                content="Hello! How can I help you?",
            ),
            JorbMessage(
                id="msg_3",
                jorb_id="jorb_12345678",
                timestamp="2026-01-30T10:10:00+00:00",
                direction="outbound",
                channel="telegram",
                recipient="@magic_hotel",
                content="Can you send availability?",
                agent_reasoning="Requesting availability info from alternative channel.",
            ),
        ]

    def test_counts_messages_correctly(self, configured_service, sample_jorb, sample_messages):
        """Test message counting is accurate."""
        summary = configured_service._build_jorb_summary(sample_jorb, sample_messages)

        assert summary.costs.message_count == 3
        assert summary.costs.inbound_count == 1
        assert summary.costs.outbound_count == 2
        assert summary.costs.sms_count == 2
        assert summary.costs.telegram_count == 1

    def test_extracts_key_decisions(self, configured_service, sample_jorb, sample_messages):
        """Test key decisions are extracted from agent reasoning."""
        summary = configured_service._build_jorb_summary(sample_jorb, sample_messages)

        assert len(summary.key_decisions) == 2
        assert "Initial outreach" in summary.key_decisions[0]
        assert "alternative channel" in summary.key_decisions[1]

    def test_limits_key_decisions_to_5(self, configured_service, sample_jorb):
        """Test key decisions are limited to 5."""
        messages = [
            JorbMessage(
                id=f"msg_{i}",
                jorb_id="jorb_12345678",
                timestamp=f"2026-01-30T10:{i:02d}:00+00:00",
                direction="outbound",
                channel="sms",
                recipient="+15551234567",
                content=f"Message {i}",
                agent_reasoning=f"Reasoning for message {i}",
            )
            for i in range(10)
        ]

        summary = configured_service._build_jorb_summary(sample_jorb, messages)
        assert len(summary.key_decisions) == 5
        # Should be the last 5
        assert "message 5" in summary.key_decisions[0]
        assert "message 9" in summary.key_decisions[4]

    def test_empty_messages(self, configured_service, sample_jorb):
        """Test handling of empty messages list."""
        summary = configured_service._build_jorb_summary(sample_jorb, [])

        assert summary.costs.message_count == 0
        assert summary.key_decisions == []


class TestSendDailyDigest:
    """Tests for send_daily_digest method."""

    @pytest.fixture
    def sample_jorb_with_messages(self, sample_jorb):
        """Create a sample JorbWithMessages."""
        sample_jorb.status = "running"
        messages = [
            JorbMessage(
                id="msg_1",
                jorb_id=sample_jorb.id,
                timestamp="2026-01-30T10:00:00+00:00",
                direction="outbound",
                channel="sms",
                recipient="+15551234567",
                content="Initial contact message",
                agent_reasoning="Starting the task.",
            ),
            JorbMessage(
                id="msg_2",
                jorb_id=sample_jorb.id,
                timestamp="2026-01-30T10:30:00+00:00",
                direction="inbound",
                channel="sms",
                sender="+15551234567",
                sender_name="Hotel",
                content="Thanks for reaching out!",
            ),
        ]
        return JorbWithMessages(jorb=sample_jorb, messages=messages)

    async def test_digest_no_recipient(self, sample_jorb_with_messages):
        """Test digest returns False without recipient."""
        service = EmailService(
            smtp_host="smtp.example.com",
            smtp_user="user",
            smtp_password="pass",
            default_to=None,
        )

        result = await service.send_daily_digest([sample_jorb_with_messages])
        assert result is False

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_digest_success(self, configured_service, sample_jorb_with_messages):
        """Test daily digest sends successfully."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send_daily_digest(
                [sample_jorb_with_messages]
            )

            assert result is True
            mock_send.assert_called_once()

            # Check message content
            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert "[Frank Bot] Daily Digest" in msg["Subject"]
            assert msg["To"] == "owner@example.com"

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_digest_paused_jorbs_in_subject(self, configured_service, sample_jorb_with_messages):
        """Test paused jorbs count appears in subject."""
        sample_jorb_with_messages.jorb.status = "paused"
        sample_jorb_with_messages.jorb.paused_reason = "Needs approval"

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await configured_service.send_daily_digest([sample_jorb_with_messages])

            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert "need attention" in msg["Subject"]

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_digest_empty_jorbs(self, configured_service):
        """Test digest handles empty jorbs list."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send_daily_digest([])

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_digest_multiple_jorbs(self, configured_service, sample_jorb_with_messages):
        """Test digest handles multiple jorbs."""
        # Create a completed jorb
        completed_jorb = Jorb(
            id="jorb_87654321",
            name="Task Complete",
            status="complete",
            original_plan="Do something",
            progress_summary="Done!",
        )
        completed_jwm = JorbWithMessages(jorb=completed_jorb, messages=[])

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send_daily_digest([
                sample_jorb_with_messages,
                completed_jwm,
            ])

            assert result is True

    @pytest.mark.skipif(not HAS_AIOSMTPLIB, reason="aiosmtplib not installed")
    async def test_digest_custom_recipient(self, configured_service, sample_jorb_with_messages):
        """Test digest can use custom recipient."""
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await configured_service.send_daily_digest(
                [sample_jorb_with_messages],
                to="custom@example.com",
            )

            assert result is True
            call_args = mock_send.call_args
            msg = call_args[0][0]
            assert msg["To"] == "custom@example.com"


class TestDigestTime:
    """Tests for get_digest_time method."""

    def test_default_digest_time(self):
        """Test default digest time is 08:00."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DIGEST_TIME if it exists
            os.environ.pop("DIGEST_TIME", None)
            assert EmailService.get_digest_time() == "08:00"

    def test_custom_digest_time(self):
        """Test custom digest time from environment."""
        with patch.dict(os.environ, {"DIGEST_TIME": "09:30"}):
            assert EmailService.get_digest_time() == "09:30"
