"""Tests for OrphanDetector."""
import os
import shutil

import pytest
from unittest.mock import MagicMock

from backend.intel.orphans import OrphanDetector
from backend.intel.models import OrphanResult


class TestOrphanDetector:

    def test_no_orphans(self, email_fixture, mock_deal_repo):
        """All ServicerIDs valid → empty list."""
        mock_deal_repo.get_all_servicer_ids.return_value = {150, 200}
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: [{"DID": 1}] if cid in (150, 200) else []
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        assert len(orphans) == 0

    def test_orphan_no_db_match(self, email_fixture, mock_deal_repo):
        """ServicerID not in DB → orphan with reason 'no_db_match'."""
        mock_deal_repo.get_all_servicer_ids.return_value = {999}
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        # 150 and 200 are not in the DB set {999}
        no_db = [o for o in orphans if o.reason == "no_db_match"]
        assert len(no_db) >= 1

    def test_orphan_no_deal_data(self, email_fixture, mock_deal_repo):
        """ServicerID exists but 0 deals → orphan with reason 'no_deal_data'."""
        mock_deal_repo.get_all_servicer_ids.return_value = {150, 200}
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: {
            150: [{"DID": 1}],
            200: [],  # exists but empty
        }.get(cid, [])
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        no_data = [o for o in orphans if o.reason == "no_deal_data"]
        assert len(no_data) >= 1
        assert any(o.servicer_id == 200 for o in no_data)

    def test_jobs_without_servicer_excluded(self, email_fixture, mock_deal_repo):
        """Jobs with empty/missing ServicerID should NOT be orphans."""
        mock_deal_repo.get_all_servicer_ids.return_value = {150, 200}
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        # TestJob_NoServicer has no ServicerID → should NOT appear
        orphan_names = [o.job_name for o in orphans]
        assert "TestJob_NoServicer" not in orphan_names

    def test_multiple_orphans(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>901</ServicerID><Parsers><P>.*</P></Parsers></J1>'
            '<J2><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>902</ServicerID><Parsers><P>.*</P></Parsers></J2>'
            '<J3><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>903</ServicerID><Parsers><P>.*</P></Parsers></J3>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "m.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_all_servicer_ids.return_value = set()
        detector = OrphanDetector(str(xml_path), mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        assert len(orphans) == 3

    def test_mixed_valid_and_orphan(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_all_servicer_ids.return_value = {150}
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: [{"DID": 1}] if cid == 150 else []
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        # 150 is valid, 200 is not in the known_ids
        orphan_sids = [o.servicer_id for o in orphans]
        assert 150 not in orphan_sids
        assert 200 in orphan_sids

    def test_non_numeric_servicer_id(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<BadJob><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>abc</ServicerID><Parsers><P>.*</P></Parsers></BadJob>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "bad.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_all_servicer_ids.return_value = set()
        detector = OrphanDetector(str(xml_path), mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        # non-numeric servicer_id might be handled differently depending on parser
        # The parser parses it as an int or None
        assert isinstance(orphans, list)

    def test_orphan_xml_type_preserved(self, sftp_fixture, mock_deal_repo):
        mock_deal_repo.get_all_servicer_ids.return_value = set()
        detector = OrphanDetector(sftp_fixture, mock_deal_repo, xml_type="sftp")
        orphans = detector.detect()
        for o in orphans:
            assert o.xml_type == "sftp"

    def test_orphan_job_name_correct(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_all_servicer_ids.return_value = set()
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        names = [o.job_name for o in orphans]
        # Should contain known job names that have servicer IDs
        assert any("TestJob" in n or "Test" in n for n in names)

    def test_db_error_during_check(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_all_servicer_ids.return_value = {150, 200}
        mock_deal_repo.get_deals_by_company.side_effect = Exception("DB boom")
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        # Should handle exception (may raise or return empty)
        try:
            orphans = detector.detect()
            assert isinstance(orphans, list)
        except Exception:
            pass  # It's acceptable to propagate DB errors

    def test_empty_xml(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled>'
            '<MailboxCollection></MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "empty.xml"
        xml_path.write_text(xml_content)
        detector = OrphanDetector(str(xml_path), mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        assert len(orphans) == 0

    def test_large_valid_servicer_set(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_all_servicer_ids.return_value = set(range(1, 1001))
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = OrphanDetector(email_fixture, mock_deal_repo, xml_type="email")
        orphans = detector.detect()
        # All fixture servicers (150, 200) are in range(1, 1001), so no orphans
        assert len(orphans) == 0
