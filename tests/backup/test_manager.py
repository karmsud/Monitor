"""Tests for BackupManager."""
import os
import shutil

import pytest

from backend.backup.manager import BackupManager


class TestBackupManager:

    def _create_backup_files(self, settings_path, filenames):
        """Helper: create fake backup XML files in the backup directory."""
        backup_dir = os.path.join(os.path.dirname(settings_path), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        for fname in filenames:
            fpath = os.path.join(backup_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("<Settings><Outlook><MailboxCollection/></Outlook></Settings>")

    def test_list_empty(self, tmp_settings):
        mgr = BackupManager(tmp_settings)
        assert mgr.list_backups() == []

    def test_list_sorted(self, tmp_settings):
        self._create_backup_files(tmp_settings, [
            "Settings_20250101_080000.xml",
            "Settings_20250115_120000.xml",
        ])
        mgr = BackupManager(tmp_settings)
        backups = mgr.list_backups()
        assert len(backups) == 2
        # Newest first
        assert backups[0]["filename"] == "Settings_20250115_120000.xml"
        assert backups[1]["filename"] == "Settings_20250101_080000.xml"

    def test_get_backup_count(self, tmp_settings):
        self._create_backup_files(tmp_settings, [
            "Settings_20250101_080000.xml",
            "Settings_20250115_120000.xml",
        ])
        mgr = BackupManager(tmp_settings)
        assert mgr.get_backup_count() == len(mgr.list_backups())

    def test_get_latest_backup(self, tmp_settings):
        self._create_backup_files(tmp_settings, [
            "Settings_20250101_080000.xml",
            "Settings_20250115_120000.xml",
        ])
        mgr = BackupManager(tmp_settings)
        latest = mgr.get_latest_backup()
        assert latest is not None
        assert latest["filename"] == "Settings_20250115_120000.xml"

    def test_get_latest_none(self, tmp_settings):
        mgr = BackupManager(tmp_settings)
        assert mgr.get_latest_backup() is None

    def test_restore_nonexistent(self, tmp_settings):
        mgr = BackupManager(tmp_settings)
        result = mgr.restore("Settings_99991231_235959.xml")
        assert result["success"] is False
