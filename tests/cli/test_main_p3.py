"""Tests for Phase 3 CLI command handlers."""
import argparse
import pytest
from unittest.mock import MagicMock, patch

from backend.common.models import CliResponse


# ──────────────────────────────────────────────────────────────────────────── #
#   Log analytics handlers
# ──────────────────────────────────────────────────────────────────────────── #

class TestCmdLogDealActivity:

    def test_cmd_log_deal_activity_success(self, log_db):
        from cli.main import cmd_log_deal_activity
        from backend.logs.models import DealActivity

        args = argparse.Namespace(
            db_path=log_db,
            did="CSMC",
            days=30,
            db_mode=None,
            secrets_path=None,
        )
        response = cmd_log_deal_activity(args)
        assert response.success is True
        assert response.command == "log_deal_activity"
        assert "events" in response.data

    def test_cmd_log_deal_activity_not_found(self, tmp_path):
        from cli.main import cmd_log_deal_activity

        args = argparse.Namespace(
            db_path=str(tmp_path / "missing.db"),
            did="X",
            days=30,
            db_mode=None,
            secrets_path=None,
        )
        response = cmd_log_deal_activity(args)
        assert response.success is False
        assert len(response.errors) > 0


class TestCmdLogDidFailures:

    def test_cmd_log_did_failures_success(self, log_db):
        from cli.main import cmd_log_did_failures

        args = argparse.Namespace(
            db_path=log_db,
            days=30,
            job_filter=None,
        )
        response = cmd_log_did_failures(args)
        assert response.success is True
        assert response.command == "log_did_failures"
        assert "failures" in response.data

    def test_cmd_log_did_failures_with_filter(self, log_db):
        from cli.main import cmd_log_did_failures

        args = argparse.Namespace(
            db_path=log_db,
            days=30,
            job_filter="TestJob_Alpha",
        )
        response = cmd_log_did_failures(args)
        assert response.success is True
        for f in response.data["failures"]:
            assert "TestJob_Alpha" in f["affected_jobs"]


class TestCmdLogJobHealth:

    def test_cmd_log_job_health_success(self, log_db):
        from cli.main import cmd_log_job_health

        args = argparse.Namespace(
            db_path=log_db,
            job_name="TestJob_Alpha",
            days=30,
        )
        response = cmd_log_job_health(args)
        assert response.success is True
        assert response.command == "log_job_health"
        assert response.data["job_name"] == "TestJob_Alpha"

    def test_cmd_log_job_health_ambiguous(self, log_db):
        from cli.main import cmd_log_job_health

        args = argparse.Namespace(
            db_path=log_db,
            job_name="TestJob",
            days=30,
        )
        response = cmd_log_job_health(args)
        assert response.success is False
        assert any("Ambiguous" in e or "ambiguous" in e.lower() for e in response.errors)


class TestCmdLogDailySummary:

    def test_cmd_log_daily_summary_success(self, log_db):
        from cli.main import cmd_log_daily_summary

        args = argparse.Namespace(
            db_path=log_db,
            date=None,
        )
        response = cmd_log_daily_summary(args)
        assert response.success is True
        assert response.command == "log_daily_summary"
        assert "total_jobs_run" in response.data

    def test_cmd_log_daily_summary_specific_date(self, log_db):
        from cli.main import cmd_log_daily_summary
        from datetime import datetime, timedelta, timezone

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        args = argparse.Namespace(
            db_path=log_db,
            date=yesterday,
        )
        response = cmd_log_daily_summary(args)
        assert response.success is True
        assert response.data["date"] == yesterday


# ──────────────────────────────────────────────────────────────────────────── #
#   Triage handlers
# ──────────────────────────────────────────────────────────────────────────── #

class TestCmdTriageVerify:

    def test_cmd_triage_verify_success(self):
        from cli.main import cmd_triage_verify
        from backend.triage.models import EmailInfo, TriageResult

        result = TriageResult(
            email_info=EmailInfo(
                sender="s@x.com", sender_name="S", subject="Sub", date="2025-01-15",
            ),
            has_match=True,
            recommendation="Best match: TestJob_Alpha",
        )

        args = argparse.Namespace(
            settings_path="fake.xml",
            xml_type="email",
            msg_path="C:\\emails\\test.msg",
            db_mode=None,
            secrets_path=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            inst = MagicMock()
            inst.verify.return_value = result
            cls.return_value = inst
            response = cmd_triage_verify(args)

        assert response.success is True
        assert response.command == "triage_verify"

    def test_cmd_triage_verify_file_not_found(self):
        from cli.main import cmd_triage_verify

        args = argparse.Namespace(
            settings_path="fake.xml",
            xml_type="email",
            msg_path="C:\\missing.msg",
            db_mode=None,
            secrets_path=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            inst = MagicMock()
            inst.verify.side_effect = FileNotFoundError(".msg file not found")
            cls.return_value = inst
            response = cmd_triage_verify(args)

        assert response.success is False


class TestCmdTriageMatch:

    def test_cmd_triage_match_by_sender(self):
        from cli.main import cmd_triage_match
        from backend.triage.models import EmailInfo, TriageResult

        result = TriageResult(
            email_info=EmailInfo(
                sender="s@x.com", sender_name="", subject="", date="",
            ),
            has_match=True,
        )

        args = argparse.Namespace(
            settings_path="fake.xml",
            xml_type="email",
            msg_path=None,
            sender="s@x.com",
            subject=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            inst = MagicMock()
            inst.match_only.return_value = result
            cls.return_value = inst
            response = cmd_triage_match(args)

        assert response.success is True
        assert response.command == "triage_match"

    def test_cmd_triage_match_no_args(self):
        from cli.main import cmd_triage_match

        args = argparse.Namespace(
            settings_path="fake.xml",
            xml_type="email",
            msg_path=None,
            sender=None,
            subject=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            inst = MagicMock()
            inst.match_only.side_effect = ValueError("Provide --msg-path, --sender, or --subject")
            cls.return_value = inst
            response = cmd_triage_match(args)

        assert response.success is False
        assert any("Provide" in e for e in response.errors)


class TestCmdTriageNew:

    def test_cmd_triage_new_success(self):
        from cli.main import cmd_triage_new
        from backend.triage.models import EmailInfo, TriageResult

        result = TriageResult(
            email_info=EmailInfo(
                sender="new@vendor.com", sender_name="Vendor",
                subject="New Data", date="2025-01-15",
            ),
            has_match=False,
            suggested_config={"suggested_parser": "excel"},
            recommendation="No match. Suggested parser: excel.",
        )

        args = argparse.Namespace(
            settings_path="fake.xml",
            xml_type="email",
            msg_path="C:\\emails\\new.msg",
            db_mode=None,
            secrets_path=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            inst = MagicMock()
            inst.analyze_new.return_value = result
            cls.return_value = inst
            response = cmd_triage_new(args)

        assert response.success is True
        assert response.command == "triage_new"

    def test_cmd_triage_new_invalid_settings(self):
        from cli.main import cmd_triage_new

        args = argparse.Namespace(
            settings_path="bad.xml",
            xml_type="email",
            msg_path="C:\\new.msg",
            db_mode=None,
            secrets_path=None,
        )

        with patch("backend.triage.analyzer.TriageAnalyzer") as cls:
            cls.side_effect = ValueError("Failed to parse settings XML")
            response = cmd_triage_new(args)

        assert response.success is False
        assert any("settings" in e.lower() for e in response.errors)
