"""Tests for XmlDiffEngine."""
import os
import shutil

import pytest

from backend.xml.diff import XmlDiffEngine
from backend.xml.models import DiffResult, FieldChange, JobDiff


class TestXmlDiffEngine:

    def test_identical_files(self, email_fixture):
        engine = XmlDiffEngine(xml_type="email")
        result = engine.diff(email_fixture, email_fixture)
        assert result.total_changes == 0
        assert result.unchanged_count > 0

    def test_added_job(self, tmp_path, email_fixture):
        """Current has extra job → 1 added."""
        current = tmp_path / "current.xml"
        shutil.copy(email_fixture, current)

        # Add a job to current
        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.create_job("TestJob_Alpha", "NewlyAddedJob")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), email_fixture)
        assert len(result.added_jobs) >= 1
        added_names = [j.job_name for j in result.added_jobs]
        assert "NewlyAddedJob" in added_names

    def test_removed_job(self, tmp_path, email_fixture):
        """Current has extra job compared to backup (reverse perspective)."""
        backup = tmp_path / "backup.xml"
        current = tmp_path / "current.xml"
        shutil.copy(email_fixture, backup)
        shutil.copy(email_fixture, current)

        # Add job to backup (so it's "removed" from current's perspective)
        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(backup), xml_type="email")
        engine.create_job("TestJob_Alpha", "RemovedJob")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        assert len(result.removed_jobs) >= 1

    def test_modified_servicer_id(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        assert len(result.modified_jobs) >= 1
        mod = result.modified_jobs[0]
        sid_change = [fc for fc in mod.field_changes if fc.field == "servicer_id"]
        assert len(sid_change) == 1
        assert sid_change[0].new_value == "999"

    def test_modified_multiple_fields(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")
        engine.edit_job("TestJob_Alpha", "sme", "new@sme.com")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        mod = [m for m in result.modified_jobs if m.job_name == "TestJob_Alpha"]
        assert len(mod) == 1
        assert len(mod[0].field_changes) >= 2

    def test_mixed_changes(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        # Modify a job in current
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")
        # Add a job in current
        engine.create_job("TestJob_Beta", "AddedInCurrent")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        assert len(result.added_jobs) >= 1
        assert len(result.modified_jobs) >= 1

    def test_unchanged_count(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        # 1 modified, rest unchanged
        assert result.unchanged_count >= 1

    def test_total_changes_property(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        assert result.total_changes == len(result.added_jobs) + len(result.removed_jobs) + len(result.modified_jobs)

    def test_empty_current(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        current.write_text(
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection></MailboxCollection></Outlook></Settings>'
        )
        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), email_fixture)
        assert len(result.removed_jobs) >= 1
        assert len(result.added_jobs) == 0

    def test_empty_backup(self, tmp_path, email_fixture):
        backup = tmp_path / "backup.xml"
        backup.write_text(
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection></MailboxCollection></Outlook></Settings>'
        )
        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(email_fixture, str(backup))
        assert len(result.added_jobs) >= 1

    def test_both_empty(self, tmp_path):
        a = tmp_path / "a.xml"
        b = tmp_path / "b.xml"
        content = (
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection></MailboxCollection></Outlook></Settings>'
        )
        a.write_text(content)
        b.write_text(content)
        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(a), str(b))
        assert result.total_changes == 0

    def test_diff_result_serialization(self, email_fixture):
        engine = XmlDiffEngine(xml_type="email")
        result = engine.diff(email_fixture, email_fixture)
        d = result.to_dict()
        assert "current_file" in d
        assert "backup_file" in d
        assert "total_changes" in d

    def test_field_change_old_new_values(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "999")

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        mod = [m for m in result.modified_jobs if m.job_name == "TestJob_Alpha"][0]
        sid_change = [fc for fc in mod.field_changes if fc.field == "servicer_id"][0]
        assert sid_change.old_value == "150"
        assert sid_change.new_value == "999"

    def test_sftp_diff(self, sftp_fixture, tmp_path):
        current = tmp_path / "current_sftp.xml"
        shutil.copy(sftp_fixture, current)

        from backend.xml.crud import JobCrudEngine
        engine = JobCrudEngine(str(current), xml_type="sftp")
        engine.edit_job("TestSftp_Alpha", "servicer_id", "999")

        diff_engine = XmlDiffEngine(xml_type="sftp")
        result = diff_engine.diff(str(current), sftp_fixture)
        assert len(result.modified_jobs) >= 1

    def test_timestamp_populated(self, email_fixture):
        engine = XmlDiffEngine(xml_type="email")
        result = engine.diff(email_fixture, email_fixture)
        assert result.timestamp
        # Should contain ISO-like format
        assert "T" in result.timestamp or "-" in result.timestamp

    def test_parser_change_detected(self, tmp_path, email_fixture):
        current = tmp_path / "current.xml"
        backup = tmp_path / "backup.xml"
        shutil.copy(email_fixture, current)
        shutil.copy(email_fixture, backup)

        # Manually modify parsers in current
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(current))
        root = tree.getroot()
        coll = root.find(".//MailboxCollection")
        job = coll.find("TestJob_Alpha")
        parsers_el = job.find("Parsers")
        if parsers_el is not None:
            ET.SubElement(parsers_el, "NewParser").text = ".*\\.new$"
        tree.write(str(current))

        diff_engine = XmlDiffEngine(xml_type="email")
        result = diff_engine.diff(str(current), str(backup))
        mod = [m for m in result.modified_jobs if m.job_name == "TestJob_Alpha"]
        assert len(mod) >= 1
        parser_changes = [fc for fc in mod[0].field_changes if fc.field == "parsers"]
        assert len(parser_changes) >= 1

    def test_case_sensitive_name_matching(self, tmp_path, email_fixture):
        a = tmp_path / "a.xml"
        b = tmp_path / "b.xml"
        a.write_text(
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<MyJob><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Parsers><P>.*</P></Parsers></MyJob>'
            '</MailboxCollection></Outlook></Settings>'
        )
        b.write_text(
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<MYJOB><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Parsers><P>.*</P></Parsers></MYJOB>'
            '</MailboxCollection></Outlook></Settings>'
        )
        engine = XmlDiffEngine(xml_type="email")
        result = engine.diff(str(a), str(b))
        # Different case = different jobs
        assert len(result.added_jobs) == 1
        assert len(result.removed_jobs) == 1
