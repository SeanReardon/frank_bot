"""
Tests for AgentRunner script execution, agent loop, rate limiting,
and integration flows (frank_bot-00114 through frank_bot-00117).
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_runner import (
    AgentRunner,
    IncomingEvent,
    SCRIPT_EXECUTION_TIMEOUT,
    MAX_ITERATIONS_PER_10_MIN,
    ITERATION_WINDOW_SECONDS,
    MAX_ITERATIONS_PER_DAY,
)
from services.jorb_storage import (
    Jorb,
    JorbContact,
    JorbStorage,
)
from services.jorb_session import (
    JorbAction,
    JorbSessionResponse,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def storage(temp_db_path):
    """Create a JorbStorage instance with temp database."""
    return JorbStorage(db_path=temp_db_path)


@pytest.fixture
def runner(storage):
    """Create an AgentRunner with storage and fake API key."""
    return AgentRunner(storage=storage, openai_api_key="test-api-key")


@pytest.fixture
def sample_jorb():
    """Create a sample jorb."""
    return Jorb(
        id="jorb_test_001",
        name="Test Calendar Query",
        status="running",
        original_plan="Check my calendar for tomorrow",
        progress_summary="",
        contacts_json='[{"identifier": "@user", "channel": "telegram", "name": "User"}]',
    )


@pytest.fixture
def sample_jorb_with_contact():
    """Create a sample jorb with telegram contact."""
    return Jorb(
        id="jorb_test_002",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel via Magic",
        progress_summary="",
        contacts_json='[{"identifier": "@magic", "channel": "telegram", "name": "Magic"}]',
    )


@pytest.fixture
def sample_event():
    """Create a sample incoming event."""
    return IncomingEvent(
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="Found 3 hotels for you!",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
    )


# =============================================================================
# Task 114: _execute_script tests
# =============================================================================


class TestExecuteScript:
    """Tests for AgentRunner._execute_script (frank_bot-00114)."""

    @pytest.mark.asyncio
    async def test_execute_script_success(self, runner, storage, sample_jorb):
        """Successful script execution stores result."""
        # Create the jorb in storage
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        # Mock FrankAPI to return calendar events
        mock_api = MagicMock()
        mock_api.calendar.events.return_value = {
            "events": [{"summary": "Meeting", "start": "10:00"}]
        }

        with patch("meta.api.FrankAPI", return_value=mock_api):
            result = await runner._execute_script(
                jorb, 'frank.calendar.events(day="2026-02-09")'
            )

        assert result["success"] is True
        assert result["result"] == {"events": [{"summary": "Meeting", "start": "10:00"}]}
        assert "script" in result
        assert "timestamp" in result

        # Verify stored in jorb_storage
        script_results = await storage.get_script_results(jorb.id)
        assert len(script_results) == 1
        assert script_results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_execute_script_with_main_loop_does_not_deadlock(self, runner, storage, sample_jorb):
        """
        When FrankAPI is configured to submit coroutines to the running event loop,
        script execution must NOT block that loop (otherwise deadlock).
        """
        # Create the jorb in storage
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        import asyncio
        import meta.api as frank_api

        # Simulate normal server startup behavior
        frank_api.set_main_loop(asyncio.get_running_loop())
        try:
            result = await runner._execute_script(
                jorb,
                "frank.system.hello('world')",
                timeout=2,
            )
        finally:
            # Avoid leaking loop state across tests
            frank_api._main_loop = None  # type: ignore[attr-defined]

        assert result["success"] is True
        assert isinstance(result["result"], dict)
        assert result["result"].get("message") == "hello world"

    @pytest.mark.asyncio
    async def test_execute_script_error_captured(self, runner, storage, sample_jorb):
        """Script errors are captured and stored, not raised."""
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        # Mock FrankAPI to raise an error
        mock_api = MagicMock()
        mock_api.calendar.events.side_effect = RuntimeError("API unavailable")

        with patch("meta.api.FrankAPI", return_value=mock_api):
            result = await runner._execute_script(
                jorb, 'frank.calendar.events(day="2026-02-09")'
            )

        # Error captured, not raised
        assert result["success"] is False
        assert "RuntimeError" in result["error"]
        assert "API unavailable" in result["error"]

        # Stored in jorb_storage
        script_results = await storage.get_script_results(jorb.id)
        assert len(script_results) == 1
        assert script_results[0]["success"] is False

    @pytest.mark.asyncio
    async def test_execute_script_timeout(self, runner, storage, sample_jorb):
        """Script execution respects timeout."""
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        import time

        mock_api = MagicMock()
        mock_api.time.now.side_effect = lambda: time.sleep(5)

        with patch("meta.api.FrankAPI", return_value=mock_api):
            result = await runner._execute_script(
                jorb, "frank.time.now()", timeout=1
            )

        assert result["success"] is False
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_script_multiline(self, runner, storage, sample_jorb):
        """Multi-line scripts work via exec fallback."""
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        mock_api = MagicMock()
        mock_api.time.now.return_value = {"time": "12:00"}

        script = "t = frank.time.now()\nresult = {'got_time': True}"

        with patch("meta.api.FrankAPI", return_value=mock_api):
            result = await runner._execute_script(jorb, script)

        assert result["success"] is True
        assert result["result"] == {"got_time": True}

    @pytest.mark.asyncio
    async def test_execute_script_multiline_res_fallback(self, runner, storage, sample_jorb):
        """
        Multi-line scripts that populate `res` (common model habit) still return
        a value, so we don't get stuck re-running scripts that "succeed" but
        produce None.
        """
        await storage.create_jorb(
            name=sample_jorb.name,
            plan=sample_jorb.original_plan,
        )
        jorbs = await storage.list_jorbs()
        jorb = jorbs[0]

        mock_api = MagicMock()
        mock_api.time.now.return_value = {"time": "12:00"}

        script = "t = frank.time.now()\nres = {'got_time': True, 't': t}"

        with patch("meta.api.FrankAPI", return_value=mock_api):
            result = await runner._execute_script(jorb, script)

        assert result["success"] is True
        assert isinstance(result["result"], dict)
        assert result["result"].get("got_time") is True

    def test_script_timeout_constant(self):
        """SCRIPT_EXECUTION_TIMEOUT default is 300."""
        assert SCRIPT_EXECUTION_TIMEOUT == 300

    def test_rate_limit_constants(self):
        """Rate limit constants have correct defaults."""
        assert MAX_ITERATIONS_PER_10_MIN == 20
        assert ITERATION_WINDOW_SECONDS == 600
        assert MAX_ITERATIONS_PER_DAY == 100


# =============================================================================
# Task 115: Agent loop tests
# =============================================================================


class TestAgentLoop:
    """Tests for AgentRunner.process_jorb_event (frank_bot-00115)."""

    def _make_session_response(
        self,
        action_type="no_action",
        script=None,
        await_reply=False,
        done=False,
        pause=False,
        pause_reason=None,
        result=None,
        reasoning="test reasoning",
        summary=None,
    ):
        """Helper to create a JorbSessionResponse."""
        action = JorbAction(
            type=action_type,
            script=script,
            await_reply=await_reply,
            done=done,
            pause=pause,
            pause_reason=pause_reason,
            result=result,
            reasoning=reasoning,
        )
        return JorbSessionResponse(
            summary=summary or reasoning,
            reasoning=reasoning,
            action=action,
            progress=None,
            tokens_used=100,
            estimated_cost=0.001,
            script=script,
            await_reply=await_reply,
            done=done,
            pause=pause,
            result=result,
        )

    @pytest.mark.asyncio
    async def test_done_breaks_loop(self, runner, storage):
        """Done action marks jorb complete and breaks loop."""
        jorb = await storage.create_jorb(
            name="Test Done", plan="Test plan"
        )
        await storage.update_jorb(jorb.id, status="running")

        done_response = self._make_session_response(
            action_type="complete",
            done=True,
            result={"answer": "42"},
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=done_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "complete"

        # Verify jorb is complete
        updated = await storage.get_jorb(jorb.id)
        assert updated.status == "complete"

    @pytest.mark.asyncio
    async def test_pause_breaks_loop(self, runner, storage):
        """Pause action marks jorb paused and breaks loop."""
        jorb = await storage.create_jorb(
            name="Test Pause", plan="Test plan"
        )
        await storage.update_jorb(jorb.id, status="running")

        pause_response = self._make_session_response(
            action_type="pause",
            pause=True,
            pause_reason="Need human approval",
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=pause_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "pause_for_approval"

        updated = await storage.get_jorb(jorb.id)
        assert updated.status == "paused"
        assert updated.paused_reason == "Need human approval"

    @pytest.mark.asyncio
    async def test_async_script_breaks_loop(self, runner, storage):
        """Script with await_reply=true executes then breaks."""
        jorb = await storage.create_jorb(
            name="Test Async", plan="Send message and wait"
        )
        await storage.update_jorb(jorb.id, status="running")

        async_response = self._make_session_response(
            action_type="script",
            script="frank.telegram.send('@magic', 'hello')",
            await_reply=True,
        )

        mock_api = MagicMock()
        mock_api.telegram.send.return_value = {"success": True}

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create, patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=async_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "script_await_reply"
        assert result.message_sent is True

    @pytest.mark.asyncio
    async def test_sync_script_continues_loop(self, runner, storage):
        """Sync script (await_reply=false) continues loop, then done breaks."""
        jorb = await storage.create_jorb(
            name="Test Sync Loop", plan="Check calendar then done"
        )
        await storage.update_jorb(jorb.id, status="running")

        # First iteration: sync script
        sync_response = self._make_session_response(
            action_type="script",
            script="frank.calendar.events()",
            await_reply=False,
        )
        # Second iteration: done
        done_response = self._make_session_response(
            action_type="complete",
            done=True,
            result={"events": []},
        )

        mock_api = MagicMock()
        mock_api.calendar.events.return_value = {"events": []}

        call_count = 0

        async def mock_kickoff():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sync_response
            return done_response

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create, patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(side_effect=mock_kickoff)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        # Loop ran twice
        assert call_count == 2
        assert result.success is True
        assert result.action_taken == "complete"

    @pytest.mark.asyncio
    async def test_poll_android_task_terminal_does_not_schedule_wake(self, runner, storage):
        """
        Regression: if the model polls a task that is already terminal, we must
        NOT schedule rapid wake ticks (which can cause runaway LLM loops).
        """
        jorb = await storage.create_jorb(
            name="Test Android Poll Terminal",
            plan="Poll android task",
        )
        await storage.update_jorb(
            jorb.id,
            status="running",
            metadata_json='{"preferred_transport":"telegram_bot","telegram_bot_chat_id":"123"}',
        )

        poll_response = self._make_session_response(action_type="POLL_ANDROID_TASK")
        poll_response.action = JorbAction(type="POLL_ANDROID_TASK", args={"task_id": "abc123"})

        completed_task = {
            "id": "abc123",
            "status": "completed",
            "current_step": "Running automation",
            "result": {"success": True, "result": "Task completed", "extracted_data": {}},
            "error": None,
        }

        with patch("services.agent_runner.create_jorb_session") as mock_create, patch(
            "actions.android_phone.task_get_action",
            new=AsyncMock(return_value=completed_task),
        ), patch.object(
            AgentRunner,
            "_send_telegram_bot_message",
            new=AsyncMock(return_value=True),
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=poll_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken in ("android_task_completed", "android_task_terminal")

        updated = await storage.get_jorb(jorb.id)
        assert updated.wake_at is None
        assert updated.awaiting == "human_reply"

    @pytest.mark.asyncio
    async def test_no_action_breaks_loop(self, runner, storage):
        """No-action response is a safety fallback that breaks the loop."""
        jorb = await storage.create_jorb(
            name="Test No Action", plan="Test plan"
        )
        await storage.update_jorb(jorb.id, status="running")

        no_action_response = self._make_session_response(
            action_type="no_action",
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=no_action_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "noop"

    @pytest.mark.asyncio
    async def test_loop_with_incoming_event(self, runner, storage):
        """First iteration uses process_message with event, not kickoff."""
        jorb = await storage.create_jorb(
            name="Test Event", plan="Handle message"
        )
        await storage.update_jorb(jorb.id, status="running")

        event = IncomingEvent(
            channel="telegram",
            sender="@user",
            sender_name="User",
            content="Hello!",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        done_response = self._make_session_response(
            action_type="complete",
            done=True,
            result={"reply": "done"},
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.process_message = AsyncMock(return_value=done_response)
            mock_session.tick = AsyncMock(return_value=done_response)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb, event=event)

        # process_message should have been called; no tick needed (done immediately)
        mock_session.process_message.assert_called_once()
        mock_session.tick.assert_not_called()
        assert result.action_taken == "complete"

    @pytest.mark.asyncio
    async def test_loop_passes_script_results(self, runner, storage):
        """Script results are available to LLM context on each iteration."""
        jorb = await storage.create_jorb(
            name="Test Results Context", plan="Two-step script flow"
        )
        await storage.update_jorb(jorb.id, status="running")

        sync_response = self._make_session_response(
            action_type="script",
            script="frank.time.now()",
            await_reply=False,
        )
        done_response = self._make_session_response(
            action_type="complete", done=True, result={"done": True}
        )

        mock_api = MagicMock()
        mock_api.time.now.return_value = {"time": "12:00"}

        call_count = 0
        sessions_created = []

        async def mock_kickoff():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sync_response
            return done_response

        def capture_session(jwm, **kwargs):
            sessions_created.append(jwm)
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(side_effect=mock_kickoff)
            return mock_session

        with patch(
            "services.agent_runner.create_jorb_session", side_effect=capture_session
        ), patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            _ = await runner.process_jorb_event(jorb)

        # Second session creation should have the script results from first execution
        assert len(sessions_created) == 2
        second_jwm = sessions_created[1]
        assert len(second_jwm.jorb.script_results) >= 1


# =============================================================================
# Task 116: Rate limiting tests
# =============================================================================


class TestIterationRateLimiting:
    """Tests for LLM iteration rate limiting (frank_bot-00116)."""

    def test_under_limit_proceeds(self, runner):
        """Under-limit check returns None (proceed)."""
        result = runner._check_iteration_rate_limit("jorb_test")
        assert result is None

    def test_window_limit_pauses(self, runner):
        """At window limit, check returns rate limit message."""
        jorb_id = "jorb_window"
        # Simulate MAX_ITERATIONS_PER_10_MIN iterations within window
        for _ in range(MAX_ITERATIONS_PER_10_MIN):
            runner._record_iteration(jorb_id)

        result = runner._check_iteration_rate_limit(jorb_id)
        assert result is not None
        assert "per 10 minutes" in result
        assert "without human" in result.lower()

    def test_daily_limit_pauses(self, runner):
        """At daily limit, check returns rate limit message."""
        jorb_id = "jorb_daily"
        key = f"iter_{jorb_id}"
        # Manually set timestamps spread over several hours but within a day
        # Important: none should fall in the last hour to avoid triggering hourly limit
        now = datetime.now(timezone.utc)
        timestamps = []
        for i in range(MAX_ITERATIONS_PER_DAY):
            # All between 2-23 hours ago (within day, but outside last hour)
            hours_ago = 2 + (i * 21 / MAX_ITERATIONS_PER_DAY)
            ts = now - timedelta(hours=hours_ago)
            timestamps.append(ts.isoformat())
        runner._message_counts[key] = timestamps

        result = runner._check_iteration_rate_limit(jorb_id)
        assert result is not None
        assert "per day" in result

    def test_counts_reset_after_time_window(self, runner):
        """Old timestamps are pruned, so limits reset over time."""
        jorb_id = "jorb_reset"
        key = f"iter_{jorb_id}"
        # Set timestamps from 2 days ago
        old = datetime.now(timezone.utc) - timedelta(days=2)
        runner._message_counts[key] = [old.isoformat()] * 50

        result = runner._check_iteration_rate_limit(jorb_id)
        assert result is None  # Old timestamps pruned

    def test_per_jorb_tracking(self, runner):
        """Rate limits are per-jorb, not global."""
        jorb_a = "jorb_a"
        jorb_b = "jorb_b"

        for _ in range(MAX_ITERATIONS_PER_10_MIN):
            runner._record_iteration(jorb_a)

        # jorb_a is at limit
        assert runner._check_iteration_rate_limit(jorb_a) is not None
        # jorb_b is not
        assert runner._check_iteration_rate_limit(jorb_b) is None

    @pytest.mark.asyncio
    async def test_rate_limit_pauses_jorb_in_loop(self, runner, storage):
        """Rate limit in agent loop pauses the jorb."""
        jorb = await storage.create_jorb(
            name="Test Rate Limit", plan="Test plan"
        )
        await storage.update_jorb(jorb.id, status="running")

        # Pre-fill iterations to hit limit
        for _ in range(MAX_ITERATIONS_PER_10_MIN):
            runner._record_iteration(jorb.id)

        result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "paused_rate_limit"

        updated = await storage.get_jorb(jorb.id)
        assert updated.status == "paused"
        assert "Rate limit" in updated.paused_reason


# =============================================================================
# Task 117: Integration tests
# =============================================================================


class TestIntegrationCalendarQuery:
    """Integration test: calendar query jorb (frank_bot-00117)."""

    @pytest.mark.asyncio
    async def test_calendar_query_flow(self, runner, storage):
        """
        Full flow: jorb created -> LLM generates calendar script ->
        result returned -> LLM says done -> jorb completes.
        """
        jorb = await storage.create_jorb(
            name="Calendar Check",
            plan="Check calendar events for tomorrow",
        )
        await storage.update_jorb(jorb.id, status="running")

        # LLM response 1: generate calendar query script
        script_response = JorbSessionResponse(
            summary="Checking calendar for tomorrow.",
            reasoning="Checking calendar for tomorrow",
            action=JorbAction(
                type="script",
                script='frank.calendar.events(day="2026-02-09")',
                await_reply=False,
            ),
            tokens_used=150,
            estimated_cost=0.002,
            script='frank.calendar.events(day="2026-02-09")',
            await_reply=False,
        )

        # LLM response 2: done with result
        done_response = JorbSessionResponse(
            summary="Calendar query complete.",
            reasoning="Calendar shows 2 events tomorrow",
            action=JorbAction(
                type="complete",
                done=True,
                result={"events_count": 2, "summary": "2 meetings tomorrow"},
            ),
            tokens_used=100,
            estimated_cost=0.001,
            done=True,
            result={"events_count": 2, "summary": "2 meetings tomorrow"},
        )

        mock_api = MagicMock()
        mock_api.calendar.events.return_value = {
            "events": [
                {"summary": "Standup", "start": "09:00"},
                {"summary": "1:1 with Alice", "start": "14:00"},
            ]
        }

        call_count = 0

        async def mock_kickoff():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return script_response
            return done_response

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create, patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(side_effect=mock_kickoff)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "complete"
        assert call_count == 2

        # Verify jorb state
        final_jorb = await storage.get_jorb(jorb.id)
        assert final_jorb.status == "complete"

        # Verify script results stored
        script_results = await storage.get_script_results(jorb.id)
        assert len(script_results) == 1
        assert script_results[0]["success"] is True


class TestIntegrationTelegramConversation:
    """Integration test: telegram conversation jorb (frank_bot-00117)."""

    @pytest.mark.asyncio
    async def test_telegram_conversation_flow(self, runner, storage):
        """
        Full flow: jorb sends message via telegram -> awaits reply ->
        reply arrives -> next iteration -> jorb completes.
        """
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Ask Magic for hotel options",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic")],
        )
        await storage.update_jorb(jorb.id, status="running")

        # Step 1: LLM sends telegram message
        send_response = JorbSessionResponse(
            summary="Contacting Magic about hotels; waiting for reply.",
            reasoning="Contacting Magic about hotels",
            action=JorbAction(
                type="script",
                script="frank.telegram.send('@magic', 'Hotels in Paris?')",
                await_reply=True,
            ),
            tokens_used=120,
            estimated_cost=0.001,
            script="frank.telegram.send('@magic', 'Hotels in Paris?')",
            await_reply=True,
        )

        mock_api = MagicMock()
        mock_api.telegram.send.return_value = {"success": True, "message_id": 123}

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create, patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=send_response)
            mock_create.return_value = mock_session

            result1 = await runner.process_jorb_event(jorb)

        assert result1.action_taken == "script_await_reply"
        assert result1.message_sent is True

        # Step 2: Simulate reply arriving, jorb processes and completes
        reply_event = IncomingEvent(
            channel="telegram",
            sender="@magic",
            sender_name="Magic",
            content="Found Hotel Le Marais at $175/night!",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        done_response = JorbSessionResponse(
            summary="Hotel option received; task complete.",
            reasoning="Magic found a hotel, task complete",
            action=JorbAction(
                type="complete",
                done=True,
                result={"hotel": "Le Marais", "price": "$175/night"},
            ),
            tokens_used=100,
            estimated_cost=0.001,
            done=True,
            result={"hotel": "Le Marais", "price": "$175/night"},
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.process_message = AsyncMock(return_value=done_response)
            mock_create.return_value = mock_session

            # Store inbound message first (simulating switchboard)
            await runner.store_inbound_message(jorb.id, reply_event)
            result2 = await runner.process_jorb_event(jorb, event=reply_event)

        assert result2.action_taken == "complete"
        final_jorb = await storage.get_jorb(jorb.id)
        assert final_jorb.status == "complete"


class TestIntegrationAndroidPhone:
    """Integration test: android phone jorb (frank_bot-00117)."""

    @pytest.mark.asyncio
    async def test_android_phone_flow(self, runner, storage):
        """
        Full flow: jorb calls task_do -> polls task_get ->
        interprets result -> jorb completes.
        """
        jorb = await storage.create_jorb(
            name="Set Thermostat",
            plan="Use phone to set thermostat to 65-69",
        )
        await storage.update_jorb(jorb.id, status="running")

        # Step 1: task_do
        task_do_response = JorbSessionResponse(
            summary="Starting phone automation task.",
            reasoning="Starting phone automation",
            action=JorbAction(
                type="script",
                script="frank.android.task_do('Set thermostat to 65-69')",
                await_reply=False,
            ),
            tokens_used=120,
            estimated_cost=0.001,
            script="frank.android.task_do('Set thermostat to 65-69')",
            await_reply=False,
        )

        # Step 2: task_get (polling)
        task_get_response = JorbSessionResponse(
            summary="Polling phone automation task status.",
            reasoning="Checking task status",
            action=JorbAction(
                type="script",
                script="frank.android.task_get('task-abc')",
                await_reply=False,
            ),
            tokens_used=100,
            estimated_cost=0.001,
            script="frank.android.task_get('task-abc')",
            await_reply=False,
        )

        # Step 3: done
        done_response = JorbSessionResponse(
            summary="Thermostat confirmed; task complete.",
            reasoning="Thermostat confirmed at 65-69",
            action=JorbAction(
                type="complete",
                done=True,
                result={"range": "65-69°F", "status": "confirmed"},
            ),
            tokens_used=80,
            estimated_cost=0.001,
            done=True,
            result={"range": "65-69°F", "status": "confirmed"},
        )

        mock_api = MagicMock()
        mock_api.android.task_do.return_value = {"task_id": "task-abc", "status": "running"}
        mock_api.android.task_get.return_value = {"task_id": "task-abc", "status": "completed", "result": "Done"}

        call_count = 0

        async def mock_kickoff():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return task_do_response
            elif call_count == 2:
                return task_get_response
            return done_response

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create, patch(
            "meta.api.FrankAPI", return_value=mock_api
        ):
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(side_effect=mock_kickoff)
            mock_create.return_value = mock_session

            result = await runner.process_jorb_event(jorb)

        assert result.success is True
        assert result.action_taken == "complete"
        assert call_count == 3

        # Verify 2 script results stored (task_do and task_get)
        script_results = await storage.get_script_results(jorb.id)
        assert len(script_results) == 2


class TestIntegrationPauseForApproval:
    """Integration test: pause for approval (frank_bot-00117)."""

    @pytest.mark.asyncio
    async def test_pause_and_resume_flow(self, runner, storage):
        """
        Full flow: jorb pauses for approval -> jorbApprove resumes ->
        jorb completes.
        """
        jorb = await storage.create_jorb(
            name="Purchase Approval",
            plan="Buy something, pause for approval",
        )
        await storage.update_jorb(jorb.id, status="running")

        # Step 1: LLM pauses for approval
        pause_response = JorbSessionResponse(
            summary="Need approval to proceed.",
            reasoning="Found item, need approval to purchase",
            action=JorbAction(
                type="pause",
                pause=True,
                pause_reason="Found Widget Pro at $99. Approve purchase?",
            ),
            tokens_used=100,
            estimated_cost=0.001,
            pause=True,
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=pause_response)
            mock_create.return_value = mock_session

            result1 = await runner.process_jorb_event(jorb)

        assert result1.action_taken == "pause_for_approval"
        paused_jorb = await storage.get_jorb(jorb.id)
        assert paused_jorb.status == "paused"
        assert "Widget Pro" in paused_jorb.paused_reason

        # Step 2: Simulate jorbApprove - resume the jorb
        await storage.update_jorb(jorb.id, status="running", paused_reason=None)

        # Step 3: Process again, now jorb completes
        done_response = JorbSessionResponse(
            summary="Approved; completing.",
            reasoning="Approved, completing purchase",
            action=JorbAction(
                type="complete",
                done=True,
                result={"purchased": "Widget Pro", "price": "$99"},
            ),
            tokens_used=80,
            estimated_cost=0.001,
            done=True,
            result={"purchased": "Widget Pro", "price": "$99"},
        )

        with patch(
            "services.agent_runner.create_jorb_session"
        ) as mock_create:
            mock_session = MagicMock()
            mock_session.tick = AsyncMock(return_value=done_response)
            mock_create.return_value = mock_session

            refreshed_jorb = await storage.get_jorb(jorb.id)
            result2 = await runner.process_jorb_event(refreshed_jorb)

        assert result2.action_taken == "complete"
        final_jorb = await storage.get_jorb(jorb.id)
        assert final_jorb.status == "complete"


class TestExistingTestsStillPass:
    """Verify backward compatibility (frank_bot-00117)."""

    def test_constants_exported(self):
        """New constants are properly exported."""
        from services.agent_runner import (
            SCRIPT_EXECUTION_TIMEOUT,
            MAX_ITERATIONS_PER_10_MIN,
            ITERATION_WINDOW_SECONDS,
            MAX_ITERATIONS_PER_HOUR,
            MAX_ITERATIONS_PER_DAY,
        )
        assert isinstance(SCRIPT_EXECUTION_TIMEOUT, int)
        assert isinstance(MAX_ITERATIONS_PER_10_MIN, int)
        assert isinstance(ITERATION_WINDOW_SECONDS, int)
        assert isinstance(MAX_ITERATIONS_PER_HOUR, int)
        assert isinstance(MAX_ITERATIONS_PER_DAY, int)

    def test_agent_runner_has_new_methods(self, runner):
        """AgentRunner has the new methods."""
        assert hasattr(runner, "_execute_script")
        assert hasattr(runner, "process_jorb_event")
        assert hasattr(runner, "_check_iteration_rate_limit")
        assert hasattr(runner, "_record_iteration")
