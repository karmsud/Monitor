"""Tests for CoverageAnalyzer."""
import os
import shutil

import pytest
from unittest.mock import MagicMock, patch

from backend.intel.coverage import CoverageAnalyzer, _get_import_did
from backend.intel.models import CoverageReport
from backend.xml.models import EmailJob, SftpJob


class TestCoverageAnalyzer:

    def test_full_coverage(self, email_fixture, mock_deal_repo):
        """All DIDs matched → 100% coverage."""
        # Make repo return DIDs that match job ImportDID keywords
        mock_deal_repo.get_deals_by_company.side_effect = lambda cid: {
            150: [
                {"DID": 1, "ImportDID": "CSMC", "CompanyID": 150},
            ],
            200: [
                {"DID": 2, "ImportDID": "BETAKW", "CompanyID": 200},
            ],
        }.get(cid, [])

        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert len(reports) == 1
        assert reports[0].coverage_percentage == 100.0

    def test_no_coverage(self, email_fixture, mock_deal_repo):
        """0 of N DIDs matched → 0% coverage."""
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "NOMATCH_XYZ", "CompanyID": 150},
            {"DID": 2, "ImportDID": "NOMATCH_ABC", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert len(reports) == 1
        assert reports[0].coverage_percentage == 0.0
        assert len(reports[0].unmapped_dids) == 2

    def test_partial_coverage(self, email_fixture, mock_deal_repo):
        """Some DIDs matched, some not."""
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2, "ImportDID": "NOMATCH", "CompanyID": 150},
            {"DID": 3, "ImportDID": "NOMATCH2", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert len(reports) == 1
        assert 0 < reports[0].coverage_percentage < 100

    def test_unmapped_dids_listed(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 99, "ImportDID": "UNMAPPED_KEYWORD", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        unmapped = reports[0].unmapped_dids
        assert len(unmapped) == 1
        assert unmapped[0]["import_did"] == "UNMAPPED_KEYWORD"

    def test_matching_jobs_listed(self, email_fixture, mock_deal_repo):
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        # Servicer 150 = TestJob_Alpha
        assert len(reports) == 1
        assert "TestJob_Alpha" in reports[0].matching_jobs

    def test_single_servicer(self, email_fixture, mock_deal_repo):
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert len(reports) == 1
        assert reports[0].servicer_id == 150

    def test_all_servicers(self, email_fixture, mock_deal_repo):
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=None)
        # The fixture has servicer IDs 150 and 200
        sids = {r.servicer_id for r in reports}
        assert 150 in sids
        assert 200 in sids

    def test_servicer_not_in_xml(self, email_fixture, mock_deal_repo):
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=999)
        assert len(reports) == 1
        assert reports[0].matching_jobs == []

    def test_case_insensitive_match(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "csmc", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert reports[0].mapped_dids >= 1

    def test_empty_import_did_not_matched(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        # Empty ImportDID should not count as covered
        assert reports[0].mapped_dids == 0

    def test_no_deals_in_db(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = []
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert reports[0].total_dids == 0
        assert reports[0].coverage_percentage == 0.0

    def test_db_error_graceful(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = Exception("DB error")
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        # Should not raise — error logged, but skipped
        reports = analyzer.analyze(servicer_id=150)
        # May return empty reports due to error
        assert isinstance(reports, list)

    def test_is_covered_exact_match(self):
        assert CoverageAnalyzer._is_covered("CSMC", ["CSMC"]) is True

    def test_is_covered_no_match(self):
        assert CoverageAnalyzer._is_covered("CSMC", ["ACME"]) is False

    def test_is_covered_empty_keyword(self):
        assert CoverageAnalyzer._is_covered("", ["CSMC"]) is False

    def test_multiple_jobs_same_servicer(self, tmp_path, mock_deal_repo):
        """Multiple jobs with same servicer should all appear in matching_jobs."""
        xml_content = (
            '<Settings><Outlook><Enabled>1</Enabled><MailboxCollection>'
            '<Job_A><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>150</ServicerID><Parsers><P1>.*</P1></Parsers></Job_A>'
            '<Job_B><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>150</ServicerID><Parsers><P2>.*</P2></Parsers></Job_B>'
            '<Job_C><Mailbox>x@y.com</Mailbox><Folder>Inbox</Folder><SME>a@b.com</SME>'
            '<ServicerID>150</ServicerID><Parsers><P3>.*</P3></Parsers></Job_C>'
            '</MailboxCollection></Outlook></Settings>'
        )
        xml_path = tmp_path / "multi.xml"
        xml_path.write_text(xml_content)
        analyzer = CoverageAnalyzer(str(xml_path), mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert len(reports[0].matching_jobs) == 3

    def test_import_did_keyword_overlap(self, email_fixture, mock_deal_repo):
        """A job keyword that covers multiple DIDs should count all."""
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2, "ImportDID": "CSMC", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert reports[0].mapped_dids == 2

    def test_whitespace_trimmed(self, email_fixture, mock_deal_repo):
        mock_deal_repo.get_deals_by_company.side_effect = None
        mock_deal_repo.get_deals_by_company.return_value = [
            {"DID": 1, "ImportDID": " CSMC ", "CompanyID": 150},
        ]
        analyzer = CoverageAnalyzer(email_fixture, mock_deal_repo, xml_type="email")
        reports = analyzer.analyze(servicer_id=150)
        assert reports[0].mapped_dids >= 1
