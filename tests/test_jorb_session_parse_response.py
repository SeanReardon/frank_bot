"""Unit tests for JorbSession response parsing with new script-based JSON format."""

import pytest
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Import the classes to test
from services.jorb_session import (
    JorbSession,
    JorbAction,
    JorbSessionResponse,
    JorbProgress,
    create_jorb_session,
)
from services.jorb_storage import Jorb, JorbMessage, JorbContact, Channel


class TestParseResponseScriptWithAwait:
    """Tests for script-with-await action type."""

    def test_parse_script_with_await_reply_true(self):
        """Parse JSON with script and await_reply=true."""
        # Create a minimal jorb and messages for session
        jorb = Jorb(
            id="test-jorb-1",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        # JSON response with script and await_reply=true
        response_json = {
            "reasoning": "Sending message to contact and waiting for response",
            "script": "frank.telegram.send('@magicapp', 'Hi! Looking for hotels in Paris')",
            "await_reply": True,
            "done": False,
            "pause": False,
            "pause_reason": None,
            "result": None,
        }

        result = session._parse_response(response_json)

        assert result.reasoning == "Sending message to contact and waiting for response"
        assert result.action.type == "script"
        assert (
            result.action.script
            == "frank.telegram.send('@magicapp', 'Hi! Looking for hotels in Paris')"
        )
        assert result.action.await_reply is True
        assert result.action.done is False
        assert result.action.pause is False
        assert result.action.pause_reason is None
        assert result.action.result is None
        assert result.script == result.action.script
        assert result.await_reply is True
        assert result.done is False
        assert result.pause is False

    def test_parse_script_with_await_reply_false(self):
        """Parse JSON with script and await_reply=false."""
        jorb = Jorb(
            id="test-jorb-2",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Checking calendar for availability",
            "script": "frank.calendar.events(day='2026-02-07')",
            "await_reply": False,
            "done": False,
            "pause": False,
            "pause_reason": None,
            "result": None,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "script"
        assert result.action.script == "frank.calendar.events(day='2026-02-07')"
        assert result.action.await_reply is False
        assert result.await_reply is False

    def test_parse_script_with_whitespace_only_returns_no_action(self):
        """Script with only whitespace should result in no_action type."""
        jorb = Jorb(
            id="test-jorb-3",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Empty script",
            "script": "   \n\t  ",
            "await_reply": False,
            "done": False,
            "pause": False,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "no_action"
        assert result.action.script == "   \n\t  "


class TestParseResponseDone:
    """Tests for done action type."""

    def test_parse_done_with_result(self):
        """Parse JSON with done=true and result."""
        jorb = Jorb(
            id="test-jorb-done",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Task completed successfully",
            "script": None,
            "await_reply": False,
            "done": True,
            "pause": False,
            "pause_reason": None,
            "result": {
                "thermostat": "65-69°F",
                "status": "confirmed",
                "current_temp": "68°F",
            },
        }

        result = session._parse_response(response_json)

        assert result.reasoning == "Task completed successfully"
        assert result.action.type == "complete"
        assert result.action.done is True
        assert result.action.script is None
        assert result.action.result == {
            "thermostat": "65-69°F",
            "status": "confirmed",
            "current_temp": "68°F",
        }
        assert result.done is True
        assert result.result == result.action.result

    def test_parse_done_without_result(self):
        """Parse JSON with done=true but no result field."""
        jorb = Jorb(
            id="test-jorb-done-2",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "All done",
            "script": None,
            "done": True,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "complete"
        assert result.action.done is True
        assert result.action.result is None
        assert result.done is True


class TestParseResponsePause:
    """Tests for pause action type."""

    def test_parse_pause_with_reason(self):
        """Parse JSON with pause=true and pause_reason."""
        jorb = Jorb(
            id="test-jorb-pause",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Need approval before booking",
            "script": None,
            "await_reply": False,
            "done": False,
            "pause": True,
            "pause_reason": "Magic found 3 hotels. Which should I book?",
            "result": None,
        }

        result = session._parse_response(response_json)

        assert result.reasoning == "Need approval before booking"
        assert result.action.type == "pause"
        assert result.action.pause is True
        assert result.action.pause_reason == "Magic found 3 hotels. Which should I book?"
        assert result.action.script is None
        assert result.pause is True

    def test_parse_pause_prioritized_over_script(self):
        """When both pause and script are present, pause takes precedence."""
        jorb = Jorb(
            id="test-jorb-pause-2",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Pausing despite having script",
            "script": "frank.calendar.events()",
            "pause": True,
            "pause_reason": "Need approval",
        }

        result = session._parse_response(response_json)

        # Pause takes precedence over script
        assert result.action.type == "pause"
        assert result.action.pause is True
        assert result.action.script == "frank.calendar.events()"  # Still stored


class TestParseResponseNoAction:
    """Tests for no-action scenarios."""

    def test_parse_no_action_all_false(self):
        """Parse JSON with no action indicators."""
        jorb = Jorb(
            id="test-jorb-none",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "No action needed",
            "script": None,
            "await_reply": False,
            "done": False,
            "pause": False,
            "pause_reason": None,
            "result": None,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "no_action"
        assert result.action.script is None
        assert result.action.done is False
        assert result.action.pause is False

    def test_parse_minimal_response(self):
        """Parse JSON with only reasoning field."""
        jorb = Jorb(
            id="test-jorb-minimal",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Spam message, ignoring",
        }

        result = session._parse_response(response_json)

        assert result.reasoning == "Spam message, ignoring"
        assert result.action.type == "no_action"
        assert result.action.script is None
        assert result.action.await_reply is False
        assert result.action.done is False
        assert result.action.pause is False

    def test_parse_empty_response(self):
        """Parse empty JSON object."""
        jorb = Jorb(
            id="test-jorb-empty",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {}

        result = session._parse_response(response_json)

        assert result.reasoning == ""
        assert result.action.type == "no_action"
        assert result.action.script is None


class TestParseResponseMalformed:
    """Tests for graceful handling of malformed LLM output."""

    def test_parse_non_dict_response_raises_error(self):
        """Non-dict response should raise ValueError."""
        jorb = Jorb(
            id="test-jorb-malformed",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        with pytest.raises(ValueError, match="Expected dict response"):
            session._parse_response("not a dict")

        with pytest.raises(ValueError, match="Expected dict response"):
            session._parse_response(["list", "not", "dict"])

        with pytest.raises(ValueError, match="Expected dict response"):
            session._parse_response(None)

    def test_parse_invalid_boolean_values(self):
        """Invalid boolean values should be coerced gracefully."""
        jorb = Jorb(
            id="test-jorb-bool",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        # String "true" should be truthy
        response_json = {
            "reasoning": "Testing",
            "await_reply": "true",  # String instead of bool
            "done": 1,  # Number instead of bool
            "pause": "yes",  # String instead of bool
        }

        result = session._parse_response(response_json)

        # bool() coercion: non-empty string -> True, non-zero number -> True
        assert result.action.await_reply is True
        assert result.action.done is True
        assert result.action.pause is True

    def test_parse_invalid_result_type(self):
        """Non-dict result should be handled gracefully."""
        jorb = Jorb(
            id="test-jorb-result",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Done",
            "done": True,
            "result": "string result",  # Should be dict
        }

        result = session._parse_response(response_json)

        # Non-dict result should become None
        assert result.action.result is None
        assert result.result is None

        # But done should still be True
        assert result.action.done is True

    def test_parse_missing_fields_get_defaults(self):
        """Missing fields should get sensible defaults."""
        jorb = Jorb(
            id="test-jorb-missing",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "script": "frank.calendar.events()",
            # Missing: reasoning, await_reply, done, pause, pause_reason, result
        }

        result = session._parse_response(response_json)

        assert result.reasoning == ""  # Empty string default
        assert result.action.reasoning == ""  # Also on action
        assert result.action.await_reply is False  # False default
        assert result.action.done is False  # False default
        assert result.action.pause is False  # False default
        assert result.action.pause_reason is None  # None default
        assert result.action.result is None  # None default
        assert result.action.type == "script"  # Because script is present


class TestParseResponseProgress:
    """Tests for progress field parsing."""

    def test_parse_with_progress(self):
        """Parse JSON with progress information."""
        jorb = Jorb(
            id="test-jorb-progress",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Making progress",
            "script": "frank.calendar.events()",
            "await_reply": False,
            "progress": {
                "note": "Checked calendar for tomorrow",
                "awaiting": "calendar_data",
                "learnings": "User prefers morning meetings",
            },
        }

        result = session._parse_response(response_json)

        assert result.progress is not None
        assert result.progress.note == "Checked calendar for tomorrow"
        assert result.progress.awaiting == "calendar_data"
        assert result.progress.learnings == "User prefers morning meetings"

    def test_parse_without_progress(self):
        """Parse JSON without progress field."""
        jorb = Jorb(
            id="test-jorb-noprogress",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Simple action",
            "script": "frank.time.now()",
        }

        result = session._parse_response(response_json)

        assert result.progress is None

    def test_parse_progress_not_dict(self):
        """Progress field that's not a dict should be ignored."""
        jorb = Jorb(
            id="test-jorb-progress-str",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Testing",
            "progress": "invalid progress format",
        }

        result = session._parse_response(response_json)

        assert result.progress is None


class TestParseResponseBackwardCompatibility:
    """Tests for backward compatibility with legacy action format."""

    def test_action_fields_populated_from_new_format(self):
        """Legacy action fields should be populated from new format."""
        jorb = Jorb(
            id="test-jorb-compat",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Sending SMS",
            "script": "frank.sms.send('+1234567890', 'Hello')",
            "await_reply": True,
        }

        result = session._parse_response(response_json)

        # Content should be set from script for backward compatibility
        assert result.action.content == "frank.sms.send('+1234567890', 'Hello')"


class TestParseResponseEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_done_takes_precedence_over_script(self):
        """When both done and script are present, done takes precedence."""
        jorb = Jorb(
            id="test-jorb-done-script",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Done but has script",
            "script": "frank.calendar.events()",
            "done": True,
        }

        result = session._parse_response(response_json)

        # Done takes precedence over script
        assert result.action.type == "complete"
        assert result.action.done is True
        assert result.action.script == "frank.calendar.events()"  # Still stored

    def test_script_with_none_value(self):
        """Script field with None value should not create script action."""
        jorb = Jorb(
            id="test-jorb-none-script",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "No script",
            "script": None,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "no_action"
        assert result.action.script is None

    def test_all_flags_true_priority(self):
        """When done, pause, and script are all true/present, done has highest priority."""
        jorb = Jorb(
            id="test-jorb-priority",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "All flags set",
            "script": "frank.calendar.events()",
            "done": True,
            "pause": True,
        }

        result = session._parse_response(response_json)

        # Priority: done > pause > script
        assert result.action.type == "complete"

    def test_pause_over_script_priority(self):
        """When pause and script are both present but not done, pause takes precedence."""
        jorb = Jorb(
            id="test-jorb-pause-over-script",
            name="Test Jorb",
            status="running",
            original_plan="Test plan",
            created_at=datetime.now().isoformat(),
        )
        session = JorbSession(jorb=jorb, messages=[])

        response_json = {
            "reasoning": "Pause with script",
            "script": "frank.calendar.events()",
            "pause": True,
            "done": False,
        }

        result = session._parse_response(response_json)

        assert result.action.type == "pause"
