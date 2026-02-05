"""
Tests for Android phone audit logging.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, "/home/claudia/dev/frank_bot")

from services.android_audit import (
    AuditEntry,
    AndroidAuditLogger,
    get_android_audit_logger,
    reset_audit_logger,
)


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_creates_entry_with_required_fields(self) -> None:
        """Creates entry with required fields."""
        entry = AuditEntry(
            timestamp="2026-02-05T10:00:00Z",
            action="thermostat_set_range",
        )
        assert entry.action == "thermostat_set_range"
        assert entry.timestamp == "2026-02-05T10:00:00Z"
        assert entry.success is True  # Default

    def test_to_json_line_format(self) -> None:
        """Converts to JSON line format."""
        entry = AuditEntry(
            timestamp="2026-02-05T10:00:00Z",
            action="get_screen",
            parameters={"include_xml": True},
            success=True,
            tokens_used=150,
            duration_ms=500,
        )

        json_line = entry.to_json_line()
        parsed = json.loads(json_line)

        assert parsed["action"] == "get_screen"
        assert parsed["tokens_used"] == 150
        assert parsed["duration_ms"] == 500
        assert parsed["parameters"]["include_xml"] is True

    def test_removes_none_values_from_json(self) -> None:
        """Removes None values from JSON output."""
        entry = AuditEntry(
            timestamp="2026-02-05T10:00:00Z",
            action="tap",
            error=None,  # Should not appear in output
            screenshot_size_bytes=None,  # Should not appear
        )

        json_line = entry.to_json_line()
        parsed = json.loads(json_line)

        assert "error" not in parsed
        assert "screenshot_size_bytes" not in parsed


class TestAndroidAuditLogger:
    """Tests for AndroidAuditLogger."""

    def test_creates_log_directory_if_missing(self) -> None:
        """Creates log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "subdir", "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(action="test_action")

            assert os.path.exists(os.path.dirname(log_path))

    def test_logs_action_to_file(self) -> None:
        """Logs action entries to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(
                action="thermostat_set_range",
                parameters={"low_temp": 68, "high_temp": 72},
                success=True,
                tokens_used=500,
                duration_ms=5000,
            )

            # Read the log file
            with open(log_path, "r") as f:
                content = f.read()

            assert "thermostat_set_range" in content
            assert "500" in content  # tokens
            assert "5000" in content  # duration

    def test_logs_json_lines_format(self) -> None:
        """Log entries are valid JSON lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(action="action1")
            logger.log_action(action="action2")

            # Each line should be valid JSON
            with open(log_path, "r") as f:
                lines = f.readlines()

            assert len(lines) == 2
            for line in lines:
                parsed = json.loads(line.strip())
                assert "action" in parsed
                assert "timestamp" in parsed

    def test_sanitizes_screenshot_data(self) -> None:
        """Does not log full screenshot data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(
                action="get_screen",
                parameters={"screenshot_base64": "abc123" * 1000},  # Large screenshot
                result={"screenshot_base64": "xyz" * 1000, "element_count": 50},
            )

            with open(log_path, "r") as f:
                content = f.read()

            # Should not contain the actual screenshot data
            assert "abc123" * 100 not in content
            # Should contain metadata
            assert "element_count" in content or "screenshot_size_bytes" in content

    def test_sanitizes_sensitive_params(self) -> None:
        """Redacts sensitive parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            safe_params = logger._sanitize_params({
                "api_key": "super-secret-key",
                "password": "hunter2",
                "normal_param": "visible",
            })

            assert safe_params["api_key"] == "<redacted>"
            assert safe_params["password"] == "<redacted>"
            assert safe_params["normal_param"] == "visible"

    def test_truncates_api_key_in_entry(self) -> None:
        """Only logs first 8 chars of API key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(
                action="test",
                api_key="super-long-api-key-12345",
            )

            with open(log_path, "r") as f:
                line = f.readline()

            parsed = json.loads(line)
            assert parsed["api_key_prefix"] == "super-lo..."
            assert "super-long-api-key-12345" not in line

    def test_get_recent_entries_returns_most_recent_first(self) -> None:
        """Returns entries in reverse chronological order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            # Log in order
            logger.log_action(action="first")
            logger.log_action(action="second")
            logger.log_action(action="third")

            entries = logger.get_recent_entries(limit=10)

            assert len(entries) == 3
            assert entries[0]["action"] == "third"  # Most recent
            assert entries[2]["action"] == "first"  # Oldest

    def test_get_recent_entries_respects_limit(self) -> None:
        """Respects the limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            for i in range(10):
                logger.log_action(action=f"action_{i}")

            entries = logger.get_recent_entries(limit=3)

            assert len(entries) == 3

    def test_get_recent_entries_filters_by_action(self) -> None:
        """Filters entries by action name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(action="get_screen")
            logger.log_action(action="thermostat_set_range")
            logger.log_action(action="get_screen")
            logger.log_action(action="tap")

            entries = logger.get_recent_entries(action_filter="get_screen")

            assert len(entries) == 2
            assert all(e["action"] == "get_screen" for e in entries)

    def test_get_stats_returns_aggregate_stats(self) -> None:
        """Returns aggregate statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            logger.log_action(action="get_screen", success=True, tokens_used=100)
            logger.log_action(action="thermostat_set_range", success=True, tokens_used=500)
            logger.log_action(action="get_screen", success=False, tokens_used=50, error="Device offline")

            stats = logger.get_stats()

            assert stats["total_actions"] == 3
            assert stats["successful_actions"] == 2
            assert stats["failed_actions"] == 1
            assert stats["total_tokens_used"] == 650
            assert stats["actions_by_type"]["get_screen"] == 2
            assert stats["actions_by_type"]["thermostat_set_range"] == 1

    def test_handles_missing_log_file(self) -> None:
        """Handles missing log file gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "nonexistent", "audit.log")
            logger = AndroidAuditLogger(log_path=log_path)

            # Don't initialize by logging first
            entries = logger.get_recent_entries()
            stats = logger.get_stats()

            assert entries == []
            assert stats["total_actions"] == 0


class TestGetAndroidAuditLogger:
    """Tests for get_android_audit_logger singleton."""

    def test_returns_singleton_instance(self) -> None:
        """Returns the same instance on multiple calls."""
        reset_audit_logger()

        logger1 = get_android_audit_logger()
        logger2 = get_android_audit_logger()

        assert logger1 is logger2

    def test_reset_clears_singleton(self) -> None:
        """reset_audit_logger clears the singleton."""
        reset_audit_logger()

        logger1 = get_android_audit_logger()
        reset_audit_logger()
        logger2 = get_android_audit_logger()

        assert logger1 is not logger2
