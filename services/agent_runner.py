"""
Agent Runner Service for LLM-powered jorb processing.

Uses a two-stage switchboard pattern:
1. Switchboard → Routes messages to the correct jorb (lightweight, fast)
2. Jorb Session → Handles conversation with personality (full context)

The switchboard only identifies which jorb a message relates to.
Each jorb has its own dedicated LLM session with personality and full history.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Literal

from config import get_settings
from services.jorb_storage import (
    Channel,
    Jorb,
    JorbContact,
    JorbMessage,
    JorbStorage,
    JorbWithMessages,
)

# Import new switchboard and session components
from services.switchboard import Switchboard, RoutingDecision, get_switchboard
from services.jorb_session import (
    JorbSession,
    JorbSessionResponse,
    JorbAction,
    create_jorb_session,
)
from services.progress_log import get_progress_log

# Import openai at module level (may be None if not installed)
# This allows tests to patch it
try:
    import openai
except ImportError:
    openai = None  # type: ignore

logger = logging.getLogger(__name__)

# The hardcoded model as specified in the PRD (for legacy single-stage mode)
AGENT_MODEL = "gpt-5.2"

# Token pricing (USD per 1K tokens) - approximations for gpt-5.2
# These should be updated based on actual OpenAI pricing
TOKEN_PRICE_INPUT = 0.01  # $0.01 per 1K input tokens
TOKEN_PRICE_OUTPUT = 0.03  # $0.03 per 1K output tokens

# Script execution timeout (seconds) for jorb scripts
SCRIPT_EXECUTION_TIMEOUT = int(os.getenv("JORB_SCRIPT_TIMEOUT", "300"))

# Rate limiting for jorb LLM invocation loops
MAX_ITERATIONS_PER_HOUR = int(os.getenv("JORB_MAX_ITERATIONS_PER_HOUR", "20"))
MAX_ITERATIONS_PER_DAY = int(os.getenv("JORB_MAX_ITERATIONS_PER_DAY", "100"))

# Feature flag for switchboard mode (can be disabled for backwards compatibility)
# Checked at runtime to allow test fixtures to override
def _use_switchboard_mode() -> bool:
    """Check if switchboard mode is enabled."""
    return os.getenv("USE_SWITCHBOARD_MODE", "true").lower() == "true"


# For backwards compatibility export
USE_SWITCHBOARD_MODE = _use_switchboard_mode()


def _calculate_token_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD from token counts."""
    input_cost = (input_tokens / 1000) * TOKEN_PRICE_INPUT
    output_cost = (output_tokens / 1000) * TOKEN_PRICE_OUTPUT
    return round(input_cost + output_cost, 6)


@dataclass
class JorbPolicy:
    """Policy settings for jorb operation guardrails."""

    max_spend_without_approval: float = 100.0
    max_messages_per_hour: int = 20
    require_approval_for: list[str] = field(default_factory=lambda: ["purchase", "commit", "cancel", "share_info"])
    stale_jorb_hours: int = 72
    max_jorb_duration_days: int = 30

    @classmethod
    def from_settings(cls) -> JorbPolicy:
        """Load policy from environment/settings."""
        settings = get_settings()
        return cls(
            max_spend_without_approval=settings.agent_spend_limit,
            max_messages_per_hour=int(os.getenv("AGENT_MAX_MESSAGES_PER_HOUR", "20")),
            require_approval_for=os.getenv(
                "AGENT_REQUIRE_APPROVAL_FOR",
                "purchase,commit,cancel,share_info"
            ).split(","),
            stale_jorb_hours=int(os.getenv("AGENT_STALE_JORB_HOURS", "72")),
            max_jorb_duration_days=int(os.getenv("AGENT_MAX_JORB_DURATION_DAYS", "30")),
        )

    def to_context_dict(self) -> dict[str, Any]:
        """Convert policy to dict for agent context."""
        return {
            "max_spend_without_approval": self.max_spend_without_approval,
            "max_messages_per_hour": self.max_messages_per_hour,
            "require_approval_for": self.require_approval_for,
        }


@dataclass
class PolicyViolation:
    """A policy violation for reporting."""

    jorb_id: str
    jorb_name: str
    violation_type: str
    message: str
    timestamp: str


@dataclass
class IncomingEvent:
    """An incoming message event from SMS/Telegram/email."""

    channel: Channel
    sender: str
    sender_name: str | None
    content: str
    timestamp: str  # ISO 8601
    message_count: int = 1
    is_human_intervention: bool = False  # True when Sean sent this directly (not frank_bot)


@dataclass
class AgentAction:
    """An action decided by the agent."""

    type: Literal["send_message", "pause", "complete", "update_status", "no_action"]
    channel: Channel | None = None
    recipient: str | None = None
    content: str | None = None
    pause_reason: str | None = None
    needs_approval_for: str | None = None


@dataclass
class TaskUpdate:
    """Update to a jorb's status/progress."""

    progress_note: str | None = None
    awaiting: str | None = None


@dataclass
class AgentResponse:
    """Complete response from the agent."""

    jorb_id: str | None
    reasoning: str
    action: AgentAction
    task_update: TaskUpdate | None = None
    # Token usage from the LLM call
    tokens_used: int = 0
    estimated_cost: float = 0.0


@dataclass
class ProcessingResult:
    """Result of processing an incoming message."""

    jorb_id: str | None
    action_taken: str
    success: bool
    error: str | None = None
    message_sent: bool = False


@dataclass
class KickoffResult:
    """Result of kicking off a new jorb."""

    jorb_id: str
    success: bool
    action_taken: str
    message_sent: bool = False
    error: str | None = None


class AgentRunnerError(Exception):
    """Error from the AgentRunner service."""

    pass


def _load_system_prompt() -> str:
    """Load the agent system prompt from file."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "agent_system.md",
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Agent system prompt not found at %s", prompt_path)
        return ""


def _format_messages_for_context(messages: list[JorbMessage], limit: int = 10) -> list[dict]:
    """Format recent messages for the agent context."""
    # Get most recent messages
    recent = messages[-limit:] if len(messages) > limit else messages

    return [
        {
            "timestamp": msg.timestamp,
            "direction": msg.direction,
            "channel": msg.channel,
            "sender": msg.sender_name or msg.sender,
            "content": msg.content,
        }
        for msg in recent
    ]


def _format_jorb_for_context(jorb: Jorb, messages: list[JorbMessage]) -> dict:
    """Format a jorb for the agent context."""
    return {
        "task_id": jorb.id,
        "name": jorb.name,
        "plan": jorb.original_plan,
        "progress": jorb.progress_summary or "",
        "recent": _format_messages_for_context(messages),
        "status": jorb.status,
        "awaiting": jorb.awaiting,
    }


class AgentRunner:
    """
    Service for running the LLM agent to process jorb events.

    Uses gpt-5.2 (hardcoded) to decide actions based on incoming events
    and the current state of all active jorbs.
    """

    def __init__(
        self,
        storage: JorbStorage | None = None,
        openai_api_key: str | None = None,
        policy: JorbPolicy | None = None,
    ):
        """
        Initialize the agent runner.

        Args:
            storage: JorbStorage instance. Creates one if not provided.
            openai_api_key: OpenAI API key. Uses OPENAI_API_KEY env var if not provided.
            policy: JorbPolicy for guardrails. Loads from settings if not provided.
        """
        self._storage = storage or JorbStorage()
        settings = get_settings()
        self._api_key = openai_api_key or settings.openai_api_key
        self._policy = policy or JorbPolicy.from_settings()
        self._spend_limit = self._policy.max_spend_without_approval
        self._system_prompt = _load_system_prompt()
        # Track messages per hour per jorb for rate limiting
        self._message_counts: dict[str, list[str]] = {}  # jorb_id -> list of timestamps
        # Track policy violations for briefing
        self._policy_violations: list[PolicyViolation] = []

    @property
    def policy(self) -> JorbPolicy:
        """Return the current policy."""
        return self._policy

    @property
    def policy_violations(self) -> list[PolicyViolation]:
        """Return recorded policy violations."""
        return self._policy_violations.copy()

    def clear_policy_violations(self) -> None:
        """Clear the policy violations list."""
        self._policy_violations.clear()

    @property
    def is_configured(self) -> bool:
        """Check if the agent runner has required configuration."""
        return bool(self._api_key)

    async def is_trusted_sender(self, sender: str) -> bool:
        """
        Check if a sender is trusted (has previously been associated with any jorb).

        A sender is trusted if their identifier matches any jorb contact (normalized).
        This is used for catch-up jorb creation - only trusted senders can auto-create jorbs.

        Args:
            sender: The sender identifier to check (phone, username, email)

        Returns:
            True if the sender has been a contact on any jorb, False otherwise
        """
        # Get all contacts from all jorbs
        known_contacts = await self._storage.get_all_contacts_from_jorbs()

        if not known_contacts:
            return False

        # Normalize the sender for comparison
        normalized_sender = JorbStorage._normalize_identifier(sender)

        # Check if sender is in known contacts
        is_trusted = normalized_sender in known_contacts

        logger.debug(
            "Trusted sender check: %s (normalized: %s) -> %s",
            sender,
            normalized_sender,
            is_trusted,
        )
        return is_trusted

    def build_context(
        self,
        event: IncomingEvent | None,
        open_jorbs: list[JorbWithMessages],
        event_type: str = "message_received",
        kickoff_jorb: Jorb | None = None,
    ) -> dict[str, Any]:
        """
        Build the context dict to send to the agent.

        Args:
            event: The incoming event (or None for kickoff)
            open_jorbs: List of open jorbs with their messages
            event_type: Type of event ("message_received" or "jorb_created")
            kickoff_jorb: For kickoff, the new jorb to start

        Returns:
            Context dict matching agent_system.md format
        """
        context: dict[str, Any] = {}

        # Event type
        context["event_type"] = event_type

        # Event section (if present)
        if event:
            context["event"] = {
                "channel": event.channel,
                "sender": event.sender,
                "sender_name": event.sender_name,
                "content": event.content,
                "timestamp": event.timestamp,
                "message_count": event.message_count,
            }
        elif kickoff_jorb:
            # For kickoff, include the new jorb's info in the event
            context["event"] = {
                "type": "jorb_created",
                "jorb_id": kickoff_jorb.id,
                "jorb_name": kickoff_jorb.name,
                "plan": kickoff_jorb.original_plan,
                "contacts": [c.to_dict() for c in kickoff_jorb.contacts],
            }
        else:
            context["event"] = None

        # Active tasks section
        context["active_tasks"] = [
            _format_jorb_for_context(jwm.jorb, jwm.messages)
            for jwm in open_jorbs
        ]

        # Policy section - include full policy context
        context["policy"] = self._policy.to_context_dict()

        return context

    async def call_agent(self, context: dict[str, Any]) -> tuple[dict[str, Any], int, float]:
        """
        Send context to the OpenAI API and get the agent's response.

        Args:
            context: The context dict built by build_context()

        Returns:
            Tuple of (raw JSON response, tokens_used, estimated_cost)

        Raises:
            AgentRunnerError: If API call fails or response is invalid
        """
        if not self._api_key:
            raise AgentRunnerError(
                "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
            )

        # Check if openai is available
        if openai is None:
            raise AgentRunnerError(
                "openai package not installed. Run: poetry add openai"
            )

        client = openai.OpenAI(api_key=self._api_key)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": json.dumps(context, indent=2)},
        ]

        try:
            logger.info("Calling %s agent with context for %d active tasks",
                       AGENT_MODEL, len(context.get("active_tasks", [])))

            response = client.chat.completions.create(
                model=AGENT_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
            )

            content = response.choices[0].message.content
            if not content:
                raise AgentRunnerError("Empty response from agent")

            # Extract token usage from response
            tokens_used = 0
            estimated_cost = 0.0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
                tokens_used = input_tokens + output_tokens
                estimated_cost = _calculate_token_cost(input_tokens, output_tokens)
                logger.debug(
                    "Token usage: %d input, %d output, $%.4f cost",
                    input_tokens, output_tokens, estimated_cost
                )

            return json.loads(content), tokens_used, estimated_cost

        except openai.APIError as e:
            logger.error("OpenAI API error: %s", e)
            raise AgentRunnerError(f"OpenAI API error: {e}")
        except json.JSONDecodeError as e:
            logger.error("Failed to parse agent response as JSON: %s", e)
            raise AgentRunnerError(f"Invalid JSON response from agent: {e}")

    def parse_agent_response(
        self,
        response: dict[str, Any],
        tokens_used: int = 0,
        estimated_cost: float = 0.0,
    ) -> AgentResponse:
        """
        Parse the raw agent response into structured AgentResponse.

        Args:
            response: Raw JSON response from call_agent()
            tokens_used: Total tokens used in the LLM call
            estimated_cost: Estimated cost of the LLM call

        Returns:
            Parsed AgentResponse

        Raises:
            AgentRunnerError: If response is missing required fields
        """
        try:
            # Extract action
            action_data = response.get("action", {})
            action_type = action_data.get("type", "no_action")

            # Validate action type
            valid_types = {"send_message", "pause", "complete", "update_status", "no_action"}
            if action_type not in valid_types:
                logger.warning("Unknown action type: %s, defaulting to no_action", action_type)
                action_type = "no_action"

            action = AgentAction(
                type=action_type,
                channel=action_data.get("channel"),
                recipient=action_data.get("recipient"),
                content=action_data.get("content"),
                pause_reason=action_data.get("pause_reason"),
                needs_approval_for=action_data.get("needs_approval_for"),
            )

            # Extract task update
            task_update = None
            task_update_data = response.get("task_update")
            if task_update_data:
                task_update = TaskUpdate(
                    progress_note=task_update_data.get("progress_note"),
                    awaiting=task_update_data.get("awaiting"),
                )

            return AgentResponse(
                jorb_id=response.get("task_id"),
                reasoning=response.get("reasoning", ""),
                action=action,
                task_update=task_update,
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
            )

        except Exception as e:
            logger.error("Error parsing agent response: %s", e)
            raise AgentRunnerError(f"Failed to parse agent response: {e}")

    async def get_open_jorbs(self) -> list[JorbWithMessages]:
        """Get all open jorbs with their messages."""
        return await self._storage.get_open_jorbs_with_messages()

    async def store_inbound_message(
        self,
        jorb_id: str,
        event: IncomingEvent,
    ) -> str:
        """
        Store an inbound message in a jorb's history.

        Args:
            jorb_id: The jorb ID
            event: The incoming event

        Returns:
            The message ID
        """
        message = JorbMessage(
            id="",  # Will be generated
            jorb_id=jorb_id,
            timestamp=event.timestamp,
            direction="inbound",
            channel=event.channel,
            sender=event.sender,
            sender_name=event.sender_name,
            content=event.content,
        )
        msg_id = await self._storage.add_message(jorb_id, message)

        # Increment inbound message counter
        await self._storage.increment_metrics(jorb_id, messages_in=1)

        return msg_id

    async def store_outbound_message(
        self,
        jorb_id: str,
        channel: Channel,
        recipient: str,
        content: str,
        reasoning: str | None = None,
    ) -> str:
        """
        Store an outbound message in a jorb's history.

        Args:
            jorb_id: The jorb ID
            channel: Message channel
            recipient: Message recipient
            content: Message content
            reasoning: Agent's reasoning for the message

        Returns:
            The message ID
        """
        message = JorbMessage(
            id="",  # Will be generated
            jorb_id=jorb_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            direction="outbound",
            channel=channel,
            recipient=recipient,
            content=content,
            agent_reasoning=reasoning,
        )
        msg_id = await self._storage.add_message(jorb_id, message)

        # Increment outbound message counter
        await self._storage.increment_metrics(jorb_id, messages_out=1)

        return msg_id

    async def store_human_intervention_message(
        self,
        jorb_id: str,
        event: IncomingEvent,
    ) -> str:
        """
        Store a human intervention message (Sean's direct message) in a jorb's history.

        This marks the message with sender='sean_direct' to indicate Sean sent it
        directly rather than through frank_bot. These messages are recorded but
        do NOT trigger LLM responses.

        Args:
            jorb_id: The jorb ID
            event: The incoming event from Sean's direct message

        Returns:
            The message ID
        """
        message = JorbMessage(
            id="",  # Will be generated
            jorb_id=jorb_id,
            timestamp=event.timestamp,
            direction="outbound",  # Sean's message TO the contact
            channel=event.channel,
            sender="sean_direct",  # Special marker for human intervention
            sender_name="Sean",
            recipient=event.sender,  # The original sender becomes recipient
            content=event.content,
        )
        msg_id = await self._storage.add_message(jorb_id, message)

        # Increment outbound message counter (Sean sent it)
        await self._storage.increment_metrics(jorb_id, messages_out=1)

        logger.info(
            "Stored human intervention message for jorb %s: %s",
            jorb_id,
            event.content[:50],
        )

        return msg_id

    def _check_closure_words(self, content: str) -> bool:
        """
        Check if message content suggests closure (task completion).

        Args:
            content: The message content to check

        Returns:
            True if content suggests closure
        """
        closure_words = {
            "thanks", "thank you", "done", "perfect", "great", "awesome",
            "got it", "all set", "sounds good", "works for me", "appreciate it",
            "thx", "ty", "cheers", "sorted", "all good",
        }
        content_lower = content.lower()
        return any(word in content_lower for word in closure_words)

    async def update_jorb_status(
        self,
        jorb_id: str,
        status: str | None = None,
        progress_summary: str | None = None,
        paused_reason: str | None = None,
        needs_approval_for: str | None = None,
        awaiting: str | None = None,
    ) -> Jorb | None:
        """
        Update a jorb's status and related fields.

        Args:
            jorb_id: The jorb ID
            status: New status (planning, running, paused, complete, failed, cancelled)
            progress_summary: Updated progress summary
            paused_reason: Reason for pausing (if pausing)
            needs_approval_for: What approval is needed (if pausing)
            awaiting: What the jorb is waiting for

        Returns:
            Updated Jorb or None if not found
        """
        updates: dict[str, Any] = {}
        if status is not None:
            updates["status"] = status
        if progress_summary is not None:
            updates["progress_summary"] = progress_summary
        if paused_reason is not None:
            updates["paused_reason"] = paused_reason
        if needs_approval_for is not None:
            updates["needs_approval_for"] = needs_approval_for
        if awaiting is not None:
            updates["awaiting"] = awaiting

        if updates:
            return await self._storage.update_jorb(jorb_id, **updates)
        return await self._storage.get_jorb(jorb_id)

    def _check_rate_limit(self, jorb_id: str) -> bool:
        """
        Check if a jorb has exceeded the message rate limit.

        Args:
            jorb_id: The jorb ID

        Returns:
            True if rate limit is exceeded
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()

        # Get timestamps for this jorb
        timestamps = self._message_counts.get(jorb_id, [])

        # Filter to only messages in the last hour
        recent = [ts for ts in timestamps if ts > one_hour_ago]
        self._message_counts[jorb_id] = recent

        return len(recent) >= self._policy.max_messages_per_hour

    def _record_message_sent(self, jorb_id: str) -> None:
        """Record that a message was sent for rate limiting."""
        now = datetime.now(timezone.utc).isoformat()
        if jorb_id not in self._message_counts:
            self._message_counts[jorb_id] = []
        self._message_counts[jorb_id].append(now)

    def _record_policy_violation(
        self,
        jorb_id: str,
        jorb_name: str,
        violation_type: str,
        message: str,
    ) -> None:
        """Record a policy violation for briefing."""
        violation = PolicyViolation(
            jorb_id=jorb_id,
            jorb_name=jorb_name,
            violation_type=violation_type,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._policy_violations.append(violation)
        logger.warning(
            "Policy violation for jorb %s (%s): %s - %s",
            jorb_id, jorb_name, violation_type, message
        )

    async def check_stale_jorbs(self) -> list[str]:
        """
        Check for and auto-pause stale jorbs (no activity in stale_jorb_hours).

        Returns:
            List of jorb IDs that were paused
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(
            hours=self._policy.stale_jorb_hours
        )
        stale_threshold_iso = stale_threshold.isoformat()

        jorbs = await self._storage.list_jorbs(status_filter="open")
        paused_ids = []

        for jorb in jorbs:
            if jorb.status != "running":
                continue

            # Check if jorb is stale (updated_at older than threshold)
            if jorb.updated_at < stale_threshold_iso:
                logger.info(
                    "Auto-pausing stale jorb %s (last updated: %s)",
                    jorb.id, jorb.updated_at
                )

                await self._storage.update_jorb(
                    jorb.id,
                    status="paused",
                    paused_reason=f"Auto-paused: no activity in {self._policy.stale_jorb_hours} hours",
                    needs_approval_for="resume",
                )

                self._record_policy_violation(
                    jorb.id,
                    jorb.name,
                    "stale_jorb",
                    f"No activity in {self._policy.stale_jorb_hours} hours",
                )

                paused_ids.append(jorb.id)

        return paused_ids

    async def check_expired_jorbs(self) -> list[str]:
        """
        Check for and auto-fail jorbs exceeding max duration.

        Returns:
            List of jorb IDs that were failed
        """
        max_duration = timedelta(days=self._policy.max_jorb_duration_days)
        expiry_threshold = datetime.now(timezone.utc) - max_duration
        expiry_threshold_iso = expiry_threshold.isoformat()

        jorbs = await self._storage.list_jorbs(status_filter="open")
        failed_ids = []

        for jorb in jorbs:
            if jorb.status in ("complete", "failed", "cancelled"):
                continue

            # Check if jorb has exceeded max duration
            if jorb.created_at < expiry_threshold_iso:
                logger.info(
                    "Auto-failing expired jorb %s (created: %s)",
                    jorb.id, jorb.created_at
                )

                previous_summary = jorb.progress_summary or ""
                new_summary = f"{previous_summary}\nAuto-failed: exceeded {self._policy.max_jorb_duration_days} day limit".strip()

                await self._storage.update_jorb(
                    jorb.id,
                    status="failed",
                    progress_summary=new_summary,
                )

                self._record_policy_violation(
                    jorb.id,
                    jorb.name,
                    "expired_jorb",
                    f"Exceeded {self._policy.max_jorb_duration_days} day duration limit",
                )

                failed_ids.append(jorb.id)

        return failed_ids

    async def enforce_policies(self) -> dict[str, list[str]]:
        """
        Run all policy enforcement checks.

        Returns:
            Dict with lists of affected jorb IDs per policy type
        """
        stale = await self.check_stale_jorbs()
        expired = await self.check_expired_jorbs()

        return {
            "paused_stale": stale,
            "failed_expired": expired,
        }

    # --- Script execution (frank_bot-00114) ---

    async def _execute_script(
        self,
        jorb: Jorb,
        script_str: str,
        timeout: int = SCRIPT_EXECUTION_TIMEOUT,
    ) -> dict:
        """
        Execute a script expression using FrankAPI and store the result.

        The script is a Python expression like 'frank.calendar.events(day="2026-02-05")'
        or a multi-line snippet using the 'frank' object. The result (or error) is
        stored via JorbStorage.add_script_result() so the LLM can see it on the
        next iteration.

        Args:
            jorb: The jorb this script belongs to
            script_str: Python code/expression to execute
            timeout: Maximum execution time in seconds

        Returns:
            Dict with keys: script, result, success, error, timestamp
        """
        from meta.api import FrankAPI

        timestamp = datetime.now(timezone.utc).isoformat()

        def _run_script() -> Any:
            frank = FrankAPI()
            namespace: dict[str, Any] = {"frank": frank, "__builtins__": __builtins__}
            # Try as expression first (e.g. frank.calendar.events(...))
            try:
                return eval(script_str, namespace)
            except SyntaxError:
                # Fall back to exec for multi-line scripts
                exec(script_str, namespace)
                return namespace.get("result")

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_run_script)
            try:
                result_value = future.result(timeout=timeout)
                result_dict = {
                    "script": script_str[:500],
                    "result": result_value,
                    "success": True,
                    "timestamp": timestamp,
                }
            except FuturesTimeoutError:
                future.cancel()
                result_dict = {
                    "script": script_str[:500],
                    "result": None,
                    "success": False,
                    "error": f"Script timed out after {timeout} seconds",
                    "timestamp": timestamp,
                }
            except Exception as exc:
                tb_str = traceback.format_exc()
                result_dict = {
                    "script": script_str[:500],
                    "result": None,
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": tb_str[:1000],
                    "timestamp": timestamp,
                }
        finally:
            executor.shutdown(wait=False)

        # Store the result
        try:
            await self._storage.add_script_result(jorb.id, result_dict)
        except Exception as e:
            logger.error("Failed to store script result for jorb %s: %s", jorb.id, e)

        logger.info(
            "Script execution for jorb %s: success=%s, script=%s",
            jorb.id,
            result_dict.get("success"),
            script_str[:80],
        )

        return result_dict

    # --- Rate limiting for LLM iteration loops (frank_bot-00116) ---

    def _check_iteration_rate_limit(self, jorb_id: str) -> str | None:
        """
        Check if a jorb has exceeded LLM iteration rate limits.

        Tracks invocation timestamps per jorb and enforces both hourly and daily limits.

        Args:
            jorb_id: The jorb ID

        Returns:
            None if under limit, or a string explaining which limit was exceeded
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        key = f"iter_{jorb_id}"
        timestamps = self._message_counts.get(key, [])

        # Parse timestamps and filter
        recent_hour = [ts for ts in timestamps if ts > one_hour_ago.isoformat()]
        recent_day = [ts for ts in timestamps if ts > one_day_ago.isoformat()]

        # Update stored timestamps (prune old ones)
        self._message_counts[key] = recent_day

        if len(recent_hour) >= MAX_ITERATIONS_PER_HOUR:
            return f"Rate limit exceeded: {MAX_ITERATIONS_PER_HOUR} LLM invocations per hour"

        if len(recent_day) >= MAX_ITERATIONS_PER_DAY:
            return f"Rate limit exceeded: {MAX_ITERATIONS_PER_DAY} LLM invocations per day"

        return None

    def _record_iteration(self, jorb_id: str) -> None:
        """Record an LLM iteration for rate limiting."""
        key = f"iter_{jorb_id}"
        now = datetime.now(timezone.utc).isoformat()
        if key not in self._message_counts:
            self._message_counts[key] = []
        self._message_counts[key].append(now)

    # --- Agent loop for jorb processing (frank_bot-00115) ---

    async def process_jorb_event(
        self,
        jorb: Jorb,
        event: IncomingEvent | None = None,
    ) -> ProcessingResult:
        """
        Process a jorb event using the iterative agent loop.

        Implements: invoke LLM -> parse action -> execute -> decide next step.
        - Sync scripts (await_reply=false, done=false): execute, feed result back, continue
        - Async scripts (await_reply=true): execute, mark awaiting reply, break
        - Done: mark complete, break
        - Pause: mark paused, break
        - No action: break (safety fallback)

        Args:
            jorb: The jorb to process
            event: Optional incoming event that triggered processing

        Returns:
            ProcessingResult with details of what happened
        """
        jorb_id = jorb.id
        message_sent = False
        last_action = "no_action"

        # Reload jorb with messages for each LLM call
        async def _get_jorb_with_messages() -> JorbWithMessages:
            refreshed_jorb = await self._storage.get_jorb(jorb_id)
            if refreshed_jorb is None:
                raise AgentRunnerError(f"Jorb {jorb_id} not found")
            messages = await self._storage.get_messages(jorb_id)
            return JorbWithMessages(jorb=refreshed_jorb, messages=messages)

        while True:
            # Check rate limit before each LLM invocation
            rate_limit_msg = self._check_iteration_rate_limit(jorb_id)
            if rate_limit_msg:
                logger.warning("Rate limit hit for jorb %s: %s", jorb_id, rate_limit_msg)
                self._record_policy_violation(
                    jorb_id, jorb.name, "iteration_rate_limit", rate_limit_msg
                )
                await self.update_jorb_status(
                    jorb_id=jorb_id,
                    status="paused",
                    paused_reason=rate_limit_msg,
                )
                return ProcessingResult(
                    jorb_id=jorb_id,
                    action_taken="paused_rate_limit",
                    success=True,
                )

            # Record this iteration
            self._record_iteration(jorb_id)

            # Get fresh jorb state with messages and script_results
            jwm = await _get_jorb_with_messages()

            # Create session and invoke LLM
            jorb_session = create_jorb_session(
                jwm,
                policy=self._policy.to_context_dict(),
            )

            if event is not None:
                # First iteration with incoming message
                session_response = await jorb_session.process_message(
                    channel=event.channel,
                    sender=event.sender,
                    sender_name=event.sender_name,
                    content=event.content,
                    timestamp=event.timestamp,
                    message_count=event.message_count,
                )
                event = None  # Only use event for first iteration
            else:
                # Subsequent iterations (kickoff or after script result)
                session_response = await jorb_session.kickoff()

            # Track token usage
            if session_response.tokens_used > 0:
                await self._storage.increment_metrics(
                    jorb_id,
                    tokens_used=session_response.tokens_used,
                    estimated_cost=session_response.estimated_cost,
                )

            action = session_response.action
            last_action = action.type

            logger.info(
                "Agent loop for jorb %s: action=%s, script=%s, await_reply=%s, done=%s, pause=%s",
                jorb_id, action.type,
                (action.script or "")[:60],
                action.await_reply, action.done, action.pause,
            )

            # Update progress if provided
            if session_response.progress:
                progress = session_response.progress
                await self.update_jorb_status(
                    jorb_id=jorb_id,
                    progress_summary=progress.note,
                    awaiting=progress.awaiting,
                )

            # --- Handle each action type ---

            if action.done:
                # Done: mark jorb complete
                result_data = action.result or session_response.result
                await self.update_jorb_status(jorb_id=jorb_id, status="complete")
                await self._storage.set_outcome(
                    jorb_id,
                    result=json.dumps(result_data) if result_data else None,
                )
                return ProcessingResult(
                    jorb_id=jorb_id,
                    action_taken="complete",
                    success=True,
                    message_sent=message_sent,
                )

            if action.pause:
                # Pause: mark jorb paused
                await self.update_jorb_status(
                    jorb_id=jorb_id,
                    status="paused",
                    paused_reason=action.pause_reason or "Paused by agent",
                )
                return ProcessingResult(
                    jorb_id=jorb_id,
                    action_taken="pause",
                    success=True,
                    message_sent=message_sent,
                )

            if action.script:
                # Execute the script
                script_result = await self._execute_script(jwm.jorb, action.script)

                if action.await_reply:
                    # Async: script sent a message, wait for human reply
                    await self.update_jorb_status(
                        jorb_id=jorb_id,
                        status="running",
                        awaiting="human_reply",
                    )
                    message_sent = True
                    return ProcessingResult(
                        jorb_id=jorb_id,
                        action_taken="script_await_reply",
                        success=True,
                        message_sent=True,
                    )
                else:
                    # Sync: feed result back to LLM, continue loop
                    continue

            # No script, no done, no pause: safety fallback - break
            return ProcessingResult(
                jorb_id=jorb_id,
                action_taken=last_action,
                success=True,
                message_sent=message_sent,
            )

    async def _send_message(
        self,
        channel: Channel,
        recipient: str,
        content: str,
    ) -> bool:
        """
        Send a message via the appropriate service.

        Args:
            channel: Channel to send on (sms, telegram, email)
            recipient: Recipient identifier
            content: Message content

        Returns:
            True if message was sent successfully
        """
        try:
            if channel == "sms":
                from services.telnyx_sms import TelnyxSMSService
                sms_service = TelnyxSMSService()
                result = sms_service.send_sms(recipient, content)
                return result.success

            elif channel == "telegram":
                from services.telegram_client import TelegramClientService
                telegram_service = TelegramClientService()
                result = await telegram_service.send_message(recipient, content)
                return result.success

            elif channel == "email":
                # Email sending will be implemented in frank_bot-00066
                logger.warning("Email sending not yet implemented")
                return False

            else:
                logger.error("Unknown channel: %s", channel)
                return False

        except Exception as e:
            logger.error("Error sending %s message to %s: %s", channel, recipient, e)
            return False

    async def _enrich_event_with_contact(self, event: IncomingEvent) -> IncomingEvent:
        """
        Enrich an incoming event with contact lookup information.

        Tries to look up the sender's name from Google Contacts if not already provided.

        Args:
            event: The incoming event

        Returns:
            The event with sender_name populated if found
        """
        # If we already have a sender name, no need to look up
        if event.sender_name:
            return event

        # Only try contact lookup for SMS (phone numbers)
        # Telegram usernames can't be looked up in Google Contacts
        if event.channel != "sms":
            return event

        try:
            from services.contact_lookup import ContactLookup
            contact_lookup = ContactLookup()
            contact = contact_lookup.lookup(event.sender)

            if contact:
                # Create a new event with the enriched name
                return IncomingEvent(
                    channel=event.channel,
                    sender=event.sender,
                    sender_name=contact.name,
                    content=event.content,
                    timestamp=event.timestamp,
                    message_count=event.message_count,
                    is_human_intervention=event.is_human_intervention,
                )
        except Exception as e:
            logger.warning("Contact lookup failed for %s: %s", event.sender, e)

        return event

    async def process_incoming_message(
        self,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Process an incoming message event.

        This is the main entry point for handling incoming SMS/Telegram messages.

        With switchboard mode (default):
        1. Enriches the event with contact information
        2. Uses switchboard to route message to correct jorb
        3. Creates jorb session with personality for matched jorb
        4. Jorb session decides on action
        5. Executes the action and stores messages

        With legacy mode (USE_SWITCHBOARD_MODE=false):
        - Uses single LLM call for both routing and action decision

        Args:
            event: The incoming message event

        Returns:
            ProcessingResult with jorb_id, action_taken, and success status
        """
        # Use switchboard mode if enabled
        if _use_switchboard_mode():
            return await self._process_with_switchboard(event)

        # Legacy single-stage mode
        return await self._process_legacy(event)

    async def _process_with_switchboard(
        self,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Process message using two-stage switchboard pattern.

        Stage 1: Switchboard routes to jorb
        Stage 2: Jorb session handles conversation
        """
        try:
            # Step 1: Enrich event with contact info
            enriched_event = await self._enrich_event_with_contact(event)
            logger.info(
                "Processing incoming %s message from %s (%s) [switchboard mode]",
                enriched_event.channel,
                enriched_event.sender,
                enriched_event.sender_name or "unknown",
            )

            # Step 2: Fetch open jorbs
            open_jorbs = await self.get_open_jorbs()
            logger.debug("Found %d open jorbs", len(open_jorbs))

            # Step 3: Route with switchboard
            switchboard = get_switchboard()
            routing = await switchboard.route(
                channel=enriched_event.channel,
                sender=enriched_event.sender,
                sender_name=enriched_event.sender_name,
                content=enriched_event.content,
                timestamp=enriched_event.timestamp,
                open_jorbs=open_jorbs,
                is_human_intervention=enriched_event.is_human_intervention,
            )

            logger.info(
                "Switchboard routed to %s (%s): %s",
                routing.jorb_id,
                routing.confidence,
                routing.reasoning[:50],
            )

            # Track switchboard tokens
            total_tokens = routing.tokens_used
            total_cost = 0.0

            # Step 4: Handle based on routing result
            if not routing.jorb_id:
                # No matching jorb
                if routing.is_spam:
                    logger.info("Message identified as spam, ignoring")
                    return ProcessingResult(
                        jorb_id=None,
                        action_taken="spam_filtered",
                        success=True,
                    )

                if routing.might_be_new_jorb:
                    # Check if this is a trusted sender who might have an in-flight task
                    is_trusted = await self.is_trusted_sender(enriched_event.sender)

                    if is_trusted:
                        # Create catch-up jorb for in-flight task
                        return await self._create_catch_up_jorb(enriched_event)
                    else:
                        # Unknown sender - flag for review instead of auto-jorbing
                        return await self._flag_for_review(enriched_event)

                return ProcessingResult(
                    jorb_id=None,
                    action_taken="no_match",
                    success=True,
                )

            # Step 5: Find the matched jorb
            matched_jorb = None
            for jwm in open_jorbs:
                if jwm.jorb.id == routing.jorb_id:
                    matched_jorb = jwm
                    break

            if not matched_jorb:
                logger.warning("Routed to jorb %s but not found in open jorbs", routing.jorb_id)
                return ProcessingResult(
                    jorb_id=routing.jorb_id,
                    action_taken="jorb_not_found",
                    success=False,
                    error="Routed jorb not found",
                )

            # Step 6: Handle human intervention (Sean's direct messages)
            if enriched_event.is_human_intervention:
                return await self._handle_human_intervention(
                    routing.jorb_id,
                    matched_jorb,
                    enriched_event,
                )

            # Step 7: Store the inbound message (for regular messages)
            await self.store_inbound_message(routing.jorb_id, enriched_event)

            # Step 8: Create jorb session with personality
            jorb_session = create_jorb_session(
                matched_jorb,
                policy=self._policy.to_context_dict(),
            )

            # Step 9: Process with jorb session
            session_response = await jorb_session.process_message(
                channel=enriched_event.channel,
                sender=enriched_event.sender,
                sender_name=enriched_event.sender_name,
                content=enriched_event.content,
                timestamp=enriched_event.timestamp,
                message_count=enriched_event.message_count,
            )

            # Track session tokens
            total_tokens += session_response.tokens_used
            total_cost = session_response.estimated_cost

            logger.info(
                "Jorb session decided: action=%s, reasoning=%s",
                session_response.action.type,
                session_response.reasoning[:100] if session_response.reasoning else "",
            )

            # Update token metrics for this jorb
            if total_tokens > 0:
                await self._storage.increment_metrics(
                    routing.jorb_id,
                    tokens_used=total_tokens,
                    estimated_cost=total_cost,
                )

            # Step 10: Execute the action
            message_sent = False
            action = session_response.action

            if action.type == "send_message":
                message_sent = await self._execute_send_message(
                    jorb_id=routing.jorb_id,
                    jorb_name=matched_jorb.jorb.name,
                    action=action,
                    reasoning=session_response.reasoning,
                )

            elif action.type == "pause":
                await self.update_jorb_status(
                    jorb_id=routing.jorb_id,
                    status="paused",
                    paused_reason=action.pause_reason,
                    needs_approval_for=action.needs_approval_for,
                )

            elif action.type == "complete":
                await self.update_jorb_status(
                    jorb_id=routing.jorb_id,
                    status="complete",
                )

            # Step 11: Update progress if provided
            if session_response.progress:
                progress = session_response.progress
                await self.update_jorb_status(
                    jorb_id=routing.jorb_id,
                    progress_summary=progress.note,
                    awaiting=progress.awaiting,
                )

                # Record progress in log
                if progress.note:
                    progress_log = get_progress_log()
                    progress_log.add_entry(
                        entry_type="task_progress",
                        summary=progress.note,
                        jorb_id=routing.jorb_id,
                        jorb_name=matched_jorb.jorb.name,
                    )

            return ProcessingResult(
                jorb_id=routing.jorb_id,
                action_taken=action.type,
                success=True,
                message_sent=message_sent,
            )

        except Exception as e:
            logger.exception("Error in switchboard processing")
            return ProcessingResult(
                jorb_id=None,
                action_taken="error",
                success=False,
                error=str(e),
            )

    async def _execute_send_message(
        self,
        jorb_id: str,
        jorb_name: str,
        action: JorbAction,
        reasoning: str,
    ) -> bool:
        """Execute a send_message action with rate limiting."""
        if not action.channel or not action.recipient or not action.content:
            logger.warning("send_message action missing required fields")
            return False

        # Check rate limit before sending
        if self._check_rate_limit(jorb_id):
            logger.warning(
                "Rate limit exceeded for jorb %s (%d messages/hour)",
                jorb_id,
                self._policy.max_messages_per_hour,
            )
            self._record_policy_violation(
                jorb_id,
                jorb_name,
                "rate_limit",
                f"Exceeded {self._policy.max_messages_per_hour} messages per hour",
            )
            await self.update_jorb_status(
                jorb_id=jorb_id,
                status="paused",
                paused_reason=f"Rate limit exceeded ({self._policy.max_messages_per_hour}/hour)",
                needs_approval_for="resume",
            )
            return False

        # Send the message
        send_success = await self._send_message(
            action.channel,
            action.recipient,
            action.content,
        )

        if send_success:
            # Store outbound message and record for rate limiting
            await self.store_outbound_message(
                jorb_id=jorb_id,
                channel=action.channel,
                recipient=action.recipient,
                content=action.content,
                reasoning=reasoning,
            )
            self._record_message_sent(jorb_id)
            return True
        else:
            logger.error(
                "Failed to send message to %s via %s",
                action.recipient,
                action.channel,
            )
            return False

    async def _handle_human_intervention(
        self,
        jorb_id: str,
        matched_jorb: JorbWithMessages,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Handle human intervention - when Sean sends a direct message.

        When Sean sends a message directly (not through frank_bot), we:
        1. Store the message with sender='sean_direct' marker
        2. Do NOT call the jorb session for LLM response
        3. Update progress_summary with intervention note
        4. Check if message suggests closure and potentially update status

        Args:
            jorb_id: The jorb ID this message relates to
            matched_jorb: The matched jorb with messages
            event: The incoming event (Sean's direct message)

        Returns:
            ProcessingResult with action_taken='human_intervention_recorded'
        """
        logger.info(
            "Human intervention detected for jorb %s: %s",
            jorb_id,
            event.content[:50],
        )

        # Step 1: Store the message with sean_direct marker
        await self.store_human_intervention_message(jorb_id, event)

        # Step 2: Create progress note
        content_preview = event.content[:50]
        if len(event.content) > 50:
            content_preview += "..."
        progress_note = f"Sean intervened directly: {content_preview}"

        # Step 3: Check if message suggests closure
        suggests_closure = self._check_closure_words(event.content)

        if suggests_closure:
            logger.info(
                "Sean's message suggests closure for jorb %s, marking as complete",
                jorb_id,
            )
            await self.update_jorb_status(
                jorb_id=jorb_id,
                status="complete",
                progress_summary=progress_note,
            )
        else:
            # Just update progress summary
            await self.update_jorb_status(
                jorb_id=jorb_id,
                progress_summary=progress_note,
            )

        # Step 4: Record in progress log
        progress_log = get_progress_log()
        progress_log.add_entry(
            entry_type="task_progress",
            summary=progress_note,
            jorb_id=jorb_id,
            jorb_name=matched_jorb.jorb.name,
            details={
                "intervention_type": "sean_direct",
                "suggests_closure": suggests_closure,
            },
        )

        return ProcessingResult(
            jorb_id=jorb_id,
            action_taken="human_intervention_recorded",
            success=True,
            message_sent=False,  # Sean already sent it, we just recorded it
        )

    async def _create_catch_up_jorb(
        self,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Create a catch-up jorb for an in-flight task from a trusted sender.

        When a trusted sender sends a message that doesn't match any existing jorb,
        we create a catch-up jorb to recover context for the in-flight task.

        Args:
            event: The incoming event from the trusted sender

        Returns:
            ProcessingResult with the new jorb_id and action_taken='catch_up_created'
        """
        logger.info(
            "Creating catch-up jorb for trusted sender %s: %s",
            event.sender,
            event.content[:50],
        )

        # Build jorb name from first 30 chars of message
        content_preview = event.content[:30]
        if len(event.content) > 30:
            content_preview = content_preview.rsplit(" ", 1)[0]  # Don't cut mid-word
            if not content_preview:
                content_preview = event.content[:30]
        jorb_name = f"Catch-up: {content_preview}"

        # Build plan that indicates this is a context recovery
        plan = f"Recover context for in-flight task. Original message: {event.content}"

        # Create the contact
        contact = JorbContact(
            identifier=event.sender,
            channel=event.channel,
            name=event.sender_name,
        )

        # Create the catch-up jorb with sean-voice personality
        jorb = await self._storage.create_jorb(
            name=jorb_name,
            plan=plan,
            contacts=[contact],
            personality="sean-voice",
        )

        # Update status to running
        await self._storage.update_jorb(jorb.id, status="running")

        # Store the incoming message as first inbound message
        await self.store_inbound_message(jorb.id, event)

        # Record in progress log
        progress_log = get_progress_log()
        progress_log.add_entry(
            entry_type="task_progress",
            summary=f"Created catch-up jorb for in-flight task: {content_preview}",
            jorb_id=jorb.id,
            jorb_name=jorb_name,
            details={
                "sender": event.sender,
                "channel": event.channel,
                "original_message": event.content,
            },
        )

        logger.info(
            "Created catch-up jorb %s: %s",
            jorb.id,
            jorb_name,
        )

        # Kick off the jorb with special first_action to ask for context
        # This will be handled by task 00084
        result = await self.kickoff_jorb(jorb)

        return ProcessingResult(
            jorb_id=jorb.id,
            action_taken="catch_up_created",
            success=True,
            message_sent=result.message_sent,
        )

    async def _flag_for_review(
        self,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Flag a message from an unknown sender for human review.

        When an unknown sender sends a message that might warrant a jorb,
        we don't auto-create (could be spam or wrong number). Instead,
        we flag for Sean to review and possibly create a jorb manually.

        Args:
            event: The incoming event from the unknown sender

        Returns:
            ProcessingResult with action_taken='flagged_for_review'
        """
        logger.info(
            "Flagging message from unknown sender %s for review: %s",
            event.sender,
            event.content[:50],
        )

        # Try to send Telegram notification to Sean
        try:
            from services.telegram_bot import TelegramBot
            telegram_bot = TelegramBot()

            content_preview = event.content[:100]
            if len(event.content) > 100:
                content_preview += "..."

            notification = (
                f"Unknown sender {event.sender} sent:\n"
                f"{content_preview}\n\n"
                f"Create jorb?"
            )
            await telegram_bot.send_notification(notification)
        except Exception as e:
            logger.warning("Failed to send review notification: %s", e)

        # Record in progress log
        progress_log = get_progress_log()
        progress_log.add_entry(
            entry_type="task_progress",
            summary=f"Flagged unknown sender for review: {event.sender}",
            details={
                "sender": event.sender,
                "channel": event.channel,
                "content_preview": event.content[:100],
            },
        )

        return ProcessingResult(
            jorb_id=None,
            action_taken="flagged_for_review",
            success=True,
            message_sent=False,
        )

    async def _process_legacy(
        self,
        event: IncomingEvent,
    ) -> ProcessingResult:
        """
        Legacy single-stage processing (pre-switchboard).

        Kept for backwards compatibility when USE_SWITCHBOARD_MODE=false.
        """
        try:
            # Step 1: Enrich event with contact info
            enriched_event = await self._enrich_event_with_contact(event)
            logger.info(
                "Processing incoming %s message from %s (%s)",
                enriched_event.channel,
                enriched_event.sender,
                enriched_event.sender_name or "unknown",
            )

            # Step 2: Fetch open jorbs
            open_jorbs = await self.get_open_jorbs()
            logger.debug("Found %d open jorbs", len(open_jorbs))

            # Step 3: Call the LLM for decision
            context = self.build_context(enriched_event, open_jorbs)
            raw_response, tokens_used, estimated_cost = await self.call_agent(context)
            agent_response = self.parse_agent_response(raw_response, tokens_used, estimated_cost)

            logger.info(
                "Agent decided: jorb=%s, action=%s, reasoning=%s",
                agent_response.jorb_id,
                agent_response.action.type,
                agent_response.reasoning[:100] if agent_response.reasoning else "",
            )

            # Step 4: Store the inbound message (if matched to a jorb)
            if agent_response.jorb_id:
                await self.store_inbound_message(agent_response.jorb_id, enriched_event)

                # Update token metrics for this jorb
                if tokens_used > 0:
                    await self._storage.increment_metrics(
                        agent_response.jorb_id,
                        tokens_used=tokens_used,
                        estimated_cost=estimated_cost,
                    )

            # Step 5: Execute the action
            message_sent = False
            action = agent_response.action

            if action.type == "send_message":
                if action.channel and action.recipient and action.content:
                    # Check rate limit before sending
                    if agent_response.jorb_id and self._check_rate_limit(agent_response.jorb_id):
                        # Rate limited - pause the jorb
                        jorb = await self._storage.get_jorb(agent_response.jorb_id)
                        logger.warning(
                            "Rate limit exceeded for jorb %s (%d messages/hour)",
                            agent_response.jorb_id,
                            self._policy.max_messages_per_hour,
                        )
                        self._record_policy_violation(
                            agent_response.jorb_id,
                            jorb.name if jorb else "unknown",
                            "rate_limit",
                            f"Exceeded {self._policy.max_messages_per_hour} messages per hour",
                        )
                        await self.update_jorb_status(
                            jorb_id=agent_response.jorb_id,
                            status="paused",
                            paused_reason=f"Rate limit exceeded ({self._policy.max_messages_per_hour}/hour)",
                            needs_approval_for="resume",
                        )
                    else:
                        # Send the message
                        send_success = await self._send_message(
                            action.channel,
                            action.recipient,
                            action.content,
                        )

                        if send_success and agent_response.jorb_id:
                            # Store outbound message and record for rate limiting
                            await self.store_outbound_message(
                                jorb_id=agent_response.jorb_id,
                                channel=action.channel,
                                recipient=action.recipient,
                                content=action.content,
                                reasoning=agent_response.reasoning,
                            )
                            self._record_message_sent(agent_response.jorb_id)
                            message_sent = True
                        elif not send_success:
                            logger.error("Failed to send message to %s via %s",
                                       action.recipient, action.channel)
                else:
                    logger.warning("send_message action missing required fields")

            elif action.type == "pause":
                if agent_response.jorb_id:
                    await self.update_jorb_status(
                        jorb_id=agent_response.jorb_id,
                        status="paused",
                        paused_reason=action.pause_reason,
                        needs_approval_for=action.needs_approval_for,
                    )

            elif action.type == "complete":
                if agent_response.jorb_id:
                    await self.update_jorb_status(
                        jorb_id=agent_response.jorb_id,
                        status="complete",
                    )

            # Step 6: Update jorb with task_update if provided
            if agent_response.jorb_id and agent_response.task_update:
                update = agent_response.task_update
                await self.update_jorb_status(
                    jorb_id=agent_response.jorb_id,
                    progress_summary=update.progress_note,
                    awaiting=update.awaiting,
                )

            return ProcessingResult(
                jorb_id=agent_response.jorb_id,
                action_taken=action.type,
                success=True,
                message_sent=message_sent,
            )

        except AgentRunnerError as e:
            logger.error("Agent runner error: %s", e)
            return ProcessingResult(
                jorb_id=None,
                action_taken="error",
                success=False,
                error=str(e),
            )
        except Exception as e:
            logger.exception("Unexpected error processing message")
            return ProcessingResult(
                jorb_id=None,
                action_taken="error",
                success=False,
                error=str(e),
            )

    async def kickoff_jorb(self, jorb: Jorb) -> KickoffResult:
        """
        Kick off a new jorb by sending its initial message.

        This is called when a jorb is created with start_immediately=True.

        With switchboard mode:
        1. Creates jorb session with personality
        2. Jorb session generates first action
        3. Executes send_message if returned
        4. Updates status to running

        With legacy mode:
        - Uses single LLM call with jorb_created event type

        Args:
            jorb: The Jorb to kick off

        Returns:
            KickoffResult with success status and details
        """
        # Use switchboard mode if enabled
        if _use_switchboard_mode():
            return await self._kickoff_with_session(jorb)

        # Legacy mode
        return await self._kickoff_legacy(jorb)

    async def _kickoff_with_session(self, jorb: Jorb) -> KickoffResult:
        """Kick off a jorb using personality-aware jorb session."""
        try:
            logger.info("Kicking off jorb %s: %s (personality: %s)", jorb.id, jorb.name, jorb.personality)

            # Create jorb session with personality (empty messages for new jorb)
            jorb_with_messages = JorbWithMessages(jorb=jorb, messages=[])
            jorb_session = create_jorb_session(
                jorb_with_messages,
                policy=self._policy.to_context_dict(),
            )

            # Get kickoff action from session
            session_response = await jorb_session.kickoff()

            logger.info(
                "Jorb session kickoff decided: action=%s, reasoning=%s",
                session_response.action.type,
                session_response.reasoning[:100] if session_response.reasoning else "",
            )

            # Update token metrics
            if session_response.tokens_used > 0:
                await self._storage.increment_metrics(
                    jorb.id,
                    tokens_used=session_response.tokens_used,
                    estimated_cost=session_response.estimated_cost,
                )

            # Execute the action
            message_sent = False
            action = session_response.action

            if action.type == "send_message":
                if action.channel and action.recipient and action.content:
                    send_success = await self._send_message(
                        action.channel,
                        action.recipient,
                        action.content,
                    )

                    if send_success:
                        await self.store_outbound_message(
                            jorb_id=jorb.id,
                            channel=action.channel,
                            recipient=action.recipient,
                            content=action.content,
                            reasoning=session_response.reasoning,
                        )
                        self._record_message_sent(jorb.id)
                        message_sent = True
                        logger.info("Kickoff message sent for jorb %s", jorb.id)
                    else:
                        logger.error("Failed to send kickoff message for jorb %s", jorb.id)
                else:
                    logger.warning("send_message action missing required fields for kickoff")

            elif action.type == "pause":
                await self.update_jorb_status(
                    jorb_id=jorb.id,
                    status="paused",
                    paused_reason=action.pause_reason,
                    needs_approval_for=action.needs_approval_for,
                )
                return KickoffResult(
                    jorb_id=jorb.id,
                    success=True,
                    action_taken="pause",
                    message_sent=False,
                )

            elif action.type == "script" and action.script:
                # Execute the kickoff script (e.g. frank.android.task_do(...))
                logger.info("Kickoff executing script for jorb %s", jorb.id)
                await self._execute_script(jorb, action.script)

                # Enter the main processing loop so the LLM can see the
                # script result and continue iterating (poll, interpret,
                # issue more scripts) until the task is done or paused.
                loop_result = await self.process_jorb_event(jorb)
                return KickoffResult(
                    jorb_id=jorb.id,
                    success=loop_result.success,
                    action_taken=f"script+{loop_result.action_taken}",
                    message_sent=loop_result.message_sent,
                )

            # Update jorb status to running
            update_fields: dict[str, Any] = {"status": "running"}
            if session_response.progress:
                if session_response.progress.note:
                    update_fields["progress_summary"] = session_response.progress.note
                if session_response.progress.awaiting:
                    update_fields["awaiting"] = session_response.progress.awaiting

            await self._storage.update_jorb(jorb.id, **update_fields)

            # Record progress
            if session_response.progress and session_response.progress.note:
                progress_log = get_progress_log()
                progress_log.add_entry(
                    entry_type="task_progress",
                    summary=f"Kickoff: {session_response.progress.note}",
                    jorb_id=jorb.id,
                    jorb_name=jorb.name,
                )

            return KickoffResult(
                jorb_id=jorb.id,
                success=True,
                action_taken=action.type,
                message_sent=message_sent,
            )

        except Exception as e:
            logger.exception("Error during jorb kickoff with session")
            return KickoffResult(
                jorb_id=jorb.id,
                success=False,
                action_taken="error",
                error=str(e),
            )

    async def _kickoff_legacy(self, jorb: Jorb) -> KickoffResult:
        """Legacy kickoff using single LLM call."""
        try:
            logger.info("Kicking off jorb %s: %s", jorb.id, jorb.name)

            # Build context for kickoff (no event, just the new jorb)
            # Include the jorb being kicked off as a JorbWithMessages with empty messages
            kickoff_jorb_with_messages = JorbWithMessages(jorb=jorb, messages=[])

            # Also get any other open jorbs for context
            other_open_jorbs = await self.get_open_jorbs()
            # Filter out the jorb being kicked off if it's already there
            other_open_jorbs = [j for j in other_open_jorbs if j.jorb.id != jorb.id]

            # Add the kickoff jorb to the list
            all_jorbs = [kickoff_jorb_with_messages] + other_open_jorbs

            context = self.build_context(
                event=None,
                open_jorbs=all_jorbs,
                event_type="jorb_created",
                kickoff_jorb=jorb,
            )

            # Call the LLM
            raw_response, tokens_used, estimated_cost = await self.call_agent(context)
            agent_response = self.parse_agent_response(raw_response, tokens_used, estimated_cost)

            logger.info(
                "Kickoff agent decided: action=%s, reasoning=%s",
                agent_response.action.type,
                agent_response.reasoning[:100] if agent_response.reasoning else "",
            )

            # Update token metrics for this jorb
            if tokens_used > 0:
                await self._storage.increment_metrics(
                    jorb.id,
                    tokens_used=tokens_used,
                    estimated_cost=estimated_cost,
                )

            # Execute the action
            message_sent = False
            action = agent_response.action

            if action.type == "send_message":
                if action.channel and action.recipient and action.content:
                    # Send the message (no rate limit check for initial kickoff)
                    send_success = await self._send_message(
                        action.channel,
                        action.recipient,
                        action.content,
                    )

                    if send_success:
                        # Store outbound message and record for rate limiting
                        await self.store_outbound_message(
                            jorb_id=jorb.id,
                            channel=action.channel,
                            recipient=action.recipient,
                            content=action.content,
                            reasoning=agent_response.reasoning,
                        )
                        self._record_message_sent(jorb.id)
                        message_sent = True
                        logger.info("Kickoff message sent for jorb %s", jorb.id)
                    else:
                        logger.error("Failed to send kickoff message for jorb %s", jorb.id)
                else:
                    logger.warning("send_message action missing required fields for kickoff")

            elif action.type == "no_action":
                # Agent decided no initial action is needed
                logger.info("Agent decided no initial action for jorb %s", jorb.id)

            elif action.type == "pause":
                # Agent decided to pause immediately (unusual but valid)
                await self.update_jorb_status(
                    jorb_id=jorb.id,
                    status="paused",
                    paused_reason=action.pause_reason,
                    needs_approval_for=action.needs_approval_for,
                )
                return KickoffResult(
                    jorb_id=jorb.id,
                    success=True,
                    action_taken="pause",
                    message_sent=False,
                )

            # Update jorb status to running (unless paused above)
            update_fields: dict[str, Any] = {"status": "running"}
            if agent_response.task_update:
                if agent_response.task_update.progress_note:
                    update_fields["progress_summary"] = agent_response.task_update.progress_note
                if agent_response.task_update.awaiting:
                    update_fields["awaiting"] = agent_response.task_update.awaiting

            await self._storage.update_jorb(jorb.id, **update_fields)

            return KickoffResult(
                jorb_id=jorb.id,
                success=True,
                action_taken=action.type,
                message_sent=message_sent,
            )

        except AgentRunnerError as e:
            logger.error("Agent runner error during kickoff: %s", e)
            return KickoffResult(
                jorb_id=jorb.id,
                success=False,
                action_taken="error",
                error=str(e),
            )
        except Exception as e:
            logger.exception("Unexpected error during jorb kickoff")
            return KickoffResult(
                jorb_id=jorb.id,
                success=False,
                action_taken="error",
                error=str(e),
            )


__all__ = [
    "AgentRunner",
    "AgentAction",
    "AgentResponse",
    "AgentRunnerError",
    "IncomingEvent",
    "JorbPolicy",
    "KickoffResult",
    "PolicyViolation",
    "ProcessingResult",
    "TaskUpdate",
    "AGENT_MODEL",
    "USE_SWITCHBOARD_MODE",
    "SCRIPT_EXECUTION_TIMEOUT",
    "MAX_ITERATIONS_PER_HOUR",
    "MAX_ITERATIONS_PER_DAY",
]
