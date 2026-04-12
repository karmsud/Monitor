# Phase 8: Testing Plan
## FRP Agent — ReAct Pipeline Orchestrator

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Companion:** [04_IMPLEMENTATION_PLAN.md](04_IMPLEMENTATION_PLAN.md)  
**Test Scope:** Manual QA via VS Code chat (`@frp`) + output channel verification  
**Test Environment:** VS Code with installed VSIX, MySQL running, backend reachable

---

## Table of Contents
1. [Testing Strategy](#1-testing-strategy)  
2. [Pipeline End-to-End Tests](#2-pipeline-end-to-end-tests)  
3. [Pipeline Failure-at-Each-Step Tests](#3-pipeline-failure-at-each-step-tests)  
4. [Remediation Offer Tests](#4-remediation-offer-tests)  
5. [Loop Cap & Edge Case Tests](#5-loop-cap--edge-case-tests)  
6. [Classifier Integration Tests](#6-classifier-integration-tests)  
7. [Phase 7 Regression Tests](#7-phase-7-regression-tests)  
8. [Progress Streaming Tests](#8-progress-streaming-tests)  
9. [Error Handling Tests](#9-error-handling-tests)  
10. [Output Channel Verification](#10-output-channel-verification)  
11. [Backend Regression Tests](#11-backend-regression-tests)  
12. [Acceptance Criteria Matrix](#12-acceptance-criteria-matrix)

---

## 1. Testing Strategy

### Test Types

| Type | Method | Purpose |
|---|---|---|
| **Manual QA** | Type prompt into `@frp` chat, inspect response + output channel | Verify end-to-end behavior |
| **Output Channel Audit** | Read `[FRP]` log lines in VS Code Output panel | Verify internal routing, tool selection, step progression |
| **Backend Regression** | `pytest tests/ -q` | Ensure no Python backend regressions |
| **Visual Inspection** | Look at chat UI | Verify progress streaming, markdown formatting, report structure |

### Test Data Requirements

| Data | Source | Purpose |
|---|---|---|
| Real `.msg` file | `Email Logs/` folder (production emails) | End-to-end .msg file pipeline test |
| Known sender domain (with job) | Any sender domain that matches an existing job in Settings.xml (e.g., `fay.com`) | Success path testing |
| Unknown sender domain | Any domain NOT in Settings.xml (e.g., `unknown-test-domain.com`) | Failure path testing |
| Known ServicerID with DIDs | Any ServicerID that has rows in tblExternalDIDRef (e.g., `296`) | DID lookup success testing |
| Known ServicerID without DIDs | Any ServicerID with no rows in tblExternalDIDRef | DID lookup failure testing |

### Test Naming Convention

Tests are labeled by category:
- **P8-E2E-N**: End-to-end pipeline tests
- **P8-FAIL-N**: Failure-at-each-step tests
- **P8-REM-N**: Remediation offer tests
- **P8-EDGE-N**: Loop cap and edge case tests
- **P8-CLS-N**: Classifier integration tests
- **P8-REG-N**: Phase 7 regression tests
- **P8-STRM-N**: Progress streaming tests
- **P8-ERR-N**: Error handling tests

---

## 2. Pipeline End-to-End Tests

These test the complete email triage pipeline from start to finish.

### P8-E2E-1: Full Success Path — Pasted Metadata

**Prompt:**
```
@frp analyze this email from reports@fay.com, subject "Monthly Report Jan 2026", attachment FayReport.xlsx
```

**Expected Behavior:**
1. Stage 1 classifies as `system_admin`, `mode: pipeline`
2. `reactLoop()` starts with `email_triage` pipeline
3. LLM calls `search_jobs` with query `fay.com` → finds matching job
4. LLM calls `deal_lookup` with ServicerID → finds DIDs
5. LLM reasons about keyword matching (no tool call)
6. LLM calls `job_health` or `daily_summary` → log evidence
7. LLM calls `staging_search` or `template_status` → staging results
8. LLM produces final report with all sections

**Expected Output:**
- Structured markdown report with: Email Summary, Job Match (✅), Deal Coverage, Keyword Match, Log Verification, Template Staging, Summary
- Data Sources section at the end

**Output Channel Verification:**
```
[FRP] Stage 1: classifying intent for: "analyze this email from reports@fay.com..."
[FRP] Stage 1 result: system_admin (mode: pipeline)
[FRP] Routing to ReAct pipeline: Email Triage Pipeline
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"fay.com"})
[FRP] ReAct step 2: deal_lookup({"query":"296"})
...
[FRP] ReAct: LLM produced final report at step N (NNNN chars)
```

---

### P8-E2E-2: Full Success Path — .msg File

**Prompt:**
```
@frp analyze email at "C:\path\to\real\email.msg"
```
*(Replace path with a real `.msg` file path from `Email Logs/`)*

**Expected Behavior:**
1. Stage 1 classifies as pipeline
2. LLM calls `triage_email` with the file path → parses .msg
3. LLM extracts sender, subject, attachments from triage result
4. LLM proceeds with Steps 2–6 using parsed metadata

**Key Verification:**
- First tool call should be `triage_email` (not `search_jobs`)
- Parsed email metadata should appear in the report

---

### P8-E2E-3: Pasted Metadata — Minimal Info

**Prompt:**
```
@frp is this email covered? sender: reports@greycapital.com, subject: Q4 Deal Summary
```

**Expected Behavior:**
- LLM works with just sender + subject (no attachments, no date)
- Pipeline proceeds normally from Step 2

**Key Verification:**
- LLM does NOT call `triage_email` (no .msg file path)
- Report shows "Attachment: N/A" or similar

---

### P8-E2E-4: Natural Language Pipeline Trigger

**Prompt:**
```
@frp what happens when an email from reports@fay.com arrives?
```

**Expected Behavior:**
- Stage 1 detects this as a pipeline query (matches trigger pattern)
- LLM traces the full pipeline: job match → DID lookup → logs → staging

**Key Verification:**
- This is a pipeline trigger, NOT a single-tool `search_jobs` query
- Output channel shows `mode: pipeline`

---

## 3. Pipeline Failure-at-Each-Step Tests

These tests verify that the pipeline handles failures gracefully at each step.

### P8-FAIL-1: Step 2 Failure — No Matching Job

**Prompt:**
```
@frp analyze this email from reports@unknown-test-domain.com, subject "Mystery Report"
```

**Expected Behavior:**
1. LLM calls `search_jobs` with `unknown-test-domain.com`
2. Tool returns no results
3. LLM stops pipeline (does NOT proceed to Step 3)
4. Reports "No matching job found for sender domain unknown-test-domain.com"
5. Offers remediation: "Would you like to create a new job for this sender?"

**Key Verification:**
- Only ONE tool call made (`search_jobs`)
- No `deal_lookup` call
- Remediation offer in the report

---

### P8-FAIL-2: Step 3 Failure — Job Found, No DIDs

**Prompt:**
Use a sender domain that matches a job whose ServicerID has no rows in tblExternalDIDRef.

**Expected Behavior:**
1. LLM calls `search_jobs` → finds job with ServicerID X
2. LLM calls `deal_lookup` with CompanyID X → returns no DIDs
3. LLM reports: "Job found (ServicerID X), but no DIDs configured for CompanyID X"
4. LLM may still check logs/staging at the job level (Steps 5/6 don't depend on DIDs)
5. Offers remediation: "Would you like to set up deal mappings for this job?"

**Key Verification:**
- Two tool calls made (`search_jobs`, `deal_lookup`)
- Report shows job match ✅, DID coverage ❌
- Steps 5/6 may or may not run (both are acceptable)

---

### P8-FAIL-3: Step 4 Failure — DIDs Exist, No Keyword Match

**Prompt:**
Use a sender domain that matches a job with DIDs, but use an email subject that doesn't match any ImportDID keyword.

**Expected Behavior:**
1. LLM calls `search_jobs` → finds job
2. LLM calls `deal_lookup` → finds DIDs with keywords
3. LLM compares keywords against subject → no match
4. Reports: "DIDs exist but no ImportDID keyword matches email subject 'X'"
5. Shows existing keywords vs. the subject
6. Offers remediation: "Would you like to add a keyword?"
7. May still check logs/staging at job level

**Key Verification:**
- Report shows: job ✅, DIDs ✅, keyword match ❌
- Existing keywords listed alongside the unmatched subject

---

## 4. Remediation Offer Tests

### P8-REM-1: Create Job Remediation Offer

**Prompt:**
```
@frp analyze email from reports@brand-new-client.com, subject "Data File"
```

**Expected Behavior:**
- Report includes a remediation section offering to create a new job
- Language: "Would you like to create a new job for this sender?" or similar

**Key Verification:**
- Remediation text is present in the report
- Follow-up prompt suggestion works if user accepts

---

### P8-REM-2: DID Setup Remediation Offer

**Test:** Use a sender that matches a job with no DIDs.

**Expected Behavior:**
- Report includes remediation: "Would you like to set up deal mappings for this job?"

---

### P8-REM-3: Keyword Addition Remediation Offer

**Test:** Use a sender that matches a job with DIDs, but email subject doesn't match any keyword.

**Expected Behavior:**
- Report includes remediation: "Would you like to add a keyword to an existing DID?"

---

## 5. Loop Cap & Edge Case Tests

### P8-EDGE-1: maxSteps Cap

**Setup:** Temporarily set `PIPELINE_DEFINITIONS.email_triage.maxSteps = 2`

**Prompt:**
```
@frp analyze email from reports@fay.com, subject "Monthly Report"
```

**Expected Behavior:**
1. Loop executes 2 steps (e.g., `search_jobs` + `deal_lookup`)
2. Hits cap → `compilePipelineReport()` called
3. Partial report displayed with "⚠️ Analysis reached the maximum step limit" warning
4. Report shows the 2 completed steps with their results

**Reset:** Set `maxSteps` back to 8 after test.

---

### P8-EDGE-2: Empty User Prompt

**Prompt:**
```
@frp analyze email
```

**Expected Behavior:**
- Pipeline activates (if classifier detects "analyze email" as pipeline trigger)
- LLM realizes insufficient info and asks for more details OR produces a partial report noting missing information
- No crash, no infinite loop

---

### P8-EDGE-3: Very Long Email Subject

**Prompt:**
```
@frp analyze email from reports@fay.com, subject "Extremely Long Subject Line With Many Words That Goes On And On And Contains Multiple Keywords Like CMLTI And TPMT And Various Other Deal Identifiers That Might Match Multiple Things"
```

**Expected Behavior:**
- Pipeline handles long subject gracefully
- Keyword matching may find multiple matches (collision note)
- No truncation errors

---

### P8-EDGE-4: Multiple Emails in One Prompt

**Prompt:**
```
@frp analyze these two emails: 1) from reports@fay.com subject "Monthly Report" and 2) from data@greycapital.com subject "Q4 Summary"
```

**Expected Behavior:**
- LLM should either analyze the first email only and suggest a follow-up for the second, OR attempt to analyze both sequentially
- Either behavior is acceptable — the key is no crash and coherent output

---

### P8-EDGE-5: Pipeline Query with Conversation History

**Setup:** First send a single-tool query, then a pipeline query.

**Turn 1:**
```
@frp list all cmbs jobs
```

**Turn 2:**
```
@frp now analyze this email from reports@fay.com — does it match any of those jobs?
```

**Expected Behavior:**
- Turn 2 triggers pipeline mode
- Conversation history from Turn 1 is available in the pipeline
- LLM may reference the previous job list in its analysis

---

## 6. Classifier Integration Tests

### P8-CLS-1: Pipeline Trigger — Explicit Triage

**Prompt:** `@frp triage this email from reports@servicer.com`  
**Expected:** `mode: pipeline` in output channel

### P8-CLS-2: Pipeline Trigger — "Is This Covered?"

**Prompt:** `@frp is this email covered? sender fay.com, subject Report`  
**Expected:** `mode: pipeline`

### P8-CLS-3: Pipeline Trigger — "What Happens When?"

**Prompt:** `@frp what happens when we get an email from data@greycapital.com?`  
**Expected:** `mode: pipeline`

### P8-CLS-4: Pipeline Trigger — "Trace This Email"

**Prompt:** `@frp trace this email: sender reports@fay.com, subject "File Delivery"`  
**Expected:** `mode: pipeline`

### P8-CLS-5: Pipeline Trigger — .msg File Path

**Prompt:** `@frp analyze C:\emails\incoming.msg`  
**Expected:** `mode: pipeline`

### P8-CLS-6: NOT a Pipeline Trigger — Simple Job Search

**Prompt:** `@frp search for cmbs jobs`  
**Expected:** `mode: single_tool`, category: `job_config`

### P8-CLS-7: NOT a Pipeline Trigger — DID Lookup

**Prompt:** `@frp show deals for CompanyID 296`  
**Expected:** `mode: single_tool`, category: `deal_mapping`

### P8-CLS-8: NOT a Pipeline Trigger — Daily Summary

**Prompt:** `@frp show today's daily summary`  
**Expected:** `mode: single_tool`, category: `logs_ops`

### P8-CLS-9: NOT a Pipeline Trigger — Deployment

**Prompt:** `@frp save the email settings`  
**Expected:** `mode: single_tool`, category: `deployment`

### P8-CLS-10: Ambiguous — Could Be Pipeline or Single-Tool

**Prompt:** `@frp check this email sender: reports@fay.com`  
**Expected:** Ideally `mode: pipeline`, but `mode: single_tool` with `search_jobs` is also acceptable. Key: no crash, coherent response.

---

## 7. Phase 7 Regression Tests

Phase 8 must NOT break any Phase 7 behavior. Run these tests after every sprint.

### P8-REG-1: Deal Mapping (Phase 7 Fix)

**Prompt:** `@frp Do we have any jobs or keyword setup for deal DID = "ICW MAT TRUST SUBI A1"`  
**Expected:**
- Stage 1: `deal_mapping` (mode: `single_tool`)
- Stage 2: `deal_lookup`
- Response about the DID lookup (found or not found)

### P8-REG-2: Job Config

**Prompt:** `@frp list all cmbs jobs`  
**Expected:** Stage 1: `job_config` → Stage 2: `search_jobs`

### P8-REG-3: Processing

**Prompt:** `@frp has TPMT_SPS been processed today`  
**Expected:** Stage 1: `processing` → Stage 2: `template_status`

### P8-REG-4: Logs & Operations

**Prompt:** `@frp show today's daily summary`  
**Expected:** Stage 1: `logs_ops` → Stage 2: `daily_summary`

### P8-REG-5: Deployment

**Prompt:** `@frp what changed since last deploy`  
**Expected:** Stage 1: `deployment` → Stage 2: `xml_diff`

### P8-REG-6: System Admin (Non-Pipeline)

**Prompt:** `@frp run a system health check`  
**Expected:** Stage 1: `system_admin` (mode: `single_tool`) → Stage 2: `system_health`

### P8-REG-7: Fallback Path

**Test:** Temporarily corrupt `classifyIntent()` to return null.  
**Expected:** Extension falls back to `routeWithAllTools()` and still works.

---

## 8. Progress Streaming Tests

### P8-STRM-1: Progress Indicators Visible

**Prompt:** Any pipeline trigger prompt (e.g., `@frp analyze email from reports@fay.com, subject "Report"`)

**Expected:**
- User sees step-by-step progress indicators BEFORE the final report
- Example: "Step 1: calling search_jobs...", "Step 2: calling deal_lookup..."
- Progress indicators appear in real-time (not all at once)

### P8-STRM-2: Status Indicators After Tool Results

**Expected:**
- After each tool result, a brief ✅ or ❌ status indicator may appear
- Example: "✅ Found job: CMBS_GreyCo (ServicerID 296)"

### P8-STRM-3: Final Report Follows Progress

**Expected:**
- Progress indicators are followed by the structured markdown report
- The report is separate from the progress indicators (not interleaved)

---

## 9. Error Handling Tests

### P8-ERR-1: Backend Unreachable

**Setup:** Stop the Python backend (or disconnect MySQL).

**Prompt:** `@frp analyze email from reports@fay.com, subject "Report"`

**Expected:**
- First tool call (`search_jobs`) fails with connection error
- Error is returned to the LLM as a tool result
- LLM reports the error in its final text: "Unable to search jobs: connection error"
- No crash, no infinite loop

### P8-ERR-2: Cancellation Mid-Pipeline

**Setup:** Start a pipeline query, then cancel via Ctrl+C or closing the chat input.

**Expected:**
- Loop stops at the current step
- No orphan processes or hanging tool calls
- Partial output may be visible (acceptable)

### P8-ERR-3: LLM Error Mid-Pipeline

**Setup:** Difficult to manufacture — may need to wait for a natural occurrence.

**Expected:**
- If `model.sendRequest()` throws in the middle of the loop
- Loop breaks gracefully
- If any steps completed, `compilePipelineReport()` generates a partial report
- Output channel shows: `[FRP] ReAct: LLM error at step N: ...`

### P8-ERR-4: Tool Returns Unexpected Format

**Setup:** Difficult to manufacture.

**Expected:**
- If a tool returns data in an unexpected format, the LLM handles it (LLMs are good at making sense of varied JSON)
- No crash

---

## 10. Output Channel Verification

For every test, verify output channel (`[FRP]` prefix) shows expected log flow.

### Pipeline Query Log Flow

```
[FRP] Stage 1: classifying intent for: "<prompt>"
[FRP] Stage 1 raw response: {"category":"system_admin","mode":"pipeline"}
[FRP] Stage 1 result: system_admin (mode: pipeline)
[FRP] Routing to ReAct pipeline: Email Triage Pipeline
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"fay.com"})
[FRP] ReAct step 2: deal_lookup({"query":"296"})
[FRP] ReAct step 3: job_health({"job_name":"CMBS_GreyCo"})
[FRP] ReAct: LLM produced final report at step 4 (1234 chars)
```

### Single-Tool Query Log Flow (Regression)

```
[FRP] Stage 1: classifying intent for: "<prompt>"
[FRP] Stage 1 raw response: {"category":"job_config","mode":"single_tool"}
[FRP] Stage 1 result: job_config (mode: single_tool)
[FRP] Stage 2: routing within job_config (7 tools: search_jobs, job_detail, ...)
[FRP] Stage 2 selected: search_jobs({"query":"cmbs"})
```

### Error Log Flow

```
[FRP] Stage 1: classifying intent for: "<prompt>"
[FRP] Stage 1 result: system_admin (mode: pipeline)
[FRP] Routing to ReAct pipeline: Email Triage Pipeline
[FRP] ReAct: starting pipeline "email_triage" (max 8 steps, 10 tools)
[FRP] ReAct step 1: search_jobs({"query":"unknown.com"})
[FRP] ReAct: LLM produced final report at step 2 (412 chars)
```

---

## 11. Backend Regression Tests

### Automated Tests

```powershell
pytest tests/ -q
```

**Expected:** 697 passed, 0 failed (or more if new tests added)

Phase 8 makes NO changes to the Python backend. This test is a safety check to ensure no accidental modifications.

### Triage Backend Verification

```powershell
pytest tests/triage/ -q -v
```

Verify triage tests still pass — these test the same backend functions that the pipeline's tools call.

---

## 12. Acceptance Criteria Matrix

Phase 8 is considered complete when ALL of the following are true:

| # | Criterion | Evidence |
|---|---|---|
| AC-1 | Email triage pipeline executes end-to-end with pasted metadata | P8-E2E-1 passes |
| AC-2 | Email triage pipeline works with .msg file path | P8-E2E-2 passes |
| AC-3 | Pipeline stops at Step 2 failure (no job) and offers remediation | P8-FAIL-1 passes |
| AC-4 | Pipeline stops at Step 3 failure (no DIDs) and offers remediation | P8-FAIL-2 passes |
| AC-5 | Pipeline handles Step 4 failure (no keyword match) with remediation | P8-FAIL-3 passes |
| AC-6 | `maxSteps` cap works — produces partial report | P8-EDGE-1 passes |
| AC-7 | Stage 1 classifier detects pipeline queries automatically | P8-CLS-1 through P8-CLS-5 pass |
| AC-8 | Stage 1 classifier does NOT trigger pipeline for single-tool queries | P8-CLS-6 through P8-CLS-9 pass |
| AC-9 | All 6 Phase 7 regression tests pass | P8-REG-1 through P8-REG-7 pass |
| AC-10 | Progress streaming shows real-time step indicators | P8-STRM-1 passes |
| AC-11 | Backend errors don't crash the pipeline | P8-ERR-1 passes |
| AC-12 | `pytest tests/ -q` → 697+ passed, 0 failed | Terminal output |
| AC-13 | VSIX builds and installs without errors | `scripts/build.ps1` succeeds |
| AC-14 | Output channel logs show correct routing flow | P8 output channel verification |
| AC-15 | No JavaScript errors in Developer Tools during pipeline execution | Console check |
