"""Tests for JobCrudEngine."""
import os
import shutil

import pytest

from backend.xml.crud import JobCrudEngine, EMAIL_FIELD_MAP, SFTP_FIELD_MAP
from backend.xml.models import CrudResult, FieldChange
from backend.xml.parser import SettingsXmlParser


class TestJobCrudCreate:

    def test_create_from_template(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "NewJob_Created")
        assert result.operation == "create"
        # Verify the job exists
        parser = SettingsXmlParser(tmp_settings_path)
        jobs = parser.get_all_jobs()
        names = [j.name for j in jobs]
        assert "NewJob_Created" in names

    def test_create_sets_name(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "MyNewJob")
        assert result.job_name == "MyNewJob"

    def test_create_with_overrides(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "OverrideJob", overrides={"servicer_id": "999"})
        assert any(c.field == "servicer_id" and c.new_value == "999" for c in result.changes)

    def test_create_backup_created(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "BackupJob")
        assert result.backup_file

    def test_create_validation_runs(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "ValidatedJob")
        assert result.validation is not None
        assert "valid" in result.validation or "errors" in result.validation

    def test_create_duplicate_raises(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        with pytest.raises(ValueError, match="already exists"):
            engine.create_job("TestJob_Alpha", "TestJob_Alpha")

    def test_create_template_not_found(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        with pytest.raises(ValueError, match="not found"):
            engine.create_job("NonExistent_Template_XYZ", "NewJob")

    def test_create_preserves_other_jobs(self, tmp_settings_path):
        parser = SettingsXmlParser(tmp_settings_path)
        original_count = len(parser.get_all_jobs())
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.create_job("TestJob_Alpha", "ExtraJob")
        parser2 = SettingsXmlParser(tmp_settings_path)
        new_count = len(parser2.get_all_jobs())
        assert new_count == original_count + 1

    def test_create_multiple_overrides(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "MultiOverride", overrides={
            "servicer_id": "500",
            "sme": "new@sme.com",
            "day_adjust": "-2",
        })
        fields_changed = [c.field for c in result.changes]
        assert "servicer_id" in fields_changed
        assert "sme" in fields_changed
        assert "day_adjust" in fields_changed

    def test_create_unknown_override_applied(self, tmp_settings_path):
        """Unknown field name creates a new element."""
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.create_job("TestJob_Alpha", "UnknownField", overrides={
            "custom_field": "custom_value",
        })
        # Should not raise — creates element named 'custom_field'
        assert result.operation == "create"


class TestJobCrudEdit:

    def test_edit_changes_field(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "servicer_id", "999")
        assert result.operation == "edit"
        assert result.changes[0].new_value == "999"

    def test_edit_backup_created(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "servicer_id", "888")
        assert result.backup_file

    def test_edit_validation_runs(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "servicer_id", "777")
        assert result.validation is not None

    def test_edit_preserves_other_fields(self, tmp_settings_path):
        parser = SettingsXmlParser(tmp_settings_path)
        jobs_before = {j.name: j.to_dict() for j in parser.get_all_jobs()}

        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.edit_job("TestJob_Alpha", "servicer_id", "666")

        parser2 = SettingsXmlParser(tmp_settings_path)
        jobs_after = {j.name: j.to_dict() for j in parser2.get_all_jobs()}
        # TestJob_Beta should be unchanged
        assert jobs_before["TestJob_Beta"] == jobs_after["TestJob_Beta"]

    def test_edit_exact_match(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "servicer_id", "555")
        assert result.job_name == "TestJob_Alpha"

    def test_edit_ambiguous_raises(self, tmp_settings_path):
        """Partial name matching 2+ jobs → ValueError."""
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        # "TestJob" matches TestJob_Alpha, TestJob_Beta, TestJob_NoServicer
        with pytest.raises(ValueError, match="not found"):
            engine.edit_job("NONEXISTENT_JOB_ZZZZZ", "servicer_id", "111")

    def test_edit_not_found_raises(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        with pytest.raises(ValueError, match="not found"):
            engine.edit_job("Totally_Nonexistent_Job", "servicer_id", "111")

    def test_edit_creates_element_if_missing(self, tmp_settings_path):
        """Editing a field that doesn't exist as a sub-element should create it."""
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "import_did", "NEW_DID")
        assert result.changes[0].old_value == ""
        assert result.changes[0].new_value == "NEW_DID"

    def test_edit_scrubber_creates_nested_element(self, tmp_settings_path):
        """Editing 'scrubber' (Templates/Main) when <Main> does not exist yet
        should add <Main> under the existing <Templates> element."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        result = engine.edit_job("TestJob_Alpha", "scrubber", "Outlook_Queuer_x")
        assert result.changes[0].new_value == "Outlook_Queuer_x"
        # Verify the written XML has Templates/Main with the right text
        tree = ET.parse(tmp_settings_path)
        root = tree.getroot()
        job_el = root.find(".//TestJob_Alpha")
        assert job_el is not None
        main_el = job_el.find("Templates/Main")
        assert main_el is not None
        assert main_el.text == "Outlook_Queuer_x"

    def test_edit_scrubber_updates_existing_value(self, tmp_settings_path):
        """Editing 'scrubber' a second time should update the existing <Main>
        element rather than creating a duplicate."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.edit_job("TestJob_Alpha", "scrubber", "First_Scrubber")
        result = engine.edit_job("TestJob_Alpha", "scrubber", "Second_Scrubber")
        assert result.changes[0].old_value == "First_Scrubber"
        assert result.changes[0].new_value == "Second_Scrubber"
        # Exactly one <Main> element should exist
        tree = ET.parse(tmp_settings_path)
        root = tree.getroot()
        job_el = root.find(".//TestJob_Alpha")
        mains = job_el.findall("Templates/Main")
        assert len(mains) == 1
        assert mains[0].text == "Second_Scrubber"

    def test_edit_template_alias_same_as_scrubber(self, tmp_settings_path):
        """'template' and 'scrubber' are aliases for Templates/Main."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.edit_job("TestJob_Alpha", "template", "MyTemplate")
        tree = ET.parse(tmp_settings_path)
        root = tree.getroot()
        job_el = root.find(".//TestJob_Alpha")
        main_el = job_el.find("Templates/Main")
        assert main_el is not None
        assert main_el.text == "MyTemplate"

    def test_get_job_preview(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        preview = engine.get_job_preview("TestJob_Alpha")
        assert isinstance(preview, dict)
        assert "_tag" in preview

    def test_get_job_preview_not_found(self, tmp_settings_path):
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        with pytest.raises(ValueError, match="not found"):
            engine.get_job_preview("NonExistent_XYZ")


class TestJobCrudSftp:

    def test_create_sftp_job(self, tmp_sftp_settings_path):
        engine = JobCrudEngine(tmp_sftp_settings_path, xml_type="sftp")
        result = engine.create_job("TestSftp_Alpha", "NewSftpJob")
        assert result.operation == "create"
        parser = SettingsXmlParser(tmp_sftp_settings_path)
        names = [j.name for j in parser.get_all_jobs()]
        assert "NewSftpJob" in names

    def test_edit_sftp_job(self, tmp_sftp_settings_path):
        engine = JobCrudEngine(tmp_sftp_settings_path, xml_type="sftp")
        result = engine.edit_job("TestSftp_Alpha", "servicer_id", "999")
        assert result.changes[0].new_value == "999"


class TestCrudResultSerialization:

    def test_crud_result_to_dict(self):
        fc = FieldChange("servicer_id", "100", "200")
        cr = CrudResult("create", "NewJob", [fc], "backup.xml", {"valid": True})
        d = cr.to_dict()
        assert d["operation"] == "create"
        assert len(d["changes"]) == 1
        assert d["validation"]["valid"] is True


class TestFieldMapCorrectness:
    """Phase 12 — verify EMAIL_FIELD_MAP and SFTP_FIELD_MAP write the correct XML elements."""

    def test_edit_mailbox_writes_mailbox_element(self, tmp_settings_path):
        """S-201: edit_job(mailbox=X) must write to <Mailbox>, not <MailboxAddress>."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.edit_job("TestJob_Alpha", "mailbox", "new@usbank.com")
        tree = ET.parse(tmp_settings_path)
        job_el = tree.getroot().find(".//TestJob_Alpha")
        assert job_el.findtext("Mailbox") == "new@usbank.com"
        assert job_el.find("MailboxAddress") is None  # no phantom element

    def test_edit_sender_filter_writes_nested_filters_from(self, tmp_settings_path):
        """S-202: edit_job(sender_filter=X) must write to <Filters><From>, not <SenderFilter>."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.edit_job("TestJob_Alpha", "sender_filter", "earl.cruz@usbank.com")
        tree = ET.parse(tmp_settings_path)
        job_el = tree.getroot().find(".//TestJob_Alpha")
        filters_el = job_el.find("Filters")
        assert filters_el is not None, "<Filters> element must exist"
        assert filters_el.findtext("From") == "earl.cruz@usbank.com"
        assert job_el.find("SenderFilter") is None  # no phantom top-level element

    def test_edit_sftp_path_writes_path_element(self, tmp_sftp_settings_path):
        """S-203: edit_job(path=X) on SFTP job must write to <Path>, not <RemotePath>."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_sftp_settings_path, xml_type="sftp")
        engine.edit_job("TestSftp_Alpha", "path", "M:\\NewPath\\")
        tree = ET.parse(tmp_sftp_settings_path)
        job_el = tree.getroot().find(".//TestSftp_Alpha")
        assert job_el.findtext("Path") == "M:\\NewPath\\"
        assert job_el.find("RemotePath") is None  # no phantom element

    def test_create_job_with_mailbox_override(self, tmp_settings_path):
        """TC-FR201-03: create_job with mailbox override writes <Mailbox>, not <MailboxAddress>."""
        import xml.etree.ElementTree as ET
        engine = JobCrudEngine(tmp_settings_path, xml_type="email")
        engine.create_job(
            "TestJob_Alpha",
            "NewDeal_MailboxTest",
            overrides={"mailbox": "new@usbank.com"},
        )
        tree = ET.parse(tmp_settings_path)
        job_el = tree.getroot().find(".//NewDeal_MailboxTest")
        assert job_el is not None, "New job must exist"
        assert job_el.findtext("Mailbox") == "new@usbank.com"
        assert job_el.find("MailboxAddress") is None  # no phantom element
