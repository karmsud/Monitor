"""Integration tests — run CLI commands end-to-end against real fixture files.

These tests invoke the actual command handlers with real XML/log fixtures
(no mocking of backend modules), validating the full pipeline from CLI
entry point to JSON output.
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
EMAIL_XML = os.path.join(FIXTURES, "email_settings_valid.xml")
SFTP_XML = os.path.join(FIXTURES, "sftp_settings_valid.xml")
LOG_DIR = os.path.join(FIXTURES, "logs")


# ================================================================== #
#  Helper: run CLI as subprocess (true integration)
# ================================================================== #

def _run_cli(*args: str, timeout: int = 30, expect_success: bool = True) -> dict:
    """Spawn ``python -m cli.main <args>`` and parse JSON stdout."""
    cmd = [sys.executable, "-m", "cli.main", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    stdout = result.stdout.strip()
    assert stdout, (
        f"CLI produced no stdout.\nstderr: {result.stderr}\nreturncode: {result.returncode}"
    )
    return json.loads(stdout)


# ================================================================== #
#  Phase 1: Foundation commands
# ================================================================== #

class TestSearchJobsIntegration:
    """End-to-end search_jobs against real XML fixtures."""

    def test_search_all_email_jobs(self):
        data = _run_cli(
            "search_jobs",
            "--query", "test",
            "--settings-path", EMAIL_XML,
            "--xml-type", "email",
        )
        assert data["success"] is True
        assert data["command"] == "search_jobs"
        assert data["data"]["total_count"] == 3
        names = [j["job_name"] for j in data["data"]["jobs"]]
        assert "TestJob_Alpha" in names
        assert "TestJob_Beta" in names
        assert "TestJob_NoServicer" in names

    def test_search_by_servicer(self):
        data = _run_cli(
            "search_jobs",
            "--query", "150",
            "--settings-path", EMAIL_XML,
            "--xml-type", "email",
        )
        assert data["success"] is True
        jobs = data["data"]["jobs"]
        assert any(j["job_name"] == "TestJob_Alpha" for j in jobs)

    def test_search_by_mailbox(self):
        data = _run_cli(
            "search_jobs",
            "--query", "frp.test",
            "--settings-path", EMAIL_XML,
            "--xml-type", "email",
        )
        assert data["success"] is True
        assert data["data"]["total_count"] >= 2

    def test_search_sftp_jobs(self):
        data = _run_cli(
            "search_jobs",
            "--query", "test",
            "--settings-path", EMAIL_XML,
            "--sftp-settings-path", SFTP_XML,
            "--xml-type", "all",
        )
        assert data["success"] is True
        # 3 email + 2 sftp = 5
        assert data["data"]["total_count"] == 5

    def test_search_no_match(self):
        data = _run_cli(
            "search_jobs",
            "--query", "zzz_nonexistent_zzz",
            "--settings-path", EMAIL_XML,
            "--xml-type", "email",
        )
        assert data["success"] is True
        assert data["data"]["total_count"] == 0


class TestValidateXmlIntegration:
    """End-to-end validate_xml against real XML fixtures."""

    def test_validate_valid_email_xml(self):
        data = _run_cli(
            "validate_xml",
            "--settings-path", EMAIL_XML,
        )
        assert data["success"] is True
        assert data["command"] == "validate_xml"
        validation = data["data"]
        assert validation["valid"] is True
        assert isinstance(validation["errors"], list)
        assert isinstance(validation["warnings"], list)
        assert isinstance(validation["info"], list)

    def test_validate_valid_sftp_xml(self):
        data = _run_cli(
            "validate_xml",
            "--settings-path", SFTP_XML,
        )
        assert data["success"] is True
        assert data["data"]["valid"] is True

    def test_validate_invalid_xml(self):
        invalid = os.path.join(FIXTURES, "email_settings_invalid.xml")
        data = _run_cli(
            "validate_xml",
            "--settings-path", invalid,
        )
        # Invalid XML causes a parse error — the CLI reports success=false
        assert data["success"] is False
        assert len(data["errors"]) > 0

    def test_validate_missing_fields(self):
        missing = os.path.join(FIXTURES, "email_settings_missing.xml")
        data = _run_cli(
            "validate_xml",
            "--settings-path", missing,
        )
        assert data["success"] is True
        assert len(data["data"]["errors"]) > 0


class TestSyncLogsIntegration:
    """End-to-end log sync against real log fixture files."""

    def test_sync_logs(self, tmp_path):
        db_path = str(tmp_path / "integration_logs.db")
        data = _run_cli(
            "sync_logs",
            "--log-folder", LOG_DIR,
            "--db-path", db_path,
            "--retention-months", "600",  # keep everything (fixtures are old)
        )
        assert data["success"] is True
        assert data["command"] == "sync_logs"
        summary = data["data"]
        assert summary["files_processed"] >= 1
        assert summary["events_indexed"] > 0
        assert summary["files_errored"] == 0

        # Verify SQLite DB was actually created with data
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
        conn.close()
        assert count == summary["events_indexed"]

    def test_sync_logs_incremental(self, tmp_path):
        """Second sync should skip already-indexed files."""
        db_path = str(tmp_path / "inc_logs.db")

        # First sync
        data1 = _run_cli(
            "sync_logs",
            "--log-folder", LOG_DIR,
            "--db-path", db_path,
            "--retention-months", "600",
        )
        assert data1["data"]["files_processed"] >= 1

        # Second sync
        data2 = _run_cli(
            "sync_logs",
            "--log-folder", LOG_DIR,
            "--db-path", db_path,
            "--retention-months", "600",
        )
        assert data2["data"]["files_processed"] == 0
        assert data2["data"]["files_skipped"] >= 1


class TestBackupsIntegration:
    """End-to-end backup list / save against real XML fixtures."""

    def test_list_backups_empty(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)
        data = _run_cli(
            "list_backups",
            "--settings-path", xml_copy,
        )
        assert data["success"] is True
        assert len(data["data"]["backups"]) == 0

    def test_save_xml(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)
        data = _run_cli(
            "save_xml",
            "--settings-path", xml_copy,
        )
        assert data["success"] is True
        assert data["command"] == "save_xml"
        assert data["data"]["backup_created"] is True

        # Verify backup directory was created
        backup_dir = tmp_path / "backup"
        assert backup_dir.exists()
        backup_files = list(backup_dir.glob("*.xml"))
        assert len(backup_files) == 1

    def test_list_backups_after_save(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        # Create a backup first
        _run_cli("save_xml", "--settings-path", xml_copy)

        # Now list
        data = _run_cli(
            "list_backups",
            "--settings-path", xml_copy,
        )
        assert data["success"] is True
        assert len(data["data"]["backups"]) == 1


class TestStatusIntegration:
    """End-to-end status command."""

    def test_status(self):
        data = _run_cli("status")
        assert data["success"] is True
        assert data["command"] == "status"
        assert "version" in data["data"]


# ================================================================== #
#  Phase 2: CRUD & Intelligence commands
# ================================================================== #

class TestTemplateInventoryIntegration:

    def test_template_inventory(self):
        data = _run_cli(
            "template_inventory",
            "--settings-path", EMAIL_XML,
        )
        assert data["success"] is True
        templates = data["data"]["templates"]
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_template_inventory_sftp(self):
        data = _run_cli(
            "template_inventory",
            "--settings-path", SFTP_XML,
        )
        assert data["success"] is True
        assert isinstance(data["data"]["templates"], list)


class TestJobCrudIntegration:

    def test_create_job_from_template(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        data = _run_cli(
            "create_job",
            "--settings-path", xml_copy,
            "--template-job", "TestJob_Alpha",
            "--name", "TestJob_Created",
        )
        assert data["success"] is True
        assert data["command"] == "create_job"

        # Verify the new job exists in the XML
        verify = _run_cli(
            "search_jobs",
            "--query", "TestJob_Created",
            "--settings-path", xml_copy,
            "--xml-type", "email",
        )
        assert verify["data"]["total_count"] >= 1

    def test_edit_job(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        data = _run_cli(
            "edit_job",
            "--settings-path", xml_copy,
            "--job-name", "TestJob_Alpha",
            "--field", "ServicerID",
            "--value", "999",
        )
        assert data["success"] is True

        # Verify the change persisted
        verify = _run_cli(
            "search_jobs",
            "--query", "999",
            "--settings-path", xml_copy,
            "--xml-type", "email",
        )
        assert any(
            j["job_name"] == "TestJob_Alpha" and j["servicer_id"] == 999
            for j in verify["data"]["jobs"]
        )

    def test_clone_job(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        prepare = _run_cli(
            "clone_prepare",
            "--settings-path", xml_copy,
            "--source-servicer-id", "150",
        )
        assert prepare["success"] is True

        data = _run_cli(
            "clone_apply",
            "--settings-path", xml_copy,
            "--source-servicer-id", "150",
            "--clone-job-name", prepare["data"]["proposed_job_name"],
            "--assigned-servicer-id", str(prepare["data"]["assigned_servicer_id"]),
            "--overrides-json", '{"Filters/From":"clone@example.com"}',
        )
        assert data["success"] is True
        assert data["data"]["operation"] == "clone"

        verify = _run_cli(
            "search_jobs",
            "--query", prepare["data"]["proposed_job_name"],
            "--settings-path", xml_copy,
            "--xml-type", "email",
        )
        assert any(
            j["job_name"] == prepare["data"]["proposed_job_name"] and j["servicer_id"] == 151
            for j in verify["data"]["jobs"]
        )


class TestXmlDiffIntegration:

    def test_diff_after_edit(self, tmp_path):
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        # Save (creates backup) then edit
        _run_cli("save_xml", "--settings-path", xml_copy)
        _run_cli(
            "edit_job",
            "--settings-path", xml_copy,
            "--job-name", "TestJob_Alpha",
            "--field", "ServicerID",
            "--value", "999",
        )

        data = _run_cli(
            "xml_diff",
            "--settings-path", xml_copy,
        )
        assert data["success"] is True
        diff = data["data"]
        assert diff["total_changes"] > 0


class TestRollbackIntegration:

    def test_rollback_after_edit(self, tmp_path):
        import time
        xml_copy = str(tmp_path / "Settings.xml")
        shutil.copy(EMAIL_XML, xml_copy)

        # Edit (this automatically creates a backup before writing)
        _run_cli(
            "edit_job",
            "--settings-path", xml_copy,
            "--job-name", "TestJob_Alpha",
            "--field", "ServicerID",
            "--value", "999",
        )

        # Discover the backup file created by edit_job
        backup_dir = tmp_path / "backup"
        backup_files = sorted(backup_dir.glob("*.xml"))
        assert len(backup_files) >= 1
        backup_file = str(backup_files[0])

        # Sleep to avoid timestamp collision in backup filenames
        # (rollback creates a safety backup with same naming scheme)
        time.sleep(1.1)

        # Rollback using the backup (which contains the original pre-edit state)
        data = _run_cli(
            "rollback_xml",
            "--settings-path", xml_copy,
            "--backup-file", backup_file,
        )
        assert data["success"] is True

        # Verify the original value is back
        verify = _run_cli(
            "search_jobs",
            "--query", "TestJob_Alpha",
            "--settings-path", xml_copy,
            "--xml-type", "email",
        )
        alpha = [j for j in verify["data"]["jobs"] if j["job_name"] == "TestJob_Alpha"]
        assert len(alpha) == 1
        assert alpha[0]["servicer_id"] == 150  # original value


# ================================================================== #
#  Phase 3: Log Analytics (against real synced data)
# ================================================================== #

class TestLogAnalyticsIntegration:
    """Run log analytics against a freshly synced SQLite DB from fixtures."""

    @pytest.fixture(autouse=True)
    def synced_db(self, tmp_path):
        """Sync the fixture log file into a temp SQLite DB."""
        self.db_path = str(tmp_path / "analytics.db")
        _run_cli(
            "sync_logs",
            "--log-folder", LOG_DIR,
            "--db-path", self.db_path,
            "--retention-months", "600",
        )

    def test_log_deal_activity(self):
        data = _run_cli(
            "log_deal_activity",
            "--db-path", self.db_path,
            "--did", "TestJob_Alpha",
            "--days", "9999",
        )
        assert data["success"] is True
        assert data["command"] == "log_deal_activity"

    def test_log_did_failures(self):
        data = _run_cli(
            "log_did_failures",
            "--db-path", self.db_path,
            "--days", "9999",
        )
        assert data["success"] is True
        failures = data["data"]
        assert isinstance(failures, (list, dict))

    def test_log_job_health(self):
        data = _run_cli(
            "log_job_health",
            "--db-path", self.db_path,
            "--job-name", "TestJob_Alpha",
            "--days", "9999",
        )
        assert data["success"] is True

    def test_log_daily_summary(self):
        data = _run_cli(
            "log_daily_summary",
            "--db-path", self.db_path,
            "--date", "2025-01-15",
        )
        assert data["success"] is True
        assert data["data"]["date"] == "2025-01-15"


# ================================================================== #
#  Phase 4: Advanced Analysis
# ================================================================== #

class TestAnalysisIntegration:

    def test_analyze_consolidation(self):
        data = _run_cli(
            "analyze_consolidation",
            "--settings-path", EMAIL_XML,
        )
        assert data["success"] is True
        assert data["command"] == "analyze_consolidation"
        assert "groups" in data["data"] or "total_groups" in data["data"]

    def test_log_trends(self, tmp_path):
        db_path = str(tmp_path / "trends.db")
        _run_cli("sync_logs", "--log-folder", LOG_DIR, "--db-path", db_path, "--retention-months", "600")
        data = _run_cli(
            "log_trends",
            "--db-path", db_path,
            "--days", "14",
        )
        assert data["success"] is True

    def test_log_performance(self, tmp_path):
        db_path = str(tmp_path / "perf.db")
        _run_cli("sync_logs", "--log-folder", LOG_DIR, "--db-path", db_path, "--retention-months", "600")
        data = _run_cli(
            "log_performance",
            "--db-path", db_path,
            "--days", "9999",
        )
        assert data["success"] is True
