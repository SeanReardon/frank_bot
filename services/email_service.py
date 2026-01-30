"""
Email Service for sending notifications and digests.

Uses aiosmtplib for async SMTP email delivery.
"""

from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import get_settings
from services.jorb_storage import Jorb, JorbMessage, JorbWithMessages

logger = logging.getLogger(__name__)


@dataclass
class JorbCosts:
    """Cost tracking for a jorb."""

    message_count: int = 0
    sms_count: int = 0
    telegram_count: int = 0
    email_count: int = 0
    inbound_count: int = 0
    outbound_count: int = 0


@dataclass
class JorbDigestSummary:
    """Summary of a jorb for the digest."""

    jorb: Jorb
    messages: list[JorbMessage] = field(default_factory=list)
    costs: JorbCosts = field(default_factory=JorbCosts)
    key_decisions: list[str] = field(default_factory=list)


@dataclass
class DailyDigestData:
    """Data for the daily digest email."""

    active_jorbs: list[JorbDigestSummary] = field(default_factory=list)
    completed_jorbs: list[JorbDigestSummary] = field(default_factory=list)
    paused_jorbs: list[JorbDigestSummary] = field(default_factory=list)
    total_messages: int = 0
    total_sms: int = 0
    total_telegram: int = 0
    generated_at: str = ""


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

    def _build_jorb_summary(
        self,
        jorb: Jorb,
        messages: list[JorbMessage],
    ) -> JorbDigestSummary:
        """
        Build a digest summary for a jorb.

        Args:
            jorb: The jorb
            messages: Messages for the jorb

        Returns:
            JorbDigestSummary with costs and key decisions
        """
        costs = JorbCosts(message_count=len(messages))

        key_decisions = []

        for msg in messages:
            if msg.direction == "inbound":
                costs.inbound_count += 1
            else:
                costs.outbound_count += 1

            if msg.channel == "sms":
                costs.sms_count += 1
            elif msg.channel == "telegram":
                costs.telegram_count += 1
            elif msg.channel == "email":
                costs.email_count += 1

            # Extract key decisions from outbound messages with reasoning
            if msg.direction == "outbound" and msg.agent_reasoning:
                # Truncate long reasoning
                reasoning = msg.agent_reasoning
                if len(reasoning) > 200:
                    reasoning = reasoning[:200] + "..."
                key_decisions.append(reasoning)

        # Limit key decisions to 5 most recent
        key_decisions = key_decisions[-5:]

        return JorbDigestSummary(
            jorb=jorb,
            messages=messages,
            costs=costs,
            key_decisions=key_decisions,
        )

    def _format_timestamp(self, iso_timestamp: str) -> str:
        """Format an ISO timestamp for display."""
        try:
            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return iso_timestamp

    def _build_digest_html(self, data: DailyDigestData) -> str:
        """Build the HTML body for the daily digest."""
        sections = []

        # Header
        sections.append(f"""
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                .jorb-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 12px 0; }}
                .jorb-running {{ border-left: 4px solid #3b82f6; }}
                .jorb-paused {{ border-left: 4px solid #eab308; }}
                .jorb-complete {{ border-left: 4px solid #22c55e; }}
                .message {{ padding: 8px; margin: 4px 0; border-radius: 4px; }}
                .inbound {{ background: #f3f4f6; }}
                .outbound {{ background: #dbeafe; }}
                .reasoning {{ font-style: italic; color: #6b7280; font-size: 0.9em; }}
                .stats {{ color: #6b7280; font-size: 0.9em; }}
                h2 {{ color: #1f2937; }}
                h3 {{ color: #374151; margin-bottom: 8px; }}
            </style>
        </head>
        <body>
            <h1>🤖 Frank Bot Daily Digest</h1>
            <p class="stats">Generated: {data.generated_at}</p>
            <p class="stats">Total: {data.total_messages} messages ({data.total_sms} SMS, {data.total_telegram} Telegram)</p>
        """)

        # Active jorbs section
        if data.active_jorbs:
            sections.append("<h2>🏃 Active Jorbs</h2>")
            for summary in data.active_jorbs:
                sections.append(self._format_jorb_card_html(summary, "running"))

        # Paused jorbs section
        if data.paused_jorbs:
            sections.append("<h2>⏸️ Paused Jorbs (Need Attention)</h2>")
            for summary in data.paused_jorbs:
                sections.append(self._format_jorb_card_html(summary, "paused"))

        # Completed jorbs section
        if data.completed_jorbs:
            sections.append("<h2>✅ Completed Jorbs</h2>")
            for summary in data.completed_jorbs:
                sections.append(self._format_jorb_card_html(summary, "complete"))

        # No activity message
        if not data.active_jorbs and not data.paused_jorbs and not data.completed_jorbs:
            sections.append("<p>No jorb activity in this period.</p>")

        sections.append("</body></html>")

        return "".join(sections)

    def _format_jorb_card_html(self, summary: JorbDigestSummary, style: str) -> str:
        """Format a single jorb as an HTML card."""
        jorb = summary.jorb
        costs = summary.costs

        card = f"""
        <div class="jorb-card jorb-{style}">
            <h3>{html.escape(jorb.name)}</h3>
            <p class="stats">
                Status: {jorb.status} |
                Messages: {costs.message_count} ({costs.inbound_count} in, {costs.outbound_count} out) |
                SMS: {costs.sms_count} | Telegram: {costs.telegram_count}
            </p>
        """

        if jorb.progress_summary:
            card += f"<p><strong>Progress:</strong> {html.escape(jorb.progress_summary)}</p>"

        if jorb.status == "paused" and jorb.paused_reason:
            card += f"<p><strong>Paused:</strong> {html.escape(jorb.paused_reason)}</p>"
            if jorb.needs_approval_for:
                card += f"<p><strong>Needs approval for:</strong> {html.escape(jorb.needs_approval_for)}</p>"

        # Recent interactions (last 10)
        recent_msgs = summary.messages[-10:]
        if recent_msgs:
            card += "<h4>Recent Interactions</h4>"
            for msg in recent_msgs:
                direction_class = "inbound" if msg.direction == "inbound" else "outbound"
                sender = msg.sender_name or msg.sender or "System"
                timestamp = self._format_timestamp(msg.timestamp)
                content = html.escape(msg.content[:200] + "..." if len(msg.content) > 200 else msg.content)

                card += f"""
                <div class="message {direction_class}">
                    <small>{timestamp} - {html.escape(sender or 'Unknown')} ({msg.channel})</small><br>
                    {content}
                </div>
                """

        # Key decisions
        if summary.key_decisions:
            card += "<h4>Agent Reasoning</h4>"
            for decision in summary.key_decisions:
                card += f'<p class="reasoning">💭 {html.escape(decision)}</p>'

        card += "</div>"
        return card

    def _build_digest_text(self, data: DailyDigestData) -> str:
        """Build the plain text body for the daily digest."""
        lines = [
            "FRANK BOT DAILY DIGEST",
            "=" * 40,
            f"Generated: {data.generated_at}",
            f"Total: {data.total_messages} messages ({data.total_sms} SMS, {data.total_telegram} Telegram)",
            "",
        ]

        # Active jorbs
        if data.active_jorbs:
            lines.append("ACTIVE JORBS")
            lines.append("-" * 20)
            for summary in data.active_jorbs:
                lines.extend(self._format_jorb_text(summary))
            lines.append("")

        # Paused jorbs
        if data.paused_jorbs:
            lines.append("PAUSED JORBS (NEED ATTENTION)")
            lines.append("-" * 20)
            for summary in data.paused_jorbs:
                lines.extend(self._format_jorb_text(summary))
            lines.append("")

        # Completed jorbs
        if data.completed_jorbs:
            lines.append("COMPLETED JORBS")
            lines.append("-" * 20)
            for summary in data.completed_jorbs:
                lines.extend(self._format_jorb_text(summary))
            lines.append("")

        if not data.active_jorbs and not data.paused_jorbs and not data.completed_jorbs:
            lines.append("No jorb activity in this period.")

        return "\n".join(lines)

    def _format_jorb_text(self, summary: JorbDigestSummary) -> list[str]:
        """Format a jorb for plain text."""
        jorb = summary.jorb
        costs = summary.costs
        lines = [
            f"* {jorb.name}",
            f"  Status: {jorb.status}",
            f"  Messages: {costs.message_count} ({costs.inbound_count} in, {costs.outbound_count} out)",
            f"  SMS: {costs.sms_count} | Telegram: {costs.telegram_count}",
        ]

        if jorb.progress_summary:
            lines.append(f"  Progress: {jorb.progress_summary}")

        if jorb.status == "paused" and jorb.paused_reason:
            lines.append(f"  Paused: {jorb.paused_reason}")

        # Recent messages (last 5 for text)
        recent = summary.messages[-5:]
        if recent:
            lines.append("  Recent:")
            for msg in recent:
                sender = msg.sender_name or msg.sender or "System"
                timestamp = self._format_timestamp(msg.timestamp)
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                lines.append(f"    [{timestamp}] {sender}: {content}")

        lines.append("")
        return lines

    async def send_daily_digest(
        self,
        jorbs_with_messages: list[JorbWithMessages],
        to: str | None = None,
    ) -> bool:
        """
        Send the daily digest email summarizing jorb activity.

        Args:
            jorbs_with_messages: List of JorbWithMessages with recent activity
            to: Recipient email (uses default_to if not provided)

        Returns:
            True if email was sent successfully
        """
        recipient = to or self._default_to
        if not recipient:
            logger.warning("No recipient configured for daily digest")
            return False

        # Build digest data
        data = DailyDigestData(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

        for jwm in jorbs_with_messages:
            summary = self._build_jorb_summary(jwm.jorb, jwm.messages)

            # Count totals
            data.total_messages += summary.costs.message_count
            data.total_sms += summary.costs.sms_count
            data.total_telegram += summary.costs.telegram_count

            # Categorize by status
            if jwm.jorb.status == "running":
                data.active_jorbs.append(summary)
            elif jwm.jorb.status == "paused":
                data.paused_jorbs.append(summary)
            elif jwm.jorb.status in ("complete", "cancelled", "failed"):
                data.completed_jorbs.append(summary)

        # Build email content
        body_html = self._build_digest_html(data)
        body_text = self._build_digest_text(data)

        # Determine subject based on content
        paused_count = len(data.paused_jorbs)
        if paused_count > 0:
            subject = f"[Frank Bot] Daily Digest - {paused_count} jorb(s) need attention"
        else:
            subject = f"[Frank Bot] Daily Digest - {data.total_messages} messages"

        return await self.send(
            to=recipient,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
        )

    @staticmethod
    def get_digest_time() -> str:
        """
        Get the configured digest send time.

        Returns:
            Time string like "08:00" from DIGEST_TIME env var
        """
        return os.getenv("DIGEST_TIME", "08:00")


__all__ = [
    "EmailService",
    "DailyDigestData",
    "JorbDigestSummary",
    "JorbCosts",
]
