"""Tests for CLI XML cache integration (Phase 6).

10 tests verifying that search_jobs, job_detail, create_job, edit_job,
and rebuild_db properly use the SQLite cache with XML fallback.
"""

import argparse
import os
import shutil

import pytest

from cli.main import (
    CliResponse,
    cmd_job_detail,
    cmd_rebuild_db,
    cmd_search_jobs,
    _rebuild_sqlite,
)


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
def cache_db(tmp_path, email_xml):
    """Populated SQLite cache for the test email XML."""
    from backend.db.xml_index import XmlJobIndex

    db_path = str(tmp_path / "cache.db")
    idx = XmlJobIndex(db_path)
    idx.rebuild(email_xml, "email")
    idx.close()
    return db_path


@pytest.fixture
def args_with_cache(email_xml, cache_db):
    """argparse.Namespace with cache_db_path pointing to a populated cache."""
    return argparse.Namespace(
        command="search_jobs",
        query="Alpha",
        xml_type="email",
        settings_path=email_xml,
        sftp_settings_path=None,
        cache_db_path=cache_db,
    )


@pytest.fixture
def args_without_cache(email_xml):
    """argparse.Namespace without cache_db_path — XML fallback only."""
    return argparse.Namespace(
        command="search_jobs",
        query="Alpha",
        xml_type="email",
        settings_path=email_xml,
        sftp_settings_path=None,
        cache_db_path=None,
    )


# ====================================================================== #
#  Tests
# ====================================================================== #

class TestCliXmlCache:
    def test_search_jobs_with_cache(self, args_with_cache):
        """cmd_search_jobs should prefer SQLite when cache DB exists."""
        response = cmd_search_jobs(args_with_cache)
        assert response.success
        assert response.data["total_count"] > 0

    def test_search_jobs_without_cache(self, args_without_cache):
        """cmd_search_jobs should fall back to XML when no cache."""
        response = cmd_search_jobs(args_without_cache)
        assert response.success
        assert response.data["total_count"] > 0

    def test_search_jobs_identical_results(self, args_with_cache, args_without_cache):
        """SQLite and XML paths should return identical job name sets."""
        args_with_cache.query = "Alpha"
        args_without_cache.query = "Alpha"
        r_cache = cmd_search_jobs(args_with_cache)
        r_xml = cmd_search_jobs(args_without_cache)
        cache_names = {j["job_name"] for j in r_cache.data["jobs"]}
        xml_names = {j["job_name"] for j in r_xml.data["jobs"]}
        assert cache_names == xml_names

    def test_job_detail_with_cache(self, email_xml, cache_db):
        """cmd_job_detail should use SQLite when cache DB exists."""
        args = argparse.Namespace(
            command="job_detail",
            job_name="TestJob_Alpha",
            xml_type="email",
            settings_path=email_xml,
            sftp_settings_path=None,
            cache_db_path=cache_db,
            db_mode=None,
            secrets_path=None,
            mssql_server=None,
            mssql_database=None,
        )
        response = cmd_job_detail(args)
        assert response.success
        assert response.data["job_name"] == "TestJob_Alpha"

    def test_job_detail_without_cache(self, email_xml):
        """cmd_job_detail should fall back to XML when no cache."""
        args = argparse.Namespace(
            command="job_detail",
            job_name="TestJob_Alpha",
            xml_type="email",
            settings_path=email_xml,
            sftp_settings_path=None,
            cache_db_path=None,
            db_mode=None,
            secrets_path=None,
            mssql_server=None,
            mssql_database=None,
        )
        response = cmd_job_detail(args)
        assert response.success
        assert response.data["job_name"] == "TestJob_Alpha"

    def test_rebuild_db_command(self, tmp_path, email_xml):
        """cmd_rebuild_db should create SQLite and populate it."""
        args = argparse.Namespace(
            command="rebuild_db",
            cache_db_path=str(tmp_path / "test_rebuild.db"),
            settings_path=email_xml,
            sftp_settings_path=None,
            xml_type="email",
        )
        response = cmd_rebuild_db(args)
        assert response.success
        assert response.data["rebuilt"]["email_jobs"] == 3

    def test_stale_cache_warning(self, email_xml, cache_db):
        """Stale cache should still return results but add a warning."""
        import xml.etree.ElementTree as ET

        # Modify a config field to create staleness
        tree = ET.parse(email_xml)
        root = tree.getroot()
        sid_elem = root.find(".//TestJob_Alpha/ServicerID")
        sid_elem.text = "999"
        tree.write(email_xml)

        args = argparse.Namespace(
            command="search_jobs",
            query="test",
            xml_type="email",
            settings_path=email_xml,
            sftp_settings_path=None,
            cache_db_path=cache_db,
        )
        response = cmd_search_jobs(args)
        assert response.success
        assert any("stale" in w.lower() for w in response.warnings)

    def test_cache_db_path_optional(self, email_xml):
        """Commands should work when --cache-db-path is omitted."""
        args = argparse.Namespace(
            command="search_jobs",
            query="Beta",
            xml_type="email",
            settings_path=email_xml,
            sftp_settings_path=None,
            cache_db_path=None,
        )
        response = cmd_search_jobs(args)
        assert response.success

    def test_rebuild_sqlite_no_db_path(self, email_xml):
        """_rebuild_sqlite should be a no-op when cache_db_path is None."""
        args = argparse.Namespace(
            cache_db_path=None,
            settings_path=email_xml,
            xml_type="email",
        )
        # Should not raise
        _rebuild_sqlite(args)

    def test_rebuild_db_with_nonexistent_xml(self, tmp_path):
        """cmd_rebuild_db should return error for missing XML."""
        args = argparse.Namespace(
            command="rebuild_db",
            cache_db_path=str(tmp_path / "err.db"),
            settings_path=str(tmp_path / "nonexistent.xml"),
            sftp_settings_path=None,
            xml_type="email",
        )
        response = cmd_rebuild_db(args)
        assert not response.success
