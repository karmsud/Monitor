# Phase 1: Testing Plan
## Comprehensive Test Coverage

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Proposal — Pending Approval  
**Target Coverage:** 90%+ line coverage across all Phase 1 modules

---

## Table of Contents
1. [Testing Strategy](#testing-strategy)
2. [Test Infrastructure](#test-infrastructure)
3. [XML Parser Tests](#xml-parser-tests)
4. [XML Validator Tests](#xml-validator-tests)
5. [XML Writer Tests](#xml-writer-tests)
6. [Backup Manager Tests](#backup-manager-tests)
7. [Database Connector Tests](#database-connector-tests)
8. [Deal Repository Tests](#deal-repository-tests)
9. [Log Parser Tests](#log-parser-tests)
10. [SQLite Indexer Tests](#sqlite-indexer-tests)
11. [CLI Tests](#cli-tests)
12. [Extension Integration Tests](#extension-integration-tests)
13. [End-to-End Scenarios](#end-to-end-scenarios)

---

## Testing Strategy

### Layer Coverage

| Layer | Framework | Approach | Target |
|-------|-----------|----------|--------|
| Python Data Models | pytest | Unit tests | 100% |
| XML Parser | pytest | Unit + integration with real XML | 95% |
| XML Validator | pytest | Parameterized over all error codes | 100% |
| XML Writer | pytest | Unit with tmp_path fixtures | 95% |
| Backup Manager | pytest | Unit with tmp_path fixtures | 95% |
| DB Connector | pytest | Mock-based (pyodbc mocked) | 90% |
| Deal Repository | pytest | Mock + optional integration | 90% |
| Log Parser | pytest | Unit + real log file integration | 95% |
| SQLite Indexer | pytest | Unit with in-memory/tmp SQLite | 95% |
| CLI Main | pytest | Subprocess + capsys | 90% |
| Extension JS | Manual F5 | Manual QA checklist | N/A |

### Test File Organization

```
tests/
├── conftest.py                    # Shared fixtures
├── __init__.py
├── xml/
│   ├── __init__.py
│   ├── test_models.py             # EmailJob, SftpJob, ValidationResult
│   ├── test_parser.py             # SettingsXmlParser
│   ├── test_validator.py          # validate() method
│   └── test_writer.py             # XmlWriter
├── db/
│   ├── __init__.py
│   ├── test_connection.py         # Connection factory
│   └── test_deal_repo.py          # DealRepository
├── logs/
│   ├── __init__.py
│   ├── test_parser.py             # LogFileParser
│   ├── test_models.py             # LogEvent
│   └── test_indexer.py            # LogIndexer
├── backup/
│   ├── __init__.py
│   └── test_manager.py            # BackupManager
├── cli/
│   ├── __init__.py
│   └── test_main.py               # CLI commands
└── fixtures/
    ├── email_settings_valid.xml
    ├── email_settings_empty.xml
    ├── email_settings_invalid.xml
    ├── email_settings_missing.xml
    ├── email_settings_duplicate.xml
    ├── sftp_settings_valid.xml
    └── logs/
        ├── EmailMonitor_Settings.20260202102003864.log
        ├── EmailMonitor_Settings.20260203080105223.log
        └── EmailMonitor_Settings.20260204091522007.log
```

---

## Test Infrastructure

### File: `tests/conftest.py`

```python
"""Shared pytest fixtures for FRP Agent tests."""
import os
import shutil
import pytest
import sqlite3

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def email_fixture():
    """Path to a valid email Settings.xml test fixture."""
    return os.path.join(FIXTURES_DIR, "email_settings_valid.xml")


@pytest.fixture
def sftp_fixture():
    """Path to a valid SFTP Settings.xml test fixture."""
    return os.path.join(FIXTURES_DIR, "sftp_settings_valid.xml")


@pytest.fixture
def empty_fixture():
    """Path to a valid but empty email Settings.xml."""
    return os.path.join(FIXTURES_DIR, "email_settings_empty.xml")


@pytest.fixture
def invalid_fixture():
    """Path to malformed XML."""
    return os.path.join(FIXTURES_DIR, "email_settings_invalid.xml")


@pytest.fixture
def missing_fixture():
    """Path to XML with missing required fields."""
    return os.path.join(FIXTURES_DIR, "email_settings_missing.xml")


@pytest.fixture
def duplicate_fixture():
    """Path to XML with duplicate job names."""
    return os.path.join(FIXTURES_DIR, "email_settings_duplicate.xml")


@pytest.fixture
def sample_log_folder():
    """Path to folder with sample log files."""
    return os.path.join(FIXTURES_DIR, "logs")


@pytest.fixture
def sample_log_path():
    """Path to a single sample log file."""
    return os.path.join(FIXTURES_DIR, "logs", "EmailMonitor_Settings.20260202102003864.log")


@pytest.fixture
def tmp_settings(email_fixture, tmp_path):
    """Create a writable copy of email settings in a temp directory."""
    dest = tmp_path / "Settings.xml"
    shutil.copy(email_fixture, dest)
    return str(dest)


@pytest.fixture
def populated_indexer(tmp_path, sample_log_folder):
    """Create a LogIndexer with sample data already synced."""
    from backend.logs.indexer import LogIndexer
    db_path = str(tmp_path / "test_logs.db")
    indexer = LogIndexer(db_path)
    indexer.sync(sample_log_folder, "email")
    yield indexer
    indexer.close()
```

### File: `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    integration: Integration tests requiring real DB or files
    slow: Tests that take more than 5 seconds
```

---

## XML Parser Tests

### File: `tests/xml/test_parser.py`

| # | Test Name | Input | Expected | Priority |
|---|-----------|-------|----------|----------|
| 1 | `test_detect_email_type` | email_fixture | `"email"` | P1 |
| 2 | `test_detect_sftp_type` | sftp_fixture | `"sftp"` | P1 |
| 3 | `test_detect_unknown_type` | `<Root/>` XML | `"unknown"` | P2 |
| 4 | `test_get_all_email_jobs_count` | email_fixture (3 jobs) | `len(jobs) == 3` | P1 |
| 5 | `test_get_all_sftp_jobs_count` | sftp_fixture (2 jobs) | `len(jobs) == 2` | P1 |
| 6 | `test_email_job_type` | email_fixture | All `isinstance(EmailJob)` | P1 |
| 7 | `test_sftp_job_type` | sftp_fixture | All `isinstance(SftpJob)` | P1 |
| 8 | `test_email_job_full_fields` | email_fixture, "TestJob_ValidFull" | All fields populated | P1 |
| 9 | `test_email_job_mailbox` | email_fixture | `mailbox == "test@example.com"` | P1 |
| 10 | `test_email_job_folder` | email_fixture | `folder == "Inbox"` | P1 |
| 11 | `test_email_job_sme` | email_fixture | `sme == "sme@example.com"` | P1 |
| 12 | `test_email_job_servicer_id` | email_fixture, full job | `servicer_id == 150` | P1 |
| 13 | `test_email_job_shelf_level` | email_fixture, shelf job | `servicer_id is None` | P1 |
| 14 | `test_email_job_queue_one_file` | email_fixture, full job | `queue_one_file is True` | P2 |
| 15 | `test_email_job_day_adjust` | email_fixture, full job | `day_adjust == -1` | P2 |
| 16 | `test_email_job_filters` | email_fixture | `"From" in filters` | P1 |
| 17 | `test_email_job_parsers` | email_fixture | `"CMS" in parsers` | P1 |
| 18 | `test_email_job_templates` | email_fixture | `"FileLoader" in templates` | P1 |
| 19 | `test_email_job_last_email` | email_fixture | String or None | P2 |
| 20 | `test_email_job_save_location` | email_fixture | Contains `{DealFolder}` | P1 |
| 21 | `test_sftp_job_path` | sftp_fixture | Non-empty string | P1 |
| 22 | `test_sftp_job_servicer_id` | sftp_fixture | Integer > 0 | P1 |
| 23 | `test_sftp_job_dsn` | sftp_fixture | Non-empty string | P1 |
| 24 | `test_sftp_job_skip_list` | sftp_fixture | Non-empty string | P1 |
| 25 | `test_sftp_job_ignore_list` | sftp_fixture | Non-empty string | P1 |
| 26 | `test_sftp_job_zip_filter` | sftp_fixture | Non-empty string | P1 |
| 27 | `test_search_by_name` | "TestJob" | Matches ≥ 1 job | P1 |
| 28 | `test_search_by_mailbox` | "test@example" | Exact match | P1 |
| 29 | `test_search_by_parser` | "cms" | Matches parser key | P1 |
| 30 | `test_search_by_template` | "FileLoader" | Matches template | P1 |
| 31 | `test_search_by_filter_value` | "sender@partner" | Matches filter value | P1 |
| 32 | `test_search_by_servicer_id` | "150" | Matches servicer | P1 |
| 33 | `test_search_shelf_level` | "shelf-level" | Only jobs with None servicer | P1 |
| 34 | `test_search_no_results` | "zzz_nonexistent" | Empty list | P1 |
| 35 | `test_search_case_insensitive` | "TESTJOB" | Matches lowercase | P1 |
| 36 | `test_get_infrastructure` | email_fixture | Dict with server, db keys | P2 |
| 37 | `test_get_element_tree` | email_fixture | Returns ET.ElementTree | P2 |
| 38 | `test_file_not_found` | "/bad/path.xml" | Raises FileNotFoundError | P1 |
| 39 | `test_malformed_xml` | invalid_fixture | Raises ET.ParseError | P1 |
| 40 | `test_empty_collection` | empty_fixture | Returns empty list | P1 |

---

## XML Validator Tests

### File: `tests/xml/test_validator.py`

| # | Test Name | Trigger | Expected Code | Priority |
|---|-----------|---------|---------------|----------|
| 1 | `test_valid_email_no_errors` | Valid email fixture | `valid=True, errors=[]` | P1 |
| 2 | `test_valid_sftp_no_errors` | Valid sftp fixture | `valid=True, errors=[]` | P1 |
| 3 | `test_e001_malformed_xml` | Invalid XML | `E001` in errors | P1 |
| 4 | `test_e002_missing_outlook` | XML without `<Outlook>` | `E002` in errors | P1 |
| 5 | `test_e003_missing_collection` | `<Outlook>` without children | `E003` in errors | P1 |
| 6 | `test_e004_missing_mailbox` | Job without `<Mailbox>` | `E004` in errors | P1 |
| 7 | `test_e005_missing_sme` | Job without `<SME>` | `E005` in errors | P1 |
| 8 | `test_e006_missing_parsers` | Job without `<Parsers>` | `E006` in errors | P1 |
| 9 | `test_e007_missing_save_location` | Job without `<SaveLocation>` | `E007` in errors | P1 |
| 10 | `test_e008_duplicate_names` | Two jobs with same tag | `E008` in errors | P1 |
| 11 | `test_e009_sftp_missing_servicerid` | SFTP job without ServicerID | `E009` in errors | P1 |
| 12 | `test_e010_sftp_missing_dsn` | SFTP job without DSN | `E010` in errors | P1 |
| 13 | `test_e011_sftp_missing_skiplist` | SFTP job without SkipList | `E011` in errors | P1 |
| 14 | `test_e012_sftp_missing_ignorelist` | SFTP job without IgnoreList | `E012` in errors | P1 |
| 15 | `test_e013_sftp_missing_zipfilter` | SFTP job without ZipContentFilter | `E013` in errors | P1 |
| 16 | `test_w001_unknown_servicer` | ServicerID not in db_servicer_ids | `W001` in warnings | P1 |
| 17 | `test_w001_skipped_without_db` | db_servicer_ids=None | No W001 | P2 |
| 18 | `test_w002_empty_filters` | Email job with empty `<Filters>` | `W002` in warnings | P2 |
| 19 | `test_w003_no_tokens` | SaveLocation without `{DealFolder}` | `W003` in warnings | P2 |
| 20 | `test_w004_bad_timestamp` | Unparseable `<LastEmail>` value | `W004` in warnings | P2 |
| 21 | `test_w005_bad_day_adjust` | `<DayAdjust>abc</DayAdjust>` | `W005` in warnings | P2 |
| 22 | `test_i001_job_count` | email_fixture (3 jobs) | `I001` with count=3 | P2 |
| 23 | `test_i002_servicerid_count` | email_fixture | `I002` present | P2 |
| 24 | `test_i003_shelf_level_count` | email_fixture | `I003` present | P2 |
| 25 | `test_valid_false_when_errors` | Any E-code fixture | `valid=False` | P1 |
| 26 | `test_valid_true_with_warnings` | W-code only fixture | `valid=True` | P1 |
| 27 | `test_multiple_errors` | Multiple issues | Multiple E-codes | P2 |

---

## XML Writer Tests

### File: `tests/xml/test_writer.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_save_creates_backup_dir` | Save when no backup/ exists | backup/ directory created | P1 |
| 2 | `test_save_creates_backup_file` | Normal save | backup/Settings_*.xml exists | P1 |
| 3 | `test_backup_filename_format` | Generate filename | Matches `Settings_\d{8}_\d{6}\.xml` | P1 |
| 4 | `test_save_preserves_content` | Parse → save → re-parse | Same job count | P1 |
| 5 | `test_save_returns_success` | Normal save | `{"success": True, "backup_path": ...}` | P1 |
| 6 | `test_save_backup_is_original` | Save modified tree | Backup matches original content | P1 |
| 7 | `test_save_verifies_written_xml` | Save then re-parse | No ParseError | P2 |
| 8 | `test_save_read_only_file` | Setting.xml is read-only | `success=False`, error message | P2 |
| 9 | `test_multiple_saves_stack` | Save 3 times | 3 backup files exist | P2 |

---

## Backup Manager Tests

### File: `tests/backup/test_manager.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_list_empty` | No backup/ folder | Empty list | P1 |
| 2 | `test_list_sorted_newest_first` | 3 backup files | First = newest | P1 |
| 3 | `test_list_ignores_non_matching` | backup/ with random.txt | Excludes random.txt | P1 |
| 4 | `test_list_includes_metadata` | Backup file | Has filename, full_path, timestamp, size_bytes, age_days | P1 |
| 5 | `test_get_backup_count` | 2 backups | Returns 2 | P1 |
| 6 | `test_get_latest_backup` | 2 backups | Returns newest | P1 |
| 7 | `test_get_latest_none` | No backups | Returns None | P1 |
| 8 | `test_restore_success` | Restore a backup | Current file = backup content | P1 |
| 9 | `test_restore_creates_safety_backup` | Restore | Safety backup of current file created | P1 |
| 10 | `test_restore_nonexistent_file` | Bad filename | Raises FileNotFoundError | P1 |
| 11 | `test_restore_validates_xml` | Restore malformed backup | Error, original preserved | P2 |

---

## Database Connector Tests

### File: `tests/db/test_connection.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_get_mysql_connection` | Mock pyodbc | Calls `pyodbc.connect` with MySQL driver | P1 |
| 2 | `test_get_mssql_connection` | Mock pyodbc | Calls `pyodbc.connect` with SQL Server driver | P1 |
| 3 | `test_factory_routes_prod_true` | `prod_mode=True` | Uses connection_mssql | P1 |
| 4 | `test_factory_routes_prod_false` | `prod_mode=False` | Uses connection_mysql | P1 |
| 5 | `test_missing_secrets_file` | Bad path | Raises FileNotFoundError | P1 |
| 6 | `test_mysql_conn_string` | Valid secrets | Connection string has MySQL driver | P2 |
| 7 | `test_mssql_conn_string` | Valid secrets | Connection string has SQL Server driver | P2 |

---

## Deal Repository Tests

### File: `tests/db/test_deal_repo.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_servicer_exists_true` | Mock returns row | `True` | P1 |
| 2 | `test_servicer_exists_false` | Mock returns None | `False` | P1 |
| 3 | `test_get_deals_by_company` | Mock returns 2 rows | List of 2 dicts | P1 |
| 4 | `test_get_deals_empty` | Mock returns 0 rows | Empty list | P1 |
| 5 | `test_get_company_summary` | Mock returns counts | Dict with 3 count keys | P1 |
| 6 | `test_get_company_summary_empty` | CompanyID not found | All counts = 0 | P1 |
| 7 | `test_get_all_servicer_ids` | Mock returns 3 IDs | Set of 3 ints | P1 |
| 8 | `test_search_by_did` | Mock returns matches | List of dicts with DID | P1 |
| 9 | `test_search_by_import_did` | Mock returns matches | List of dicts with ImportDID | P1 |
| 10 | `test_context_manager` | `with DealRepository()` | Connection closed after exit | P2 |
| 11 | `test_close_idempotent` | Call close twice | No error | P2 |

---

## Log Parser Tests

### File: `tests/logs/test_parser.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_parse_real_log_not_empty` | Real log file | `len(events) > 0` | P1 |
| 2 | `test_all_events_have_log_file` | Any log | All `.log_file` non-empty | P1 |
| 3 | `test_all_events_have_timestamp` | Any log | All `.timestamp` non-empty | P1 |
| 4 | `test_job_start_detected` | Log with job starts | `event_type == "job_start"` events found | P1 |
| 5 | `test_job_start_has_name` | Job start event | `job_name` is not None | P1 |
| 6 | `test_job_start_has_mailbox` | Job start event | `mailbox` is not None | P1 |
| 7 | `test_emails_found_count` | "found 3" line | `emails_found == 3` | P1 |
| 8 | `test_processing_subject` | "Processing: [...]" line | `subject` captured | P1 |
| 9 | `test_from_sender` | "From: ..." line | `sender` captured | P1 |
| 10 | `test_parser_match` | "Matched email..." line | `parser` name captured | P2 |
| 11 | `test_file_load` | "Load > ..." line | `filename` captured | P2 |
| 12 | `test_template_queue` | "Queue file [...]" line | `template` captured | P2 |
| 13 | `test_did_failure` | "Did not find DID..." line | `event_type == "did_mapping_failed"` | P1 |
| 14 | `test_error_detection` | Line with "error" | `event_type == "error"` | P1 |
| 15 | `test_header_lines_skipped` | `## Heading` lines | Not in events | P1 |
| 16 | `test_timestamp_extraction` | Valid line | `(timestamp, message)` tuple | P1 |
| 17 | `test_no_timestamp_returns_none` | `## Header line` | Returns None | P1 |
| 18 | `test_job_context_carries_forward` | Multi-job log | Events after job_start have correct job_name | P1 |
| 19 | `test_job_context_resets` | Second job_start | Events get new job_name | P1 |
| 20 | `test_empty_file` | Empty file | Empty list | P2 |
| 21 | `test_encoding_tolerance` | UTF-8 with BOM | Parses without error | P2 |

---

## SQLite Indexer Tests

### File: `tests/logs/test_indexer.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_create_tables` | New database | 3 tables exist | P1 |
| 2 | `test_create_indexes` | New database | Indexes on timestamp, job_name, event_type | P1 |
| 3 | `test_sync_processes_files` | Folder with 3 logs | `files_processed == 3` | P1 |
| 4 | `test_sync_indexes_events` | Folder with logs | `events_indexed > 0` | P1 |
| 5 | `test_sync_skips_indexed` | Sync twice | Second run: `files_skipped == N` | P1 |
| 6 | `test_sync_incremental` | Add new file after first sync | Only new file processed | P1 |
| 7 | `test_sync_returns_summary` | Normal sync | Dict with all expected keys | P1 |
| 8 | `test_query_all` | No filters | Returns events up to limit | P1 |
| 9 | `test_query_by_job_name` | Specific job | All results match job_name | P1 |
| 10 | `test_query_by_event_type` | "error" type | All results are errors | P1 |
| 11 | `test_query_by_date_range` | Start + end dates | All timestamps in range | P2 |
| 12 | `test_query_limit` | limit=5 | `len(results) <= 5` | P1 |
| 13 | `test_query_ordered_desc` | Default | First result has latest timestamp | P1 |
| 14 | `test_get_job_summary` | Known job | Dict with expected keys | P1 |
| 15 | `test_get_job_summary_unknown` | Nonexistent job | Zeroed counts | P2 |
| 16 | `test_get_sync_status` | After sync | Shows last_sync, total_events | P1 |
| 17 | `test_retention_purge` | 0-month retention | Old events deleted | P1 |
| 18 | `test_retention_keeps_recent` | 12-month retention | Recent events kept | P2 |
| 19 | `test_db_file_created` | New indexer | File exists on disk | P1 |
| 20 | `test_context_manager` | `with LogIndexer()` | Connection closed | P2 |
| 21 | `test_error_on_bad_file` | Corrupt log file | `files_errored == 1`, no crash | P1 |

---

## CLI Tests

### File: `tests/cli/test_main.py`

| # | Test Name | Description | Expected | Priority |
|---|-----------|-------------|----------|----------|
| 1 | `test_search_jobs_valid_json` | search_jobs command | stdout is valid JSON | P1 |
| 2 | `test_search_jobs_returns_data` | search_jobs --query test | `data.jobs` is a list | P1 |
| 3 | `test_validate_xml_valid` | validate_xml command | `data.valid` is True | P1 |
| 4 | `test_validate_xml_invalid` | validate_xml on bad XML | `data.valid` is False | P1 |
| 5 | `test_sync_logs_command` | sync_logs command | Returns sync summary | P1 |
| 6 | `test_list_backups_command` | list_backups command | Returns list (may be empty) | P1 |
| 7 | `test_status_command` | status command | `success` is True | P1 |
| 8 | `test_unknown_command_exit` | invalid command | SystemExit | P1 |
| 9 | `test_missing_required_arg` | No --settings-path | SystemExit or error | P1 |
| 10 | `test_all_output_is_json` | Any command | stdout parses as JSON | P1 |
| 11 | `test_errors_go_to_stderr` | Command with logging | stderr has log messages, stdout has JSON only | P1 |
| 12 | `test_error_response_format` | Bad path | `success=False, errors=[...]` | P1 |
| 13 | `test_elapsed_ms_present` | Any command | `elapsed_ms > 0` | P2 |
| 14 | `test_servicer_dossier_command` | servicer_dossier | Returns dossier data | P1 |
| 15 | `test_save_xml_command` | save_xml with fixture | Creates backup | P1 |

---

## Extension Integration Tests

### Manual F5 QA Checklist

Since VS Code extension tests require the Extension Development Host, Phase 1 uses a manual checklist.

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | Extension activates | F5 → Open chat → Type `@frp` | @frp appears in participant list |
| 2 | /jobs search | `@frp /jobs search rptent` | Returns matching jobs in markdown table |
| 3 | /jobs validate email | `@frp /jobs validate` | Shows validation result with error/warning/info |
| 4 | /jobs validate sftp | `@frp /jobs validate sftp` | Shows SFTP validation result |
| 5 | /jobs no query | `@frp /jobs` | Shows all jobs or prompts for query |
| 6 | /deals servicer | `@frp /deals servicer 150` | Shows servicer dossier |
| 7 | /logs sync | `@frp /logs sync` | Shows sync summary |
| 8 | /deploy backups | `@frp /deploy backups` | Lists backup files |
| 9 | /deploy save | `@frp /deploy save email` | Saves XML, shows backup path |
| 10 | /triage stub | `@frp /triage` | Shows "Coming in Phase 3" message |
| 11 | /analyze stub | `@frp /analyze` | Shows "Coming in Phase 4" message |
| 12 | No slash command | `@frp how many jobs are there?` | Answers using job data (default search) |
| 13 | Follow-ups appear | After /jobs search | Suggestion buttons shown |
| 14 | Settings missing | Remove outlookSettingsPath | Helpful error message |
| 15 | Backend error | Corrupt Python | Error shown in chat, no crash |
| 16 | Output panel | View → Output → FRP Agent | Shows backend logs |

---

## End-to-End Scenarios

### Scenario E2E-1: Job Search Workflow

```
Precondition: Settings.xml configured, extension running
Steps:
1. @frp /jobs search rptent
2. Observe markdown table of matching jobs
3. Click follow-up "validate"
4. @frp /jobs validate
5. Observe validation results
Expected: No errors in settings, jobs found with rptent in filters
```

### Scenario E2E-2: Servicer Dossier

```
Precondition: Settings.xml + DB configured
Steps:
1. @frp /deals servicer 150
2. Observe dossier with: deals table, XML jobs list, log summary
Expected: Shows CompanyID 150 deals from DB + matching XML jobs
```

### Scenario E2E-3: Log Sync + Query

```
Precondition: Log folder configured with sample logs
Steps:
1. @frp /logs sync
2. Observe: "Synced N files, M events indexed"
3. @frp query: what happened with COOFS_LateMoney today?
4. Observe: Recent events for that job
Expected: Sync completes, query returns relevant events
```

### Scenario E2E-4: Backup + Restore Cycle

```
Precondition: Settings.xml exists
Steps:
1. @frp /deploy save email
2. Observe: "Saved. Backup at: <path>"
3. @frp /deploy backups
4. Observe: List with at least 1 backup
```

### Scenario E2E-5: Graceful Degradation

```
Precondition: DB settings incorrect (connection will fail)
Steps:
1. @frp /jobs search test
2. Expected: Jobs returned (search doesn't need DB)
3. @frp /jobs validate
4. Expected: Validation works but shows "DB cross-reference skipped"
5. @frp /deals servicer 150
6. Expected: Error message about DB connection, but no crash
```

---

## Coverage Targets

| Module | Target | Metric |
|--------|--------|--------|
| `backend/xml/models.py` | 100% | Lines |
| `backend/xml/parser.py` | 95% | Lines |
| `backend/xml/writer.py` | 95% | Lines |
| `backend/backup/manager.py` | 95% | Lines |
| `backend/db/connection.py` | 90% | Lines |
| `backend/db/deal_repo.py` | 90% | Lines |
| `backend/logs/parser.py` | 95% | Lines |
| `backend/logs/indexer.py` | 95% | Lines |
| `cli/main.py` | 90% | Lines |
| **Overall** | **93%+** | **Lines** |

### Run Coverage

```powershell
pytest tests/ --cov=backend --cov=cli --cov-report=term-missing --cov-report=html
```

---

## Test Execution Summary

| Category | Test Count | Estimated Time |
|----------|-----------|---------------|
| XML Parser | 40 | 2 min |
| XML Validator | 27 | 1 min |
| XML Writer | 9 | 30 sec |
| Backup Manager | 11 | 30 sec |
| DB Connector | 7 | 15 sec |
| Deal Repository | 11 | 15 sec |
| Log Parser | 21 | 1 min |
| SQLite Indexer | 21 | 1 min |
| CLI | 15 | 1 min |
| Manual Extension | 16 | 20 min |
| **Total Automated** | **162** | **~7 min** |
| **Total with Manual** | **178** | **~27 min** |
