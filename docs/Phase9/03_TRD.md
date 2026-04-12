# Phase 9 TRD — Technical Requirements Document
## FRP Agent VS Code Extension — Conversational Intelligence Upgrade

**Document type:** Technical Requirements Document  
**Parent:** Phase 9 PRD (`01_PRD.md`), FRD (`02_FRD.md`)  
**Status:** Draft  
**Date:** March 7, 2026

---

## 1. Purpose

This document specifies exactly which files and functions change, what the before/after code looks like for each change, and the precise sequencing of implementation. Every story from the PRD is mapped to one or more concrete code changes with file paths, line numbers, and test requirements.

---

## 2. Affected Files

| File | Change type | Stories |
|---|---|---|
| `extension/chat/participant.js` | Modify (3000+ line file — targeted edits only) | S-101–S-103, S-201–S-203, S-302–S-303, S-401–S-403, S-501–S-503, S-601–S-603 |
| `extension/test/` | New test files | All S-xxx stories |
| `backend/xml/crud.py` | **No changes required** — SFTP support (SFTP_FIELD_MAP, JobCrudEngine xml_type='sftp') already fully implemented | S-501–S-503 (extension changes only) |

---

## 3. Implementation Sequence

The four epics must be implemented in this order because later epics depend on earlier ones:

```
Epic 1 (Structured Schemas)
  → required by Epic 2 (History) because structured schema + history = contextual resolution
  → required by Epic 3 (Confirmation) because confirmation wraps handler calls
  → required by Epic 4 (CRUD pipeline) because pipeline calls handlers

Epic 2 (History)
  → standalone; can be done in parallel with Epic 1

Epic 3 (Confirmation)
  → depends on Epic 1 (handlers must accept structured params before wrapping them)

Epic 4 (CRUD Pipeline)
  → depends on Epics 1, 2, 3
```

**Recommended order:** 1A (schema), 1B (handler refactor), 2 (history), 3 (confirmation), 4 (pipeline), 5 (SFTP), 6 (command intelligence)

**Epic 5 (SFTP CRUD Parity)** depends on Epic 1 completing first — the `xmlType` field is an extension to the `edit_job` / `create_job` schemas that Epic 1 introduces. Epic 5 adds `xmlType` + SFTP field names to those schemas and extends the helper functions. Zero backend changes are needed (backend already supports SFTP via `SFTP_FIELD_MAP` and `JobCrudEngine(xml_type='sftp')`).

**Epic 6 (Command Intelligence)** depends on:
- **Epic 1** — structured schemas for `triage_email` and `impact_analysis` follow the same pattern established in Epic 1
- **Epic 2** — the conversational triage flow uses history to resolve "check it as new" followups
- **Epic 4** — `analysis_pipeline` is a new `PIPELINE_DEFINITIONS` entry (same mechanism as `crud_planning`)

```
Epic 1 (Structured Schemas + Handler Refactor)
  → Epic 3 (Confirmation) — handlers must accept structured params before wrapping
  → Epic 5 (SFTP) — extends Epic 1 schemas with xmlType + SFTP fields

Epic 2 (History) — standalone; can run in parallel with Epic 1

Epic 4 (CRUD Pipeline) — depends on Epics 1, 2, 3
  → Epic 6 (Command Intelligence) — analysis_pipeline requires Epic 4 pipeline mechanism
```

---

## 4. Epic 1 Technical Specification — Structured Tool Schemas

### 4.1 Change: `edit_job` tool definition

**File:** `extension/chat/participant.js`  
**Location:** Find `name: 'edit_job'` (currently around line 488)

**Before:**
```javascript
{
  name: 'edit_job',
  description: 'Edit/update an existing job configuration (change servicer, sender, filter, scrubber, etc.).',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: 'The edit instruction, e.g. "change servicer for CMBS_GreyCo to 999".' },
    },
    required: ['prompt'],
  },
},
```

**After:**
```javascript
{
  name: 'edit_job',
  description: 'Edit/update an existing email job configuration field. Use for: changing scrubber/template, servicer ID, mailbox, sender filter, subject filter, SME, save location, import DID, day adjust.',
  inputSchema: {
    type: 'object',
    properties: {
      jobName: {
        type: 'string',
        description: 'Exact job name (e.g. "CMBS_GreyCo"). If the user used a pronoun ("it", "that job"), resolve from conversation history.',
      },
      field: {
        type: 'string',
        enum: [
          'name', 'servicer_id', 'mailbox', 'folder', 'sme', 'save_location',
          'last_email', 'queue_one_file', 'day_adjust', 'import_did',
          'subject_filter', 'sender_filter', 'scrubber', 'template',
        ],
        description: 'The configuration field to update.',
      },
      value: {
        type: 'string',
        description: 'The new value to set for the field.',
      },
    },
    required: ['jobName', 'field', 'value'],
  },
},
```

---

### 4.2 Change: `create_job` tool definition

**File:** `extension/chat/participant.js`  
**Location:** Find `name: 'create_job'`

**Before:**
```javascript
{
  name: 'create_job',
  description: 'Create a new email monitoring job by copying an existing job as a template...',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: 'The create instruction...' },
    },
    required: ['prompt'],
  },
},
```

**After:**
```javascript
{
  name: 'create_job',
  description: 'Create a new email monitoring job by copying an existing job as a template. Use when user says "create a job", "add a new job", "make a copy of job X".',
  inputSchema: {
    type: 'object',
    properties: {
      newName: {
        type: 'string',
        description: 'Name for the new job.',
      },
      templateJob: {
        type: 'string',
        description: 'Name of the existing job to copy as template.',
      },
      overrides: {
        type: 'object',
        description: 'Optional field overrides to apply to the new job (e.g. {"servicer_id": "999"}).',
        additionalProperties: { type: 'string' },
      },
    },
    required: ['newName', 'templateJob'],
  },
},
```

---

### 4.3 Change: `rollback` tool definition

**File:** `extension/chat/participant.js`  
**Location:** Find `name: 'rollback'`

**After:**
```javascript
{
  name: 'rollback',
  description: 'Restore Settings.xml from a backup file. Use when user says "roll back", "restore from backup", "undo last save".',
  inputSchema: {
    type: 'object',
    properties: {
      backupFile: {
        type: 'string',
        description: 'The backup file name to restore (e.g. "Settings_20260307_092000.xml"). Resolve from conversation history if user says "this morning\'s backup".',
      },
    },
    required: ['backupFile'],
  },
},
```

---

### 4.4 Change: `buildToolArgs` — `edit_job` case

**File:** `extension/chat/participant.js`  
**Location:** `buildToolArgs` function, `case 'edit_job'` (currently line 1111)

**Before:**
```javascript
case 'edit_job':
  return { command: 'edit_job', params: { jobName: toolInput.jobName || '', field: toolInput.field || '', value: toolInput.value || '', xmlType: toolInput.type || 'email' } };
```

**After:** (no change needed — already uses structured params; this was pre-wired for the structured schema. Verify `jobName`, `field`, `value` keys match new schema keys. They do.)

---

### 4.5 Change: `executeToolCall` — `create_job` and `edit_job` cases

**File:** `extension/chat/participant.js`  
**Location:** `executeToolCall` function (line 1212)

**Before:**
```javascript
case 'create_job':
  return handleJobCreate(input.prompt || prompt, request, context, stream, token, shared);

case 'edit_job':
  return handleJobEdit(input.prompt || prompt, request, context, stream, token, shared);
```

**After:**
```javascript
case 'create_job':
  return handleJobCreate(
    input.newName || '',
    input.templateJob || '',
    input.overrides || {},
    request, context, stream, token, shared
  );

case 'edit_job':
  return handleJobEdit(
    input.jobName || '',
    input.field   || '',
    input.value   || '',
    request, context, stream, token, shared
  );
```

---

### 4.6 Change: `handleJobEdit` — remove regex, add structured params

**File:** `extension/chat/participant.js`  
**Location:** `handleJobEdit` function (line 3704)

**Before (full current signature + regex):**
```javascript
async function handleJobEdit(prompt, request, context, stream, token, shared) {
  // Parse: "edit <job_name> set <field> <value>"
  const match = prompt.match(/^edit\s+["']?(.+?)["']?\s+set\s+(\w+)\s+(.+)$/i);
  if (!match) {
    stream.markdown([
      '### Edit a Job\n',
      '**Usage:** `/jobs edit "<job_name>" set <field> <value>`\n',
      '**Example:** `/jobs edit "Exeter - rptent" set servicer_id 225`\n',
      '**Editable fields:** name, servicer_id, mailbox, folder, import_did, subject_filter, sender_filter, scrubber, day_adjust, sme, save_location',
    ].join('\n'));
    return { followUps: [] };
  }

  const jobName = match[1].replace(/^["']|["']$/g, '');
  const fieldName = match[2];
  const newValue = match[3].trim();

  // Confirmation
  const confirm = await vscode.window.showWarningMessage(
    `Apply change to job "${jobName}"?\n${fieldName}: → ${newValue}`,
    { modal: true }, 'Apply', 'Cancel');

  if (confirm !== 'Apply') {
    stream.markdown('Edit cancelled.\n');
    return { followUps: [] };
  }

  stream.progress(`Editing job "${jobName}"...`);
  const data = await backendCall('edit_job', {
    jobName,
    field: fieldName,
    value: newValue,
    xmlType: 'email',
  }, shared);
  ...
```

**After:**
```javascript
async function handleJobEdit(jobName, field, value, request, context, stream, token, shared) {
  // Validate params (guard against empty strings if called from slash-command path)
  if (!jobName || !field || !value) {
    stream.markdown('Missing required parameters: jobName, field, and value are all required.\n');
    return { followUps: [] };
  }

  // Step 1: Fetch current config for before/after diff
  stream.progress(`Fetching current config for "${jobName}"...`);
  const currentData = await backendCall('job_detail', { jobName }, shared);
  if (!currentData || currentData.status === 'error') {
    stream.markdown(`❌ Could not retrieve current config for "${jobName}": ${currentData?.error || 'unknown error'}. Edit aborted.\n`);
    return { followUps: [] };
  }

  // Step 2: Render before/after diff (FR-3.1)
  const currentValue = resolveCurrentFieldValue(currentData, field); // helper — see 4.11
  stream.markdown(renderEditDiff(jobName, field, currentValue, value));  // helper — see 4.12

  // Step 3: Inline confirmation (FR-3.2)
  const confirmed = await inlineCrudConfirm(stream, token);  // helper — see 4.13
  if (!confirmed) {
    stream.markdown('Edit cancelled.\n');
    return { followUps: [] };
  }

  // Step 4: Execute
  stream.progress(`Editing job "${jobName}"...`);
  const data = await backendCall('edit_job', {
    jobName,
    field,
    value,
    xmlType: 'email',
  }, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  // Step 5: LLM summary (includes backup path — FR-3.3)
  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `Job "${jobName}" was edited: ${field} changed from "${currentValue}" to "${value}".`,
    `A backup was saved at: ${data.data?.backup_file || 'unknown'}.`,
    'Show the before→after change clearly. Confirm the backup file name. Include validation result.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);

  return {
    followUps: [
      { prompt: 'validate all jobs', label: 'Validate all jobs' },
      { prompt: 'what changed since last deploy', label: 'View changes since last backup' },
    ],
  };
}
```

---

### 4.7 Change: `handleJobCreate` — remove regex, add structured params

**Before signature:** `handleJobCreate(prompt, request, ...)`  
**After signature:** `handleJobCreate(newName, templateJob, overrides, request, ...)`

The internal regex `^create\s+(.+?)\s+from\s+["']?(.+?)["']?\s*$` is deleted from `handleJobCreate`.

---

### 4.8 Change: `handleJobsCommand` — retain slash-command regex here only

The `/jobs edit` and `/jobs create` slash-command parsing regex moves into `handleJobsCommand` where it processes the raw prompt for slash invocations:

```javascript
// In handleJobsCommand, where sub-commands are dispatched:
if (/^edit\s+/i.test(sub)) {
  const m = sub.match(/^edit\s+["']?(.+?)["']?\s+set\s+(\w+)\s+(.+)$/i);
  if (!m) { /* show help */ return; }
  return handleJobEdit(
    m[1].replace(/^["']|["']$/g, ''),
    m[2],
    m[3].trim(),
    request, context, stream, token, shared
  );
}
if (/^create\s+/i.test(sub)) {
  const m = sub.match(/^create\s+(.+?)\s+from\s+["']?(.+?)["']?\s*$/i);
  if (!m) { /* show help */ return; }
  return handleJobCreate(
    m[1].replace(/^["']|["']$/g, ''),
    m[2].replace(/^["']|["']$/g, ''),
    {},
    request, context, stream, token, shared
  );
}
```

---

### 4.9 Change: `handleDeployRollback` — remove regex, add structured params

**Before:** Handler extracts backup filename from `prompt` with regex.  
**After:** Handler receives `backupFile: string` directly from `executeToolCall` via the new tool schema.

`executeToolCall` rollback case update:
```javascript
case 'rollback':
  return handleDeployRollback(input.backupFile || '', request, context, stream, token, shared);
```

---

### 4.10 Helper: `resolveCurrentFieldValue(jobDetailResult, fieldName)`

```javascript
/**
 * Extract the current value of a field from a job_detail result.
 * Handles both flat fields (ServicerID) and nested fields (Templates/Main = scrubber).
 */
function resolveCurrentFieldValue(jobDetailResult, fieldName) {
  const job = jobDetailResult?.data?.job || {};
  // Map logical field names to result keys
  const fieldMap = {
    scrubber: () => job.scrubber || job.template || job['templates_main'] || '',
    template: () => job.scrubber || job.template || job['templates_main'] || '',
    servicer_id: () => String(job.servicer_id || job.ServicerID || ''),
    mailbox: () => job.mailbox || job.MailboxAddress || '',
    folder: () => job.folder || job.Folder || '',
    sme: () => job.sme || job.SME || '',
    save_location: () => job.save_location || job.SaveLocation || '',
    import_did: () => job.import_did || job.ImportDID || '',
    subject_filter: () => job.subject_filter || job.SubjectFilter || '',
    sender_filter: () => job.sender_filter || job.SenderFilter || '',
    day_adjust: () => String(job.day_adjust || job.DayAdjust || ''),
    name: () => job.name || job.Name || '',
  };
  return (fieldMap[fieldName] || (() => ''))();
}
```

---

### 4.11 Helper: `renderEditDiff(jobName, field, currentValue, newValue)`

```javascript
/**
 * Render a before/after diff in the chat stream for a single field edit.
 */
function renderEditDiff(jobName, field, currentValue, newValue) {
  const isNested = (field === 'scrubber' || field === 'template');
  let beforeXml, afterXml;

  if (isNested) {
    beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
    afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
  } else {
    // Derive XML tag from EMAIL_FIELD_MAP equivalents for display purposes
    const tagMap = {
      servicer_id: 'ServicerID', mailbox: 'MailboxAddress', folder: 'Folder',
      sme: 'SME', save_location: 'SaveLocation', import_did: 'ImportDID',
      subject_filter: 'SubjectFilter', sender_filter: 'SenderFilter',
      day_adjust: 'DayAdjust', name: 'Name',
    };
    const tag = tagMap[field] || field;
    beforeXml = `<${tag}>${currentValue || '(not set)'}</${tag}>`;
    afterXml  = `<${tag}>${newValue}</${tag}>`;
  }

  return [
    `\n**Proposed edit on job \`${jobName}\`:**\n`,
    `**Before:**`,
    `\`\`\`xml`,
    beforeXml,
    `\`\`\``,
    `**After:**`,
    `\`\`\`xml`,
    afterXml,
    `\`\`\`\n`,
  ].join('\n');
}
```

---

### 4.12 Helper: `inlineCrudConfirm(stream, token)` — returns Promise\<boolean\>

```javascript
/**
 * Present an in-chat Confirm / Cancel prompt.
 * Uses stream.button() if available (VS Code 1.95+), otherwise plain text.
 * Returns true if the next user turn matches a confirm phrase.
 *
 * NOTE: Because VS Code chat handlers cannot await the next user turn directly
 * in the same handler invocation, this function uses the pending-confirmation 
 * pattern: it stores a flag and returns immediately with the stream output.
 * The NEXT invocation of the participant handler reads the pending flag.
 * See Section 4.13 for the pending-confirmation state machine.
 */
async function inlineCrudConfirm(stream) {
  if (typeof stream.button === 'function') {
    stream.markdown('\n**Confirm this change?**\n');
    stream.button({ title: 'Confirm ✓', command: 'frp.confirmPending' });
    stream.button({ title: 'Cancel ✗',  command: 'frp.cancelPending'  });
  } else {
    stream.markdown('\nType **yes** to confirm or **no** to cancel.\n');
  }
  // Signal that we are awaiting confirmation — actual confirmation is checked
  // in the NEXT participant handler invocation (see pendingConfirmation state machine)
  return PENDING_CONFIRMATION; // special sentinel value
}
const PENDING_CONFIRMATION = Symbol('PENDING_CONFIRMATION');
```

---

### 4.13 Pending-Confirmation State Machine

**Why needed:** VS Code Chat handlers are invoked once per user turn and return a `ChatResult`. There is no "await next message" mechanism within a single handler invocation. The confirmation round-trip therefore spans two handler invocations:

**Turn N** (edit/create/rollback intent):
1. Handler extracts params, renders diff, renders confirm/cancel buttons
2. Sets `shared.pendingOperation = { type: 'edit_job', params: {jobName, field, value} }`
3. Returns `{ followUps: [] }` — no backend call yet

**Turn N+1** (user says "yes"/"no"):
1. At the TOP of the main `frpParticipantHandler`, before routing:
```javascript
if (shared.pendingOperation) {
  const lc = request.prompt.toLowerCase().trim();
  const confirmed = /^(yes|y|confirm|apply|ok|proceed|do it)/.test(lc);
  const cancelled  = /^(no|n|cancel|stop|abort|nevermind|nope)/.test(lc);

  if (confirmed || cancelled) {
    const op = shared.pendingOperation;
    shared.pendingOperation = null;  // always clear

    if (cancelled) {
      stream.markdown('Operation cancelled.\n');
      return { followUps: [] };
    }

    // Dispatch saved operation
    if (op.type === 'edit_job') {
      return executeConfirmedEdit(op.params, request, context, stream, token, shared);
    }
    if (op.type === 'create_job') {
      return executeConfirmedCreate(op.params, request, context, stream, token, shared);
    }
    if (op.type === 'rollback') {
      return executeConfirmedRollback(op.params, request, context, stream, token, shared);
    }
  }
  // If user said neither yes nor no, clear the pending operation and route normally
  shared.pendingOperation = null;
}
```

**`shared.pendingOperation` structure:**
```javascript
{
  type: 'edit_job' | 'create_job' | 'rollback',
  params: {
    // edit_job:  { jobName, field, value, xmlType }
    // create_job: { newName, templateJob, overrides, xmlType }
    // rollback:   { backupFile }
  }
}
```

**Persistence:** `shared` is the extension-level shared object passed to every handler. It persists across turns within a VS Code session. `pendingOperation` is reset to `null` whenever a confirmation or cancellation is received, or when a new non-confirmation prompt is received.

---

## 5. Epic 2 Technical Specification — Conversation History

### 5.1 New Function: `buildMessageHistory`

**File:** `extension/chat/participant.js`  
**Location:** Add adjacent to `buildConversationContext` (line 1981)

```javascript
/**
 * Build a LanguageModelChatMessage[] array from conversation history.
 *
 * This replaces the plain-string historyContext injection in LLM calls that
 * use model.sendRequest(messages, {tools}). The LLM receives a proper
 * multi-turn conversation object rather than a text summary, enabling native
 * contextual reference resolution across turns.
 *
 * @param {Object}  context        VS Code ChatContext
 * @param {string}  systemContent  System / domain knowledge text (goes as User msg #0)
 * @param {string}  currentPrompt  The current user turn text (goes as final User message)
 * @returns {import('vscode').LanguageModelChatMessage[]}
 */
function buildMessageHistory(context, systemContent, currentPrompt) {
  const messages = [
    vscode.LanguageModelChatMessage.User(systemContent),
  ];

  if (context && context.history && context.history.length > 0) {
    const recent = context.history.slice(-6); // cap at 6 turns
    for (const turn of recent) {
      if (turn instanceof vscode.ChatRequestTurn) {
        messages.push(vscode.LanguageModelChatMessage.User(turn.prompt));
      } else if (turn instanceof vscode.ChatResponseTurn) {
        const parts = [];
        for (const part of turn.response) {
          if (part instanceof vscode.ChatResponseMarkdownPart) {
            parts.push(part.value.value);
          }
        }
        const text = parts.join('').slice(0, 2000);
        if (text.trim()) {
          messages.push(vscode.LanguageModelChatMessage.Assistant(text));
        }
      }
    }
  }

  messages.push(vscode.LanguageModelChatMessage.User(currentPrompt));
  return messages;
}
```

---

### 5.2 Change: `routeWithinCategory` — use `buildMessageHistory`

**Location:** `routeWithinCategory` function (line 1398)

**Before:**
```javascript
const routingPrompt = [
  SYSTEM_PROMPT, '',
  DOMAIN_KNOWLEDGE, '',
  categoryContext, '',
  'Select the best tool...', '',
  historyContext ? historyContext + '\n' : '',
  `User question: ${prompt}`,
].join('\n');

const messages = [
  vscode.LanguageModelChatMessage.User(routingPrompt),
];
```

**After:**
```javascript
const systemContent = [
  SYSTEM_PROMPT, '',
  DOMAIN_KNOWLEDGE, '',
  categoryContext, '',
  'Select the best tool and extract the correct parameters from the prompt.',
  'You MUST call exactly one tool.',
  'For numeric IDs, extract ONLY the number.',
  'If the user uses pronouns ("it", "that job", "its"), resolve to the explicit entity in conversation history.',
].join('\n');

const messages = buildMessageHistory(context, systemContent, prompt);
```

---

### 5.3 Change: `routeWithAllTools` — use `buildMessageHistory`

**Location:** `routeWithAllTools` function (line 1483)

**Before:**
```javascript
const routingPrompt = [
  SYSTEM_PROMPT, '',
  DOMAIN_KNOWLEDGE, '',
  'You are routing the user\'s question...',
  historyContext ? historyContext + '\n' : '',
  `User question: ${prompt}`,
].join('\n');

const messages = [
  vscode.LanguageModelChatMessage.User(routingPrompt),
];
```

**After:**
```javascript
const systemContent = [
  SYSTEM_PROMPT, '',
  DOMAIN_KNOWLEDGE, '',
  'You are routing the user\'s question to the correct backend tool.',
  'Use the data model above to select the BEST tool.',
  'You MUST call exactly one tool. Extract the correct parameters from the prompt.',
  'For numeric IDs, extract ONLY the number.',
  'If the user references previous results, extract identifiers from conversation history.',
].join('\n');

const messages = buildMessageHistory(context, systemContent, prompt);
```

---

### 5.4 Change: `reactLoop` — use `buildMessageHistory`

**Location:** `reactLoop` function (line 1580)

**Before:**
```javascript
const historyContext = buildConversationContext(context);
const userContent = historyContext
  ? `Previous conversation context:\n${historyContext}\n\nCurrent question: ${prompt}`
  : prompt;

const messages = [
  vscode.LanguageModelChatMessage.User(
    `${pipelineDef.playbook}\n\n---\n\nUser question: ${userContent}`
  ),
];
```

**After:**
```javascript
const systemContent = `${pipelineDef.playbook}\n\n---`;
const messages = buildMessageHistory(context, systemContent, prompt);
```

**Note:** `buildConversationContext` is retained — it is still used by Stage 1 `classifyIntent` which passes a plain string in a text prompt (not `messages[]` style). Do NOT remove it.

---

## 6. Epic 3 Technical Specification — Native Confirmation UX

### 6.1 Remove all three `vscode.window.showWarningMessage` calls

| Handler | Line | Replacement |
|---|---|---|
| `handleJobCreate` | 3662 | `shared.pendingOperation = {type:'create_job', params:{...}}` + `inlineCrudConfirm(stream)` |
| `handleJobEdit` | 3722 | `shared.pendingOperation = {type:'edit_job', params:{...}}` + `inlineCrudConfirm(stream)` |
| `handleDeployRollback` | 3972 | `shared.pendingOperation = {type:'rollback', params:{...}}` + `inlineCrudConfirm(stream)` |

### 6.2 Add `shared.pendingOperation` check at top of `frpParticipantHandler`

**Location:** Near top of the main handler function (after request validation, before command routing)

```javascript
// ── Pending confirmation check ──────────────────────────────────────────────
if (shared.pendingOperation) {
  const lc = request.prompt.toLowerCase().trim();
  const isConfirm = /^(yes|y|confirm|apply|ok|proceed|do\s+it|sure|go ahead)/.test(lc);
  const isCancel  = /^(no|n|cancel|stop|abort|nevermind|nope|don.?t)/.test(lc);

  if (isConfirm || isCancel) {
    const op = shared.pendingOperation;
    shared.pendingOperation = null;

    if (isCancel) {
      stream.markdown('Operation cancelled.\n');
      return { followUps: [] };
    }

    switch (op.type) {
      case 'edit_job':    return executeConfirmedEdit(op.params,     request, context, stream, token, shared);
      case 'create_job':  return executeConfirmedCreate(op.params,   request, context, stream, token, shared);
      case 'rollback':    return executeConfirmedRollback(op.params, request, context, stream, token, shared);
    }
  }

  // Unrecognised response — clear pending and route normally
  shared.pendingOperation = null;
}
// ── End pending confirmation ─────────────────────────────────────────────────
```

### 6.3 New functions: `executeConfirmedEdit`, `executeConfirmedCreate`, `executeConfirmedRollback`

These are thin wrappers that execute the actual backend calls after confirmation. They are split from the handler functions (which prepare and show the diff) to maintain clean separation of the "prepare" and "execute" phases.

```javascript
async function executeConfirmedEdit({ jobName, field, value, xmlType }, request, context, stream, token, shared) {
  stream.progress(`Editing job "${jobName}"...`);
  const data = await backendCall('edit_job', { jobName, field, value, xmlType: xmlType || 'email' }, shared);
  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }
  const currentValue = ''; // value was captured at diff-render time; not re-fetched here
  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `Job "${jobName}" field "${field}" was changed to "${value}".`,
    `A backup was saved at: ${data.data?.backup_file || 'unknown'}.`,
    'Show the change clearly, confirm backup file, include validation result.',
  ].join('\n');
  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);
  return {
    followUps: [
      { prompt: 'validate all jobs', label: 'Validate all jobs' },
      { prompt: 'what changed since last deploy', label: 'View recent changes' },
    ],
  };
}
```

(Similar patterns for `executeConfirmedCreate` and `executeConfirmedRollback` — omitted for brevity, same pattern.)

---

## 7. Epic 4 Technical Specification — Multi-Step CRUD Pipeline

### 7.1 New constant: `CRUD_PLANNING_PLAYBOOK`

**File:** `extension/chat/participant.js`  
**Location:** Add near other playbook constants (before `PIPELINE_DEFINITIONS`)

```javascript
const CRUD_PLANNING_PLAYBOOK = `
You are the FRP CRUD planning agent. Your job is to plan and execute a sequence of
create/edit/validate operations on FRP job configurations.

## PHASE 1 — PLAN (mandatory first step, NO tool calls)
Before calling any tool, output a numbered plan using this EXACT format:
  PLAN:
  1. <tool_name>: <param>=<value>, <param>=<value>
  2. <tool_name>: <param>=<value>
  ...
  (End of plan — awaiting confirmation)

Do NOT call any tool in Phase 1. Output the plan as plain text only.

## PHASE 2 — EXECUTE (only after the user confirms the plan)
- Execute each step in the order listed.
- After each tool call, briefly report: "Step N complete: <result summary>"
- If a step fails, STOP immediately. Report the failure and mention any backups created.
- ALWAYS mention the backup_file returned from create_job and edit_job calls.

## RULES
- Never merge multiple edits into a single tool call.
- Always call job_detail before edit_job to verify the job exists.
- If any required parameter is unknown, ask BEFORE presenting the plan.
- The plan confirmation is done by the FRP agent infrastructure — you do not ask again.
`.trim();
```

---

### 7.2 New pipeline entry in `PIPELINE_DEFINITIONS`

```javascript
crud_planning: {
  name: 'crud_planning',
  displayName: 'CRUD Planning',
  triggerDescription:
    'User wants to perform 2+ create/edit/validate operations on jobs in a single request, ' +
    'OR wants to create AND configure a job in the same message.',
  playbook: CRUD_PLANNING_PLAYBOOK,
  tools: ['search_jobs', 'job_detail', 'create_job', 'edit_job', 'validate_email', 'validate_sftp'],
  maxSteps: 8,
},
```

---

### 7.3 Stage 1 classifier update — add `crud_planning` pipeline trigger

**Location:** `buildClassifierPrompt` function — `pipelineSection` array  
Add alongside `emailTriageTriggers`, `jobInvestTriggers`, `servicerInvestTriggers`:

```javascript
const crudPlanningTriggers =
  '**crud_planning** pipeline: ' +
  (PIPELINE_DEFINITIONS.crud_planning?.triggerDescription || '');
```

Add to the `pipelineSection` array:
```javascript
crudPlanningTriggers,
```

Add classifier examples:
```javascript
'- "create GreyCo_v2 from CSMC_Template and set scrubber to Outlook_Queuer_x" → mode: pipeline, pipeline: crud_planning',
'- "add a new job and configure servicer 569 on it" → mode: pipeline, pipeline: crud_planning',
'- "create a job, rename it, then validate" → mode: pipeline, pipeline: crud_planning',
```

---

### 7.4 `crud_planning` Plan Extraction

The `reactLoop` currently processes tool calls and text output. For `crud_planning`, Phase 1 produces a `PLAN:` text block (no tool calls). The loop must detect this and emit the consolidated confirmation:

```javascript
// In reactLoop, after the first LLM response stream is consumed:
if (pipelineDef.name === 'crud_planning' && step === 1) {
  if (!toolCallMade && finalText.includes('PLAN:')) {
    // Extract and render the plan
    stream.markdown(`\n${finalText}\n`);
    // Store plan for execution, show confirm buttons
    shared.pendingOperation = {
      type: 'crud_plan',
      params: { planText: finalText, messages: [...messages] },
    };
    await inlineCrudConfirm(stream);
    return { followUps: [] }; // pause — await confirmation in next turn
  }
}
```

After confirmation via the `pendingOperation` state machine, `executeConfirmedCrudPlan` resumes the `reactLoop` with the messages array (which includes the plan text) and sends a `User("Confirmed. Execute the plan.")` message to trigger Phase 2.

---

## 8. Test Specification

### 8.1 Test file structure

```
extension/test/
  unit/
    test_tool_schemas.js          ← S-101, S-102, S-103: schema validation
    test_build_message_history.js ← S-201: buildMessageHistory unit tests
    test_inline_confirm.js        ← S-302: pendingOperation state machine
    test_render_diff.js           ← S-301: renderEditDiff output
    test_resolve_field_value.js   ← helper: resolveCurrentFieldValue
  integration/
    test_edit_flow.js             ← end-to-end NL → diff → confirm → execute
    test_create_flow.js           ← end-to-end NL → create flow
    test_contextual_resolution.js ← S-202: "that job" resolves from history
    test_crud_planning.js         ← S-401, S-402: multi-step plan
```

### 8.2 Key unit test cases

**`test_tool_schemas.js`**
```
TC-SCHEMA-01: edit_job schema has required=['jobName','field','value']
TC-SCHEMA-02: edit_job field enum contains all 14 valid field names
TC-SCHEMA-03: create_job schema has required=['newName','templateJob']
TC-SCHEMA-04: rollback schema has required=['backupFile']
TC-SCHEMA-05: no FRP_TOOLS entry has { prompt: string } schema after Phase 9
```

**`test_build_message_history.js`**
```
TC-MH-01: empty history → [User(system), User(current)]
TC-MH-02: 3 turns → [User(system), User(t1), Asst(t2), User(t3), User(current)]
TC-MH-03: response text > 2000 chars is truncated to 2000
TC-MH-04: empty response text → no Assistant message pushed
TC-MH-05: 7+ turns → only last 6 included
TC-MH-06: return type is array of LanguageModelChatMessage (check constructor names)
```

**`test_render_diff.js`**
```
TC-RD-01: scrubber field → renders <Templates><Main>...</Main></Templates> blocks
TC-RD-02: flat field (servicer_id) → renders <ServicerID>...</ServicerID> blocks
TC-RD-03: old value "(not set)" when currentValue is empty string
TC-RD-04: job name appears in diff title
```

**`test_inline_confirm.js`**
```
TC-IC-01: "yes" → isConfirm = true
TC-IC-02: "y" → isConfirm = true
TC-IC-03: "confirm" → isConfirm = true
TC-IC-04: "no" → isCancel = true
TC-IC-05: "cancel" → isCancel = true
TC-IC-06: "maybe" → neither → pendingOperation cleared, normal routing proceeds
TC-IC-07: pendingOperation cleared after confirmation
TC-IC-08: pendingOperation cleared after cancellation
TC-IC-09: pendingOperation cleared on unrecognised response
```

**`test_resolve_field_value.js`**
```
TC-RFV-01: field=scrubber → returns job.scrubber
TC-RFV-02: field=servicer_id → returns string(job.servicer_id)
TC-RFV-03: field=scrubber with no scrubber key → returns ''
TC-RFV-04: unknown field → returns ''
```

### 8.3 Integration test outline (`test_edit_flow.js`)

```javascript
// Mocks: backendCall, vscode.LanguageModelChatMessage, generateOrFallback
// Test: full flow from handleJobEdit(jobName, field, value) → diff shown → confirmed → backend called

it('shows diff and calls backend on confirm', async () => {
  backendCallMock
    .onCall(0).resolves({ data: { job: { scrubber: 'OldScrubber' } } })  // job_detail
    .onCall(1).resolves({ success: true, data: { backup_file: 'Settings_test.xml' } }); // edit_job

  const stream = createMockStream();
  const shared = createMockShared();

  // First turn: show diff
  await handleJobEdit('CMBS_GreyCo', 'scrubber', 'NewScrubber', mockRequest, mockContext, stream, mockToken, shared);
  
  assert.ok(stream.markdownOutput.includes('OldScrubber'));    // before value shown
  assert.ok(stream.markdownOutput.includes('NewScrubber'));    // after value shown
  assert.equal(shared.pendingOperation.type, 'edit_job');      // pending op set
  assert.equal(backendCallMock.callCount, 1);                  // only job_detail called

  // Second turn: confirm
  await executeConfirmedEdit(shared.pendingOperation.params, mockRequest, mockContext, stream, mockToken, shared);
  
  assert.equal(backendCallMock.callCount, 2);                  // edit_job now called
  assert.ok(stream.markdownOutput.includes('Settings_test.xml')); // backup mentioned
});

it('does not call backend when cancelled', async () => {
  // ... setup similar...
  // Simulate cancel turn
  const shared = { pendingOperation: { type: 'edit_job', params: {...} } };
  mockRequest.prompt = 'cancel';
  
  // Invoke participant handler
  await frpParticipantHandler(mockRequest, mockContext, stream, mockToken);
  
  assert.ok(stream.markdownOutput.includes('cancelled'));
  assert.equal(backendCallMock.callCount, 0);  // no writes
  assert.isNull(shared.pendingOperation);
});
```

### 8.4 Python backend tests (no changes needed)

All 719 existing pytest tests in `tests/` must continue to pass without modification. The backend is unchanged in Phase 9.

```
pytest tests/ -q   →   719 passed (no change from Phase 8.5 baseline)
```

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `stream.button()` not available in deployed VS Code version | Medium | Low | `inlineCrudConfirm` has text fallback ("Type yes/no") |
| `LanguageModelChatMessage.Assistant()` not available (vs User only) | Low | Medium | Check API — fallback to User messages labelled "Assistant:" if needed |
| LLM ignores `required` fields in schema and still calls tool with missing params | Medium | Medium | Add guard at top of each handler: if `!jobName` → return error message |
| `pendingOperation` state left stale after VS Code reload | Low | Low | Check timestamp — if pending op is >5 min old, discard |
| `crud_planning` Phase 1 plan text format varies by model | Medium | Medium | Regex detection of "PLAN:" is loose; also check for numbered list format |
| Concurrent operations from multiple chat tabs | Low | Medium | `shared` is session-scoped; document that concurrent ops are not supported |

---

## 10. Definition of Done

Phase 9 is complete when ALL of the following are true:

### Epics 1–4 (Structured Schemas, History, Confirmation, CRUD Pipeline)
- [ ] Zero `prompt.match(/regex/)` calls in `handleJobEdit`, `handleJobCreate`, `handleDeployRollback`
- [ ] Zero `vscode.window.showWarningMessage` calls in any CRUD handler
- [ ] `edit_job`, `create_job`, `rollback` tool schemas have structured required fields (no `prompt: string`)
- [ ] `buildMessageHistory` function exists and is called by `routeWithinCategory`, `routeWithAllTools`, `reactLoop`
- [ ] `shared.pendingOperation` check exists at top of `frpParticipantHandler`
- [ ] `crud_planning` pipeline definition exists in `PIPELINE_DEFINITIONS`
- [ ] Stage 1 classifier prompt includes `crud_planning` trigger description and examples

### Epic 5 (SFTP CRUD Parity)
- [ ] `edit_job` schema `field` enum contains all 19 values (14 email + 5 SFTP-only: path, dsn, skip_list, ignore_list, zip_content_filter)
- [ ] `edit_job` schema has `xmlType: enum('email','sftp')` optional field
- [ ] `create_job` schema has `xmlType: enum('email','sftp')` optional field
- [ ] `buildToolArgs` edit_job uses `toolInput.xmlType` (not `toolInput.type`)
- [ ] `resolveCurrentFieldValue(result, fieldName, xmlType)` handles all 5 SFTP-only fields
- [ ] `renderEditDiff(jobName, field, current, new, xmlType)` has SFTP tag map (RemotePath, DSN, SkipList, IgnoreList, ZipContentFilter)
- [ ] Manual smoke test: "change the remote path on SFTP_GreyCo to /Inbox/New" → shows SFTP diff (RemotePath) → confirm → backend called with xmlType='sftp'
- [ ] Manual smoke test: "create an SFTP job called SFTP_GreyCo from SFTPTemplate" → creates with xmlType='sftp'

### Epic 6 (Command Intelligence)
- [ ] `triage_email` schema has structured params (sender/subject/msgPath/body/mode) — no `prompt: string`
- [ ] `impact_analysis` schema has structured params (changeType/targetJob/newValue/etc.) — no `prompt: string`
- [ ] `coverage_gaps` schema has `focus: enum('email','sftp','all')` — no `prompt: string`
- [ ] `parseChangeIntent()` function is deleted from `participant.js` (zero occurrences)
- [ ] `buildTriagePrompt(input)` helper function exists and returns mode-prefixed string
- [ ] `ANALYSIS_PLAYBOOK` constant exists before `PIPELINE_DEFINITIONS`
- [ ] `analysis_pipeline` entry exists in `PIPELINE_DEFINITIONS` with all 12 tools
- [ ] Stage 1 classifier prompt includes `analysis_pipeline` trigger description and examples
- [ ] Manual smoke test: "triage email from sender@bank.com about CMBS reporting" → calls `triage_email` with sender param (not prompt string)
- [ ] Manual smoke test: "what's the impact of changing the scrubber on CMBS_GreyCo to Outlook_Queuer_x" → calls `impact_analysis` with changeType='scrubber_change', targetJob='CMBS_GreyCo' (no `parseChangeIntent` LLM call)
- [ ] Manual smoke test: "run a full system health check" → routes to `analysis_pipeline` → calls ≥2 analysis tools

### All Epics
- [ ] All unit tests in `extension/test/unit/` pass
- [ ] All integration tests in `extension/test/integration/` pass
- [ ] `pytest tests/ -q` shows 719+ passed, 0 failed (backend unchanged)
- [ ] VSIX builds successfully and installs in VS Code
- [ ] No tool schema in `FRP_TOOLS` has `{ prompt: { type: 'string' } }` as its only property

---

## 11. Epic 5 Technical Specification — SFTP CRUD Parity

**Objective:** Allow the LLM to create and edit SFTP Settings.xml jobs via the same `create_job` / `edit_job` tools used for email jobs. The backend already supports this fully — all changes are in `participant.js`.

**Root cause of current gap:**
1. `edit_job` / `create_job` schemas have no `xmlType` parameter — the LLM cannot signal `xmlType='sftp'`
2. `buildToolArgs` passes `xmlType: toolInput.type || 'email'` — uses `toolInput.type` (a key that never exists in the schema), so SFTP edits silently default to `xmlType='email'` and fail

---

### 11.1 Change: `edit_job` schema — add `xmlType` and SFTP field names

**File:** `extension/chat/participant.js`  
**Location:** Find `name: 'edit_job'` (the structured schema added in Epic 1, §4.1)

**Before (Epic 1 result — email-only):**
```javascript
field: {
  type: 'string',
  enum: [
    'name', 'servicer_id', 'mailbox', 'folder', 'sme', 'save_location',
    'last_email', 'queue_one_file', 'day_adjust', 'import_did',
    'subject_filter', 'sender_filter', 'scrubber', 'template',
  ],
  description: 'The configuration field to update.',
},
```
*(no `xmlType` property in the schema)*

**After (Epic 5 — combined email + SFTP):**
```javascript
xmlType: {
  type: 'string',
  enum: ['email', 'sftp'],
  description: 'Job type: "email" for email monitoring jobs, "sftp" for SFTP delivery jobs. Defaults to "email" if omitted.',
},
field: {
  type: 'string',
  enum: [
    // Email job fields
    'name', 'servicer_id', 'mailbox', 'folder', 'sme', 'save_location',
    'last_email', 'queue_one_file', 'day_adjust', 'import_did',
    'subject_filter', 'sender_filter', 'scrubber', 'template',
    // SFTP job fields (xmlType='sftp' required)
    'path', 'dsn', 'skip_list', 'ignore_list', 'zip_content_filter',
  ],
  description: 'The configuration field to update. SFTP-only fields (path, dsn, skip_list, ignore_list, zip_content_filter) require xmlType="sftp".',
},
```

---

### 11.2 Change: `create_job` schema — add `xmlType`

**Location:** Find `name: 'create_job'` (the structured schema added in Epic 1, §4.2)

**Before (Epic 1 result):**
```javascript
properties: {
  newName: { type: 'string', description: 'Name for the new job.' },
  templateJob: { type: 'string', description: 'Name of the existing job to copy as template.' },
  overrides: { type: 'object', description: '...', additionalProperties: { type: 'string' } },
},
required: ['newName', 'templateJob'],
```

**After:**
```javascript
properties: {
  newName: { type: 'string', description: 'Name for the new job.' },
  templateJob: { type: 'string', description: 'Name of the existing job to copy as template.' },
  overrides: { type: 'object', description: 'Optional field overrides to apply (e.g. {"servicer_id": "999"}).', additionalProperties: { type: 'string' } },
  xmlType: {
    type: 'string',
    enum: ['email', 'sftp'],
    description: 'Job type: "email" or "sftp". Defaults to "email" if omitted.',
  },
},
required: ['newName', 'templateJob'],
```

---

### 11.3 Change: `buildToolArgs` — fix `toolInput.type` → `toolInput.xmlType`

**File:** `extension/chat/participant.js`  
**Location:** `buildToolArgs` function, `case 'edit_job'` (~line 1111)

**Before (bug — `toolInput.type` key never exists in schema):**
```javascript
case 'edit_job':
  return {
    command: 'edit_job',
    params: {
      jobName: toolInput.jobName || '',
      field:   toolInput.field   || '',
      value:   toolInput.value   || '',
      xmlType: toolInput.type    || 'email',   // ← BUG: .type not in schema
    },
  };
```

**After:**
```javascript
case 'edit_job':
  return {
    command: 'edit_job',
    params: {
      jobName: toolInput.jobName  || '',
      field:   toolInput.field    || '',
      value:   toolInput.value    || '',
      xmlType: toolInput.xmlType  || 'email',  // ← FIX: matches schema key
    },
  };
```

Also update `case 'create_job'` in `buildToolArgs` (if not already passing xmlType):
```javascript
case 'create_job':
  return {
    command: 'create_job',
    params: {
      newName:     toolInput.newName     || '',
      templateJob: toolInput.templateJob || '',
      overrides:   toolInput.overrides   || {},
      xmlType:     toolInput.xmlType     || 'email',  // ← NEW
    },
  };
```

---

### 11.4 Change: `executeToolCall` — pass `xmlType` to handlers

**Location:** `executeToolCall` function, `create_job` and `edit_job` cases (Epic 1 result from §4.5)

**Before (Epic 1 result):**
```javascript
case 'create_job':
  return handleJobCreate(
    input.newName || '',
    input.templateJob || '',
    input.overrides || {},
    request, context, stream, token, shared
  );

case 'edit_job':
  return handleJobEdit(
    input.jobName || '',
    input.field   || '',
    input.value   || '',
    request, context, stream, token, shared
  );
```

**After:**
```javascript
case 'create_job':
  return handleJobCreate(
    input.newName     || '',
    input.templateJob || '',
    input.overrides   || {},
    input.xmlType     || 'email',   // ← NEW
    request, context, stream, token, shared
  );

case 'edit_job':
  return handleJobEdit(
    input.jobName  || '',
    input.field    || '',
    input.value    || '',
    input.xmlType  || 'email',      // ← NEW
    request, context, stream, token, shared
  );
```

---

### 11.5 Change: `handleJobEdit` and `handleJobCreate` — accept `xmlType` parameter

**Before (Epic 1 signatures):**
```javascript
async function handleJobEdit(jobName, field, value, request, context, stream, token, shared) { ... }
async function handleJobCreate(newName, templateJob, overrides, request, context, stream, token, shared) { ... }
```

**After:**
```javascript
async function handleJobEdit(jobName, field, value, xmlType, request, context, stream, token, shared) { ... }
async function handleJobCreate(newName, templateJob, overrides, xmlType, request, context, stream, token, shared) { ... }
```

Inside `handleJobEdit`, the `backendCall` invocation changes:
```javascript
// Before:
const data = await backendCall('edit_job', { jobName, field, value, xmlType: 'email' }, shared);

// After:
const data = await backendCall('edit_job', { jobName, field, value, xmlType: xmlType || 'email' }, shared);
```

Inside `handleJobCreate`:
```javascript
// Before:
const data = await backendCall('create_job', { newName, templateJob, overrides }, shared);

// After:
const data = await backendCall('create_job', { newName, templateJob, overrides, xmlType: xmlType || 'email' }, shared);
```

Also pass `xmlType` to the helper functions:
```javascript
// In handleJobEdit:
const currentValue = resolveCurrentFieldValue(currentData, field, xmlType);
stream.markdown(renderEditDiff(jobName, field, currentValue, value, xmlType));
```

The `handleJobsCommand` slash-command dispatch (§4.8) should also be updated to pass `xmlType` (defaulting to `'email'` for slash commands, since the slash interface doesn't expose job type):
```javascript
return handleJobEdit(m[1]..., m[2], m[3].trim(), 'email', request, ...);
```

---

### 11.6 Change: `resolveCurrentFieldValue` — extend for SFTP fields

**Location:** Helper function (added in Epic 1 §4.10)

**Before (email-only `fieldMap`):**
```javascript
const fieldMap = {
  scrubber:       () => job.scrubber || job.template || job['templates_main'] || '',
  template:       () => job.scrubber || job.template || job['templates_main'] || '',
  servicer_id:    () => String(job.servicer_id || job.ServicerID || ''),
  mailbox:        () => job.mailbox || job.MailboxAddress || '',
  folder:         () => job.folder || job.Folder || '',
  sme:            () => job.sme || job.SME || '',
  save_location:  () => job.save_location || job.SaveLocation || '',
  import_did:     () => job.import_did || job.ImportDID || '',
  subject_filter: () => job.subject_filter || job.SubjectFilter || '',
  sender_filter:  () => job.sender_filter || job.SenderFilter || '',
  day_adjust:     () => String(job.day_adjust || job.DayAdjust || ''),
  name:           () => job.name || job.Name || '',
};
```

**After (add SFTP fields, update signature):**
```javascript
function resolveCurrentFieldValue(jobDetailResult, fieldName, xmlType) {
  const job = jobDetailResult?.data?.job || {};
  const fieldMap = {
    // Email fields
    scrubber:            () => job.scrubber || job.template || job['templates_main'] || '',
    template:            () => job.scrubber || job.template || job['templates_main'] || '',
    servicer_id:         () => String(job.servicer_id || job.ServicerID || ''),
    mailbox:             () => job.mailbox || job.MailboxAddress || '',
    folder:              () => job.folder || job.Folder || '',
    sme:                 () => job.sme || job.SME || '',
    save_location:       () => job.save_location || job.SaveLocation || '',
    import_did:          () => job.import_did || job.ImportDID || '',
    subject_filter:      () => job.subject_filter || job.SubjectFilter || '',
    sender_filter:       () => job.sender_filter || job.SenderFilter || '',
    day_adjust:          () => String(job.day_adjust || job.DayAdjust || ''),
    name:                () => job.name || job.Name || '',
    // SFTP-only fields
    path:                () => job.path || job.RemotePath || '',
    dsn:                 () => job.dsn || job.DSN || '',
    skip_list:           () => job.skip_list || job.SkipList || '',
    ignore_list:         () => job.ignore_list || job.IgnoreList || '',
    zip_content_filter:  () => job.zip_content_filter || job.ZipContentFilter || '',
  };
  return (fieldMap[fieldName] || (() => ''))();
}
```

---

### 11.7 Change: `renderEditDiff` — extend tag map for SFTP fields

**Location:** Helper function (added in Epic 1 §4.11)

**Before (email-only `tagMap`):**
```javascript
const tagMap = {
  servicer_id: 'ServicerID', mailbox: 'MailboxAddress', folder: 'Folder',
  sme: 'SME', save_location: 'SaveLocation', import_did: 'ImportDID',
  subject_filter: 'SubjectFilter', sender_filter: 'SenderFilter',
  day_adjust: 'DayAdjust', name: 'Name',
};
```

**After (update signature + add SFTP entries):**
```javascript
function renderEditDiff(jobName, field, currentValue, newValue, xmlType) {
  const isNested = (field === 'scrubber' || field === 'template');
  let beforeXml, afterXml;

  if (isNested) {
    beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
    afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
  } else {
    const tagMap = {
      // Email fields
      servicer_id:    'ServicerID',
      mailbox:        'MailboxAddress',
      folder:         'Folder',
      sme:            'SME',
      save_location:  'SaveLocation',
      import_did:     'ImportDID',
      subject_filter: 'SubjectFilter',
      sender_filter:  'SenderFilter',
      day_adjust:     'DayAdjust',
      name:           'Name',
      // SFTP fields
      path:               'RemotePath',
      dsn:                'DSN',
      skip_list:          'SkipList',
      ignore_list:        'IgnoreList',
      zip_content_filter: 'ZipContentFilter',
    };
    const tag = tagMap[field] || field;
    beforeXml = `<${tag}>${currentValue || '(not set)'}</${tag}>`;
    afterXml  = `<${tag}>${newValue}</${tag}>`;
  }

  return [
    `\n**Proposed edit on job \`${jobName}\` (${xmlType || 'email'}):**\n`,
    `**Before:**`,
    `\`\`\`xml`,
    beforeXml,
    `\`\`\``,
    `**After:**`,
    `\`\`\`xml`,
    afterXml,
    `\`\`\`\n`,
  ].join('\n');
}
```

---

### 11.8 Test Cases — Epic 5

**`test_tool_schemas.js`** additions:

```
TC-S501-01: edit_job schema field enum contains all 5 SFTP-only fields (path, dsn, skip_list, ignore_list, zip_content_filter)
TC-S501-02: edit_job schema has xmlType property with enum=['email','sftp']
TC-S501-03: create_job schema has xmlType property
TC-S501-04: buildToolArgs edit_job reads toolInput.xmlType (not toolInput.type)
TC-S501-05: buildToolArgs create_job passes xmlType to params
```

**`test_render_diff.js`** additions:

```
TC-S502-01: SFTP field 'path' → renders <RemotePath> tags
TC-S502-02: SFTP field 'dsn' → renders <DSN> tags
TC-S502-03: SFTP field 'skip_list' → renders <SkipList> tags
TC-S502-04: diff title includes '(sftp)' when xmlType='sftp'
```

**`test_resolve_field_value.js`** additions:

```
TC-S503-01: field='path' → returns job.RemotePath
TC-S503-02: field='dsn' → returns job.DSN
TC-S503-03: field='skip_list' → returns job.SkipList
TC-S503-04: field='ignore_list' → returns job.IgnoreList
TC-S503-05: field='zip_content_filter' → returns job.ZipContentFilter
TC-S503-06: SFTP field with no value → returns ''
```

**Integration test** additions (`test_edit_flow.js`):

```
TC-S503-10: handleJobEdit('SFTP_GreyCo', 'path', '/Inbox/New', 'sftp', ...) shows <RemotePath> diff
TC-S503-11: executeConfirmedEdit with xmlType='sftp' calls backendCall with xmlType='sftp'
TC-S503-12: handleJobCreate newName='SFTP_Test', xmlType='sftp' passes xmlType='sftp' to backendCall

---

## 12. Epic 6 Technical Specification — Command Intelligence

**Objective:** Replace three free-text tool schemas (`triage_email`, `impact_analysis`, `coverage_gaps`) with structured parameter schemas; delete the hidden `parseChangeIntent()` internal LLM call; introduce `ANALYSIS_PLAYBOOK` constant; add `analysis_pipeline` to `PIPELINE_DEFINITIONS` so broad health queries route to a multi-tool agentic loop.

---

### 12.1 Change: `triage_email` tool schema

**File:** `extension/chat/participant.js`  
**Location:** Find `name: 'triage_email'`

**Before:**
```javascript
{
  name: 'triage_email',
  description: 'Process an email through the FRP triage pipeline to identify which job it belongs to.',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: 'The triage instruction.' },
    },
    required: ['prompt'],
  },
},
```

**After:**
```javascript
{
  name: 'triage_email',
  description: 'Process an email through the FRP triage pipeline. Use when user provides an email sender, subject, message path, or asks to verify/match/triage an email message. Resolves which job the email belongs to.',
  inputSchema: {
    type: 'object',
    properties: {
      sender: {
        type: 'string',
        description: 'Email sender address (e.g. "noreply@bank.com"). Optional if msgPath is provided.',
      },
      subject: {
        type: 'string',
        description: 'Email subject line. Optional.',
      },
      msgPath: {
        type: 'string',
        description: 'Absolute or relative path to a .msg or .eml file. Pass if the user provides a file path.',
      },
      body: {
        type: 'string',
        description: 'Raw email body text (first 2000 chars). Optional.',
      },
      mode: {
        type: 'string',
        enum: ['new', 'verify', 'match'],
        description: '"new" — triage as a new unknown email; "verify" — check if the email matches an existing job; "match" — find the best matching job for this email. Default: "new".',
      },
    },
    required: [],   // all params optional — LLM fills whatever it knows
  },
},
```

---

### 12.2 New Helper: `buildTriagePrompt(input)`

**File:** `extension/chat/participant.js`  
**Location:** Add near `inlineCrudConfirm` and other helpers

**Purpose:** Bridge between the structured `triage_email` schema parameters and the string-based `handleTriageCommand`, which still uses sub-command regex (`/^verify\b/`, `/^match\b/`, `/^new\b/`). The bridge reconstructs the string the handler expects.

```javascript
/**
 * Build a triage prompt string from structured triage_email tool parameters.
 * The result is compatible with handleTriageCommand's sub-command regex dispatch.
 *
 * @param {Object} input  - Structured input from triage_email tool call
 * @param {string} [input.mode='new'] - 'new' | 'verify' | 'match'
 * @param {string} [input.msgPath]    - Path to .msg file (if provided, use directly)
 * @param {string} [input.sender]     - Sender email address
 * @param {string} [input.subject]    - Subject line
 * @param {string} [input.body]       - Email body text
 * @returns {string}  Prompt string for handleTriageCommand
 */
function buildTriagePrompt(input) {
  const mode = (input.mode || 'new').toLowerCase();

  // If a file path was provided, the handler can extract it from the prompt
  if (input.msgPath) {
    return `${mode} ${input.msgPath}`;
  }

  // Otherwise build a synthetic context string from known fields
  const parts = [mode];
  if (input.sender)  parts.push(`from:${input.sender}`);
  if (input.subject) parts.push(`subject:${input.subject}`);
  if (input.body)    parts.push(`body:${input.body.slice(0, 500)}`);
  return parts.join(' ');
}
```

---

### 12.3 Change: `executeToolCall` — `triage_email` case

**Location:** `executeToolCall` function, `triage_email` case

**Before:**
```javascript
case 'triage_email':
  return handleTriageCommand(input.prompt || prompt, request, context, stream, token, shared);
```

**After:**
```javascript
case 'triage_email': {
  const triagePrompt = buildTriagePrompt(input);
  return handleTriageCommand(triagePrompt, request, context, stream, token, shared);
}
```

**Note:** `handleTriageCommand` itself is NOT changed. Its regex sub-commands (`/^verify\b/i`, `/^match\b/i`, `/^new\b/i`) continue to work because `buildTriagePrompt` always starts with the mode keyword.

---

### 12.4 Change: `impact_analysis` tool schema

**Location:** Find `name: 'impact_analysis'`

**Before:**
```javascript
{
  name: 'impact_analysis',
  description: 'Analyze the downstream impact of a proposed configuration change.',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: 'Description of the change to analyze.' },
    },
    required: ['prompt'],
  },
},
```

**After:**
```javascript
{
  name: 'impact_analysis',
  description: 'Model the downstream impact of a proposed configuration change on jobs, servicers, and daily processing. Use when user asks "what happens if I change X", "impact of removing Y", "what breaks if I update Z".',
  inputSchema: {
    type: 'object',
    properties: {
      changeType: {
        type: 'string',
        enum: [
          'servicer_change',
          'scrubber_change',
          'template_change',
          'job_disable',
          'job_create',
          'job_delete',
          'sender_filter_change',
          'subject_filter_change',
          'sftp_path_change',
        ],
        description: 'Category of change being modeled.',
      },
      targetJob: {
        type: 'string',
        description: 'Job name the change applies to (e.g. "CMBS_GreyCo").',
      },
      newValue: {
        type: 'string',
        description: 'The new value being set (e.g. new scrubber name, new servicer ID).',
      },
      currentValue: {
        type: 'string',
        description: 'Current value before the change (optional — helps scope the analysis).',
      },
      affectedServicers: {
        type: 'array',
        items: { type: 'string' },
        description: 'Servicer IDs known to be affected (optional — model will derive if omitted).',
      },
      dryRun: {
        type: 'boolean',
        description: 'If true (default), no changes are made — analysis only.',
      },
    },
    required: ['changeType', 'targetJob'],
  },
},
```

---

### 12.5 Change: `executeToolCall` — `impact_analysis` case

**Before:**
```javascript
case 'impact_analysis':
  return handleAnalyzeCommand(input.prompt || prompt, request, context, stream, token, shared);
```

**After:**
```javascript
case 'impact_analysis': {
  // Build structured changeSpec — eliminates parseChangeIntent() internal LLM call
  const changeSpec = {
    changeType:         input.changeType     || '',
    targetJob:          input.targetJob      || '',
    newValue:           input.newValue       || '',
    currentValue:       input.currentValue   || '',
    affectedServicers:  input.affectedServicers || [],
    dryRun:             input.dryRun !== false,   // default true
  };
  return handleAnalyzeImpact(changeSpec, request, context, stream, token, shared);
}
```

**`handleAnalyzeImpact(changeSpec, ...)`** is the extracted sub-function for the impact path of `handleAnalyzeCommand`. It receives a fully-typed `changeSpec` object and calls the backend directly, skipping `parseChangeIntent()`.

---

### 12.6 Delete: `parseChangeIntent()` function

**File:** `extension/chat/participant.js`  
**Location:** ~line 3339 (inside `handleAnalyzeCommand`, impact path)

**Current function (to delete in full):**
```javascript
async function parseChangeIntent(prompt, token) {
  // Internal LLM call to gpt-4o — parses natural language change description
  // into structured fields (job name, field, old value, new value)
  const model = await vscode.lm.selectChatModels({ vendor: 'copilot', family: 'gpt-4o' });
  if (!model || model.length === 0) return null;
  const messages = [
    vscode.LanguageModelChatMessage.User(
      `Parse this change description and return JSON: ...\n\n"${prompt}"`
    ),
  ];
  const response = await model[0].sendRequest(messages, {}, token);
  let text = '';
  for await (const chunk of response.text) { text += chunk; }
  try { return JSON.parse(text.match(/\{[\s\S]*\}/)?.[0] || 'null'); }
  catch { return null; }
}
```

**Action:** Delete the entire function body. No replacement needed — the structured `impact_analysis` schema provides all parameters directly.

Any `parseChangeIntent(...)` call sites in `handleAnalyzeCommand` are also deleted. The impact analysis path in `handleAnalyzeCommand` is replaced by a direct call to `handleAnalyzeImpact(changeSpec, ...)` (see §12.5).

---

### 12.7 Change: `coverage_gaps` tool schema

**Location:** Find `name: 'coverage_gaps'`

**Before:**
```javascript
{
  name: 'coverage_gaps',
  description: 'Find coverage gaps — jobs with deals that have no associated DID mapping.',
  inputSchema: {
    type: 'object',
    properties: {
      prompt: { type: 'string', description: 'Optional filter instructions.' },
    },
  },
},
```

**After:**
```javascript
{
  name: 'coverage_gaps',
  description: 'Find coverage gaps — deals or jobs with missing DID mappings. Can be scoped to email jobs, SFTP jobs, or both.',
  inputSchema: {
    type: 'object',
    properties: {
      focus: {
        type: 'string',
        enum: ['email', 'sftp', 'all'],
        description: 'Scope of coverage check. Default: "all".',
      },
    },
    required: [],
  },
},
```

Update `buildToolArgs` and `executeToolCall` for `coverage_gaps`:
```javascript
// buildToolArgs:
case 'coverage_gaps':
  return {
    command: 'coverage_gaps',
    params: { focus: toolInput.focus || 'all' },
  };

// executeToolCall (no handler change needed — backend accepts focus param):
case 'coverage_gaps':
  return handleAnalyzeCommand(
    `coverage_gaps focus:${input.focus || 'all'}`,
    request, context, stream, token, shared
  );
```

---

### 12.8 New Constant: `ANALYSIS_PLAYBOOK`

**File:** `extension/chat/participant.js`  
**Location:** Add immediately before `PIPELINE_DEFINITIONS` (alongside `CRUD_PLANNING_PLAYBOOK` added in §7.1)

```javascript
const ANALYSIS_PLAYBOOK = `
You are the FRP System Analysis agent. Your role is to investigate health, coverage, performance,
and configuration quality across the email and SFTP processing pipelines.

## TOOL SELECTION GUIDANCE

| Tool | Use when |
|---|---|
| validate_email | User asks about email job config validity, misconfigured email jobs |
| validate_sftp | User asks about SFTP job config validity, misconfigured SFTP jobs |
| coverage_gaps | User asks about missing DID mappings, underserved deals, coverage holes |
| orphan_detection | User asks about orphan deals, deals with no matching job |
| collision_detection | User asks about duplicate DIDs, DID conflicts between jobs |
| failure_analysis | User asks about processing failures, error rates, error spikes |
| log_performance | User asks about processing throughput, duration trends, slow jobs |
| system_health | User asks for a broad system overview, overall health, everything that is wrong |
| job_health | User asks about a specific job or servicer's health |
| daily_summary | User asks about recent activity, what happened today/this week |
| consolidation_analysis | User asks about consolidation opportunities, jobs that could be merged |
| impact_analysis | User wants to model the impact of a proposed change before making it |

## STRATEGY

1. **Broad health queries** ("how is the system?", "anything wrong?") → call system_health + daily_summary
2. **Specific job queries** ("how is CMBS_GreyCo?") → call job_health, then validate_email or validate_sftp
3. **Coverage concerns** ("any gaps?", "missing DIDs?") → call coverage_gaps + orphan_detection + collision_detection
4. **Change impact** ("what breaks if I change X?") → call impact_analysis + job_detail for the target job
5. **Do not call redundant tools.** If job_health already covers a job, do not also call system_health for the same job.
6. **Synthesize.** After all tool calls, output ONE prioritized action list — do not repeat raw data.

## OUTPUT FORMAT

- One-sentence executive summary first
- Issues ranked: 🔴 Critical → 🟡 Warning → 🔵 Info
- For each issue: job/servicer name, problem description, recommended action
- Final line: "X issues found: Y critical, Z warnings, N info"
`.trim();
```

---

### 12.9 New Pipeline Entry: `analysis_pipeline` in `PIPELINE_DEFINITIONS`

**Location:** `PIPELINE_DEFINITIONS` object (alongside `email_triage`, `job_investigation`, `servicer_investigation`, `general_reasoning`, `crud_planning`)

```javascript
analysis_pipeline: {
  name: 'analysis_pipeline',
  displayName: 'System Analysis',
  triggerDescription:
    'User wants a broad system health check, coverage gap analysis, performance investigation, ' +
    'consolidation review, or impact modeling of a change — any query that may require multiple ' +
    'analysis tools to answer fully.',
  playbook: ANALYSIS_PLAYBOOK,
  tools: [
    'validate_email', 'validate_sftp', 'coverage_gaps', 'orphan_detection', 'collision_detection',
    'failure_analysis', 'log_performance', 'system_health', 'job_health', 'daily_summary',
    'consolidation_analysis', 'impact_analysis',
  ],
  maxSteps: 6,
},
```

---

### 12.10 Stage 1 Classifier Update — add `analysis_pipeline` trigger

**Location:** `buildClassifierPrompt` function — `pipelineSection` array

Add alongside the `crud_planning` trigger (§7.3):

```javascript
const analysisPipelineTriggers =
  '**analysis_pipeline** pipeline: ' +
  (PIPELINE_DEFINITIONS.analysis_pipeline?.triggerDescription || '');
```

Add to `pipelineSection` array:
```javascript
analysisPipelineTriggers,
```

Add classifier examples:
```javascript
'- "run a full health check on the system" → mode: pipeline, pipeline: analysis_pipeline',
'- "are there any coverage gaps across all email jobs?" → mode: pipeline, pipeline: analysis_pipeline',
'- "what\'s the performance like this week and are there any consolidation opportunities?" → mode: pipeline, pipeline: analysis_pipeline',
'- "what breaks if I change the scrubber on CMBS_GreyCo?" → mode: pipeline, pipeline: analysis_pipeline',
```

---

### 12.11 Test Cases — Epic 6

**`test_tool_schemas.js`** additions:
```
TC-S601-01: triage_email schema has no 'prompt' property
TC-S601-02: triage_email schema mode enum = ['new','verify','match']
TC-S601-03: triage_email schema required = [] (all fields optional)
TC-S602-01: impact_analysis schema has no 'prompt' property
TC-S602-02: impact_analysis schema changeType enum contains 9 values
TC-S602-03: impact_analysis schema required = ['changeType','targetJob']
TC-S602-04: coverage_gaps schema has focus enum=['email','sftp','all']
TC-S603-01: analysis_pipeline exists in PIPELINE_DEFINITIONS
TC-S603-02: analysis_pipeline.tools contains all 12 expected tool names
```

**`test_build_triage_prompt.js`**:
```
TC-TP-01: mode='verify' + msgPath → returns 'verify /path/to/file.msg'
TC-TP-02: mode='match' + sender → returns 'match from:sender@bank.com'
TC-TP-03: mode='new' + sender + subject → returns 'new from:... subject:...'
TC-TP-04: mode omitted → defaults to 'new'
TC-TP-05: body longer than 500 chars → truncated to 500 chars in output
TC-TP-06: empty input → returns 'new'
```

**`test_parse_change_intent_deleted.js`**:
```
TC-PCI-01: parseChangeIntent is not a defined function in participant scope
TC-PCI-02: impact_analysis executeToolCall path does NOT call any secondary LLM before handleAnalyzeImpact
```

**`test_analysis_pipeline.js`** (integration):
```
TC-AP-01: classifier routes "run full health check" → pipeline: analysis_pipeline
TC-AP-02: classifier routes "coverage gaps across email jobs" → pipeline: analysis_pipeline
TC-AP-03: analysis_pipeline reactLoop calls system_health + daily_summary for broad query
TC-AP-04: analysis_pipeline reactLoop calls job_health for specific-job query (does not call system_health)
TC-AP-05: analysis_pipeline output includes issue severity markers (Critical/Warning/Info)
```
```
