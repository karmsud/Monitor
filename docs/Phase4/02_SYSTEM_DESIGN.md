# Phase 4: System Design
## FRP Agent — Advanced Analysis Layer

**Document Version:** 1.0  
**Date:** February 24, 2026

---

## Table of Contents
1. [Module Map](#1-module-map)
2. [Dependency Graph](#2-dependency-graph)
3. [Data Models](#3-data-models)
4. [Trend Analyzer Design](#4-trend-analyzer-design)
5. [Performance Benchmarker Design](#5-performance-benchmarker-design)
6. [Consolidation Analyzer Design](#6-consolidation-analyzer-design)
7. [Impact Simulator Design](#7-impact-simulator-design)
8. [Health Checker Design](#8-health-checker-design)
9. [CLI Command Specifications](#9-cli-command-specifications)
10. [Extension Handler Specifications](#10-extension-handler-specifications)
11. [Data Flow Diagrams](#11-data-flow-diagrams)

---

## 1. Module Map

### New Files (Phase 4)

```
backend/
├── analysis/
│   ├── __init__.py              # Package init — exports all public classes
│   ├── models.py                # TrendDay, PerformanceEntry, ConsolidationGroup,
│   │                            #   ChangeSpec, AffectedEntity, ImpactReport,
│   │                            #   HealthSection, HealthReport
│   ├── trends.py                # TrendAnalyzer class
│   ├── performance.py           # PerformanceBenchmarker class
│   ├── consolidation.py         # ConsolidationAnalyzer class
│   ├── impact.py                # ImpactSimulator class
│   └── health.py                # HealthChecker orchestrator class
```

### Modified Files (Phase 4)

```
cli/main.py                      # 5 new commands: log_trends, log_performance,
                                 #   analyze_consolidation, analyze_impact, analyze_health
extension/
├── chat/participant.js          # /analyze handler routing added
├── handlers/analyze.js          # NEW — handleAnalyze() dispatcher
└── handlers/logs.js             # Updated — trends + performance subcommands
```

### Complete Module Tree (All Phases)

```
backend/
├── __init__.py
├── common/
│   ├── __init__.py
│   └── models.py                # CliResponse (P1)
├── parsing/
│   ├── __init__.py
│   ├── models.py                # EmailJob, SftpJob, ValidationResult (P1)
│   ├── settings_xml.py          # SettingsXmlParser (P1)
│   └── xml_writer.py            # XmlWriter, BackupManager (P1)
├── db/
│   ├── __init__.py
│   ├── connection.py            # DualDbFactory (P1)
│   └── deal_repo.py             # DealRepository (P1) + P3 additions
├── logs/
│   ├── __init__.py
│   ├── models.py                # LogEvent (P1) + DealActivity, DIDFailure, etc. (P3)
│   ├── parser.py                # LogFileParser (P1)
│   ├── indexer.py               # LogIndexer (P1)
│   └── analytics.py             # LogAnalytics (P3)
├── intel/
│   ├── __init__.py
│   ├── models.py                # IntelModels (P2)
│   ├── templates.py             # TemplateInventory (P2)
│   ├── coverage.py              # CoverageAnalyzer (P2)
│   ├── orphans.py               # OrphanDetector (P2)
│   └── collisions.py            # CollisionDetector (P2)
├── crud/
│   ├── __init__.py
│   ├── crud.py                  # JobCrudEngine (P2)
│   ├── diff.py                  # XmlDiffEngine (P2)
│   └── rollback.py              # RollbackHandler (P2)
├── triage/
│   ├── __init__.py
│   ├── models.py                # EmailInfo, MatchResult, TriageResult (P3)
│   ├── msg_parser.py            # MsgParser (P3)
│   ├── matcher.py               # TriageMatcher (P3)
│   └── analyzer.py              # TriageAnalyzer (P3)
└── analysis/                    # ← NEW Phase 4
    ├── __init__.py
    ├── models.py
    ├── trends.py
    ├── performance.py
    ├── consolidation.py
    ├── impact.py
    └── health.py

cli/main.py                      # 26 total commands

extension/
├── extension.js
├── chat/participant.js
├── copilot/tool.js
├── lib/frp_backend.js
├── handlers/
│   ├── jobs.js
│   ├── deals.js
│   ├── logs.js                  # Updated P4
│   ├── deploy.js
│   ├── triage.js
│   └── analyze.js               # NEW P4
└── commands/
    ├── sync.js
    └── status.js
```

---

## 2. Dependency Graph

```
analysis/models.py          ← no dependencies (pure data)
      │
      ├─── analysis/trends.py
      │        └── depends on: logs/analytics.py → SQLite
      │
      ├─── analysis/performance.py
      │        └── depends on: logs/analytics.py → SQLite
      │                        parsing/settings_xml.py → XML (for job names)
      │
      ├─── analysis/consolidation.py
      │        └── depends on: parsing/settings_xml.py → XML
      │                        db/deal_repo.py → DB (DID counts)
      │
      ├─── analysis/impact.py
      │        └── depends on: parsing/settings_xml.py → XML
      │                        db/deal_repo.py → DB
      │                        logs/analytics.py → SQLite (recent activity check)
      │
      └─── analysis/health.py   (orchestrator)
               └── depends on: parsing/settings_xml.py → XML
                               intel/coverage.py → CoverageAnalyzer
                               intel/orphans.py → OrphanDetector
                               intel/collisions.py → CollisionDetector
                               logs/analytics.py → LogAnalytics
                               analysis/performance.py → PerformanceBenchmarker
```

### Dependency Injection Pattern

All Phase 4 classes receive their dependencies via constructor injection. They never instantiate Phase 1–3 classes directly.

```python
# Good — injectable
class HealthChecker:
    def __init__(self, parser, repo, analytics, coverage, orphans, collisions, benchmarker):
        ...

# Bad — tightly coupled
class HealthChecker:
    def __init__(self, xml_path, db_path):
        self.parser = SettingsXmlParser(xml_path)  # DON'T do this
```

---

## 3. Data Models

### analysis/models.py

```python
@dataclass
class TrendDay:
    date: str               # "2026-02-24"
    total_files: int        # Files processed that day
    total_errors: int
    did_failures: int
    job_runs: int
    trend_files: str        # "↑", "↓", "→" vs previous day
    trend_errors: str

@dataclass
class TrendSummary:
    days: list[TrendDay]
    period_total_files: int
    period_total_errors: int
    period_avg_files_per_day: float
    vs_previous_period: dict | None   # {"files_delta": +12%, "errors_delta": -3%}
    worst_day: str | None
    best_day: str | None

@dataclass
class PerformanceEntry:
    job_name: str
    job_type: str           # "email" or "sftp"
    total_runs: int
    success_rate: float     # 0.0 – 100.0
    avg_files_per_run: float
    total_errors: int
    last_run: str | None    # ISO timestamp
    status: str             # "healthy", "warning", "critical"
    common_errors: list[str]  # Top 3

@dataclass
class PerformanceSummary:
    entries: list[PerformanceEntry]
    total_jobs: int
    healthy_count: int
    warning_count: int
    critical_count: int
    avg_success_rate: float

@dataclass
class ConsolidationGroup:
    group_id: int
    shared_mailbox: str          # Common mailbox/path
    shared_parser: str           # Common parser type
    shared_template: str         # Common template name
    jobs: list[dict]             # [{name, servicer_id, did_count, unique_attributes}]
    total_dids_affected: int
    merge_recommendation: str    # "safe", "review", "risky"
    rationale: str               # Why this recommendation

@dataclass
class ConsolidationReport:
    groups: list[ConsolidationGroup]
    total_groups: int
    total_jobs_affected: int
    total_dids_affected: int

@dataclass
class ChangeSpec:
    change_type: str             # "delete_job", "rename_did", "change_filter", "move_servicer"
    target_job: str | None       # Job name for delete_job / change_filter
    target_did: str | None       # ImportDID for rename_did
    target_company_id: int | None
    new_value: str | None        # New DID value, new filter value, etc.
    raw_description: str         # Original user input

@dataclass
class AffectedEntity:
    entity_type: str             # "deal", "job", "did_mapping"
    identifier: str              # Job name or DID
    detail: str                  # What happens to this entity
    severity: str                # "high", "medium", "low"

@dataclass
class ImpactReport:
    change: ChangeSpec
    affected: list[AffectedEntity]
    coverage_before: int         # Number of covered DIDs
    coverage_after: int          # Projected after change
    coverage_delta: int          # Difference
    recent_activity: bool        # Whether affected jobs had activity in last 7 days
    risk_level: str              # "low", "medium", "high"
    recommendation: str          # Human-readable recommendation

@dataclass
class HealthSection:
    name: str                    # "XML Validation", "Coverage", etc.
    status: str                  # "pass", "warning", "fail"
    score: float                 # 0.0 – 100.0
    weight: float                # 0.0 – 1.0 (sum of all = 1.0)
    summary: str                 # One-line summary
    details: dict                # Section-specific details
    action_items: list[str]      # Recommended follow-ups

@dataclass
class HealthReport:
    sections: list[HealthSection]
    overall_score: float         # 0.0 – 100.0
    overall_status: str          # "Healthy", "Attention Needed", "Action Required"
    generated_at: str            # ISO timestamp
    xml_type: str                # "email", "sftp", "all"
```

### Serialization

All models follow the `to_dict()` pattern established in Phases 1–3:

```python
def to_dict(self) -> dict:
    return asdict(self)
```

---

## 4. Trend Analyzer Design

### Class: `TrendAnalyzer`

**Purpose:** Aggregate daily log event counts into time-series data with trend indicators.

**Dependencies:**
- `LogAnalytics` instance (from Phase 3)

### Algorithm (L-06)

```
Input: days=14, job_filter=None
1. Calculate date range: [today - days, today]
2. SQL: SELECT date(timestamp) as day,
              SUM(CASE event_type = 'email_processed' THEN 1 ELSE 0 END) AS files,
              SUM(CASE event_type = 'error' THEN 1 ELSE 0 END) AS errors,
              SUM(CASE event_type = 'did_mapping_failure' THEN 1 ELSE 0 END) AS did_fails,
              COUNT(DISTINCT CASE event_type = 'job_start' THEN job_name END) AS job_runs
        FROM log_events
        WHERE timestamp >= ? AND timestamp < ?
        [AND job_name LIKE ?]
        GROUP BY date(timestamp)
        ORDER BY day ASC
3. For each day, compare with previous day:
   - If files > prev: trend = "↑"
   - If files < prev: trend = "↓"
   - If files == prev: trend = "→"
4. Calculate period totals and averages.
5. If days*2 of data available, compare with previous period of same length
   for vs_previous_period delta.
6. Find worst_day (most errors) and best_day (most files, 0 errors).
7. Return TrendSummary.
```

### Edge Cases

| Case | Handling |
|------|----------|
| No data for requested period | Return empty days list, totals = 0 |
| Only partial data (e.g., 5 of 14 days) | Fill missing days with 0s |
| Single day requested | No trend indicator (first day = "→") |
| Stale index | Include staleness warning from Phase 3 `check_staleness()` |

---

## 5. Performance Benchmarker Design

### Class: `PerformanceBenchmarker`

**Purpose:** Rank all jobs by operational metrics to identify best- and worst-performing jobs.

**Dependencies:**
- `LogAnalytics` instance
- `SettingsXmlParser` instance (for complete job name list)

### Algorithm (L-07)

```
Input: sort_by="success_rate", ascending=True, top_n=None, days=30
1. Get all job names from SettingsXmlParser (email + SFTP).
2. For each job, query SQLite:
   a. Total runs: COUNT(DISTINCT date(timestamp)) WHERE event_type = 'job_start' AND job_name = ?
   b. Total files: COUNT(*) WHERE event_type = 'email_processed' AND job_name = ?
   c. Total errors: COUNT(*) WHERE event_type = 'error' AND job_name = ?
   d. Last run: MAX(timestamp) WHERE event_type = 'job_start' AND job_name = ?
3. Calculate:
   - success_rate = (total_runs - error_runs) / total_runs * 100
   - avg_files_per_run = total_files / total_runs
4. Determine status using Phase 3 thresholds:
   - ≥95% → "healthy"
   - ≥80% → "warning"
   - <80% → "critical"
5. Get common_errors: top 3 error detail strings by COUNT.
6. Sort by requested metric.
7. Apply top_n filter if specified.
8. Compile PerformanceSummary with aggregate counts.
```

### Performance Optimization

- **Batch query:** Instead of N individual queries, use a single aggregation grouped by job_name:
  ```sql
  SELECT job_name,
         COUNT(CASE WHEN event_type='job_start' THEN 1 END) as runs,
         COUNT(CASE WHEN event_type='email_processed' THEN 1 END) as files,
         COUNT(CASE WHEN event_type='error' THEN 1 END) as errors,
         MAX(CASE WHEN event_type='job_start' THEN timestamp END) as last_run
  FROM log_events
  WHERE timestamp >= date('now', '-{days} days')
  GROUP BY job_name
  ```
- **Jobs with no log data:** Include in results with total_runs=0, status="unknown".

---

## 6. Consolidation Analyzer Design

### Class: `ConsolidationAnalyzer`

**Purpose:** Detect groups of jobs that share identical configurations and could be merged.

**Dependencies:**
- `SettingsXmlParser` instance
- `DealRepository` instance (optional — for DID counts)

### Algorithm (A-01)

```
Input: xml_type="all"
1. Load all jobs from Settings.xml (email, SFTP, or both).
2. For each job, extract signature tuple:
   (mailbox, parser_class, template_name)
   - mailbox: Mailbox tag for email, Folder/Path for SFTP
   - parser_class: Top-level parser type name (e.g., "MailToParser", "MailToFolder")
   - template_name: Template/Queue name
3. Group jobs by signature.
4. Filter: only groups with ≥2 jobs are candidates.
5. For each group:
   a. Collect unique attributes per job (ServicerID, filters, DID mappings).
   b. If DealRepository available:
      - Count DIDs per ServicerID → total_dids_affected
   c. Determine merge_recommendation:
      - "safe" if all jobs have same parser attributes (only ServicerID differs)
      - "review" if parser attributes differ slightly (e.g., different SenderFilter)
      - "risky" if template configs differ or ServicerID overlap within group
   d. Generate rationale string.
6. Sort groups by total_dids_affected descending (largest impact first).
7. Return ConsolidationReport.
```

### Group Example

```
Consolidation Group #1:
  Shared: mailbox=rptent, parser=MailToParser, template=QueueToParser
  Jobs:
    - "CSMC 2015-1 rptent" (ServicerID=150, DIDs=23, SenderFilter="reports@csmc.com")
    - "CSMC 2015-2 rptent" (ServicerID=151, DIDs=18, SenderFilter="reports@csmc.com")
    - "CSMC 2016-1 rptent" (ServicerID=152, DIDs=12, SenderFilter="reports@csmc.com")
  Total DIDs: 53
  Recommendation: safe — identical parser config, only ServicerID differs
  Rationale: These 3 jobs share the same sender and could potentially be consolidated
             into a single job with a broader DID mapping.
```

---

## 7. Impact Simulator Design

### Class: `ImpactSimulator`

**Purpose:** Simulate the effect of a proposed configuration change without modifying anything.

**Dependencies:**
- `SettingsXmlParser` instance
- `DealRepository` instance
- `LogAnalytics` instance (for recent activity check)

### Change Type Handlers

| Change Type | Handler | Inputs | Analysis |
|-------------|---------|--------|----------|
| `delete_job` | `_sim_delete_job()` | job_name | Find all ServicerIDs → all DIDs → check if any other job covers them |
| `rename_did` | `_sim_rename_did()` | old_did, new_did, company_id | Find all jobs referencing old ImportDID → check for collisions with new |
| `change_filter` | `_sim_change_filter()` | job_name, filter_type, new_value | Evaluate how many emails would match/miss with new filter |
| `move_servicer` | `_sim_move_servicer()` | company_id, from_job, to_job | Check DID count, template compatibility, coverage continuity |

### Algorithm (A-02 — Delete Job Example)

```
Input: ChangeSpec(change_type="delete_job", target_job="CSMC 2015-1 rptent")

1. Find job in Settings.xml → get ServicerID.
2. Query DealRepository: all DIDs for this ServicerID → affected_dids.
3. For each affected DID:
   a. Check if any OTHER job covers this DID (via ImportDID mapping).
   b. If covered elsewhere → severity="low", detail="Also covered by job 'X'"
   c. If NOT covered → severity="high", detail="Would lose coverage"
4. Check LogAnalytics: any activity for this job in last 7 days?
   - If yes: recent_activity=True, risk_level ↑
5. Calculate coverage_before (current count), coverage_after (minus orphaned DIDs).
6. Determine overall risk_level:
   - "low": No uncovered DIDs, no recent activity
   - "medium": Some uncovered DIDs OR recent activity
   - "high": Many uncovered DIDs AND recent activity
7. Generate recommendation text.
8. Return ImpactReport.
```

### LLM Intent Parsing (A-02)

The `/analyze impact` command accepts natural language. The Extension handler uses the LLM to parse intent into a `ChangeSpec`:

```
User: "@frp /analyze impact delete job CSMC 2015-1 rptent"

LLM prompt (system): You are a configuration change parser. Extract the change type
and parameters from the user's request. Return ONLY valid JSON.

LLM response:
{
  "change_type": "delete_job",
  "target_job": "CSMC 2015-1 rptent",
  "target_did": null,
  "target_company_id": null,
  "new_value": null
}
```

**Fallback:** If LLM parsing fails, the CLI also supports explicit flags:
```bash
python -m cli.main analyze_impact --change-type delete_job --target-job "CSMC 2015-1 rptent"
```

---

## 8. Health Checker Design

### Class: `HealthChecker`

**Purpose:** Orchestrate all diagnostic checks from Phases 1–4 into a single unified report.

**Dependencies:** (all injected)
- `SettingsXmlParser` — for validation (J-05)
- `CoverageAnalyzer` — for coverage summary (D-01)
- `OrphanDetector` — for orphan count (D-02)
- `CollisionDetector` — for collision count (D-03)
- `LogAnalytics` — for staleness + DID failures (P3)
- `PerformanceBenchmarker` — for job performance summary (P4)

### Health Sections (9 total)

| # | Section | Weight | Source | Score Calculation |
|---|---------|--------|--------|-------------------|
| 1 | XML Validation | 0.15 | J-05 `validate()` | 100 if 0 errors, -20 per error, min 0 |
| 2 | Coverage Rate | 0.20 | D-01 `analyze()` | (covered_dids / total_dids) × 100 |
| 3 | Orphan DIDs | 0.10 | D-02 `detect()` | 100 if 0 orphans, max(0, 100 - orphan_count × 5) |
| 4 | ImportDID Collisions | 0.10 | D-03 `detect()` | 100 if 0 collisions, max(0, 100 - collision_count × 10) |
| 5 | Template Distribution | 0.05 | J-04 `inventory()` | 100 (informational only, always passes) |
| 6 | Log Freshness | 0.10 | P3 `check_staleness()` | 100 if synced <24h ago, 50 if <48h, 0 if >48h |
| 7 | DID Failure Rate | 0.10 | P3 `did_failures()` | max(0, 100 - failure_count × 2) |
| 8 | Job Performance | 0.15 | P4 `benchmark()` | avg_success_rate across all jobs |
| 9 | Recent Errors | 0.05 | P3 `daily_summary()` | 100 if 0 errors today, -10 per error, min 0 |

### Algorithm (A-03)

```
Input: xml_type="all"
1. Initialize sections = [].
2. For each health section (1-9):
   a. Call the appropriate source function with try/except.
   b. If source unavailable (e.g., DB down), section.status = "warning",
      section.score = 50, section.summary = "Unable to check: {error}".
   c. Calculate section score per table above.
   d. Determine section status:
      - score ≥ 90 → "pass"
      - score ≥ 70 → "warning"
      - score < 70 → "fail"
   e. Generate action_items for any non-pass sections.
   f. Append HealthSection to sections.
3. Calculate overall_score = Σ(section.score × section.weight).
4. Determine overall_status:
   - ≥ 90 → "Healthy"
   - ≥ 70 → "Attention Needed"
   - < 70 → "Action Required"
5. Return HealthReport.
```

### Graceful Degradation

Phase 4's health check must handle missing dependencies gracefully:

| Scenario | Behavior |
|----------|----------|
| DB unavailable | Coverage/orphan/collision sections get score=50, status="warning" |
| SQLite not synced | Log sections get score=0, status="fail", suggest "Run @frp /logs sync" |
| SFTP Settings.xml missing | SFTP sections skipped, email-only report |
| Any section throws exception | Catch, log, section.status="fail", continue with remaining |

---

## 9. CLI Command Specifications

### New Commands (5)

#### `log_trends`

```
python -m cli.main log_trends [--days 14] [--job JOB_NAME] --db-path SQLITE_PATH
```

**Response:**
```json
{
  "success": true,
  "command": "log_trends",
  "data": {
    "period": {"start": "2026-02-10", "end": "2026-02-24", "days": 14},
    "days": [
      {"date": "2026-02-24", "total_files": 123, "total_errors": 2,
       "did_failures": 1, "job_runs": 48, "trend_files": "↑", "trend_errors": "↓"},
      ...
    ],
    "summary": {
      "period_total_files": 1534,
      "period_total_errors": 18,
      "period_avg_files_per_day": 109.6,
      "vs_previous_period": {"files_delta_pct": 12.3, "errors_delta_pct": -5.1},
      "worst_day": "2026-02-15",
      "best_day": "2026-02-22"
    },
    "staleness_warning": null
  }
}
```

#### `log_performance`

```
python -m cli.main log_performance [--sort success_rate] [--top 10] [--days 30] --db-path SQLITE_PATH --settings-path SETTINGS_PATH
```

**Response:**
```json
{
  "success": true,
  "command": "log_performance",
  "data": {
    "entries": [
      {"job_name": "bonds mailbox", "job_type": "email", "total_runs": 30,
       "success_rate": 67.3, "avg_files_per_run": 2.1, "total_errors": 10,
       "last_run": "2026-02-24T08:00:00", "status": "critical",
       "common_errors": ["Connection timeout", "SMTP auth failure"]},
      ...
    ],
    "summary": {
      "total_jobs": 48, "healthy_count": 40, "warning_count": 5,
      "critical_count": 3, "avg_success_rate": 94.2
    }
  }
}
```

#### `analyze_consolidation`

```
python -m cli.main analyze_consolidation [--type email|sftp|all] --settings-path SETTINGS_PATH [--db-conn-str CONN]
```

**Response:**
```json
{
  "success": true,
  "command": "analyze_consolidation",
  "data": {
    "groups": [
      {
        "group_id": 1,
        "shared_mailbox": "rptent",
        "shared_parser": "MailToParser",
        "shared_template": "QueueToParser",
        "jobs": [
          {"name": "CSMC 2015-1 rptent", "servicer_id": "150", "did_count": 23,
           "unique_attributes": {"SenderFilter": "reports@csmc.com"}},
          {"name": "CSMC 2015-2 rptent", "servicer_id": "151", "did_count": 18,
           "unique_attributes": {"SenderFilter": "reports@csmc.com"}}
        ],
        "total_dids_affected": 41,
        "merge_recommendation": "safe",
        "rationale": "Identical parser config with same sender filter. Only ServicerID differs."
      }
    ],
    "total_groups": 3,
    "total_jobs_affected": 9,
    "total_dids_affected": 127
  }
}
```

#### `analyze_impact`

```
python -m cli.main analyze_impact --change-type delete_job --target-job "CSMC 2015-1 rptent" --settings-path SETTINGS_PATH --db-conn-str CONN [--db-path SQLITE_PATH]
```

**Response:**
```json
{
  "success": true,
  "command": "analyze_impact",
  "data": {
    "change": {
      "change_type": "delete_job",
      "target_job": "CSMC 2015-1 rptent",
      "raw_description": "delete job CSMC 2015-1 rptent"
    },
    "affected": [
      {"entity_type": "deal", "identifier": "CSMC0001", "detail": "Would lose coverage — no other job handles this DID", "severity": "high"},
      {"entity_type": "deal", "identifier": "CSMC0002", "detail": "Also covered by 'CSMC 2015-2 rptent'", "severity": "low"}
    ],
    "coverage_before": 23,
    "coverage_after": 18,
    "coverage_delta": -5,
    "recent_activity": true,
    "risk_level": "high",
    "recommendation": "This job had 12 files processed in the last 7 days. Deleting it would orphan 5 DIDs. Consider migrating ServicerID 150 to another job before deleting."
  }
}
```

#### `analyze_health`

```
python -m cli.main analyze_health [--type email|sftp|all] --settings-path SETTINGS_PATH --db-conn-str CONN --db-path SQLITE_PATH
```

**Response:**
```json
{
  "success": true,
  "command": "analyze_health",
  "data": {
    "sections": [
      {"name": "XML Validation", "status": "pass", "score": 100.0,
       "weight": 0.15, "summary": "0 errors, 2 warnings",
       "details": {"errors": 0, "warnings": 2}, "action_items": []},
      {"name": "Coverage Rate", "status": "pass", "score": 96.2,
       "weight": 0.20, "summary": "2,856 of 2,967 DIDs covered (96.2%)",
       "details": {"covered": 2856, "total": 2967}, "action_items": []},
      {"name": "Orphan DIDs", "status": "warning", "score": 75.0,
       "weight": 0.10, "summary": "5 orphan DIDs found in 2 mailboxes",
       "details": {"orphan_count": 5}, "action_items": ["@frp /deals orphans"]},
      ...
    ],
    "overall_score": 84.3,
    "overall_status": "Attention Needed",
    "generated_at": "2026-02-24T12:00:00",
    "xml_type": "all"
  }
}
```

---

## 10. Extension Handler Specifications

### New Handler: `handleAnalyze()`

```
extension/handlers/analyze.js

Routes:
  /analyze consolidation  → CLI: analyze_consolidation
  /analyze impact <desc>  → LLM parse intent → CLI: analyze_impact
  /analyze health         → CLI: analyze_health
```

**Intent Parsing for `/analyze impact`:**

```javascript
// Use vscode.lm API to parse natural language change description
const parsePrompt = `You are a configuration change parser for an email monitoring system.
Parse the user's change description into a structured change spec.
Return ONLY valid JSON with these fields:
- change_type: one of "delete_job", "rename_did", "change_filter", "move_servicer"
- target_job: job name if applicable (string or null)
- target_did: ImportDID keyword if applicable (string or null)  
- target_company_id: CompanyID if applicable (number or null)
- new_value: new value if applicable (string or null)

User description: "${userDescription}"`;
```

**Fallback:** If LLM returns invalid JSON, show error and suggest structured input:
```
Could not parse your change description. Try:
@frp /analyze impact --change-type delete_job --target-job "CSMC 2015-1 rptent"
```

### Updated Handler: `handleLogs()`

Add routing for `trends` and `performance` subcommands:

```javascript
// handlers/logs.js — additions
case 'trends':
    const trendArgs = { days: extractDays(prompt) || 14, job: extractJobName(prompt) };
    result = await runCliJson('log_trends', trendArgs);
    break;
case 'performance':
    const perfArgs = { sort: extractSort(prompt) || 'success_rate', top: extractTop(prompt) };
    result = await runCliJson('log_performance', perfArgs);
    break;
```

### Follow-Up Suggestion Table

| Command | Result Condition | Follow-Up |
|---------|-----------------|-----------|
| `/logs trends` | Errors increasing | `/logs failures`, `/logs health <worst_job>` |
| `/logs trends` | Volume dropping | `/analyze health` |
| `/logs performance` | Critical jobs found | `/logs health <job>`, `/analyze impact` |
| `/analyze consolidation` | Groups found | `/deals servicer <id>`, `/analyze impact merge` |
| `/analyze impact` | High risk | `/jobs show <affected>`, `/deals servicer <id>` |
| `/analyze impact` | Low risk | `/jobs edit <target>`, `/deploy save` |
| `/analyze health` | Score < 70 | Action items from each failing section |
| `/analyze health` | Score ≥ 90 | "System is healthy. No action needed." |

---

## 11. Data Flow Diagrams

### L-06: Timeline Trends

```
User: @frp /logs trends --days 30
    │
    ▼
participant.js → handleLogs("trends", {days: 30})
    │
    ▼
runCliJson("log_trends", {days: 30, db_path: ...})
    │
    ▼
cli/main.py: cmd_log_trends()
    │
    ├── TrendAnalyzer(LogAnalytics(db_path))
    │       │
    │       ├── SQL: GROUP BY date(timestamp) for 30 days
    │       ├── Calculate trend indicators (↑/↓/→)
    │       └── Compare with previous 30-day period
    │
    └── Return TrendSummary.to_dict()
    │
    ▼
handleLogs() receives JSON
    │
    ▼
vscode.lm: "Summarize these trends in natural language"
    │
    ▼
Stream to chat: "Over the past 30 days, file volume averaged 109.6/day (↑12% vs prior period)..."
    │
    ▼
Follow-ups: [/logs health bonds, /logs failures]
```

### A-02: Impact Simulation

```
User: @frp /analyze impact delete job "CSMC 2015-1 rptent"
    │
    ▼
participant.js → handleAnalyze("impact", prompt)
    │
    ├── vscode.lm: Parse intent → ChangeSpec JSON
    │   {"change_type": "delete_job", "target_job": "CSMC 2015-1 rptent"}
    │
    ▼
runCliJson("analyze_impact", {
    change_type: "delete_job",
    target_job: "CSMC 2015-1 rptent",
    settings_path, db_conn_str, db_path
})
    │
    ▼
cli/main.py: cmd_analyze_impact()
    │
    ├── ImpactSimulator(parser, repo, analytics)
    │       │
    │       ├── Find job → ServicerID = 150
    │       ├── DealRepository: get DIDs for ServicerID 150 → 23 DIDs
    │       ├── For each DID: check other jobs → 5 uncovered
    │       ├── LogAnalytics: recent activity? → Yes, 12 files last 7 days
    │       └── risk_level = "high"
    │
    └── Return ImpactReport.to_dict()
    │
    ▼
handleAnalyze() receives JSON
    │
    ▼
vscode.lm: "Explain this impact analysis in conversational English"
    │
    ▼
Stream to chat: "⚠️ HIGH RISK: Deleting 'CSMC 2015-1 rptent' would affect 23 deals.
5 DIDs would lose all coverage. The job processed 12 files in the last week."
    │
    ▼
Follow-ups: [/deals servicer 150, /jobs show "CSMC 2015-1 rptent"]
```

### A-03: Full Health Check

```
User: @frp /analyze health
    │
    ▼
participant.js → handleAnalyze("health", {type: "all"})
    │
    ▼
runCliJson("analyze_health", {type: "all", settings_path, db_conn_str, db_path})
    │
    ▼
cli/main.py: cmd_analyze_health()
    │
    ├── HealthChecker(parser, repo, analytics, coverage, orphans, collisions, benchmarker)
    │       │
    │       ├── Section 1: parser.validate()        → XML Validation score
    │       ├── Section 2: coverage.analyze()        → Coverage Rate score
    │       ├── Section 3: orphans.detect()          → Orphan DIDs score
    │       ├── Section 4: collisions.detect()       → Collisions score
    │       ├── Section 5: coverage.template_dist()  → Template Distribution
    │       ├── Section 6: analytics.check_staleness()→ Log Freshness
    │       ├── Section 7: analytics.did_failures()  → DID Failure Rate
    │       ├── Section 8: benchmarker.benchmark()   → Job Performance avg
    │       └── Section 9: analytics.daily_summary() → Recent Errors
    │       │
    │       ├── overall_score = Σ(section.score × weight)
    │       └── overall_status = threshold(overall_score)
    │
    └── Return HealthReport.to_dict()
    │
    ▼
handleAnalyze() receives JSON
    │
    ▼
vscode.lm: "Generate an executive summary of this health report"
    │
    ▼
Stream to chat:
    "📊 System Health: 84.3/100 — Attention Needed
    
    ✅ XML Validation: 0 errors
    ✅ Coverage: 96.2% (2,856/2,967)
    ⚠️ Orphans: 5 unmapped DIDs
    ⚠️ Job Performance: 3 critical jobs
    
    Recommended actions:
    • @frp /deals orphans — Review 5 orphan DIDs
    • @frp /logs health bonds — Investigate critical job"
    │
    ▼
Follow-ups: [/deals orphans, /logs health bonds, /logs failures]
```

---

*End of Phase 4 System Design.*
