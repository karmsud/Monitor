# Phase 2: System Design
## FRP Agent — CRUD & Intelligence Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Prerequisite:** Phase 1 System Design (Phase1/02_SYSTEM_DESIGN.md)

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [New Data Models](#new-data-models)
3. [Job CRUD Engine](#job-crud-engine)
4. [Template Inventory Engine](#template-inventory-engine)
5. [Coverage Intelligence Module](#coverage-intelligence-module)
6. [XML Diff Engine](#xml-diff-engine)
7. [Rollback Engine](#rollback-engine)
8. [New CLI Commands](#new-cli-commands)
9. [Extension Handler Updates](#extension-handler-updates)
10. [Confirmation Flow Design](#confirmation-flow-design)
11. [Data Flow Diagrams](#data-flow-diagrams)

---

## 1. Architecture Overview

### Phase 2 Module Map

Phase 2 adds to the existing three-layer architecture established in Phase 1. No structural changes — only new Python modules and enhanced extension handlers.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  VS Code Extension (JavaScript)                                         │
│                                                                         │
│  chat/participant.js  ── Enhanced command handlers ──────────┐          │
│   /jobs create|edit|templates (NEW subcommands)              │          │
│   /deals gaps|orphans|collisions (NEW subcommands)           │          │
│   /deploy diff|rollback (NEW subcommands)                    │          │
│                                                              │          │
│  copilot/tool.js  ── backendCall() ── 8 new commands ────────┤          │
│                                                              │          │
│  Confirmation dialog ── vscode.window.showWarningMessage ────┘          │
└─────────────────────────┬─────────────────────────────┬─────────────────┘
                          │ CLI (JSON)                  │ LLM
                          ▼                             ▼
┌─────────────────────────────────────────────┐  ┌───────────────────────┐
│  Python Backend                              │  │  Copilot LLM          │
│                                              │  │                       │
│  PHASE 1 (existing):                         │  │  Format CRUD results  │
│   xml/parser.py, writer.py, models.py        │  │  Explain coverage gaps│
│   db/connection.py, deal_repo.py, queries.py │  │  Describe diff changes│
│   logs/parser.py, indexer.py                 │  │  Assist job creation  │
│   backup/manager.py                          │  │                       │
│                                              │  └───────────────────────┘
│  PHASE 2 (new):                              │
│   xml/diff.py          ← XML diff engine     │
│   xml/crud.py          ← Create/edit jobs    │
│   xml/templates.py     ← Template discovery  │
│   intel/coverage.py    ← Coverage gap logic  │
│   intel/orphans.py     ← Orphan detection    │
│   intel/collisions.py  ← Collision detection │
│   intel/models.py      ← Shared intel models │
│                                              │
│  cli/main.py  ← 8 new subcommands           │
└──────────────────────────────────────────────┘
```

### Module Dependency Graph

```
xml/crud.py ──depends-on──→ xml/parser.py (read jobs)
             ──depends-on──→ xml/writer.py (save changes)
             ──depends-on──→ xml/models.py (EmailJob, SftpJob)

xml/diff.py ──depends-on──→ xml/parser.py (parse both files)
             ──depends-on──→ xml/models.py (job comparison)

xml/templates.py ──depends-on──→ xml/parser.py (get_all_jobs)

intel/coverage.py ──depends-on──→ xml/parser.py (get jobs with ServicerID)
                   ──depends-on──→ db/deal_repo.py (get deals by CompanyID)

intel/orphans.py ──depends-on──→ xml/parser.py (get jobs with ServicerID)
                  ──depends-on──→ db/deal_repo.py (check servicer exists)

intel/collisions.py ──depends-on──→ xml/parser.py (get ImportDID keywords)
                     ──depends-on──→ db/deal_repo.py (query ImportDID matches)
```

---

## 2. New Data Models

### backend/xml/models.py — Additions

```python
@dataclass
class JobTemplate:
    """A discovered template pattern across existing jobs."""
    pattern_name: str          # e.g., "rptent - Standard Email"
    parser_names: list[str]    # e.g., ["MailToFolder", "ExcelMail"]
    template_names: list[str]  # e.g., ["DealTemplate.xlsx"]
    mailbox: str               # Common mailbox pattern
    example_job_name: str      # Name of one representative job
    job_count: int             # How many jobs share this pattern
    has_servicer_id: bool      # Whether these jobs typically have a ServicerID
    sample_fields: dict        # Key config fields from the example job

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class JobDiff:
    """Difference between two versions of a single job."""
    job_name: str
    change_type: str           # "added" | "removed" | "modified"
    field_changes: list[dict]  # [{ field, old_value, new_value }]

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DiffResult:
    """Result of comparing two Settings.xml files."""
    current_file: str
    backup_file: str
    added_jobs: list[JobDiff]
    removed_jobs: list[JobDiff]
    modified_jobs: list[JobDiff]
    unchanged_count: int
    timestamp: str

    @property
    def total_changes(self) -> int:
        return len(self.added_jobs) + len(self.removed_jobs) + len(self.modified_jobs)

    def to_dict(self) -> dict:
        return {
            "current_file": self.current_file,
            "backup_file": self.backup_file,
            "added": [j.to_dict() for j in self.added_jobs],
            "removed": [j.to_dict() for j in self.removed_jobs],
            "modified": [j.to_dict() for j in self.modified_jobs],
            "unchanged_count": self.unchanged_count,
            "total_changes": self.total_changes,
            "timestamp": self.timestamp,
        }
```

### backend/intel/models.py — New File

```python
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class CoverageReport:
    """Coverage gap analysis for a single servicer."""
    servicer_id: int                     # CompanyID
    total_dids: int                      # Total DIDs in DB for this CompanyID
    mapped_dids: int                     # DIDs matched by at least one job's ImportDID keyword
    unmapped_dids: list[dict]            # [{ did, import_did }] — DIDs with no job match
    coverage_percentage: float           # mapped / total * 100
    matching_jobs: list[str]             # Job names covering this servicer

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class OrphanResult:
    """An orphaned job — has ServicerID but no matching DB records."""
    job_name: str
    servicer_id: int
    reason: str                          # "no_db_match" | "no_deal_data"
    xml_type: str                        # "email" | "sftp"

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class CollisionResult:
    """An ImportDID keyword that matches multiple CompanyIDs."""
    import_did_keyword: str              # The colliding keyword
    matching_company_ids: list[int]      # CompanyIDs this keyword matches
    affected_jobs: list[str]             # Job names using this keyword
    risk_level: str                      # "high" (3+ companies), "medium" (2 companies)
    deal_counts: dict                    # { company_id: deal_count }

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IntelSummary:
    """Summary report from coverage/orphan/collision analysis."""
    total_jobs_scanned: int
    jobs_with_servicer: int
    jobs_without_servicer: int
    coverage_reports: list[CoverageReport] = field(default_factory=list)
    orphans: list[OrphanResult] = field(default_factory=list)
    collisions: list[CollisionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_jobs_scanned": self.total_jobs_scanned,
            "jobs_with_servicer": self.jobs_with_servicer,
            "jobs_without_servicer": self.jobs_without_servicer,
            "coverage_reports": [r.to_dict() for r in self.coverage_reports],
            "orphans": [o.to_dict() for o in self.orphans],
            "collisions": [c.to_dict() for c in self.collisions],
            "errors": self.errors,
        }
```

---

## 3. Job CRUD Engine

### backend/xml/crud.py

The CRUD engine operates on the parsed ElementTree, modifying it in-memory and then delegating save to the existing `XmlWriter`.

#### Create Job Flow

```
Input: template_job_name, new_job_name, overrides (dict of field→value)
  1. Parse Settings.xml → ElementTree
  2. Find template job element by name
  3. Deep copy template element
  4. Apply overrides (name, ServicerID, mailbox, parsers, etc.)
  5. Insert copy into the <MailboxCollection> parent
  6. Validate the modified tree
  7. Save via XmlWriter (auto-backup)
  8. Return: new job details + validation result
```

#### Edit Job Flow

```
Input: job_name_query, field, new_value
  1. Parse Settings.xml → ElementTree
  2. Search for job by name (fuzzy match if needed)
  3. If ambiguous → return list of matches for disambiguation
  4. Record old value of target field
  5. Modify field in-place on the ElementTree
  6. Validate the modified tree
  7. Save via XmlWriter (auto-backup)
  8. Return: { job_name, field, old_value, new_value, validation }
```

#### Editable Fields Matrix

| Field Path | CLI Flag | Example Value | Notes |
|------------|----------|---------------|-------|
| `Name` | --name | "Exeter - rptent" | Job display name |
| `ServicerID` | --servicer-id | "225" | Maps to CompanyID |
| `MailboxAddress` | --mailbox | "exeter@bank.com" | Email address to monitor |
| `ImportDID` | --import-did | "EXETER" | Keyword for deal matching |
| `SubjectFilter` | --subject-filter | "rptent" | Subject line filter |
| `SenderFilter` | --sender-filter | "*@exeter.com" | Sender email filter |
| `ParserCollection/*` | --add-parser, --remove-parser | "MailToFolder" | Add/remove parsers |
| `TemplateCollection/*` | --add-template, --remove-template | "Deal.xlsx" | Add/remove templates |
| `Active` | --active | "true" | Enable/disable job |

#### Disambiguation Flow

```
User: @frp /jobs edit "exeter" set servicer 225
  → search_jobs("exeter") returns 3 matches:
    1. "Exeter - rptent" (ServicerID: 150)
    2. "Exeter - Remittance" (ServicerID: 150)
    3. "Exeter Bankruptcy" (ServicerID: 225)

  → Extension shows disambiguation:
    "Found 3 jobs matching 'exeter'. Which one?"
    Follow-ups: each job name as a clickable option
```

---

## 4. Template Inventory Engine

### backend/xml/templates.py

Template discovery analyzes all jobs to identify recurring patterns.

#### Pattern Detection Algorithm

```
1. For each job, extract the "signature":
   - Parser combination (sorted set of parser names)
   - Template combination (sorted set of template names)
   - Has ServicerID (bool)
   
2. Group jobs by signature

3. For each group (= one template pattern):
   - Create JobTemplate with group statistics
   - Pick a representative job as example
   - Extract common mailbox pattern (if present)
   - Name the pattern: "{first_parser} - {template_type}"
```

#### Output Format

```json
{
  "success": true,
  "data": {
    "templates": [
      {
        "pattern_name": "MailToFolder - Standard Bond Report",
        "parser_names": ["MailToFolder"],
        "template_names": ["BondReport.xlsx"],
        "mailbox": "varies",
        "example_job_name": "CSMC 2015-1 rptent",
        "job_count": 12,
        "has_servicer_id": true,
        "sample_fields": {
          "SubjectFilter": "*rptent*",
          "SenderFilter": "",
          "Active": "true"
        }
      }
    ],
    "total_templates": 8,
    "total_jobs": 48
  }
}
```

---

## 5. Coverage Intelligence Module

### backend/intel/coverage.py — Coverage Gap Analysis

#### Algorithm

```
Input: servicer_id (or "all"), settings_path, db_connection

1. Get all jobs with the target ServicerID from XML
2. Extract all ImportDID keywords from those jobs
3. Query tblExternalDIDRef: SELECT DID, ImportDID FROM tblExternalDIDRef WHERE CompanyID = ?
4. For each DID in DB:
   - Check if any job's ImportDID keyword matches the DID's ImportDID value
   - Using case-insensitive substring/keyword match (same logic as EmailMonitor)
5. Build CoverageReport:
   - mapped_dids = DIDs that match at least one job keyword
   - unmapped_dids = DIDs with no matching job keyword
   - coverage_percentage = mapped / total * 100
```

#### Matching Logic

The EmailMonitor uses ImportDID as a keyword match. The coverage engine must replicate this:

```python
def does_job_cover_did(job_import_did: str, did_import_did: str) -> bool:
    """
    Check if a job's ImportDID keyword covers a specific DID.
    Mirrors EmailMonitor's matching logic:
    - Case-insensitive
    - Full match only (not substring unless explicitly using wildcards)
    """
    if not job_import_did or not did_import_did:
        return False
    return job_import_did.strip().upper() == did_import_did.strip().upper()
```

### backend/intel/orphans.py — Orphan Detection

#### Algorithm

```
Input: settings_path, db_connection

1. Get all jobs from XML
2. Filter to jobs that HAVE a ServicerID (non-empty, non-null)
3. Get all distinct CompanyIDs from tblExternalDIDRef
4. For each job with ServicerID:
   - If ServicerID not in the set of valid CompanyIDs → orphan (reason: "no_db_match")
   - If ServicerID exists but has 0 deals → orphan (reason: "no_deal_data")
5. Return list of OrphanResult
```

**Important**: Jobs WITHOUT a ServicerID are **NOT orphans** — they are shelf-level or process-level jobs and should be reported separately as "uncategorized" if needed.

### backend/intel/collisions.py — ImportDID Collision Detection

#### Algorithm

```
Input: settings_path, db_connection

1. Get all jobs from XML
2. Extract all unique ImportDID keywords (across all jobs)
3. For each ImportDID keyword:
   a. Query tblExternalDIDRef: SELECT DISTINCT CompanyID FROM tblExternalDIDRef 
      WHERE ImportDID = ? (case-insensitive)
   b. If result has more than 1 CompanyID → collision
4. For each collision:
   - Find all jobs using that ImportDID keyword
   - Count deals per CompanyID
   - Assign risk level: 3+ CompanyIDs = "high", 2 CompanyIDs = "medium"
5. Return list of CollisionResult

CRITICAL EXCLUSION:
- Same ImportDID + same CompanyID + multiple DIDs = LEGITIMATE BATCH, NOT a collision
- A collision requires the SAME ImportDID matching DIFFERENT CompanyIDs
```

---

## 6. XML Diff Engine

### backend/xml/diff.py

Job-level diff compares two Settings.xml files and reports changes at the job granularity (not raw text diff).

#### Algorithm

```
Input: current_settings_path, backup_file_path

1. Parse both files with SettingsXmlParser
2. Get all jobs from both: current_jobs, backup_jobs
3. Build lookup dictionaries keyed by job name:
   current_map = { job.name: job for job in current_jobs }
   backup_map  = { job.name: job for job in backup_jobs }

4. Added jobs:   names in current_map but not in backup_map
5. Removed jobs:  names in backup_map but not in current_map
6. Modified jobs: names in both, but with field differences

7. For modified jobs, compare field-by-field:
   fields_to_compare = [
     'servicer_id', 'mailbox', 'import_did', 'subject_filter',
     'sender_filter', 'active', 'parsers', 'templates'
   ]
   For each field:
     old_val = getattr(backup_job, field)
     new_val = getattr(current_job, field)
     if old_val != new_val:
       changes.append({ field, old_value, new_value })

8. Return DiffResult with job-level changes
```

#### Output Format

```json
{
  "success": true,
  "data": {
    "current_file": "C:\\Settings\\Settings.xml",
    "backup_file": "C:\\Settings\\backup\\Settings_20260201_120000.xml",
    "added": [
      {
        "job_name": "New Exeter Job",
        "change_type": "added",
        "field_changes": []
      }
    ],
    "removed": [
      {
        "job_name": "Old Defunct Job",
        "change_type": "removed",
        "field_changes": []
      }
    ],
    "modified": [
      {
        "job_name": "CSMC 2015-1 rptent",
        "change_type": "modified",
        "field_changes": [
          { "field": "servicer_id", "old_value": "150", "new_value": "225" },
          { "field": "import_did", "old_value": "CSMC", "new_value": "CSMC2015" }
        ]
      }
    ],
    "unchanged_count": 45,
    "total_changes": 3,
    "timestamp": "2026-02-24T10:30:00Z"
  }
}
```

---

## 7. Rollback Engine

### Rollback Flow (Two-Stage)

```
Stage 1: Preview
  User: @frp /deploy rollback Settings_20260201_120000.xml
  → Extension calls: backendCall('xml_diff', { backupFile: '...' })
  → Shows diff summary in chat
  → Asks: "Restore from this backup? Current state will be backed up first."

Stage 2: Execute (after user confirmation)
  → Extension calls: backendCall('save_xml', { xmlType: 'email' })  ← backup current first
  → Extension calls: backendCall('rollback_xml', { backupFile: '...' })
  → Backend copies backup file → Settings.xml
  → Validates the restored file
  → Shows: "Restored from backup. Validation: ✅ passed"
  → Follow-up suggestion: "diff" (to see what changed)
```

### Safety Guarantees

1. **Pre-rollback backup**: Current Settings.xml is backed up BEFORE the rollback
2. **Post-rollback validation**: Full XML validation runs on the restored file
3. **Two-step confirmation**: User sees the diff before confirming
4. **Audit trail**: Rollback operation logged to output channel with timestamp

---

## 8. New CLI Commands

### Command Specifications

#### create_job

```
python -m cli.main create_job \
  --settings-path "C:\path\Settings.xml" \
  --xml-type email \
  --template-job "CSMC 2015-1 rptent" \
  --name "New Exeter Job" \
  [--servicer-id 225] \
  [--mailbox "exeter@bank.com"] \
  [--import-did "EXETER"]
```

Response:
```json
{
  "success": true,
  "data": {
    "created_job": { "name": "New Exeter Job", "servicer_id": "225", ... },
    "validation": { "valid": true, "errors": [], "warnings": [], "info": [] },
    "backup_created": "Settings_20260224_103000.xml"
  }
}
```

#### edit_job

```
python -m cli.main edit_job \
  --settings-path "C:\path\Settings.xml" \
  --xml-type email \
  --job-name "Exeter - rptent" \
  --field servicer_id \
  --value "225"
```

Response:
```json
{
  "success": true,
  "data": {
    "job_name": "Exeter - rptent",
    "field": "servicer_id",
    "old_value": "150",
    "new_value": "225",
    "validation": { "valid": true, "errors": [], "warnings": [], "info": [] },
    "backup_created": "Settings_20260224_103100.xml"
  }
}
```

#### template_inventory

```
python -m cli.main template_inventory \
  --settings-path "C:\path\Settings.xml" \
  --xml-type email \
  [--filter "rptent"]
```

#### coverage_gaps

```
python -m cli.main coverage_gaps \
  --settings-path "C:\path\Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json" \
  --servicer-id 150
```

Response:
```json
{
  "success": true,
  "data": {
    "servicer_id": 150,
    "total_dids": 45,
    "mapped_dids": 42,
    "unmapped_dids": [
      { "did": 12345, "import_did": "CSMC2020" },
      { "did": 12346, "import_did": "CSMC2021" },
      { "did": 12347, "import_did": "CSMC2022" }
    ],
    "coverage_percentage": 93.3,
    "matching_jobs": ["CSMC 2015-1 rptent", "CSMC Remittance"]
  }
}
```

#### orphan_detection

```
python -m cli.main orphan_detection \
  --settings-path "C:\path\Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json"
```

#### collision_detection

```
python -m cli.main collision_detection \
  --settings-path "C:\path\Settings.xml" \
  --db-mode mysql \
  --secrets-path "config/secrets_mysql.json"
```

#### xml_diff

```
python -m cli.main xml_diff \
  --settings-path "C:\path\Settings.xml" \
  --backup-file "C:\path\backup\Settings_20260201_120000.xml"
```

#### rollback_xml

```
python -m cli.main rollback_xml \
  --settings-path "C:\path\Settings.xml" \
  --backup-file "C:\path\backup\Settings_20260201_120000.xml"
```

---

## 9. Extension Handler Updates

### Updated /jobs Handler — Subcommand Routing

```javascript
async function handleJobsCommand(vscode, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  // Phase 2 subcommands
  if (/^create\b/i.test(prompt)) {
    return handleJobCreate(vscode, request, stream, token, shared, prompt);
  }
  if (/^edit\b/i.test(prompt)) {
    return handleJobEdit(vscode, request, stream, token, shared, prompt);
  }
  if (/^templates?\b/i.test(prompt)) {
    return handleJobTemplates(vscode, request, stream, token, shared, prompt);
  }

  // Phase 1 subcommands (existing)
  if (/^validate/i.test(prompt)) { ... }
  
  // Default: search (Phase 1)
  ...
}
```

### Updated /deals Handler — Subcommand Routing

```javascript
async function handleDealsCommand(vscode, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  // Phase 2 subcommands
  if (/^gaps?\b/i.test(prompt)) {
    return handleCoverageGaps(vscode, request, stream, token, shared, prompt);
  }
  if (/^orphans?\b/i.test(prompt)) {
    return handleOrphanDetection(vscode, request, stream, token, shared, prompt);
  }
  if (/^collisions?\b/i.test(prompt)) {
    return handleCollisionDetection(vscode, request, stream, token, shared, prompt);
  }

  // Phase 1 subcommands (existing)
  if (/^servicer\b/i.test(prompt)) { ... }
}
```

### Updated /deploy Handler — Subcommand Routing

```javascript
async function handleDeployCommand(vscode, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  // Phase 2 subcommands
  if (/^diff\b/i.test(prompt)) {
    return handleXmlDiff(vscode, request, stream, token, shared, prompt);
  }
  if (/^rollback\b/i.test(prompt)) {
    return handleRollback(vscode, request, stream, token, shared, prompt);
  }

  // Phase 1 subcommands (existing)
  if (/^save\b/i.test(prompt)) { ... }
  if (/^backups?\b/i.test(prompt)) { ... }
}
```

---

## 10. Confirmation Flow Design

### General Pattern

All mutation operations (create, edit, rollback) follow this confirmation flow:

```
1. User issues command: @frp /jobs edit "Exeter" set servicer 225
2. Extension parses command → extracts target job, field, value
3. Extension calls backend for DRY-RUN (preview mode):
   backendCall('search_jobs', { query: 'Exeter' })
4. Extension shows preview in chat:
   "Found job 'Exeter - rptent'. Change ServicerID from 150 → 225?"
5. Extension shows modal confirmation dialog:
   vscode.window.showWarningMessage("Apply changes?", { modal: true }, "Apply", "Cancel")
6. If confirmed:
   a. Call backendCall('edit_job', { jobName: 'Exeter - rptent', field: 'servicer_id', value: '225' })
   b. Backend creates backup → modifies XML → validates → returns result
   c. Extension shows result + validation
   d. Generate follow-ups
7. If cancelled:
   stream.markdown("Edit cancelled.")
```

### Confirmation Dialog Variants

| Operation | Dialog Message | Buttons |
|-----------|---------------|---------|
| Create job | "Create new job '{name}' based on template '{template}'?" | Create / Cancel |
| Edit job | "Apply changes to job '{name}'? (ServicerID: 150 → 225)" | Apply / Cancel |
| Rollback | "Restore Settings.xml from backup '{file}'? Current state will be backed up." | Restore / Cancel |

### No Confirmation Needed

| Operation | Why |
|-----------|-----|
| Search jobs | Read-only |
| Validate XML | Read-only |
| Template inventory | Read-only |
| Coverage gaps | Read-only |
| Orphan detection | Read-only |
| Collision detection | Read-only |
| XML diff | Read-only |
| List backups | Read-only |

---

## 11. Data Flow Diagrams

### Coverage Gaps Flow

```
User: @frp /deals gaps 150
  │
  ├─→ Extension: parse servicerId=150
  │
  ├─→ backendCall('coverage_gaps', { servicerId: 150, dbMode, secretsPath, settingsPath })
  │     │
  │     ├─→ cli.main coverage_gaps
  │     │     │
  │     │     ├─→ SettingsXmlParser.get_all_jobs()
  │     │     │     → Filter to jobs with ServicerID=150
  │     │     │     → Extract ImportDID keywords
  │     │     │
  │     │     ├─→ DealRepository.get_deals_by_company(150)
  │     │     │     → Returns list of { DID, ImportDID }
  │     │     │
  │     │     ├─→ CoverageAnalyzer.analyze()
  │     │     │     → Match each DID's ImportDID against job keywords
  │     │     │     → Compute mapped vs unmapped
  │     │     │
  │     │     └─→ Return CoverageReport.to_dict()
  │     │
  │     └─→ JSON response → Extension
  │
  ├─→ LLM formats: "CompanyID 150 has 93.3% coverage. 3 DIDs unmapped..."
  │
  └─→ Follow-ups: "gaps all", "orphans", "servicer 150"
```

### Job Creation Flow

```
User: @frp /jobs create rptent from "CSMC 2015-1 rptent"
  │
  ├─→ Extension: parse templateJob="CSMC 2015-1 rptent", parser context="rptent"
  │
  ├─→ backendCall('search_jobs', { query: 'CSMC 2015-1 rptent' })
  │     → Verify template exists, show preview
  │
  ├─→ Show preview in chat: "Create new job based on 'CSMC 2015-1 rptent'?"
  │
  ├─→ Confirmation dialog: "Create?" → user clicks "Create"
  │
  ├─→ backendCall('create_job', { templateJob, name, settingsPath, xmlType })
  │     │
  │     ├─→ cli.main create_job
  │     │     ├─→ Deep copy template job element
  │     │     ├─→ Apply overrides
  │     │     ├─→ Insert into <MailboxCollection>
  │     │     ├─→ Create backup
  │     │     ├─→ Save modified XML
  │     │     └─→ Validate
  │     │
  │     └─→ JSON response with new job + validation
  │
  ├─→ LLM formats: "Created 'New Job'. Validation: ✅ passed"
  │
  └─→ Follow-ups: "edit New Job", "validate", "search New Job"
```

### XML Diff + Rollback Flow

```
User: @frp /deploy diff
  │
  ├─→ Extension: get latest backup filename
  ├─→ backendCall('xml_diff', { settingsPath, backupFile: latestBackup })
  ├─→ LLM formats: "2 jobs modified, 1 added since last backup"
  └─→ Follow-ups: "rollback {backup_file}"

User: @frp /deploy rollback Settings_20260201_120000.xml
  │
  ├─→ Extension: show diff first
  ├─→ backendCall('xml_diff', { settingsPath, backupFile })
  ├─→ Show diff summary
  ├─→ Confirmation: "Restore from backup?"
  │     │
  │     └─→ User confirms
  │
  ├─→ backendCall('save_xml', { xmlType })     ← backup current FIRST
  ├─→ backendCall('rollback_xml', { backupFile, settingsPath })
  │     │
  │     ├─→ Copy backup → Settings.xml
  │     └─→ Validate restored file
  │
  ├─→ LLM formats: "Restored. Previous state saved as backup. Validation: ✅"
  └─→ Follow-ups: "diff", "validate"
```

---

*Next document: [03_TECHNICAL_DESIGN.md](03_TECHNICAL_DESIGN.md)*
