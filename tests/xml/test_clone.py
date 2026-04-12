"""Tests for deterministic job cloning."""

import os

from backend.xml.clone import JOB_NAME_FIELD, JobCloneEngine
from backend.xml.parser import SettingsXmlParser


class TestJobCloneEngine:

    def test_prepare_clone_returns_source_order_fields(self, tmp_settings_path):
        engine = JobCloneEngine(tmp_settings_path)

        result = engine.prepare_clone(150)

        assert result["source_job_name"] == "TestJob_Alpha"
        assert result["assigned_servicer_id"] == 151
        assert result["editable_fields"][0]["path"] == JOB_NAME_FIELD
        assert result["editable_fields"][0]["suggested_value"] == "TestJob_Alpha_151"

        paths = [field["path"] for field in result["editable_fields"]]
        assert paths == [
            JOB_NAME_FIELD,
            "Mailbox",
            "Folder",
            "SME",
            "LastEmail",
            "SaveLocation",
            "Filters/From",
            "Filters/Attachments",
            "Filters/Subject",
            "Filters/ImportDID",
            "Parsers/ConditionalParser",
            "QueueOneFile",
            "Templates/ChecklistTemplate",
            "DayAdjust",
        ]

    def test_preview_clone_renders_updated_xml(self, tmp_settings_path):
        engine = JobCloneEngine(tmp_settings_path)

        preview = engine.preview_clone(
            150,
            "TestJob_Alpha_151",
            151,
            {
                "Filters/From": "reports@partner.com",
                "Filters/Subject": "Monthly remittance",
            },
        )

        assert preview["job_name"] == "TestJob_Alpha_151"
        assert preview["assigned_servicer_id"] == 151
        assert "<TestJob_Alpha_151>" in preview["preview_xml"]
        assert "<ServicerID>151</ServicerID>" in preview["preview_xml"]
        assert "<From>reports@partner.com</From>" in preview["preview_xml"]
        assert "<Subject>Monthly remittance</Subject>" in preview["preview_xml"]

    def test_apply_clone_persists_new_job_and_backup(self, tmp_settings_path):
        engine = JobCloneEngine(tmp_settings_path)

        result = engine.apply_clone(
            150,
            "TestJob_Alpha_151",
            151,
            {
                "Filters/From": "reports@partner.com",
                "Filters/Subject": "Monthly remittance",
            },
        )

        assert result["operation"] == "clone"
        assert result["job_name"] == "TestJob_Alpha_151"
        assert os.path.isfile(result["backup_file"])

        parser = SettingsXmlParser(tmp_settings_path)
        jobs = {job.name: job for job in parser.get_all_jobs()}
        assert "TestJob_Alpha_151" in jobs
        assert jobs["TestJob_Alpha_151"].servicer_id == 151
