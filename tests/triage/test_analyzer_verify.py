"""Tests for TriageAnalyzer.verify() — E-01."""
import pytest
from unittest.mock import MagicMock, patch

from backend.triage.analyzer import TriageAnalyzer
from backend.triage.models import EmailInfo, MatchResult, TriageResult
from backend.xml.models import EmailJob


# ──────────────────────────────────────────────────────────────────────────── #
#   Fixtures
# ──────────────────────────────────────────────────────────────────────────── #

@pytest.fixture
def mock_jobs():
    return [
        EmailJob(
            name="TestJob_Alpha",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="Team",
            filters={"From": "sender@acme.com"},
            servicer_id=150,
        ),
    ]


@pytest.fixture
def matching_email():
    return EmailInfo(
        sender="sender@acme.com",
        sender_name="ACME Sender",
        subject="Monthly Data",
        date="2025-01-15T10:00:00",
        to=["frp.test@example.com"],
        cc=[],
        body_preview="Please see attached.",
        attachment_names=["report.xlsx"],
        file_path="C:\\emails\\sample.msg",
    )


@pytest.fixture
def non_matching_email():
    return EmailInfo(
        sender="nobody@random.org",
        sender_name="Nobody",
        subject="Unrelated",
        date="2025-01-15T10:00:00",
        to=["other@example.com"],
        cc=[],
        body_preview="Nothing relevant.",
        attachment_names=[],
        file_path="C:\\emails\\no_match.msg",
    )


@pytest.fixture
def analyzer_with_match(mock_jobs, matching_email):
    with patch("backend.triage.analyzer.SettingsXmlParser") as mock_parser_cls:
        inst = MagicMock()
        inst.get_all_jobs.return_value = mock_jobs
        mock_parser_cls.return_value = inst
        with patch("backend.triage.analyzer.MsgParser") as mock_msg:
            mock_msg.parse.return_value = matching_email
            analyzer = TriageAnalyzer("fake_settings.xml", "email")
            yield analyzer, mock_msg


@pytest.fixture
def analyzer_no_match(mock_jobs, non_matching_email):
    with patch("backend.triage.analyzer.SettingsXmlParser") as mock_parser_cls:
        inst = MagicMock()
        inst.get_all_jobs.return_value = mock_jobs
        mock_parser_cls.return_value = inst
        with patch("backend.triage.analyzer.MsgParser") as mock_msg:
            mock_msg.parse.return_value = non_matching_email
            analyzer = TriageAnalyzer("fake_settings.xml", "email")
            yield analyzer, mock_msg


# ──────────────────────────────────────────────────────────────────────────── #
#   Tests
# ──────────────────────────────────────────────────────────────────────────── #

class TestVerify:

    def test_verify_with_match(self, analyzer_with_match):
        analyzer, _ = analyzer_with_match
        result = analyzer.verify("C:\\emails\\sample.msg")
        assert result.has_match is True
        assert len(result.matches) >= 1

    def test_verify_accepts_exact_mailbox_match_from_cc(self, mock_jobs):
        email = EmailInfo(
            sender="nobody@random.org",
            sender_name="Nobody",
            subject="Unrelated",
            date="2025-01-15T10:00:00",
            to=["other@example.com"],
            cc=["frp.test@example.com"],
            body_preview="Nothing relevant.",
            attachment_names=[],
            file_path="C:\\emails\\cc_match.msg",
        )
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = mock_jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = email
                analyzer = TriageAnalyzer("fake.xml", "email")
                result = analyzer.verify("C:\\emails\\cc_match.msg")
        assert result.has_match is True
        assert any(match.job_name == "TestJob_Alpha" for match in result.matches)

    def test_verify_no_match(self, analyzer_no_match):
        analyzer, _ = analyzer_no_match
        result = analyzer.verify("C:\\emails\\no_match.msg")
        assert result.has_match is False
        assert result.matches == []

    def test_verify_recommendation_match(self, analyzer_with_match):
        analyzer, _ = analyzer_with_match
        result = analyzer.verify("C:\\emails\\sample.msg")
        assert "Best match" in result.recommendation or "TestJob_Alpha" in result.recommendation

    def test_verify_recommendation_no_match(self, analyzer_no_match):
        analyzer, _ = analyzer_no_match
        result = analyzer.verify("C:\\emails\\no_match.msg")
        assert "new job" in result.recommendation.lower() or "no existing" in result.recommendation.lower()

    def test_verify_coverage_check(self, mock_jobs, matching_email):
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = [
            {"DID": 1001, "ImportDID": "ACME", "CompanyID": 150},
        ]
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = mock_jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = matching_email
                analyzer = TriageAnalyzer("fake.xml", "email", deal_repo)
                result = analyzer.verify("C:\\emails\\sample.msg")
        assert result.coverage_status == "covered"
        assert result.did_count == 1

    def test_verify_coverage_no_deals(self, mock_jobs, matching_email):
        deal_repo = MagicMock()
        deal_repo.get_deals_by_company.return_value = []
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = mock_jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = matching_email
                analyzer = TriageAnalyzer("fake.xml", "email", deal_repo)
                result = analyzer.verify("C:\\emails\\sample.msg")
        assert result.coverage_status == "no_deals"

    def test_verify_file_not_found(self, mock_jobs):
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = mock_jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.side_effect = FileNotFoundError("File not found")
                analyzer = TriageAnalyzer("fake.xml", "email")
                with pytest.raises(FileNotFoundError):
                    analyzer.verify("C:\\missing.msg")

    def test_verify_invalid_settings(self):
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            cls.side_effect = Exception("Bad XML")
            with pytest.raises(ValueError, match="Failed to parse settings"):
                TriageAnalyzer("bad_settings.xml", "email")

    def test_verify_multiple_matches(self, matching_email):
        jobs = [
            EmailJob(name="Job1", mailbox="frp.test@example.com", folder="Inbox",
                     sme="T", filters={"From": "sender@acme.com"}, servicer_id=150),
            EmailJob(name="Job2", mailbox="", folder="Inbox",
                     sme="T", filters={"From": "acme.com"}, servicer_id=200),
        ]
        with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
            inst = MagicMock()
            inst.get_all_jobs.return_value = jobs
            cls.return_value = inst
            with patch("backend.triage.analyzer.MsgParser") as mp:
                mp.parse.return_value = matching_email
                analyzer = TriageAnalyzer("fake.xml", "email")
                result = analyzer.verify("C:\\emails\\sample.msg")
        assert len(result.matches) >= 2
        # Sorted by sort_score descending
        scores = [m.sort_score for m in result.matches]
        assert scores == sorted(scores, reverse=True)

    def test_verify_email_info_populated(self, analyzer_with_match):
        analyzer, _ = analyzer_with_match
        result = analyzer.verify("C:\\emails\\sample.msg")
        assert result.email_info is not None
        assert result.email_info.sender != ""
        assert result.email_info.subject != ""
        assert result.email_info.file_path != ""
