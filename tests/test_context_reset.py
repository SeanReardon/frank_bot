"""
Unit tests for ContextResetService.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if openai is available
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from services.context_reset import (
    ContextResetService,
    ContextResetState,
    HandoffSummary,
    JorbHandoff,
)
from services.jorb_storage import Jorb, JorbMessage, JorbWithMessages


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"DATA_DIR": tmpdir}):
            yield tmpdir


@pytest.fixture
def sample_jorb():
    """Create a sample jorb."""
    return Jorb(
        id="jorb_12345678",
        name="Hotel Booking",
        status="running",
        original_plan="Book a hotel in SF for March 17-21",
        progress_summary="Initial outreach complete",
        contacts_json='[{"identifier": "+15551234567", "channel": "sms", "name": "Hotel Contact"}]',
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_messages():
    """Create sample messages."""
    return [
        JorbMessage(
            id="msg_1",
            jorb_id="jorb_12345678",
            timestamp="2026-01-28T10:00:00+00:00",
            direction="outbound",
            channel="sms",
            recipient="+15551234567",
            content="Hi, I'd like to book a room.",
        ),
        JorbMessage(
            id="msg_2",
            jorb_id="jorb_12345678",
            timestamp="2026-01-28T10:30:00+00:00",
            direction="inbound",
            channel="sms",
            sender="+15551234567",
            sender_name="Hotel",
            content="Sure! We have availability.",
        ),
    ]


class TestContextResetState:
    """Tests for ContextResetState dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        state = ContextResetState(
            last_reset_at="2026-01-28T00:00:00+00:00",
            reset_count=5,
            last_activity_at="2026-01-30T12:00:00+00:00",
        )

        d = state.to_dict()
        assert d["last_reset_at"] == "2026-01-28T00:00:00+00:00"
        assert d["reset_count"] == 5
        assert d["last_activity_at"] == "2026-01-30T12:00:00+00:00"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "last_reset_at": "2026-01-28T00:00:00+00:00",
            "reset_count": 3,
            "last_activity_at": "2026-01-29T12:00:00+00:00",
        }

        state = ContextResetState.from_dict(data)
        assert state.last_reset_at == "2026-01-28T00:00:00+00:00"
        assert state.reset_count == 3
        assert state.last_activity_at == "2026-01-29T12:00:00+00:00"

    def test_from_dict_defaults(self):
        """Test deserialization with missing fields."""
        state = ContextResetState.from_dict({})
        assert state.last_reset_at is None
        assert state.reset_count == 0
        assert state.last_activity_at is None


class TestMaybeResetContext:
    """Tests for maybe_reset_context method."""

    def test_no_previous_reset_no_activity(self, temp_data_dir):
        """No reset needed if no activity ever occurred."""
        service = ContextResetService()
        assert service.maybe_reset_context() is False

    def test_no_previous_reset_with_activity(self, temp_data_dir):
        """Reset needed if activity occurred but never reset."""
        service = ContextResetService()
        service.record_activity()
        assert service.maybe_reset_context() is True

    def test_recent_reset_no_activity(self, temp_data_dir):
        """No reset if recent reset and no new activity."""
        service = ContextResetService()

        # Create state with recent reset but no activity after
        state = ContextResetState(
            last_reset_at=datetime.now(timezone.utc).isoformat(),
            reset_count=1,
            last_activity_at=None,
        )
        service._save_state(state)

        assert service.maybe_reset_context() is False

    def test_reset_needed_after_interval(self, temp_data_dir):
        """Reset needed after CONTEXT_RESET_DAYS with activity."""
        with patch.dict(os.environ, {"CONTEXT_RESET_DAYS": "3"}):
            service = ContextResetService()

            # Set last reset to 4 days ago
            past = datetime.now(timezone.utc) - timedelta(days=4)
            state = ContextResetState(
                last_reset_at=past.isoformat(),
                reset_count=1,
                last_activity_at=datetime.now(timezone.utc).isoformat(),
            )
            service._save_state(state)

            assert service.maybe_reset_context() is True

    def test_no_reset_before_interval(self, temp_data_dir):
        """No reset before CONTEXT_RESET_DAYS."""
        with patch.dict(os.environ, {"CONTEXT_RESET_DAYS": "3"}):
            service = ContextResetService()

            # Set last reset to 2 days ago (before 3-day interval)
            past = datetime.now(timezone.utc) - timedelta(days=2)
            state = ContextResetState(
                last_reset_at=past.isoformat(),
                reset_count=1,
                last_activity_at=datetime.now(timezone.utc).isoformat(),
            )
            service._save_state(state)

            assert service.maybe_reset_context() is False


class TestRecordActivity:
    """Tests for record_activity method."""

    def test_records_activity_timestamp(self, temp_data_dir):
        """Activity is recorded with current timestamp."""
        service = ContextResetService()
        service.record_activity()

        state = service._load_state()
        assert state.last_activity_at is not None

        # Verify it's a valid timestamp
        dt = datetime.fromisoformat(state.last_activity_at.replace("Z", "+00:00"))
        assert dt <= datetime.now(timezone.utc)


class TestProgressLog:
    """Tests for progress log operations."""

    def test_append_to_progress_log(self, temp_data_dir):
        """Handoff is appended to progress log."""
        service = ContextResetService()

        handoff = HandoffSummary(
            session_summary="Made progress on hotel booking.",
            jorb_handoffs=[
                JorbHandoff(
                    jorb_id="jorb_12345678",
                    jorb_name="Hotel Booking",
                    status="running",
                    progress_summary="Initial outreach complete.",
                    recent_activity="Received quote from hotel.",
                    next_steps="Confirm booking dates.",
                ),
            ],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        service._append_to_progress_log(handoff)

        # Verify file was created
        log_path = os.path.join(temp_data_dir, "jorbs_progress.txt")
        assert os.path.exists(log_path)

        with open(log_path, "r") as f:
            content = f.read()

        assert "Context Reset" in content
        assert "Made progress on hotel booking" in content
        assert "Hotel Booking" in content
        assert "Initial outreach complete" in content

    def test_get_progress_log_tail(self, temp_data_dir):
        """Get last N lines of progress log."""
        service = ContextResetService()

        # Create a log file
        log_path = os.path.join(temp_data_dir, "jorbs_progress.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            for i in range(200):
                f.write(f"Line {i}\n")

        tail = service.get_progress_log_tail(100)
        lines = tail.strip().split("\n")
        assert len(lines) == 100
        assert "Line 100" in lines[0]
        assert "Line 199" in lines[-1]

    def test_get_progress_log_tail_file_not_found(self, temp_data_dir):
        """Returns empty string if log doesn't exist."""
        service = ContextResetService()
        assert service.get_progress_log_tail() == ""


@pytest.mark.asyncio
class TestPerformContextReset:
    """Tests for perform_context_reset method."""

    async def test_reset_with_no_jorbs(self, temp_data_dir):
        """Reset with no active jorbs still records the reset."""
        with patch("services.context_reset.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.get_open_jorbs_with_messages = AsyncMock(return_value=[])
            mock_storage_cls.return_value = mock_storage

            service = ContextResetService(storage=mock_storage, openai_api_key="test-key")
            handoff = await service.perform_context_reset()

            assert "No active tasks" in handoff.session_summary

            # State should be updated
            state = service._load_state()
            assert state.reset_count == 1
            assert state.last_reset_at is not None

    @pytest.mark.skipif(not HAS_OPENAI, reason="openai not installed")
    async def test_reset_updates_jorb_summaries(self, temp_data_dir, sample_jorb, sample_messages):
        """Reset updates jorb progress summaries."""
        jwm = JorbWithMessages(jorb=sample_jorb, messages=sample_messages)

        with patch("services.context_reset.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.get_open_jorbs_with_messages = AsyncMock(return_value=[jwm])
            mock_storage.update_jorb = AsyncMock(return_value=sample_jorb)
            mock_storage.add_checkpoint = AsyncMock(return_value="ckpt_123")
            mock_storage_cls.return_value = mock_storage

            # Mock OpenAI response
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock()]
                mock_response.choices[0].message.content = json.dumps({
                    "session_summary": "Good progress on booking task.",
                    "jorb_handoffs": [
                        {
                            "jorb_id": "jorb_12345678",
                            "jorb_name": "Hotel Booking",
                            "status": "running",
                            "progress_summary": "Hotel contacted, awaiting confirmation.",
                            "recent_activity": "Received availability info.",
                            "next_steps": "Confirm booking.",
                        }
                    ],
                })
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai_cls.return_value = mock_client

                service = ContextResetService(storage=mock_storage, openai_api_key="test-key")
                handoff = await service.perform_context_reset()

                assert handoff.session_summary == "Good progress on booking task."
                assert len(handoff.jorb_handoffs) == 1

                # Verify jorb was updated
                mock_storage.update_jorb.assert_called_once()
                call_args = mock_storage.update_jorb.call_args
                assert call_args[0][0] == "jorb_12345678"
                assert "progress_summary" in call_args[1]


@pytest.mark.asyncio
class TestBuildFreshContext:
    """Tests for build_fresh_context method."""

    async def test_builds_context_with_open_jorbs(self, temp_data_dir, sample_jorb):
        """Fresh context includes open jorbs and progress log."""
        with patch("services.context_reset.JorbStorage") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage.list_jorbs = AsyncMock(return_value=[sample_jorb])
            mock_storage_cls.return_value = mock_storage

            # Create some progress log content
            service = ContextResetService(storage=mock_storage)
            log_path = os.path.join(temp_data_dir, "jorbs_progress.txt")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w") as f:
                f.write("Previous session summary\n")

            context = await service.build_fresh_context()

            assert context["context_type"] == "fresh_start_after_reset"
            assert len(context["active_tasks"]) == 1
            assert context["active_tasks"][0]["id"] == "jorb_12345678"
            assert context["active_tasks"][0]["original_plan"] == "Book a hotel in SF for March 17-21"
            assert "Previous session summary" in context["progress_history"]


class TestGetResetStatus:
    """Tests for get_reset_status method."""

    def test_status_never_reset(self, temp_data_dir):
        """Status when never reset."""
        service = ContextResetService()
        status = service.get_reset_status()

        assert status["last_reset_at"] is None
        assert status["reset_count"] == 0
        assert status["reset_interval_days"] == 3  # default
        assert status["needs_reset"] is False

    def test_status_with_previous_reset(self, temp_data_dir):
        """Status after previous reset."""
        with patch.dict(os.environ, {"CONTEXT_RESET_DAYS": "7"}):
            service = ContextResetService()

            # Set up state
            past = datetime.now(timezone.utc) - timedelta(days=2)
            state = ContextResetState(
                last_reset_at=past.isoformat(),
                reset_count=3,
                last_activity_at=datetime.now(timezone.utc).isoformat(),
            )
            service._save_state(state)

            status = service.get_reset_status()

            assert status["reset_count"] == 3
            assert status["reset_interval_days"] == 7
            # days_until_reset can be 4 or 5 depending on exact timing
            assert status["days_until_reset"] in (4, 5)
            assert status["needs_reset"] is False  # not enough days
