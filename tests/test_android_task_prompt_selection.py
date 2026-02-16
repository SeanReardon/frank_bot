"""
Tests for Android task prompt selection in actions.android_phone.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_background_android_task_uses_thermostat_prompt_for_thermostat_goal() -> None:
    from services.android_phone_runner import RunResult
    from services.android_client import ADBResult
    from services.android_task_storage import AndroidTaskStorage

    storage = AndroidTaskStorage()
    task = await storage.create_task(
        goal="Check my home's temp settings in Google Home",
        app="google_home",
    )

    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
    mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
    mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

    mock_runner = MagicMock()
    mock_runner.is_configured = True
    mock_runner.run_task = AsyncMock(return_value=RunResult(
        success=True,
        final_action="done",
        steps_taken=3,
        total_tokens_used=1000,
        total_cost=0.02,
        extracted_data={
            "current_temp": 72,
            "target_low": 68,
            "target_high": 74,
            "mode": "heat_cool",
            "humidity": 45,
            "status": "idle",
        },
        steps=[],
    ))

    with patch("actions.android_phone.get_android_client", return_value=mock_client), patch(
        "services.android_phone_runner.get_android_phone_runner",
        return_value=mock_runner,
    ), patch(
        "services.android_task_storage.get_android_task_storage",
        return_value=storage,
    ), patch(
        "actions.android_phone.asyncio.sleep",
        new=AsyncMock(),
    ):
        from actions.android_phone import _execute_task_background

        await _execute_task_background(task.id, task.goal, task.app)

    mock_runner.run_task.assert_called_once()
    _, kwargs = mock_runner.run_task.call_args
    assert kwargs["task_prompt"] == "thermostat-getStatus"
    assert kwargs["parameters"] == {}

    updated = await storage.get_task(task.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.result
    assert updated.result["success"] is True
    assert updated.result["extracted_data"]["current_temp"] == 72


@pytest.mark.asyncio
async def test_background_android_task_uses_generic_prompt_for_non_thermostat_goal() -> None:
    from services.android_phone_runner import RunResult
    from services.android_client import ADBResult
    from services.android_task_storage import AndroidTaskStorage

    goal = "Open Uber and check ride prices to the airport"
    storage = AndroidTaskStorage()
    task = await storage.create_task(goal=goal, app="uber")

    mock_client = MagicMock()
    mock_client.connect = AsyncMock(return_value=ADBResult(success=True, output="connected"))
    mock_client.wake_device = AsyncMock(return_value=ADBResult(success=True, output="awake"))
    mock_client.launch_app = AsyncMock(return_value=ADBResult(success=True, output="launched"))

    mock_runner = MagicMock()
    mock_runner.is_configured = True
    mock_runner.run_task = AsyncMock(return_value=RunResult(
        success=True,
        final_action="done",
        steps_taken=1,
        total_tokens_used=500,
        total_cost=0.01,
        extracted_data={"result": "Checked prices", "extracted_data": {"prices": []}},
        steps=[],
    ))

    with patch("actions.android_phone.get_android_client", return_value=mock_client), patch(
        "services.android_phone_runner.get_android_phone_runner",
        return_value=mock_runner,
    ), patch(
        "services.android_task_storage.get_android_task_storage",
        return_value=storage,
    ), patch(
        "actions.android_phone.asyncio.sleep",
        new=AsyncMock(),
    ):
        from actions.android_phone import _execute_task_background

        await _execute_task_background(task.id, task.goal, task.app)

    mock_runner.run_task.assert_called_once()
    _, kwargs = mock_runner.run_task.call_args
    assert kwargs["task_prompt"] == "_generic"
    assert kwargs["parameters"] == {"GOAL": goal}

