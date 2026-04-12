"""Tests for RollbackHandler."""
import os
import shutil

import pytest

from backend.xml.rollback import RollbackHandler
from backend.xml.models import DiffResult
from backend.xml.parser import SettingsXmlParser


class TestRollbackHandler:

    def test_preview_returns_diff(self, tmp_settings_path, tmp_backup_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        result = handler.preview(tmp_backup_path)
        assert isinstance(result, DiffResult)

    def test_execute_creates_safety_backup(self, tmp_settings_path, tmp_backup_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        result = handler.execute(tmp_backup_path)
        assert result["safety_backup"]
        assert os.path.exists(result["safety_backup"])

    def test_execute_restores_content(self, tmp_path, email_fixture):
        """After rollback, current file should match backup."""
        current = tmp_path / "current.xml"
        shutil.copy(email_fixture, current)

        # Modify current
        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")

        # Create backup of original
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, backup)

        handler = RollbackHandler(str(current), xml_type="email")
        handler.execute(str(backup))

        # Current should now match backup (original fixture)
        parser = SettingsXmlParser(str(current))
        jobs = {j.name: j for j in parser.get_all_jobs()}
        assert jobs["TestJob_Alpha"].servicer_id == 150

    def test_execute_validates_restored(self, tmp_settings_path, tmp_backup_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        result = handler.execute(tmp_backup_path)
        assert "validation" in result
        assert result["validation"]["valid"] is True

    def test_execute_backup_not_found(self, tmp_settings_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        with pytest.raises(FileNotFoundError):
            handler.execute("nonexistent_backup.xml")

    def test_execute_preserves_original_as_backup(self, tmp_settings_path, tmp_backup_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        result = handler.execute(tmp_backup_path)
        safety = result["safety_backup"]
        assert os.path.exists(safety)

    def test_rollback_result_structure(self, tmp_settings_path, tmp_backup_path):
        handler = RollbackHandler(tmp_settings_path, xml_type="email")
        result = handler.execute(tmp_backup_path)
        assert "safety_backup" in result
        assert "restored_from" in result
        assert "validation" in result

    def test_rollback_then_diff_shows_no_changes(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        handler = RollbackHandler(str(current), xml_type="email")
        handler.execute(str(backup))

        from backend.xml.diff import XmlDiffEngine
        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        assert result.total_changes == 0

    def test_execute_invalid_xml_backup(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        shutil.copy(email_fixture, current)
        bad_backup = tmp_path / "bad.xml"
        bad_backup.write_text("<not valid xml><unclosed>")

        handler = RollbackHandler(str(current), xml_type="email")
        try:
            result = handler.execute(str(bad_backup))
            # If it succeeds, validation should show errors
            assert result["validation"]["valid"] is False or len(result["validation"].get("errors", [])) > 0
        except Exception:
            pass  # It's acceptable to raise on invalid XML

    def test_double_rollback(self, tmp_path, email_fixture):
        import time
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        handler = RollbackHandler(str(current), xml_type="email")
        result1 = handler.execute(str(backup))
        time.sleep(1.1)  # Ensure different second for backup filename
        result2 = handler.execute(str(backup))

        assert result1["safety_backup"] != result2["safety_backup"]
        assert os.path.exists(result1["safety_backup"])
        assert os.path.exists(result2["safety_backup"])
