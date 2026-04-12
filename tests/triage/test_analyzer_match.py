"""Tests for TriageAnalyzer.match_only() — E-02."""
import pytest
from unittest.mock import MagicMock, patch

from backend.triage.analyzer import TriageAnalyzer
from backend.triage.models import EmailInfo, TriageResult
from backend.xml.models import EmailJob


@pytest.fixture
def mock_jobs():
    return [
        EmailJob(
            name="TestJob_Alpha",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="Team",
            filters={"From": "sender@acme.com", "Subject": "Monthly Report"},
            servicer_id=150,
        ),
        EmailJob(
            name="TestJob_Beta",
            mailbox="frp.test@example.com",
            folder="Inbox",
            sme="Team",
            filters={"From": "reports@beta.org"},
            servicer_id=200,
        ),
    ]


@pytest.fixture
def analyzer(mock_jobs):
    with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
        inst = MagicMock()
        inst.get_all_jobs.return_value = mock_jobs
        cls.return_value = inst
        yield TriageAnalyzer("fake_settings.xml", "email")


class TestMatchOnly:

    def test_match_by_msg_path(self, analyzer):
        email = EmailInfo(
            sender="sender@acme.com",
            sender_name="ACME",
            subject="Monthly Report",
            date="2025-01-15",
            file_path="C:\\test.msg",
        )
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            result = analyzer.match_only(msg_path="C:\\test.msg")
        assert result.has_match is True

    def test_match_by_sender(self, analyzer):
        result = analyzer.match_only(sender="sender@acme.com")
        assert isinstance(result, TriageResult)
        assert result.has_match is True

    def test_match_by_subject(self, analyzer):
        result = analyzer.match_only(subject="Monthly Report")
        assert isinstance(result, TriageResult)
        assert result.has_match is True

    def test_match_both_sender_subject(self, analyzer):
        result = analyzer.match_only(
            sender="sender@acme.com",
            subject="Monthly Report",
        )
        assert result.has_match is True
        alpha = [m for m in result.matches if m.job_name == "TestJob_Alpha"]
        assert len(alpha) == 1
        assert alpha[0].match_type == "both"

    def test_match_no_args(self, analyzer):
        with pytest.raises(ValueError, match="Provide"):
            analyzer.match_only()

    def test_match_results_sorted(self, analyzer):
        result = analyzer.match_only(
            sender="sender@acme.com",
            subject="Monthly Report",
        )
        if len(result.matches) >= 2:
            scores = [m.sort_score for m in result.matches]
            assert scores == sorted(scores, reverse=True)
