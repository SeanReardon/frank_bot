"""Tests for SMS compliance service."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sms_compliance import (
    HELP_KEYWORDS,
    HELP_RESPONSE,
    OPT_IN_KEYWORDS,
    OPT_IN_RESPONSE,
    OPT_OUT_KEYWORDS,
    STOP_RESPONSE,
    ComplianceKeyword,
    SMSComplianceService,
    detect_compliance_keyword,
    get_keyword_type,
)


class TestDetectComplianceKeyword:
    """Tests for detect_compliance_keyword function."""

    def test_detects_stop(self):
        """Should detect STOP keyword."""
        assert detect_compliance_keyword("STOP") == ComplianceKeyword.STOP
        assert detect_compliance_keyword("stop") == ComplianceKeyword.STOP
        assert detect_compliance_keyword("Stop") == ComplianceKeyword.STOP
        assert detect_compliance_keyword("  STOP  ") == ComplianceKeyword.STOP

    def test_detects_other_opt_out_keywords(self):
        """Should detect other opt-out keywords."""
        assert detect_compliance_keyword("unsubscribe") == ComplianceKeyword.UNSUBSCRIBE
        assert detect_compliance_keyword("CANCEL") == ComplianceKeyword.CANCEL
        assert detect_compliance_keyword("end") == ComplianceKeyword.END
        assert detect_compliance_keyword("QUIT") == ComplianceKeyword.QUIT
        assert detect_compliance_keyword("stopall") == ComplianceKeyword.STOPALL

    def test_detects_help(self):
        """Should detect HELP keyword."""
        assert detect_compliance_keyword("HELP") == ComplianceKeyword.HELP
        assert detect_compliance_keyword("help") == ComplianceKeyword.HELP
        assert detect_compliance_keyword("INFO") == ComplianceKeyword.INFO

    def test_detects_opt_in_keywords(self):
        """Should detect opt-in keywords."""
        assert detect_compliance_keyword("START") == ComplianceKeyword.START
        assert detect_compliance_keyword("yes") == ComplianceKeyword.YES
        assert detect_compliance_keyword("OPTIN") == ComplianceKeyword.OPTIN
        assert detect_compliance_keyword("subscribe") == ComplianceKeyword.SUBSCRIBE
        assert detect_compliance_keyword("unstop") == ComplianceKeyword.UNSTOP

    def test_returns_none_for_non_keyword(self):
        """Should return None for non-compliance messages."""
        assert detect_compliance_keyword("Hello") is None
        assert detect_compliance_keyword("STOP IT") is None
        assert detect_compliance_keyword("Please stop") is None
        assert detect_compliance_keyword("") is None
        assert detect_compliance_keyword("  ") is None

    def test_returns_none_for_none_input(self):
        """Should return None for None input."""
        assert detect_compliance_keyword(None) is None


class TestGetKeywordType:
    """Tests for get_keyword_type function."""

    def test_opt_out_keywords(self):
        """Should return 'opt_out' for opt-out keywords."""
        for keyword in OPT_OUT_KEYWORDS:
            assert get_keyword_type(keyword) == "opt_out"

    def test_help_keywords(self):
        """Should return 'help' for help keywords."""
        for keyword in HELP_KEYWORDS:
            assert get_keyword_type(keyword) == "help"

    def test_opt_in_keywords(self):
        """Should return 'opt_in' for opt-in keywords."""
        for keyword in OPT_IN_KEYWORDS:
            assert get_keyword_type(keyword) == "opt_in"


class TestSMSComplianceService:
    """Tests for SMSComplianceService class."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def service(self, temp_data_dir):
        """Create a compliance service with temp data dir."""
        return SMSComplianceService(data_dir=temp_data_dir)

    def test_is_opted_out_returns_false_initially(self, service):
        """Should return False when no opt-outs exist."""
        assert service.is_opted_out("+15551234567") is False

    def test_record_opt_out(self, service, temp_data_dir):
        """Should record opt-out and persist to file."""
        phone = "+15551234567"
        service.record_opt_out(phone)

        assert service.is_opted_out(phone) is True

        # Verify file was created
        opt_outs_file = Path(temp_data_dir) / "opt_outs.json"
        assert opt_outs_file.exists()

        with open(opt_outs_file) as f:
            data = json.load(f)
            assert phone in data["opt_outs"]
            assert "opted_out_at" in data["opt_outs"][phone]

    def test_record_opt_in_removes_opt_out(self, service):
        """Should remove phone from opt-out list when opting in."""
        phone = "+15551234567"

        # First opt out
        service.record_opt_out(phone)
        assert service.is_opted_out(phone) is True

        # Then opt in
        was_opted_out = service.record_opt_in(phone)
        assert was_opted_out is True
        assert service.is_opted_out(phone) is False

    def test_record_opt_in_returns_false_if_not_opted_out(self, service):
        """Should return False if phone wasn't opted out."""
        phone = "+15551234567"
        was_opted_out = service.record_opt_in(phone)
        assert was_opted_out is False

    def test_get_opt_out_count(self, service):
        """Should return correct count of opt-outs."""
        assert service.get_opt_out_count() == 0

        service.record_opt_out("+15551234567")
        assert service.get_opt_out_count() == 1

        service.record_opt_out("+15559876543")
        assert service.get_opt_out_count() == 2

        service.record_opt_in("+15551234567")
        assert service.get_opt_out_count() == 1

    def test_loads_existing_opt_outs(self, temp_data_dir):
        """Should load existing opt-outs from file."""
        # Create opt_outs.json manually
        opt_outs_file = Path(temp_data_dir) / "opt_outs.json"
        with open(opt_outs_file, "w") as f:
            json.dump({
                "opt_outs": {
                    "+15551234567": {"opted_out_at": "2026-01-30T12:00:00+00:00"}
                },
                "updated_at": "2026-01-30T12:00:00+00:00",
            }, f)

        # Create new service and verify it loads the data
        service = SMSComplianceService(data_dir=temp_data_dir)
        assert service.is_opted_out("+15551234567") is True
        assert service.is_opted_out("+15559876543") is False

    def test_handles_corrupted_file(self, temp_data_dir):
        """Should handle corrupted opt_outs.json gracefully."""
        opt_outs_file = Path(temp_data_dir) / "opt_outs.json"
        with open(opt_outs_file, "w") as f:
            f.write("not valid json")

        service = SMSComplianceService(data_dir=temp_data_dir)
        # Should not raise, should return False
        assert service.is_opted_out("+15551234567") is False


class TestComplianceResponses:
    """Tests for compliance response messages."""

    def test_stop_response_content(self):
        """STOP response should contain unsubscribe confirmation and START info."""
        assert "unsubscribed" in STOP_RESPONSE.lower()
        assert "START" in STOP_RESPONSE

    def test_help_response_content(self):
        """HELP response should contain service info and STOP info."""
        assert "STOP" in HELP_RESPONSE

    def test_opt_in_response_content(self):
        """OPT_IN response should contain re-subscribe confirmation and STOP info."""
        assert "re-subscribed" in OPT_IN_RESPONSE.lower() or "subscribed" in OPT_IN_RESPONSE.lower()
        assert "STOP" in OPT_IN_RESPONSE
