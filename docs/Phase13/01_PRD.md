# Phase 13 PRD — Response Speed & Streaming Architecture Upgrade
## FRP Agent VS Code Extension

**Document type:** Product Requirements Document
**Phase:** 13
**Status:** Draft — awaiting approval before implementation begins
**Date:** March 2026
**Author:** Engineering (GitHub Copilot assisted)

---

## 1. Executive Summary

Phase 13 addresses the perceived response latency of the FRP Agent by closing four structural gaps identified by comparing FRP's `participant.js` to the KTS Agent's `participant.js` — both of which use the same VS Code Chat API and the same Copilot LLM models.

The changes are ordered by evidence strength:

| # | Change | Evidence | Risk | Visible impact |
|---|--------|----------|------|----------------|
| 1 | Stream tokens immediately | **Proven** — direct code diff (FRP buffers, KTS streams) | Low | User sees first text in ~1s instead of 5-10s |
| 2 | Two-phase generation | **First-principles** — removing `{tools}` on final call eliminates tool-schema processing | Medium | Faster first-token on final answer |
| 3 | Multi-model strategy | **Proven pattern** — KTS uses free GPT-4.1 for intermediate work | Medium | Reduces premium model cost; potentially faster routing |
| 4 | Auto-sync debounce | **Proven** — tool.js spawns sync_logs before every backend call | Low | Eliminates N-1 redundant subprocess spawns per query |

---

## 2. Problem Statement

### 2.1 The Perceived Latency Problem

Users observe that the FRP Agent feels significantly slower than the KTS Agent, despite both extensions sharing:
- The same VS Code Chat Participant API (`vscode.chat.createChatParticipant`)
- The same Copilot LLM models (`vscode.lm.selectChatModels`)
- The same PyInstaller backend architecture (Python CLI → EXE → JSON response)
- Backend calls that complete quickly (confirmed in the VS Code Output tab)

The latency is between "backend data arrives" and "user sees formatted response" — the rendering phase.

### 2.2 Investigation History (Transparency)

This problem was investigated three times. Each iteration was informed by the user's counterevidence that invalidated the previous hypothesis:

**Iteration 1 — "14K token system prompt + 36 tool schemas cause the slowdown"**
- Hypothesis: The combined weight of `SYSTEM_PROMPT` (~1,500 tokens) + `DOMAIN_KNOWLEDGE` (~5,000 tokens) + `ROUTING_GUIDANCE` (~1,200 tokens) + `FRP_TOOLS` (36 schemas, ~6,000 tokens) creates ~14K baseline tokens per call, causing latency.
- **Disproved** by the user: *"You (Copilot) process 192K tokens and you're fast."* Token count at this scale does not explain the latency. The model's context window is not the bottleneck.

**Iteration 2 — "Don't use the LLM for formatting — use `formatRawData()` directly"**
- Hypothesis: Every tool result passes through `generateOrFallback()` → `generateAnswer()` (a full LLM roundtrip) to format JSON as Markdown, when JavaScript can do it in 0ms via `formatRawData()`.
- **Rejected** by the user: *"I like the polished LLM output."* The LLM-formatted responses are a valued feature. Removing them degrades quality.

**Iteration 3 — "Three structural differences between FRP and KTS explain the gap"**
- Hypothesis: FRP's `agentLoop()` buffers text instead of streaming, pays a tool-calling tax on every call, and uses the premium model for all steps. KTS streams immediately, passes no tools during generation, and uses a free model for intermediate work.
- **Supported** by line-by-line code comparison between both extensions. All evidence cited below with exact file locations.

### 2.3 The Four Structural Gaps

#### Gap 1: Text Buffered, Then Dumped (PROVEN — code comparison)

**FRP `agentLoop()`** — `extension/chat/participant.js`:

In the main `for await (const part of response.stream)` loop, text parts are accumulated in a local variable `finalText`, never shown to the user during generation:
```javascript
// FRP: text goes into a buffer
finalText += text;
reasoningText += text;
```

Then, only AFTER the entire `for await` loop completes and the `while` loop detects `!toolCallMade`:
```javascript
// FRP: dump everything at once
stream.markdown(finalText);
```

The user sees **zero output** while the LLM generates the answer. Then the entire response appears instantaneously.

**KTS `generateAnswer()`** — `gsf_ir_kts_agentic_system/extension/chat/participant.js`:
```javascript
// KTS: stream each token as it arrives
for await (const chunk of response.text) {
  if (!bufferMode) stream.markdown(chunk);
  collectedChunks.push(chunk);
}
```

The user sees the first token within ~1 second. The answer builds progressively in the chat panel.

**Important note:** FRP's own `generateAnswer()` function at line ~1557 DOES stream properly — but it is only used in confirmation flows via `generateOrFallback()`. The main code path through `agentLoop()` does NOT stream.

#### Gap 2: Tool Schemas Passed on Final Answer Generation (FIRST-PRINCIPLES)

**FRP `agentLoop()`:**
```javascript
response = await model.sendRequest(messages, { tools: scopedTools }, token);
```

EVERY iteration — including the final one where the LLM produces its text answer — passes `{ tools: scopedTools }`. The model must evaluate all 36 tool schemas as candidates before deciding to produce text.

**KTS `generateAnswer()`:**
```javascript
const response = await model.sendRequest(messages, {}, token);
```

No tools passed. Pure text generation mode.

**Impact:** When `{tools}` is passed to `model.sendRequest()`, the VS Code Language Model API activates the model's function-calling mode. The model must process every tool schema before generating its first token. Removing `{tools}` on the final generation step eliminates this overhead.

**Caveat:** I cannot provide an exact millisecond measurement for this overhead. It is a first-principles argument based on how tool-calling mode works in LLMs. This should be validated with timing measurements before/after implementation.

#### Gap 3: Same Premium Model for All Steps (PROVEN — code comparison)

**FRP `selectModel()`:**
```javascript
async function selectModel(request) {
  if (request.model) return request.model;
  // ... fallback chain
}
```

Single function, single model. The user's chosen model (e.g., Claude Sonnet 4) is used for EVERY tool-routing step AND the final answer. In a 5-step agentic loop, that's 5 premium model calls.

**KTS `selectModel()`:**
```javascript
async function selectModel(vscode, requestModel) {
  // 1. User's model (highest priority)
  if (requestModel && typeof requestModel.sendRequest === 'function') {
    return requestModel;
  }
  // 2. Setting override
  // 3. Fallback: auto-select gpt-4.1 → gpt-4o → claude-sonnet-4 → gpt-4o-mini
}
```

Called with `selectModel(vscode, request.model)` for the final answer (user's premium model).
Called with `selectModel(vscode, null)` for critique/CRAG loops (falls back to GPT-4.1, which is free).

FRP could use the same pattern: free/fast model for tool routing decisions, premium model only for the final user-facing answer.

#### Gap 4: Auto-Sync Before Every Backend Call (PROVEN — code review)

**FRP `backendCall()`** — `extension/copilot/tool.js`:
```javascript
if (!_SKIP_AUTO_SYNC.has(command)) {
  await _autoSync(shared);
}
```

Every backend call (except `sync_logs`, `status`, `log_search`) triggers `_autoSync()`, which spawns `runCliJson(['sync_logs', ...])`. During a 5-step agentic loop with 5 backend calls, this means **5 subprocess spawns** — each with PyInstaller EXE startup overhead — before the actual command runs.

**KTS equivalent:** No auto-sync. Backend indexes data on demand or via explicit commands.

---

## 3. Goals

### 3.1 In Scope (Phase 13)

| ID | Goal | Epic |
|---|---|---|
| G-1 | Stream LLM text tokens to the chat panel as they arrive, so the user sees the answer forming in real-time. | 1 |
| G-2 | Apply the same streaming fix to `executeConfirmedCrudPlan()`, which has an identical buffering pattern. | 1 |
| G-3 | After the agentic loop finishes tool calls, generate the final answer in text-only mode (`{}` — no tools) for faster first-token. | 2 |
| G-4 | Add a `selectIntermediateModel()` function that returns a free/fast model (GPT-4.1) for tool routing steps. | 3 |
| G-5 | Use the intermediate model for agentic loop tool routing; use the user's premium model for the final answer. | 3 |
| G-6 | Debounce `_autoSync()` so it runs at most once per 60 seconds, regardless of how many backend calls are made. | 4 |
| G-7 | All existing JS tests pass unchanged. No visible behaviour change to the user except faster responses. | All |

### 3.2 Out of Scope (Phase 13)

- Reducing the system prompt size or tool count — established in §2.2 as not the bottleneck.
- Removing LLM formatting in favour of `formatRawData()` — explicitly rejected by the user.
- Backend Python optimizations — backend calls are already fast.
- Any changes to the backend CLI, Python code, or PyInstaller packaging.
- Any new tools, commands, or features.

### 3.3 Implementation Order

Phase 13 is designed to be shipped in two sub-phases:

**Phase 13a (Safe, Immediate):** Epic 1 + Epic 4
- Streaming fix: change ~10 lines in `participant.js`. No architectural change.
- Auto-sync debounce: change ~5 lines in `tool.js`. No architectural change.
- Risk: Very low. Both changes are additive and preserve all existing behaviour.

**Phase 13b (Architectural):** Epic 2 + Epic 3
- Two-phase generation: restructures the end of `agentLoop()` to make a separate text-only call.
- Multi-model: adds a new model selection function and changes how models are assigned in the loop.
- Risk: Medium. Changes the control flow of the agentic loop. Should be validated with timing measurements.

---

## 4. User Stories

### Epic 1 — Token Streaming (S-1xx)

**Epic goal:** The user sees the FRP Agent's answer forming token-by-token in the chat panel, not as a single block dump after a long wait.

---

**S-101 — Stream text tokens in agentLoop()**

> *As a user I want to see the FRP Agent's answer appearing progressively in the chat panel — just like other Copilot Chat agents — so I don't have to stare at a blank panel wondering if the agent is working.*

**Current behaviour:** `agentLoop()` accumulates text in `finalText`, then calls `stream.markdown(finalText)` once after the response stream completes. The user sees nothing during generation.

**Target behaviour:** Each text token is sent to `stream.markdown()` as it arrives from the LLM response stream. The user sees the answer forming in real-time.

**Acceptance criteria:**
```gherkin
Feature: Token-by-token streaming

  Scenario: Simple query with no tool calls
    Given the user asks "what is the FRP system?"
    When the FRP Agent generates a text response
    Then the chat panel shows the answer forming token-by-token
    And the first visible token appears within ~1 second of the LLM starting generation

  Scenario: Multi-step query with final answer
    Given the user asks "tell me about job CMBS_GreyCo"
    When the agentic loop calls tools and then generates a final text answer
    Then tool calls show progress indicators as before
    And the final answer streams token-by-token (not as a block dump)
```

---

**S-102 — Stream text tokens in executeConfirmedCrudPlan()**

> *As a user waiting for a CRUD plan to execute I want to see the plan execution results streaming progressively, not appearing all at once after a long pause.*

**Current behaviour:** `executeConfirmedCrudPlan()` has an identical agentic loop with the same buffering pattern — `finalText += text` followed by `stream.markdown(finalText)`.

**Target behaviour:** Same as S-101 — stream each text token immediately.

---

**S-103 — Remove duplicate finalText dump**

> *After implementing S-101, the `stream.markdown(finalText)` call after the `for await` loop must be removed, or the user will see the entire answer twice.*

**Acceptance criteria:**
```gherkin
  Scenario: No duplicate output
    Given the user asks any question
    When the FRP Agent responds
    Then the response appears exactly once in the chat panel
    And no text is duplicated
```

---

### Epic 2 — Two-Phase Generation (S-2xx)

**Epic goal:** After the agentic loop finishes its tool calls, generate the final answer in a separate `model.sendRequest()` call WITHOUT tool schemas — pure text generation mode.

---

**S-201 — Build final answer context from step results**

> *As the FRP Agent I need a helper function that takes the agentic loop's step results and produces a clean prompt for final answer generation, containing: system prompt, domain knowledge, user's question, and all tool results as structured data — but NOT tool schemas or routing guidance.*

**Target function:** `buildFinalAnswerContext(systemPrompt, domainKnowledge, stepResults, userPrompt)`

Returns a `LanguageModelChatMessage[]` array suitable for a text-only `sendRequest()`.

---

**S-202 — Final answer generation without tools**

> *As a user I want the FRP Agent's final answer to be generated without tool-schema overhead, so the first token arrives faster.*

**Current behaviour:** The agentic loop's last iteration calls `model.sendRequest(messages, { tools: scopedTools }, token)` even when the LLM is producing text (not calling tools). The model must evaluate 36 tool schemas before producing its first token.

**Target behaviour:** When the agentic loop detects that tools have been called AND the LLM is ready to produce a final answer, a SEPARATE `model.sendRequest(finalMessages, {}, token)` call is made — no tools — and the response is streamed token-by-token.

**Trigger condition:** `!toolCallMade && stepResults.length > 0` — the LLM previously called tools and now on this iteration decided to produce text instead of calling another tool.

**Bypass condition:** `!toolCallMade && stepResults.length === 0` — the LLM never called any tools (simple query). In this case, the response is already streaming via Epic 1 — no two-phase needed.

---

**S-203 — Preserve single-step queries**

> *When the user asks a simple question that doesn't require tool calls (e.g., "what is the FRP system?"), the response should stream directly without an extra generation step.*

**Acceptance criteria:**
```gherkin
  Scenario: Simple query with no tool calls
    Given the user asks "what is the FRP system?"
    When the LLM produces text on the first iteration
    Then the text is streamed immediately (Epic 1)
    And no additional model.sendRequest() call is made
    And the response is identical to the current behaviour (minus the buffering delay)
```

---

### Epic 3 — Multi-Model Strategy (S-3xx)

**Epic goal:** Use a free/fast model (GPT-4.1) for tool routing decisions during the agentic loop, and the user's premium model only for the final answer generation.

---

**S-301 — Add selectIntermediateModel()**

> *As the FRP extension I need a function that returns a free/fast model (GPT-4.1) for intermediate work like tool selection, falling back through available models if GPT-4.1 is unavailable.*

**Function signature:** `selectIntermediateModel()` — takes no request object, always returns an auto-selected model via `vscode.lm.selectChatModels()`.

**KTS evidence:** KTS's `selectModel(vscode, null)` uses the exact same pattern — when `requestModel` is null, it falls back through the preference chain `gpt-4.1 → gpt-4o → claude-sonnet-4 → gpt-4o-mini`.

---

**S-302 — Use intermediate model for tool routing in agentLoop()**

> *As the FRP Agent I want to use the free intermediate model for all tool-routing iterations of the agentic loop, so that the premium model budget is reserved for the final answer.*

**Current behaviour:** `agentLoop()` calls `selectModel(request)` once and uses that model for EVERY iteration.

**Target behaviour:** `agentLoop()` selects TWO models:
1. `intermediateModel` ← `selectIntermediateModel()` — for tool routing (steps where LLM picks tools)
2. `answerModel` ← `selectModel(request)` — for the final answer generation (Epic 2)

---

**S-303 — Premium model for final answer only**

> *As a user I want to see the same high-quality formatted answer I currently get, generated by the model I chose — but with faster response time because intermediate routing used a free model.*

**Acceptance criteria:**
```gherkin
  Scenario: Multi-step query uses two models
    Given the user selects Claude Sonnet 4 as their model
    When the user asks "investigate job CMBS_GreyCo"
    Then tool routing steps (search_jobs, job_detail, etc.) use GPT-4.1 or similar free model
    And the final formatted answer is generated by Claude Sonnet 4
    And the answer quality is identical to the current behaviour
```

---

### Epic 4 — Auto-Sync Debounce (S-4xx)

**Epic goal:** Prevent redundant `sync_logs` subprocess spawns during multi-step queries.

---

**S-401 — Debounce _autoSync() to once per 60 seconds**

> *As the FRP extension I want to avoid spawning `sync_logs` before every backend call, because during a 5-step agentic loop this creates 5 redundant subprocess spawns that add cumulative startup overhead.*

**Current behaviour:** `backendCall()` calls `_autoSync()` before EVERY backend call (except `sync_logs`, `status`, `log_search`). Each sync spawns `runCliJson(['sync_logs', ...])`.

**Target behaviour:** `_autoSync()` tracks the timestamp of its last successful run. If called again within 60 seconds, it returns immediately without spawning a subprocess.

**Acceptance criteria:**
```gherkin
  Scenario: Multi-step query with 5 backend calls
    Given the agentic loop calls 5 tools sequentially
    When each tool triggers backendCall()
    Then _autoSync() runs only on the FIRST call
    And the subsequent 4 calls skip sync (debounce window)
    And the VS Code output channel logs "Auto-sync: skipped (debounce)" for skipped calls
```

---

## 5. Out of Scope

| Item | Reason |
|---|---|
| System prompt reduction | Disproved as the bottleneck in §2.2 |
| Tool set reduction | Not the bottleneck; scoped pipelines already exist for /triage and /analyze |
| `formatRawData()` as primary formatter | User prefers LLM-polished output |
| Backend CLI / Python changes | Backend is already fast |
| New features or tools | Phase 13 is performance-only |
| Changes to `SYSTEM_PROMPT`, `DOMAIN_KNOWLEDGE`, or playbooks | No knowledge changes needed |
| Database migrations | No schema changes |

---

## 6. Success Metrics

| Metric | Current (estimated) | Target | How to measure |
|---|---|---|---|
| Time to first visible token (simple query) | 3-5 seconds | < 1.5 seconds | Stopwatch from Enter to first text appearing |
| Time to first visible token (multi-step query) | 5-15 seconds | < 2 seconds for progress + < 1 second for answer start | Same |
| Number of sync_logs spawns per multi-step query | N (= number of tool calls) | 1 | Count in VS Code Output tab |
| Premium model calls per multi-step query | N (= number of loop iterations) | 1 (final answer only) | Count in VS Code Output tab |

**Measurement note:** "Current (estimated)" values are based on observed user experience. Exact measurements should be taken before and after implementation to validate each change's contribution.

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Streaming shows intermediate LLM reasoning to user | Low | Low | Only text produced BEFORE any tool call in the same response would show. In practice, LLMs in tool-calling mode rarely produce text before a tool call. If it happens, it's harmless ("Let me look that up..."). |
| Two-phase generation adds an extra LLM call | Medium | Medium | The extra call has NO tools (faster first-token) and shorter prompt (no routing guidance). Net effect should be neutral or positive. Validate with timing. |
| Free model (GPT-4.1) makes worse tool routing decisions | Low | Medium | GPT-4.1 is a strong general model. Tool routing is a simple classification task (pick the right tool name from 36 options given a user question). If quality degrades, fall back to the premium model. |
| Auto-sync debounce causes stale log data | Very low | Low | 60-second window means logs are at most 60 seconds stale. The user can explicitly call `/logs sync logs` to force an immediate sync. |
