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
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.jorb_storage import Jorb, JorbWithMessages

logger = logging.getLogger(__name__)

# Detect explicit jorb/thread references in messages.
_JORB_ID_PATTERN = re.compile(r"\bjorb_[0-9a-f]{8}\b", re.IGNORECASE)
_THREAD_NUM_PATTERN = re.compile(r"\bthread\s*(\d{1,3})\b", re.IGNORECASE)

# Control-plane directive: explicitly request a brand new jorb/thread.
_START_NEW_JORB_RE = re.compile(
    r"^\s*(?:can\s+we\s+|can\s+you\s+|please\s+)?(?:start|create|make)\s+(?:a\s+)?new\s+jorb\b",
    re.IGNORECASE,
)
_NEW_JORB_PREFIX_RE = re.compile(r"^\s*new\s+jorb\s*[:\\-]\s*", re.IGNORECASE)

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


def _format_jorb_for_switchboard(jwm: JorbWithMessages) -> dict[str, Any]:
    """
    Format a jorb for the switchboard context.

    This is a LIGHTWEIGHT format - just enough for routing decisions.
    No message history, just identifiers and status.
    """
    jorb = jwm.jorb
    # Extract contact identifiers for matching
    contacts = jorb.contacts
    contact_identifiers = [c.identifier for c in contacts]

    # Truncate plan to first 200 chars for summary
    plan_summary = jorb.original_plan[:200]
    if len(jorb.original_plan) > 200:
        plan_summary += "..."

    # Current jorb summary (used for routing), truncated
    summary = (jorb.progress_summary or "").strip()
    if len(summary) > 240:
        summary = summary[:240] + "..."

    def _snippet(text: str | None, limit: int = 160) -> str:
        raw = (text or "").strip().replace("\n", " ")
        if len(raw) > limit:
            return raw[:limit] + "..."
        return raw

    # Last inbound/outbound message snippets
    last_inbound = None
    last_outbound = None
    if jwm.messages:
        for msg in reversed(jwm.messages):
            if last_inbound is None and msg.direction == "inbound":
                last_inbound = {
                    "timestamp": msg.timestamp,
                    "sender": msg.sender_name or msg.sender,
                    "content": _snippet(msg.content),
                }
            if last_outbound is None and msg.direction == "outbound":
                last_outbound = {
                    "timestamp": msg.timestamp,
                    "recipient": msg.recipient or "",
                    "content": _snippet(msg.content),
                }
            if last_inbound and last_outbound:
                break

    return {
        "id": jorb.id,
        "name": jorb.name,
        "status": jorb.status,
        "plan_summary": plan_summary,
        "summary": summary,
        "contacts": contact_identifiers,
        "awaiting": jorb.awaiting,
        "wake_at": getattr(jorb, "wake_at", None),
        "metadata": getattr(jorb, "metadata", {}),
        "last_inbound": last_inbound,
        "last_outbound": last_outbound,
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
        message_metadata: dict[str, Any] | None = None,
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
                "metadata": message_metadata or {},
            },
            "jorbs": [
                _format_jorb_for_switchboard(jwm) for jwm in open_jorbs
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
        message_metadata: dict[str, Any] | None = None,
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
        # Deterministic: explicit references should win over conversation-key fast routing.
        explicit = self._try_explicit_jorb_id_match(content, open_jorbs)
        if explicit:
            logger.info(
                "Explicit jorb id mention: message from %s routed to %s%s",
                sender,
                explicit,
                " (human intervention)" if is_human_intervention else "",
            )
            return RoutingDecision(
                jorb_id=explicit,
                confidence="high",
                reasoning="Message explicitly referenced this jorb id",
                tokens_used=0,
                is_human_intervention=is_human_intervention,
            )

        thread_match = self._try_thread_name_match(content, open_jorbs)
        if thread_match:
            logger.info(
                "Thread selection match: message from %s routed to %s%s",
                sender,
                thread_match,
                " (human intervention)" if is_human_intervention else "",
            )
            return RoutingDecision(
                jorb_id=thread_match,
                confidence="high",
                reasoning="Message referenced a thread number that matches exactly one open jorb name",
                tokens_used=0,
                is_human_intervention=is_human_intervention,
            )

        # If the user explicitly asks to start a new jorb, do NOT fast-route by
        # conversation/contact. Let the main pipeline create a new jorb (or the
        # switchboard LLM decide) rather than forcing continuity.
        if _START_NEW_JORB_RE.match(content or "") or _NEW_JORB_PREFIX_RE.match(content or ""):
            return RoutingDecision(
                jorb_id=None,
                confidence="high",
                reasoning="Explicit request to start a new jorb",
                might_be_new_jorb=True,
                tokens_used=0,
                is_human_intervention=is_human_intervention,
            )

        # First, try fast matching (no LLM needed) when unambiguous
        fast_convo_match = self._try_fast_conversation_match(message_metadata, open_jorbs)
        if fast_convo_match:
            logger.info(
                "Fast conversation match: message from %s routed to %s%s",
                sender,
                fast_convo_match,
                " (human intervention)" if is_human_intervention else "",
            )
            return RoutingDecision(
                jorb_id=fast_convo_match,
                confidence="high",
                reasoning="Conversation key matches exactly one open jorb",
                tokens_used=0,
                is_human_intervention=is_human_intervention,
            )

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
            channel,
            sender,
            sender_name,
            content,
            timestamp,
            open_jorbs,
            message_metadata=message_metadata,
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

    def _try_explicit_jorb_id_match(self, content: str, open_jorbs: list[JorbWithMessages]) -> str | None:
        """
        If the message explicitly references a jorb id (e.g. "jorb_ab12cd34"),
        route directly when the reference is unambiguous.
        """
        text = content or ""
        found = [m.group(0).lower() for m in _JORB_ID_PATTERN.finditer(text)]
        if not found:
            return None

        open_ids = {jwm.jorb.id.lower(): jwm.jorb.id for jwm in open_jorbs}
        matches: list[str] = []
        for jid in found:
            resolved = open_ids.get(jid)
            if resolved and resolved not in matches:
                matches.append(resolved)

        return matches[0] if len(matches) == 1 else None

    def _try_thread_name_match(self, content: str, open_jorbs: list[JorbWithMessages]) -> str | None:
        """
        If the message references "thread N" and exactly one open jorb name contains
        "thread N", route directly.
        """
        text = content or ""
        m = _THREAD_NUM_PATTERN.search(text)
        if not m:
            return None

        token = f"thread {m.group(1)}"
        matches = [
            jwm.jorb.id
            for jwm in open_jorbs
            if token.lower() in str(jwm.jorb.name or "").lower()
        ]
        return matches[0] if len(matches) == 1 else None

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

        matches: list[str] = []
        for jwm in open_jorbs:
            for contact in jwm.jorb.contacts:
                contact_normalized = self._normalize_identifier(contact.identifier)
                if sender_normalized == contact_normalized:
                    matches.append(jwm.jorb.id)
                    break

        # Only fast-match when unambiguous.
        if len(matches) == 1:
            return matches[0]
        return None

    def _try_fast_conversation_match(
        self,
        message_metadata: dict[str, Any] | None,
        open_jorbs: list[JorbWithMessages],
    ) -> str | None:
        """
        Try to match on a conversation key (e.g. Telegram bot chat_id) when unique.

        This avoids LLM routing when we have a deterministic conversation identity.
        """
        if not message_metadata:
            return None

        chat_id = message_metadata.get("telegram_bot_chat_id")
        chat_id = str(chat_id).strip() if chat_id else ""
        if not chat_id:
            return None

        matches: list[Jorb] = []
        for jwm in open_jorbs:
            meta = getattr(jwm.jorb, "metadata", {})
            if str(meta.get("telegram_bot_chat_id") or "").strip() == chat_id:
                matches.append(jwm.jorb)

        if len(matches) == 1:
            candidate = matches[0]

            # Guardrail: conversation key match alone is not enough to assume
            # continuity. Only fast-route when the candidate jorb is active and
            # recently updated; otherwise let the LLM decide (new task vs follow-up).
            updated_at = str(getattr(candidate, "updated_at", "") or "").strip()
            updated_dt: datetime | None = None
            try:
                if updated_at.endswith("Z"):
                    updated_at = updated_at[:-1] + "+00:00"
                updated_dt = datetime.fromisoformat(updated_at) if updated_at else None
            except Exception:
                updated_dt = None

            max_age = timedelta(minutes=30)
            now = datetime.now(timezone.utc)
            if not updated_dt or (now - updated_dt) > max_age:
                return None

            status = str(getattr(candidate, "status", "") or "").strip().lower()
            awaiting = str(getattr(candidate, "awaiting", "") or "").strip()
            paused_reason = str(getattr(candidate, "paused_reason", "") or "").strip().lower()

            if status == "paused":
                # Don't fast-route to long-stale auto-paused jorbs.
                if "auto-paused" in paused_reason:
                    return None
                # If it's paused and not waiting on the human, let the LLM decide.
                if not awaiting:
                    return None

            # Only fast-route when the jorb is explicitly waiting on Sean.
            # For everything else (including long-running tasks), let the LLM
            # decide whether this is a follow-up or a new request.
            needs_approval_for = str(getattr(candidate, "needs_approval_for", "") or "").strip()
            if needs_approval_for:
                return candidate.id

            awaiting_norm = awaiting.lower()
            if awaiting_norm in ("human_reply", "context_recovery") or awaiting_norm.startswith("human_reply"):
                return candidate.id

            return None

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
