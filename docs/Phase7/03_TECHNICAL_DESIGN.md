# Phase 7: Technical Design
## FRP Agent — Two-Stage Intent Routing Architecture

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [02_SYSTEM_DESIGN.md](02_SYSTEM_DESIGN.md)  
**Est. New Lines:** ~120 added, ~40 removed (all within `participant.js`)

---

## Table of Contents
1. [INTENT_CATEGORIES Constant](#1-intent_categories-constant)  
2. [CATEGORY_TOOLS Constant](#2-category_tools-constant)  
3. [buildClassifierPrompt() Function](#3-buildclassifierprompt-function)  
4. [classifyIntent() Function](#4-classifyintent-function)  
5. [routeWithinCategory() Function](#5-routewithincategory-function)  
6. [routeWithToolCalling() Refactor](#6-routewithtoolcalling-refactor)  
7. [routeWithAllTools() Fallback Function](#7-routewithalltools-fallback-function)  
8. [DOMAIN_KNOWLEDGE Simplification](#8-domain_knowledge-simplification)  
9. [Tool Description Cleanup](#9-tool-description-cleanup)  
10. [Code Placement Within participant.js](#10-code-placement-within-participantjs)  
11. [Complete Diff Summary](#11-complete-diff-summary)

---

## 1. INTENT_CATEGORIES Constant

This constant defines the 6 intent categories that Stage 1 classifies into. It is used by `buildClassifierPrompt()` to construct the classification prompt. It is NOT sent to the LLM as tool definitions — it is rendered as structured text.

### Exact Code

```javascript
// ---------------------------------------------------------------------------
// Intent Categories — Stage 1 classification targets
// ---------------------------------------------------------------------------

const INTENT_CATEGORIES = [
  {
    name: 'deal_mapping',
    displayName: 'Deal & Reference Mapping',
    description: 'Questions about deals, DIDs, ImportDID keywords, CompanyID/ServicerID lookups, and deal-to-job reverse mapping. The answer comes FROM the deal reference table (tblExternalDIDRef) and cross-references to Settings.xml.',
    dataLayer: 'tblExternalDIDRef (MySQL) + cross-reference to Settings.xml',
    examples: [
      'any jobs for deal DID = "ICW MAT TRUST SUBI A1"',
      'which keywords map to servicer 296',
      'do we have coverage for deal CMLTI 2014-A',
      'show me all deals for CompanyID 569',
      'are there orphaned jobs with no deal mapping',
    ],
  },
  {
    name: 'job_config',
    displayName: 'Job Configuration',
    description: 'Searching, listing, filtering, or inspecting email/SFTP monitoring jobs by job-level attributes (job name, scrubber, sender, type). Also creating or editing jobs and validating Settings.xml.',
    dataLayer: 'Settings.xml via SQLite cache',
    examples: [
      'list all cmbs jobs',
      'search jobs by sender "reports@fay.com"',
      'show details for job CMLTI_Fay',
      'validate the email settings',
      'create a new job from CMBS_GreyCo template',
    ],
  },
  {
    name: 'processing',
    displayName: 'Processing & Execution History',
    description: 'Questions about file processing runs, execution status, success/failure analysis, file source tracing, manual vs automated queuing, processing duration, and end-to-end pipeline views. Data comes from tblTemplateStaging.',
    dataLayer: 'tblTemplateStaging (MySQL)',
    examples: [
      'has TPMT_SPS been processed today',
      'show processing history for servicer 296',
      'what templates are failing',
      'trace where file M:\\Data\\report.xlsx came from',
      'pipeline view for deal CMLTI 2014-A',
    ],
  },
  {
    name: 'logs_ops',
    displayName: 'Application Logs & Operations',
    description: 'Questions about application log entries, daily operation summaries, DID lookup failures from logs, job health metrics, activity trends, and performance rankings. Data comes from EmailMonitor/SFTP log files indexed in SQLite.',
    dataLayer: 'Application log files (SQLite-indexed)',
    examples: [
      'show me today\'s daily summary',
      'any DID lookup failures recently',
      'how is job CMBS_GreyCo performing',
      'show log trends for the past week',
      'sync the latest log files',
    ],
  },
  {
    name: 'deployment',
    displayName: 'Deployment & Configuration Management',
    description: 'Saving, deploying, backing up, diffing, or rolling back Settings.xml configuration files.',
    dataLayer: 'Settings.xml backup/deploy system',
    examples: [
      'save the email settings',
      'list available backups',
      'what changed since last deploy',
      'rollback to the previous version',
    ],
  },
  {
    name: 'system_admin',
    displayName: 'System Administration & Analysis',
    description: 'Email triage (is this email monitored?), job consolidation analysis, impact analysis ("what if" scenarios), full system health checks, and agent status.',
    dataLayer: 'Cross-cutting — reads from multiple data layers',
    examples: [
      'triage this email from reports@servicer.com',
      'which jobs could be consolidated',
      'what if we remove servicer 569',
      'run a full system health check',
      'show agent status',
    ],
  },
];
```

### Design Notes

- `name` is the machine identifier. It must match a key in `CATEGORY_TOOLS`.
- `displayName` is used only in log messages for readability.
- `description` is included verbatim in the Stage 1 classifier prompt. It describes what the category OWNS (data layer), not what it sounds like.
- `dataLayer` tells the LLM which data source answers questions in this category.
- `examples` are included in the classifier prompt to give the LLM concrete reference points. These are carefully chosen to include the known ambiguous cases (e.g., "any jobs for deal DID" in `deal_mapping`, not `job_config`).
- The examples are NOT exhaustive. The LLM generalises from them — they serve as calibration anchors, not an allowlist.

---

## 2. CATEGORY_TOOLS Constant

This constant maps each category name to the array of tool names that belong to it. At runtime, the actual tool definition objects are filtered from `FRP_TOOLS`.

### Exact Code

```javascript
// ---------------------------------------------------------------------------
// Category → Tool mapping — determines which tools Stage 2 sees
// ---------------------------------------------------------------------------

const CATEGORY_TOOLS = {
  deal_mapping:  ['deal_lookup', 'servicer_dossier', 'coverage_gaps', 'orphan_detection', 'collision_detection'],
  job_config:    ['search_jobs', 'job_detail', 'validate_email', 'validate_sftp', 'templates', 'create_job', 'edit_job'],
  processing:    ['template_status', 'processing_history', 'failure_analysis', 'source_trace', 'manual_queue', 'processing_duration', 'deal_pipeline', 'staging_search'],
  logs_ops:      ['sync_logs', 'daily_summary', 'did_failures', 'job_health', 'deal_activity', 'log_trends', 'log_performance'],
  deployment:    ['save_settings', 'list_backups', 'xml_diff', 'rollback'],
  system_admin:  ['triage_email', 'consolidation_analysis', 'impact_analysis', 'system_health', 'agent_status'],
};
```

### Validation Rule

Every tool name in `FRP_TOOLS` must appear in exactly one `CATEGORY_TOOLS` array. Every tool name in `CATEGORY_TOOLS` must correspond to a tool in `FRP_TOOLS`. This invariant is not enforced at runtime (to avoid startup overhead) but is verified in the manual QA checklist.

**Total tool assignment check:**
- `deal_mapping`: 5 tools
- `job_config`: 7 tools
- `processing`: 8 tools
- `logs_ops`: 7 tools
- `deployment`: 4 tools
- `system_admin`: 5 tools
- **Sum: 36 tools** (must equal `FRP_TOOLS.length`)

---

## 3. buildClassifierPrompt() Function

Builds the Stage 1 prompt string. This is a pure function with no side effects.

### Exact Code

```javascript
/**
 * Build the Stage 1 intent classification prompt.
 *
 * @param {string} prompt  The user's natural-language question
 * @param {string} historyContext  Conversation history from buildConversationContext()
 * @returns {string} The complete classifier prompt to send to the LLM
 */
function buildClassifierPrompt(prompt, historyContext) {
  const categoryDefs = INTENT_CATEGORIES.map(cat => {
    const examples = cat.examples.map(e => `    - "${e}"`).join('\n');
    return [
      `**${cat.name}** — ${cat.displayName}`,
      `  Description: ${cat.description}`,
      `  Data layer: ${cat.dataLayer}`,
      `  Example prompts:`,
      examples,
    ].join('\n');
  }).join('\n\n');

  const disambiguationRules = [
    '## Disambiguation Rules',
    '- If the user provides a deal name, DID, ImportDID keyword, or CompanyID and asks about jobs, keywords, or setup → deal_mapping (NOT job_config). The answer starts from the deal reference table.',
    '- If the user asks to search, list, or filter jobs by job-level attributes (name, scrubber, sender) → job_config.',
    '- If the user asks about a specific job by name (e.g., "details for CMBS_GreyCo") → job_config.',
    '- If the user says "deals for job X" or "keywords linked to job X" → job_config (job_detail returns linked deals).',
    '- If the user asks about processing runs, failures, duration, or "has X been processed" → processing.',
    '- If the user asks about log entries, daily summary, trends, or performance rankings from logs → logs_ops.',
    '- If the user says "save", "deploy", "backup", "rollback", or "diff" → deployment.',
    '- If the user asks for triage, consolidation, impact, or system health → system_admin.',
    '- If the user says "pipeline view" or "end-to-end" → processing.',
  ].join('\n');

  const parts = [
    'You are classifying a user\'s question about the FRP (File Reception Portal) system into exactly one category.',
    '',
    '## Categories',
    '',
    categoryDefs,
    '',
    disambiguationRules,
    '',
  ];

  if (historyContext) {
    parts.push('## Conversation History');
    parts.push(historyContext);
    parts.push('');
  }

  parts.push(`## User Question`);
  parts.push(prompt);
  parts.push('');
  parts.push('Respond with ONLY a JSON object: { "category": "<category_name>", "mode": "single_tool" }');
  parts.push('The mode field must always be "single_tool".');
  parts.push('Do not explain. Do not include any other text.');

  return parts.join('\n');
}
```

### Design Notes

- **No SYSTEM_PROMPT:** The classifier prompt does not include the 50-line `SYSTEM_PROMPT`. Stage 1 does not need formatting rules or data model rules — it only needs to classify intent. Including SYSTEM_PROMPT would increase token count and dilute the classification task.
- **No DOMAIN_KNOWLEDGE:** Same reason. The category definitions contain all the domain knowledge the classifier needs.
- **Disambiguation rules are explicit:** The known ambiguous cases (especially "jobs for deal X" → `deal_mapping`) are called out as explicit rules. These replace the old 14-point decision tree but are simpler, shorter, and scoped to classification only.
- **Examples are critical:** The LLM calibrates its classification based on example prompts. The examples for `deal_mapping` deliberately include "any jobs for deal DID = X" to anchor this pattern.

---

## 4. classifyIntent() Function

Sends the Stage 1 classification prompt to the LLM, parses the JSON response, and returns the category name. Falls back gracefully on any failure.

### Exact Code

```javascript
/**
 * Stage 1: Classify the user's intent into one of INTENT_CATEGORIES.
 *
 * Sends a lightweight prompt to the LLM (no tools) asking for a JSON
 * response with the category name. Falls back to null on any error
 * (parse failure, unknown category, LLM error).
 *
 * @param {string} prompt          The user's natural-language question
 * @param {string} historyContext  Conversation history string
 * @param {Object} model           The LLM model (from selectModel)
 * @param {Object} token           CancellationToken
 * @param {Object} shared          Shared extension context (for logging)
 * @returns {Promise<string|null>} Category name string, or null on failure
 */
async function classifyIntent(prompt, historyContext, model, token, shared) {
  const classifierPromptText = buildClassifierPrompt(prompt, historyContext);

  const messages = [
    vscode.LanguageModelChatMessage.User(classifierPromptText),
  ];

  try {
    shared.outputChannel.appendLine(`[FRP] Stage 1: classifying intent for: "${prompt}"`);

    const response = await model.sendRequest(messages, {}, token);

    // Collect the full text response
    let responseText = '';
    for await (const part of response.stream) {
      if (typeof part === 'string') {
        responseText += part;
      } else if (part.value && typeof part.value === 'string') {
        responseText += part.value;
      }
    }

    responseText = responseText.trim();
    shared.outputChannel.appendLine(`[FRP] Stage 1 raw response: ${responseText}`);

    // Strip markdown code fences if the LLM wraps the JSON in them
    let jsonText = responseText;
    const fenceMatch = responseText.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenceMatch) {
      jsonText = fenceMatch[1].trim();
    }

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

  } catch (err) {
    shared.outputChannel.appendLine(
      `[FRP] Stage 1 error: ${err.message} — falling back`
    );
    return null;
  }
}
```

### Design Notes

- **No tools in sendRequest:** Stage 1 sends `{}` as options (no tools). This is a pure text classification call, which is faster than a tool-calling call.
- **Markdown fence stripping:** Some LLMs wrap JSON in `` ```json ``` `` blocks even when asked not to. The function strips these before parsing.
- **Returns null on ANY failure:** This is the fallback signal. The caller (`routeWithToolCalling()`) falls back to the full 36-tool single-stage router when `classifyIntent()` returns null.
- **Logging:** Both the raw LLM response and the parsed category are logged. This enables post-incident debugging of misclassifications without needing to reproduce the issue.
- **Response stream iteration:** The LLM response stream may yield `string` parts or `TextPart` objects with a `.value` property. The function handles both cases.

---

## 5. routeWithinCategory() Function

Stage 2: sends a category-scoped tool set to the LLM for tool selection. This function is structurally similar to the current `routeWithToolCalling()` but with fewer tools.

### Exact Code

```javascript
/**
 * Stage 2: Route within a classified category using scoped tool-calling.
 *
 * Filters FRP_TOOLS to only the tools in the given category, then sends
 * the prompt to the LLM with this reduced tool set.
 *
 * @param {string} category  The category from Stage 1 (e.g., "deal_mapping")
 * @param {string} prompt    The user's question
 * @param {Object} request   VS Code ChatRequest
 * @param {Object} context   VS Code ChatContext
 * @param {Object} stream    VS Code ChatResponseStream
 * @param {Object} token     CancellationToken
 * @param {Object} shared    Shared extension context
 * @returns {Promise<Object|null>} ChatResult if handled, null if no tool selected
 */
async function routeWithinCategory(category, prompt, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) return null;

  const toolNames = CATEGORY_TOOLS[category];
  const scopedTools = FRP_TOOLS.filter(t => toolNames.includes(t.name));

  shared.outputChannel.appendLine(
    `[FRP] Stage 2: routing within ${category} (${scopedTools.length} tools: ${toolNames.join(', ')})`
  );

  const historyContext = buildConversationContext(context);

  const categoryDef = INTENT_CATEGORIES.find(c => c.name === category);
  const categoryContext = categoryDef
    ? `You are routing within the "${categoryDef.displayName}" category. ${categoryDef.description}`
    : '';

  const routingPrompt = [
    SYSTEM_PROMPT,
    '',
    DOMAIN_KNOWLEDGE,
    '',
    categoryContext,
    '',
    'Select the best tool and extract the correct parameters from the prompt.',
    'You MUST call exactly one tool.',
    'For numeric IDs (CompanyID, ServicerID), extract ONLY the number (e.g. "296"), not the label.',
    'If the user references previous results, extract identifiers from conversation history below.',
    '',
    historyContext ? historyContext + '\n' : '',
    `User question: ${prompt}`,
  ].join('\n');

  const messages = [
    vscode.LanguageModelChatMessage.User(routingPrompt),
  ];

  const toolModeRequired = vscode.LanguageModelChatToolMode
    ? vscode.LanguageModelChatToolMode.Required
    : undefined;

  const sendOptions = { tools: scopedTools };
  if (toolModeRequired !== undefined) {
    sendOptions.toolMode = toolModeRequired;
  }

  try {
    const response = await model.sendRequest(messages, sendOptions, token);

    for await (const part of response.stream) {
      if (part instanceof vscode.LanguageModelToolCallPart) {
        shared.outputChannel.appendLine(
          `[FRP] Stage 2 selected: ${part.name}(${JSON.stringify(part.input)})`
        );
        return executeToolCall(part.name, part.input || {}, request, context, stream, token, shared, prompt);
      }
    }

    shared.outputChannel.appendLine('[FRP] Stage 2: no tool selected — falling back');
    return null;

  } catch (err) {
    shared.outputChannel.appendLine(`[FRP] Stage 2 error: ${err.message}`);
    return null;
  }
}
```

### Design Notes

- **`scopedTools` filtering:** `FRP_TOOLS.filter(t => toolNames.includes(t.name))` creates a new array with only the tools in this category. The original `FRP_TOOLS` array is not modified.
- **`categoryContext` injection:** The Stage 2 prompt tells the LLM which category domain it is operating in. This provides additional disambiguation context.
- **`SYSTEM_PROMPT` + `DOMAIN_KNOWLEDGE` included:** Unlike Stage 1 (which is a pure classifier), Stage 2 needs the data model context to extract correct parameters. The simplified `DOMAIN_KNOWLEDGE` (without the decision tree) provides the three-table pipeline and cross-reference chains.
- **`toolMode: Required`:** Same as the current implementation — the LLM MUST select a tool.
- **`selectModel()` called again:** The model may have been garbage-collected between Stage 1 and Stage 2 calls. The function is fast (uses cached request.model when available).
- **Error handling:** Returns null on any failure, which causes the caller to fall back.

---

## 6. routeWithToolCalling() Refactor

The current `routeWithToolCalling()` function is refactored to orchestrate Stage 1 → Stage 2, with fallback to the old single-stage logic.

### Exact Code

```javascript
/**
 * Route a natural-language prompt through Two-Stage Intent Routing.
 *
 * Stage 1: Classify intent into one of 6 categories (lightweight LLM call).
 * Stage 2: Select tool from category-scoped tool subset (tool-calling LLM call).
 * Fallback: If Stage 1 fails, use the full 36-tool single-stage router.
 *
 * @returns {Promise<Object|null>} ChatResult if handled, null if LLM declined tools
 */
async function routeWithToolCalling(prompt, request, context, stream, token, shared) {

  // ── Guard: check that the tool-calling API classes exist ──
  if (typeof vscode.LanguageModelToolCallPart === 'undefined') {
    shared.outputChannel.appendLine(
      '[FRP] LanguageModelToolCallPart is not available — skipping tool-calling'
    );
    return null;
  }

  const model = await selectModel(request);
  if (!model) {
    shared.outputChannel.appendLine('[FRP] No model available — skipping tool-calling');
    return null;
  }

  if (model.capabilities && model.capabilities.toolCalling === false) {
    shared.outputChannel.appendLine(
      `[FRP] Model "${model.name || model.family}" does not support tool-calling — skipping`
    );
    return null;
  }

  const historyContext = buildConversationContext(context);

  // ── Stage 1: Intent Classification ──
  const category = await classifyIntent(prompt, historyContext, model, token, shared);

  if (category) {
    // ── Stage 2: Category-Scoped Tool Selection ──
    const result = await routeWithinCategory(category, prompt, request, context, stream, token, shared);
    if (result !== null) {
      return result;
    }
    // Stage 2 failed — fall through to full tool set
    shared.outputChannel.appendLine('[FRP] Stage 2 returned null — falling back to full tool set');
  }

  // ── Fallback: single-stage router with all 36 tools ──
  shared.outputChannel.appendLine('[FRP] Falling back to routeWithAllTools()');
  return routeWithAllTools(prompt, request, context, stream, token, shared, historyContext, model);
}
```

### What Changed from Current

| Aspect | Current Code | New Code |
|---|---|---|
| Regex pre-routing | 2 patterns + `if (dealMatch)` block | **Removed entirely** |
| Main logic | Builds one prompt, sends 36 tools | Calls `classifyIntent()` → `routeWithinCategory()` |
| Fallback | None (LLM picks wrong tool silently) | `routeWithAllTools()` preserves current single-stage behavior |
| Guard checks | Same | **Unchanged** — same 3 guard checks preserved |
| `buildConversationContext()` | Called once | Called once, result passed to both stages |

---

## 7. routeWithAllTools() Fallback Function

This function contains the **exact current logic** from `routeWithToolCalling()` — the single-stage 36-tool router. It is called only when Stage 1 fails.

### Exact Code

```javascript
/**
 * Fallback: Single-stage router using full FRP_TOOLS array (36 tools).
 *
 * This is the CURRENT routing logic, preserved as a fallback.
 * Called when Stage 1 classification fails (bad JSON, unknown category, error).
 *
 * @returns {Promise<Object|null>} ChatResult if handled, null if LLM declined tools
 */
async function routeWithAllTools(prompt, request, context, stream, token, shared, historyContext, model) {
  const routingPrompt = [
    SYSTEM_PROMPT,
    '',
    DOMAIN_KNOWLEDGE,
    '',
    'You are routing the user\'s question to the correct backend tool.',
    'Use the data model above to select the BEST tool.',
    'You MUST call exactly one tool. Extract the correct parameters from the prompt.',
    'For numeric IDs (CompanyID, ServicerID), extract ONLY the number (e.g. "296"), not the label.',
    'If the user references previous results, extract identifiers from conversation history below.',
    '',
    historyContext ? historyContext + '\n' : '',
    `User question: ${prompt}`,
  ].join('\n');

  const messages = [
    vscode.LanguageModelChatMessage.User(routingPrompt),
  ];

  const toolModeRequired = vscode.LanguageModelChatToolMode
    ? vscode.LanguageModelChatToolMode.Required
    : undefined;

  const sendOptions = { tools: FRP_TOOLS };
  if (toolModeRequired !== undefined) {
    sendOptions.toolMode = toolModeRequired;
  }

  try {
    shared.outputChannel.appendLine(
      `[FRP] routeWithAllTools: sending request (model=${model.name || model.family}, tools=${FRP_TOOLS.length})`
    );

    const response = await model.sendRequest(messages, sendOptions, token);

    for await (const part of response.stream) {
      if (part instanceof vscode.LanguageModelToolCallPart) {
        shared.outputChannel.appendLine(
          `[FRP] routeWithAllTools selected: ${part.name} input=${JSON.stringify(part.input)}`
        );
        return executeToolCall(part.name, part.input || {}, request, context, stream, token, shared, prompt);
      }
    }

    shared.outputChannel.appendLine('[FRP] routeWithAllTools: no tool selected');
    return null;

  } catch (err) {
    shared.outputChannel.appendLine(`[FRP] routeWithAllTools error: ${err.message}`);
    return null;
  }
}
```

### Design Notes

- This function is a direct extraction of the current `routeWithToolCalling()` body (after the guard checks), minus the regex pre-routing block.
- The regex pre-routing is NOT preserved in the fallback. It was a band-aid that didn't work — there is no value in keeping it as a fallback.
- The `historyContext` and `model` are passed as parameters (already computed by the caller) to avoid re-computing them.
- The routing prompt uses `DOMAIN_KNOWLEDGE` (simplified — no decision tree), not the old version with the decision tree.

---

## 8. DOMAIN_KNOWLEDGE Simplification

The current `DOMAIN_KNOWLEDGE` constant has two sections:
1. **Three-Table Pipeline + Cross-Reference Chains** (kept)
2. **Tool Selection Decision Tree (points 1–14)** (removed)

### What Gets Removed

The entire "Tool Selection Decision Tree" section, from the line "### Tool Selection Decision Tree" to the end of the constant (the line with `14. User asks about configuration health...`). This is approximately 30 lines.

### Current Text (to be removed)

```
### Tool Selection Decision Tree
When choosing a tool, determine WHAT DATA the user needs, then pick the tool that owns that data:

1. User mentions a specific job name → job_detail (returns config + linked deals + keywords)
2. User asks to search/list/find/filter multiple jobs BY JOB attributes (name, scrubber, sender) → search_jobs
3. User asks about deals, keywords, DID, or ImportDID for a JOB NAME → job_detail (NOT deal_lookup — it resolves ServicerID→deals)
4. User provides a deal name (DID), ImportDID keyword, or CompanyID/ServicerID number and asks which jobs serve it, what keywords map to it, or which template will be queued → deal_lookup
   IMPORTANT: If the user says "DID", "deal", or provides a deal name (e.g. "ICW MAT TRUST SUBI A1", "CMLTI 2014-A") → ALWAYS use deal_lookup, even if they also say "jobs" or "keyword". The question is about a DEAL, not about searching jobs.
5. User asks about processing runs, execution, success, failure for a job/template → processing_history or template_status
6. User asks "what's failing" or error analysis → failure_analysis
7. User references "the above", "those jobs", "these results" → extract the relevant identifiers (ServicerID, TemplateName, job name) from conversation history, then pick the tool for what they're NOW asking about
8. User asks about coverage gaps or missing configs → coverage_gaps
9. User asks about orphaned jobs → orphan_detection
10. User asks for end-to-end / full pipeline / combined view → deal_pipeline
11. User asks about processing speed / slow / duration → processing_duration
12. User asks about manual queuing or automation gaps → manual_queue
13. User asks to trace a specific file → source_trace
14. User asks about configuration health or system status → system_health or agent_status
```

### Resulting DOMAIN_KNOWLEDGE (after removal)

The `DOMAIN_KNOWLEDGE` constant retains only the data model reference:

```javascript
const DOMAIN_KNOWLEDGE = `## FRP Data Model Reference

### Three-Table Pipeline
The FRP system has three interconnected data layers:

1. **Settings.xml** — Job Configuration Layer
   - Email/SFTP monitoring job definitions (one XML element per job)
   - Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation

2. **tblExternalDIDRef** — Deal Reference Layer (MySQL)
   - Maps CompanyID → DealID (DID) + ImportDID (the keyword the system searches for in emails/files)
   - Key relationship: Job.ServicerID = tblExternalDIDRef.CompanyID

3. **tblTemplateStaging** — Processing Execution History (MySQL)
   - Every file the system has ever processed: timestamp, scrubber/template, success/failure, duration, filepath
   - Relationships: TemplateName = job's scrubber; DID/ServicerID link to deals

### Cross-Reference Chains (how tables connect)
- Job→Deals: ServicerID → tblExternalDIDRef.CompanyID → all deals
- Deal→Jobs: CompanyID → Settings.xml jobs that use it as ServicerID
- Job→Processing: processing history by scrubber/TemplateName or ServicerID
- Deal→Processing: processing history by DID
- Full pipeline: all three layers combined for one entity`;
```

### Why the Decision Tree Is Removed

The decision tree was an attempt to teach the LLM correct routing through text instructions. It did not work — the LLM still selected `search_jobs` for DID queries despite explicit "IMPORTANT" clauses. The two-stage architecture replaces this approach entirely:
- **Stage 1** handles the "which domain?" question (what the decision tree tried to do)
- **Stage 2** handles the "which tool?" question (with a much smaller candidate set)

The data model reference (Three-Table Pipeline + Cross-Reference Chains) is still useful for Stage 2 tool selection — it tells the LLM how tables are connected, which helps it extract correct parameters.

---

## 9. Tool Description Cleanup

Several tool descriptions were bloated with negative constraints and cross-references as routing fix attempts. These are cleaned to be affirmative and concise.

### search_jobs — Before

```
'Search, list, or filter email/SFTP monitoring jobs by job-level attributes (job name, scrubber, sender, servicer category like "CMBS"). Do NOT use this when the user provides a deal name (DID) or asks about deal-to-job mapping — use deal_lookup for that instead.'
```

### search_jobs — After

```
'Search, list, or filter email/SFTP monitoring jobs by job-level attributes (job name, scrubber, sender, servicer category like "CMBS").'
```

### deal_lookup — Before

```
'Reverse lookup: find deals and their linked jobs by deal name (DID), ImportDID keyword, or CompanyID/ServicerID number. ALWAYS USE THIS when the user mentions a deal name/DID (e.g. "ICW MAT TRUST SUBI A1", "CMLTI 2014-A") and asks about jobs, keywords, or setup — even if they say "any jobs" or "keyword setup". Also use when user provides a numeric ServicerID to see all deals. Returns both tblExternalDIDRef matches AND any Settings.xml jobs that serve them. NOTE: If the user asks by *job name* (not a DID), use job_detail instead.'
```

### deal_lookup — After

```
'Reverse lookup: find deals and their linked jobs by deal name (DID), ImportDID keyword, or CompanyID/ServicerID number. Returns both tblExternalDIDRef matches AND any Settings.xml jobs that serve them.'
```

### Why This Is Safe Now

In the current single-stage architecture, these negative constraints were (unsuccessful) attempts to help the LLM discriminate among 36 tools. In the two-stage architecture:
- `search_jobs` is only visible in Stage 2 when the category is `job_config`
- `deal_lookup` is only visible in Stage 2 when the category is `deal_mapping`
- They are **never in the same tool set** during Stage 2. There is no need for cross-references like "use deal_lookup instead" because the LLM never sees both tools at once.

### Other Tool Descriptions (No Changes)

All other tool descriptions are already clean and affirmative. No changes needed for the remaining 34 tools.

---

## 10. Code Placement Within participant.js

All new code is placed in a logical location within the existing file structure. No handler functions, no backend code, and no imports change.

### Current File Structure (Relevant Sections)

```
Line     1:  const vscode = require('vscode');
Line    10:  const SYSTEM_PROMPT = `...`;
Line    98:  const DOMAIN_KNOWLEDGE = `...`;
Line   117:  const FRP_TOOLS = [...];
Line   451:  // ---------------------------------------------------------------------------
Line   453:  async function executeToolCall(...) { ... }
Line   622:  async function routeWithToolCalling(...) { ... }
Line   715:  // ---------------------------------------------------------------------------
Line   717:  const MODEL_PREFERENCE = [...];
             ...handler functions...
             ...activation code...
```

### New File Structure (After Phase 7)

```
Line     1:  const vscode = require('vscode');
Line    10:  const SYSTEM_PROMPT = `...`;                            ← UNCHANGED
Line    98:  const DOMAIN_KNOWLEDGE = `...`;                         ← SIMPLIFIED (decision tree removed)
Line   117:  const FRP_TOOLS = [...];                                ← DESCRIPTIONS CLEANED
Line   ~450: const INTENT_CATEGORIES = [...];                        ← NEW
Line   ~530: const CATEGORY_TOOLS = {...};                           ← NEW
Line   ~545: function buildClassifierPrompt(prompt, historyContext) { ... } ← NEW
Line   ~590: async function classifyIntent(prompt, historyContext, model, token, shared) { ... } ← NEW
Line   ~640: // ---------------------------------------------------------------------------
Line   ~642: async function executeToolCall(...) { ... }             ← UNCHANGED
Line   ~810: async function routeWithinCategory(category, prompt, ...) { ... } ← NEW
Line   ~870: async function routeWithAllTools(prompt, ...) { ... }   ← NEW (extracted from old routeWithToolCalling)
Line   ~920: async function routeWithToolCalling(prompt, ...) { ... } ← MODIFIED (orchestrator)
Line   ~970: // ---------------------------------------------------------------------------
Line   ~972: const MODEL_PREFERENCE = [...];                         ← UNCHANGED
             ...handler functions...                                  ← ALL UNCHANGED
             ...activation code...                                    ← UNCHANGED
```

### Placement Rationale

- `INTENT_CATEGORIES` and `CATEGORY_TOOLS` are placed immediately after `FRP_TOOLS` because they reference tool names from that array.
- `buildClassifierPrompt()` and `classifyIntent()` are placed before `executeToolCall()` because they are called before tool execution.
- `routeWithinCategory()` and `routeWithAllTools()` are placed after `executeToolCall()` because they call it.
- `routeWithToolCalling()` remains in its current position but with new orchestrator logic.

---

## 11. Complete Diff Summary

### Lines Added (~120)

| Element | Approx. Lines |
|---|---|
| `INTENT_CATEGORIES` constant | 70 |
| `CATEGORY_TOOLS` constant | 10 |
| `buildClassifierPrompt()` function | 35 |
| `classifyIntent()` function | 45 |
| `routeWithinCategory()` function | 55 |
| `routeWithAllTools()` function (extracted from old code) | 40 |
| New `routeWithToolCalling()` body | 25 |
| Log statements | 8 |
| **Total added** | **~288** |

### Lines Removed (~175)

| Element | Approx. Lines |
|---|---|
| Decision tree in `DOMAIN_KNOWLEDGE` | 30 |
| Regex pre-routing block (`dealIntentRe`, `dealIntent2`, `if (dealMatch)`) | 10 |
| Negative constraint clauses in `search_jobs` and `deal_lookup` descriptions | 5 |
| Old `routeWithToolCalling()` body (replaced by new orchestrator + extracted `routeWithAllTools()`) | 60 |
| Routing instructions previously in `routeWithToolCalling()` prompt | 5 |
| **Total removed** | **~110** |

### Net Change

**~+178 lines** within a single file (`participant.js`). The file grows from approximately 3,100 lines to approximately 3,280 lines.

### Files Untouched (Explicit Confirmation)

- `extension/copilot/tool.js` — Zero changes
- `extension/extension.js` — Zero changes
- `extension/package.json` — Zero changes
- `cli/main.py` — Zero changes
- `backend/**` — Zero changes
- `tests/**` — Zero changes
- `config/**` — Zero changes
- `scripts/build.ps1` — Zero changes
- `docs/Phase1-6/**` — Zero changes
