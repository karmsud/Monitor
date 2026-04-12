# Phase 2: Implementation Plan
## FRP Agent — CRUD & Intelligence Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Sprint Numbering:** Continues from Phase 1 (Sprints 1–7). Phase 2 = Sprints 8–14.

---

## Table of Contents
1. [Implementation Principles](#1-implementation-principles)
2. [Prerequisites](#2-prerequisites)
3. [Sprint Structure](#3-sprint-structure)
4. [Step-by-Step Build Order](#4-step-by-step-build-order)
5. [Verification Checkpoints](#5-verification-checkpoints)
6. [Rollback Strategy](#6-rollback-strategy)

---

## 1. Implementation Principles

1. **Phase 1 is frozen** — Do not modify Phase 1 modules' public interfaces. Only add new methods/classes.
2. **Test before integrate** — Each new module gets unit tests BEFORE wiring into CLI commands.
3. **Read-only first** — Build all read-only intelligence (D-01, D-02, D-03, J-04) before mutation operations (J-02, J-03).
4. **Confirmation is mandatory** — Never auto-save XML from a create/edit/rollback without user confirmation flow.
5. **One module per sprint** — Keep sprints focused. Each sprint produces a testable, isolated module.

---

## 2. Prerequisites

### Phase 1 Gate

All Phase 1 verification checkpoints must pass before starting Phase 2:

```
✅ CP-1: Data models importable
✅ CP-2: XML parser handles both formats
✅ CP-3: Validator detects all error codes
✅ CP-4: Writer creates backups
✅ CP-5: DB connector works (both modes)
✅ CP-6: Deal repository returns data
✅ CP-7: Log parser extracts events
✅ CP-8: CLI returns JSON
✅ CP-FINAL: F5 Extension Dev Host works
```

### Workspace Ready

```powershell
# Verify Phase 1 tests pass
cd FRP_Agent
python -m pytest tests/ -v --tb=short
# Expected: 162+ tests pass, 93%+ coverage

# Verify CLI commands work
python -m cli.main search_jobs --query "all" --settings-path "path/to/Settings.xml"
python -m cli.main validate_xml --settings-path "path/to/Settings.xml"
```

---

## 3. Sprint Structure

| Sprint | Description | Hours | Key Deliverables |
|--------|-------------|-------|-----------------|
| Sprint 8 | Intel Data Models | 2–3h | `intel/models.py`, `xml/models.py` additions |
| Sprint 9 | Template Inventory | 3–4h | `xml/templates.py`, `cmd_template_inventory` |
| Sprint 10 | Coverage Intelligence | 5–7h | `intel/coverage.py`, `intel/orphans.py`, `intel/collisions.py` |
| Sprint 11 | Job CRUD Engine | 5–7h | `xml/crud.py`, `cmd_create_job`, `cmd_edit_job` |
| Sprint 12 | XML Diff & Rollback | 4–5h | `xml/diff.py`, `xml/rollback.py` |
| Sprint 13 | Extension Handlers | 4–5h | Participant.js subcommand handlers, confirmations |
| Sprint 14 | Integration Testing | 4–5h | E2E tests, manual QA |
| **Total** | | **27–36h** | |

---

## 4. Step-by-Step Build Order

### Sprint 8: Intel Data Models (2–3 hours)

**Goal:** Define all Phase 2 data models and verify serialization.

#### Step 8.1: Create intel/models.py

```bash
# Create the intel module directory
mkdir -p backend/intel
touch backend/intel/__init__.py
```

Create `backend/intel/models.py` with:
- `CoverageReport` dataclass
- `OrphanResult` dataclass
- `CollisionResult` dataclass
- `IntelSummary` dataclass

All with `to_dict()` methods.

#### Step 8.2: Extend xml/models.py

Add to existing `backend/xml/models.py`:
- `JobTemplate` dataclass
- `FieldChange` dataclass
- `JobDiff` dataclass
- `DiffResult` dataclass
- `CrudResult` dataclass

#### Step 8.3: Test Data Models

```python
# tests/intel/test_models.py
def test_coverage_report_serialization():
    report = CoverageReport(
        servicer_id=150, total_dids=45, mapped_dids=42,
        unmapped_dids=[{"did": 12345, "import_did": "CSMC2020"}],
        coverage_percentage=93.3, matching_jobs=["Job A"]
    )
    d = report.to_dict()
    assert d["servicer_id"] == 150
    assert d["coverage_percentage"] == 93.3
    assert len(d["unmapped_dids"]) == 1

def test_diff_result_total_changes():
    result = DiffResult(
        current_file="a.xml", backup_file="b.xml",
        added_jobs=[JobDiff("New", "added")],
        removed_jobs=[],
        modified_jobs=[JobDiff("Changed", "modified", [FieldChange("x", "1", "2")])],
    )
    assert result.total_changes == 2
```

Expected: ~20 tests for all model classes.

---

### Sprint 9: Template Inventory (3–4 hours)

**Goal:** Discover and catalog template patterns from existing jobs.

#### Step 9.1: Build xml/templates.py

Implement `TemplateInventory` class:
- `discover_templates()` — signature-based grouping
- `_compute_signature()` — hash based on parsers + templates + has_sid
- `_compute_pattern_name()` — human-readable label
- `_extract_sample_fields()` — key config values

#### Step 9.2: Wire CLI Command

Add `template_inventory` to `cli/main.py`:

```bash
# Test command
python -m cli.main template_inventory \
  --settings-path "Settings.xml" \
  --xml-type email
```

Expected output:
```json
{
  "success": true,
  "data": {
    "templates": [ ... ],
    "total_templates": 8,
    "total_jobs": 48
  }
}
```

#### Step 9.3: Test

```python
# tests/xml/test_templates.py
# Use email_settings_valid.xml fixture

def test_discover_templates_groups_by_parsers(sample_settings_path):
    inventory = TemplateInventory(sample_settings_path, "email")
    templates = inventory.discover_templates()
    assert len(templates) > 0
    assert all(t.job_count >= 1 for t in templates)
    assert sum(t.job_count for t in templates) == 48  # total jobs

def test_filter_narrows_results(sample_settings_path):
    inventory = TemplateInventory(sample_settings_path, "email")
    all_templates = inventory.discover_templates()
    filtered = inventory.discover_templates(filter_query="rptent")
    assert len(filtered) <= len(all_templates)
```

Expected: ~15 tests.

---

### Sprint 10: Coverage Intelligence (5–7 hours)

**Goal:** Build all three intel analyzers. This is the heaviest sprint.

#### Step 10.1: Add DB Repository Methods

Add to `backend/db/deal_repo.py`:
- `get_companies_by_import_did(keyword)` — returns list of CompanyIDs matching an ImportDID
- `get_all_distinct_company_ids()` — returns all unique CompanyIDs

Add to `backend/db/queries.py`:
- `GET_COMPANIES_BY_IMPORT_DID` SQL constant
- `GET_ALL_DISTINCT_COMPANY_IDS` SQL constant

Test with mocked pyodbc connection.

#### Step 10.2: Build intel/coverage.py

Implement `CoverageAnalyzer`:
- `analyze(servicer_id)` — main entry point
- `_analyze_servicer()` — per-servicer analysis
- `_is_covered()` — static keyword match logic

```bash
# Test command
python -m cli.main coverage_gaps \
  --settings-path "Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json" \
  --servicer-id 150
```

#### Step 10.3: Build intel/orphans.py

Implement `OrphanDetector`:
- `detect()` — find jobs with invalid ServicerIDs

```bash
python -m cli.main orphan_detection \
  --settings-path "Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json"
```

#### Step 10.4: Build intel/collisions.py

Implement `CollisionDetector`:
- `detect()` — find ImportDID keyword overlaps

```bash
python -m cli.main collision_detection \
  --settings-path "Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json"
```

#### Step 10.5: Test

```python
# tests/intel/test_coverage.py — Mock DB, real XML fixtures
# tests/intel/test_orphans.py — Mock DB with missing CompanyIDs
# tests/intel/test_collisions.py — Mock DB with overlapping ImportDIDs
```

Testing approach:
- Mock `DealRepository` to return controlled data
- Use test XML fixtures with known ServicerIDs and ImportDIDs
- Verify batch patterns (same ImportDID + same CompanyID) are NOT flagged

Expected: ~44 tests across 3 files.

---

### Sprint 11: Job CRUD Engine (5–7 hours)

**Goal:** Create and edit jobs in Settings.xml with safety mechanisms.

#### Step 11.1: Build xml/crud.py

Implement `JobCrudEngine`:
- `create_job()` — deep copy + override + save
- `edit_job()` — find + modify + save
- `get_job_preview()` — read-only preview for confirmation
- `_find_job_element()` — exact name match
- `_fuzzy_find_jobs()` — substring match for disambiguation

#### Step 11.2: Wire CLI Commands

```bash
# Create job
python -m cli.main create_job \
  --settings-path "Settings.xml" \
  --template-job "CSMC 2015-1 rptent" \
  --name "Test New Job" \
  --servicer-id 999

# Edit job
python -m cli.main edit_job \
  --settings-path "Settings.xml" \
  --job-name "Test New Job" \
  --field servicer_id \
  --value "225"
```

#### Step 11.3: Test (using tmp_path for write safety)

```python
# tests/xml/test_crud.py

def test_create_job_from_template(tmp_settings_path):
    engine = JobCrudEngine(str(tmp_settings_path), "email")
    result = engine.create_job(
        template_job_name="CSMC 2015-1 rptent",
        new_job_name="Test Job",
        overrides={"servicer_id": "999"},
    )
    assert result.operation == "create"
    assert result.job_name == "Test Job"
    assert result.backup_file  # backup was created
    # Verify job exists in re-parsed XML
    parser = SettingsXmlParser(str(tmp_settings_path))
    found = parser.search_jobs("Test Job")
    assert len(found) == 1
    assert found[0].servicer_id == "999"

def test_create_duplicate_raises(tmp_settings_path):
    engine = JobCrudEngine(str(tmp_settings_path), "email")
    with pytest.raises(ValueError, match="already exists"):
        engine.create_job("CSMC 2015-1 rptent", "CSMC 2015-1 rptent")

def test_edit_job_changes_field(tmp_settings_path):
    engine = JobCrudEngine(str(tmp_settings_path), "email")
    result = engine.edit_job("CSMC 2015-1 rptent", "servicer_id", "999")
    assert result.changes[0].old_value == "150"
    assert result.changes[0].new_value == "999"

def test_edit_ambiguous_raises(tmp_settings_path):
    # If multiple jobs match "CSMC", should raise with match list
    engine = JobCrudEngine(str(tmp_settings_path), "email")
    with pytest.raises(ValueError, match="Ambiguous"):
        engine.edit_job("CSMC", "servicer_id", "999")
```

Expected: ~25 tests.

---

### Sprint 12: XML Diff & Rollback (4–5 hours)

**Goal:** Job-level comparison and safe restore from backups.

#### Step 12.1: Build xml/diff.py

Implement `XmlDiffEngine`:
- `diff()` — compare two XML files
- `_compare_jobs()` — field-by-field comparison

#### Step 12.2: Build xml/rollback.py

Implement `RollbackHandler`:
- `preview()` — show diff without modifying
- `execute()` — backup current + restore + validate

#### Step 12.3: Wire CLI Commands

```bash
# Diff
python -m cli.main xml_diff \
  --settings-path "Settings.xml" \
  --backup-file "backup/Settings_20260201_120000.xml"

# Rollback
python -m cli.main rollback_xml \
  --settings-path "Settings.xml" \
  --backup-file "backup/Settings_20260201_120000.xml"
```

#### Step 12.4: Test

```python
# tests/xml/test_diff.py

def test_diff_detects_added_job(tmp_path):
    # Create two XML files: backup without job, current with job
    ...
    result = engine.diff(str(current_path), str(backup_path))
    assert len(result.added_jobs) == 1
    assert result.added_jobs[0].change_type == "added"

def test_diff_detects_field_change(tmp_path):
    ...
    result = engine.diff(str(current_path), str(backup_path))
    assert len(result.modified_jobs) == 1
    assert result.modified_jobs[0].field_changes[0].field == "servicer_id"

# tests/xml/test_rollback.py

def test_rollback_creates_safety_backup(tmp_path):
    handler = RollbackHandler(str(current_path), "email")
    result = handler.execute(str(backup_path))
    assert result["safety_backup"]  # safety backup was created before restore
    # Verify current file now matches backup content

def test_rollback_validates_after_restore(tmp_path):
    handler = RollbackHandler(str(current_path), "email")
    result = handler.execute(str(backup_path))
    assert result["validation"] is not None
```

Expected: ~28 tests.

---

### Sprint 13: Extension Handlers (4–5 hours)

**Goal:** Wire all Phase 2 backend commands into the extension.

#### Step 13.1: Update tool.js Parameter Mappings

Add Phase 2 parameter mappings to `backendCall()`.

#### Step 13.2: Add /jobs Subcommand Handlers

- `handleJobCreate()` — parse "create X from Y", preview, confirm, execute
- `handleJobEdit()` — parse "edit X set Y Z", preview, confirm, execute
- `handleJobTemplates()` — call `template_inventory`, format response

#### Step 13.3: Add /deals Subcommand Handlers

- `handleCoverageGaps()` — parse servicer ID, call backend, format
- `handleOrphanDetection()` — call backend, format
- `handleCollisionDetection()` — call backend, format

#### Step 13.4: Add /deploy Subcommand Handlers

- `handleXmlDiff()` — call backend, format diff output
- `handleRollback()` — show diff first, confirm, execute

#### Step 13.5: Update Follow-Up Suggestions

| After Command | New Follow-Ups |
|---------------|---------------|
| `/jobs create` | "edit {name}", "validate" |
| `/jobs edit` | "validate", "diff" |
| `/jobs templates` | "create {pattern} from {example}" |
| `/deals gaps N` | "orphans", "collisions", "servicer N" |
| `/deals orphans` | "gaps all", "collisions" |
| `/deals collisions` | "gaps all", "orphans" |
| `/deploy diff` | "rollback {file}", "backups" |
| `/deploy rollback` | "diff", "validate" |

#### Step 13.6: F5 Manual Testing

Press F5, test each new subcommand in the Extension Development Host.

---

### Sprint 14: Integration Testing (4–5 hours)

**Goal:** End-to-end verification and edge case testing.

#### E2E Scenarios

1. **Full CRUD cycle**: Create job → edit field → validate → diff → rollback
2. **Coverage analysis pipeline**: Search jobs → gaps for servicer → check orphans
3. **Collision + gap combined**: Run collisions → investigate affected servicer gaps
4. **Template → create workflow**: List templates → create from template → edit
5. **Diff + rollback safety**: Save → make changes → diff → rollback → verify restored

---

## 5. Verification Checkpoints

| CP# | Checkpoint | Sprint | Verification |
|-----|-----------|--------|--------------|
| CP-9 | Intel models serialize correctly | Sprint 8 | `pytest tests/intel/test_models.py` — all pass |
| CP-10 | Template inventory discovers patterns | Sprint 9 | CLI returns correct template count for test fixture |
| CP-11 | Coverage gaps detected with mock DB | Sprint 10 | Known unmapped DIDs appear in result |
| CP-12 | Orphans detected (mock DB missing IDs) | Sprint 10 | Known orphan jobs appear, shelf-level excluded |
| CP-13 | Collisions detected (mock overlaps) | Sprint 10 | Batch patterns excluded, real collisions caught |
| CP-14 | Create job adds valid XML element | Sprint 11 | Re-parsed XML contains new job with correct fields |
| CP-15 | Edit job modifies only target field | Sprint 11 | Other fields unchanged after edit |
| CP-16 | Diff shows meaningful job changes | Sprint 12 | Added/removed/modified jobs correctly classified |
| CP-17 | Rollback creates safety backup | Sprint 12 | Two backup files exist after rollback |
| CP-18 | Confirmation dialogs fire for mutations | Sprint 13 | F5 test: create/edit/rollback all prompt user |
| CP-FINAL-P2 | Full E2E cycle works in Extension Host | Sprint 14 | All 5 E2E scenarios pass manually |

---

## 6. Rollback Strategy

### Sprint-Level Rollback

| Sprint | If It Fails | Recovery |
|--------|-------------|----------|
| Sprint 8 | Model definitions wrong | Fix dataclass fields; no dependencies yet |
| Sprint 9 | Template grouping incorrect | Adjust signature hash; standalone module |
| Sprint 10 | DB queries fail | Fix SQL; mock tests should catch this early |
| Sprint 11 | CRUD corrupts XML | revert crud.py changes; XML fixtures are temp copies |
| Sprint 12 | Diff misclassifies changes | Adjust comparison logic; isolated module |
| Sprint 13 | Extension handlers fail | Revert participant.js; Phase 1 handlers still work |
| Sprint 14 | E2E tests reveal issues | Fix in targeted sprints; no new features at risk |

### Minimum Viable Phase 2

If time is constrained, deliver in this priority order:

1. **Must have:** Template inventory (J-04) — read-only, low risk
2. **Must have:** Coverage gaps (D-01) — highest business value
3. **Must have:** Orphan detection (D-02) — high business value
4. **Should have:** XML diff (X-02) — important for change tracking
5. **Should have:** Job edit (J-03) — high utility, moderate risk
6. **Could defer:** Job create (J-02) — can use manual copy + edit instead
7. **Could defer:** Collision detection (D-03) — nice to have
8. **Could defer:** Rollback (X-03) — can manually copy backup files

---

*Next document: [05_TESTING_PLAN.md](05_TESTING_PLAN.md)*
