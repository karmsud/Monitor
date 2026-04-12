# Phase 7: System Design
## FRP Agent — Two-Stage Intent Routing Architecture

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [01_EXECUTIVE_SUMMARY.md](01_EXECUTIVE_SUMMARY.md)

---

## Table of Contents
1. [Module Map](#1-module-map)  
2. [Intent Categories](#2-intent-categories)  
3. [Category-to-Tool Assignments](#3-category-to-tool-assignments)  
4. [Two-Stage Routing Flow](#4-two-stage-routing-flow)  
5. [Stage 1: Intent Classifier Design](#5-stage-1-intent-classifier-design)  
6. [Stage 2: Category-Scoped Tool Router Design](#6-stage-2-category-scoped-tool-router-design)  
7. [Fallback Strategy](#7-fallback-strategy)  
8. [Conversation History Handling](#8-conversation-history-handling)  
9. [Logging and Diagnostics](#9-logging-and-diagnostics)  
10. [Data Flow Diagrams](#10-data-flow-diagrams)  
11. [Error Handling Strategy](#11-error-handling-strategy)  
12. [File Manifest](#12-file-manifest)

---

## 1. Module Map

### Modified Files

| File | Change |
|---|---|
| `extension/chat/participant.js` | Add `INTENT_CATEGORIES` constant, `CATEGORY_TOOLS` lookup, `classifyIntent()` function, `routeWithinCategory()` function. Modify `routeWithToolCalling()` to use two-stage routing. Remove regex pre-routing. Clean tool descriptions. Simplify `DOMAIN_KNOWLEDGE`. |

### New Code Elements (All Within `participant.js`)

| Element | Type | Purpose |
|---|---|---|
| `INTENT_CATEGORIES` | `const Array<Object>` | 6 category definitions — each has `name`, `description`, `dataLayer`, `examples` |
| `CATEGORY_TOOLS` | `const Object` | Maps category name → array of tool names belonging to that category |
| `classifyIntent(prompt, history, model, token, shared)` | `async function` | Stage 1: sends category definitions + prompt to LLM, returns category name string |
| `routeWithinCategory(category, prompt, request, context, stream, token, shared)` | `async function` | Stage 2: filters `FRP_TOOLS` to category subset, sends to LLM with tool-calling, returns `executeToolCall()` result |
| `buildClassifierPrompt(prompt, history)` | `function` | Builds the Stage 1 prompt string from categories + user prompt + history |

### Removed Code Elements

| Element | Type | Reason |
|---|---|---|
| `dealIntentRe` | `const RegExp` | Regex band-aid; replaced by Stage 1 classification |
| `dealIntent2` | `const RegExp` | Second regex band-aid |
| `if (dealMatch) { ... }` block | Code block in `routeWithToolCalling()` | Pre-routing bypass; replaced by Stage 1 |
| Decision tree (points 1–14) | Text in `DOMAIN_KNOWLEDGE` | Routing instructions that didn't work; replaced by category definitions |

### Untouched Files (Confirmed)

| File | Why Untouched |
|---|---|
| `extension/copilot/tool.js` | `backendCall()` interface unchanged |
| `extension/package.json` | No new settings needed |
| `extension/extension.js` | Extension activation unchanged |
| `cli/main.py` | All CLI commands unchanged |
| `backend/**` | All Python modules unchanged |
| `tests/**` | All 697 tests unchanged |
| `scripts/build.ps1` | Build process unchanged |
| `config/**` | Settings files unchanged |

---

## 2. Intent Categories

Each category represents a **distinct data layer or operational concern** within the FRP system. The boundaries are based on **which data source answers the question**, not on keywords in the user's prompt.

### Category 1: `deal_mapping`

| Property | Value |
|---|---|
| **Display Name** | Deal & Reference Mapping |
| **Data Layer** | `tblExternalDIDRef` (MySQL) + cross-references to Settings.xml |
| **Handles** | Questions about deals, DIDs, ImportDID keywords, CompanyID/ServicerID lookups, deal-to-job reverse mapping, coverage gaps, orphan detection, import collisions |
| **Key Signal** | User provides or asks about a deal name, DID, ImportDID keyword, or CompanyID — OR asks "which jobs serve deal X" (answer comes from cross-referencing tblExternalDIDRef → Settings.xml, not from searching Settings.xml) |
| **Tool Count** | 5 |

**Why this boundary:** The tblExternalDIDRef table is the authority on deal-to-job relationships. Any question that starts from a deal name, DID, or CompanyID and asks about related entities (jobs, keywords, coverage) is answered by querying this table and cross-referencing. This is distinct from `job_config`, which searches Settings.xml by job attributes.

**Critical disambiguation:** "Any jobs for deal DID = X" belongs here, NOT in `job_config`. The answer starts from tblExternalDIDRef (find CompanyID for the DID), then cross-references to Settings.xml (find jobs with that ServicerID). The primary data source is the deal table.

### Category 2: `job_config`

| Property | Value |
|---|---|
| **Display Name** | Job Configuration |
| **Data Layer** | Settings.xml (email + SFTP job definitions) via SQLite cache |
| **Handles** | Searching/listing/filtering jobs by job attributes (name, scrubber, sender, type), getting detailed config for a specific job, validating XML configs, viewing template inventory, creating new jobs, editing existing jobs |
| **Key Signal** | User asks to search/list/browse jobs by attributes (not by deal name), asks for details of a specific named job, asks about job validation, or wants to create/edit a job |
| **Tool Count** | 7 |

**Why this boundary:** Settings.xml is the authority on job definitions. Any question about job configurations, validation, or CRUD operations starts and ends in this data layer.

**Critical disambiguation:** "Show me the details for job CMBS_GreyCo" belongs here (starting from a job name). But "which jobs serve deal CMLTI 2014-A" belongs in `deal_mapping` (starting from a deal name, cross-referencing to jobs).

### Category 3: `processing`

| Property | Value |
|---|---|
| **Display Name** | Processing & Execution History |
| **Data Layer** | `tblTemplateStaging` (MySQL) |
| **Handles** | Template processing status, processing history, failure analysis, file source tracing, manual vs automated queue analysis, processing duration/performance, end-to-end pipeline views, staging record searches |
| **Key Signal** | User asks about processing runs, execution status, failures, file tracing, queue analysis, duration, "has X been processed", "what's failing", "pipeline view" |
| **Tool Count** | 8 |

**Why this boundary:** tblTemplateStaging is the authority on what has actually been processed. Any question about execution history, success/failure, timing, or file lifecycle belongs here.

### Category 4: `logs_ops`

| Property | Value |
|---|---|
| **Display Name** | Application Logs & Operations |
| **Data Layer** | Application log files (EmailMonitor.log, SFTP logs) indexed in SQLite |
| **Handles** | Log sync/indexing, daily operation summaries, DID lookup failures from logs, job health metrics from logs, deal activity from logs, processing trends over time, performance rankings |
| **Key Signal** | User asks about daily operations, log entries, DID failures in logs, job health from a log perspective, trends, or performance rankings |
| **Tool Count** | 7 |

**Why this boundary:** Application logs are a distinct data source from tblTemplateStaging (which tracks structured processing records). Logs contain raw operational events — email processing attempts, attachment downloads, DID lookup failures — that are indexed differently.

**Distinguishing from `processing`:** `processing` answers "was file X processed successfully in tblTemplateStaging?" while `logs_ops` answers "what happened in the EmailMonitor log when job Y ran today?"

### Category 5: `deployment`

| Property | Value |
|---|---|
| **Display Name** | Deployment & Configuration Management |
| **Data Layer** | Settings.xml backup/deploy/rollback system |
| **Handles** | Saving/deploying Settings.xml, listing backup restore points, showing XML diff since last deploy, rolling back to a previous version |
| **Key Signal** | User says "save", "deploy", "backup", "restore", "rollback", "diff", "what changed" |
| **Tool Count** | 4 |

**Why this boundary:** Deployment operations are destructive/stateful — they modify the live Settings.xml file. They form a distinct workflow (save → verify → rollback if needed) that is separate from read-only queries.

### Category 6: `system_admin`

| Property | Value |
|---|---|
| **Display Name** | System Administration & Analysis |
| **Data Layer** | Cross-cutting — reads from multiple data layers |
| **Handles** | Email triage (is this email monitored?), consolidation analysis (which jobs can merge?), impact analysis ("what if" scenarios), full system health checks, agent status |
| **Key Signal** | User asks about triage, consolidation, impact analysis, system health, or agent status |
| **Tool Count** | 5 |

**Why this boundary:** These tools read from multiple data layers and perform analytical or administrative functions. They don't map cleanly to a single table but provide cross-cutting insights.

---

## 3. Category-to-Tool Assignments

Every tool in `FRP_TOOLS` is assigned to exactly one category. This is the **authoritative mapping** — no tool appears in multiple categories.

### deal_mapping (5 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `deal_lookup` | Reverse lookup: DID/CompanyID → deals + linked jobs | Primary tool for deal-layer queries |
| `servicer_dossier` | Comprehensive dossier for a servicer — jobs, deals, coverage | Starts from servicer/deal layer, aggregates across tables |
| `coverage_gaps` | ServicerIDs without deals, or CompanyIDs without jobs | Detects gaps in tblExternalDIDRef ↔ Settings.xml alignment |
| `orphan_detection` | Jobs with ServicerIDs not in tblExternalDIDRef | Detects jobs with no deal mapping — deal-layer integrity |
| `collision_detection` | ImportDID keywords duplicated across CompanyIDs | Detects ambiguity in tblExternalDIDRef data |

### job_config (7 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `search_jobs` | Search/list/filter jobs by attributes (name, scrubber, sender) | Primary tool for job-layer queries |
| `job_detail` | Full config for one job + linked deals + keywords | Returns a single job's complete configuration from Settings.xml |
| `validate_email` | Validate email Settings.xml structure | Configuration validation — Settings.xml domain |
| `validate_sftp` | Validate SFTP Settings.xml structure | Configuration validation — Settings.xml domain |
| `templates` | Show template/scrubber inventory | Enumerates scrubber patterns from Settings.xml |
| `create_job` | Create a new job from a template | Settings.xml CRUD operation |
| `edit_job` | Edit an existing job's configuration | Settings.xml CRUD operation |

### processing (8 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `template_status` | Processing status for a template or deal | Queries tblTemplateStaging |
| `processing_history` | Full processing history for a deal/servicer/template | Queries tblTemplateStaging |
| `failure_analysis` | Analyze failures — what failed, why, error patterns | Queries tblTemplateStaging failures |
| `source_trace` | Trace where a file came from | Queries tblTemplateStaging file path data |
| `manual_queue` | Manual vs automated processing breakdown | Queries tblTemplateStaging QueuedBy field |
| `processing_duration` | Processing time analysis — slowest templates, outliers | Queries tblTemplateStaging durations |
| `deal_pipeline` | End-to-end pipeline view for a deal/servicer | Starts from tblTemplateStaging, cross-references all layers |
| `staging_search` | Direct search of tblTemplateStaging records | Ad-hoc staging queries |

**Note on `deal_pipeline`:** This tool reads from all three tables (Settings.xml, tblExternalDIDRef, tblTemplateStaging). It is placed in `processing` because the primary question it answers is "is this deal being processed end-to-end?" — the processing/execution layer is the primary concern. The user asking for a "pipeline view" is typically asking "is the whole chain working?" which is an execution-history question.

### logs_ops (7 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `sync_logs` | Index application log files into SQLite | Log management operation |
| `daily_summary` | Daily operations summary from logs | Log analytics |
| `did_failures` | DID lookup failures from logs | Log-specific failure tracking |
| `job_health` | Job health metrics from logs (run count, success rate) | Log-derived health metrics |
| `deal_activity` | Recent activity for a deal from logs | Log-derived activity tracking |
| `log_trends` | Volume and processing trends over time from logs | Log analytics |
| `log_performance` | Performance rankings from logs | Log analytics |

### deployment (4 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `save_settings` | Save/deploy Settings.xml with backup | Deployment operation |
| `list_backups` | List available backup restore points | Deployment management |
| `xml_diff` | Show changes since last backup/deploy | Pre-deployment verification |
| `rollback` | Rollback to a previous backup version | Deployment recovery |

### system_admin (5 tools)

| Tool Name | Purpose | Why This Category |
|---|---|---|
| `triage_email` | Triage an email — does it match a job? | Cross-cutting analysis |
| `consolidation_analysis` | Which jobs could be merged? | Cross-cutting configuration analysis |
| `impact_analysis` | "What if" scenario simulation | Cross-cutting impact assessment |
| `system_health` | Full system health report | Cross-cutting status |
| `agent_status` | FRP Agent backend status | System information |

---

## 4. Two-Stage Routing Flow

### Detailed Sequence Diagram

```
User types: "@frp Do we have any jobs or keyword setup for deal DID = ICW MAT TRUST SUBI A1"
     │
     ▼
[participant handler]
     │
     ├── buildConversationContext(context)  →  historyContext
     │
     ▼
[STAGE 1: classifyIntent()]
     │
     ├── Build classifier prompt:
     │     - 6 category definitions (name, description, key signals, examples)
     │     - Conversation history (if any)
     │     - User prompt
     │     - Instruction: "Return JSON { category: '<name>' }"
     │
     ├── LLM sendRequest() — NO tools, text-only response
     │     - Short prompt (~400 tokens)
     │     - No SYSTEM_PROMPT, no DOMAIN_KNOWLEDGE
     │     - Response: '{ "category": "deal_mapping" }'
     │
     ├── Parse JSON response
     │     - Success: category = "deal_mapping"
     │     - Failure: fall back to single-stage 36-tool router
     │
     ├── Log: "[FRP] Stage 1: deal_mapping"
     │
     ▼
[STAGE 2: routeWithinCategory("deal_mapping")]
     │
     ├── Filter FRP_TOOLS to category subset:
     │     CATEGORY_TOOLS["deal_mapping"] = ["deal_lookup", "servicer_dossier",
     │       "coverage_gaps", "orphan_detection", "collision_detection"]
     │     → 5 tool definitions (not 36)
     │
     ├── Build routing prompt:
     │     - SYSTEM_PROMPT (formatting rules, data model rules)
     │     - DOMAIN_KNOWLEDGE (simplified — data model only, no decision tree)
     │     - Category context: "You are routing within the Deal & Reference Mapping category"
     │     - Conversation history
     │     - User prompt
     │
     ├── LLM sendRequest() — WITH tools (5 tools), toolMode: Required
     │     - Response: ToolCallPart { name: "deal_lookup", input: { query: "ICW MAT TRUST SUBI A1" } }
     │
     ├── Log: "[FRP] Stage 2: deal_lookup({ query: 'ICW MAT TRUST SUBI A1' })"
     │
     ▼
[executeToolCall("deal_lookup", { query: "ICW MAT TRUST SUBI A1" })]
     │
     ├── → handleDealLookup("ICW MAT TRUST SUBI A1", ...)
     │     → Backend CLI: deal_lookup --query "ICW MAT TRUST SUBI A1"
     │     → MySQL: SELECT * FROM tblExternalDIDRef WHERE DID LIKE '%ICW MAT TRUST SUBI A1%'
     │     → Result: 0 rows
     │     → Deterministic "not found" response (no LLM formatting)
     │
     ▼
[Response stream]
     "No matching deals found for **ICW MAT TRUST SUBI A1** in tblExternalDIDRef."
     *📦 Source: MySQL · Jobs: n/a*
```

### Comparison: Current vs Proposed

| Aspect | Current (Single-Stage) | Proposed (Two-Stage) |
|---|---|---|
| LLM calls for routing | 1 (with 36 tools) | 2 (Stage 1: text classification + Stage 2: ≤8 tools) |
| Tool discrimination | 36-way | 6-way → ≤8-way |
| DID query routing | ❌ Picks `search_jobs` | ✅ Stage 1 → `deal_mapping` → Stage 2 → `deal_lookup` |
| Regex pre-routing | 2 patterns, fragile | None (removed) |
| Negative tool descriptions | "Do NOT use for X" | Clean, affirmative |
| Decision tree | 14 points, insufficient | Removed; replaced by category definitions |
| Fallback behavior | None (LLM picks wrong tool silently) | Falls back to single-stage if Stage 1 fails |

---

## 5. Stage 1: Intent Classifier Design

### Classifier Prompt Structure

The Stage 1 prompt is deliberately **minimal and focused**. It does NOT include SYSTEM_PROMPT or DOMAIN_KNOWLEDGE — those are routing instructions for Stage 2. Stage 1 only needs to classify the user's intent into one of 6 categories.

```
┌──────────────────────────────────────────────────────────┐
│  CLASSIFIER PROMPT                                        │
│                                                          │
│  "You are classifying a user's question about the FRP    │
│   (File Reception Portal) system into exactly one of     │
│   these categories."                                     │
│                                                          │
│  [6 category definitions with:]                          │
│    - name                                                │
│    - description (1–2 sentences)                         │
│    - data_layer (which table/source)                     │
│    - examples (3–4 example prompts)                      │
│                                                          │
│  [Disambiguation rules — explicit boundary guidance:]    │
│    - "jobs for deal X" → deal_mapping (starts from deal) │
│    - "search jobs by name" → job_config (starts from job)│
│    - "pipeline view" → processing                        │
│                                                          │
│  [Conversation history (if any)]                         │
│                                                          │
│  "User question: <THE PROMPT>"                           │
│                                                          │
│  "Respond with ONLY a JSON object:                       │
│     { \"category\": \"<name>\", \"mode\": \"single_tool\" }"    │
│  "The mode field must always be \"single_tool\"."          │
│  "Do not explain. Do not include any other text."        │
└──────────────────────────────────────────────────────────┘
```

### Category Definitions for the Classifier Prompt

Each category definition in the classifier prompt contains exactly these fields:

| Field | Purpose | Example |
|---|---|---|
| `name` | Category identifier | `"deal_mapping"` |
| `description` | What this category covers (1–2 sentences) | `"Questions about deals, DIDs, ImportDID keywords, CompanyID lookups, and deal-to-job reverse mapping. The answer comes FROM the deal reference table (tblExternalDIDRef) and cross-references to Settings.xml."` |
| `dataLayer` | Which data source answers the question | `"tblExternalDIDRef (MySQL) + cross-reference to Settings.xml"` |
| `examples` | 3–4 representative user prompts | `["any jobs for deal DID = ICW", "which keywords map to servicer 296", "do we have coverage for deal CMLTI 2014-A"]` |

### Disambiguation Rules

The classifier prompt includes explicit disambiguation rules for known confusing cases. These replace the old decision tree and are specifically written for the classifier:

| User Pattern | Correct Category | Why |
|---|---|---|
| "any jobs for deal X" / "jobs that serve deal X" | `deal_mapping` | Starts from a deal name → cross-references to jobs. Answer comes from tblExternalDIDRef |
| "search jobs" / "list all jobs" / "find jobs named X" | `job_config` | Searches Settings.xml by job attributes |
| "show details for job X" | `job_config` | Returns a specific job's config from Settings.xml |
| "which deals use job X" / "deals linked to job X" | `job_config` | Starts from a job name → `job_detail` returns linked deals |
| "has deal X been processed" / "processing status" | `processing` | Answers from tblTemplateStaging execution records |
| "what's failing" / "error analysis" | `processing` | Failure data lives in tblTemplateStaging |
| "what happened today in the logs" / "daily summary" | `logs_ops` | Log-derived operational data |
| "save settings" / "deploy" / "rollback" | `deployment` | Settings.xml lifecycle management |
| "triage this email" / "system health" | `system_admin` | Cross-cutting analysis/administration |
| "pipeline view for deal X" | `processing` | End-to-end execution status, anchored in tblTemplateStaging |

### Classifier Output Parsing

1. Send prompt to LLM (no tools, text-only response)
2. Collect response text
3. Attempt `JSON.parse()` on the response
4. Validate that `result.category` is one of the 6 known category names
5. Read `result.mode` (default: `"single_tool"`) — reserved for Phase 8 ReAct pipeline support
6. If parsing succeeds and category is valid → return `result.category` (and `mode` when Phase 8 activates)
7. If parsing fails OR category is unknown → log warning, fall back to single-stage 36-tool router

---

## 6. Stage 2: Category-Scoped Tool Router Design

### Stage 2 Prompt Structure

Stage 2 receives the classified category name and sends only that category's tools to the LLM. The prompt structure is similar to the current `routeWithToolCalling()` but with a **much smaller tool set**.

```
┌──────────────────────────────────────────────────────────┐
│  STAGE 2 ROUTING PROMPT                                   │
│                                                          │
│  SYSTEM_PROMPT (formatting rules, data model rules)      │
│                                                          │
│  DOMAIN_KNOWLEDGE_SIMPLIFIED                             │
│  (Three-table pipeline + cross-reference chains ONLY     │
│   — no decision tree, no routing instructions)           │
│                                                          │
│  "You are routing within the [Category Name] category."  │
│  "Select the best tool and extract parameters."          │
│  "You MUST call exactly one tool."                       │
│                                                          │
│  [Conversation history (if any)]                         │
│                                                          │
│  "User question: <THE PROMPT>"                           │
│                                                          │
│  Tools: CATEGORY_TOOLS[category]                         │
│  (4–8 tool definitions, NOT 36)                          │
│                                                          │
│  toolMode: Required                                      │
└──────────────────────────────────────────────────────────┘
```

### How `CATEGORY_TOOLS` Is Built

`CATEGORY_TOOLS` is a static lookup object. It maps each category name to an array of tool names. At runtime, the actual tool definition objects are filtered from `FRP_TOOLS`:

```
CATEGORY_TOOLS = {
  "deal_mapping":  ["deal_lookup", "servicer_dossier", "coverage_gaps", "orphan_detection", "collision_detection"],
  "job_config":    ["search_jobs", "job_detail", "validate_email", "validate_sftp", "templates", "create_job", "edit_job"],
  "processing":    ["template_status", "processing_history", "failure_analysis", "source_trace", "manual_queue", "processing_duration", "deal_pipeline", "staging_search"],
  "logs_ops":      ["sync_logs", "daily_summary", "did_failures", "job_health", "deal_activity", "log_trends", "log_performance"],
  "deployment":    ["save_settings", "list_backups", "xml_diff", "rollback"],
  "system_admin":  ["triage_email", "consolidation_analysis", "impact_analysis", "system_health", "agent_status"]
}
```

At runtime, `routeWithinCategory()` filters:
```javascript
const toolNames = CATEGORY_TOOLS[category];
const scopedTools = FRP_TOOLS.filter(t => toolNames.includes(t.name));
```

This ensures `FRP_TOOLS` remains the single source of truth for tool definitions.

---

## 7. Fallback Strategy

### When Fallback Triggers

| Scenario | Detection | Action |
|---|---|---|
| Stage 1 returns invalid JSON | `JSON.parse()` throws | Log `[FRP] Stage 1 parse failure`, fall back to single-stage 36-tool router |
| Stage 1 returns unknown category | `result.category` not in CATEGORY_TOOLS keys | Log `[FRP] Stage 1 unknown category: X`, fall back to single-stage 36-tool router |
| Stage 1 LLM call fails (timeout, API error) | `sendRequest()` throws | Log `[FRP] Stage 1 error: ...`, fall back to single-stage 36-tool router |
| Stage 2 LLM selects no tool | `foundToolCall` remains false after stream | Log `[FRP] Stage 2 no tool selected`, return null (existing free-form fallback) |
| Stage 2 LLM call fails | `sendRequest()` throws | Log `[FRP] Stage 2 error: ...`, return null (existing free-form fallback) |

### Fallback Implementation

The fallback path is literally the current `routeWithToolCalling()` implementation (single-stage, 36 tools). During Phase 7 implementation, the old logic is preserved inside a `routeWithAllTools()` function that is called when the two-stage path fails.

This means:
- **Phase 7 can never make things worse.** If the new two-stage routing fails for any reason, it falls back to exactly the current behavior.
- **The fallback is the current production code.** It has been running since Phase 1 and handles 90%+ of queries correctly. The 10% that fail (DID queries) will still fail in fallback mode, but they also fail today.

---

## 8. Conversation History Handling

### Current Behavior (Preserved)

The `buildConversationContext()` function extracts relevant context from VS Code's `ChatContext`. This includes:
- Previous user prompts
- Previous assistant responses (summarised)
- Previous tool calls and their results

### Two-Stage Usage

| Stage | Uses History? | Why |
|---|---|---|
| Stage 1 | ✅ Yes | Follow-up queries like "show me details for the first one" need conversation context to determine which domain the user is in |
| Stage 2 | ✅ Yes | Same as current behavior — the LLM needs history to extract identifiers like job names or ServicerIDs from previous results |

### History Format in Stage 1

Conversation history is appended to the classifier prompt as a brief context section:

```
Previous conversation:
- User asked about CMBS jobs (category: job_config)
- System returned 9 email jobs matching "CMBS"

Now the user says: "show me the deals for the first one"
```

The key insight: Stage 1 can see that the conversation has been about jobs, and the user is now asking about deals for a specific job — this should route to `job_config` (via `job_detail`) because the starting point is a job name from the previous results.

---

## 9. Logging and Diagnostics

### Log Output Format

Every routing decision is logged to the VS Code output channel (`[FRP]` prefix) with stage-specific tags:

```
[FRP] Stage 1 classifier input: "Do we have any jobs or keyword setup for deal DID = ICW MAT TRUST SUBI A1"
[FRP] Stage 1 raw response: '{ "category": "deal_mapping" }'
[FRP] Stage 1 result: deal_mapping
[FRP] Stage 2 tools: ["deal_lookup", "servicer_dossier", "coverage_gaps", "orphan_detection", "collision_detection"]
[FRP] Stage 2 sending request (model=gpt-4.1, tools=5)
[FRP] Stage 2 selected: deal_lookup({ query: "ICW MAT TRUST SUBI A1" })
[FRP] LLM tool call → deal_lookup({"query":"ICW MAT TRUST SUBI A1"})
```

### Error Logging

```
[FRP] Stage 1 parse failure: Unexpected token at position 0 — raw: "I think this is deal_mapping"
[FRP] Falling back to single-stage 36-tool router
```

```
[FRP] Stage 1 unknown category: "deal_query" (not in categories)
[FRP] Falling back to single-stage 36-tool router
```

---

## 10. Data Flow Diagrams

### Complete Request Flow

```
┌──────────────────────────────────────────────────────────────┐
│  User types prompt in @frp chat                               │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  frpChatHandler(request, context, stream, token)              │
│  ├── selectModel(request)                                     │
│  ├── buildConversationContext(context)                         │
│  └── routeWithToolCalling(prompt, request, context, ...)      │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  routeWithToolCalling() — MODIFIED                            │
│                                                              │
│  1. Guard checks (LanguageModelToolCallPart, model, etc.)     │
│                                                              │
│  2. STAGE 1: classifyIntent()                                │
│     ├── buildClassifierPrompt(prompt, historyContext)          │
│     ├── model.sendRequest(classifierPrompt, {}, token)        │
│     │   → No tools, text-only response                        │
│     ├── JSON.parse(response) → { category: "deal_mapping" }   │
│     └── Validate category name                                │
│         ├── Valid → proceed to Stage 2                         │
│         └── Invalid → routeWithAllTools() (fallback)          │
│                                                              │
│  3. STAGE 2: routeWithinCategory(category)                   │
│     ├── scopedTools = FRP_TOOLS.filter(in category)           │
│     ├── Build routing prompt (SYSTEM_PROMPT + context)         │
│     ├── model.sendRequest(routingPrompt, {tools: scopedTools}) │
│     │   → toolMode: Required                                  │
│     ├── Stream response, look for ToolCallPart                │
│     └── executeToolCall(tool.name, tool.input, ...)           │
│                                                              │
│  4. Fallback: routeWithAllTools() — current single-stage      │
│     (Only reached if Stage 1 fails)                          │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  executeToolCall() — UNCHANGED                                │
│  ├── 36-branch switch                                         │
│  └── Calls handler function (handleDealLookup, etc.)          │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  Handler function → backendCall() → CLI → result              │
│  LLM formats response with <data> tags                        │
│  dataSourceFooter() appended                                  │
│  stream.markdown() → user sees formatted response             │
└──────────────────────────────────────────────────────────────┘
```

---

## 11. Error Handling Strategy

| Error Point | Handling | User Impact |
|---|---|---|
| Stage 1 LLM timeout | Catch error, log, fall back to `routeWithAllTools()` | None — user sees normal response (may be wrong tool, same as today) |
| Stage 1 JSON parse failure | Catch error, log raw response, fall back to `routeWithAllTools()` | None — same as above |
| Stage 1 unknown category | Log warning, fall back to `routeWithAllTools()` | None — same as above |
| Stage 2 LLM timeout | Catch error, log, return null → free-form LLM response | User gets a conversational answer instead of structured tool output |
| Stage 2 no tool selected | Return null → free-form LLM response | Same as above |
| Stage 2 unknown tool name | `executeToolCall()` default case → "Unknown tool" message | User sees error message — same as current behavior |
| Backend CLI error | Handler-level error handling — unchanged | User sees error message — same as current behavior |

### Key Principle: No Silent Failures

Every fallback path logs the reason. The output channel (`[FRP]`) shows exactly what happened:
- Which stage failed
- What the raw LLM response was
- Which fallback path was taken

This enables post-incident debugging without requiring reproduction.

---

## 12. File Manifest

### Summary

| Operation | File | Lines Added | Lines Removed | Net Change |
|---|---|---|---|---|
| Modified | `extension/chat/participant.js` | ~120 | ~40 | ~+80 |

### Detailed Changes Within `participant.js`

| Section | Operation | Description |
|---|---|---|
| `DOMAIN_KNOWLEDGE` constant | Modified | Remove "Tool Selection Decision Tree" section (14 points, ~30 lines). Keep "Three-Table Pipeline" and "Cross-Reference Chains" sections |
| `FRP_TOOLS[search_jobs].description` | Modified | Remove "Do NOT use this when the user provides a deal name..." clause |
| `FRP_TOOLS[deal_lookup].description` | Modified | Remove "ALWAYS USE THIS when the user mentions a deal name/DID..." clause. Clean to affirmative description |
| After `FRP_TOOLS` array | Added | `INTENT_CATEGORIES` constant (~40 lines) — 6 category definitions |
| After `INTENT_CATEGORIES` | Added | `CATEGORY_TOOLS` constant (~10 lines) — category → tool name mapping |
| After `CATEGORY_TOOLS` | Added | `buildClassifierPrompt()` function (~20 lines) |
| After `buildClassifierPrompt` | Added | `classifyIntent()` function (~30 lines) |
| After `classifyIntent` | Added | `routeWithinCategory()` function (~35 lines) |
| `routeWithToolCalling()` | Modified | Rename old logic to `routeWithAllTools()`. New `routeWithToolCalling()` calls `classifyIntent()` → `routeWithinCategory()` with fallback to `routeWithAllTools()` |
| Regex pre-routing block | Removed | `dealIntentRe`, `dealIntent2`, `if (dealMatch)` — ~10 lines |
