"""
Unit tests for JorbStorage service.
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from services.jorb_storage import (
    Jorb,
    JorbCheckpoint,
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
    # Cleanup
    if os.path.exists(f.name):
        os.unlink(f.name)


@pytest.fixture
def storage(temp_db_path):
    """Create a JorbStorage instance with temp database."""
    return JorbStorage(db_path=temp_db_path)


class TestJorbCRUD:
    """Tests for jorb CRUD operations."""

    async def test_create_jorb_minimal(self, storage):
        """Test creating a jorb with minimal fields."""
        jorb = await storage.create_jorb(
            name="Test Task",
            plan="Do the thing",
        )

        assert jorb.id.startswith("jorb_")
        assert jorb.name == "Test Task"
        assert jorb.status == "planning"
        assert jorb.original_plan == "Do the thing"
        assert jorb.contacts == []
        assert jorb.created_at
        assert jorb.updated_at

    async def test_create_jorb_with_contacts(self, storage):
        """Test creating a jorb with contacts."""
        contacts = [
            JorbContact(identifier="@magic", channel="telegram", name="Magic Concierge"),
            JorbContact(identifier="+15551234567", channel="sms"),
        ]

        jorb = await storage.create_jorb(
            name="Hotel Booking",
            plan="Book hotel for GDC",
            contacts=contacts,
        )

        assert len(jorb.contacts) == 2
        assert jorb.contacts[0].identifier == "@magic"
        assert jorb.contacts[0].channel == "telegram"
        assert jorb.contacts[0].name == "Magic Concierge"
        assert jorb.contacts[1].identifier == "+15551234567"
        assert jorb.contacts[1].channel == "sms"
        assert jorb.contacts[1].name is None

    async def test_get_jorb_exists(self, storage):
        """Test retrieving an existing jorb."""
        created = await storage.create_jorb(
            name="Test Task",
            plan="Plan text",
        )

        retrieved = await storage.get_jorb(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name
        assert retrieved.status == created.status

    async def test_get_jorb_not_found(self, storage):
        """Test retrieving a non-existent jorb."""
        result = await storage.get_jorb("jorb_nonexistent")
        assert result is None

    async def test_list_jorbs_all(self, storage):
        """Test listing all jorbs."""
        await storage.create_jorb(name="Task 1", plan="Plan 1")
        await storage.create_jorb(name="Task 2", plan="Plan 2")
        await storage.create_jorb(name="Task 3", plan="Plan 3")

        jorbs = await storage.list_jorbs(status_filter="all")

        assert len(jorbs) == 3

    async def test_list_jorbs_open(self, storage):
        """Test listing open jorbs."""
        jorb1 = await storage.create_jorb(name="Planning", plan="Plan")
        jorb2 = await storage.create_jorb(name="Running", plan="Plan")
        jorb3 = await storage.create_jorb(name="Complete", plan="Plan")

        await storage.update_jorb(jorb2.id, status="running")
        await storage.update_jorb(jorb3.id, status="complete")

        open_jorbs = await storage.list_jorbs(status_filter="open")

        # planning and running are open
        assert len(open_jorbs) == 2
        statuses = {j.status for j in open_jorbs}
        assert statuses == {"planning", "running"}

    async def test_list_jorbs_closed(self, storage):
        """Test listing closed jorbs."""
        jorb1 = await storage.create_jorb(name="Complete", plan="Plan")
        jorb2 = await storage.create_jorb(name="Failed", plan="Plan")
        jorb3 = await storage.create_jorb(name="Running", plan="Plan")

        await storage.update_jorb(jorb1.id, status="complete")
        await storage.update_jorb(jorb2.id, status="failed")
        await storage.update_jorb(jorb3.id, status="running")

        closed_jorbs = await storage.list_jorbs(status_filter="closed")

        assert len(closed_jorbs) == 2
        statuses = {j.status for j in closed_jorbs}
        assert statuses == {"complete", "failed"}

    async def test_update_jorb(self, storage):
        """Test updating jorb fields."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")
        original_updated_at = jorb.updated_at

        updated = await storage.update_jorb(
            jorb.id,
            status="running",
            progress_summary="Started working",
            awaiting="Response from Magic",
        )

        assert updated is not None
        assert updated.status == "running"
        assert updated.progress_summary == "Started working"
        assert updated.awaiting == "Response from Magic"
        assert updated.updated_at != original_updated_at

    async def test_update_jorb_invalid_field(self, storage):
        """Test that invalid field names raise an error."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        with pytest.raises(ValueError, match="Invalid fields"):
            await storage.update_jorb(jorb.id, invalid_field="value")

    async def test_update_jorb_not_found(self, storage):
        """Test updating a non-existent jorb."""
        result = await storage.update_jorb("jorb_nonexistent", status="running")
        assert result is None


class TestJorbMessages:
    """Tests for jorb message tracking."""

    async def test_add_message(self, storage):
        """Test adding a message to a jorb."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        message = JorbMessage(
            id="",
            jorb_id=jorb.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            direction="outbound",
            channel="telegram",
            sender="frank_bot",
            recipient="@magic",
            content="Hi, can you help me book a hotel?",
            agent_reasoning="Initial outreach to Magic",
        )

        msg_id = await storage.add_message(jorb.id, message)

        assert msg_id.startswith("msg_")

    async def test_get_messages(self, storage):
        """Test retrieving messages for a jorb."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        # Add multiple messages
        for i in range(3):
            await storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    direction="outbound" if i % 2 == 0 else "inbound",
                    channel="telegram",
                    content=f"Message {i}",
                ),
            )

        messages = await storage.get_messages(jorb.id)

        assert len(messages) == 3
        assert messages[0].content == "Message 0"

    async def test_get_messages_limit(self, storage):
        """Test message limit parameter."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        # Add 10 messages
        for i in range(10):
            await storage.add_message(
                jorb.id,
                JorbMessage(
                    id="",
                    jorb_id=jorb.id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    direction="outbound",
                    channel="sms",
                    content=f"Message {i}",
                ),
            )

        messages = await storage.get_messages(jorb.id, limit=5)

        assert len(messages) == 5

    async def test_get_open_jorbs_with_messages(self, storage):
        """Test getting open jorbs with their messages."""
        # Create jorbs with different statuses
        running_jorb = await storage.create_jorb(name="Running", plan="Plan")
        await storage.update_jorb(running_jorb.id, status="running")
        await storage.add_message(
            running_jorb.id,
            JorbMessage(
                id="",
                jorb_id=running_jorb.id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                direction="outbound",
                channel="telegram",
                content="Running message",
            ),
        )

        paused_jorb = await storage.create_jorb(name="Paused", plan="Plan")
        await storage.update_jorb(paused_jorb.id, status="paused")
        await storage.add_message(
            paused_jorb.id,
            JorbMessage(
                id="",
                jorb_id=paused_jorb.id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                direction="inbound",
                channel="sms",
                content="Paused message",
            ),
        )

        # Planning jorb (should not be included - only running/paused)
        await storage.create_jorb(name="Planning", plan="Plan")

        # Completed jorb (should not be included)
        complete_jorb = await storage.create_jorb(name="Complete", plan="Plan")
        await storage.update_jorb(complete_jorb.id, status="complete")

        results = await storage.get_open_jorbs_with_messages()

        assert len(results) == 2
        assert all(isinstance(r, JorbWithMessages) for r in results)

        statuses = {r.jorb.status for r in results}
        assert statuses == {"running", "paused"}

        # Verify messages are included
        for result in results:
            assert len(result.messages) > 0


class TestJorbCheckpoints:
    """Tests for jorb checkpoints."""

    async def test_add_checkpoint(self, storage):
        """Test adding a checkpoint."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        checkpoint_id = await storage.add_checkpoint(
            jorb.id,
            summary="Day 3 handoff: Contacted Magic, waiting for response",
            token_count=15000,
        )

        assert checkpoint_id.startswith("ckpt_")

    async def test_get_checkpoints(self, storage):
        """Test retrieving checkpoints."""
        jorb = await storage.create_jorb(name="Test", plan="Plan")

        await storage.add_checkpoint(jorb.id, summary="Checkpoint 1", token_count=5000)
        await storage.add_checkpoint(jorb.id, summary="Checkpoint 2", token_count=10000)

        checkpoints = await storage.get_checkpoints(jorb.id)

        assert len(checkpoints) == 2
        assert checkpoints[0].summary == "Checkpoint 1"
        assert checkpoints[0].token_count == 5000
        assert checkpoints[1].summary == "Checkpoint 2"


class TestJorbContact:
    """Tests for JorbContact dataclass."""

    def test_contact_to_dict_with_name(self):
        """Test serializing contact with name."""
        contact = JorbContact(
            identifier="@magic",
            channel="telegram",
            name="Magic Concierge",
        )

        data = contact.to_dict()

        assert data == {
            "identifier": "@magic",
            "channel": "telegram",
            "name": "Magic Concierge",
        }

    def test_contact_to_dict_without_name(self):
        """Test serializing contact without name."""
        contact = JorbContact(identifier="+15551234567", channel="sms")

        data = contact.to_dict()

        assert data == {
            "identifier": "+15551234567",
            "channel": "sms",
        }

    def test_contact_from_dict(self):
        """Test deserializing contact."""
        data = {
            "identifier": "@magic",
            "channel": "telegram",
            "name": "Magic Concierge",
        }

        contact = JorbContact.from_dict(data)

        assert contact.identifier == "@magic"
        assert contact.channel == "telegram"
        assert contact.name == "Magic Concierge"


class TestGetAllContactsFromJorbs:
    """Tests for get_all_contacts_from_jorbs method."""

    async def test_returns_empty_set_when_no_jorbs(self, storage):
        """Returns empty set when no jorbs exist."""
        contacts = await storage.get_all_contacts_from_jorbs()
        assert contacts == set()

    async def test_returns_contacts_from_single_jorb(self, storage):
        """Returns contacts from a single jorb."""
        await storage.create_jorb(
            name="Test Jorb",
            plan="Test plan",
            contacts=[
                JorbContact(identifier="@magic", channel="telegram"),
                JorbContact(identifier="+15551234567", channel="sms"),
            ],
        )

        contacts = await storage.get_all_contacts_from_jorbs()

        assert len(contacts) == 2
        assert "magic" in contacts  # Normalized (@ stripped, lowercased)
        assert "5551234567" in contacts  # Normalized (last 10 digits)

    async def test_returns_unique_contacts_across_multiple_jorbs(self, storage):
        """Returns unique contacts across multiple jorbs."""
        await storage.create_jorb(
            name="Jorb 1",
            plan="Plan 1",
            contacts=[
                JorbContact(identifier="@magic", channel="telegram"),
            ],
        )
        await storage.create_jorb(
            name="Jorb 2",
            plan="Plan 2",
            contacts=[
                JorbContact(identifier="@magic", channel="telegram"),  # Duplicate
                JorbContact(identifier="+15559876543", channel="sms"),
            ],
        )

        contacts = await storage.get_all_contacts_from_jorbs()

        assert len(contacts) == 2  # Deduped
        assert "magic" in contacts
        assert "5559876543" in contacts

    async def test_normalizes_phone_numbers(self, storage):
        """Normalizes phone numbers to last 10 digits."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[
                JorbContact(identifier="+1 555 123 4567", channel="sms"),
            ],
        )

        contacts = await storage.get_all_contacts_from_jorbs()

        assert "5551234567" in contacts

    async def test_normalizes_usernames(self, storage):
        """Normalizes usernames by stripping @ and lowercasing."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[
                JorbContact(identifier="@MagicBot", channel="telegram"),
            ],
        )

        contacts = await storage.get_all_contacts_from_jorbs()

        assert "magicbot" in contacts

    async def test_normalizes_emails(self, storage):
        """Normalizes emails by lowercasing."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[
                JorbContact(identifier="Sean@Example.COM", channel="email"),
            ],
        )

        contacts = await storage.get_all_contacts_from_jorbs()

        assert "sean@example.com" in contacts

    async def test_includes_contacts_from_all_statuses(self, storage):
        """Includes contacts from jorbs of any status."""
        jorb1 = await storage.create_jorb(
            name="Running",
            plan="Plan",
            contacts=[JorbContact(identifier="@contact1", channel="telegram")],
        )
        jorb2 = await storage.create_jorb(
            name="Complete",
            plan="Plan",
            contacts=[JorbContact(identifier="@contact2", channel="telegram")],
        )

        # Update statuses
        await storage.update_jorb(jorb1.id, status="running")
        await storage.update_jorb(jorb2.id, status="complete")

        contacts = await storage.get_all_contacts_from_jorbs()

        assert len(contacts) == 2
        assert "contact1" in contacts
        assert "contact2" in contacts


class TestNormalizeIdentifier:
    """Tests for _normalize_identifier static method."""

    def test_normalizes_phone_with_country_code(self):
        """Normalizes phone with +1 country code."""
        result = JorbStorage._normalize_identifier("+15551234567")
        assert result == "5551234567"

    def test_normalizes_phone_with_spaces(self):
        """Normalizes phone with spaces and dashes."""
        result = JorbStorage._normalize_identifier("+1 555-123-4567")
        assert result == "5551234567"

    def test_normalizes_phone_11_digits(self):
        """Normalizes 11-digit phone to last 10."""
        result = JorbStorage._normalize_identifier("15551234567")
        assert result == "5551234567"

    def test_normalizes_username_with_at(self):
        """Normalizes username with @ prefix."""
        result = JorbStorage._normalize_identifier("@MagicBot")
        assert result == "magicbot"

    def test_normalizes_email(self):
        """Normalizes email to lowercase."""
        result = JorbStorage._normalize_identifier("Sean@Example.COM")
        assert result == "sean@example.com"

    def test_normalizes_plain_string(self):
        """Normalizes plain string to lowercase."""
        result = JorbStorage._normalize_identifier("SomeContact")
        assert result == "somecontact"

    def test_strips_whitespace(self):
        """Strips leading/trailing whitespace."""
        result = JorbStorage._normalize_identifier("  @magic  ")
        assert result == "magic"
