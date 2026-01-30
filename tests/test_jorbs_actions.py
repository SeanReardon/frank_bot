"""
Unit tests for jorbs actions.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from actions.jorbs import (
    create_jorb_action,
    get_jorb_action,
    get_jorb_messages_action,
    list_jorbs_action,
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
