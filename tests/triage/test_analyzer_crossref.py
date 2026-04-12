"""Tests for TriageAnalyzer cross-reference enhancements.

Covers:
- _match_dids_to_email (DID keyword matching in Subject/Filename/Both modes)
- _assess_confidence (evidence-chain confidence labels)
- verify() with log_indexer and ts_repo integration
- SFTP MoveFile/MoveFile2 filename-only matching
"""
import pytest
from unittest.mock import MagicMock, patch

from backend.triage.analyzer import TriageAnalyzer
from backend.triage.models import DIDMatch, EmailInfo, MatchResult, TriageResult
from backend.xml.models import EmailJob, SftpJob


# ──────────────────────────────────────────────────────────────────────────── #
#   Fixtures
# ──────────────────────────────────────────────────────────────────────────── #

@pytest.fixture
def email_info_subject():
    """Email with a recognisable keyword in the subject."""
    return EmailInfo(
        sender="reports@fayservicing.com",
        sender_name="Fay Servicing",
        subject="Monthly Report CMLTI2006NC2",
        date="2025-06-01T09:00:00",
        attachment_names=["data_file.xlsx"],
    )


@pytest.fixture
def email_info_filename():
    """Email with a recognisable keyword in an attachment name."""
    return EmailInfo(
        sender="reports@fayservicing.com",
        sender_name="Fay Servicing",
        subject="See attached",
        date="2025-06-01T09:00:00",
        attachment_names=["CMLTI2006NC2_20250601.xlsx", "coversheet.pdf"],
    )


@pytest.fixture
def email_info_both():
    """Email with keywords in both subject and attachment."""
    return EmailInfo(
        sender="reports@fayservicing.com",
        sender_name="Fay Servicing",
        subject="Monthly Report CMLTI2006NC2",
        date="2025-06-01T09:00:00",
        attachment_names=["WAMU2007OA5_20250601.xlsx"],
    )


@pytest.fixture
def deals_list():
    """Sample deals from tblExternalDIDRef."""
    return [
        {"DID": "1001", "ImportDID": "CMLTI2006NC2", "CompanyID": 296},
        {"DID": "1002", "ImportDID": "WAMU2007OA5", "CompanyID": 296},
        {"DID": "1003", "ImportDID": "NONEXISTENT", "CompanyID": 296},
    ]


@pytest.fixture
def email_job_subject():
    """EmailJob using DetachFileSubject parser → Subject match mode."""
    return EmailJob(
        name="CMLTI_Fay",
        mailbox="rptent@usbank.com",
        folder="Inbox",
        sme="Team",
        filters={"From": "@fayservicing.com"},
        servicer_id=296,
        parsers={"DetachFileSubject": {"Keyword": "CMLTI"}},
        templates={"Main": "CMLTI_Fay_1948"},
    )


@pytest.fixture
def email_job_filename():
    """EmailJob using DetachFile parser → Filename match mode."""
    return EmailJob(
        name="Plaza_RTL_Fay",
        mailbox="rptent@usbank.com",
        folder="Inbox",
        sme="Team",
        filters={"From": "@fayservicing.com"},
        servicer_id=296,
        parsers={"DetachFile": {"Extensions": ".xlsx"}},
        templates={"Main": "Plaza_RTL_Fay_3003"},
    )


@pytest.fixture
def email_job_both():
    """EmailJob using both parsers → Both match mode."""
    return EmailJob(
        name="DualParser_Job",
        mailbox="rptent@usbank.com",
        folder="Inbox",
        sme="Team",
        filters={"From": "@fayservicing.com"},
        servicer_id=296,
        parsers={
            "DetachFileSubject": {"Keyword": "DUAL"},
            "DetachFile": {"Extensions": ".xlsx"},
        },
        templates={"Main": "DualParser_1234"},
    )


@pytest.fixture
def sftp_job_movefile():
    """SftpJob using MoveFile parser → Filename match mode."""
    return SftpJob(
        name="SFTP_Fay_Move",
        path="/incoming/fay",
        servicer_id=296,
        dsn="sftp.fay.com",
        sme="Team",
        parsers={"MoveFile": {"DestPath": "/processed"}},
        templates={"Main": "SFTP_Fay_Template"},
    )


@pytest.fixture
def sftp_job_movefile2():
    """SftpJob using MoveFile2 parser → Filename match mode."""
    return SftpJob(
        name="SFTP_Fay_Move2",
        path="/incoming/fay",
        servicer_id=296,
        dsn="sftp.fay.com",
        sme="Team",
        parsers={"MoveFile2": {"DestPath": "/processed"}},
        templates={"Main": "SFTP_Fay_Template2"},
    )


# ──────────────────────────────────────────────────────────────────────────── #
#   _match_dids_to_email
# ──────────────────────────────────────────────────────────────────────────── #

class TestMatchDIDsToEmail:
    """Unit tests for the static _match_dids_to_email helper."""

    def test_subject_mode_finds_keyword_in_subject(self, email_info_subject, deals_list):
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_subject, "Subject")
        assert len(hits) == 1
        assert hits[0].did == "1001"
        assert hits[0].import_did == "CMLTI2006NC2"
        assert hits[0].matched_in == "subject"

    def test_filename_mode_finds_keyword_in_attachment(self, email_info_filename, deals_list):
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_filename, "Filename")
        assert len(hits) == 1
        assert hits[0].did == "1001"
        assert hits[0].matched_in == "filename"
        assert "CMLTI2006NC2" in hits[0].matched_value

    def test_subject_mode_ignores_filenames(self, email_info_filename, deals_list):
        """Subject mode should NOT match keywords in attachment names."""
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_filename, "Subject")
        assert len(hits) == 0

    def test_filename_mode_ignores_subject(self, email_info_subject, deals_list):
        """Filename mode should NOT match keywords in subject."""
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_subject, "Filename")
        assert len(hits) == 0

    def test_both_mode_finds_in_subject_and_filename(self, email_info_both, deals_list):
        """Both mode finds CMLTI in subject, WAMU in filename."""
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_both, "Both")
        assert len(hits) == 2
        matched_dids = {h.did for h in hits}
        assert "1001" in matched_dids  # CMLTI2006NC2 in subject
        assert "1002" in matched_dids  # WAMU2007OA5 in filename

    def test_both_mode_subject_priority(self, deals_list):
        """If keyword appears in both subject and filename, report as subject."""
        email = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="File CMLTI2006NC2 attached",
            date="2025-01-01",
            attachment_names=["CMLTI2006NC2_report.xlsx"],
        )
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email, "Both")
        cmlti_hit = [h for h in hits if h.did == "1001"][0]
        assert cmlti_hit.matched_in == "subject"  # subject takes priority

    def test_case_insensitive_matching(self, deals_list):
        email = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="Report cmlti2006nc2",
            date="2025-01-01",
        )
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email, "Subject")
        assert len(hits) == 1

    def test_subject_matching_ignores_spacing_and_punctuation(self, deals_list):
        email = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="Report FREMF 18-KS10 monthly tape",
            date="2025-01-01",
        )
        deals = deals_list + [{"DID": "5065", "ImportDID": "FREMF18KS10", "CompanyID": 224}]
        hits = TriageAnalyzer._match_dids_to_email(deals, email, "Subject")
        assert any(hit.did == "5065" and hit.matched_in == "subject" for hit in hits)

    def test_filename_matching_ignores_spacing_and_punctuation(self, deals_list):
        email = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="Report",
            date="2025-01-01",
            attachment_names=["FREMF 18-KS10_202603_IRP.zip"],
        )
        deals = deals_list + [{"DID": "5065", "ImportDID": "FREMF18KS10", "CompanyID": 224}]
        hits = TriageAnalyzer._match_dids_to_email(deals, email, "Filename")
        assert any(hit.did == "5065" and hit.matched_in == "filename" for hit in hits)

    def test_no_matches_returns_empty(self, deals_list):
        email = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="Nothing relevant here",
            date="2025-01-01",
            attachment_names=["unrelated.pdf"],
        )
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email, "Both")
        assert hits == []

    def test_none_mode_returns_empty(self, email_info_subject, deals_list):
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email_info_subject, "(none)")
        assert hits == []

    def test_empty_import_did_skipped(self, email_info_subject):
        deals = [{"DID": "999", "ImportDID": "", "CompanyID": 100}]
        hits = TriageAnalyzer._match_dids_to_email(deals, email_info_subject, "Subject")
        assert hits == []

    def test_sftp_movefile_filename_only(self, deals_list):
        """SFTP MoveFile jobs should match against filename, not subject."""
        from backend.xml.models import _match_mode

        # MoveFile parser → Filename mode
        parsers = {"MoveFile": {"DestPath": "/processed"}}
        mode = _match_mode(parsers)
        assert mode == "Filename"

        email = EmailInfo(
            sender="sftp-system",
            sender_name="SFTP",
            subject="CMLTI2006NC2 in subject",
            date="2025-01-01",
            attachment_names=["WAMU2007OA5_20250601.xlsx"],
        )
        hits = TriageAnalyzer._match_dids_to_email(deals_list, email, mode)
        # Only WAMU in filename should match, not CMLTI in subject
        assert len(hits) == 1
        assert hits[0].did == "1002"
        assert hits[0].matched_in == "filename"

    def test_sftp_movefile2_filename_only(self, deals_list):
        """SFTP MoveFile2 parser also → Filename mode."""
        from backend.xml.models import _match_mode

        parsers = {"MoveFile2": {"DestPath": "/processed"}}
        mode = _match_mode(parsers)
        assert mode == "Filename"


# ──────────────────────────────────────────────────────────────────────────── #
#   _assess_confidence
# ──────────────────────────────────────────────────────────────────────────── #

class TestAssessConfidence:
    """Unit tests for _assess_confidence static method."""

    def _make_result(self, has_match=True, did_matches=None,
                     log_summary=None, template_status=None):
        return TriageResult(
            email_info=EmailInfo(
                sender="test@example.com",
                sender_name="Test",
                subject="Test",
                date="2025-01-01",
            ),
            has_match=has_match,
            did_matches=did_matches or [],
            log_summary=log_summary,
            template_status=template_status,
        )

    def test_no_match_returns_empty(self):
        r = self._make_result(has_match=False)
        assert TriageAnalyzer._assess_confidence(r) == ""

    def test_match_only_returns_monitored(self):
        r = self._make_result(has_match=True)
        assert TriageAnalyzer._assess_confidence(r) == "monitored"

    def test_dids_only_returns_should_process(self):
        r = self._make_result(
            did_matches=[DIDMatch("1", "KW", "subject", "test")],
        )
        assert TriageAnalyzer._assess_confidence(r) == "should_process"

    def test_dids_plus_logs_returns_processed(self):
        r = self._make_result(
            did_matches=[DIDMatch("1", "KW", "subject", "test")],
            log_summary={"total_events": 5},
        )
        assert TriageAnalyzer._assess_confidence(r) == "processed"

    def test_dids_plus_template_run_returns_completed(self):
        r = self._make_result(
            did_matches=[DIDMatch("1", "KW", "subject", "test")],
            template_status={"summary": {"total_runs": 3}},
        )
        assert TriageAnalyzer._assess_confidence(r) == "completed"

    def test_dids_plus_logs_plus_template_returns_completed(self):
        r = self._make_result(
            did_matches=[DIDMatch("1", "KW", "subject", "test")],
            log_summary={"total_events": 10},
            template_status={"summary": {"total_runs": 5}},
        )
        assert TriageAnalyzer._assess_confidence(r) == "completed"

    def test_logs_only_no_dids_returns_monitored(self):
        """Without DID matches, logs alone don't elevate confidence."""
        r = self._make_result(
            log_summary={"total_events": 10},
        )
        assert TriageAnalyzer._assess_confidence(r) == "monitored"

    def test_empty_logs_treated_as_no_logs(self):
        r = self._make_result(
            did_matches=[DIDMatch("1", "KW", "subject", "test")],
            log_summary={"total_events": 0},
        )
        assert TriageAnalyzer._assess_confidence(r) == "should_process"


# ──────────────────────────────────────────────────────────────────────────── #
#   verify() full cross-reference chain
# ──────────────────────────────────────────────────────────────────────────── #

class TestVerifyCrossRef:
    """Integration-style tests for verify() with all services wired up."""

    def _build_and_verify(self, jobs, email, deal_repo=None,
                          log_indexer=None, ts_repo=None, xml_type="email"):
        """Create a TriageAnalyzer with mocked parser/msg, call verify(), return result."""
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = email
                analyzer = TriageAnalyzer(
                    "fake.xml", xml_type,
                    deal_repo=deal_repo,
                    log_indexer=log_indexer,
                    ts_repo=ts_repo,
                )
                return analyzer.verify("test.msg")

    def test_verify_full_chain(self, email_job_subject, email_info_subject, deals_list):
        """verify() populates deals, did_matches, log_summary, template_status."""
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        log_indexer = MagicMock()
        log_indexer.get_job_summary.return_value = {
            "job_name": "CMLTI_Fay",
            "total_events": 42,
            "total_files_loaded": 10,
            "total_errors": 0,
        }

        ts_repo = MagicMock()
        ts_repo.get_recent_by_query.return_value = {
            "summary": {"total_runs": 8, "success_rate": 100.0},
            "runs": [],
        }

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            deal_repo=deal_repo,
            log_indexer=log_indexer,
            ts_repo=ts_repo,
        )

        assert result.has_match is True
        assert result.deals == deals_list
        assert result.did_count == 3
        assert result.coverage_status == "covered"
        # CMLTI2006NC2 should match in subject
        assert len(result.did_matches) == 1
        assert result.did_matches[0].import_did == "CMLTI2006NC2"
        assert result.did_matches[0].matched_in == "subject"
        # Log summary populated
        assert result.log_summary["total_events"] == 42
        # Template status populated
        assert result.template_status["summary"]["total_runs"] == 8
        # Confidence: DID + logs + template → completed
        assert result.confidence == "completed"

    def test_verify_did_match_filename_mode(
        self, email_job_filename, email_info_filename, deals_list,
    ):
        """Filename-mode job detects keyword in attachment names."""
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        result = self._build_and_verify(
            [email_job_filename], email_info_filename,
            deal_repo=deal_repo,
        )

        assert result.has_match is True
        assert len(result.did_matches) == 1
        assert result.did_matches[0].matched_in == "filename"
        assert "CMLTI2006NC2" in result.did_matches[0].matched_value

    def test_verify_no_deal_repo(self, email_job_subject, email_info_subject):
        """Without deal_repo, DID fields stay at defaults."""
        result = self._build_and_verify([email_job_subject], email_info_subject)
        assert result.has_match is True
        assert result.deals is None
        assert result.did_matches == []
        assert result.confidence == "monitored"

    def test_verify_no_log_indexer(
        self, email_job_subject, email_info_subject, deals_list,
    ):
        """Without log_indexer, log_summary stays None."""
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            deal_repo=deal_repo,
        )
        assert result.log_summary is None
        assert result.confidence == "should_process"  # DID matches but no logs

    def test_verify_template_lookup_uses_main_template(
        self, email_job_subject, email_info_subject, deals_list,
    ):
        """ts_repo.get_recent_by_query receives the Main template name."""
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        ts_repo = MagicMock()
        ts_repo.get_recent_by_query.return_value = {
            "summary": {"total_runs": 0},
            "runs": [],
        }

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            deal_repo=deal_repo, ts_repo=ts_repo,
        )
        ts_repo.get_recent_by_query.assert_called_once_with("CMLTI_Fay_1948")

    def test_verify_sftp_movefile_filename_match(
        self, sftp_job_movefile, deals_list,
    ):
        """SFTP MoveFile jobs use filename-only matching."""
        email = EmailInfo(
            sender="sftp@system",
            sender_name="SFTP",
            subject="CMLTI2006NC2 in subject should be ignored",
            date="2025-01-01",
            attachment_names=["WAMU2007OA5_monthly.xlsx"],
        )
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        # Use sftp xml_type
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = [sftp_job_movefile]
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = email
                with patch("backend.triage.analyzer.TriageMatcher") as tm:
                    tm.match.return_value = [
                        MatchResult(
                            job_name="SFTP_Fay_Move",
                            xml_type="sftp",
                            match_type="sender",
                            match_confidence="exact",
                            servicer_id="296",
                            matched_filter="sftp@system",
                            email_field_matched="sftp@system",
                        ),
                    ]
                    analyzer = TriageAnalyzer(
                        "fake.xml", "sftp",
                        deal_repo=deal_repo,
                    )
                    result = analyzer.verify("test.msg")

        # Only WAMU in filename should match — not CMLTI in subject
        assert len(result.did_matches) == 1
        assert result.did_matches[0].did == "1002"
        assert result.did_matches[0].matched_in == "filename"

    def test_verify_to_dict_serialises_did_matches(
        self, email_job_subject, email_info_subject, deals_list,
    ):
        """TriageResult.to_dict() includes did_matches as list of dicts."""
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = deals_list

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            deal_repo=deal_repo,
        )
        d = result.to_dict()

        assert "did_matches" in d
        assert isinstance(d["did_matches"], list)
        if d["did_matches"]:
            assert "did" in d["did_matches"][0]
            assert "import_did" in d["did_matches"][0]

    def test_verify_log_indexer_error_graceful(
        self, email_job_subject, email_info_subject,
    ):
        """If log_indexer throws, verify() still completes."""
        log_indexer = MagicMock()
        log_indexer.get_job_summary.side_effect = RuntimeError("DB locked")

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            log_indexer=log_indexer,
        )
        assert result.has_match is True
        assert result.log_summary is None  # Graceful fallback

    def test_verify_ts_repo_error_graceful(
        self, email_job_subject, email_info_subject,
    ):
        """If ts_repo throws, verify() still completes."""
        ts_repo = MagicMock()
        ts_repo.get_recent_by_query.side_effect = RuntimeError("Connection lost")

        result = self._build_and_verify(
            [email_job_subject], email_info_subject,
            ts_repo=ts_repo,
        )
        assert result.has_match is True
        assert result.template_status is None  # Graceful fallback
