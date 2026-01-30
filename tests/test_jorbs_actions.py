"""
Unit tests for jorbs actions.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from actions.jorbs import (
    approve_jorb_action,
    brief_me_action,
    cancel_jorb_action,
    create_jorb_action,
    get_jorb_action,
    get_jorb_messages_action,
    list_jorbs_action,
    _BRIEFING_STATE_FILE,
)
from services.jorb_storage import JorbContact, JorbMessage, JorbStorage


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
def mock_storage(temp_db_path):
    """Create a mock-patched storage for testing."""
    with patch("actions.jorbs.JorbStorage") as mock_class:
        storage = JorbStorage(db_path=temp_db_path)
        mock_class.return_value = storage
        yield storage


class TestCreateJorbAction:
    """Tests for create_jorb_action."""

    async def test_create_minimal(self, mock_storage):
        """Test creating a jorb with minimal fields."""
        result = await create_jorb_action({
            "name": "Test Task",
            "plan": "Do the thing",
            "start_immediately": False,
        })

        assert result["name"] == "Test Task"
        assert result["plan"] == "Do the thing"
        assert result["status"] == "planning"
        assert result["jorb_id"].startswith("jorb_")
        assert "kickoff" not in result  # Not kicked off

    async def test_create_with_contacts_json(self, mock_storage):
        """Test creating a jorb with contacts as JSON string."""
        contacts = [
            {"identifier": "@magic", "channel": "telegram", "name": "Magic"},
            {"identifier": "+15551234567", "channel": "sms"},
        ]

        result = await create_jorb_action({
            "name": "Hotel Booking",
            "plan": "Book a hotel",
            "contacts": json.dumps(contacts),
            "start_immediately": False,
        })

        assert len(result["contacts"]) == 2
        assert result["contacts"][0]["identifier"] == "@magic"
        assert result["contacts"][0]["channel"] == "telegram"
        assert result["contacts"][0]["name"] == "Magic"
        assert result["contacts"][1]["identifier"] == "+15551234567"
        assert result["contacts"][1]["channel"] == "sms"

    async def test_create_with_contacts_list(self, mock_storage):
        """Test creating a jorb with contacts as list."""
        contacts = [
            {"identifier": "@magic", "channel": "telegram"},
        ]

        result = await create_jorb_action({
            "name": "Test",
            "plan": "Test plan",
            "contacts": contacts,
            "start_immediately": False,
        })

        assert len(result["contacts"]) == 1

    async def test_create_missing_name(self, mock_storage):
        """Test that missing name raises error."""
        with pytest.raises(ValueError, match="name is required"):
            await create_jorb_action({"plan": "Do something"})

    async def test_create_missing_plan(self, mock_storage):
        """Test that missing plan raises error."""
        with pytest.raises(ValueError, match="plan is required"):
            await create_jorb_action({"name": "Test"})

    async def test_create_invalid_contacts_json(self, mock_storage):
        """Test that invalid contacts JSON raises error."""
        with pytest.raises(ValueError, match="valid JSON"):
            await create_jorb_action({
                "name": "Test",
                "plan": "Plan",
                "contacts": "not valid json",
                "start_immediately": False,
            })

    async def test_create_contacts_missing_identifier(self, mock_storage):
        """Test that contacts without identifier raises error."""
        with pytest.raises(ValueError, match="missing 'identifier'"):
            await create_jorb_action({
                "name": "Test",
                "plan": "Plan",
                "contacts": [{"channel": "sms"}],
                "start_immediately": False,
            })

    async def test_create_contacts_invalid_channel(self, mock_storage):
        """Test that contacts with invalid channel raises error."""
        with pytest.raises(ValueError, match="invalid channel"):
            await create_jorb_action({
                "name": "Test",
                "plan": "Plan",
                "contacts": [{"identifier": "test", "channel": "invalid"}],
                "start_immediately": False,
            })

    async def test_create_with_kickoff_no_openai(self, mock_storage):
        """Test creating with kickoff when OpenAI not configured."""
        with patch("actions.jorbs.AgentRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner_class.return_value = mock_runner
            mock_runner.is_configured = False

            result = await create_jorb_action({
                "name": "Test",
                "plan": "Plan",
                "start_immediately": True,
            })

            assert "kickoff" in result
            assert result["kickoff"]["success"] is False
            assert "not configured" in result["kickoff"]["error"]


class TestListJorbsAction:
    """Tests for list_jorbs_action."""

    async def test_list_all(self, mock_storage):
        """Test listing all jorbs."""
        # Create some jorbs
        await mock_storage.create_jorb("Task 1", "Plan 1")
        await mock_storage.create_jorb("Task 2", "Plan 2")
        await mock_storage.create_jorb("Task 3", "Plan 3")

        result = await list_jorbs_action({"status": "all"})

        assert result["count"] == 3
        assert len(result["jorbs"]) == 3
        assert result["status_filter"] == "all"

    async def test_list_open(self, mock_storage):
        """Test listing open jorbs."""
        jorb1 = await mock_storage.create_jorb("Planning", "Plan")
        jorb2 = await mock_storage.create_jorb("Running", "Plan")
        jorb3 = await mock_storage.create_jorb("Complete", "Plan")

        await mock_storage.update_jorb(jorb2.id, status="running")
        await mock_storage.update_jorb(jorb3.id, status="complete")

        result = await list_jorbs_action({"status": "open"})

        # planning and running are open
        assert result["count"] == 2
        statuses = {j["status"] for j in result["jorbs"]}
        assert statuses == {"planning", "running"}

    async def test_list_closed(self, mock_storage):
        """Test listing closed jorbs."""
        jorb1 = await mock_storage.create_jorb("Complete", "Plan")
        jorb2 = await mock_storage.create_jorb("Running", "Plan")

        await mock_storage.update_jorb(jorb1.id, status="complete")
        await mock_storage.update_jorb(jorb2.id, status="running")

        result = await list_jorbs_action({"status": "closed"})

        assert result["count"] == 1
        assert result["jorbs"][0]["status"] == "complete"

    async def test_list_default_open(self, mock_storage):
        """Test that default status filter is 'open'."""
        result = await list_jorbs_action({})

        assert result["status_filter"] == "open"

    async def test_list_invalid_status(self, mock_storage):
        """Test that invalid status raises error."""
        with pytest.raises(ValueError, match="must be 'open', 'closed', or 'all'"):
            await list_jorbs_action({"status": "invalid"})


class TestGetJorbAction:
    """Tests for get_jorb_action."""

    async def test_get_jorb(self, mock_storage):
        """Test getting a jorb by ID."""
        jorb = await mock_storage.create_jorb("Test Task", "Test plan")

        result = await get_jorb_action({"jorb_id": jorb.id})

        assert result["jorb_id"] == jorb.id
        assert result["name"] == "Test Task"
        assert result["plan"] == "Test plan"
        assert result["status"] == "planning"
        assert "messages" not in result

    async def test_get_jorb_with_messages(self, mock_storage):
        """Test getting a jorb with message history."""
        jorb = await mock_storage.create_jorb("Test Task", "Test plan")

        # Add some messages
        await mock_storage.add_message(
            jorb.id,
            JorbMessage(
                id="",
                jorb_id=jorb.id,
                timestamp="2026-01-30T10:00:00Z",
                direction="outbound",
                channel="telegram",
                recipient="@magic",
                content="Hello!",
            ),
        )

        result = await get_jorb_action({
            "jorb_id": jorb.id,
            "include_messages": True,
        })

        assert "messages" in result
        assert result["message_count"] == 1
        assert result["messages"][0]["content"] == "Hello!"

    async def test_get_jorb_not_found(self, mock_storage):
        """Test getting a non-existent jorb raises error."""
        with pytest.raises(ValueError, match="Jorb not found"):
            await get_jorb_action({"jorb_id": "jorb_nonexistent"})

    async def test_get_jorb_missing_id(self, mock_storage):
        """Test that missing jorb_id raises error."""
        with pytest.raises(ValueError, match="jorb_id is required"):
            await get_jorb_action({})


class TestGetJorbMessagesAction:
    """Tests for get_jorb_messages_action."""

    async def test_get_messages(self, mock_storage):
        """Test getting messages for a jorb."""
        jorb = await mock_storage.create_jorb("Test", "Plan")

        for i in range(5):
            await mock_storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=f"2026-01-30T10:0{i}:00Z",
                    direction="outbound",
                    channel="telegram",
                    content=f"Message {i}",
                ),
            )

        result = await get_jorb_messages_action({"jorb_id": jorb.id})

        assert result["jorb_id"] == jorb.id
        assert result["count"] == 5
        assert len(result["messages"]) == 5

    async def test_get_messages_with_limit(self, mock_storage):
        """Test getting messages with limit."""
        jorb = await mock_storage.create_jorb("Test", "Plan")

        for i in range(10):
            await mock_storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=f"2026-01-30T10:{i:02d}:00Z",
                    direction="outbound",
                    channel="telegram",
                    content=f"Message {i}",
                ),
            )

        result = await get_jorb_messages_action({
            "jorb_id": jorb.id,
            "limit": 5,
        })

        assert result["count"] == 5
        assert result["limit"] == 5

    async def test_get_messages_with_offset(self, mock_storage):
        """Test getting messages with offset."""
        jorb = await mock_storage.create_jorb("Test", "Plan")

        for i in range(10):
            await mock_storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=f"2026-01-30T10:{i:02d}:00Z",
                    direction="outbound",
                    channel="telegram",
                    content=f"Message {i}",
                ),
            )

        result = await get_jorb_messages_action({
            "jorb_id": jorb.id,
            "offset": 5,
            "limit": 3,
        })

        assert result["count"] == 3
        assert result["offset"] == 5
        # Should get messages 5, 6, 7
        assert result["messages"][0]["content"] == "Message 5"

    async def test_get_messages_not_found(self, mock_storage):
        """Test getting messages for non-existent jorb raises error."""
        with pytest.raises(ValueError, match="Jorb not found"):
            await get_jorb_messages_action({"jorb_id": "jorb_nonexistent"})

    async def test_get_messages_missing_id(self, mock_storage):
        """Test that missing jorb_id raises error."""
        with pytest.raises(ValueError, match="jorb_id is required"):
            await get_jorb_messages_action({})


class TestApproveJorbAction:
    """Tests for approve_jorb_action."""

    async def test_approve_paused_jorb(self, mock_storage):
        """Test approving a paused jorb."""
        # Create a paused jorb
        jorb = await mock_storage.create_jorb("Paused Task", "Do something")
        await mock_storage.update_jorb(
            jorb.id,
            status="paused",
            paused_reason="Needs approval for purchase",
            needs_approval_for="purchase",
            progress_summary="Initial progress",
        )

        with patch("actions.jorbs.AgentRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner_class.return_value = mock_runner
            mock_runner.is_configured = False

            result = await approve_jorb_action({
                "jorb_id": jorb.id,
                "decision": "Approved, proceed with purchase",
            })

        assert result["jorb_id"] == jorb.id
        assert result["status"] == "running"
        assert result["decision"] == "Approved, proceed with purchase"
        assert "Approved: Approved, proceed with purchase" in result["progress_summary"]
        assert "Initial progress" in result["progress_summary"]

    async def test_approve_with_agent_kickoff(self, mock_storage):
        """Test approving a jorb triggers agent kickoff."""
        jorb = await mock_storage.create_jorb("Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="paused")

        with patch("actions.jorbs.AgentRunner") as mock_runner_class:
            mock_runner = MagicMock()
            mock_runner_class.return_value = mock_runner
            mock_runner.is_configured = True

            # Mock kickoff result
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.action_taken = "send_message"
            mock_result.message_sent = True
            mock_result.error = None
            mock_runner.kickoff_jorb = AsyncMock(return_value=mock_result)

            result = await approve_jorb_action({
                "jorb_id": jorb.id,
                "decision": "Go ahead",
            })

        assert "agent_result" in result
        assert result["agent_result"]["success"] is True
        assert result["agent_result"]["action_taken"] == "send_message"

    async def test_approve_not_paused(self, mock_storage):
        """Test approving a non-paused jorb raises error."""
        jorb = await mock_storage.create_jorb("Running Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="running")

        with pytest.raises(ValueError, match="not paused"):
            await approve_jorb_action({
                "jorb_id": jorb.id,
                "decision": "Approved",
            })

    async def test_approve_not_found(self, mock_storage):
        """Test approving non-existent jorb raises error."""
        with pytest.raises(ValueError, match="Jorb not found"):
            await approve_jorb_action({
                "jorb_id": "jorb_nonexistent",
                "decision": "Approved",
            })

    async def test_approve_missing_jorb_id(self, mock_storage):
        """Test that missing jorb_id raises error."""
        with pytest.raises(ValueError, match="jorb_id is required"):
            await approve_jorb_action({"decision": "Approved"})

    async def test_approve_missing_decision(self, mock_storage):
        """Test that missing decision raises error."""
        jorb = await mock_storage.create_jorb("Task", "Plan")

        with pytest.raises(ValueError, match="decision is required"):
            await approve_jorb_action({"jorb_id": jorb.id})


class TestCancelJorbAction:
    """Tests for cancel_jorb_action."""

    async def test_cancel_running_jorb(self, mock_storage):
        """Test cancelling a running jorb."""
        jorb = await mock_storage.create_jorb("Running Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="running")

        result = await cancel_jorb_action({
            "jorb_id": jorb.id,
            "reason": "No longer needed",
        })

        assert result["jorb_id"] == jorb.id
        assert result["status"] == "cancelled"
        assert result["reason"] == "No longer needed"
        assert "Cancelled: No longer needed" in result["progress_summary"]

    async def test_cancel_paused_jorb(self, mock_storage):
        """Test cancelling a paused jorb."""
        jorb = await mock_storage.create_jorb("Paused Task", "Plan")
        await mock_storage.update_jorb(
            jorb.id,
            status="paused",
            progress_summary="Was in progress",
        )

        result = await cancel_jorb_action({
            "jorb_id": jorb.id,
            "reason": "Changed my mind",
        })

        assert result["status"] == "cancelled"
        assert "Was in progress" in result["progress_summary"]
        assert "Cancelled: Changed my mind" in result["progress_summary"]

    async def test_cancel_without_reason(self, mock_storage):
        """Test cancelling a jorb without providing a reason."""
        jorb = await mock_storage.create_jorb("Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="running")

        result = await cancel_jorb_action({"jorb_id": jorb.id})

        assert result["status"] == "cancelled"
        assert result["reason"] is None
        assert "Cancelled by user" in result["progress_summary"]

    async def test_cancel_complete_jorb(self, mock_storage):
        """Test cannot cancel a completed jorb."""
        jorb = await mock_storage.create_jorb("Complete Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="complete")

        with pytest.raises(ValueError, match="Cannot cancel jorb with status"):
            await cancel_jorb_action({"jorb_id": jorb.id})

    async def test_cancel_cancelled_jorb(self, mock_storage):
        """Test cannot cancel an already cancelled jorb."""
        jorb = await mock_storage.create_jorb("Cancelled Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="cancelled")

        with pytest.raises(ValueError, match="Cannot cancel jorb with status"):
            await cancel_jorb_action({"jorb_id": jorb.id})

    async def test_cancel_not_found(self, mock_storage):
        """Test cancelling non-existent jorb raises error."""
        with pytest.raises(ValueError, match="Jorb not found"):
            await cancel_jorb_action({"jorb_id": "jorb_nonexistent"})

    async def test_cancel_missing_jorb_id(self, mock_storage):
        """Test that missing jorb_id raises error."""
        with pytest.raises(ValueError, match="jorb_id is required"):
            await cancel_jorb_action({})


class TestBriefMeAction:
    """Tests for brief_me_action."""

    @pytest.fixture(autouse=True)
    def cleanup_briefing_state(self, temp_db_path):
        """Clean up briefing state file before and after each test."""
        # Use temp directory for briefing state
        import actions.jorbs as jorbs_module
        original_state_file = jorbs_module._BRIEFING_STATE_FILE
        temp_state_file = temp_db_path + ".briefing_state.json"
        jorbs_module._BRIEFING_STATE_FILE = temp_state_file
        yield
        # Restore and cleanup
        jorbs_module._BRIEFING_STATE_FILE = original_state_file
        if os.path.exists(temp_state_file):
            os.unlink(temp_state_file)

    async def test_brief_me_empty(self, mock_storage):
        """Test briefing with no jorbs."""
        result = await brief_me_action({})

        assert result["needs_attention"] == 0
        assert result["activity_summary"] == []
        assert result["pending_decisions"] == []
        assert result["total_open_jorbs"] == 0

    async def test_brief_me_with_paused_jorb(self, mock_storage):
        """Test briefing with a paused jorb needing attention."""
        jorb = await mock_storage.create_jorb("Paused Task", "Plan")
        await mock_storage.update_jorb(
            jorb.id,
            status="paused",
            paused_reason="Need approval",
            needs_approval_for="purchase",
        )

        result = await brief_me_action({})

        assert result["needs_attention"] == 1
        assert len(result["pending_decisions"]) == 1
        assert result["pending_decisions"][0]["jorb_id"] == jorb.id
        assert result["pending_decisions"][0]["paused_reason"] == "Need approval"
        assert "approve" in result["pending_decisions"][0]["options"]
        assert "cancel" in result["pending_decisions"][0]["options"]

    async def test_brief_me_with_activity(self, mock_storage):
        """Test briefing with jorb activity."""
        jorb = await mock_storage.create_jorb("Active Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="running")

        # Add some messages
        for i in range(3):
            await mock_storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=f"2099-01-30T10:0{i}:00Z",  # Future date to ensure inclusion
                    direction="outbound",
                    channel="telegram",
                    content=f"Test message {i}",
                ),
            )

        result = await brief_me_action({"hours": 8760})  # 1 year

        assert result["total_open_jorbs"] == 1
        assert len(result["activity_summary"]) == 1
        assert result["activity_summary"][0]["jorb_id"] == jorb.id
        assert result["activity_summary"][0]["message_count"] == 3

    async def test_brief_me_with_completed_jorb(self, mock_storage):
        """Test briefing includes recently completed jorbs in highlights."""
        jorb = await mock_storage.create_jorb("Completed Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="complete")

        result = await brief_me_action({"hours": 1})

        assert result["recently_completed"] == 1
        assert any("Completed" in h for h in result["highlights"])

    async def test_brief_me_updates_timestamp(self, mock_storage):
        """Test that briefing updates the last briefing timestamp."""
        import actions.jorbs as jorbs_module

        # First briefing
        result1 = await brief_me_action({"update_timestamp": True})
        assert result1["last_briefing"] is None  # First time

        # Second briefing
        result2 = await brief_me_action({"update_timestamp": True})
        assert result2["last_briefing"] is not None
        assert result2["last_briefing"] == result1["briefing_time"]

    async def test_brief_me_no_timestamp_update(self, mock_storage):
        """Test briefing without updating timestamp."""
        import actions.jorbs as jorbs_module

        # First briefing with update
        result1 = await brief_me_action({"update_timestamp": True})

        # Second briefing without update
        result2 = await brief_me_action({"update_timestamp": False})

        # Third briefing - should see same last_briefing as result2
        result3 = await brief_me_action({})
        assert result3["last_briefing"] == result1["briefing_time"]

    async def test_brief_me_hours_parameter(self, mock_storage):
        """Test briefing respects hours parameter."""
        result = await brief_me_action({"hours": 48})

        # Verify the since timestamp is approximately 48 hours ago
        from datetime import datetime, timezone, timedelta
        since = datetime.fromisoformat(result["since"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - since
        assert 47 < diff.total_seconds() / 3600 < 49

    async def test_brief_me_message_truncation(self, mock_storage):
        """Test that long messages are truncated in activity summary."""
        jorb = await mock_storage.create_jorb("Task", "Plan")
        await mock_storage.update_jorb(jorb.id, status="running")

        long_message = "A" * 200
        await mock_storage.add_message(
            jorb.id,
            JorbMessage(
                id="",
                jorb_id=jorb.id,
                timestamp="2099-01-30T10:00:00Z",
                direction="outbound",
                channel="telegram",
                content=long_message,
            ),
        )

        result = await brief_me_action({"hours": 8760})

        msg = result["activity_summary"][0]["recent_messages"][0]
        assert len(msg["content"]) <= 103  # 100 chars + "..."
        assert msg["content"].endswith("...")
