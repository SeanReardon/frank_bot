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
from dataclasses import dataclass, field
from datetime import datetime  # noqa: F401 - used by format functions
from typing import Any, Literal

from services.jorb_storage import Jorb, JorbMessage, JorbWithMessages, Channel
from services.personality_loader import Personality, get_personality_loader
from services.progress_log import get_progress_log
from services.jorb_capabilities import generate_capabilities_reference

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


def _parse_json_object_from_model(content: str) -> dict[str, Any]:
    """
    Parse a JSON object from an LLM response string.

    We request `response_format={"type": "json_object"}`, but in practice the
    model can still occasionally return trailing text or multiple JSON objects.
    This helper is tolerant: it parses the first JSON object and ignores
    trailing data (with a warning).
    """
    raw = (content or "").strip()
    if not raw:
        raise ValueError("Empty response from jorb session")

    # Defensive: strip common fenced-code wrappers if they appear.
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    # Try to start parsing from the first JSON object.
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]

    decoder = json.JSONDecoder()
    obj, idx = decoder.raw_decode(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object, got {type(obj).__name__}")

    trailing = raw[idx:].strip()
    if trailing:
        logger.warning(
            "Trailing data after JSON object from model (ignored): %s",
            trailing[:200],
        )

    return obj


@dataclass
class JorbAction:
    """A command decided by the jorb session (executed by a switch statement)."""

    type: Literal[
        # New command schema (preferred)
        "RUN_SCRIPT",
        "SEND_MESSAGE",
        "WAIT_FOR_HUMAN",
        "SCHEDULE_WAKE",
        "PAUSE_FOR_APPROVAL",
        "COMPLETE",
        "NOOP",
        "START_ANDROID_TASK",
        "POLL_ANDROID_TASK",
        "START_META_TASK",
        "POLL_META_TASK",
        # Legacy action schema (backwards compat)
        "send_message",
        "pause",
        "complete",
        "update_status",
        "no_action",
        "script",
    ]
    args: dict[str, Any] = field(default_factory=dict)
    # Legacy fields for backward compatibility
    channel: Channel | None = None
    recipient: str | None = None
    content: str | None = None
    pause_reason: str | None = None
    needs_approval_for: str | None = None
    # New script-based response format fields
    script: str | None = None
    await_reply: bool = False
    done: bool = False
    pause: bool = False
    result: dict | None = None
    reasoning: str = ""


@dataclass
class JorbProgress:
    """Progress update from the jorb session."""

    note: str | None = None
    awaiting: str | None = None
    learnings: str | None = None  # New learnings to record


@dataclass
class JorbSessionResponse:
    """Complete response from a jorb session."""

    summary: str
    reasoning: str
    action: JorbAction
    progress: JorbProgress | None = None
    # Token usage
    tokens_used: int = 0
    estimated_cost: float = 0.0
    # New script-based format fields (extracted from action for convenience)
    script: str | None = None
    await_reply: bool = False
    done: bool = False
    pause: bool = False
    result: dict | None = None


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
    result = {
        "timestamp": msg.timestamp,
        "direction": msg.direction,
        "channel": msg.channel,
        "sender": msg.sender_name or msg.sender,
        "content": msg.content,
    }
    # Mark sean_direct messages specially for learning
    if msg.sender == "sean_direct":
        result["is_sean_direct"] = True
    return result


def _is_sean_direct_message(msg: JorbMessage) -> bool:
    """Check if a message is a direct message from Sean (human intervention)."""
    return msg.sender == "sean_direct"


def _format_jorb_context(jorb: Jorb) -> dict[str, Any]:
    """Format jorb details for the session context."""
    return {
        "id": jorb.id,
        "name": jorb.name,
        "plan": jorb.original_plan,
        "status": jorb.status,
        "progress_summary": jorb.progress_summary or "",
        "awaiting": jorb.awaiting,
        "wake_at": getattr(jorb, "wake_at", None),
        "metadata": getattr(jorb, "metadata", {}),
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

    def _parse_response(self, response_json: dict[str, Any]) -> JorbSessionResponse:
        """
        Parse the LLM JSON response into a JorbSessionResponse.

        Supports two formats:
        1) Preferred (strict) command schema:
           - summary: required short status
           - reasoning: optional short explanation
           - command: { type, args }
        2) Legacy script schema (backwards compatibility)

        Args:
            response_json: Parsed JSON dict from LLM response

        Returns:
            JorbSessionResponse with action and metadata

        Raises:
            ValueError: If response_json is not a dict
        """
        if not isinstance(response_json, dict):
            raise ValueError(f"Expected dict response, got {type(response_json).__name__}")

        # ------------------------------------------------------------
        # Preferred strict command schema
        # ------------------------------------------------------------
        if "command" in response_json:
            summary = str(response_json.get("summary") or "").strip()
            if not summary:
                raise ValueError("summary is required")

            reasoning = str(response_json.get("reasoning") or "").strip()

            command = response_json.get("command")
            if not isinstance(command, dict):
                raise ValueError("command must be an object")

            cmd_type = str(command.get("type") or "").strip()
            args = command.get("args") or {}
            if not isinstance(args, dict):
                raise ValueError("command.args must be an object")

            allowed = {
                "RUN_SCRIPT",
                "SEND_MESSAGE",
                "WAIT_FOR_HUMAN",
                "SCHEDULE_WAKE",
                "PAUSE_FOR_APPROVAL",
                "COMPLETE",
                "NOOP",
                "START_ANDROID_TASK",
                "POLL_ANDROID_TASK",
                "START_META_TASK",
                "POLL_META_TASK",
            }
            if cmd_type not in allowed:
                raise ValueError(f"Invalid command.type: {cmd_type}")

            action = JorbAction(
                type=cmd_type,  # type: ignore[arg-type]
                args=args,
                reasoning=reasoning,
            )

            # Populate legacy convenience fields for existing code paths/logging.
            if cmd_type == "RUN_SCRIPT":
                script = str(args.get("script") or "").strip()
                action.script = script or None
                action.content = action.script
            elif cmd_type == "PAUSE_FOR_APPROVAL":
                action.pause = True
                action.pause_reason = str(args.get("pause_reason") or "").strip() or None
                naf = args.get("needs_approval_for")
                action.needs_approval_for = str(naf).strip() if naf else None
            elif cmd_type == "COMPLETE":
                action.done = True
                result_val = args.get("result")
                action.result = result_val if isinstance(result_val, dict) else None
            elif cmd_type == "SEND_MESSAGE":
                # AgentRunner handles sending; keep content populated for logs.
                action.content = str(args.get("text") or "").strip() or None

            # Summary doubles as the canonical progress note for routing.
            progress = JorbProgress(note=summary)

            return JorbSessionResponse(
                summary=summary,
                reasoning=reasoning,
                action=action,
                progress=progress,
            )

        # ------------------------------------------------------------
        # Legacy script schema (backwards compatibility)
        # ------------------------------------------------------------
        reasoning = response_json.get("reasoning", "") or ""
        script = response_json.get("script")
        await_reply = bool(response_json.get("await_reply", False))
        done = bool(response_json.get("done", False))
        pause = bool(response_json.get("pause", False))
        pause_reason = response_json.get("pause_reason")
        result = response_json.get("result")

        action_type: Literal[
            "send_message", "pause", "complete", "update_status", "no_action", "script"
        ] = "no_action"
        if done:
            action_type = "complete"
        elif pause:
            action_type = "pause"
        elif script is not None and str(script).strip():
            action_type = "script"

        action = JorbAction(
            type=action_type,
            script=script,
            await_reply=await_reply,
            done=done,
            pause=pause,
            pause_reason=pause_reason,
            result=result if isinstance(result, dict) else None,
            reasoning=reasoning,
            content=script if script else None,
        )

        progress = None
        progress_data = response_json.get("progress")
        if progress_data and isinstance(progress_data, dict):
            progress = JorbProgress(
                note=progress_data.get("note"),
                awaiting=progress_data.get("awaiting"),
                learnings=progress_data.get("learnings"),
            )

        # Derive a best-effort summary from legacy fields.
        summary = (
            (progress.note if progress and progress.note else None)
            or (reasoning.strip() if isinstance(reasoning, str) else None)
            or "Working…"
        )

        return JorbSessionResponse(
            summary=summary,
            reasoning=reasoning,
            action=action,
            progress=progress,
            script=script,
            await_reply=await_reply,
            done=done,
            pause=pause,
            result=result if isinstance(result, dict) else None,
        )

    def _build_system_prompt(self) -> str:
        """Build the complete system prompt for this session."""
        # Start with template
        prompt = self._template

        # Replace personality section
        personality_section = self._personality.format_for_prompt()
        prompt = prompt.replace("{{PERSONALITY_SECTION}}", personality_section)

        # Replace capabilities reference
        capabilities_reference = generate_capabilities_reference()
        prompt = prompt.replace("{{CAPABILITIES_REFERENCE}}", capabilities_reference)

        # Replace jorb context
        jorb_context = json.dumps(_format_jorb_context(self._jorb), indent=2)
        prompt = prompt.replace("{{JORB_CONTEXT}}", jorb_context)

        # Replace message history with special labeling for sean_direct messages
        sean_direct_messages = []
        if self._messages:
            history_lines = []
            for msg in self._messages[-50:]:  # Last 50 messages
                formatted = _format_message_for_history(msg)
                direction = "→" if msg.direction == "outbound" else "←"

                # Special formatting for sean_direct messages
                if _is_sean_direct_message(msg):
                    history_lines.append(
                        f"★ [GUIDANCE FROM PRINCIPAL - {formatted['timestamp'][:16]}] "
                        f"Sean: {formatted['content'][:200]}"
                    )
                    sean_direct_messages.append(msg)
                else:
                    history_lines.append(
                        f"{direction} [{formatted['timestamp'][:16]}] "
                        f"{formatted['sender']}: {formatted['content'][:200]}"
                    )
            message_history = "\n".join(history_lines)
        else:
            message_history = "(No messages yet)"
        prompt = prompt.replace("{{MESSAGE_HISTORY}}", message_history)

        # Replace script results history
        script_results = getattr(self._jorb, "script_results", [])
        if script_results:
            script_results_lines = []
            for i, result in enumerate(script_results[-10:]):  # Last 10 results
                script_results_lines.append(f"Step {i + 1}:")
                script = str(result.get("script", "N/A"))
                success = bool(result.get("success", False))
                payload = result.get("result", {})

                script_results_lines.append(f"  Script: {script[:100]}...")
                script_results_lines.append(f"  Success: {success}")

                # Guardrail: always surface critical fields (status/id/error) even
                # when payloads contain long strings (e.g. Android task goal) that
                # would otherwise push `status` past the truncation window.
                if isinstance(payload, dict):
                    task_id = (
                        payload.get("task_id")
                        or payload.get("id")
                        or payload.get("job_id")
                        or payload.get("task")
                    )
                    status = payload.get("status") or payload.get("state")
                    current_step = (
                        payload.get("current_step")
                        or payload.get("step")
                        or payload.get("phase")
                    )
                    error = payload.get("error") or payload.get("failure_reason")

                    if task_id:
                        script_results_lines.append(f"  Task/ID: {str(task_id)[:64]}")
                    if status:
                        script_results_lines.append(f"  Status: {str(status)[:64]}")
                    if current_step:
                        script_results_lines.append(
                            f"  Current step: {str(current_step)[:160]}"
                        )
                    if error:
                        err_one_line = " ".join(str(error).split())
                        if len(err_one_line) > 300:
                            err_one_line = err_one_line[:300] + "..."
                        script_results_lines.append(f"  Error: {err_one_line}")

                    # Keep a compact JSON preview but avoid letting very long
                    # fields drown out important keys.
                    compact = dict(payload)
                    if isinstance(compact.get("goal"), str) and len(compact["goal"]) > 180:
                        compact["goal"] = compact["goal"][:180] + "..."
                    if isinstance(compact.get("stdout"), str) and len(compact["stdout"]) > 500:
                        compact["stdout"] = compact["stdout"][-500:]
                    if isinstance(compact.get("stderr"), str) and len(compact["stderr"]) > 500:
                        compact["stderr"] = compact["stderr"][-500:]

                    preview = json.dumps(compact, ensure_ascii=False)[:400]
                else:
                    preview = json.dumps(payload, ensure_ascii=False)[:400]

                script_results_lines.append(f"  Result: {preview}")
                script_results_lines.append("")
            script_results_text = "\n".join(script_results_lines)
        else:
            script_results_text = "(No scripts executed yet)"
        prompt = prompt.replace("{{SCRIPT_RESULTS}}", script_results_text)

        # Add learning instruction if there are sean_direct messages
        if sean_direct_messages:
            learning_instruction = (
                "\n## Learning from Principal's Direct Messages\n"
                "Messages marked with ★ [GUIDANCE FROM PRINCIPAL] are direct messages "
                "Sean sent himself (not through you). Study these carefully:\n"
                "- They show Sean's preferred phrasing and tone\n"
                "- Adapt your style to match his natural communication\n"
                "- Note patterns: brevity, word choice, punctuation, formality\n"
                "- In your response, include learnings about Sean's style if you notice patterns\n"
            )
            prompt = prompt.replace("{{POLICY}}", f"{learning_instruction}\n\n{{POLICY}}")

        # Replace policy
        policy_text = _format_policy_context(self._policy)
        prompt = prompt.replace("{{POLICY}}", policy_text)

        # Get relevant learnings
        contact_subjects = [c.name or c.identifier for c in self._jorb.contacts]
        learnings_text = self._progress_log.format_learnings_for_prompt(contact_subjects)

        # Add learnings to the prompt (after personality section)
        if learnings_text and "No relevant learnings" not in learnings_text:
            prompt = prompt.replace("## Learnings\n", f"{learnings_text}\n\n## Learnings\n")

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
                summary="Session not configured (missing OpenAI API key).",
                reasoning="Session not configured",
                action=JorbAction(type="no_action"),
            )

        # Build the system prompt with all context
        system_prompt = self._build_system_prompt()

        # Build the user message (current event)
        event_context = _format_event_context(
            channel, sender, sender_name, content, timestamp, message_count
        )
        user_message = (
            f"New message received:\n\n```json\n{json.dumps(event_context, indent=2)}\n```"
        )

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

            result = _parse_json_object_from_model(content_str)

            # Extract token usage
            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)

            # Parse response using new format
            response_obj = self._parse_response(result)
            response_obj.tokens_used = tokens_used
            response_obj.estimated_cost = estimated_cost

            # Record any new learnings from progress
            if response_obj.progress and response_obj.progress.learnings:
                self._record_learning(response_obj.progress.learnings)

            logger.info(
                "Jorb session decided: action=%s, tokens=%d",
                response_obj.action.type,
                tokens_used,
            )

            return response_obj

        except Exception as e:
            logger.exception("Jorb session error: %s", e)
            return JorbSessionResponse(
                summary=f"Session error: {e}",
                reasoning=f"Session error: {e}",
                action=JorbAction(type="no_action"),
                progress=JorbProgress(note=f"Session error: {e}"),
            )

    async def tick(self) -> JorbSessionResponse:
        """
        Continue working a jorb when there is no new external message.

        This is used for worker ticks (scheduled wakes) and for multi-step
        iteration after tools/scripts have produced new results.
        """
        if not self._api_key or openai is None:
            logger.warning("Jorb session not configured for tick")
            return JorbSessionResponse(
                summary="Tick not configured (missing OpenAI API key).",
                reasoning="Session not configured",
                action=JorbAction(type="no_action"),
            )

        system_prompt = self._build_system_prompt()
        system_prompt = system_prompt.replace("{{CURRENT_EVENT}}", "See user message")

        user_message = (
            "Tick: there is no new external message.\n\n"
            "Continue working this jorb using the current plan, message history, "
            "and tool/script results history. Emit the next command.\n\n"
            "Important:\n"
            "- Do NOT assume you must wait for a human reply unless truly required.\n"
            "- If you're waiting on an external task (Android/meta task), poll it or "
            "schedule a wake.\n"
            "- Always include an up-to-date `summary` suitable for routing."
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
                "Ticking jorb %s with personality %s",
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
                raise ValueError("Empty response from tick")

            result = _parse_json_object_from_model(content_str)

            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)

            response_obj = self._parse_response(result)
            response_obj.tokens_used = tokens_used
            response_obj.estimated_cost = estimated_cost

            if response_obj.progress and response_obj.progress.learnings:
                self._record_learning(response_obj.progress.learnings)

            return response_obj

        except Exception as e:
            logger.exception("Jorb tick error: %s", e)
            return JorbSessionResponse(
                summary=f"Tick error: {e}",
                reasoning=f"Tick error: {e}",
                action=JorbAction(type="no_action"),
                progress=JorbProgress(note=f"Tick error: {e}"),
            )

    def _is_catch_up_jorb(self) -> bool:
        """Check if this is a catch-up jorb for context recovery."""
        return "Recover context" in self._jorb.original_plan

    def _kickoff_catch_up_jorb(self) -> JorbSessionResponse:
        """
        Generate kickoff for a catch-up jorb - asks for context in Sean's style.

        Uses predefined casual messages that vary slightly for natural feel.
        No LLM call needed - these are simple context-recovery messages.

        Returns:
            JorbSessionResponse with send_message action to ask for context
        """
        import random

        # Casual context-recovery messages in Sean's style
        # These vary to feel natural but all accomplish the same goal
        context_messages = [
            "hey sorry i lost track of this - can you remind me where we left off?",
            "hey sorry my bad i lost the thread here - what were we working on again?",
            "sorry brain fart - where did we leave this?",
            "hey can you catch me up? lost track of where we were",
            "wait what was this about again? sorry my memory is fried",
        ]

        # Use personality temperature to add slight variation in message selection
        # Higher temperature = more likely to pick less common variants
        temperature = self._personality.model_preferences.temperature
        if temperature > 0.5:
            # More random selection
            message = random.choice(context_messages)
        else:
            # Favor the first (most polite) message
            weights = [0.5, 0.2, 0.1, 0.1, 0.1]
            message = random.choices(context_messages, weights=weights)[0]

        # Get contact for the action
        contacts = self._jorb.contacts
        if not contacts:
            logger.warning("Catch-up jorb %s has no contacts", self._jorb.id)
            return JorbSessionResponse(
                summary="Catch-up jorb has no contacts to message.",
                reasoning="Catch-up jorb has no contacts to message",
                action=JorbAction(type="no_action"),
            )

        contact = contacts[0]

        recipient = contact.identifier
        if contact.channel == "telegram_bot":
            # Bot API requires numeric chat_id for private chats; use stored metadata when available.
            chat_id = str(self._jorb.metadata.get("telegram_bot_chat_id") or "").strip()
            if chat_id:
                recipient = chat_id

        logger.info(
            "Catch-up jorb %s kickoff: asking %s for context",
            self._jorb.id,
            recipient,
        )

        return JorbSessionResponse(
            summary="Asked contact for context recovery; awaiting reply.",
            reasoning="Catch-up jorb - asking contact to remind me of context",
            action=JorbAction(
                type="send_message",
                channel=contact.channel,
                recipient=recipient,
                content=message,
            ),
            progress=JorbProgress(
                note="Asked contact for context recovery",
                awaiting="context_recovery",
            ),
            tokens_used=0,  # No LLM call
            estimated_cost=0.0,
        )

    async def kickoff(self) -> JorbSessionResponse:
        """
        Generate the initial action for a new jorb.

        This is called when a jorb is created with start_immediately=True.
        For catch-up jorbs (plan contains 'Recover context'), generates a
        context-recovery message in Sean's casual style instead of using LLM.

        Returns:
            JorbSessionResponse with the first action to take
        """
        # Handle catch-up jorbs specially - no LLM needed
        if self._is_catch_up_jorb():
            return self._kickoff_catch_up_jorb()

        if not self._api_key or openai is None:
            logger.warning("Jorb session not configured for kickoff")
            return JorbSessionResponse(
                summary="Kickoff not configured (missing OpenAI API key).",
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

            result = _parse_json_object_from_model(content_str)

            # Extract token usage
            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)

            # Parse response using new format
            response_obj = self._parse_response(result)
            response_obj.tokens_used = tokens_used
            response_obj.estimated_cost = estimated_cost

            return response_obj

        except Exception as e:
            logger.exception("Jorb kickoff error: %s", e)
            return JorbSessionResponse(
                summary=f"Kickoff error: {e}",
                reasoning=f"Kickoff error: {e}",
                action=JorbAction(type="no_action"),
                progress=JorbProgress(note=f"Kickoff error: {e}"),
            )

    def _record_learning(self, learning_text: str) -> None:
        """Record a learning from the jorb session."""
        # Check if this is a style learning about Sean's communication
        is_sean_style_learning = any(
            keyword in learning_text.lower()
            for keyword in [
                "sean's style",
                "sean style",
                "principal's",
                "phrasing",
                "brevity",
                "tone",
                "communication style",
            ]
        )

        if is_sean_style_learning:
            self._record_sean_style_learning(learning_text)
        else:
            # Regular learning - try to extract subject from jorb contacts
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

    def _record_sean_style_learning(self, learning_text: str) -> None:
        """
        Record a learning specifically about Sean's communication style.

        These learnings are tagged with subject="Sean's communication style"
        so they can be easily retrieved and applied to future jorbs.

        Args:
            learning_text: The style learning to record
        """
        try:
            self._progress_log.add_learning(
                category="contact_behavior",
                subject="Sean's communication style",
                insight=learning_text,
                jorb_id=self._jorb.id,
                confidence="high",  # Higher confidence for direct observation
            )
            logger.info("Recorded Sean style learning: %s", learning_text[:50])
        except Exception as e:
            logger.warning("Failed to record Sean style learning: %s", e)

    def has_sean_direct_messages(self) -> bool:
        """Check if this session has any sean_direct messages to learn from."""
        return any(_is_sean_direct_message(msg) for msg in self._messages)


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
