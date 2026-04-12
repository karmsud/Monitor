# FRP Agent — VS Code Chat Agent Bootstrap

> **Purpose**: Drop this file as guidance for GitHub Copilot to scaffold the FRP Agent VSIX extension — a VS Code Chat Participant (`@frp`) that manages email and SFTP monitoring jobs, deal coverage, log analysis, and Settings.xml operations.
>
> **Usage**: `@workspace set up this project using the blueprint in docs/Phase1/VSCODE_CHAT_AGENT_BOOTSTRAP.md`
>
> **Origin**: Tailored from the GSF IR KTS Agentic System Bootstrap (1,910 lines, 20 sections). Only sections applicable to FRP Agent are included.

---

## Table of Contents

1. [Quick Start — What to Tell Copilot](#1-quick-start)
2. [Project Structure](#2-project-structure)
3. [Extension Architecture](#3-extension-architecture)
4. [Chat Participant Setup](#4-chat-participant-setup)
5. [Backend Bridge (Python ↔ JS)](#5-backend-bridge)
6. [LLM Generation via VS Code LM API](#6-llm-generation)
7. [Slash Commands & Mode Routing](#7-slash-commands)
8. [VS Code Native Features](#8-vscode-native-features)
9. [Conversation Memory](#9-conversation-memory)
10. [Unit & Integration Testing](#10-testing)
11. [Dev Environment & F5 Workflow](#11-dev-environment)
12. [VSIX Build & Packaging](#12-vsix-packaging)
13. [Settings & Configuration](#13-settings)
14. [Critical Gotchas](#14-gotchas)
15. [Checklist](#15-checklist)
16. [VS Code API Quick Reference](#16-api-reference)

### Sections NOT Included (Not Applicable to FRP Agent)

- **RAG Pipeline** — FRP Agent does not use vector search, embeddings, or document chunking. Data comes from structured XML parsing, SQL queries, and log file parsing.
- **Scoped Knowledge Spaces** — FRP Agent has a fixed domain (email + SFTP jobs). No folder-based namespace discovery.
- **Confidence Scoring & Gap Detection** — Not applicable; FRP returns deterministic data from structured sources, not probabilistic search results.
- **Golden Answer Test Harness** — FRP answers are data-driven (job lists, validation results, deal tables), not prose. Standard pytest + manual QA is sufficient.

---

## 1. Quick Start — What to Tell Copilot {#1-quick-start}

Copy-paste this prompt to bootstrap the FRP Agent project:

```
@workspace Using the blueprint in docs/Phase1/VSCODE_CHAT_AGENT_BOOTSTRAP.md, scaffold a
VS Code Chat Participant extension called "@frp" that:
1. Uses a Python backend for XML parsing, DB queries, and log indexing (CLI bridge, not HTTP)
2. Uses the VS Code LM API (Copilot models) for response formatting and natural language answers
3. Has a chat participant with slash commands: /jobs, /deals, /logs, /deploy, /triage, /analyze
4. Packages as a VSIX with PyInstaller-compiled backend
5. Supports F5 dev workflow with Extension Development Host

Domain: File Reception Portal — email/SFTP monitoring job management
Data Sources: Settings.xml (email + SFTP), tblExternalDIDRef (SQL), App Logs (text files), SQLite index
```

---

## 2. Project Structure {#2-project-structure}

```
FRP_Agent/
├── .vscode/
│   └── launch.json                # F5 Extension Dev Host config
├── backend/
│   ├── __init__.py
│   ├── xml/
│   │   ├── __init__.py
│   │   ├── parser.py              # Settings.xml read, search, validate
│   │   ├── writer.py              # Settings.xml write with backup
│   │   └── models.py              # EmailJob, SftpJob, ValidationResult
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py          # Factory: MySQL (dev) or MSSQL (prod)
│   │   ├── connection_mysql.py    # MySQL via pyodbc
│   │   ├── connection_mssql.py    # MSSQL via pyodbc
│   │   ├── queries.py             # SQL constants
│   │   └── deal_repo.py           # tblExternalDIDRef access layer
│   ├── logs/
│   │   ├── __init__.py
│   │   ├── parser.py              # Log file event extraction
│   │   ├── indexer.py             # SQLite CRUD & sync workflow
│   │   └── models.py              # LogEvent dataclass
│   ├── backup/
│   │   ├── __init__.py
│   │   └── manager.py             # Backup create, list, restore
│   └── common/
│       ├── __init__.py
│       ├── models.py              # CliResponse envelope
│       └── config.py              # Backend configuration
├── cli/
│   ├── __init__.py
│   └── main.py                    # CLI entry: python -m cli.main <command>
├── config/
│   ├── __init__.py
│   ├── settings.py                # FrpConfig dataclass
│   ├── secrets_mysql.json         # Gitignored — MySQL credentials
│   └── secrets_mssql.json         # Gitignored — MSSQL credentials
├── extension/
│   ├── package.json               # VSIX manifest
│   ├── extension.js               # activate/deactivate
│   ├── .vscodeignore              # Exclude dev files from VSIX
│   ├── chat/
│   │   └── participant.js         # @frp handler + LLM generation
│   ├── copilot/
│   │   └── tool.js                # Backend bridge: backendCall()
│   ├── lib/
│   │   └── frp_backend.js         # ExeRunner / VenvRunner + runCliJson()
│   ├── commands/
│   │   ├── sync.js                # Log sync command
│   │   └── status.js              # Status command
│   └── bin/                       # PyInstaller exe bundled here for VSIX
│       └── win-x64/
│           └── frp-backend/
│               └── frp-backend.exe
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── xml/
│   │   ├── test_models.py
│   │   ├── test_parser.py
│   │   ├── test_validator.py
│   │   └── test_writer.py
│   ├── db/
│   │   ├── test_connection.py
│   │   └── test_deal_repo.py
│   ├── logs/
│   │   ├── test_parser.py
│   │   └── test_indexer.py
│   ├── backup/
│   │   └── test_manager.py
│   ├── cli/
│   │   └── test_main.py
│   └── fixtures/
│       ├── email_settings_valid.xml
│       ├── sftp_settings_valid.xml
│       └── logs/
├── scripts/
│   ├── build_vsix.ps1             # Master build pipeline
│   └── build_backend.ps1          # PyInstaller compilation
├── packaging/
│   └── frp_backend.spec           # PyInstaller spec
├── docs/
│   ├── Phase1/                    # Foundation docs (this file lives here)
│   ├── Phase2/
│   ├── Phase3/
│   └── Phase4/
├── .gitignore
├── requirements.txt               # Python dependencies
├── pytest.ini
└── README.md
```

---

## 3. Extension Architecture {#3-extension-architecture}

### Core Principle

The VS Code extension is the **orchestrator**. The Python backend is the **data engine**. The Copilot LLM is the **response formatter**. Keep these three layers cleanly separated.

```
┌──────────────────────────────────────────────────────────┐
│  VS Code Extension (JavaScript)                          │
│                                                          │
│  extension.js           — Activation, command registry   │
│  chat/participant.js    — @frp handler, LLM generation   │
│  copilot/tool.js        — Backend CLI bridge             │
│  lib/frp_backend.js     — runCliJson() subprocess        │
│  commands/*.js           — One file per VS Code command   │
└──────────────────┬─────────────────┬─────────────────────┘
                   │ CLI (JSON on stdout)   │ vscode.lm API
                   ▼                        ▼
┌────────────────────────┐    ┌──────────────────────────────┐
│  Python Backend         │    │  Copilot LLM (GPT-4.1,       │
│  cli/main.py            │    │  Claude, etc.)                │
│  → search_jobs          │    │  → Format results as natural  │
│  → validate_xml         │    │    language for chat           │
│  → sync_logs            │    │  → Answer follow-up questions │
│  → servicer_dossier     │    │                               │
│  → list_backups         │    │                               │
│  → save_xml             │    │                               │
│  → status               │    │                               │
│  Returns JSON to stdout │    │                               │
└────────────────────────┘    └──────────────────────────────┘
```

### Data Flow (Single Query)

```
User types "@frp /jobs search rptent"
  → participant.js receives (request, stream, token)
  → Extracts command ("jobs") and prompt ("search rptent")
  → Parses subcommand: default action = search_jobs
  → Reads settings: frpAgent.outlookSettingsPath, frpAgent.prod
  → Calls tool.js: backendCall("search_jobs", { query: "rptent", settingsPath: "..." })
    → tool.js calls runCliJson(['search_jobs', '--query', 'rptent', '--settings-path', '...'])
      → Spawns: python -m cli.main search_jobs --query "rptent" --settings-path "..."
      → Backend: SettingsXmlParser → search_jobs() → EmailJob[].to_dict()
      → Returns JSON: { success: true, data: { jobs: [...], total_count: 5 } }
  → participant.js receives structured data
  → Selects LLM model (request.model → setting → auto-detect)
  → Builds prompt: SYSTEM_PROMPT + data context (job JSON) + user question
  → Sends to model.sendRequest() → streams response
  → Generates follow-up suggestions ("validate", "servicer 150")
```

### Key Difference from KTS

FRP Agent does **NO vector search or document chunking**. The backend returns:
- **Job lists** from XML parsing
- **Validation results** from XML validation
- **Deal tables** from SQL queries
- **Log events** from SQLite queries
- **Backup lists** from filesystem

The LLM's job is purely to **format and explain** this structured data in natural language.

---

## 4. Chat Participant Setup {#4-chat-participant-setup}

### package.json — Participant Declaration

```json
{
  "name": "frp-agent-extension",
  "displayName": "FRP Agent",
  "description": "VS Code Chat Agent for File Reception Portal — manage email/SFTP monitoring jobs, deal coverage, and application logs.",
  "version": "0.1.0",
  "publisher": "your-publisher-id",
  "engines": { "vscode": "^1.95.0" },
  "main": "./extension.js",
  "activationEvents": ["onStartupFinished"],
  "contributes": {
    "chatParticipants": [
      {
        "id": "frp-agent.assistant",
        "name": "frp",
        "fullName": "FRP Agent",
        "description": "Manage email and SFTP monitoring jobs, query deal coverage, analyze logs, and deploy Settings.xml changes.",
        "isSticky": true,
        "commands": [
          { "name": "jobs", "description": "Search, filter, and validate email/SFTP monitoring jobs" },
          { "name": "deals", "description": "Query deal coverage, servicer dossiers, and DID mappings" },
          { "name": "logs", "description": "Sync and query application logs" },
          { "name": "deploy", "description": "Save Settings.xml, manage backups, list restore points" },
          { "name": "triage", "description": "Triage incoming emails against job configurations (Phase 3)" },
          { "name": "analyze", "description": "Advanced analysis: trends, health checks, consolidation (Phase 4)" }
        ]
      }
    ],
    "commands": [
      { "command": "frp-agent.syncLogs", "title": "FRP Agent: Sync Logs" },
      { "command": "frp-agent.status", "title": "FRP Agent: Status" }
    ],
    "configuration": {
      "title": "FRP Agent",
      "properties": {
        "frpAgent.prod": {
          "type": "boolean",
          "default": false,
          "order": 1,
          "description": "Database mode. true = MSSQL production, false = MySQL local development."
        },
        "frpAgent.outlookSettingsPath": {
          "type": "string",
          "default": "",
          "order": 2,
          "description": "Absolute path to the email monitoring Settings.xml file."
        },
        "frpAgent.sftpSettingsPath": {
          "type": "string",
          "default": "",
          "order": 3,
          "description": "Absolute path to the SFTP monitoring Settings.xml file."
        },
        "frpAgent.emailLogFolder": {
          "type": "string",
          "default": "",
          "order": 4,
          "description": "Folder containing EmailMonitor log files."
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
          "description": "Months of log data to retain in the SQLite index."
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
          "enumDescriptions": [
            "Use your active Copilot model (recommended)",
            "GPT-4.1 — strongest reasoning, 1M context",
            "GPT-4o — balanced quality and speed",
            "GPT-4o Mini — fast and lightweight",
            "Claude Sonnet 4 — strong analysis"
          ],
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

### extension.js — Activation

```javascript
const vscode = require('vscode');
const { registerChatParticipant } = require('./chat/participant');
const { initBackendRunner } = require('./lib/frp_backend');

async function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('FRP Agent', { log: true });
  outputChannel.appendLine('[FRP] Activating...');

  const shared = {
    context,
    outputChannel,
    workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '',
  };

  // Initialize backend runner (venv or exe based on settings)
  await initBackendRunner(vscode, context, outputChannel);

  // Register chat participant
  registerChatParticipant(vscode, context, shared);

  // Register VS Code commands
  function register(command, handler) {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, async () => {
        try { await handler(shared); }
        catch (err) {
          outputChannel.appendLine(`[FRP] ${command} failed: ${err.message}`);
          vscode.window.showErrorMessage(`Command failed: ${err.message}`);
        }
      })
    );
  }

  register('frp-agent.syncLogs', require('./commands/sync'));
  register('frp-agent.status', require('./commands/status'));

  outputChannel.appendLine('[FRP] Activated successfully.');
}

function deactivate() {}
module.exports = { activate, deactivate };
```

---

## 5. Backend Bridge (Python ↔ JS) {#5-backend-bridge}

### Design Principle

The extension talks to Python via **CLI subprocess** (not HTTP):
- VSIX packaging with PyInstaller exe (no server to manage)
- Clean process lifecycle (spawn → JSON stdout → exit)
- Same CLI works for terminal debugging
- Dev mode: live Python venv. Prod mode: compiled exe.

### CLI Protocol

```
Extension → Backend:   python -m cli.main <command> [--arg value ...]
Backend  → Extension:  JSON on stdout, logs on stderr
```

### frp_backend.js — Runner Factory + CLI Bridge

```javascript
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let runner = null;

class ExeRunner {
  constructor(exePath) { this.exePath = exePath; }
  spawn(args, opts) { return spawn(this.exePath, args, opts); }
}

class VenvRunner {
  constructor(pythonPath, cliModule) {
    this.pythonPath = pythonPath;
    this.cliModule = cliModule;
  }
  spawn(args, opts) {
    return spawn(this.pythonPath, ['-m', this.cliModule, ...args], opts);
  }
}

async function initBackendRunner(vscode, context, outputChannel) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const mode = config.get('backendMode') || 'auto';

  if (mode === 'exe' || mode === 'auto') {
    const exePath = path.join(context.extensionPath, 'bin', 'win-x64',
                              'frp-backend', 'frp-backend.exe');
    if (fs.existsSync(exePath)) {
      runner = new ExeRunner(exePath);
      outputChannel.appendLine('[FRP] Using compiled backend (exe)');
      return;
    }
  }

  // Fallback to venv
  runner = new VenvRunner('python', 'cli.main');
  outputChannel.appendLine('[FRP] Using Python venv backend');
}

async function runCliJson(args, env = {}) {
  return new Promise((resolve, reject) => {
    const proc = runner.spawn(args, {
      env: { ...process.env, ...env },
      cwd: env.WORKSPACE_ROOT || process.cwd()
    });
    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', d => stdout += d.toString());
    proc.stderr.on('data', d => stderr += d.toString());

    proc.on('close', code => {
      if (code !== 0) {
        return reject(new Error(`Backend exited ${code}: ${stderr.slice(-500)}`));
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (err) {
        reject(new Error(`Invalid JSON from backend: ${err.message}\nOutput: ${stdout.slice(0, 200)}`));
      }
    });
  });
}

module.exports = { initBackendRunner, runCliJson };
```

### tool.js — High-Level Backend Bridge

```javascript
const { runCliJson } = require('../lib/frp_backend');
const vscode = require('vscode');

/**
 * Call a backend CLI command with settings auto-populated from VS Code config.
 *
 * @param {string} command - CLI command name (e.g., 'search_jobs', 'validate_xml')
 * @param {object} params - Command-specific parameters
 * @param {object} shared - Extension shared context
 * @returns {Promise<object>} Unwrapped response data from backend
 */
async function backendCall(command, params = {}, shared = {}) {
  const config = vscode.workspace.getConfiguration('frpAgent');

  // Build CLI args array
  const args = [command];

  // Auto-populate settings paths
  if (!params.settingsPath) {
    params.settingsPath = config.get('outlookSettingsPath') || '';
  }
  if (!params.sftpSettingsPath) {
    params.sftpSettingsPath = config.get('sftpSettingsPath') || '';
  }

  // Auto-populate DB mode
  if (!params.dbMode) {
    params.dbMode = config.get('prod') ? 'mssql' : 'mysql';
  }

  // Auto-populate log settings
  if (!params.logFolder && command === 'sync_logs') {
    params.logFolder = config.get('emailLogFolder') || '';
  }

  // Map params to CLI args: camelCase → --kebab-case
  const paramMap = {
    query: '--query',
    xmlType: '--xml-type',
    settingsPath: '--settings-path',
    sftpSettingsPath: '--sftp-settings-path',
    dbMode: '--db-mode',
    secretsPath: '--secrets-path',
    servicerId: '--servicer-id',
    jobName: '--job-name',
    logFolder: '--log-folder',
    logType: '--log-type',
    dbPath: '--db-path',
    retentionMonths: '--retention-months',
    logDbPath: '--log-db-path',
  };

  for (const [key, flag] of Object.entries(paramMap)) {
    if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
      args.push(flag, String(params[key]));
    }
  }

  const verbose = config.get('logLevel') === 'verbose';
  if (verbose && shared.outputChannel) {
    shared.outputChannel.appendLine(`[FRP] → ${command} ${args.slice(1).join(' ')}`);
  }

  const response = await runCliJson(args);

  if (verbose && shared.outputChannel) {
    shared.outputChannel.appendLine(`[FRP] ← ${command}: success=${response.success}, ${response.elapsed_ms}ms`);
  }

  if (!response.success) {
    throw new Error(response.errors?.join('; ') || 'Backend command failed');
  }

  return response.data;
}

module.exports = { backendCall };
```

### Python CLI Entry Point

See [03_TECHNICAL_DESIGN.md §9](03_TECHNICAL_DESIGN.md) for the full `cli/main.py` specification.

Commands:
- `search_jobs` — Search/filter jobs by query
- `validate_xml` — Validate Settings.xml structure
- `sync_logs` — Sync log files into SQLite index
- `servicer_dossier` — Generate servicer dossier report
- `list_backups` — List backup files
- `save_xml` — Save Settings.xml with backup
- `status` — Agent status information

---

## 6. LLM Generation via VS Code LM API {#6-llm-generation}

### Model Selection

```javascript
/**
 * Select a Copilot LLM model.
 * Priority: request.model → frpAgent.model setting → auto-detect
 */
async function selectModel(vscode, requestModel) {
  // 1. Honor user's chat model picker selection
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }

  // 2. Check extension setting
  const config = vscode.workspace.getConfiguration('frpAgent');
  const modelSetting = config.get('model') || 'auto';

  if (modelSetting !== 'auto' && vscode.lm?.selectChatModels) {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: modelSetting });
      if (models?.length) return models[0];
    } catch (_) {}
  }

  // 3. Auto-detect: try preferred families in order
  if (vscode.lm?.selectChatModels) {
    for (const family of ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini']) {
      try {
        const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family });
        if (models?.length) return models[0];
      } catch (_) {}
    }
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
      if (models?.length) return models[0];
    } catch (_) {}
  }

  return null;
}
```

### FRP System Prompt

```javascript
const SYSTEM_PROMPT = `You are FRP Agent — a precise operations assistant for the File Reception Portal.
You help manage email and SFTP monitoring jobs, analyze deal coverage, query application logs, and deploy Settings.xml changes.

Rules:
- Answer using ONLY the data provided in the context below.
- Format job listings as markdown tables with columns: Name, Mailbox/Path, ServicerID, Parsers, Templates.
- Format validation results with ❌ errors, ⚠️ warnings, and ℹ️ info icons.
- Format deal tables with DID, ImportDID, and CompanyID columns.
- For log summaries, show timestamps, job names, event counts, and error details.
- For backup lists, show filename, timestamp, and size.
- If the data doesn't contain an answer, say so explicitly.
- Never invent job configurations, deal mappings, or log events.
- Use professional, concise language appropriate for financial operations.
- When referencing ServicerID, note it maps to CompanyID in the database.`;
```

### Streaming Generation

```javascript
/**
 * Generate answer via LLM and stream into chat.
 *
 * CRITICAL: vscode.LanguageModelChatMessage has NO .System() method!
 * Embed system prompt in the User message.
 * 
 * @param {object} backendData - Structured data from backend (jobs, validation, etc.)
 * @param {string} query - User's original question
 */
async function generateAnswer(vscode, model, stream, token, query, backendData) {
  const dataContext = JSON.stringify(backendData, null, 2);

  const userMessage = [
    SYSTEM_PROMPT,
    '',
    '## Data from Backend',
    dataContext,
    '',
    '## User Question',
    query,
  ].join('\n');

  // ⚠️ User() only — NO System() method exists!
  const messages = [
    vscode.LanguageModelChatMessage.User(userMessage),
  ];

  try {
    const response = await model.sendRequest(messages, {}, token);
    for await (const chunk of response.text) {
      stream.markdown(chunk);
    }
    return true;
  } catch (err) {
    // Quota exceeded, network error, cancellation → fall back
    return false;
  }
}
```

### Fallback Pattern

```javascript
// In the chat handler — ALWAYS have a fallback
let generated = false;
if (backendData) {
  const model = await selectModel(vscode, request.model);
  if (model) {
    generated = await generateAnswer(vscode, model, stream, token, query, backendData);
  }
}

if (!generated) {
  // Fallback: format raw data as markdown (never leave user with nothing)
  stream.markdown(formatRawData(backendData));
}
```

### Raw Data Formatter (Fallback)

```javascript
function formatRawData(data) {
  if (!data) return 'No data returned from backend.';

  // Jobs list
  if (data.jobs) {
    const header = '| Name | Mailbox | ServicerID | Parsers |\n|------|---------|------------|---------|';
    const rows = data.jobs.map(j =>
      `| ${j.name} | ${j.mailbox || j.path || ''} | ${j.servicer_id || 'N/A'} | ${Object.keys(j.parsers || {}).join(', ')} |`
    );
    return `**Found ${data.total_count} jobs:**\n\n${header}\n${rows.join('\n')}`;
  }

  // Validation result
  if (data.valid !== undefined) {
    const lines = [];
    lines.push(data.valid ? '✅ **Validation passed**' : '❌ **Validation failed**');
    if (data.errors?.length) data.errors.forEach(e => lines.push(`❌ ${e}`));
    if (data.warnings?.length) data.warnings.forEach(w => lines.push(`⚠️ ${w}`));
    if (data.info?.length) data.info.forEach(i => lines.push(`ℹ️ ${i}`));
    return lines.join('\n');
  }

  // Default: pretty JSON
  return '```json\n' + JSON.stringify(data, null, 2) + '\n```';
}
```

---

## 7. Slash Commands & Mode Routing {#7-slash-commands}

### Command Dispatch

```javascript
// In the chat handler
const command = request.command || '';  // empty = free-form question
const prompt = request.prompt || '';

// Route to command handler
const COMMAND_HANDLERS = {
  'jobs': handleJobsCommand,
  'deals': handleDealsCommand,
  'logs': handleLogsCommand,
  'deploy': handleDeployCommand,
  'triage': handleTriageCommand,    // Phase 3 stub
  'analyze': handleAnalyzeCommand,  // Phase 4 stub
  '': handleFreeformQuestion,       // No slash command
};

const handler = COMMAND_HANDLERS[command] || handleFreeformQuestion;
await handler(vscode, request, context, stream, token, shared);
```

### Jobs Command Handler

```javascript
async function handleJobsCommand(vscode, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  // Subcommand detection
  if (/^validate\s*sftp$/i.test(prompt)) {
    stream.progress('Validating SFTP Settings.xml...');
    const data = await backendCall('validate_xml', { xmlType: 'sftp' }, shared);
    await generateOrFallback(vscode, request, stream, token, 'Validate SFTP settings', data);
    return { metadata: { followUps: [{ prompt: 'show all sftp jobs', command: 'jobs' }] } };
  }

  if (/^validate/i.test(prompt)) {
    stream.progress('Validating email Settings.xml...');
    const data = await backendCall('validate_xml', { xmlType: 'email' }, shared);
    await generateOrFallback(vscode, request, stream, token, 'Validate email settings', data);
    return { metadata: { followUps: [{ prompt: 'validate sftp', command: 'jobs' }] } };
  }

  // Default: search
  const query = prompt.replace(/^search\s*/i, '') || 'all';
  stream.progress('Searching jobs...');
  const data = await backendCall('search_jobs', { query }, shared);
  await generateOrFallback(vscode, request, stream, token, `Search jobs: ${query}`, data);

  // Dynamic follow-ups
  const followUps = [{ prompt: 'validate', command: 'jobs' }];
  if (data?.jobs?.length) {
    const firstWithServicer = data.jobs.find(j => j.servicer_id);
    if (firstWithServicer) {
      followUps.push({
        prompt: `servicer ${firstWithServicer.servicer_id}`,
        command: 'deals',
      });
    }
  }
  return { metadata: { followUps } };
}
```

### Deploy Command Handler

```javascript
async function handleDeployCommand(vscode, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  if (/^save\s+email$/i.test(prompt)) {
    stream.progress('Saving email Settings.xml...');
    const data = await backendCall('save_xml', { xmlType: 'email' }, shared);
    await generateOrFallback(vscode, request, stream, token, 'Save email settings', data);
    return { metadata: { followUps: [{ prompt: 'backups', command: 'deploy' }] } };
  }

  if (/^save\s+sftp$/i.test(prompt)) {
    stream.progress('Saving SFTP Settings.xml...');
    const data = await backendCall('save_xml', { xmlType: 'sftp' }, shared);
    await generateOrFallback(vscode, request, stream, token, 'Save SFTP settings', data);
    return { metadata: { followUps: [{ prompt: 'backups sftp', command: 'deploy' }] } };
  }

  if (/^backups?\s*sftp$/i.test(prompt)) {
    stream.progress('Listing SFTP backups...');
    const data = await backendCall('list_backups', { xmlType: 'sftp' }, shared);
    await generateOrFallback(vscode, request, stream, token, 'SFTP backup list', data);
    return {};
  }

  // Default: list email backups
  stream.progress('Listing email backups...');
  const data = await backendCall('list_backups', { xmlType: 'email' }, shared);
  await generateOrFallback(vscode, request, stream, token, 'Email backup list', data);
  return { metadata: { followUps: [{ prompt: 'save email', command: 'deploy' }] } };
}
```

### Phase Stubs

```javascript
async function handleTriageCommand(vscode, request, context, stream, token, shared) {
  stream.markdown('📬 **Email Triage** is coming in **Phase 3**.\n\n' +
    'This will include:\n' +
    '- E-01: Verify which job would pick up an email\n' +
    '- E-02: Match .msg files against job filters\n' +
    '- E-03: Identify emails with no matching job\n');
  return {};
}

async function handleAnalyzeCommand(vscode, request, context, stream, token, shared) {
  stream.markdown('📊 **Advanced Analysis** is coming in **Phase 4**.\n\n' +
    'This will include:\n' +
    '- A-01: Job consolidation analysis\n' +
    '- A-02: Change impact simulation\n' +
    '- A-03: Full health check\n');
  return {};
}
```

---

## 8. VS Code Native Features {#8-vscode-native-features}

### 8.1 Follow-Up Suggestions (Deterministic, Zero LLM Cost)

```javascript
// Follow-ups are generated based on what command was just run
// and what data was returned — no LLM call needed.

const participant = vscode.chat.createChatParticipant('frp-agent.assistant', handler);
participant.followupProvider = {
  provideFollowups(result, context, token) {
    return (result.metadata?.followUps || []).map(f => ({
      prompt: f.prompt,
      command: f.command,
      label: f.prompt,
    }));
  },
};
```

### FRP Follow-Up Patterns

| After Command | Suggested Follow-Ups |
|---------------|---------------------|
| `/jobs search X` | "validate", "servicer {ID}" |
| `/jobs validate` | "validate sftp", "search {first_error_job}" |
| `/deals servicer N` | "validate", "show logs for {job_name}" |
| `/logs sync` | "what happened today?", "any errors?" |
| `/deploy backups` | "save email", "save sftp" |
| `/deploy save email` | "backups" |

### 8.2 Progress Streaming

```javascript
// Show progress during backend calls
stream.progress('Searching jobs...');
const data = await backendCall('search_jobs', params, shared);
stream.progress('Generating response...');
await generateAnswer(vscode, model, stream, token, query, data);
```

### 8.3 Confirmation for Destructive Operations

```javascript
// Before saving Settings.xml (creates backup but modifies files)
if (command === 'save_xml') {
  const choice = await vscode.window.showWarningMessage(
    `Save ${xmlType} Settings.xml? A backup will be created automatically.`,
    { modal: true },
    'Save', 'Cancel'
  );
  if (choice !== 'Save') {
    stream.markdown('Save cancelled.');
    return {};
  }
}
```

---

## 9. Conversation Memory {#9-conversation-memory}

### Design Principle

"VS Code IS the session store." Read `context.history` — don't replicate it. Backend stays stateless.

### History Extraction for FRP

```javascript
function buildConversationContext(context) {
  const turns = [];
  const maxTurns = 6;  // Keep last 6 turns for FRP

  if (!context?.history?.length) return [];

  const history = context.history.slice(-maxTurns);
  for (const turn of history) {
    if (turn instanceof vscode.ChatRequestTurn) {
      turns.push({ role: 'user', content: turn.prompt });
    } else if (turn instanceof vscode.ChatResponseTurn) {
      let text = '';
      for (const part of turn.response) {
        if (part instanceof vscode.ChatResponseMarkdownPart) {
          text += part.value.value;
        }
      }
      if (text) turns.push({ role: 'assistant', content: text.slice(0, 500) });
    }
  }

  return turns;
}
```

### When to Use History

FRP Agent uses conversation history for:
1. **Freeform follow-ups** — "what about the SFTP one?" after showing email jobs
2. **Pronoun resolution** — "validate it" after showing a specific settings file

The backend does NOT need history; all context is resolved in the extension layer.

---

## 10. Unit & Integration Testing {#10-testing}

### Python Backend Tests

See [05_TESTING_PLAN.md](05_TESTING_PLAN.md) for the complete test matrix (162 automated + 16 manual tests).

Key testing approach:
- **pytest** for all Python backend modules
- **Mock pyodbc** for database tests (no real DB required for CI)
- **tmp_path fixtures** for XML write/backup tests
- **Real log files** as test fixtures for log parser tests
- **100% coverage** target for data models

### Mock VS Code for Node.js Tests (Optional)

```javascript
// tests/test_helpers.js
function createMockVscode({ modelAvailable = true } = {}) {
  const streamedOutput = [];

  const mockModel = {
    id: 'gpt-4o-test',
    family: 'gpt-4o',
    maxInputTokens: 128000,
    sendRequest: async (messages, opts, token) => ({
      text: (async function* () {
        yield 'Mock response for testing.';
      })(),
    }),
  };

  return {
    vscode: {
      lm: {
        selectChatModels: async () => modelAvailable ? [mockModel] : [],
      },
      chat: {
        createChatParticipant: (id, handler) => ({
          id, handler, dispose: () => {},
          followupProvider: null,
        }),
      },
      LanguageModelChatMessage: {
        User: (text) => ({ role: 'user', content: text }),
        Assistant: (text) => ({ role: 'assistant', content: text }),
      },
      CancellationTokenSource: class {
        constructor() { this.token = { isCancellationRequested: false }; }
      },
      workspace: {
        getConfiguration: () => ({
          get: (key) => ({
            prod: false,
            outlookSettingsPath: '',
            model: 'auto',
            logLevel: 'normal',
            backendMode: 'venv',
          }[key]),
        }),
      },
    },
    mockModel,
    streamedOutput,
    stream: {
      markdown: (text) => streamedOutput.push(text),
      progress: () => {},
      reference: () => {},
    },
    token: { isCancellationRequested: false },
  };
}
```

---

## 11. Dev Environment & F5 Workflow {#11-dev-environment}

### launch.json

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FRP Agent — Extension Dev Host",
      "type": "extensionHost",
      "request": "launch",
      "args": [
        "--extensionDevelopmentPath=${workspaceFolder}/FRP_Agent/extension"
      ],
      "outFiles": [],
      "preLaunchTask": null
    }
  ]
}
```

### Dev Workflow

1. Set `frpAgent.backendMode` to `"venv"` in VS Code settings
2. Configure `frpAgent.outlookSettingsPath` pointing to your real Settings.xml
3. Press `F5` → Extension Development Host opens
4. Type `@frp /jobs search rptent` in Copilot Chat
5. Edit `participant.js` → save → `Ctrl+R` in Dev Host to reload
6. **Edit-test cycle: < 5 seconds** (no VSIX rebuild needed)

### Backend Dev Mode

```powershell
# Terminal testing (bypass extension):
cd FRP_Agent
python -m cli.main search_jobs --query "rptent" --settings-path "path/to/Settings.xml"
python -m cli.main validate_xml --settings-path "path/to/Settings.xml"
python -m cli.main sync_logs --log-folder "path/to/logs" --db-path "frp_logs.db"
python -m cli.main status
```

---

## 12. VSIX Build & Packaging {#12-vsix-packaging}

### Build Pipeline (PowerShell)

```powershell
# scripts/build_vsix.ps1
param(
    [string]$Version = "0.1.0",
    [switch]$SkipBackend,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

# Step 1: Clean (optional)
if ($Clean) {
    Remove-Item -Recurse -Force extension/bin -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
}

# Step 2: Build Python backend with PyInstaller
if (-not $SkipBackend) {
    Write-Host "[BUILD] Compiling Python backend..." -ForegroundColor Cyan
    Push-Location .
    pyinstaller packaging/frp_backend.spec --distpath extension/bin/win-x64 --clean -y
    Pop-Location
}

# Step 3: Update package.json version
$pkg = Get-Content extension/package.json | ConvertFrom-Json
$pkg.version = $Version
$pkg | ConvertTo-Json -Depth 10 | Set-Content extension/package.json

# Step 4: Package VSIX
Write-Host "[BUILD] Packaging VSIX..." -ForegroundColor Cyan
Push-Location extension
npx @vscode/vsce package --no-dependencies -o "../dist/frp-agent-$Version.vsix"
Pop-Location

Write-Host "[BUILD] Done! VSIX at: dist/frp-agent-$Version.vsix" -ForegroundColor Green
```

### PyInstaller Spec

```python
# packaging/frp_backend.spec
a = Analysis(
    ['../cli/main.py'],
    pathex=['..'],
    datas=[
        ('../config', 'config'),
    ],
    hiddenimports=[
        'backend.xml.parser',
        'backend.xml.writer',
        'backend.db.connection',
        'backend.db.connection_mysql',
        'backend.db.connection_mssql',
        'backend.db.deal_repo',
        'backend.logs.parser',
        'backend.logs.indexer',
        'backend.backup.manager',
        'pyodbc',
    ],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], name='frp-backend', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='frp-backend')
```

### .vscodeignore

```
.vscode/**
tests/**
docs/**
scripts/**
packaging/**
backend/**
cli/**
config/**
*.py
*.spec
.gitignore
.git/**
__pycache__/**
*.pyc
node_modules/**
*.md
!README.md
```

---

## 13. Settings & Configuration {#13-settings}

### FRP Agent Settings Summary

| Setting | Type | Default | Purpose |
|---------|------|---------|---------|
| `frpAgent.prod` | boolean | false | DB mode: MSSQL (true) vs MySQL (false) |
| `frpAgent.outlookSettingsPath` | string | "" | Email Settings.xml path |
| `frpAgent.sftpSettingsPath` | string | "" | SFTP Settings.xml path |
| `frpAgent.emailLogFolder` | string | "" | Email log files directory |
| `frpAgent.sftpLogFolder` | string | "" | SFTP log files directory |
| `frpAgent.logRetentionMonths` | number | 3 | SQLite retention months |
| `frpAgent.logLevel` | enum | "normal" | Output panel detail |
| `frpAgent.model` | enum | "auto" | LLM for response generation |
| `frpAgent.backendMode` | enum | "auto" | **[Developer]** Backend mode |

### Design Notes

- 8 user-facing settings (more than the KTS "3 settings" rule because FRP has more external dependencies: 2 XML files, 2 log folders, DB mode, retention)
- 1 developer-only setting at order 100 (backendMode)
- All external paths are absolute — no workspace-relative assumptions
- `frpAgent.prod` is the most important setting: it controls which database the agent connects to

---

## 14. Critical Gotchas {#14-gotchas}

### Gotcha 1: `LanguageModelChatMessage.System is not a function`

```javascript
// ❌ CRASHES
vscode.LanguageModelChatMessage.System(SYSTEM_PROMPT)

// ✅ Embed system prompt in User message
vscode.LanguageModelChatMessage.User(SYSTEM_PROMPT + '\n---\n' + data + '\n' + query)
```

### Gotcha 2: `request.model` Ignored

```javascript
// ❌ Always picks first available
async function selectModel() {
  const models = await vscode.lm.selectChatModels({ family: 'gpt-4o' });
  return models[0];
}

// ✅ Check request.model first
async function selectModel(vscode, requestModel) {
  if (requestModel?.sendRequest) return requestModel;
  // ... fallback chain
}
```

### Gotcha 3: Backend Returns JSON on stdout — Logs Go to stderr

```python
# ❌ print() goes to stdout and corrupts JSON
print("Debugging...")
json.dump(response.to_dict(), sys.stdout)

# ✅ All logging to stderr
logging.basicConfig(stream=sys.stderr)
logger.info("Debugging...")
json.dump(response.to_dict(), sys.stdout)
```

### Gotcha 4: XML Field Names Are Case-Sensitive

```python
# ❌ Wrong casing
element.find('servicerid')  # Returns None

# ✅ Match exact XML casing
element.find('ServicerID')
```

### Gotcha 5: Streaming Requires `for await...of`

```javascript
// ❌ Gets nothing
const answer = response.text;

// ✅ Iterate the stream
for await (const chunk of response.text) {
  stream.markdown(chunk);
}
```

### Gotcha 6: `selectChatModels()` Returns Empty Outside Extension Host

Always mock the `vscode` object in tests. The `vscode.lm` API only works inside a running VS Code extension host.

### Gotcha 7: pyodbc Connection Strings Need Braces Around Driver Names

```python
# ❌ Missing braces
f"DRIVER=MySQL ODBC 8.0 Unicode Driver;..."

# ✅ Driver name in braces
f"DRIVER={{MySQL ODBC 8.0 Unicode Driver}};..."
```

---

## 15. Checklist {#15-checklist}

### Setup
- [ ] Project structure matches §2
- [ ] `package.json` with `chatParticipants`, `commands`, `configuration`
- [ ] `engines.vscode: "^1.95.0"`
- [ ] `activationEvents: ["onStartupFinished"]`
- [ ] `.vscode/launch.json` for F5 Extension Dev Host
- [ ] `.vscodeignore` to exclude dev files
- [ ] `.gitignore` with secrets, __pycache__, .venv, frp_logs.db

### Chat Participant
- [ ] `vscode.chat.createChatParticipant('frp-agent.assistant', handler)`
- [ ] Handler receives `(request, context, stream, token)`
- [ ] Slash command dispatch: /jobs, /deals, /logs, /deploy, /triage (stub), /analyze (stub)
- [ ] Subcommand parsing within each slash command
- [ ] `followupProvider` for suggestion chips

### Backend Bridge
- [ ] CLI: `python -m cli.main <command> [args] → JSON stdout`
- [ ] `runCliJson()` spawns subprocess, parses JSON
- [ ] `BackendRunnerFactory`: ExeRunner (prod) vs VenvRunner (dev)
- [ ] `backendCall()` auto-populates settings from VS Code config
- [ ] All params mapped: camelCase → --kebab-case

### LLM Generation
- [ ] `selectModel()`: request.model → setting → auto-detect
- [ ] FRP system prompt with domain rules and formatting instructions
- [ ] Message: `LanguageModelChatMessage.User()` only — NO `.System()`
- [ ] Streaming: `for await (chunk of response.text) { stream.markdown(chunk) }`
- [ ] Fallback: if LLM unavailable → raw data as formatted markdown

### Python Backend
- [ ] CliResponse envelope for all commands
- [ ] XML parser: email + SFTP auto-detection
- [ ] XML validator: E001–E013 errors, W001–W005 warnings, I001–I006 info
- [ ] XML writer: backup before save, verify after write
- [ ] DB connector: factory pattern (MySQL/MSSQL)
- [ ] Deal repository: servicer lookup, deal search
- [ ] Log parser: event extraction from monitor logs
- [ ] SQLite indexer: sync, query, retention purge
- [ ] Backup manager: list, restore, count
- [ ] All logging to stderr (stdout = JSON only)

### Testing
- [ ] pytest suite: 162+ automated tests
- [ ] Manual F5 QA: 16 test scenarios
- [ ] Coverage target: 93%+
- [ ] Test fixtures for both XML formats and log files

### Packaging
- [ ] `scripts/build_vsix.ps1` pipeline
- [ ] PyInstaller spec for frp-backend.exe
- [ ] VSIX contains exe + extension files only

---

## 16. VS Code API Quick Reference {#16-api-reference}

```javascript
// ─── Chat Participant ─────────────────────────────────
const participant = vscode.chat.createChatParticipant('frp-agent.assistant', handler);
participant.isSticky = true;
participant.followupProvider = { provideFollowups(result, ctx, token) { ... } };

// Handler signature:
async function handler(request, context, stream, token) {
  request.prompt;       // User's message text
  request.command;      // Slash command: 'jobs', 'deals', 'logs', 'deploy', etc.
  request.model;        // User's selected LLM model
  request.references;   // #file, #selection, #editor references
  context.history;      // Array of ChatRequestTurn / ChatResponseTurn

  stream.markdown(text);              // Render markdown
  stream.progress(msg);               // Show progress indicator
  stream.reference(uri);              // Clickable file citation

  return { metadata: { followUps: [...] } };
}

// ─── Language Model API ───────────────────────────────
const models = await vscode.lm.selectChatModels({ vendor: 'copilot', family: 'gpt-4.1' });
const model = models[0];

model.maxInputTokens;   // e.g., 1000000

const message = vscode.LanguageModelChatMessage.User('prompt text');
// ⚠️ NO .System() method. Only .User() and .Assistant().

const response = await model.sendRequest([message], {}, cancellationToken);
for await (const chunk of response.text) {
  stream.markdown(chunk);
}

// ─── Configuration ────────────────────────────────────
const config = vscode.workspace.getConfiguration('frpAgent');
const isProd = config.get('prod');
const settingsPath = config.get('outlookSettingsPath');

// ─── Commands ─────────────────────────────────────────
vscode.commands.registerCommand('frp-agent.syncLogs', async () => { ... });

// ─── UI ───────────────────────────────────────────────
const channel = vscode.window.createOutputChannel('FRP Agent', { log: true });
channel.appendLine('[FRP] Message');
channel.show(true);

await vscode.window.showWarningMessage('Save Settings.xml?', { modal: true }, 'Save', 'Cancel');
```

---

*Bootstrap version: 1.0.0*  
*Tailored from: GSF IR KTS Agentic System Bootstrap Template*  
*Last updated: February 24, 2026*
