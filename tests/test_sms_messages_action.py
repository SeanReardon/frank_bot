"""Tests for SMS messages action."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions.sms import get_sms_messages_action
from services.sms_storage import Contact, SMSMessage, SMSStorage


class TestGetSmsMessagesAction:
    """Tests for get_sms_messages_action function."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def storage(self, temp_data_dir):
        """Create an SMS storage instance."""
        return SMSStorage(data_dir=temp_data_dir)

    def _create_message(
        self,
        storage: SMSStorage,
        content: str = "Hello",
        direction: str = "inbound",
        from_number: str = "+12148170664",
        to_number: str = "+15551234567",
        contact_name: str | None = None,
        timestamp: str | None = None,
    ) -> SMSMessage:
        """Create and store a test message."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        contact = None
        if contact_name:
            contact = Contact(name=contact_name, googleContactId=f"people/c{contact_name}")

        message = SMSMessage(
            id=f"sms_{int(datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp())}_{to_number}",
            timestamp=timestamp,
            direction=direction,
            localNumber=from_number,
            remoteNumber=to_number,
            content=content,
            contact=contact,
            attachments=[],
            processed=False,
        )
        storage.store_message(message)
        return message

    @pytest.mark.asyncio
    async def test_returns_recent_messages(self, temp_data_dir, storage):
        """Should return recent messages."""
        # Create some test messages
        self._create_message(storage, content="Message 1")
        self._create_message(storage, content="Message 2")
        self._create_message(storage, content="Message 3")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({})

        assert result["count"] == 3
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_respects_limit(self, temp_data_dir, storage):
        """Should respect limit parameter."""
        for i in range(10):
            self._create_message(storage, content=f"Message {i}")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({"limit": 5})

        assert result["count"] == 5
        assert len(result["messages"]) == 5

    @pytest.mark.asyncio
    async def test_clamps_limit_to_max(self, temp_data_dir, storage):
        """Should clamp limit to max 100."""
        for i in range(110):
            self._create_message(storage, content=f"Message {i}")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({"limit": 200})

        assert result["count"] == 100

    @pytest.mark.asyncio
    async def test_filters_by_direction(self, temp_data_dir, storage):
        """Should filter by direction."""
        self._create_message(storage, content="Inbound 1", direction="inbound")
        self._create_message(storage, content="Outbound 1", direction="outbound")
        self._create_message(storage, content="Inbound 2", direction="inbound")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({"direction": "inbound"})

        assert result["count"] == 2
        for msg in result["messages"]:
            assert msg["direction"] == "inbound"

    @pytest.mark.asyncio
    async def test_filters_by_contact(self, temp_data_dir, storage):
        """Should filter by contact name (case-insensitive)."""
        self._create_message(storage, content="From Mom", contact_name="Mom")
        self._create_message(storage, content="From Dad", contact_name="Dad")
        self._create_message(storage, content="From unknown")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({"contact": "mom"})

        assert result["count"] == 1
        assert result["messages"][0]["contact"] == "Mom"

    @pytest.mark.asyncio
    async def test_filters_by_phone(self, temp_data_dir, storage):
        """Should filter by phone number."""
        self._create_message(storage, content="Message 1", to_number="+15551234567")
        self._create_message(storage, content="Message 2", to_number="+15559876543")
        self._create_message(storage, content="Message 3", to_number="+15551234567")

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({"phone": "+15551234567"})

        assert result["count"] == 2
        for msg in result["messages"]:
            assert msg["phone"] == "+15551234567"

    @pytest.mark.asyncio
    async def test_invalid_direction_raises_error(self, temp_data_dir):
        """Should raise error for invalid direction."""
        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            with pytest.raises(ValueError, match="direction must be"):
                await get_sms_messages_action({"direction": "invalid"})

    @pytest.mark.asyncio
    async def test_message_preview_truncated(self, temp_data_dir, storage):
        """Message preview should be truncated at 100 chars."""
        long_content = "x" * 200
        self._create_message(storage, content=long_content)

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({})

        assert len(result["messages"]) == 1
        preview = result["messages"][0]["preview"]
        assert len(preview) == 103  # 100 chars + "..."
        assert preview.endswith("...")

    @pytest.mark.asyncio
    async def test_includes_contact_when_available(self, temp_data_dir, storage):
        """Should include contact name when available."""
        self._create_message(storage, content="Hello", contact_name="Mom")
        self._create_message(storage, content="Hello", contact_name=None)

        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({})

        messages = result["messages"]
        # Find the one with contact
        with_contact = [m for m in messages if "contact" in m]
        without_contact = [m for m in messages if "contact" not in m]

        assert len(with_contact) == 1
        assert with_contact[0]["contact"] == "Mom"
        assert len(without_contact) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_messages(self, temp_data_dir):
        """Should return empty list when no messages exist."""
        with patch.dict("os.environ", {"DATA_DIR": temp_data_dir}):
            result = await get_sms_messages_action({})

        assert result["count"] == 0
        assert result["messages"] == []
