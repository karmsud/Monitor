# Phase 8: System Design
## FRP Agent — ReAct Pipeline Orchestrator (Email Triage Deep Analysis)

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [01_EXECUTIVE_SUMMARY.md](01_EXECUTIVE_SUMMARY.md)

---

## Table of Contents
1. [Module Map](#1-module-map)  
2. [ReAct Loop Architecture](#2-react-loop-architecture)  
3. [Pipeline Definitions](#3-pipeline-definitions)  
4. [Email Triage Pipeline — Detailed Design](#4-email-triage-pipeline--detailed-design)  
5. [Playbook Prompt Design](#5-playbook-prompt-design)  
6. [Tool Subset for Email Triage](#6-tool-subset-for-email-triage)  
7. [ReAct Loop Data Flow](#7-react-loop-data-flow)  
8. [Stage 1 Classifier Update](#8-stage-1-classifier-update)  
9. [Progress Streaming Design](#9-progress-streaming-design)  
10. [Report Compilation Design](#10-report-compilation-design)  
11. [Remediation Offers](#11-remediation-offers)  
12. [Error Handling & Loop Termination](#12-error-handling--loop-termination)  
13. [Message Context Management](#13-message-context-management)  
14. [File Manifest](#14-file-manifest)

---

## 1. Module Map

### Modified Files

| File | Change |
|---|---|
| `extension/chat/participant.js` | Add `reactLoop()`, `executePipelineTool()`, `compilePipelineReport()`, `PIPELINE_DEFINITIONS`, `EMAIL_TRIAGE_PLAYBOOK`, `EMAIL_TRIAGE_TOOLS`. Update `buildClassifierPrompt()` with pipeline trigger definitions. Update `classifyIntent()` to parse `mode`. Update `routeWithToolCalling()` with `mode === 'pipeline'` branch. |

### New Code Elements (All Within `participant.js`)

| Element | Type | Lines Est. | Purpose |
|---|---|---|---|
| `EMAIL_TRIAGE_PLAYBOOK` | `const string` | ~80 | System prompt encoding the 6-step pipeline with branching rules |
| `EMAIL_TRIAGE_TOOLS` | `const string[]` | ~5 | Array of tool names available to the email triage pipeline |
| `PIPELINE_DEFINITIONS` | `const Object` | ~15 | Maps pipeline name → { playbook, tools, maxSteps, triggerDescription } |
| `reactLoop()` | `async function` | ~80 | Generic ReAct THINK→ACT→OBSERVE orchestrator |
| `executePipelineTool()` | `async function` | ~30 | Execute a tool call within the ReAct loop; returns raw JSON result |
| `compilePipelineReport()` | `function` | ~40 | Assembles accumulated step results into structured markdown |

### Modified Code Elements

| Element | Change | Lines Changed |
|---|---|---|
| `buildClassifierPrompt()` | Add pipeline trigger section after category definitions | ~15 added |
| `classifyIntent()` | Parse and return `{ category, mode }` object instead of just category string | ~10 changed |
| `routeWithToolCalling()` | Add `if (mode === 'pipeline')` branch before Stage 2 | ~10 added |

### Untouched Files (Confirmed)

| File | Why Untouched |
|---|---|
| `extension/copilot/tool.js` | `backendCall()` unchanged |
| `extension/package.json` | No new settings |
| `extension/extension.js` | Activation unchanged |
| `cli/main.py` | All CLI commands unchanged |
| `backend/**` | All Python modules unchanged |
| `backend/triage/**` | Triage backend unchanged; ReAct calls individual tools, not `triage_verify` |
| `tests/**` | All tests unchanged |
| `scripts/build.ps1` | Build unchanged |

---

## 2. ReAct Loop Architecture

### Core Loop Pattern

```
reactLoop(prompt, pipelineDef, request, context, stream, token, shared)
     │
     ├── messages = [
     │     systemMessage(pipelineDef.playbook),
     │     userMessage(prompt)
     │   ]
     │
     ├── tools = FRP_TOOLS.filter(t => pipelineDef.tools.includes(t.name))
     │
     ├── stepResults = []   // Accumulated results for final report
     │
     │   ┌─────────── LOOP (max: pipelineDef.maxSteps) ──────────┐
     │   │                                                         │
     │   │  step++                                                 │
     │   │                                                         │
     │   │  response = model.sendRequest(messages, {tools}, token) │
     │   │                                                         │
     │   │  FOR EACH part IN response.stream:                      │
     │   │    │                                                    │
     │   │    ├── IF ToolCallPart:                                 │
     │   │    │   ├── Log: "[FRP] ReAct step N: <tool>(<input>)"   │
     │   │    │   ├── stream.progress("Step N: <description>...")  │
     │   │    │   ├── result = executePipelineTool(tool, input)     │
     │   │    │   ├── stepResults.push({step, tool, input, result}) │
     │   │    │   ├── messages.push(assistantToolCall)              │
     │   │    │   ├── messages.push(toolResultMessage)              │
     │   │    │   └── CONTINUE LOOP                                │
     │   │    │                                                    │
     │   │    └── IF TextPart:                                     │
     │   │        ├── Collect text → finalText                     │
     │   │        └── (text = LLM's final analysis, loop will end) │
     │   │                                                         │
     │   │  IF no tool call was made (only text):                  │
     │   │    └── BREAK (LLM is done reasoning)                    │
     │   │                                                         │
     │   └─────────────────────────────────────────────────────────┘
     │
     ├── IF loop completed without final text (hit maxSteps):
     │   ├── finalText = compilePipelineReport(stepResults)
     │   └── Log: "[FRP] ReAct: hit max steps, compiling partial report"
     │
     ├── stream.markdown(finalText)
     │
     └── Return with follow-up suggestions from remediation analysis
```

### Why This Pattern Works

| Property | Explanation |
|---|---|
| **Natural termination** | The LLM returns text (no tool call) when it decides it has enough information to answer. This is the "I'm done" signal. |
| **Conditional branching** | After each tool result, the LLM reviews the result and decides what to do next. If Step 2 returns "no job found," the LLM reasons about remediation instead of proceeding to Step 3. |
| **Context accumulation** | The messages array grows with each step — the LLM always sees the full history of what it's done and what results came back. This enables coherent multi-step reasoning. |
| **Tool reuse** | The same tools used in Phase 7 single-tool mode are reused here. `executeToolCall()` is called identically. |
| **Graceful cap** | If the LLM doesn't terminate naturally, the maxSteps cap forces a partial report. No infinite loops. |

---

## 3. Pipeline Definitions

### Structure

Each pipeline is defined as an object with:

```javascript
{
  name: 'email_triage',             // Unique identifier
  displayName: 'Email Triage Pipeline',
  triggerDescription: string,       // Description for the Stage 1 classifier
  playbook: string,                 // System prompt with step-by-step guidance
  tools: string[],                  // Array of tool names available in this pipeline
  maxSteps: number,                 // Maximum ReAct iterations (default: 8)
}
```

### Registry

`PIPELINE_DEFINITIONS` is a lookup object mapping pipeline names to their definitions:

```javascript
const PIPELINE_DEFINITIONS = {
  email_triage: {
    name: 'email_triage',
    displayName: 'Email Triage Pipeline',
    triggerDescription: '...', // See Section 8
    playbook: EMAIL_TRIAGE_PLAYBOOK,
    tools: EMAIL_TRIAGE_TOOLS,
    maxSteps: 8,
  },
  // Future pipelines added here:
  // servicer_audit: { ... },
  // deal_onboarding: { ... },
};
```

### Extensibility

Adding a new pipeline requires:
1. Define a new playbook constant (system prompt)
2. Define a curated tool subset
3. Add the pipeline to `PIPELINE_DEFINITIONS`
4. Add a trigger description to `buildClassifierPrompt()`

No changes to `reactLoop()` — it is generic and pipeline-agnostic.

---

## 4. Email Triage Pipeline — Detailed Design

### Pipeline Step Definitions

Each step describes what the LLM should do, which tool(s) to use, and all possible decision branches.

#### Step 1: Email Metadata Extraction

| Aspect | Detail |
|---|---|
| **Input** | User's prompt — either a .msg file path or pasted email metadata |
| **LLM Task** | Extract: sender domain, sender name, mailbox, subject line, attachment filenames, approximate date |
| **Tool Call** | `triage_email` (if .msg file path provided) or NO tool call (if metadata is pasted inline) |
| **Output** | Structured metadata: `{ sender, sender_domain, subject, attachments, date }` |
| **Failure Mode** | .msg file not found → report error, ask user to verify path |

#### Step 2: Job Matching

| Aspect | Detail |
|---|---|
| **Input** | Sender domain from Step 1 |
| **LLM Task** | Find a job configuration that monitors this sender |
| **Tool Call** | `search_jobs` (search by sender domain) |
| **Branch: FOUND** | Extract job name + ServicerID → continue to Step 3 |
| **Branch: NOT FOUND** | Report: "No matching job found for sender domain `X`" |
| **Remediation (if not found)** | Offer: "Would you like to create a new job for this sender?" → follow-up calls `create_job` |
| **Edge Case** | Multiple jobs match → list all matches, recommend the best match (highest ServicerID relevance) |

#### Step 3: DID Lookup

| Aspect | Detail |
|---|---|
| **Input** | ServicerID from Step 2 (used as CompanyID in tblExternalDIDRef) |
| **LLM Task** | Find all DIDs and their ImportDID keywords for this ServicerID |
| **Tool Call** | `deal_lookup` with query = ServicerID (as CompanyID) |
| **Branch: DIDs FOUND** | List all DIDs with their keywords → continue to Step 4 |
| **Branch: NO DIDs** | Report: "Job `<name>` found (ServicerID `<id>`), but no DIDs are configured in tblExternalDIDRef for CompanyID `<id>`" |
| **Remediation (if no DIDs)** | Offer: "Would you like to set up new DIDs for this job?" → follow-up guides DID creation |

#### Step 4: DID Keyword Matching

| Aspect | Detail |
|---|---|
| **Input** | DID keywords from Step 3 + email subject from Step 1 |
| **LLM Task** | Match ImportDID keywords against email subject line to identify which specific DID this email corresponds to |
| **Tool Call** | None — this is pure LLM reasoning (string matching) |
| **Branch: KEYWORD MATCHED** | Report which keyword matched, which DID it belongs to → continue to Step 5 |
| **Branch: NO MATCH** | Report: "DIDs exist but no keyword matches email subject `'<subject>'`" + show existing keywords vs subject |
| **Remediation (if no match)** | Offer: "Would you like to add a new keyword to an existing DID so this email subject is picked up?" |
| **Edge Case** | Multiple keywords match → list all matches, note potential collision |

#### Step 5: Log Verification

| Aspect | Detail |
|---|---|
| **Input** | Job name + matched DID + approximate email date from Step 1 |
| **LLM Task** | Check application logs for evidence of this email being processed |
| **Tool Call** | `job_health` (check job execution history) or `did_failures` (check DID matching failures) or `daily_summary` (check recent activity) |
| **Branch: PROCESSED** | Report: log evidence of successful processing → continue to Step 6 |
| **Branch: JOB MATCHING FAILED** | Report: log details of failure + ask "What more should we investigate?" |
| **Branch: DID MATCHING FAILED** | Report: DID failure details from logs + offer remediation |
| **Branch: NO LOG ENTRIES** | Report: "No log entries found for this job/DID in the time window around `<date>`" |

#### Step 6: Template Staging Verification

| Aspect | Detail |
|---|---|
| **Input** | Job/DID/template identifiers from previous steps |
| **LLM Task** | Check tblTemplateStaging for template run results |
| **Tool Call** | `staging_search` or `template_status` |
| **Branch: NEVER QUEUED** | Report: "Template was supposed to queue but never did" |
| **Branch: QUEUED, WAITING** | Check: StartTime and EndTime are both NULL → Report: "Template is in queue but hasn't been processed yet" |
| **Branch: FAILED** | Check: Comment column → Report: "Template failed with error: `<Comment>`" |
| **Branch: SUCCEEDED** | Report: "Template processed successfully" + show run details (start/end time, result) |

---

## 5. Playbook Prompt Design

### Playbook Structure

The playbook is a structured system prompt that guides the LLM through the pipeline. It uses a directive style: telling the LLM what to do at each step, what tools to use, and how to interpret results.

```
┌──────────────────────────────────────────────────────────────────┐
│  EMAIL_TRIAGE_PLAYBOOK                                           │
│                                                                  │
│  SECTION 1: Your Role                                            │
│    "You are the FRP Email Triage Analyst. You analyze incoming   │
│     emails to determine if they match existing job configs,      │
│     which deals they correspond to, and whether they were         │
│     processed successfully."                                     │
│                                                                  │
│  SECTION 2: Domain Knowledge (condensed)                         │
│    - Three-table pipeline: Settings.xml → tblExternalDIDRef      │
│      → tblTemplateStaging                                        │
│    - ServicerID in Settings.xml = CompanyID in tblExternalDIDRef │
│    - ImportDID keywords in tblExternalDIDRef are matched against  │
│      email subject lines to identify specific deals              │
│                                                                  │
│  SECTION 3: Pipeline Steps (6 steps with branching)              │
│    Step 1: Extract email metadata (sender, subject, attachments) │
│    Step 2: search_jobs to find matching job config               │
│      → Not found? Report + offer create_job                     │
│    Step 3: deal_lookup to find DIDs (CompanyID = ServicerID)     │
│      → No DIDs? Report + offer DID setup                        │
│    Step 4: Match ImportDID keywords against email subject         │
│      → No match? Report + offer add keyword                     │
│    Step 5: Check logs (job_health / did_failures / daily_summary)│
│      → Failures? Report log details                              │
│    Step 6: Check staging (staging_search / template_status)      │
│      → Never queued / waiting / failed / succeeded               │
│                                                                  │
│  SECTION 4: Reporting Rules                                      │
│    - After completing all applicable steps (or hitting a dead     │
│      end), produce a COMPREHENSIVE REPORT                        │
│    - Show what you tried at each step                            │
│    - Show what worked and what didn't                            │
│    - Offer specific remediation for each failure                 │
│    - Use structured markdown: headers, tables, code blocks       │
│    - Data source indicators after each section                   │
│                                                                  │
│  SECTION 5: Important Rules                                      │
│    - Call ONE tool at a time, review result, then decide next     │
│    - If a step fails, do NOT skip to the next dependent step     │
│    - If the user pasted metadata (not a .msg file), work with    │
│      whatever information is provided                            │
│    - If you have enough information to match, proceed; if not,   │
│      ask the user                                                │
│    - When you are done analyzing, produce the final report as    │
│      text (do not call another tool)                             │
└──────────────────────────────────────────────────────────────────┘
```

### Playbook Key Principles

1. **Directive, not conversational.** The playbook tells the LLM "Do step 1, then step 2" — it doesn't ask "What would you like to do?"
2. **Branching is explicit.** Each step has "IF found → ..., IF not found → ..." branches documented.
3. **Tool names are explicit.** The playbook names the exact tools to use at each step.
4. **Stopping conditions are clear.** "When you are done analyzing, produce the final report as text (do not call another tool)" tells the LLM how to signal completion.
5. **Remediation language is provided.** The playbook includes the exact text for remediation offers ("Would you like to create a new job?" etc.) so the LLM uses consistent language.

---

## 6. Tool Subset for Email Triage

### Tool List

```javascript
const EMAIL_TRIAGE_TOOLS = [
  'search_jobs',       // Step 2: Find job by sender domain/attributes
  'job_detail',        // Step 2: Get full job config with ServicerID
  'triage_email',      // Step 1/2: Parse .msg and match (alternative entry point)
  'deal_lookup',       // Step 3: Find DIDs by CompanyID
  'staging_search',    // Step 6: Search tblTemplateStaging
  'template_status',   // Step 6: Check template processing status
  'daily_summary',     // Step 5: Log activity summary
  'job_health',        // Step 5: Job health from logs
  'did_failures',      // Step 5: DID failure details from logs
  'create_job',        // Remediation: create new job
];
```

### Why Each Tool Is Included

| Tool | Pipeline Step | Justification |
|---|---|---|
| `search_jobs` | Step 2 | Primary job-matching tool — search by sender domain, job name |
| `job_detail` | Step 2 | Full job config gives ServicerID, filter details, scrubber info |
| `triage_email` | Step 1/2 | Best entry point when user provides .msg file path — parses and matches in one call |
| `deal_lookup` | Step 3 | DID lookup by CompanyID — the core cross-reference |
| `staging_search` | Step 6 | Search template staging by various criteria |
| `template_status` | Step 6 | Quick template processing status check |
| `daily_summary` | Step 5 | Daily operation summary from logs |
| `job_health` | Step 5 | Job-specific health metrics from logs |
| `did_failures` | Step 5 | DID matching failure details from logs |
| `create_job` | Remediation | When no matching job found, create a new one |

### Why Other Tools Are Excluded

| Tool | Why Excluded |
|---|---|
| `rollback`, `save_settings`, `xml_diff` | Deployment operations — not relevant during email analysis |
| `validate_email`, `validate_sftp` | Configuration validation — not part of email triage |
| `impact_analysis`, `consolidation_analysis` | Admin analytics — not related to single email analysis |
| `orphan_detection`, `collision_detection` | Data integrity checks — tangential to email triage |
| `log_trends`, `log_performance` | Aggregate analytics — email triage needs specific job/date lookups |

---

## 7. ReAct Loop Data Flow

### Message Array Evolution

The messages array is the central state of the ReAct loop. It grows with each iteration:

```
Initial state:
  messages = [
    System("EMAIL_TRIAGE_PLAYBOOK..."),
    User("Analyze this email from reports@fay.com, subject: 'Monthly Report Jan 2026', attachment: FayReport.xlsx")
  ]

After Step 2 (Job Match):
  messages = [
    System("EMAIL_TRIAGE_PLAYBOOK..."),
    User("Analyze this email..."),
    Assistant(ToolCall("search_jobs", {query: "fay.com"})),
    Tool(Result({success: true, data: [{jobName: "CMBS_GreyCo", servicerID: "296", ...}]})),
  ]

After Step 3 (DID Lookup):
  messages = [
    System("EMAIL_TRIAGE_PLAYBOOK..."),
    User("Analyze this email..."),
    Assistant(ToolCall("search_jobs", {query: "fay.com"})),
    Tool(Result({success: true, ...})),
    Assistant(ToolCall("deal_lookup", {query: "296"})),
    Tool(Result({success: true, data: [{DID: "CMLTI 2014-A", ImportDID: "CMLTI", CompanyID: 296, ...}, ...]})),
  ]

After Step 6 (Final — LLM returns text):
  messages = [
    System(...),
    User(...),
    Assistant(ToolCall("search_jobs", ...)),
    Tool(Result(...)),
    Assistant(ToolCall("deal_lookup", ...)),
    Tool(Result(...)),
    Assistant(ToolCall("staging_search", ...)),
    Tool(Result(...)),
    Assistant("## Email Triage Report\n\n### Email Metadata\n...\n### Job Match\n...\n### Deal Coverage\n...\n### Template Status\n...")
  ]
```

### Step Results Accumulation

In parallel with the messages array (which is for the LLM), a `stepResults` array tracks structured data for the `compilePipelineReport()` fallback:

```javascript
stepResults = [
  {
    step: 1,
    tool: 'search_jobs',
    input: { query: 'fay.com' },
    result: { success: true, data: [...] },
    summary: 'Found job CMBS_GreyCo (ServicerID 296)',
  },
  {
    step: 2,
    tool: 'deal_lookup',
    input: { query: '296' },
    result: { success: true, data: [...] },
    summary: 'Found 5 DIDs for CompanyID 296',
  },
  // ...
];
```

This is used only if the loop hits `maxSteps` without the LLM producing a final text report.

---

## 8. Stage 1 Classifier Update

### What Changes in `buildClassifierPrompt()`

After the existing category definitions and disambiguation rules, a new section is added for pipeline triggers:

```
## Pipeline Triggers

Some queries require multi-step analysis across multiple data layers.
If the user's question matches a pipeline trigger, set mode to "pipeline" instead of "single_tool".

**email_triage pipeline:**
- User asks to analyze, triage, or investigate an incoming email
- User provides a .msg file path and asks about it
- User provides email metadata (sender, subject, attachments) and asks if it's monitored, processed, or set up
- User asks "is this email covered?" or "what happens when this email arrives?"
- User says phrases like "trace this email", "check this email", "what job handles this email"
- Category: system_admin (or whichever fits best)

Examples of pipeline triggers:
- "analyze this email from reports@fay.com with subject Monthly Report"
- "triage C:\\emails\\incoming.msg"
- "check if we have a job for this email: sender fay.com, subject Monthly report, attachment FayReport.xlsx"
- "what happens when an email from reports@fay.com arrives?"
- "is this email covered: sender reports@greycapital.com, subject: Deal Summary Q4"
```

### What Changes in `classifyIntent()`

Currently (Phase 7), `classifyIntent()` returns a string (category name) or null. After Phase 8, it returns an object:

```javascript
// Phase 7 return:
return category;  // string

// Phase 8 return:
return { category, mode };  // { string, string }
```

### What Changes in `routeWithToolCalling()`

A new branch is added between Stage 1 and Stage 2:

```javascript
const classification = await classifyIntent(prompt, historyContext, model, token, shared);

if (classification) {
  const { category, mode } = classification;

  if (mode === 'pipeline') {
    // Phase 8: ReAct loop for multi-step pipeline queries
    const pipelineName = 'email_triage'; // For now, only one pipeline
    const pipelineDef = PIPELINE_DEFINITIONS[pipelineName];
    if (pipelineDef) {
      return reactLoop(prompt, pipelineDef, request, context, stream, token, shared);
    }
    // If pipeline not found, fall through to Stage 2
  }

  // Phase 7: Single-tool selection
  const result = await routeWithinCategory(category, prompt, ...);
  if (result !== null) return result;
}

// Fallback
return routeWithAllTools(...);
```

### Backward Compatibility

- Phase 7's `classifyIntent()` returns a string. Phase 8 changes it to return an object `{ category, mode }`.
- All Phase 7 code that uses `category` is updated to destructure: `const { category, mode } = classification;`
- When `mode` is `"single_tool"` (the default), behavior is identical to Phase 7.
- When `mode` is `"pipeline"`, the new ReAct branch activates.
- The fallback to `routeWithAllTools()` still works for any failure.

---

## 9. Progress Streaming Design

### Visual Flow for the User

The user sees real-time progress as the ReAct loop executes:

```
User: @frp analyze this email from reports@fay.com, subject "Monthly Report Jan 2026",
      attachment FayReport.xlsx

Agent: ⏳ Step 1: Extracting email metadata...
       ⏳ Step 2: Searching for matching job configuration...
       ✅ Found job: CMBS_GreyCo (ServicerID 296, Scrubber: CMBS)
       ⏳ Step 3: Looking up DIDs for CompanyID 296...
       ✅ Found 5 DIDs with ImportDID keywords
       ⏳ Step 4: Matching keywords against email subject "Monthly Report Jan 2026"...
       ✅ Keyword match: "Monthly Report" → DID "CMLTI 2014-A"
       ⏳ Step 5: Checking application logs for processing evidence...
       ✅ Log shows successful processing at 2026-01-15 08:42:00
       ⏳ Step 6: Checking template staging results...
       ✅ Template run completed successfully

       ## 📧 Email Triage Report

       ### Email Summary
       | Field | Value |
       |-------|-------|
       | Sender | reports@fay.com |
       | Subject | Monthly Report Jan 2026 |
       | Attachment | FayReport.xlsx |

       ### Job Match ✅
       Matched job **CMBS_GreyCo** (ServicerID 296, Scrubber: CMBS)
       Match type: sender domain (exact)

       ### Deal Coverage ✅
       CompanyID 296 has 5 DIDs in tblExternalDIDRef
       Email subject "Monthly Report Jan 2026" matched DID **CMLTI 2014-A**
       via keyword **"Monthly Report"**

       ### Processing Evidence ✅
       Application logs show this email was processed on 2026-01-15 at 08:42:00
       Job execution: successful

       ### Template Staging ✅
       Template **CMBS** ran successfully
       - Queued: 2026-01-15 08:42:15
       - Started: 2026-01-15 08:42:20
       - Completed: 2026-01-15 08:43:05
       - Result: Success (no errors)

       ### Summary
       ✅ This email is fully covered. Job matched, DID identified, logs confirm
       processing, template ran successfully.
```

### Progress Implementation

```javascript
// During each ReAct step:
stream.progress(`Step ${step}: ${stepDescription}...`);

// After tool result:
if (stepSucceeded) {
  stream.markdown(`✅ ${briefResult}\n`);
} else {
  stream.markdown(`❌ ${briefResult}\n`);
}
```

### Failure Scenario — Visual Flow

```
User: @frp analyze this email from newclient@unknown.com, subject "Q4 Summary"

Agent: ⏳ Step 1: Extracting email metadata...
       ⏳ Step 2: Searching for matching job configuration...
       ❌ No matching job found for sender domain "unknown.com"

       ## 📧 Email Triage Report

       ### Email Summary
       | Field | Value |
       |-------|-------|
       | Sender | newclient@unknown.com |
       | Subject | Q4 Summary |

       ### Job Match ❌
       No existing job configuration monitors sender domain **unknown.com**.

       ### Recommendation
       This email is not currently monitored by any FRP job. To start
       monitoring emails from this sender:

       👉 **Create a new job** — I can help you set up a new email
       monitoring job for `unknown.com` using an existing template.

       [Create new job for unknown.com]  ← follow-up button
```

---

## 10. Report Compilation Design

### Report Structure

The final report is a structured markdown document with these sections:

```markdown
## 📧 Email Triage Report

### Email Summary
[Table: sender, subject, date, attachments]

### Step 1: Job Match [✅ or ❌]
[Job match details or "not found" + remediation]

### Step 2: Deal Coverage [✅ or ❌ or ⏭️ skipped]
[DID lookup results or "no DIDs" + remediation]

### Step 3: Keyword Match [✅ or ❌ or ⏭️ skipped]
[Which keyword matched or "no match" + remediation]

### Step 4: Log Verification [✅ or ❌ or ⏭️ skipped]
[Log evidence or "no log entries" or "failure details"]

### Step 5: Template Staging [✅ or ❌ or ⏭️ skipped]
[Template status: never queued / waiting / failed / succeeded]

### Summary
[Overall assessment + numbered remediation actions]

### Data Sources
[📦 Source indicators for each data layer queried]
```

### Skip Logic

When a step fails, dependent steps are skipped and marked accordingly:

| If This Fails | These Are Skipped | Reason |
|---|---|---|
| Step 2 (no job) | Steps 3, 4, 5, 6 | No ServicerID → can't look up DIDs → can't check logs/staging |
| Step 3 (no DIDs) | Step 4 | No DID keywords to match → keyword matching skipped |
| Step 4 (no keyword match) | Steps 5, 6 still run | Logs and staging might still show activity for the job (even if DID matching is incomplete) |

### compilePipelineReport() — Fallback Only

This function is called only when the ReAct loop hits `maxSteps` without the LLM producing its own final text report. It assembles the `stepResults` array into markdown:

```javascript
function compilePipelineReport(stepResults) {
  // Build markdown from stepResults array
  // Each entry has: step, tool, input, result, summary
  // Render as structured markdown matching the report template
  return markdownReport;
}
```

In the normal case, the LLM produces its own report (guided by the playbook), which is higher quality than the mechanical fallback.

---

## 11. Remediation Offers

### Remediation Actions

| Failure Point | Remediation Offer | Follow-Up Action | Tool Called |
|---|---|---|---|
| No matching job | "Create a new job for this sender" | User clicks → `create_job` via Phase 7 routing | `create_job` |
| Job found, no DIDs | "Set up DIDs for this job" | User clicks → agent guides DID creation discussion | Free-form guidance |
| DIDs exist, no keyword match | "Add keyword to existing DID" | User clicks → agent explains how to add keyword | Free-form guidance |
| Log shows failure | "Investigate further" | User clicks → more detailed log analysis | `job_health` or `did_failures` |
| Template never queued | "Check template configuration" | User clicks → `template_status` deep dive | `template_status` |
| Template failed | "View error details" | User clicks → shows `Comment` column content | `staging_search` |

### Follow-Up Button Implementation

```javascript
const followUps = [];

if (!jobFound) {
  followUps.push({
    prompt: `create a new email job for sender domain ${senderDomain}`,
    label: `Create job for ${senderDomain}`,
  });
}

if (jobFound && !didsFound) {
  followUps.push({
    prompt: `set up DIDs for job ${jobName} with ServicerID ${servicerID}`,
    label: `Set up DIDs for ${jobName}`,
  });
}

if (didsFound && !keywordMatched) {
  followUps.push({
    prompt: `add keyword "${suggestedKeyword}" to DID for job ${jobName}`,
    label: `Add keyword for ${jobName}`,
  });
}

return { followUps };
```

---

## 12. Error Handling & Loop Termination

### Termination Conditions

| Condition | Action |
|---|---|
| LLM returns text (no tool call) | **Normal termination.** Display text as final report. |
| Loop reaches `maxSteps` | **Cap termination.** Call `compilePipelineReport()` to generate partial report from collected results. Log warning. |
| LLM sendRequest() throws error | **Error termination.** Log error. If any steps completed, compile partial report. If no steps completed, fall back to single-tool routing. |
| Tool execution fails | **Soft error.** Log error, append error result to messages, let LLM decide what to do next (it may try a different tool or produce a partial report). |
| Token/cancellation signal | **Cancelled.** Stop immediately, show whatever partial results are available. |

### Error in Tool Execution

When a tool call fails inside the ReAct loop, the error is returned to the LLM as a tool result, not thrown as an exception:

```javascript
try {
  result = await executePipelineTool(toolName, toolInput, ...);
} catch (err) {
  result = { success: false, error: err.message };
}
// Either way, append to messages — LLM sees the error and decides what to do
messages.push(toolResultMessage(result));
```

This allows the LLM to react to errors: "The staging_search call failed with a database error. I'll note this in my report and skip template verification."

---

## 13. Message Context Management

### Token Budget Concerns

Each ReAct iteration adds ~500–2000 tokens to the messages array (tool call + tool result). After 6 iterations, the accumulated context could be 6000–12000 tokens. Combined with the playbook (~800 tokens) and user prompt (~200 tokens), the total could approach 13000 tokens.

This is well within the context window of GPT-4.1 (1M tokens) and Claude models (200K tokens). No truncation is needed for typical pipelines.

### Large Tool Results

Some tools return large JSON results (e.g., `search_jobs` with many matches). To prevent context bloat:

1. **`executePipelineTool()`** (not `executeToolCall()`) returns raw JSON results directly. But the playbook instructs the LLM: "When you receive tool results, focus on the relevant fields. You don't need to reproduce the entire result in your analysis."

2. If a tool result exceeds 4000 tokens, it is truncated to the first 4000 tokens with a `"... (truncated, N more results)"` suffix. This ensures the LLM always sees the most important data.

### Conversation History from Prior Turns

The existing `buildConversationContext()` provides history from previous `@frp` chat turns (before the current pipeline query). This is included in the initial user message:

```javascript
const historyContext = buildConversationContext(context);
const userMessage = historyContext
  ? `Previous conversation context:\n${historyContext}\n\nCurrent question: ${prompt}`
  : prompt;
```

This enables continuity: if the user ran `@frp list all cmbs jobs` in a previous turn, and now says "analyze this email and tell me if it matches one of those jobs," the pipeline has access to the previous results.

---

## 14. File Manifest

### Files Modified

| File | Sections Changed |
|---|---|
| `extension/chat/participant.js` | New constants + functions added; `buildClassifierPrompt()`, `classifyIntent()`, and `routeWithToolCalling()` updated |

### New Constants Added to `participant.js`

| Constant | Approx. Position | Purpose |
|---|---|---|
| `EMAIL_TRIAGE_PLAYBOOK` | After `DOMAIN_KNOWLEDGE` | Playbook system prompt for email triage pipeline |
| `EMAIL_TRIAGE_TOOLS` | After `EMAIL_TRIAGE_PLAYBOOK` | Tool name array for email triage |
| `PIPELINE_DEFINITIONS` | After `EMAIL_TRIAGE_TOOLS` | Pipeline registry mapping name → definition |

### New Functions Added to `participant.js`

| Function | Approx. Position | Purpose |
|---|---|---|
| `reactLoop()` | After `routeWithAllTools()` | Generic ReAct orchestrator |
| `executePipelineTool()` | After `reactLoop()` | Tool execution for ReAct loop (returns raw JSON) |
| `compilePipelineReport()` | After `executePipelineTool()` | Fallback report compilation |

### No New Files Created

All Phase 8 code lives within the existing `extension/chat/participant.js` file. No new files, no new folders, no new dependencies.
