"""
Switchboard Operator Service.

The switchboard is a lightweight LLM session that ONLY routes incoming messages
to the correct jorb. It does NOT generate responses or decide on actions.

This is the first stage of the two-stage pattern:
1. Switchboard → Identifies which jorb
2. Jorb Session → Handles the actual conversation with personality
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from services.jorb_storage import Jorb, JorbWithMessages

logger = logging.getLogger(__name__)

# The model used for switchboard routing (can be lighter/faster than main model)
SWITCHBOARD_MODEL = os.getenv("SWITCHBOARD_MODEL", "gpt-5.2")

# Try to import openai
try:
    import openai
except ImportError:
    openai = None  # type: ignore


@dataclass
class RoutingDecision:
    """Result of the switchboard routing decision."""

    jorb_id: str | None
    confidence: str  # "high", "medium", "low"
    reasoning: str
    might_be_new_jorb: bool = False
    is_spam: bool = False
    is_urgent: bool = False
    unknown_sender: bool = False
    is_human_intervention: bool = False  # True when Sean sent this message directly
    # Token usage
    tokens_used: int = 0


def _load_switchboard_prompt() -> str:
    """Load the switchboard system prompt from file."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "switchboard_system.md",
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Switchboard prompt not found at %s", prompt_path)
        return ""


def _format_jorb_for_switchboard(jorb: Jorb) -> dict[str, Any]:
    """
    Format a jorb for the switchboard context.

    This is a LIGHTWEIGHT format - just enough for routing decisions.
    No message history, just identifiers and status.
    """
    # Extract contact identifiers for matching
    contacts = jorb.contacts
    contact_identifiers = [c.identifier for c in contacts]

    # Truncate plan to first 200 chars for summary
    plan_summary = jorb.original_plan[:200]
    if len(jorb.original_plan) > 200:
        plan_summary += "..."

    return {
        "id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "plan_summary": plan_summary,
        "contacts": contact_identifiers,
        "awaiting": jorb.awaiting,
        "last_activity": jorb.updated_at,
    }


class Switchboard:
    """
    Switchboard operator for routing incoming messages to jorbs.

    Uses a lightweight LLM call to determine which jorb (if any) an
    incoming message relates to. This is the first stage of the
    two-stage pattern.

    The switchboard:
    - Sees message details + jorb summaries (NOT full history)
    - Makes a routing decision with confidence level
    - Flags special cases (spam, urgent, unknown sender)
    - Does NOT generate responses or decide on actions
    """

    def __init__(self, openai_api_key: str | None = None):
        """
        Initialize the switchboard.

        Args:
            openai_api_key: OpenAI API key. Uses settings if not provided.
        """
        from config import get_settings

        settings = get_settings()
        self._api_key = openai_api_key or settings.openai_api_key
        self._system_prompt = _load_switchboard_prompt()

    @property
    def is_configured(self) -> bool:
        """Check if the switchboard has required configuration."""
        return bool(self._api_key)

    def build_context(
        self,
        channel: str,
        sender: str,
        sender_name: str | None,
        content: str,
        timestamp: str,
        open_jorbs: list[JorbWithMessages],
    ) -> dict[str, Any]:
        """
        Build the lightweight context for routing.

        Args:
            channel: Message channel (telegram, sms, email)
            sender: Sender identifier
            sender_name: Sender name if known
            content: Message content
            timestamp: Message timestamp
            open_jorbs: List of open jorbs (we only use jorb data, not messages)

        Returns:
            Context dict for the switchboard LLM
        """
        return {
            "message": {
                "channel": channel,
                "sender": sender,
                "sender_name": sender_name,
                "content": content,
                "timestamp": timestamp,
            },
            "jorbs": [
                _format_jorb_for_switchboard(jwm.jorb) for jwm in open_jorbs
            ],
        }

    async def route(
        self,
        channel: str,
        sender: str,
        sender_name: str | None,
        content: str,
        timestamp: str,
        open_jorbs: list[JorbWithMessages],
        is_human_intervention: bool = False,
    ) -> RoutingDecision:
        """
        Route an incoming message to the appropriate jorb.

        Args:
            channel: Message channel (telegram, sms, email)
            sender: Sender identifier (phone, username, email)
            sender_name: Sender name if known from contacts
            content: Message content
            timestamp: ISO 8601 timestamp
            open_jorbs: List of open jorbs with their messages
            is_human_intervention: True if this is Sean's direct message (outgoing)
                                   When True, routing still identifies the jorb but
                                   the message is handled differently by AgentRunner.

        Returns:
            RoutingDecision with jorb_id (or None) and metadata
        """
        # First, try fast contact matching (no LLM needed)
        fast_match = self._try_fast_contact_match(sender, open_jorbs)
        if fast_match:
            logger.info(
                "Fast contact match: message from %s routed to %s%s",
                sender,
                fast_match,
                " (human intervention)" if is_human_intervention else "",
            )
            return RoutingDecision(
                jorb_id=fast_match,
                confidence="high",  # Sean knows what he's doing
                reasoning=f"Sender {sender} is a known contact for this jorb",
                tokens_used=0,
                is_human_intervention=is_human_intervention,
            )

        # No fast match - use LLM for routing
        if not self._api_key or openai is None:
            logger.warning("Switchboard not configured, returning no match")
            return RoutingDecision(
                jorb_id=None,
                confidence="low",
                reasoning="Switchboard not configured",
                unknown_sender=True,
                is_human_intervention=is_human_intervention,
            )

        context = self.build_context(
            channel, sender, sender_name, content, timestamp, open_jorbs
        )

        try:
            client = openai.OpenAI(api_key=self._api_key)

            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": json.dumps(context, indent=2)},
            ]

            logger.debug(
                "Calling switchboard with %d jorbs",
                len(context.get("jorbs", [])),
            )

            response = client.chat.completions.create(
                model=SWITCHBOARD_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more deterministic routing
            )

            content_str = response.choices[0].message.content
            if not content_str:
                raise ValueError("Empty response from switchboard")

            result = json.loads(content_str)

            # Extract token usage
            tokens_used = 0
            if response.usage:
                tokens_used = (response.usage.prompt_tokens or 0) + (
                    response.usage.completion_tokens or 0
                )

            # Parse routing decision
            routing = result.get("routing", {})
            signals = result.get("signals", {})

            # For human intervention, if we find a jorb match, confidence is high
            confidence = routing.get("confidence", "low")
            if is_human_intervention and routing.get("jorb_id"):
                confidence = "high"  # Sean knows what he's doing

            decision = RoutingDecision(
                jorb_id=routing.get("jorb_id"),
                confidence=confidence,
                reasoning=routing.get("reasoning", ""),
                might_be_new_jorb=signals.get("might_be_new_jorb", False),
                is_spam=signals.get("is_spam", False),
                is_urgent=signals.get("is_urgent", False),
                unknown_sender=signals.get("unknown_sender", False),
                is_human_intervention=is_human_intervention,
                tokens_used=tokens_used,
            )

            logger.info(
                "Switchboard routed to %s (%s confidence): %s",
                decision.jorb_id,
                decision.confidence,
                decision.reasoning[:50],
            )

            return decision

        except Exception as e:
            logger.error("Switchboard routing failed: %s", e)
            return RoutingDecision(
                jorb_id=None,
                confidence="low",
                reasoning=f"Routing failed: {e}",
                unknown_sender=True,
                is_human_intervention=is_human_intervention,
            )

    def _try_fast_contact_match(
        self,
        sender: str,
        open_jorbs: list[JorbWithMessages],
    ) -> str | None:
        """
        Try to match sender to a jorb via fast contact lookup.

        This avoids an LLM call when we have an exact contact match.

        Args:
            sender: The sender identifier
            open_jorbs: List of open jorbs

        Returns:
            jorb_id if exact match found, None otherwise
        """
        # Normalize sender for comparison
        sender_normalized = self._normalize_identifier(sender)

        for jwm in open_jorbs:
            for contact in jwm.jorb.contacts:
                contact_normalized = self._normalize_identifier(contact.identifier)
                if sender_normalized == contact_normalized:
                    return jwm.jorb.id

        return None

    def _normalize_identifier(self, identifier: str) -> str:
        """
        Normalize an identifier for comparison.

        Handles phone numbers, Telegram usernames, etc.
        """
        # Remove whitespace
        identifier = identifier.strip()

        # Telegram usernames - normalize to lowercase without @
        if identifier.startswith("@"):
            return identifier[1:].lower()

        # Phone numbers - remove common formatting
        if any(c.isdigit() for c in identifier):
            # Keep only digits and leading +
            digits = "".join(c for c in identifier if c.isdigit() or c == "+")
            # Normalize US numbers (add +1 if 10 digits)
            if len(digits) == 10 and not digits.startswith("+"):
                digits = "+1" + digits
            # Remove leading +1 for comparison
            if digits.startswith("+1"):
                digits = digits[2:]
            return digits

        # Email - lowercase
        if "@" in identifier:
            return identifier.lower()

        return identifier.lower()


# Singleton instance
_switchboard: Switchboard | None = None


def get_switchboard() -> Switchboard:
    """Get the global switchboard instance."""
    global _switchboard
    if _switchboard is None:
        _switchboard = Switchboard()
    return _switchboard


__all__ = [
    "Switchboard",
    "RoutingDecision",
    "get_switchboard",
]
