# Phase 7: Testing Plan
## FRP Agent — Two-Stage Intent Routing Architecture

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)  
**Existing Tests:** 697 passed  
**Target:** 697 passed, 0 failed (no new pytest tests — changes are extension-only)

---

## Table of Contents
1. [Test Architecture](#1-test-architecture)  
2. [Test Principles](#2-test-principles)  
3. [Unit Verification — Category Assignments](#3-unit-verification--category-assignments)  
4. [Stage 1 Classification Tests](#4-stage-1-classification-tests)  
5. [Stage 2 Tool Selection Tests](#5-stage-2-tool-selection-tests)  
6. [End-to-End Routing Tests](#6-end-to-end-routing-tests)  
7. [Fallback Path Tests](#7-fallback-path-tests)  
8. [Regression Tests — Previously Working Prompts](#8-regression-tests--previously-working-prompts)  
9. [Edge Case Tests](#9-edge-case-tests)  
10. [Multi-Turn Conversation Tests](#10-multi-turn-conversation-tests)  
11. [Diagnostics Verification](#11-diagnostics-verification)  
12. [Manual QA Checklist](#12-manual-qa-checklist)  
13. [Code Cleanup Verification](#13-code-cleanup-verification)  
14. [Performance Baseline](#14-performance-baseline)  
15. [Test Execution Order](#15-test-execution-order)

---

## 1. Test Architecture

### Why No New Pytest Tests

Phase 7 modifies only `extension/chat/participant.js` — a VS Code extension JavaScript file. The existing 697 Python tests verify the **backend CLI and data layer**, which are completely untouched by Phase 7. There is no new Python code to test.

The VS Code extension's routing logic cannot be meaningfully tested via pytest because:
- It requires a live VS Code instance with an LLM model
- Tool routing is non-deterministic (LLM output varies between calls)
- The VS Code `LanguageModelChatMessage` API is only available inside the extension host

Therefore, all Phase 7 testing is **manual QA** performed in a running VS Code instance with the VSIX installed.

### Test Categories

```
Phase 7 Testing
├── Unit Verification (code inspection, no execution)
│   └── Category assignment completeness check
├── Manual QA — Stage 1 (36 prompts, verify output channel category)
├── Manual QA — Stage 2 (36 prompts, verify output channel tool selection)
├── Manual QA — End-to-End (36 prompts, verify final user-facing output)
├── Manual QA — Fallback Path (3 scenarios)
├── Manual QA — Regression (8 previously working prompts)
├── Manual QA — Edge Cases (8 ambiguous/unusual prompts)
├── Manual QA — Multi-Turn (3 conversation sequences)
├── Diagnostics Verification (output channel log format)
├── Code Cleanup Verification (grep for removed items)
└── Performance Baseline (latency comparison)
```

---

## 2. Test Principles

1. **Output channel is the oracle.** For routing tests, the VS Code output channel (`FRP Agent`) shows exactly which Stage 1 category and Stage 2 tool were selected. This is the definitive source of truth.
2. **Test one category per prompt.** Each test prompt is designed to target a single category. Ambiguous prompts are tested separately in the edge case section.
3. **Both stages must be correct.** A test passes only when BOTH Stage 1 (category) AND Stage 2 (tool) are correct. A correct Stage 1 with wrong Stage 2 is a partial failure that needs investigation.
4. **Existing behavior is the baseline.** For previously working prompts, the expected result is the same as before Phase 7. For previously broken prompts (DID queries), the expected result is the correct tool.
5. **Fallback must work.** The `routeWithAllTools()` fallback path is tested explicitly — it must function correctly even if the two-stage path is disabled.
6. **Run pytest after every sprint.** Even though no Python code changes, confirm 697 tests still pass (ensures no accidental file corruption or import issues from build process).

---

## 3. Unit Verification — Category Assignments

This is a code inspection check performed once during Sprint 1 (S1-7). No execution required.

### Verification Steps

| # | Check | Method | Expected Result |
|---|---|---|---|
| UV-1 | Every `FRP_TOOLS` entry has a category | Compare `FRP_TOOLS.map(t => t.name)` against all values in `CATEGORY_TOOLS` | All 36 tool names present in exactly one category |
| UV-2 | No tool appears in multiple categories | Count occurrences of each tool name across all `CATEGORY_TOOLS` arrays | Each count = 1 |
| UV-3 | No phantom tools in `CATEGORY_TOOLS` | Every tool name in `CATEGORY_TOOLS` must exist in `FRP_TOOLS` | No orphaned references |
| UV-4 | Category count = 6 | `INTENT_CATEGORIES.length` | 6 |
| UV-5 | Tool count sums to 36 | Sum of all `CATEGORY_TOOLS` array lengths | 36 = `FRP_TOOLS.length` |
| UV-6 | `CATEGORY_TOOLS` keys match `INTENT_CATEGORIES` names | `Object.keys(CATEGORY_TOOLS)` vs `INTENT_CATEGORIES.map(c => c.name)` | Same 6 names |

### Quick Console Check (paste in developer tools)

```javascript
// Run this in VS Code developer console after extension loads
const toolNames = FRP_TOOLS.map(t => t.name);
const categoryToolNames = Object.values(CATEGORY_TOOLS).flat();
console.log('FRP_TOOLS count:', toolNames.length);
console.log('CATEGORY_TOOLS total:', categoryToolNames.length);
console.log('Missing from categories:', toolNames.filter(n => !categoryToolNames.includes(n)));
console.log('Phantom in categories:', categoryToolNames.filter(n => !toolNames.includes(n)));
console.log('Duplicates:', categoryToolNames.filter((n, i) => categoryToolNames.indexOf(n) !== i));
```

Expected output:
```
FRP_TOOLS count: 36
CATEGORY_TOOLS total: 36
Missing from categories: []
Phantom in categories: []
Duplicates: []
```

---

## 4. Stage 1 Classification Tests

For each test prompt, check the VS Code output channel for the Stage 1 classification result. The format is: `[FRP] Stage 1 result: <category_name>`.

### deal_mapping Category (5 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-DM-1 | `Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` | `deal_mapping` |
| S1-DM-2 | `which keywords map to servicer 296` | `deal_mapping` |
| S1-DM-3 | `show me all deals for CompanyID 569` | `deal_mapping` |
| S1-DM-4 | `are there any orphaned jobs with no deal mapping` | `deal_mapping` |
| S1-DM-5 | `check for ImportDID collisions` | `deal_mapping` |

### job_config Category (5 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-JC-1 | `list all cmbs jobs` | `job_config` |
| S1-JC-2 | `show details for job CMLTI_Fay` | `job_config` |
| S1-JC-3 | `validate the email settings` | `job_config` |
| S1-JC-4 | `what scrapers do we have` | `job_config` |
| S1-JC-5 | `create a new job from CMBS_GreyCo template` | `job_config` |

### processing Category (5 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-PR-1 | `has TPMT_SPS been processed today` | `processing` |
| S1-PR-2 | `show processing history for servicer 296` | `processing` |
| S1-PR-3 | `what templates are failing` | `processing` |
| S1-PR-4 | `pipeline view for deal CMLTI 2014-A` | `processing` |
| S1-PR-5 | `how long does the CMBS scrubber take to run` | `processing` |

### logs_ops Category (5 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-LO-1 | `show me today's daily summary` | `logs_ops` |
| S1-LO-2 | `any DID lookup failures recently` | `logs_ops` |
| S1-LO-3 | `how is job CMBS_GreyCo performing` | `logs_ops` |
| S1-LO-4 | `show log trends for the past week` | `logs_ops` |
| S1-LO-5 | `sync the latest log files` | `logs_ops` |

### deployment Category (4 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-DP-1 | `save the email settings` | `deployment` |
| S1-DP-2 | `list available backups` | `deployment` |
| S1-DP-3 | `what changed since last deploy` | `deployment` |
| S1-DP-4 | `rollback to the previous version` | `deployment` |

### system_admin Category (5 prompts)

| # | Test Prompt | Expected Stage 1 |
|---|---|---|
| S1-SA-1 | `triage this email from reports@servicer.com about monthly report` | `system_admin` |
| S1-SA-2 | `which jobs could be consolidated` | `system_admin` |
| S1-SA-3 | `what if we remove servicer 569` | `system_admin` |
| S1-SA-4 | `run a full system health check` | `system_admin` |
| S1-SA-5 | `show agent status` | `system_admin` |

**Pass Criteria:** All 29 prompts produce the expected Stage 1 category in the output channel.

---

## 5. Stage 2 Tool Selection Tests

For each test prompt, check the output channel for Stage 2 tool selection. The format is: `[FRP] Stage 2 selected: <tool_name>(...)`.

### deal_mapping Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-DM-1 | `Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | `deal_lookup` | `query: "ICW MAT TRUST SUBI A1"` |
| S2-DM-2 | `show all deals for CompanyID 569` | `deal_lookup` | `query: "569"` |
| S2-DM-3 | `build a servicer dossier for CMBS_GreyCo` | `servicer_dossier` | `query: "CMBS_GreyCo"` |
| S2-DM-4 | `are there orphaned jobs` | `orphan_detection` | (no input) |
| S2-DM-5 | `any coverage gaps` | `coverage_gaps` | (optional prompt) |

### job_config Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-JC-1 | `list all cmbs jobs` | `search_jobs` | `query: "cmbs"` |
| S2-JC-2 | `show details for CMLTI_Fay` | `job_detail` | `jobName: "CMLTI_Fay"` |
| S2-JC-3 | `validate email settings` | `validate_email` | (no input) |
| S2-JC-4 | `validate sftp settings` | `validate_sftp` | (no input) |
| S2-JC-5 | `show template inventory` | `templates` | (no input) |

### processing Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-PR-1 | `has TPMT_SPS been processed today` | `template_status` | `query: "TPMT_SPS"` |
| S2-PR-2 | `processing history for servicer 296` | `processing_history` | `query: "296"` |
| S2-PR-3 | `what templates are failing` | `failure_analysis` | (optional filters) |
| S2-PR-4 | `trace file M:\Data\report.xlsx` | `source_trace` | `filepath: "M:\\Data\\report.xlsx"` |
| S2-PR-5 | `pipeline view for CMLTI 2014-A` | `deal_pipeline` | `query: "CMLTI 2014-A"` |

### logs_ops Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-LO-1 | `show today's daily summary` | `daily_summary` | (optional date) |
| S2-LO-2 | `any DID lookup failures` | `did_failures` | (no input) |
| S2-LO-3 | `how is CMBS_GreyCo performing` | `job_health` | `jobName: "CMBS_GreyCo"` |
| S2-LO-4 | `show processing trends` | `log_trends` | (no input) |
| S2-LO-5 | `sync log files` | `sync_logs` | (no input) |

### deployment Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-DP-1 | `save email settings` | `save_settings` | `type: "email"` |
| S2-DP-2 | `list backups` | `list_backups` | (no input) |
| S2-DP-3 | `what changed since last deploy` | `xml_diff` | (no input) |
| S2-DP-4 | `rollback to previous version` | `rollback` | (optional prompt) |

### system_admin Tools

| # | Test Prompt | Expected Tool | Expected Input Key |
|---|---|---|---|
| S2-SA-1 | `triage email from reports@servicer.com` | `triage_email` | `prompt: "..."` |
| S2-SA-2 | `which jobs can be consolidated` | `consolidation_analysis` | (no input) |
| S2-SA-3 | `what if we remove servicer 569` | `impact_analysis` | `prompt: "..."` |
| S2-SA-4 | `system health check` | `system_health` | (no input) |
| S2-SA-5 | `agent status` | `agent_status` | (no input) |

**Pass Criteria:** All 25 prompts produce the expected Stage 2 tool in the output channel with correct primary input parameter.

---

## 6. End-to-End Routing Tests

These tests verify the complete path from user prompt to formatted response. They confirm that the handler produces the expected output type (not just that the right tool was selected).

### Critical Path Tests (Previously Broken)

| # | Prompt | Expected Behavior | Pass Criteria |
|---|---|---|---|
| E2E-1 | `Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` | `deal_lookup` → no matches found | Response says "No matching deals found" (deterministic not-found), NOT a list of 9 unrelated jobs |
| E2E-2 | `any jobs for deal CMLTI 2014-A` | `deal_lookup` → returns matching deals + linked jobs | Response shows deal records from tblExternalDIDRef with linked job information |
| E2E-3 | `do we monitor DID "TOWD 2017-1A"` | `deal_lookup` → returns match or not-found | Response either shows matching deal records or says "not found" |

### Previously Working Tests (Regression Check)

| # | Prompt | Expected Behavior | Pass Criteria |
|---|---|---|---|
| E2E-4 | `list all cmbs jobs` | `search_jobs` → 9 CMBS email jobs | Table showing 9 jobs with JobName, Sender, ServicerID, etc. |
| E2E-5 | `show details for CMLTI_Fay` | `job_detail` → full job config + linked deals | Detailed config display + tblExternalDIDRef linked deals |
| E2E-6 | `list all deals that use the job with ServicerID 224` | `deal_lookup` or `job_detail` → deals for ServicerID 224 | Deal records shown correctly |
| E2E-7 | `validate the email settings` | `validate_email` → validation report | Validation results with ✅/❌ |
| E2E-8 | `show agent status` | `agent_status` → status info | Version, connection status, etc. |

### Data Source Indicator Tests

| # | Prompt | Expected Footer |
|---|---|---|
| DSI-1 | `list all cmbs jobs` | Footer shows SQLite or XML data source |
| DSI-2 | `Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | Footer shows MySQL or appropriate source |

---

## 7. Fallback Path Tests

These tests verify that the `routeWithAllTools()` fallback path works correctly when Stage 1 fails.

### Test Procedure

To test the fallback path, temporarily modify `classifyIntent()` to force a failure:

```javascript
// TEMPORARY — for testing only
async function classifyIntent(prompt, historyContext, model, token, shared) {
  shared.outputChannel.appendLine('[FRP] Stage 1: FORCED FAILURE (testing fallback)');
  return null; // Force fallback
}
```

### Fallback Tests

| # | Prompt | Expected Behavior | Expected Output Channel |
|---|---|---|---|
| FB-1 | `list all cmbs jobs` | Same result as current production | `[FRP] Stage 1: FORCED FAILURE` → `[FRP] Falling back to routeWithAllTools()` → `[FRP] routeWithAllTools selected: search_jobs(...)` |
| FB-2 | `show details for CMLTI_Fay` | Same result as current production | `[FRP] routeWithAllTools selected: job_detail(...)` |
| FB-3 | `show agent status` | Same result as current production | `[FRP] routeWithAllTools selected: agent_status(...)` |

**After testing, restore `classifyIntent()` to its proper implementation.**

### Pass Criteria

- All 3 fallback prompts produce correct results (same as pre-Phase 7)
- Output channel clearly shows the fallback was triggered
- No user-facing error messages

---

## 8. Regression Tests — Previously Working Prompts

These 8 prompts are known to work correctly in the current single-stage router. They must continue to work after Phase 7.

| # | Prompt | Expected Tool | Expected Result Type |
|---|---|---|---|
| REG-1 | `list all cmbs jobs` | `search_jobs` | Table of CMBS jobs |
| REG-2 | `show details for CMLTI_Fay` | `job_detail` | Full job config |
| REG-3 | `list all deals that use the job with ServicerID 224` | `deal_lookup` | Deal records |
| REG-4 | `validate email settings` | `validate_email` | Validation report |
| REG-5 | `show template inventory` | `templates` | Template list |
| REG-6 | `show agent status` | `agent_status` | Status info |
| REG-7 | `list all jobs` | `search_jobs` | Full job list |
| REG-8 | `search jobs by fay` | `search_jobs` | Jobs matching "fay" |

---

## 9. Edge Case Tests

These prompts are deliberately ambiguous, unusual, or designed to test category boundary decisions.

### Ambiguous Prompts (Multiple Keywords Crossing Categories)

| # | Prompt | Expected Category | Expected Tool | Why |
|---|---|---|---|---|
| EC-1 | `any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | `deal_mapping` | `deal_lookup` | **THE critical test.** "jobs" suggests job_config, but "deal DID" is the primary signal → deal_mapping |
| EC-2 | `show me the jobs and their processing status for servicer 296` | `deal_mapping` or `processing` | `servicer_dossier` or `deal_pipeline` | Mentions both "jobs" and "processing status" — should go to the more comprehensive tool |
| EC-3 | `which deals have failing processing` | `processing` | `failure_analysis` | Mentions "deals" and "failing processing" — the question is about failures (processing layer) |
| EC-4 | `is the CMBS_GreyCo job healthy` | `logs_ops` | `job_health` | "healthy" + job name → log-derived health metrics |

### Unusual/Edge Prompts

| # | Prompt | Expected Category | Expected Tool | Why |
|---|---|---|---|---|
| EC-5 | `what's the weather today` | Any (or free-form decline) | None or free-form response | Out-of-domain question — should be politely declined |
| EC-6 | `list all` | `job_config` | `search_jobs` (query: "*") | Minimal input — should default to listing all jobs |
| EC-7 | `scrubber TPMT_SPS_CFF` | `job_config` or `processing` | `search_jobs` or `template_status` | A scrubber name alone — could go either way depending on LLM interpretation |
| EC-8 | `296` | `deal_mapping` | `deal_lookup` (query: "296") | A bare number — should interpret as a ServicerID/CompanyID |

### Pass Criteria

- EC-1 is **mandatory pass** — this is the critical DID routing fix
- EC-2 through EC-4 may route to any reasonable tool — verify the user-facing output makes sense
- EC-5 should not crash — OK to get a free-form "I can only help with FRP topics" response
- EC-6 through EC-8 should produce some reasonable result — no crashes, no "Unknown tool" errors

---

## 10. Multi-Turn Conversation Tests

These tests verify that conversation context is correctly passed to both Stage 1 and Stage 2.

### Conversation Sequence 1: Job → Deals

| Turn | User Prompt | Expected Category | Expected Tool | Expected Behavior |
|---|---|---|---|---|
| 1 | `list all cmbs jobs` | `job_config` | `search_jobs` | Shows 9 CMBS jobs |
| 2 | `show me the deals for the first one` | `job_config` | `job_detail` | LLM extracts job name from previous results, shows deals linked to that job |
| 3 | `has it been processed recently` | `processing` | `template_status` or `processing_history` | LLM extracts template/DID from previous context |

### Conversation Sequence 2: Deal → Processing

| Turn | User Prompt | Expected Category | Expected Tool | Expected Behavior |
|---|---|---|---|---|
| 1 | `show me all deals for CompanyID 569` | `deal_mapping` | `deal_lookup` | Shows deals for CompanyID 569 |
| 2 | `are any of those deals failing` | `processing` | `failure_analysis` | LLM extracts DIDs from previous results, checks failures |

### Conversation Sequence 3: Deal Lookup → Follow Up

| Turn | User Prompt | Expected Category | Expected Tool | Expected Behavior |
|---|---|---|---|---|
| 1 | `do we have any jobs for deal DID = "CMLTI 2014-A"` | `deal_mapping` | `deal_lookup` | Shows deals + linked jobs |
| 2 | `show me the full pipeline for that deal` | `processing` | `deal_pipeline` | E2E pipeline view |

### Pass Criteria

- Turn 1 in each sequence routes correctly (as per Stage 1 tests)
- Follow-up turns correctly use conversation context to extract identifiers
- No "I don't know what you mean" responses on follow-ups
- Category may shift between turns (e.g., from `job_config` to `processing`) — this is expected and correct

---

## 11. Diagnostics Verification

Verify the output channel logging format for 3 representative prompts.

### Expected Log Format — Two-Stage Success

```
[FRP] Stage 1: classifying intent for: "list all cmbs jobs"
[FRP] Stage 1 raw response: { "category": "job_config" }
[FRP] Stage 1 result: job_config
[FRP] Stage 2: routing within job_config (7 tools: search_jobs, job_detail, validate_email, validate_sftp, templates, create_job, edit_job)
[FRP] Stage 2 selected: search_jobs({"query":"cmbs"})
[FRP] LLM tool call → search_jobs({"query":"cmbs"})
```

### Expected Log Format — Stage 1 Fallback

```
[FRP] Stage 1: classifying intent for: "some confusing prompt"
[FRP] Stage 1 raw response: I think you should use deal_lookup
[FRP] Stage 1 error: Unexpected token 'I' at position 0 — falling back
[FRP] Falling back to routeWithAllTools()
[FRP] routeWithAllTools: sending request (model=gpt-4.1, tools=36)
[FRP] routeWithAllTools selected: deal_lookup({"query":"..."})
```

### Verification Checklist

| # | Check | Expected |
|---|---|---|
| DV-1 | Stage 1 input logged | `[FRP] Stage 1: classifying intent for: "<prompt>"` |
| DV-2 | Stage 1 raw response logged | `[FRP] Stage 1 raw response: <json>` |
| DV-3 | Stage 1 result logged | `[FRP] Stage 1 result: <category>` |
| DV-4 | Stage 2 tool list logged | `[FRP] Stage 2: routing within <category> (N tools: ...)` |
| DV-5 | Stage 2 selection logged | `[FRP] Stage 2 selected: <tool>(...)` |
| DV-6 | Tool execution logged | `[FRP] LLM tool call → <tool>(...)` |
| DV-7 | Fallback logged (when triggered) | `[FRP] Falling back to routeWithAllTools()` |

---

## 12. Manual QA Checklist

Complete checklist to be executed during Sprint 4 (S4-2). Each row is a test prompt. Record the result (PASS/FAIL) and any notes.

### Instructions

1. Open VS Code with the FRP Agent VSIX installed
2. Open the `FRP Agent` output channel (View → Output → select "FRP Agent")
3. For each prompt below, type it in the `@frp` chat
4. Check the output channel for Stage 1 category and Stage 2 tool
5. Check the chat response for correct content
6. Record PASS or FAIL

### Checklist

| # | Prompt | Exp. Category | Exp. Tool | Result | Notes |
|---|---|---|---|---|---|
| QA-1 | `list all cmbs jobs` | job_config | search_jobs | | |
| QA-2 | `list all jobs` | job_config | search_jobs | | |
| QA-3 | `search jobs by fay` | job_config | search_jobs | | |
| QA-4 | `show details for CMLTI_Fay` | job_config | job_detail | | |
| QA-5 | `validate email settings` | job_config | validate_email | | |
| QA-6 | `validate sftp settings` | job_config | validate_sftp | | |
| QA-7 | `show template inventory` | job_config | templates | | |
| QA-8 | `Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"` | deal_mapping | deal_lookup | | **CRITICAL** |
| QA-9 | `any jobs for deal CMLTI 2014-A` | deal_mapping | deal_lookup | | **CRITICAL** |
| QA-10 | `show all deals for CompanyID 569` | deal_mapping | deal_lookup | | |
| QA-11 | `which keywords map to servicer 296` | deal_mapping | deal_lookup | | |
| QA-12 | `build servicer dossier for 224` | deal_mapping | servicer_dossier | | |
| QA-13 | `are there orphaned jobs` | deal_mapping | orphan_detection | | |
| QA-14 | `any coverage gaps` | deal_mapping | coverage_gaps | | |
| QA-15 | `check for ImportDID collisions` | deal_mapping | collision_detection | | |
| QA-16 | `has TPMT_SPS been processed today` | processing | template_status | | |
| QA-17 | `processing history for servicer 296` | processing | processing_history | | |
| QA-18 | `what templates are failing` | processing | failure_analysis | | |
| QA-19 | `trace file M:\Data\report.xlsx` | processing | source_trace | | |
| QA-20 | `manual vs automated queue stats` | processing | manual_queue | | |
| QA-21 | `slowest processing templates` | processing | processing_duration | | |
| QA-22 | `pipeline view for CMLTI 2014-A` | processing | deal_pipeline | | |
| QA-23 | `search staging for TemplateProcessID 12345` | processing | staging_search | | |
| QA-24 | `show today's daily summary` | logs_ops | daily_summary | | |
| QA-25 | `any DID lookup failures` | logs_ops | did_failures | | |
| QA-26 | `how is CMBS_GreyCo performing` | logs_ops | job_health | | |
| QA-27 | `show deal activity for CMLTI 2014-A` | logs_ops | deal_activity | | |
| QA-28 | `show processing trends` | logs_ops | log_trends | | |
| QA-29 | `performance rankings` | logs_ops | log_performance | | |
| QA-30 | `sync log files` | logs_ops | sync_logs | | |
| QA-31 | `save email settings` | deployment | save_settings | | |
| QA-32 | `list backups` | deployment | list_backups | | |
| QA-33 | `what changed since last deploy` | deployment | xml_diff | | |
| QA-34 | `rollback to previous version` | deployment | rollback | | |
| QA-35 | `triage email from reports@servicer.com` | system_admin | triage_email | | |
| QA-36 | `which jobs can be consolidated` | system_admin | consolidation_analysis | | |
| QA-37 | `what if we remove servicer 569` | system_admin | impact_analysis | | |
| QA-38 | `system health check` | system_admin | system_health | | |
| QA-39 | `agent status` | system_admin | agent_status | | |

**Pass threshold:** All 39 prompts pass. QA-8 and QA-9 are **mandatory pass** — they are the critical fix that Phase 7 exists to solve.

---

## 13. Code Cleanup Verification

After Sprint 3, verify that all removed items are actually gone.

### Grep Checks

Run these searches in `participant.js`. All should return **zero matches**.

| # | Search Pattern | Why It Should Be Gone |
|---|---|---|
| CC-1 | `dealIntentRe` | Regex pre-routing removed |
| CC-2 | `dealIntent2` | Second regex pattern removed |
| CC-3 | `dealMatch` | Pre-routing match variable removed |
| CC-4 | `Pre-route intercept` | Comment for regex block removed |
| CC-5 | `Do NOT use this when` | Negative constraint in search_jobs description removed |
| CC-6 | `ALWAYS USE THIS` | Negative constraint in deal_lookup description removed |
| CC-7 | `Tool Selection Decision Tree` | Decision tree header removed |
| CC-8 | `IMPORTANT: If the user says "DID"` | Decision tree clause removed |

### Positive Checks

These should still be present:

| # | Search Pattern | Why It Should Be Present |
|---|---|---|
| PC-1 | `INTENT_CATEGORIES` | New constant |
| PC-2 | `CATEGORY_TOOLS` | New constant |
| PC-3 | `classifyIntent` | New function |
| PC-4 | `routeWithinCategory` | New function |
| PC-5 | `routeWithAllTools` | Fallback function |
| PC-6 | `buildClassifierPrompt` | New function |
| PC-7 | `Stage 1` | Log messages |
| PC-8 | `Stage 2` | Log messages |
| PC-9 | `Three-Table Pipeline` | Preserved in DOMAIN_KNOWLEDGE |
| PC-10 | `Cross-Reference Chains` | Preserved in DOMAIN_KNOWLEDGE |

---

## 14. Performance Baseline

### Measurement Method

For 3 representative prompts, measure total response time (from pressing Enter to seeing the complete response) before Phase 7 and after Phase 7.

### Prompts to Measure

| # | Prompt | Pre-Phase 7 Time | Post-Phase 7 Time | Delta |
|---|---|---|---|---|
| PB-1 | `list all cmbs jobs` | ___s | ___s | ___s |
| PB-2 | `show details for CMLTI_Fay` | ___s | ___s | ___s |
| PB-3 | `Do we have any jobs for deal DID = "ICW MAT TRUST SUBI A1"` | ___s | ___s | ___s |

### Acceptable Performance

- **Expected latency increase:** 200–500ms (one additional lightweight LLM call for Stage 1)
- **Maximum acceptable increase:** 2× current response time
- **If latency exceeds 2×:** Investigate Stage 1 prompt length, consider reducing category descriptions or examples

### Mitigation If Latency Is Too High

1. Reduce `INTENT_CATEGORIES[].examples` from 4–5 examples to 2–3
2. Shorten `INTENT_CATEGORIES[].description` to 1 sentence
3. Remove disambiguation rules from classifier prompt (rely on examples + descriptions alone)
4. As a last resort: use a smaller/faster model for Stage 1 classification (e.g., force gpt-4o-mini for Stage 1 while keeping gpt-4.1 for Stage 2)

---

## 15. Test Execution Order

### Sprint 1 Tests (after CP-71)
1. UV-1 through UV-6 (category assignment verification)
2. QA-1, QA-4, QA-8 (3 representative prompts — extension still works via fallback)

### Sprint 2 Tests (after CP-72)
1. All Stage 1 tests (S1-DM-1 through S1-SA-5) — 29 prompts
2. All Stage 2 tests (S2-DM-1 through S2-SA-5) — 25 prompts
3. Fallback tests (FB-1 through FB-3)
4. PB-1 through PB-3 (initial performance measurement)

### Sprint 3 Tests (after CP-73)
1. Re-run QA-1, QA-8, QA-9 (verify still works after cleanup)
2. CC-1 through CC-8 (code cleanup verification)
3. PC-1 through PC-10 (positive verification)

### Sprint 4 Tests (after CP-74)
1. Full manual QA checklist (QA-1 through QA-39) — complete pass
2. End-to-end tests (E2E-1 through E2E-8)
3. Edge case tests (EC-1 through EC-8)
4. Multi-turn tests (3 conversation sequences)
5. Diagnostics verification (DV-1 through DV-7)
6. Data source indicator tests (DSI-1, DSI-2)
7. Performance baseline comparison (PB-1 through PB-3)
8. `pytest tests/ -q` → 697 passed, 0 failed
