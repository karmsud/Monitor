"""Tests for TriageAnalyzer.analyze_new() — E-03."""
import pytest
from unittest.mock import MagicMock, patch

from backend.triage.analyzer import TriageAnalyzer
from backend.triage.models import EmailInfo, TriageResult
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
            filters={"From": "sender@acme.com", "Subject": "Monthly Report"},
            servicer_id=150,
        ),
    ]


def _make_analyzer(mock_jobs, deal_repo=None):
    """Helper to build an analyzer with patched settings parser."""
    with patch("backend.triage.analyzer.SettingsXmlParser") as cls:
        inst = MagicMock()
        inst.get_all_jobs.return_value = mock_jobs
        cls.return_value = inst
        return TriageAnalyzer("fake_settings.xml", "email", deal_repo)


def _email_no_match(**overrides):
    """Build an EmailInfo that does NOT match TestJob_Alpha."""
    defaults = dict(
        sender="newvendor@vendor.com",
        sender_name="Vendor",
        subject="New Monthly Data 01/15/2025",
        date="2025-01-15T10:00:00",
        to=["someone@elsewhere.com"],
        cc=[],
        body_preview="Please process the attached file.",
        attachment_names=["data_jan2025.xlsx"],
        file_path="C:\\emails\\new.msg",
    )
    defaults.update(overrides)
    return EmailInfo(**defaults)


# ──────────────────────────────────────────────────────────────────────────── #
#   Tests
# ──────────────────────────────────────────────────────────────────────────── #

class TestAnalyzeNew:

    def test_new_email_no_match(self, mock_jobs):
        email = _email_no_match()
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\emails\\new.msg")
        assert result.has_match is False
        assert result.suggested_config is not None
        assert "suggested_parser" in result.suggested_config

    def test_new_email_already_matched(self, mock_jobs):
        email = EmailInfo(
            sender="sender@acme.com",
            sender_name="ACME",
            subject="Monthly Report",
            date="2025-01-15",
            to=["frp.test@example.com"],
            file_path="C:\\emails\\match.msg",
        )
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            result = analyzer.analyze_new("C:\\emails\\match.msg")
        assert result.has_match is True
        assert "already matches" in result.recommendation.lower()

    def test_new_email_partial_sender_without_mailbox_stays_new(self, mock_jobs):
        jobs = [
            EmailJob(
                name="BayviewAdditions_4000",
                mailbox="bayview@usbank.com",
                folder="Inbox",
                sme="Team",
                filters={"From": "@usbank.com"},
                servicer_id=4000,
            ),
        ]
        email = _email_no_match(
            sender="earl.cruz@usbank.com",
            to=["Pascale"],
            subject="RE: HET 2024 A1/A2 and B Invoices",
        )
        analyzer = _make_analyzer(jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\emails\\new.msg")
        assert result.has_match is False
        assert result.matches == []
        assert "no existing jobs match" in result.recommendation.lower()

    def test_suggested_parser_excel(self, mock_jobs):
        email = _email_no_match(attachment_names=["report.xlsx"])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "excel"

    def test_suggested_parser_csv(self, mock_jobs):
        email = _email_no_match(attachment_names=["data.csv"])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "csv"

    def test_suggested_parser_pdf(self, mock_jobs):
        email = _email_no_match(attachment_names=["document.pdf"])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "pdf"

    def test_suggested_parser_archive(self, mock_jobs):
        email = _email_no_match(attachment_names=["archive.zip"])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "archive"

    def test_suggested_parser_text(self, mock_jobs):
        email = _email_no_match(attachment_names=["readme.txt"])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "text"

    def test_suggested_parser_generic(self, mock_jobs):
        email = _email_no_match(attachment_names=[])
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["suggested_parser"] == "generic"

    def test_subject_pattern_extraction(self, mock_jobs):
        email = _email_no_match(subject="Report for 01/15/2025 - Batch 12345")
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        pattern = result.suggested_config["subject_pattern"]
        # Dates and long numbers replaced with *
        assert "*" in pattern

    def test_subject_pattern_empty(self, mock_jobs):
        email = _email_no_match(subject="")
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["subject_pattern"] == ""

    def test_sender_domain_extracted(self, mock_jobs):
        email = _email_no_match(sender="user@bigcorp.com")
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config["sender_domain"] == "bigcorp.com"

    def test_suggested_config_structure(self, mock_jobs):
        email = _email_no_match()
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        config = result.suggested_config
        assert "suggested_parser" in config
        assert "subject_pattern" in config
        assert "sender_domain" in config
        assert "attachment_types" in config

    def test_deal_repo_domain_lookup(self, mock_jobs):
        deal_repo = MagicMock()
        deal_repo.get_companies_by_sender_domain.return_value = [300, 400]
        email = _email_no_match(sender="user@bigcorp.com")
        analyzer = _make_analyzer(mock_jobs, deal_repo)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_config.get("potential_servicer_ids") == [300, 400]

    def test_deal_repo_not_provided(self, mock_jobs):
        email = _email_no_match()
        analyzer = _make_analyzer(mock_jobs, deal_repo=None)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = []
                result = analyzer.analyze_new("C:\\new.msg")
        assert "potential_servicer_ids" not in (result.suggested_config or {})

    def test_template_suggestion(self, mock_jobs):
        email = _email_no_match()
        analyzer = _make_analyzer(mock_jobs)
        template_mock = MagicMock()
        template_mock.pattern_name = "ExcelTemplate_v1"
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.return_value.discover_templates.return_value = [template_mock]
                result = analyzer.analyze_new("C:\\new.msg")
        assert result.suggested_template == "ExcelTemplate_v1"

    def test_template_discovery_fails_gracefully(self, mock_jobs):
        email = _email_no_match()
        analyzer = _make_analyzer(mock_jobs)
        with patch("backend.triage.analyzer.MsgParser") as mp:
            mp.parse.return_value = email
            with patch("backend.triage.analyzer.TemplateInventory") as ti:
                ti.side_effect = Exception("Template error")
                result = analyzer.analyze_new("C:\\new.msg")
        # Should not crash — suggested_template stays None
        assert result.suggested_template is None
