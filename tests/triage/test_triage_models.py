"""Tests for Phase 3 triage dataclass models."""
import pytest
from backend.triage.models import EmailInfo, MatchResult, TriageResult


# ──────────────────────────────────────────────────────────────────────────── #
#   EmailInfo
# ──────────────────────────────────────────────────────────────────────────── #

class TestEmailInfo:

    def test_creation(self):
        ei = EmailInfo(
            sender="test@example.com",
            sender_name="Test User",
            subject="Hello World",
            date="2025-01-15T10:00:00",
            to=["recipient@example.com"],
            cc=["cc@example.com"],
            body_preview="Body text",
            attachment_names=["file.xlsx"],
            file_path="C:\\emails\\test.msg",
        )
        assert ei.sender == "test@example.com"
        assert ei.sender_name == "Test User"
        assert ei.subject == "Hello World"
        assert ei.attachment_names == ["file.xlsx"]

    def test_to_dict(self):
        ei = EmailInfo(
            sender="test@example.com",
            sender_name="Test",
            subject="Sub",
            date="2025-01-15",
        )
        d = ei.to_dict()
        assert isinstance(d, dict)
        assert d["sender"] == "test@example.com"
        assert d["subject"] == "Sub"
        assert "to" in d
        assert "cc" in d

    def test_to_safe_dict_omits_sender(self):
        ei = EmailInfo(
            sender="secret@acme.com",
            sender_name="ACME",
            subject="Report",
            date="2025-01-15",
            attachment_names=["a.xlsx", "b.pdf"],
        )
        sd = ei.to_safe_dict()
        # Must not expose the full sender address
        assert "secret@acme.com" not in str(sd)
        assert sd["sender_domain"] == "acme.com"
        assert sd["sender_name"] == "ACME"
        assert sd["attachment_count"] == 2

    def test_to_safe_dict_no_at_sign(self):
        ei = EmailInfo(
            sender="localuser",
            sender_name="Local",
            subject="X",
            date="2025-01-15",
        )
        sd = ei.to_safe_dict()
        assert sd["sender_domain"] == ""


# ──────────────────────────────────────────────────────────────────────────── #
#   MatchResult
# ──────────────────────────────────────────────────────────────────────────── #

class TestMatchResult:

    def test_creation(self):
        mr = MatchResult(
            job_name="TestJob",
            xml_type="email",
            match_type="sender",
            match_confidence="exact",
            servicer_id="150",
            matched_filter="sender@acme.com",
            email_field_matched="sender@acme.com",
        )
        assert mr.job_name == "TestJob"
        assert mr.match_type == "sender"

    def test_to_dict(self):
        mr = MatchResult(
            job_name="TestJob",
            xml_type="email",
            match_type="both",
            match_confidence="exact",
            servicer_id="150",
            matched_filter="x",
            email_field_matched="y",
        )
        d = mr.to_dict()
        assert isinstance(d, dict)
        assert d["match_type"] == "both"

    def test_sort_score_both_exact(self):
        mr = MatchResult(
            job_name="X", xml_type="email", match_type="both",
            match_confidence="exact", servicer_id=None,
            matched_filter="", email_field_matched="",
        )
        assert mr.sort_score == 42  # 4*10 + 2

    def test_sort_score_both_partial(self):
        mr = MatchResult(
            job_name="X", xml_type="email", match_type="both",
            match_confidence="partial", servicer_id=None,
            matched_filter="", email_field_matched="",
        )
        assert mr.sort_score == 41  # 4*10 + 1

    def test_sort_score_mailbox_exact(self):
        mr = MatchResult(
            job_name="X", xml_type="email", match_type="mailbox",
            match_confidence="exact", servicer_id=None,
            matched_filter="", email_field_matched="",
        )
        assert mr.sort_score == 32  # 3*10 + 2

    def test_sort_score_sender_exact(self):
        mr = MatchResult(
            job_name="X", xml_type="email", match_type="sender",
            match_confidence="exact", servicer_id=None,
            matched_filter="", email_field_matched="",
        )
        assert mr.sort_score == 22  # 2*10 + 2

    def test_sort_score_subject_partial(self):
        mr = MatchResult(
            job_name="X", xml_type="email", match_type="subject",
            match_confidence="partial", servicer_id=None,
            matched_filter="", email_field_matched="",
        )
        assert mr.sort_score == 11  # 1*10 + 1


# ──────────────────────────────────────────────────────────────────────────── #
#   TriageResult
# ──────────────────────────────────────────────────────────────────────────── #

class TestTriageResult:

    def test_creation(self):
        ei = EmailInfo(
            sender="s@x.com", sender_name="S", subject="Sub", date="2025-01-15",
        )
        tr = TriageResult(email_info=ei, has_match=False)
        assert tr.email_info is ei
        assert tr.has_match is False
        assert tr.matches == []

    def test_to_dict_nested(self):
        ei = EmailInfo(
            sender="s@x.com", sender_name="S", subject="Sub", date="2025-01-15",
        )
        mr = MatchResult(
            job_name="Job1", xml_type="email", match_type="sender",
            match_confidence="exact", servicer_id="150",
            matched_filter="s@x.com", email_field_matched="s@x.com",
        )
        tr = TriageResult(email_info=ei, matches=[mr], has_match=True)
        d = tr.to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["email_info"], dict)
        assert isinstance(d["matches"], list)
        assert len(d["matches"]) == 1
        assert d["matches"][0]["job_name"] == "Job1"

    def test_has_match_flag(self):
        ei = EmailInfo(
            sender="s@x.com", sender_name="S", subject="Sub", date="2025-01-15",
        )
        tr_match = TriageResult(email_info=ei, has_match=True)
        tr_no = TriageResult(email_info=ei, has_match=False)
        assert tr_match.has_match is True
        assert tr_no.has_match is False

    def test_default_optional_fields(self):
        ei = EmailInfo(
            sender="s@x.com", sender_name="S", subject="Sub", date="2025-01-15",
        )
        tr = TriageResult(email_info=ei)
        assert tr.coverage_status is None
        assert tr.did_count is None
        assert tr.suggested_template is None
        assert tr.suggested_config is None
        assert tr.recommendation == ""
