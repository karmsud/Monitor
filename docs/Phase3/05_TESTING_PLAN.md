# Phase 3: Testing Plan
## FRP Agent — Log Analytics & Email Triage Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Total Tests:** 133 automated + 12 manual = 145 tests  
**Target Coverage:** ≥90% for Phase 3 modules

---

## Table of Contents
1. [Test Strategy](#1-test-strategy)
2. [Test Infrastructure](#2-test-infrastructure)
3. [Log Models Tests](#3-log-models-tests)
4. [Log Analytics Tests](#4-log-analytics-tests)
5. [Triage Models Tests](#5-triage-models-tests)
6. [Msg Parser Tests](#6-msg-parser-tests)
7. [Triage Matcher Tests](#7-triage-matcher-tests)
8. [Triage Analyzer Tests](#8-triage-analyzer-tests)
9. [DB Repository Tests](#9-db-repository-tests)
10. [CLI Command Tests](#10-cli-command-tests)
11. [Extension Manual QA](#11-extension-manual-qa)
12. [End-to-End Scenarios](#12-end-to-end-scenarios)
13. [Coverage Targets](#13-coverage-targets)

---

## 1. Test Strategy

| Layer | Framework | Approach | Target |
|-------|-----------|----------|--------|
| Data Models | pytest | Direct construction + serialization | 100% |
| Log Analytics | pytest | In-memory SQLite with fixtures | 95% |
| Msg Parser | pytest | Mock .msg files via extract-msg mock | 90% |
| Triage Matcher | pytest | Mock jobs + EmailInfo fixtures | 95% |
| Triage Analyzer | pytest | Mock all dependencies | 90% |
| CLI Commands | pytest | Subprocess JSON validation | 90% |
| Extension JS | Manual F5 | Extension Development Host | Checklist |

### Key Testing Principles

1. **SQLite test database in conftest** — Pre-populated in-memory DB for all log analytics tests
2. **Mock extract-msg** — Unit tests don't require real .msg files; mock the Message class
3. **Real .msg file for integration** — At least 1 real .msg in test fixtures for smoke test
4. **Filter matching coverage** — Test exact, partial, sender-only, subject-only, both, and no-match cases
5. **Privacy check** — Verify `to_safe_dict()` excludes body and full email addresses

---

## 2. Test Infrastructure

### conftest.py Additions

```python
# tests/conftest.py — Phase 3 additions

import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from backend.logs.models import DealActivity, DIDFailure, JobHealth, DailySummary
from backend.triage.models import EmailInfo, MatchResult, TriageResult


@pytest.fixture
def log_db(tmp_path):
    """Create an in-memory SQLite log database with test data."""
    db_path = str(tmp_path / "test_frp_logs.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_file TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            job_name TEXT,
            event_type TEXT NOT NULL,
            detail TEXT,
            extra TEXT
        );
        CREATE TABLE log_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            file_path TEXT NOT NULL,
            parsed_at TEXT NOT NULL,
            event_count INTEGER
        );
        CREATE TABLE sync_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE INDEX idx_events_type_ts ON log_events(event_type, timestamp);
        CREATE INDEX idx_events_job ON log_events(job_name);

        INSERT INTO sync_meta (key, value) VALUES ('last_sync', datetime('now'));

        INSERT INTO log_files (filename, file_path, parsed_at, event_count)
        VALUES ('test1.log', '/logs/test1.log', datetime('now'), 10);

        -- Sample events for "CSMC 2015-1 rptent" job
        INSERT INTO log_events (log_file, timestamp, job_name, event_type, detail)
        VALUES
            ('test1.log', datetime('now', '-1 hour'), 'CSMC 2015-1 rptent', 'job_start', 'Starting job'),
            ('test1.log', datetime('now', '-1 hour'), 'CSMC 2015-1 rptent', 'email_processed', 'Subject: CSMC Monthly Report'),
            ('test1.log', datetime('now', '-1 hour'), 'CSMC 2015-1 rptent', 'email_processed', 'Subject: CSMC Q4 Report'),
            ('test1.log', datetime('now', '-2 hours'), 'CSMC 2015-1 rptent', 'job_start', 'Starting job'),
            ('test1.log', datetime('now', '-2 hours'), 'CSMC 2015-1 rptent', 'email_processed', 'Subject: CSMC Data File'),

            -- Error event
            ('test1.log', datetime('now', '-3 hours'), 'bonds mailbox', 'error', 'Connection timeout'),
            ('test1.log', datetime('now', '-3 hours'), 'bonds mailbox', 'job_start', 'Starting job'),

            -- DID mapping failures
            ('test1.log', datetime('now', '-1 hour'), 'rptent mailbox', 'did_mapping_failure', 'Did not find DID mapping for [UNKNKW1]'),
            ('test1.log', datetime('now', '-2 hours'), 'rptent mailbox', 'did_mapping_failure', 'Did not find DID mapping for [UNKNKW1]'),
            ('test1.log', datetime('now', '-1 hour'), 'bonds mailbox', 'did_mapping_failure', 'Did not find DID mapping for [RNDKW2]');
    """)
    conn.close()
    return db_path


@pytest.fixture
def sample_email_info():
    """Sample parsed email for triage testing."""
    return EmailInfo(
        sender="reports@csmc.com",
        sender_name="CSMC Reports",
        subject="CSMC 2015-1 Monthly Report February 2026",
        date="2026-02-24T10:00:00",
        to=["rptent@bank.com"],
        cc=[],
        body_preview="Please find attached the monthly report...",
        attachment_names=["CSMC_Monthly_Feb2026.csv"],
        file_path="C:\\inbox\\test.msg",
    )


@pytest.fixture
def sample_email_no_match():
    """Email that should NOT match any existing job."""
    return EmailInfo(
        sender="unknown@newcorp.com",
        sender_name="NewCorp Servicing",
        subject="NewCorp Deal Report Q1 2026",
        date="2026-02-24T10:00:00",
        to=["rptent@bank.com"],
        cc=[],
        body_preview="New servicing report attached.",
        attachment_names=["NewCorp_Q1.xlsx"],
        file_path="C:\\inbox\\new.msg",
    )


@pytest.fixture
def mock_jobs():
    """Mock job objects with filter attributes for matcher tests."""
    class MockParser:
        def __init__(self, sender="", subject=""):
            self.SenderFilter = sender
            self.SubjectFilter = subject
    
    class MockJob:
        def __init__(self, name, servicer_id, parsers):
            self.name = name
            self.servicer_id = servicer_id
            self.parsers = parsers
    
    return [
        MockJob("CSMC 2015-1 rptent", "150", [
            MockParser(sender="reports@csmc.com", subject="CSMC 2015"),
        ]),
        MockJob("XYZ Bonds", "200", [
            MockParser(sender="bonds@xyz.com", subject="XYZ Bond"),
        ]),
        MockJob("General Shelf", None, [
            MockParser(sender="", subject="Monthly Statement"),
        ]),
    ]
```

### Test File Organization

```
tests/
├── conftest.py                        # Updated with Phase 3 fixtures
├── logs/
│   ├── __init__.py
│   ├── test_log_models.py            # 12 tests
│   └── test_analytics.py             # 32 tests
├── triage/
│   ├── __init__.py
│   ├── test_triage_models.py         # 15 tests
│   ├── test_msg_parser.py            # 14 tests
│   ├── test_matcher.py               # 18 tests
│   ├── test_analyzer_verify.py       # 10 tests (E-01)
│   ├── test_analyzer_match.py        # 6 tests (E-02)
│   └── test_analyzer_new.py          # 16 tests (E-03)
├── db/
│   └── test_deal_repo_p3.py          # 8 tests
└── cli/
    └── test_main_p3.py               # 14 tests (was 2 tests for Phase 1)
```

---

## 3. Log Models Tests

### tests/logs/test_log_models.py — 12 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_deal_activity_serialization | DealActivity with all fields | to_dict() complete | P1 |
| 2 | test_deal_activity_defaults | Minimal DealActivity | All fields present | P1 |
| 3 | test_did_failure_serialization | DIDFailure | to_dict() matches | P1 |
| 4 | test_did_failure_list_in_dict | DIDFailure with 3 jobs | affected_jobs is list | P1 |
| 5 | test_job_health_serialization | JobHealth with all metrics | to_dict() complete | P1 |
| 6 | test_job_health_status_healthy | success_rate=99.0 | status="healthy" | P1 |
| 7 | test_job_health_status_warning | success_rate=85.0 | status="warning" | P1 |
| 8 | test_job_health_status_critical | success_rate=50.0 | status="critical" | P1 |
| 9 | test_daily_summary_serialization | DailySummary | to_dict() complete | P1 |
| 10 | test_daily_summary_no_comparison | comparison=None | comparison is None | P1 |
| 11 | test_daily_summary_with_comparison | With delta dict | comparison populated | P2 |
| 12 | test_daily_summary_empty_lists | No top jobs/errors | Empty lists in dict | P2 |

---

## 4. Log Analytics Tests

### tests/logs/test_analytics.py — 32 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_init_valid_db | Valid log_db path | No error | P1 |
| 2 | test_init_missing_db | Non-existent path | FileNotFoundError | P1 |
| 3 | test_init_missing_tables | DB without log_events | ValueError | P1 |
| 4 | test_staleness_fresh | last_sync = now | None (no warning) | P1 |
| 5 | test_staleness_stale | last_sync = 36h ago | Warning dict | P1 |
| 6 | test_staleness_never_synced | No sync_meta entry | Warning dict | P1 |
| 7 | test_deal_activity_found | Known DID keyword | Events returned | P1 |
| 8 | test_deal_activity_empty | Unknown keyword | Empty list | P1 |
| 9 | test_deal_activity_date_range | days=1 | Only recent events | P1 |
| 10 | test_deal_activity_sort_order | Multiple events | Newest first | P1 |
| 11 | test_deal_activity_pre_resolved | import_did provided | Uses that keyword | P2 |
| 12 | test_did_failures_aggregated | 2 unique failures | 2 DIDFailure entries | P1 |
| 13 | test_did_failures_count_correct | UNKNKW1 appears 2x | failure_count=2 | P1 |
| 14 | test_did_failures_sorted_by_count | Mixed counts | Highest first | P1 |
| 15 | test_did_failures_affected_jobs | UNKNKW1 in rptent | affected_jobs has "rptent mailbox" | P1 |
| 16 | test_did_failures_date_filter | days=0.01 | Only very recent | P2 |
| 17 | test_did_failures_job_filter | job_filter="rptent" | Only rptent failures | P2 |
| 18 | test_did_failures_keyword_extraction | Full detail string | ImportDID extracted | P1 |
| 19 | test_job_health_exact_match | Exact job name | Correct job metrics | P1 |
| 20 | test_job_health_fuzzy_match | Partial name "rptent" | Single match resolves | P2 |
| 21 | test_job_health_ambiguous | Multiple matches | ValueError with list | P1 |
| 22 | test_job_health_not_found | Unknown job name | ValueError | P1 |
| 23 | test_job_health_success_rate | 2 runs, 0 errors | 100.0 success rate | P1 |
| 24 | test_job_health_error_rate | 1 error run | Rate < 100 | P1 |
| 25 | test_job_health_common_errors | Known errors | Common errors populated | P2 |
| 26 | test_job_health_avg_emails | 3 emails, 2 runs | avg=1.5 | P2 |
| 27 | test_daily_summary_counts | Known date with data | Correct totals | P1 |
| 28 | test_daily_summary_top_jobs | Multiple jobs | Top 5 sorted | P1 |
| 29 | test_daily_summary_comparison | Prev day has data | Delta computed | P2 |
| 30 | test_daily_summary_no_prev_data | No prev day events | comparison=None | P2 |
| 31 | test_daily_summary_default_today | No date arg | Uses today | P2 |
| 32 | test_daily_summary_specific_date | Date="2026-02-20" | That date's data | P1 |

---

## 5. Triage Models Tests

### tests/triage/test_triage_models.py — 15 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_email_info_serialization | Full EmailInfo | to_dict() complete | P1 |
| 2 | test_email_info_safe_dict | Full EmailInfo | No body, no full address | P1 |
| 3 | test_email_info_safe_dict_no_domain | sender="" | sender_domain="" | P2 |
| 4 | test_email_info_defaults | Minimal EmailInfo | Empty lists default | P1 |
| 5 | test_match_result_serialization | Full MatchResult | to_dict() complete | P1 |
| 6 | test_match_result_sort_score_both | match_type="both", exact | Score = 32 | P1 |
| 7 | test_match_result_sort_score_sender | match_type="sender", partial | Score = 21 | P1 |
| 8 | test_match_result_sort_score_subject | match_type="subject", exact | Score = 12 | P2 |
| 9 | test_triage_result_serialization | Full TriageResult | to_dict() complete | P1 |
| 10 | test_triage_result_no_matches | Empty matches | has_match=False | P1 |
| 11 | test_triage_result_with_matches | 2 matches | has_match=True | P1 |
| 12 | test_triage_result_coverage_status | "covered" | Field serialized | P1 |
| 13 | test_triage_result_suggested_template | "MailToFolder" | In to_dict() | P2 |
| 14 | test_triage_result_suggested_config | Dict with fields | Serialized correctly | P2 |
| 15 | test_email_info_attachment_count | 3 attachments | to_safe_dict() has count=3 | P1 |

---

## 6. Msg Parser Tests

### tests/triage/test_msg_parser.py — 14 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_parse_valid_msg | Mock .msg with all fields | EmailInfo populated | P1 |
| 2 | test_parse_sender | Mock .msg | sender matches | P1 |
| 3 | test_parse_subject | Mock .msg | subject matches | P1 |
| 4 | test_parse_date | Mock .msg with datetime | ISO date string | P1 |
| 5 | test_parse_recipients_to | Mock .msg with 2 To | to list has 2 | P1 |
| 6 | test_parse_recipients_cc | Mock .msg with CC | cc list populated | P2 |
| 7 | test_parse_body_truncated | Mock .msg with 1000-char body | body_preview ≤ 500 chars | P1 |
| 8 | test_parse_attachments | Mock .msg with 3 attachments | 3 names in list | P1 |
| 9 | test_parse_no_attachments | Mock .msg, no attachments | Empty list | P2 |
| 10 | test_file_not_found | Non-existent path | FileNotFoundError | P1 |
| 11 | test_wrong_extension | ".txt" file | ValueError | P1 |
| 12 | test_corrupted_msg | Mock raises parse error | RuntimeError | P2 |
| 13 | test_empty_fields | Mock .msg all empty | Empty strings, no crash | P2 |
| 14 | test_msg_handle_closed | After parse | No resource leak | P2 |

---

## 7. Triage Matcher Tests

### tests/triage/test_matcher.py — 18 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_match_sender_exact | Email sender matches filter | match_type="sender", confidence="exact" | P1 |
| 2 | test_match_sender_partial | Sender filter is substring | match_type="sender", confidence="partial" | P1 |
| 3 | test_match_subject_exact | Subject matches filter | match_type="subject" | P1 |
| 4 | test_match_subject_partial | Subject filter is substring | confidence="partial" | P1 |
| 5 | test_match_both | Sender + subject match | match_type="both" | P1 |
| 6 | test_no_match | No filters match | Empty result list | P1 |
| 7 | test_case_insensitive_sender | "REPORTS@csmc.com" vs "reports@csmc.com" | Match found | P1 |
| 8 | test_case_insensitive_subject | Mixed case subject | Match found | P1 |
| 9 | test_multiple_jobs_match | Email matches 2 jobs | 2 MatchResults | P1 |
| 10 | test_sorted_by_score | both > sender > subject | Best match first | P1 |
| 11 | test_servicer_id_populated | Job has servicer_id | In MatchResult | P1 |
| 12 | test_servicer_id_none | Job without ServicerID | servicer_id=None | P2 |
| 13 | test_filter_extraction_from_parsers | Job with nested parsers | Filters extracted | P1 |
| 14 | test_filter_extraction_no_parsers | Job without parsers | Empty filter list | P2 |
| 15 | test_filter_extraction_dict_format | Parser as dict | Filters extracted | P2 |
| 16 | test_empty_filter_skipped | Empty SenderFilter | Not matched | P2 |
| 17 | test_sender_name_match | SenderFilter matches sender_name | Match found | P2 |
| 18 | test_matched_filter_in_result | Known filter value | matched_filter populated | P1 |

---

## 8. Triage Analyzer Tests

### tests/triage/test_analyzer_verify.py — 10 tests (E-01)

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_verify_match_found | Known matching email | has_match=True | P1 |
| 2 | test_verify_no_match | Unknown email | has_match=False | P1 |
| 3 | test_verify_coverage_checked | Match + DB available | coverage_status set | P1 |
| 4 | test_verify_coverage_covered | ServicerID has deals | coverage_status="covered" | P1 |
| 5 | test_verify_coverage_partial | ServicerID 0 deals | coverage_status="partial" | P2 |
| 6 | test_verify_no_db | DB unavailable | coverage_status=None | P1 |
| 7 | test_verify_recommendation_match | Match found | "matches job 'X'" in recommendation | P1 |
| 8 | test_verify_recommendation_no_match | No match | "No existing job" in recommendation | P1 |
| 9 | test_verify_did_count | Match + DB | did_count populated | P2 |
| 10 | test_verify_top_match | Multiple matches | Top match used for coverage | P2 |

### tests/triage/test_analyzer_match.py — 6 tests (E-02)

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_match_from_msg | .msg file path | Matches returned | P1 |
| 2 | test_match_from_manual | sender+subject strings | Matches returned | P1 |
| 3 | test_match_no_results | Unknown sender/subject | Empty matches | P1 |
| 4 | test_match_recommendation | Matches found | Recommendation text set | P2 |
| 5 | test_match_no_db_required | No DB provided | Still works | P1 |
| 6 | test_match_manual_empty_fields | sender="", subject="" | Empty matches, no crash | P2 |

### tests/triage/test_analyzer_new.py — 16 tests (E-03)

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_new_no_match_confirmed | Unknown email | has_match=False | P1 |
| 2 | test_new_suggested_template | Email with .csv attachment | "MailToParser" template | P1 |
| 3 | test_new_suggested_template_pdf | Email with .pdf | "MailToFolder" template | P2 |
| 4 | test_new_suggested_template_no_att | No attachments | "MailToFolder" default | P2 |
| 5 | test_new_suggested_config | Any no-match email | Config dict has mailbox, subject_filter, sender_filter | P1 |
| 6 | test_new_subject_pattern_extracted | "Report Feb 2026" | Date stripped from pattern | P1 |
| 7 | test_new_subject_pattern_no_dates | "Annual Report" | Pattern unchanged | P2 |
| 8 | test_new_coverage_status | DB available | "no_coverage" set | P2 |
| 9 | test_new_recommendation | No match | "No matching job found" | P1 |
| 10 | test_new_recommendation_template | Has suggestion | Template name in recommendation | P1 |
| 11 | test_new_db_unavailable | No DB | Still returns result | P1 |
| 12 | test_new_msg_not_found | Bad path | FileNotFoundError propagated | P1 |
| 13 | test_guess_parser_csv | .csv attachment | "MailToParser" | P1 |
| 14 | test_guess_parser_xlsx | .xlsx attachment | "MailToParser" | P2 |
| 15 | test_guess_parser_mixed | .csv + .pdf | "MailToParser" (first match) | P2 |
| 16 | test_guess_parser_unknown_ext | .xyz attachment | "MailToFolder" default | P2 |

---

## 9. DB Repository Tests

### tests/db/test_deal_repo_p3.py — 8 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_resolve_did_by_number | DID=1001 | ImportDID returned | P1 |
| 2 | test_resolve_did_by_name_exact | "CSMC" | "CSMC" returned | P1 |
| 3 | test_resolve_did_by_name_partial | "CSM" unique match | "CSMC" returned | P2 |
| 4 | test_resolve_did_not_found | Unknown identifier | None returned | P1 |
| 5 | test_resolve_did_ambiguous_partial | "C" matches 2+ | None returned | P2 |
| 6 | test_companies_by_domain | "csmc.com" | [150] | P2 |
| 7 | test_companies_by_domain_no_match | "unknown.com" | [] | P2 |
| 8 | test_companies_by_domain_multiple | Overlapping prefix | Multiple CompanyIDs | P2 |

---

## 10. CLI Command Tests

### tests/cli/test_main_p3.py — 14 tests

| # | Test Name | Command | Expected | P |
|---|-----------|---------|----------|---|
| 1 | test_log_deal_activity_success | log_deal_activity --did CSMC | success=true, events list | P1 |
| 2 | test_log_deal_activity_no_results | log_deal_activity --did ZZZZZ | success=true, events=[] | P1 |
| 3 | test_log_did_failures_success | log_did_failures | success=true, failures list | P1 |
| 4 | test_log_did_failures_with_days | log_did_failures --days 7 | Date range matches | P2 |
| 5 | test_log_job_health_success | log_job_health --job-name "CSMC 2015-1 rptent" | success=true, health data | P1 |
| 6 | test_log_job_health_not_found | log_job_health --job-name "nope" | success=false | P1 |
| 7 | test_log_daily_summary_success | log_daily_summary | success=true, summary | P1 |
| 8 | test_log_daily_summary_date | log_daily_summary --date 2026-02-24 | Correct date | P2 |
| 9 | test_triage_verify_success | triage_verify --msg-path X --settings-path Y | success=true | P1 |
| 10 | test_triage_verify_file_not_found | triage_verify --msg-path "nope.msg" | success=false | P1 |
| 11 | test_triage_match_success | triage_match --sender "test@x.com" | success=true | P1 |
| 12 | test_triage_new_success | triage_new --msg-path X --settings-path Y | success=true, suggested_template | P1 |
| 13 | test_staleness_warning_included | Stale DB + any log command | response has warning field | P1 |
| 14 | test_all_commands_return_json | All Phase 3 commands | Valid JSON with success field | P1 |

---

## 11. Extension Manual QA

### F5 Extension Dev Host Checklist — 12 items

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | /logs deal | `@frp /logs deal CSMC` | Timeline of events shown |
| 2 | /logs deal unknown | `@frp /logs deal ZZZZNOTHING` | "No events found" message |
| 3 | /logs failures | `@frp /logs failures` | Failure summary table |
| 4 | /logs health | `@frp /logs health rptent` | Health dashboard with status indicator |
| 5 | /logs health ambiguous | `@frp /logs health mail` | Disambiguation prompt |
| 6 | /logs summary | `@frp /logs summary` | Daily operations dashboard |
| 7 | /logs stale warning | Set sync >24h ago, run /logs summary | Warning shown before results |
| 8 | /triage verify | `@frp /triage verify path_to.msg` | Match + coverage result |
| 9 | /triage verify no match | `@frp /triage verify unknown.msg` | "No matching job" + suggest /triage new |
| 10 | /triage match | `@frp /triage match --sender "test@bank.com"` | Ranked match list |
| 11 | /triage new | `@frp /triage new new_request.msg` | Template suggestion + config |
| 12 | Follow-ups | After any triage command | Relevant follow-up buttons shown |

---

## 12. End-to-End Scenarios

### E2E-P3-1: Log Investigation Pipeline

```
1. @frp /logs summary                    → See today's dashboard
2. @frp /logs failures                   → Top DID mapping failures
3. @frp /logs deal UNKNKW1              → Events for failing keyword
4. @frp /logs health rptent             → Health check on affected job
5. @frp /deals gaps all                  → (Phase 2) Coverage gap link
```

### E2E-P3-2: Email Triage — Existing Coverage

```
1. @frp /triage verify inbox/csmc_report.msg
   → "Email matches job 'CSMC 2015-1 rptent'. 3 DIDs covered."
2. @frp /logs health "CSMC 2015-1 rptent"
   → Job health: 98.3% success rate
3. @frp /deals servicer 150
   → (Phase 1) Full servicer dossier
```

### E2E-P3-3: Email Triage — New Request

```
1. @frp /triage verify inbox/new_servicer.msg
   → "No existing job matches this email."
2. @frp /triage new inbox/new_servicer.msg
   → "Suggested template: MailToFolder — rptent"
   → Suggested config: mailbox, subject_filter, sender_filter
3. @frp /jobs create rptent from "CSMC 2015-1 rptent"
   → (Phase 2) Create new job
4. @frp /jobs validate
   → (Phase 1) Validate with new job
```

### E2E-P3-4: Job Health Monitoring Loop

```
1. @frp /logs summary 2026-02-24         → Check specific day
2. @frp /logs summary 2026-02-23         → Compare with previous
3. @frp /logs health "bonds mailbox"     → Investigate error source
4. @frp /logs deal "CSFB 2006-HEAT5"    → Check specific deal
```

---

## 13. Coverage Targets

| Module | File | Target | Tests |
|--------|------|--------|-------|
| Log Models | `logs/models.py` | 100% | 12 |
| Log Analytics | `logs/analytics.py` | 95% | 32 |
| Triage Models | `triage/models.py` | 100% | 15 |
| Msg Parser | `triage/msg_parser.py` | 90% | 14 |
| Triage Matcher | `triage/matcher.py` | 95% | 18 |
| Analyzer (E-01) | `triage/analyzer.py` verify | 90% | 10 |
| Analyzer (E-02) | `triage/analyzer.py` match | 90% | 6 |
| Analyzer (E-03) | `triage/analyzer.py` new | 90% | 16 |
| DB Repository (P3) | `deal_repo.py` additions | 90% | 8 |
| CLI (Phase 3) | `cli/main.py` additions | 90% | 14 |
| **Total Automated** | | **≥90% avg** | **133** |
| Extension (Manual) | participant.js | Checklist | 12 |
| **Grand Total** | | | **145** |

### Execution Time

| Category | Tests | Time |
|----------|-------|------|
| Unit tests (models) | 27 | ~2 min |
| Log analytics (SQLite) | 32 | ~3 min |
| Triage (mock deps) | 50 | ~4 min |
| DB repository | 8 | ~2 min |
| CLI integration | 14 | ~3 min |
| Manual QA | 12 | ~15 min |
| E2E scenarios | 4 | ~10 min |
| **Total** | **145** | **~39 min** |

---

*End of Phase 3 documentation.*
