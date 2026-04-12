# Phase 8: Executive Summary
## FRP Agent — ReAct Pipeline Orchestrator (Email Triage Deep Analysis)

**Document Version:** 1.0  
**Date:** March 2026  
**Status:** Planning  
**Phase Scope:** Add a ReAct (Reasoning + Acting) loop to the `@frp` chat participant for multi-step pipeline queries, starting with a comprehensive email triage pipeline  
**Prerequisites:** Phase 7 (Two-Stage Intent Routing) complete and verified

---

## Table of Contents
1. [Executive Overview](#executive-overview)  
2. [Business Context — The Pipeline in Your Head](#business-context--the-pipeline-in-your-head)  
3. [Phase 8 Objectives](#phase-8-objectives)  
4. [Architecture Overview — ReAct Loop](#architecture-overview--react-loop)  
5. [Architecture Decision Records](#architecture-decision-records)  
6. [What Already Exists](#what-already-exists)  
7. [What Phase 8 Adds](#what-phase-8-adds)  
8. [Risk Assessment](#risk-assessment)  
9. [Success Criteria](#success-criteria)  
10. [Dependencies & Prerequisites](#dependencies--prerequisites)  
11. [Estimated Effort](#estimated-effort)

---

## Executive Overview

### What Does Phase 8 Fix?

Phase 7 solves routing for **single-tool queries**: a user asks one question, the agent picks the right tool, returns the answer. But 50%+ of real-world usage follows a far more complex pattern:

> *"Here's an email. Tell me everything — is there a job for it? Which deals does it match? Was it processed? Did the template run succeed? If not, what went wrong? And if nothing matched, help me set it up."*

This requires **4–6 chained tool calls** with conditional branching at every step. The current architecture (Phase 7) picks ONE tool and stops. The user must manually ask follow-up questions to drive the chain — which defeats the purpose of having an intelligent agent.

Phase 8 adds a **ReAct (Reasoning + Acting) orchestrator** that enables the agent to autonomously execute multi-step pipelines: think about what to do, call a tool, observe the result, decide what to do next, call another tool, and so on until the full analysis is complete.

### What Is ReAct?

ReAct (Reasoning + Acting) is an industry-standard pattern used by LangChain agents, OpenAI Assistants, AutoGPT, and Microsoft Semantic Kernel. The loop is:

```
User prompt
     │
     ▼
┌─────────────────────────┐
│  LLM: THINK             │ ← "What do I need to find out first?"
│  → "I should look up    │
│     the sender domain   │
│     in our job configs"  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  ACT: call search_jobs  │ ← Execute a tool
│  → Result: Found job    │
│    CMBS_GreyCo (SID 296)│
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  LLM: THINK             │ ← "Job found. Now I need to check DIDs"
│  → "I should look up    │
│     CompanyID 296 in     │
│     tblExternalDIDRef"   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  ACT: call deal_lookup  │ ← Execute another tool
│  → Result: 5 DIDs found │
└──────────┬──────────────┘
           │
           ▼
      ... (continues until analysis is complete)
           │
           ▼
┌─────────────────────────┐
│  LLM: FINAL REPORT      │ ← Compile comprehensive analysis
│  → Detailed output to   │
│    user with findings,   │
│    recommendations, and  │
│    remediation offers    │
└─────────────────────────┘
```

The key insight: **the LLM decides at each step what to do next** based on what it observed from the previous step. This handles conditional branching naturally — if step 2 returns "no job found," the LLM reasons "I should suggest creating a new job" instead of proceeding to step 3.

### What Changed for Phase 7?

Phase 7 docs have been updated with **ReAct-readiness**:

- **ADR-8** added: Stage 1 output schema includes a `mode` field (`"single_tool"` or `"pipeline"`)
- Phase 7 code ignores `mode` (defaults to `"single_tool"`)
- Phase 8 activates `mode: "pipeline"` → enters the ReAct loop

This means Phase 8 requires **zero modifications to Phase 7 code**. It only adds new code.

---

## Business Context — The Pipeline in Your Head

You described the exact analysis pipeline you run mentally every time an email arrives. This section documents that pipeline precisely, because Phase 8's job is to encode it into the agent.

### The Email Triage Pipeline (6 Steps)

```
STEP 1: EMAIL ANALYSIS (LLM inference)
├── Input: .msg file OR email metadata pasted into chat
├── Extract: sender domain, mailbox/inbox, attachment filenames, subject line
├── LLM's task: Parse and structure the email metadata
└── Output: Structured email metadata for subsequent lookups

STEP 2: JOB MATCHING (Tool call → search_jobs or triage_match)
├── Input: sender domain from Step 1
├── Action: Search SQLite job cache for a job monitoring this sender
├── IF NOT FOUND:
│   ├── Report: "No matching job found for sender domain X"
│   └── Offer: "Do you want to create a new job for this sender?"
│         → If user says yes, gather suggested config from email → create_job
├── IF FOUND:
│   ├── Report: job name, ServicerID, scrubber type
│   └── Continue to Step 3 with ServicerID
└── Output: job name + ServicerID (or remediation offer)

STEP 3: DID LOOKUP (Tool call → deal_lookup)
├── Input: ServicerID from Step 2 (used as CompanyID)
├── Action: Query tblExternalDIDRef WHERE CompanyID = ServicerID
├── IF NO DIDs FOUND:
│   ├── Report: "Job found but no DIDs configured"
│   └── Offer: "Do you want to set up new DIDs for this job?"
├── IF DIDs FOUND:
│   └── Continue to Step 4 with DID list + ImportDID keywords
└── Output: List of DIDs with their ImportDID keywords (or remediation offer)

STEP 4: DID KEYWORD MATCHING (LLM inference)
├── Input: DID keywords from Step 3 + email subject from Step 1
├── Action: LLM matches ImportDID keywords against email subject line
│   to determine which specific DID this email corresponds to
├── IF NO KEYWORD MATCH:
│   ├── Report: "DIDs exist but no keyword matches email subject: '<subject>'"
│   ├── Show: existing keywords vs subject line
│   └── Offer: "Do you want to add a new keyword to an existing DID
│         so this email subject is picked up?"
├── IF KEYWORD MATCHED:
│   ├── Report: "Email subject matches DID '<matched_DID>' via keyword '<keyword>'"
│   └── Continue to Step 5 with matched DID
└── Output: Matched DID name (or remediation offer)

STEP 5: LOG VERIFICATION (Tool call → daily_summary/job_health/did_failures)
├── Input: job name + DID + approximate email date from Step 1
├── Action: Query application logs for this email's processing
├── IF JOB MATCHING FAILED IN LOGS:
│   ├── Report: log details of what failed and why
│   └── Ask: "What more should we investigate?"
├── IF DID MATCHING FAILED IN LOGS:
│   ├── Report: DID failure details from logs
│   └── Offer: remediation based on failure mode
├── IF PROCESSED SUCCESSFULLY IN LOGS:
│   └── Continue to Step 6 with processing confirmation
└── Output: Log evidence of processing (or failure details + remediation)

STEP 6: TEMPLATE STAGING VERIFICATION (Tool call → staging_search/template_status)
├── Input: job/DID/template identifiers from previous steps
├── Action: Query tblTemplateStaging for template run results
├── IF TEMPLATE NEVER QUEUED:
│   └── Report: "Template was supposed to queue but never did"
├── IF TEMPLATE QUEUED BUT WAITING:
│   ├── Check: StartTime and EndTime are both NULL
│   └── Report: "Template is in queue but hasn't been processed yet"
├── IF TEMPLATE FAILED:
│   ├── Check: Comment column for error result
│   └── Report: "Template failed with error: <Comment>"
├── IF TEMPLATE SUCCEEDED:
│   └── Report: "Template processed successfully" + show run details
└── Output: Template processing status + result details

FINAL: COMPREHENSIVE REPORT (LLM inference)
├── Compile everything:
│   ├── Email metadata summary
│   ├── Job match result (found/not found)
│   ├── DID lookup result (DIDs found/not found, keyword match/no match)
│   ├── Log verification result (processed/failed/not found)
│   ├── Template staging result (queued/waiting/failed/success)
│   └── Recommended next steps
├── At each step where something failed or was not found:
│   ├── Explain WHAT was tried
│   ├── Explain WHAT the result was
│   └── OFFER specific remediation action
└── Format: Detailed, structured markdown with clear sections
```

### Why This Can't Be a Single Tool Call

The current `triage_verify` backend command (`TriageAnalyzer.verify()`) already performs a simplified version of this pipeline. But it has critical limitations:

1. **No LLM reasoning between steps.** The backend runs each step unconditionally and returns a flat JSON result. It can't reason: "The keyword didn't match — I should try fuzzy matching" or "The log shows a different sender domain — maybe the email was forwarded."

2. **No remediation offers.** The backend returns data. It doesn't say "do you want to create a job?" or "do you want to add a keyword?" That requires LLM reasoning + user interaction.

3. **No streaming feedback.** The backend returns the full result at the end. The user sees nothing until the complete analysis is done. The ReAct loop can stream progress: "Found job CMBS_GreyCo... now checking DIDs... found 5 DIDs... matching keywords against subject..."

4. **No conditional branching.** The backend always runs all steps. The ReAct loop stops and offers remediation when a step fails, rather than plowing through to steps that depend on the failed step's output.

5. **No email content analysis.** The backend can parse a .msg file from disk, but the user might paste email metadata directly into the chat. The ReAct loop handles both: .msg file path OR pasted text.

---

## Phase 8 Objectives

| ID | Objective | Deliverable |
|---|---|---|
| P8-1 | Build the ReAct loop orchestrator | New `reactLoop()` function in `participant.js` that iteratively calls LLM + tools |
| P8-2 | Define the Email Triage Pipeline Playbook | System prompt (playbook) encoding the 6-step pipeline with conditional branching rules |
| P8-3 | Activate `mode: "pipeline"` in Stage 1 classifier | Update `classifyIntent()` prompt to recognize multi-step queries and return `mode: "pipeline"` |
| P8-4 | Stream progress to user during pipeline execution | Each ReAct step reports progress via `stream.progress()` and intermediate `stream.markdown()` |
| P8-5 | Support both .msg file path and pasted email metadata | Pipeline handles `"analyze email at C:\emails\report.msg"` AND `"this email came from reports@fay.com, subject: Monthly Report Jan 2026, attachment: FayReport.xlsx"` |
| P8-6 | Offer remediation at failure points | When a step fails (no job, no DID, no keyword match), the agent offers a specific action (create job, add DID keyword) |
| P8-7 | Compile comprehensive final report | At the end of the pipeline, produce a structured markdown report covering every step, what worked, what didn't, and what the user can do next |
| P8-8 | Cap the loop to prevent runaway | Maximum iteration count (8 steps default) with graceful termination |

---

## Architecture Overview — ReAct Loop

### How It Fits with Phase 7

```
User prompt → @frp
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  STAGE 1: classifyIntent()  (Phase 7 — unchanged)       │
│                                                          │
│  Returns: { category: "system_admin", mode: "pipeline" } │
│           OR { category: "job_config", mode: "single_tool" } │
└────────┬──────────────────────────────┬──────────────────┘
         │                              │
    mode: "single_tool"           mode: "pipeline"
         │                              │
         ▼                              ▼
┌──────────────────┐    ┌──────────────────────────────────┐
│ Stage 2: pick     │    │  ReAct Orchestrator (Phase 8)    │
│ one tool (Phase 7)│    │                                  │
│ → execute → done  │    │  THINK → ACT → OBSERVE           │
└──────────────────┘    │    ▲                  │           │
                        │    └──────────────────┘           │
                        │    (loop until done or max steps) │
                        │                                   │
                        │  → Comprehensive report           │
                        └──────────────────────────────────┘
```

### The ReAct Loop — Internal Flow

```
reactLoop(userPrompt, playbook, tools, model, stream)
     │
     ├── messages = [systemMessage(playbook), userMessage(prompt)]
     │
     ├── ITERATION 1:
     │   ├── LLM sendRequest(messages, {tools}) → tool call: search_jobs(sender_domain)
     │   ├── stream.progress("Searching for matching job...")
     │   ├── Execute: search_jobs → result
     │   ├── Append: assistantToolCall + toolResult to messages
     │   └── CONTINUE (tool call means "not done yet")
     │
     ├── ITERATION 2:
     │   ├── LLM sendRequest(messages, {tools}) → tool call: deal_lookup(companyID)
     │   ├── stream.progress("Looking up deals for ServicerID 296...")
     │   ├── Execute: deal_lookup → result (5 DIDs found)
     │   ├── Append to messages
     │   └── CONTINUE
     │
     ├── ITERATION 3:
     │   ├── LLM sendRequest(messages, {tools}) → NO tool call → text response
     │   │   (LLM decides it can now do keyword matching via reasoning, no tool needed)
     │   ├── OR: LLM sendRequest → tool call: staging_search
     │   ├── ...
     │   └── CONTINUE or FINAL
     │
     ├── ... (up to maxSteps iterations)
     │
     └── FINAL:
         ├── LLM returns text response (no tool call) = final report
         ├── stream.markdown(finalReport)
         └── Return with follow-up suggestions
```

### Key Design Properties

1. **The loop stops when the LLM returns text instead of a tool call.** This is the natural "I'm done thinking, here's my final answer" signal in the VS Code LLM API.

2. **The playbook guides but doesn't constrain.** The system prompt tells the LLM the 6-step pipeline and the branching rules, but the LLM can deviate if the data suggests a different path. For example, if the email subject contains a unique deal identifier, the LLM might skip Step 2 (job matching) and go directly to Step 3 (DID lookup).

3. **Each iteration has all previous context.** The messages array accumulates: the original prompt, every tool call made, every tool result received. The LLM sees the full history of what it's done and what the results were.

4. **Tools are a curated subset.** The ReAct loop doesn't receive all 36 tools — it gets only the tools relevant to the pipeline (e.g., `search_jobs`, `deal_lookup`, `staging_search`, `job_health`, `did_failures`, `daily_summary`, `template_status`). This keeps the tool space manageable.

5. **Progress is streamed.** Unlike a single tool call that blocks until done, the ReAct loop streams status updates: "Found job CMBS_GreyCo (ServicerID 296)... Now checking deal coverage..."

---

## Architecture Decision Records

### ADR-1: ReAct Loop Over Fixed Pipeline Steps

**Context:** We could implement the email triage as a hard-coded 6-step function (no LLM reasoning between steps) or as a ReAct loop (LLM decides next step based on previous results).  
**Decision:** ReAct loop. The LLM decides what to do next at each step.  
**Why:**
- **Conditional branching is natural.** When Step 2 returns "no job found," the LLM reasons "I should offer to create a job" instead of proceeding to Step 3 which depends on Step 2's output.
- **Fuzzy matching.** The LLM can reason: "The keyword didn't match exactly, but 'CMLTI 2014-A' is very close to 'CMLTI 2014A' — this is likely the same deal."
- **Extensibility.** Adding a new pipeline (e.g., "full audit of servicer 296") means adding a new playbook, not writing new hard-coded logic.
- **Error recovery.** If a tool call fails, the LLM can try an alternative approach.

**Consequence:** Each pipeline query makes 3–7 LLM calls (one per ReAct step). This is slower than a single tool call (~3–10 seconds total) but produces dramatically more comprehensive results.  
**Mitigation:** Progress streaming keeps the user informed. Each step takes ~500ms–1s for LLM + tool execution.

### ADR-2: Playbook-Driven, Not Hard-Coded

**Context:** The email triage pipeline could be implemented as procedural JavaScript code (if/else chain calling tools in sequence) or as an LLM-driven loop guided by a playbook prompt.  
**Decision:** Playbook-driven. The pipeline knowledge lives in a system prompt (the "playbook"), not in JavaScript if/else logic.  
**Why:**
- **Your domain knowledge → playbook text.** The pipeline in your head translates directly to a structured prompt. No complex code to maintain.
- **LLM handles ambiguity.** "Is `reports@fay.com` the same as `fayservicing@fay.com`?" — procedural code would need explicit rules. The LLM reasons about it naturally.
- **New pipelines = new playbooks.** Adding a "full servicer audit" pipeline means writing a new playbook prompt. The `reactLoop()` function is generic and reusable.

**Consequence:** Pipeline behavior depends on LLM prompt quality. The playbook must be precise and tested.  
**Mitigation:** The playbook includes explicit decision rules, not vague instructions. Each step has clear "IF found / IF not found" branches documented.

### ADR-3: Curated Tool Subset Per Pipeline

**Context:** Should the ReAct loop receive all 36 tools or a curated subset?  
**Decision:** Curated subset. The email triage pipeline gets ~10 tools. Other future pipelines get their own tool subsets.  
**Why:**
- 36 tools in a ReAct loop means the LLM could wander — calling `rollback` or `xml_diff` during email triage makes no sense.
- A curated subset keeps the LLM focused on the relevant tools.
- The tool subset is defined in the pipeline configuration, not hard-coded.

**Consequence:** Each pipeline definition includes a `tools` array listing which tools the ReAct loop can use.

### ADR-4: Maximum Iteration Cap

**Context:** An unrestricted ReAct loop could theoretically run forever (LLM keeps calling tools without producing a final answer).  
**Decision:** Cap at 8 iterations (tool calls). If the loop reaches 8 without the LLM producing a final text response, force termination and compile a partial report from collected results.  
**Why:** 8 iterations covers the 6-step pipeline plus 2 extra for error recovery or alternative paths. In practice, most runs complete in 4–6 iterations.  
**Consequence:** Edge cases where the LLM needs more than 8 steps will produce a partial report. The cap can be adjusted per pipeline.

### ADR-5: Existing Backend Triage vs ReAct Loop

**Context:** The backend already has `TriageAnalyzer.verify()` which does a simplified version of the pipeline in one CLI call. Should Phase 8 call `triage_verify` as a single tool in the ReAct loop, or call individual tools (search_jobs, deal_lookup, etc.) as separate steps?  
**Decision:** Call individual tools as separate steps. Do NOT use `triage_verify` as a single tool in the pipeline.  
**Why:**
- `triage_verify` runs all steps unconditionally and returns a flat result. The ReAct loop needs to reason between steps.
- `triage_verify` can't offer remediation between steps (it's a backend function, not an interactive agent).
- `triage_verify` requires a .msg file path on disk. The ReAct loop also handles pasted email metadata.
- The individual tools (`search_jobs`, `deal_lookup`, `staging_search`) already exist and are well-tested.

**Consequence:** The ReAct loop orchestrates the same backend capabilities but with LLM-driven reasoning between steps. `triage_verify` remains available for the slash-command `/triage verify` use case (quick, non-interactive).

### ADR-6: Support Pasted Email Metadata (No .msg File Required)

**Context:** The user might not always have a .msg file to provide. They might paste email details into the chat: sender, subject, attachment names.  
**Decision:** The pipeline handles both input modes:
1. `.msg file path` → Pipeline calls `triage_verify` or `triage_match` to parse the file, then proceeds with ReAct reasoning
2. `Pasted metadata` → The LLM extracts sender/subject/attachments from the user's text, then proceeds with the same tool calls

**Why:** In practice, users often don't have .msg files readily accessible. They'll paste email headers or forward text. The agent should be smart enough to work with whatever input is available.  
**Consequence:** Step 1 of the pipeline is LLM inference (extract metadata), not necessarily a tool call. The LLM decides if it has enough info or if it needs to parse a .msg file.

### ADR-7: Remediation Offers as Follow-Up Prompts

**Context:** When a step fails (no job found, no DID match), the agent should offer remediation. How should this be presented?  
**Decision:** Remediation offers are presented as VS Code chat follow-up buttons AND as text in the report. The user can click a follow-up button to execute the remediation (e.g., "Create new job for this sender").  
**Why:** Follow-up buttons are discoverable and easy to click. The text in the report provides context for why the remediation is needed.  
**Consequence:** The final report includes both textual recommendations AND `followUps` array entries. If the user clicks a follow-up, it enters the standard Phase 7 routing (single-tool call to `create_job` or `edit_job`).

---

## What Already Exists

Phase 8 builds on extensive existing infrastructure. This section catalogs what's already built and tested.

### Backend Triage Module (`backend/triage/`)

| Component | What It Does | Phase 8 Usage |
|---|---|---|
| `MsgParser.parse(path)` | Parses .msg file → `EmailInfo` (sender, subject, date, attachments) | Used when user provides a .msg file path |
| `TriageMatcher.match(email, jobs)` | Matches email against all job configs → `MatchResult[]` | Used indirectly via `triage_match` CLI command |
| `TriageAnalyzer.verify(path)` | Full pipeline: parse → match → DID → logs → staging | NOT used directly; ReAct loop calls individual tools instead |
| `TriageAnalyzer.match_only()` | Quick match by sender/subject text | Used via `triage_match` CLI command |
| `TriageAnalyzer.analyze_new(path)` | Suggest template for unmatched email | Used via `triage_new` CLI command for remediation |

### Existing Tools Usable in the Pipeline

| Tool | What It Does | Pipeline Step |
|---|---|---|
| `search_jobs` | Search jobs by attributes (sender, name, etc.) | Step 2: Find job by sender domain |
| `triage_email` | Match email against jobs via `triage_match` | Step 2: Alternative to search_jobs |
| `deal_lookup` | Query tblExternalDIDRef by CompanyID/DID | Step 3: Find DIDs for job's ServicerID |
| `job_detail` | Full job config + linked deals | Step 2/3: Get ServicerID + deal cross-ref |
| `staging_search` | Search tblTemplateStaging | Step 6: Check template run results |
| `template_status` | Template processing status | Step 6: Check if template was queued/run |
| `daily_summary` | Daily log summary | Step 5: Check log activity |
| `job_health` | Job health from logs | Step 5: Check job execution health |
| `did_failures` | DID lookup failures from logs | Step 5: Check if DID matching failed |
| `create_job` | Create a new job from template | Remediation: create job for unmatched sender |

### Data Models

| Model | Fields | Usage |
|---|---|---|
| `EmailInfo` | sender, sender_name, subject, date, to, cc, body_preview, attachment_names, file_path | Step 1 output (parsed email data) |
| `MatchResult` | job_name, xml_type, match_type, match_confidence, servicer_id, matched_filter | Step 2 output (job match) |
| `DIDMatch` | did, import_did, matched_in, matched_value | Step 4 output (keyword match) |
| `TriageResult` | email_info, matches, deals, did_matches, log_summary, template_status, confidence | Final assembly (when using triage_verify) |

### Extension-Side Handlers

| Handler | What It Does | Phase 8 Usage |
|---|---|---|
| `handleTriageCommand()` | Routes `/triage verify\|match\|new` subcommands | Remains for slash-command usage; ReAct loop bypasses this |
| `handleJobsSearch()` | Executes search_jobs tool call | Called by ReAct loop via `executeToolCall('search_jobs', ...)` |
| `handleDealLookup()` | Executes deal_lookup tool call | Called by ReAct loop via `executeToolCall('deal_lookup', ...)` |
| `handleStagingSearch()` | Executes staging_search tool call | Called by ReAct loop via `executeToolCall('staging_search', ...)` |
| `backendCall()` | Calls Python backend CLI | Used by all handlers; unchanged |

---

## What Phase 8 Adds

### New Code Elements (All Within `participant.js`)

| Element | Type | Purpose |
|---|---|---|
| `PIPELINE_DEFINITIONS` | `const Object` | Maps pipeline name → { playbook prompt, tool subset, maxSteps } |
| `EMAIL_TRIAGE_PLAYBOOK` | `const string` | The 6-step pipeline playbook system prompt |
| `EMAIL_TRIAGE_TOOLS` | `const string[]` | Curated tool subset for email triage (~10 tools) |
| `reactLoop()` | `async function` | Generic ReAct orchestrator: THINK → ACT → OBSERVE loop |
| `executePipelineTool()` | `async function` | Tool execution within the ReAct loop — calls `executeToolCall()` but returns raw JSON (not streamed markdown) |
| `compilePipelineReport()` | `function` | Assembles collected step results into a structured final report |
| Stage 1 classifier update | Prompt text | Updated classifier prompt to recognize pipeline triggers and return `mode: "pipeline"` |
| `routeWithToolCalling()` update | Code branch | New `if (mode === 'pipeline')` branch after Stage 1 → enters `reactLoop()` |

### Modified Code Elements

| Element | Change |
|---|---|
| `buildClassifierPrompt()` | Add pipeline trigger definitions to the classifier prompt |
| `classifyIntent()` | Parse and return `mode` field (currently ignored in Phase 7) |
| `routeWithToolCalling()` | Add `mode === 'pipeline'` branch between Stage 1 and Stage 2 |

### What Does NOT Change

| Element | Why Untouched |
|---|---|
| `FRP_TOOLS` array | No new tools; ReAct uses existing tools |
| `executeToolCall()` switch | Unchanged; ReAct calls it for each tool execution |
| All 30+ handler functions | Unchanged; ReAct calls them via executeToolCall() |
| All backend Python code | Zero changes |
| All CLI commands | Zero changes |
| All 697+ tests | Zero changes; ReAct is extension-only |
| Stage 2 `routeWithinCategory()` | Unchanged; used for single_tool mode (not pipeline) |
| `routeWithAllTools()` fallback | Unchanged; still available as fallback |

---

## Risk Assessment

| # | Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| R-1 | ReAct loop runs away (too many iterations) | High | Low | Hard cap at 8 iterations; partial report on cap hit; each iteration logged |
| R-2 | LLM calls wrong tool in loop | Medium | Medium | Curated tool subset (~10, not 36); playbook explicitly guides which tools to use at each step |
| R-3 | Latency for full pipeline (3–10s) | Medium | High | Progress streaming keeps user informed; each step ~500ms–1s; accepted trade-off for comprehensive analysis |
| R-4 | LLM hallucinates tool results | Medium | Low | Tool results are real data from backend; LLM can only reason about actual results, not fabricate them |
| R-5 | Pasted email metadata is incomplete | Low | Medium | Playbook instructs LLM to ask for missing info ("I need the sender domain to search for a matching job. Can you provide it?") |
| R-6 | Remediation follow-up doesn't route correctly | Medium | Low | Remediation follow-ups use standard Phase 7 routing (single-tool); already tested |
| R-7 | Pipeline produces overwhelming output | Low | Medium | Report is structured with collapsible sections; summary at top, details below |
| R-8 | Token limit exceeded from accumulated context | Medium | Low | Each tool result is summarized (not full JSON) when appended to messages; large result truncation |

---

## Success Criteria

| # | Criterion | Measurement |
|---|---|---|
| SC-1 | Email triage with .msg file works end-to-end | Provide a .msg file → agent extracts metadata, matches job, checks DIDs, verifies logs, checks template staging, produces comprehensive report |
| SC-2 | Email triage with pasted metadata works | Paste sender/subject/attachment info → same pipeline, same quality of report |
| SC-3 | No-job-found remediation works | Email with unknown sender → agent reports "no matching job" + offers "create new job" follow-up button |
| SC-4 | No-DID-match remediation works | Email matches job but subject doesn't match any DID keywords → agent reports mismatch + offers "add keyword" follow-up |
| SC-5 | Template staging verification works | Agent checks tblTemplateStaging: reports never-queued, waiting-in-queue, failed (with Comment), or succeeded |
| SC-6 | Progress streaming works | User sees step-by-step progress: "Found job...", "Checking DIDs...", "Verifying logs..." |
| SC-7 | Loop cap works | Force a scenario where loop hits max iterations → partial report generated, no hang |
| SC-8 | Single-tool queries unaffected | Phase 7 queries (list jobs, show details, etc.) still work identically via Stage 2 |
| SC-9 | Comprehensive report quality | Report includes: email metadata, job match details, DID coverage, keyword match analysis, log evidence, template status, recommendations |
| SC-10 | All 697+ existing tests pass | `pytest tests/ -q` → 697 passed, 0 failed |

---

## Dependencies & Prerequisites

| # | Prerequisite | Verification |
|---|---|---|
| PG-1 | Phase 7 complete and verified | All Phase 7 tests pass; two-stage routing works; `mode` field in Stage 1 output |
| PG-2 | Stage 1 classifier returns valid `mode` field | `classifyIntent()` parses `mode` from JSON response |
| PG-3 | All existing tools work via `executeToolCall()` | Verified during Phase 7 QA |
| PG-4 | Backend triage module functional | `triage_verify`, `triage_match`, `triage_new` CLI commands work |
| PG-5 | SQLite job cache populated | `search_jobs` returns results from SQLite index |
| PG-6 | MySQL tblExternalDIDRef accessible | `deal_lookup` returns deal data |
| PG-7 | Log index functional | `daily_summary`, `job_health`, `did_failures` return log data |
| PG-8 | tblTemplateStaging accessible | `staging_search`, `template_status` return staging data |

---

## Estimated Effort

| Sprint | Name | Est. Hours | Files Changed |
|---|---|---|---|
| S1 | ReAct loop function + pipeline infrastructure | 3–4h | 1 (participant.js) |
| S2 | Email triage playbook + tool subset + classifier update | 2–3h | 1 (participant.js) |
| S3 | Progress streaming + report compilation + remediation | 2–3h | 1 (participant.js) |
| S4 | Testing + edge cases + polish | 2–3h | 1 (participant.js) |
| **Total** | | **9–13h** | **1 file** |

All changes are in a single file: `extension/chat/participant.js`. No backend changes. No new dependencies. No test file changes.
