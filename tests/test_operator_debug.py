from __future__ import annotations

from pathlib import Path

import pytest

from actions.operator_debug import get_operator_debug_action
from services.android_task_storage import AndroidTaskStorage
from services.event_traces import EventTraceStore
from services.jorb_storage import JorbMessage, JorbStorage


@pytest.fixture
def temp_json_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JORBS_DB_PATH", str(tmp_path / "jorbs"))
    monkeypatch.setattr("services.event_traces._trace_store", None)
    monkeypatch.setattr("services.android_task_storage._storage", None)
    return tmp_path


@pytest.mark.asyncio
async def test_operator_debug_action_returns_agent_facing_snapshot(
    temp_json_state: Path,
) -> None:
    storage = JorbStorage(db_path=str(temp_json_state / "jorbs"))
    trace_store = EventTraceStore(data_dir=str(temp_json_state))
    android_storage = AndroidTaskStorage()

    jorb = await storage.create_jorb(
        name="Check thermostat screenshot",
        plan="Take a screenshot and report what happened",
    )
    await storage.add_message(
        jorb.id,
        JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp="2026-03-07T12:00:00+00:00",
            direction="inbound",
            channel="telegram",
            sender="@sean",
            sender_name="Sean",
            content="please debug the thermostat",
        ),
    )
    await storage.increment_metrics(
        jorb.id,
        messages_in=1,
        tokens_used=321,
        estimated_cost=0.123,
    )
    await storage.add_script_result(
        jorb.id,
        {
            "script": "inspect_android_state",
            "result": {"ok": True},
            "success": True,
            "timestamp": "2026-03-07T12:00:01+00:00",
        },
    )

    task = await android_storage.create_task(
        "Take a screenshot of the thermostat app",
        app="Nest",
    )
    await android_storage.update_task(
        task.id,
        status="failed",
        steps_taken=2,
        current_step="done",
        tokens_used=88,
        estimated_cost=0.055,
        artifacts=[
            {
                "kind": "screenshot",
                "path": "./data/android_tasks/screen.png",
            }
        ],
        error="Phone screen status is lockscreen.",
        result={
            "summary": "Captured screenshot",
            "extracted_data": {
                "screen_status": "lockscreen",
                "screen_status_source": "dumpsys_window",
                "focused_app": "com.android.systemui",
                "focused_window": "StatusBar",
                "status_reason": "showing_lockscreen",
                "lockscreen_detected": True,
            },
        },
        metadata={
            "screen_status": "lockscreen",
            "screen_status_source": "dumpsys_window",
            "focused_app": "com.android.systemui",
            "focused_window": "StatusBar",
            "status_reason": "showing_lockscreen",
            "lockscreen_detected": True,
        },
    )

    event_id, trace_id = await trace_store.record_event(
        {
            "channel": "telegram",
            "sender": "@sean",
            "content": "debug frank",
            "task_class": "diagnostic_probe",
        }
    )
    await trace_store.append_step(
        trace_id,
        "session_action",
        {"action": "RUN_SCRIPT"},
    )
    await trace_store.finalize(trace_id, {"ok": True}, status="completed")

    result = await get_operator_debug_action({"limit": 10})

    assert result["audience"] == "agentic_tooling"
    assert result["models"]["agent_runner"] == "gpt-5.2"
    assert result["token_cost_summary"]["jorbs"]["tokens_used"] == 321
    assert result["token_cost_summary"]["android_tasks"][
        "estimated_cost"
    ] == pytest.approx(0.055)
    assert result["jorbs"]["recent"][0]["task_class"] == "android_capture"
    assert result["latest_script_results"][0]["script"] == "inspect_android_state"
    assert result["android"]["tasks"][0]["artifacts"][0]["kind"] == "screenshot"
    assert result["android"]["tasks"][0]["screen_context"][
        "screen_status"
    ] == "lockscreen"
    assert result["android"]["tasks"][0]["screen_context"][
        "focused_app"
    ] == "com.android.systemui"
    assert result["recent_messages"][0]["content"] == "please debug the thermostat"
    assert result["recent_events"][0]["event_id"] == event_id
    assert result["recent_traces"][0]["trace_id"] == trace_id
    assert result["last_error_by_subsystem"]["android_tasks"][0][
        "screen_context"
    ]["status_reason"] == "showing_lockscreen"


def test_operator_debug_action_runs_through_http_route(
    temp_json_state: Path,
) -> None:
    from config import Settings
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from server.routes import build_action_routes

    settings = Settings(
        app_version="test",
        host="localhost",
        port=8000,
        log_file="test.log",
        log_level="DEBUG",
        default_timezone="UTC",
        google_token_file="token.json",
        google_credentials_file=None,
        google_client_id=None,
        google_client_secret=None,
        google_calendar_scopes=(),
        google_contacts_scopes=(),
        public_base_url="http://localhost:8000",
        actions_api_key="test-api-key",
        actions_name_for_human="Test",
        actions_name_for_model="test",
        actions_description_for_human="Test",
        actions_description_for_model="Test",
        actions_logo_url=None,
        actions_contact_email=None,
        actions_legal_url=None,
        actions_openapi_path="openapi/spec.json",
        swarm_oauth_token=None,
        swarm_api_version="20240501",
        telnyx_api_key=None,
        telnyx_phone_number=None,
        notify_numbers=(),
        telegram_api_id=None,
        telegram_api_hash=None,
        telegram_phone=None,
        telegram_session_name="test",
        telegram_bot_token=None,
        telegram_bot_chat_id=None,
        stytch_project_id=None,
        stytch_secret=None,
        openai_api_key=None,
        jorbs_db_path=str(temp_json_state / "jorbs"),
        jorbs_progress_log="./test_progress.txt",
        agent_spend_limit=100.0,
        context_reset_days=3,
        debounce_telegram_seconds=60,
        debounce_sms_seconds=30,
        smtp_host=None,
        smtp_port=587,
        smtp_user=None,
        smtp_password=None,
        digest_email_to=None,
        digest_time="08:00",
        claudia_api_url=None,
        claudia_api_key=None,
        android_device_serial="",
        android_adb_host="",
        android_adb_port=5555,
        android_llm_model="gpt-5.2",
        android_llm_api_key=None,
        android_maintenance_cron="0 3 1 * *",
        android_health_check_cron="0 4 * * 0",
        android_rate_limit_minute=10,
        android_rate_limit_hour=100,
        owner_name="Test User",
        earshot_api_url=None,
        earshot_api_key=None,
    )

    app = Starlette(routes=build_action_routes(settings))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/actions/operator/debug",
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    assert response.json()["audience"] == "agentic_tooling"
