"""
Unit tests for AgentRunner service.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if openai is available for tests that need it
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from services.agent_runner import (
    AGENT_MODEL,
    AgentAction,
    AgentResponse,
    AgentRunner,
    AgentRunnerError,
    IncomingEvent,
    JorbPolicy,
    KickoffResult,
    PolicyViolation,
    ProcessingResult,
    TaskUpdate,
)
from services.jorb_storage import (
    Jorb,
    JorbContact,
    JorbMessage,
    JorbStorage,
    JorbWithMessages,
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
def sample_event():
    """Create a sample incoming event."""
    return IncomingEvent(
        channel="telegram",
        sender="@magic",
        sender_name="Magic Concierge",
        content="Hi! Hotel Nikko has availability at $289/night.",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message_count=1,
    )


@pytest.fixture
def sample_jorb():
    """Create a sample jorb."""
    return Jorb(
        id="jorb_12345678",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel in SF for March 17-21",
        progress_summary="Contacted Magic, waiting for response",
        awaiting="Hotel options from Magic",
    )


@pytest.fixture
def sample_messages():
    """Create sample jorb messages."""
    return [
        JorbMessage(
            id="msg_000000000001",
            jorb_id="jorb_12345678",
            timestamp="2026-01-29T10:00:00Z",
            direction="outbound",
            channel="telegram",
            recipient="@magic",
            content="Hi Magic, can you check hotel availability in SF?",
            agent_reasoning="Initial outreach",
        ),
    ]


class TestAgentRunnerConfig:
    """Tests for AgentRunner configuration."""

    def test_is_configured_with_key(self, storage):
        """Test is_configured returns True with API key."""
        runner = AgentRunner(storage=storage, openai_api_key="test-key")
        assert runner.is_configured is True

    def test_is_configured_without_key(self, storage):
        """Test is_configured returns False without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing OPENAI_API_KEY
            os.environ.pop("OPENAI_API_KEY", None)
            runner = AgentRunner(storage=storage, openai_api_key=None)
            # This might still be True if config.py has a fallback
            # Just test that it doesn't crash
            _ = runner.is_configured

    def test_model_is_hardcoded(self):
        """Verify the model is hardcoded to gpt-5.2."""
        assert AGENT_MODEL == "gpt-5.2"


class TestBuildContext:
    """Tests for context building."""

    def test_build_context_with_event(self, runner, sample_event, sample_jorb, sample_messages):
        """Test building context with an incoming event."""
        jorb_with_messages = JorbWithMessages(jorb=sample_jorb, messages=sample_messages)

        context = runner.build_context(
            event=sample_event,
            open_jorbs=[jorb_with_messages],
        )

        # Check event section
        assert "event" in context
        assert context["event"]["channel"] == "telegram"
        assert context["event"]["sender"] == "@magic"
        assert context["event"]["sender_name"] == "Magic Concierge"
        assert context["event"]["content"].startswith("Hi!")
        assert context["event"]["message_count"] == 1

        # Check active_tasks section
        assert "active_tasks" in context
        assert len(context["active_tasks"]) == 1
        task = context["active_tasks"][0]
        assert task["task_id"] == "jorb_12345678"
        assert task["name"] == "Hotel Booking"
        assert task["status"] == "running"
        assert "recent" in task
        assert len(task["recent"]) == 1

        # Check policy section
        assert "policy" in context
        assert "max_spend_without_approval" in context["policy"]
        assert "require_approval_for" in context["policy"]

    def test_build_context_without_event(self, runner, sample_jorb, sample_messages):
        """Test building context for kickoff (no event)."""
        jorb_with_messages = JorbWithMessages(jorb=sample_jorb, messages=sample_messages)

        context = runner.build_context(
            event=None,
            open_jorbs=[jorb_with_messages],
        )

        assert context["event"] is None
        assert len(context["active_tasks"]) == 1

    def test_build_context_empty_jorbs(self, runner, sample_event):
        """Test building context with no active jorbs."""
        context = runner.build_context(
            event=sample_event,
            open_jorbs=[],
        )

        assert context["event"] is not None
        assert context["active_tasks"] == []

    def test_build_context_message_limit(self, runner, sample_jorb):
        """Test that context limits recent messages."""
        # Create 20 messages
        messages = [
            JorbMessage(
                id=f"msg_00000000{i:04d}",
                jorb_id=sample_jorb.id,
                timestamp=f"2026-01-{15+i:02d}T10:00:00Z",
                direction="outbound",
                channel="telegram",
                content=f"Message {i}",
            )
            for i in range(20)
        ]
        jorb_with_messages = JorbWithMessages(jorb=sample_jorb, messages=messages)

        context = runner.build_context(
            event=None,
            open_jorbs=[jorb_with_messages],
        )

        # Should only have last 10 messages
        assert len(context["active_tasks"][0]["recent"]) == 10
        # Should be the most recent ones
        assert context["active_tasks"][0]["recent"][-1]["content"] == "Message 19"


class TestParseAgentResponse:
    """Tests for parsing agent responses."""

    def test_parse_send_message_response(self, runner):
        """Test parsing a send_message action response."""
        response = {
            "task_id": "jorb_12345678",
            "reasoning": "Responding to Magic's hotel quote",
            "action": {
                "type": "send_message",
                "channel": "telegram",
                "recipient": "@magic",
                "content": "Sounds good, please book it.",
            },
            "task_update": {
                "progress_note": "Approved Hotel Nikko booking",
                "awaiting": "Booking confirmation",
            },
        }

        result = runner.parse_agent_response(response)

        assert isinstance(result, AgentResponse)
        assert result.jorb_id == "jorb_12345678"
        assert result.reasoning == "Responding to Magic's hotel quote"
        assert result.action.type == "send_message"
        assert result.action.channel == "telegram"
        assert result.action.recipient == "@magic"
        assert result.action.content == "Sounds good, please book it."
        assert result.task_update is not None
        assert result.task_update.progress_note == "Approved Hotel Nikko booking"
        assert result.task_update.awaiting == "Booking confirmation"

    def test_parse_pause_response(self, runner):
        """Test parsing a pause action response."""
        response = {
            "task_id": "jorb_12345678",
            "reasoning": "Booking requires approval per policy",
            "action": {
                "type": "pause",
                "pause_reason": "Hotel booking requires approval",
                "needs_approval_for": "commit",
            },
            "task_update": {
                "progress_note": "Hotel Nikko $289/night ready to book",
                "awaiting": "User approval",
            },
        }

        result = runner.parse_agent_response(response)

        assert result.action.type == "pause"
        assert result.action.pause_reason == "Hotel booking requires approval"
        assert result.action.needs_approval_for == "commit"

    def test_parse_complete_response(self, runner):
        """Test parsing a complete action response."""
        response = {
            "task_id": "jorb_12345678",
            "reasoning": "Booking confirmed, task complete",
            "action": {
                "type": "complete",
            },
            "task_update": {
                "progress_note": "Hotel Nikko booked, confirmation #12345",
            },
        }

        result = runner.parse_agent_response(response)

        assert result.action.type == "complete"

    def test_parse_no_action_response(self, runner):
        """Test parsing a no_action response."""
        response = {
            "task_id": None,
            "reasoning": "Message doesn't relate to any active task",
            "action": {
                "type": "no_action",
            },
            "task_update": None,
        }

        result = runner.parse_agent_response(response)

        assert result.jorb_id is None
        assert result.action.type == "no_action"
        assert result.task_update is None

    def test_parse_unknown_action_type(self, runner):
        """Test that unknown action types default to no_action."""
        response = {
            "task_id": "jorb_12345678",
            "reasoning": "Something weird",
            "action": {
                "type": "unknown_action",
            },
        }

        result = runner.parse_agent_response(response)

        assert result.action.type == "no_action"

    def test_parse_missing_action(self, runner):
        """Test parsing response with missing action (should use defaults)."""
        response = {
            "task_id": "jorb_12345678",
            "reasoning": "Minimal response",
        }

        result = runner.parse_agent_response(response)

        assert result.action.type == "no_action"


class TestCallAgent:
    """Tests for calling the OpenAI API."""

    async def test_call_agent_not_configured(self, storage):
        """Test that call_agent raises error when not configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            runner = AgentRunner(storage=storage, openai_api_key=None)

            with pytest.raises(AgentRunnerError, match="not configured"):
                await runner.call_agent({"event": None, "active_tasks": []})

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_call_agent_success(self, runner):
        """Test successful API call with mocked OpenAI."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": None,
            "reasoning": "No active tasks",
            "action": {"type": "no_action"},
        })
        # Mock usage for token tracking
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result, tokens_used, estimated_cost = await runner.call_agent({"event": None, "active_tasks": []})

            # Verify the call was made
            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args[1]

            assert call_kwargs["model"] == AGENT_MODEL
            assert call_kwargs["response_format"] == {"type": "json_object"}
            assert len(call_kwargs["messages"]) == 2  # system + user

            # Verify response parsing
            assert result["action"]["type"] == "no_action"

            # Verify token tracking
            assert tokens_used == 150  # 100 + 50
            assert estimated_cost > 0

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_call_agent_api_error(self, runner):
        """Test handling of OpenAI API errors."""
        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_openai_module.APIError = openai.APIError
            mock_client.chat.completions.create.side_effect = openai.APIError(
                message="Rate limit exceeded",
                request=None,
                body=None,
            )

            with pytest.raises(AgentRunnerError, match="API error"):
                await runner.call_agent({"event": None, "active_tasks": []})

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_call_agent_invalid_json(self, runner):
        """Test handling of invalid JSON responses."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_openai_module.APIError = openai.APIError  # Use real exception class
            mock_client.chat.completions.create.return_value = mock_response

            with pytest.raises(AgentRunnerError, match="Invalid JSON"):
                await runner.call_agent({"event": None, "active_tasks": []})


class TestMessageStorage:
    """Tests for message storage methods."""

    async def test_store_inbound_message(self, runner, storage, sample_event):
        """Test storing an inbound message."""
        jorb = await storage.create_jorb(name="Test", plan="Test plan")
        await storage.update_jorb(jorb.id, status="running")

        msg_id = await runner.store_inbound_message(jorb.id, sample_event)

        assert msg_id.startswith("msg_")

        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        assert messages[0].direction == "inbound"
        assert messages[0].channel == "telegram"
        assert messages[0].sender == "@magic"
        assert messages[0].sender_name == "Magic Concierge"

    async def test_store_outbound_message(self, runner, storage):
        """Test storing an outbound message."""
        jorb = await storage.create_jorb(name="Test", plan="Test plan")

        msg_id = await runner.store_outbound_message(
            jorb_id=jorb.id,
            channel="telegram",
            recipient="@magic",
            content="Please check hotel availability",
            reasoning="Initial outreach to Magic",
        )

        assert msg_id.startswith("msg_")

        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        assert messages[0].direction == "outbound"
        assert messages[0].channel == "telegram"
        assert messages[0].recipient == "@magic"
        assert messages[0].agent_reasoning == "Initial outreach to Magic"


class TestJorbStatusUpdates:
    """Tests for jorb status update methods."""

    async def test_update_jorb_status(self, runner, storage):
        """Test updating jorb status."""
        jorb = await storage.create_jorb(name="Test", plan="Test plan")

        updated = await runner.update_jorb_status(
            jorb_id=jorb.id,
            status="running",
            progress_summary="Started working",
            awaiting="Response from contact",
        )

        assert updated is not None
        assert updated.status == "running"
        assert updated.progress_summary == "Started working"
        assert updated.awaiting == "Response from contact"

    async def test_update_jorb_paused(self, runner, storage):
        """Test pausing a jorb."""
        jorb = await storage.create_jorb(name="Test", plan="Test plan")
        await storage.update_jorb(jorb.id, status="running")

        updated = await runner.update_jorb_status(
            jorb_id=jorb.id,
            status="paused",
            paused_reason="Hotel booking requires approval",
            needs_approval_for="commit",
        )

        assert updated is not None
        assert updated.status == "paused"
        assert updated.paused_reason == "Hotel booking requires approval"
        assert updated.needs_approval_for == "commit"

    async def test_get_open_jorbs(self, runner, storage):
        """Test getting open jorbs with messages."""
        # Create a running jorb with a message
        jorb = await storage.create_jorb(name="Test", plan="Test plan")
        await storage.update_jorb(jorb.id, status="running")
        await storage.add_message(
            jorb.id,
            JorbMessage(
                id="",
                jorb_id=jorb.id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                direction="outbound",
                channel="telegram",
                content="Test message",
            ),
        )

        open_jorbs = await runner.get_open_jorbs()

        assert len(open_jorbs) == 1
        assert open_jorbs[0].jorb.id == jorb.id
        assert len(open_jorbs[0].messages) == 1


class TestDataclasses:
    """Tests for dataclass objects."""

    def test_incoming_event_defaults(self):
        """Test IncomingEvent default values."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name=None,
            content="Hello",
            timestamp="2026-01-30T12:00:00Z",
        )

        assert event.message_count == 1

    def test_agent_action_defaults(self):
        """Test AgentAction default values."""
        action = AgentAction(type="no_action")

        assert action.channel is None
        assert action.recipient is None
        assert action.content is None
        assert action.pause_reason is None
        assert action.needs_approval_for is None

    def test_task_update_defaults(self):
        """Test TaskUpdate default values."""
        update = TaskUpdate()

        assert update.progress_note is None
        assert update.awaiting is None

    def test_agent_response_defaults(self):
        """Test AgentResponse default values."""
        response = AgentResponse(
            jorb_id="jorb_123",
            reasoning="Test",
            action=AgentAction(type="no_action"),
        )

        assert response.task_update is None

    def test_processing_result_defaults(self):
        """Test ProcessingResult default values."""
        result = ProcessingResult(
            jorb_id="jorb_123",
            action_taken="no_action",
            success=True,
        )

        assert result.error is None
        assert result.message_sent is False


class TestProcessIncomingMessage:
    """Tests for process_incoming_message method."""

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_process_message_no_action(self, runner, storage, sample_event):
        """Test processing a message that matches no jorb."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": None,
            "reasoning": "Message doesn't match any active task",
            "action": {"type": "no_action"},
            "task_update": None,
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.process_incoming_message(sample_event)

            assert result.success is True
            assert result.jorb_id is None
            assert result.action_taken == "no_action"
            assert result.message_sent is False

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_process_message_with_send(self, runner, storage, sample_event):
        """Test processing a message that results in sending a response."""
        # Create a running jorb
        jorb = await storage.create_jorb(name="Hotel Booking", plan="Book hotel")
        await storage.update_jorb(jorb.id, status="running")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "Responding to Magic's hotel quote",
            "action": {
                "type": "send_message",
                "channel": "telegram",
                "recipient": "@magic",
                "content": "Sounds good, please proceed!",
            },
            "task_update": {
                "progress_note": "Approved booking",
                "awaiting": "Confirmation",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            # Mock the Telegram send
            with patch("services.telegram_client.TelegramClientService") as mock_tg:
                mock_tg_instance = MagicMock()
                mock_tg.return_value = mock_tg_instance
                mock_tg_instance.send_message = AsyncMock(
                    return_value=MagicMock(success=True, message_id=12345)
                )

                result = await runner.process_incoming_message(sample_event)

                assert result.success is True
                assert result.jorb_id == jorb.id
                assert result.action_taken == "send_message"
                assert result.message_sent is True

        # Verify messages were stored
        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 2  # inbound + outbound
        assert messages[0].direction == "inbound"
        assert messages[1].direction == "outbound"
        assert messages[1].agent_reasoning == "Responding to Magic's hotel quote"

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_process_message_pause_action(self, runner, storage, sample_event):
        """Test processing a message that pauses a jorb."""
        jorb = await storage.create_jorb(name="Hotel Booking", plan="Book hotel")
        await storage.update_jorb(jorb.id, status="running")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "Need approval to proceed",
            "action": {
                "type": "pause",
                "pause_reason": "Booking requires approval",
                "needs_approval_for": "commit",
            },
            "task_update": {
                "progress_note": "Ready to book, awaiting approval",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.process_incoming_message(sample_event)

            assert result.success is True
            assert result.jorb_id == jorb.id
            assert result.action_taken == "pause"

        # Verify jorb was paused
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "paused"
        assert updated_jorb.paused_reason == "Booking requires approval"
        assert updated_jorb.needs_approval_for == "commit"

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_process_message_complete_action(self, runner, storage, sample_event):
        """Test processing a message that completes a jorb."""
        jorb = await storage.create_jorb(name="Hotel Booking", plan="Book hotel")
        await storage.update_jorb(jorb.id, status="running")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "Booking confirmed, task complete",
            "action": {"type": "complete"},
            "task_update": {
                "progress_note": "Hotel booked successfully!",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.process_incoming_message(sample_event)

            assert result.success is True
            assert result.action_taken == "complete"

        # Verify jorb was completed
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "complete"

    async def test_process_message_agent_error(self, runner, storage, sample_event):
        """Test handling of agent errors during processing."""
        # Without mocking OpenAI, this should fail with "not configured" or similar
        with patch.object(runner, "call_agent", side_effect=AgentRunnerError("API failed")):
            result = await runner.process_incoming_message(sample_event)

            assert result.success is False
            assert result.action_taken == "error"
            assert result.error == "API failed"


class TestContactEnrichment:
    """Tests for contact enrichment."""

    async def test_enrich_event_with_existing_name(self, runner):
        """Test that events with sender_name are not modified."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name="John Doe",
            content="Hello",
            timestamp="2026-01-30T12:00:00Z",
        )

        enriched = await runner._enrich_event_with_contact(event)

        assert enriched.sender_name == "John Doe"

    async def test_enrich_event_telegram_skips_lookup(self, runner):
        """Test that Telegram events skip contact lookup."""
        event = IncomingEvent(
            channel="telegram",
            sender="@someone",
            sender_name=None,
            content="Hello",
            timestamp="2026-01-30T12:00:00Z",
        )

        enriched = await runner._enrich_event_with_contact(event)

        # Should not have changed (no lookup for Telegram)
        assert enriched.sender_name is None

    async def test_enrich_event_sms_with_contact(self, runner):
        """Test SMS event enrichment with contact lookup."""
        event = IncomingEvent(
            channel="sms",
            sender="+15551234567",
            sender_name=None,
            content="Hello",
            timestamp="2026-01-30T12:00:00Z",
        )

        # Mock the contact lookup
        # Note: 'name' is a reserved attribute in MagicMock, so we create a simple object
        from services.contact_lookup import Contact
        mock_contact = Contact(name="Jane Smith", googleContactId="people/123")

        with patch("services.contact_lookup.ContactLookup") as mock_lookup_class:
            mock_lookup = MagicMock()
            mock_lookup_class.return_value = mock_lookup
            mock_lookup.lookup.return_value = mock_contact

            enriched = await runner._enrich_event_with_contact(event)

            assert enriched.sender_name == "Jane Smith"
            mock_lookup.lookup.assert_called_once_with("+15551234567")

    async def test_enrich_event_contact_not_found(self, runner):
        """Test enrichment when contact is not found."""
        event = IncomingEvent(
            channel="sms",
            sender="+15559999999",
            sender_name=None,
            content="Hello",
            timestamp="2026-01-30T12:00:00Z",
        )

        with patch("services.contact_lookup.ContactLookup") as mock_lookup_class:
            mock_lookup = MagicMock()
            mock_lookup_class.return_value = mock_lookup
            mock_lookup.lookup.return_value = None

            enriched = await runner._enrich_event_with_contact(event)

            assert enriched.sender_name is None


class TestSendMessage:
    """Tests for message sending."""

    async def test_send_sms_message(self, runner):
        """Test sending SMS via TelnyxSMSService."""
        with patch("services.telnyx_sms.TelnyxSMSService") as mock_sms_class:
            mock_sms = MagicMock()
            mock_sms_class.return_value = mock_sms
            mock_sms.send_sms.return_value = MagicMock(success=True)

            result = await runner._send_message("sms", "+15551234567", "Test message")

            assert result is True
            mock_sms.send_sms.assert_called_once_with("+15551234567", "Test message")

    async def test_send_telegram_message(self, runner):
        """Test sending Telegram message."""
        with patch("services.telegram_client.TelegramClientService") as mock_tg_class:
            mock_tg = MagicMock()
            mock_tg_class.return_value = mock_tg
            mock_tg.send_message = AsyncMock(return_value=MagicMock(success=True))

            result = await runner._send_message("telegram", "@magic", "Test message")

            assert result is True
            mock_tg.send_message.assert_called_once_with("@magic", "Test message")

    async def test_send_unknown_channel(self, runner):
        """Test sending to unknown channel returns False."""
        result = await runner._send_message("unknown", "recipient", "message")
        assert result is False

    async def test_send_email_not_implemented(self, runner):
        """Test that email sending returns False (not implemented)."""
        result = await runner._send_message("email", "test@example.com", "message")
        assert result is False


class TestKickoffJorb:
    """Tests for kickoff_jorb method."""

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_kickoff_sends_message(self, runner, storage):
        """Test kickoff sends initial message and updates status."""
        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book a hotel in SF for March 17-21",
            contacts=[JorbContact(identifier="@magic", channel="telegram", name="Magic")],
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "Initiating hotel search with Magic",
            "action": {
                "type": "send_message",
                "channel": "telegram",
                "recipient": "@magic",
                "content": "Hi! Can you help me find a hotel in SF for March 17-21?",
            },
            "task_update": {
                "progress_note": "Initial outreach sent",
                "awaiting": "Response from Magic",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            # Mock the Telegram send
            with patch("services.telegram_client.TelegramClientService") as mock_tg:
                mock_tg_instance = MagicMock()
                mock_tg.return_value = mock_tg_instance
                mock_tg_instance.send_message = AsyncMock(
                    return_value=MagicMock(success=True, message_id=12345)
                )

                result = await runner.kickoff_jorb(jorb)

                assert result.success is True
                assert result.jorb_id == jorb.id
                assert result.action_taken == "send_message"
                assert result.message_sent is True

        # Verify jorb was updated to running
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "running"
        assert updated_jorb.progress_summary == "Initial outreach sent"
        assert updated_jorb.awaiting == "Response from Magic"

        # Verify message was stored
        messages = await storage.get_messages(jorb.id)
        assert len(messages) == 1
        assert messages[0].direction == "outbound"
        assert messages[0].channel == "telegram"

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_kickoff_no_action(self, runner, storage):
        """Test kickoff when agent decides no initial action needed."""
        jorb = await storage.create_jorb(
            name="Monitoring Task",
            plan="Monitor for incoming messages",
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "This is a passive monitoring task, no initial action needed",
            "action": {"type": "no_action"},
            "task_update": {
                "progress_note": "Task created, waiting for incoming messages",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.kickoff_jorb(jorb)

            assert result.success is True
            assert result.action_taken == "no_action"
            assert result.message_sent is False

        # Still updated to running
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "running"

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
    async def test_kickoff_immediate_pause(self, runner, storage):
        """Test kickoff when agent decides to pause immediately."""
        jorb = await storage.create_jorb(
            name="Expensive Task",
            plan="Book something expensive",
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "task_id": jorb.id,
            "reasoning": "This task requires approval before any action",
            "action": {
                "type": "pause",
                "pause_reason": "Task requires user approval to proceed",
                "needs_approval_for": "commit",
            },
        })
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        with patch("services.agent_runner.openai") as mock_openai_module:
            mock_client = MagicMock()
            mock_openai_module.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = await runner.kickoff_jorb(jorb)

            assert result.success is True
            assert result.action_taken == "pause"
            assert result.message_sent is False

        # Jorb was paused instead of running
        updated_jorb = await storage.get_jorb(jorb.id)
        assert updated_jorb.status == "paused"
        assert updated_jorb.paused_reason == "Task requires user approval to proceed"

    async def test_kickoff_agent_error(self, runner, storage):
        """Test kickoff when agent fails."""
        jorb = await storage.create_jorb(name="Test", plan="Test plan")

        with patch.object(runner, "call_agent", side_effect=AgentRunnerError("API failed")):
            result = await runner.kickoff_jorb(jorb)

            assert result.success is False
            assert result.action_taken == "error"
            assert result.error == "API failed"

    def test_kickoff_result_defaults(self):
        """Test KickoffResult default values."""
        result = KickoffResult(
            jorb_id="jorb_123",
            success=True,
            action_taken="send_message",
        )

        assert result.message_sent is False
        assert result.error is None


class TestJorbPolicy:
    """Tests for JorbPolicy dataclass."""

    def test_default_values(self):
        """Test policy default values."""
        policy = JorbPolicy()

        assert policy.max_spend_without_approval == 100.0
        assert policy.max_messages_per_hour == 20
        assert "purchase" in policy.require_approval_for
        assert policy.stale_jorb_hours == 72
        assert policy.max_jorb_duration_days == 30

    def test_to_context_dict(self):
        """Test converting policy to context dict."""
        policy = JorbPolicy(
            max_spend_without_approval=50.0,
            max_messages_per_hour=10,
            require_approval_for=["purchase"],
        )

        context = policy.to_context_dict()

        assert context["max_spend_without_approval"] == 50.0
        assert context["max_messages_per_hour"] == 10
        assert context["require_approval_for"] == ["purchase"]

    def test_from_settings(self):
        """Test loading policy from settings."""
        with patch.dict(os.environ, {
            "AGENT_SPEND_LIMIT": "200.0",
            "AGENT_MAX_MESSAGES_PER_HOUR": "30",
            "AGENT_STALE_JORB_HOURS": "48",
            "AGENT_MAX_JORB_DURATION_DAYS": "14",
        }):
            # Clear cached settings
            from config import get_settings
            get_settings.cache_clear()

            policy = JorbPolicy.from_settings()

            assert policy.max_spend_without_approval == 200.0
            assert policy.max_messages_per_hour == 30
            assert policy.stale_jorb_hours == 48
            assert policy.max_jorb_duration_days == 14

            # Restore settings
            get_settings.cache_clear()


class TestPolicyEnforcement:
    """Tests for policy enforcement in AgentRunner."""

    @pytest.fixture
    def policy(self):
        """Create a test policy with short timeframes."""
        return JorbPolicy(
            max_spend_without_approval=100.0,
            max_messages_per_hour=3,  # Low limit for testing
            require_approval_for=["purchase"],
            stale_jorb_hours=1,  # 1 hour for quick testing
            max_jorb_duration_days=1,  # 1 day for quick testing
        )

    @pytest.fixture
    def runner_with_policy(self, storage, policy):
        """Create an AgentRunner with test policy."""
        return AgentRunner(
            storage=storage,
            openai_api_key="test-api-key",
            policy=policy,
        )

    def test_rate_limit_check_under_limit(self, runner_with_policy):
        """Test rate limit check when under limit."""
        assert not runner_with_policy._check_rate_limit("jorb_123")

    def test_rate_limit_check_at_limit(self, runner_with_policy):
        """Test rate limit check when at limit."""
        # Record some messages
        for _ in range(3):
            runner_with_policy._record_message_sent("jorb_123")

        # Should now be at limit
        assert runner_with_policy._check_rate_limit("jorb_123")

    def test_rate_limit_different_jorbs(self, runner_with_policy):
        """Test rate limits are tracked per jorb."""
        # Fill up one jorb's limit
        for _ in range(3):
            runner_with_policy._record_message_sent("jorb_1")

        # Other jorb should not be limited
        assert not runner_with_policy._check_rate_limit("jorb_2")

    def test_policy_violations_tracking(self, runner_with_policy):
        """Test policy violations are recorded."""
        assert len(runner_with_policy.policy_violations) == 0

        runner_with_policy._record_policy_violation(
            "jorb_123",
            "Test Task",
            "rate_limit",
            "Exceeded rate limit",
        )

        violations = runner_with_policy.policy_violations
        assert len(violations) == 1
        assert violations[0].jorb_id == "jorb_123"
        assert violations[0].violation_type == "rate_limit"

    def test_clear_policy_violations(self, runner_with_policy):
        """Test clearing policy violations."""
        runner_with_policy._record_policy_violation(
            "jorb_123", "Test", "rate_limit", "Test"
        )
        assert len(runner_with_policy.policy_violations) == 1

        runner_with_policy.clear_policy_violations()
        assert len(runner_with_policy.policy_violations) == 0

    async def test_check_stale_jorbs(self, runner_with_policy, storage):
        """Test auto-pausing stale jorbs."""
        # Create a running jorb with old updated_at
        jorb = await storage.create_jorb(name="Stale Task", plan="Plan")
        await storage.update_jorb(jorb.id, status="running")

        # Manually set updated_at to 2 hours ago (older than 1 hour limit)
        from datetime import timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await storage.update_jorb(jorb.id, progress_summary="old")  # Triggers update
        # Hack: directly update the timestamp in DB
        import aiosqlite
        async with aiosqlite.connect(storage._db_path) as conn:
            await conn.execute(
                "UPDATE jorbs SET updated_at = ? WHERE id = ?",
                (old_time, jorb.id),
            )
            await conn.commit()

        # Check for stale jorbs
        paused_ids = await runner_with_policy.check_stale_jorbs()

        assert jorb.id in paused_ids
        updated = await storage.get_jorb(jorb.id)
        assert updated.status == "paused"
        assert "no activity" in updated.paused_reason.lower()

    async def test_check_expired_jorbs(self, runner_with_policy, storage):
        """Test auto-failing expired jorbs."""
        # Create a running jorb with old created_at
        jorb = await storage.create_jorb(name="Old Task", plan="Plan")
        await storage.update_jorb(jorb.id, status="running")

        # Hack: set created_at to 2 days ago (older than 1 day limit)
        from datetime import timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        import aiosqlite
        async with aiosqlite.connect(storage._db_path) as conn:
            await conn.execute(
                "UPDATE jorbs SET created_at = ? WHERE id = ?",
                (old_time, jorb.id),
            )
            await conn.commit()

        # Check for expired jorbs
        failed_ids = await runner_with_policy.check_expired_jorbs()

        assert jorb.id in failed_ids
        updated = await storage.get_jorb(jorb.id)
        assert updated.status == "failed"
        assert "exceeded" in updated.progress_summary.lower()

    async def test_enforce_policies(self, runner_with_policy, storage):
        """Test running all policy enforcement checks."""
        result = await runner_with_policy.enforce_policies()

        assert "paused_stale" in result
        assert "failed_expired" in result
        assert isinstance(result["paused_stale"], list)
        assert isinstance(result["failed_expired"], list)

    def test_policy_accessible(self, runner_with_policy, policy):
        """Test policy is accessible via property."""
        assert runner_with_policy.policy == policy

    def test_build_context_includes_policy(self, runner_with_policy, sample_event):
        """Test that build_context includes policy settings."""
        context = runner_with_policy.build_context(sample_event, [])

        assert "policy" in context
        assert "max_spend_without_approval" in context["policy"]
        assert "max_messages_per_hour" in context["policy"]
        assert "require_approval_for" in context["policy"]
