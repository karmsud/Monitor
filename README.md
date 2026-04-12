# FRP AI Email Monitor — VS Code Chat Agent

A VS Code Chat Participant (`@frp`) that provides natural-language access to the File Reception Portal email/SFTP monitoring system.

## Architecture

```
┌─────────────────────────────────┐
│  VS Code Chat  (@frp)          │  JavaScript extension
│  /jobs  /deals  /logs          │  extension/
│  /deploy  /triage  /analyze    │
└────────────┬────────────────────┘
             │ subprocess (JSON on stdout)
┌────────────▼────────────────────┐
│  Python CLI Backend             │  cli/main.py  →  26 commands
│  xml · db · logs · intel ·      │  backend/
│  triage · analysis · backup     │
└─────────────────────────────────┘
```

**Three layers:**

1. **VS Code Extension** (`extension/`) — Chat participant with slash commands, LM API integration for Copilot-powered responses, debug/sync commands.
2. **Python CLI** (`cli/main.py`) — 26 subcommands emitting structured JSON. Invoked as a subprocess by the extension.
3. **Backend modules** (`backend/`) — XML parsing, database access, log indexing, intelligence analysis, email triage, and advanced analytics.

---

## Getting Started (Fresh Clone)

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ (for VS Code extension packaging) |
| VS Code | 1.95+ with GitHub Copilot |
| ODBC Drivers | [ODBC Driver 17 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server), [MySQL ODBC 9.x](https://dev.mysql.com/downloads/connector/odbc/) |

### 1. Clone and set up Python environment

```powershell
git clone <repo-url> FRP_Agent
cd FRP_Agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install all dependencies (runtime + build + test)
pip install -r requirements.txt
```

### 2. Configure secrets (git-ignored, never committed)

Copy the example files and fill in your credentials:

```powershell
# Database secrets
Copy-Item config\secrets_mssql.example.json  config\secrets_mssql.json
Copy-Item config\secrets_mysql.example.json  config\secrets_mysql.json

# MCP server config (optional — for MySQL MCP integration)
Copy-Item .vscode\mcp.example.json  .vscode\mcp.json

# MSSQL connection utility (optional)
Copy-Item mssql_connection\secrets.example.toml  mssql_connection\secrets2.toml
```

Edit each copied file with your actual credentials.

### 3. Provide Settings XML files (git-ignored)

The application operates on `Settings.ps1` XML configuration files. These contain production job definitions and are **not** included in the repository. Place them at:

- `Settings.ps1` — Email monitoring settings (root)
- `Email Settings/Settings.ps1` — Email settings (alternative location)
- `SFTP Settings/Settings.ps1` — SFTP monitoring settings

### 4. Install VS Code extension dependencies

```powershell
cd extension
npm install
cd ..
```

### 5. Verify setup — run tests

```powershell
python -m pytest tests/ -q
```

---

## Building

The build pipeline is fully automated via `scripts/build.ps1`. It creates a Python venv, installs dependencies, compiles the backend with PyInstaller, and packages the VS Code extension as a VSIX.

```powershell
# Full build (backend exe + VSIX)
.\scripts\build.ps1 -Version 1.2.3

# Full build + install into local VS Code
.\scripts\build.ps1 -Version 1.2.3 -Install

# Backend exe only (no VSIX)
.\scripts\build.ps1 -BackendOnly

# VSIX only (reuse existing exe)
.\scripts\build.ps1 -SkipBackend -Version 1.2.3

# Clean build artifacts first
.\scripts\build.ps1 -Clean -Version 1.2.3

# Skip pip install (venv already up to date)
.\scripts\build.ps1 -NoPip -Version 1.2.3
```

> **Tip:** Always bump the version when testing a rebuilt VSIX. Reusing the same version can leave VS Code running a stale copy.

### Build Outputs

| Artifact | Location |
|---|---|
| Backend executable | `extension/bin/win-x64/frp-backend/frp-backend.exe` |
| VSIX package | `dist/frp-agent-<version>.vsix` |

### Development (without building)

Press **F5** in VS Code to launch the Extension Development Host directly. The `launch.json` is pre-configured.

---

## CLI Commands (26 total)

### Phase 1 — Foundation

| Command | Description |
|---------|-------------|
| `search_jobs` | Search for jobs in Settings.xml by keyword, servicer, or mailbox |
| `validate_xml` | Validate a Settings.xml file for structural issues |
| `sync_logs` | Sync log files into the SQLite index |
| `servicer_dossier` | Build a servicer/job dossier |
| `list_backups` | List backup files for Settings.xml |
| `save_xml` | Re-save Settings.xml with a timestamped backup |
| `status` | System status and diagnostic information |

### Phase 2 — CRUD & Intelligence

| Command | Description |
|---------|-------------|
| `create_job` | Create a new job from an existing template |
| `edit_job` | Edit a field on an existing job (auto-backup) |
| `template_inventory` | Discover template patterns across jobs |
| `coverage_gaps` | Analyze coverage gaps vs. database records |
| `orphan_detection` | Detect orphaned jobs with no valid DB match |
| `collision_detection` | Detect ImportDID collisions between jobs |
| `xml_diff` | Diff current Settings.xml against its latest backup |
| `rollback_xml` | Rollback Settings.xml to a backup version |

### Phase 3 — Log Analytics & Email Triage

| Command | Description |
|---------|-------------|
| `log_deal_activity` | Query deal activity from the indexed log database |
| `log_did_failures` | Aggregate DID-mapping failures |
| `log_job_health` | Compute job health metrics |
| `log_daily_summary` | One-day operational summary |
| `triage_verify` | Verify a .msg file against existing jobs |
| `triage_match` | Match an email to existing jobs |
| `triage_new` | Analyze an email for new-job creation |

### Phase 4 — Advanced Analysis

| Command | Description |
|---------|-------------|
| `log_trends` | Timeline trend analysis |
| `log_performance` | Job performance benchmarking and ranking |
| `analyze_consolidation` | Job consolidation analysis (duplicate detection) |
| `analyze_impact` | Change impact simulation |
| `analyze_health` | Full system health check |

---

## Testing

```powershell
# Run all tests
python -m pytest tests/ -q

# Unit tests only
python -m pytest tests/ -q --ignore=tests/integration

# Integration tests only (end-to-end CLI via subprocess)
python -m pytest tests/integration/ -v

# With coverage
python -m pytest tests/ --cov=backend --cov=cli --cov-report=term-missing
```

### Test Structure

```
tests/
  analysis/      Phase 4 analysis module tests
  backup/        Backup manager tests
  cli/           CLI command handler tests
  db/            Database connection/repository tests
  fixtures/      XML, log, and .msg test fixtures
  intel/         Coverage, orphan, collision detection tests
  integration/   End-to-end CLI integration tests
  logs/          Log parser, indexer, analytics tests
  triage/        Email triage matcher/parser tests
  xml/           XML parser, writer, CRUD, diff, rollback tests
```

---

## Project Structure

```
FRP_Agent/
  backend/           Python backend modules
    analysis/        Trends, performance, consolidation, impact, health
    backup/          Backup manager
    common/          Shared config, errors, models
    db/              Database connections (MSSQL prod / MySQL dev)
    intel/           Coverage, orphans, collisions
    logs/            Log parser, indexer, analytics
    triage/          Email triage (matcher, msg_parser)
    xml/             XML parser, writer, CRUD, diff, rollback, templates
  cli/               CLI entry point (main.py)
  config/            Runtime configuration and secrets (git-ignored)
  docs/              Design documentation
  extension/         VS Code extension (JavaScript)
    chat/            Chat participant
    commands/        Status/sync commands
    copilot/         Tool definitions
    lib/             Python backend bridge
    test/            Extension tests
  packaging/         PyInstaller spec
  scripts/           Build pipeline (build.ps1)
  tests/             Python test suite
```

---

## Configuration

| Item | Path | Git-tracked? |
|---|---|---|
| MSSQL secrets | `config/secrets_mssql.json` | No (use `.example.json`) |
| MySQL secrets | `config/secrets_mysql.json` | No (use `.example.json`) |
| MCP server config | `.vscode/mcp.json` | No (use `.example.json`) |
| Email Settings XML | `Settings.ps1` | No |
| SFTP Settings XML | `SFTP Settings/Settings.ps1` | No |
| VS Code launch config | `.vscode/launch.json` | Yes |

---

## License

See [LICENSE.txt](LICENSE.txt).