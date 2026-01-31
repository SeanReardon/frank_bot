"""
Unit tests for trusted sender detection in AgentRunner.
"""

import os
import tempfile

import pytest

from services.jorb_storage import JorbContact, JorbStorage
from services.agent_runner import AgentRunner


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


@pytest.fixture
def agent_runner(storage):
    """Create an AgentRunner instance with the storage."""
    return AgentRunner(storage=storage)


class TestIsTrustedSender:
    """Tests for is_trusted_sender method."""

    async def test_returns_false_when_no_jorbs(self, agent_runner):
        """Returns False when no jorbs exist."""
        result = await agent_runner.is_trusted_sender("@unknown")
        assert result is False

    async def test_returns_true_for_known_contact(self, storage, agent_runner):
        """Returns True for a known contact."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        result = await agent_runner.is_trusted_sender("@magic")
        assert result is True

    async def test_returns_false_for_unknown_sender(self, storage, agent_runner):
        """Returns False for unknown sender."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[JorbContact(identifier="@magic", channel="telegram")],
        )

        result = await agent_runner.is_trusted_sender("@unknown")
        assert result is False

    async def test_normalizes_phone_numbers(self, storage, agent_runner):
        """Normalizes phone numbers for comparison."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[JorbContact(identifier="+15551234567", channel="sms")],
        )

        # Different format but same number
        result = await agent_runner.is_trusted_sender("5551234567")
        assert result is True

        result = await agent_runner.is_trusted_sender("+1 555-123-4567")
        assert result is True

    async def test_normalizes_usernames(self, storage, agent_runner):
        """Normalizes usernames for comparison."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[JorbContact(identifier="@MagicBot", channel="telegram")],
        )

        # Different case but same username
        result = await agent_runner.is_trusted_sender("@magicbot")
        assert result is True

        result = await agent_runner.is_trusted_sender("MagicBot")
        assert result is True

    async def test_normalizes_emails(self, storage, agent_runner):
        """Normalizes emails for comparison."""
        await storage.create_jorb(
            name="Test",
            plan="Plan",
            contacts=[JorbContact(identifier="sean@example.com", channel="email")],
        )

        # Different case but same email
        result = await agent_runner.is_trusted_sender("Sean@Example.COM")
        assert result is True

    async def test_trusted_across_multiple_jorbs(self, storage, agent_runner):
        """Sender is trusted if in any jorb (regardless of status)."""
        jorb1 = await storage.create_jorb(
            name="Old Completed",
            plan="Plan",
            contacts=[JorbContact(identifier="@contact1", channel="telegram")],
        )
        await storage.update_jorb(jorb1.id, status="complete")

        jorb2 = await storage.create_jorb(
            name="Current",
            plan="Plan",
            contacts=[JorbContact(identifier="@contact2", channel="telegram")],
        )
        await storage.update_jorb(jorb2.id, status="running")

        # Both should be trusted
        assert await agent_runner.is_trusted_sender("@contact1") is True
        assert await agent_runner.is_trusted_sender("@contact2") is True
        assert await agent_runner.is_trusted_sender("@unknown") is False
