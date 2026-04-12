# Phase 1: Executive Summary
## FRP Agent — Foundation Layer

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Implemented — 568 tests passing  
**Phase Scope:** Core parsing, connectivity, basic read operations, backup engine  
**Use Cases Delivered:** L-01, J-01, J-05, D-04, X-04, X-01

---

## Table of Contents
1. [Executive Overview](#executive-overview)
2. [Business Context](#business-context)
3. [Phase 1 Objectives](#phase-1-objectives)
4. [Use Cases Delivered](#use-cases-delivered)
5. [Architecture Summary](#architecture-summary)
6. [Data Sources](#data-sources)
7. [Risk Assessment](#risk-assessment)
8. [Success Criteria](#success-criteria)
9. [Dependencies & Prerequisites](#dependencies--prerequisites)
10. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Is the FRP Agent?

The FRP Agent (`@frp`) is a VS Code Chat Participant extension that replaces the existing FRP web application's browser UI with GitHub Copilot Chat as the sole interface. It provides a conversational interface for managing email/SFTP monitoring jobs, analyzing deal coverage, querying application logs, and triaging emails — all within VS Code.

### Why Phase 1 First?

Phase 1 builds the **foundational engines** that every subsequent phase depends on:

- **XML Parser/Writer** — Every use case that reads or modifies Settings.xml needs this
- **Database Connectivity** — Deal intelligence (Phase 2), email triage (Phase 3) all query `tblExternalDIDRef`
- **Log Indexer** — All log analytics (Phase 3, Phase 4) depend on the SQLite index
- **Backup Engine** — Any write operation (Phase 2 CRUD) requires backup-before-save
- **CLI Bridge** — The core infrastructure connecting VS Code ↔ Python backend

Without Phase 1, no other phase can function.

### What Does Phase 1 Deliver?

At the end of Phase 1, a user can:

1. **`@frp /logs sync`** — Index all email/SFTP log files into a local SQLite database
2. **`@frp /jobs show all`** — Search and filter jobs across both email and SFTP Settings.xml
3. **`@frp /jobs validate`** — Lint and validate Settings.xml structure and cross-reference ServicerIDs with the database
4. **`@frp /deals servicer 150`** — Get a complete servicer dossier combining XML config + DB data + log activity
5. **`@frp /deploy backups`** — List all available backup files for both email and SFTP Settings.xml
6. **`@frp /deploy save email`** — Save the current email Settings.xml, creating an automatic timestamped backup

---

## Business Context

### Current State

The FRP (File Reception Portal) is a web application that manages automated email and SFTP file monitoring for US Bank's Global Structured Finance division. It monitors ~48 email mailbox jobs and an SFTP equivalent, receiving financial data files from servicers for ~2,967 unique deals.

Key infrastructure:
- **Settings.xml (Email)**: 2,092-line XML configuration with 48+ monitoring jobs
- **Settings.xml (SFTP)**: Separate XML for SFTP file transfers
- **tblExternalDIDRef**: MSSQL table (4,347 rows) mapping deals to jobs via ImportDID keywords
- **App Logs**: ~144 log files/day from the EmailMonitor.ps1 and SFTP scripts
- **ActiveBatch**: Scheduler that executes the monitoring scripts (not managed by agent)

### Problem Statement

The web UI requires context-switching, manual navigation, and doesn't support conversational queries like "which jobs are failing?" or "when was the last file for deal CSFB 2006-HEAT5?". The FRP Agent brings this capability directly into VS Code, where the operations team already works.

### Design Constraints

| Constraint | Detail |
|------------|--------|
| **Never write to database** | Agent reads tblExternalDIDRef via pyodbc but NEVER writes to MSSQL or MySQL |
| **Write only to Settings.xml** | Agent modifies email/SFTP XML config files (with automatic backup) |
| **Dual DB mode** | `frpAgent.prod = true` → MSSQL via pyodbc; `false` → MySQL for local testing |
| **No ActiveBatch integration** | Agent configures jobs; ActiveBatch executes them (separate system) |
| **Single mode** | No dev/prod split for XML — single Settings.xml per type |
| **Jobs without ServicerID** | Valid — they are process-level or shelf-level jobs, not mapped to individual deals |
| **Batch file pattern** | Same ImportDID + same CompanyID + multiple DIDs = legitimate batch, not a collision |

---

## Phase 1 Objectives

### Primary Objectives

1. **Scaffold the complete VSIX extension** — package.json, extension.js, chat participant, CLI bridge
2. **Build the XML parser/writer** — Read/write both email and SFTP Settings.xml formats
3. **Build the dual-mode DB connector** — MSSQL (prod) / MySQL (local) via pyodbc with secret files
4. **Build the log indexer** — Parse email/SFTP log files into SQLite for fast querying
5. **Build the backup engine** — Timestamped backups in `backup/` subfolder
6. **Implement 6 use cases** — L-01, J-01, J-05, D-04, X-04, X-01

### Secondary Objectives

1. Output channel logging (normal + verbose modes)
2. Proper error handling across all CLI commands
3. Comprehensive unit tests for every component
4. F5 dev workflow for fast edit-test cycle

---

## Use Cases Delivered

### L-01: Sync Logs → SQLite Index

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /logs sync` |
| **Description** | Parse email and SFTP log files, extract events, store in local SQLite database |
| **Input** | Log folder paths from VSIX settings |
| **Output** | Sync summary: files processed, events indexed, errors encountered |
| **Data Sources** | Email log files, SFTP log files |
| **Data Written** | SQLite database (local, `frp_logs.db`) |
| **Incremental** | Yes — skips already-indexed files (by filename) |
| **Retention** | Configurable via `frpAgent.logRetentionMonths` (default: 3) |
| **Log Filename Pattern** | `EmailMonitor_Settings.{YYYYMMDDHHMMSSMMM}.log` |

**Events Extracted Per Log File:**
- Job start: job name, mailbox, timestamp
- Emails found: count per job
- Email processed: subject, sender, parser matched, files loaded, template queued
- DID mapping failures: "Did not find DID mapping for [...]"
- Errors: any exception or failure lines

### J-01: Search & Filter Jobs

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /jobs <query>` |
| **Description** | Natural language search across all jobs in both email and SFTP Settings.xml |
| **Input** | Free-text query (e.g., "show me all jobs for mailbox rptent", "shelf-level jobs", "jobs with ServicerID 150") |
| **Output** | Filtered job list with key fields: name, mailbox/path, ServicerID, parsers, templates |
| **Data Sources** | Email Settings.xml, SFTP Settings.xml |
| **Searchable Fields** | Job name, Mailbox, Folder, Path, DSN, SME, ServicerID, Parser names, Template names, Filter values |
| **Special Filters** | "shelf-level jobs" = jobs with no ServicerID; "email jobs" vs "sftp jobs" |

### J-05: Validate Settings.xml

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /jobs validate` or `@frp /jobs validate sftp` |
| **Description** | Lint and structural validation of Settings.xml |
| **Input** | XML type (email or sftp, defaults to email) |
| **Output** | Validation report: errors, warnings, info messages |
| **Checks Performed** | See detailed list in Technical Design |
| **Data Sources** | Settings.xml + tblExternalDIDRef (for ServicerID cross-reference) |

### D-04: Servicer Dossier

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /deals servicer <ID>` or `@frp /deals servicer <job_name>` |
| **Description** | Complete profile for a servicer/job: XML config + DB mappings + log activity |
| **Input** | CompanyID (number) or job name (string) |
| **Output** | Combined report: job configuration, all mapped DIDs/ImportDIDs, recent log events |
| **Data Sources** | Settings.xml + tblExternalDIDRef + SQLite log index |

### X-04: List Backups

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /deploy backups` or `@frp /deploy backups sftp` |
| **Description** | Show all backup files in the `backup/` directory |
| **Input** | XML type (email or sftp) |
| **Output** | List of backup files with timestamps and sizes |
| **Backup Location** | `<Settings.xml parent>/backup/` subfolder |
| **Filename Pattern** | `Settings_{YYYYMMDD}_{HHMMSS}.xml` |

### X-01: Save Settings.xml

| Attribute | Detail |
|-----------|--------|
| **Slash Command** | `@frp /deploy save email` or `@frp /deploy save sftp` |
| **Description** | Write current in-memory XML to disk after backing up the current file |
| **Input** | XML type (email or sftp) |
| **Output** | Confirmation with backup filename |
| **Side Effects** | Creates backup file, overwrites current Settings.xml |
| **Confirmation** | Requires user confirmation before writing |

---

## Architecture Summary

```
┌──────────────────────────────────────────────────────────────────┐
│  VS Code Extension (JavaScript)                                  │
│                                                                  │
│  extension.js          — Activation, command registration        │
│  chat/participant.js   — @frp chat handler, LLM generation       │
│  copilot/tool.js       — Backend CLI bridge (runCliJson)         │
│  lib/frp_backend.js    — CLI runner (venv/exe factory)           │
│  commands/sync.js      — VS Code command: FRP: Sync Logs        │
│  commands/status.js    — VS Code command: FRP: Status            │
└──────────────────┬──────────────────┬────────────────────────────┘
                   │ CLI (JSON stdout) │ vscode.lm API
                   ▼                   ▼
┌──────────────────────┐    ┌──────────────────────────────────────┐
│  Python Backend       │    │  Copilot LLM (GPT-4.1, Claude, etc.) │
│  cli/main.py          │    │  → Natural language understanding     │
│  → search_jobs        │    │  → Response formatting               │
│  → validate_xml       │    │  → Follow-up suggestions            │
│  → sync_logs          │    │                                      │
│  → servicer_dossier   │    │                                      │
│  → list_backups       │    │                                      │
│  → save_xml           │    │                                      │
│  Returns JSON stdout  │    │                                      │
└──────────────────────┘    └──────────────────────────────────────┘
```

---

## Data Sources

| Source | Type | Access | Used By |
|--------|------|--------|---------|
| Email Settings.xml | XML file | Read/Write | J-01, J-05, D-04, X-01 |
| SFTP Settings.xml | XML file | Read/Write | J-01, J-05, D-04, X-01 |
| tblExternalDIDRef | MSSQL/MySQL table | Read-Only | J-05 (cross-ref), D-04 |
| Email App Logs | Log files | Read-Only | L-01 |
| SFTP App Logs | Log files | Read-Only | L-01 |
| SQLite Index | Local database | Read/Write | D-04 (log activity) |
| Backup files | XML files | Read/Write | X-04, X-01 |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| XML parsing edge cases | Medium | Medium | Comprehensive test suite with real Settings.xml samples |
| DB connection failures | Low | High | Graceful degradation — UCs work without DB (show warning) |
| Log format changes | Low | Medium | Regex patterns tested against 10 real log files |
| Large log volume (~13K files) | Medium | Medium | Incremental sync + retention limit (3 months) |
| PyInstaller bundling issues | Low | Medium | Test exe build early in Phase 1 |

---

## Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| All 6 use cases functional | Manual verification in Extension Dev Host |
| XML parser handles both email and SFTP formats | Unit tests pass for both formats |
| DB connection works in both modes | Tests pass with MySQL and MSSQL |
| Log sync processes sample files correctly | 10 sample logs indexed, events queryable |
| Backup/save cycle works | Save creates backup, file matches expected content |
| F5 dev workflow < 5 seconds | Edit participant.js → save → Ctrl+R → test |
| Unit test coverage | 100+ tests across all components |

---

## Dependencies & Prerequisites

| Dependency | Details |
|------------|---------|
| VS Code | ^1.95.0 |
| GitHub Copilot subscription | Required for vscode.lm API |
| Python | ^3.10 |
| pyodbc | Database connectivity |
| Node.js | ^18.0.0 |
| MySQL (local) | For `frpAgent.prod = false` testing |
| MSSQL (prod) | For `frpAgent.prod = true` |
| ODBC Drivers | MySQL ODBC driver (local) + SQL Server ODBC driver (prod) |

---

## Estimated Effort

| Component | Estimated Time | Risk Level |
|-----------|----------------|------------|
| VSIX scaffold (package.json, extension.js, participant.js) | 3-4 hours | Low |
| CLI bridge (frp_backend.js, tool.js, cli/main.py) | 2-3 hours | Low |
| XML parser/writer (email + SFTP) | 4-5 hours | Medium |
| Dual DB connector (connection.py, secrets) | 2-3 hours | Low |
| Log indexer (parser + SQLite) | 4-5 hours | Medium |
| Backup engine | 1-2 hours | Low |
| UC implementation (6 use cases) | 4-6 hours | Medium |
| Unit tests | 4-6 hours | Low |
| Integration testing + F5 workflow | 2-3 hours | Low |
| **TOTAL** | **26-37 hours** | **Low-Medium** |

**Timeline:** 7-10 work days (4 hours/day)
