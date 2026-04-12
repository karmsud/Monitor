# Phase 5: tblTemplateStaging Intelligence — Use Cases, Implementation & Testing Plan

## Table of Contents
1. [Overview](#1-overview)
2. [New Use Cases](#2-new-use-cases)
3. [Enhancements to Existing Use Cases](#3-enhancements-to-existing-use-cases)
4. [Implementation Plan](#4-implementation-plan)
5. [Testing Plan](#5-testing-plan)
6. [File Change Inventory](#6-file-change-inventory)

---

## 1. Overview

### What We Have Today
The FRP Agent currently understands **configuration** (Settings.xml jobs) and **deal mapping** (tblExternalDIDRef), plus **log analytics** (SQLite index of EmailMonitor/SFTPMonitor logs). It can answer "what jobs exist?", "which deals does servicer 296 manage?", and "how are jobs performing in the logs?"

### What tblTemplateStaging Adds
`tblTemplateStaging` is the **execution history** table — it records every time a scrubber/template ran against a file. This is the missing link between "a job was configured" and "did the file actually get processed successfully?" It tells us:
- **What ran** (TemplateName, Job parser)
- **What was processed** (FilePath, DID)
- **When** (StartTime, EndTime, Dt)
- **Outcome** (ResultCode 0=success, 1=failure, Comments for errors)
- **How it got there** (SourceProcess: ActiveBatch vs ManualQueue, DataSource: mailbox/SFTP folder)
- **Who services it** (ServicerID = CompanyID from tblExternalDIDRef)

### Guiding Principles
- All new commands follow the existing pattern: `backend/` module → `cli/main.py` handler → `extension/copilot/tool.js` registration → `extension/chat/participant.js` tool + handler
- New queries go in `backend/db/queries.py`, new repository methods in `backend/db/template_staging_repo.py`
- New data models go in a new `backend/db/ts_models.py` (to keep things clean)
- Tests use mocked DB connections (same pattern as existing `test_deal_repo.py`)
- No breaking changes to existing commands

---

## 2. New Use Cases

### UC-01: `template_status` — Check Processing Status for a Deal/Template

**User asks:** "Has TPMT_SPS processed any files lately?" or "What's the latest run for DID WB6 GT 2020-1?"

**What it does:**
- Queries tblTemplateStaging by TemplateName or DID
- Returns the most recent runs with ResultCode, timing, and error comments
- Shows success/failure ratio for the queried scope

**Output includes:**
- Last N runs (default 10) sorted by StartTime DESC
- Per-run: TemplateName, DID, FilePath, StartTime, EndTime, ResultCode, Comments (if failed)
- Summary: total runs, success rate, last success, last failure

**CLI command:** `template_status`
**CLI args:** `--query` (template name, DID, or keyword), `--days` (look-back, default 30), `--limit` (max rows, default 10)

---

### UC-02: `processing_history` — Full Processing History for a Deal

**User asks:** "Show me the full processing history for DID 'CMLTI 2007-AMC2'" or "What files were processed for servicer 296 this month?"

**What it does:**
- Deep lookup by DID, ServicerID, or TemplateName with date range filtering
- Shows every file processed, how it arrived (DataSource), which parser ran (Job), and the outcome
- Cross-references tblExternalDIDRef for deal metadata

**Output includes:**
- Chronological list of all processing runs
- Per-run: FilePath, TemplateName, Job, DataSource, SourceProcess, ResultCode, Comments, StartTime→EndTime duration
- Deal metadata from tblExternalDIDRef (ImportDID keyword, CompanyID)
- Summary stats: total files, success/failure count, unique templates used

**CLI command:** `processing_history`
**CLI args:** `--query` (DID, ServicerID, or TemplateName), `--start-date`, `--end-date`, `--limit` (default 50)

---

### UC-03: `failure_analysis` — Failure Deep-Dive

**User asks:** "What's been failing lately?" or "Show me all failures for TPMT templates" or "Why did SCRT_Queuer fail?"

**What it does:**
- Queries tblTemplateStaging for all ResultCode=1 records
- Groups failures by TemplateName, DID, and error message pattern
- Shows failure trends over time
- Correlates with tblExternalDIDRef to identify affected servicers

**Output includes:**
- Failure summary: total failures in period, top templates by failure count, top DIDs by failure count
- Error categories: groups Comments into patterns (e.g. "Template mismatch", "File not found", "DID mapping failed")
- Per-failure detail (optional): FilePath, TemplateName, DID, Comments, DataSource, StartTime
- Affected servicers: ServicerID → CompanyName cross-ref

**CLI command:** `failure_analysis`
**CLI args:** `--days` (default 30), `--template` (optional filter), `--did` (optional filter), `--detail` (show individual failures)

---

### UC-04: `source_trace` — Trace File Origin to Processing

**User asks:** "Where did this file come from?" or "Trace the processing for file FKMF_2026.xlsx" or "Which mailbox triggered this run?"

**What it does:**
- Takes a filename/path pattern and finds matching tblTemplateStaging records
- Extracts the DataSource field to show where the file came from:
  - Email: `"<mailbox>: <subject>"` — identifies the email job
  - SFTP: `"SFTPMonitor: <folder>"` — identifies the SFTP source
  - Manual: `"Queued via macro by <user>"` — identifies manual queue
- Cross-references Settings.xml to find the originating job configuration

**Output includes:**
- File path matched
- Source type (email / SFTP / manual) parsed from DataSource
- Originating mailbox or SFTP path
- Job configuration from Settings.xml (if found)
- Processing result and timing

**CLI command:** `source_trace`
**CLI args:** `--filepath` (pattern with wildcards), `--limit` (default 10)

---

### UC-05: `manual_queue_report` — Manual vs. Automated Processing Breakdown

**User asks:** "How many files were manually queued this month?" or "Which deals require the most manual intervention?"

**What it does:**
- Segments tblTemplateStaging records by SourceProcess (`ActiveBatch` vs `ManualQueue`)
- Identifies deals/templates that are frequently manually queued (red flag for automation gaps)
- Shows which users manually queue files (extracted from DataSource "Queued via macro by <user>")

**Output includes:**
- Overall ratio: automated vs. manual in the period
- Top templates by manual queue count
- Top DIDs by manual queue count
- Manual queue operators: which usernames appear most
- Trend: is manual queuing increasing or decreasing?

**CLI command:** `manual_queue_report`
**CLI args:** `--days` (default 30), `--template` (optional filter), `--servicer-id` (optional filter)

---

### UC-06: `processing_duration` — Processing Time Analysis

**User asks:** "How long do CMBS scrubbers take to run?" or "Which templates are slowest?" or "Are processing times getting worse?"

**What it does:**
- Calculates duration from StartTime → EndTime for each run
- Aggregates by TemplateName to show avg/min/max/p95 processing times
- Identifies outlier runs (>2x the average)
- Shows duration trends over time

**Output includes:**
- Per-template: avg duration, min, max, p95, total runs
- Outlier runs: exceptionally slow processing instances
- Duration trend: comparing recent period vs prior period
- Sorted by longest average first (identifies bottlenecks)

**CLI command:** `processing_duration`
**CLI args:** `--days` (default 30), `--template` (optional filter), `--sort` (avg_duration | max_duration | total_runs)

---

### UC-07: `deal_pipeline_status` — End-to-End Pipeline Visibility

**User asks:** "Give me the full pipeline view for DID CMLTI 2007-AMC2" or "What's the end-to-end status for servicer 296?"

**What it does:**
- Combines data from **three sources**: Settings.xml (config), tblExternalDIDRef (deal mapping), and tblTemplateStaging (execution)
- For a given DID or ServicerID, shows: which jobs are configured → which templates run → what the outcomes are
- Identifies gaps: configured but never processed, processed but not configured

**Output includes:**
- **Config layer**: Jobs from Settings.xml matching the ServicerID
- **Mapping layer**: DID/ImportDID from tblExternalDIDRef for the CompanyID
- **Execution layer**: Recent tblTemplateStaging runs for those DIDs/templates
- **Gap analysis**: DIDs with jobs but no recent processing, templates running but not in Settings.xml
- **Health score**: percentage of configured deals that have successful recent processing

**CLI command:** `deal_pipeline`
**CLI args:** `--query` (DID, ServicerID, or TemplateName), `--days` (look-back, default 30)

---

### UC-08: `staging_search` — General-Purpose tblTemplateStaging Search

**User asks:** "Search template staging for FKMF" or "Look up template process ID 144755"

**What it does:**
- Flexible search across tblTemplateStaging (same pattern as `search_deals` on tblExternalDIDRef)
- Auto-detects query type: numeric → TemplateProcessID, otherwise tries DID → TemplateName → FilePath pattern

**Output includes:**
- Matched records with key columns
- Smart result formatting based on result count

**CLI command:** `staging_search`
**CLI args:** `--query` (free-text search term)

---

## 3. Enhancements to Existing Use Cases

### EX-01: Enrich `servicer_dossier` with Template Staging Data

**Current behavior:** Shows jobs from Settings.xml + deals from tblExternalDIDRef + log summaries from SQLite.

**Enhancement:** Add a `template_staging` section showing:
- Recent processing runs for the servicer's DIDs
- Success/failure summary from tblTemplateStaging
- Last successful processing timestamp per DID
- Any active failures

**Files changed:** `cli/main.py` (`cmd_servicer_dossier`), `extension/copilot/tool.js` (add to `_ACCEPTS`)

---

### EX-02: Enrich `job_detail` with Template Staging Data

**Current behavior:** Shows job config + linked deals from tblExternalDIDRef.

**Enhancement:** Add a `recent_processing` section showing:
- Last N template staging runs for this job's TemplateName
- Current success rate
- Last failure with error message

**Files changed:** `cli/main.py` (`cmd_job_detail`), `extension/copilot/tool.js` (add to `_ACCEPTS`)

---

### EX-03: Enrich `triage_verify` / `triage_new` with Processing Outcome

**Current behavior:** Verifies email matches a job and checks deal coverage.

**Enhancement:** After matching the job, query tblTemplateStaging to show:
- "This job's template last ran successfully on X"
- "This job's template has a Y% failure rate recently"
- "Last failure error: Z"

**Files changed:** `backend/triage/analyzer.py` (add template_staging_repo parameter), `cli/main.py` (`cmd_triage_verify`, `cmd_triage_new`)

---

### EX-04: Enrich `analyze_health` with Processing Health

**Current behavior:** Aggregates XML validation, coverage, orphans, collisions, and log performance.

**Enhancement:** Add a `processing_health` section with:
- Overall success rate from tblTemplateStaging
- Templates with >10% failure rate flagged
- Deals with no recent processing flagged
- Manual queue percentage

**Files changed:** `backend/analysis/health.py`, `cli/main.py` (`cmd_analyze_health`)

---

## 4. Implementation Plan

### Phase 5A — Foundation (Backend Data Layer)

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5A-1 | `backend/db/ts_models.py` | Create dataclass models: `TemplateRun`, `TemplateSummary`, `FailureSummary`, `DurationStats`, `PipelineStatus`, `ManualQueueReport`, `SourceTraceResult` | None |
| 5A-2 | `backend/db/queries.py` | Add ~15 new SQL constants for new use cases (failure grouping, duration calc, source process grouping, date-range filters, cross-table JOINs) | None |
| 5A-3 | `backend/db/template_staging_repo.py` | Add new methods: `get_recent_by_query()`, `get_failure_summary()`, `get_duration_stats()`, `get_manual_queue_stats()`, `trace_by_filepath()`, `get_pipeline_status()`, `get_processing_for_servicer()` | 5A-1, 5A-2 |

### Phase 5B — New CLI Commands

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5B-1 | `cli/main.py` | Add `_ts_repo_from_args()` helper (mirrors `_repo_from_args()`) | 5A-3 |
| 5B-2 | `cli/main.py` | Add `cmd_template_status()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-3 | `cli/main.py` | Add `cmd_processing_history()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-4 | `cli/main.py` | Add `cmd_failure_analysis()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-5 | `cli/main.py` | Add `cmd_source_trace()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-6 | `cli/main.py` | Add `cmd_manual_queue_report()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-7 | `cli/main.py` | Add `cmd_processing_duration()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-8 | `cli/main.py` | Add `cmd_deal_pipeline()` handler + argparse subparser (cross-references XML + tblExternalDIDRef + tblTemplateStaging) | 5A-3, 5B-1 |
| 5B-9 | `cli/main.py` | Add `cmd_staging_search()` handler + argparse subparser | 5A-3, 5B-1 |
| 5B-10 | `cli/main.py` | Register all 8 new commands in `_COMMAND_DISPATCH` dict and `_build_parser()` | 5B-2 → 5B-9 |

### Phase 5C — Enrich Existing Commands

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5C-1 | `cli/main.py` | Enhance `cmd_servicer_dossier()` — add template_staging section | 5A-3 |
| 5C-2 | `cli/main.py` | Enhance `cmd_job_detail()` — add recent_processing section | 5A-3 |
| 5C-3 | `backend/triage/analyzer.py` | Add optional `template_staging_repo` parameter, enrich triage results with processing status | 5A-3 |
| 5C-4 | `cli/main.py` | Pass template_staging_repo to `cmd_triage_verify()` and `cmd_triage_new()` | 5C-3 |
| 5C-5 | `backend/analysis/health.py` | Add processing health checks using TemplateStagingRepository | 5A-3 |
| 5C-6 | `cli/main.py` | Pass template_staging_repo to `cmd_analyze_health()` | 5C-5 |

### Phase 5D — Intelligence & NL Routing Layer (VS Code Extension)

This is the **critical layer** where the user's natural language prompt gets decomposed, understood, and routed to the right tool. The existing architecture uses LLM tool-calling: the LLM receives `FRP_TOOLS` definitions, semantically understands the user's intent, selects the right tool, extracts parameters, and the extension dispatches to a handler function. We need to wire ALL 8 new use cases into this pipeline.

#### How It Works Today (Architecture Reference)

```
User types: "What's been failing in TPMT templates lately?"
                    ↓
    handleFreeformQuestion()          ← entry point for non-slash prompts
                    ↓
    routeWithToolCalling()            ← sends prompt + FRP_TOOLS to LLM
        LLM sees all tool definitions     (name, description, inputSchema)
        LLM picks: failure_analysis       ← semantic intent resolution
        LLM extracts params: { template: "TPMT" }
                    ↓
    executeToolCall('failure_analysis', { template: 'TPMT' }, ...)
                    ↓
    handleFailureAnalysis('TPMT', ...)   ← new handler function
        → backendCall('failure_analysis', { template: 'TPMT' })
        → CLI: cmd_failure_analysis()
        → TemplateStagingRepository.get_failure_summary()
        → LLM formats response with SYSTEM_PROMPT context
                    ↓
    Returns: formatted markdown + contextual followUps
```

#### 5D-1: `extension/copilot/tool.js` — `_ACCEPTS` Map Update

Add all 8 new CLI commands to the `_ACCEPTS` map so that VS Code settings (dbMode, secretsPath, etc.) are auto-injected:

```javascript
// Commands that accept --db-mode (all new commands need DB access)
dbMode: new Set([
  ...existing...,
  'template_status', 'processing_history', 'failure_analysis',
  'source_trace', 'manual_queue_report', 'processing_duration',
  'deal_pipeline', 'staging_search',
]),

// Commands that accept --settings-path (deal_pipeline needs XML cross-ref)
settingsPath: new Set([
  ...existing...,
  'deal_pipeline',
]),

// Commands that accept --secrets-path, --mssql-server, --mssql-database
secretsPath / mssqlServer / mssqlDatabase: new Set([
  ...existing...,
  'template_status', 'processing_history', 'failure_analysis',
  'source_trace', 'manual_queue_report', 'processing_duration',
  'deal_pipeline', 'staging_search',
]),
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-1 | `extension/copilot/tool.js` | Add 8 new commands to `dbMode`, `secretsPath`, `mssqlServer`, `mssqlDatabase` sets; add `deal_pipeline` to `settingsPath` set | 5B-10 |

#### 5D-2: `FRP_TOOLS` — LLM Tool Definitions (Intent Resolution)

These definitions are what the LLM reads to decide which tool to call. The `description` field is the most important — it controls whether the LLM routes correctly for a given natural language prompt. Each description must cover all ways a user might phrase the intent.

```javascript
// --- 8 NEW TOOL DEFINITIONS ---

{
  name: 'template_status',
  description: 'Check the processing status of a template (scrubber) or deal (DID). Shows recent runs, success/failure ratio, last run time. Use when user asks "has X been processed", "status of template Y", "latest run for deal Z", "is TPMT_SPS running", "when did scrubber X last run".',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Template name, DID, or keyword to check status for.' },
      days: { type: 'number', description: 'Look-back window in days (default 30).' },
    },
    required: ['query'],
  },
},
{
  name: 'processing_history',
  description: 'Show full processing history — every file that was processed for a deal, servicer, or template. Use when user asks "show processing history for X", "what files were processed for servicer 296", "all runs for DID Y", "processing log for Z".',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'DID, ServicerID, or TemplateName to look up.' },
      startDate: { type: 'string', description: 'Start date in YYYY-MM-DD format.' },
      endDate: { type: 'string', description: 'End date in YYYY-MM-DD format.' },
    },
    required: ['query'],
  },
},
{
  name: 'failure_analysis',
  description: 'Analyze processing failures from tblTemplateStaging. Shows what failed, why, error patterns, affected deals/servicers. Use when user asks "what\'s failing", "why did X fail", "show errors", "failure report", "which templates are broken".',
  inputSchema: {
    type: 'object',
    properties: {
      template: { type: 'string', description: 'Optional template name filter.' },
      did: { type: 'string', description: 'Optional DID filter.' },
      days: { type: 'number', description: 'Look-back window in days (default 30).' },
    },
  },
},
{
  name: 'source_trace',
  description: 'Trace where a file came from — shows the email mailbox, SFTP folder, or manual queue that triggered processing. Use when user asks "where did this file come from", "trace file X", "which mailbox triggered Y", "how did file Z get processed".',
  inputSchema: {
    type: 'object',
    properties: {
      filepath: { type: 'string', description: 'Full or partial file path to trace.' },
    },
    required: ['filepath'],
  },
},
{
  name: 'manual_queue',
  description: 'Show manual vs automated processing breakdown. Identifies deals/templates frequently manually queued. Use when user asks "how much is manual", "manual queue stats", "automation gaps", "which deals need manual intervention", "who is manually queuing".',
  inputSchema: {
    type: 'object',
    properties: {
      days: { type: 'number', description: 'Look-back window in days (default 30).' },
      template: { type: 'string', description: 'Optional template filter.' },
      servicerId: { type: 'string', description: 'Optional servicer ID filter.' },
    },
  },
},
{
  name: 'processing_duration',
  description: 'Analyze processing times — how long templates take to run, which are slowest, outlier detection. Use when user asks "how long does X take", "slowest templates", "processing time analysis", "performance bottlenecks", "duration report".',
  inputSchema: {
    type: 'object',
    properties: {
      template: { type: 'string', description: 'Optional template name filter.' },
      days: { type: 'number', description: 'Look-back window in days (default 30).' },
      sort: { type: 'string', description: 'Sort by: avg_duration, max_duration, total_runs.' },
    },
  },
},
{
  name: 'deal_pipeline',
  description: 'End-to-end pipeline view for a deal or servicer — combines Settings.xml configuration, tblExternalDIDRef deal mapping, and tblTemplateStaging execution history into a single unified view. Use when user asks "full pipeline for X", "end to end status", "pipeline view for servicer 296", "is deal X fully configured and processing".',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'DID name, ServicerID number, or TemplateName.' },
      days: { type: 'number', description: 'Look-back window in days (default 30).' },
    },
    required: ['query'],
  },
},
{
  name: 'staging_search',
  description: 'Search tblTemplateStaging records directly. Use when user asks "search staging for X", "look up template process ID 12345", "find staging records matching Y", "query template staging".',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search term: TemplateProcessID (number), DID, TemplateName, or FilePath pattern.' },
    },
    required: ['query'],
  },
},
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-2 | `extension/chat/participant.js` | Add 8 tool definitions to `FRP_TOOLS` array with rich descriptions for intent resolution | 5B-10 |

#### 5D-3: `SYSTEM_PROMPT` — Domain Knowledge Update

The `SYSTEM_PROMPT` is what gives the LLM context about the FRP domain. It must be updated to include tblTemplateStaging knowledge so the LLM can correctly interpret user prompts and format responses.

**Additions to SYSTEM_PROMPT:**

```
• tblTemplateStaging — the execution history table. Records every scrubber/template run:
  - TemplateName: the scrubber that ran (matches <Template> in Settings.xml jobs)
  - DID: the deal identifier (matches tblExternalDIDRef.DID)
  - ServicerID: same as CompanyID in tblExternalDIDRef
  - FilePath: the resolved file path after save
  - ResultCode: 0 = success, 1 = failure; Comments has error detail
  - SourceProcess: "ActiveBatch" = automated pipeline, "ManualQueue" = human override
  - DataSource: for email → "<mailbox>: <subject>"; for SFTP → "SFTPMonitor: <folder>"; for manual → "Queued via macro by <user>"
  - Job: the parser name (DetachFile, DetachFileSubject, MoveFile, etc.)
  - StartTime / EndTime: processing timestamps (duration = EndTime - StartTime)
• When showing processing results, label columns: Template, DID, FilePath, Result (✅/❌), Duration, Source, Date
• For failure analysis, group errors by pattern and show affected deals/servicers
• For pipeline views, show three layers: Config (Settings.xml) → Mapping (tblExternalDIDRef) → Execution (tblTemplateStaging)
• SourceProcess "ManualQueue" means human intervention was needed — flag as automation gap
• Include columns Priority, ServerSide, PID, Notify, EmailList, NotificationSent as internal — omit from output unless specifically asked
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-3 | `extension/chat/participant.js` | Update `SYSTEM_PROMPT` with tblTemplateStaging domain knowledge (column meanings, formatting rules, pipeline layer concept) | None (can be done early) |

#### 5D-4: `executeToolCall()` — Route Tool Selections to Handlers

Add 8 new `case` branches to the `switch` statement in `executeToolCall()`:

```javascript
case 'template_status':
  return handleTemplateStatus(input.query, input.days, request, context, stream, token, shared);

case 'processing_history':
  return handleProcessingHistory(input.query, input, request, context, stream, token, shared);

case 'failure_analysis':
  return handleFailureAnalysis(input, request, context, stream, token, shared);

case 'source_trace':
  return handleSourceTrace(input.filepath, request, context, stream, token, shared);

case 'manual_queue':
  return handleManualQueue(input, request, context, stream, token, shared);

case 'processing_duration':
  return handleProcessingDuration(input, request, context, stream, token, shared);

case 'deal_pipeline':
  return handleDealPipeline(input.query, input.days, request, context, stream, token, shared);

case 'staging_search':
  return handleStagingSearch(input.query, request, context, stream, token, shared);
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-4 | `extension/chat/participant.js` | Add 8 `case` branches in `executeToolCall()` switch statement | 5D-5 |

#### 5D-5: Handler Functions — Backend Call + LLM Formatting + Follow-ups

Each handler follows the established pattern:
1. Show progress indicator
2. Call `backendCall()` with the right CLI command + params
3. Check for errors
4. Build an LLM prompt with `SYSTEM_PROMPT` + `<data>` + formatting instructions
5. Call `generateOrFallback()` (LLM formats; raw markdown if LLM unavailable)
6. Return contextual `followUps` for conversation flow

**8 new handler functions:**

| Handler | Backend Call | LLM Formatting Instructions | Follow-ups |
|---------|-------------|---------------------------|------------|
| `handleTemplateStatus()` | `template_status` | "Show recent runs as a table with ✅/❌ icons. Include success rate and last run timestamp." | `→ failure_analysis`, `→ processing_history` |
| `handleProcessingHistory()` | `processing_history` | "Show chronological processing log. Include File, Template, Parser, Source, Result, Duration columns." | `→ source_trace`, `→ deal_pipeline` |
| `handleFailureAnalysis()` | `failure_analysis` | "Group failures by error pattern. Show affected templates and deals. Use ❌ icons. Suggest remediation." | `→ template_status`, `→ system_health` |
| `handleSourceTrace()` | `source_trace` | "Show source type (Email/SFTP/Manual), originating mailbox/folder, job config from Settings.xml." | `→ job_detail`, `→ processing_history` |
| `handleManualQueue()` | `manual_queue_report` | "Show automated vs manual ratio. Flag deals with >20% manual rate. List operators." | `→ failure_analysis`, `→ deal_pipeline` |
| `handleProcessingDuration()` | `processing_duration` | "Rank templates by avg duration. Flag outliers. Show duration trend." | `→ template_status`, `→ system_health` |
| `handleDealPipeline()` | `deal_pipeline` | "Show 3 layers: Config → Mapping → Execution. Use ✅/⚠️/❌ for each layer. Highlight gaps." | `→ servicer_dossier`, `→ failure_analysis` |
| `handleStagingSearch()` | `staging_search` | "Show matching records as a clean table. Auto-detect search type (ID/DID/template/filepath)." | `→ template_status`, `→ source_trace` |

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-5 | `extension/chat/participant.js` | Implement 8 handler functions (each ~40-60 lines): `handleTemplateStatus()`, `handleProcessingHistory()`, `handleFailureAnalysis()`, `handleSourceTrace()`, `handleManualQueue()`, `handleProcessingDuration()`, `handleDealPipeline()`, `handleStagingSearch()` | 5D-2 |

#### 5D-6: `keywordFallbackRoute()` — Keyword-Based Fallback Patterns

When LLM tool-calling is unavailable (old VS Code, model doesn't support it), the keyword fallback router handles common patterns. Add patterns for the new use cases:

```javascript
// Template staging / processing patterns
if (/\bfailures?\b.*\btemplate|scrubber\b/i.test(lower)
    || /\bwhat.+fail/i.test(lower)) {
  return handleFailureAnalysis({}, request, context, stream, token, shared);
}

if (/\bmanual\s*queue/i.test(lower)
    || /\bautomation\s+gap/i.test(lower)) {
  return handleManualQueue({}, request, context, stream, token, shared);
}

if (/\bpipeline\s+(?:for|view|status)/i.test(lower)
    || /\bend.to.end/i.test(lower)) {
  const q = lower.replace(/.*(?:pipeline|end.to.end)\s*(?:for|view|status|of)?\s*/i, '').trim();
  return handleDealPipeline(q || prompt, 30, request, context, stream, token, shared);
}

if (/\btrace\s+file/i.test(lower)
    || /\bwhere\s+did.*come\s+from/i.test(lower)) {
  const q = lower.replace(/.*(?:trace\s+file|where\s+did)\s*/i, '').trim();
  return handleSourceTrace(q, request, context, stream, token, shared);
}

if (/\bprocessing\s+(?:time|duration|speed|slow)/i.test(lower)
    || /\bslowest\s+template/i.test(lower)) {
  return handleProcessingDuration({}, request, context, stream, token, shared);
}

if (/\bstaging\s+search|search\s+staging/i.test(lower)) {
  const q = lower.replace(/.*staging\s+search|search\s+staging\s*/i, '').trim();
  return handleStagingSearch(q || prompt, request, context, stream, token, shared);
}
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-6 | `extension/chat/participant.js` | Add ~6 keyword fallback patterns to `keywordFallbackRoute()` for processing failures, manual queue, pipeline view, source trace, duration, staging search | 5D-5 |

#### 5D-7: `formatRawData()` — Raw Data Formatting Fallback

When the LLM is unavailable, `formatRawData()` renders backend data as plain Markdown tables. Add formatting for the new data shapes:

```javascript
// Template staging results
if (command === 'staging' && Array.isArray(data.runs)) {
  // Table with Template, DID, FilePath, Result, Date columns
}

// Failure analysis
if (command === 'failures' && data.failure_summary) {
  // Grouped list with error counts and affected templates
}

// Pipeline view
if (command === 'pipeline' && data.config_layer) {
  // Three-section display: Config → Mapping → Execution
}

// Manual queue report
if (command === 'manual_queue' && data.automated_count !== undefined) {
  // Ratio display + top manual-queued deals
}
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-7 | `extension/chat/participant.js` | Add raw data formatting cases for `staging`, `failures`, `pipeline`, `manual_queue`, `duration`, `trace` data shapes in `formatRawData()` | 5D-5 |

#### 5D-8: Slash Command — `/staging` (New)

Add a new `/staging` slash command as a direct entry point for template staging queries, similar to how `/logs`, `/deals`, `/jobs` work today:

```javascript
// In COMMAND_HANDLERS:
staging: handleStagingCommand,

// handleStagingCommand routes subcommands:
// /staging status <query>      → handleTemplateStatus()
// /staging history <query>     → handleProcessingHistory()
// /staging failures            → handleFailureAnalysis()
// /staging trace <filepath>    → handleSourceTrace()
// /staging manual              → handleManualQueue()
// /staging duration            → handleProcessingDuration()
// /staging pipeline <query>    → handleDealPipeline()
// /staging search <query>      → handleStagingSearch()
// /staging (no args)           → help text with usage examples
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-8 | `extension/chat/participant.js` | Add `handleStagingCommand()` router + register in `COMMAND_HANDLERS` + add to `participant.commandProvider` | 5D-5 |

#### 5D-9: Update Existing Handlers for Enriched Data

The enriched commands (EX-01 through EX-04) return new data sections. The existing LLM formatting prompts in their handlers need updates:

| Handler | Addition to LLM Prompt |
|---------|----------------------|
| `handleJobDetail()` | "If `recent_processing` is present, show a 'Processing Status' section with last run, success rate, and recent failures." |
| `handleDealsCommand()` (servicer dossier) | "If `template_staging` section is present, show 'Processing Activity' with recent runs, success/failure counts, and last successful processing per DID." |
| Triage handlers | "If `processing_status` is present, show downstream processing health for the matched template." |
| `handleAnalyzeCommand()` health | "If `processing_health` section is present, include it in the health dashboard with ✅/⚠️/❌ status." |

| Handler | Addition to Follow-ups |
|---------|----------------------|
| `handleJobDetail()` | Add `→ template_status` and `→ processing_history` follow-ups |
| `handleDealsCommand()` | Add `→ deal_pipeline` follow-up |
| Triage handlers | Add `→ failure_analysis` follow-up if failures detected |

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-9 | `extension/chat/participant.js` | Update LLM prompts and follow-ups in `handleJobDetail()`, `handleDealsCommand()`, triage handlers, and `handleAnalyzeCommand()` health branch for enriched data sections | 5C-1 through 5C-6 |

#### 5D-10: `package.json` — Register `/staging` Slash Command

The VS Code extension's `package.json` must declare the new slash command for it to appear in the chat participant's command palette:

```json
"chatParticipants": [{
  "id": "frp-agent.assistant",
  "commands": [
    ...existing...,
    { "name": "staging", "description": "Query template processing history, failures, duration, and pipeline status" }
  ]
}]
```

| Step | File | Work | Dependencies |
|------|------|------|-------------|
| 5D-10 | `extension/package.json` | Add `staging` to chat participant commands array | 5D-8 |

### Implementation Order (Recommended)

```
5A-1 → 5A-2 → 5A-3          (foundation — backend data layer)
  ↓
5B-1                          (shared CLI helper)
  ↓
5B-2 through 5B-9             (can be done in parallel, all independent)
  ↓
5B-10                         (CLI registration — depends on all above)
  ↓
5C-1 through 5C-6             (enrichments — can be done in parallel)
  ↓
5D-1                          (tool.js _ACCEPTS — must come before extension handlers)
  ↓
5D-2 + 5D-3                   (FRP_TOOLS + SYSTEM_PROMPT — can be parallel)
  ↓
5D-5                          (handler functions — depends on tool defs)
  ↓
5D-4 + 5D-6 + 5D-7 + 5D-8   (routing: executeToolCall + keyword fallback + raw format + slash cmd — parallel, all depend on handlers)
  ↓
5D-9                          (update existing handlers — depends on enriched CLI output)
  ↓
5D-10                         (package.json — last, after everything is connected)
```

---

## 5. Testing Plan

### Test File Organization

```
tests/
  db/
    test_template_staging_repo.py      ← NEW: repo method tests (mocked DB)
    test_template_staging_repo_p5.py   ← NEW: Phase 5 new methods
  cli/
    test_cli_template_staging.py       ← NEW: CLI command handler tests
  analysis/
    test_health_p5.py                  ← NEW: enriched health check tests
  triage/
    test_triage_p5.py                  ← NEW: enriched triage tests
  integration/
    test_template_staging_e2e.py       ← NEW: end-to-end with real MySQL
  fixtures/
    (no new fixture files needed — all tests use mocked data)
```

### Test Fixtures (in `conftest.py`)

```python
# New fixtures to add:

@pytest.fixture
def mock_ts_repo():
    """Mock TemplateStagingRepository for Phase 5 tests."""
    # Returns pre-configured mock with sample tblTemplateStaging data
    # Covers: success runs, failure runs, manual queue, SFTP source, email source

@pytest.fixture  
def sample_template_runs():
    """List of sample template staging records as dicts."""
    # 10-15 sample rows covering diverse scenarios:
    # - Different templates (TPMT_SPS, QueueCMBS_Scrubber_x, SCRT_Queuer)
    # - Success and failure ResultCodes
    # - ActiveBatch and ManualQueue source processes
    # - Email and SFTP and manual DataSources
```

### Test Cases by Module

#### T-01: `tests/db/test_template_staging_repo_p5.py` — Repository Methods

| Test ID | Method Under Test | Scenario | Assertion |
|---------|------------------|----------|-----------|
| T-01-01 | `get_recent_by_query()` | Query by TemplateName | Returns rows sorted by StartTime DESC, limited to N |
| T-01-02 | `get_recent_by_query()` | Query by DID | Returns rows for exact DID match |
| T-01-03 | `get_recent_by_query()` | Query with days filter | Only returns rows within date range |
| T-01-04 | `get_recent_by_query()` | No results | Returns empty list |
| T-01-05 | `get_failure_summary()` | Multiple failures | Returns grouped by template with counts |
| T-01-06 | `get_failure_summary()` | With template filter | Only returns failures for specified template |
| T-01-07 | `get_failure_summary()` | No failures | Returns empty summary |
| T-01-08 | `get_duration_stats()` | Normal runs | Calculates avg/min/max correctly |
| T-01-09 | `get_duration_stats()` | With template filter | Only stats for specified template |
| T-01-10 | `get_manual_queue_stats()` | Mix of auto and manual | Returns correct counts and percentages |
| T-01-11 | `get_manual_queue_stats()` | All automated | Returns 0 manual count |
| T-01-12 | `trace_by_filepath()` | Exact filepath match | Returns matching records with DataSource parsed |
| T-01-13 | `trace_by_filepath()` | Wildcard filepath | Returns partial matches |
| T-01-14 | `get_pipeline_status()` | ServicerID with mixed results | Returns config + mapping + execution layers |
| T-01-15 | `get_processing_for_servicer()` | Valid ServicerID | Returns all runs for that servicer |

#### T-02: `tests/cli/test_cli_template_staging.py` — CLI Command Handlers

| Test ID | Command | Scenario | Assertion |
|---------|---------|----------|-----------|
| T-02-01 | `template_status` | Valid template name | Response has runs + summary |
| T-02-02 | `template_status` | Unknown template | Response has empty runs, zero counts |
| T-02-03 | `processing_history` | By DID with date range | Filtered results returned |
| T-02-04 | `processing_history` | By ServicerID | Cross-refs tblExternalDIDRef |
| T-02-05 | `failure_analysis` | Failures exist | Grouped output correct |
| T-02-06 | `failure_analysis` | No failures | Success message returned |
| T-02-07 | `source_trace` | Email source file | DataSource parsed correctly |
| T-02-08 | `source_trace` | SFTP source file | "SFTPMonitor:" prefix detected |
| T-02-09 | `source_trace` | Manual queue file | "Queued via macro" detected |
| T-02-10 | `manual_queue_report` | Mixed source processes | Percentages correct |
| T-02-11 | `processing_duration` | Multiple templates | Duration stats sorted correctly |
| T-02-12 | `deal_pipeline` | Full pipeline query | All three layers present |
| T-02-13 | `staging_search` | Numeric query | Treated as TemplateProcessID |
| T-02-14 | `staging_search` | Text query | Falls through DID→Template→FilePath |
| T-02-15 | `_ts_repo_from_args()` | MySQL mode | TemplateStagingRepository created correctly |
| T-02-16 | `_ts_repo_from_args()` | MSSQL mode | prod_mode=True passed |

#### T-03: `tests/triage/test_triage_p5.py` — Enriched Triage

| Test ID | Scenario | Assertion |
|---------|----------|-----------|
| T-03-01 | Triage verify with template staging repo available | Result includes `processing_status` section |
| T-03-02 | Triage verify, template has recent failures | Result includes failure warning |
| T-03-03 | Triage verify without template staging repo | Graceful degradation, no error |
| T-03-04 | Triage new with template staging data | Suggested template shows success rate |

#### T-04: `tests/analysis/test_health_p5.py` — Enriched Health Check

| Test ID | Scenario | Assertion |
|---------|----------|-----------|
| T-04-01 | Health check with template staging available | `processing_health` section in output |
| T-04-02 | High failure rate template flagged | Warning in health check output |
| T-04-03 | Deal with no recent processing | Flagged as stale |
| T-04-04 | Health check without template staging | Graceful degradation |

#### T-05: `tests/cli/test_cli_enrichments.py` — Enriched Existing Commands

| Test ID | Command | Scenario | Assertion |
|---------|---------|----------|-----------|
| T-05-01 | `servicer_dossier` | With template staging data | Dossier includes `template_staging` section |
| T-05-02 | `servicer_dossier` | Without DB connection | Graceful degradation |
| T-05-03 | `job_detail` | With template staging data | Detail includes `recent_processing` section |
| T-05-04 | `job_detail` | Template staging not available | No error, omits section |

### Test Run Commands

```bash
# Run all Phase 5 tests
pytest tests/db/test_template_staging_repo_p5.py tests/cli/test_cli_template_staging.py tests/triage/test_triage_p5.py tests/analysis/test_health_p5.py tests/cli/test_cli_enrichments.py -v

# Run just the repo layer
pytest tests/db/test_template_staging_repo_p5.py -v

# Run just the CLI layer
pytest tests/cli/test_cli_template_staging.py tests/cli/test_cli_enrichments.py -v

# Run integration test against real MySQL (manual, requires DB)
pytest tests/integration/test_template_staging_e2e.py -v --run-integration
```

---

## 6. File Change Inventory

### New Files
| File | Purpose |
|------|---------|
| `backend/db/ts_models.py` | Dataclass models for tblTemplateStaging use cases |
| `tests/db/test_template_staging_repo_p5.py` | Unit tests for new repo methods |
| `tests/cli/test_cli_template_staging.py` | Unit tests for new CLI commands |
| `tests/triage/test_triage_p5.py` | Unit tests for enriched triage |
| `tests/analysis/test_health_p5.py` | Unit tests for enriched health check |
| `tests/cli/test_cli_enrichments.py` | Unit tests for enriched existing commands |
| `tests/integration/test_template_staging_e2e.py` | Integration tests (real MySQL) |
| `docs/Phase5/01_TEMPLATE_STAGING_PLAN.md` | This document |

### Modified Files
| File | Changes |
|------|---------|
| `backend/db/queries.py` | Add ~15 new SQL query constants |
| `backend/db/template_staging_repo.py` | Add ~7 new methods |
| `cli/main.py` | Add `_ts_repo_from_args()` + 8 new cmd handlers + argparse subparsers + dispatch registration |
| `backend/triage/analyzer.py` | Add optional `template_staging_repo` parameter, enrich results |
| `backend/analysis/health.py` | Add processing health checks |
| `extension/copilot/tool.js` | Add 8 new commands to `_ACCEPTS` map (`dbMode`, `secretsPath`, `mssqlServer`, `mssqlDatabase`); add `deal_pipeline` to `settingsPath` |
| `extension/chat/participant.js` | Add 8 `FRP_TOOLS` definitions + 8 handler functions + 8 `executeToolCall()` cases + `handleStagingCommand()` slash command router + `SYSTEM_PROMPT` domain knowledge + ~6 `keywordFallbackRoute()` patterns + ~5 `formatRawData()` cases + update existing handlers for enriched data + follow-up chains |
| `extension/package.json` | Add `staging` slash command to `chatParticipants` commands array |
| `tests/conftest.py` | Add `mock_ts_repo` and `sample_template_runs` fixtures |

### Unchanged Files
| File | Reason |
|------|--------|
| `backend/db/deal_repo.py` | No changes needed |
| `backend/db/connection.py` | Reused as-is |
| `backend/db/connection_mysql.py` | Reused as-is |
| `backend/xml/*` | Not affected |
| `backend/logs/*` | Not affected |
| `backend/intel/*` | Not affected (could be enhanced later) |

---

## Summary: New Commands at a Glance

| # | CLI Command | Chat Tool Name | User Intent |
|---|------------|---------------|-------------|
| 1 | `template_status` | `template_status` | "Has this template/deal been processed recently?" |
| 2 | `processing_history` | `processing_history` | "Show all processing runs for this deal/servicer" |
| 3 | `failure_analysis` | `failure_analysis` | "What's been failing? Why?" |
| 4 | `source_trace` | `source_trace` | "Where did this file come from?" |
| 5 | `manual_queue_report` | `manual_queue` | "How much is manually queued vs automated?" |
| 6 | `processing_duration` | `processing_duration` | "How long do templates take to run?" |
| 7 | `deal_pipeline` | `deal_pipeline` | "Give me end-to-end pipeline view for this deal" |
| 8 | `staging_search` | `staging_search` | "Search template staging for X" |

Plus 4 enrichments to existing commands: `servicer_dossier`, `job_detail`, `triage_verify`/`triage_new`, `analyze_health`.

---

## Estimated Lines of Code

| Component | Estimated LOC | Notes |
|-----------|---------------|-------|
| `backend/db/ts_models.py` | ~150 | Dataclass models |
| `backend/db/queries.py` additions | ~120 | 15 new SQL constants |
| `backend/db/template_staging_repo.py` additions | ~200 | 7 new query methods |
| `cli/main.py` (new commands + enrichments) | ~400 | 8 cmd handlers + argparse + helper |
| `backend/triage/analyzer.py` additions | ~40 | Optional enrichment |
| `backend/analysis/health.py` additions | ~50 | Processing health section |
| `extension/copilot/tool.js` additions | ~40 | `_ACCEPTS` map entries |
| `extension/chat/participant.js` — `FRP_TOOLS` | ~120 | 8 tool definitions with rich descriptions |
| `extension/chat/participant.js` — `SYSTEM_PROMPT` | ~30 | Domain knowledge additions |
| `extension/chat/participant.js` — handler functions | ~400 | 8 new handlers (~50 lines each) |
| `extension/chat/participant.js` — `executeToolCall()` | ~30 | 8 switch cases |
| `extension/chat/participant.js` — `keywordFallbackRoute()` | ~50 | 6 keyword patterns |
| `extension/chat/participant.js` — `formatRawData()` | ~60 | 5 raw formatting cases |
| `extension/chat/participant.js` — `handleStagingCommand()` | ~50 | Slash command router |
| `extension/chat/participant.js` — enriched handler updates | ~40 | Updated prompts + follow-ups |
| `extension/package.json` | ~5 | Slash command registration |
| Test files (all combined) | ~600 | ~50 test cases |
| **Total** | **~2,385** | |
