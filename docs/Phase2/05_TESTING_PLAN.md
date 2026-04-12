# Phase 2: Testing Plan
## FRP Agent — CRUD & Intelligence Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Total Tests:** 154 automated + 16 manual = 170 tests  
**Target Coverage:** ≥90% for Phase 2 modules

---

## Table of Contents
1. [Test Strategy](#1-test-strategy)
2. [Test Infrastructure](#2-test-infrastructure)
3. [Intel Models Tests](#3-intel-models-tests)
4. [Template Inventory Tests](#4-template-inventory-tests)
5. [Coverage Gap Tests](#5-coverage-gap-tests)
6. [Orphan Detection Tests](#6-orphan-detection-tests)
7. [Collision Detection Tests](#7-collision-detection-tests)
8. [Job CRUD Tests](#8-job-crud-tests)
9. [XML Diff Tests](#9-xml-diff-tests)
10. [Rollback Tests](#10-rollback-tests)
11. [CLI Command Tests](#11-cli-command-tests)
12. [Extension Manual QA](#12-extension-manual-qa)
13. [End-to-End Scenarios](#13-e2e-scenarios)
14. [Coverage Targets](#14-coverage-targets)

---

## 1. Test Strategy

| Layer | Framework | Approach | Target |
|-------|-----------|----------|--------|
| Data Models | pytest | Direct construction + serialization | 100% |
| XML Operations | pytest | Real XML fixtures in tmp_path | 95% |
| Intel Analysis | pytest | Mock DealRepository, real XML fixtures | 95% |
| CLI Commands | pytest + subprocess | JSON output validation | 90% |
| Extension JS | Manual F5 | Extension Development Host | Checklist |

### Key Testing Principles

1. **Never write to real Settings.xml** — All write tests use `tmp_path` copies
2. **Mock the database** — DealRepository is mocked with controlled data
3. **Test the collision exclusion** — Batch patterns (same ImportDID + same CompanyID) must NOT trigger collisions
4. **Test disambiguation** — Fuzzy job matching must handle ambiguous cases
5. **Test safety mechanisms** — Backup creation, confirmation flow, post-mutation validation

---

## 2. Test Infrastructure

### New Test Fixtures (conftest.py additions)

```python
# tests/conftest.py — Phase 2 additions

import pytest
import shutil
from unittest.mock import MagicMock
from backend.db.deal_repo import DealRepository

@pytest.fixture
def mock_deal_repo():
    """Mock DealRepository for intel tests."""
    repo = MagicMock(spec=DealRepository)
    
    # Default data: 3 companies, some deals
    repo.get_all_servicer_ids.return_value = [100, 150, 200]
    
    repo.get_deals_by_company.side_effect = lambda cid: {
        100: [
            {"DID": 1001, "ImportDID": "ACME", "CompanyID": 100},
            {"DID": 1002, "ImportDID": "ACME", "CompanyID": 100},
        ],
        150: [
            {"DID": 2001, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2002, "ImportDID": "CSMC", "CompanyID": 150},
            {"DID": 2003, "ImportDID": "CSFB", "CompanyID": 150},  # different ImportDID
        ],
        200: [],  # exists but no deals
    }.get(cid, [])
    
    repo.get_companies_by_import_did.side_effect = lambda kw: {
        "ACME": [100],
        "CSMC": [150],
        "CSFB": [150],
        "OVERLAP": [100, 150, 200],  # collision keyword
    }.get(kw.upper(), [])
    
    repo.check_servicer_exists.side_effect = lambda sid: sid in [100, 150, 200]
    
    return repo


@pytest.fixture
def tmp_settings_path(tmp_path, sample_email_settings_path):
    """Copy sample Settings.xml to tmp_path for write tests."""
    dest = tmp_path / "Settings.xml"
    shutil.copy(sample_email_settings_path, dest)
    return dest


@pytest.fixture
def tmp_backup_path(tmp_path, sample_email_settings_path):
    """Create a backup copy for diff/rollback tests."""
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    backup = backup_dir / "Settings_20260201_120000.xml"
    shutil.copy(sample_email_settings_path, backup)
    return backup
```

### Test File Organization

```
tests/
├── conftest.py                     # Updated with Phase 2 fixtures
├── intel/
│   ├── __init__.py
│   ├── test_models.py              # CoverageReport, OrphanResult, etc.
│   ├── test_coverage.py            # CoverageAnalyzer tests
│   ├── test_orphans.py             # OrphanDetector tests
│   └── test_collisions.py          # CollisionDetector tests
├── xml/
│   ├── test_models_p2.py           # Phase 2 model additions
│   ├── test_templates.py           # TemplateInventory tests
│   ├── test_crud.py                # JobCrudEngine tests
│   ├── test_diff.py                # XmlDiffEngine tests
│   └── test_rollback.py            # RollbackHandler tests
├── db/
│   └── test_deal_repo_p2.py        # New query methods
└── cli/
    └── test_main_p2.py             # Phase 2 CLI commands
```

---

## 3. Intel Models Tests

### tests/intel/test_models.py — 12 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_coverage_report_serialization | CoverageReport with data | to_dict() has all fields | P1 |
| 2 | test_coverage_report_zero_dids | total_dids=0 | coverage_percentage=0.0 | P1 |
| 3 | test_orphan_result_serialization | OrphanResult | to_dict() matches | P1 |
| 4 | test_collision_result_serialization | CollisionResult with 3 companies | risk_level="high" | P1 |
| 5 | test_collision_risk_medium | CollisionResult with 2 companies | risk_level="medium" | P1 |
| 6 | test_intel_summary_aggregation | IntelSummary with mixed data | to_dict() includes all lists | P1 |
| 7 | test_job_template_serialization | JobTemplate | to_dict() complete | P1 |
| 8 | test_field_change_serialization | FieldChange | old/new values preserved | P1 |
| 9 | test_job_diff_added | JobDiff(change_type="added") | No field_changes | P1 |
| 10 | test_job_diff_modified | JobDiff with changes | field_changes populated | P1 |
| 11 | test_diff_result_total_changes | DiffResult with mixed | total_changes is sum | P1 |
| 12 | test_crud_result_serialization | CrudResult with validation | validation dict included | P1 |

---

## 4. Template Inventory Tests

### tests/xml/test_templates.py — 15 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_discover_returns_templates | Valid email XML | Non-empty template list | P1 |
| 2 | test_total_job_count_matches | Valid email XML | sum(job_count) = total jobs | P1 |
| 3 | test_templates_sorted_by_count | Valid email XML | First template has highest count | P1 |
| 4 | test_each_template_has_example | Valid email XML | example_job_name is non-empty | P1 |
| 5 | test_parser_names_populated | Valid email XML | At least one parser per template | P1 |
| 6 | test_filter_by_parser | filter="MailToFolder" | Only templates with that parser | P2 |
| 7 | test_filter_no_match | filter="nonexistent" | Empty list | P2 |
| 8 | test_has_servicer_id_flag | Valid email XML | Some true, some false | P1 |
| 9 | test_sample_fields_extracted | Valid email XML | subject_filter, sender_filter present | P2 |
| 10 | test_mailbox_pattern_varies | Jobs with different mailboxes | mailbox_pattern="varies" | P2 |
| 11 | test_mailbox_pattern_single | Jobs with same mailbox | Actual mailbox string | P2 |
| 12 | test_sftp_templates | Valid SFTP XML | Templates discovered for SFTP | P1 |
| 13 | test_empty_xml | XML with no jobs | Empty template list | P1 |
| 14 | test_single_job_xml | XML with one job | One template, job_count=1 | P2 |
| 15 | test_pattern_name_format | Valid email XML | "ParserName — TemplateName" format | P2 |

---

## 5. Coverage Gap Tests

### tests/intel/test_coverage.py — 18 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_full_coverage | All DIDs matched | coverage_percentage=100.0 | P1 |
| 2 | test_partial_coverage | 2 of 3 DIDs matched | coverage_percentage=66.7 | P1 |
| 3 | test_no_coverage | 0 DIDs matched | coverage_percentage=0.0, all unmapped | P1 |
| 4 | test_unmapped_dids_listed | Known unmapped | unmapped_dids has correct entries | P1 |
| 5 | test_matching_jobs_listed | Jobs with target servicer | matching_jobs populated | P1 |
| 6 | test_single_servicer | servicer_id=150 | Only one report returned | P1 |
| 7 | test_all_servicers | servicer_id=None | Reports for all servicers in XML | P1 |
| 8 | test_servicer_not_in_xml | servicer_id=999 | Report with 0 matching_jobs | P2 |
| 9 | test_case_insensitive_match | ImportDID "csmc" vs "CSMC" | Match succeeds | P1 |
| 10 | test_whitespace_trimmed | ImportDID " CSMC " | Match succeeds after trim | P2 |
| 11 | test_empty_import_did_not_matched | DID with empty ImportDID | Not counted as covered | P1 |
| 12 | test_no_deals_in_db | DB returns empty list | total_dids=0, coverage=0 | P2 |
| 13 | test_db_error_graceful | Mock raises exception | Error propagated cleanly | P2 |
| 14 | test_is_covered_exact_match | "CSMC" matches "CSMC" | True | P1 |
| 15 | test_is_covered_no_match | "CSMC" vs "ACME" | False | P1 |
| 16 | test_is_covered_empty_keyword | "" vs "CSMC" | False | P1 |
| 17 | test_multiple_jobs_same_servicer | 3 jobs, servicer 150 | All jobs in matching_jobs | P2 |
| 18 | test_import_did_keyword_overlap | Job keyword covers multiple DIDs | All matching DIDs counted | P1 |

---

## 6. Orphan Detection Tests

### tests/intel/test_orphans.py — 12 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_no_orphans | All ServicerIDs valid | Empty list | P1 |
| 2 | test_orphan_no_db_match | ServicerID=999 not in DB | Orphan with reason="no_db_match" | P1 |
| 3 | test_orphan_no_deal_data | ServicerID=200 exists, 0 deals | Orphan with reason="no_deal_data" | P1 |
| 4 | test_jobs_without_servicer_excluded | Jobs with empty ServicerID | NOT in orphan list | P1 |
| 5 | test_multiple_orphans | 3 invalid ServicerIDs | 3 OrphanResult entries | P1 |
| 6 | test_mixed_valid_and_orphan | Some valid, some orphaned | Only orphans returned | P1 |
| 7 | test_non_numeric_servicer_id | ServicerID="abc" | Orphan with reason="invalid_servicer_id" | P2 |
| 8 | test_orphan_xml_type_preserved | xml_type="sftp" | OrphanResult.xml_type=="sftp" | P2 |
| 9 | test_orphan_job_name_correct | Known orphan job | Correct job_name in result | P1 |
| 10 | test_db_error_during_check | Mock raises on get_deals_by_company | Error handled gracefully | P2 |
| 11 | test_large_valid_servicer_set | 1000 valid CompanyIDs | No false positives | P2 |
| 12 | test_empty_xml | No jobs in XML | Empty orphan list | P2 |

---

## 7. Collision Detection Tests

### tests/intel/test_collisions.py — 14 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_no_collisions | All unique ImportDIDs | Empty list | P1 |
| 2 | test_collision_two_companies | ImportDID "OVERLAP" matches 2 CompanyIDs | 1 collision, risk="medium" | P1 |
| 3 | test_collision_three_companies | ImportDID matches 3+ CompanyIDs | risk="high" | P1 |
| 4 | test_batch_not_flagged | Same ImportDID, same CompanyID, multiple DIDs | NOT a collision | P1 |
| 5 | test_affected_jobs_listed | Collision keyword used by 2 jobs | Both job names in affected_jobs | P1 |
| 6 | test_deal_counts_per_company | Collision with varying deal counts | deal_counts dict accurate | P2 |
| 7 | test_sorted_by_risk | Mix of high and medium | High risk first | P2 |
| 8 | test_case_insensitive_keyword | "overlap" vs DB "OVERLAP" | Collision detected | P1 |
| 9 | test_empty_import_did_skipped | Jobs with empty ImportDID | Skipped, not queried | P2 |
| 10 | test_multiple_collisions | 3 different colliding keywords | 3 CollisionResult entries | P2 |
| 11 | test_single_company_not_collision | ImportDID matches only 1 CompanyID | Not a collision | P1 |
| 12 | test_db_error_graceful | Mock raises exception | Error handled | P2 |
| 13 | test_whitespace_in_keyword | ImportDID " OVERLAP " | Trimmed, collision detected | P2 |
| 14 | test_keyword_job_mapping | 2 jobs share same ImportDID | Both in affected_jobs | P1 |

---

## 8. Job CRUD Tests

### tests/xml/test_crud.py — 25 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_create_from_template | Valid template + new name | New job exists in XML | P1 |
| 2 | test_create_sets_name | Template + custom name | New job has correct name | P1 |
| 3 | test_create_with_overrides | servicer_id override | Override applied | P1 |
| 4 | test_create_backup_created | Any create | Backup file exists | P1 |
| 5 | test_create_validation_runs | Any create | validation field populated | P1 |
| 6 | test_create_duplicate_raises | Existing name | ValueError | P1 |
| 7 | test_create_template_not_found | Non-existent template | ValueError | P1 |
| 8 | test_create_preserves_other_jobs | Create one | Other jobs unchanged | P1 |
| 9 | test_create_multiple_overrides | 3 overrides | All applied | P2 |
| 10 | test_create_unknown_override_skipped | Unknown field name | Warning logged, skipped | P2 |
| 11 | test_edit_changes_field | Edit servicer_id | Old → new value | P1 |
| 12 | test_edit_backup_created | Any edit | Backup file exists | P1 |
| 13 | test_edit_validation_runs | Any edit | validation field populated | P1 |
| 14 | test_edit_preserves_other_fields | Edit one field | Other fields unchanged | P1 |
| 15 | test_edit_exact_match | Exact job name | Correct job edited | P1 |
| 16 | test_edit_fuzzy_single_match | Partial name, 1 match | Correct job edited | P2 |
| 17 | test_edit_ambiguous_raises | Partial name, 2+ matches | ValueError with match list | P1 |
| 18 | test_edit_not_found_raises | Non-existent job | ValueError | P1 |
| 19 | test_edit_invalid_field_raises | Non-editable field | ValueError with field list | P1 |
| 20 | test_edit_creates_element_if_missing | Field element doesn't exist | Element created | P2 |
| 21 | test_get_job_preview | Existing job | Dict with all fields | P2 |
| 22 | test_get_job_preview_not_found | Non-existent job | ValueError | P2 |
| 23 | test_create_sftp_job | SFTP template | SFTP job created | P2 |
| 24 | test_edit_sftp_job | SFTP job field | Field changed | P2 |
| 25 | test_crud_result_to_dict | After create | Serializable dict | P1 |

---

## 9. XML Diff Tests

### tests/xml/test_diff.py — 18 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_identical_files | Same file twice | No changes, all unchanged | P1 |
| 2 | test_added_job | Current has extra job | 1 added, 0 removed | P1 |
| 3 | test_removed_job | Backup has extra job | 0 added, 1 removed | P1 |
| 4 | test_modified_servicer_id | Different ServicerID | 1 modified, field change shown | P1 |
| 5 | test_modified_multiple_fields | 3 fields changed | 1 modified with 3 field_changes | P1 |
| 6 | test_mixed_changes | 1 added, 1 removed, 1 modified | All categories populated | P1 |
| 7 | test_unchanged_count | 45 identical, 3 changed | unchanged_count=45 | P1 |
| 8 | test_total_changes_property | Mixed changes | total_changes = sum of all | P1 |
| 9 | test_parser_change_detected | Different parser set | field "parsers" in changes | P2 |
| 10 | test_template_change_detected | Different template set | field "templates" in changes | P2 |
| 11 | test_case_sensitive_name_matching | Same name, different case | Treated as different jobs | P2 |
| 12 | test_empty_current | No jobs in current | All backup jobs "removed" | P2 |
| 13 | test_empty_backup | No jobs in backup | All current jobs "added" | P2 |
| 14 | test_both_empty | No jobs in either | No changes | P2 |
| 15 | test_diff_result_serialization | DiffResult | to_dict() complete | P1 |
| 16 | test_field_change_old_new_values | Known change | Exact old/new values | P1 |
| 17 | test_sftp_diff | SFTP XML files | Uses SFTP compare fields | P2 |
| 18 | test_timestamp_populated | Any diff | timestamp is ISO format | P2 |

---

## 10. Rollback Tests

### tests/xml/test_rollback.py — 10 tests

| # | Test Name | Input | Expected | P |
|---|-----------|-------|----------|---|
| 1 | test_preview_returns_diff | Valid backup | DiffResult returned | P1 |
| 2 | test_execute_creates_safety_backup | Valid rollback | Safety backup file exists | P1 |
| 3 | test_execute_restores_content | Rollback to backup | Current file matches backup content | P1 |
| 4 | test_execute_validates_restored | After rollback | validation field populated | P1 |
| 5 | test_execute_backup_not_found | Non-existent backup | FileNotFoundError | P1 |
| 6 | test_execute_preserves_original_as_backup | After rollback | Pre-rollback state in backup dir | P1 |
| 7 | test_execute_invalid_xml_backup | Corrupted backup file | Validation shows errors | P2 |
| 8 | test_rollback_result_structure | After rollback | Has safety_backup, restored_from, validation | P1 |
| 9 | test_rollback_then_diff_shows_changes | After rollback | Diff reflects restoration | P2 |
| 10 | test_double_rollback | Rollback twice | Both safety backups exist | P2 |

---

## 11. CLI Command Tests

### tests/cli/test_main_p2.py — 16 tests

| # | Test Name | Command | Expected | P |
|---|-----------|---------|----------|---|
| 1 | test_create_job_success | create_job --template-job X --name Y | success=true, data.operation="create" | P1 |
| 2 | test_create_job_template_not_found | create_job --template-job "nope" | success=false, error message | P1 |
| 3 | test_edit_job_success | edit_job --job-name X --field Y --value Z | success=true, old/new values | P1 |
| 4 | test_edit_job_not_found | edit_job --job-name "nope" | success=false | P1 |
| 5 | test_template_inventory | template_inventory | success=true, templates list | P1 |
| 6 | test_template_inventory_filter | template_inventory --filter rptent | Filtered results | P2 |
| 7 | test_coverage_gaps_single | coverage_gaps --servicer-id 150 | Report for servicer 150 | P1 |
| 8 | test_coverage_gaps_all | coverage_gaps --servicer-id all | Multiple reports | P2 |
| 9 | test_orphan_detection | orphan_detection | orphans list | P1 |
| 10 | test_collision_detection | collision_detection | collisions list | P1 |
| 11 | test_xml_diff_with_backup | xml_diff --backup-file X | DiffResult | P1 |
| 12 | test_xml_diff_default_latest | xml_diff (no backup arg) | Uses latest backup | P2 |
| 13 | test_xml_diff_no_backups | xml_diff (no backups exist) | Error message | P2 |
| 14 | test_rollback_xml | rollback_xml --backup-file X | Restored + validated | P1 |
| 15 | test_rollback_xml_not_found | rollback_xml --backup-file "nope" | Error | P1 |
| 16 | test_all_commands_return_json | All Phase 2 commands | Valid JSON with success field | P1 |

---

## 12. Extension Manual QA

### F5 Extension Dev Host Checklist — 16 items

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | /jobs templates | Type `@frp /jobs templates` | Table of template patterns displayed |
| 2 | /jobs templates filter | `@frp /jobs templates rptent` | Filtered template list |
| 3 | /jobs create preview | `@frp /jobs create rptent from "CSMC 2015-1 rptent"` | Template preview shown, confirmation dialog |
| 4 | /jobs create confirm | Click "Create" on dialog | Job created, validation shown |
| 5 | /jobs create cancel | Click "Cancel" on dialog | "Job creation cancelled" message |
| 6 | /jobs edit | `@frp /jobs edit "CSMC 2015-1 rptent" set servicer 999` | Confirmation dialog with old → new |
| 7 | /deals gaps | `@frp /deals gaps 150` | Coverage report with percentage |
| 8 | /deals gaps all | `@frp /deals gaps all` | Multiple servicer reports |
| 9 | /deals orphans | `@frp /deals orphans` | Orphan list (or "no orphans found") |
| 10 | /deals collisions | `@frp /deals collisions` | Collision list (or "no collisions") |
| 11 | /deploy diff | `@frp /deploy diff` | Job-level diff displayed |
| 12 | /deploy diff specific | `@frp /deploy diff Settings_20260201_120000.xml` | Diff against specific backup |
| 13 | /deploy rollback | `@frp /deploy rollback Settings_20260201_120000.xml` | Diff shown first, then confirmation |
| 14 | Follow-ups after create | After creating job | "edit", "validate" suggestions appear |
| 15 | Follow-ups after gaps | After gaps result | "orphans", "collisions" suggestions |
| 16 | DB unavailable graceful | Disconnect DB, run /deals gaps | Clear error message, no crash |

---

## 13. End-to-End Scenarios

### E2E-P2-1: Full CRUD Cycle

```
1. @frp /jobs templates              → See available templates
2. @frp /jobs create rptent from "CSMC 2015-1 rptent"
   → Confirm → Job created
3. @frp /jobs edit "New rptent Job" set servicer 225
   → Confirm → Field changed
4. @frp /jobs validate                → Should pass with new job
5. @frp /deploy diff                  → Shows new job as "added"
6. @frp /deploy rollback {backup}     → Restore original state
7. @frp /jobs search "New rptent Job" → Should not find it (rolled back)
```

### E2E-P2-2: Coverage Intelligence Pipeline

```
1. @frp /jobs show all                → List all jobs with ServicerIDs
2. @frp /deals gaps 150              → Coverage report for servicer 150
3. @frp /deals orphans               → Any orphaned jobs?
4. @frp /deals collisions            → Any ImportDID collisions?
5. @frp /deals servicer 150          → Phase 1 dossier for context
```

### E2E-P2-3: Diff + Rollback Safety

```
1. @frp /deploy save email            → Create initial backup
2. @frp /jobs edit "Job X" set servicer 999  → Make a change
3. @frp /deploy diff                  → See change: servicer 150 → 999
4. @frp /deploy rollback {backup}     → Restore original
5. @frp /deploy diff                  → No changes (current matches backup)
6. @frp /deploy backups               → 3 backups now: original, pre-rollback, safety
```

### E2E-P2-4: Template → Create → Customize

```
1. @frp /jobs templates               → Find "MailToFolder — BondReport" pattern
2. @frp /jobs create BondReport from "Example Job"
   → Confirm → Created
3. @frp /jobs edit "New Job" set mailbox new@bank.com
   → Confirm → Updated
4. @frp /jobs edit "New Job" set servicer 300
   → Confirm → Updated
5. @frp /jobs validate                → Validate with new job
6. @frp /deals gaps 300              → Check coverage for new servicer
```

### E2E-P2-5: Collision Investigation

```
1. @frp /deals collisions            → Find collision on ImportDID "OVERLAP"
2. @frp /deals gaps 100              → Check coverage for CompanyID 100
3. @frp /deals gaps 150              → Check coverage for CompanyID 150
4. @frp /jobs search "OVERLAP"       → Find jobs using the colliding keyword
```

---

## 14. Coverage Targets

| Module | File | Target | Tests |
|--------|------|--------|-------|
| Intel Models | `intel/models.py` | 100% | 12 |
| XML Models (P2) | `xml/models.py` additions | 100% | 8 |
| Template Inventory | `xml/templates.py` | 95% | 15 |
| Coverage Analyzer | `intel/coverage.py` | 95% | 18 |
| Orphan Detector | `intel/orphans.py` | 95% | 12 |
| Collision Detector | `intel/collisions.py` | 95% | 14 |
| Job CRUD Engine | `xml/crud.py` | 90% | 25 |
| XML Diff Engine | `xml/diff.py` | 95% | 18 |
| Rollback Handler | `xml/rollback.py` | 90% | 10 |
| CLI (Phase 2) | `cli/main.py` additions | 90% | 16 |
| DB Repository (P2) | `deal_repo.py` additions | 90% | 6 |
| **Total Automated** | | **≥90% avg** | **154** |
| Extension (Manual) | participant.js | Checklist | 16 |
| **Grand Total** | | | **170** |

### Execution Time Estimate

| Category | Tests | Time |
|----------|-------|------|
| Unit tests (models, serialization) | 20 | ~2 min |
| XML operations (file I/O) | 68 | ~5 min |
| Intel analysis (mock DB) | 44 | ~3 min |
| CLI integration | 16 | ~4 min |
| Manual QA | 16 | ~20 min |
| E2E scenarios | 5 | ~15 min |
| **Total** | **170** | **~49 min** |

---

*End of Phase 2 documentation.*
