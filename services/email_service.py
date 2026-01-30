"""
Email Service for sending notifications and digests.

Uses aiosmtplib for async SMTP email delivery.
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import get_settings
from services.jorb_storage import Jorb

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending email notifications.

    Supports sending HTML and plain text emails via SMTP.
    """

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        default_to: str | None = None,
    ):
        """
        Initialize the email service.

        Args:
            smtp_host: SMTP server hostname. Uses SMTP_HOST env var if not provided.
            smtp_port: SMTP server port. Uses SMTP_PORT env var if not provided (default 587).
            smtp_user: SMTP username. Uses SMTP_USER env var if not provided.
            smtp_password: SMTP password. Uses SMTP_PASSWORD env var if not provided.
            default_to: Default recipient email. Uses DIGEST_EMAIL_TO env var if not provided.
        """
        settings = get_settings()
        self._host = smtp_host or settings.smtp_host
        self._port = smtp_port or settings.smtp_port
        self._user = smtp_user or settings.smtp_user
        self._password = smtp_password or settings.smtp_password
        self._default_to = default_to or settings.digest_email_to

    @property
    def is_configured(self) -> bool:
        """Check if the email service has required SMTP configuration."""
        return bool(self._host and self._user and self._password)

    @property
    def default_recipient(self) -> str | None:
        """Return the default recipient email address."""
        return self._default_to

    async def send(
        self,
        to: str,
        subject: str,
        body_html: str | None = None,
        body_text: str | None = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject line
            body_html: HTML body content (optional)
            body_text: Plain text body content (optional, auto-generated from HTML if not provided)

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.warning("Email service not configured, cannot send email")
            return False

        if not body_html and not body_text:
            logger.error("Email must have at least body_html or body_text")
            return False

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._user
        msg["To"] = to

        # Add plain text part
        if body_text:
            text_part = MIMEText(body_text, "plain")
            msg.attach(text_part)
        elif body_html:
            # Generate plain text from HTML (basic strip)
            import re
            plain = re.sub(r"<[^>]+>", "", body_html)
            plain = re.sub(r"\s+", " ", plain).strip()
            text_part = MIMEText(plain, "plain")
            msg.attach(text_part)

        # Add HTML part
        if body_html:
            html_part = MIMEText(body_html, "html")
            msg.attach(html_part)

        try:
            import aiosmtplib

            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                start_tls=True,
            )

            logger.info("Email sent to %s: %s", to, subject)
            return True

        except Exception as e:
            logger.error("Failed to send email to %s: %s", to, e)
            return False

    async def notify_jorb_paused(self, jorb: Jorb) -> bool:
        """
        Send a notification that a jorb has been paused for approval.

        Args:
            jorb: The paused Jorb

        Returns:
            True if email was sent successfully
        """
        if not self._default_to:
            logger.warning("No default recipient configured for jorb notifications")
            return False

        subject = f"[Frank Bot] Jorb paused: {jorb.name}"

        body_html = f"""
        <h2>Jorb Paused for Approval</h2>
        <p><strong>{jorb.name}</strong> has been paused and needs your input.</p>

        <h3>Details</h3>
        <ul>
            <li><strong>Jorb ID:</strong> {jorb.id}</li>
            <li><strong>Status:</strong> {jorb.status}</li>
            <li><strong>Reason:</strong> {jorb.paused_reason or "Not specified"}</li>
            <li><strong>Approval Needed For:</strong> {jorb.needs_approval_for or "Not specified"}</li>
        </ul>

        <h3>Plan</h3>
        <pre>{jorb.original_plan}</pre>

        <h3>Progress</h3>
        <p>{jorb.progress_summary or "No progress recorded yet."}</p>

        <p><a href="#">Approve in Dashboard</a></p>
        """

        body_text = f"""
Jorb Paused for Approval: {jorb.name}

Jorb ID: {jorb.id}
Status: {jorb.status}
Reason: {jorb.paused_reason or "Not specified"}
Approval Needed For: {jorb.needs_approval_for or "Not specified"}

Plan:
{jorb.original_plan}

Progress:
{jorb.progress_summary or "No progress recorded yet."}
        """

        return await self.send(
            to=self._default_to,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
        )

    async def notify_jorb_complete(self, jorb: Jorb) -> bool:
        """
        Send a notification that a jorb has been completed.

        Args:
            jorb: The completed Jorb

        Returns:
            True if email was sent successfully
        """
        if not self._default_to:
            logger.warning("No default recipient configured for jorb notifications")
            return False

        subject = f"[Frank Bot] Jorb complete: {jorb.name}"

        body_html = f"""
        <h2>Jorb Completed</h2>
        <p><strong>{jorb.name}</strong> has been completed!</p>

        <h3>Details</h3>
        <ul>
            <li><strong>Jorb ID:</strong> {jorb.id}</li>
            <li><strong>Status:</strong> {jorb.status}</li>
            <li><strong>Created:</strong> {jorb.created_at}</li>
            <li><strong>Updated:</strong> {jorb.updated_at}</li>
        </ul>

        <h3>Original Plan</h3>
        <pre>{jorb.original_plan}</pre>

        <h3>Final Status</h3>
        <p>{jorb.progress_summary or "No progress summary recorded."}</p>
        """

        body_text = f"""
Jorb Completed: {jorb.name}

Jorb ID: {jorb.id}
Status: {jorb.status}
Created: {jorb.created_at}
Updated: {jorb.updated_at}

Original Plan:
{jorb.original_plan}

Final Status:
{jorb.progress_summary or "No progress summary recorded."}
        """

        return await self.send(
            to=self._default_to,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
        )


__all__ = ["EmailService"]
