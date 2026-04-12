# Phase 6: System Design
## FRP Agent — SQLite Job Cache + Multi-Agent Framework Retrofit

**Document Version:** 1.0  
**Date:** March 4, 2026  
**Status:** Planning  
**Companion:** [01_EXECUTIVE_SUMMARY.md](01_EXECUTIVE_SUMMARY.md)

---

## Table of Contents
1. [Module Map](#module-map)  
2. [Work Stream A — SQLite Cache Design](#work-stream-a--sqlite-cache-design)  
3. [Work Stream B — Framework Retrofit Design](#work-stream-b--framework-retrofit-design)  
4. [Dependency Graph](#dependency-graph)  
5. [Data Models](#data-models)  
6. [CLI Command Changes](#cli-command-changes)  
7. [Extension Impact Assessment](#extension-impact-assessment)  
8. [Data Flow Diagrams](#data-flow-diagrams)  
9. [Error Handling Strategy](#error-handling-strategy)  
10. [File Manifest](#file-manifest)

---

## 1. Module Map

### New Files

| File | Work Stream | Purpose |
|---|---|---|
| `backend/db/xml_index.py` | WS-A | `XmlJobIndex` class — SQLite cache for email/SFTP jobs |
| `tests/db/test_xml_index.py` | WS-A | Unit + integration tests for XmlJobIndex |
| `AGENTS.md` | WS-B | Root-level agent operating rules |
| `.github/copilot-instructions.md` | WS-B | Rewrite — prescriptive rules (not descriptive) |
| `.github/agents/config.agent.md` | WS-B | XML config agent persona |
| `.github/agents/triage.agent.md` | WS-B | Email triage agent persona |
| `.github/agents/intel.agent.md` | WS-B | Deal intelligence agent persona |
| `.github/agents/ops.agent.md` | WS-B | Operations/analytics agent persona |
| `.github/prompts/search-jobs.prompt.md` | WS-B | Task launcher: search jobs |
| `.github/prompts/triage-email.prompt.md` | WS-B | Task launcher: triage email |
| `.github/prompts/staging-lookup.prompt.md` | WS-B | Task launcher: staging lookup |
| `.github/prompts/deploy-diff.prompt.md` | WS-B | Task launcher: deploy diff |
| `.github/prompts/health-check.prompt.md` | WS-B | Task launcher: health check |
| `.github/prompts/deal-lookup.prompt.md` | WS-B | Task launcher: deal lookup |
| `backend.instructions.md` | WS-B | Python backend path-specific rules |
| `extension.instructions.md` | WS-B | Extension JS path-specific rules |
| `cli.instructions.md` | WS-B | CLI path-specific rules |
| `skills/xml-config/SKILL.md` | WS-B | XML config skill pack |
| `skills/email-triage/SKILL.md` | WS-B | Email triage skill pack |
| `skills/deal-intelligence/SKILL.md` | WS-B | Deal intelligence skill pack |
| `skills/log-forensics/SKILL.md` | WS-B | Log forensics skill pack |
| `skills/template-staging/SKILL.md` | WS-B | Template staging skill pack |

### Modified Files

| File | Work Stream | Change |
|---|---|---|
| `cli/main.py` | WS-A | `cmd_search_jobs`, `cmd_job_detail` internals swap to SQLite; `cmd_create_job`, `cmd_edit_job` add `_rebuild_sqlite()` call; new `cmd_rebuild_db` handler |
| `backend/db/__init__.py` | WS-A | Export `XmlJobIndex` |
| `extension/package.json` | WS-A | Add `frpAgent.cacheDbPath` setting (order 12) |
| `packaging/frp_backend.spec` | WS-A | Add Phase 5 + Phase 6 hidden imports |

### Untouched Files (Confirmed)

| File | Why Untouched |
|---|---|
| `backend/xml/parser.py` | Still used by crud, diff, rollback, templates — not removed |
| `backend/xml/models.py` | `EmailJob` / `SftpJob` dataclasses remain canonical types |
| `backend/xml/crud.py` | `JobCrudEngine` writes XML; SQLite rebuild is called after, not inside |
| `backend/xml/writer.py` | Writes XML directly — no SQLite awareness needed |
| `backend/xml/diff.py` | Compares two XML files — no caching needed |
| `backend/xml/rollback.py` | Restores XML from backup — `_rebuild_sqlite()` called after rollback in CLI |
| `extension/chat/participant.js` | All changes are CLI-level; backendCall interface unchanged |
| `extension/copilot/tool.js` | No new tools needed — existing schema covers all commands |
| `extension/package.json` | **Moved to Modified** — `frpAgent.cacheDbPath` setting added |
| All `backend/intel/`, `backend/analysis/`, `backend/triage/` | No changes — they consume XML models, not XML parser |
| All `backend/logs/` | LogIndexer already uses SQLite — no changes |

---

## 2. Work Stream A — SQLite Cache Design

### 2.1 Architecture Principles

1. **XML is truth; SQLite is cache.** PowerShell EmailMonitor reads/writes XML. SQLite is invisible to it.
2. **Config fields only.** `last_run_time` (updated by PowerShell every ~10 min) is excluded from caching and hashing.
3. **Content hash for passive correctness.** Every query checks hash; stale detection is a warning, not a blocker.
4. **Explicit rebuild for bootstrap.** `frp xml rebuild-db` parses XML → populates SQLite. Called by agent after CRUD operations.
5. **Follows LogIndexer patterns.** Same WAL mode, `row_factory=sqlite3.Row`, schema versioning, `__enter__`/`__exit__`.

### 2.2 SQLite Schema

```sql
-- Table: email_jobs
CREATE TABLE IF NOT EXISTS email_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    mailbox         TEXT    NOT NULL,
    folder          TEXT    NOT NULL DEFAULT '',
    sme             TEXT    NOT NULL DEFAULT '',
    last_email      TEXT,
    save_location   TEXT    NOT NULL DEFAULT '',
    filters_json    TEXT    NOT NULL DEFAULT '{}',
    parsers_json    TEXT    NOT NULL DEFAULT '{}',
    servicer_id     INTEGER,
    queue_one_file  INTEGER,              -- 0/1 boolean
    templates_json  TEXT    NOT NULL DEFAULT '{}',
    day_adjust      INTEGER,
    sender          TEXT    NOT NULL DEFAULT '', -- denormalised from filters.From
    scrubber        TEXT    NOT NULL DEFAULT '', -- denormalised from templates.Main
    match_mode      TEXT    NOT NULL DEFAULT ''  -- computed from parsers
);

-- Table: sftp_jobs
CREATE TABLE IF NOT EXISTS sftp_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    path                TEXT    NOT NULL DEFAULT '',
    servicer_id         INTEGER NOT NULL DEFAULT 0,
    dsn                 TEXT    NOT NULL DEFAULT '',
    sme                 TEXT    NOT NULL DEFAULT '',
    save_location       TEXT    NOT NULL DEFAULT '',
    skip_list           TEXT    NOT NULL DEFAULT '',
    ignore_list         TEXT    NOT NULL DEFAULT '',
    parsers_json        TEXT    NOT NULL DEFAULT '{}',
    zip_content_filter  TEXT    NOT NULL DEFAULT '',
    templates_json      TEXT    NOT NULL DEFAULT '{}',
    day_adjust          INTEGER,
    scrubber            TEXT    NOT NULL DEFAULT '', -- denormalised from templates.Main
    match_mode          TEXT    NOT NULL DEFAULT ''  -- computed from parsers
);

-- Table: cache_metadata
CREATE TABLE IF NOT EXISTS cache_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_email_jobs_servicer    ON email_jobs(servicer_id);
CREATE INDEX IF NOT EXISTS idx_email_jobs_mailbox     ON email_jobs(mailbox);
CREATE INDEX IF NOT EXISTS idx_email_jobs_sender      ON email_jobs(sender);
CREATE INDEX IF NOT EXISTS idx_sftp_jobs_servicer     ON sftp_jobs(servicer_id);
CREATE INDEX IF NOT EXISTS idx_sftp_jobs_dsn          ON sftp_jobs(dsn);
```

**Design Notes:**

- `filters_json`, `parsers_json`, `templates_json` store the raw dicts as JSON text. This preserves fidelity without schema explosion.
- `sender`, `scrubber`, `match_mode` are **denormalised computed columns** extracted during rebuild. They enable direct `WHERE` filtering without JSON parsing.
- `queue_one_file` is stored as integer (0/1) since SQLite has no boolean type.
- `last_run_time` is deliberately **excluded** — PowerShell owns it.

### 2.3 XmlJobIndex Class Interface

```python
class XmlJobIndex:
    """SQLite-backed query cache for Settings.xml job configurations.

    Follows the same patterns as LogIndexer:
    - WAL journal mode
    - row_factory = sqlite3.Row
    - Schema versioning via cache_metadata
    - Context manager support (__enter__/__exit__)
    """

    _SCHEMA_VERSION = "1"

    def __init__(self, db_path: str) -> None: ...
    def rebuild(self, xml_path: str, xml_type: str = "email") -> Dict: ...
    def search_jobs(self, query: str, xml_type: str = "all") -> List[Dict]: ...
    def get_job(self, name: str) -> Optional[Dict]: ...
    def get_all_jobs(self, xml_type: str = "all") -> List[Dict]: ...
    def check_hash(self, xml_path: str, xml_type: str = "email") -> Dict: ...
    def get_status(self) -> Dict: ...
    def close(self) -> None: ...
    def __enter__(self) -> "XmlJobIndex": ...
    def __exit__(self, *args) -> None: ...
```

### 2.4 Content Hash Algorithm

```python
def _compute_config_hash(xml_path: str, xml_type: str) -> str:
    """Compute SHA-256 hash of config-only XML content.

    Strips <LastRunTime> elements before hashing so that
    PowerShell's periodic updates don't trigger false staleness.
    """
    import hashlib
    import copy
    import xml.etree.ElementTree as ET

    tree = ET.parse(xml_path)
    root = copy.deepcopy(tree.getroot())

    # Strip last_run_time elements
    for elem in root.iter():
        for child in list(elem):
            if child.tag.lower() in ("lastruntime", "last_run_time"):
                elem.remove(child)

    canonical = ET.tostring(root, encoding="unicode")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Why strip `LastRunTime`?**  
PowerShell's EmailMonitor.ps1 updates this field every ~10 minutes. Without stripping it, the hash would always report "stale" even though no configuration changed. By excluding it, the hash only changes when a job's config fields are modified.

### 2.5 Rebuild Flow

```
             ┌──────────────┐
             │ Settings.xml │
             └──────┬───────┘
                    │  ET.parse()
                    ▼
          ┌─────────────────────┐
          │ SettingsXmlParser   │
          │  .get_all_jobs()    │
          └─────────┬───────────┘
                    │  List[EmailJob | SftpJob]
                    ▼
          ┌─────────────────────┐
          │ XmlJobIndex.rebuild │
          │  1. DELETE all rows │
          │  2. INSERT each job │
          │  3. Compute hash    │
          │  4. Store metadata  │
          └─────────┬───────────┘
                    │
                    ▼
          ┌─────────────────────┐
          │  frp_xml_cache.db   │
          │  (SQLite file)      │
          └─────────────────────┘
```

---

## 3. Work Stream B — Framework Retrofit Design

### 3.1 Framework Hierarchy

The Copilot multi-agent file hierarchy defines 5 layers:

```
Layer 1: copilot-instructions.md    — Global rules (always loaded)
Layer 2: AGENTS.md                  — Agent operating manual
Layer 3: *.agent.md                 — Per-agent persona + tools + rules
Layer 4: SKILL.md                   — Teachable capability packs
Layer 5: *.prompt.md                — Reusable task launchers
         *.instructions.md          — Path-specific rules (auto-loaded per file)
```

### 3.2 Current State → Target State

| Layer | Current | Target |
|---|---|---|
| Layer 1 | `.github/copilot-instructions.md` (60 lines, descriptive) | Rewrite: prescriptive rules (~120 lines) |
| Layer 2 | None | `AGENTS.md` with validation rules, testing contract, field ownership |
| Layer 3 | None | 4 agent files: config, triage, intel, ops |
| Layer 4 | None | 5 skill packs: xml-config, email-triage, deal-intelligence, log-forensics, template-staging |
| Layer 5 | None | 6 prompt files + 3 instructions.md files |

### 3.3 Agent Personas — Design Map

Each agent persona corresponds to an existing code domain:

| Agent | Domain Modules | CLI Commands | Slash Commands |
|---|---|---|---|
| **config** | `backend/xml/*`, `backend/backup/*` | `search_jobs`, `job_detail`, `create_job`, `edit_job`, `template_inventory`, `diff`, `rollback`, `rebuild_db` | `/jobs`, `/deploy` |
| **triage** | `backend/triage/*` | `triage_verify` | `/triage` |
| **intel** | `backend/intel/*`, `backend/db/deal_repo.py` | `deal_lookup`, `coverage_gaps`, `orphan_detection`, `collision_detection` | `/deals`, `/analyze` |
| **ops** | `backend/logs/*`, `backend/analysis/*`, `backend/db/template_staging_repo.py` | `sync_logs`, `log_search`, `log_summary`, `staging_*` | `/logs`, `/staging` |

### 3.4 Agent File Structure

Each `.agent.md` file follows a consistent structure:

```markdown
---
name: <agent-name>
description: <one-line description>
tools:
  - <tool-1>
  - <tool-2>
---

# <Agent Name>
## Role
## Rules
## Tools & Data Sources
## Output Format
## Example Interactions
```

### 3.5 Skill Pack Structure

Each `SKILL.md` describes domain knowledge that Copilot can apply:

```markdown
# <Skill Name>
## Domain Overview
## Key Concepts
## Common Patterns
## Data Sources
## CLI Commands (with examples)
## Troubleshooting
```

### 3.6 Prompt File Structure

Each `.prompt.md` provides a repeatable task template:

```markdown
---
mode: <agent|ask|edit>
tools:
  - <tool-list>
description: <one-line summary>
---

# <Task Title>
## Context
## Steps
## Expected Output
```

### 3.7 Instructions.md Files

Path-specific rules auto-loaded when editing files under that path:

| File | Path Scope | Key Rules |
|---|---|---|
| `backend.instructions.md` | `backend/**` | Python conventions, dataclass patterns, error handling, test expectations |
| `extension.instructions.md` | `extension/**` | JS conventions, backendCall patterns, handler structure, participant format |
| `cli.instructions.md` | `cli/**` | CliResponse contract, argparse patterns, JSON output rules |

---

## 4. Dependency Graph

### WS-A Dependencies

```
backend/db/xml_index.py
  ├── imports: sqlite3 (stdlib)
  ├── imports: hashlib (stdlib)
  ├── imports: json (stdlib)
  ├── imports: xml.etree.ElementTree (stdlib)
  ├── imports: backend.xml.parser.SettingsXmlParser
  ├── imports: backend.xml.models (EmailJob, SftpJob)
  └── used by: cli/main.py (cmd_search_jobs, cmd_job_detail, cmd_create_job, cmd_edit_job, cmd_rebuild_db)

cli/main.py
  ├── existing: backend.xml.parser.SettingsXmlParser (still used by diff, rollback, etc.)
  ├── NEW: backend.db.xml_index.XmlJobIndex
  └── existing: all other imports unchanged
```

### WS-B Dependencies

**None.** All framework files are standalone markdown. They reference existing code paths but have no import dependencies.

---

## 5. Data Models

### 5.1 XmlJobIndex Return Types

All public methods return plain dicts (not dataclasses) to match the existing CLI interface:

```python
# search_jobs() returns:
{
    "jobs": [
        {
            "job_name": "CMLTI_Fay_100",
            "mailbox": "gsfi_llc_dl@usbank.com",
            "sender": "reports@fayservicing.com",
            "servicer_id": 60,
            "save_path": "M:\\{DealFolder}\\Data\\{YYYY}\\{M}\\",
            "scrubber": "CMLTI_Fay_100",
            "match_mode": "Subject",
            "match_mode_description": "Detects files by matching a keyword in the email subject line",
            "queue_one_file": True,
            "xml_type": "email",
        },
        # ...
    ],
    "total_count": 5,
    "xml_type": "all",
    "cache_status": "fresh",  # or "stale" with warning
}
```

```python
# get_job() returns:
{
    "job_name": "CMLTI_Fay_100",
    "mailbox": "gsfi_llc_dl@usbank.com",
    "folder": "Inbox",
    "sme": "John.Doe",
    "last_email": None,
    "sender": "reports@fayservicing.com",
    "save_path": "M:\\{DealFolder}\\Data\\{YYYY}\\{M}\\",
    "servicer_id": 60,
    "scrubber": "CMLTI_Fay_100",
    "match_mode": "Subject",
    "match_mode_description": "...",
    "queue_one_file": True,
    "xml_type": "email",
    "filters": {...},
    "parsers": {...},
    "templates": {...},
}
```

```python
# rebuild() returns:
{
    "email_jobs_loaded": 48,
    "sftp_jobs_loaded": 22,
    "content_hash": "a1b2c3d4...",
    "xml_path": "Settings.xml",
    "rebuilt_at": "2026-03-04T14:30:00Z",
}
```

```python
# check_hash() returns:
{
    "stored_hash": "a1b2c3d4...",
    "current_hash": "a1b2c3d4...",
    "is_fresh": True,  # or False
    "last_rebuild": "2026-03-04T14:30:00Z",
}
```

### 5.2 Mapping: EmailJob → email_jobs table

| EmailJob field | SQLite column | Notes |
|---|---|---|
| `name` | `name` | UNIQUE |
| `mailbox` | `mailbox` | — |
| `folder` | `folder` | — |
| `sme` | `sme` | — |
| `last_email` | `last_email` | Nullable |
| `save_location` | `save_location` | — |
| `filters` | `filters_json` | `json.dumps(filters)` |
| `parsers` | `parsers_json` | `json.dumps(parsers)` |
| `servicer_id` | `servicer_id` | Nullable |
| `queue_one_file` | `queue_one_file` | 0/1 integer |
| `templates` | `templates_json` | `json.dumps(templates)` |
| `day_adjust` | `day_adjust` | Nullable |
| *(computed)* | `sender` | `filters.get("From", "")` |
| *(computed)* | `scrubber` | `templates.get("Main", "")` |
| *(computed)* | `match_mode` | `_match_mode(parsers)` |

### 5.3 Mapping: SftpJob → sftp_jobs table

| SftpJob field | SQLite column | Notes |
|---|---|---|
| `name` | `name` | UNIQUE |
| `path` | `path` | — |
| `servicer_id` | `servicer_id` | — |
| `dsn` | `dsn` | — |
| `sme` | `sme` | — |
| `save_location` | `save_location` | — |
| `skip_list` | `skip_list` | — |
| `ignore_list` | `ignore_list` | — |
| `parsers` | `parsers_json` | `json.dumps(parsers)` |
| `zip_content_filter` | `zip_content_filter` | — |
| `templates` | `templates_json` | `json.dumps(templates)` |
| `day_adjust` | `day_adjust` | Nullable |
| *(computed)* | `scrubber` | `templates.get("Main", "")` |
| *(computed)* | `match_mode` | `_match_mode(parsers)` |

---

## 6. CLI Command Changes

### 6.1 Modified Commands

#### `cmd_search_jobs` (current: lines 86–145)

**Current:** Calls `SettingsXmlParser(path).search_jobs(query)` for each XML file.  
**After:** Calls `XmlJobIndex(db_path).search_jobs(query, xml_type)`. Falls back to XML if SQLite doesn't exist.

```python
# BEFORE
parser = SettingsXmlParser(args.settings_path)
matched = parser.search_jobs(args.query)

# AFTER
index = _xml_index_from_args(args)
if index:
    result = index.search_jobs(args.query, args.xml_type)
    all_jobs_dicts = result  # already dicts
    index.close()
else:
    # Fallback: parse XML directly (backward compat)
    parser = SettingsXmlParser(args.settings_path)
    matched = parser.search_jobs(args.query)
    all_jobs_dicts = [j.to_summary_dict() for j in matched]
```

**Key constraint:** The JSON shape returned to the extension must be identical. The extension calls `backendCall('search_jobs', {...})` and expects `{jobs: [...], total_count: N, xml_type: "..."}`.

#### `cmd_job_detail` (current: lines 144–260)

**Current:** Loops `parser.get_all_jobs()` to find by name.  
**After:** Calls `XmlJobIndex(db_path).get_job(name)`. Falls back to XML if SQLite doesn't exist.

#### `cmd_create_job` (current: lines 566–580)

**Current:** Uses `JobCrudEngine` to write XML.  
**After:** Same, plus calls `_rebuild_sqlite(args)` after successful write.

#### `cmd_edit_job` (current: lines 583–596)

**Current:** Uses `JobCrudEngine` to write XML.  
**After:** Same, plus calls `_rebuild_sqlite(args)` after successful write.

### 6.2 New Commands

#### `cmd_rebuild_db`

```python
def cmd_rebuild_db(args: argparse.Namespace) -> CliResponse:
    """Rebuild SQLite cache from XML settings files."""
    response = CliResponse(success=True, command="rebuild_db")

    index = XmlJobIndex(args.cache_db_path)
    results = {}

    if args.xml_type in ("email", "all"):
        results["email"] = index.rebuild(args.settings_path, "email")

    if args.xml_type in ("sftp", "all"):
        sftp_path = getattr(args, "sftp_settings_path", None)
        if sftp_path:
            results["sftp"] = index.rebuild(sftp_path, "sftp")

    response.data = results
    index.close()
    return response
```

### 6.3 New CLI Helper

```python
def _xml_index_from_args(args) -> Optional[XmlJobIndex]:
    """Build an XmlJobIndex if a cache DB path is available."""
    db_path = getattr(args, "cache_db_path", None)
    if db_path and os.path.exists(db_path):
        return XmlJobIndex(db_path)
    return None

def _rebuild_sqlite(args) -> None:
    """Rebuild the SQLite cache after an XML write operation."""
    db_path = getattr(args, "cache_db_path", None)
    if not db_path:
        return
    index = XmlJobIndex(db_path)
    try:
        if args.xml_type in ("email", "all"):
            index.rebuild(args.settings_path, "email")
        if args.xml_type in ("sftp", "all"):
            sftp_path = getattr(args, "sftp_settings_path", None)
            if sftp_path:
                index.rebuild(sftp_path, "sftp")
    finally:
        index.close()
```

### 6.4 Argparse Changes

New global argument added to the argument parser:

```python
parser.add_argument(
    "--cache-db-path",
    default=None,
    help="Path to SQLite cache database for Settings.xml queries",
)
```

The `rebuild_db` subcommand:

```python
sub_rebuild = subparsers.add_parser("rebuild_db", help="Rebuild SQLite cache from XML")
sub_rebuild.add_argument("--cache-db-path", required=True, help="SQLite DB path")
sub_rebuild.set_defaults(func=cmd_rebuild_db)
```

---

## 7. Extension Impact Assessment

### 7.1 participant.js — No Changes

The extension communicates with the CLI via `backendCall()`. Since the JSON interface is identical, no handler changes are needed:

| Handler | Backend Call | Change? |
|---|---|---|
| `COMMAND_HANDLERS.jobs` | `search_jobs`, `job_detail` | No — same JSON shape |
| `COMMAND_HANDLERS.deals` | `deal_lookup` | No |
| `COMMAND_HANDLERS.logs` | `sync_logs`, `log_search`, `log_summary` | No |
| `COMMAND_HANDLERS.deploy` | `diff`, `rollback`, `save` | No |
| `COMMAND_HANDLERS.triage` | `triage_verify` | No |
| `COMMAND_HANDLERS.analyze` | `coverage_gaps`, `orphan_detection`, `collision_detection` | No |
| `COMMAND_HANDLERS.staging` | `staging_*` | No |

### 7.2 package.json — No Changes

No new slash commands. The `rebuild_db` is an internal operation triggered after CRUD — not exposed as a user-facing slash command.

### 7.3 tool.js — No Changes

No new tools. The existing `_ACCEPTS` list covers all commands.

### 7.4 Extension Settings

The extension settings in `package.json` may optionally add a `cacheDbPath` setting if we want the extension to pass `--cache-db-path` to every CLI invocation. This is a minor additive change:

```json
{
    "frpAgent.cacheDbPath": {
        "type": "string",
        "default": "",
        "description": "Path to SQLite cache database for Settings.xml queries"
    }
}
```

This setting is **required** for SQLite cache queries. The extension passes it as `--cache-db-path` to all CLI invocations that involve job search/detail. Similar to `frpAgent.logDbPath` for the log index.

---

## 8. Data Flow Diagrams

### 8.1 Search Jobs — Current vs Phase 6

**Current Flow:**
```
User → Extension → backendCall('search_jobs') → CLI → SettingsXmlParser.search_jobs()
  → parse XML from disk → iterate all jobs → matches_query() → return list
```

**Phase 6 Flow:**
```
User → Extension → backendCall('search_jobs') → CLI → XmlJobIndex.search_jobs()
  → SQLite SELECT with LIKE → return list (same JSON shape)
  → [optional: check_hash() → warn if stale]
```

### 8.2 Create Job — Current vs Phase 6

**Current Flow:**
```
User → Extension → backendCall('create_job') → CLI → JobCrudEngine.create_job()
  → write XML → return result
```

**Phase 6 Flow:**
```
User → Extension → backendCall('create_job') → CLI → JobCrudEngine.create_job()
  → write XML → _rebuild_sqlite() → return result
```

### 8.3 Rebuild DB — New Flow

```
User → CLI: frp xml rebuild-db → XmlJobIndex.rebuild()
  → SettingsXmlParser(email_path).get_all_jobs()
  → SettingsXmlParser(sftp_path).get_all_jobs()
  → DELETE FROM email_jobs; INSERT all
  → DELETE FROM sftp_jobs; INSERT all
  → compute_config_hash() → store in cache_metadata
  → return summary dict
```

### 8.4 Stale Detection — Passive Check

```
cmd_search_jobs() → XmlJobIndex.search_jobs()
  → ALSO: check_hash(xml_path) → compare stored vs current
  → If different: add warning to response.warnings
  → User sees: "Cache may be stale — run 'frp xml rebuild-db' to refresh"
  → Results still returned (not blocked)
```

---

## 9. Error Handling Strategy

### 9.1 SQLite Not Found

If the SQLite database doesn't exist:
- `_xml_index_from_args()` returns `None`
- CLI falls back to `SettingsXmlParser` (current behavior)
- An INFO-level log message is emitted
- User is not blocked

### 9.2 SQLite Stale

If the content hash doesn't match:
- Results are still returned from SQLite (stale is better than nothing)
- A warning is added to the response: `"Cache may be stale — config hash mismatch"`
- The extension can display this warning to the user

### 9.3 Rebuild Failure

If `rebuild()` throws:
- The error is caught in `_rebuild_sqlite()`
- A warning is logged but the CLI response for the original command succeeds
- The CRUD operation (create/edit) is not rolled back — XML was already written successfully

### 9.4 Concurrent Access

SQLite WAL mode supports concurrent readers with one writer. The FRP Agent is single-threaded per invocation, so this is sufficient. PowerShell never touches the SQLite file.

---

## 10. File Manifest

### WS-A: SQLite Cache (2 new files, 1 modified)

| # | File | Type | Est. Lines |
|---|---|---|---|
| 1 | `backend/db/xml_index.py` | New | ~250 |
| 2 | `tests/db/test_xml_index.py` | New | ~350 |
| 3 | `cli/main.py` | Modified | ~+60 (net) |

### WS-B: Framework Retrofit (20 new files, 1 rewritten)

| # | File | Type | Est. Lines |
|---|---|---|---|
| 4 | `.github/copilot-instructions.md` | Rewrite | ~120 |
| 5 | `AGENTS.md` | New | ~100 |
| 6 | `.github/agents/config.agent.md` | New | ~80 |
| 7 | `.github/agents/triage.agent.md` | New | ~60 |
| 8 | `.github/agents/intel.agent.md` | New | ~60 |
| 9 | `.github/agents/ops.agent.md` | New | ~60 |
| 10 | `.github/prompts/search-jobs.prompt.md` | New | ~30 |
| 11 | `.github/prompts/triage-email.prompt.md` | New | ~30 |
| 12 | `.github/prompts/staging-lookup.prompt.md` | New | ~30 |
| 13 | `.github/prompts/deploy-diff.prompt.md` | New | ~30 |
| 14 | `.github/prompts/health-check.prompt.md` | New | ~30 |
| 15 | `.github/prompts/deal-lookup.prompt.md` | New | ~30 |
| 16 | `backend.instructions.md` | New | ~40 |
| 17 | `extension.instructions.md` | New | ~40 |
| 18 | `cli.instructions.md` | New | ~30 |
| 19 | `skills/xml-config/SKILL.md` | New | ~80 |
| 20 | `skills/email-triage/SKILL.md` | New | ~60 |
| 21 | `skills/deal-intelligence/SKILL.md` | New | ~60 |
| 22 | `skills/log-forensics/SKILL.md` | New | ~60 |
| 23 | `skills/template-staging/SKILL.md` | New | ~60 |

**Grand Total:** ~22 new files, 2 modified files, ~1,350 estimated new lines
