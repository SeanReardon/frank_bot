"""
Android Phone Runner Service for LLM-in-the-loop phone automation.

Orchestrates multi-step phone control tasks by:
1. Capturing screen state (XML + screenshot)
2. Sending state to LLM for action decision
3. Executing the decided action via AndroidClient
4. Repeating until task complete or max steps reached
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from config import get_settings
from services.android_audit import get_android_audit_logger

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_MAX_STEPS = 20
DEFAULT_STEP_DELAY = 0.5  # seconds between steps

# Token pricing (USD per 1K tokens) - approximations for vision models
# These should be updated based on actual pricing
TOKEN_PRICE_INPUT = 0.005  # $0.005 per 1K input tokens (vision is cheaper)
TOKEN_PRICE_OUTPUT = 0.015  # $0.015 per 1K output tokens


def _calculate_token_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD from token counts."""
    input_cost = (input_tokens / 1000) * TOKEN_PRICE_INPUT
    output_cost = (output_tokens / 1000) * TOKEN_PRICE_OUTPUT
    return round(input_cost + output_cost, 6)


# Action types the LLM can decide
ActionType = Literal["tap", "type", "swipe", "press_key", "wait", "done", "error"]


@dataclass
class PhoneAction:
    """An action decided by the LLM for phone control."""

    action: ActionType
    params: dict[str, Any] = field(default_factory=dict)
    done: bool = False
    reasoning: str = ""


@dataclass
class StepResult:
    """Result of a single step in the automation loop."""

    step_number: int
    action: PhoneAction
    success: bool
    error: str | None = None
    screenshot_base64: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: float = 0


@dataclass
class RunResult:
    """Result of a complete automation run."""

    success: bool
    final_action: str
    steps_taken: int
    total_tokens_used: int
    total_cost: float
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None
    final_screenshot_base64: str | None = None
    extracted_data: dict[str, Any] | None = None


def _load_base_prompt() -> str:
    """Load the base prompt template for phone control."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "androidPhone",
        "_base.md",
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Base prompt not found at %s, using minimal prompt", prompt_path)
        return """You are controlling an Android phone via accessibility commands.
Analyze the screen state and decide the next action to complete the task.
Respond with JSON: {"action": "tap|type|swipe|press_key|wait|done|error", "params": {}, "done": boolean, "reasoning": "..."}
"""


def _load_task_prompt(task_name: str) -> str | None:
    """Load a task-specific prompt template."""
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "androidPhone",
        f"{task_name}.md",
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.debug("Task prompt not found at %s", prompt_path)
        return None


class AndroidPhoneRunner:
    """
    Orchestrator for LLM-in-the-loop Android phone control.

    Implements the control loop:
    1. Capture screen state (screenshot + accessibility XML)
    2. Send to LLM with task prompt
    3. Execute returned action
    4. Repeat until done or max_steps reached
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        step_delay: float = DEFAULT_STEP_DELAY,
    ):
        """
        Initialize the phone runner.

        Args:
            model: LLM model to use. Defaults to ANDROID_LLM_MODEL setting.
            api_key: API key for LLM. Defaults to ANDROID_LLM_API_KEY setting.
            max_steps: Maximum steps before stopping.
            step_delay: Delay between steps in seconds.
        """
        settings = get_settings()
        self._model = model or settings.android_llm_model
        self._api_key = api_key or settings.android_llm_api_key or settings.openai_api_key
        self._max_steps = max_steps
        self._step_delay = step_delay
        self._base_prompt = _load_base_prompt()

    @property
    def is_configured(self) -> bool:
        """Check if the runner has required configuration."""
        return bool(self._api_key and self._model)

    @property
    def model(self) -> str:
        """Return the configured model."""
        return self._model

    async def _capture_screen_state(self) -> dict[str, Any]:
        """
        Capture the current screen state.

        Returns:
            Dict with screenshot_base64, xml, and clickable_elements
        """
        from actions.android_phone import get_screen_action

        return await get_screen_action({})

    async def _execute_action(self, action: PhoneAction) -> tuple[bool, str | None]:
        """
        Execute a phone action via AndroidClient.

        Args:
            action: The action to execute

        Returns:
            Tuple of (success, error_message)
        """
        from services.android_client import get_android_client

        client = get_android_client()
        await client.connect()

        try:
            if action.action == "tap":
                x = action.params.get("x")
                y = action.params.get("y")
                if x is None or y is None:
                    return False, "tap requires x and y parameters"
                result = await client.tap(int(x), int(y))
                return result.success, result.error

            elif action.action == "type":
                text = action.params.get("text", "")
                if not text:
                    return False, "type requires text parameter"
                result = await client.type_text(text)
                return result.success, result.error

            elif action.action == "swipe":
                direction = action.params.get("direction", "up")
                result = await client.swipe(direction)
                return result.success, result.error

            elif action.action == "press_key":
                key = action.params.get("key", "")
                if not key:
                    return False, "press_key requires key parameter"
                result = await client.press_key(key)
                return result.success, result.error

            elif action.action == "wait":
                seconds = action.params.get("seconds", 1)
                await asyncio.sleep(float(seconds))
                return True, None

            elif action.action == "done":
                # No action needed, task complete
                return True, None

            elif action.action == "error":
                # LLM indicated an error condition
                error_msg = action.params.get("message", "Unknown error from LLM")
                return False, error_msg

            else:
                return False, f"Unknown action: {action.action}"

        except Exception as e:
            logger.exception("Error executing action %s", action.action)
            return False, str(e)

    async def _call_llm(
        self,
        system_prompt: str,
        screen_state: dict[str, Any],
        task_context: dict[str, Any],
    ) -> tuple[PhoneAction, int, int]:
        """
        Call the LLM for action decision.

        Args:
            system_prompt: Combined base + task prompt
            screen_state: Current screen state with screenshot
            task_context: Task parameters and step info

        Returns:
            Tuple of (PhoneAction, input_tokens, output_tokens)
        """
        if not self._api_key:
            raise ValueError("LLM API key not configured")

        # Build the message content
        # For vision models, we include the screenshot as an image
        user_content: list[dict[str, Any]] = []

        # Add screenshot as image if present
        screenshot_b64 = screen_state.get("screenshot_base64")
        if screenshot_b64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{screenshot_b64}",
                    # Prefer low detail by default to reduce vision token burn.
                    # If we need a higher-fidelity pass later, we'll add a handshake.
                    "detail": "low",
                },
            })

        # Build text content with screen state and task info
        text_content = self._build_user_message(screen_state, task_context)
        user_content.append({
            "type": "text",
            "text": text_content,
        })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Determine which API to use based on model name
        if self._model.startswith("claude"):
            return await self._call_anthropic(messages)
        else:
            return await self._call_openai(messages)

    def _build_user_message(
        self,
        screen_state: dict[str, Any],
        task_context: dict[str, Any],
    ) -> str:
        """Build the user message text from screen state and task context."""
        parts = []

        # Task context
        parts.append("## Task Context")
        parts.append(f"Task: {task_context.get('task_description', 'Unknown task')}")
        parts.append(f"Step: {task_context.get('step_number', 1)} of {task_context.get('max_steps', self._max_steps)}")

        if task_context.get("parameters"):
            parts.append("\n### Parameters")
            for key, value in task_context["parameters"].items():
                parts.append(f"- {key}: {value}")

        # Screen state
        parts.append("\n## Screen State")
        parts.append(f"Total elements on screen: {screen_state.get('element_count', 0)}")
        dominant_package = screen_state.get("dominant_package")
        if dominant_package:
            parts.append(f"Dominant package on screen: {dominant_package}")

        # Clickable elements summary
        elements = screen_state.get("clickable_elements", [])
        if elements:
            labeled = []
            unlabeled_clickable = []
            for el in elements:
                text = (el.get("text", "") or el.get("content_desc", "") or "").strip()
                if text:
                    labeled.append(el)
                elif el.get("clickable"):
                    unlabeled_clickable.append(el)

            parts.append(f"\n### Interactive Elements ({len(elements)} total)")
            if labeled:
                parts.append("Labeled elements (up to 25):")
                for i, el in enumerate(labeled[:25]):
                    text = (el.get("text", "") or el.get("content_desc", "") or "").strip()
                    resource = (el.get("resource_id", "") or "").strip()
                    x, y = el.get("center_x", 0), el.get("center_y", 0)
                    clickable = "clickable" if el.get("clickable") else "text-only"
                    label = f" [{i}] \"{text}\" at ({x}, {y}) - {clickable}"
                    if resource:
                        label += f" (id={resource})"
                    parts.append(label)

            # Google Home (and many apps) rely heavily on icon buttons with no text.
            # Include a small set so the model can still act deterministically.
            if unlabeled_clickable:
                parts.append("\nUnlabeled clickable elements (up to 10):")
                for i, el in enumerate(unlabeled_clickable[:10]):
                    resource = (el.get("resource_id", "") or "").strip() or "unknown"
                    cls = (el.get("class_name", "") or "").strip() or "unknown"
                    x, y = el.get("center_x", 0), el.get("center_y", 0)
                    b = el.get("bounds") or {}
                    bounds_str = ""
                    if isinstance(b, dict) and all(k in b for k in ("left", "top", "right", "bottom")):
                        bounds_str = f" bounds=({b.get('left')},{b.get('top')})-({b.get('right')},{b.get('bottom')})"
                    parts.append(f"  [u{i}] id={resource} class={cls} at ({x}, {y}){bounds_str}")

        # Raw XML snippet (truncated for context efficiency)
        xml = screen_state.get("xml", "")
        if xml and len(xml) > 4000:
            parts.append("\n### XML (truncated)")
            parts.append(xml[:4000] + "\n... [truncated]")
        elif xml:
            parts.append("\n### XML")
            parts.append(xml)

        parts.append("\n## Your Response")
        parts.append("Respond with a JSON object containing:")
        parts.append("- action: tap|type|swipe|press_key|wait|done|error")
        parts.append("- params: {x, y} for tap, {text} for type, {direction} for swipe, etc.")
        parts.append("- done: true if the task is complete")
        parts.append("- reasoning: your thought process")

        return "\n".join(parts)

    async def _call_openai(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[PhoneAction, int, int]:
        """Call OpenAI API for action decision."""
        try:
            import openai
        except ImportError:
            raise ValueError("openai package not installed")

        client = openai.OpenAI(api_key=self._api_key)

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more deterministic actions
                max_completion_tokens=1000,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")

            # Parse response
            data = json.loads(content)

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            return PhoneAction(
                action=data.get("action", "error"),
                params=data.get("params", {}),
                done=data.get("done", False),
                reasoning=data.get("reasoning", ""),
            ), input_tokens, output_tokens

        except openai.APIError as e:
            logger.error("OpenAI API error: %s", e)
            raise ValueError(f"OpenAI API error: {e}")
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON: %s", e)
            raise ValueError(f"Invalid JSON from LLM: {e}")

    async def _call_anthropic(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[PhoneAction, int, int]:
        """Call Anthropic API for action decision."""
        try:
            import anthropic
        except ImportError:
            raise ValueError("anthropic package not installed")

        client = anthropic.Anthropic(api_key=self._api_key)

        # Convert OpenAI format to Anthropic format
        system = ""
        converted_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                # Handle multimodal content
                content = msg["content"]
                if isinstance(content, list):
                    anthropic_content = []
                    for item in content:
                        if item["type"] == "text":
                            anthropic_content.append({
                                "type": "text",
                                "text": item["text"],
                            })
                        elif item["type"] == "image_url":
                            # Extract base64 from data URL
                            url = item["image_url"]["url"]
                            if url.startswith("data:image/png;base64,"):
                                b64_data = url.replace("data:image/png;base64,", "")
                                anthropic_content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": b64_data,
                                    },
                                })
                    content = anthropic_content
                converted_messages.append({
                    "role": msg["role"],
                    "content": content,
                })

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=1000,
                system=system,
                messages=converted_messages,
                temperature=0.3,
            )

            # Extract text from response
            content = ""
            for block in response.content:
                if block.type == "text":
                    content = block.text
                    break

            if not content:
                raise ValueError("Empty response from LLM")

            # Parse JSON from response
            # Handle case where LLM wraps in markdown code block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            return PhoneAction(
                action=data.get("action", "error"),
                params=data.get("params", {}),
                done=data.get("done", False),
                reasoning=data.get("reasoning", ""),
            ), input_tokens, output_tokens

        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            raise ValueError(f"Anthropic API error: {e}")
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON: %s", e)
            raise ValueError(f"Invalid JSON from LLM: {e}")

    async def run_task(
        self,
        task_prompt: str,
        parameters: dict[str, Any] | None = None,
        max_steps: int | None = None,
    ) -> RunResult:
        """
        Run an automation task on the phone.

        This is the main entry point for phone automation. It:
        1. Loads the base prompt and combines with task prompt
        2. Runs the capture -> LLM -> execute loop
        3. Returns comprehensive result with all steps

        Args:
            task_prompt: The task-specific prompt or prompt template name
            parameters: Parameters to pass to the task (e.g., temperatures)
            max_steps: Override max steps for this run

        Returns:
            RunResult with success status, steps taken, and token usage
        """
        if not self.is_configured:
            return RunResult(
                success=False,
                final_action="error",
                steps_taken=0,
                total_tokens_used=0,
                total_cost=0.0,
                error="AndroidPhoneRunner not configured (missing API key or model)",
            )

        effective_max_steps = max_steps or self._max_steps
        params = parameters or {}

        # Check if task_prompt is a template name or actual prompt
        task_template = _load_task_prompt(task_prompt)
        if task_template:
            # Use loaded template
            full_task_prompt = task_template
            # Substitute any parameters in template
            for key, value in params.items():
                full_task_prompt = full_task_prompt.replace(f"{{{key}}}", str(value))
                full_task_prompt = full_task_prompt.replace(f"{{{{ {key} }}}}", str(value))
                full_task_prompt = full_task_prompt.replace(f"{{{{{key}}}}}", str(value))
        else:
            # Use task_prompt as-is
            full_task_prompt = task_prompt

        # Combine base prompt with task prompt
        system_prompt = f"{self._base_prompt}\n\n# Current Task\n\n{full_task_prompt}"

        steps: list[StepResult] = []
        total_input_tokens = 0
        total_output_tokens = 0
        final_screenshot: str | None = None
        extracted_data: dict[str, Any] | None = None

        logger.info(
            "Starting phone automation task with max_steps=%d, model=%s",
            effective_max_steps,
            self._model,
        )

        audit_logger = None
        try:
            audit_logger = get_android_audit_logger()
        except Exception:
            audit_logger = None

        for step_num in range(1, effective_max_steps + 1):
            start_time = time.time()

            try:
                # Step 1: Capture screen state
                logger.debug("Step %d: Capturing screen state", step_num)
                screen_state = await self._capture_screen_state()
                final_screenshot = screen_state.get("screenshot_base64")

                # Step 2: Build task context
                task_context = {
                    "task_description": task_prompt,
                    "parameters": params,
                    "step_number": step_num,
                    "max_steps": effective_max_steps,
                }

                # Step 3: Call LLM for decision
                logger.debug("Step %d: Calling LLM for action decision", step_num)
                action, input_tokens, output_tokens = await self._call_llm(
                    system_prompt,
                    screen_state,
                    task_context,
                )

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

                elapsed_ms = (time.time() - start_time) * 1000

                logger.info(
                    "Step %d: LLM decided action=%s, done=%s, reasoning=%s",
                    step_num,
                    action.action,
                    action.done,
                    action.reasoning[:100] if action.reasoning else "",
                )

                # Audit the decision + screen metadata (no raw screenshot/xml persisted).
                if audit_logger is not None:
                    try:
                        audit_logger.log_action(
                            action="runner_step",
                            parameters={
                                "task": task_prompt,
                                "step": step_num,
                                "action": action.action,
                                "done": action.done,
                                "params": action.params,
                            },
                            result={
                                "screenshot_base64": final_screenshot or "",
                                "element_count": screen_state.get("element_count"),
                            },
                            success=True,
                            tokens_used=input_tokens + output_tokens,
                            duration_ms=int(elapsed_ms),
                            api_key=self._api_key,
                        )
                    except Exception:
                        pass

                # Step 4: Execute action
                if action.action != "done":
                    success, error = await self._execute_action(action)
                else:
                    success = True
                    error = None
                    # Extract any data from the final action params
                    if action.params:
                        extracted_data = action.params

                step_result = StepResult(
                    step_number=step_num,
                    action=action,
                    success=success,
                    error=error,
                    screenshot_base64=final_screenshot,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    elapsed_ms=elapsed_ms,
                )
                steps.append(step_result)

                # Step 5: Check if done
                if action.done:
                    logger.info("Task completed at step %d", step_num)
                    total_tokens = total_input_tokens + total_output_tokens
                    total_cost = _calculate_token_cost(total_input_tokens, total_output_tokens)

                    if audit_logger is not None:
                        try:
                            audit_logger.log_action(
                                action="runner_complete",
                                parameters={"task": task_prompt},
                                result={
                                    "element_count": screen_state.get("element_count"),
                                },
                                success=True,
                                tokens_used=total_tokens,
                                duration_ms=int((time.time() - start_time) * 1000),
                                api_key=self._api_key,
                            )
                        except Exception:
                            pass

                    return RunResult(
                        success=True,
                        final_action=action.action,
                        steps_taken=step_num,
                        total_tokens_used=total_tokens,
                        total_cost=total_cost,
                        steps=steps,
                        final_screenshot_base64=final_screenshot,
                        extracted_data=extracted_data,
                    )

                # Step 6: Check for execution error
                if not success:
                    logger.warning("Step %d action failed: %s", step_num, error)
                    # Don't fail immediately - let LLM see the error and decide
                    if audit_logger is not None:
                        try:
                            audit_logger.log_action(
                                action="runner_action_failed",
                                parameters={
                                    "task": task_prompt,
                                    "step": step_num,
                                    "action": action.action,
                                    "params": action.params,
                                },
                                success=False,
                                error=error,
                                tokens_used=input_tokens + output_tokens,
                                duration_ms=int(elapsed_ms),
                                api_key=self._api_key,
                            )
                        except Exception:
                            pass

                # Add delay between steps to allow UI to settle
                if self._step_delay > 0:
                    await asyncio.sleep(self._step_delay)

            except Exception as e:
                logger.exception("Error at step %d", step_num)
                elapsed_ms = (time.time() - start_time) * 1000
                step_result = StepResult(
                    step_number=step_num,
                    action=PhoneAction(action="error", reasoning=str(e)),
                    success=False,
                    error=str(e),
                    elapsed_ms=elapsed_ms,
                )
                steps.append(step_result)

                total_tokens = total_input_tokens + total_output_tokens
                total_cost = _calculate_token_cost(total_input_tokens, total_output_tokens)

                if audit_logger is not None:
                    try:
                        audit_logger.log_action(
                            action="runner_exception",
                            parameters={"task": task_prompt, "step": step_num},
                            success=False,
                            error=str(e),
                            tokens_used=total_tokens,
                            duration_ms=int(elapsed_ms),
                            api_key=self._api_key,
                        )
                    except Exception:
                        pass

                return RunResult(
                    success=False,
                    final_action="error",
                    steps_taken=step_num,
                    total_tokens_used=total_tokens,
                    total_cost=total_cost,
                    steps=steps,
                    error=str(e),
                    final_screenshot_base64=final_screenshot,
                )

        # Reached max steps without completion
        logger.warning("Task did not complete within %d steps", effective_max_steps)
        total_tokens = total_input_tokens + total_output_tokens
        total_cost = _calculate_token_cost(total_input_tokens, total_output_tokens)

        if audit_logger is not None:
            try:
                audit_logger.log_action(
                    action="runner_max_steps",
                    parameters={"task": task_prompt, "max_steps": effective_max_steps},
                    success=False,
                    error=f"Task did not complete within {effective_max_steps} steps",
                    tokens_used=total_tokens,
                    api_key=self._api_key,
                )
            except Exception:
                pass

        return RunResult(
            success=False,
            final_action="max_steps_reached",
            steps_taken=effective_max_steps,
            total_tokens_used=total_tokens,
            total_cost=total_cost,
            steps=steps,
            error=f"Task did not complete within {effective_max_steps} steps",
            final_screenshot_base64=final_screenshot,
        )


# Module-level singleton
_runner: AndroidPhoneRunner | None = None


def get_android_phone_runner() -> AndroidPhoneRunner:
    """Get the singleton AndroidPhoneRunner instance."""
    global _runner
    if _runner is None:
        _runner = AndroidPhoneRunner()
    return _runner


__all__ = [
    "AndroidPhoneRunner",
    "PhoneAction",
    "RunResult",
    "StepResult",
    "get_android_phone_runner",
]
