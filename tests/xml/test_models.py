"""Tests for EmailJob, SftpJob, ValidationResult, CliResponse, and LogEvent models."""
import pytest

from backend.xml.models import EmailJob, SftpJob, ValidationResult
from backend.common.models import CliResponse
from backend.logs.models import LogEvent


# ── EmailJob ─────────────────────────────────────────────────────────── #

class TestEmailJob:

    def _make_job(self, **overrides):
        defaults = dict(
            name="TestJob_Alpha",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="admin@example.com",
            servicer_id=150,
            save_location="{DealFolder}\\incoming\\",
            filters={"From": "*"},
            parsers={"ConditionalParser": "^RPT.+\\.xlsx?$"},
            templates={"ChecklistTemplate": "CL_Standard"},
            queue_one_file=True,
            day_adjust=-1,
        )
        defaults.update(overrides)
        return EmailJob(**defaults)

    def test_email_job_to_dict(self):
        job = self._make_job()
        d = job.to_dict()
        for key in ("name", "mailbox", "folder", "sme", "servicer_id",
                     "save_location", "filters", "parsers", "templates",
                     "queue_one_file", "day_adjust", "xml_type"):
            assert key in d, f"Missing key: {key}"
        assert d["xml_type"] == "email"

    def test_email_job_matches_query_name(self):
        job = self._make_job()
        assert job.matches_query("TestJob_Alpha")

    def test_email_job_matches_query_mailbox(self):
        job = self._make_job()
        assert job.matches_query("frp.test@example.com")

    def test_email_job_matches_query_servicer(self):
        job = self._make_job()
        assert job.matches_query("150")

    def test_email_job_matches_query_case_insensitive(self):
        job = self._make_job()
        assert job.matches_query("TESTJOB")

    def test_email_job_no_match(self):
        job = self._make_job()
        assert not job.matches_query("zzz_nonexistent")


# ── SftpJob ──────────────────────────────────────────────────────────── #

class TestSftpJob:

    def _make_job(self, **overrides):
        defaults = dict(
            name="TestSftp_Alpha",
            path=r"\\sftp-server\incoming\alpha",
            servicer_id=150,
            dsn="SftpConnection1",
            sme="admin@example.com",
            save_location="{DealFolder}\\sftp\\",
            skip_list=r"\\server\config\skip.txt",
            ignore_list=r"\\server\config\ignore.txt",
            parsers={"StandardParser": r"\.csv$"},
            zip_content_filter=".csv,.txt,.xlsx",
            templates={"ChecklistTemplate": "CL_SFTP"},
        )
        defaults.update(overrides)
        return SftpJob(**defaults)

    def test_sftp_job_to_dict(self):
        job = self._make_job()
        d = job.to_dict()
        for key in ("name", "path", "servicer_id", "dsn", "sme",
                     "save_location", "skip_list", "ignore_list",
                     "parsers", "zip_content_filter", "templates",
                     "xml_type"):
            assert key in d, f"Missing key: {key}"
        assert d["xml_type"] == "sftp"

    def test_sftp_job_matches_query_path(self):
        job = self._make_job()
        assert job.matches_query("sftp-server")


# ── ValidationResult ─────────────────────────────────────────────────── #

class TestValidationResult:

    def test_validation_result_default_valid(self):
        vr = ValidationResult()
        assert vr.valid is True
        assert vr.errors == []

    def test_validation_result_add_error_makes_invalid(self):
        vr = ValidationResult()
        vr.add_error("E001: test error")
        assert vr.valid is False
        assert len(vr.errors) == 1

    def test_validation_result_to_dict(self):
        vr = ValidationResult()
        vr.add_warning("W001: test warning")
        vr.add_info("I001: test info")
        d = vr.to_dict()
        for key in ("valid", "errors", "warnings", "info", "xml_type", "job_count"):
            assert key in d, f"Missing key: {key}"


# ── CliResponse ──────────────────────────────────────────────────────── #

class TestCliResponse:

    def test_cli_response_add_error(self):
        resp = CliResponse(success=True, command="test")
        resp.add_error("Something went wrong")
        assert resp.success is False
        assert "Something went wrong" in resp.errors

    def test_cli_response_add_warning(self):
        resp = CliResponse(success=True, command="test")
        resp.add_warning("Minor issue")
        assert resp.success is True
        assert "Minor issue" in resp.warnings


# ── LogEvent ─────────────────────────────────────────────────────────── #

class TestLogEvent:

    def test_log_event_to_dict(self):
        event = LogEvent(
            log_file="EmailMonitor_20250115.log",
            log_type="email",
            timestamp="2025-01-15 08:00:05.000",
            job_name="TestJob_Alpha",
            mailbox="frp.test@example.com",
            event_type="job_start",
            emails_found=3,
            subject="January Report",
            sender="sender@partner.com",
            parser="ConditionalParser",
            filename="RPT_Jan2025.xlsx",
            template="CL_Standard",
            error_message=None,
            raw_line="2025-01-15 08:00:05.000:\tStarting Outlook download...",
        )
        d = event.to_dict()
        for key in ("log_file", "log_type", "timestamp", "job_name",
                     "mailbox", "event_type", "emails_found", "subject",
                     "sender", "parser", "filename", "template",
                     "error_message", "raw_line"):
            assert key in d, f"Missing key: {key}"
        assert d["job_name"] == "TestJob_Alpha"
        assert d["event_type"] == "job_start"
