"""Unit tests for SMS storage service."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from services.sms_storage import (
    Attachment,
    Contact,
    SMSMessage,
    SMSStorage,
    _generate_filename,
    _generate_attachment_filename,
    _sanitize_filename,
    _format_timestamp_for_filename,
)


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_sanitizes_colons(self):
        """Colons are replaced with underscores."""
        result = _sanitize_filename("test:file:name")
        assert result == "test_file_name"

    def test_sanitizes_slashes(self):
        """Slashes are replaced with underscores."""
        result = _sanitize_filename("test/file\\name")
        assert result == "test_file_name"

    def test_sanitizes_windows_chars(self):
        """All Windows-invalid characters are replaced."""
        result = _sanitize_filename('<>:"/\\|?*test')
        assert result == "_________test"

    def test_allows_valid_chars(self):
        """Valid characters pass through unchanged."""
        result = _sanitize_filename("Mom (Home)")
        assert result == "Mom (Home)"

    def test_preserves_spaces(self):
        """Spaces are preserved."""
        result = _sanitize_filename("John Smith")
        assert result == "John Smith"


class TestFormatTimestamp:
    """Tests for timestamp formatting."""

    def test_replaces_colons(self):
        """Colons in timestamp are replaced with dashes."""
        result = _format_timestamp_for_filename("2026-01-29T18:45:32Z")
        assert result == "2026-01-29T18-45-32Z"

    def test_handles_milliseconds(self):
        """Timestamps with milliseconds are handled."""
        result = _format_timestamp_for_filename("2026-01-29T18:45:32.123Z")
        assert result == "2026-01-29T18-45-32.123Z"


class TestGenerateFilename:
    """Tests for message filename generation."""

    def test_with_contact(self):
        """Filename uses contact name when available."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
            contact=Contact(name="Mom", googleContactId="people/c123"),
        )
        filename = _generate_filename(msg)
        assert filename == "2026-01-29T18-45-32Z-Mom.json"

    def test_without_contact(self):
        """Filename uses phone number when no contact."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
        )
        filename = _generate_filename(msg)
        assert filename == "2026-01-29T18-45-32Z-+15551234567.json"

    def test_sanitizes_contact_name(self):
        """Contact name is sanitized for filesystem."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
            contact=Contact(name="John: The Great", googleContactId="people/c123"),
        )
        filename = _generate_filename(msg)
        assert filename == "2026-01-29T18-45-32Z-John_ The Great.json"


class TestSMSMessage:
    """Tests for SMSMessage model."""

    def test_minimal_message(self):
        """Message can be created with required fields only."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
        )
        assert msg.contact is None
        assert msg.attachments == []
        assert msg.processed is False
        assert msg.jorbId is None

    def test_full_message(self):
        """Message can be created with all fields."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Here's a photo",
            contact=Contact(name="Mom", googleContactId="people/c123"),
            attachments=[
                Attachment(
                    filename="photo.jpg",
                    contentType="image/jpeg",
                    size=12345,
                    originalUrl="https://example.com/photo.jpg",
                )
            ],
            telnyxMessageId="msg-123",
            processed=True,
            jorbId="jorb_123",
            classification="jorb",
        )
        assert msg.contact.name == "Mom"
        assert len(msg.attachments) == 1
        assert msg.attachments[0].contentType == "image/jpeg"

    def test_model_dump(self):
        """Message serializes to dict correctly."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
            contact=Contact(name="Mom"),
        )
        data = msg.model_dump(mode="json")
        assert data["id"] == "sms_1706550332_+15551234567"
        assert data["contact"]["name"] == "Mom"
        assert data["contact"]["googleContactId"] is None


class TestSMSStorageStoreMessage:
    """Tests for storing messages."""

    def test_store_message(self):
        """Message is stored as JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
            )

            filepath = storage.store_message(msg)

            assert filepath.exists()
            assert filepath.name == "2026-01-29T18-45-32Z-+15551234567.json"

            # Verify content
            with open(filepath) as f:
                data = json.load(f)
            assert data["id"] == "sms_1706550332_+15551234567"
            assert data["content"] == "Hello"

    def test_store_creates_directory(self):
        """Directory is created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
            )

            filepath = storage.store_message(msg)

            # Directory should be created
            assert (Path(tmpdir) / "sms" / "12148170664").is_dir()

    def test_store_message_with_contact(self):
        """Message with contact uses contact name in filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
                contact=Contact(name="Mom"),
            )

            filepath = storage.store_message(msg)

            assert filepath.name == "2026-01-29T18-45-32Z-Mom.json"


class TestSMSStorageGetRecentMessages:
    """Tests for retrieving messages."""

    def test_get_empty_returns_empty(self):
        """Empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            messages = storage.get_recent_messages()
            assert messages == []

    def test_get_recent_messages(self):
        """Messages are retrieved and sorted by timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)

            # Store messages out of order
            msg1 = SMSMessage(
                id="sms_1_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="First",
            )
            msg2 = SMSMessage(
                id="sms_2_+15551234567",
                timestamp="2026-01-29T18:50:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Second",
            )
            msg3 = SMSMessage(
                id="sms_3_+15551234567",
                timestamp="2026-01-29T18:47:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Third",
            )

            storage.store_message(msg1)
            storage.store_message(msg2)
            storage.store_message(msg3)

            messages = storage.get_recent_messages()

            # Should be sorted newest first
            assert len(messages) == 3
            assert messages[0].content == "Second"
            assert messages[1].content == "Third"
            assert messages[2].content == "First"

    def test_filter_by_remote_number(self):
        """Messages can be filtered by remote number."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)

            msg1 = SMSMessage(
                id="sms_1_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="From 567",
            )
            msg2 = SMSMessage(
                id="sms_2_+15559999999",
                timestamp="2026-01-29T18:50:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15559999999",
                content="From 999",
            )

            storage.store_message(msg1)
            storage.store_message(msg2)

            messages = storage.get_recent_messages(remote_number="+15551234567")

            assert len(messages) == 1
            assert messages[0].content == "From 567"

    def test_filter_by_contact_name(self):
        """Messages can be filtered by contact name (case-insensitive)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)

            msg1 = SMSMessage(
                id="sms_1_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="From Mom",
                contact=Contact(name="Mom"),
            )
            msg2 = SMSMessage(
                id="sms_2_+15559999999",
                timestamp="2026-01-29T18:50:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15559999999",
                content="From Dad",
                contact=Contact(name="Dad"),
            )
            msg3 = SMSMessage(
                id="sms_3_+15558888888",
                timestamp="2026-01-29T18:55:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15558888888",
                content="Unknown",
            )

            storage.store_message(msg1)
            storage.store_message(msg2)
            storage.store_message(msg3)

            messages = storage.get_recent_messages(contact_name="mom")

            assert len(messages) == 1
            assert messages[0].content == "From Mom"

    def test_filter_by_local_number(self):
        """Messages can be filtered by local number."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)

            msg1 = SMSMessage(
                id="sms_1_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="To 664",
            )
            msg2 = SMSMessage(
                id="sms_2_+15551234567",
                timestamp="2026-01-29T18:50:32Z",
                direction="inbound",
                localNumber="+12145551234",
                remoteNumber="+15551234567",
                content="To 234",
            )

            storage.store_message(msg1)
            storage.store_message(msg2)

            messages = storage.get_recent_messages(local_number="+12148170664")

            assert len(messages) == 1
            assert messages[0].content == "To 664"

    def test_limit(self):
        """Limit restricts number of returned messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)

            for i in range(10):
                msg = SMSMessage(
                    id=f"sms_{i}_+15551234567",
                    timestamp=f"2026-01-29T18:{45+i:02d}:32Z",
                    direction="inbound",
                    localNumber="+12148170664",
                    remoteNumber="+15551234567",
                    content=f"Message {i}",
                )
                storage.store_message(msg)

            messages = storage.get_recent_messages(limit=3)

            assert len(messages) == 3


class TestSMSStorageGetMessageById:
    """Tests for retrieving a message by ID."""

    def test_get_existing_message(self):
        """Existing message can be retrieved by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
            )
            storage.store_message(msg)

            retrieved = storage.get_message_by_id("sms_1706550332_+15551234567")

            assert retrieved is not None
            assert retrieved.content == "Hello"

    def test_get_nonexistent_message(self):
        """Getting nonexistent message returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            result = storage.get_message_by_id("nonexistent")
            assert result is None


class TestSMSStorageGetMessageFilepath:
    """Tests for getting expected message filepath."""

    def test_get_filepath(self):
        """Filepath is correctly computed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
                contact=Contact(name="Mom"),
            )

            filepath = storage.get_message_filepath(msg)

            expected = Path(tmpdir) / "sms" / "12148170664" / "2026-01-29T18-45-32Z-Mom.json"
            assert filepath == expected


class TestGenerateAttachmentFilename:
    """Tests for attachment filename generation."""

    def test_with_contact(self):
        """Filename includes contact name."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
            contact=Contact(name="Mom"),
        )
        filename = _generate_attachment_filename(msg, 1, "image/jpeg")
        assert filename == "2026-01-29T18-45-32Z-Mom-attachment-1.jpg"

    def test_without_contact(self):
        """Filename uses phone number when no contact."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
        )
        filename = _generate_attachment_filename(msg, 2, "image/png")
        assert filename == "2026-01-29T18-45-32Z-+15551234567-attachment-2.png"

    def test_unknown_mime_type(self):
        """Falls back to .bin for unknown MIME types."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
        )
        filename = _generate_attachment_filename(msg, 1, "application/x-unknown-type")
        assert filename.endswith("-attachment-1.bin")

    def test_video_mime_type(self):
        """Video MIME types get correct extension."""
        msg = SMSMessage(
            id="sms_1706550332_+15551234567",
            timestamp="2026-01-29T18:45:32Z",
            direction="inbound",
            localNumber="+12148170664",
            remoteNumber="+15551234567",
            content="Hello",
        )
        filename = _generate_attachment_filename(msg, 1, "video/mp4")
        assert filename.endswith("-attachment-1.mp4")


class TestSMSStorageDownloadAttachment:
    """Tests for attachment download functionality."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """Attachment is downloaded successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            filepath = Path(tmpdir) / "test.jpg"

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.content = b"fake image content"
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                size = await storage._download_attachment(
                    "https://example.com/image.jpg",
                    filepath,
                )

                assert size == len(b"fake image content")
                assert filepath.exists()
                assert filepath.read_bytes() == b"fake image content"

    @pytest.mark.asyncio
    async def test_download_creates_directory(self):
        """Download creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            filepath = Path(tmpdir) / "nested" / "dir" / "test.jpg"

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.content = b"data"
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                await storage._download_attachment(
                    "https://example.com/image.jpg",
                    filepath,
                )

                assert filepath.exists()

    @pytest.mark.asyncio
    async def test_download_http_error(self):
        """HTTP errors are propagated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            filepath = Path(tmpdir) / "test.jpg"

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "404 Not Found",
                        request=MagicMock(),
                        response=MagicMock(),
                    )
                )

                with pytest.raises(httpx.HTTPStatusError):
                    await storage._download_attachment(
                        "https://example.com/missing.jpg",
                        filepath,
                    )


class TestSMSStorageStoreMessageAsync:
    """Tests for async message storage with attachments."""

    @pytest.mark.asyncio
    async def test_store_message_no_attachments(self):
        """Message without attachments is stored correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Hello",
            )

            filepath = await storage.store_message_async(msg)

            assert filepath.exists()
            with open(filepath) as f:
                data = json.load(f)
            assert data["content"] == "Hello"
            assert data["attachments"] == []

    @pytest.mark.asyncio
    async def test_store_message_with_attachments(self):
        """Message with attachments downloads and stores them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Photo",
                attachments=[
                    Attachment(
                        filename="temp.jpg",
                        contentType="image/jpeg",
                        size=0,
                        originalUrl="https://example.com/photo.jpg",
                    )
                ],
            )

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.content = b"fake image data 12345"
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                filepath = await storage.store_message_async(msg)

            assert filepath.exists()
            with open(filepath) as f:
                data = json.load(f)

            # Attachment should have updated filename and size
            assert len(data["attachments"]) == 1
            attachment = data["attachments"][0]
            assert attachment["filename"].endswith("-attachment-1.jpg")
            assert attachment["size"] == len(b"fake image data 12345")
            assert attachment["originalUrl"] == "https://example.com/photo.jpg"

            # Verify attachment file was created
            attachment_path = filepath.parent / attachment["filename"]
            assert attachment_path.exists()
            assert attachment_path.read_bytes() == b"fake image data 12345"

    @pytest.mark.asyncio
    async def test_store_message_download_failure(self):
        """Download failure doesn't prevent message storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Photo",
                attachments=[
                    Attachment(
                        filename="temp.jpg",
                        contentType="image/jpeg",
                        size=1000,
                        originalUrl="https://example.com/photo.jpg",
                    )
                ],
            )

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "404",
                        request=MagicMock(),
                        response=MagicMock(),
                    )
                )

                filepath = await storage.store_message_async(msg)

            # Message should still be stored
            assert filepath.exists()
            with open(filepath) as f:
                data = json.load(f)

            # Original attachment info preserved (download failed)
            assert len(data["attachments"]) == 1
            attachment = data["attachments"][0]
            assert attachment["filename"] == "temp.jpg"  # Original filename kept
            assert attachment["size"] == 1000  # Original size kept

    @pytest.mark.asyncio
    async def test_store_message_multiple_attachments(self):
        """Multiple attachments are all downloaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SMSStorage(data_dir=tmpdir)
            msg = SMSMessage(
                id="sms_1706550332_+15551234567",
                timestamp="2026-01-29T18:45:32Z",
                direction="inbound",
                localNumber="+12148170664",
                remoteNumber="+15551234567",
                content="Photos",
                attachments=[
                    Attachment(
                        filename="temp1.jpg",
                        contentType="image/jpeg",
                        size=0,
                        originalUrl="https://example.com/photo1.jpg",
                    ),
                    Attachment(
                        filename="temp2.png",
                        contentType="image/png",
                        size=0,
                        originalUrl="https://example.com/photo2.png",
                    ),
                ],
            )

            with patch("services.sms_storage.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.content = b"image data"
                mock_response.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )

                filepath = await storage.store_message_async(msg)

            with open(filepath) as f:
                data = json.load(f)

            assert len(data["attachments"]) == 2
            assert data["attachments"][0]["filename"].endswith("-attachment-1.jpg")
            assert data["attachments"][1]["filename"].endswith("-attachment-2.png")
