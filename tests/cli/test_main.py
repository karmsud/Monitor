"""Tests for CLI command handlers — called directly, no subprocess."""
import argparse
import os

import pytest

from cli.main import (
    cmd_status,
    cmd_search_jobs,
    cmd_validate_xml,
    cmd_list_backups,
    cmd_save_xml,
    cmd_sync_logs,
)


def _ns(**kwargs):
    """Build an argparse.Namespace from keyword arguments."""
    return argparse.Namespace(**kwargs)


class TestCmdStatus:

    def test_status_command(self):
        args = _ns()
        response = cmd_status(args)
        assert response.success is True
        assert response.command == "status"
        assert "version" in response.data


class TestCmdSearchJobs:

    def test_search_jobs_valid(self, email_fixture):
        args = _ns(
            query="TestJob",
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
        )
        response = cmd_search_jobs(args)
        assert response.success is True
        assert isinstance(response.data["jobs"], list)

    def test_search_jobs_returns_results(self, email_fixture):
        args = _ns(
            query="TestJob",
            xml_type="email",
            settings_path=email_fixture,
            sftp_settings_path=None,
        )
        response = cmd_search_jobs(args)
        assert len(response.data["jobs"]) > 0


class TestCmdValidateXml:

    def test_validate_xml_valid(self, email_fixture):
        args = _ns(
            settings_path=email_fixture,
            xml_type="email",
            db_mode=None,
            secrets_path=None,
        )
        response = cmd_validate_xml(args)
        assert response.success is True
        assert isinstance(response.data, dict)


class TestCmdListBackups:

    def test_list_backups(self, tmp_settings):
        args = _ns(
            settings_path=tmp_settings,
            xml_type="email",
        )
        response = cmd_list_backups(args)
        assert response.success is True
        assert isinstance(response.data["backups"], list)


class TestCmdSaveXml:

    def test_save_xml(self, tmp_settings):
        args = _ns(
            settings_path=tmp_settings,
            xml_type="email",
        )
        response = cmd_save_xml(args)
        assert response.success is True
        assert response.data["backup_created"] is True


class TestCmdSyncLogs:

    def test_sync_logs(self, sample_log_folder, tmp_path):
        db_path = str(tmp_path / "test_log_index.db")
        args = _ns(
            log_folder=sample_log_folder,
            log_type="email",
            db_path=db_path,
            retention_months=3,
        )
        response = cmd_sync_logs(args)
        assert response.success is True
        assert response.data["files_processed"] >= 1
