"""
Tests for AndroidPhoneRunner service.

Tests the LLM-in-the-loop orchestration for phone automation.
"""

import sys
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/claudia/dev/frank_bot")

from services.android_phone_runner import (
    AndroidPhoneRunner,
    PhoneAction,
    RunResult,
    StepResult,
    _calculate_token_cost,
    _load_base_prompt,
    _load_task_prompt,
)


class TestTokenCostCalculation:
    """Tests for token cost calculation."""

    def test_basic_cost_calculation(self) -> None:
        """Calculates cost correctly for basic token counts."""
        cost = _calculate_token_cost(1000, 1000)
        # 1000 input @ $0.005/1K = $0.005
        # 1000 output @ $0.015/1K = $0.015
        # Total = $0.02
        assert cost == 0.02

    def test_zero_tokens(self) -> None:
        """Handles zero tokens."""
        cost = _calculate_token_cost(0, 0)
        assert cost == 0.0

    def test_large_token_counts(self) -> None:
        """Handles large token counts."""
        cost = _calculate_token_cost(10000, 5000)
        # 10000 input @ $0.005/1K = $0.05
        # 5000 output @ $0.015/1K = $0.075
        # Total = $0.125
        assert cost == 0.125


class TestPromptLoading:
    """Tests for prompt template loading."""

    def test_load_base_prompt_returns_string(self) -> None:
        """Base prompt loader returns a string."""
        prompt = _load_base_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain key instructions
        assert "Android" in prompt or "phone" in prompt.lower()

    def test_load_task_prompt_nonexistent(self) -> None:
        """Returns None for nonexistent task prompt."""
        result = _load_task_prompt("nonexistent-task-12345")
        assert result is None

    def test_load_task_prompt_thermostat_set_range(self) -> None:
        """Loads thermostat-setRange prompt."""
        result = _load_task_prompt("thermostat-setRange")
        assert result is not None
        assert "low_temp" in result
        assert "high_temp" in result
        assert "Google Home" in result

    def test_load_task_prompt_thermostat_get_status(self) -> None:
        """Loads thermostat-getStatus prompt."""
        result = _load_task_prompt("thermostat-getStatus")
        assert result is not None
        assert "current_temp" in result or "status" in result


class TestAndroidPhoneRunnerInit:
    """Tests for AndroidPhoneRunner initialization."""

    def test_default_initialization(self) -> None:
        """Initializes with default settings."""
        with patch("services.android_phone_runner.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_llm_model="gpt-5.2",
                android_llm_api_key="test-key",
                openai_api_key=None,
            )
            runner = AndroidPhoneRunner()
            assert runner.model == "gpt-5.2"
            assert runner.is_configured is True

    def test_custom_initialization(self) -> None:
        """Initializes with custom settings."""
        runner = AndroidPhoneRunner(
            model="claude-3-opus",
            api_key="custom-key",
            max_steps=10,
            step_delay=1.0,
        )
        assert runner.model == "claude-3-opus"
        assert runner.is_configured is True
        assert runner._max_steps == 10
        assert runner._step_delay == 1.0

    def test_not_configured_without_api_key(self) -> None:
        """Reports not configured when API key missing."""
        with patch("services.android_phone_runner.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_llm_model="gpt-5.2",
                android_llm_api_key=None,
                openai_api_key=None,
            )
            runner = AndroidPhoneRunner(api_key=None)
            assert runner.is_configured is False


class TestPhoneAction:
    """Tests for PhoneAction dataclass."""

    def test_tap_action(self) -> None:
        """Creates tap action correctly."""
        action = PhoneAction(
            action="tap",
            params={"x": 100, "y": 200},
            done=False,
            reasoning="Tapping button",
        )
        assert action.action == "tap"
        assert action.params["x"] == 100
        assert action.params["y"] == 200
        assert action.done is False

    def test_done_action(self) -> None:
        """Creates done action correctly."""
        action = PhoneAction(
            action="done",
            params={"result": "success"},
            done=True,
            reasoning="Task complete",
        )
        assert action.action == "done"
        assert action.done is True


class TestExecuteAction:
    """Tests for action execution."""

    @pytest.mark.asyncio
    async def test_execute_tap_action(self) -> None:
        """Executes tap action via client."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.tap = AsyncMock(return_value=MagicMock(success=True, error=None))

        action = PhoneAction(action="tap", params={"x": 100, "y": 200})

        with patch("services.android_client.get_android_client", return_value=mock_client):
            success, error = await runner._execute_action(action)

        assert success is True
        assert error is None
        mock_client.tap.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_execute_type_action(self) -> None:
        """Executes type action via client."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.type_text = AsyncMock(return_value=MagicMock(success=True, error=None))

        action = PhoneAction(action="type", params={"text": "hello"})

        with patch("services.android_client.get_android_client", return_value=mock_client):
            success, error = await runner._execute_action(action)

        assert success is True
        mock_client.type_text.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_execute_swipe_action(self) -> None:
        """Executes swipe action via client."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.swipe = AsyncMock(return_value=MagicMock(success=True, error=None))

        action = PhoneAction(action="swipe", params={"direction": "up"})

        with patch("services.android_client.get_android_client", return_value=mock_client):
            success, error = await runner._execute_action(action)

        assert success is True
        mock_client.swipe.assert_called_once_with("up")

    @pytest.mark.asyncio
    async def test_execute_press_key_action(self) -> None:
        """Executes press_key action via client."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.press_key = AsyncMock(return_value=MagicMock(success=True, error=None))

        action = PhoneAction(action="press_key", params={"key": "back"})

        with patch("services.android_client.get_android_client", return_value=mock_client):
            success, error = await runner._execute_action(action)

        assert success is True
        mock_client.press_key.assert_called_once_with("back")

    @pytest.mark.asyncio
    async def test_execute_wait_action(self) -> None:
        """Executes wait action."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        action = PhoneAction(action="wait", params={"seconds": 0.1})

        # wait doesn't need client mocking
        success, error = await runner._execute_action(action)

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_execute_done_action(self) -> None:
        """Done action succeeds without calling client."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        action = PhoneAction(action="done", params={}, done=True)

        # done doesn't need client mocking
        success, error = await runner._execute_action(action)

        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_execute_error_action(self) -> None:
        """Error action returns failure."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        action = PhoneAction(action="error", params={"message": "Something went wrong"})

        # error doesn't need client mocking
        success, error = await runner._execute_action(action)

        assert success is False
        assert "Something went wrong" in error

    @pytest.mark.asyncio
    async def test_execute_tap_missing_params(self) -> None:
        """Tap action fails with missing params."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()

        action = PhoneAction(action="tap", params={})  # Missing x, y

        with patch("services.android_client.get_android_client", return_value=mock_client):
            success, error = await runner._execute_action(action)

        assert success is False
        assert "x and y" in error.lower()


class TestRunTask:
    """Tests for the main run_task method."""

    @pytest.mark.asyncio
    async def test_returns_error_when_not_configured(self) -> None:
        """Returns error result when runner not configured."""
        with patch("services.android_phone_runner.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_llm_model="gpt-5.2",
                android_llm_api_key=None,
                openai_api_key=None,
            )
            runner = AndroidPhoneRunner(api_key=None)
            result = await runner.run_task("test task")

        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_completes_task_on_done_action(self) -> None:
        """Completes successfully when LLM returns done."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        # Mock screen capture
        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        # Mock LLM response
        done_action = PhoneAction(
            action="done",
            params={"result": "success"},
            done=True,
            reasoning="Task completed",
        )

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", return_value=(done_action, 100, 50)):
                result = await runner.run_task("test task")

        assert result.success is True
        assert result.final_action == "done"
        assert result.steps_taken == 1
        assert result.total_tokens_used == 150

    @pytest.mark.asyncio
    async def test_executes_multiple_steps(self) -> None:
        """Executes multiple steps before completing."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        # First call returns tap, second returns done
        tap_action = PhoneAction(action="tap", params={"x": 100, "y": 200})
        done_action = PhoneAction(action="done", params={}, done=True)

        llm_responses = [(tap_action, 100, 50), (done_action, 100, 50)]
        call_count = [0]

        async def mock_call_llm(*args, **kwargs):
            result = llm_responses[call_count[0]]
            call_count[0] += 1
            return result

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", side_effect=mock_call_llm):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task("test task")

        assert result.success is True
        assert result.steps_taken == 2
        assert result.total_tokens_used == 300

    @pytest.mark.asyncio
    async def test_stops_at_max_steps(self) -> None:
        """Stops and reports failure at max steps."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0, max_steps=3)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        # Always return tap (never done)
        tap_action = PhoneAction(action="tap", params={"x": 100, "y": 200})

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", return_value=(tap_action, 100, 50)):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task("test task")

        assert result.success is False
        assert result.steps_taken == 3
        assert "3 steps" in result.error

    @pytest.mark.asyncio
    async def test_loads_task_prompt_template(self) -> None:
        """Loads and uses task-specific prompt template."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        done_action = PhoneAction(action="done", params={}, done=True)

        captured_system_prompt = []

        async def capture_call_llm(system_prompt, *args, **kwargs):
            captured_system_prompt.append(system_prompt)
            return done_action, 100, 50

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", side_effect=capture_call_llm):
                # Use actual template name
                result = await runner.run_task(
                    "thermostat-setRange",
                    parameters={"low_temp": 68, "high_temp": 72},
                )

        assert result.success is True
        # Should have substituted parameters
        assert "68" in captured_system_prompt[0]
        assert "72" in captured_system_prompt[0]

    @pytest.mark.asyncio
    async def test_extracts_data_from_done_action(self) -> None:
        """Extracts data from done action params."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        done_action = PhoneAction(
            action="done",
            params={"current_temp": 72, "mode": "cooling"},
            done=True,
        )

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", return_value=(done_action, 100, 50)):
                result = await runner.run_task("test task")

        assert result.success is True
        assert result.extracted_data is not None
        assert result.extracted_data["current_temp"] == 72
        assert result.extracted_data["mode"] == "cooling"


class TestBuildUserMessage:
    """Tests for user message building."""

    def test_includes_task_description(self) -> None:
        """User message includes task description."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        screen_state = {
            "element_count": 5,
            "clickable_elements": [],
        }
        task_context = {
            "task_description": "Set thermostat to 72°F",
            "step_number": 1,
            "max_steps": 20,
            "parameters": {},
        }

        message = runner._build_user_message(screen_state, task_context)

        assert "Set thermostat to 72°F" in message
        assert "Step: 1 of 20" in message

    def test_includes_parameters(self) -> None:
        """User message includes task parameters."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        screen_state = {"element_count": 5, "clickable_elements": []}
        task_context = {
            "task_description": "test",
            "step_number": 1,
            "max_steps": 20,
            "parameters": {"low_temp": 68, "high_temp": 72},
        }

        message = runner._build_user_message(screen_state, task_context)

        assert "low_temp: 68" in message
        assert "high_temp: 72" in message

    def test_includes_clickable_elements(self) -> None:
        """User message includes clickable elements list."""
        runner = AndroidPhoneRunner(model="test", api_key="test")

        screen_state = {
            "element_count": 2,
            "clickable_elements": [
                {"text": "Submit", "center_x": 540, "center_y": 1200, "clickable": True},
                {"text": "Cancel", "center_x": 200, "center_y": 1200, "clickable": True},
            ],
        }
        task_context = {
            "task_description": "test",
            "step_number": 1,
            "max_steps": 20,
            "parameters": {},
        }

        message = runner._build_user_message(screen_state, task_context)

        assert "Submit" in message
        assert "540" in message
        assert "Cancel" in message


class TestThermostatIntegration:
    """Integration tests for thermostat workflow through AndroidPhoneRunner."""

    @pytest.mark.asyncio
    async def test_thermostat_set_range_executes_full_flow(self) -> None:
        """Verifies setRange flow: screen capture -> LLM call -> action -> completion."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        # Simulate a real flow with multiple steps
        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [
                {"text": "Thermostat", "center_x": 540, "center_y": 300, "clickable": True},
                {"text": "68°F", "center_x": 300, "center_y": 600, "clickable": True},
            ],
            "element_count": 2,
        }

        # LLM will: 1) tap thermostat, 2) tap low temp, 3) set value, 4) done
        tap_thermostat = PhoneAction(action="tap", params={"x": 540, "y": 300})
        tap_low = PhoneAction(action="tap", params={"x": 300, "y": 600})
        swipe_adjust = PhoneAction(action="swipe", params={"direction": "up"})
        done_action = PhoneAction(
            action="done",
            params={"final_low_temp": 68, "final_high_temp": 72},
            done=True,
        )

        llm_responses = [
            (tap_thermostat, 200, 50),
            (tap_low, 200, 50),
            (swipe_adjust, 200, 50),
            (done_action, 200, 100),
        ]
        call_idx = [0]

        async def mock_call_llm(*args, **kwargs):
            result = llm_responses[call_idx[0]]
            call_idx[0] += 1
            return result

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", side_effect=mock_call_llm):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task(
                        "thermostat-setRange",
                        parameters={"low_temp": 68, "high_temp": 72},
                        max_steps=20,
                    )

        assert result.success is True
        assert result.steps_taken == 4
        # Total tokens = (200+50)*4 + extra 50 for done action output = 1050
        # Each step: 200 input + 50 output = 250 * 4 = 1000, plus done action has extra 50 = 1050
        assert result.total_tokens_used == 1050
        assert result.extracted_data["final_low_temp"] == 68
        assert result.extracted_data["final_high_temp"] == 72

    @pytest.mark.asyncio
    async def test_thermostat_get_status_extracts_all_fields(self) -> None:
        """Verifies getStatus flow extracts all thermostat status fields."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [
                {"text": "72°F", "center_x": 540, "center_y": 400, "clickable": False},
                {"text": "Heat & Cool", "center_x": 540, "center_y": 500, "clickable": True},
            ],
            "element_count": 2,
        }

        # Two steps: navigate to thermostat, then read status
        tap_thermostat = PhoneAction(action="tap", params={"x": 540, "y": 200})
        done_action = PhoneAction(
            action="done",
            params={
                "current_temp": 72,
                "target_low": 68,
                "target_high": 74,
                "mode": "heat_cool",
                "humidity": 45,
                "status": "idle",
            },
            done=True,
        )

        llm_responses = [
            (tap_thermostat, 300, 100),
            (done_action, 300, 150),
        ]
        call_idx = [0]

        async def mock_call_llm(*args, **kwargs):
            result = llm_responses[call_idx[0]]
            call_idx[0] += 1
            return result

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", side_effect=mock_call_llm):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task(
                        "thermostat-getStatus",
                        parameters={},
                        max_steps=15,
                    )

        assert result.success is True
        assert result.steps_taken == 2
        assert result.extracted_data["current_temp"] == 72
        assert result.extracted_data["target_low"] == 68
        assert result.extracted_data["target_high"] == 74
        assert result.extracted_data["mode"] == "heat_cool"
        assert result.extracted_data["humidity"] == 45
        assert result.extracted_data["status"] == "idle"

    @pytest.mark.asyncio
    async def test_llm_loop_respects_max_steps(self) -> None:
        """Verifies runner stops at max_steps and reports failure."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        # LLM keeps tapping forever (never returns done)
        tap_action = PhoneAction(action="tap", params={"x": 100, "y": 100})

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", return_value=(tap_action, 100, 50)):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task(
                        "thermostat-setRange",
                        parameters={"low_temp": 68, "high_temp": 72},
                        max_steps=5,
                    )

        assert result.success is False
        assert result.steps_taken == 5
        assert "5 steps" in result.error

    @pytest.mark.asyncio
    async def test_error_handling_when_device_disconnected_mid_task(self) -> None:
        """Verifies runner records device disconnection errors in step results."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        tap_action = PhoneAction(action="tap", params={"x": 100, "y": 100})

        # First action succeeds, rest fail due to disconnection
        execute_responses = [(True, None), (False, "device offline: no devices found")]
        exec_idx = [0]

        async def mock_execute(*args, **kwargs):
            result = execute_responses[min(exec_idx[0], len(execute_responses) - 1)]
            exec_idx[0] += 1
            return result

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", return_value=(tap_action, 100, 50)):
                with patch.object(runner, "_execute_action", side_effect=mock_execute):
                    result = await runner.run_task(
                        "thermostat-setRange",
                        parameters={"low_temp": 68, "high_temp": 72},
                        max_steps=10,
                    )

        # Runner doesn't abort on action failure - it keeps trying and records errors
        assert result.success is False
        # Verify that step errors were recorded
        failed_steps = [s for s in result.steps if s.error is not None]
        assert len(failed_steps) > 0
        # At least one step should have the device offline error
        assert any("device offline" in s.error.lower() for s in failed_steps)

    @pytest.mark.asyncio
    async def test_token_tracking_accumulates_correctly_across_steps(self) -> None:
        """Verifies token usage accumulates correctly across multiple steps."""
        runner = AndroidPhoneRunner(model="test", api_key="test", step_delay=0)

        mock_screen = {
            "screenshot_base64": "abc123",
            "xml": "<hierarchy/>",
            "clickable_elements": [],
            "element_count": 0,
        }

        # Three steps with specific token counts
        step1 = PhoneAction(action="tap", params={"x": 100, "y": 100})
        step2 = PhoneAction(action="swipe", params={"direction": "up"})
        step3 = PhoneAction(action="done", params={}, done=True)

        # Input/output tokens: (500, 100), (600, 150), (700, 200)
        llm_responses = [
            (step1, 500, 100),
            (step2, 600, 150),
            (step3, 700, 200),
        ]
        call_idx = [0]

        async def mock_call_llm(*args, **kwargs):
            result = llm_responses[call_idx[0]]
            call_idx[0] += 1
            return result

        with patch.object(runner, "_capture_screen_state", return_value=mock_screen):
            with patch.object(runner, "_call_llm", side_effect=mock_call_llm):
                with patch.object(runner, "_execute_action", return_value=(True, None)):
                    result = await runner.run_task("test task", max_steps=10)

        # Total tokens = 500+100 + 600+150 + 700+200 = 2250
        assert result.total_tokens_used == 2250
        assert result.steps_taken == 3

        # Cost calculation: (1800 input @ $0.005/1K) + (450 output @ $0.015/1K)
        # = $0.009 + $0.00675 = $0.01575
        expected_cost = (1800 * 0.005 / 1000) + (450 * 0.015 / 1000)
        assert abs(result.total_cost - expected_cost) < 0.0001
