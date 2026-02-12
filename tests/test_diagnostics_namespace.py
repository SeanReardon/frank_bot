"""
Unit tests for DiagnosticsNamespace and SystemNamespace in meta/api.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from meta.api import DiagnosticsNamespace, SystemNamespace, FrankAPI


class TestDiagnosticsNamespaceFull:
    """Tests for DiagnosticsNamespace.full()."""

    def test_full_returns_diagnostics(self) -> None:
        mock_result = {
            "message": "diagnostics summary",
            "server": {"uptime_human": "2h"},
            "subsystems": {},
        }

        with patch(
            "actions.diagnostics.get_diagnostics_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = DiagnosticsNamespace()
            result = ns.full()
            mock_action.assert_called_once()
            assert result == mock_result

    def test_full_calls_correct_action(self) -> None:
        with patch(
            "actions.diagnostics.get_diagnostics_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"message": "ok"}
            DiagnosticsNamespace().full()
            mock_action.assert_called_once()


class TestDiagnosticsNamespaceHealth:
    """Tests for DiagnosticsNamespace.health()."""

    def test_health_returns_status(self) -> None:
        mock_result = {
            "status": "ok",
            "uptime": "3h 15m",
            "build": "abc1234",
        }

        with patch(
            "actions.diagnostics.health_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = DiagnosticsNamespace()
            result = ns.health()
            mock_action.assert_called_once()
            assert result["status"] == "ok"
            assert result["uptime"] == "3h 15m"

    def test_health_calls_correct_action(self) -> None:
        with patch(
            "actions.diagnostics.health_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"status": "ok"}
            DiagnosticsNamespace().health()
            mock_action.assert_called_once()


class TestSystemNamespaceStatus:
    """Tests for SystemNamespace.status()."""

    def test_status_returns_orchestration_status(self) -> None:
        mock_result = {
            "message": "All systems operational",
            "healthy": True,
            "switchboard": {"configured": True},
            "agent_runner": {"configured": True},
        }

        with patch(
            "actions.system_status.get_system_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = SystemNamespace()
            result = ns.status()
            mock_action.assert_called_once()
            assert result["healthy"] is True

    def test_status_calls_correct_action(self) -> None:
        with patch(
            "actions.system_status.get_system_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"message": "ok"}
            SystemNamespace().status()
            mock_action.assert_called_once()


class TestSystemNamespaceServer:
    """Tests for SystemNamespace.server()."""

    def test_server_returns_uptime(self) -> None:
        mock_result = {
            "message": "Docker instance start time.",
            "startup_iso_time": "2026-02-12T00:00:00+00:00",
            "uptime_seconds": 3600,
        }

        with patch(
            "actions.system.get_server_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = SystemNamespace()
            result = ns.server()
            mock_action.assert_called_once()
            assert result["uptime_seconds"] == 3600

    def test_server_calls_correct_action(self) -> None:
        with patch(
            "actions.system.get_server_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"message": "ok"}
            SystemNamespace().server()
            mock_action.assert_called_once()


class TestSystemNamespaceHello:
    """Tests for SystemNamespace.hello()."""

    def test_hello_default_name(self) -> None:
        mock_result = {"message": "hello world", "name": "world"}

        with patch(
            "actions.system.hello_world_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = SystemNamespace()
            result = ns.hello()
            mock_action.assert_called_once_with({"name": "world"})
            assert result["message"] == "hello world"

    def test_hello_with_name(self) -> None:
        mock_result = {"message": "hello Frank", "name": "Frank"}

        with patch(
            "actions.system.hello_world_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = mock_result
            ns = SystemNamespace()
            result = ns.hello("Frank")
            mock_action.assert_called_once_with({"name": "Frank"})
            assert result["name"] == "Frank"


class TestFrankAPIDiagnosticsIntegration:
    """Tests for FrankAPI diagnostics/system namespace access."""

    def test_frank_api_has_diagnostics_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "diagnostics")
        assert isinstance(api.diagnostics, DiagnosticsNamespace)

    def test_frank_api_has_system_namespace(self) -> None:
        api = FrankAPI()
        assert hasattr(api, "system")
        assert isinstance(api.system, SystemNamespace)

    def test_frank_api_diagnostics_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.diagnostics is api.diagnostics

    def test_frank_api_system_is_same_instance(self) -> None:
        api = FrankAPI()
        assert api.system is api.system

    def test_frank_api_diagnostics_full_works(self) -> None:
        with patch(
            "actions.diagnostics.get_diagnostics_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"message": "full diagnostics"}
            api = FrankAPI()
            result = api.diagnostics.full()
            assert result["message"] == "full diagnostics"
            mock_action.assert_called_once()

    def test_frank_api_diagnostics_health_works(self) -> None:
        with patch(
            "actions.diagnostics.health_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"status": "ok"}
            api = FrankAPI()
            result = api.diagnostics.health()
            assert result["status"] == "ok"
            mock_action.assert_called_once()

    def test_frank_api_system_status_works(self) -> None:
        with patch(
            "actions.system_status.get_system_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"healthy": True, "message": "ok"}
            api = FrankAPI()
            result = api.system.status()
            assert result["healthy"] is True
            mock_action.assert_called_once()

    def test_frank_api_system_server_works(self) -> None:
        with patch(
            "actions.system.get_server_status_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"uptime_seconds": 100}
            api = FrankAPI()
            result = api.system.server()
            assert result["uptime_seconds"] == 100
            mock_action.assert_called_once()

    def test_frank_api_system_hello_works(self) -> None:
        with patch(
            "actions.system.hello_world_action",
            new_callable=AsyncMock,
        ) as mock_action:
            mock_action.return_value = {"message": "hello world"}
            api = FrankAPI()
            result = api.system.hello()
            assert result["message"] == "hello world"
            mock_action.assert_called_once()
