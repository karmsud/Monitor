# Phase 3: System Design
## FRP Agent — Log Analytics & Email Triage Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  

---

## Table of Contents
1. [Module Map](#1-module-map)
2. [New Data Models](#2-new-data-models)
3. [Log Analytics Engine](#3-log-analytics-engine)
4. [Email Triage Pipeline](#4-email-triage-pipeline)
5. [CLI Command Specifications](#5-cli-command-specifications)
6. [Extension Handler Updates](#6-extension-handler-updates)
7. [Data Flow Diagrams](#7-data-flow-diagrams)
8. [Stale Index Detection](#8-stale-index-detection)

---

## 1. Module Map

### Phase 3 Module Overview

```
backend/
├── logs/
│   ├── parser.py                  # Phase 1 — unchanged
│   ├── indexer.py                 # Phase 1 — unchanged
│   └── analytics.py               # NEW — Query engine over SQLite index
├── triage/
│   ├── __init__.py                # NEW
│   ├── models.py                  # NEW — EmailInfo, TriageResult, MatchResult
│   ├── msg_parser.py              # NEW — .msg file parsing with extract-msg
│   ├── matcher.py                 # NEW — Email ↔ job filter matching
│   └── analyzer.py                # NEW — No-match analysis + template suggestion
├── xml/
│   ├── parser.py                  # Phase 1 — unchanged
│   ├── writer.py                  # Phase 1 — unchanged
│   ├── models.py                  # Phase 1+2 — unchanged
│   ├── crud.py                    # Phase 2 — unchanged
│   ├── templates.py               # Phase 2 — used by analyzer.py
│   ├── diff.py                    # Phase 2 — unchanged
│   └── rollback.py                # Phase 2 — unchanged
├── intel/
│   ├── coverage.py                # Phase 2 — used by analyzer.py (gap check)
│   ├── orphans.py                 # Phase 2 — unchanged
│   └── collisions.py              # Phase 2 — unchanged
├── db/
│   ├── connection.py              # Phase 1 — unchanged
│   └── deal_repo.py               # Phase 1+2 — add resolve_did_by_name()
└── common/
    └── errors.py                  # Phase 1 — add TRIAGE error codes
```

### Module Dependency Graph

```
analytics.py ──→ indexer.py (SQLite queries)
             ──→ deal_repo.py (DID name resolution for L-02)

msg_parser.py ──→ extract-msg (external library)

matcher.py ──→ msg_parser.py (parsed email data)
           ──→ parser.py (job filter data)

analyzer.py ──→ msg_parser.py (parsed email data)
            ──→ matcher.py (match results)
            ──→ templates.py (template inventory)
            ──→ coverage.py (gap analysis)
            ──→ deal_repo.py (DID lookup)
```

---

## 2. New Data Models

### triage/models.py

```python
@dataclass
class EmailInfo:
    """Parsed .msg file metadata."""
    sender: str                    # From address
    sender_name: str               # Display name
    subject: str                   # Subject line
    date: str                      # ISO timestamp
    to: list[str]                  # To recipients
    cc: list[str]                  # CC recipients
    body_preview: str              # First 500 chars of body (never sent to LLM)
    attachment_names: list[str]    # Filenames only (no content)
    file_path: str                 # Source .msg path
    
    def to_dict(self) -> dict: ...
    def to_safe_dict(self) -> dict:
        """Return metadata safe for LLM (no body, no full addresses)."""
        return {
            "sender_domain": self.sender.split("@")[-1] if "@" in self.sender else "",
            "sender_name": self.sender_name,
            "subject": self.subject,
            "date": self.date,
            "attachment_count": len(self.attachment_names),
            "attachment_names": self.attachment_names,
        }
```

```python
@dataclass
class MatchResult:
    """Single job match for an email."""
    job_name: str
    xml_type: str                  # "email" or "sftp"
    match_type: str                # "sender", "subject", "both"
    match_confidence: str          # "exact", "partial"
    servicer_id: str | None
    matched_filter: str            # The filter value that matched
    email_field_matched: str       # Which email field triggered the match

    def to_dict(self) -> dict: ...
```

```python
@dataclass
class TriageResult:
    """Complete triage analysis result."""
    email_info: EmailInfo
    matches: list[MatchResult]
    has_match: bool
    coverage_status: str | None    # "covered", "partial", "no_coverage", None
    did_count: int | None          # Number of DIDs for matched servicer
    suggested_template: str | None # Template name if no match (E-03)
    suggested_config: dict | None  # Recommended field values (E-03)
    recommendation: str            # LLM-friendly summary for the user
    
    def to_dict(self) -> dict: ...
```

### logs/analytics.py — Return Models

```python
@dataclass
class DealActivity:
    """Single log event for a deal."""
    timestamp: str
    job_name: str
    event_type: str
    detail: str                    # Subject, filename, error text
    log_file: str

    def to_dict(self) -> dict: ...
```

```python
@dataclass
class DIDFailure:
    """Aggregated DID mapping failure."""
    import_did: str                # The failed keyword
    failure_count: int
    affected_jobs: list[str]
    first_seen: str                # ISO timestamp
    last_seen: str                 # ISO timestamp

    def to_dict(self) -> dict: ...
```

```python
@dataclass
class JobHealth:
    """Health metrics for a single job."""
    job_name: str
    total_runs: int
    successful_runs: int
    error_count: int
    success_rate: float            # 0.0 - 100.0
    status: str                    # "healthy", "warning", "critical"
    last_run: str | None           # ISO timestamp
    last_error: str | None         # Most recent error text
    avg_emails_per_run: float
    common_errors: list[dict]      # [{"error": "...", "count": N}]
    date_range: str                # "Last 30 days"

    def to_dict(self) -> dict: ...
```

```python
@dataclass
class DailySummary:
    """Operational summary for a single day."""
    date: str                      # YYYY-MM-DD
    total_jobs_run: int
    total_emails_processed: int
    total_files_loaded: int
    total_errors: int
    total_did_failures: int
    top_jobs_by_volume: list[dict] # [{"job": "...", "emails": N}]
    top_error_sources: list[dict]  # [{"job": "...", "errors": N}]
    comparison: dict | None        # {"prev_date": "...", "delta_emails": +5, ...}

    def to_dict(self) -> dict: ...
```

---

## 3. Log Analytics Engine

### analytics.py — Query Design

The analytics engine queries the SQLite log index populated by Phase 1's `L-01` sync command. All queries use parameterized SQL against the `log_events` table.

### SQLite Schema Reminder (from Phase 1)

```sql
CREATE TABLE log_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_file    TEXT NOT NULL,
    timestamp   TEXT NOT NULL,       -- ISO-8601
    job_name    TEXT,
    event_type  TEXT NOT NULL,       -- job_start, email_found, email_processed,
                                    -- did_mapping_failure, error, job_end
    detail      TEXT,                -- Subject, filename, error message
    extra       TEXT                 -- JSON blob for additional fields
);

CREATE INDEX idx_events_type_ts ON log_events(event_type, timestamp);
CREATE INDEX idx_events_job ON log_events(job_name);
CREATE INDEX idx_events_detail ON log_events(detail);

CREATE TABLE log_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT UNIQUE NOT NULL,
    file_path   TEXT NOT NULL,
    parsed_at   TEXT NOT NULL,
    event_count INTEGER
);

CREATE TABLE sync_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### L-02: Deal Activity Query Algorithm

```
INPUT: did_identifier (str), days (int = 30)
1. Resolve DID:
   a. If numeric → query tblExternalDIDRef for ImportDID by DID number
   b. If string → use as ImportDID keyword directly
2. Query SQLite: SELECT * FROM log_events
     WHERE detail LIKE '%{import_did}%'
       AND timestamp >= date('now', '-{days} days')
     ORDER BY timestamp DESC
3. Return list[DealActivity]
```

### L-03: DID Failure Analysis Algorithm

```
INPUT: days (int = 30), job_filter (str | None = None)
1. Query SQLite: SELECT detail, COUNT(*) as cnt, 
     GROUP_CONCAT(DISTINCT job_name) as jobs,
     MIN(timestamp) as first_seen, MAX(timestamp) as last_seen
   FROM log_events
   WHERE event_type = 'did_mapping_failure'
     AND timestamp >= date('now', '-{days} days')
     {AND job_name = '{job_filter}' if job_filter}
   GROUP BY detail
   ORDER BY cnt DESC
2. Extract ImportDID keyword from detail (regex: "Did not find DID mapping for \[(.+?)\]")
3. Return list[DIDFailure]
```

### L-04: Job Health Algorithm

```
INPUT: job_name (str), days (int = 30)
1. Resolve job name:
   a. Exact match against log_events.job_name
   b. If no exact match → LIKE '%{job_name}%' (fuzzy)
   c. If multiple matches → raise ValueError with match list
2. Query run count: COUNT(DISTINCT log_file) WHERE job_name = X AND event_type = 'job_start'
3. Query error count: COUNT(*) WHERE job_name = X AND event_type = 'error'
4. Query email volume: COUNT(*) WHERE job_name = X AND event_type = 'email_processed'
5. Compute success_rate: ((total_runs - error_runs) / total_runs) * 100
6. Determine status: 
   - >95% → "healthy" 
   - 80-95% → "warning"
   - <80% → "critical"
7. Return JobHealth
```

### L-05: Daily Summary Algorithm

```
INPUT: date (str = 'today')
1. Resolve date: parse to YYYY-MM-DD, default to today
2. Query totals for the date:
   - jobs_run: COUNT(DISTINCT job_name) WHERE event_type = 'job_start' AND date(timestamp) = date
   - emails_processed: COUNT(*) WHERE event_type = 'email_processed' AND ...
   - files_loaded: COUNT(*) WHERE event_type IN ('files_loaded', 'email_processed') AND ...
   - errors: COUNT(*) WHERE event_type = 'error' AND ...
   - did_failures: COUNT(*) WHERE event_type = 'did_mapping_failure' AND ...
3. Top 5 jobs by volume: GROUP BY job_name ORDER BY cnt DESC LIMIT 5
4. Top 5 error sources: GROUP BY job_name WHERE event_type = 'error' ORDER BY cnt DESC LIMIT 5
5. If previous day data exists:
   - Query same metrics for (date - 1 day)
   - Compute deltas
6. Return DailySummary
```

---

## 4. Email Triage Pipeline

### msg_parser.py — .msg Parsing

```
INPUT: msg_path (str) — path to .msg file
1. Validate file exists and has .msg extension
2. Open with extract_msg.Message(msg_path)
3. Extract fields:
   - sender = msg.sender
   - sender_name = msg.senderName or ""
   - subject = msg.subject or ""
   - date = msg.date (as ISO string)
   - to = [r.email for r in msg.recipients if r.type == 'to']
   - cc = [r.email for r in msg.recipients if r.type == 'cc']
   - body_preview = msg.body[:500] if msg.body else ""
   - attachment_names = [a.longFilename for a in msg.attachments]
4. Return EmailInfo dataclass
5. Close msg handle
```

### matcher.py — Email ↔ Job Filter Matching

```
INPUT: email_info (EmailInfo), jobs (list[EmailJob | SftpJob]) from parser
1. For each job:
   a. Extract filter fields:
      - Email jobs: SubjectFilter, SenderFilter (from Parsers/Parser elements)
      - SFTP jobs: FileNameFilter, PathFilter
   b. Compare email.sender against SenderFilter:
      - Case-insensitive substring match
      - If match → match_type = "sender", confidence = "exact" if full match else "partial"
   c. Compare email.subject against SubjectFilter:
      - Case-insensitive substring match
      - If match → match_type = "subject", confidence per above
   d. Both match → match_type = "both"
   e. If any match → create MatchResult, add to matches list
2. Sort matches:
   - "both" > "sender" > "subject"
   - "exact" > "partial" within same match_type
3. Return list[MatchResult]
```

### Filter Extraction from Settings.xml

Email jobs have nested parser configurations with filter values:

```xml
<MailboxMonitor>
  <Name>CSMC 2015-1 rptent</Name>
  <Mailbox>rptent@bank.com</Mailbox>
  <ServicerID>150</ServicerID>
  <Parsers>
    <Parser>
      <ParserDll>MailToFolder</ParserDll>
      <SubjectFilter>CSMC 2015</SubjectFilter>
      <SenderFilter>reports@csmc.com</SenderFilter>
      <Templates>
        <Template>
          <TemplateName>rptent_csmc</TemplateName>
        </Template>
      </Templates>
    </Parser>
  </Parsers>
</MailboxMonitor>
```

Matching fields for triage:
| XML Element | Email Field Compared Against |
|-------------|------------------------------|
| `SubjectFilter` | `email_info.subject` |
| `SenderFilter` | `email_info.sender` and `email_info.sender_name` |
| `Mailbox` | `email_info.to` (if email was sent to this mailbox) |
| `Name` (job name) | Informational only — not used for matching |

### analyzer.py — No-Match Analysis (E-03)

```
INPUT: email_info (EmailInfo), settings_path (str), db_mode (str)
1. Run matcher.py → confirm no matches (or very low confidence matches)
2. Run template_inventory() from Phase 2:
   - Analyze email attachments to guess parser type:
     - .csv, .xlsx → "MailToFolder" or "MailToParser"
     - .pdf → "MailToFolder" (store only)
     - No attachments → likely notification email
3. Extract servicer hints from email:
   - Sender domain → could map to Company name
   - Subject keywords → could match ImportDID patterns
4. If sender domain maps to a known company:
   - Run coverage_gaps(servicer_id) to check existing coverage
5. Compile recommendation:
   - suggested_template: best matching template from inventory
   - suggested_config: {
       "mailbox": email_info.to[0] if applicable,
       "subject_filter": extracted pattern from subject,
       "sender_filter": email_info.sender,
       "servicer_id": resolved servicer ID or "UNKNOWN"
     }
   - recommendation: Natural language summary
6. Return TriageResult
```

---

## 5. CLI Command Specifications

### log_deal_activity

```
python -m cli.main log_deal_activity --did "CSFB 2006-HEAT5" --days 30 --db-mode mysql --secrets-path ./secrets
```

**Response:**
```json
{
  "success": true,
  "command": "log_deal_activity",
  "data": {
    "did_identifier": "CSFB 2006-HEAT5",
    "resolved_import_did": "CSFB",
    "date_range": "Last 30 days",
    "total_events": 42,
    "events": [
      {
        "timestamp": "2026-02-24T08:30:15",
        "job_name": "CSFB 2006-HEAT5 rptent",
        "event_type": "email_processed",
        "detail": "Subject: Monthly Report Feb 2026",
        "log_file": "EmailMonitor_Settings.20260224083000000.log"
      }
    ]
  }
}
```

### log_did_failures

```
python -m cli.main log_did_failures --days 7 --db-path ./frp_logs.db
```

**Response:**
```json
{
  "success": true,
  "command": "log_did_failures",
  "data": {
    "date_range": "Last 7 days",
    "total_unique_failures": 5,
    "failures": [
      {
        "import_did": "UNKNOWNKW",
        "failure_count": 23,
        "affected_jobs": ["rptent mailbox", "bonds mailbox"],
        "first_seen": "2026-02-17T10:00:00",
        "last_seen": "2026-02-24T14:30:00"
      }
    ]
  }
}
```

### log_job_health

```
python -m cli.main log_job_health --job-name "CSMC 2015-1 rptent" --days 30 --db-path ./frp_logs.db
```

**Response:**
```json
{
  "success": true,
  "command": "log_job_health",
  "data": {
    "job_name": "CSMC 2015-1 rptent",
    "total_runs": 120,
    "successful_runs": 118,
    "error_count": 2,
    "success_rate": 98.3,
    "status": "healthy",
    "last_run": "2026-02-24T14:00:00",
    "last_error": "Connection timeout at 2026-02-22T09:15:00",
    "avg_emails_per_run": 3.5,
    "common_errors": [
      {"error": "Connection timeout", "count": 2}
    ],
    "date_range": "Last 30 days"
  }
}
```

### log_daily_summary

```
python -m cli.main log_daily_summary --date 2026-02-24 --db-path ./frp_logs.db
```

**Response:**
```json
{
  "success": true,
  "command": "log_daily_summary",
  "data": {
    "date": "2026-02-24",
    "total_jobs_run": 48,
    "total_emails_processed": 312,
    "total_files_loaded": 1547,
    "total_errors": 3,
    "total_did_failures": 12,
    "top_jobs_by_volume": [
      {"job": "rptent mailbox", "emails": 87},
      {"job": "bonds mailbox", "emails": 64}
    ],
    "top_error_sources": [
      {"job": "sftp_job_3", "errors": 2}
    ],
    "comparison": {
      "prev_date": "2026-02-23",
      "delta_emails": 15,
      "delta_errors": -1,
      "delta_did_failures": 3
    }
  }
}
```

### triage_verify

```
python -m cli.main triage_verify --msg-path "./inbox/request.msg" --settings-path "C:\FRP\Settings.xml" --db-mode mysql --secrets-path ./secrets
```

**Response:**
```json
{
  "success": true,
  "command": "triage_verify",
  "data": {
    "email_info": {
      "sender": "reports@csmc.com",
      "sender_name": "CSMC Reports",
      "subject": "CSMC 2015-1 Monthly Report",
      "date": "2026-02-24T10:00:00",
      "attachment_names": ["report.csv"]
    },
    "matches": [
      {
        "job_name": "CSMC 2015-1 rptent",
        "xml_type": "email",
        "match_type": "both",
        "match_confidence": "exact",
        "servicer_id": "150",
        "matched_filter": "CSMC 2015",
        "email_field_matched": "subject"
      }
    ],
    "has_match": true,
    "coverage_status": "covered",
    "did_count": 3,
    "recommendation": "Email matches existing job 'CSMC 2015-1 rptent' with 3 DIDs covered."
  }
}
```

### triage_match

```
python -m cli.main triage_match --msg-path "./inbox/unknown.msg" --settings-path "C:\FRP\Settings.xml"
```

**Response:**
```json
{
  "success": true,
  "command": "triage_match",
  "data": {
    "email_info": {
      "sender": "notifications@newbank.com",
      "subject": "New Bank Monthly Statement"
    },
    "matches": [
      {
        "job_name": "General Notifications",
        "match_type": "subject",
        "match_confidence": "partial",
        "servicer_id": null
      }
    ],
    "total_matches": 1,
    "recommendation": "1 partial match found. Review match details and confirm relevance."
  }
}
```

### triage_new

```
python -m cli.main triage_new --msg-path "./inbox/new_request.msg" --settings-path "C:\FRP\Settings.xml" --db-mode mysql --secrets-path ./secrets
```

**Response:**
```json
{
  "success": true,
  "command": "triage_new",
  "data": {
    "email_info": {
      "sender": "servicing@newcorp.com",
      "subject": "NewCorp Deal Report Q1 2026",
      "attachment_names": ["report.xlsx"]
    },
    "matches": [],
    "has_match": false,
    "suggested_template": "MailToFolder — rptent",
    "suggested_config": {
      "mailbox": "rptent@bank.com",
      "subject_filter": "NewCorp",
      "sender_filter": "servicing@newcorp.com",
      "servicer_id": "UNKNOWN"
    },
    "coverage_status": "no_coverage",
    "recommendation": "No matching job found. Suggested template: 'MailToFolder — rptent'. Use /jobs create rptent to get started."
  }
}
```

---

## 6. Extension Handler Updates

### /logs Handler — Phase 3 Additions

```javascript
// chat/participant.js — COMMAND_HANDLERS['/logs'] update

// Phase 1 subcommands: sync
// Phase 3 additions:
const LOG_SUBCOMMANDS = {
    'sync':     { cmd: 'sync_logs', ... },           // Phase 1
    'deal':     { cmd: 'log_deal_activity', ... },    // Phase 3
    'failures': { cmd: 'log_did_failures', ... },     // Phase 3
    'health':   { cmd: 'log_job_health', ... },       // Phase 3
    'summary':  { cmd: 'log_daily_summary', ... },    // Phase 3
};
```

### /triage Handler — New

```javascript
// chat/participant.js — new COMMAND_HANDLERS['/triage']

const TRIAGE_SUBCOMMANDS = {
    'verify': { cmd: 'triage_verify',  requiresMsgPath: true },
    'match':  { cmd: 'triage_match',   requiresMsgPath: true },
    'new':    { cmd: 'triage_new',     requiresMsgPath: true },
};
```

### .msg File Path Detection

```javascript
// Detect .msg file path in user input
function extractMsgPath(userMessage) {
    // Match quoted paths or paths ending in .msg
    const patterns = [
        /"([^"]+\.msg)"/i,          // "path/to/file.msg"
        /'([^']+\.msg)'/i,          // 'path/to/file.msg'
        /(\S+\.msg)\b/i,            // path/to/file.msg (no quotes)
    ];
    for (const p of patterns) {
        const m = userMessage.match(p);
        if (m) return m[1];
    }
    return null;
}
```

### Follow-up Suggestions

| After Command | Suggested Follow-ups |
|---------------|---------------------|
| `/logs deal` | "Check job health", "View failures" |
| `/logs failures` | "Coverage gaps for top failure", "Job health" |
| `/logs health` | "View deal activity", "Daily summary" |
| `/logs summary` | "Check failures", "Sync logs" |
| `/triage verify` (match) | "Job health for {job}", "Servicer dossier" |
| `/triage verify` (no match) | "Triage new", "Coverage gaps" |
| `/triage match` | "Verify email", "Triage new" |
| `/triage new` | "Create job from template", "Coverage gaps" |

---

## 7. Data Flow Diagrams

### L-02: Deal Activity Flow

```
User: @frp /logs deal CSFB 2006-HEAT5
  │
  ├─→ Extension: parse "deal CSFB 2006-HEAT5"
  │     → backendCall('log_deal_activity', { did: 'CSFB 2006-HEAT5', days: 30 })
  │
  ├─→ CLI: cmd_log_deal_activity(args)
  │     │
  │     ├─→ DealRepository.resolve_did_by_name('CSFB 2006-HEAT5')
  │     │     → Returns: import_did = 'CSFB'
  │     │
  │     └─→ LogAnalytics.deal_activity(import_did='CSFB', days=30)
  │           → SQLite: SELECT * FROM log_events WHERE detail LIKE '%CSFB%' ...
  │           → Returns: list[DealActivity]
  │
  └─→ LLM: Format timeline with key details
        → Stream to user
```

### E-01: Email Verification Flow

```
User: @frp /triage verify C:\inbox\request.msg
  │
  ├─→ Extension: extractMsgPath() → "C:\inbox\request.msg"
  │     → backendCall('triage_verify', { msg_path: '...', settings_path: '...', db_mode: '...' })
  │
  ├─→ CLI: cmd_triage_verify(args)
  │     │
  │     ├─→ MsgParser.parse(msg_path)
  │     │     → EmailInfo { sender, subject, ... }
  │     │
  │     ├─→ SettingsXmlParser.get_all_jobs(settings_path)
  │     │     → list[EmailJob]
  │     │
  │     ├─→ TriageMatcher.match(email_info, jobs)
  │     │     → list[MatchResult]
  │     │
  │     ├─→ IF has_match:
  │     │     DealRepository.get_deals_by_company(servicer_id)
  │     │     → coverage_status, did_count
  │     │
  │     └─→ Return TriageResult
  │
  └─→ LLM: Format verification result
        → "Email matches job 'X' — 3 DIDs covered"
```

### E-03: No-Match Analysis Flow

```
User: @frp /triage new C:\inbox\new_request.msg
  │
  ├─→ Extension: parse msg_path
  │     → backendCall('triage_new', { ... })
  │
  ├─→ CLI: cmd_triage_new(args)
  │     │
  │     ├─→ MsgParser.parse(msg_path) → EmailInfo
  │     │
  │     ├─→ TriageMatcher.match(email_info, jobs) → confirm no/low matches
  │     │
  │     ├─→ TemplateInventory.discover_templates(settings)
  │     │     → Suggest best template based on attachment types
  │     │
  │     ├─→ CoverageAnalyzer.analyze(servicer_hint)
  │     │     → Gap status for potential servicer
  │     │
  │     └─→ Compile TriageResult with suggested_template + suggested_config
  │
  └─→ LLM: "No matching job found. Recommended: create from 'MailToFolder — rptent' template."
        → Follow-up: /jobs create rptent
```

---

## 8. Stale Index Detection

### Design

The SQLite `sync_meta` table (from Phase 1) stores the last sync timestamp:

```sql
INSERT OR REPLACE INTO sync_meta (key, value)
VALUES ('last_sync', '2026-02-24T14:00:00');
```

### Staleness Check Algorithm

```
1. Read sync_meta.last_sync
2. If NULL or missing → index is empty, sync required
3. If (now - last_sync) > 24 hours → "stale"
4. If stale:
   a. CLI returns warning in response envelope:
      { "warning": "Log index was last synced 36 hours ago. Run /logs sync for latest data." }
   b. Extension shows warning before results
   c. Results are still returned (not blocked)
5. If index is empty (no events at all):
   a. CLI returns error:
      { "success": false, "error": "Log index is empty. Run @frp /logs sync first." }
```

### Extension Integration

```javascript
// After receiving CLI response for any /logs command:
if (response.warning) {
    stream.markdown(`> ⚠️ ${response.warning}\n\n`);
}
```

---

*Next document: [03_TECHNICAL_DESIGN.md](03_TECHNICAL_DESIGN.md)*
