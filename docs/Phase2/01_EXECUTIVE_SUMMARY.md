# Phase 2: Executive Summary
## FRP Agent — CRUD & Intelligence Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Implemented — 568 tests passing  
**Phase Scope:** Job creation/editing, template inventory, coverage gap analysis, orphan detection, ImportDID collision detection, XML diff, rollback  
**Use Cases Delivered:** J-02, J-03, J-04, D-01, D-02, D-03, X-02, X-03  
**Prerequisites:** Phase 1 (Foundation Layer) completed and verified

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Business Context](#business-context)
3. [Phase 2 Objectives](#phase-2-objectives)
4. [Use Cases Delivered](#use-cases-delivered)
5. [Architecture Evolution](#architecture-evolution)
6. [Risk Assessment](#risk-assessment)
7. [Success Criteria](#success-criteria)
8. [Dependencies & Prerequisites](#dependencies--prerequisites)
9. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Does Phase 2 Add?

Phase 2 transforms the FRP Agent from a **read-only viewer** into an **intelligent operations assistant** with two major capability sets:

1. **CRUD Operations** — Users can create new monitoring jobs, edit existing jobs, and manage XML change history with diff comparison and rollback capabilities.
2. **Coverage Intelligence** — The agent cross-references Settings.xml configurations with the `tblExternalDIDRef` database to identify coverage gaps, orphaned jobs, and ImportDID collisions — problems that previously required manual investigation across multiple systems.

### Why Phase 2 After Phase 1?

Phase 2 depends on every foundation component built in Phase 1:

| Phase 1 Component | Phase 2 Usage |
|-------------------|---------------|
| XML Parser | J-02, J-03, J-04 — read job structures for templates, editing |
| XML Writer & Backup | J-02, J-03, X-02, X-03 — save changes, compare backups |
| DB Connector & Deal Repo | D-01, D-02, D-03 — cross-reference jobs ↔ deals |
| XML Validator | J-02, J-03 — auto-validate after mutations |
| Backup Manager | X-02, X-03 — list backups for diff/rollback |

### What Can Users Do After Phase 2?

At the end of Phase 2, a user can:

1. **`@frp /jobs create rptent from "Exeter Finance" template`** — Create a new job from an existing template with LLM-assisted configuration
2. **`@frp /jobs edit "Exeter - rptent" set servicer 225`** — Modify a specific field on an existing job with automatic backup and validation
3. **`@frp /jobs templates`** — View all available job templates (identified as common patterns), with parser/template combos and frequency analysis
4. **`@frp /deals gaps 150`** — Show which DIDs for CompanyID 150 have no matching jobs
5. **`@frp /deals orphans`** — Find jobs with ServicerIDs that don't exist in the database
6. **`@frp /deals collisions`** — Detect ImportDID strings that match multiple CompanyIDs
7. **`@frp /deploy diff`** — Compare current Settings.xml to the most recent backup, showing added/removed/changed jobs
8. **`@frp /deploy rollback`** — Restore Settings.xml from a specific backup point

---

## Business Context

### Problem Phase 2 Solves

| Problem | Current State | Phase 2 Solution |
|---------|--------------|------------------|
| **Job Creation** | Manually copy/paste XML blocks, prone to typos | Template-based creation with validation |
| **Job Editing** | Open 2,092-line XML in text editor, find the right block | Conversational edit with atomic field changes |
| **Template Knowledge** | Tribal — only experienced team members know patterns | Auto-discover parser/template combinations from existing jobs |
| **Coverage Gaps** | Run manual SQL queries, cross-reference with XML | Single `/deals gaps {servicerID}` command |
| **Orphaned Jobs** | Unknown until a job fails | Proactive detection comparing XML ↔ DB |
| **ImportDID Collisions** | Discovered only during incident investigation | Proactive collision scan across all jobs and DB |
| **Change Tracking** | No diff capability; overwrite with no comparison | Side-by-side job-level diff between current and backup |
| **Rollback** | Manual file replacement, no validation | Guided rollback with confirmation and auto-backup |

### Design Constraints (Carried from Phase 1)

All Phase 1 constraints remain in effect:
- **Never write to database** — All intelligence is read-only against `tblExternalDIDRef`
- **Write only to Settings.xml** — CRUD operations modify XML files only
- **Automatic backup before every write** — Every save_xml call creates a timestamped backup
- **Dual DB mode** — MSSQL (prod) / MySQL (dev), selectable via `frpAgent.prod`
- **Jobs without ServicerID are valid** — Template inventory should categorize them separately

### New Phase 2 Constraint

| Constraint | Detail |
|------------|--------|
| **Confirmation before mutation** | All create/edit/rollback operations MUST prompt the user with a confirmation dialog before modifying Settings.xml |
| **Auto-validate after mutation** | After every create or edit, the full XML validator runs automatically and results are shown |
| **Diff is job-level** | XML diff compares individual jobs, not raw text — meaningful change detection |

---

## Phase 2 Objectives

### Primary Objectives

1. **Job CRUD engine** — Create new jobs from templates, edit existing job fields, with full XML validation
2. **Template inventory** — Auto-discover and catalog all unique parser/template combinations from existing jobs
3. **Coverage gap analysis** — Cross-reference XML ServicerIDs with DB CompanyIDs to find unmapped deals
4. **Orphan detection** — Find jobs whose ServicerIDs don't exist in the database
5. **ImportDID collision detection** — Identify ImportDID strings that would match multiple CompanyIDs
6. **XML diff engine** — Job-level comparison between current settings and any backup
7. **XML rollback** — Restore from backup with confirmation, auto-backup-before-rollback, and post-rollback validation

### Secondary Objectives

1. **LLM-assisted job creation guidance** — Use Copilot to suggest configuration values based on templates and natural language descriptions
2. **Coverage statistics dashboard** — Summary stats: total jobs, mapped vs unmapped, coverage percentage
3. **Change audit trail** — Log all CRUD operations to output channel for accountability

---

## Use Cases Delivered

### J-02: Create New Job from Template

| Attribute | Value |
|-----------|-------|
| **ID** | J-02 |
| **Category** | Job Management |
| **Phase** | 2 |
| **Slash Command** | `/jobs create` |
| **Trigger** | `@frp /jobs create rptent from "Exeter Finance" template` |
| **Inputs** | Parser keyword (e.g., "rptent"), optional template source job name |
| **Backend Commands** | `search_jobs` (find template), `create_job`, `validate_xml`, `save_xml` |
| **Data Sources** | Settings.xml (read template, write new job), Copilot LLM (assist config) |
| **Output** | New job XML block added, validation result shown, follow-up: edit fields |
| **Confirmation** | Required — "Create job 'New Job Name'?" dialog before save |

### J-03: Edit Existing Job

| Attribute | Value |
|-----------|-------|
| **ID** | J-03 |
| **Category** | Job Management |
| **Phase** | 2 |
| **Slash Command** | `/jobs edit` |
| **Trigger** | `@frp /jobs edit "Exeter - rptent" set servicer 225` |
| **Inputs** | Job name/partial match, field name, new value |
| **Backend Commands** | `search_jobs` (find target), `edit_job`, `validate_xml`, `save_xml` |
| **Data Sources** | Settings.xml (read/write), Copilot LLM (confirm changes) |
| **Output** | Changed fields highlighted (before → after), validation result, follow-up: more edits |
| **Confirmation** | Required — "Apply changes to job 'Exeter - rptent'?" dialog |

### J-04: Template Inventory

| Attribute | Value |
|-----------|-------|
| **ID** | J-04 |
| **Category** | Job Management |
| **Phase** | 2 |
| **Slash Command** | `/jobs templates` |
| **Trigger** | `@frp /jobs templates` |
| **Inputs** | Optional filter (parser name, template name) |
| **Backend Commands** | `template_inventory` |
| **Data Sources** | Settings.xml (all jobs) |
| **Output** | Table: Template Pattern, Parser, Count, Example Job, has ServicerID (Y/N) |
| **Confirmation** | None — read-only |

### D-01: Coverage Gap Analysis

| Attribute | Value |
|-----------|-------|
| **ID** | D-01 |
| **Category** | Deal Intelligence |
| **Phase** | 2 |
| **Slash Command** | `/deals gaps` |
| **Trigger** | `@frp /deals gaps 150` or `@frp /deals gaps all` |
| **Inputs** | CompanyID (specific or "all") |
| **Backend Commands** | `coverage_gaps` |
| **Data Sources** | Settings.xml (jobs with ServicerID), tblExternalDIDRef (DIDs per CompanyID) |
| **Output** | Per-servicer table: Total DIDs, Mapped DIDs, Unmapped DIDs, Coverage %, Missing ImportDIDs |
| **Confirmation** | None — read-only |

### D-02: Orphan Detection

| Attribute | Value |
|-----------|-------|
| **ID** | D-02 |
| **Category** | Deal Intelligence |
| **Phase** | 2 |
| **Slash Command** | `/deals orphans` |
| **Trigger** | `@frp /deals orphans` |
| **Inputs** | None |
| **Backend Commands** | `orphan_detection` |
| **Data Sources** | Settings.xml (jobs with ServicerID), tblExternalDIDRef (valid CompanyIDs) |
| **Output** | List: Job Name, ServicerID, Why Orphaned (no DB match / no deal data) |
| **Confirmation** | None — read-only |
| **Note** | Jobs WITHOUT a ServicerID are excluded — they are shelf-level/process-level, not orphans |

### D-03: ImportDID Collision Detection

| Attribute | Value |
|-----------|-------|
| **ID** | D-03 |
| **Category** | Deal Intelligence |
| **Phase** | 2 |
| **Slash Command** | `/deals collisions` |
| **Trigger** | `@frp /deals collisions` |
| **Inputs** | None |
| **Backend Commands** | `collision_detection` |
| **Data Sources** | Settings.xml (all ImportDID keywords), tblExternalDIDRef (ImportDID → CompanyID mapping) |
| **Output** | Collision table: ImportDID keyword, Matching CompanyIDs, Affected Jobs, Risk Level |
| **Confirmation** | None — read-only |
| **Note** | Same ImportDID + same CompanyID + multiple DIDs = legitimate batch, NOT a collision. A collision is same ImportDID + different CompanyIDs. |

### X-02: XML Diff Against Backup

| Attribute | Value |
|-----------|-------|
| **ID** | X-02 |
| **Category** | XML Management |
| **Phase** | 2 |
| **Slash Command** | `/deploy diff` |
| **Trigger** | `@frp /deploy diff` or `@frp /deploy diff Settings_20260101_120000.xml` |
| **Inputs** | Optional backup filename (defaults to most recent backup) |
| **Backend Commands** | `xml_diff` |
| **Data Sources** | Current Settings.xml + Backup Settings.xml |
| **Output** | Job-level diff: Added jobs, Removed jobs, Modified jobs (field-by-field before→after) |
| **Confirmation** | None — read-only |

### X-03: Rollback to Backup

| Attribute | Value |
|-----------|-------|
| **ID** | X-03 |
| **Category** | XML Management |
| **Phase** | 2 |
| **Slash Command** | `/deploy rollback` |
| **Trigger** | `@frp /deploy rollback Settings_20260101_120000.xml` |
| **Inputs** | Backup filename to restore |
| **Backend Commands** | `rollback_xml` |
| **Data Sources** | Backup file → Settings.xml |
| **Output** | Diff summary shown first, then confirmation, then restore + validate |
| **Confirmation** | **Required** — Two-step: (1) show diff, (2) confirm "Restore from backup?" |
| **Safety** | Auto-creates a backup of the CURRENT state before restoring the old one |

---

## Architecture Evolution

### New Backend Modules (Phase 2 adds)

```
backend/
├── xml/
│   ├── parser.py           # Existing (Phase 1) — no changes
│   ├── writer.py            # Existing — enhanced with create_job, edit_job methods
│   ├── models.py            # Existing — add JobTemplate, DiffResult models
│   └── diff.py              # NEW — Job-level XML comparison engine
├── db/
│   ├── deal_repo.py         # Existing — add coverage_gaps, orphan_detection, collision_detection
│   └── ...                  # Existing (Phase 1) — no changes
└── intel/
    ├── __init__.py           # NEW module
    ├── coverage.py           # NEW — Coverage gap analysis logic
    ├── orphans.py            # NEW — Orphan detection logic
    └── collisions.py         # NEW — ImportDID collision logic
```

### New CLI Commands (Phase 2 adds)

| Command | Use Case | Args |
|---------|----------|------|
| `create_job` | J-02 | --template-job, --name, --settings-path, --xml-type |
| `edit_job` | J-03 | --job-name, --field, --value, --settings-path, --xml-type |
| `template_inventory` | J-04 | --settings-path, --xml-type, --filter |
| `coverage_gaps` | D-01 | --servicer-id, --settings-path, --db-mode, --secrets-path |
| `orphan_detection` | D-02 | --settings-path, --db-mode, --secrets-path |
| `collision_detection` | D-03 | --settings-path, --db-mode, --secrets-path |
| `xml_diff` | X-02 | --settings-path, --backup-file |
| `rollback_xml` | X-03 | --settings-path, --backup-file |

### Extension Updates

- **`/jobs` handler**: Add subcommand parsing for `create`, `edit`, `templates`
- **`/deals` handler**: Add subcommand parsing for `gaps`, `orphans`, `collisions`
- **`/deploy` handler**: Add subcommand parsing for `diff`, `rollback`
- **Follow-ups**: Post-CRUD → suggest validate. Post-diff → suggest rollback. Post-orphans → suggest gaps.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Job creation produces invalid XML** | Medium | High | Auto-validate after create; require confirmation with preview |
| **Edit targets wrong job (partial match)** | Medium | Medium | Fuzzy match with disambiguation prompt; show matched job details before confirming |
| **Coverage gaps require DB access (prod)** | Low | Medium | Graceful degradation: skip DB-dependent intel in local dev with clear message |
| **ImportDID collision logic too slow for large datasets** | Low | Low | Pre-filter by parsing keywords first, then query DB only for relevant CompanyIDs |
| **Rollback to wrong backup** | Low | High | Two-step confirmation: show diff first, then confirm. Auto-backup current before rollback. |
| **XML diff misclassifies changes** | Medium | Low | Job-level comparison using job name as key; handle renames as remove+add |

---

## Success Criteria

### Functional Criteria

| SC# | Criterion | Verification |
|-----|-----------|--------------|
| SC-01 | Create new email job from template | New `<MailboxMonitor>` block appears in Settings.xml with correct structure |
| SC-02 | Edit job field | Single field updated, rest of job untouched, backup created |
| SC-03 | Template inventory lists all unique patterns | Count matches manual analysis of Settings.xml |
| SC-04 | Coverage gaps show unmapped DIDs | Cross-verified with direct SQL query on tblExternalDIDRef |
| SC-05 | Orphan detection flags only jobs with invalid ServicerIDs | Jobs WITHOUT ServicerID are not flagged |
| SC-06 | Collision detection distinguishes batch pattern from real collisions | Same ImportDID + same CompanyID not flagged |
| SC-07 | XML diff shows meaningful job-level changes | Not raw text diff; shows field-by-field changes |
| SC-08 | Rollback restores from backup with safety backup | Current state preserved before rollback |
| SC-09 | All mutations require confirmation | No silent writes; modal dialog before every create/edit/rollback |
| SC-10 | Auto-validation runs after every mutation | Post-save validation results displayed in chat |

### Non-Functional Criteria

| Criterion | Target |
|-----------|--------|
| Coverage gap analysis (single servicer) | < 3 seconds |
| Full orphan detection (all jobs) | < 5 seconds |
| Collision detection (all ImportDIDs) | < 5 seconds |
| XML diff (2,092-line file vs backup) | < 2 seconds |
| Job creation (template → save) | < 3 seconds (excluding confirmation wait) |
| Test coverage (Phase 2 modules) | ≥ 90% |

---

## Dependencies & Prerequisites

### Phase 1 Gate

All Phase 1 verification checkpoints must pass:

- [ ] CP-1: Data models importable and serializable
- [ ] CP-2: XML parser can parse both email and SFTP formats
- [ ] CP-3: XML validator detects all E/W/I codes
- [ ] CP-4: XML writer creates backups and verifies saves
- [ ] CP-5: Database connector works in both MySQL and MSSQL modes
- [ ] CP-6: Deal repository returns correct deal data
- [ ] CP-7: Log parser extracts events from sample logs
- [ ] CP-8: CLI returns valid JSON for all 7 commands
- [ ] CP-FINAL: F5 Extension Dev Host responds to all slash commands

### External Dependencies

| Dependency | Required By | Status |
|------------|-------------|--------|
| pyodbc + ODBC drivers | D-01, D-02, D-03 | Same as Phase 1 |
| Read access to tblExternalDIDRef | D-01, D-02, D-03 | Same as Phase 1 |
| Settings.xml (email + SFTP) | All use cases | Same as Phase 1 |
| Backup directory writable | J-02, J-03, X-03 | Same as Phase 1 |

---

## Estimated Effort

| Sprint | Description | Hours |
|--------|-------------|-------|
| Sprint 8 | Data Models (JobTemplate, DiffResult, CoverageReport, etc.) | 2–3h |
| Sprint 9 | Job CRUD Engine (create_job, edit_job, template_inventory) | 6–8h |
| Sprint 10 | Coverage Intelligence (coverage_gaps, orphan_detection, collision_detection) | 5–7h |
| Sprint 11 | XML Diff Engine | 3–4h |
| Sprint 12 | XML Rollback + Confirmation Flow | 3–4h |
| Sprint 13 | Extension Updates (subcommand routing, follow-ups, confirmations) | 4–5h |
| Sprint 14 | Integration Testing + Manual QA | 4–5h |
| **Total** | | **27–36 hours** |

**Calendar estimate:** 7–10 working days (continuing sprint numbering from Phase 1's 7 sprints)

---

*Next document: [02_SYSTEM_DESIGN.md](02_SYSTEM_DESIGN.md)*
