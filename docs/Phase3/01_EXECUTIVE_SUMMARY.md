# Phase 3: Executive Summary
## FRP Agent — Log Analytics & Email Triage Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Implemented — 568 tests passing  
**Phase Scope:** Advanced log querying, deal activity tracking, DID failure analysis, job health monitoring, daily summaries, email triage (.msg parsing, verification, matching)  
**Use Cases Delivered:** L-02, L-03, L-04, L-05, E-01, E-02, E-03  
**Prerequisites:** Phase 1 (Foundation) + Phase 2 (CRUD & Intelligence) completed and verified

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Business Context](#business-context)
3. [Phase 3 Objectives](#phase-3-objectives)
4. [Use Cases Delivered](#use-cases-delivered)
5. [Architecture Evolution](#architecture-evolution)
6. [Risk Assessment](#risk-assessment)
7. [Success Criteria](#success-criteria)
8. [Dependencies & Prerequisites](#dependencies--prerequisites)
9. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Does Phase 3 Add?

Phase 3 transforms the FRP Agent from a **configuration management tool** into an **operational intelligence and triage assistant** with two major capability families:

1. **Log Analytics** — Users can query the SQLite log index built in Phase 1 to answer operational questions: "What happened with deal CSFB 2006-HEAT5?", "Which DIDs had mapping failures this week?", "Is the rptent job healthy?", and "Give me today's summary." These replace manual log file trawling across ~144 log files per day.

2. **Email Triage** — Users can drag-and-drop `.msg` files from Outlook to verify whether a new email notification request has an existing corresponding job, find matching jobs for known senders, or discover when no matching job exists and get guidance on creating one.

### Why Phase 3 After Phase 2?

Phase 3 depends on the cumulative foundation of Phases 1 and 2:

| Earlier Component | Phase 3 Usage |
|-------------------|---------------|
| SQLite Log Index (Phase 1) | L-02, L-03, L-04, L-05 — all log analytics query the index |
| Log Parser (Phase 1) | Log sync must be current before any analytics |
| XML Parser (Phase 1) | E-01, E-02 — search XML for matching jobs |
| DB Connector (Phase 1) | E-01 — verify sender against tblExternalDIDRef |
| Coverage Analysis (Phase 2) | E-01, E-03 — gap detection informs triage recommendations |
| Template Inventory (Phase 2) | E-03 — suggest template for new job creation |
| Job CRUD (Phase 2) | E-03 — transition from "no match" to "create new job" |

### What Can Users Do After Phase 3?

At the end of Phase 3, a user can:

1. **`@frp /logs deal CSFB 2006-HEAT5`** — Show all log activity for a specific deal across all jobs and dates
2. **`@frp /logs failures`** — List all DID mapping failures from recent logs with frequency analysis
3. **`@frp /logs health rptent`** — Health dashboard for a specific job: success rate, recent errors, volume trends
4. **`@frp /logs summary`** — Today's operational summary: files processed, errors, jobs triggered, top issues
5. **`@frp /triage verify`** — Drop a .msg file and verify if the sender/subject has a matching job and valid DID mapping
6. **`@frp /triage match`** — Search for jobs whose filters match a given email's sender/subject patterns
7. **`@frp /triage new`** — When no matching job exists, analyze the email and suggest which template to use for job creation

---

## Business Context

### Problem Phase 3 Solves

| Problem | Current State | Phase 3 Solution |
|---------|--------------|------------------|
| **Deal Activity Tracking** | Open 144+ log files per day, Ctrl+F for keywords | `@frp /logs deal {DID}` — instant cross-job history |
| **DID Failure Investigation** | Grep log files for "Did not find DID mapping" | `@frp /logs failures` — aggregated failures with counts |
| **Job Health Monitoring** | No aggregated view; check logs file-by-file | `@frp /logs health {job}` — success rate, error history |
| **Daily Ops Summary** | Manual tally from log files | `@frp /logs summary` — automated daily dashboard |
| **Email Triage (new request)** | Receive request via Outlook, manually check Settings.xml + DB | `@frp /triage verify` — automated verification pipeline |
| **Finding Matching Jobs** | Search XML by sender/subject manually | `@frp /triage match` — cross-reference .msg against all job filters |
| **No-Match Response** | Reply to requester with manual analysis | `@frp /triage new` — LLM-assisted template suggestion + gap analysis |

### Email Triage Workflow

The operations team receives monitoring requests via Outlook email. Today's workflow:

```
1. Receive email from internal stakeholder:
   "Please add monitoring for [Servicer X] sending [report type] to [mailbox]"
2. Open email in Outlook, examine sender/subject patterns
3. Open Settings.xml (2,092 lines), search for existing coverage
4. Query tblExternalDIDRef for DID/ImportDID mapping
5. If match → inform requester it's already covered
6. If no match → create new job (Phase 2 CRUD) or add to existing job
```

Phase 3's `/triage` commands automate steps 2-6 into a conversational flow.

### .msg File Format

| Attribute | Detail |
|-----------|--------|
| **Extension** | `.msg` (Microsoft Outlook message format) |
| **Python Library** | `extract-msg` (pip install extract-msg) |
| **Key Fields Extracted** | `sender`, `subject`, `body`, `date`, `to`, `cc`, `attachments` (filenames only) |
| **Delivery to Agent** | User drags .msg file into VS Code workspace or references file path in chat |
| **Processing** | Parse with extract-msg → extract fields → compare against Settings.xml filters |

### Design Constraints (Carried Forward)

All Phase 1 & 2 constraints remain:
- **Never write to database** — Email triage is read-only analysis
- **Write only to Settings.xml** — Only if user proceeds to job creation (via Phase 2 CRUD)
- **Automatic backup before mutation** — If triage leads to create, normal CRUD backup applies
- **Dual DB mode** — MSSQL (prod) / MySQL (dev)

### New Phase 3 Constraint

| Constraint | Detail |
|------------|--------|
| **.msg parsing is local only** | Files are parsed locally; no email content sent to external services |
| **No email sending** | Agent never sends emails; triage produces analysis for human decision-making |
| **Log queries use SQLite only** | All log analytics query the local SQLite index, never parse raw log files inline |
| **Auto-sync recommendation** | If SQLite index is stale (>24h since last sync), suggest `/logs sync` before analytics |

---

## Phase 3 Objectives

### Primary Objectives

1. **Log query engine** — Build query interfaces over the SQLite log index for deal activity, DID failures, job health, and daily summaries
2. **Email triage pipeline** — Parse .msg files, extract sender/subject/body, cross-reference against Settings.xml job filters and tblExternalDIDRef
3. **Health metrics** — Compute per-job success rates, error frequencies, and volume trends from indexed log events
4. **Daily summary generator** — Automated operational dashboard from the most recent day's log data

### Secondary Objectives

1. **Stale index detection** — Warn user if SQLite index hasn't been synced recently
2. **Triage follow-up chains** — After verify/match/new, suggest logical next steps (edit job, create job, check gaps)
3. **Failure pattern recognition** — Group DID mapping failures by ImportDID for bulk remediation hints

---

## Use Cases Delivered

### L-02: Deal Activity Query

| Attribute | Value |
|-----------|-------|
| **ID** | L-02 |
| **Category** | Log Analytics |
| **Phase** | 3 |
| **Slash Command** | `/logs deal` |
| **Trigger** | `@frp /logs deal CSFB 2006-HEAT5` or `@frp /logs deal 1234` |
| **Inputs** | DID identifier (name or number) |
| **Backend Commands** | `log_deal_activity` |
| **Data Sources** | SQLite log index (log_events table), tblExternalDIDRef (resolve DID → ImportDID) |
| **Output** | Timeline: date, job name, event type, file names, status |
| **Sort** | Chronological descending (newest first) |
| **Date Range** | Defaults to last 30 days; override with `--days N` |

### L-03: DID Failure Analysis

| Attribute | Value |
|-----------|-------|
| **ID** | L-03 |
| **Category** | Log Analytics |
| **Phase** | 3 |
| **Slash Command** | `/logs failures` |
| **Trigger** | `@frp /logs failures` or `@frp /logs failures --days 7` |
| **Inputs** | Optional: date range, specific job filter |
| **Backend Commands** | `log_did_failures` |
| **Data Sources** | SQLite log index (event_type = 'did_mapping_failure') |
| **Output** | Table: ImportDID keyword, failure count, affected jobs, first seen, last seen |
| **Grouping** | Grouped by ImportDID keyword, sorted by failure count descending |
| **Follow-up** | Suggest `@frp /deals gaps` for top failure keywords |

### L-04: Job Health Dashboard

| Attribute | Value |
|-----------|-------|
| **ID** | L-04 |
| **Category** | Log Analytics |
| **Phase** | 3 |
| **Slash Command** | `/logs health` |
| **Trigger** | `@frp /logs health rptent` or `@frp /logs health "CSMC 2015-1 rptent"` |
| **Inputs** | Job name or partial match |
| **Backend Commands** | `log_job_health` |
| **Data Sources** | SQLite log index |
| **Output** | Health report: run count, success rate, error count, last run timestamp, last error, avg emails per run, common errors |
| **Date Range** | Last 30 days by default |
| **Status Indicator** | 🟢 >95% success, 🟡 80-95%, 🔴 <80% |

### L-05: Daily Summary

| Attribute | Value |
|-----------|-------|
| **ID** | L-05 |
| **Category** | Log Analytics |
| **Phase** | 3 |
| **Slash Command** | `/logs summary` |
| **Trigger** | `@frp /logs summary` or `@frp /logs summary 2026-02-20` |
| **Inputs** | Optional: specific date (defaults to today) |
| **Backend Commands** | `log_daily_summary` |
| **Data Sources** | SQLite log index |
| **Output** | Dashboard: total jobs run, total emails processed, total files loaded, total errors, total DID failures, top 5 jobs by volume, top 5 error sources |
| **Comparison** | If previous day data exists, show delta (↑/↓) |

### E-01: Email Verification

| Attribute | Value |
|-----------|-------|
| **ID** | E-01 |
| **Category** | Email Triage |
| **Phase** | 3 |
| **Slash Command** | `/triage verify` |
| **Trigger** | `@frp /triage verify path/to/email.msg` |
| **Inputs** | Path to .msg file |
| **Backend Commands** | `triage_verify` |
| **Data Sources** | .msg file (parsed), Settings.xml (job filter matching), tblExternalDIDRef (DID mapping verification) |
| **Processing Pipeline** | 1. Parse .msg → extract sender, subject, body 2. Search Settings.xml for jobs whose filters match sender/subject 3. If match → query DB for matching ImportDIDs/CompanyIDs 4. Report: matching job(s), coverage status, any issues |
| **Output — Match Found** | "Email matches job 'X' (ServicerID Y). DID mapping verified: Z deals covered." |
| **Output — Partial Match** | "Email matches job 'X' but ServicerID Y has no DID mapping in database." |
| **Output — No Match** | "No existing job matches this email. Suggest: /triage new" |
| **Confirmation** | None — read-only analysis |

### E-02: Email Matching

| Attribute | Value |
|-----------|-------|
| **ID** | E-02 |
| **Category** | Email Triage |
| **Phase** | 3 |
| **Slash Command** | `/triage match` |
| **Trigger** | `@frp /triage match path/to/email.msg` or `@frp /triage match --sender "reports@bank.com" --subject "Monthly Report"` |
| **Inputs** | .msg file path OR manual sender/subject values |
| **Backend Commands** | `triage_match` |
| **Data Sources** | .msg file or manual input, Settings.xml (all job filters) |
| **Matching Logic** | Compare email sender against SubjectFilter/SenderFilter fields in each job. Case-insensitive substring match. Return all jobs with match score. |
| **Output** | Ranked list: Job Name, Match Type (sender/subject/both), Match Confidence (exact/partial), ServicerID |
| **Follow-up** | If multiple matches → suggest user pick one. If no matches → suggest `/triage new`. |

### E-03: No-Match Triage (New Job Suggestion)

| Attribute | Value |
|-----------|-------|
| **ID** | E-03 |
| **Category** | Email Triage |
| **Phase** | 3 |
| **Slash Command** | `/triage new` |
| **Trigger** | `@frp /triage new path/to/email.msg` |
| **Inputs** | .msg file path |
| **Backend Commands** | `triage_new` |
| **Data Sources** | .msg file (parsed), Settings.xml (template inventory), tblExternalDIDRef (gap check), Copilot LLM (recommendation) |
| **Processing Pipeline** | 1. Parse .msg → extract sender, subject, body, attachments 2. Run template inventory from Phase 2 → suggest best template match 3. Run coverage gap check → identify if sender's servicer has gaps 4. Use LLM to generate recommendation: template, fields, rationale |
| **Output** | Analysis: email details, suggested template, recommended configuration, gap analysis, next step: `/jobs create` |
| **Follow-up** | Direct user to `/jobs create {template} from "{suggested_job}"` with pre-filled values |
| **Confirmation** | None — this is analysis only; user decides whether to create |

---

## Architecture Evolution

### New Backend Modules (Phase 3 adds)

```
backend/
├── logs/                          # ENHANCED from Phase 1
│   ├── indexer.py                 # Existing — no changes
│   ├── parser.py                  # Existing — no changes
│   └── analytics.py               # NEW — Log query engine
├── triage/                        # NEW module
│   ├── __init__.py
│   ├── msg_parser.py              # NEW — .msg file parsing (extract-msg)
│   ├── matcher.py                 # NEW — Email ↔ job filter matching
│   └── analyzer.py                # NEW — No-match analysis + LLM recommendation
└── ...
```

### New CLI Commands (Phase 3 adds)

| Command | Use Case | Args |
|---------|----------|------|
| `log_deal_activity` | L-02 | --did, --days, --db-mode, --secrets-path |
| `log_did_failures` | L-03 | --days, --job-filter, --db-path |
| `log_job_health` | L-04 | --job-name, --days, --db-path |
| `log_daily_summary` | L-05 | --date, --db-path |
| `triage_verify` | E-01 | --msg-path, --settings-path, --db-mode, --secrets-path |
| `triage_match` | E-02 | --msg-path, --sender, --subject, --settings-path |
| `triage_new` | E-03 | --msg-path, --settings-path, --db-mode, --secrets-path |

### Extension Updates

- **`/logs` handler**: Add subcommand parsing for `deal`, `failures`, `health`, `summary`
- **`/triage` handler**: New slash command with `verify`, `match`, `new` subcommands
- **Follow-ups**: Post-failures → suggest gaps. Post-verify-match → suggest health. Post-new → suggest create.
- **File drop integration**: Detect .msg file paths in user input for triage commands

### New Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `extract-msg` | ^0.48.0 | Parse .msg files (Outlook format) |
| `olefile` | Transitive dep of extract-msg | OLE compound file parsing |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Stale SQLite index** | High | Medium | Auto-detect staleness, suggest /logs sync before analytics |
| **.msg format variations** | Medium | Medium | Test with multiple Outlook versions; graceful fallback for unparseable fields |
| **Large log volume slows queries** | Medium | Medium | SQLite indexes on event_type + timestamp + job_name; LIMIT queries |
| **Email filter matching false positives** | Medium | Low | Return ranked matches with confidence; user decides which match is correct |
| **extract-msg pip install in exe mode** | Low | High | Bundle extract-msg in PyInstaller spec; test .msg parsing in exe |
| **Sensitive email content** | Medium | Medium | Parse locally only; never send email body to LLM (only metadata) |

---

## Success Criteria

### Functional Criteria

| SC# | Criterion | Verification |
|-----|-----------|--------------|
| SC-01 | Deal activity query returns events for known DID | Cross-verify with log file grep |
| SC-02 | DID failure list matches known failures | Cross-verify with log file grep for "Did not find DID mapping" |
| SC-03 | Job health shows correct success rate | Manual count from log files |
| SC-04 | Daily summary totals match manual tally | Spot-check against 2-3 log files |
| SC-05 | .msg file parses sender/subject/body | Verify against Outlook display |
| SC-06 | Triage verify finds matching job for known email | Confirm against Settings.xml manual search |
| SC-07 | Triage match ranks results by relevance | Top match is the expected job |
| SC-08 | Triage new suggests appropriate template | Template matches the email's parser pattern |
| SC-09 | Stale index warning shown | Set index >24h old, run analytics, see warning |
| SC-10 | .msg content never sent to LLM | Verify LLM receives only metadata (sender, subject) not body |

### Non-Functional Criteria

| Criterion | Target |
|-----------|--------|
| Deal activity query (single DID) | < 2 seconds |
| DID failure analysis (30 days) | < 3 seconds |
| Job health (single job, 30 days) | < 2 seconds |
| Daily summary | < 3 seconds |
| .msg parsing | < 1 second per file |
| Triage verify (end-to-end) | < 5 seconds |
| Test coverage (Phase 3 modules) | ≥ 90% |

---

## Dependencies & Prerequisites

### Phase 2 Gate

All Phase 2 verification checkpoints must pass:

- [ ] CP-9: Phase 2 data models importable and serializable
- [ ] CP-10: Template inventory discovers correct pattern count
- [ ] CP-11: Coverage analysis matches manual SQL verification
- [ ] CP-12: CRUD engine creates/edits jobs correctly
- [ ] CP-13: Diff engine detects all change types
- [ ] CP-14: Extension handles all Phase 2 subcommands
- [ ] CP-FINAL-P2: All 8 Phase 2 use cases verified in Extension Dev Host

### External Dependencies

| Dependency | Required By | Status |
|------------|-------------|--------|
| `extract-msg` Python package | E-01, E-02, E-03 | New for Phase 3 |
| SQLite index fully populated | L-02, L-03, L-04, L-05 | Via Phase 1 L-01 |
| Settings.xml (email + SFTP) | E-01, E-02 | Same as Phase 1 |
| tblExternalDIDRef access | E-01, L-02 | Same as Phase 1 |
| Sample .msg files for testing | E-01, E-02, E-03 | Need 3-5 real/mock .msg files |

---

## Estimated Effort

| Sprint | Description | Hours |
|--------|-------------|-------|
| Sprint 15 | Triage Data Models + .msg Parser | 3–4h |
| Sprint 16 | Log Analytics Engine (L-02, L-03, L-04, L-05) | 5–7h |
| Sprint 17 | Email Triage Pipeline (E-01, E-02) | 5–7h |
| Sprint 18 | No-Match Analyzer (E-03) + LLM Integration | 4–5h |
| Sprint 19 | Extension Handlers (/logs analytics, /triage) | 4–5h |
| Sprint 20 | Integration Testing + Manual QA | 4–5h |
| **Total** | | **25–33 hours** |

**Calendar estimate:** 7–9 working days (continuing sprint numbering from Phase 2's Sprint 14)

---

*Next document: [02_SYSTEM_DESIGN.md](02_SYSTEM_DESIGN.md)*
