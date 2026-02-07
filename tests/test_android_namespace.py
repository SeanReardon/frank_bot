"""
Unit tests for AndroidNamespace in meta/api.py.

These tests verify that the namespace methods correctly wrap the underlying
async action handlers with synchronous calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import AndroidNamespace, FrankAPI


class TestAndroidNamespaceTaskDo:
    """Tests for AndroidNamespace.task_do()."""

    def test_task_do_creates_task(self) -> None:
        """Task_do method creates a new Android task."""
        mock_result = {
            "task_id": "task-abc123",
            "status": "pending",
            "goal": "Check thermostat temperature",
            "app": "google_home",
            "message": "Task started. Check status with androidPhoneTaskGet(task_id='task-abc123')",
        }

        with patch(
            "actions.android_phone.task_do_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = AndroidNamespace()
            result = namespace.task_do("Check thermostat temperature", app="google_home")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["goal"] == "Check thermostat temperature"
            assert call_args["app"] == "google_home"

            assert result == mock_result
            assert result["task_id"] == "task-abc123"
            assert result["status"] == "pending"

    def test_task_do_auto_detects_app(self) -> None:
        """Task_do method auto-detects app from goal if not provided."""
        mock_result = {
            "task_id": "task-def456",
            "status": "pending",
            "goal": "Check Uber prices to airport",
            "app": "uber",
            "message": "Task started.",
        }

        with patch(
            "actions.android_phone.task_do_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = AndroidNamespace()
            result = namespace.task_do("Check Uber prices to airport")

            call_args = mock_action.call_args[0][0]
            assert call_args["goal"] == "Check Uber prices to airport"
            assert "app" in call_args
            assert result["task_id"] == "task-def456"


class TestAndroidNamespaceTaskGet:
    """Tests for AndroidNamespace.task_get()."""

    def test_task_get_returns_task_status(self) -> None:
        """Task_get method retrieves task status and results."""
        mock_result = {
            "id": "task-abc123",
            "status": "completed",
            "goal": "Check thermostat temperature",
            "app": "google_home",
            "result": {
                "success": True,
                "result": "Current temperature is 72°F",
            },
            "steps_taken": 5,
            "tokens_used": 8500,
            "estimated_cost": 0.05,
        }

        with patch(
            "actions.android_phone.task_get_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = AndroidNamespace()
            result = namespace.task_get("task-abc123")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["task_id"] == "task-abc123"

            assert result == mock_result
            assert result["status"] == "completed"
            assert result["result"]["success"] is True


class TestAndroidNamespaceTaskCancel:
    """Tests for AndroidNamespace.task_cancel()."""

    def test_task_cancel_cancels_running_task(self) -> None:
        """Task_cancel method cancels a running task."""
        mock_result = {
            "message": "Task cancelled",
            "id": "task-abc123",
            "status": "cancelled",
            "goal": "Check thermostat temperature",
            "app": "google_home",
        }

        with patch(
            "actions.android_phone.task_cancel_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = AndroidNamespace()
            result = namespace.task_cancel("task-abc123")

            mock_action.assert_called_once()
            call_args = mock_action.call_args[0][0]
            assert call_args["task_id"] == "task-abc123"

            assert result == mock_result
            assert result["status"] == "cancelled"
            assert result["message"] == "Task cancelled"

    def test_task_cancel_already_completed_task(self) -> None:
        """Task_cancel handles already completed tasks."""
        mock_result = {
            "message": "Task already completed, cannot cancel",
            "id": "task-def456",
            "status": "completed",
            "goal": "Check Uber prices",
            "app": "uber",
        }

        with patch(
            "actions.android_phone.task_cancel_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            namespace = AndroidNamespace()
            result = namespace.task_cancel("task-def456")

            assert result["status"] == "completed"
            assert "cannot cancel" in result["message"]


class TestFrankAPIAndroidIntegration:
    """Tests for FrankAPI.android namespace access."""

    def test_frank_api_has_android_namespace(self) -> None:
        """FrankAPI provides access to AndroidNamespace via property."""
        api = FrankAPI()
        assert hasattr(api, "android")
        assert isinstance(api.android, AndroidNamespace)

    def test_frank_api_android_is_same_instance(self) -> None:
        """FrankAPI returns the same AndroidNamespace instance."""
        api = FrankAPI()
        assert api.android is api.android

    def test_frank_api_android_task_do_works(self) -> None:
        """FrankAPI.android.task_do() works correctly."""
        mock_result = {
            "task_id": "task-xyz789",
            "status": "pending",
            "goal": "Turn off living room lights",
            "app": "google_home",
            "message": "Task started.",
        }

        with patch(
            "actions.android_phone.task_do_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.android.task_do("Turn off living room lights", app="google_home")

            assert result == mock_result
            assert result["task_id"] == "task-xyz789"
            mock_action.assert_called_once()

    def test_frank_api_android_task_get_works(self) -> None:
        """FrankAPI.android.task_get() works correctly."""
        mock_result = {
            "id": "task-xyz789",
            "status": "running",
            "goal": "Turn off living room lights",
            "current_step": "Launching google_home",
        }

        with patch(
            "actions.android_phone.task_get_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.android.task_get("task-xyz789")

            assert result == mock_result
            assert result["status"] == "running"
            mock_action.assert_called_once()

    def test_frank_api_android_task_cancel_works(self) -> None:
        """FrankAPI.android.task_cancel() works correctly."""
        mock_result = {
            "message": "Task cancelled",
            "id": "task-xyz789",
            "status": "cancelled",
        }

        with patch(
            "actions.android_phone.task_cancel_action", new_callable=AsyncMock
        ) as mock_action:
            mock_action.return_value = mock_result

            api = FrankAPI()
            result = api.android.task_cancel("task-xyz789")

            assert result == mock_result
            assert result["status"] == "cancelled"
            mock_action.assert_called_once()

    def test_frank_api_android_methods_exist(self) -> None:
        """FrankAPI.android has all expected methods."""
        api = FrankAPI()
        assert hasattr(api.android, "task_do")
        assert hasattr(api.android, "task_get")
        assert hasattr(api.android, "task_cancel")
        assert callable(api.android.task_do)
        assert callable(api.android.task_get)
        assert callable(api.android.task_cancel)
