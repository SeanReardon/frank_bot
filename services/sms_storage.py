"""
SMS Storage Service for file-based message persistence.

Stores SMS/MMS messages as JSON files in ./data/sms/{localNumber}/ directory.
Handles MMS attachment download and storage.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default timeout for attachment downloads (30 seconds)
ATTACHMENT_DOWNLOAD_TIMEOUT = 30.0

# Characters not allowed in filenames (Windows + Unix restrictions)
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


class Contact(BaseModel):
    """Contact information from Google Contacts."""

    name: str
    googleContactId: str | None = None


class Attachment(BaseModel):
    """MMS attachment metadata."""

    filename: str
    contentType: str
    size: int
    originalUrl: str | None = None


class SMSMessage(BaseModel):
    """
    SMS/MMS message model matching schemas/sms.schema.json.
    """

    id: str = Field(description="Unique message ID (sms_{timestamp}_{remoteNumber})")
    timestamp: str = Field(description="ISO 8601 timestamp when message was sent/received")
    direction: Literal["inbound", "outbound"]
    localNumber: str = Field(description="Our Telnyx number (E.164 format)")
    remoteNumber: str = Field(description="The other party's phone number (E.164 format)")
    content: str = Field(description="Message text content")
    contact: Contact | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    telnyxMessageId: str | None = None
    processed: bool = False
    jorbId: str | None = None
    replyToMessageId: str | None = None
    classification: Literal["jorb", "spam", "unknown", "compliance"] | None = None


def _sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use in a filename.

    Replaces invalid characters with underscores.
    """
    return INVALID_FILENAME_CHARS.sub("_", name)


def _format_timestamp_for_filename(iso_timestamp: str) -> str:
    """
    Convert ISO 8601 timestamp to filesystem-safe format.

    Replaces : with - to avoid issues on Windows/Unix.
    Example: 2026-01-29T18:45:32Z -> 2026-01-29T18-45-32Z
    """
    return iso_timestamp.replace(":", "-")


def _generate_filename(message: SMSMessage) -> str:
    """
    Generate a filename for the message JSON.

    Pattern: {ISO8601-timestamp}-{contact-name-or-phone}.json
    - Timestamp has : replaced with - for filesystem safety
    - Contact name is sanitized for filesystem
    - If no contact, use phone number (+ is valid in filenames)
    """
    timestamp_safe = _format_timestamp_for_filename(message.timestamp)
    if message.contact:
        identifier = _sanitize_filename(message.contact.name)
    else:
        # Use phone number, + is valid in filenames
        identifier = message.remoteNumber
    return f"{timestamp_safe}-{identifier}.json"


def _generate_attachment_filename(
    message: SMSMessage,
    index: int,
    content_type: str,
) -> str:
    """
    Generate a filename for an MMS attachment.

    Pattern: {timestamp}-{contact}-attachment-{n}.{ext}
    """
    timestamp_safe = _format_timestamp_for_filename(message.timestamp)
    if message.contact:
        identifier = _sanitize_filename(message.contact.name)
    else:
        identifier = message.remoteNumber

    # Determine extension from MIME type
    ext = mimetypes.guess_extension(content_type)
    if not ext:
        ext = ".bin"  # Fallback for unknown types
    # Remove leading dot if present (mimetypes returns ".jpg")
    ext = ext.lstrip(".")

    return f"{timestamp_safe}-{identifier}-attachment-{index}.{ext}"


class SMSStorage:
    """
    Service for storing and retrieving SMS/MMS messages.

    Messages are stored as JSON files in ./data/sms/{localNumber}/ directory.
    """

    def __init__(self, data_dir: str | None = None):
        """
        Initialize the SMS storage service.

        Args:
            data_dir: Base data directory. Defaults to DATA_DIR env var or ./data
        """
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._sms_dir = self._data_dir / "sms"

    def _get_message_dir(self, local_number: str) -> Path:
        """Get the directory for a specific local number."""
        # Remove + prefix for directory name (cleaner paths)
        safe_number = local_number.lstrip("+")
        return self._sms_dir / safe_number

    def _ensure_dir(self, dir_path: Path) -> None:
        """Create directory if it doesn't exist."""
        dir_path.mkdir(parents=True, exist_ok=True)

    async def _download_attachment(
        self,
        url: str,
        filepath: Path,
        *,
        timeout: float = ATTACHMENT_DOWNLOAD_TIMEOUT,
    ) -> int:
        """
        Download a media attachment from Telnyx URL.

        Args:
            url: The attachment URL to download from
            filepath: Local path to save the file
            timeout: Request timeout in seconds

        Returns:
            Size of downloaded file in bytes

        Raises:
            httpx.HTTPError: On download failure
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Write to file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(response.content)

            size = len(response.content)
            logger.info(
                "Downloaded attachment (%d bytes) to %s",
                size,
                filepath,
            )
            return size

    async def store_message_async(self, message: SMSMessage) -> Path:
        """
        Store a message to disk, downloading any attachments first.

        This is the async version that handles MMS attachments.

        Args:
            message: The SMSMessage to store

        Returns:
            Path to the stored JSON file
        """
        message_dir = self._get_message_dir(message.localNumber)
        self._ensure_dir(message_dir)

        # Download attachments and update their filenames
        updated_attachments = []
        for i, attachment in enumerate(message.attachments, start=1):
            if attachment.originalUrl:
                # Generate local filename
                local_filename = _generate_attachment_filename(
                    message,
                    i,
                    attachment.contentType,
                )
                local_path = message_dir / local_filename

                try:
                    size = await self._download_attachment(
                        attachment.originalUrl,
                        local_path,
                    )
                    # Update attachment with local filename and actual size
                    updated_attachments.append(
                        Attachment(
                            filename=local_filename,
                            contentType=attachment.contentType,
                            size=size,
                            originalUrl=attachment.originalUrl,
                        )
                    )
                except httpx.HTTPError as exc:
                    logger.error(
                        "Failed to download attachment from %s: %s",
                        attachment.originalUrl,
                        exc,
                    )
                    # Keep original attachment info without download
                    updated_attachments.append(attachment)
            else:
                # No URL to download, keep as-is
                updated_attachments.append(attachment)

        # Create updated message with downloaded attachments
        message_data = message.model_dump(mode="json")
        message_data["attachments"] = [a.model_dump(mode="json") for a in updated_attachments]

        filename = _generate_filename(message)
        filepath = message_dir / filename

        # Write JSON with pretty formatting
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(message_data, f, indent=2, ensure_ascii=False)

        logger.info(
            "Stored SMS message %s to %s",
            message.id,
            filepath,
        )
        return filepath

    def store_message(self, message: SMSMessage) -> Path:
        """
        Store a message to disk.

        Args:
            message: The SMSMessage to store

        Returns:
            Path to the stored JSON file
        """
        message_dir = self._get_message_dir(message.localNumber)
        self._ensure_dir(message_dir)

        filename = _generate_filename(message)
        filepath = message_dir / filename

        # Write JSON with pretty formatting
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(message.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        logger.info(
            "Stored SMS message %s to %s",
            message.id,
            filepath,
        )
        return filepath

    def get_recent_messages(
        self,
        local_number: str | None = None,
        remote_number: str | None = None,
        contact_name: str | None = None,
        limit: int = 50,
    ) -> list[SMSMessage]:
        """
        Retrieve and filter stored messages.

        Args:
            local_number: Filter by local (Telnyx) number
            remote_number: Filter by remote party's number
            contact_name: Filter by contact name (case-insensitive partial match)
            limit: Maximum number of messages to return

        Returns:
            List of messages sorted by timestamp descending (most recent first)
        """
        messages: list[SMSMessage] = []

        # Determine which directories to search
        if local_number:
            dirs_to_search = [self._get_message_dir(local_number)]
        else:
            # Search all local number directories
            if not self._sms_dir.exists():
                return []
            dirs_to_search = [d for d in self._sms_dir.iterdir() if d.is_dir()]

        # Collect all message files
        message_files: list[tuple[Path, float]] = []
        for dir_path in dirs_to_search:
            if not dir_path.exists():
                continue
            for json_file in dir_path.glob("*.json"):
                # Use modification time for initial sorting
                mtime = json_file.stat().st_mtime
                message_files.append((json_file, mtime))

        # Sort by modification time descending for efficient limiting
        message_files.sort(key=lambda x: x[1], reverse=True)

        # Load and filter messages
        contact_name_lower = contact_name.lower() if contact_name else None

        for filepath, _ in message_files:
            if len(messages) >= limit:
                break

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                message = SMSMessage.model_validate(data)

                # Apply filters
                if remote_number and message.remoteNumber != remote_number:
                    continue
                if contact_name_lower:
                    if not message.contact:
                        continue
                    if contact_name_lower not in message.contact.name.lower():
                        continue

                messages.append(message)
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning("Failed to load message from %s: %s", filepath, exc)
                continue

        # Sort by timestamp descending (most recent first)
        messages.sort(
            key=lambda m: m.timestamp,
            reverse=True,
        )

        return messages[:limit]

    def get_message_by_id(self, message_id: str) -> SMSMessage | None:
        """
        Retrieve a specific message by its ID.

        Args:
            message_id: The unique message ID

        Returns:
            The message if found, None otherwise
        """
        if not self._sms_dir.exists():
            return None

        # Search all directories for the message
        for dir_path in self._sms_dir.iterdir():
            if not dir_path.is_dir():
                continue
            for json_file in dir_path.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("id") == message_id:
                        return SMSMessage.model_validate(data)
                except (json.JSONDecodeError, Exception):
                    continue

        return None

    def get_message_filepath(self, message: SMSMessage) -> Path:
        """
        Get the expected filepath for a message.

        Useful for determining where attachments should be stored.

        Args:
            message: The SMSMessage

        Returns:
            Path to where the message JSON file would be stored
        """
        message_dir = self._get_message_dir(message.localNumber)
        filename = _generate_filename(message)
        return message_dir / filename


__all__ = [
    "SMSStorage",
    "SMSMessage",
    "Contact",
    "Attachment",
]
