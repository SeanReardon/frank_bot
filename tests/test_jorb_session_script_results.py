"""
Regression tests for JorbSession prompt formatting.

These tests ensure the LLM can see critical fields (e.g. `status`) even when
payloads include long strings that would otherwise be truncated.
"""

from __future__ import annotations

from services.jorb_session import JorbSession
from services.jorb_storage import Jorb


def test_script_results_always_include_status_even_with_long_goal() -> None:
    long_goal = "X" * 400
    jorb = Jorb(
        id="jorb_test",
        name="Test",
        status="running",
        original_plan="Test plan",
        contacts_json="[]",
        personality="default",
        progress_summary=None,
        created_at="2026-02-16T00:00:00+00:00",
        updated_at="2026-02-16T00:00:00+00:00",
        paused_reason=None,
        needs_approval_for=None,
        awaiting=None,
        messages_in=0,
        messages_out=0,
        tokens_used=0,
        estimated_cost=0.0,
        context_resets=0,
        outcome_result=None,
        outcome_completed_at=None,
        outcome_failure_reason=None,
        script_results=[
            {
                "script": "android.task_get",
                "success": True,
                "result": {
                    "id": "c503ac70",
                    "goal": long_goal,
                    "status": "completed",
                },
            }
        ],
        metadata_json="{}",
        wake_at=None,
    )

    session = JorbSession(jorb=jorb, messages=[], policy={})
    prompt = session._build_system_prompt()

    assert "Script: android.task_get" in prompt
    assert "Status: completed" in prompt


def test_script_results_include_error_one_line() -> None:
    jorb = Jorb(
        id="jorb_test2",
        name="Test2",
        status="running",
        original_plan="Test plan",
        contacts_json="[]",
        personality="default",
        progress_summary=None,
        created_at="2026-02-16T00:00:00+00:00",
        updated_at="2026-02-16T00:00:00+00:00",
        paused_reason=None,
        needs_approval_for=None,
        awaiting=None,
        messages_in=0,
        messages_out=0,
        tokens_used=0,
        estimated_cost=0.0,
        context_resets=0,
        outcome_result=None,
        outcome_completed_at=None,
        outcome_failure_reason=None,
        script_results=[
            {
                "script": "android.task_get",
                "success": False,
                "result": {
                    "id": "deadbeef",
                    "status": "failed",
                    "error": "adb: device '10.0.0.95:5555' not found\n",
                },
            }
        ],
        metadata_json="{}",
        wake_at=None,
    )

    session = JorbSession(jorb=jorb, messages=[], policy={})
    prompt = session._build_system_prompt()

    assert "Status: failed" in prompt
    assert "Error: adb: device '10.0.0.95:5555' not found" in prompt

