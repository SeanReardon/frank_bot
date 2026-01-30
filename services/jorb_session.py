"""
Jorb Session Service.

Handles conversations for individual jorbs with personality-aware LLM sessions.
This is the second stage of the two-stage pattern:
1. Switchboard → Identifies which jorb
2. Jorb Session → Handles the actual conversation with personality
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime  # noqa: F401 - used by format functions
from typing import Any, Literal

from services.jorb_storage import Jorb, JorbMessage, JorbWithMessages, Channel
from services.personality_loader import Personality, get_personality_loader
from services.progress_log import get_progress_log

logger = logging.getLogger(__name__)

# Default model for jorb sessions
DEFAULT_JORB_MODEL = "gpt-5.2"

# Token pricing (USD per 1K tokens)
TOKEN_PRICE_INPUT = 0.01
TOKEN_PRICE_OUTPUT = 0.03

# Try to import openai
try:
    import openai
except ImportError:
    openai = None  # type: ignore


def _calculate_token_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD from token counts."""
    input_cost = (input_tokens / 1000) * TOKEN_PRICE_INPUT
    output_cost = (output_tokens / 1000) * TOKEN_PRICE_OUTPUT
    return round(input_cost + output_cost, 6)


@dataclass
class JorbAction:
    """An action decided by the jorb session."""

    type: Literal["send_message", "pause", "complete", "update_status", "no_action"]
    channel: Channel | None = None
    recipient: str | None = None
    content: str | None = None
    pause_reason: str | None = None
    needs_approval_for: str | None = None


@dataclass
class JorbProgress:
    """Progress update from the jorb session."""

    note: str | None = None
    awaiting: str | None = None
    learnings: str | None = None  # New learnings to record


@dataclass
class JorbSessionResponse:
    """Complete response from a jorb session."""

    reasoning: str
    action: JorbAction
    progress: JorbProgress | None = None
    # Token usage
    tokens_used: int = 0
    estimated_cost: float = 0.0


def _load_jorb_session_template() -> str:
    """Load the jorb session system prompt template."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "jorb_session_system.md",
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Jorb session template not found at %s", prompt_path)
        return ""


def _format_message_for_history(msg: JorbMessage) -> dict[str, Any]:
    """Format a message for the conversation history."""
    return {
        "timestamp": msg.timestamp,
        "direction": msg.direction,
        "channel": msg.channel,
        "sender": msg.sender_name or msg.sender,
        "content": msg.content,
    }


def _format_jorb_context(jorb: Jorb) -> dict[str, Any]:
    """Format jorb details for the session context."""
    return {
        "id": jorb.id,
        "name": jorb.name,
        "plan": jorb.original_plan,
        "status": jorb.status,
        "progress_summary": jorb.progress_summary or "",
        "awaiting": jorb.awaiting,
        "contacts": [c.to_dict() for c in jorb.contacts],
        "created_at": jorb.created_at,
    }


def _format_event_context(
    channel: str,
    sender: str,
    sender_name: str | None,
    content: str,
    timestamp: str,
    message_count: int = 1,
) -> dict[str, Any]:
    """Format the current event for context."""
    return {
        "channel": channel,
        "sender": sender,
        "sender_name": sender_name,
        "content": content,
        "timestamp": timestamp,
        "message_count": message_count,
    }


def _format_policy_context(policy: dict[str, Any]) -> str:
    """Format policy constraints for the prompt."""
    lines = [
        f"- Maximum spend without approval: ${policy.get('max_spend_without_approval', 100)}",
        f"- Maximum messages per hour: {policy.get('max_messages_per_hour', 20)}",
    ]

    require_approval = policy.get("require_approval_for", [])
    if require_approval:
        lines.append(f"- Require approval for: {', '.join(require_approval)}")

    return "\n".join(lines)


class JorbSession:
    """
    Session handler for an individual jorb.

    Each jorb session:
    - Has full conversation history for the jorb
    - Uses the jorb's configured personality
    - Makes decisions about actions, progress, learnings
    - Is dedicated to a single jorb
    """

    def __init__(
        self,
        jorb: Jorb,
        messages: list[JorbMessage],
        personality: Personality | None = None,
        openai_api_key: str | None = None,
        policy: dict[str, Any] | None = None,
    ):
        """
        Initialize a jorb session.

        Args:
            jorb: The jorb this session is for
            messages: Full conversation history
            personality: Personality to use (loaded from jorb.personality if not provided)
            openai_api_key: OpenAI API key
            policy: Policy constraints
        """
        from config import get_settings

        self._jorb = jorb
        self._messages = messages
        self._policy = policy or {}

        # Load personality
        if personality:
            self._personality = personality
        else:
            loader = get_personality_loader()
            self._personality = loader.get_or_default(jorb.personality)

        # Get API key
        settings = get_settings()
        self._api_key = openai_api_key or settings.openai_api_key

        # Load template
        self._template = _load_jorb_session_template()

        # Get learnings relevant to this jorb's contacts
        self._progress_log = get_progress_log()

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt for this session."""
        # Start with template
        prompt = self._template

        # Replace personality section
        personality_section = self._personality.format_for_prompt()
        prompt = prompt.replace("{{PERSONALITY_SECTION}}", personality_section)

        # Replace jorb context
        jorb_context = json.dumps(_format_jorb_context(self._jorb), indent=2)
        prompt = prompt.replace("{{JORB_CONTEXT}}", jorb_context)

        # Replace message history
        if self._messages:
            history_lines = []
            for msg in self._messages[-50:]:  # Last 50 messages
                formatted = _format_message_for_history(msg)
                direction = "→" if msg.direction == "outbound" else "←"
                history_lines.append(
                    f"{direction} [{formatted['timestamp'][:16]}] "
                    f"{formatted['sender']}: {formatted['content'][:200]}"
                )
            message_history = "\n".join(history_lines)
        else:
            message_history = "(No messages yet)"
        prompt = prompt.replace("{{MESSAGE_HISTORY}}", message_history)

        # Replace policy
        policy_text = _format_policy_context(self._policy)
        prompt = prompt.replace("{{POLICY}}", policy_text)

        # Get relevant learnings
        contact_subjects = [c.name or c.identifier for c in self._jorb.contacts]
        learnings_text = self._progress_log.format_learnings_for_prompt(contact_subjects)

        # Add learnings to the prompt (after personality section)
        if learnings_text and "No relevant learnings" not in learnings_text:
            prompt = prompt.replace(
                "## Learnings\n",
                f"{learnings_text}\n\n## Learnings\n"
            )

        return prompt

    async def process_message(
        self,
        channel: str,
        sender: str,
        sender_name: str | None,
        content: str,
        timestamp: str,
        message_count: int = 1,
    ) -> JorbSessionResponse:
        """
        Process an incoming message and decide on action.

        Args:
            channel: Message channel
            sender: Sender identifier
            sender_name: Sender name if known
            content: Message content
            timestamp: Message timestamp
            message_count: Number of bundled messages

        Returns:
            JorbSessionResponse with action, progress, and token usage
        """
        if not self._api_key or openai is None:
            logger.warning("Jorb session not configured")
            return JorbSessionResponse(
                reasoning="Session not configured",
                action=JorbAction(type="no_action"),
            )

        # Build the system prompt with all context
        system_prompt = self._build_system_prompt()

        # Build the user message (current event)
        event_context = _format_event_context(
            channel, sender, sender_name, content, timestamp, message_count
        )
        user_message = f"New message received:\n\n```json\n{json.dumps(event_context, indent=2)}\n```"

        # Replace the placeholder in template
        system_prompt = system_prompt.replace("{{CURRENT_EVENT}}", "See user message")

        try:
            client = openai.OpenAI(api_key=self._api_key)

            # Use personality's preferred model/temperature
            model = self._personality.model_preferences.preferred_model or DEFAULT_JORB_MODEL
            temperature = self._personality.model_preferences.temperature

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            logger.info(
                "Jorb session for %s (personality: %s) processing message",
                self._jorb.id,
                self._personality.id,
            )

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )

            content_str = response.choices[0].message.content
            if not content_str:
                raise ValueError("Empty response from jorb session")

            result = json.loads(content_str)

            # Extract token usage
            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)

            # Parse action
            action_data = result.get("action", {})
            action = JorbAction(
                type=action_data.get("type", "no_action"),
                channel=action_data.get("channel"),
                recipient=action_data.get("recipient"),
                content=action_data.get("content"),
                pause_reason=action_data.get("pause_reason"),
                needs_approval_for=action_data.get("needs_approval_for"),
            )

            # Parse progress
            progress = None
            progress_data = result.get("progress")
            if progress_data:
                progress = JorbProgress(
                    note=progress_data.get("note"),
                    awaiting=progress_data.get("awaiting"),
                    learnings=progress_data.get("learnings"),
                )

                # Record any new learnings
                if progress.learnings:
                    self._record_learning(progress.learnings)

            response_obj = JorbSessionResponse(
                reasoning=result.get("reasoning", ""),
                action=action,
                progress=progress,
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
            )

            logger.info(
                "Jorb session decided: action=%s, tokens=%d",
                action.type,
                tokens_used,
            )

            return response_obj

        except Exception as e:
            logger.error("Jorb session error: %s", e)
            return JorbSessionResponse(
                reasoning=f"Session error: {e}",
                action=JorbAction(type="no_action"),
            )

    async def kickoff(self) -> JorbSessionResponse:
        """
        Generate the initial action for a new jorb.

        This is called when a jorb is created with start_immediately=True.

        Returns:
            JorbSessionResponse with the first action to take
        """
        if not self._api_key or openai is None:
            logger.warning("Jorb session not configured for kickoff")
            return JorbSessionResponse(
                reasoning="Session not configured",
                action=JorbAction(type="no_action"),
            )

        # Build the system prompt
        system_prompt = self._build_system_prompt()
        system_prompt = system_prompt.replace("{{CURRENT_EVENT}}", "This is a new jorb - kickoff")

        # Build kickoff message
        user_message = (
            "This jorb has just been created and needs to be kicked off. "
            "Based on the plan and contacts, what should be the first action? "
            "Typically this means sending an initial message to start the task."
        )

        try:
            client = openai.OpenAI(api_key=self._api_key)

            model = self._personality.model_preferences.preferred_model or DEFAULT_JORB_MODEL
            temperature = self._personality.model_preferences.temperature

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            logger.info(
                "Kicking off jorb %s with personality %s",
                self._jorb.id,
                self._personality.id,
            )

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )

            content_str = response.choices[0].message.content
            if not content_str:
                raise ValueError("Empty response from kickoff")

            result = json.loads(content_str)

            # Extract token usage
            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)

            # Parse action
            action_data = result.get("action", {})
            action = JorbAction(
                type=action_data.get("type", "no_action"),
                channel=action_data.get("channel"),
                recipient=action_data.get("recipient"),
                content=action_data.get("content"),
                pause_reason=action_data.get("pause_reason"),
                needs_approval_for=action_data.get("needs_approval_for"),
            )

            # Parse progress
            progress = None
            progress_data = result.get("progress")
            if progress_data:
                progress = JorbProgress(
                    note=progress_data.get("note"),
                    awaiting=progress_data.get("awaiting"),
                    learnings=progress_data.get("learnings"),
                )

            return JorbSessionResponse(
                reasoning=result.get("reasoning", ""),
                action=action,
                progress=progress,
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
            )

        except Exception as e:
            logger.error("Jorb kickoff error: %s", e)
            return JorbSessionResponse(
                reasoning=f"Kickoff error: {e}",
                action=JorbAction(type="no_action"),
            )

    def _record_learning(self, learning_text: str) -> None:
        """Record a learning from the jorb session."""
        # Try to extract subject from jorb contacts
        subjects = [c.name or c.identifier for c in self._jorb.contacts]
        subject = subjects[0] if subjects else self._jorb.name

        try:
            self._progress_log.add_learning(
                category="tip",
                subject=subject,
                insight=learning_text,
                jorb_id=self._jorb.id,
                confidence="medium",
            )
        except Exception as e:
            logger.warning("Failed to record learning: %s", e)


def create_jorb_session(
    jorb_with_messages: JorbWithMessages,
    openai_api_key: str | None = None,
    policy: dict[str, Any] | None = None,
) -> JorbSession:
    """
    Create a jorb session from a JorbWithMessages.

    Args:
        jorb_with_messages: The jorb and its messages
        openai_api_key: Optional API key override
        policy: Policy constraints

    Returns:
        Configured JorbSession
    """
    return JorbSession(
        jorb=jorb_with_messages.jorb,
        messages=jorb_with_messages.messages,
        openai_api_key=openai_api_key,
        policy=policy,
    )


__all__ = [
    "JorbSession",
    "JorbSessionResponse",
    "JorbAction",
    "JorbProgress",
    "create_jorb_session",
]
