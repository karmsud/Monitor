# Phase 7: Implementation Plan
## FRP Agent — Two-Stage Intent Routing Architecture

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [03_TECHNICAL_DESIGN.md](03_TECHNICAL_DESIGN.md)  
**Total Estimated Effort:** 6–10 hours across 4 sprints  
**Total Modified Files:** 1 (`extension/chat/participant.js`)

---

## Table of Contents
1. [Implementation Principles](#implementation-principles)  
2. [Phase Gate Prerequisites](#phase-gate-prerequisites)  
3. [Sprint Plan](#sprint-plan)  
4. [Verification Checkpoints](#verification-checkpoints)  
5. [Sprint Details](#sprint-details)  
6. [Rollback Strategy](#rollback-strategy)  
7. [Post-Implementation Validation](#post-implementation-validation)

---

## Implementation Principles

1. **One file, surgical changes.** All modifications occur in `extension/chat/participant.js`. No backend, CLI, or test file changes.
2. **Preserve the fallback path.** The current single-stage router is extracted into `routeWithAllTools()` before any changes. At no point during implementation should the extension be non-functional — it always falls back.
3. **Test at every checkpoint.** Each sprint ends with a manual QA pass using the same prompts that currently fail. No sprint is complete until the prompt works.
4. **Additive before destructive.** New code (`INTENT_CATEGORIES`, `classifyIntent()`, `routeWithinCategory()`) is added first. Old code (regex, decision tree) is removed last.
5. **Build and install after every sprint.** Run `scripts/build.ps1` and install the VSIX after every sprint to verify real-world behavior.
6. **Commit at every checkpoint.** Each sprint produces a git-committable state.

---

## Phase Gate Prerequisites

Before starting Sprint 1, verify:

| # | Prerequisite | Verification Command |
|---|---|---|
| PG-1 | Phase 6 complete | `pytest tests/ -q` → 697 passed, 0 failed |
| PG-2 | VSIX builds successfully | `scripts/build.ps1` completes without errors |
| PG-3 | Current routing works for non-DID queries | `@frp list all cmbs jobs` → returns job list (search_jobs) |
| PG-4 | Current routing fails for DID queries (confirms the problem) | `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` → incorrectly returns search_jobs results |
| PG-5 | VS Code ≥ 1.95.0 | `code --version` |
| PG-6 | Git clean | `git status` shows no uncommitted changes |

---

## Sprint Plan

| Sprint | Name | Est. Hours | What Changes | Checkpoint |
|---|---|---|---|---|
| S1 | Extract Fallback + Add Category Constants | 2–3h | Extract `routeWithAllTools()`, add `INTENT_CATEGORIES`, `CATEGORY_TOOLS` | CP-71 |
| S2 | Build Stage 1 Classifier + Stage 2 Router | 2–3h | Add `buildClassifierPrompt()`, `classifyIntent()`, `routeWithinCategory()`, wire into `routeWithToolCalling()` | CP-72 |
| S3 | Cleanup — Remove Regex, Decision Tree, Description Cruft | 1–2h | Remove regex pre-routing, simplify DOMAIN_KNOWLEDGE, clean tool descriptions | CP-73 |
| S4 | Final Validation + Build + Deploy | 1–2h | Full manual QA, pytest, VSIX build, install | CP-74 |

---

## Verification Checkpoints

| # | After Sprint | Verification | Method |
|---|---|---|---|
| CP-71 | S1 | `routeWithAllTools()` extracted; `INTENT_CATEGORIES` and `CATEGORY_TOOLS` constants defined; extension still works identically (fallback path active) | Build VSIX, install, test `@frp list all cmbs jobs` and `@frp show details for CMLTI_Fay` |
| CP-72 | S2 | Two-stage routing active; DID queries now route to `deal_lookup`; non-DID queries still work; fallback path activates when Stage 1 fails | Build VSIX, install, test all 6 prompt categories (see test matrix in 05_TESTING_PLAN.md) |
| CP-73 | S3 | Regex removed, decision tree removed, tool descriptions cleaned; all tests still pass; output channel shows clean Stage 1 + Stage 2 logs | Build VSIX, install, verify output channel logs |
| CP-74 | S4 | Full manual QA checklist passed; `pytest tests/ -q` → 697 passed; VSIX installed and functional | Full QA pass + pytest + production test |

---

## Sprint Details

### Sprint 1: Extract Fallback + Add Category Constants (2–3h)

**Goal:** Prepare the codebase for two-stage routing without changing any behavior. After this sprint, the extension works exactly as it does today, but the code structure is ready for the two-stage insertion.

| # | Task | Detail | Est. |
|---|---|---|---|
| S1-1 | Create a backup copy of `participant.js` | Copy to `participant.js.backup-phase6` for safety | 2m |
| S1-2 | Extract `routeWithAllTools()` function | Move the current `routeWithToolCalling()` body (lines ~632–712) into a new `routeWithAllTools(prompt, request, context, stream, token, shared, historyContext, model)` function. This function should be identical to the current routing logic minus the regex pre-routing block. | 20m |
| S1-3 | Modify `routeWithToolCalling()` to call `routeWithAllTools()` | After extraction, `routeWithToolCalling()` should: (1) perform guard checks (unchanged), (2) build `historyContext`, (3) call `routeWithAllTools()`. This is a no-op refactor — behavior is identical. | 10m |
| S1-4 | Verify extension works identically | Build VSIX (`scripts/build.ps1`), install, test 2–3 prompts. Confirm output channel shows same log messages. | 15m |
| S1-5 | Add `INTENT_CATEGORIES` constant | Add the constant after `FRP_TOOLS` (see 03_TECHNICAL_DESIGN.md §1 for exact code). 6 category objects with `name`, `displayName`, `description`, `dataLayer`, `examples`. | 25m |
| S1-6 | Add `CATEGORY_TOOLS` constant | Add the mapping object after `INTENT_CATEGORIES` (see 03_TECHNICAL_DESIGN.md §2). | 5m |
| S1-7 | Validate tool assignments | Manually verify: every tool in `FRP_TOOLS` appears in exactly one `CATEGORY_TOOLS` array. Count: 5+7+8+7+4+5 = 36 = `FRP_TOOLS.length`. | 10m |
| S1-8 | Build and test again | Build VSIX, install. Extension should work identically because the new constants are not yet used. | 10m |

**Checkpoint CP-71:** Extension works identically. `routeWithAllTools()` is a clean extraction. `INTENT_CATEGORIES` and `CATEGORY_TOOLS` are defined but unused.

**What to check in the output channel:** Log messages should be exactly the same as before Sprint 1. No new `[FRP] Stage 1` or `[FRP] Stage 2` messages should appear.

---

### Sprint 2: Build Stage 1 Classifier + Stage 2 Router (2–3h)

**Goal:** Implement the two-stage routing logic and wire it into `routeWithToolCalling()`. After this sprint, the two-stage architecture is active and the critical DID query should route correctly.

| # | Task | Detail | Est. |
|---|---|---|---|
| S2-1 | Add `buildClassifierPrompt()` function | Pure function that builds the Stage 1 prompt (see 03_TECHNICAL_DESIGN.md §3). Place after `CATEGORY_TOOLS`. | 20m |
| S2-2 | Add `classifyIntent()` function | Async function that sends classifier prompt to LLM, parses JSON, returns category name or null (see 03_TECHNICAL_DESIGN.md §4). Place after `buildClassifierPrompt()`. | 30m |
| S2-3 | Add `routeWithinCategory()` function | Async function that filters `FRP_TOOLS` by category and sends scoped tools to LLM (see 03_TECHNICAL_DESIGN.md §5). Place after `executeToolCall()`. | 25m |
| S2-4 | Modify `routeWithToolCalling()` to orchestrate two stages | After guard checks and `buildConversationContext()`: (1) call `classifyIntent()`, (2) if category returned → call `routeWithinCategory()`, (3) if either fails → call `routeWithAllTools()`. See 03_TECHNICAL_DESIGN.md §6 for exact code. | 20m |
| S2-5 | Build and install VSIX | `scripts/build.ps1`, install VSIX. | 10m |
| S2-6 | Test the critical DID query | `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` — verify output channel shows `Stage 1: deal_mapping`, `Stage 2: deal_lookup`. | 10m |
| S2-7 | Test non-DID queries | Test at least one prompt per category (see test matrix below). Verify correct routing. | 20m |
| S2-8 | Test fallback path | Temporarily corrupt `classifyIntent()` (e.g., force it to return `null`) and verify the extension still works via `routeWithAllTools()` fallback. Then restore. | 15m |

**Sprint 2 Quick Test Matrix:**

| Prompt | Expected Category | Expected Tool |
|---|---|---|
| `list all cmbs jobs` | `job_config` | `search_jobs` |
| `Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | `deal_mapping` | `deal_lookup` |
| `has TPMT_SPS been processed today` | `processing` | `template_status` |
| `show today's daily summary` | `logs_ops` | `daily_summary` |
| `save the email settings` | `deployment` | `save_settings` |
| `run a system health check` | `system_admin` | `system_health` |

**Checkpoint CP-72:** Two-stage routing active. DID queries route correctly. All 6 categories produce expected results. Fallback path works when Stage 1 is disabled.

**What to check in the output channel:**
```
[FRP] Stage 1: classifying intent for: "Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1""
[FRP] Stage 1 raw response: { "category": "deal_mapping" }
[FRP] Stage 1 result: deal_mapping
[FRP] Stage 2: routing within deal_mapping (5 tools: deal_lookup, servicer_dossier, coverage_gaps, orphan_detection, collision_detection)
[FRP] Stage 2 selected: deal_lookup({"query":"ICW MAT TRUST SUBI A1"})
[FRP] LLM tool call → deal_lookup({"query":"ICW MAT TRUST SUBI A1"})
```

---

### Sprint 3: Cleanup — Remove Regex, Decision Tree, Description Cruft (1–2h)

**Goal:** Remove all the band-aid fixes and bloated descriptions that were added during previous routing fix attempts. After this sprint, the code is clean and the two-stage architecture is the sole routing mechanism (with `routeWithAllTools()` as the fallback path, which itself no longer has regex).

| # | Task | Detail | Est. |
|---|---|---|---|
| S3-1 | Remove regex pre-routing from `routeWithAllTools()` | Delete `dealIntentRe` constant declaration, `dealIntent2` constant declaration, and the `if (dealMatch) { ... }` block (~10 lines). These were in the old `routeWithToolCalling()` and are now in `routeWithAllTools()`. | 5m |
| S3-2 | Simplify `DOMAIN_KNOWLEDGE` | Remove the "### Tool Selection Decision Tree" section and everything after it (points 1–14, ~30 lines). Keep "### Three-Table Pipeline" and "### Cross-Reference Chains" sections. Rename the header from "## FRP Data Model — Tool Selection Guide" to "## FRP Data Model Reference". See 03_TECHNICAL_DESIGN.md §8 for exact resulting text. | 15m |
| S3-3 | Clean `search_jobs` tool description | Remove the sentence starting with "Do NOT use this when..." from the description. See 03_TECHNICAL_DESIGN.md §9. | 5m |
| S3-4 | Clean `deal_lookup` tool description | Remove the "ALWAYS USE THIS..." clause and the "NOTE: If the user asks by *job name*..." clause. See 03_TECHNICAL_DESIGN.md §9. | 5m |
| S3-5 | Verify no other tool descriptions need cleaning | Scan all 36 tool descriptions for any negative constraints or cross-references that were added as routing fixes. Remove any found. | 15m |
| S3-6 | Review output channel routing instructions in prompts | In `routeWithAllTools()`, update the routing prompt text: remove "Use the data model and decision tree above" → "Use the data model above" (since the decision tree is gone). | 5m |
| S3-7 | Build and install VSIX | `scripts/build.ps1`, install VSIX. | 10m |
| S3-8 | Re-test all 6 category prompts | Same test matrix as Sprint 2. Verify all still work correctly after cleanup. | 15m |
| S3-9 | Re-test the fallback path | Force `classifyIntent()` to return null, verify `routeWithAllTools()` still works (now without regex). Restore. | 10m |

**Checkpoint CP-73:** All regex, decision tree, and negative description cruft removed. Two-stage routing works. Fallback works. Output channel logs are clean.

**What to check:**
- No `dealIntentRe` or `dealIntent2` anywhere in the file
- `DOMAIN_KNOWLEDGE` does not contain "Decision Tree" or "IMPORTANT"
- `search_jobs` description does not contain "Do NOT"
- `deal_lookup` description does not contain "ALWAYS USE THIS"

---

### Sprint 4: Final Validation + Build + Deploy (1–2h)

**Goal:** Comprehensive validation pass, final build, and deployment.

| # | Task | Detail | Est. |
|---|---|---|---|
| S4-1 | Run full pytest suite | `pytest tests/ -q` → 697 passed, 0 failed | 5m |
| S4-2 | Run full manual QA checklist | Test all prompts from the Manual QA Checklist in 05_TESTING_PLAN.md (36 prompts, one per tool, plus edge cases). | 30m |
| S4-3 | Verify output channel diagnostics | For 3–4 representative prompts, check that output channel shows correct Stage 1 category and Stage 2 tool selection. | 10m |
| S4-4 | Test follow-up queries | Test 2–3 multi-turn conversations: ask about a job, then ask a follow-up about its deals, then ask about processing history. Verify Stage 1 classifies correctly with conversation context. | 15m |
| S4-5 | Test edge cases | Test the 5 edge-case prompts from 05_TESTING_PLAN.md: ambiguous queries, typos, combined questions. | 10m |
| S4-6 | Final VSIX build | `scripts/build.ps1 -Clean` — clean build. | 10m |
| S4-7 | Install and verify | Install VSIX, restart VS Code, run 3 representative prompts. | 5m |
| S4-8 | Delete backup file | Remove `participant.js.backup-phase6` created in S1-1. | 1m |
| S4-9 | Commit | Git commit with message: "Phase 7: Two-Stage Intent Routing Architecture" | 5m |

**Checkpoint CP-74:** Full suite passes. All manual QA prompts produce correct results. VSIX deployed. Commit tagged.

---

## Rollback Strategy

### During Implementation

If any sprint produces a broken state:
1. Restore `participant.js` from `participant.js.backup-phase6` (created in S1-1)
2. Build and install VSIX
3. Verify extension works (original single-stage behavior)

### After Deployment

The `routeWithAllTools()` fallback function IS the rollback. If two-stage routing (Stage 1 + Stage 2) is causing problems in production:
1. In `routeWithToolCalling()`, change:
   ```javascript
   const category = await classifyIntent(prompt, historyContext, model, token, shared);
   ```
   to:
   ```javascript
   const category = null; // DISABLED — force fallback to single-stage
   ```
2. Build and install VSIX
3. Extension reverts to single-stage routing with all 36 tools (pre-Phase 7 behavior)

This is a **one-line change** that can be applied in under 1 minute.

---

## Post-Implementation Validation

### Immediate (Same Day)

| # | Validation | Expected Result |
|---|---|---|
| PIV-1 | Critical DID query | `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` → "No matching deals found" (deal_lookup, deterministic not-found) |
| PIV-2 | Job search still works | `@frp list all cmbs jobs` → 9 CMBS email jobs |
| PIV-3 | Job detail still works | `@frp show details for CMLTI_Fay` → full job config + linked deals |
| PIV-4 | Deal lookup by ServicerID works | `@frp list all deals that use the job with ServicerID 224` → deal list |
| PIV-5 | Processing query works | `@frp has TPMT_SPS been processed` → template status |
| PIV-6 | Daily summary works | `@frp show today's summary` → daily log summary |
| PIV-7 | Deploy command works | `@frp save email settings` → backup + save confirmation |
| PIV-8 | System health works | `@frp system health check` → system health report |

### Ongoing (First Week)

Monitor the VS Code output channel (`FRP Agent` channel) for:
- Any `[FRP] Stage 1 error:` messages → indicates classification failures
- Any `[FRP] Falling back to routeWithAllTools()` messages → indicates the fallback path was triggered
- Any `[FRP] Stage 1 unknown category:` messages → indicates the LLM returned an unexpected category name

If any of these appear frequently, review the classifier prompt and category definitions for potential improvements.
