# Phase 13 FRD — Functional Requirements Document
## FRP Agent VS Code Extension — Response Speed & Streaming Architecture Upgrade

**Document type:** Functional Requirements Document
**Parent:** Phase 13 PRD (`01_PRD.md`)
**Status:** Draft
**Date:** March 2026

---

## 1. Purpose

This document specifies the exact functional behaviour of each Phase 13 change. Where the PRD explains *what* and *why*, this document specifies *how the system behaves* after the change — inputs, outputs, control flow, and the precise content of every modified function.

---

## 2. Current System Behaviour Reference

The following facts are established by reading source code and are referenced throughout this document.

| Fact | Location | Phase 13 disposition |
|---|---|---|
| `agentLoop()` accumulates text in `finalText`, dumps via `stream.markdown(finalText)` after `for await` completes | `participant.js` → `agentLoop()`, inner `for await` loop | Fix: stream each token immediately via `stream.markdown(text)` |
| `executeConfirmedCrudPlan()` has identical buffering pattern | `participant.js` → `executeConfirmedCrudPlan()`, inner `for await` loop | Fix: same streaming change |
| `agentLoop()` passes `{ tools: scopedTools }` on every `model.sendRequest()`, including the final answer iteration | `participant.js` → `agentLoop()`, while loop | Fix: after tool loop, do a separate `model.sendRequest(msgs, {}, token)` for final answer |
| `selectModel(request)` returns a single model used for all iterations | `participant.js` → `selectModel()` | Fix: add `selectIntermediateModel()` for tool routing; keep `selectModel()` for final answer |
| `_autoSync()` runs before every `backendCall()` except sync_logs/status/log_search | `tool.js` → `backendCall()` calls `_autoSync()` | Fix: debounce to once per 60 seconds |
| FRP's `generateAnswer()` (used in `generateOrFallback()`) DOES stream correctly | `participant.js` → `generateAnswer()` | No change — this is already correct |
| CRUD plan detection checks `finalText.includes('PLAN:')` and then streams `finalText` | `participant.js` → `agentLoop()`, CRUD plan block | Fix: plan is already streamed with Epic 1; remove duplicate `stream.markdown()` |

---

## 3. Functional Requirements — Epic 1: Token Streaming

### FR-1.1 — agentLoop() Streaming Behaviour

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`
**Affected code block:** The `for await (const part of response.stream)` loop inside the `while (step < maxSteps)` loop.

**Current behaviour:**
```
for await (const part of response.stream) {
  if (toolCall) { execute tool }
  else {
    text = part.value || part;
    if (toolCallMade) { reasoningText += text; }
    else { finalText += text; reasoningText += text; }
  }
}
if (!toolCallMade) {
  stream.markdown(finalText);  // ← dump all at once
}
```

**New behaviour:**
```
for await (const part of response.stream) {
  if (toolCall) { execute tool }
  else {
    text = part.value || part;
    if (toolCallMade) { reasoningText += text; }
    else {
      stream.markdown(text);    // ← stream immediately
      finalText += text;
      reasoningText += text;
    }
  }
}
if (!toolCallMade) {
  // Text already streamed — just log and return
  if (!finalText.trim()) {
    stream.markdown(compilePipelineReport(...));
  }
}
```

**Key design decisions:**

1. **Only stream text when `!toolCallMade`:** Text produced BEFORE a tool call in the same response is accumulated but NOT streamed. This prevents intermediate LLM reasoning ("Let me look that up...") from appearing in the chat. If the LLM produces text and then makes a tool call in the same response, `toolCallMade` becomes `true` partway through the `for await` loop, and subsequent text goes to `reasoningText` (logged but not shown). The `finalText` accumulated before the tool call is NOT shown because the outer `if (!toolCallMade)` check will be `false`.

2. **`finalText` is still accumulated:** We keep `finalText += text` for CRUD plan detection (`finalText.includes('PLAN:')`) and for logging. The variable serves as a record of what was streamed.

3. **Empty response fallback is preserved:** If `finalText.trim()` is empty and `!toolCallMade`, the `compilePipelineReport()` fallback still runs. This handles edge cases where the LLM produces no output.

### FR-1.2 — executeConfirmedCrudPlan() Streaming Behaviour

**File:** `extension/chat/participant.js`
**Function:** `executeConfirmedCrudPlan()`

Same change as FR-1.1. The `for await` loop in this function has an identical pattern:
```javascript
// Current:
finalText += text;
// ... later:
stream.markdown(finalText);
```

Changed to:
```javascript
// New:
stream.markdown(text);
finalText += text;
// ... later: remove stream.markdown(finalText)
```

### FR-1.3 — CRUD Plan Detection Adjustment

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`

The CRUD plan detection block currently reads:
```javascript
if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
  stream.markdown(`\n${finalText}\n`);  // ← shows plan to user
  // ... set pendingOperation, return followUps
}
```

With token streaming enabled (FR-1.1), the plan text is already visible to the user as it was streamed token-by-token. The `stream.markdown(\n${finalText}\n)` line must be removed to avoid duplicating the plan output.

**New behaviour:**
```javascript
if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
  // Plan already streamed token-by-token via FR-1.1 — no need to dump again
  shared.pendingOperation = {
    type: 'crud_plan',
    params: { planText: finalText, messages: [...messages] },
  };
  stream.markdown('\n**Confirm this plan?**\n');
  return { followUps: [...] };
}
```

---

## 4. Functional Requirements — Epic 2: Two-Phase Generation

### FR-2.1 — buildFinalAnswerContext() Function

**File:** `extension/chat/participant.js`
**New function:** `buildFinalAnswerContext(stepResults, systemContent, userPrompt)`

Builds a clean `LanguageModelChatMessage[]` array for the final answer generation pass. Includes:
- `SYSTEM_PROMPT` (formatting rules)
- `DOMAIN_KNOWLEDGE` (data model reference — needed for understanding tool results)
- All step results as structured `<data>` blocks
- The user's original prompt

Does NOT include:
- `ROUTING_GUIDANCE` (not needed for text generation)
- Tool schemas (eliminated — that's the whole point)
- Playbook instructions (not needed for formatting)

**Function signature:**
```javascript
function buildFinalAnswerContext(stepResults, userPrompt) {
  // Returns: vscode.LanguageModelChatMessage[]
}
```

**Output format:**
```
SYSTEM_PROMPT

DOMAIN_KNOWLEDGE

## Retrieved Data

The following data was retrieved to answer the user's question:

### Step 1: search_jobs
<data>
{ ...result JSON... }
</data>

### Step 2: job_detail
<data>
{ ...result JSON... }
</data>

## User's Question
[user's original prompt]

Answer the user's question using the retrieved data above.
Format your response with Markdown as specified in the system prompt.
```

### FR-2.2 — Two-Phase Trigger Logic in agentLoop()

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`

**Trigger condition:** `!toolCallMade && stepResults.length > 0`
- The LLM has finished calling tools (it produced text instead of a tool call on this iteration)
- At least one tool was previously called (there's data to synthesize)
- This means the agentic loop is DONE and we need to generate a final answer

**What happens when triggered:**
1. Discard the text from the current (tool-mode) iteration — it was generated with tool overhead
2. Build a fresh prompt via `buildFinalAnswerContext(stepResults, prompt)`
3. Select the answer model: `const answerModel = await selectModel(request)` (Epic 3 makes this the premium model)
4. Call `answerModel.sendRequest(finalMessages, {}, token)` — **no tools**
5. Stream the response token-by-token: `for await (const chunk of response.text) { stream.markdown(chunk); }`

**Bypass condition:** `!toolCallMade && stepResults.length === 0`
- The LLM produced text on the FIRST iteration without calling any tools
- This is a simple query ("what is the FRP system?")
- The text is already being streamed via Epic 1 — no two-phase needed
- Behaviour is identical to current behaviour minus the buffering delay

**Important:** With two-phase enabled, the text produced in the `for await` loop during a tool-calling iteration is NOT streamed (since it's intermediate reasoning). Only the final answer from Phase 2 is streamed.

### FR-2.3 — Interaction with CRUD Plan Detection

When `pipelineName === 'crud_planning'`, the two-phase logic must NOT override the existing CRUD plan flow. If `finalText.includes('PLAN:')`, the plan detection takes priority and the two-phase generation does not run.

**Priority order:**
1. CRUD plan detection (if applicable)
2. Two-phase generation (if `stepResults.length > 0`)
3. Direct streaming (if `stepResults.length === 0` — simple query)

---

## 5. Functional Requirements — Epic 3: Multi-Model Strategy

### FR-3.1 — selectIntermediateModel() Function

**File:** `extension/chat/participant.js`
**New function:** `selectIntermediateModel()`

Returns a free/fast model for intermediate work (tool routing). Does NOT use the request's model.

**Resolution order:**
1. `frpAgent.intermediateModel` setting (if set and not `"auto"`)
2. GPT-4.1 (free, fast, strong at classification tasks)
3. GPT-4o
4. Claude Sonnet 4
5. GPT-4o-mini
6. Any available Copilot model
7. `null` (no model available)

This is identical to KTS's `selectModel(vscode, null)` — when no `requestModel` is passed, fall through the preference chain.

**KTS evidence:** `gsf_ir_kts_agentic_system/extension/chat/participant.js`, `selectModel()` function. When called with `selectModel(vscode, null)`, the `requestModel` check fails (`null` is not a function), and the function falls through to the auto-select chain starting with GPT-4.1.

### FR-3.2 — Dual Model Usage in agentLoop()

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`

**Current model selection:**
```javascript
const model = await selectModel(request);
// ... model used for ALL iterations
```

**New model selection:**
```javascript
const routingModel = await selectIntermediateModel();
const answerModel = await selectModel(request);
const effectiveRoutingModel = routingModel || answerModel; // fallback if no free model available
```

**Usage:**
- `effectiveRoutingModel` is used for all `model.sendRequest(messages, { tools }, token)` calls — tool routing
- `answerModel` is used for the Phase 2 final answer: `answerModel.sendRequest(finalMessages, {}, token)` — text generation

**Graceful degradation:** If `selectIntermediateModel()` returns `null` (no free model available), the routing model falls back to the premium model. The behaviour is identical to the current code — no degradation.

### FR-3.3 — Output Channel Logging

The output channel should log which model is being used for each step:
```
[FRP] agentLoop: routing model=gpt-4.1, answer model=claude-sonnet-4
[FRP] agentLoop step 1: search_jobs (routing model: gpt-4.1)
[FRP] agentLoop step 2: job_detail (routing model: gpt-4.1)
[FRP] agentLoop: generating final answer (answer model: claude-sonnet-4, no tools)
```

This provides transparency for debugging and timing validation.

---

## 6. Functional Requirements — Epic 4: Auto-Sync Debounce

### FR-4.1 — Debounce Logic

**File:** `extension/copilot/tool.js`
**Function:** `_autoSync()`

**New behaviour:**
- Module-level variable `_lastSyncTimestamp` (initialized to 0)
- On entry, check `Date.now() - _lastSyncTimestamp < 60000`. If true, return immediately.
- After successful sync, set `_lastSyncTimestamp = Date.now()`.
- On sync error, do NOT update the timestamp (allow retry on next call).

**Debounce window:** 60 seconds (configurable via `frpAgent.autoSyncDebounceMs` setting if desired, but default is 60000).

### FR-4.2 — Logging

When sync is skipped due to debounce:
```
[FRP] Auto-sync: skipped (last sync 12s ago, debounce=60s)
```

When sync runs:
```
[FRP] Auto-sync: running (last sync 75s ago)
```

### FR-4.3 — Explicit Sync Override

The debounce does NOT affect explicit `sync_logs` commands. The `_SKIP_AUTO_SYNC` set already excludes `sync_logs` from auto-sync, so the user's explicit `/logs sync logs` always runs the full sync regardless of debounce state.

After an explicit sync, `_lastSyncTimestamp` should be updated so that subsequent auto-syncs are debounced from the explicit sync time.

---

## 7. Edge Cases

### 7.1 — LLM produces text THEN makes a tool call in the same response

**Scenario:** The LLM responds with "Let me search for that..." (text) followed by a `search_jobs` tool call.

**With Epic 1 streaming:** The text "Let me search for that..." arrives as text parts in the `for await` loop BEFORE the tool call part. At that point, `toolCallMade` is still `false`, so the text IS streamed to the user. Then the tool call arrives, `toolCallMade` becomes `true`, the loop continues executing the tool, and the outer check sees `toolCallMade = true` → continues the while loop.

**User sees:** "Let me search for that..." followed by "Step 2: calling search_jobs..." progress indicator. This is acceptable — it shows the agent is working.

**On the next while iteration:** `finalText` resets to `''`, `toolCallMade` resets to `false`. The previous "Let me search for that..." text is gone from `finalText` but already visible to the user.

### 7.2 — Simple query with no tool calls

**Scenario:** User asks "what is the FRP system?" and the LLM responds with pure text.

**With Epic 1:** Text streams immediately. `!toolCallMade` is true. `stepResults.length === 0`. The code returns directly — no two-phase generation needed.

**With Epic 2:** The bypass condition `stepResults.length === 0` prevents the two-phase path. Behaviour is identical to Epic 1 alone.

### 7.3 — CRUD plan text

**Scenario:** User asks to "create and configure job X and Y" and the CRUD planning pipeline produces a plan.

**With Epic 1:** The plan text streams token-by-token as it arrives. After the `for await` loop, `finalText.includes('PLAN:')` is true. The CRUD plan block fires, sets `shared.pendingOperation`, and shows "Confirm this plan?".

**Key difference from current:** The plan is already visible (streamed) when the confirmation prompt appears. Currently, the plan and confirmation appear together as a block. The new behaviour is arguably better — the user can read the plan as it forms.

### 7.4 — Cancellation during streaming

**Scenario:** User cancels the request while tokens are streaming.

**Behaviour:** The `for await` loop throws a cancellation error (from the `token` parameter). The `try/catch` around the while loop catches it. No change from current behaviour — cancellation works the same way whether text was buffered or streamed.

### 7.5 — selectIntermediateModel() returns null

**Scenario:** No free model is available (e.g., Copilot subscription doesn't include GPT-4.1).

**Behaviour:** `routingModel` is `null`, `effectiveRoutingModel` falls back to `answerModel` (the premium model). The behaviour is identical to the current code — every step uses the premium model. No degradation.
