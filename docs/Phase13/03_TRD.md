# Phase 13 TRD — Technical Requirements Document
## FRP Agent VS Code Extension — Response Speed & Streaming Architecture Upgrade

**Document type:** Technical Requirements Document
**Parent:** Phase 13 PRD (`01_PRD.md`), FRD (`02_FRD.md`)
**Status:** Draft
**Date:** March 2026

---

## 1. Purpose

This document specifies exactly which files and functions change, what the before/after code looks like for each change, and the precise sequencing of implementation. Every story from the PRD is mapped to one or more concrete code changes with exact file paths, function names, line numbers, and surrounding context.

---

## 2. Affected Files

| File | Change type | Stories | Estimated lines changed |
|---|---|---|---|
| `extension/chat/participant.js` | Modify — 6 changes across `agentLoop()`, `executeConfirmedCrudPlan()`, and new functions | S-101, S-102, S-103, S-201, S-202, S-301, S-302 | ~80 lines |
| `extension/copilot/tool.js` | Modify — 1 change to `_autoSync()` | S-401 | ~8 lines |

**No new files are created. No backend changes. No database migrations. No new dependencies.**

---

## 3. Implementation Sequence

```
Phase 13a (Safe, Immediate):
  Step 1: participant.js  — Stream tokens in agentLoop() (S-101)
  Step 2: participant.js  — Stream tokens in executeConfirmedCrudPlan() (S-102)
  Step 3: participant.js  — Remove duplicate finalText dumps + fix CRUD plan (S-103)
  Step 4: tool.js         — Debounce _autoSync() (S-401)

Phase 13b (Architectural):
  Step 5: participant.js  — Add selectIntermediateModel() (S-301)
  Step 6: participant.js  — Add buildFinalAnswerContext() (S-201)
  Step 7: participant.js  — Restructure agentLoop() end: two-phase + multi-model (S-202, S-302)
```

Steps 1–4 are safe, additive changes that can be shipped immediately. Each is independently testable.
Steps 5–7 change the control flow and should be validated with timing measurements.

---

## 4. Epic 1: Token Streaming — `participant.js`

### 4.1 Change S-101: Stream tokens in `agentLoop()`

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()` starting at line 2410
**Target:** The `else` branch inside `for await (const part of response.stream)` — line 2517

**Before (lines 2517–2523):**
```javascript
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        if (toolCallMade) {
          reasoningText += text;
        } else {
          finalText += text;
          reasoningText += text;
        }
      }
```

**After:**
```javascript
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        if (toolCallMade) {
          reasoningText += text;
        } else {
          stream.markdown(text);   // Stream token immediately to user
          finalText += text;
          reasoningText += text;
        }
      }
```

**Change:** One line added — `stream.markdown(text);` — before `finalText += text;`.

**Why `finalText` is still kept:** It's used for CRUD plan detection (`finalText.includes('PLAN:')`) at line 2529 and for length logging at line 2546. It serves as a record of what was streamed.

**Why `reasoningText` is unchanged:** It continues to log LLM reasoning to the output channel for debugging.

---

### 4.2 Change S-102: Stream tokens in `executeConfirmedCrudPlan()`

**File:** `extension/chat/participant.js`
**Function:** `executeConfirmedCrudPlan()` starting at line 2197
**Target:** The `else` branch inside `for await (const part of response.stream)` — line 2249

**Before (lines 2247–2250):**
```javascript
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        finalText += text;
      }
```

**After:**
```javascript
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        stream.markdown(text);   // Stream token immediately to user
        finalText += text;
      }
```

**Change:** One line added — `stream.markdown(text);`.

---

### 4.3 Change S-103a: Remove duplicate `stream.markdown(finalText)` in `agentLoop()`

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`
**Target:** The `if (finalText.trim())` block after the `for await` loop — lines 2544–2549

**Before (lines 2544–2549):**
```javascript
      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] agentLoop: final report at step ${step} (${finalText.length} chars)`
        );
        stream.markdown(finalText);
      } else {
```

**After:**
```javascript
      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] agentLoop: final report at step ${step} (${finalText.length} chars)`
        );
        // Text already streamed token-by-token in the for-await loop (S-101)
      } else {
```

**Change:** Remove `stream.markdown(finalText);` — text was already streamed.

---

### 4.4 Change S-103b: Remove duplicate `stream.markdown(finalText)` in `executeConfirmedCrudPlan()`

**File:** `extension/chat/participant.js`
**Function:** `executeConfirmedCrudPlan()`
**Target:** The `if (finalText.trim())` block — line 2255

**Before (lines 2253–2256):**
```javascript
    if (!toolCallMade) {
      if (finalText.trim()) {
        stream.markdown(finalText);
      } else {
```

**After:**
```javascript
    if (!toolCallMade) {
      if (finalText.trim()) {
        // Text already streamed token-by-token (S-102)
      } else {
```

**Change:** Remove `stream.markdown(finalText);`.

---

### 4.5 Change S-103c: Fix CRUD plan detection duplicate

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`
**Target:** The CRUD plan detection block — line 2530

**Before (lines 2528–2531):**
```javascript
      if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
        stream.markdown(`\n${finalText}\n`);
        shared.pendingOperation = {
          type: 'crud_plan',
```

**After:**
```javascript
      if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
        // Plan text already streamed token-by-token (S-101) — don't duplicate
        shared.pendingOperation = {
          type: 'crud_plan',
```

**Change:** Remove `stream.markdown(\`\n${finalText}\n\`);`.

---

## 5. Epic 4: Auto-Sync Debounce — `tool.js`

### 5.1 Change S-401: Add timestamp-based debounce to `_autoSync()`

**File:** `extension/copilot/tool.js`
**Function:** `_autoSync()` at line 112

**Before (lines 105–139):**
```javascript
/**
 * Run an incremental log sync if log-related settings are configured.
 * Silently skips if logDbPath or log folders are not set.
 * Errors are logged but never block the primary command.
 */
async function _autoSync(shared) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const logDbPath = config.get('logDbPath', '');
  if (!logDbPath) return;

  const emailFolder = config.get('emailLogFolder', '');
  const sftpFolder = config.get('sftpLogFolder', '');
  if (!emailFolder && !sftpFolder) return;

  const retentionMonths = config.get('logRetentionMonths', 3);
  const args = ['sync_logs'];
  if (emailFolder) args.push('--log-folder', emailFolder);
  if (sftpFolder) args.push('--sftp-log-folder', sftpFolder);
  args.push('--db-path', logDbPath);
  args.push('--retention-months', String(retentionMonths));

  try {
    await runCliJson(args);
  } catch (err) {
    if (shared.outputChannel) {
      shared.outputChannel.appendLine(`[FRP] Auto-sync: ${err.message}`);
    }
  }
}
```

**After:**
```javascript
/**
 * Run an incremental log sync if log-related settings are configured.
 * Silently skips if logDbPath or log folders are not set.
 * Debounces to at most once per 60 seconds to avoid redundant spawns
 * during multi-step agentic loops.
 * Errors are logged but never block the primary command.
 */
let _lastSyncTimestamp = 0;

async function _autoSync(shared) {
  const now = Date.now();
  if (now - _lastSyncTimestamp < 60000) {
    if (shared.outputChannel) {
      shared.outputChannel.appendLine(
        `[FRP] Auto-sync: skipped (last sync ${Math.round((now - _lastSyncTimestamp) / 1000)}s ago, debounce=60s)`
      );
    }
    return;
  }

  const config = vscode.workspace.getConfiguration('frpAgent');
  const logDbPath = config.get('logDbPath', '');
  if (!logDbPath) return;

  const emailFolder = config.get('emailLogFolder', '');
  const sftpFolder = config.get('sftpLogFolder', '');
  if (!emailFolder && !sftpFolder) return;

  const retentionMonths = config.get('logRetentionMonths', 3);
  const args = ['sync_logs'];
  if (emailFolder) args.push('--log-folder', emailFolder);
  if (sftpFolder) args.push('--sftp-log-folder', sftpFolder);
  args.push('--db-path', logDbPath);
  args.push('--retention-months', String(retentionMonths));

  try {
    await runCliJson(args);
    _lastSyncTimestamp = Date.now();   // Update only on success
  } catch (err) {
    if (shared.outputChannel) {
      shared.outputChannel.appendLine(`[FRP] Auto-sync: ${err.message}`);
    }
    // Do NOT update timestamp on failure — allow retry on next call
  }
}
```

**Changes:**
1. New module-level variable `_lastSyncTimestamp` (initialized to 0)
2. Debounce check at function entry — returns immediately if < 60 seconds since last sync
3. Logging when debounce skips a sync
4. `_lastSyncTimestamp = Date.now()` after successful sync

**Debounce window:** 60 seconds. This means during a 5-step agentic loop that takes ~30 seconds, only the first `backendCall()` triggers a sync. The remaining 4 calls skip instantly.

---

## 6. Epic 2: Two-Phase Generation — `participant.js`

### 6.1 Change S-201: Add `buildFinalAnswerContext()` helper

**File:** `extension/chat/participant.js`
**Location:** After `buildMessageHistory()` (approximately line 1596), before the CRUD helpers section.

**New function (insert — no existing code replaced):**
```javascript
/**
 * Build a clean prompt for final answer generation (Phase 13 two-phase).
 * Includes system prompt + domain knowledge + tool results + user question.
 * Excludes: tool schemas, routing guidance, playbooks.
 */
function buildFinalAnswerContext(stepResults, userPrompt) {
  const dataSections = stepResults.map((sr, i) => {
    const resultStr = typeof sr.result === 'string'
      ? sr.result
      : JSON.stringify(sr.result, null, 2);
    // Truncate very large results to keep the prompt manageable
    const truncated = resultStr.length > 3000
      ? resultStr.slice(0, 3000) + '\n... (truncated)'
      : resultStr;
    const inputStr = Object.entries(sr.input)
      .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
      .join(', ');
    return `### Step ${sr.step}: ${sr.tool}(${inputStr})\n<data>\n${truncated}\n</data>`;
  }).join('\n\n');

  const answerPrompt = [
    SYSTEM_PROMPT,
    '',
    DOMAIN_KNOWLEDGE,
    '',
    '## Retrieved Data',
    '',
    'The following data was retrieved to answer the user\'s question:',
    '',
    dataSections,
    '',
    '## User\'s Question',
    userPrompt,
    '',
    'Answer the user\'s question using the retrieved data above.',
    'Format your response with Markdown as specified in the system prompt.',
  ].join('\n');

  return [vscode.LanguageModelChatMessage.User(answerPrompt)];
}
```

---

### 6.2 Change S-202: Two-phase generation in `agentLoop()`

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()`
**Target:** The `if (!toolCallMade)` block after the `for await` loop — lines 2527–2557

This change restructures the "LLM is done" exit path. When the agentic loop has collected tool results AND the LLM signals it's done (text instead of tool call), we discard the text from the tool-calling response and generate a fresh answer without tools.

**Before (lines 2527–2557):**
```javascript
    // If no tool was called, the LLM is done
    if (!toolCallMade) {
      // CRUD planning Phase 1 plan detection
      if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
        stream.markdown(`\n${finalText}\n`);
        shared.pendingOperation = {
          type: 'crud_plan',
          params: { planText: finalText, messages: [...messages] },
        };
        stream.markdown('\n**Confirm this plan?**\n');
        return {
          followUps: [
            { prompt: 'Confirm', label: 'Confirm ✓' },
            { prompt: 'Cancel', label: 'Cancel ✗' },
          ],
        };
      }

      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] agentLoop: final report at step ${step} (${finalText.length} chars)`
        );
        stream.markdown(finalText);
      } else {
        shared.outputChannel.appendLine('[FRP] agentLoop: empty response — compiling fallback');
        stream.markdown(compilePipelineReport(stepResults, { displayName: pipelineName || 'Query', maxSteps }));
      }
      return buildPipelineResult(stepResults);
    }
```

**After:**
```javascript
    // If no tool was called, the LLM is done
    if (!toolCallMade) {
      // CRUD planning Phase 1 plan detection
      if (pipelineName === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
        // Plan text already streamed token-by-token (S-101) — don't duplicate
        shared.pendingOperation = {
          type: 'crud_plan',
          params: { planText: finalText, messages: [...messages] },
        };
        stream.markdown('\n**Confirm this plan?**\n');
        return {
          followUps: [
            { prompt: 'Confirm', label: 'Confirm ✓' },
            { prompt: 'Cancel', label: 'Cancel ✗' },
          ],
        };
      }

      // ── Two-phase generation (Phase 13b) ──
      // If tools were called, generate the final answer in a separate
      // text-only call (no tool schemas → faster first-token, cleaner output).
      if (stepResults.length > 0) {
        shared.outputChannel.appendLine(
          `[FRP] agentLoop: two-phase — generating final answer (${stepResults.length} tool results, no tools)`
        );
        const answerModel = await selectModel(request);
        if (answerModel) {
          const finalMessages = buildFinalAnswerContext(stepResults, prompt);
          try {
            const answerResponse = await answerModel.sendRequest(finalMessages, {}, token);
            for await (const chunk of answerResponse.text) {
              stream.markdown(chunk);
            }
          } catch (err) {
            shared.outputChannel.appendLine(`[FRP] agentLoop: two-phase LLM error: ${err.message}`);
            // Fallback: show the text from the tool-calling response (already partially streamed)
            if (!finalText.trim()) {
              stream.markdown(compilePipelineReport(stepResults, { displayName: pipelineName || 'Query', maxSteps }));
            }
          }
        } else {
          // No model — compile a raw report
          stream.markdown(compilePipelineReport(stepResults, { displayName: pipelineName || 'Query', maxSteps }));
        }
        return buildPipelineResult(stepResults);
      }

      // Simple query — no tools called. Text already streamed (S-101).
      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] agentLoop: final report at step ${step} (${finalText.length} chars)`
        );
        // Text already streamed token-by-token — nothing to dump
      } else {
        shared.outputChannel.appendLine('[FRP] agentLoop: empty response — compiling fallback');
        stream.markdown(compilePipelineReport(stepResults, { displayName: pipelineName || 'Query', maxSteps }));
      }
      return buildPipelineResult(stepResults);
    }
```

**Key logic:**
1. CRUD plan detection still runs first (unchanged priority)
2. If `stepResults.length > 0`: tools were called → two-phase generation. Build a fresh prompt from step results, call `sendRequest({}, token)` (no tools), stream the answer.
3. If `stepResults.length === 0`: no tools called → simple query. Text already streamed via S-101. Just log and return.
4. Error fallback: if the two-phase LLM call fails, show a compiled report from step results.

**Important interaction with S-101 streaming:** When two-phase is active (`stepResults.length > 0`), the streaming in the `for await` loop (S-101) may have already shown some text to the user — the routing model's "final" text before handing off to two-phase. This creates a potential for mixed output:

To prevent this, when two-phase generation is enabled, the streaming in the `for await` loop should be SUPPRESSED for iterations where `stepResults.length > 0` (tools have been called). This means the S-101 streaming change needs a guard:

**Revised S-101 (with two-phase awareness):**
```javascript
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        if (toolCallMade) {
          reasoningText += text;
        } else {
          // Stream immediately ONLY if no tools have been called yet (simple query).
          // If tools were called (stepResults.length > 0), two-phase will handle final answer.
          if (stepResults.length === 0) {
            stream.markdown(text);
          }
          finalText += text;
          reasoningText += text;
        }
      }
```

This ensures:
- **Simple queries** (no tool calls): text streams immediately → user sees answer forming
- **After tool calls**: text is NOT streamed → two-phase generates a clean final answer

---

## 7. Epic 3: Multi-Model Strategy — `participant.js`

### 7.1 Change S-301: Add `selectIntermediateModel()` function

**File:** `extension/chat/participant.js`
**Location:** After `selectModel()` (line 1530), before `generateAnswer()`.

**New function (insert — no existing code replaced):**
```javascript
/**
 * Select a free/fast model for intermediate work (tool routing, reasoning).
 * Does NOT use the request's model — always auto-selects.
 * Mirrors KTS's selectModel(vscode, null) pattern.
 */
async function selectIntermediateModel() {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const intermediateSetting = config.get('intermediateModel', 'auto');

  if (intermediateSetting !== 'auto') {
    try {
      const [model] = await vscode.lm.selectChatModels({ family: intermediateSetting });
      if (model) return model;
    } catch (_) { /* fall through */ }
  }

  for (const family of MODEL_PREFERENCE) {
    try {
      const [model] = await vscode.lm.selectChatModels({ family });
      if (model) return model;
    } catch (_) { /* continue */ }
  }

  try {
    const all = await vscode.lm.selectChatModels();
    if (all.length > 0) return all[0];
  } catch (_) { /* nothing available */ }

  return null;
}
```

**Note:** This function is nearly identical to `selectModel()` but skips the `request.model` check. It always falls through to the auto-select chain, which starts with GPT-4.1 (a free model).

---

### 7.2 Change S-302: Dual model usage in `agentLoop()`

**File:** `extension/chat/participant.js`
**Function:** `agentLoop()` at line 2418

**Before (lines 2418–2421):**
```javascript
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('⚠️ No language model available. Please ensure GitHub Copilot is active.\n');
    return { followUps: [] };
  }
```

**After:**
```javascript
  const answerModel = await selectModel(request);
  if (!answerModel) {
    stream.markdown('⚠️ No language model available. Please ensure GitHub Copilot is active.\n');
    return { followUps: [] };
  }
  const routingModel = await selectIntermediateModel() || answerModel;

  shared.outputChannel.appendLine(
    `[FRP] agentLoop: routing model=${routingModel.id || routingModel.name || 'unknown'}, ` +
    `answer model=${answerModel.id || answerModel.name || 'unknown'}`
  );
```

Then in the while loop, change the `model.sendRequest()` call:

**Before (line 2455):**
```javascript
      response = await model.sendRequest(messages, { tools: scopedTools }, token);
```

**After:**
```javascript
      response = await routingModel.sendRequest(messages, { tools: scopedTools }, token);
```

And in the two-phase generation block (from §6.2), `answerModel` is already used:
```javascript
      const answerResponse = await answerModel.sendRequest(finalMessages, {}, token);
```

**Summary of model usage after all changes:**
- `routingModel` (free/fast, e.g. GPT-4.1) → all `sendRequest(messages, { tools }, token)` calls
- `answerModel` (user's premium, e.g. Claude Sonnet 4) → the final `sendRequest(finalMessages, {}, token)` call (no tools)

---

## 8. Verification Plan

### 8.1 Existing Tests

All existing JavaScript tests in `extension/test/` must pass without modification. The changes are:
- Streaming: additive (extra `stream.markdown()` call) — no API change
- Two-phase: produces the same Markdown output, just from a different code path
- Multi-model: falls back to the same model if no intermediate model is available
- Auto-sync debounce: reduces sync calls but doesn't change their behaviour

### 8.2 Manual Verification — Phase 13a

| Test | How to verify | Expected result |
|---|---|---|
| Simple query streaming | Ask `@frp what is the FRP system?` | Answer appears token-by-token, not as a block |
| Multi-step query streaming | Ask `@frp tell me about job CMBS_GreyCo` | Progress → tool calls → answer streams token-by-token |
| CRUD plan streaming | Ask `@frp /staging create and configure two jobs` | Plan streams token-by-token → "Confirm this plan?" appears after |
| No duplicate output | All above queries | Response text appears exactly once |
| Auto-sync debounce | Run a multi-step query and check Output tab | `Auto-sync: skipped (last sync Ns ago)` messages for calls 2–N |
| Explicit sync override | Run `@frp /logs sync logs` | Sync runs even if debounce window hasn't elapsed |

### 8.3 Manual Verification — Phase 13b

| Test | How to verify | Expected result |
|---|---|---|
| Two-phase generation | Ask `@frp investigate job CMBS_GreyCo` and check Output tab | Log shows `two-phase — generating final answer (N tool results, no tools)` |
| Multi-model routing | Check Output tab after a multi-step query | Log shows `routing model=gpt-4.1, answer model=claude-sonnet-4` (or similar) |
| Fallback when no free model | Configure `frpAgent.intermediateModel` to an unavailable model | Falls back to the answer model; behaviour identical to current |
| Answer quality | Compare answer from Phase 13b to same query before Phase 13b | Same content quality (may differ in exact wording, but same data coverage) |

### 8.4 Timing Measurement Protocol

To validate each change's contribution, measure these timings before and after:

1. **Simple query (no tools):** `@frp what is the FRP system?`
   - Measure: time from Enter to first visible text
   - Expected improvement: 3-5s → <1.5s (streaming makes text appear as it generates)

2. **Single-tool query:** `@frp list all email jobs`
   - Measure: time from Enter to first visible answer text (after progress bar)
   - Expected improvement: noticeable with two-phase (final answer generated without tools)

3. **Multi-step query:** `@frp investigate job CMBS_GreyCo`
   - Measure: time from Enter to first visible answer text
   - Expected improvement: visible with all four changes combined

4. **Check Output tab** for `Auto-sync: skipped` messages to confirm debounce is working.

---

## 9. Rollback Plan

Each change can be rolled back independently:

| Change | Rollback |
|---|---|
| Streaming (S-101/102) | Remove `stream.markdown(text)` lines; restore `stream.markdown(finalText)` |
| Two-phase (S-202) | Remove the `if (stepResults.length > 0)` block; restore `stream.markdown(finalText)` |
| Multi-model (S-302) | Change `routingModel` back to `model`; remove `selectIntermediateModel()` |
| Auto-sync debounce (S-401) | Remove `_lastSyncTimestamp` and debounce check |

No database migrations, settings file changes, or backend changes need to be rolled back.
