"""Tests for SettingsXmlParser — parsing, searching, and infrastructure."""
import os
import xml.etree.ElementTree as ET

import pytest

from backend.xml.parser import SettingsXmlParser
from backend.xml.models import EmailJob, SftpJob

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
INVALID_FIXTURE = os.path.join(FIXTURES_DIR, "email_settings_invalid.xml")


# ── Type detection ───────────────────────────────────────────────────── #

class TestDetectXmlType:

    def test_detect_email_type(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        assert parser.detect_xml_type() == "email"

    def test_detect_sftp_type(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        assert parser.detect_xml_type() == "sftp"


# ── get_all_jobs ─────────────────────────────────────────────────────── #

class TestGetAllJobs:

    def test_get_all_email_jobs_count(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        assert len(jobs) == 3

    def test_get_all_sftp_jobs_count(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        assert len(jobs) == 2

    def test_email_job_types(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        assert all(isinstance(j, EmailJob) for j in jobs)

    def test_sftp_job_types(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        assert all(isinstance(j, SftpJob) for j in jobs)


# ── Email job fields ─────────────────────────────────────────────────── #

class TestEmailJobFields:

    def test_email_job_alpha_fields(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestJob_Alpha")
        assert alpha.mailbox == "frp.test@example.com"
        assert alpha.folder == "Inbox"
        assert alpha.sme == "admin@example.com"
        assert alpha.servicer_id == 150
        assert alpha.queue_one_file is True
        assert alpha.day_adjust == -1

    def test_email_job_noservicer(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        ns = next(j for j in jobs if j.name == "TestJob_NoServicer")
        assert ns.servicer_id is None

    def test_email_job_parsers(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestJob_Alpha")
        assert "ConditionalParser" in alpha.parsers

    def test_email_job_templates(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestJob_Alpha")
        assert "ChecklistTemplate" in alpha.templates

    def test_email_job_filters(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestJob_Alpha")
        assert "From" in alpha.filters

    def test_email_job_save_location(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestJob_Alpha")
        assert "{DealFolder}" in alpha.save_location


# ── SFTP job fields ──────────────────────────────────────────────────── #

class TestSftpJobFields:

    def test_sftp_job_fields(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestSftp_Alpha")
        assert alpha.name == "TestSftp_Alpha"
        assert "sftp-server" in alpha.path
        assert alpha.servicer_id == 150
        assert alpha.dsn == "SftpConnection1"

    def test_sftp_job_skip_list(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestSftp_Alpha")
        assert alpha.skip_list != ""

    def test_sftp_job_ignore_list(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestSftp_Alpha")
        assert alpha.ignore_list != ""

    def test_sftp_job_zip_filter(self, sftp_fixture):
        parser = SettingsXmlParser(sftp_fixture)
        jobs = parser.get_all_jobs()
        alpha = next(j for j in jobs if j.name == "TestSftp_Alpha")
        assert alpha.zip_content_filter != ""


# ── search_jobs ──────────────────────────────────────────────────────── #

class TestSearchJobs:

    def test_search_by_name(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("TestJob")
        assert len(results) == 3

    def test_search_by_mailbox(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("frp.test@example")
        assert len(results) >= 2

    def test_search_by_servicer_id(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("150")
        assert len(results) >= 1

    def test_search_shelf_level(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("shelf-level")
        assert all(j.servicer_id is None for j in results)
        assert len(results) >= 1

    def test_search_no_results(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("zzz_nonexistent")
        assert results == []

    def test_search_case_insensitive(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        results = parser.search_jobs("TESTJOB")
        assert len(results) >= 1


# ── Infrastructure & tree ────────────────────────────────────────────── #

class TestInfrastructure:

    def test_get_infrastructure(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        infra = parser.get_infrastructure()
        assert isinstance(infra, dict)
        assert "Server" in infra
        assert "Db" in infra

    def test_get_element_tree(self, email_fixture):
        parser = SettingsXmlParser(email_fixture)
        tree = parser.get_element_tree()
        assert isinstance(tree, ET.ElementTree)


# ── Error handling ───────────────────────────────────────────────────── #

class TestParserErrors:

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            SettingsXmlParser("/bad/path/does_not_exist.xml")

    def test_malformed_xml(self):
        with pytest.raises(ET.ParseError):
            SettingsXmlParser(INVALID_FIXTURE)


# ── Production layout (no <Outlook> wrapper) ────────────────────────── #

PROD_LAYOUT_FIXTURE = os.path.join(FIXTURES_DIR, "sftp_settings_prod_layout.xml")


class TestProductionLayout:
    """Verify parsing of SFTP Settings.xml where <FolderCollection> is
    directly under <Settings> (production layout, no <Outlook> wrapper)."""

    def test_detect_sftp_type(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        assert parser.detect_xml_type() == "sftp"

    def test_get_all_jobs_count(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        jobs = parser.get_all_jobs()
        assert len(jobs) == 2

    def test_job_types(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        jobs = parser.get_all_jobs()
        assert all(isinstance(j, SftpJob) for j in jobs)

    def test_ocwen_job_fields(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        jobs = parser.get_all_jobs()
        ocwen = next(j for j in jobs if j.name == "Ocwen")
        assert ocwen.servicer_id == 150
        assert ocwen.dsn == "xf00.ocwen3.iman"
        assert ocwen.day_adjust == -2
        assert "MoveFile2" in ocwen.parsers
        assert ocwen.templates.get("Main") == "Ocwen"

    def test_sps_job_fields(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        jobs = parser.get_all_jobs()
        sps = next(j for j in jobs if j.name == "SPS_FMSCRT_3001")
        assert sps.servicer_id == 3001
        assert sps.dsn == "xf00.sps2.iman"
        assert sps.templates.get("Main") == "SCRT_Queuer_x"

    def test_search_by_name(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        results = parser.search_jobs("Ocwen")
        assert len(results) >= 1
        assert results[0].name == "Ocwen"

    def test_infrastructure_from_second_mapdrives(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        infra = parser.get_infrastructure()
        assert infra["Server"] == "prodserver.example.com,49001"
        assert infra["Db"] == "Servicing"
        assert infra["StagingServer"] == "staging.example.com,1433"
        assert infra["StagingDb"] == "ToolsHub"
        # Drive letters from first MapDrives
        assert "N" in infra["MapDrives"]
        assert "M" in infra["MapDrives"]

    def test_validate_no_errors(self):
        parser = SettingsXmlParser(PROD_LAYOUT_FIXTURE)
        result = parser.validate()
        assert result.valid is True
        assert len(result.errors) == 0
        assert result.job_count == 2
