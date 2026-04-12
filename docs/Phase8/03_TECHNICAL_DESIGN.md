# Phase 8: Technical Design
## FRP Agent — ReAct Pipeline Orchestrator

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [02_SYSTEM_DESIGN.md](02_SYSTEM_DESIGN.md)  
**Est. New Lines:** ~280 added, ~10 changed (all within `participant.js`)

---

## Table of Contents
1. [EMAIL_TRIAGE_PLAYBOOK Constant](#1-email_triage_playbook-constant)  
2. [EMAIL_TRIAGE_TOOLS Constant](#2-email_triage_tools-constant)  
3. [PIPELINE_DEFINITIONS Constant](#3-pipeline_definitions-constant)  
4. [reactLoop() Function](#4-reactloop-function)  
5. [executePipelineTool() Function](#5-executepipelinetool-function)  
6. [compilePipelineReport() Function](#6-compilepipelinereport-function)  
7. [buildClassifierPrompt() Update](#7-buildclassifierprompt-update)  
8. [classifyIntent() Update](#8-classifyintent-update)  
9. [routeWithToolCalling() Update](#9-routewithtoolcalling-update)  
10. [Code Placement Within participant.js](#10-code-placement-within-participantjs)  
11. [Complete Diff Summary](#11-complete-diff-summary)

---

## 1. EMAIL_TRIAGE_PLAYBOOK Constant

The playbook is a system prompt injected into the ReAct loop's message array. It tells the LLM what role it plays, what steps to follow, and how to handle branching.

### Exact Code

```javascript
// ---------------------------------------------------------------------------
// Email Triage Pipeline — Playbook (system prompt for ReAct loop)
// ---------------------------------------------------------------------------

const EMAIL_TRIAGE_PLAYBOOK = `You are the FRP Email Triage Analyst. Your job is to analyze an incoming email and trace it through the full FRP processing pipeline: job configuration → deal mapping → log verification → template staging.

## Domain Model (Condensed)

FRP has a three-table pipeline:
- **Settings.xml** — email/SFTP monitoring jobs. Each job has a ServicerID and Filters (sender, subject patterns).
- **tblExternalDIDRef** — deal mapping table. Columns: ItemID, DID, ImportDID (keyword used for matching), CompanyID (= ServicerID in Settings.xml). No DealName or Active flag.
- **tblTemplateStaging** — template processing results. Key columns: TemplateName, FilePath, DID, Dt, StartTime, EndTime, ResultCode, Comments, ServicerID, SourceProcess, Job, DataSource.

ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef). ImportDID keywords are matched against email subject lines to identify which specific deal an email corresponds to.

## Your Analysis Pipeline

Follow these steps IN ORDER. After each tool call, review the result and decide what to do next. If a step fails, do NOT skip to a step that depends on it.

### Step 1: Email Metadata
Extract from the user's message: sender (email/domain), subject line, attachment filenames, approximate date.
- If the user provides a .msg file path, call **triage_email** with `{ prompt: "verify <filepath>" }` — e.g., `{ prompt: "verify C:\\Users\\...\\test_emails\\report.msg" }`. The file will be in the user's `test_emails` workspace folder.
- If the user pastes metadata inline, extract what is available and proceed.
- If critical info is missing (e.g., no sender), note what is missing but continue with what you have.

### Step 2: Job Match
Find which FRP job monitors emails from this sender.
- Call **search_jobs** with the sender domain as query.
- If FOUND: Record the job name, ServicerID, scrubber type. Continue to Step 3.
- If NOT FOUND: Report "No matching job found for sender domain." Offer: "Would you like to create a new job for this sender?" STOP here — do not continue to Step 3.
- If MULTIPLE matches: List all matches. Pick the best match (highest relevance). Continue with that match.

### Step 3: DID Lookup
Find all deals mapped to this job's ServicerID.
- Call **deal_lookup** with the ServicerID from Step 2 (as CompanyID).
- If DIDs FOUND: List the count and ImportDID keywords. Continue to Step 4.
- If NO DIDs: Report "Job found but no DIDs configured for CompanyID <id>." Offer: "Would you like to set up deal mappings for this job?" STOP here for DID-dependent steps.

### Step 4: Keyword Matching (No Tool Call)
Match ImportDID keywords against the email subject from Step 1.
- Compare each ImportDID keyword against the email subject line (case-insensitive substring match).
- If KEYWORD MATCHED: Report which keyword matched and which DID it belongs to. Continue to Step 5.
- If NO MATCH: Report "DIDs exist but no ImportDID keyword matches email subject." Show existing keywords vs. the subject. Offer: "Would you like to add a keyword to an existing DID?"
- If MULTIPLE MATCHES: List all matching keywords. Note potential collision.

### Step 5: Log Verification
Check application logs for evidence of processing. Logs record **individual email events** — each email gets its own processing lines.
- Call **daily_summary** (shows individual email events per day — look for lines matching the sender or subject from Step 1).
- Call **job_health** with the job name to check recent execution health.
- Call **did_failures** if the email may have failed DID matching (rolling window, max 60 days, most recent first).
- Call **deal_activity** with the matched DID from Step 4 to see DID-specific log activity.

Key log event patterns to look for:
- `Processing: <subject>` + `From: <sender>` — confirms the email was seen by the monitor
- `Matched email [<subject>] to [<parser>] parser` — the email was recognized by a configured job
- `Did not find DID mapping for [<filename>]...` — DID match failure (the email was seen but no DID keyword matched)
- `Queue file [<filename>] for [<template>] template` — the email was successfully queued for template processing
- `HashiVault: Retrieved secret` — normal operational line, not an issue

For SFTP logs:
- `Checking SFTP folder for <job_name> (<folder>)...` followed by `Found <N> file(s)` — SFTP scan event
- `Matched DID to [<DID>] and updated save location` — SFTP file matched a DID
- `Did not find DID mapping for [<filename>]...` — same DID failure pattern as email

### Step 6: Template Staging
Check tblTemplateStaging for template run results.
- Call **staging_search** or **template_status** using job/deal identifiers.
- Match rows by `ServicerID` + `SourceProcess` + `Job` + `DataSource`. DataSource format: for email = `<sender_email> <email_subject>`; for SFTP = `SFTPMonitor: <folder_path>` (e.g., `SFTPMonitor: M:\\!Sweeps\\SPS\\In`).

Interpret `StartTime` / `EndTime` / `ResultCode` / `Comments` as follows:
| State | StartTime | EndTime | ResultCode | Comments |
|---|---|---|---|---|
| **Never queued** | *(no row found)* | — | — | — |
| **Queued, not started** | NULL | NULL | — | — |
| **In progress** | NOT NULL | NULL | — | — |
| **Success** | NOT NULL | NOT NULL | 0 | "Ok" |
| **Failed** | NOT NULL | NOT NULL | 1 | error message detail |

## Reporting Rules
When you have enough information (either completed all steps or hit a dead end):
1. Return your FINAL REPORT as text — do NOT call another tool.
2. Use structured markdown: headers, tables, status indicators (✅ ❌ ⏭️).
3. Show what you checked at each step and what the result was.
4. For each failure, offer a specific remediation action.
5. Include a Summary section at the end with overall assessment.
6. Add a Data Sources section listing which tools/tables were queried.

## Important Rules
- Call ONE tool at a time. Review the result before deciding the next step.
- If a step fails, do NOT proceed to steps that depend on its output.
- Steps 5 and 6 can still run even if Step 4 fails (logs/staging may show activity at the job level).
- When you are DONE, produce your final report as text. This signals the loop to end.
- Keep intermediate reasoning brief. Save detail for the final report.`;
```

### Design Notes

- **~80 lines** of structured guidance. Deliberately concise — the LLM doesn't need verbose instructions, it needs clear rules.
- **Tool names are explicit.** The playbook says "Call **search_jobs**" not "search for the job." This eliminates ambiguity.
- **Branching is explicit.** Each step has IF FOUND / IF NOT FOUND branches.
- **Stopping conditions are clear.** "Return your FINAL REPORT as text — do NOT call another tool" is the termination signal.
- **Remediation offers use consistent language.** "Would you like to..." is used at every failure point.
- **Step 4 is tool-free.** Keyword matching is pure LLM reasoning (string comparison). No tool call needed.

---

## 2. EMAIL_TRIAGE_TOOLS Constant

The curated subset of tools available during the email triage pipeline.

### Exact Code

```javascript
// ---------------------------------------------------------------------------
// Email Triage Pipeline — Tool subset
// ---------------------------------------------------------------------------

const EMAIL_TRIAGE_TOOLS = [
  'search_jobs',       // Step 2: Find job by sender domain
  'job_detail',        // Step 2: Full job config with ServicerID
  'triage_email',      // Step 1: Parse .msg file (call with { prompt: "verify <filepath>" })
  'deal_lookup',       // Step 3: Find DIDs by CompanyID
  'staging_search',    // Step 6: Search tblTemplateStaging
  'template_status',   // Step 6: Check template processing status
  'daily_summary',     // Step 5: Individual email event log
  'job_health',        // Step 5: Job health from logs
  'did_failures',      // Step 5: DID failure rolling window (max 60 days)
  'deal_activity',     // Step 5: DID-specific log activity
  'create_job',        // Remediation: create new job
];
```

### Design Notes

- **11 tools** out of 36 total. This is a 69% reduction in tool choices, which significantly reduces LLM confusion.
- **`deal_activity` added** per domain review — provides DID-specific log activity essential for Step 5 when a deal keyword was matched.
- **`create_job` included for remediation.** If no job is found, the LLM can offer to create one and actually execute it within the same pipeline.
- **`triage_email` special case:** This tool routes through `handleTriageCommand()` (not `backendCall()`). In `executePipelineTool()`, when `buildToolArgs()` returns `null` for this tool, the function delegates to the existing `handleTriageCommand` path, passing `{ prompt: "verify <filepath>" }` constructed from `toolInput.prompt`.
- **Tools not included** are deployment tools (`rollback`, `save_settings`, `xml_diff`), validation tools (`validate_email`, `validate_sftp`), admin analytics (`impact_analysis`, `consolidation_analysis`), and aggregate analytics (`log_trends`, `log_performance`). None of these are relevant during single-email analysis.

---

## 3. PIPELINE_DEFINITIONS Constant

Registry mapping pipeline names to their configuration objects.

### Exact Code

```javascript
// ---------------------------------------------------------------------------
// Pipeline Definitions — registry of all ReAct-capable pipelines
// ---------------------------------------------------------------------------

const PIPELINE_DEFINITIONS = {
  email_triage: {
    name: 'email_triage',
    displayName: 'Email Triage Pipeline',
    triggerDescription: [
      'User asks to analyze, triage, or investigate an incoming email',
      'User provides a .msg file path and asks about it',
      'User provides email metadata (sender, subject, attachments) and asks if it is monitored or processed',
      'User asks "is this email covered?" or "what happens when this email arrives?"',
      'User says "trace this email", "check this email", "what job handles this email"',
    ].join('; '),
    playbook: EMAIL_TRIAGE_PLAYBOOK,
    tools: EMAIL_TRIAGE_TOOLS,
    maxSteps: 8,
  },
  // Future pipelines:
  // servicer_audit: { ... },
  // deal_onboarding: { ... },
};
```

### Design Notes

- **`triggerDescription`** is a semicolon-joined string of natural-language trigger patterns. It is injected into `buildClassifierPrompt()` to help Stage 1 detect pipeline queries.
- **`maxSteps: 8`** allows for the 6-step pipeline plus 2 extra iterations for remediation or error recovery.
- **Extensibility:** Adding a new pipeline is pure configuration: define a playbook constant, a tools array, and add an entry to this object. No changes to `reactLoop()`.

---

## 4. reactLoop() Function

The generic ReAct orchestrator. Pipeline-agnostic — it works with any pipeline definition.

### Exact Code

```javascript
/**
 * ReAct (Reasoning + Acting) loop for multi-step pipeline queries.
 *
 * Sends the pipeline's playbook as a system prompt along with the user's
 * question, then iterates: the LLM calls tools one at a time, observes
 * results, and decides what to do next. The loop ends when the LLM
 * produces a text response (its final report) or hits maxSteps.
 *
 * @param {string}  prompt       The user's natural-language question
 * @param {Object}  pipelineDef  Pipeline definition from PIPELINE_DEFINITIONS
 * @param {Object}  request      VS Code ChatRequest
 * @param {Object}  context      VS Code ChatContext
 * @param {Object}  stream       VS Code ChatResponseStream
 * @param {Object}  token        CancellationToken
 * @param {Object}  shared       Shared extension context
 * @returns {Promise<Object>}    ChatResult with optional follow-up suggestions
 */
async function reactLoop(prompt, pipelineDef, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('Unable to select a language model for pipeline analysis.');
    return {};
  }

  // Build scoped tool set from the pipeline's tool list
  const scopedTools = FRP_TOOLS.filter(t => pipelineDef.tools.includes(t.name));

  shared.outputChannel.appendLine(
    `[FRP] ReAct: starting pipeline "${pipelineDef.name}" (max ${pipelineDef.maxSteps} steps, ${scopedTools.length} tools)`
  );

  // Seed the message array with system prompt (playbook) + user question
  const historyContext = buildConversationContext(context);
  const userContent = historyContext
    ? `Previous conversation context:\n${historyContext}\n\nCurrent question: ${prompt}`
    : prompt;

  const messages = [
    vscode.LanguageModelChatMessage.User(
      `${pipelineDef.playbook}\n\n---\n\nUser question: ${userContent}`
    ),
  ];

  const stepResults = []; // Accumulated for compilePipelineReport fallback
  let step = 0;

  // ── Main ReAct loop ──
  while (step < pipelineDef.maxSteps) {
    step++;

    let response;
    try {
      response = await model.sendRequest(messages, { tools: scopedTools }, token);
    } catch (err) {
      shared.outputChannel.appendLine(`[FRP] ReAct: LLM error at step ${step}: ${err.message}`);
      break;
    }

    let toolCallMade = false;
    let finalText = '';

    for await (const part of response.stream) {
      if (part instanceof vscode.LanguageModelToolCallPart) {
        toolCallMade = true;
        const toolName = part.name;
        const toolInput = part.input || {};

        shared.outputChannel.appendLine(
          `[FRP] ReAct step ${step}: ${toolName}(${JSON.stringify(toolInput)})`
        );
        stream.progress(`Step ${step}: calling ${toolName}...`);

        // Execute the tool and capture the result
        let result;
        try {
          result = await executePipelineTool(toolName, toolInput, request, stream, token, shared);
        } catch (err) {
          result = { success: false, error: err.message };
          shared.outputChannel.appendLine(
            `[FRP] ReAct step ${step}: tool error: ${err.message}`
          );
        }

        stepResults.push({
          step,
          tool: toolName,
          input: toolInput,
          result,
        });

        // Append assistant tool-call + tool result to message history
        messages.push(
          vscode.LanguageModelChatMessage.Assistant([
            new vscode.LanguageModelToolCallPart(part.callId, toolName, toolInput)
          ])
        );
        messages.push(
          vscode.LanguageModelChatMessage.Tool(
            part.callId,
            typeof result === 'string' ? result : JSON.stringify(result)
          )
        );

      } else {
        // Text part — the LLM is producing its final answer
        const text = typeof part === 'string' ? part : (part.value || '');
        finalText += text;
      }
    }

    // If no tool was called, the LLM is done — finalText is the report
    if (!toolCallMade) {
      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] ReAct: LLM produced final report at step ${step} (${finalText.length} chars)`
        );
        stream.markdown(finalText);
      } else {
        shared.outputChannel.appendLine('[FRP] ReAct: LLM returned empty response — compiling fallback');
        stream.markdown(compilePipelineReport(stepResults, pipelineDef));
      }
      return buildPipelineResult(stepResults);
    }
  }

  // Hit maxSteps without a final text response
  shared.outputChannel.appendLine(
    `[FRP] ReAct: hit max steps (${pipelineDef.maxSteps}) — compiling partial report`
  );
  stream.markdown(compilePipelineReport(stepResults, pipelineDef));
  return buildPipelineResult(stepResults);
}

/**
 * Build a ChatResult with follow-up suggestions based on pipeline step results.
 * @param {Array} stepResults  Accumulated step results from the ReAct loop
 * @returns {Object} ChatResult with optional followUp array
 */
function buildPipelineResult(stepResults) {
  // Follow-up suggestions are extracted from step results by the LLM
  // in its final report. For now, return an empty result.
  // Future: parse remediation offers from stepResults to create
  // clickable follow-up buttons.
  return {};
}
```

### Design Notes

- **Pipeline-agnostic.** The function has no knowledge of email triage. It works with any `pipelineDef` from `PIPELINE_DEFINITIONS`.
- **Tool-call detection.** The loop iterates the response stream. If a `LanguageModelToolCallPart` is encountered, a tool is executed and the result is fed back. If only text parts are encountered, the LLM is done.
- **Message accumulation.** After each tool call, two messages are appended: the assistant's tool-call message and the tool result message. This is the standard VS Code LLM API pattern for multi-turn tool calling.
- **`stream.progress()`** is used for real-time step indicators. The text is progress-only — it does not become part of the final response.
- **Error handling.** Tool execution errors are caught and returned as `{ success: false, error: ... }` to the LLM, not thrown. The LLM can reason about the error and decide what to do next.
- **Loop termination.** Two paths: (1) LLM returns text → normal exit, (2) `maxSteps` reached → `compilePipelineReport()` fallback.
- **`buildPipelineResult()`** is a placeholder for generating follow-up buttons from pipeline results. Initially returns empty object — the LLM's final text report contains remediation offers as prose.

---

## 5. executePipelineTool() Function

Executes a single tool call within the ReAct loop. Similar to `executeToolCall()` but returns raw JSON instead of streaming markdown.

### Exact Code

```javascript
/**
 * Execute a tool within the ReAct pipeline and return the raw result.
 *
 * Unlike executeToolCall() (which streams formatted markdown to the user),
 * this function returns the raw JSON result so the LLM can process it
 * in the next ReAct iteration.
 *
 * @param {string}  toolName   Name of the tool to execute
 * @param {Object}  toolInput  Input parameters for the tool
 * @param {Object}  request    VS Code ChatRequest
 * @param {Object}  stream     VS Code ChatResponseStream (for progress only)
 * @param {Object}  token      CancellationToken
 * @param {Object}  shared     Shared extension context
 * @returns {Promise<Object>}  Raw tool result (success/error object)
 */
async function executePipelineTool(toolName, toolInput, request, stream, token, shared) {
  // Build the CLI args same way executeToolCall() does
  // This reuses the same parameter extraction logic from the existing switch block
  const tool = FRP_TOOLS.find(t => t.name === toolName);
  if (!tool) {
    return { success: false, error: `Unknown tool: ${toolName}` };
  }

  // Call backendCall() which invokes the Python CLI and returns JSON
  // The exact arguments depend on the tool name — reuse executeToolCall()'s
  // argument-building logic via a shared helper or inline mapping.
  //
  // Implementation note: The simplest approach is to call executeToolCall()
  // but capture its JSON output instead of streaming it. Since executeToolCall()
  // calls backendCall() internally which returns the parsed JSON, we can
  // extract the backendCall() invocation into this function.
  //
  // The exact argument mapping for each tool is already defined in the
  // 36-branch switch statement inside executeToolCall(). Rather than
  // duplicating that switch, Phase 8 implementation will extract the
  // argument-building logic into a shared helper: buildToolArgs(toolName, toolInput)
  // that both executeToolCall() and executePipelineTool() can call.

  const args = buildToolArgs(toolName, toolInput);
  if (!args) {
    return { success: false, error: `Could not build args for tool: ${toolName}` };
  }

  const result = await backendCall(args, shared);

  // Truncate large results to prevent context bloat
  const resultStr = JSON.stringify(result);
  if (resultStr.length > 4000) {
    shared.outputChannel.appendLine(
      `[FRP] ReAct: truncating large tool result (${resultStr.length} chars → 4000)`
    );
    return JSON.parse(resultStr.substring(0, 4000) + '..."}}');
  }

  return result;
}
```

### Key Design Decision: `buildToolArgs()` Helper

The existing `executeToolCall()` contains a 36-branch `switch` statement that maps tool names + inputs to CLI arguments. Phase 8 needs the same mapping but returns raw JSON instead of streaming markdown.

**Solution:** Extract the argument-building logic from `executeToolCall()` into a new helper function:

```javascript
/**
 * Build CLI argument array for a given tool name and input.
 *
 * Extracted from the existing executeToolCall() switch block so that
 * both executeToolCall() (Phase 7 single-tool) and executePipelineTool()
 * (Phase 8 pipeline) can share argument construction logic.
 *
 * @param {string} toolName  Name of the tool
 * @param {Object} toolInput Input parameters from LLM tool call
 * @returns {string[]|null}  CLI argument array, or null if unknown tool
 */
function buildToolArgs(toolName, toolInput) {
  switch (toolName) {
    case 'search_jobs':
      return ['search-jobs', '--query', toolInput.query || '', '--type', toolInput.type || 'email'];
    case 'job_detail':
      return ['job-detail', '--job', toolInput.job_name || '', '--type', toolInput.type || 'email'];
    case 'triage_email':
      // triage_email goes through handleTriageCommand — not backendCall.
      // The prompt must be "verify <filepath>".
      // executePipelineTool() handles this as a special case (see NOTE below).
      return null; // signals special-case routing in executePipelineTool()
    case 'deal_lookup':
      return ['deal-lookup', '--query', toolInput.query || ''];
    case 'staging_search':
      return ['staging-search', '--query', toolInput.query || ''];
    case 'template_status':
      return ['template-status', '--query', toolInput.query || ''];
    case 'daily_summary':
      return ['daily-summary'];
    case 'job_health':
      return ['job-health', '--job', toolInput.job_name || ''];
    case 'did_failures':
      return ['did-failures'];
    case 'create_job':
      return ['create-job', '--template', toolInput.template || '', '--name', toolInput.name || '', '--type', toolInput.type || 'email'];
      case 'deal_activity':
      return ['deal-activity', '--did', toolInput.did || ''];
    // NOTE: 'triage_email' intentionally returns null here.
    // It routes through handleTriageCommand(), not backendCall().
    // executePipelineTool() must detect null + toolName === 'triage_email'
    // and delegate to handleTriageCommand with { prompt: toolInput.prompt }.
    default:
      return null;
  }
}
```

**Refactoring note:** The existing `executeToolCall()` switch block will be updated to delegate to `buildToolArgs()` for argument construction, then handle formatting and streaming separately. This is a refactor, not a behavior change.

---

## 6. compilePipelineReport() Function

Assembles a fallback report from accumulated step results when the LLM hits `maxSteps` without producing its own report.

### Exact Code

```javascript
/**
 * Compile a markdown report from accumulated ReAct step results.
 *
 * Called only when the ReAct loop hits maxSteps without the LLM producing
 * a final text answer. Generates a structured report from the raw
 * tool call/result pairs collected during the loop.
 *
 * @param {Array}  stepResults   Array of { step, tool, input, result }
 * @param {Object} pipelineDef   Pipeline definition (for display name)
 * @returns {string}             Markdown report
 */
function compilePipelineReport(stepResults, pipelineDef) {
  const lines = [
    `## ${pipelineDef.displayName} — Partial Report`,
    '',
    `> ⚠️ Analysis reached the maximum step limit (${pipelineDef.maxSteps}). ` +
    `Results below may be incomplete.`,
    '',
  ];

  if (stepResults.length === 0) {
    lines.push('No tool calls were completed before the limit was reached.');
    return lines.join('\n');
  }

  for (const sr of stepResults) {
    const status = sr.result && sr.result.success !== false ? '✅' : '❌';
    lines.push(`### Step ${sr.step}: ${sr.tool} ${status}`);
    lines.push('');

    // Input parameters
    const inputStr = Object.entries(sr.input)
      .map(([k, v]) => `\`${k}\`: ${v}`)
      .join(', ');
    if (inputStr) {
      lines.push(`**Input:** ${inputStr}`);
    }

    // Result summary
    if (sr.result && sr.result.success === false) {
      lines.push(`**Error:** ${sr.result.error || 'Unknown error'}`);
    } else if (sr.result && sr.result.data) {
      const data = sr.result.data;
      if (Array.isArray(data)) {
        lines.push(`**Result:** ${data.length} record(s) returned`);
      } else {
        lines.push(`**Result:** Data returned successfully`);
      }
    } else {
      lines.push(`**Result:** ${JSON.stringify(sr.result).substring(0, 200)}`);
    }

    lines.push('');
  }

  lines.push('---');
  lines.push('*This is an auto-generated partial report. Ask a follow-up question for additional analysis.*');

  return lines.join('\n');
}
```

### Design Notes

- **Fallback only.** In normal operation, the LLM produces a high-quality report via the playbook guidelines. This function is the safety net.
- **No domain logic.** The function doesn't know what "Step 2: Job Match" means — it just renders tool name + input + result status. This keeps it generic across pipelines.
- **Truncation.** Raw results are capped at 200 chars to keep the fallback report readable.

---

## 7. buildClassifierPrompt() Update

Phase 7's `buildClassifierPrompt()` is updated to include pipeline trigger definitions after the disambiguation rules.

### What Changes

After the `disambiguationRules` array and before the `if (historyContext)` block, insert a new pipeline trigger section:

### Exact Code (Addition Only)

```javascript
  // ── Pipeline triggers (Phase 8) ──
  const pipelineTriggers = Object.values(PIPELINE_DEFINITIONS).map(pd =>
    `**${pd.name}** pipeline: ${pd.triggerDescription}`
  ).join('\n');

  const pipelineSection = [
    '## Pipeline Triggers',
    '',
    'Some queries require multi-step analysis across multiple data layers.',
    'If the user\'s question matches a pipeline trigger below, set mode to "pipeline" and category to "system_admin".',
    '',
    pipelineTriggers,
    '',
    'Examples of pipeline triggers:',
    '- "analyze this email from reports@fay.com with subject Monthly Report" → mode: pipeline',
    '- "triage C:\\\\emails\\\\incoming.msg" → mode: pipeline',
    '- "check if we have a job for this email: sender fay.com, subject Monthly report" → mode: pipeline',
    '- "what happens when an email from reports@fay.com arrives?" → mode: pipeline',
    '- "is this email covered: sender reports@greycapital.com, subject: Deal Summary Q4" → mode: pipeline',
    '',
    'If the query does NOT match a pipeline trigger, set mode to "single_tool" (the default).',
  ].join('\n');
```

And update the `parts` array to include `pipelineSection`:

```javascript
  const parts = [
    'You are classifying a user\'s question ...',
    '',
    '## Categories',
    '',
    categoryDefs,
    '',
    disambiguationRules,
    '',
    pipelineSection,   // ← NEW
    '',
  ];
```

And update the final JSON instruction:

```javascript
  // Before (Phase 7):
  parts.push('Respond with ONLY a JSON object: { "category": "<category_name>", "mode": "single_tool" }');
  parts.push('The mode field must always be "single_tool".');

  // After (Phase 8):
  parts.push('Respond with ONLY a JSON object: { "category": "<category_name>", "mode": "<single_tool|pipeline>" }');
  parts.push('Set mode to "pipeline" if the query matches a pipeline trigger above. Otherwise set mode to "single_tool".');
```

---

## 8. classifyIntent() Update

Phase 7's `classifyIntent()` currently returns a string (category name) or null. Phase 8 changes it to return an object `{ category, mode }` or null.

### What Changes

```javascript
// ── Phase 7 code (to be changed) ──

    const parsed = JSON.parse(jsonText);
    const category = parsed.category;
    // mode field reserved for Phase 8 ReAct pipeline support
    // const mode = parsed.mode || 'single_tool';

    if (!category || !CATEGORY_TOOLS[category]) {
      shared.outputChannel.appendLine(
        `[FRP] Stage 1 unknown category: "${category}" — falling back`
      );
      return null;
    }

    shared.outputChannel.appendLine(`[FRP] Stage 1 result: ${category}`);
    return category;


// ── Phase 8 code (replacement) ──

    const parsed = JSON.parse(jsonText);
    const category = parsed.category;
    const mode = parsed.mode || 'single_tool';

    if (!category || !CATEGORY_TOOLS[category]) {
      shared.outputChannel.appendLine(
        `[FRP] Stage 1 unknown category: "${category}" — falling back`
      );
      return null;
    }

    shared.outputChannel.appendLine(`[FRP] Stage 1 result: ${category} (mode: ${mode})`);
    return { category, mode };
```

### Downstream Impact

Every caller of `classifyIntent()` must be updated to destructure the result:

```javascript
// Phase 7:
const category = await classifyIntent(prompt, historyContext, model, token, shared);
if (category) { ... }

// Phase 8:
const classification = await classifyIntent(prompt, historyContext, model, token, shared);
if (classification) {
  const { category, mode } = classification;
  ...
}
```

Since `classifyIntent()` is only called from `routeWithToolCalling()`, this is exactly one call site.

---

## 9. routeWithToolCalling() Update

The main routing function gets a new `mode === 'pipeline'` branch between Stage 1 and Stage 2.

### What Changes

```javascript
// ── Phase 7 code (to be changed) ──

  const category = await classifyIntent(prompt, historyContext, model, token, shared);

  if (category) {
    const result = await routeWithinCategory(category, prompt, request, context, stream, token, shared);
    if (result !== null) {
      return result;
    }
    shared.outputChannel.appendLine('[FRP] Stage 2 returned null — falling back to full tool set');
  }


// ── Phase 8 code (replacement) ──

  const classification = await classifyIntent(prompt, historyContext, model, token, shared);

  if (classification) {
    const { category, mode } = classification;

    // Phase 8: ReAct pipeline mode
    if (mode === 'pipeline') {
      // Determine which pipeline to use based on category + mode
      // For now, email triage is the only pipeline and it maps from system_admin
      const pipelineName = 'email_triage';
      const pipelineDef = PIPELINE_DEFINITIONS[pipelineName];
      if (pipelineDef) {
        shared.outputChannel.appendLine(
          `[FRP] Routing to ReAct pipeline: ${pipelineDef.displayName}`
        );
        return reactLoop(prompt, pipelineDef, request, context, stream, token, shared);
      }
      // Pipeline not found — fall through to Stage 2
      shared.outputChannel.appendLine(`[FRP] Pipeline "${pipelineName}" not found — falling to Stage 2`);
    }

    // Phase 7: Single-tool mode
    const result = await routeWithinCategory(category, prompt, request, context, stream, token, shared);
    if (result !== null) {
      return result;
    }
    shared.outputChannel.appendLine('[FRP] Stage 2 returned null — falling back to full tool set');
  }
```

### Routing Decision Flow (Complete)

```
User prompt
     │
     ▼
  classifyIntent()  ────→  null? ──→ routeWithAllTools() (36-tool fallback)
     │
     ▼
  { category, mode }
     │
     ├── mode === 'pipeline'?
     │   ├── YES → PIPELINE_DEFINITIONS[pipelineName]
     │   │         ├── found? → reactLoop()  ← Phase 8 path
     │   │         └── not found? → fall through to Stage 2
     │   │
     │   └── NO → routeWithinCategory(category)  ← Phase 7 path
     │            ├── result? → return
     │            └── null? → routeWithAllTools() (fallback)
```

---

## 10. Code Placement Within participant.js

All new code is added to the existing `extension/chat/participant.js` file. The placement follows the existing code structure.

### Insertion Order (Top to Bottom)

```
Line ~98    DOMAIN_KNOWLEDGE         (existing — unchanged)

Line ~NEW   EMAIL_TRIAGE_PLAYBOOK    ← INSERT AFTER DOMAIN_KNOWLEDGE
Line ~NEW   EMAIL_TRIAGE_TOOLS       ← INSERT AFTER EMAIL_TRIAGE_PLAYBOOK
Line ~NEW   PIPELINE_DEFINITIONS     ← INSERT AFTER EMAIL_TRIAGE_TOOLS

Line ~117   FRP_TOOLS                (existing — unchanged)
...
Line ~453   executeToolCall()        (existing — refactored: extract buildToolArgs)

Line ~NEW   buildToolArgs()          ← INSERT BEFORE executeToolCall (extracted from it)

Line ~622   routeWithToolCalling()   (existing — MODIFIED: add pipeline branch)
Line ~NEW   reactLoop()             ← INSERT AFTER routeWithAllTools()
Line ~NEW   executePipelineTool()   ← INSERT AFTER reactLoop()
Line ~NEW   compilePipelineReport() ← INSERT AFTER executePipelineTool()
Line ~NEW   buildPipelineResult()   ← INSERT AFTER compilePipelineReport()
```

### Constants Block

```
SYSTEM_PROMPT            // ~10 → existing
DOMAIN_KNOWLEDGE         // ~98 → existing
EMAIL_TRIAGE_PLAYBOOK    // NEW — after DOMAIN_KNOWLEDGE
EMAIL_TRIAGE_TOOLS       // NEW — after playbook
PIPELINE_DEFINITIONS     // NEW — after tools
FRP_TOOLS                // ~117 → existing
INTENT_CATEGORIES        // Phase 7 — after FRP_TOOLS
CATEGORY_TOOLS           // Phase 7 — after INTENT_CATEGORIES
```

### Functions Block

```
buildToolArgs()           // NEW — extracted from executeToolCall
executeToolCall()         // existing — simplified to use buildToolArgs
buildClassifierPrompt()   // Phase 7 — MODIFIED: add pipeline triggers
classifyIntent()          // Phase 7 — MODIFIED: return { category, mode }
routeWithinCategory()     // Phase 7 — unchanged
routeWithToolCalling()    // Phase 7 — MODIFIED: add pipeline branch
routeWithAllTools()       // Phase 7 — unchanged
reactLoop()               // NEW
executePipelineTool()     // NEW
compilePipelineReport()   // NEW
buildPipelineResult()     // NEW
```

---

## 11. Complete Diff Summary

### New Code (~280 lines)

| Element | Lines | Section |
|---|---|---|
| `EMAIL_TRIAGE_PLAYBOOK` | ~80 | Constants |
| `EMAIL_TRIAGE_TOOLS` | ~12 | Constants |
| `PIPELINE_DEFINITIONS` | ~18 | Constants |
| `reactLoop()` | ~80 | Functions |
| `executePipelineTool()` | ~30 | Functions |
| `compilePipelineReport()` | ~40 | Functions |
| `buildPipelineResult()` | ~10 | Functions |
| `buildToolArgs()` | ~30 | Functions (extracted) |

### Modified Code (~25 lines changed)

| Element | Change | Lines Affected |
|---|---|---|
| `buildClassifierPrompt()` | Add pipeline trigger section + update mode instruction | ~15 added |
| `classifyIntent()` | Parse `mode`, return `{ category, mode }` | ~6 changed |
| `routeWithToolCalling()` | Add `mode === 'pipeline'` branch | ~12 added |
| `executeToolCall()` | Delegate arg-building to `buildToolArgs()` | ~10 changed (simplification) |

### Deleted Code

None. Phase 8 is purely additive.

### Total Impact

- **~305 net new lines** in `participant.js`
- **0 new files**
- **0 backend changes**
- **0 test changes** (new tests added separately — see 05_TESTING_PLAN.md)
