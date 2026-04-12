# Phase 1: System Design
## FRP Agent — Foundation Architecture

**Document Version:** 1.0  
**Date:** February 24, 2026  
**Status:** Proposal — Pending Approval  
**Scope:** System-level architecture, data flows, component specifications

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Three-Layer Architecture](#three-layer-architecture)
3. [Project Structure](#project-structure)
4. [Data Model](#data-model)
5. [XML Schema — Email Settings](#xml-schema--email-settings)
6. [XML Schema — SFTP Settings](#xml-schema--sftp-settings)
7. [Database Schema — tblExternalDIDRef](#database-schema--tblexternaldidref)
8. [SQLite Index Schema](#sqlite-index-schema)
9. [CLI Command Protocol](#cli-command-protocol)
10. [Data Flow Diagrams](#data-flow-diagrams)
11. [VSIX Settings](#vsix-settings)
12. [Integration Points](#integration-points)

---

## Architecture Overview

### Core Principle

The FRP Agent follows the **three-layer pattern** proven in the KTS Agentic System:

1. **VS Code Extension (JavaScript)** — Orchestrator: handles chat UI, command routing, LLM calls
2. **Python Backend (CLI)** — Engine: XML parsing, DB queries, log indexing, data processing
3. **Copilot LLM (VS Code LM API)** — Generator: natural language understanding and response formatting

The extension communicates with the Python backend via **CLI subprocess** (JSON on stdout), not HTTP. This enables VSIX packaging with PyInstaller and clean process lifecycle.

### Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| CLI bridge (not HTTP) | VSIX packaging with PyInstaller, no server management, clean process lifecycle |
| SQLite for log index (not in-memory) | Persistence across sessions, 13K+ files too large for RAM |
| pyodbc for DB (not ORM) | Direct SQL, minimal dependencies, same driver for MSSQL/MySQL |
| xml.etree for XML (not lxml) | Built into Python stdlib, no native compiled dependencies for PyInstaller |
| Dual DB mode via VSIX setting | Same codebase for prod (MSSQL) and dev (MySQL), toggle via boolean |
| Backup as sibling folder | Simple, predictable, no additional config needed |

---

## Three-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    VS CODE EXTENSION (JavaScript)                     │
│                                                                       │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐     │
│  │ extension.js │  │chat/participant.js│  │  copilot/tool.js     │     │
│  │              │  │                  │  │  (backend bridge)    │     │
│  │ • activate() │  │ • @frp handler   │  │  • runCliJson()      │     │
│  │ • commands   │  │ • slash routing  │  │  • JSON parse        │     │
│  │ • settings   │  │ • LLM generation │  │  • error handling    │     │
│  └──────────────┘  │ • follow-ups     │  └──────────┬───────────┘     │
│                    │ • streaming      │             │                  │
│                    └──────────────────┘             │                  │
│                                                      │                  │
│  ┌──────────────────┐  ┌───────────────────────┐    │                  │
│  │ lib/frp_backend.js│  │ commands/             │    │                  │
│  │                  │  │  sync.js              │    │                  │
│  │ • ExeRunner      │  │  status.js            │    │                  │
│  │ • VenvRunner      │  │  validate.js          │    │                  │
│  │ • factory         │  └───────────────────────┘    │                  │
│  └──────────────────┘                                │                  │
└──────────────────────────────────────────────────────┼──────────────────┘
                                                       │
                              CLI subprocess (JSON on stdout)
                                                       │
┌──────────────────────────────────────────────────────┼──────────────────┐
│                     PYTHON BACKEND                    │                  │
│                                                       ▼                  │
│  ┌─────────────┐  ┌────────────────────────────────────────────┐        │
│  │ cli/main.py  │  │              COMMAND ROUTER               │        │
│  │              │  │                                            │        │
│  │ argparse     │──▶  search_jobs | validate_xml | sync_logs  │        │
│  │ JSON output  │  │  servicer_dossier | list_backups          │        │
│  └─────────────┘  │  save_xml | status                        │        │
│                    └────────────────────────────────────────────┘        │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐      │
│  │                        CORE ENGINES                            │      │
│  │                                                                │      │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │      │
│  │  │ xml_parser.py │  │ db/          │  │ log_indexer.py   │    │      │
│  │  │              │  │ connection.py │  │                  │    │      │
│  │  │ • parse()     │  │ conn_mysql.py│  │ • parse_file()   │    │      │
│  │  │ • search()    │  │ conn_mssql.py│  │ • sync_all()     │    │      │
│  │  │ • validate()  │  │ secrets_*.json│  │ • query()        │    │      │
│  │  │ • write()     │  │              │  │ • SQLite CRUD    │    │      │
│  │  │ • diff()      │  │ • factory()  │  │                  │    │      │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘    │      │
│  │                                                                │      │
│  │  ┌──────────────┐                                              │      │
│  │  │ backup.py     │                                              │      │
│  │  │              │                                              │      │
│  │  │ • create()    │                                              │      │
│  │  │ • list()      │                                              │      │
│  │  │ • restore()   │                                              │      │
│  │  └──────────────┘                                              │      │
│  └────────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                        COPILOT LLM (VS Code LM API)                      │
│                                                                          │
│  • Natural language query understanding                                  │
│  • Response formatting (markdown tables, summaries)                     │
│  • Follow-up suggestion generation                                      │
│  • J-01 query → structured filter translation                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
FRP_Agent/
├── .vscode/
│   ├── launch.json                    # F5 Extension Dev Host config
│   └── mcp.json                       # MCP server config (existing)
├── .github/
│   └── copilot-instructions.md        # Domain knowledge (existing)
├── extension/
│   ├── package.json                   # Extension manifest
│   ├── extension.js                   # Activation, command registration
│   ├── .vscodeignore                  # Exclude dev files from VSIX
│   ├── chat/
│   │   └── participant.js             # @frp chat handler
│   ├── copilot/
│   │   └── tool.js                    # Backend bridge (runCliJson)
│   ├── lib/
│   │   └── frp_backend.js             # ExeRunner / VenvRunner factory
│   ├── commands/
│   │   ├── sync.js                    # FRP: Sync Logs command
│   │   └── status.js                  # FRP: Status command
│   └── bin/                           # PyInstaller exe (VSIX only)
│       └── win-x64/
│           └── frp-backend/
│               └── frp-backend.exe
├── backend/
│   ├── __init__.py
│   ├── xml/
│   │   ├── __init__.py
│   │   ├── parser.py                  # XML read, search, validate
│   │   ├── writer.py                  # XML write with backup
│   │   └── models.py                  # EmailJob, SftpJob dataclasses
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py              # Factory: get_connection(prod_mode)
│   │   ├── connection_mysql.py        # MySQL connector for local dev
│   │   ├── connection_mssql.py        # MSSQL pyodbc for production
│   │   ├── queries.py                 # SQL query constants
│   │   └── deal_repo.py              # tblExternalDIDRef data access
│   ├── logs/
│   │   ├── __init__.py
│   │   ├── parser.py                  # Log file event extraction
│   │   ├── indexer.py                 # SQLite CRUD, sync workflow
│   │   └── models.py                  # LogEvent dataclass
│   ├── backup/
│   │   ├── __init__.py
│   │   └── manager.py                 # Backup create, list, restore
│   └── common/
│       ├── __init__.py
│       ├── models.py                  # Shared data models
│       └── config.py                  # Backend configuration
├── cli/
│   ├── __init__.py
│   └── main.py                        # CLI entry point: argparse → JSON stdout
├── config/
│   ├── __init__.py
│   ├── settings.py                    # Config dataclass
│   ├── secrets_mysql.json             # Local MySQL creds (gitignored)
│   └── secrets_mssql.json             # Prod MSSQL creds (gitignored)
├── tests/
│   ├── conftest.py                    # Pytest fixtures
│   ├── test_xml_parser.py             # XML parsing tests
│   ├── test_xml_writer.py             # XML writing tests
│   ├── test_db_connection.py          # Database connectivity tests
│   ├── test_deal_repo.py             # Deal data access tests
│   ├── test_log_parser.py            # Log parsing tests
│   ├── test_log_indexer.py           # SQLite indexer tests
│   ├── test_backup.py                # Backup manager tests
│   ├── test_cli.py                   # CLI integration tests
│   └── test_helpers.py               # Mock vscode for JS tests
├── scripts/
│   ├── build_vsix.ps1                 # Master build pipeline
│   ├── build_backend.ps1              # PyInstaller compilation
│   └── clean.ps1                      # Remove build artifacts
├── packaging/
│   └── frp_backend.spec               # PyInstaller spec file
├── docs/
│   ├── Phase1/                        # ← You are here
│   ├── Phase2/
│   ├── Phase3/
│   └── Phase4/
├── App Logs/                          # Sample log files (10 files)
├── Settings.ps1                       # Production email Settings.xml (reference)
├── Settings sample sftp.ps1           # Sample SFTP Settings.xml (reference)
├── tblExternalDIDRef.csv              # Reference copy (actual data from DB)
├── requirements.txt                   # Python dependencies
└── README.md                          # Project overview
```

---

## Data Model

### Entity Relationships

```
┌─────────────────────┐         ┌──────────────────────────┐
│   Email Settings.xml │         │    SFTP Settings.xml     │
│                     │         │                          │
│ <MailboxCollection>  │         │ <FolderCollection>       │
│   <JOB_NAME>         │         │   <JOB_NAME>             │
│     <Mailbox>        │         │     <Path>               │
│     <Folder>         │         │     <DSN>                │
│     <SME>            │         │     <SME>                │
│     <Filters>        │         │     <SkipList>           │
│     <Parsers>        │         │     <IgnoreList>         │
│     <ServicerID>  ◄──┼─────┐  │     <Parsers>            │
│     <Templates>      │     │  │     <ServicerID>  ◄──┐   │
│     ...              │     │  │     <Templates>      │   │
│   </JOB_NAME>        │     │  │     ...              │   │
│ </MailboxCollection>  │     │  │   </JOB_NAME>        │   │
└─────────────────────┘     │  │ </FolderCollection>    │   │
                             │  └──────────────────────┘   │
                             │                              │
           ServicerID = CompanyID                            │
                             │                              │
                    ┌────────┴──────────────────────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│         tblExternalDIDRef (DB Table)          │
│                                               │
│  ItemID  │ DID              │ ImportDID │ CompanyID │
│  (PK)    │ (Deal name)      │ (keyword) │ (→ServicerID) │
│──────────┼──────────────────┼───────────┼───────────│
│  1       │ CSFB 2006-HEAT5  │ C88       │ 150       │
│  2       │ CSFB 2006-HEAT5  │ C88       │ 111       │
│  3       │ JPMCWLT 2010-1   │ JPM10     │ 3722      │
│  ...     │ ...              │ ...       │ ...       │
│  4347    │ ...              │ ...       │ ...       │
└───────────────────────────────────────────────┘

Cardinality:
  • 4,347 total rows
  • 2,967 unique DIDs (deals)  
  • 118 unique CompanyIDs (servicers)
  • 3,720 unique ImportDIDs (keywords)
  • ONE CompanyID → ONE job in Settings.xml (1:1)
  • ONE DID → MANY CompanyIDs (1:N, different servicers handle same deal)
  • Batch pattern: same ImportDID + same CompanyID + multiple DIDs → NOT a collision
```

---

## XML Schema — Email Settings

### Structure

```xml
<?xml version="1.0"?>
<Settings>
  <!-- Infrastructure -->
  <DisableJob>0</DisableJob>
  <MapDrives>
    <N>\\server\share</N>
    <F>\\server\share</F>
    <!-- ... more drive mappings ... -->
  </MapDrives>
  <Server>server:port</Server>
  <Db>database_name</Db>
  <StagingServer>server:port</StagingServer>
  <StagingDb>database_name</StagingDb>
  <HashiAPI>/v1/.../creds/...</HashiAPI>
  <Email>
    <SMTPServer>smtp.server.com</SMTPServer>
    <SubjectTag>Email Monitor</SubjectTag>
    <From>sender@domain.com</From>
    <Support>support@domain.com</Support>
  </Email>
  
  <!-- Outlook Job Collection -->
  <Outlook>
    <Enabled>1</Enabled>
    <CredFileLocation>path_to_cred.xml</CredFileLocation>
    <MailboxCollection>
      
      <!-- Individual Job -->
      <JOB_NAME>
        <Mailbox>email@domain.com</Mailbox>              <!-- REQUIRED -->
        <Folder>Inbox</Folder>                             <!-- REQUIRED -->
        <SME>contact@domain.com</SME>                      <!-- REQUIRED -->
        <LastEmail>timestamp</LastEmail>                    <!-- OPTIONAL, auto-updated -->
        <SaveLocation>path_with_{tokens}</SaveLocation>    <!-- REQUIRED -->
        <Filters>                                          <!-- REQUIRED -->
          <From>@domain.com</From>                         <!-- OPTIONAL -->
          <Attachments>True</Attachments>                  <!-- OPTIONAL -->
          <Subject>keyword</Subject>                       <!-- OPTIONAL -->
        </Filters>
        <Parsers>                                          <!-- REQUIRED -->
          <DetachFile>regex_pattern</DetachFile>            <!-- One of several parser types -->
          <DetachFileSubject>regex_pattern</DetachFileSubject>
        </Parsers>
        <ServicerID>150</ServicerID>                       <!-- OPTIONAL (absent = shelf-level job) -->
        <QueueOneFile>True</QueueOneFile>                  <!-- OPTIONAL -->
        <Templates>                                        <!-- OPTIONAL -->
          <Main>template_name</Main>
        </Templates>
        <DayAdjust>3</DayAdjust>                           <!-- OPTIONAL -->
      </JOB_NAME>
      
    </MailboxCollection>
  </Outlook>
</Settings>
```

### Email Job Required vs Optional Tags

| Tag | Required | Notes |
|-----|----------|-------|
| `<Mailbox>` | **Yes** | Email address for EWS connection |
| `<Folder>` | **Yes** | Mailbox folder to monitor |
| `<SME>` | **Yes** | Subject matter expert email |
| `<SaveLocation>` | **Yes** | Path with tokens: `{DealFolder}`, `{YYYY}`, `{M}` |
| `<Filters>` | **Yes** | Container; child tags are optional |
| `<Parsers>` | **Yes** | At least one parser required |
| `<LastEmail>` | No | Auto-updated timestamp; may be absent on new jobs |
| `<ServicerID>` | No | Absent = shelf-level/process-level job |
| `<QueueOneFile>` | No | Boolean flag |
| `<Templates>` | No | Absent if no template needed |
| `<DayAdjust>` | No | Day offset for date calculations |

### Parser Types (Email)

| Parser Element | Description |
|----------------|-------------|
| `<DetachFile>` | Detach files by attachment name regex |
| `<DetachFileSubject>` | Detach files, using subject as filename base |
| Other custom parsers | Project-specific parser names |

---

## XML Schema — SFTP Settings

### Structure

```xml
<?xml version="1.0"?>
<Settings>
  <!-- Infrastructure (same as email) -->
  <DisableJob>0</DisableJob>
  <MapDrives>...</MapDrives>
  <Server>...</Server>
  <Db>...</Db>
  <StagingServer>...</StagingServer>
  <StagingDb>...</StagingDb>
  <HashiAPI>...</HashiAPI>
  <Email>
    <SMTPServer>...</SMTPServer>
    <SubjectTag>SFTP Monitor</SubjectTag>  <!-- Different from email -->
    <From>...</From>
    <Support>...</Support>
  </Email>
  
  <!-- SFTP Job Collection -->
  <Outlook>
    <Enabled>1</Enabled>
    <CredFileLocation>path_to_cred.xml</CredFileLocation>
    <FolderCollection>                       <!-- NOT MailboxCollection -->
      
      <!-- Individual SFTP Job -->
      <JOB_NAME>
        <Path>M:\path\to\folder</Path>                     <!-- REQUIRED (replaces Mailbox+Folder) -->
        <ServicerID>150</ServicerID>                       <!-- REQUIRED for SFTP -->
        <DSN>xf00.servicer.iman</DSN>                      <!-- REQUIRED (SFTP connection ID) -->
        <SME>contact@domain.com</SME>                      <!-- REQUIRED -->
        <SaveLocation>path_with_{tokens}</SaveLocation>    <!-- REQUIRED -->
        <SkipList>path_to_skiplist.txt</SkipList>          <!-- ALWAYS PRESENT -->
        <IgnoreList>path_to_ignorelist.txt</IgnoreList>    <!-- ALWAYS PRESENT -->
        <Parsers>                                          <!-- REQUIRED -->
          <MoveFile2>regex_pattern</MoveFile2>
        </Parsers>
        <ZipContentFilter>.xls</ZipContentFilter>          <!-- REQUIRED -->
        <Templates>                                        <!-- CONDITIONAL: absent if no template -->
          <Main>template_name</Main>
        </Templates>
        <DayAdjust>2</DayAdjust>                           <!-- REQUIRED -->
      </JOB_NAME>
      
    </FolderCollection>
  </Outlook>
</Settings>
```

### SFTP Job Tags

| Tag | Required | Notes |
|-----|----------|-------|
| `<Path>` | **Yes** | Source filesystem path (not mailbox) |
| `<ServicerID>` | **Yes** | Always present for SFTP jobs |
| `<DSN>` | **Yes** | SFTP data source name |
| `<SME>` | **Yes** | Subject matter expert email |
| `<SaveLocation>` | **Yes** | Path with tokens |
| `<SkipList>` | **Yes** | Always present — skip list file path |
| `<IgnoreList>` | **Yes** | Always present — ignore list file path |
| `<Parsers>` | **Yes** | Uses `<MoveFile2>` parser type |
| `<ZipContentFilter>` | **Yes** | File extension filter for zip contents |
| `<Templates>` | **Conditional** | Absent if no template exists yet |
| `<DayAdjust>` | **Yes** | Day adjustment value |

### Differences Between Email and SFTP

| Aspect | Email | SFTP |
|--------|-------|------|
| Container element | `<MailboxCollection>` | `<FolderCollection>` |
| Source identifier | `<Mailbox>` + `<Folder>` | `<Path>` |
| Connection info | (uses EWS) | `<DSN>` |
| Filter lists | `<Filters>` block | `<SkipList>` + `<IgnoreList>` |
| ServicerID | Optional | Always present |
| `<QueueOneFile>` | Optional | Not present |
| `<LastEmail>` | Optional | Not present |
| `<ZipContentFilter>` | Not present | Always present |
| Primary parser | `<DetachFile>` / `<DetachFileSubject>` | `<MoveFile2>` |
| SubjectTag in Email | "Email Monitor" | "SFTP Monitor" |

---

## Database Schema — tblExternalDIDRef

### Table Structure

```sql
CREATE TABLE tblExternalDIDRef (
    ItemID      INT PRIMARY KEY AUTO_INCREMENT,
    DID         VARCHAR(255) NOT NULL,      -- Deal identifier (e.g., "CSFB 2006-HEAT5")
    ImportDID   VARCHAR(255) NOT NULL,      -- Filename/subject keyword (e.g., "C88")
    CompanyID   INT NOT NULL                -- Maps to <ServicerID> in Settings.xml
);

-- Unique constraint: DID + ImportDID + CompanyID combination
CREATE UNIQUE INDEX UX_DealKeywordServicer 
ON tblExternalDIDRef (DID, ImportDID, CompanyID);
```

### Query Patterns Used in Phase 1

```sql
-- J-05: Cross-reference ServicerIDs
-- Check if a ServicerID from Settings.xml exists in the database
SELECT DISTINCT CompanyID FROM tblExternalDIDRef WHERE CompanyID = ?;

-- D-04: Servicer dossier — get all deals for a CompanyID
SELECT DID, ImportDID, CompanyID 
FROM tblExternalDIDRef 
WHERE CompanyID = ?
ORDER BY DID, ImportDID;

-- D-04: Servicer dossier — count summary
SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT DID) as unique_deals,
    COUNT(DISTINCT ImportDID) as unique_keywords
FROM tblExternalDIDRef 
WHERE CompanyID = ?;
```

### Dual Mode Connection

```python
# config/secrets_mysql.json (local dev — gitignored)
{
    "driver": "MySQL ODBC 8.0 Unicode Driver",
    "server": "localhost",
    "port": 3306,
    "database": "frp",
    "uid": "frp_user",
    "pwd": "local_password"
}

# config/secrets_mssql.json (production — gitignored)
{
    "driver": "ODBC Driver 17 for SQL Server",
    "server": "prod-server.us.bank-dns.com,49001",
    "database": "Servicing",
    "uid": "prod_user",
    "pwd": "prod_password",
    "trusted_connection": "no",
    "encrypt": "yes"
}
```

---

## SQLite Index Schema

### Database: `frp_logs.db`

Located alongside the extension data (workspace-specific or VSIX storage path).

```sql
-- Primary events table
CREATE TABLE IF NOT EXISTS log_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    log_file        TEXT NOT NULL,                      -- Source log filename
    log_type        TEXT NOT NULL,                      -- 'email' or 'sftp'
    timestamp       TEXT NOT NULL,                      -- ISO-8601 from log line
    job_name        TEXT,                               -- Job being processed
    mailbox         TEXT,                               -- Mailbox/path
    event_type      TEXT NOT NULL,                      -- See event types below
    emails_found    INTEGER,                            -- Count of emails found for job
    subject         TEXT,                               -- Email subject line
    sender          TEXT,                               -- From address
    parser          TEXT,                               -- Parser that matched
    filename        TEXT,                               -- File loaded/saved
    template        TEXT,                               -- Template queued
    error_message   TEXT,                               -- Error text if applicable
    raw_line        TEXT                                 -- Original log line
);

-- Index for common query patterns
CREATE INDEX IF NOT EXISTS idx_log_events_job ON log_events(job_name);
CREATE INDEX IF NOT EXISTS idx_log_events_timestamp ON log_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_log_events_type ON log_events(event_type);
CREATE INDEX IF NOT EXISTS idx_log_events_log_file ON log_events(log_file);

-- Tracking table to avoid re-indexing
CREATE TABLE IF NOT EXISTS indexed_files (
    filename        TEXT PRIMARY KEY,
    indexed_at      TEXT NOT NULL,                      -- When this file was indexed
    event_count     INTEGER NOT NULL,                   -- Events extracted from this file
    file_size       INTEGER                             -- File size in bytes
);

-- Metadata table
CREATE TABLE IF NOT EXISTS index_metadata (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
-- Keys: 'last_sync', 'schema_version', 'total_events', 'retention_months'
```

### Event Types

| Event Type | Extracted From | Fields Populated |
|------------|----------------|------------------|
| `job_start` | "Starting Outlook download for {JOB} ({MAILBOX})" | job_name, mailbox, timestamp |
| `emails_found` | "found {N}" | job_name, emails_found, timestamp |
| `email_processed` | "Processing: [SUBJECT]" + "From: {SENDER}" | job_name, subject, sender, timestamp |
| `parser_matched` | "Matched email [...] to [{PARSER}] parser" | job_name, parser, timestamp |
| `file_loaded` | "Load > {FILENAME}" | job_name, filename, timestamp |
| `template_queued` | "Queue file [{FILENAME}] for [{TEMPLATE}] template" | job_name, filename, template, timestamp |
| `did_mapping_failed` | "Did not find DID mapping for [...]" | job_name, subject, sender, timestamp |
| `error` | Exception or error lines | job_name, error_message, timestamp |

---

## CLI Command Protocol

### Invocation Pattern

```
Extension → Backend:   python -m cli.main <command> [args...] --json
Backend  → Extension:  JSON on stdout, logs on stderr
```

### Phase 1 CLI Commands

| Command | Arguments | Returns |
|---------|-----------|---------|
| `search_jobs` | `--query "text" --xml-type email\|sftp\|all --settings-path <path> [--sftp-settings-path <path>]` | `{ jobs: [...], total_count: N, xml_type: "email"\|"sftp" }` |
| `validate_xml` | `--xml-type email\|sftp --settings-path <path> [--db-mode mysql\|mssql] [--secrets-path <path>]` | `{ valid: bool, errors: [...], warnings: [...], info: [...] }` |
| `sync_logs` | `--log-folder <path> --log-type email\|sftp --db-path <path> --retention-months N` | `{ files_processed: N, events_indexed: N, files_skipped: N, errors: [...] }` |
| `servicer_dossier` | `--servicer-id N\|--job-name "name" --settings-path <path> [--sftp-settings-path <path>] --db-mode mysql\|mssql --secrets-path <path> --log-db-path <path>` | `{ job: {...}, deals: [...], log_summary: {...} }` |
| `list_backups` | `--settings-path <path> --xml-type email\|sftp` | `{ backups: [ { filename, timestamp, size_bytes } ], backup_folder: "path" }` |
| `save_xml` | `--settings-path <path> --xml-type email\|sftp` | `{ success: bool, backup_created: "filename", message: "..." }` |
| `status` | (none) | `{ version: "0.1.0", settings: {...}, log_index: {...}, db: {...} }` |

### Response Envelope

All CLI responses follow this envelope:

```json
{
    "success": true,
    "command": "search_jobs",
    "data": { /* command-specific data */ },
    "errors": [],
    "warnings": [],
    "elapsed_ms": 42
}
```

On error:
```json
{
    "success": false,
    "command": "search_jobs",
    "data": null,
    "errors": ["XML file not found: C:\\path\\to\\Settings.xml"],
    "warnings": [],
    "elapsed_ms": 1
}
```

---

## Data Flow Diagrams

### L-01: Log Sync Flow

```
User: "@frp /logs sync"
  │
  ▼
participant.js
  │ Parses command: /logs, subcommand: sync
  │
  ▼
tool.js → runCliJson(['sync_logs', 
    '--log-folder', emailLogFolder, 
    '--log-type', 'email',
    '--db-path', logDbPath,
    '--retention-months', '3'])
  │
  ▼
cli/main.py → sync_logs handler
  │
  ▼
backend/logs/indexer.py
  │
  ├── 1. List all .log files in folder
  ├── 2. Query indexed_files table for already-processed files
  ├── 3. For each NEW file:
  │     ├── backend/logs/parser.py → parse_log_file(path)
  │     │     ├── Read line by line
  │     │     ├── Extract events via regex patterns
  │     │     └── Return List[LogEvent]
  │     ├── Insert events into log_events table
  │     └── Record in indexed_files table
  ├── 4. Purge events older than retention_months
  └── 5. Return summary JSON
  │
  ▼
participant.js receives JSON
  │
  ▼
LLM formats response:
  "Synced 10 log files:
   - 847 events indexed
   - 0 files skipped (all new)
   - 3 errors encountered"
```

### J-01: Job Search Flow

```
User: "@frp /jobs show all sftp jobs"
  │
  ▼
participant.js
  │ Parses: command=/jobs, query="show all sftp jobs"
  │ Detects: xml_type hint = "sftp"
  │
  ▼
tool.js → runCliJson(['search_jobs', 
    '--query', 'show all sftp jobs',
    '--xml-type', 'sftp',
    '--settings-path', sftpSettingsPath])
  │
  ▼
cli/main.py → search_jobs handler
  │
  ▼
backend/xml/parser.py
  │
  ├── 1. Parse Settings.xml (SFTP) with xml.etree.ElementTree
  ├── 2. Extract all jobs from <FolderCollection>
  ├── 3. Build list of SftpJob dataclasses
  ├── 4. Apply query filter (match against all searchable fields)
  └── 5. Return filtered jobs as JSON
  │
  ▼
participant.js receives JSON
  │
  ▼
LLM formats as table:
  "Found 5 SFTP jobs:
   | Job Name | Path | ServicerID | DSN | Parser |
   |----------|------|------------|-----|--------|
   | Ocwen    | M:\..| 150        | xf00| MoveFile2 |
   ..."
```

### D-04: Servicer Dossier Flow

```
User: "@frp /deals servicer 150"
  │
  ▼
participant.js
  │ Parses: command=/deals, subcommand=servicer, id=150
  │
  ▼
tool.js → runCliJson(['servicer_dossier',
    '--servicer-id', '150',
    '--settings-path', emailSettingsPath,
    '--sftp-settings-path', sftpSettingsPath,
    '--db-mode', 'mysql',
    '--secrets-path', secretsPath,
    '--log-db-path', logDbPath])
  │
  ▼
cli/main.py → servicer_dossier handler
  │
  ├── 1. XML Parser: Find job(s) with ServicerID=150
  │     ├── Search email Settings.xml
  │     └── Search SFTP Settings.xml
  │     Result: job config details
  │
  ├── 2. DB Query: Get all deals for CompanyID=150
  │     ├── connection.py → get_connection(prod_mode=False)
  │     ├── deal_repo.py → get_deals_by_company(150)
  │     Result: list of {DID, ImportDID}
  │
  ├── 3. Log Query: Get recent activity for job name
  │     ├── indexer.py → query_events(job_name=job.name, limit=20)
  │     Result: recent log events
  │
  └── 4. Combine into dossier JSON
  │
  ▼
participant.js receives JSON
  │
  ▼
LLM formats comprehensive report:
  "## Servicer Dossier: CompanyID 150 (Ocwen)
   
   ### Job Configuration
   - Type: SFTP
   - Path: M:\!Sweep\Ocwen\In
   - DSN: xf00.ocwen3.iman
   ...
   
   ### Deal Mappings (from DB)
   | DID | ImportDID |
   |-----|-----------|
   | CSFB 2006-HEAT5 | C88 |
   ...
   
   ### Recent Activity (last 7 days)
   ..."
```

---

## VSIX Settings

### Extension Settings Declaration

```json
{
  "contributes": {
    "configuration": {
      "title": "FRP Agent",
      "properties": {
        "frpAgent.prod": {
          "type": "boolean",
          "default": false,
          "order": 1,
          "description": "Enable production mode (MSSQL). When false, uses local MySQL."
        },
        "frpAgent.outlookSettingsPath": {
          "type": "string",
          "default": "",
          "order": 2,
          "description": "Path to email Settings.xml file."
        },
        "frpAgent.sftpSettingsPath": {
          "type": "string",
          "default": "",
          "order": 3,
          "description": "Path to SFTP Settings.xml file."
        },
        "frpAgent.emailLogFolder": {
          "type": "string",
          "default": "",
          "order": 4,
          "description": "Folder containing email monitor log files."
        },
        "frpAgent.sftpLogFolder": {
          "type": "string",
          "default": "",
          "order": 5,
          "description": "Folder containing SFTP monitor log files."
        },
        "frpAgent.logRetentionMonths": {
          "type": "number",
          "default": 3,
          "order": 6,
          "description": "Number of months of log data to retain in the index."
        },
        "frpAgent.logLevel": {
          "type": "string",
          "default": "normal",
          "enum": ["normal", "verbose"],
          "order": 7,
          "description": "Output panel logging detail."
        },
        "frpAgent.model": {
          "type": "string",
          "default": "auto",
          "enum": ["auto", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "claude-sonnet-4"],
          "order": 8,
          "description": "LLM for response generation. 'auto' uses your active Copilot model."
        },
        "frpAgent.backendMode": {
          "type": "string",
          "default": "auto",
          "enum": ["auto", "venv", "exe"],
          "order": 100,
          "markdownDescription": "**[Developer]** Backend execution: 'auto' (prefer exe), 'venv' (live Python), 'exe' (compiled)."
        }
      }
    }
  }
}
```

---

## Integration Points

| Integration | Direction | Protocol | Phase |
|-------------|-----------|----------|-------|
| VS Code ↔ Python Backend | Bidirectional | CLI subprocess (JSON stdout) | Phase 1 |
| Python Backend ↔ MySQL | Read-only | pyodbc | Phase 1 |
| Python Backend ↔ MSSQL | Read-only | pyodbc | Phase 1 |
| Python Backend ↔ SQLite | Read/Write | sqlite3 (stdlib) | Phase 1 |
| Python Backend ↔ Settings.xml | Read/Write | xml.etree (stdlib) | Phase 1 |
| Python Backend ↔ Log files | Read-only | File I/O + regex | Phase 1 |
| VS Code ↔ Copilot LLM | Request/Response | vscode.lm API | Phase 1 |
| Python Backend ↔ .msg files | Read-only | extract-msg library | Phase 3 |
