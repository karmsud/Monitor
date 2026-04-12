"""Tests for backend.db.xml_index — SQLite job-config cache.

Phase 6 WS-A: 32 tests covering schema creation, rebuild, search,
get_job, get_all_jobs, content hash, status, and context manager.

All tests use tmp_path SQLite — no real XML files or network required.
"""

import json
import os
import xml.etree.ElementTree as ET

import pytest

from backend.db.xml_index import XmlJobIndex, _compute_config_hash


# ====================================================================== #
#  Fixtures
# ====================================================================== #

@pytest.fixture
def email_xml(tmp_path):
    """Minimal email Settings.xml with 3 jobs."""
    xml_content = """\
<?xml version="1.0" encoding="utf-8"?>
<root>
  <Outlook>
    <MailboxCollection>
      <TestJob_Alpha>
        <ServicerID>10</ServicerID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>John.Doe</SME>
        <SaveLocation>M:\\TestDeal\\Data\\</SaveLocation>
        <LastEmail />
        <QueueOneFile>True</QueueOneFile>
        <Filters><From>reports@alpha.com</From></Filters>
        <Parsers><DetachFileSubject><Keyword>monthly</Keyword></DetachFileSubject></Parsers>
        <Templates><Main>TestScrubber_Alpha</Main></Templates>
      </TestJob_Alpha>
      <TestJob_Beta>
        <ServicerID>20</ServicerID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>Jane.Doe</SME>
        <SaveLocation>M:\\BetaDeal\\Data\\</SaveLocation>
        <QueueOneFile>True</QueueOneFile>
        <Filters><From>data@beta.com</From></Filters>
        <Parsers><DetachFile><Keyword>report</Keyword></DetachFile></Parsers>
        <Templates><Main>TestScrubber_Beta</Main></Templates>
      </TestJob_Beta>
      <ShelfJob_NoSID>
        <Mailbox>test@usbank.com</Mailbox>
        <Folder>Inbox</Folder>
        <SME>Jim.Shelf</SME>
        <SaveLocation>M:\\Shelf\\Data\\</SaveLocation>
        <Filters><From>info@shelf.com</From></Filters>
      </ShelfJob_NoSID>
    </MailboxCollection>
  </Outlook>
</root>"""
    xml_file = tmp_path / "email_settings.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    return str(xml_file)


@pytest.fixture
def sftp_xml(tmp_path):
    """Minimal SFTP Settings.xml with 2 jobs."""
    xml_content = """\
<?xml version="1.0" encoding="utf-8"?>
<root>
  <Outlook>
    <FolderCollection>
      <SftpJob_Gamma>
        <ServicerID>30</ServicerID>
        <Path>/incoming/gamma/</Path>
        <DSN>SFTP_Gamma</DSN>
        <SME>Bob.Sftp</SME>
        <SaveLocation>M:\\GammaDeal\\Data\\</SaveLocation>
        <SkipList>*.tmp</SkipList>
        <Templates><Main>SFTP_Gamma_Scrub</Main></Templates>
      </SftpJob_Gamma>
      <SftpJob_Delta>
        <ServicerID>40</ServicerID>
        <Path>/incoming/delta/</Path>
        <DSN>SFTP_Delta</DSN>
        <SME>Alice.Sftp</SME>
        <SaveLocation>M:\\DeltaDeal\\Data\\</SaveLocation>
        <Templates><Main>SFTP_Delta_Scrub</Main></Templates>
      </SftpJob_Delta>
    </FolderCollection>
  </Outlook>
</root>"""
    xml_file = tmp_path / "sftp_settings.xml"
    xml_file.write_text(xml_content, encoding="utf-8")
    return str(xml_file)


@pytest.fixture
def index(tmp_path):
    """XmlJobIndex backed by a tmp_path SQLite DB."""
    db_path = str(tmp_path / "test_cache.db")
    idx = XmlJobIndex(db_path)
    yield idx
    idx.close()


# ====================================================================== #
#  TestSchemaCreation (3 tests)
# ====================================================================== #

class TestSchemaCreation:
    def test_tables_created(self, index):
        tables = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "cache_metadata" in names
        assert "email_jobs" in names
        assert "sftp_jobs" in names

    def test_indexes_created(self, index):
        indexes = index._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        names = {i["name"] for i in indexes}
        assert "idx_email_jobs_servicer" in names
        assert "idx_email_jobs_mailbox" in names
        assert "idx_email_jobs_sender" in names
        assert "idx_sftp_jobs_servicer" in names
        assert "idx_sftp_jobs_dsn" in names

    def test_schema_version_seeded(self, index):
        row = index._conn.execute(
            "SELECT value FROM cache_metadata WHERE key='schema_version'"
        ).fetchone()
        assert row["value"] == "1"


# ====================================================================== #
#  TestRebuildEmail (5 tests)
# ====================================================================== #

class TestRebuildEmail:
    def test_rebuild_email_count(self, index, email_xml):
        result = index.rebuild(email_xml, "email")
        assert result["email_jobs_loaded"] == 3

    def test_rebuild_email_hash_stored(self, index, email_xml):
        index.rebuild(email_xml, "email")
        assert index._get_metadata("email_hash") is not None

    def test_rebuild_email_fields(self, index, email_xml):
        index.rebuild(email_xml, "email")
        row = index._conn.execute(
            "SELECT * FROM email_jobs WHERE name='TestJob_Alpha'"
        ).fetchone()
        assert row["mailbox"] == "test@usbank.com"
        assert row["servicer_id"] == 10
        assert row["sme"] == "John.Doe"

    def test_rebuild_email_replaces_previous(self, index, email_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(email_xml, "email")
        count = index._conn.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0]
        assert count == 3  # Not 6

    def test_rebuild_email_computed_columns(self, index, email_xml):
        index.rebuild(email_xml, "email")
        row = index._conn.execute(
            "SELECT * FROM email_jobs WHERE name='TestJob_Alpha'"
        ).fetchone()
        assert row["sender"] == "reports@alpha.com"
        assert row["scrubber"] == "TestScrubber_Alpha"
        assert row["match_mode"] == "Subject"


# ====================================================================== #
#  TestRebuildSftp (3 tests)
# ====================================================================== #

class TestRebuildSftp:
    def test_rebuild_sftp_count(self, index, sftp_xml):
        result = index.rebuild(sftp_xml, "sftp")
        assert result["sftp_jobs_loaded"] == 2

    def test_rebuild_sftp_hash_stored(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        assert index._get_metadata("sftp_hash") is not None

    def test_rebuild_sftp_fields(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        row = index._conn.execute(
            "SELECT * FROM sftp_jobs WHERE name='SftpJob_Gamma'"
        ).fetchone()
        assert row["path"] == "/incoming/gamma/"
        assert row["dsn"] == "SFTP_Gamma"
        assert row["servicer_id"] == 30


# ====================================================================== #
#  TestSearchJobs (6 tests)
# ====================================================================== #

class TestSearchJobs:
    def test_search_by_name(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("Alpha", "email")
        assert len(results) == 1
        assert results[0]["job_name"] == "TestJob_Alpha"

    def test_search_by_sender(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("alpha.com", "email")
        assert len(results) == 1

    def test_search_by_servicer_id(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("10", "email")
        assert any(r["servicer_id"] == 10 for r in results)

    def test_search_no_match(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("nonexistent_zzz_xyz", "email")
        assert results == []

    def test_search_all_types(self, index, email_xml, sftp_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(sftp_xml, "sftp")
        results = index.search_jobs("30", "all")
        assert any(r.get("xml_type") == "sftp" for r in results)

    def test_search_summary_format(self, index, email_xml):
        index.rebuild(email_xml, "email")
        results = index.search_jobs("Alpha", "email")
        r = results[0]
        assert "job_name" in r
        assert "mailbox" in r
        assert "sender" in r
        assert "servicer_id" in r
        assert "save_path" in r
        assert "scrubber" in r
        assert "match_mode" in r
        assert "xml_type" in r


# ====================================================================== #
#  TestGetJob (4 tests)
# ====================================================================== #

class TestGetJob:
    def test_get_email_job(self, index, email_xml):
        index.rebuild(email_xml, "email")
        job = index.get_job("TestJob_Alpha")
        assert job is not None
        assert job["job_name"] == "TestJob_Alpha"
        assert "filters" in job
        assert "parsers" in job
        assert "templates" in job

    def test_get_sftp_job(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        job = index.get_job("SftpJob_Gamma")
        assert job is not None
        assert job["sftp_path"] == "/incoming/gamma/"
        assert job["xml_type"] == "sftp"

    def test_get_job_not_found(self, index, email_xml):
        index.rebuild(email_xml, "email")
        assert index.get_job("DoesNotExist") is None

    def test_get_job_case_insensitive(self, index, email_xml):
        index.rebuild(email_xml, "email")
        job = index.get_job("testjob_alpha")
        assert job is not None
        assert job["job_name"] == "TestJob_Alpha"


# ====================================================================== #
#  TestGetAllJobs (3 tests)
# ====================================================================== #

class TestGetAllJobs:
    def test_get_all_email(self, index, email_xml):
        index.rebuild(email_xml, "email")
        jobs = index.get_all_jobs("email")
        assert len(jobs) == 3

    def test_get_all_sftp(self, index, sftp_xml):
        index.rebuild(sftp_xml, "sftp")
        jobs = index.get_all_jobs("sftp")
        assert len(jobs) == 2

    def test_get_all_combined(self, index, email_xml, sftp_xml):
        index.rebuild(email_xml, "email")
        index.rebuild(sftp_xml, "sftp")
        jobs = index.get_all_jobs("all")
        assert len(jobs) == 5


# ====================================================================== #
#  TestContentHash (4 tests)
# ====================================================================== #

class TestContentHash:
    def test_hash_is_fresh_after_rebuild(self, index, email_xml):
        index.rebuild(email_xml, "email")
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is True

    def test_hash_detects_config_change(self, index, email_xml):
        index.rebuild(email_xml, "email")
        # Modify a config field
        tree = ET.parse(email_xml)
        root = tree.getroot()
        sid_elem = root.find(".//TestJob_Alpha/ServicerID")
        sid_elem.text = "999"
        tree.write(email_xml)
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is False

    def test_hash_ignores_last_run_time(self, index, email_xml):
        index.rebuild(email_xml, "email")
        # Add a <LastRunTime> element (simulating PowerShell update)
        tree = ET.parse(email_xml)
        root = tree.getroot()
        job_elem = root.find(".//TestJob_Alpha")
        lrt = ET.SubElement(job_elem, "LastRunTime")
        lrt.text = "2026-03-04T14:00:00"
        tree.write(email_xml)
        result = index.check_hash(email_xml, "email")
        assert result["is_fresh"] is True  # last_run_time excluded from hash

    def test_hash_deterministic(self, email_xml):
        h1 = _compute_config_hash(email_xml, "email")
        h2 = _compute_config_hash(email_xml, "email")
        assert h1 == h2


# ====================================================================== #
#  TestGetStatus (2 tests)
# ====================================================================== #

class TestGetStatus:
    def test_status_empty(self, index):
        status = index.get_status()
        assert status["email_jobs_cached"] == 0
        assert status["sftp_jobs_cached"] == 0

    def test_status_after_rebuild(self, index, email_xml):
        index.rebuild(email_xml, "email")
        status = index.get_status()
        assert status["email_jobs_cached"] == 3
        assert status["email_hash"] is not None
        assert status["schema_version"] == "1"


# ====================================================================== #
#  TestContextManager (2 tests)
# ====================================================================== #

class TestContextManager:
    def test_with_statement(self, tmp_path):
        db_path = str(tmp_path / "ctx_test.db")
        with XmlJobIndex(db_path) as idx:
            status = idx.get_status()
            assert status["email_jobs_cached"] == 0
        # Connection should be closed after exit

    def test_double_close_safe(self, tmp_path):
        db_path = str(tmp_path / "dbl_close.db")
        idx = XmlJobIndex(db_path)
        idx.close()
        idx.close()  # Should not raise
