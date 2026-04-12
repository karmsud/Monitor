"""Tests for LogFileParser."""
import os

import pytest

from backend.logs.parser import LogFileParser


@pytest.fixture
def events(sample_log_path):
    """Parse the sample log file once and return all events."""
    parser = LogFileParser()
    return parser.parse_file(sample_log_path, log_type="email")


class TestLogFileParser:

    def test_parse_real_log_not_empty(self, events):
        assert len(events) > 0

    def test_all_events_have_log_file(self, events):
        assert all(e.log_file for e in events)

    def test_all_events_have_timestamp(self, events):
        assert all(e.timestamp for e in events)

    def test_job_start_detected(self, events):
        job_starts = [e for e in events if e.event_type == "job_start"]
        assert len(job_starts) >= 1

    def test_job_start_has_name(self, events):
        job_start = next(e for e in events if e.event_type == "job_start")
        assert job_start.job_name is not None and job_start.job_name != ""

    def test_job_start_has_mailbox(self, events):
        job_start = next(e for e in events if e.event_type == "job_start")
        assert job_start.mailbox is not None and job_start.mailbox != ""

    def test_found_count(self, events):
        found_events = [e for e in events if e.event_type == "found_count"]
        assert any(e.emails_found == 3 for e in found_events)

    def test_processing_subject(self, events):
        proc_events = [e for e in events if e.event_type == "processing"]
        assert any(e.subject == "January Report" for e in proc_events)

    def test_from_sender(self, events):
        from_events = [e for e in events if e.event_type == "from"]
        assert any(e.sender == "sender@partner.com" for e in from_events)

    def test_parser_match(self, events):
        match_events = [e for e in events if e.event_type == "parser_match"]
        assert any(e.parser == "ConditionalParser" for e in match_events)

    def test_file_load(self, events):
        load_events = [e for e in events if e.event_type == "file_load"]
        assert any("RPT_Jan2025.xlsx" in (e.filename or "") for e in load_events)

    def test_template_queue(self, events):
        tq_events = [e for e in events if e.event_type == "template_queue"]
        assert any(e.template == "CL_Standard" for e in tq_events)

    def test_did_failure(self, events):
        did_events = [e for e in events if e.event_type == "did_mapping_failed"]
        assert len(did_events) >= 1

    def test_error_detection(self, events):
        error_events = [e for e in events if e.event_type == "error"]
        assert len(error_events) >= 1

    def test_header_lines_skipped(self, events):
        assert not any(
            (e.raw_line or "").lstrip().startswith("##") for e in events
        )

    def test_job_context_carries(self, events):
        """Events after TestJob_Alpha job_start should have that job_name."""
        saw_alpha = False
        for e in events:
            if e.event_type == "job_start" and e.job_name == "TestJob_Alpha":
                saw_alpha = True
                continue
            if saw_alpha:
                if e.event_type == "job_start" and e.job_name != "TestJob_Alpha":
                    break  # entered next job
                assert e.job_name == "TestJob_Alpha"

    def test_empty_file(self, tmp_path):
        empty_log = tmp_path / "empty.log"
        empty_log.write_text("", encoding="utf-8")
        parser = LogFileParser()
        result = parser.parse_file(str(empty_log), log_type="email")
        assert result == []

    def test_processing_starts_distinct_email_event_groups(self, events):
        january = [e for e in events if e.subject == "January Report" and e.event_type in ("processing", "from", "parser_match", "file_load", "template_queue")]
        weekly = [e for e in events if e.subject == "Weekly Data Push"]

        assert january
        assert weekly
        assert all(e.email_event_id == january[0].email_event_id for e in january)
        assert all(e.email_event_index == 1 for e in january)
        assert all(e.email_event_id == weekly[0].email_event_id for e in weekly)
        assert all(e.email_event_index == 2 for e in weekly)
        assert january[0].email_event_id != weekly[0].email_event_id

    def test_job_start_is_not_assigned_to_email_event(self, events):
        job_start = next(e for e in events if e.event_type == "job_start")
        assert job_start.email_event_id is None
        assert job_start.email_event_index is None


# ===================================================================== #
#  SFTP log parser tests
# ===================================================================== #

@pytest.fixture
def sftp_events(sample_sftp_log_path):
    """Parse the SFTP fixture log and return all events."""
    parser = LogFileParser()
    return parser.parse_file(sample_sftp_log_path, log_type="sftp")


class TestSFTPLogParser:
    """Tests specific to SFTP monitor log format."""

    def test_sftp_events_not_empty(self, sftp_events):
        assert len(sftp_events) > 0

    def test_sftp_log_type(self, sftp_events):
        assert all(e.log_type == "sftp" for e in sftp_events)

    def test_sftp_job_start_detected(self, sftp_events):
        starts = [e for e in sftp_events if e.event_type == "job_start"]
        assert len(starts) >= 3  # TPMT_Newrez, SPS_FMSCRT, Ocwen

    def test_sftp_job_start_has_name(self, sftp_events):
        start = next(e for e in sftp_events if e.event_type == "job_start")
        assert start.job_name == "TPMT_Newrez_6616"

    def test_sftp_job_start_has_path_as_mailbox(self, sftp_events):
        start = next(e for e in sftp_events if e.event_type == "job_start")
        assert r"!Sweeps" in start.mailbox  # SFTP path stored in mailbox

    def test_sftp_found_count(self, sftp_events):
        found = [e for e in sftp_events if e.event_type == "found_count"]
        assert any(e.emails_found == 2 for e in found)
        assert any(e.emails_found == 0 for e in found)

    def test_sftp_processing_no_brackets(self, sftp_events):
        proc = [e for e in sftp_events if e.event_type == "processing"]
        assert any("xf00.newrez" in (e.subject or "") for e in proc)

    def test_sftp_parser_match_file(self, sftp_events):
        matches = [e for e in sftp_events if e.event_type == "parser_match"]
        assert any(e.parser == "MoveFile2" for e in matches)

    def test_sftp_did_match_success(self, sftp_events):
        dm = [e for e in sftp_events if e.event_type == "did_match"]
        assert len(dm) == 1
        assert dm[0].filename == "TPMT 2025-HE1"

    def test_sftp_did_mapping_failed(self, sftp_events):
        fails = [e for e in sftp_events if e.event_type == "did_mapping_failed"]
        assert len(fails) >= 1

    def test_sftp_template_queue(self, sftp_events):
        tq = [e for e in sftp_events if e.event_type == "template_queue"]
        assert any(e.template == "SFTP_Queuer_x" for e in tq)

    def test_sftp_error_detected(self, sftp_events):
        errors = [e for e in sftp_events if e.event_type == "error"]
        assert len(errors) >= 1

    def test_sftp_header_lines_skipped(self, sftp_events):
        assert not any(
            (e.raw_line or "").lstrip().startswith("##") for e in sftp_events
        )
