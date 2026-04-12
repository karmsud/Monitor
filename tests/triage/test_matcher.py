"""Tests for TriageMatcher — matching emails to configured jobs."""
import pytest
from backend.triage.matcher import TriageMatcher
from backend.triage.models import EmailInfo, MatchResult
from backend.xml.models import EmailJob


# ──────────────────────────────────────────────────────────────────────────── #
#   Fixtures
# ──────────────────────────────────────────────────────────────────────────── #

@pytest.fixture
def jobs():
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
        EmailJob(
            name="TestJob_NoFilter",
            mailbox="",
            folder="Inbox",
            sme="Team",
            filters={},
        ),
    ]


@pytest.fixture
def email_sender_match():
    return EmailInfo(
        sender="sender@acme.com",
        sender_name="ACME Sender",
        subject="Quarterly Data",
        date="2025-01-15",
    )


@pytest.fixture
def email_both_match():
    return EmailInfo(
        sender="sender@acme.com",
        sender_name="ACME Sender",
        subject="Monthly Report - January 2025",
        date="2025-01-15",
    )


@pytest.fixture
def email_subject_only():
    return EmailInfo(
        sender="unknown@elsewhere.com",
        sender_name="Unknown",
        subject="Monthly Report - February 2025",
        date="2025-02-15",
    )


@pytest.fixture
def email_no_match():
    return EmailInfo(
        sender="random@random.org",
        sender_name="Random",
        subject="Lunch Plans",
        date="2025-01-15",
    )


# ──────────────────────────────────────────────────────────────────────────── #
#   Tests
# ──────────────────────────────────────────────────────────────────────────── #

class TestTriageMatcher:

    def test_match_sender_exact(self, jobs, email_sender_match):
        results = TriageMatcher.match(email_sender_match, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_Alpha" in matched_names

    def test_match_sender_partial(self, jobs):
        email = EmailInfo(
            sender="noreply-sender@acme.com",
            sender_name="ACME",
            subject="Other",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_Alpha" in matched_names

    def test_match_subject_exact(self, jobs, email_subject_only):
        results = TriageMatcher.match(email_subject_only, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_Alpha" in matched_names

    def test_match_subject_partial(self, jobs):
        email = EmailInfo(
            sender="other@other.com",
            sender_name="Other",
            subject="Here is the Monthly Report you requested",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_Alpha" in matched_names

    def test_match_both(self, jobs, email_both_match):
        results = TriageMatcher.match(email_both_match, jobs)
        alpha_matches = [r for r in results if r.job_name == "TestJob_Alpha"]
        assert len(alpha_matches) == 1
        assert alpha_matches[0].match_type == "both"

    def test_match_mailbox_fallback(self, jobs):
        """When no sender filter matches but mailbox is in the To list."""
        email = EmailInfo(
            sender="unknown@xyz.com",
            sender_name="Unknown",
            subject="Other topic",
            date="2025-01-15",
            to=["frp.test@example.com"],
        )
        results = TriageMatcher.match(email, jobs)
        mailbox_matches = [r for r in results if r.job_name in ("TestJob_Alpha", "TestJob_Beta")]
        assert mailbox_matches
        assert all(match.match_type == "mailbox" for match in mailbox_matches)
        assert all(match.match_confidence == "exact" for match in mailbox_matches)
        assert all(match.matched_filter == "frp.test@example.com" for match in mailbox_matches)

    def test_match_mailbox_display_name_normalized(self, jobs):
        email = EmailInfo(
            sender="unknown@xyz.com",
            sender_name="Unknown",
            subject="Other topic",
            date="2025-01-15",
            to=["FRP Shared Mailbox <frp.test@example.com>"],
        )
        results = TriageMatcher.match(email, jobs)
        mailbox_matches = [r for r in results if r.job_name == "TestJob_Alpha"]
        assert len(mailbox_matches) == 1
        assert mailbox_matches[0].match_type == "mailbox"
        assert mailbox_matches[0].email_field_matched == "frp.test@example.com"

    def test_match_mailbox_found_in_cc(self, jobs):
        email = EmailInfo(
            sender="unknown@xyz.com",
            sender_name="Unknown",
            subject="Other topic",
            date="2025-01-15",
            to=["someone@elsewhere.com"],
            cc=["frp.test@example.com"],
        )
        results = TriageMatcher.match(email, jobs)
        mailbox_matches = [r for r in results if r.job_name == "TestJob_Alpha"]
        assert len(mailbox_matches) == 1
        assert mailbox_matches[0].match_type == "mailbox"
        assert mailbox_matches[0].match_confidence == "exact"
        assert mailbox_matches[0].email_field_matched == "frp.test@example.com"

    def test_exact_mailbox_outranks_partial_sender_domain(self):
        jobs = [
            EmailJob(
                name="Bayview_Additions",
                mailbox="bayview@usbank.com",
                folder="Inbox",
                sme="Team",
                filters={"From": "@usbank.com"},
                servicer_id=4000,
            ),
            EmailJob(
                name="ABS_Deals",
                mailbox="USBankGSFABSMailboxShared@usbank.com",
                folder="Inbox",
                sme="Team",
                filters={"From": "reports@vendor.com"},
            ),
        ]
        email = EmailInfo(
            sender="Phan_Alyssa@usbank.com",
            sender_name="Alyssa Phan",
            subject="Resend Fortiva 2025-Two",
            date="2026-03-11",
            to=["US Bank GSF ABS Mailbox Shared <USBankGSFABSMailboxShared@usbank.com>"],
        )

        results = TriageMatcher.match(email, jobs)
        assert [result.job_name for result in results[:2]] == ["ABS_Deals", "Bayview_Additions"]
        assert results[0].match_type == "mailbox"
        assert results[0].match_confidence == "exact"
        assert results[1].match_type == "sender"
        assert results[1].match_confidence == "partial"

    def test_no_match(self, jobs, email_no_match):
        results = TriageMatcher.match(email_no_match, jobs)
        assert results == []

    def test_multiple_matches(self, jobs):
        email = EmailInfo(
            sender="sender@acme.com",
            sender_name="ACME",
            subject="Monthly Report",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        assert len(results) >= 1

    def test_sort_order(self, jobs, email_both_match):
        results = TriageMatcher.match(email_both_match, jobs)
        if len(results) >= 2:
            assert results[0].sort_score >= results[1].sort_score

    def test_confidence_exact(self, jobs):
        email = EmailInfo(
            sender="sender@acme.com",
            sender_name="ACME",
            subject="Other",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        alpha = [r for r in results if r.job_name == "TestJob_Alpha"]
        assert len(alpha) == 1
        assert alpha[0].match_confidence == "exact"

    def test_confidence_partial(self, jobs):
        email = EmailInfo(
            sender="person-sender@acme.com-extra",
            sender_name="ACME",
            subject="Other",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        alpha = [r for r in results if r.job_name == "TestJob_Alpha"]
        if alpha:
            assert alpha[0].match_confidence == "partial"

    def test_empty_jobs_list(self):
        email = EmailInfo(
            sender="x@x.com", sender_name="X", subject="Y", date="2025-01-15",
        )
        results = TriageMatcher.match(email, [])
        assert results == []

    def test_xml_type_filter(self, jobs):
        email = EmailInfo(
            sender="sender@acme.com", sender_name="ACME",
            subject="Monthly Report", date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs, xml_type="sftp")
        # All test jobs are xml_type="email", so sftp should match none
        assert results == []

    def test_case_insensitive(self, jobs):
        email = EmailInfo(
            sender="SENDER@ACME.COM",
            sender_name="ACME",
            subject="monthly report",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_Alpha" in matched_names

    def test_servicer_id_in_result(self, jobs, email_sender_match):
        results = TriageMatcher.match(email_sender_match, jobs)
        alpha = [r for r in results if r.job_name == "TestJob_Alpha"]
        assert len(alpha) == 1
        assert alpha[0].servicer_id == "150"

    def test_no_filter_job_skipped(self, jobs, email_no_match):
        results = TriageMatcher.match(email_no_match, jobs)
        matched_names = [r.job_name for r in results]
        assert "TestJob_NoFilter" not in matched_names

    def test_filter_key_variations(self):
        """Jobs with 'sender' or 'senderfilter' keys should also match."""
        job = EmailJob(
            name="VariantJob",
            mailbox="",
            folder="Inbox",
            sme="Team",
            filters={"senderfilter": "variant@test.com"},
        )
        email = EmailInfo(
            sender="variant@test.com",
            sender_name="V",
            subject="X",
            date="2025-01-15",
        )
        results = TriageMatcher.match(email, [job])
        assert len(results) == 1
        assert results[0].job_name == "VariantJob"

    def test_match_result_fields(self, jobs, email_both_match):
        results = TriageMatcher.match(email_both_match, jobs)
        alpha = [r for r in results if r.job_name == "TestJob_Alpha"][0]
        assert alpha.xml_type == "email"
        assert alpha.match_type in ("mailbox", "sender", "subject", "both")
        assert alpha.match_confidence in ("exact", "partial")
        assert alpha.matched_filter != ""
        assert alpha.email_field_matched != ""
