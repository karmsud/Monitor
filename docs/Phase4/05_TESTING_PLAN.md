# Phase 4: Testing Plan
## FRP Agent — Advanced Analysis Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Total Tests:** 125 (117 automated + 8 manual)  
**Coverage Target:** ≥ 90% line coverage for `backend/analysis/`  

---

## Table of Contents
1. [Test Architecture](#1-test-architecture)
2. [Conftest Additions](#2-conftest-additions)
3. [Unit Tests by Module](#3-unit-tests-by-module)
4. [CLI Integration Tests](#4-cli-integration-tests)
5. [Extension Handler Tests](#5-extension-handler-tests)
6. [Manual QA Checklist](#6-manual-qa-checklist)
7. [End-to-End Scenarios](#7-end-to-end-scenarios)
8. [Coverage Targets](#8-coverage-targets)
9. [Test Execution Order](#9-test-execution-order)

---

## 1. Test Architecture

```
tests/
  analysis/
    __init__.py
    conftest.py              ← Phase 4 shared fixtures
    test_analysis_models.py  ← 25 tests
    test_trends.py           ← 18 tests
    test_performance.py      ← 18 tests
    test_consolidation.py    ← 16 tests
    test_impact.py           ← 22 tests
    test_health.py           ← 18 tests
  cli/
    test_main_p4.py          ← 10 CLI tests (Phase 4 commands)
  extension/
    test_analyze_handler.js  ← 10 handler tests (Jest)
                             ─────────────────
                             Total: 137 tests
```

> **Note:** Final count is 127 automated + 10 extension-side = 137. The
> 125 estimate in the Technical Design was conservative; the breakdown
> below adds 12 tests during detailed planning.

### Test Principles

1. **Every analyzer gets its own fixture set** — No shared mutable state between tests.
2. **SQLite in-memory** — TrendAnalyzer and PerformanceBenchmarker tests use `:memory:` SQLite databases populated in fixtures.
3. **Mock external dependencies** — DB connections (MySQL/MSSQL), file system reads, and Phase 1–3 classes are mocked.
4. **Deterministic dates** — All tests use `freezegun` or hardcoded date ranges. Never use `datetime.now()` in assertions.
5. **Snapshot testing for health reports** — HealthChecker output is compared against golden JSON snapshots.

---

## 2. Conftest Additions

### `tests/analysis/conftest.py`

```python
"""Phase 4 shared fixtures."""
import sqlite3
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock
from backend.analysis.models import (
    TrendDay, TrendSummary,
    PerformanceEntry, PerformanceSummary,
    ConsolidationCandidate, ConsolidationGroup, ConsolidationReport,
    ChangeSpec, AffectedEntity, ImpactReport,
    HealthSection, HealthReport,
)


# ── SQLite Fixtures (for TrendAnalyzer / PerformanceBenchmarker) ─────────

@pytest.fixture
def analysis_db():
    """In-memory SQLite with 10 jobs × 14 days of realistic data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY,
            job_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            details TEXT,
            file_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE log_files (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            service_type TEXT,
            last_modified TEXT,
            indexed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_events_job_date ON log_events(job_name, event_date)")
    conn.execute("CREATE INDEX idx_events_type ON log_events(event_type)")

    jobs = [
        "Ocwen", "PHH", "Shellpoint", "BSI", "LoanCare",
        "Cenlar", "SPS", "FlagStar", "Chase", "WellsFargo",
    ]
    base_date = date(2025, 2, 1)

    for day_offset in range(14):
        d = (base_date + timedelta(days=day_offset)).isoformat()
        for i, job in enumerate(jobs):
            # Successes: varies by job
            success_count = 3 + (i % 4)
            for s in range(success_count):
                conn.execute(
                    "INSERT INTO log_events (job_name, event_type, event_date, details) VALUES (?,?,?,?)",
                    (job, "file_processed", d, f"file_{s}.csv"),
                )
            # Failures: some jobs have failures
            if i in (0, 3, 7):  # Ocwen, BSI, FlagStar
                fail_count = 1 if day_offset % 3 == 0 else 0
                for f in range(fail_count):
                    conn.execute(
                        "INSERT INTO log_events (job_name, event_type, event_date, details) VALUES (?,?,?,?)",
                        (job, "error", d, "parse failure"),
                    )
            # Warnings
            if i in (2, 5):  # Shellpoint, Cenlar
                conn.execute(
                    "INSERT INTO log_events (job_name, event_type, event_date, details) VALUES (?,?,?,?)",
                    (job, "warning", d, "timeout"),
                )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def empty_db():
    """Empty SQLite — tests graceful handling of no data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE log_events (
            id INTEGER PRIMARY KEY,
            job_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            details TEXT,
            file_path TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE log_files (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            service_type TEXT,
            last_modified TEXT,
            indexed_at TEXT
        )
    """)
    conn.commit()
    yield conn
    conn.close()


# ── Mock Parser Fixture ──────────────────────────────────────────────────

@pytest.fixture
def mock_parser():
    """Mock SettingsParser with 10 email jobs."""
    parser = MagicMock()
    jobs = []
    for i, name in enumerate([
        "Ocwen", "PHH", "Shellpoint", "BSI", "LoanCare",
        "Cenlar", "SPS", "FlagStar", "Chase", "WellsFargo",
    ]):
        job = MagicMock()
        job.name = name
        job.servicer_id = str(100 + i) if i < 8 else None  # Chase, WellsFargo have no ServicerID
        job.mailbox = f"inbox{i // 3}@bank.com"
        job.folder = "Inbox"
        job.email_filter = f"*{name.lower()}*"
        job.did = f"DID{i:03d}"
        job.import_did = f"IMP{i:03d}"
        job.company_id = str(1 + i // 3)
        job.template = f"Template{i % 3}"
        job.queue_one_file = "True" if i % 2 == 0 else "False"
        job.parser_type = "csv" if i % 3 != 2 else "xlsx"
        jobs.append(job)

    parser.get_all_jobs.return_value = jobs
    parser.get_job_by_name.side_effect = lambda n: next((j for j in jobs if j.name == n), None)
    parser.type = "email"
    return parser


# ── Mock LogAnalytics Fixture ────────────────────────────────────────────

@pytest.fixture
def mock_log_analytics(analysis_db):
    """Mock LogAnalytics that exposes the in-memory connection."""
    analytics = MagicMock()
    analytics._get_conn.return_value = analysis_db
    analytics.check_staleness.return_value = {
        "stale_count": 1,
        "stale_jobs": [{"name": "FlagStar", "last_seen": "2025-02-10"}],
    }
    analytics.job_health.return_value = {
        "error_jobs": ["BSI"],
        "warning_jobs": ["Shellpoint"],
    }
    return analytics


# ── Mock DealRepository Fixture ──────────────────────────────────────────

@pytest.fixture
def mock_deal_repo():
    """Mock DealRepository with sample DID mappings."""
    repo = MagicMock()
    repo.get_by_did.side_effect = lambda did: {
        "DID000": [{"DID": "DID000", "ImportDID": "IMP000", "CompanyID": "1", "ItemID": "1001"}],
        "DID001": [{"DID": "DID001", "ImportDID": "IMP001", "CompanyID": "1", "ItemID": "1002"}],
        "DID003": [{"DID": "DID003", "ImportDID": "IMP003", "CompanyID": "2", "ItemID": "1004"}],
    }.get(did, [])
    repo.get_all.return_value = [
        {"DID": f"DID{i:03d}", "ImportDID": f"IMP{i:03d}", "CompanyID": str(1 + i // 3), "ItemID": str(1001 + i)}
        for i in range(10)
    ]
    return repo
```

---

## 3. Unit Tests by Module

### 3.1 `test_analysis_models.py` — 25 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_trend_day_creation` | TrendDay(date, 10, 1, 0) | All fields set correctly | P1 |
| 2 | `test_trend_day_success_rate` | TrendDay(date, 10, 2, 1) | success_rate = 76.9% | P1 |
| 3 | `test_trend_day_zero_total` | TrendDay(date, 0, 0, 0) | success_rate = 100.0 (no events = clean) | P1 |
| 4 | `test_trend_day_to_dict` | TrendDay instance | Dict with all fields | P1 |
| 5 | `test_trend_summary_to_dict` | TrendSummary with 3 days | {"days": [...], "overall_trend": "↑"} | P1 |
| 6 | `test_performance_entry_creation` | PerformanceEntry(job, 100, 5, ...) | All fields set | P1 |
| 7 | `test_performance_entry_status` | success_rate 99% vs 85% vs 60% | "healthy" / "warning" / "critical" | P1 |
| 8 | `test_performance_entry_to_dict` | PerformanceEntry instance | Serialized dict | P1 |
| 9 | `test_performance_summary_sorting` | 5 entries with varying rates | Sorted by success_rate ascending (worst first) | P1 |
| 10 | `test_performance_summary_to_dict` | PerformanceSummary instance | Dict with entries[] and summary | P1 |
| 11 | `test_consolidation_candidate_creation` | ConsolidationCandidate() | All fields set | P1 |
| 12 | `test_consolidation_group_creation` | Group with 3 candidates | group_size = 3, unique_attributes populated | P1 |
| 13 | `test_consolidation_group_merge_safety` | safe / review / risky | Correct safety levels | P1 |
| 14 | `test_consolidation_report_to_dict` | ConsolidationReport with 2 groups | Serialized with total_groups, total_candidates | P1 |
| 15 | `test_change_spec_delete` | ChangeSpec(type="delete_job") | valid, target_job required | P1 |
| 16 | `test_change_spec_rename` | ChangeSpec(type="rename_did") | valid, old_did + new_did required | P1 |
| 17 | `test_change_spec_change_filter` | ChangeSpec(type="change_filter") | valid, target_job + new_filter required | P1 |
| 18 | `test_change_spec_move_servicer` | ChangeSpec(type="move_servicer") | valid, old_servicer + new_servicer | P1 |
| 19 | `test_change_spec_invalid_type` | ChangeSpec(type="unknown") | Raises ValueError | P1 |
| 20 | `test_impact_report_creation` | ImpactReport with 3 affected | All fields, risk_level computed | P1 |
| 21 | `test_impact_report_to_dict` | ImpactReport instance | Serialized with affected[] | P1 |
| 22 | `test_health_section_creation` | HealthSection(name, status, ...) | All fields set | P1 |
| 23 | `test_health_section_score_range` | score = -5, 0, 50, 100, 150 | Clamped to 0–100 | P2 |
| 24 | `test_health_report_overall_score` | 9 sections with various scores | Weighted average matches manual calc | P1 |
| 25 | `test_health_report_to_dict` | HealthReport with 9 sections | Serialized with overall_status | P1 |

---

### 3.2 `test_trends.py` — 18 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_query_period_7_days` | analysis_db, days=7 | Returns 7 or fewer date-grouped rows | P1 |
| 2 | `test_query_period_14_days` | analysis_db, days=14 | Returns up to 14 date-grouped rows | P1 |
| 3 | `test_query_period_30_days` | analysis_db, 14 days of data | Only 14 days returned (not padded yet) | P1 |
| 4 | `test_query_period_specific_job` | analysis_db, job_name="Ocwen" | Only Ocwen data | P1 |
| 5 | `test_build_day_list_fills_gaps` | 10 data days across 14-day range | 14 TrendDay objects, 4 with zeros | P1 |
| 6 | `test_build_day_list_no_gaps` | Continuous 7 days | 7 TrendDay objects, all with data | P1 |
| 7 | `test_build_day_list_empty` | No data, 7-day range | 7 TrendDay objects, all zeros | P2 |
| 8 | `test_trend_indicator_increasing` | Week1 avg=10, Week2 avg=20 | "↑" | P1 |
| 9 | `test_trend_indicator_decreasing` | Week1 avg=20, Week2 avg=10 | "↓" | P1 |
| 10 | `test_trend_indicator_stable` | Week1 avg=10, Week2 avg=11 | "→" (within 10% threshold) | P1 |
| 11 | `test_analyze_all_jobs_14_days` | analysis_db, days=14 | TrendSummary with 14 days, totals correct | P1 |
| 12 | `test_analyze_single_job` | analysis_db, job="Ocwen", days=7 | TrendSummary filtered to Ocwen | P1 |
| 13 | `test_analyze_empty_db` | empty_db | TrendSummary with zero-days, no crash | P1 |
| 14 | `test_analyze_partial_data` | DB with only 3 days in 14-day range | 14 days returned, 11 zero-filled | P2 |
| 15 | `test_to_dict_serialization` | analyze() result | Valid JSON-serializable dict | P1 |
| 16 | `test_comparison_periods` | analysis_db, days=7 | previous_period populated if data exists | P2 |
| 17 | `test_error_handling_bad_conn` | Closed connection | Raises TREND-001 error | P1 |
| 18 | `test_performance_large_dataset` | 100 jobs × 30 days | Completes in < 2 seconds | P3 |

---

### 3.3 `test_performance.py` — 18 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_batch_query_all_jobs` | analysis_db | Returns metrics for all 10 jobs | P1 |
| 2 | `test_batch_query_date_range` | analysis_db, last 7 days | Only recent data included | P1 |
| 3 | `test_batch_query_single_job` | analysis_db, job="Ocwen" | Only Ocwen metrics | P1 |
| 4 | `test_get_all_job_names_from_db` | analysis_db | 10 unique job names | P1 |
| 5 | `test_get_all_job_names_from_parser` | Mock parser, empty DB | 10 names from parser | P2 |
| 6 | `test_get_all_job_names_union` | DB has 8, parser has 10 | 10 unique (union) | P2 |
| 7 | `test_success_rate_calculation` | 100 success, 5 error | 95.24% | P1 |
| 8 | `test_success_rate_no_events` | Job with 0 events | 100.0% (no activity = clean) | P1 |
| 9 | `test_status_thresholds` | 99%, 95%, 90%, 80%, 50% | healthy, healthy, warning, warning, critical | P1 |
| 10 | `test_benchmark_sorting` | 5 jobs, different rates | Sorted worst-first | P1 |
| 11 | `test_benchmark_top_n` | analysis_db, top=3 | Only 3 entries returned | P1 |
| 12 | `test_benchmark_empty_db` | empty_db | Empty entries[], no crash | P1 |
| 13 | `test_benchmark_to_dict` | benchmark() result | Valid JSON-serializable dict | P1 |
| 14 | `test_avg_files_per_day` | 70 files over 14 days | avg_daily = 5.0 | P1 |
| 15 | `test_peak_day_detection` | Varies by day | Peak day identified with correct count | P2 |
| 16 | `test_zero_day_handling` | Job active only 3 of 14 days | avg_daily based on 14 days, not 3 | P2 |
| 17 | `test_error_handling_bad_conn` | Closed connection | Raises PERF-001 error | P1 |
| 18 | `test_performance_100_jobs` | 100 jobs × 14 days | Single query, completes < 2s | P3 |

---

### 3.4 `test_consolidation.py` — 16 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_extract_signature_email` | Email job with mailbox+template+parser | (mailbox, template, parser_type) tuple | P1 |
| 2 | `test_extract_signature_sftp` | SFTP job with path+parser | (path, None, parser_type) tuple | P1 |
| 3 | `test_same_signature_groups` | 3 jobs with same mailbox+template | Grouped into 1 ConsolidationGroup | P1 |
| 4 | `test_no_groups_all_unique` | 5 jobs, all different signatures | 0 groups in report | P1 |
| 5 | `test_multiple_groups` | 8 jobs forming 2 groups | 2 ConsolidationGroups | P1 |
| 6 | `test_singleton_filtered_out` | 1 job with unique signature | Not included as a group | P1 |
| 7 | `test_unique_attributes_extracted` | Group of 3 with different filters | unique_attributes = ["email_filter"] | P1 |
| 8 | `test_unique_attributes_multiple` | Group differing in filter + DID | unique_attributes = ["email_filter", "did"] | P1 |
| 9 | `test_merge_safety_safe` | Same mailbox, same template, only DID differs | safety = "safe" | P1 |
| 10 | `test_merge_safety_review` | Different filters but same mailbox | safety = "review" | P1 |
| 11 | `test_merge_safety_risky` | Different ServicerIDs | safety = "risky" | P1 |
| 12 | `test_analyze_full_pipeline` | mock_parser with 10 jobs | ConsolidationReport with correct counts | P1 |
| 13 | `test_analyze_empty_parser` | Parser with 0 jobs | Empty report, no crash | P1 |
| 14 | `test_report_to_dict` | analyze() result | Valid JSON-serializable dict | P1 |
| 15 | `test_cross_service_type` | Mixed email + SFTP jobs | Never groups email with SFTP | P2 |
| 16 | `test_jobs_without_servicer_id` | Jobs with None servicer_id | Handled gracefully, grouped by other attributes | P2 |

---

### 3.5 `test_impact.py` — 22 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_sim_delete_job_exists` | ChangeSpec(delete, "Ocwen") | ImpactReport with coverage delta, affected DIDs | P1 |
| 2 | `test_sim_delete_job_not_found` | ChangeSpec(delete, "NonExistent") | Error: job not found | P1 |
| 3 | `test_sim_delete_job_with_activity` | Delete job with recent log events | risk_level = "high", recommendation includes warning | P1 |
| 4 | `test_sim_delete_job_no_activity` | Delete job with no recent events | risk_level = "low" | P1 |
| 5 | `test_sim_delete_job_batch_member` | Delete job sharing ImportDID with another | Affected entities include batch info | P2 |
| 6 | `test_sim_rename_did_no_collision` | Rename DID000 to DID999 | risk_level = "low", no collision | P1 |
| 7 | `test_sim_rename_did_collision` | Rename DID000 to DID001 (existing) | risk_level = "high", collision detected | P1 |
| 8 | `test_sim_rename_did_not_found` | Rename DID999 (doesn't exist in jobs) | Error: DID not in use | P1 |
| 9 | `test_sim_rename_did_deal_table_impact` | Rename DID in tblExternalDIDRef | Affected entities include deal table rows | P1 |
| 10 | `test_sim_change_filter_valid` | Change Ocwen filter to "*ocwen_new*" | ImpactReport with old/new comparison | P1 |
| 11 | `test_sim_change_filter_job_not_found` | Change filter on non-existent job | Error: job not found | P1 |
| 12 | `test_sim_change_filter_broadening` | Narrow → broad filter (e.g., "*ocwen*" → "*") | risk_level = "medium", may capture unintended files | P2 |
| 13 | `test_sim_change_filter_narrowing` | Broad → narrow filter | risk_level = "low" | P2 |
| 14 | `test_sim_move_servicer_single_job` | Move ServicerID 100 to 200, 1 job affected | 1 affected entity | P1 |
| 15 | `test_sim_move_servicer_multi_job` | Move ServicerID 100 to 200, 3 jobs affected | 3 affected entities | P1 |
| 16 | `test_sim_move_servicer_not_found` | Move ServicerID 999 (not used) | Error: servicerID not found | P1 |
| 17 | `test_sim_move_servicer_null_target` | Move from 100 to None | Affected jobs become process-level | P2 |
| 18 | `test_simulate_invalid_change_type` | ChangeSpec(type="unknown") | Raises ValueError | P1 |
| 19 | `test_impact_report_to_dict` | Any simulation result | Valid JSON-serializable dict | P1 |
| 20 | `test_risk_level_computation` | Various affected counts + activity levels | Correct risk: low/medium/high | P1 |
| 21 | `test_recommendation_text` | Delete active job | Non-empty recommendation string | P2 |
| 22 | `test_simulate_with_no_deal_repo` | deal_repo=None | Graceful: skip DID coverage check, note in recommendation | P1 |

---

### 3.6 `test_health.py` — 18 tests

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_check_xml_validity_healthy` | Valid parsed XML | Section: status="pass", score=100 | P1 |
| 2 | `test_check_xml_validity_unhealthy` | XML with parse errors | Section: status="fail", score < 50 | P1 |
| 3 | `test_check_job_coverage_full` | All DIDs mapped in deal table | Section: status="pass" | P1 |
| 4 | `test_check_job_coverage_gaps` | 2 unmapped DIDs | Section: status="warning", details list gaps | P1 |
| 5 | `test_check_orphan_dids` | 1 orphan detected | Section: status="warning" | P1 |
| 6 | `test_check_orphan_dids_none` | No orphans | Section: status="pass" | P1 |
| 7 | `test_check_collision_risk` | 1 collision found | Section: status="fail", details list collision | P1 |
| 8 | `test_check_collision_risk_clean` | No collisions | Section: status="pass" | P1 |
| 9 | `test_check_log_staleness` | 2 stale jobs | Section: status="warning" | P1 |
| 10 | `test_check_log_health` | 1 error job, 2 warning jobs | Section: status="warning" | P1 |
| 11 | `test_check_performance_trends` | 98% avg success rate | Section: status="pass" | P1 |
| 12 | `test_check_performance_trends_low` | 70% avg success rate | Section: status="fail" | P1 |
| 13 | `test_check_consolidation_opps` | 3 consolidation groups | Section: status="info" | P2 |
| 14 | `test_check_config_consistency` | All jobs valid | Section: status="pass" | P2 |
| 15 | `test_overall_healthy` | 9 sections all pass | Overall: status="healthy", score ≥ 90 | P1 |
| 16 | `test_overall_warning` | 2 sections warning | Overall: status="warning" | P1 |
| 17 | `test_overall_critical` | 3+ sections fail | Overall: status="critical" | P1 |
| 18 | `test_graceful_degradation` | analytics=None, deal_repo=None | Unavailable sections marked, no crash, overall still computed | P1 |

---

## 4. CLI Integration Tests

### `tests/cli/test_main_p4.py` — 10 tests

These tests invoke CLI commands via `subprocess` or direct function call and verify JSON output.

| # | Test Name | Command | Expected | Priority |
|---|-----------|---------|----------|----------|
| 1 | `test_cli_log_trends_default` | `log_trends --db-path test.db` | Valid JSON with "days" array, "summary" | P1 |
| 2 | `test_cli_log_trends_custom_days` | `log_trends --db-path test.db --days 30` | 30-day range in output | P1 |
| 3 | `test_cli_log_trends_single_job` | `log_trends --db-path test.db --job Ocwen` | Only Ocwen data | P1 |
| 4 | `test_cli_log_performance_default` | `log_performance --db-path test.db` | Valid JSON with "entries" array | P1 |
| 5 | `test_cli_log_performance_top` | `log_performance --db-path test.db --top 3` | 3 entries max | P1 |
| 6 | `test_cli_analyze_consolidation` | `analyze_consolidation --settings-path test.xml` | Valid JSON with "groups" array | P1 |
| 7 | `test_cli_analyze_impact` | `analyze_impact --change-type delete_job --target-job Ocwen --settings-path test.xml` | Valid JSON with "affected_entities", "risk_level" | P1 |
| 8 | `test_cli_analyze_impact_bad_type` | `analyze_impact --change-type unknown` | Error JSON with IMPACT-004 code | P1 |
| 9 | `test_cli_analyze_health` | `analyze_health --settings-path test.xml --db-path test.db` | Valid JSON with "sections", "overall_score" | P1 |
| 10 | `test_cli_analyze_health_partial` | `analyze_health` (no paths) | Graceful degradation JSON, no crash | P1 |

---

## 5. Extension Handler Tests

### `tests/extension/test_analyze_handler.js` — 10 tests (Jest)

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `handles consolidation subcommand` | "/analyze consolidation" | Calls CLI `analyze_consolidation` | P1 |
| 2 | `handles impact subcommand` | "/analyze impact delete job Ocwen" | Calls `parseChangeIntent()` then CLI | P1 |
| 3 | `handles health subcommand` | "/analyze health" | Calls CLI `analyze_health` with settings paths | P1 |
| 4 | `handles health with type filter` | "/analyze health --type email" | Passes `--type email` to CLI | P1 |
| 5 | `routes unknown subcommand to LLM` | "/analyze blah" | Falls back to intent parsing | P2 |
| 6 | `formats consolidation response` | CLI returns groups JSON | Markdown table with groups | P1 |
| 7 | `formats impact response` | CLI returns impact JSON | Risk badge + affected list | P1 |
| 8 | `formats health response` | CLI returns health JSON | Section-by-section report with overall score | P1 |
| 9 | `handles CLI error gracefully` | CLI returns error JSON | User-friendly error message | P1 |
| 10 | `suggests follow-up actions` | After any subcommand | Appropriate follow-up buttons shown | P2 |

---

## 6. Manual QA Checklist

These tests must be run in F5 Extension Development Host with real or realistic data.

| # | Scenario | Steps | Pass Criteria |
|---|----------|-------|---------------|
| M1 | Trend visualization | Type `@frp /logs trends` | 14-day timeline renders; LLM summarizes trend direction |
| M2 | Trend with job filter | Type `@frp /logs trends for Ocwen` | Only Ocwen data; LLM notes it's a single-job view |
| M3 | Performance ranking | Type `@frp /logs performance` | All jobs listed with success rates; worst-first sorting |
| M4 | Performance top-N | Type `@frp /logs performance top 5` | Only 5 entries shown |
| M5 | Consolidation report | Type `@frp /analyze consolidation` | Groups shown with merge safety; LLM provides actionable advice |
| M6 | Impact simulation NL | Type `@frp /analyze impact what happens if I delete the Ocwen job?` | LLM parses intent → ChangeSpec; impact report shown with risk level |
| M7 | Full health check | Type `@frp /analyze health` | 9 sections rendered; overall score and status badge visible |
| M8 | Health with partial deps | Remove DB path from settings, type `@frp /analyze health` | Unavailable sections shown as "⚠ unavailable"; overall score still computed from available sections |

---

## 7. End-to-End Scenarios

### E2E-P4-1: Daily Operations Check

```
User: @frp /logs trends
→ 14-day trend timeline with success/fail/warning breakdown
→ LLM summary: "Volume is stable at ~50 files/day. Slight ↑ in errors on weekends."

User: @frp /logs performance
→ Ranked table of all jobs
→ FlagStar flagged as "warning" (93% success)
→ Follow-up: "Want to drill into FlagStar errors?"

User: @frp /logs health FlagStar
→ (Phase 3) Single-job health detail

User: @frp /analyze health
→ Full 9-section report
→ Overall: 82/100 "warning"
→ Sections: XML valid ✅, Coverage 95% ⚠, No orphans ✅, No collisions ✅,
  1 stale job ⚠, FlagStar errors ⚠, Performance 94% ⚠, 2 consolidation groups ℹ, Config valid ✅
```

### E2E-P4-2: Pre-Change Safety

```
User: @frp /analyze impact what if I delete the Ocwen job?
→ LLM parses intent: ChangeSpec(type="delete_job", target_job="Ocwen")
→ Impact report:
  - Affected DID: DID000 (mapped to CompanyID 1)
  - Coverage delta: 1 DID loses coverage
  - Recent activity: 47 files processed in last 7 days
  - Risk: HIGH
  - Recommendation: "Ocwen is actively processing files. Consider disabling before deleting."

User: @frp /analyze consolidation
→ 2 groups found:
  Group 1: PHH + LoanCare (same mailbox, same template) — safety: safe
  Group 2: Cenlar + SPS (same mailbox, different filters) — safety: review
→ Follow-up: "Want to simulate merging Group 1?"
```

### E2E-P4-3: Graceful Degradation

```
# Settings: frpAgent.prod = false, no MySQL running, no SQLite DB
User: @frp /analyze health
→ Sections rendered:
  - XML Validity: ✅ pass (direct file parse, no DB needed)
  - Job Coverage: ⚠ unavailable (DB connection failed)
  - Orphan DIDs: ⚠ unavailable (DB connection failed)
  - Collision Risk: ⚠ unavailable (DB connection failed)
  - Log Staleness: ⚠ unavailable (SQLite not found)
  - Log Health: ⚠ unavailable (SQLite not found)
  - Performance Trends: ⚠ unavailable (SQLite not found)
  - Consolidation Ops: ✅ pass (parser-only analysis)
  - Config Consistency: ✅ pass (parser-only analysis)
→ Overall: 3/9 sections available → Score: based on available only
→ LLM note: "3 sections unavailable due to missing connections. Run with DB and SQLite for full report."
```

---

## 8. Coverage Targets

| Module | Min. Line Coverage | Branch Coverage |
|--------|--------------------|-----------------|
| `analysis/models.py` | 95% | 90% |
| `analysis/trends.py` | 90% | 85% |
| `analysis/performance.py` | 90% | 85% |
| `analysis/consolidation.py` | 90% | 85% |
| `analysis/impact.py` | 90% | 85% |
| `analysis/health.py` | 85% | 80% |
| `cli/main.py` (Phase 4 commands) | 85% | 80% |
| **Overall Phase 4 Python** | **≥ 90%** | **≥ 83%** |

### Coverage Enforcement

```bash
pytest tests/analysis/ tests/cli/test_main_p4.py \
  --cov=backend/analysis --cov=cli/main \
  --cov-report=term-missing \
  --cov-fail-under=90
```

---

## 9. Test Execution Order

### Quick Smoke (< 30 seconds)

```bash
pytest tests/analysis/test_analysis_models.py -v
```

### Module Suite (< 2 minutes)

```bash
pytest tests/analysis/ -v --tb=short
```

### Full Phase 4 Suite (< 3 minutes)

```bash
pytest tests/analysis/ tests/cli/test_main_p4.py -v --tb=short
```

### All Phases Regression (< 5 minutes)

```bash
pytest tests/ -v --tb=short
```

### Extension Tests (separate)

```bash
cd extension && npm test -- --testPathPattern="analyze"
```

---

### Test Count Summary

| Category | Count |
|----------|-------|
| Model unit tests | 25 |
| TrendAnalyzer tests | 18 |
| PerformanceBenchmarker tests | 18 |
| ConsolidationAnalyzer tests | 16 |
| ImpactSimulator tests | 22 |
| HealthChecker tests | 18 |
| CLI integration tests | 10 |
| Extension handler tests (Jest) | 10 |
| **Total Automated** | **137** |
| Manual QA | 8 |
| **Grand Total** | **145** |

---

*Previous document: [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)*  
*Phase 4 documentation complete.*
