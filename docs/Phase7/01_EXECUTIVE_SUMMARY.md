# Phase 7: Executive Summary
## FRP Agent — Two-Stage Intent Routing Architecture

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Phase Scope:** Replace monolithic LLM tool-calling router with a two-stage intent classification → tool selection architecture  
**Prerequisites:** Phase 1–6 complete and verified (697 tests passing)

---

## Table of Contents
1. [Executive Overview](#executive-overview)  
2. [Business Context](#business-context)  
3. [Phase 7 Objectives](#phase-7-objectives)  
4. [Architecture Overview](#architecture-overview)  
5. [Architecture Decision Records](#architecture-decision-records)  
6. [Risk Assessment](#risk-assessment)  
7. [Success Criteria](#success-criteria)  
8. [Dependencies & Prerequisites](#dependencies--prerequisites)  
9. [Why Not a Rewrite](#why-not-a-rewrite)  
10. [What Gets Removed](#what-gets-removed)  
11. [What Gets Kept](#what-gets-kept)  
12. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Does Phase 7 Fix?

Phase 7 solves a **fundamental routing accuracy problem** in the `@frp` chat participant. The current architecture sends all 36 tool definitions to the LLM in a single request and asks it to pick the right tool. When a user's question contains overlapping keywords — like asking "any jobs for deal DID = X" (which contains both "jobs" and "deal") — the LLM frequently selects the wrong tool (`search_jobs` instead of `deal_lookup`), producing misleading results.

Three successive fix attempts using regex pre-routing and enhanced tool descriptions all failed. The root cause is architectural: **36 tools in a single decision space is too many for reliable LLM discrimination, especially when user prompts contain keywords that match multiple tool descriptions.**

### What Does Phase 7 Add?

Phase 7 replaces the single-pass monolithic router with a **Two-Stage Routing Architecture**:

| Stage | What It Does | LLM Decision Space |
|---|---|---|
| **Stage 1: Intent Classification** | Classifies the user's prompt into one of 6 domain categories | 6 choices (not 36) |
| **Stage 2: Tool Selection** | Selects the exact tool from the matched category's tool subset | 4–8 tools (category-specific) |

This is the same pattern used by industry-grade agent frameworks: Microsoft Semantic Kernel (Planner → skill invocation), Amazon Bedrock Agents (intent → action groups), and LangChain (ReAct → tool selection). The key insight is **hierarchical decomposition**: reduce a 36-way classification problem into a 6-way problem followed by a ≤8-way problem.

### What Changes for Existing Users?

**Nothing.** Every `@frp` prompt continues to produce the same answers. No backend code changes. No CLI changes. No new dependencies. The user sees the same response format, the same data source indicators, the same follow-up suggestions. The only change is **which path the prompt takes internally** to arrive at the correct tool — and that path becomes dramatically more reliable.

---

## Business Context

### Problem Phase 7 Solves

| Problem | Current State | Phase 7 Solution |
|---|---|---|
| **Routing misclassification** | User asks "any jobs for deal DID = X" → LLM picks `search_jobs` instead of `deal_lookup` → shows 9 unrelated jobs | Stage 1 classifies as `deal_mapping` → Stage 2 sees only 5 deal-related tools → picks `deal_lookup` correctly |
| **36 tools in one decision space** | LLM must discriminate among 36 tools with overlapping descriptions in a single pass | Each stage sees ≤8 options. Total discrimination load drops from 36-way to 6-way + ≤8-way |
| **Regex band-aids don't scale** | Two regex pre-routing patterns added; neither catches all DID query variants; maintainability is poor | Regex intercepts are completely removed. Classification is purely semantic (LLM-based) |
| **Tool description inflation** | Tool descriptions bloated with "Do NOT use for X" and "ALWAYS use this for Y" negative constraints | Descriptions return to clean, affirmative statements. Category boundaries handle disambiguation |
| **DOMAIN_KNOWLEDGE decision tree complexity** | 14-point decision tree with bolded IMPORTANT clauses, still insufficient for correct routing | Simplified to data model reference only. Routing logic moves into structured category definitions |
| **Silent failures** | User gets a confident-sounding wrong answer (9 jobs listed) instead of "not found" | Correct tool selection means correct empty results trigger the deterministic "not found" UX |

### Who Benefits?

| Persona | Benefit |
|---|---|
| **Current User** | DID/deal queries work correctly. "Any jobs for deal X" produces the right answer for the first time |
| **Current Developer** | No more regex whack-a-mole. Adding a new tool = adding it to the right category. No cross-tool description conflicts |
| **Future Maintainer** | Clear, documented architecture. Each category is self-contained with its own tool definitions |

---

## Phase 7 Objectives

| ID | Objective | Deliverable |
|---|---|---|
| P7-1 | Define 6 intent categories with clear boundaries | Category definitions with descriptions and boundary rules |
| P7-2 | Assign all 36 existing tools to their correct category | Category-to-tool mapping table — every tool has exactly one category |
| P7-3 | Build Stage 1 intent classifier | New `classifyIntent()` function that sends a lightweight prompt to the LLM with 6 category descriptions, returns the selected category name |
| P7-4 | Build Stage 2 category-scoped tool router | Modified `routeWithToolCalling()` that receives the category from Stage 1 and sends only that category's tools to the LLM |
| P7-5 | Remove regex pre-routing intercepts | Delete the `dealIntentRe`, `dealIntent2` patterns and the `if (dealMatch)` block from `routeWithToolCalling()` |
| P7-6 | Clean tool descriptions | Remove all negative constraints ("Do NOT use for…") and cross-references ("use deal_lookup instead") from tool descriptions |
| P7-7 | Simplify DOMAIN_KNOWLEDGE | Remove the 14-point decision tree. Keep only the data model reference (three-table pipeline + cross-reference chains) |
| P7-8 | Add routing diagnostics | Log both Stage 1 (category) and Stage 2 (tool) decisions to the output channel for debugging |
| P7-9 | Handle ambiguous/cross-category queries | Define fallback behavior when Stage 1 confidence is low or the category is unclear |
| P7-10 | Validate with known failure cases | Confirm the 3 previously-failing DID queries now route correctly |

---

## Architecture Overview

### Current Architecture (Single-Stage — 36 Tools)

```
User prompt
     │
     ▼
┌─────────────────────────────────────────────────┐
│  routeWithToolCalling()                         │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │ Regex pre-intercept (2 patterns)          │──│──→ deal_lookup (if pattern matches)
│  └───────────────────────────────────────────┘  │
│                    │ (no match)                  │
│                    ▼                             │
│  ┌───────────────────────────────────────────┐  │
│  │ LLM sendRequest()                         │  │
│  │   Input: SYSTEM_PROMPT + DOMAIN_KNOWLEDGE │  │
│  │          + 14-point decision tree          │  │
│  │   Tools: ALL 36 FRP_TOOLS                 │  │
│  │   Output: 1 tool call                     │  │
│  └───────────────────────────────────────────┘  │
│                    │                             │
│                    ▼                             │
│           executeToolCall(tool, input)           │
│                    │                             │
│                    ▼                             │
│       36-branch switch → handler function        │
└─────────────────────────────────────────────────┘
```

**Failure mode:** With 36 tools and overlapping keywords ("jobs" + "deal"), the LLM picks `search_jobs` instead of `deal_lookup`. Regex patches catch some patterns but not all.

### Proposed Architecture (Two-Stage — 6 Categories × ≤8 Tools)

```
User prompt
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 1: classifyIntent()                          │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ LLM sendRequest()                             │  │
│  │   Input: Lightweight category prompt           │  │
│  │   No tools — structured text output            │  │
│  │   Output: category name (1 of 6)               │  │
│  └───────────────────────────────────────────────┘  │
│                    │                                 │
│          category = "deal_mapping"                   │
│                    │                                 │
│                    ▼                                 │
│  STAGE 2: routeWithinCategory(category, prompt)     │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ LLM sendRequest()                             │  │
│  │   Input: Category-specific context prompt      │  │
│  │   Tools: CATEGORY_TOOLS["deal_mapping"]        │  │
│  │          (5 tools, not 36)                     │  │
│  │   Output: 1 tool call                          │  │
│  └───────────────────────────────────────────────┘  │
│                    │                                 │
│                    ▼                                 │
│           executeToolCall(tool, input)               │
│                    │                                 │
│                    ▼                                 │
│       36-branch switch → handler function            │
│       (UNCHANGED — same handlers as before)          │
└─────────────────────────────────────────────────────┘
```

**Why this works:** In Stage 1, "any jobs for deal DID = X" clearly maps to `deal_mapping` (the word "deal" is the primary signal, and there is no competing "job_config" category pulling it away). In Stage 2, the LLM sees only 5 deal-related tools and easily picks `deal_lookup`.

### Phase 8 Extension Point (ReAct Pipeline)

Phase 7 is designed to be forward-compatible with **Phase 8**, which adds a ReAct (Reasoning + Acting) loop for multi-step pipelines. The Stage 1 classifier output schema includes a `mode` field:

```json
{ "category": "deal_mapping", "mode": "single_tool" }
```

In Phase 7, `mode` is always `"single_tool"` and is ignored by the routing logic. In Phase 8, Stage 1 may return `"mode": "pipeline"` for complex multi-step queries (e.g., full email triage pipeline), which triggers a ReAct orchestrator loop instead of single-tool selection. This design means Phase 8 requires **zero changes to Phase 7 code** — it only adds the ReAct loop as a new branch after Stage 1.

```
Stage 1 result
     │
     ├── mode: "single_tool" → Stage 2 (Phase 7 — pick one tool)
     │
     └── mode: "pipeline" → ReAct Loop (Phase 8 — multi-step reasoning)
```

---

## Architecture Decision Records

### ADR-1: Two LLM Calls Is Acceptable Latency

**Context:** The current architecture makes 1 LLM call for routing + 1 for response formatting = 2 total. The proposed architecture adds 1 more for intent classification = 3 total.  
**Decision:** Accept the additional ~200–500ms latency for Stage 1 classification. The alternative (single-stage with 36 tools) produces wrong answers, which is worse than slower correct answers.  
**Consequence:** Total response time increases by the duration of one lightweight LLM call. Stage 1 uses a short prompt (~400 tokens) with no tool definitions (just text classification), so it is the fastest possible LLM call. This is the same trade-off made by Semantic Kernel's Planner and Bedrock Agents' intent classifier.  
**Mitigation:** Stage 1 prompt is deliberately minimal — no SYSTEM_PROMPT, no DOMAIN_KNOWLEDGE, just the category definitions and the user's prompt. This minimises token count and latency.

### ADR-2: 6 Categories, Not More, Not Fewer

**Context:** We have 36 tools. We could group them into 3 mega-categories (too broad, same disambiguation problem) or 12 micro-categories (too many for Stage 1 to discriminate reliably).  
**Decision:** 6 categories, each mapping to a distinct data layer or operational concern. The categories are:

| Category | Data Layer | Tool Count |
|---|---|---|
| `deal_mapping` | tblExternalDIDRef + cross-references | 5 |
| `job_config` | Settings.xml configuration | 7 |
| `processing` | tblTemplateStaging execution history | 8 |
| `logs_ops` | Application logs (EmailMonitor, SFTP) | 7 |
| `deployment` | Settings.xml backup/deploy/rollback | 4 |
| `system_admin` | System health, triage, analysis | 5 |

**Consequence:** Stage 1 has a clean 6-way classification. The largest category (`processing`) has 8 tools, which is well within LLM discrimination capability. No category overlaps with another in data layer.

### ADR-3: Stage 1 Uses Text Output, Not Tool-Calling

**Context:** Stage 1 could use tool-calling (define 6 "category tools") or structured text output (ask the LLM to return a JSON object with the category name).  
**Decision:** Stage 1 uses structured text output — the LLM returns a JSON object like `{ "category": "deal_mapping" }`. This avoids tool-calling overhead for what is essentially a classification task.  
**Consequence:** Stage 1 is faster (no tool schema evaluation) and simpler (no fake "category tools" to maintain). The response is parsed as JSON; if parsing fails, we fall back to the full 36-tool single-stage router as a safety net.  
**Alternative considered:** Using `toolMode: Required` with 6 dummy tools. Rejected because it adds unnecessary complexity and the LLM must still evaluate tool schemas.

### ADR-4: Category Boundaries Are Based on Data Layer, Not User Intent Phrasing

**Context:** We could define categories by how users phrase questions ("questions about deals" vs "questions about jobs") or by which data layer answers the question (tblExternalDIDRef vs Settings.xml).  
**Decision:** Categories align with data layers. This is more robust because the same user phrasing can be answered by different data layers depending on context. The Stage 1 classifier prompt explains what each category OWNS (which data), not what it SOUNDS LIKE.  
**Consequence:** "What jobs serve deal X?" routes to `deal_mapping` (because the answer comes from tblExternalDIDRef cross-reference), not `job_config` (which searches Settings.xml by job attributes). This is exactly the disambiguation we need.

### ADR-5: Conversation History Is Available to Both Stages

**Context:** Follow-up queries ("show me the details for the first one") require conversation context. If only Stage 2 sees conversation history, Stage 1 might misclassify a follow-up.  
**Decision:** Both Stage 1 and Stage 2 receive the conversation history (same `buildConversationContext()` output used today). Stage 1 uses it to understand what domain the conversation is in. Stage 2 uses it to extract identifiers.  
**Consequence:** Slightly larger Stage 1 prompt. But conversation history is typically short (last 2–3 exchanges) and critical for correct classification.

### ADR-6: Fallback to Full Tool Set If Classification Fails

**Context:** What happens if Stage 1 returns an invalid category or JSON parsing fails?  
**Decision:** If Stage 1 fails (bad JSON, unknown category, or timeout), fall back to the current single-stage router with all 36 tools. This ensures the system never becomes completely non-functional due to the classification layer.  
**Consequence:** The fallback path preserves today's behavior — which is imperfect but functional for most queries. The failure is logged for debugging. This means Phase 7 can never make things worse than the current state.

### ADR-7: executeToolCall() Switch Is Unchanged

**Context:** Should we refactor the 36-branch `executeToolCall()` switch into per-category dispatchers?  
**Decision:** No. `executeToolCall()` works correctly and has been production-tested through Phases 1–6. The routing problem is upstream (choosing the wrong tool name), not downstream (executing the wrong handler). Refactoring the switch introduces unnecessary risk.  
**Consequence:** `executeToolCall()` keeps its current structure. The only change is that the tool name arriving at it is more likely to be correct.

### ADR-8: Stage 1 Output Schema Is Forward-Compatible for Phase 8 ReAct

**Context:** Phase 8 will add a ReAct (Reasoning + Acting) loop for multi-step pipelines (e.g., full email triage: parse email → match job → check DIDs → query logs → check template staging → compile report). Phase 8 needs Stage 1 to signal whether a query requires single-tool selection or multi-step pipeline execution.  
**Decision:** Stage 1's JSON output schema includes a `mode` field: `{ "category": "...", "mode": "single_tool" }`. In Phase 7, `mode` is always `"single_tool"` and is ignored (default). In Phase 8, the classifier prompt gains additional pipeline definitions, and `mode: "pipeline"` triggers the ReAct loop.  
**Consequence:** Phase 7 code parses `result.category` and ignores `result.mode`. Phase 8 adds a single `if (result.mode === 'pipeline')` branch — no refactoring of Phase 7 code required. The classifier prompt is the only thing that changes.  
**Why not add mode later?** If Phase 8 had to retrofit `mode` into the classifier, it would need to modify `classifyIntent()`, `buildClassifierPrompt()`, and `routeWithToolCalling()`. By defining the schema now, Phase 8 only adds new code.

---

## Risk Assessment

| # | Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| R-1 | Stage 1 classifier misclassifies intent | High | Low | Category descriptions are based on data layers with clear boundaries; 6-way classification is much simpler than 36-way |
| R-2 | Latency increase frustrates users | Medium | Medium | Stage 1 uses minimal prompt (~400 tokens); typical LLM latency for this is 200–500ms |
| R-3 | Follow-up queries misclassified | Medium | Medium | Conversation history included in Stage 1; LLM sees previous tool calls and can infer the domain |
| R-4 | Stage 1 JSON parsing fails | Low | Low | Fallback to full 36-tool single-stage router; logged for debugging |
| R-5 | New tools added in future phases break categories | Low | Low | Each new tool is assigned to exactly one category at definition time; categories are data-layer-aligned, so placement is natural |
| R-6 | Category boundaries are wrong for edge cases | Medium | Low | Categories are based on data ownership (which table answers the question), not keyword matching; edge cases like "deal_pipeline" (crosses all layers) get their own explicit placement |

---

## Success Criteria

| # | Criterion | Measurement |
|---|---|---|
| SC-1 | DID query routes to `deal_lookup` | `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` → `deal_lookup` tool selected |
| SC-2 | Job search still routes to `search_jobs` | `@frp list all cmbs jobs` → `search_jobs` tool selected |
| SC-3 | Job-to-deal query routes to `job_detail` | `@frp list all deals that use the job with ServicerID 224` → `job_detail` or `deal_lookup` as appropriate |
| SC-4 | All 697 existing tests pass | `pytest tests/ -q` → 697 passed, 0 failed |
| SC-5 | Stage 1 + Stage 2 logged in output channel | Output channel shows `[FRP] Stage 1: deal_mapping` then `[FRP] Stage 2: deal_lookup(...)` |
| SC-6 | Fallback works when Stage 1 fails | Simulate bad JSON from Stage 1 → system falls back to 36-tool single-stage router |
| SC-7 | No regressions in any tool | test all tools from the manual QA checklist (see 05_TESTING_PLAN.md) |
| SC-8 | Regex pre-routing intercepts removed | No `dealIntentRe`, `dealIntent2`, or `if (dealMatch)` in `participant.js` |
| SC-9 | Tool descriptions cleaned | No "Do NOT use for…" or "ALWAYS use this for…" negative constraints in any tool description |
| SC-10 | Latency acceptable | Total response time (Stage 1 + Stage 2 + handler + formatting) ≤ 2× current response time |

---

## Dependencies & Prerequisites

| # | Prerequisite | Verification |
|---|---|---|
| PG-1 | Phase 6 complete | `pytest tests/ -q` → 697 passed, 0 failed |
| PG-2 | VSIX builds successfully | `scripts/build.ps1` completes with no errors |
| PG-3 | VS Code ≥ 1.95.0 | `code --version` |
| PG-4 | `vscode.LanguageModelToolCallPart` available | Already verified in `routeWithToolCalling()` guard |
| PG-5 | LLM tool-calling API available | Model supports `toolMode: Required` (already tested) |
| PG-6 | SQLite cache functional | `deal_lookup` uses SQLite-first for job cross-referencing |
| PG-7 | Data source indicators in place | `dataSourceFooter()` renders source indicators |

---

## Why Not a Rewrite

Phase 7 is a **focused surgery on a single function** (`routeWithToolCalling()`) in a single file (`participant.js`). It does not:

- Change any backend code (`backend/`, `cli/`)
- Change any handler function (30+ handlers remain identical)
- Change any tool's `executeToolCall()` dispatch
- Change any CLI command interface or JSON shape
- Change any test file
- Introduce any new dependencies or libraries

The only file that changes is `extension/chat/participant.js`, and within that file, only these sections change:

| Section | Change |
|---|---|
| `DOMAIN_KNOWLEDGE` constant | Remove 14-point decision tree, keep data model reference |
| `FRP_TOOLS` array | Remove negative constraints from descriptions; remains the single source of truth for all tool definitions |
| `routeWithToolCalling()` function | Replace with two-stage logic: `classifyIntent()` → `routeWithinCategory()` |
| New: `INTENT_CATEGORIES` constant | 6 category definitions with tool-name arrays |
| New: `CATEGORY_TOOLS` lookup | Category name → subset of `FRP_TOOLS` |
| New: `classifyIntent()` function | Builds Stage 1 prompt, sends to LLM, parses JSON response |
| New: `routeWithinCategory()` function | Builds Stage 2 prompt with category-scoped tools, sends to LLM |
| Removed: regex pre-routing | `dealIntentRe`, `dealIntent2`, `if (dealMatch)` block deleted |

---

## What Gets Removed

These items are deleted from `participant.js` during Phase 7. They are listed here explicitly so that implementation does not accidentally preserve them.

| Item | Location | Why Removed |
|---|---|---|
| `dealIntentRe` regex pattern | `routeWithToolCalling()`, line ~653 | Regex band-aid for DID routing; replaced by Stage 1 classification |
| `dealIntent2` regex pattern | `routeWithToolCalling()`, line ~654 | Second regex band-aid; same reason |
| `if (dealMatch)` block | `routeWithToolCalling()`, lines ~655–661 | Pre-routing intercept that bypasses LLM; no longer needed |
| Decision tree (points 1–14) | `DOMAIN_KNOWLEDGE` constant | Replaced by Stage 1 category definitions; trying to teach the LLM routing rules via text did not work |
| Negative tool description constraints | `FRP_TOOLS[search_jobs].description` | "Do NOT use this when the user provides a deal name…" — replaced by category boundaries |
| Negative tool description constraints | `FRP_TOOLS[deal_lookup].description` | "ALWAYS USE THIS when the user mentions a deal name/DID…" — replaced by category boundaries |
| `IMPORTANT` clause in decision tree | `DOMAIN_KNOWLEDGE`, point 4 | Added as a routing fix attempt; no longer needed |

---

## What Gets Kept

These items are explicitly preserved during Phase 7. They are listed here so that implementation does not accidentally remove them.

| Item | Location | Why Kept |
|---|---|---|
| `SYSTEM_PROMPT` constant | Top of `participant.js` | Still used in Stage 2 and response formatting; contains data model rules and formatting rules that are independent of routing |
| `DOMAIN_KNOWLEDGE` (simplified) | Top of `participant.js` | Data model reference (three-table pipeline, cross-reference chains) still useful for Stage 2 tool selection context. Only the decision tree section is removed |
| `FRP_TOOLS` array | `participant.js` | Remains the single source of truth for all 36 tool definitions. `CATEGORY_TOOLS` subsets reference entries from this array by name |
| `executeToolCall()` function | `participant.js` | 36-branch switch is unchanged; it correctly dispatches any tool name |
| All 30+ handler functions | `participant.js` | `handleJobsSearch()`, `handleDealLookup()`, `handleJobDetail()`, etc. — all unchanged |
| `dataSourceFooter()` utility | `participant.js` | Data source indicator rendering — unchanged |
| `buildConversationContext()` | `participant.js` | Conversation history builder — used by both Stage 1 and Stage 2 |
| `selectModel()` | `participant.js` | Model selection logic — unchanged |
| `MODEL_PREFERENCE` array | `participant.js` | Model priority list — unchanged |
| All backend code | `backend/`, `cli/` | Zero changes to Python code |
| All tests | `tests/` | Zero changes to test files; 697 tests continue passing |
| VSIX build process | `scripts/build.ps1` | Unchanged |

---

## Estimated Effort

| Sprint | Name | Est. Hours | Files Changed |
|---|---|---|---|
| S1 | Category definitions + Stage 1 classifier | 2–3h | 1 (participant.js) |
| S2 | Stage 2 scoped router + integration | 2–3h | 1 (participant.js) |
| S3 | Cleanup + description refactor | 1–2h | 1 (participant.js) |
| S4 | Testing + validation + VSIX build | 1–2h | 0 new code; build + manual QA |
| **Total** | | **6–10h** | **1 file modified** |

**Compared to Phase 6:** Phase 6 modified 24 files across 2 work streams. Phase 7 modifies 1 file with a focused, surgical change. The effort is lower, but the testing must be thorough because routing affects every single user interaction.
