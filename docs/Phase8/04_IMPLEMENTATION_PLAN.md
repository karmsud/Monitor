# Phase 8: Implementation Plan
## FRP Agent — ReAct Pipeline Orchestrator

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [03_TECHNICAL_DESIGN.md](03_TECHNICAL_DESIGN.md)  
**Total Estimated Effort:** 9–13 hours across 4 sprints  
**Total Modified Files:** 1 (`extension/chat/participant.js`)  
**Prerequisite:** Phase 7 (Two-Stage Intent Routing) complete and verified

---

## Table of Contents
1. [Implementation Principles](#1-implementation-principles)  
2. [Phase Gate Prerequisites](#2-phase-gate-prerequisites)  
3. [Sprint Plan](#3-sprint-plan)  
4. [Verification Checkpoints](#4-verification-checkpoints)  
5. [Sprint Details](#5-sprint-details)  
6. [Rollback Strategy](#6-rollback-strategy)  
7. [Post-Implementation Validation](#7-post-implementation-validation)

---

## 1. Implementation Principles

1. **Phase 7 is the foundation.** All Phase 7 code must be working before Phase 8 begins. Phase 8 builds on top — it never replaces Phase 7 logic.
2. **One file, additive changes.** All modifications occur in `extension/chat/participant.js`. No backend, CLI, or test changes. Phase 8 adds ~305 lines and modifies ~25.
3. **Pipeline first, then classifier.** Build and test `reactLoop()` in isolation (hardcoded trigger) before updating the Stage 1 classifier to detect pipeline queries. This ensures the loop works before we rely on automatic detection.
4. **Each sprint produces a deployable VSIX.** Build and install after every sprint. Phase 7 single-tool routing continues to work throughout.
5. **Commit at every checkpoint.** Each sprint produces a clean git commit.
6. **Test with real .msg files AND pasted metadata.** The pipeline must handle both entry points: a `.msg` file path and pasted email metadata (sender, subject, attachments).

---

## 2. Phase Gate Prerequisites

Before starting Sprint 1, verify:

| # | Prerequisite | Verification |
|---|---|---|
| PG-1 | Phase 7 complete and verified | CP-74 passed (all 4 Phase 7 sprints done) |
| PG-2 | Two-stage routing works for all 6 categories | Test all 6 prompts in Phase 7 test matrix — all route correctly |
| PG-3 | DID routing fixed | `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` → Stage 1: `deal_mapping`, Stage 2: `deal_lookup` |
| PG-4 | Fallback path works | Force `classifyIntent()` to return null → extension still works via `routeWithAllTools()` |
| PG-5 | VSIX builds | `scripts/build.ps1` completes without errors |
| PG-6 | Backend tests pass | `pytest tests/ -q` → 697 passed, 0 failed |
| PG-7 | Git clean | `git status` shows no uncommitted changes |
| PG-8 | .msg test file available | At least one `.msg` file available for end-to-end testing. Record its path: `_________` |

---

## 3. Sprint Plan

| Sprint | Name | Est. Hours | What Changes | Checkpoint |
|---|---|---|---|---|
| S1 | ReAct Loop Infrastructure | 3–4h | Add `reactLoop()`, `executePipelineTool()`, `buildToolArgs()`, `compilePipelineReport()`, `buildPipelineResult()`. Hardcoded trigger for testing. | CP-81 |
| S2 | Email Triage Playbook + Pipeline Definition | 2–3h | Add `EMAIL_TRIAGE_PLAYBOOK`, `EMAIL_TRIAGE_TOOLS`, `PIPELINE_DEFINITIONS`. Wire playbook into `reactLoop()`. | CP-82 |
| S3 | Classifier Integration + Progress Streaming | 2–3h | Update `buildClassifierPrompt()`, `classifyIntent()`, `routeWithToolCalling()` for `mode: "pipeline"`. Add progress streaming. | CP-83 |
| S4 | Final Validation + Build + Deploy | 2–3h | Full manual QA with real .msg files and pasted metadata. Edge cases. VSIX build + install. | CP-84 |

---

## 4. Verification Checkpoints

| # | After Sprint | Verification | Method |
|---|---|---|---|
| CP-81 | S1 | `reactLoop()` works when invoked directly; can execute a hardcoded 2-tool chain; `compilePipelineReport()` generates readable output; Phase 7 single-tool routing still works unchanged | Build VSIX, hardcoded test, verify Phase 7 prompts still work |
| CP-82 | S2 | Playbook guides the LLM through 6-step email triage analysis; LLM calls the right tools in the right order; pipeline produces a comprehensive report | Build VSIX, test with real email metadata via hardcoded trigger |
| CP-83 | S3 | Stage 1 classifier detects pipeline queries automatically; `mode: "pipeline"` routes to `reactLoop()`; progress streaming shows real-time step indicators; single-tool queries still route via Phase 7 | Build VSIX, test pipeline queries AND single-tool queries |
| CP-84 | S4 | Full QA: .msg file, pasted metadata, failure scenarios, maxSteps cap, edge cases. Pytest passes. VSIX deployed. | Full QA checklist + pytest + production deployment |

---

## 5. Sprint Details

### Sprint 1: ReAct Loop Infrastructure (3–4h)

**Goal:** Build and test the generic ReAct loop machinery. After this sprint, `reactLoop()` can execute a hardcoded multi-tool chain, and Phase 7 routing is unchanged.

| # | Task | Detail | Est. |
|---|---|---|---|
| S1-1 | Backup `participant.js` | Copy to `participant.js.backup-phase7` for safety | 2m |
| S1-2 | Add `buildToolArgs()` function | Extract the argument-building logic from the existing `executeToolCall()` switch block into a new function. This covers all 10 tools in `EMAIL_TRIAGE_TOOLS` first; extend to all 36 later. See 03_TECHNICAL_DESIGN.md §5 for code. Place before `executeToolCall()`. | 30m |
| S1-3 | Update `executeToolCall()` to use `buildToolArgs()` | Refactor the existing switch block: for each case that `buildToolArgs()` covers, replace the inline argument construction with a call to `buildToolArgs()`. Keep formatting/streaming logic in `executeToolCall()`. | 30m |
| S1-4 | Build and verify no regression | Build VSIX, install, test 2–3 Phase 7 prompts. `executeToolCall()` should behave identically. | 15m |
| S1-5 | Add `executePipelineTool()` function | Calls `buildToolArgs()` → `backendCall()`, returns raw JSON. See 03_TECHNICAL_DESIGN.md §5. Place after `executeToolCall()`. | 20m |
| S1-6 | Add `compilePipelineReport()` function | Generates fallback markdown from step results array. See 03_TECHNICAL_DESIGN.md §6. Place after `executePipelineTool()`. | 15m |
| S1-7 | Add `buildPipelineResult()` function | Returns empty result object (placeholder for follow-up buttons). See 03_TECHNICAL_DESIGN.md §4. Place after `compilePipelineReport()`. | 5m |
| S1-8 | Add `reactLoop()` function | The main ReAct orchestrator. See 03_TECHNICAL_DESIGN.md §4. Place after `routeWithAllTools()`. | 40m |
| S1-9 | Add a temporary hardcoded trigger | In `routeWithToolCalling()`, add a temporary block: `if (prompt.toLowerCase().startsWith('react-test:'))` → call `reactLoop()` with a minimal test pipeline. This bypasses the classifier for manual testing. | 10m |
| S1-10 | Test the hardcoded trigger | Build VSIX, install, test: `@frp react-test: search for jobs with cmbs`. Verify output channel shows `[FRP] ReAct step 1: search_jobs(...)`. Verify the tool executes and the LLM produces a response. | 20m |
| S1-11 | Test `compilePipelineReport()` fallback | Set the test pipeline's `maxSteps` to 1 so the loop hits the cap after one tool call. Verify a partial report is rendered. | 10m |
| S1-12 | Verify Phase 7 still works | Test existing Phase 7 prompts: `@frp list all cmbs jobs`, `@frp show daily summary`. Confirm two-stage routing is unaffected. | 10m |

**Checkpoint CP-81:** `reactLoop()` executes, calls tools, gets results, and produces output. `compilePipelineReport()` works as fallback. Phase 7 unchanged.

**Output channel log for CP-81:**
```
[FRP] ReAct: starting pipeline "test" (max 3 steps, 2 tools)
[FRP] ReAct step 1: search_jobs({"query":"cmbs"})
[FRP] ReAct: LLM produced final report at step 2 (437 chars)
```

---

### Sprint 2: Email Triage Playbook + Pipeline Definition (2–3h)

**Goal:** Build the email triage playbook and wire it into the ReAct loop. After this sprint, the full 6-step email triage pipeline works when triggered via the hardcoded trigger.

| # | Task | Detail | Est. |
|---|---|---|---|
| S2-1 | Add `EMAIL_TRIAGE_PLAYBOOK` constant | The full ~80 line system prompt. See 03_TECHNICAL_DESIGN.md §1. Place after `DOMAIN_KNOWLEDGE`. | 25m |
| S2-2 | Add `EMAIL_TRIAGE_TOOLS` constant | Array of 10 tool names. See 03_TECHNICAL_DESIGN.md §2. Place after `EMAIL_TRIAGE_PLAYBOOK`. | 5m |
| S2-3 | Add `PIPELINE_DEFINITIONS` constant | Registry object with the `email_triage` pipeline entry. See 03_TECHNICAL_DESIGN.md §3. Place after `EMAIL_TRIAGE_TOOLS`. | 5m |
| S2-4 | Update hardcoded trigger | Change the temporary trigger from `react-test:` to `triage-test:` and route to `PIPELINE_DEFINITIONS.email_triage`. | 5m |
| S2-5 | Build and test: Successful email triage | Build VSIX, install. Test: `@frp triage-test: analyze this email from reports@fay.com, subject "Monthly Report Jan 2026", attachment FayReport.xlsx` | 20m |
| S2-6 | Verify step progression | Check output channel for sequential step execution: Step 1 (metadata extraction or triage), Step 2 (search_jobs), Step 3 (deal_lookup), etc. | 10m |
| S2-7 | Test failure scenario: unknown sender | Test: `@frp triage-test: analyze email from unknown@newclient.com, subject "Q4 Summary"`. Verify the LLM stops after Step 2 (no job found) and offers remediation. | 15m |
| S2-8 | Test pasted metadata (no .msg file) | Test: `@frp triage-test: is this email covered? sender: reports@greycapital.com, subject: Deal Summary Q4, attachment: summary.xlsx`. Verify the LLM works with pasted metadata (no triage_email tool call). | 15m |
| S2-9 | Test maxSteps cap | Set `maxSteps` to 2 temporarily. Run a full triage query. Verify `compilePipelineReport()` produces a readable partial report. Reset `maxSteps` to 8. | 10m |
| S2-10 | Verify Phase 7 still works | Test: `@frp list all cmbs jobs`, `@frp show details for CMLTI_Fay`. Confirm Phase 7 routing unchanged. | 10m |

**Checkpoint CP-82:** Email triage pipeline executes all 6 steps (or stops appropriately at failure points). Produces comprehensive report. Phase 7 unchanged.

**Output channel log for CP-82 (success case):**
```
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"fay.com"})
[FRP] ReAct step 2: deal_lookup({"query":"296"})
[FRP] ReAct step 3: job_health({"job_name":"CMBS_GreyCo"})
[FRP] ReAct step 4: staging_search({"query":"CMBS_GreyCo"})
[FRP] ReAct: LLM produced final report at step 5 (1538 chars)
```

**Output channel log for CP-82 (failure case):**
```
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"newclient.com"})
[FRP] ReAct: LLM produced final report at step 2 (412 chars)
```

---

### Sprint 3: Classifier Integration + Progress Streaming (2–3h)

**Goal:** Remove the hardcoded trigger and let the Stage 1 classifier automatically detect pipeline queries. Add real-time progress streaming.

| # | Task | Detail | Est. |
|---|---|---|---|
| S3-1 | Update `buildClassifierPrompt()` | Add pipeline trigger section after disambiguation rules. Update mode instruction to allow `"pipeline"` value. See 03_TECHNICAL_DESIGN.md §7. | 15m |
| S3-2 | Update `classifyIntent()` | Change return type from `string` to `{ category, mode }`. Parse `mode` from LLM response. See 03_TECHNICAL_DESIGN.md §8. | 15m |
| S3-3 | Update `routeWithToolCalling()` | Add `mode === 'pipeline'` branch. Destructure `{ category, mode }` from classification result. See 03_TECHNICAL_DESIGN.md §9. | 15m |
| S3-4 | Remove hardcoded trigger | Delete the temporary `if (prompt.toLowerCase().startsWith('triage-test:'))` block from `routeWithToolCalling()`. | 2m |
| S3-5 | Add progress streaming | In `reactLoop()`, add `stream.progress()` calls before each tool execution. After tool results, optionally stream brief status indicators (✅/❌). See 02_SYSTEM_DESIGN.md §9. | 20m |
| S3-6 | Build and test: Automatic detection | Build VSIX, install. Test: `@frp analyze this email from reports@fay.com, subject "Monthly Report Jan 2026"`. Verify output channel shows `Stage 1: system_admin (mode: pipeline)` → `ReAct: starting pipeline "email_triage"`. | 15m |
| S3-7 | Test: Single-tool queries still work | Test: `@frp list all cmbs jobs` → Stage 1: `job_config (mode: single_tool)` → Stage 2: `search_jobs`. Confirm no regression. | 10m |
| S3-8 | Test: DID queries still route correctly | Test: `@frp Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` → Stage 1: `deal_mapping (mode: single_tool)` → Stage 2: `deal_lookup`. | 10m |
| S3-9 | Test: Edge case — ambiguous queries | Test: `@frp what happens when an email arrives?` (pipeline-like but vague). Verify classifier handles it gracefully (pipeline or single-tool — either is acceptable as long as it doesn't crash). | 10m |
| S3-10 | Verify progress streaming | Run a full triage query and verify the user sees real-time step indicators in the chat response before the final report. | 10m |

**Checkpoint CP-83:** Pipeline queries are automatically detected. Single-tool queries still work. Progress streaming shows real-time updates. No regressions.

**Output channel log for CP-83:**
```
[FRP] Stage 1: classifying intent for: "analyze this email from reports@fay.com..."
[FRP] Stage 1 raw response: {"category":"system_admin","mode":"pipeline"}
[FRP] Stage 1 result: system_admin (mode: pipeline)
[FRP] Routing to ReAct pipeline: Email Triage Pipeline
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"fay.com"})
...
```

---

### Sprint 4: Final Validation + Build + Deploy (2–3h)

**Goal:** Comprehensive testing, edge case coverage, and production deployment.

| # | Task | Detail | Est. |
|---|---|---|---|
| S4-1 | Test with real .msg file | Use a real `.msg` file from the `Email Logs/` folder. Test: `@frp analyze email at "C:\path\to\email.msg"`. Verify `triage_email` is called in Step 1 and the pipeline proceeds. | 20m |
| S4-2 | Test with pasted metadata — multiple scenarios | Test 3+ variants of pasted metadata: (a) sender + subject only, (b) sender + subject + attachment, (c) minimal info (just sender domain). | 15m |
| S4-3 | Test failure at each pipeline step | Manufacture queries that fail at Step 2 (unknown sender), Step 3 (no DIDs), Step 4 (no keyword match). Verify the LLM stops and offers remediation at each point. | 20m |
| S4-4 | Test maxSteps cap in production | Set `maxSteps` to 3 temporarily, run a full triage. Verify partial report. Reset to 8. | 10m |
| S4-5 | Test tool execution error | Temporarily break a backend tool (e.g., disconnect MySQL). Run pipeline. Verify the LLM receives the error and reports it gracefully instead of crashing. | 15m |
| S4-6 | Test cancellation | Start a pipeline query, then cancel (Ctrl+C or close chat). Verify no hangs or orphan processes. | 5m |
| S4-7 | Run pytest | `pytest tests/ -q` → 697 passed, 0 failed (or more if new tests added) | 5m |
| S4-8 | Check for console errors | Open VS Code Developer Tools (Help → Toggle Developer Tools), run pipeline queries, check for JavaScript errors. | 10m |
| S4-9 | Build VSIX | `scripts/build.ps1` | 5m |
| S4-10 | Install VSIX | Install in VS Code, restart, run one final pipeline test. | 10m |
| S4-11 | Git commit | Commit all changes with message: `Phase 8: ReAct pipeline orchestrator for email triage` | 5m |

**Checkpoint CP-84:** All tests pass. Edge cases handled. VSIX deployed. Git commit clean.

---

## 6. Rollback Strategy

### Quick Rollback (< 2 minutes)

If Phase 8 causes a critical issue after deployment:

1. Copy `participant.js.backup-phase7` back to `participant.js`
2. Run `scripts/build.ps1`
3. Install the VSIX
4. Phase 7 is fully restored — single-tool mode works

### Surgical Rollback (5–10 minutes)

If only the pipeline detection is broken (single-tool queries still work):

1. In `routeWithToolCalling()`, comment out the `if (mode === 'pipeline')` block
2. In `classifyIntent()`, change `return { category, mode }` back to `return category`
3. In `buildClassifierPrompt()`, remove the pipeline trigger section
4. Build and install VSIX
5. Phase 7 is restored; Phase 8 constants and functions remain as dead code (harmless)

### Guardrails Built Into the Code

| Guardrail | Protection |
|---|---|
| `mode === 'pipeline'` check | Only triggers when classifier explicitly returns `"pipeline"` |
| `PIPELINE_DEFINITIONS[pipelineName]` check | If pipeline definition is missing, falls through to Stage 2 |
| `maxSteps` cap | Prevents infinite loops — always terminates |
| `compilePipelineReport()` fallback | Even if LLM misbehaves, a report is generated |
| Tool error catching | Tool failures become data, not exceptions |
| `reactLoop()` outer try/catch | Any unexpected error falls through gracefully |

---

## 7. Post-Implementation Validation

### Full QA Checklist

After Sprint 4, run this complete checklist:

| # | Test | Expected Behavior | Pass? |
|---|---|---|---|
| QA-1 | `@frp analyze email from reports@fay.com, subject "Monthly Report"` | Pipeline: multi-step triage report | |
| QA-2 | `@frp triage this email: sender unknown@client.com, subject "Data"` | Pipeline: stops at Step 2, offers create job | |
| QA-3 | `@frp analyze email at "C:\path\to\real.msg"` | Pipeline: parses .msg, continues through steps | |
| QA-4 | `@frp list all cmbs jobs` | Single-tool: `job_config` → `search_jobs` | |
| QA-5 | `@frp Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | Single-tool: `deal_mapping` → `deal_lookup` | |
| QA-6 | `@frp has TPMT_SPS been processed today` | Single-tool: `processing` → `template_status` | |
| QA-7 | `@frp show today's daily summary` | Single-tool: `logs_ops` → `daily_summary` | |
| QA-8 | `@frp save the email settings` | Single-tool: `deployment` → `save_settings` | |
| QA-9 | `@frp run a system health check` | Single-tool: `system_admin` → `system_health` | |
| QA-10 | `@frp what is the capital of France?` | Fallback: polite refusal (not FRP-related) | |
| QA-11 | Output channel: pipeline query | Shows `Stage 1: system_admin (mode: pipeline)` → `ReAct: starting pipeline` → Step logs | |
| QA-12 | Output channel: single-tool query | Shows `Stage 1: <category> (mode: single_tool)` → `Stage 2: <tool>` | |
| QA-13 | Progress streaming | User sees step-by-step progress during pipeline | |
| QA-14 | `pytest tests/ -q` | 697+ passed, 0 failed | |

### Monitoring After Deployment

For the first week after deployment:
- Check output channel logs after each `@frp` query
- Watch for `[FRP] Stage 1 unknown category` messages (misclassification)  
- Watch for `[FRP] ReAct: hit max steps` messages (LLM getting stuck in loops)
- Watch for `[FRP] ReAct: LLM returned empty response` messages (LLM failing to produce report)
- Note any queries that should trigger pipeline but don't (false negatives) or queries that trigger pipeline but shouldn't (false positives)
