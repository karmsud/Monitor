"""Tests for CollisionDetector."""
import os
import shutil

import pytest
from unittest.mock import MagicMock

from backend.intel.collisions import CollisionDetector, _get_import_did
from backend.intel.models import CollisionResult
from backend.xml.models import EmailJob


class TestCollisionDetector:

    def test_no_collisions(self, email_fixture, mock_deal_repo):
        """All unique ImportDIDs → no collisions."""
        mock_deal_repo.get_companies_by_import_did.return_value = [150]
        detector = CollisionDetector(email_fixture, mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 0

    def test_collision_two_companies(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>OVERLAP</ImportDID></Filters>'
            '<Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlet></Settings>'
        ).replace('</Outlet>', '</Outlook>')
        xml_path = tmp_path / "collision.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.side_effect = None
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 150]
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: [{"DID": 1}] * (2 if cid == 100 else 3)
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 1
        assert collisions[0].risk_level == "medium"

    def test_collision_three_companies(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>OVERLAP</ImportDID></Filters>'
            '<Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "collision3.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 150, 200]
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 1
        assert collisions[0].risk_level == "high"

    def test_batch_not_flagged(self, email_fixture, mock_deal_repo):
        """Same ImportDID, same CompanyID → NOT a collision."""
        mock_deal_repo.get_companies_by_import_did.return_value = [150]
        detector = CollisionDetector(email_fixture, mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 0

    def test_affected_jobs_listed(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<JobA><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>CLASH</ImportDID></Filters><Parsers><P>.*</P></Parsers></JobA>'
            '<JobB><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>CLASH</ImportDID></Filters><Parsers><P>.*</P></Parsers></JobB>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "affected.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.side_effect = None
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 200]
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 1
        assert "JobA" in collisions[0].affected_jobs
        assert "JobB" in collisions[0].affected_jobs

    def test_deal_counts_per_company(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>OVERLAP</ImportDID></Filters><Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "counts.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 150]
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: {
            100: [{"DID": 1}, {"DID": 2}],
            150: [{"DID": 3}],
        }.get(cid, [])
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert collisions[0].deal_counts[100] == 2
        assert collisions[0].deal_counts[150] == 1

    def test_case_insensitive_keyword(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>overlap</ImportDID></Filters><Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "case.xml"
        xml_path.write_text(xml_content)
        # The DealRepo mock uses .upper() for lookup
        mock_deal_repo.get_companies_by_import_did.side_effect = lambda kw: {
            "OVERLAP": [100, 150],
        }.get(kw.upper(), [])
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 1

    def test_empty_import_did_skipped(self, email_fixture, mock_deal_repo):
        """Jobs with empty ImportDID should be skipped."""
        # The fixture has no ImportDID filters, so all are empty
        mock_deal_repo.get_companies_by_import_did.return_value = []
        detector = CollisionDetector(email_fixture, mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        # Should not crash and should return empty (no keywords to check)
        assert isinstance(collisions, list)

    def test_multiple_collisions(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>KEY1</ImportDID></Filters><Parsers><P>.*</P></Parsers></J1>'
            '<J2><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>KEY2</ImportDID></Filters><Parsers><P>.*</P></Parsers></J2>'
            '<J3><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>KEY3</ImportDID></Filters><Parsers><P>.*</P></Parsers></J3>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "multi.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.side_effect = None
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 200]
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 3

    def test_single_company_not_collision(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>UNIQUE</ImportDID></Filters><Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "single.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.return_value = [100]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 0

    def test_db_error_graceful(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_companies_by_import_did.side_effect = Exception("DB fail")
        detector = CollisionDetector(email_fixture, mock_deal_repo, xml_type="email")
        # Should log warning and continue, not crash
        collisions = detector.detect()
        assert isinstance(collisions, list)

    def test_whitespace_in_keyword(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<J1><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID> OVERLAP </ImportDID></Filters><Parsers><P>.*</P></Parsers></J1>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "ws.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.side_effect = lambda kw: {
            "OVERLAP": [100, 150],
        }.get(kw.strip().upper(), [])
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        # Trimmed keyword should detect collision
        assert len(collisions) >= 1

    def test_keyword_job_mapping(self, tmp_path, mock_deal_repo):
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<Alpha><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>SHARED</ImportDID></Filters><Parsers><P>.*</P></Parsers></Alpha>'
            '<Beta><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<Filters><ImportDID>SHARED</ImportDID></Filters><Parsers><P>.*</P></Parsers></Beta>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "shared.xml"
        xml_path.write_text(xml_content)
        mock_deal_repo.get_companies_by_import_did.side_effect = None
        mock_deal_repo.get_companies_by_import_did.return_value = [100, 200]
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [{"DID": 1}]
        detector = CollisionDetector(str(xml_path), mock_deal_repo, xml_type="email")
        collisions = detector.detect()
        assert len(collisions) == 1
        assert "Alpha" in collisions[0].affected_jobs
        assert "Beta" in collisions[0].affected_jobs
