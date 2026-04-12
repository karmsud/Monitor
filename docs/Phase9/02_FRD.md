# Phase 9 FRD — Functional Requirements Document
## FRP Agent VS Code Extension — Conversational Intelligence Upgrade

**Document type:** Functional Requirements Document  
**Parent:** Phase 9 PRD (`01_PRD.md`)  
**Status:** Draft  
**Date:** March 7, 2026

---

## 1. Purpose

This document specifies the exact functional behaviour of each Phase 9 change. Where the PRD explains *what* and *why*, this document specifies *how the system behaves* from the user's perspective — inputs, outputs, state transitions, error paths, and interaction flows. Each section maps to PRD stories (S-1xx through S-4xx).

---

## 2. Current System Behaviour Reference

The following current-code facts are established by reading the extension source and are referenced throughout this document.

| Fact | Location in code | Phase 9 disposition |
|---|---|---|
| `edit_job` tool schema `{ prompt: string }` | `participant.js` line 490–499 | Replaced with structured schema + `xmlType` |
| `create_job` tool schema `{ prompt: string }` | `participant.js` ~ line 465 | Replaced with structured schema + `xmlType` |
| `rollback` tool schema `{ prompt: string }` | `participant.js` ~ line 530 | Replaced with structured schema |
| `triage_email` tool schema `{ prompt: string }` | `participant.js` ~ line 540 | Replaced with structured schema (sender/subject/msgPath/mode) |
| `impact_analysis` tool schema `{ prompt: string }` | `participant.js` ~ line 555 | Replaced with structured schema (changeType/targetJob/etc.) |
| `coverage_gaps` tool schema `{ prompt: string }` (optional) | `participant.js` ~ line 510 | Simplified to `{focus: enum}` optional |
| `handleJobEdit` regex `^edit\s+["']?(.+?)["']?\s+set\s+(\w+)\s+(.+)$` | line 3706 | Deleted from handler; retained in `handleJobsCommand` slash path only |
| `handleJobCreate` regex `^create\s+(.+?)\s+from\s+["']?(.+?)["']?\s*$` | line 3633 | Same |
| `handleDeployRollback` regex (filename extraction) | ~ line 3910 | Same |
| `parseChangeIntent()` internal LLM call | ~ line 3339 | Deleted entirely |
| `buildConversationContext` returns plain string | line 1981–2004 | Supplemented with `buildMessageHistory` |
| History string injected into Stage 1 + Stage 2, NOT tool LLM | lines 964, 1443, 1495, 1580 | History passed as structured messages to all LLM calls |
| `vscode.window.showWarningMessage({modal:true})` × 3 | lines 3662, 3722, 3972 | Replaced with in-chat confirm flow |
| `general_reasoning` pipeline excludes CRUD tools | line 403 comment | New `crud_planning` pipeline added; general_reasoning unchanged |
| `reactLoop` tool set from pipelineDef.tools | line 1844 | New `crud_planning` and `analysis_pipeline` pipelineDefs added |
| `edit_job` `buildToolArgs` uses `toolInput.type` (wrong key) | ~ line 1111 | Fixed to use `toolInput.xmlType` (matches schema key) |
| No `analysis_pipeline` in `PIPELINE_DEFINITIONS` | line 355 | New pipeline added (Epic 6) |
| `SFTP_FIELD_MAP` defined in backend, not exposed to LLM | `crud.py` line 40 | SFTP fields added to `edit_job` field enum (Epic 5) |

---

## 3. Functional Requirements — Epic 1: Structured Tool Schemas

### FR-1.1 — `edit_job` Tool Input Schema

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "jobName": {
      "type": "string",
      "description": "The exact job name to edit, e.g. CMBS_GreyCo. If not stated explicitly, resolve from conversation history."
    },
    "field": {
      "type": "string",
      "enum": ["name", "servicer_id", "mailbox", "folder", "sme", "save_location",
               "last_email", "queue_one_file", "day_adjust", "import_did",
               "subject_filter", "sender_filter", "scrubber", "template"],
      "description": "The configuration field to change."
    },
    "value": {
      "type": "string",
      "description": "The new value to set."
    }
  },
  "required": ["jobName", "field", "value"]
}
```

**Handler signature change:**

| Before | After |
|---|---|
| `handleJobEdit(prompt, ...)` — parses prompt with regex | `handleJobEdit(jobName, field, value, ...)` — uses params directly |

**Handler behavior:**
1. Receives `{jobName, field, value}` directly from `executeToolCall` → `buildToolArgs`
2. Fetches current job XML via `backendCall('job_detail', {jobName})` to populate the before-state for the diff (FR-3.1)
3. Renders before/after diff in stream (FR-3.1)
4. Awaits inline confirmation (FR-3.2)
5. On confirm: calls `backendCall('edit_job', {jobName, field, value, xmlType: 'email'})`
6. Surfaces backup path from result (FR-3.3)
7. Passes result to `generateOrFallback` for LLM summary

**`buildToolArgs` change for `edit_job`:**
```javascript
// Before:
case 'edit_job':
  return { command: 'edit_job', params: { prompt: toolInput.prompt || '' } };

// After:
case 'edit_job':
  return { command: 'edit_job', params: {
    jobName: toolInput.jobName || '',
    field:   toolInput.field   || '',
    value:   toolInput.value   || '',
    xmlType: toolInput.xmlType || 'email',
  }};
```

**Slash-command backward compatibility:**  
The existing `/jobs edit <job> set <field> <value>` slash-command in `handleJobsCommand` (line 2241) is updated to extract parts and call `handleJobEdit(jobName, field, value, ...)` directly — the regex moves from inside `handleJobEdit` to inside `handleJobsCommand` where it processes the explicit slash command syntax only. NL routing never goes through `handleJobsCommand`.

---

### FR-1.2 — `create_job` Tool Input Schema

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "newName": {
      "type": "string",
      "description": "The name for the new job."
    },
    "templateJob": {
      "type": "string",
      "description": "The existing job to copy as a template."
    },
    "overrides": {
      "type": "object",
      "description": "Optional field overrides to apply after copying, e.g. {servicer_id: '999'}.",
      "additionalProperties": { "type": "string" }
    }
  },
  "required": ["newName", "templateJob"]
}
```

**Handler signature change:** `handleJobCreate(newName, templateJob, overrides, ...)` — no regex.

**Handler behavior:**
1. Pre-flight: calls `backendCall('search_jobs', {query: templateJob})` to verify template exists
2. Renders template preview in stream
3. Renders confirmation block (FR-3.1/3.2)
4. On confirm: calls `backendCall('create_job', {templateJob, name: newName, overrides, xmlType: 'email'})`
5. Surfaces backup path (FR-3.3)

---

### FR-1.3 — `rollback` Tool Input Schema

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "backupFile": {
      "type": "string",
      "description": "The backup file name to restore, e.g. Settings_20260307_092000.xml. Resolve from conversation history if user says 'this morning's backup' etc."
    }
  },
  "required": ["backupFile"]
}
```

**Handler behavior:**
1. Calls `backendCall('xml_diff', {backupFile})` to get the diff preview
2. Renders diff (FR-3.1)
3. Awaits inline confirmation (FR-3.2)
4. On confirm: calls `backendCall('rollback_xml', {backupFile})`

---

## 4. Functional Requirements — Epic 2: Conversation History

### FR-2.1 — `buildMessageHistory(context, systemPrompt, currentPrompt)` Function

**Inputs:**
- `context` — VS Code `ChatContext` object (has `context.history: (ChatRequestTurn | ChatResponseTurn)[]`)
- `systemPrompt` — string to use as the first User message (contains SYSTEM_PROMPT + DOMAIN_KNOWLEDGE)
- `currentPrompt` — the current user turn text

**Output:** `LanguageModelChatMessage[]` in this order:
```
[0] User(systemPrompt)            ← always first
[1] User(history[0] user text)    ← if history exists
[2] Assistant(history[0] response text, truncated to 2000 chars)
...
[N-1] User(history[last] user turn)
[N] User(currentPrompt)           ← current turn, always last
```

**Rules:**
- History is capped at the most recent 6 turns (3 request/response pairs) — matching current `slice(-6)`
- Response text is concatenated from `ChatResponseMarkdownPart.value.value` parts, truncated to 2000 chars
- Turns with empty response text are skipped (no empty Assistant messages)
- `buildConversationContext` (the old string builder) is **not deleted** — it is kept as a fallback for Stage 1 classification which benefits from plain-text context injection and doesn't use `model.sendRequest(messages)` style

**Callers to be updated:**
1. `routeWithinCategory` — replace `historyContext` string injection in `routingPrompt` with `buildMessageHistory` messages array
2. `routeWithAllTools` — same
3. `reactLoop` — replace `userContent` string build with `buildMessageHistory` messages array

---

### FR-2.2 — Anaphora Resolution Behaviour

When conversation history is passed as structured messages to the tool-calling LLM:

- The LLM MUST resolve single-referent anaphora ("that job", "its scrubber", "it") to the most recently mentioned job name in history, if unambiguous
- When two or more different job names appear in the last 3 turns, the LLM MUST ask the clarifying question rather than guess
- The existing anaphora resolution hint in `routingPrompt` (line 1444) is retained verbatim; it now redundantly reinforces native multi-turn behaviour

---

### FR-2.3 — Clarifying Question Behaviour

When the LLM calls a tool with a `required` parameter it could not resolve:

**If the tool schema marks a param as `required` and the LLM cannot fill it:**
The LLM will naturally not call the tool and instead produce text output (e.g., "Which job should I update?"). This is standard LLM tool-calling behaviour when `required` params can't be determined.

**The participant handler must NOT show a "Usage:" help block** unless the user explicitly types a help-related phrase (`help`, `?`, `how do I`, `usage`, `syntax`).

**The clarifying question is surfaced as normal chat markdown.** Subsequent user turns go through the normal routing pipeline — the prior incomplete intent is reconstructed from conversation history.

---

## 5. Functional Requirements — Epic 3: Native Confirmation UX

### FR-3.1 — Before/After XML Diff Rendering

**Trigger:** Any call to `handleJobEdit`, `handleJobCreate`, or `handleDeployRollback` after parameter extraction succeeds.

**For `handleJobEdit`:**
1. Call `backendCall('job_detail', {jobName})`
2. Extract the target element's current text value from the result
   - For flat fields: `result.data.job[fieldXmlTag]` (e.g., `result.data.job.ServicerID`)
   - For nested fields (scrubber/template): `result.data.job.templates?.main` or equivalent path
3. Stream to chat:
```
**Before:**
```xml
<Templates><Main>QueueCMBS_Scrubber_x</Main></Templates>
```
**After this change:**
```xml
<Templates><Main>Outlook_Queuer_x</Main></Templates>
```
```

**For `handleJobCreate`:** Show the template job's key fields, then label the new job section with overrides highlighted.

**For `handleDeployRollback`:** The `xml_diff` backend call already returns a diff; render it as a fenced diff block.

**Error path:** If `job_detail` fails, emit the error and stop. Do not proceed to confirmation.

---

### FR-3.2 — Inline Chat Confirmation Pattern

**Pattern (replaces all three `showWarningMessage` calls):**

```javascript
// After rendering the diff:
stream.markdown('\n**Confirm this change?**\n');
stream.button({ title: 'Confirm', command: 'frp.confirmPending' });
stream.button({ title: 'Cancel',  command: 'frp.cancelPending'  });
```

**If `stream.button()` is not available** (VS Code < 1.95 or API shimmed away), fall back to:
```
Type **yes** to confirm or **no** to cancel.
```

**Response detection:** The subsequent user turn in the same conversation is inspected:
```javascript
const lc = nextTurn.toLowerCase().trim();
const confirmed = /^(yes|y|confirm|apply|ok|proceed|do it)/.test(lc);
const cancelled = /^(no|n|cancel|stop|abort|nevermind|nope)/.test(lc);
```
- `confirmed = true` → execute the backend call
- `cancelled = true` OR neither → emit "Operation cancelled." and stop
- The 'pending intent' is NOT stored as global state — it is reconstructed from conversation history if needed

**Important:** This is a user-turn-based confirmation, not a callback. The confirmation round-trip is a new chat turn. The `crud_planning` pipeline will batch confirmations (FR-4.2) so multi-step operations show one confirmation block.

---

### FR-3.3 — Backup Path in Response

**Requirement:** Every LLM summary prompt for write operations MUST include the `backup_file` string and explicitly instruct the LLM to mention it.

**Example LLM prompt addition:**
```javascript
const llmPrompt = [
  SYSTEM_PROMPT, '',
  '<data>', JSON.stringify(data, null, 2), '</data>', '',
  `Job "${jobName}" was edited: ${field} changed to "${value}".`,
  `A backup was saved at: ${data.data?.backup_file || 'unknown'}.`,   // ← new
  'Show the before→after change. Confirm the backup file name. Include validation result.',
].join('\n');
```

---

## 6. Functional Requirements — Epic 4: Multi-Step CRUD Pipeline

### FR-4.1 — `crud_planning` Pipeline Definition

**New entry in `PIPELINE_DEFINITIONS`:**
```javascript
crud_planning: {
  name: 'crud_planning',
  displayName: 'CRUD Planning',
  triggerDescription:
    'User wants to perform multiple create/edit/validate operations on jobs in a single request, ' +
    'or wants to create a job AND configure it in the same message.',
  playbook: CRUD_PLANNING_PLAYBOOK,   // new constant — see FR-4.3
  tools: ['search_jobs', 'job_detail', 'create_job', 'edit_job', 'validate_email', 'validate_sftp'],
  maxSteps: 8,
},
```

**Stage 1 classifier update:** Add `crud_planning` pipeline trigger to the pipeline section of `buildClassifierPrompt`, alongside `email_triage`, `job_investigation`, `servicer_investigation`.

**Trigger examples added to classifier:**
```
- "create a job from CSMC, set the scrubber to X, and validate it" → crud_planning
- "create GreyCo_v2 from CSMC_Template and change its scrubber to Outlook_Queuer_x" → crud_planning
- "add a new job and configure servicer 296 on it" → crud_planning
```

---

### FR-4.2 — Consolidated Confirmation for Multi-Step Plans

**Within `crud_planning` ReAct loop:**

Before executing the FIRST tool call, the loop pauses and presents a consolidated plan:
```
**Planned operations:**
1. Create job `GreyCo_v2` from template `CSMC_Template`
2. Set scrubber → `Outlook_Queuer_x`
3. Validate `GreyCo_v2`

Confirm all? (yes / no)
```

The plan is assembled from the LLM's first response (which lists tool calls it intends to make before actually making them — this is achieved via the `CRUD_PLANNING_PLAYBOOK` instruction, see FR-4.3).

After confirmation → steps execute sequentially with no further interruptions.

---

### FR-4.3 — `CRUD_PLANNING_PLAYBOOK` Content

```
You are the FRP CRUD planning agent.

Your role is to plan and execute a sequence of create/edit/validate operations on job configurations.

PHASE 1 — PLAN (do NOT call any tools yet):
List every operation you intend to perform in order, using this format:
  PLAN:
  1. create_job: newName=X, templateJob=Y
  2. edit_job: jobName=X, field=scrubber, value=Z
  3. validate_email: jobName=X

Wait for the user to confirm the plan before executing.

PHASE 2 — EXECUTE (only after confirmation):
Execute each step in order. After each tool call, report the result.
If a step fails, stop and report the failure. Do not attempt the next step.
Always mention the backup file created at each write step.

RULES:
- Never combine multiple operations into a single tool call
- Always call job_detail before edit_job to verify the job exists
- If you are unsure of a parameter, ask before executing (not during planning)
```

---

### FR-4.4 — `general_reasoning` Pipeline CRUD Exclusion — Preserved

The comment and tool exclusion at line 403 are preserved verbatim:
```javascript
// Deliberately excludes niche CRUD tools (create_job, edit_job, rollback, etc.)
// that should never be invoked in an open-ended reasoning loop.
```
`general_reasoning` tools list is unchanged. CRUD operations only enter the agentic loop via `crud_planning`.

---

## 7. Interaction Flow Diagrams

### 7.1 Single-Step NL Edit (after Phase 9)

```
User: "change the scrubber on CMBS_GreyCo to Outlook_Queuer_x"
  │
  ▼
Stage 1: category=job_config, mode=single_tool
  │
  ▼
Stage 2: routeWithinCategory("job_config")
  LLM receives structured schema for edit_job
  LLM produces: { jobName: "CMBS_GreyCo", field: "scrubber", value: "Outlook_Queuer_x" }
  │
  ▼
handleJobEdit("CMBS_GreyCo", "scrubber", "Outlook_Queuer_x")
  │
  ├─ backendCall('job_detail', {jobName})  → current XML
  │
  ├─ stream: before/after XML diff
  │
  ├─ stream.button("Confirm") + stream.button("Cancel")
  │
  ▼
[Next user turn: "yes"]
  │
  ▼
backendCall('edit_job', {jobName, field, value})
  │
  ▼
generateOrFallback → LLM summary including backup_file
```

### 7.2 Contextual "that job" Edit (after Phase 9)

```
Turn N-1: "show details for CMBS_GreyCo"
  └─ job_detail → result streamed

Turn N: "update its scrubber to Outlook_Queuer_x"
  │
  ▼
Stage 1: category=job_config, mode=single_tool
  │
  ▼
Stage 2: routeWithinCategory
  LLM receives buildMessageHistory (includes Turn N-1 as structured message)
  LLM resolves "its" → CMBS_GreyCo
  LLM produces: { jobName: "CMBS_GreyCo", field: "scrubber", value: "Outlook_Queuer_x" }
  │
  ▼
  [same as 7.1 from here]
```

### 7.3 Multi-Step CRUD (after Phase 9)

```
User: "create GreyCo_v2 from CSMC_Template and set scrubber to Outlook_Queuer_x"
  │
  ▼
Stage 1: category=job_config, mode=pipeline, pipeline=crud_planning
  │
  ▼
reactLoop with crud_planning playbook
  │
  ├─ PHASE 1: LLM lists plan (no tool calls yet)
  │   PLAN:
  │   1. create_job: newName=GreyCo_v2, templateJob=CSMC_Template
  │   2. edit_job: jobName=GreyCo_v2, field=scrubber, value=Outlook_Queuer_x
  │   3. validate_email: jobName=GreyCo_v2
  │
  ├─ stream: plan summary + confirm/cancel buttons
  │
  ▼
[Next user turn: "yes"]
  │
  ├─ Step 1: create_job → backup_file_1 created
  ├─ Step 2: edit_job → backup_file_2 created
  └─ Step 3: validate_email → result
  │
  ▼
LLM final summary: "Created GreyCo_v2 ✅, set scrubber ✅, validated ✅. Backups at..."
```

---

## 8. Error Handling Matrix

| Scenario | Handler | Response |
|---|---|---|
| `job_detail` fails before edit confirmation | `handleJobEdit` | "Could not retrieve current job config: {error}. Edit aborted." |
| LLM can't resolve job name (no history) | Stage 2 LLM | "Which job should I update?" |
| LLM can't resolve job name (ambiguous history) | Stage 2 LLM | "Which job — {A} or {B}?" |
| Backend returns `success: false` on write | all write handlers | "❌ Error: {error}" — tells user backup status |
| User says neither confirm nor cancel | inline confirm | "Operation cancelled." |
| `stream.button()` unavailable | inline confirm fallback | "Type **yes** to confirm or **no** to cancel." |
| `crud_planning` step N fails | `reactLoop` | Stops, reports failure, lists backup from prior steps |
| `required` param missing from tool call | LLM (implicit) | LLM asks clarifying question — no backend call |

---

## 9. Slash-Command Backward Compatibility

All existing slash commands (`/jobs`, `/deals`, `/logs`, `/deploy`, etc.) continue to work after Phase 9. The regex that currently lives inside `handleJobEdit` moves into `handleJobsCommand` to parse the explicit `/jobs edit X set Y Z` syntax. This is the only remaining regex in any handler, and it is clearly labelled as explicit-command parsing only.

| Slash command | Phase 9 behaviour |
|---|---|
| `/jobs edit CMBS_GreyCo set scrubber X` | Regex in `handleJobsCommand` extracts params → calls `handleJobEdit(jobName, field, value)` |
| `/jobs create GreyCo_v2 from CSMC` | Regex in `handleJobsCommand` extracts params → calls `handleJobCreate(newName, templateJob)` |
| All other slash commands | Unchanged |

---

## 10. Data Flow: Parameter Extraction Comparison

### Before Phase 9 (edit_job):
```
User text → Stage 1 (LLM) → Stage 2 (LLM) → "edit CMBS_GreyCo set scrubber X" → regex → params
                                              ^^^^^^^^^^ LLM reformats to match regex pattern
```

### After Phase 9 (edit_job):
```
User text → Stage 1 (LLM) → Stage 2 (LLM with structured schema) → {jobName, field, value}
                                                                      ^^^^^^^^^^ LLM extracts directly
```

The key insight: the same LLM that picks the tool also fills the parameters. When schema is structured, the LLM is not "reformatting to match a pattern" — it's filling a typed form. This is intrinsically more robust.

---

## 11. Functional Requirements — Epic 5: SFTP CRUD Parity

### Current State Reference (SFTP)

| Fact | Code location | Phase 9 disposition |
|---|---|---|
| `SFTP_FIELD_MAP` fully defined in backend | `backend/xml/crud.py` line 40 | Backend complete — no changes needed |
| `JobCrudEngine(xml_type='sftp')` works in backend | `crud.py` line 68 | Backend complete — no changes needed |
| `edit_job` tool schema has no `xmlType` param | `participant.js` ~ line 490 | Add `xmlType: enum('email','sftp')` |
| `buildToolArgs` for `edit_job` uses `toolInput.type \|\| 'email'` | `participant.js` ~ line 1111 | Change to use `toolInput.xmlType \|\| 'email'` |
| `edit_job` `field` enum contains only email fields | TRD §4.1 | Extend to include SFTP fields |
| `create_job` tool schema has no `xmlType` param | `participant.js` ~ line 465 | Add `xmlType: enum('email','sftp')` |
| SFTP fields: path→RemotePath, dsn→DSN, skip_list→SkipList, ignore_list→IgnoreList, zip_content_filter→ZipContentFilter | `crud.py` line 40 | Expose in field enum |

---

### FR-5.1 — `edit_job` Schema: Add `xmlType` and SFTP Field Enum

**Updated full schema:**
```json
{
  "type": "object",
  "properties": {
    "jobName": {
      "type": "string",
      "description": "Exact job name to edit. Resolve from conversation history if user says 'that job' / 'it'."
    },
    "xmlType": {
      "type": "string",
      "enum": ["email", "sftp"],
      "description": "Whether this is an email monitoring job or SFTP monitoring job. Default email unless user says 'SFTP job' or the job name starts with SFTP."
    },
    "field": {
      "type": "string",
      "enum": [
        "name", "servicer_id", "day_adjust", "sme", "save_location",
        "mailbox", "folder", "last_email", "queue_one_file",
        "import_did", "subject_filter", "sender_filter", "scrubber", "template",
        "path", "dsn", "skip_list", "ignore_list", "zip_content_filter"
      ],
      "description": "The field to change. Email fields: mailbox, folder, last_email, queue_one_file, import_did, subject_filter, sender_filter, scrubber, template. SFTP fields: path, dsn, skip_list, ignore_list, zip_content_filter. Shared fields: name, servicer_id, day_adjust, sme, save_location."
    },
    "value": {
      "type": "string",
      "description": "The new value to set."
    }
  },
  "required": ["jobName", "xmlType", "field", "value"]
}
```

**`buildToolArgs` update:**
```javascript
// Before (wrong — uses toolInput.type, schema had no xmlType key):
case 'edit_job':
  return { command: 'edit_job', params: {
    jobName: toolInput.jobName || '',
    field:   toolInput.field   || '',
    value:   toolInput.value   || '',
    xmlType: toolInput.type    || 'email',   // ← BUG: key mismatch
  }};

// After:
case 'edit_job':
  return { command: 'edit_job', params: {
    jobName: toolInput.jobName   || '',
    field:   toolInput.field     || '',
    value:   toolInput.value     || '',
    xmlType: toolInput.xmlType   || 'email',  // ← correct key
  }};
```

---

### FR-5.2 — `create_job` Schema: Add `xmlType`

**Updated schema:**
```json
{
  "type": "object",
  "properties": {
    "newName":     { "type": "string" },
    "templateJob": { "type": "string" },
    "xmlType": {
      "type": "string",
      "enum": ["email", "sftp"],
      "description": "Job type. Default email unless user explicitly says SFTP or template job name starts with SFTP."
    },
    "overrides": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    }
  },
  "required": ["newName", "templateJob", "xmlType"]
}
```

**`buildToolArgs` update:**
```javascript
case 'create_job':
  return { command: 'create_job', params: {
    templateJob: toolInput.templateJob || '',
    name:        toolInput.newName     || '',
    overrides:   toolInput.overrides   || {},
    xmlType:     toolInput.xmlType     || 'email',
  }};
```

---

### FR-5.3 — `resolveCurrentFieldValue` — SFTP Extension

The helper function (TRD §4.10) gains SFTP field mappings:

```javascript
const sftp_fieldMap = {
  path:                () => job.path || job.RemotePath || '',
  dsn:                 () => job.dsn  || job.DSN        || '',
  skip_list:           () => job.skip_list || job.SkipList || '',
  ignore_list:         () => job.ignore_list || job.IgnoreList || '',
  zip_content_filter:  () => job.zip_content_filter || job.ZipContentFilter || '',
};
// Select map based on xmlType parameter passed alongside jobDetailResult
const map = (xmlType === 'sftp') ? { ...fieldMap, ...sftp_fieldMap } : fieldMap;
return (map[fieldName] || (() => ''))();
```

---

### FR-5.4 — `renderEditDiff` — SFTP-Aware XML Rendering

The diff renderer (TRD §4.11) gains an SFTP tag map:

```javascript
const sftp_tagMap = {
  path: 'RemotePath', dsn: 'DSN', skip_list: 'SkipList',
  ignore_list: 'IgnoreList', zip_content_filter: 'ZipContentFilter',
  sme: 'SME', save_location: 'SaveLocation', day_adjust: 'DayAdjust',
  servicer_id: 'ServicerID', name: 'Name',
};
// When xmlType === 'sftp', use sftp_tagMap for tag resolution
const tagMap = (xmlType === 'sftp') ? sftp_tagMap : email_tagMap;
const tag = tagMap[field] || field;
```

---

### FR-5.5 — SFTP Interaction Flow

```
User: "change the remote path on SFTPJob_Wells to /data/bonds/wells/"
  │
  ▼
Stage 1: category=job_config, mode=single_tool
  │
  ▼
Stage 2: routeWithinCategory("job_config")
  LLM produces: { jobName: "SFTPJob_Wells", xmlType: "sftp", field: "path", value: "/data/bonds/wells/" }
  │
  ▼
handleJobEdit("SFTPJob_Wells", "path", "/data/bonds/wells/", ..., xmlType="sftp")
  │
  ├─ job_detail → current RemotePath value
  │
  ├─ stream:
  │   **Before:**
  │   ```xml
  │   <RemotePath>/data/bonds/wells_old/</RemotePath>
  │   ```
  │   **After:**
  │   ```xml
  │   <RemotePath>/data/bonds/wells/</RemotePath>
  │   ```
  │
  ├─ Confirm / Cancel
  │
  ▼
backendCall('edit_job', {jobName, field, value, xmlType: 'sftp'})
  → Python: JobCrudEngine(sftp_settings_path, xml_type='sftp').edit_job(...)
```

---

## 12. Functional Requirements — Epic 6: Command Intelligence

### Current State Reference (Triage and Analyze)

| Fact | Code location | Phase 9 disposition |
|---|---|---|
| `triage_email` tool schema `{prompt: string}` | `participant.js` ~ line 530 | Replace with structured schema |
| `handleTriageCommand` has regex for verify/match/new sub-commands | lines 3036, 3069, 3108 | Regex retained for slash-command path only; tool-call path uses structured params |
| `impact_analysis` tool schema `{prompt: string}` | `participant.js` ~ line 555 | Replace with structured schema |
| `parseChangeIntent()` makes internal LLM call | `participant.js` line ~3339 | Deleted entirely |
| `coverage_gaps` tool schema `{prompt: string}` (optional) | `participant.js` ~ line 510 | Simplify to `{focus: enum('email','sftp','all')}` optional |
| No `analysis_pipeline` in `PIPELINE_DEFINITIONS` | `participant.js` line 355 | New pipeline added |

---

### FR-6.1 — `triage_email` Structured Schema

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "sender":  { "type": "string", "description": "Sender email address to check." },
    "subject": { "type": "string", "description": "Email subject line to check." },
    "msgPath": { "type": "string", "description": "Path to a .msg email file." },
    "mode": {
      "type": "string",
      "enum": ["verify", "match", "new"],
      "description": "verify: full match against all jobs via .msg file. match: quick match by sender/subject. new: analyze unmatched email for job creation. Default: 'match' if sender/subject provided; 'verify' if msgPath provided."
    }
  }
}
```
(No `required` fields — any combination is valid; mode inferred from which params are provided.)

**`executeToolCall` dispatch for `triage_email`:**
```javascript
case 'triage_email': {
  // Build structured request for handleTriageCommand
  const synth = { ...request, prompt: buildTriagePrompt(input) };
  return handleTriageCommand(synth, context, stream, token, shared);
}

function buildTriagePrompt(input) {
  if (input.msgPath) return `${input.mode || 'verify'} ${input.msgPath}`;
  if (input.sender && input.mode === 'new') return `new ${input.sender}`;
  if (input.sender) return `match ${input.sender}`;
  if (input.subject) return `match ${input.subject}`;
  return '';
}
```

This bridges the structured schema to the existing `handleTriageCommand` string-based dispatch without rewriting the handler entirely. The handler's regex sub-command routing is retained as-is; only the entry-point changes.

**Slash command compatibility:** `/triage verify C:\email.msg` still calls `handleTriageCommand` directly from the slash-command router, completely bypassing the tool path.

---

### FR-6.2 — `impact_analysis` Structured Schema

**New schema:**
```json
{
  "type": "object",
  "properties": {
    "changeType": {
      "type": "string",
      "enum": ["delete_job", "rename_did", "change_filter", "move_servicer", "change_servicer_id"],
      "description": "The type of configuration change to simulate."
    },
    "targetJob":       { "type": "string",  "description": "Job name if change affects a job." },
    "targetDid":       { "type": "string",  "description": "ImportDID keyword if change affects a DID." },
    "targetCompanyId": { "type": "number",  "description": "CompanyID / ServicerID if change affects a servicer." },
    "newValue":        { "type": "string",  "description": "New value for rename/change operations." },
    "description":     { "type": "string",  "description": "Human-readable description (shown in output)." }
  },
  "required": ["changeType"]
}
```

**`executeToolCall` dispatch:**
```javascript
case 'impact_analysis': {
  // Build changeSpec directly from structured LLM output
  const changeSpec = {
    change_type:       input.changeType,
    target_job:        input.targetJob        || null,
    target_did:        input.targetDid        || null,
    target_company_id: input.targetCompanyId  || null,
    new_value:         input.newValue         || null,
    raw_description:   input.description      || '',
  };
  const data = await backendCall('analyze_impact', changeSpec, shared);
  ...
}
```

**`parseChangeIntent()` deletion:** This function at `participant.js` line ~3339 is deleted entirely. No internal LLM calls are made for impact analysis after Phase 9.

---

### FR-6.3 — `coverage_gaps` Schema Simplification

**Current (unused):** `{prompt: string}` — the prompt was never interpreted by the backend.

**New:**
```json
{
  "type": "object",
  "properties": {
    "focus": {
      "type": "string",
      "enum": ["email", "sftp", "all"],
      "description": "Which configuration file to check for coverage gaps. Default all."
    }
  }
}
```

**`buildToolArgs` update:**
```javascript
case 'coverage_gaps':
  return { command: 'coverage_gaps', params: { focus: toolInput.focus || 'all' } };
```

---

### FR-6.4 — `analysis_pipeline` Definition

**New entry in `PIPELINE_DEFINITIONS`:**
```javascript
analysis_pipeline: {
  name: 'analysis_pipeline',
  displayName: 'System Analysis',
  triggerDescription:
    'User wants a broad health check, system status, or multi-faceted analysis requiring ' +
    'data from multiple sources (validation + coverage + logs + processing). ' +
    'Examples: "how is the system doing", "full health check", "what\'s broken", ' +
    '"consolidation analysis", "impact analysis".',
  playbook: ANALYSIS_PLAYBOOK,     // new constant
  tools: [
    'validate_email', 'validate_sftp', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'failure_analysis', 'log_performance', 'system_health',
    'job_health', 'daily_summary', 'consolidation_analysis', 'impact_analysis',
  ],
  maxSteps: 8,
},
```

**`ANALYSIS_PLAYBOOK` content:**
```
You are the FRP system analysis agent. Your goal is to give the user a comprehensive picture
of system health and configuration quality by calling relevant tools and synthesizing findings.

STRATEGY:
- For broad health queries ("how is the system"), call: validate_email, validate_sftp, 
  coverage_gaps, failure_analysis, log_performance — then synthesize.
- For focused queries ("what's failing"), call only the relevant subset.
- For impact/consolidation, call the specific tool and provide a risk-rated summary.
- Always prioritize: configuration errors > coverage gaps > performance issues > opportunities.
- Present a prioritized action list with each finding linked to its fix.

REPORTING FORMAT:
- Use section headers for each data domain checked
- Use ✅ / ⚠️ / ❌ status indicators
- Always include an "Action Items" section ranked by severity
```

---

### FR-6.5 — Triage Interaction Flow (Conversational)

```
User: "is this email from reports@wells.com about Q4 bonds monitored?"
  │
  ▼
Stage 1: category=system_admin, mode=single_tool
  │
  ▼
Stage 2: routeWithinCategory("system_admin")
  LLM produces: { sender: "reports@wells.com", subject: "Q4 bonds", mode: "match" }
  │
  ▼
buildTriagePrompt → "match reports@wells.com"
  │
  ▼
handleTriageCommand request.prompt = "match reports@wells.com"
  → regex /^match\b/ matches
  → backendCall('triage_match', {sender: "reports@wells.com"})
  → generateOrFallback → LLM summary of matches
```

```
User: "now check it as a new job"   (next turn referring to same sender)
  │
  ▼
Stage 2 with full history:
  LLM sees prior turn had sender="reports@wells.com"
  LLM produces: { sender: "reports@wells.com", mode: "new" }
  │
  ▼
buildTriagePrompt → "new reports@wells.com"
  → handleTriageCommand → backendCall('triage_new', ...)
```

---

### FR-6.6 — Agentic Health Analysis Flow

```
User: "run a full system health check"
  │
  ▼
Stage 1: mode=pipeline, pipeline=analysis_pipeline
  │
  ▼
reactLoop(analysis_pipeline playbook)
  │
  ├─ Step 1: validate_email      → 3 issues found
  ├─ Step 2: validate_sftp       → 1 issue found
  ├─ Step 3: coverage_gaps       → 2 servicer orphans
  ├─ Step 4: failure_analysis    → 4 failures past 7 days
  ├─ Step 5: log_performance     → CMLTI_Fay at 61% success (outlier)
  │
  ▼
LLM synthesis:
  ## System Health Report

  ❌ **Email Validation** — 3 issues:
  - Blank scrubber on TOWD_PNC_Wells
  - Missing SME on 2 jobs

  ❌ **Coverage** — Servicer 569 has jobs but no DID mapping

  ⚠️ **Processing Failures** — 4 failures in last 7 days (TPMT_SPS ×4)

  ⚠️ **Performance** — CMLTI_Fay at 61% success rate (below 90% threshold)

  ✅ **SFTP Validation** — 1 minor issue (non-blocking)

  ## Action Items (by severity)
  1. 🔴 Fix scrubber on TOWD_PNC_Wells → `/jobs edit TOWD_PNC_Wells set scrubber X`
  2. 🔴 Map servicer 569 in tblExternalDIDRef
  3. 🟡 Investigate TPMT_SPS failure pattern
  4. 🟡 Diagnose CMLTI_Fay 61% success rate
  5. 🟢 Add SME to 2 jobs
```

The user gets a **prioritized, fully cross-referenced health report** instead of a monolithic paragraph. Each finding is actionable and linked to the specific tool or command that resolves it.
