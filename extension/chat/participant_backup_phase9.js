const vscode = require('vscode');
const { backendCall } = require('../copilot/tool');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PARTICIPANT_ID = 'frp-agent.assistant';

const SYSTEM_PROMPT = `You are the FRP Agent — a specialist assistant for the File Reception Portal.

Your domain covers:
• Email & SFTP monitoring jobs (Settings.xml configurations)
• Deal coverage, servicer dossiers, and DID mapping (tblExternalDIDRef)
• Application logs (EmailMonitor, SFTP monitor)
• Deployment of Settings.xml changes with backup/restore

Formatting rules (CRITICAL):
1. Answer ONLY about FRP-related topics. Politely decline unrelated questions.
2. When data is provided in <data>…</data> tags, base your answer on that data.
3. Format responses with Markdown: tables, bold, code blocks as appropriate.
4. For validation results, use ✅ for pass and ❌ for fail.
5. Be concise but thorough. Offer follow-up suggestions when useful.
6. If data is empty or missing, say so clearly — never fabricate records.
7. NEVER show raw JSON snippets or source data to the user. Present all data as formatted Markdown tables or bullet lists.
8. File paths MUST be shown exactly as-is inside backticks. Preserve every backslash and curly bracket — e.g. \`M:\\{DealFolder}\\Data\\{YYYY}\\{M}\\EmailExtract\`. NEVER approximate, strip, or escape path characters.
9. Omit any field whose value is null or empty — do not show "Day Adjust: null" or similar.

Data model rules (CRITICAL — do not violate):
• Jobs do NOT have a DealName field. Never fabricate a "DealName" column. The job↔deal relationship is: Job.ServicerID = tblExternalDIDRef.CompanyID.
• Jobs do NOT have a Subject field. Subject/filename keywords come from tblExternalDIDRef.ImportDID and are deal-specific, not job-specific.
• The field called "scrubber" (or "template") is the automation workflow that processes the downloaded file. Always label it "Scrubber" in output.
• "match_mode" describes HOW the job identifies relevant emails. Explain it in plain English:
  - "Subject" → "This job detects files by matching a keyword in the email subject line."
  - "Filename" → "This job detects files by matching the attachment filename."
  - "Both" → "This job matches on both email subject line and attachment filename."
• When listing multiple jobs, use these columns: JobName, Sender, ServicerID, Scrubber, MatchMode, SavePath.
• If groups_by_scrubber or groups_by_source are provided, show a brief summary before the table.
• For large result sets (>20 jobs), show the summary groups and the table — do NOT truncate rows.
• When showing linked deals from tblExternalDIDRef, include DID (deal name), ImportDID (the keyword), and CompanyID.
  ImportDID is the critical keyword the system searches for in incoming emails/files.

Processing pipeline (tblTemplateStaging):
• tblTemplateStaging records every file the system has processed — when, which template/scrubber ran, success/failure, duration, and the source filepath.
• Key fields: TemplateProcessID, TemplateName (scrubber), DID, ServicerID, FilePath, ProcessStarted, ProcessCompleted, ProcessDuration, QueuedBy, Status.
• A "manual queue" means QueuedBy contains a person's name (not 'EmailMonitor' or 'SFTP').
• The three-table pipeline is: Settings.xml (configuration) → tblExternalDIDRef (deal mapping) → tblTemplateStaging (execution history).
• When showing processing records, use columns: TemplateName, DID, Status, ProcessStarted, Duration, FilePath.
• For failure analysis, group by error pattern and show affected templates/deals.
• For pipeline views, show all three layers and highlight gaps (configured but never processed, or processed but not configured).`;

// ---------------------------------------------------------------------------
// Domain Knowledge — injected into the routing prompt so the LLM can reason
// about tool selection based on data model understanding, not memorized rules.
// ---------------------------------------------------------------------------

const DOMAIN_KNOWLEDGE = `## FRP Data Model Reference

### Three-Table Pipeline
The FRP system has three interconnected data layers:

1. **Settings.xml** — Job Configuration Layer
   - Email/SFTP monitoring job definitions (one XML element per job)
   - Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation

2. **tblExternalDIDRef** — Deal Reference Layer
   - Maps CompanyID → DealID (DID) + ImportDID (the keyword the system searches for in emails/files)
   - Key relationship: Job.ServicerID = tblExternalDIDRef.CompanyID

3. **tblTemplateStaging** — Processing Execution History
   - Every file the system has ever processed: timestamp, scrubber/template, success/failure, duration, filepath
   - Relationships: TemplateName = job's scrubber; DID/ServicerID link to deals

### Cross-Reference Chains (how tables connect)
- Job→Deals: ServicerID → tblExternalDIDRef.CompanyID → all deals
- Deal→Jobs: CompanyID → Settings.xml jobs that use it as ServicerID
- Job→Processing: processing history by scrubber/TemplateName or ServicerID
- Deal→Processing: processing history by DID
- Full pipeline: all three layers combined for one entity`;

// ---------------------------------------------------------------------------
// Email Triage Pipeline — Playbook (system prompt for ReAct loop)
// ---------------------------------------------------------------------------

const EMAIL_TRIAGE_PLAYBOOK = `You are the FRP Email Triage Analyst. Your job is to analyze an incoming email and trace it through the full FRP processing pipeline: job configuration → deal mapping → log verification → template staging.

## Domain Model (Condensed)

FRP has a three-table pipeline:
- **Settings.xml** — email/SFTP monitoring jobs. Each job has a ServicerID and Filters (sender, subject patterns).
- **tblExternalDIDRef** — deal mapping table. Columns: ItemID, DID, ImportDID (keyword used for matching), CompanyID (= ServicerID in Settings.xml). No DealName or Active flag.
- **tblTemplateStaging** — template processing results. Key columns: TemplateName, FilePath, DID, Dt, StartTime, EndTime, ResultCode, Comments, ServicerID, SourceProcess, Job, DataSource.

ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef). ImportDID keywords are matched against email subject lines to identify which specific deal an email corresponds to.

## Your Analysis Pipeline

Follow these steps IN ORDER. After each tool call, review the result and decide what to do next. If a step fails, do NOT skip to a step that depends on it.

### Step 1: Email Metadata
Extract from the user's message: sender (email/domain), subject line, attachment filenames, approximate date.
- If the user provides a .msg file path, call **triage_email** with { prompt: "verify <filepath>" } — e.g., { prompt: "verify C:\\\\Users\\\\...\\\\test_emails\\\\report.msg" }. The file will be in the user's test_emails workspace folder.
- If the user pastes metadata inline, extract what is available and proceed.
- If critical info is missing (e.g., no sender), note what is missing but continue with what you have.

### Step 2: Job Match
Find which FRP job monitors emails from this sender.
- Call **search_jobs** with the sender domain as query.
- If FOUND: Record the job name, ServicerID, scrubber type. Continue to Step 3.
- If NOT FOUND: Report "No matching job found for sender domain." Offer: "Would you like to create a new job for this sender?" STOP here — do not continue to Step 3.
- If MULTIPLE matches: List all matches. Pick the best match (highest relevance). Continue with that match.

### Step 3: DID Lookup
Find all deals mapped to this job's ServicerID.
- Call **deal_lookup** with the ServicerID from Step 2 (as CompanyID).
- If DIDs FOUND: List the count and ImportDID keywords. Continue to Step 4.
- If NO DIDs: Report "Job found but no DIDs configured for CompanyID <id>." Offer: "Would you like to set up deal mappings for this job?" STOP here for DID-dependent steps.

### Step 4: Keyword Matching (No Tool Call)
Match ImportDID keywords against the email subject from Step 1.
- Compare each ImportDID keyword against the email subject line (case-insensitive substring match).
- If KEYWORD MATCHED: Report which keyword matched and which DID it belongs to. Continue to Step 5.
- If NO MATCH: Report "DIDs exist but no ImportDID keyword matches email subject." Show existing keywords vs. the subject. Offer: "Would you like to add a keyword to an existing DID?"
- If MULTIPLE MATCHES: List all matching keywords. Note potential collision.

### Step 5: Log Verification
Check application logs for evidence of processing. Logs record **individual email events** — each email gets its own processing lines.
- Call **daily_summary** (shows individual email events per day — look for lines matching the sender or subject from Step 1).
- Call **job_health** with the job name to check recent execution health.
- Call **did_failures** if the email may have failed DID matching (rolling window, max 60 days, most recent first).
- Call **deal_activity** with the matched DID from Step 4 to see DID-specific log activity.

Key log event patterns to look for:
- Processing: <subject> + From: <sender> — confirms the email was seen by the monitor
- Matched email [<subject>] to [<parser>] parser — the email was recognized by a configured job
- Did not find DID mapping for [<filename>]... — DID match failure (the email was seen but no DID keyword matched)
- Queue file [<filename>] for [<template>] template — the email was successfully queued for template processing
- HashiVault: Retrieved secret — normal operational line, not an issue

For SFTP logs:
- Checking SFTP folder for <job_name> (<folder>)... followed by Found <N> file(s) — SFTP scan event
- Matched DID to [<DID>] and updated save location — SFTP file matched a DID
- Did not find DID mapping for [<filename>]... — same DID failure pattern as email

### Step 6: Template Staging
Check tblTemplateStaging for template run results.
- Call **staging_search** or **template_status** using job/deal identifiers.
- Match rows by ServicerID + SourceProcess + Job + DataSource. DataSource format: for email = <sender_email> <email_subject>; for SFTP = SFTPMonitor: <folder_path> (e.g., SFTPMonitor: M:\\\\!Sweeps\\\\SPS\\\\In).

Interpret StartTime / EndTime / ResultCode / Comments as follows:
| State | StartTime | EndTime | ResultCode | Comments |
|---|---|---|---|---|
| **Never queued** | *(no row found)* | — | — | — |
| **Queued, not started** | NULL | NULL | — | — |
| **In progress** | NOT NULL | NULL | — | — |
| **Success** | NOT NULL | NOT NULL | 0 | "Ok" |
| **Failed** | NOT NULL | NOT NULL | 1 | error message detail |

## Reporting Rules
When you have enough information (either completed all steps or hit a dead end):
1. Return your FINAL REPORT as text — do NOT call another tool.
2. Use structured markdown: headers, tables, status indicators.
3. Show what you checked at each step and what the result was.
4. For each failure, offer a specific remediation action.
5. Include a Summary section at the end with overall assessment.
6. Add a Data Sources section listing which tools/tables were queried.

## Important Rules
- Call ONE tool at a time. Review the result before deciding the next step.
- If a step fails, do NOT proceed to steps that depend on its output.
- Steps 5 and 6 can still run even if Step 4 fails (logs/staging may show activity at the job level).
- When you are DONE, produce your final report as text. This signals the loop to end.
- Keep intermediate reasoning brief. Save detail for the final report.`;

// ---------------------------------------------------------------------------
// General Reasoning Playbook — use-case-agnostic multi-step reasoning
// ---------------------------------------------------------------------------

const GENERAL_REASONING_PLAYBOOK = `You are the FRP System Analyst. You solve complex questions about the FRP (File Reception Portal) system by reasoning step-by-step and calling tools as needed.

## Domain Model

FRP has a three-table pipeline:
- **Settings.xml** — email/SFTP monitoring jobs. Each job has a JobName, ServicerID, Scrubber (template name), Sender, and Filters (subject patterns).
- **tblExternalDIDRef** — deal mapping table. Columns: ItemID, DID, ImportDID (keyword used for matching), CompanyID (= ServicerID in Settings.xml). No DealName or Active flag.
- **tblTemplateStaging** — template processing results. Key columns: TemplateName, FilePath, DID, Dt, StartTime, EndTime, ResultCode, Comments, ServicerID, SourceProcess, Job, DataSource.

Cross-references: ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef). ImportDID keywords are matched against email subject lines to identify which specific deal an email corresponds to.

Application logs (EmailMonitor/SFTP logs) are indexed in SQLite and provide: daily summaries, DID failure events, job health metrics, deal-level activity, volume trends, and performance rankings.

## Your Approach

1. Break the user's question into sub-questions. Identify which data source answers each.
2. Call ONE tool at a time. Review the result before deciding the next step.
3. Use output from earlier steps to inform later tool parameters (e.g., get ServicerID from job_detail → use it in deal_lookup).
4. If a tool returns no data or errors, note it and try an alternative approach or skip that sub-question.
5. Do NOT call the same tool with identical parameters twice.
6. When you have enough information to fully answer the user's question, produce your FINAL ANSWER as text — do not call another tool.

## Reporting

- Use markdown: headers, tables, status indicators (✅ ❌ ⚠️).
- Structure your answer around the user's original question.
- For each finding, show what data source confirmed it.
- If something is missing or broken, suggest a specific remediation.
- Keep intermediate reasoning brief. Save detail for the final report.

## Parameter Extraction Rules
- ALWAYS resolve anaphoric references to the explicit named entity in the CURRENT message.
- "this job" / "it" / "the job" = the specific job name mentioned earlier in the same message.
- "this deal" / "the deal" = the specific DID/deal name from the same message.
- "this servicer" = the specific ServicerID or servicer name from the same message.
- Extract ONLY the identifier, not surrounding labels: "CompanyID 296" → "296", "job CMBS_GreyCo" → "CMBS_GreyCo".

## Common Cross-Layer Patterns (use these before inventing a sequence)
- "job X AND its linked deals/keywords" → call job_detail(X) ONLY. It returns job config AND linked deals in ONE call. Do NOT call deal_lookup separately unless job_detail fails.
- "servicer N" analysis → call servicer_dossier(N) first. Returns jobs + deals together.
- "DID or deal D and its jobs" → call deal_lookup(D). Returns deals + linked jobs.`;

// ---------------------------------------------------------------------------
// Job Investigation Pipeline — Playbook (system prompt for ReAct loop)
// ---------------------------------------------------------------------------

const JOB_INVESTIGATION_PLAYBOOK = `You are the FRP Job Analyst. Comprehensively analyze a specific monitoring job by traversing all three FRP data layers.

## Domain Model
- **Settings.xml** — job config: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SavePath.
- **tblExternalDIDRef** — deal mapping: CompanyID = ServicerID → DID + ImportDID (keyword). No DealName field.
- **tblTemplateStaging** — processing history: TemplateName = Scrubber, ServicerID, ResultCode, Comments.
- **Application logs** — job health metrics, DID match failures, daily activity events.

## Analysis Steps

### Step 1: Job Configuration + Linked Deals (ALWAYS run this first)
Call **job_detail** with the exact job name from the user's message.
- This returns BOTH the full job config AND all linked deals (DID, ImportDID keyword, CompanyID) in ONE call.
- Record: JobName, ServicerID, Scrubber (template name), Sender, MatchMode, SavePath.
- Record: Linked deals list (DID, ImportDID, CompanyID). If empty → note "no deals mapped to this job's ServicerID."
- If job NOT FOUND: suggest using search_jobs to find similar names. STOP — do not proceed to other steps.

### Step 2: Log Health (run ONLY if user asked about health, errors, activity, or "is it working")
Call **job_health** with the job name from Step 1.
- Shows: run count, success rate, last run time, common error patterns.
- Record: health status (healthy / warning / critical).

### Step 3: Processing Status (run ONLY if user asked about processing, template runs, or staging)
Call **template_status** with the Scrubber name from Step 1.
- Shows recent tblTemplateStaging runs: success/failure ratio, last run, file paths.
- If Scrubber is empty/none → skip this step.

### Step 4: DID Failures (run ONLY if deals exist from Step 1 but health shows DID-related failures)
Call **did_failures** to surface any DID match failures linked to this job.

## When to Stop
- User asked for job config + deals only → produce final report after Step 1.
- User asked for job + health → run Steps 1–2 then report.
- User asked for full status / "is it working" / end-to-end → run Steps 1–3 then report.
- ALWAYS: when you have enough information, produce your FINAL REPORT as text. Do NOT call another tool.

## Reporting Rules
1. **Job Configuration** section: JobName | ServicerID | Sender | Scrubber | MatchMode | SavePath.
2. **Linked Deals** table: DID | ImportDID Keyword | CompanyID. If empty → state "No deals configured."
3. **Log Health** section (if Step 2): health status + key metrics + top errors.
4. **Processing Status** section (if Step 3): recent runs table + success rate.
5. **Summary**: overall assessment and specific recommended actions.
6. Use ✅ ❌ ⚠️ status indicators. Never fabricate data — state explicitly when a step returned no results.`;

const JOB_INVESTIGATION_TOOLS = [
  'job_detail',        // Step 1: Full job config + linked deals in one call
  'job_health',        // Step 2: Log-based health metrics
  'template_status',   // Step 3: Processing history from tblTemplateStaging
  'did_failures',      // Step 4: DID match failure events
  'daily_summary',     // Optional: recent email events for this job
  'staging_search',    // Optional: direct tblTemplateStaging search
  'search_jobs',       // Fallback: if exact job name not found, search for it
];

// ---------------------------------------------------------------------------
// Servicer Investigation Pipeline — Playbook (system prompt for ReAct loop)
// ---------------------------------------------------------------------------

const SERVICER_INVESTIGATION_PLAYBOOK = `You are the FRP Servicer Analyst. Comprehensively analyze a servicer (by ID, job name, or name) across all FRP data layers.

## Domain Model
- **Settings.xml** — monitoring jobs. ServicerID links jobs to deals.
- **tblExternalDIDRef** — deal mapping. CompanyID = ServicerID. Holds all deals + ImportDID keywords.
- **tblTemplateStaging** — processing history indexed by ServicerID / TemplateName.
- **Application logs** — job health metrics and DID failure events.

Cross-reference: ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef).

## Analysis Steps

### Step 1: Servicer Overview (ALWAYS run first)
Call **servicer_dossier** with the servicer ID, job name, or servicer name from the user's question.
- Returns all jobs for this servicer, all linked deals, and coverage summary.
- If NOT FOUND, try **deal_lookup** with the numeric ID as a CompanyID query.
- Record: ServicerID, jobs list, deals list, counts.

### Step 2: DID Coverage (run if Step 1 did not return full deal info)
Call **deal_lookup** with the numeric ServicerID as the CompanyID query.
- Returns all DIDs + ImportDID keywords for this ServicerID.

### Step 3: Processing Status (run ONLY if user asked about processing, failures, or "is it working")
Call **failure_analysis** or **template_status** to check recent runs and failure patterns.

### Step 4: Coverage Gaps (run ONLY if user asked about gaps, missing setup, or uncovered deals)
Call **coverage_gaps** for this servicer.

## When to Stop
ALWAYS: when you have enough information, produce your FINAL REPORT as text. Do NOT call another tool.

## Reporting Rules
1. **Servicer Overview**: ServicerID | Total Jobs | Total Deals.
2. **Monitoring Jobs** table: JobName | Sender | Scrubber | MatchMode.
3. **Linked Deals** table: DID | ImportDID Keyword | CompanyID.
4. Optional sections for processing status / coverage gaps if those steps ran.
5. **Summary**: overall assessment + recommended actions.
6. Use ✅ ❌ ⚠️ status indicators. Never fabricate data.`;

const SERVICER_INVESTIGATION_TOOLS = [
  'servicer_dossier',   // Step 1: Jobs + deals + coverage in one call
  'deal_lookup',        // Step 2: All DIDs for a CompanyID
  'template_status',    // Step 3: Processing status
  'failure_analysis',   // Step 3: Failure patterns from tblTemplateStaging
  'job_health',         // Optional: health for specific jobs
  'coverage_gaps',      // Step 4: Coverage gap analysis
  'did_failures',       // Optional: DID-level failures
  'deal_pipeline',      // Optional: full pipeline view
];

// ---------------------------------------------------------------------------
// Email Triage Pipeline — Tool subset
// ---------------------------------------------------------------------------

const EMAIL_TRIAGE_TOOLS = [
  'search_jobs',       // Step 2: Find job by sender domain
  'job_detail',        // Step 2: Full job config with ServicerID
  'triage_email',      // Step 1: Parse .msg file (call with { prompt: "verify <filepath>" })
  'deal_lookup',       // Step 3: Find DIDs by CompanyID
  'staging_search',    // Step 6: Search tblTemplateStaging
  'template_status',   // Step 6: Check template processing status
  'daily_summary',     // Step 5: Individual email event log
  'job_health',        // Step 5: Job health from logs
  'did_failures',      // Step 5: DID failure rolling window (max 60 days)
  'deal_activity',     // Step 5: DID-specific log activity
  'create_job',        // Remediation: create new job
];

// ---------------------------------------------------------------------------
// Pipeline Definitions — registry of all ReAct-capable pipelines
// ---------------------------------------------------------------------------

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

const PIPELINE_DEFINITIONS = {
  email_triage: {
    name: 'email_triage',
    displayName: 'Email Triage Pipeline',
    triggerDescription: [
      'User asks to analyze, triage, or investigate an incoming email',
      'User provides a .msg file path and asks about it',
      'User provides email metadata (sender, subject, attachments) and asks if it is monitored or processed',
      'User asks "is this email covered?" or "what happens when this email arrives?"',
      'User says "trace this email", "check this email", "what job handles this email"',
    ].join('; '),
    playbook: EMAIL_TRIAGE_PLAYBOOK,
    tools: EMAIL_TRIAGE_TOOLS,
    maxSteps: 8,
  },
  job_investigation: {
    name: 'job_investigation',
    displayName: 'Job Investigation',
    triggerDescription: [
      'User asks about a specific job AND also wants health, processing status, or end-to-end verification',
      'User says "is job X working", "investigate job X", "full status of job X", "audit job X"',
      'User asks "why isn\'t job X processing" or "what\'s wrong with job X"',
      'User asks to verify a job is fully configured and processing correctly across all layers',
    ].join('; '),
    playbook: JOB_INVESTIGATION_PLAYBOOK,
    tools: JOB_INVESTIGATION_TOOLS,
    maxSteps: 5,
  },

  servicer_investigation: {
    name: 'servicer_investigation',
    displayName: 'Servicer Investigation',
    triggerDescription: [
      'User asks to investigate, audit, or check a servicer (by ID or name) across all data layers',
      'User says "investigate servicer 296", "audit servicer X", "full status for servicer N"',
      'User asks "why isn\'t servicer N processing" or "what deals does servicer N have and are they working"',
      'User asks for a complete coverage or processing report for a servicer ID',
    ].join('; '),
    playbook: SERVICER_INVESTIGATION_PLAYBOOK,
    tools: SERVICER_INVESTIGATION_TOOLS,
    maxSteps: 6,
  },

  general_reasoning: {
    name: 'general_reasoning',
    displayName: 'Multi-Step Reasoning',
    playbook: GENERAL_REASONING_PLAYBOOK,
    // Curated cross-domain tool set — covers all categories without exposing all 36 tools.
    // Deliberately excludes niche CRUD tools (create_job, edit_job, rollback, etc.)
    // that should never be invoked in an open-ended reasoning loop.
    tools: [
      'search_jobs', 'job_detail', 'deal_lookup', 'servicer_dossier',
      'template_status', 'processing_history', 'failure_analysis', 'source_trace',
      'daily_summary', 'did_failures', 'job_health', 'deal_activity',
      'coverage_gaps', 'deal_pipeline', 'staging_search',
    ],
    maxSteps: 10,
  },

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
};

// ---------------------------------------------------------------------------
// LLM Tool Definitions — the LLM picks the right tool based on the user's
// natural-language prompt.  No regex needed.
// ---------------------------------------------------------------------------

/**
 * All tools the @frp chat participant exposes to the LLM.
 * Each tool maps 1-to-1 with a handler function.
 *
 * The LLM sees { name, description, inputSchema } and decides which tool
 * to call and with what parameters.
 */
const FRP_TOOLS = [
  {
    name: 'search_jobs',
    description: 'Search, list, or filter email/SFTP monitoring jobs by job-level attributes (job name, scrubber, sender, servicer category like "CMBS").',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Free-text search term (job name, scrubber, sender, etc.). Use "*" to list all jobs.' },
      },
      required: ['query'],
    },
  },
  {
    name: 'job_detail',
    description: 'Get full details for a single job including configuration, servicer ID, scrubber, match mode, AND all linked deals/keywords from tblExternalDIDRef. Use when user asks about a specific job by name, OR asks "which deals/keywords are linked to job X", "list deals for job X", "what deals use job X", "show me the DID mappings for job X".',
    inputSchema: {
      type: 'object',
      properties: {
        jobName: { type: 'string', description: 'The exact job name (e.g. "CMBS_GreyCo", "CMLTI_Fay", "TOWD_Wells_6502").' },
      },
      required: ['jobName'],
    },
  },
  {
    name: 'deal_lookup',
    description: 'Query the tblExternalDIDRef database table. Supports: search by deal name (DID), ImportDID keyword, or CompanyID/ServicerID number. Also supports "*" or "all" to list ALL records. Returns tblExternalDIDRef rows AND any linked Settings.xml jobs. Use this whenever the user mentions tblExternalDIDRef, deals, DIDs, ImportDID, or CompanyID.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The lookup value: "*" or "all" for all records, a numeric CompanyID (e.g. "296"), a deal name/DID (e.g. "CMLTI 2014-A"), or an ImportDID keyword (e.g. "M70"). Extract ONLY the identifier — do NOT include labels like "CompanyID".' },
      },
      required: ['query'],
    },
  },
  {
    name: 'validate_email',
    description: 'Validate the email monitoring Settings.xml configuration. Check for structural issues, missing fields, or invalid values across all email jobs.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'validate_sftp',
    description: 'Validate the SFTP monitoring Settings.xml configuration.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'templates',
    description: 'Show the template/scrubber inventory — all unique scrubber patterns and parser combinations used across jobs.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'create_job',
    description: 'Create a new email or SFTP monitoring job by copying an existing job as a template. Use when user says "create a job", "add a new job", "make a copy of job X".',
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
          description: 'Optional field overrides to apply (e.g. {"servicer_id": "999"}).',
          additionalProperties: { type: 'string' },
        },
        xmlType: {
          type: 'string',
          enum: ['email', 'sftp'],
          description: 'Job type: "email" or "sftp". Defaults to "email" if omitted.',
        },
      },
      required: ['newName', 'templateJob'],
    },
  },
  {
    name: 'edit_job',
    description: 'Edit/update an existing email or SFTP job configuration field. Use for: changing scrubber/template, servicer ID, mailbox, sender filter, subject filter, SME, save location, import DID, day adjust, SFTP path/DSN.',
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
            // Email job fields
            'name', 'servicer_id', 'mailbox', 'folder', 'sme', 'save_location',
            'last_email', 'queue_one_file', 'day_adjust', 'import_did',
            'subject_filter', 'sender_filter', 'scrubber', 'template',
            // SFTP job fields (xmlType='sftp' required)
            'path', 'dsn', 'skip_list', 'ignore_list', 'zip_content_filter',
          ],
          description: 'The configuration field to update. SFTP-only fields (path, dsn, skip_list, ignore_list, zip_content_filter) require xmlType="sftp".',
        },
        value: {
          type: 'string',
          description: 'The new value to set for the field.',
        },
        xmlType: {
          type: 'string',
          enum: ['email', 'sftp'],
          description: 'Job type: "email" for email monitoring jobs, "sftp" for SFTP delivery jobs. Defaults to "email" if omitted.',
        },
      },
      required: ['jobName', 'field', 'value'],
    },
  },
  {
    name: 'servicer_dossier',
    description: 'Build a comprehensive dossier for a servicer or job — shows all jobs, deals, coverage, and configuration for a given servicer ID or job name.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Servicer ID number, job name, or servicer name to look up.' },
      },
      required: ['query'],
    },
  },
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
  {
    name: 'orphan_detection',
    description: 'Detect orphaned jobs — jobs whose ServicerID has no matching CompanyID in tblExternalDIDRef.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'collision_detection',
    description: 'Detect ImportDID collisions — ImportDID keywords that appear under multiple CompanyIDs in tblExternalDIDRef, causing ambiguous matching.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'sync_logs',
    description: 'Sync or index application log files into the SQLite database for analytics. Call this for any user request that says "sync logs", "index logs", "refresh logs", "update log index", or similar. Takes no parameters.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'daily_summary',
    description: 'Show the daily operations summary — emails processed, attachments downloaded, DID lookups, errors. Optionally for a specific date.',
    inputSchema: {
      type: 'object',
      properties: {
        date: { type: 'string', description: 'Optional date in YYYY-MM-DD format. Defaults to today.' },
      },
    },
  },
  {
    name: 'did_failures',
    description: 'Show recent DID lookup failures — emails that could not be matched to a deal.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'job_health',
    description: 'Check health metrics for a specific job — run count, success rate, last run, errors.',
    inputSchema: {
      type: 'object',
      properties: {
        jobName: { type: 'string', description: 'The job name to check health for.' },
      },
    },
  },
  {
    name: 'deal_activity',
    description: 'Show recent activity for a specific deal (DID) from the logs.',
    inputSchema: {
      type: 'object',
      properties: {
        did: { type: 'string', description: 'The deal identifier (DID) to check activity for.' },
      },
    },
  },
  {
    name: 'log_trends',
    description: 'Show volume and processing trends over time from the logs.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'log_performance',
    description: 'Show performance rankings — worst/best performing jobs, underperforming jobs.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'save_settings',
    description: 'Save/deploy the current email or SFTP Settings.xml configuration (creates a backup first).',
    inputSchema: {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['email', 'sftp'], description: 'Which settings file to save.' },
      },
      required: ['type'],
    },
  },
  {
    name: 'list_backups',
    description: 'List available Settings.xml backup/restore points.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'xml_diff',
    description: 'Show what changed in Settings.xml since the last backup/deploy.',
    inputSchema: { type: 'object', properties: {} },
  },
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
          description: '"new" — triage as a new unknown email; "verify" — check if the email matches an existing job; "match" — find the best matching job. Default: "new".',
        },
      },
      required: [],
    },
  },
  {
    name: 'consolidation_analysis',
    description: 'Analyze which jobs could be merged/consolidated based on similar configurations.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'impact_analysis',
    description: 'Model the downstream impact of a proposed configuration change on jobs, servicers, and daily processing. Use when user asks "what happens if I change X", "impact of removing Y", "what breaks if I update Z".',
    inputSchema: {
      type: 'object',
      properties: {
        changeType: {
          type: 'string',
          enum: [
            'servicer_change', 'scrubber_change', 'template_change',
            'job_disable', 'job_create', 'job_delete',
            'sender_filter_change', 'subject_filter_change', 'sftp_path_change',
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
  {
    name: 'system_health',
    description: 'Full system health report — configuration validation, coverage stats, log sync status, overall system status.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'agent_status',
    description: 'Show FRP Agent backend status — version, database mode, connection status.',
    inputSchema: { type: 'object', properties: {} },
  },
  // --- Phase 5: tblTemplateStaging tools ---
  {
    name: 'template_status',
    description: 'Check the processing status of a template (scrubber) or deal (DID). Shows recent runs, success/failure ratio, last run time. Use when user asks "has X been processed", "status of template Y", "latest run for deal Z", "is TPMT_SPS running", "when did scrubber X last run".',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Template name, DID, or keyword to check status for.' },
        days: { type: 'number', description: 'Look-back window in days (default 30).' },
      },
      required: ['query'],
    },
  },
  {
    name: 'processing_history',
    description: 'Query tblTemplateStaging to show processing runs. Supports filtering by DID, TemplateName (scrubber name), or ServicerID, optionally with a date range. Use for ANY question about: scrubbers queued/ran for a DID, processing history, what was processed, show all runs, template execution, did it run, was it successful, list scrubbers for a deal in the last N days.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'DID (e.g. "FREMF 2026-KF169"), TemplateName/scrubber name (e.g. "QueueCMBS_Scrubber_x"), or ServicerID (e.g. "363") to filter by.' },
        startDate: { type: 'string', description: 'Start date in YYYY-MM-DD format for the time window.' },
        endDate: { type: 'string', description: 'End date in YYYY-MM-DD format for the time window.' },
      },
      required: ['query'],
    },
  },
  {
    name: 'failure_analysis',
    description: 'Analyze processing failures from tblTemplateStaging. Shows what failed, why, error patterns, affected deals/servicers. Use when user asks "what\'s failing", "why did X fail", "show errors", "failure report", "which templates are broken".',
    inputSchema: {
      type: 'object',
      properties: {
        template: { type: 'string', description: 'Optional template name filter.' },
        did: { type: 'string', description: 'Optional DID filter.' },
        days: { type: 'number', description: 'Look-back window in days (default 30).' },
      },
    },
  },
  {
    name: 'source_trace',
    description: 'Trace where a file came from — shows the email mailbox, SFTP folder, or manual queue that triggered processing. Use when user asks "where did this file come from", "trace file X", "which mailbox triggered Y", "how did file Z get processed".',
    inputSchema: {
      type: 'object',
      properties: {
        filepath: { type: 'string', description: 'Full or partial file path to trace.' },
      },
      required: ['filepath'],
    },
  },
  {
    name: 'manual_queue',
    description: 'Show manual vs automated processing breakdown. Identifies deals/templates frequently manually queued. Use when user asks "how much is manual", "manual queue stats", "automation gaps", "which deals need manual intervention", "who is manually queuing".',
    inputSchema: {
      type: 'object',
      properties: {
        days: { type: 'number', description: 'Look-back window in days (default 30).' },
        template: { type: 'string', description: 'Optional template filter.' },
        servicerId: { type: 'string', description: 'Optional servicer ID filter.' },
      },
    },
  },
  {
    name: 'processing_duration',
    description: 'Analyze processing times — how long templates take to run, which are slowest, outlier detection. Use when user asks "how long does X take", "slowest templates", "processing time analysis", "performance bottlenecks", "duration report".',
    inputSchema: {
      type: 'object',
      properties: {
        template: { type: 'string', description: 'Optional template name filter.' },
        days: { type: 'number', description: 'Look-back window in days (default 30).' },
        sort: { type: 'string', description: 'Sort by: avg_seconds, max_seconds, total_runs.' },
      },
    },
  },
  {
    name: 'deal_pipeline',
    description: 'End-to-end pipeline view for a deal or servicer — combines Settings.xml configuration, tblExternalDIDRef deal mapping, and tblTemplateStaging execution history into a single unified view. Use when user asks "full pipeline for X", "end to end status", "pipeline view for servicer 296", "is deal X fully configured and processing".',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'DID name, ServicerID number, or TemplateName.' },
        days: { type: 'number', description: 'Look-back window in days (default 30).' },
      },
      required: ['query'],
    },
  },
  {
    name: 'staging_search',
    description: 'Search tblTemplateStaging records directly. Use when user asks "search staging for X", "look up template process ID 12345", "find staging records matching Y", "query template staging".',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search term: TemplateProcessID (number), DID, TemplateName, or FilePath pattern.' },
      },
      required: ['query'],
    },
  },
];

// ---------------------------------------------------------------------------
// Intent Categories — Stage 1 classification targets
// ---------------------------------------------------------------------------

const INTENT_CATEGORIES = [
  {
    name: 'deal_mapping',
    displayName: 'Deal & Reference Mapping',
    description: 'Questions about deals, DIDs, ImportDID keywords, CompanyID/ServicerID lookups, and deal-to-job reverse mapping. The answer comes FROM the deal reference table (tblExternalDIDRef) and cross-references to Settings.xml.',
    dataLayer: 'tblExternalDIDRef + cross-reference to Settings.xml',
    examples: [
      'any jobs for deal DID = "ICW MAT TRUST SUBI A1"',
      'do we have any jobs and keywords setup for Deal with DID: "ICW MAT TRUST SUBI A1"',
      'what jobs handle deal CMLTI 2014-A',
      'which keywords map to servicer 296',
      'do we have coverage for deal CMLTI 2014-A',
      'show me all deals for CompanyID 569',
      'are there orphaned jobs with no deal mapping',
    ],
  },
  {
    name: 'job_config',
    displayName: 'Job Configuration',
    description: 'Searching, listing, filtering, or inspecting email/SFTP monitoring jobs by job-level attributes (job name, scrubber, sender, type). Also creating or editing jobs and validating Settings.xml. NOT for queries that start from a deal name, DID, keyword, or CompanyID — those go to deal_mapping even if "jobs" is mentioned.',
    dataLayer: 'Settings.xml via SQLite cache',
    examples: [
      'list all cmbs jobs',
      'search jobs by sender "reports@fay.com"',
      'show details for job CMLTI_Fay',
      'validate the email settings',
      'create a new job from CMBS_GreyCo template',
    ],
  },
  {
    name: 'processing',
    displayName: 'Processing & Execution History',
    description: 'Questions about whether a scrubber/template ran, processing runs, execution status, queued templates, success/failure analysis, file source tracing, manual vs automated queuing, processing duration, and end-to-end pipeline views. Data comes from tblTemplateStaging. ANY question about "did it run", "was it processed", "scrubbers queued", "show runs", or filtering tblTemplateStaging by DID, TemplateName, date range, distribution period, or ServicerID belongs HERE.',
    dataLayer: 'tblTemplateStaging',
    examples: [
      'has TPMT_SPS been processed today',
      'show processing history for servicer 296',
      'what templates are failing',
      'trace where file M:\\Data\\report.xlsx came from',
      'pipeline view for deal CMLTI 2014-A',
      'list all scrubbers queued for DID FREMF 2026-KF169 in last 25 days',
      'did any scrubbers run for deal CMLTI 2014-A this month',
      'what was processed for DID ICW MAT TRUST SUBI A1',
      'show all runs for template QueueCMBS_Scrubber_x in February',
      'any processing for servicer 363 in the last week',
      'was the scrubber for FREMF 2026-KF169 successful',
    ],
  },
  {
    name: 'logs_ops',
    displayName: 'Application Logs & Operations',
    description: 'Questions about application log entries, daily operation summaries, DID lookup failures from logs, job health metrics, activity trends, and performance rankings. Data comes from EmailMonitor/SFTP log files indexed in SQLite.',
    dataLayer: 'Application log files (SQLite-indexed)',
    examples: [
      'show me today\'s daily summary',
      'any DID lookup failures recently',
      'how is job CMBS_GreyCo performing',
      'show log trends for the past week',
      'sync the latest log files',
    ],
  },
  {
    name: 'deployment',
    displayName: 'Deployment & Configuration Management',
    description: 'Saving, deploying, backing up, diffing, or rolling back Settings.xml configuration files.',
    dataLayer: 'Settings.xml backup/deploy system',
    examples: [
      'save the email settings',
      'list available backups',
      'what changed since last deploy',
      'rollback to the previous version',
    ],
  },
  {
    name: 'system_admin',
    displayName: 'System Administration & Analysis',
    description: 'Email triage (is this email monitored?), job consolidation analysis, impact analysis ("what if" scenarios), full system health checks, and agent status.',
    dataLayer: 'Cross-cutting — reads from multiple data layers',
    examples: [
      'triage this email from reports@servicer.com',
      'which jobs could be consolidated',
      'what if we remove servicer 569',
      'run a full system health check',
      'show agent status',
    ],
  },
];

// ---------------------------------------------------------------------------
// Category → Tool mapping — determines which tools Stage 2 sees
// ---------------------------------------------------------------------------

const CATEGORY_TOOLS = {
  deal_mapping:  ['deal_lookup', 'servicer_dossier', 'coverage_gaps', 'orphan_detection', 'collision_detection'],
  job_config:    ['search_jobs', 'job_detail', 'validate_email', 'validate_sftp', 'templates', 'create_job', 'edit_job'],
  processing:    ['template_status', 'processing_history', 'failure_analysis', 'source_trace', 'manual_queue', 'processing_duration', 'deal_pipeline', 'staging_search', 'templates'],
  logs_ops:      ['sync_logs', 'daily_summary', 'did_failures', 'job_health', 'deal_activity', 'log_trends', 'log_performance'],
  deployment:    ['save_settings', 'list_backups', 'xml_diff', 'rollback'],
  system_admin:  ['triage_email', 'consolidation_analysis', 'impact_analysis', 'system_health', 'agent_status'],
};

// ---------------------------------------------------------------------------
// Stage 1: Intent Classification
// ---------------------------------------------------------------------------

/**
 * Build the Stage 1 intent classification prompt.
 *
 * @param {string} prompt  The user's natural-language question
 * @param {string} historyContext  Conversation history from buildConversationContext()
 * @returns {string} The complete classifier prompt to send to the LLM
 */
function buildClassifierPrompt(prompt, historyContext) {
  const categoryDefs = INTENT_CATEGORIES.map(cat => {
    const examples = cat.examples.map(e => `    - "${e}"`).join('\n');
    return [
      `**${cat.name}** — ${cat.displayName}`,
      `  Description: ${cat.description}`,
      `  Data layer: ${cat.dataLayer}`,
      `  Example prompts:`,
      examples,
    ].join('\n');
  }).join('\n\n');

  const disambiguationRules = [
    '## Disambiguation Rules',
    '',
    '### HIGHEST PRIORITY RULE — Processing vs Deal Mapping',
    '**FIRST check if the user is asking about EXECUTION / PROCESSING / RUNS / STATUS / QUEUING.** If the question is about whether something ran, was processed, was queued, execution history, run results, or filters on tblTemplateStaging (by DID, TemplateName, date range, distribution period, ServicerID) → classify as **processing**, even if a DID or deal name is mentioned. The presence of a DID does NOT automatically mean deal_mapping.',
    '',
    'Signal words for **processing**: ran, run, processed, queued, scrubber, template, execution, status, failed, succeeded, history, last N days, date range, distribution period, StartTime, when did it run, was it processed, show runs.',
    '',
    'Signal words for **deal_mapping**: jobs setup, keywords, ImportDID, coverage, mapping, which jobs handle, do we have coverage, orphaned, what jobs are configured, CompanyID lookup.',
    '',
    '**Only classify as deal_mapping when the user is asking about the CONFIGURATION/SETUP of deals, keywords, and monitoring jobs — i.e., data from tblExternalDIDRef and Settings.xml.** If they mention a DID but ask about runs/processing/scrubbers/queuing → processing.',
    '',
    '### Job + Deals Rule (OVERRIDE — apply before pipeline detection)',
    '**If the user names a SPECIFIC JOB by name and also wants its linked deals/keywords/DIDs — classify as job_config + single_tool.** The job_detail tool returns BOTH the job configuration AND all linked deals from tblExternalDIDRef in a single call. Do NOT classify this as pipeline. Do NOT classify as deal_mapping.',
    '- "list job CMBS_GreyCo and deals associated with this job" → job_config, single_tool',
    '- "show details for CMBS_GreyCo including linked deals/keywords" → job_config, single_tool',
    '- "what deals are linked to job CMBS_GreyCo?" → job_config, single_tool (job_detail)',
    '- Exception: if user ALSO asks about health, processing, logs, or "is it working" → job_investigation pipeline.',
    '',
    '- If the user provides a deal name, DID, ImportDID keyword, or CompanyID and asks about jobs, keywords, or setup (NOT about processing/runs/execution) → deal_mapping (NOT job_config). The answer starts from the deal reference table.',
    '- If the user asks to search, list, or filter jobs by job-level attributes (name, scrubber, sender) → job_config.',
    '- If the user asks about a specific job by name (e.g., "details for CMBS_GreyCo") → job_config.',
    '- If the user says "deals for job X" or "keywords linked to job X" → job_config (job_detail returns linked deals).',
    '- If the user asks about processing runs, failures, duration, or "has X been processed" → processing.',
    '- If the user asks about log entries, daily summary, trends, or performance rankings from logs → logs_ops.',
    '- If the user says "save", "deploy", "backup", "rollback", or "diff" → deployment.',
    '- If the user asks for triage, consolidation, impact, or system health → system_admin.',
    '- If the user says "pipeline view" or "end-to-end" → processing.',
  ].join('\n');

  // ── Complexity detection (Phase 8 upgraded) ──
  const emailTriageDef = PIPELINE_DEFINITIONS.email_triage;
  const jobInvestDef = PIPELINE_DEFINITIONS.job_investigation;
  const servicerInvestDef = PIPELINE_DEFINITIONS.servicer_investigation;
  const crudPlanningDef = PIPELINE_DEFINITIONS.crud_planning;
  const analysisPipelineDef = PIPELINE_DEFINITIONS.analysis_pipeline;

  const emailTriageTriggers = emailTriageDef
    ? `**email_triage** pipeline: ${emailTriageDef.triggerDescription}`
    : '';
  const jobInvestTriggers = jobInvestDef
    ? `**job_investigation** pipeline: ${jobInvestDef.triggerDescription}`
    : '';
  const servicerInvestTriggers = servicerInvestDef
    ? `**servicer_investigation** pipeline: ${servicerInvestDef.triggerDescription}`
    : '';
  const crudPlanningTriggers = crudPlanningDef
    ? `**crud_planning** pipeline: ${crudPlanningDef.triggerDescription}`
    : '';
  const analysisPipelineTriggers = analysisPipelineDef
    ? `**analysis_pipeline** pipeline: ${analysisPipelineDef.triggerDescription}`
    : '';

  const pipelineSection = [
    '## Mode Detection: single_tool vs pipeline',
    '',
    'After choosing a category, decide whether the question needs **one tool call** or **multiple sequential tool calls where one result feeds the next**.',
    '',
    '### Set mode = "single_tool" when:',
    '- The question asks for ONE piece of data from ONE data source.',
    '- Simple lookup, list, search, status check, CRUD operation.',
    '- A job name + its linked deals (job_detail returns both in ONE call).',
    '- Examples: "list all jobs", "show deals for 296", "template status for TPMT_SPS", "create job from X", "save settings", "list job CMBS_GreyCo and its deals".',
    '',
    '### Set mode = "pipeline" when ALL of these are true:',
    '- The answer CANNOT be served by a single tool call.',
    '- AND one of: (a) investigation/diagnosis across 3+ data layers, (b) "is X working end-to-end", (c) compound question with 3+ sub-questions, (d) operational report covering multiple domains.',
    '',
    '### DO NOT set mode = "pipeline" for:',
    '- "job X and its linked deals" → single_tool (job_detail returns both).',
    '- "deals for servicer N" → single_tool (deal_lookup or servicer_dossier).',
    '- Any question answerable with a single tool call, even if it spans 2 tables.',
    '',
    '### Specialized pipelines',
    'If pipeline mode is set, also set the pipeline name to the most specific matching pipeline:',
    emailTriageTriggers,
    jobInvestTriggers,
    servicerInvestTriggers,
    crudPlanningTriggers,
    analysisPipelineTriggers,
    '**general_reasoning** pipeline: Use as fallback when mode=pipeline but none of the above match.',
    '',
    '### Examples',
    '- "list all cmbs jobs" → mode: single_tool, category: job_config',
    '- "template status for TPMT_SPS" → mode: single_tool, category: processing',
    '- "any DID failures recently" → mode: single_tool, category: logs_ops',
    '- "list all scrubbers queued for DID FREMF 2026-KF169 in last 25 days" → mode: single_tool, category: processing (asks about runs/queuing, not setup)',
    '- "did any scrubbers run for deal CMLTI 2014-A this month" → mode: single_tool, category: processing',
    '- "what was processed for DID ICW MAT TRUST SUBI A1" → mode: single_tool, category: processing',
    '- "was the scrubber for FREMF 2026-KF169 successful" → mode: single_tool, category: processing',
    '- "any processing for servicer 363 in the last week" → mode: single_tool, category: processing',
    '- "do we have any jobs and keywords for deal ICW MAT TRUST SUBI A1" → mode: single_tool, category: deal_mapping (asks about setup/config)',
    '- "what jobs handle deal CMLTI 2014-A" → mode: single_tool, category: deal_mapping (asks about job mapping)',
    '- "show me all deals for CompanyID 569" → mode: single_tool, category: deal_mapping',
    '- "list all jobs with job name CMBS_GreyCo and also deals associated with this job" → mode: single_tool, category: job_config (job_detail returns both)',
    '- "show details for CMBS_GreyCo including its linked deals" → mode: single_tool, category: job_config',
    '- "is job CMBS_GreyCo working end-to-end" → mode: pipeline, pipeline: job_investigation',
    '- "investigate job CMBS_GreyCo — config, health, and processing" → mode: pipeline, pipeline: job_investigation',
    '- "audit servicer 296 across all layers" → mode: pipeline, pipeline: servicer_investigation',
    '- "morning report: failures, DID issues, pending" → mode: pipeline, pipeline: general_reasoning',
    '- "why isn\'t servicer 296 processing" → mode: pipeline, pipeline: servicer_investigation',
    '- "triage this email from reports@fay.com" → mode: pipeline, pipeline: email_triage',
    '- "what if we remove servicer 569" → mode: pipeline, pipeline: general_reasoning',
    '- "validate config, check gaps, then deploy" → mode: pipeline, pipeline: general_reasoning',
    '- "compare deal activity between servicer 150 and 296" → mode: pipeline, pipeline: general_reasoning',
    '- "create GreyCo_v2 from CSMC_Template and set scrubber to Outlook_Queuer_x" → mode: pipeline, pipeline: crud_planning',
    '- "add a new job and configure servicer 569 on it" → mode: pipeline, pipeline: crud_planning',
    '- "create a job, rename it, then validate" → mode: pipeline, pipeline: crud_planning',
    '- "run a full health check on the system" → mode: pipeline, pipeline: analysis_pipeline',
    '- "are there any coverage gaps across all email jobs?" → mode: pipeline, pipeline: analysis_pipeline',
    '- "what\'s the performance like this week and are there any consolidation opportunities?" → mode: pipeline, pipeline: analysis_pipeline',
    '- "what breaks if I change the scrubber on CMBS_GreyCo?" → mode: pipeline, pipeline: analysis_pipeline',
  ].join('\n');

  const parts = [
    'You are classifying a user\'s question about the FRP (File Reception Portal) system into exactly one category.',
    '',
    '## Categories',
    '',
    categoryDefs,
    '',
    disambiguationRules,
    '',
    pipelineSection,
    '',
  ];

  if (historyContext) {
    parts.push('## Conversation History');
    parts.push(historyContext);
    parts.push('');
  }

  parts.push(`## User Question`);
  parts.push(prompt);
  parts.push('');
  parts.push('Respond with ONLY a JSON object: { "category": "<category_name>", "mode": "<single_tool|pipeline>", "pipeline": "<pipeline_name_or_null>" }');
  parts.push('Set mode to "pipeline" ONLY if the query genuinely requires multiple chained tool calls that cannot be answered by a single tool (see rules above).');
  parts.push('Set pipeline to one of: "email_triage", "job_investigation", "servicer_investigation", "crud_planning", "analysis_pipeline", "general_reasoning", or null (for single_tool mode). Never invent other pipeline names.');
  parts.push('Do not explain. Do not include any other text.');

  return parts.join('\n');
}

/**
 * Stage 1: Classify the user's intent into one of INTENT_CATEGORIES.
 *
 * Sends a lightweight prompt to the LLM (no tools) asking for a JSON
 * response with the category name. Falls back to null on any error
 * (parse failure, unknown category, LLM error).
 *
 * @param {string} prompt          The user's natural-language question
 * @param {string} historyContext  Conversation history string
 * @param {Object} model           The LLM model (from selectModel)
 * @param {Object} token           CancellationToken
 * @param {Object} shared          Shared extension context (for logging)
 * @returns {Promise<{category: string, mode: string, pipeline: string|null}|null>} Classification result, or null on failure
 */
async function classifyIntent(prompt, historyContext, model, token, shared) {
  const classifierPromptText = buildClassifierPrompt(prompt, historyContext);

  const messages = [
    vscode.LanguageModelChatMessage.User(classifierPromptText),
  ];

  try {
    shared.outputChannel.appendLine(`[FRP]   │  Classifying: "${prompt.slice(0, 80)}"`);

    const response = await model.sendRequest(messages, {}, token);

    // Collect the full text response
    let responseText = '';
    for await (const part of response.stream) {
      if (typeof part === 'string') {
        responseText += part;
      } else if (part.value && typeof part.value === 'string') {
        responseText += part.value;
      }
    }

    responseText = responseText.trim();
    shared.outputChannel.appendLine(`[FRP]   │  LLM raw: ${responseText.slice(0, 120)}${responseText.length > 120 ? '...' : ''}`);

    const parsed = extractJSON(responseText);
    if (!parsed) {
      shared.outputChannel.appendLine('[FRP]   │  ✗ Could not extract JSON from LLM response');
      return null; // will be retried by caller
    }
    const category = parsed.category;
    const mode = parsed.mode || 'single_tool';
    // Validate pipeline name against known definitions; reject unknown names
    const rawPipeline = parsed.pipeline || null;
    const pipeline = (rawPipeline && PIPELINE_DEFINITIONS[rawPipeline]) ? rawPipeline : null;

    if (!category || !CATEGORY_TOOLS[category]) {
      shared.outputChannel.appendLine(
        `[FRP]   │  ✗ Unknown category: "${category}"`
      );
      return null;
    }

    if (rawPipeline && !pipeline) {
      shared.outputChannel.appendLine(
        `[FRP]   │  ⚠ Unknown pipeline "${rawPipeline}" — will use general_reasoning`
      );
    }

    shared.outputChannel.appendLine(`[FRP]   │  ✓ Result: category=${category} mode=${mode} pipeline=${pipeline || 'none'}`);
    return { category, mode, pipeline };

  } catch (err) {
    shared.outputChannel.appendLine(
      `[FRP]   │  ✗ Error: ${err.message}`
    );
    return null;
  }
}

/**
 * Extract a JSON object from an LLM response that may contain surrounding
 * prose, markdown fences, or chain-of-thought text.
 *
 * Tries, in order:
 *   1. Direct JSON.parse of the full trimmed text
 *   2. Content inside markdown code fences (```json ... ```)
 *   3. First { ... } substring (greedy, handles nested braces)
 *
 * @param {string} text  Raw LLM response text
 * @returns {Object|null}  Parsed JSON object, or null on failure
 */
function extractJSON(text) {
  const trimmed = text.trim();

  // 1. Try direct parse (ideal case — model returned pure JSON)
  try { return JSON.parse(trimmed); } catch { /* continue */ }

  // 2. Try extracting from markdown code fences
  const fenceMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenceMatch) {
    try { return JSON.parse(fenceMatch[1].trim()); } catch { /* continue */ }
  }

  // 3. Find the first top-level { ... } in the text
  const start = trimmed.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  for (let i = start; i < trimmed.length; i++) {
    if (trimmed[i] === '{') depth++;
    else if (trimmed[i] === '}') depth--;
    if (depth === 0) {
      try { return JSON.parse(trimmed.slice(start, i + 1)); } catch { return null; }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Tool argument builder — shared by executeToolCall and executePipelineTool
// ---------------------------------------------------------------------------

/**
 * Build backendCall arguments for a given tool name and input.
 *
 * Returns { command, params } for use with backendCall(), or null for tools
 * that require special handling (e.g., triage_email routes through
 * handleTriageCommand, not backendCall).
 *
 * @param {string} toolName  Name of the tool
 * @param {Object} toolInput Input parameters from LLM tool call
 * @returns {{ command: string, params: Object }|null}
 */
function buildToolArgs(toolName, toolInput) {
  switch (toolName) {
    case 'search_jobs':
      return { command: 'search_jobs', params: { query: toolInput.query || '' } };
    case 'job_detail':
      return { command: 'job_detail', params: { jobName: toolInput.jobName || '' } };
    case 'deal_lookup':
      return { command: 'deal_lookup', params: { query: toolInput.query || '' } };
    case 'staging_search':
      return { command: 'staging_search', params: { query: toolInput.query || '' } };
    case 'template_status': {
      const args = { query: toolInput.query || '' };
      if (toolInput.days) args.days = String(toolInput.days);
      return { command: 'template_status', params: args };
    }
    case 'daily_summary': {
      const params = {};
      if (toolInput.date) params.date = toolInput.date;
      return { command: 'log_daily_summary', params };
    }
    case 'job_health':
      return { command: 'log_job_health', params: { jobName: toolInput.jobName || '' } };
    case 'did_failures':
      return { command: 'log_did_failures', params: {} };
    case 'deal_activity':
      return { command: 'log_deal_activity', params: { did: toolInput.did || '' } };
    case 'create_job':
      return { command: 'create_job', params: { newName: toolInput.newName || '', templateJob: toolInput.templateJob || '', overrides: toolInput.overrides || {}, xmlType: toolInput.xmlType || 'email' } };
    case 'triage_email':
      return null; // special-cased in executePipelineTool

    // --- Remaining tools for general reasoning pipeline ---
    case 'validate_email':
      return { command: 'validate_email', params: { jobName: toolInput.jobName || '' } };
    case 'validate_sftp':
      return { command: 'validate_sftp', params: { jobName: toolInput.jobName || '' } };
    case 'templates':
      return { command: 'template_inventory', params: { filter: toolInput.filter || '' } };
    case 'edit_job':
      return { command: 'edit_job', params: { jobName: toolInput.jobName || '', field: toolInput.field || '', value: toolInput.value || '', xmlType: toolInput.xmlType || 'email' } };
    case 'servicer_dossier':
      return { command: 'servicer_dossier', params: { query: toolInput.query || '' } };
    case 'coverage_gaps':
      return { command: 'coverage_gaps', params: { focus: toolInput.focus || 'all' } };
    case 'orphan_detection':
      return { command: 'orphan_detection', params: {} };
    case 'collision_detection':
      return { command: 'collision_detection', params: {} };
    case 'sync_logs':
      return { command: 'sync_logs', params: {} };
    case 'log_trends': {
      const params = {};
      if (toolInput.days) params.days = String(toolInput.days);
      if (toolInput.job) params.job = toolInput.job;
      return { command: 'log_trends', params };
    }
    case 'log_performance': {
      const params = {};
      if (toolInput.sort) params.sort = toolInput.sort;
      if (toolInput.top) params.top = String(toolInput.top);
      if (toolInput.days) params.days = String(toolInput.days);
      return { command: 'log_performance', params };
    }
    case 'save_settings':
      return { command: toolInput.type === 'sftp' ? 'save_sftp_settings' : 'save_email_settings', params: {} };
    case 'list_backups':
      return { command: 'list_backups', params: {} };
    case 'xml_diff': {
      const params = {};
      if (toolInput.backupFile) params.backupFile = toolInput.backupFile;
      return { command: 'xml_diff', params };
    }
    case 'rollback':
      return { command: 'rollback_xml', params: { backupFile: toolInput.backupFile || '' } };
    case 'consolidation_analysis':
      return { command: 'analyze_consolidation', params: { type: toolInput.type || 'all' } };
    case 'impact_analysis':
      return { command: 'analyze_impact', params: { change_type: toolInput.changeType || '', target_job: toolInput.targetJob || '', new_value: toolInput.newValue || '', current_value: toolInput.currentValue || '', affected_servicers: toolInput.affectedServicers || [], dry_run: toolInput.dryRun !== false } };
    case 'system_health':
      return { command: 'analyze_health', params: { type: toolInput.type || 'all' } };
    case 'agent_status':
      return { command: 'search_jobs', params: { query: '' } };
    case 'processing_history': {
      const params = { query: toolInput.query || '' };
      if (toolInput.startDate) params.startDate = toolInput.startDate;
      if (toolInput.endDate) params.endDate = toolInput.endDate;
      return { command: 'processing_history', params };
    }
    case 'failure_analysis': {
      const params = {};
      if (toolInput.template) params.template = toolInput.template;
      if (toolInput.did) params.did = toolInput.did;
      if (toolInput.days) params.days = String(toolInput.days);
      return { command: 'failure_analysis', params };
    }
    case 'source_trace':
      return { command: 'source_trace', params: { filepath: toolInput.filepath || '' } };
    case 'manual_queue': {
      const params = {};
      if (toolInput.days) params.days = String(toolInput.days);
      if (toolInput.template) params.template = toolInput.template;
      if (toolInput.servicerId) params.servicerId = toolInput.servicerId;
      return { command: 'manual_queue_report', params };
    }
    case 'processing_duration': {
      const params = {};
      if (toolInput.template) params.template = toolInput.template;
      if (toolInput.days) params.days = String(toolInput.days);
      if (toolInput.sort) params.sort = toolInput.sort;
      return { command: 'processing_duration', params };
    }
    case 'deal_pipeline': {
      const params = { query: toolInput.query || '' };
      if (toolInput.days) params.days = String(toolInput.days);
      return { command: 'deal_pipeline', params };
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// LLM Tool-Call Router — dispatches tool calls to handler functions
// ---------------------------------------------------------------------------

/**
 * Execute a tool call returned by the LLM and return the result via the
 * appropriate handler function.
 *
 * @param {string}  toolName  The name of the tool from FRP_TOOLS
 * @param {Object}  input     The input parameters selected by the LLM
 * @param {Object}  request   VS Code ChatRequest
 * @param {Object}  context   VS Code ChatContext
 * @param {Object}  stream    VS Code ChatResponseStream
 * @param {Object}  token     CancellationToken
 * @param {Object}  shared    Shared extension context
 * @param {string}  prompt    Original user prompt (used as fallback)
 * @returns {Promise<Object>} ChatResult with optional followUps
 */
async function executeToolCall(toolName, input, request, context, stream, token, shared, prompt) {
  shared.outputChannel.appendLine(
    `[FRP]   └─ Executing: ${toolName}(${JSON.stringify(input)})`
  );

  switch (toolName) {
    case 'search_jobs':
      return handleJobsSearch(input.query || prompt, request, context, stream, token, shared);

    case 'job_detail':
      return handleJobDetail(input.jobName, request, context, stream, token, shared);

    case 'deal_lookup':
      return handleDealLookup(input.query, request, context, stream, token, shared);

    case 'validate_email':
      return handleJobsValidate('', request, context, stream, token, shared);

    case 'validate_sftp':
      return handleJobsValidateSftp('', request, context, stream, token, shared);

    case 'templates':
      return handleJobTemplates('', request, context, stream, token, shared);

    case 'create_job':
      return handleJobCreate(
        input.newName     || '',
        input.templateJob || '',
        input.overrides   || {},
        input.xmlType     || 'email',
        request, context, stream, token, shared
      );

    case 'edit_job':
      return handleJobEdit(
        input.jobName  || '',
        input.field    || '',
        input.value    || '',
        input.xmlType  || 'email',
        request, context, stream, token, shared
      );

    case 'servicer_dossier': {
      const synth = { ...request, prompt: input.query || prompt };
      return handleDealsCommand(synth, context, stream, token, shared);
    }

    case 'coverage_gaps':
      return handleCoverageGaps(input.focus || 'all', request, context, stream, token, shared);

    case 'orphan_detection':
      return handleOrphanDetection('', request, context, stream, token, shared);

    case 'collision_detection':
      return handleCollisionDetection('', request, context, stream, token, shared);

    case 'sync_logs': {
      const synth = { ...request, prompt: 'sync' };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'daily_summary': {
      const dateStr = input.date ? `summary ${input.date}` : 'summary';
      const synth = { ...request, prompt: dateStr };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'did_failures': {
      const synth = { ...request, prompt: 'failures' };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'job_health': {
      const jn = input.jobName || '';
      const synth = { ...request, prompt: `health ${jn}`.trim() };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'deal_activity': {
      const did = input.did || '';
      const synth = { ...request, prompt: `deal ${did}`.trim() };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'log_trends': {
      const synth = { ...request, prompt: 'trends' };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'log_performance': {
      const synth = { ...request, prompt: 'performance' };
      return handleLogsCommand(synth, context, stream, token, shared);
    }

    case 'save_settings': {
      const sub = input.type === 'sftp' ? 'save sftp' : 'save';
      const synth = { ...request, prompt: sub };
      return handleDeployCommand(synth, context, stream, token, shared);
    }

    case 'list_backups': {
      const synth = { ...request, prompt: 'list' };
      return handleDeployCommand(synth, context, stream, token, shared);
    }

    case 'xml_diff': {
      const synth = { ...request, prompt: 'diff' };
      return handleDeployCommand(synth, context, stream, token, shared);
    }

    case 'rollback':
      return handleRollback(input.backupFile || '', request, context, stream, token, shared);

    case 'triage_email': {
      const triagePrompt = buildTriagePrompt(input);
      const synth = { ...request, prompt: triagePrompt };
      return handleTriageCommand(synth, context, stream, token, shared);
    }

    case 'consolidation_analysis': {
      const synth = { ...request, prompt: 'consolidation' };
      return handleAnalyzeCommand(synth, context, stream, token, shared);
    }

    case 'impact_analysis': {
      const changeSpec = {
        change_type:         input.changeType     || '',
        target_job:          input.targetJob      || '',
        new_value:           input.newValue       || '',
        current_value:       input.currentValue   || '',
        affected_servicers:  input.affectedServicers || [],
        dry_run:             input.dryRun !== false,
      };
      return handleAnalyzeImpact(changeSpec, request, context, stream, token, shared);
    }

    case 'system_health': {
      const synth = { ...request, prompt: 'health' };
      return handleAnalyzeCommand(synth, context, stream, token, shared);
    }

    case 'agent_status':
      return handleStatusIntent(stream, shared);

    // --- Phase 5: tblTemplateStaging tools ---
    case 'template_status':
      return handleTemplateStatus(input, request, context, stream, token, shared);

    case 'processing_history':
      return handleProcessingHistory(input, request, context, stream, token, shared);

    case 'failure_analysis':
      return handleFailureAnalysis(input, request, context, stream, token, shared);

    case 'source_trace':
      return handleSourceTrace(input, request, context, stream, token, shared);

    case 'manual_queue':
      return handleManualQueue(input, request, context, stream, token, shared);

    case 'processing_duration':
      return handleProcessingDuration(input, request, context, stream, token, shared);

    case 'deal_pipeline':
      return handleDealPipeline(input, request, context, stream, token, shared);

    case 'staging_search':
      return handleStagingSearch(input, request, context, stream, token, shared);

    default:
    shared.outputChannel.appendLine(`[FRP]   └─ ✗ Unknown tool: ${toolName}`);
      stream.markdown(`⚠️ Unknown tool: ${toolName}. Please try rephrasing your question.\n`);
      return {};
  }
}

// ---------------------------------------------------------------------------
// Tool call detection — robust across all LLM providers
// ---------------------------------------------------------------------------

/**
 * Extract a tool call from a stream part.
 *
 * Uses instanceof when available, but also falls back to duck-typing
 * (checking for .name + .callId properties) to handle cases where
 * the LanguageModelToolCallPart class differs between module boundaries
 * or LLM providers.
 *
 * @param {Object} part  A part from the LLM response stream
 * @returns {{ name: string, input: Object, callId: string }|null}
 */
function _extractToolCall(part) {
  // Primary check — official API
  if (vscode.LanguageModelToolCallPart && part instanceof vscode.LanguageModelToolCallPart) {
    return { name: part.name, input: part.input || {}, callId: part.callId };
  }
  // Duck-typing fallback — works when instanceof fails across contexts
  if (part && typeof part.name === 'string' && typeof part.callId === 'string' && part.name) {
    return { name: part.name, input: part.input || {}, callId: part.callId };
  }
  return null;
}

/**
 * Stage 2: Route within a classified category using scoped tool-calling.
 *
 * Filters FRP_TOOLS to only the tools in the given category, then sends
 * the prompt to the LLM with this reduced tool set.
 *
 * @param {string} category  The category from Stage 1 (e.g., "deal_mapping")
 * @param {string} prompt    The user's question
 * @param {Object} request   VS Code ChatRequest
 * @param {Object} context   VS Code ChatContext
 * @param {Object} stream    VS Code ChatResponseStream
 * @param {Object} token     CancellationToken
 * @param {Object} shared    Shared extension context
 * @returns {Promise<Object|null>} ChatResult if handled, null if no tool selected
 */
async function routeWithinCategory(category, prompt, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) return null;

  const toolNames = CATEGORY_TOOLS[category];
  const scopedTools = FRP_TOOLS.filter(t => toolNames.includes(t.name));

  shared.outputChannel.appendLine(
    `[FRP]   ├─ Stage 2: Tool Selection (${scopedTools.length} tools in "${category}")`
  );

  const categoryDef = INTENT_CATEGORIES.find(c => c.name === category);
  const categoryContext = categoryDef
    ? `You are routing within the "${categoryDef.displayName}" category. ${categoryDef.description}`
    : '';

  const systemContent = [
    SYSTEM_PROMPT,
    '',
    DOMAIN_KNOWLEDGE,
    '',
    categoryContext,
    '',
    'Select the best tool and extract the correct parameters from the prompt.',
    'You MUST call exactly one tool.',
    'For numeric IDs (CompanyID, ServicerID), extract ONLY the number (e.g. "296"), not the label.',
    'IMPORTANT — Anaphora resolution: If the user uses pronouns or references like "this job", "this deal", "it", "the job", "this servicer", resolve them to the EXPLICIT named entity stated earlier in the SAME message. For example: "list all jobs with job name CMBS_GreyCo and also deals associated with this job" → extract jobName = "CMBS_GreyCo" (not "this job").',
    'If the user references previous results, extract identifiers from conversation history.',
  ].join('\n');

  const messages = buildMessageHistory(context, systemContent, prompt);

  const sendOptions = { tools: scopedTools };

  try {
    const response = await model.sendRequest(messages, sendOptions, token);

    for await (const part of response.stream) {
      const toolCall = _extractToolCall(part);
      if (toolCall) {
        shared.outputChannel.appendLine(
          `[FRP]   │  Selected: ${toolCall.name}(${JSON.stringify(toolCall.input)})`
        );
        return executeToolCall(toolCall.name, toolCall.input || {}, request, context, stream, token, shared, prompt);
      }
    }

    shared.outputChannel.appendLine('[FRP]   │  ✗ LLM did not select any tool');
    return null;

  } catch (err) {
    shared.outputChannel.appendLine(`[FRP]   │  ✗ Stage 2 error: ${err.message}`);
    return null;
  }
}

/**
 * Fallback: Single-stage router using full FRP_TOOLS array (36 tools).
 *
 * This is the CURRENT routing logic, preserved as a fallback.
 * Called when Stage 1 classification fails (bad JSON, unknown category, error).
 *
 * @returns {Promise<Object|null>} ChatResult if handled, null if LLM declined tools
 */
async function routeWithAllTools(prompt, request, context, stream, token, shared, historyContext, model) {
  const systemContent = [
    SYSTEM_PROMPT,
    '',
    DOMAIN_KNOWLEDGE,
    '',
    'You are routing the user\'s question to the correct backend tool.',
    'Use the data model above to select the BEST tool.',
    'You MUST call exactly one tool. Extract the correct parameters from the prompt.',
    'For numeric IDs (CompanyID, ServicerID), extract ONLY the number (e.g. "296"), not the label.',
    'If the user references previous results, extract identifiers from conversation history.',
  ].join('\n');

  const messages = buildMessageHistory(context, systemContent, prompt);

  const sendOptions = { tools: FRP_TOOLS };

  try {
    shared.outputChannel.appendLine(
      `[FRP] routeWithAllTools: sending request (model=${model.name || model.family}, tools=${FRP_TOOLS.length})`
    );

    const response = await model.sendRequest(messages, sendOptions, token);

    let partCount = 0;
    for await (const part of response.stream) {
      partCount++;
      const toolCall = _extractToolCall(part);
      if (toolCall) {
        shared.outputChannel.appendLine(
          `[FRP] routeWithAllTools selected: ${toolCall.name} input=${JSON.stringify(toolCall.input)}`
        );
        return executeToolCall(toolCall.name, toolCall.input || {}, request, context, stream, token, shared, prompt);
      }
      // Log first few non-tool parts for diagnostics
      if (partCount <= 3) {
        const partType = part?.constructor?.name || typeof part;
        const partKeys = part && typeof part === 'object' ? Object.keys(part).join(',') : '';
        shared.outputChannel.appendLine(
          `[FRP] routeWithAllTools stream part #${partCount}: type=${partType} keys=[${partKeys}]`
        );
      }
    }

    shared.outputChannel.appendLine('[FRP] routeWithAllTools: no tool selected');
    return null;

  } catch (err) {
    shared.outputChannel.appendLine(`[FRP] routeWithAllTools error: ${err.message}`);
    return null;
  }
}

// ---------------------------------------------------------------------------
// ReAct Pipeline Orchestrator
// ---------------------------------------------------------------------------

/**
 * ReAct (Reasoning + Acting) loop for multi-step pipeline queries.
 *
 * Sends the pipeline's playbook as a system prompt along with the user's
 * question, then iterates: the LLM calls tools one at a time, observes
 * results, and decides what to do next. The loop ends when the LLM
 * produces a text response (its final report) or hits maxSteps.
 *
 * @param {string}  prompt       The user's natural-language question
 * @param {Object}  pipelineDef  Pipeline definition from PIPELINE_DEFINITIONS
 * @param {Object}  request      VS Code ChatRequest
 * @param {Object}  context      VS Code ChatContext
 * @param {Object}  stream       VS Code ChatResponseStream
 * @param {Object}  token        CancellationToken
 * @param {Object}  shared       Shared extension context
 * @returns {Promise<Object>}    ChatResult with optional follow-up suggestions
 */
async function reactLoop(prompt, pipelineDef, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('Unable to select a language model for pipeline analysis.');
    return {};
  }

  // Build scoped tool set from the pipeline's tool list (null = all tools)
  const scopedTools = pipelineDef.tools
    ? FRP_TOOLS.filter(t => pipelineDef.tools.includes(t.name))
    : FRP_TOOLS;

  shared.outputChannel.appendLine(
    `[FRP] ReAct: starting pipeline "${pipelineDef.name}" (max ${pipelineDef.maxSteps} steps, ${scopedTools.length} tools)`
  );

  // Seed the message array with system prompt (playbook) + user question
  const systemContent = `${pipelineDef.playbook}\n\n---`;
  const messages = buildMessageHistory(context, systemContent, prompt);

  const stepResults = []; // Accumulated for compilePipelineReport fallback
  let step = 0;

  // ── Main ReAct loop ──
  while (step < pipelineDef.maxSteps) {
    step++;

    let response;
    try {
      response = await model.sendRequest(messages, { tools: scopedTools }, token);
    } catch (err) {
      shared.outputChannel.appendLine(`[FRP] ReAct: LLM error at step ${step}: ${err.message}`);
      break;
    }

    let toolCallMade = false;
    let finalText = '';
    let reasoningText = ''; // Intermediate "think" text before a tool call

    for await (const part of response.stream) {
      const toolCall = _extractToolCall(part);
      if (toolCall) {
        // Surface any reasoning the LLM produced before deciding on this tool call
        if (reasoningText.trim()) {
          shared.outputChannel.appendLine(
            `[FRP] ReAct step ${step} reasoning: ${reasoningText.trim().slice(0, 200)}`
          );
          // Show lightweight "thinking" indicator to the user (collapsed — not the full report)
          stream.markdown(`> 🔍 *${reasoningText.trim().replace(/\n+/g, ' ').slice(0, 300)}*\n\n`);
          reasoningText = '';
        }

        toolCallMade = true;
        const toolName = toolCall.name;
        const toolInput = toolCall.input || {};

        shared.outputChannel.appendLine(
          `[FRP] ReAct step ${step}: ${toolName}(${JSON.stringify(toolInput)})`
        );
        stream.progress(`Step ${step}: calling ${toolName}...`);

        // Execute the tool and capture the result
        let result;
        try {
          result = await executePipelineTool(toolName, toolInput, request, stream, token, shared);
        } catch (err) {
          result = { success: false, error: err.message };
          shared.outputChannel.appendLine(
            `[FRP] ReAct step ${step}: tool error: ${err.message}`
          );
        }

        stepResults.push({
          step,
          tool: toolName,
          input: toolInput,
          result,
        });

        // Append assistant tool-call + tool result to message history
        messages.push(
          vscode.LanguageModelChatMessage.Assistant([
            new vscode.LanguageModelToolCallPart(toolCall.callId, toolName, toolInput)
          ])
        );
        messages.push(
          makeToolResultMessage(
            toolCall.callId,
            typeof result === 'string' ? result : JSON.stringify(result)
          )
        );

      } else {
        // Text part — either intermediate reasoning or the final answer.
        // We don't know which until the loop ends (tool call = reasoning; no tool call = final answer).
        const text = typeof part === 'string' ? part : (part.value || '');
        if (toolCallMade) {
          // Text arriving AFTER a tool call in the same response — treat as reasoning for next step
          reasoningText += text;
        } else {
          // Text arriving BEFORE any tool call — could be reasoning OR final answer
          finalText += text;
          reasoningText += text; // Mirror: if a tool call follows, we'll surface this as reasoning
        }
      }
    }

    // If no tool was called, the LLM is done — finalText is the final report
    if (!toolCallMade) {
      // ── crud_planning Phase 1 plan detection (TRD §7.4) ──
      if (pipelineDef.name === 'crud_planning' && step === 1 && finalText.includes('PLAN:')) {
        stream.markdown(`\n${finalText}\n`);
        shared.pendingOperation = {
          type: 'crud_plan',
          params: { planText: finalText, messages: [...messages] },
        };
        stream.markdown('\n**Confirm this plan?**\n');
        if (typeof stream.button === 'function') {
          stream.button({ title: 'Confirm ✓', command: 'frp.confirmPending' });
          stream.button({ title: 'Cancel ✗', command: 'frp.cancelPending' });
        } else {
          stream.markdown('Type **yes** to confirm or **no** to cancel.\n');
        }
        return { followUps: [] };
      }

      if (finalText.trim()) {
        shared.outputChannel.appendLine(
          `[FRP] ReAct: LLM produced final report at step ${step} (${finalText.length} chars)`
        );
        stream.markdown(finalText);
      } else {
        shared.outputChannel.appendLine('[FRP] ReAct: LLM returned empty response — compiling fallback');
        stream.markdown(compilePipelineReport(stepResults, pipelineDef));
      }
      return buildPipelineResult(stepResults);
    }
  }

  // Hit maxSteps without a final text response
  shared.outputChannel.appendLine(
    `[FRP] ReAct: hit max steps (${pipelineDef.maxSteps}) — compiling partial report`
  );
  stream.markdown(compilePipelineReport(stepResults, pipelineDef));
  return buildPipelineResult(stepResults);
}

/**
 * Build a ChatResult with follow-up suggestions based on pipeline step results.
 * @param {Array} stepResults  Accumulated step results from the ReAct loop
 * @returns {Object} ChatResult
 */
function buildPipelineResult(stepResults) {
  return {};
}

/**
 * Execute a tool within the ReAct pipeline and return the raw result.
 *
 * Unlike executeToolCall() (which streams formatted markdown to the user),
 * this function returns the raw JSON result so the LLM can process it
 * in the next ReAct iteration.
 *
 * @param {string}  toolName   Name of the tool to execute
 * @param {Object}  toolInput  Input parameters for the tool
 * @param {Object}  request    VS Code ChatRequest
 * @param {Object}  stream     VS Code ChatResponseStream (for progress only)
 * @param {Object}  token      CancellationToken
 * @param {Object}  shared     Shared extension context
 * @returns {Promise<Object>}  Raw tool result (success/error object)
 */
async function executePipelineTool(toolName, toolInput, request, stream, token, shared) {
  // Special case: triage_email routes through backendCall('triage_verify')
  if (toolName === 'triage_email') {
    const triagePrompt = buildTriagePrompt(toolInput);
    const msgPath = extractMsgPath(triagePrompt.replace(/^(new|verify|match)\s*/i, ''));
    if (msgPath) {
      const result = await backendCall('triage_verify', { msgPath }, shared);
      return result;
    }
    return { success: false, error: 'triage_email requires a .msg file path in the prompt' };
  }

  const toolArgs = buildToolArgs(toolName, toolInput);
  if (!toolArgs) {
    return { success: false, error: `Could not build args for tool: ${toolName}` };
  }

  const result = await backendCall(toolArgs.command, toolArgs.params, shared);

  // Truncate large results to prevent context bloat
  const resultStr = JSON.stringify(result);
  if (resultStr.length > 4000) {
    shared.outputChannel.appendLine(
      `[FRP] ReAct: truncating large tool result (${resultStr.length} chars → 4000)`
    );
    // Return a truncated version that preserves key metadata
    const truncated = { ...result, _truncated: true };
    if (result.data && Array.isArray(result.data)) {
      truncated.data = result.data.slice(0, 10);
      truncated._totalRecords = result.data.length;
    }
    return truncated;
  }

  return result;
}

/**
 * Compile a markdown report from accumulated ReAct step results.
 *
 * Called only when the ReAct loop hits maxSteps without the LLM producing
 * a final text answer. Generates a structured report from the raw
 * tool call/result pairs collected during the loop.
 *
 * @param {Array}  stepResults   Array of { step, tool, input, result }
 * @param {Object} pipelineDef   Pipeline definition (for display name)
 * @returns {string}             Markdown report
 */
function compilePipelineReport(stepResults, pipelineDef) {
  const lines = [
    `## ${pipelineDef.displayName} — Partial Report`,
    '',
    `> ⚠️ Analysis reached the maximum step limit (${pipelineDef.maxSteps}). ` +
    `Results below may be incomplete.`,
    '',
  ];

  if (stepResults.length === 0) {
    lines.push('No tool calls were completed before the limit was reached.');
    return lines.join('\n');
  }

  for (const sr of stepResults) {
    const status = sr.result && sr.result.success !== false ? '✅' : '❌';
    lines.push(`### Step ${sr.step}: ${sr.tool} ${status}`);
    lines.push('');

    // Input parameters
    const inputStr = Object.entries(sr.input)
      .map(([k, v]) => `\`${k}\`: ${v}`)
      .join(', ');
    if (inputStr) {
      lines.push(`**Input:** ${inputStr}`);
    }

    // Result summary
    if (sr.result && sr.result.success === false) {
      lines.push(`**Error:** ${sr.result.error || 'Unknown error'}`);
    } else if (sr.result && sr.result.data) {
      const data = sr.result.data;
      if (Array.isArray(data)) {
        lines.push(`**Result:** ${data.length} record(s) returned`);
      } else {
        lines.push(`**Result:** Data returned successfully`);
      }
    } else {
      lines.push(`**Result:** ${JSON.stringify(sr.result).substring(0, 200)}`);
    }

    lines.push('');
  }

  lines.push('---');
  lines.push('*This is an auto-generated partial report. Ask a follow-up question for additional analysis.*');

  return lines.join('\n');
}

/**
 * Route a natural-language prompt through Two-Stage Intent Routing.
 *
 * Stage 1: Classify intent into one of 6 categories (lightweight LLM call).
 * Stage 2: Select tool from category-scoped tool subset (tool-calling LLM call).
 * Fallback: If Stage 1 fails, use the full 36-tool single-stage router.
 *
 * @returns {Promise<Object|null>} ChatResult if handled, null if LLM declined tools
 */
/**
 * Build a tool-result message for the LLM conversation history.
 * The VS Code API uses LanguageModelToolResultPart inside a User message.
 */
function makeToolResultMessage(callId, content) {
  return vscode.LanguageModelChatMessage.User([
    new vscode.LanguageModelToolResultPart(callId, [
      new vscode.LanguageModelTextPart(content)
    ])
  ]);
}

async function routeWithToolCalling(prompt, request, context, stream, token, shared) {

  const banner = '═'.repeat(56);
  shared.outputChannel.appendLine(`[FRP] ${banner}`);
  shared.outputChannel.appendLine(`[FRP] ROUTING START — "${prompt.slice(0, 80)}"`);
  shared.outputChannel.appendLine(`[FRP] ${banner}`);

  // ── Guard: check that the tool-calling API classes exist ──
  if (typeof vscode.LanguageModelToolCallPart === 'undefined') {
    shared.outputChannel.appendLine(
      '[FRP]   ✗ BLOCKED: LanguageModelToolCallPart API not available'
    );
    return null;
  }

  const model = await selectModel(request);
  if (!model) {
    shared.outputChannel.appendLine('[FRP]   ✗ BLOCKED: No LLM model available');
    return null;
  }

  const modelName = model.name || model.family || model.id || 'unknown';
  shared.outputChannel.appendLine(
    `[FRP]   Model: ${modelName} (vendor=${model.vendor || 'unknown'})`,
  );

  if (model.capabilities && model.capabilities.toolCalling === false) {
    shared.outputChannel.appendLine(
      `[FRP]   ✗ BLOCKED: Model "${modelName}" does not support tool-calling`
    );
    return null;
  }

  const historyContext = buildConversationContext(context);

  // ── Stage 1: Intent Classification (with one retry) ──
  shared.outputChannel.appendLine('[FRP]   ┌─ Stage 1: Intent Classification');
  let classification = await classifyIntent(prompt, historyContext, model, token, shared);
  if (!classification) {
    shared.outputChannel.appendLine('[FRP]   │  Attempt 1 failed — retrying');
    classification = await classifyIntent(prompt, historyContext, model, token, shared);
  }

  if (!classification) {
    shared.outputChannel.appendLine('[FRP]   │  ✗ FAILED after 2 attempts');
    shared.outputChannel.appendLine('[FRP]   └─ ROUTING END: classification failed');
    stream.markdown(
      '⚠️ I could not classify your question. Please try rephrasing, or try again.'
    );
    return { metadata: { command: 'frp' } };
  }

  const { category, mode, pipeline } = classification;
  shared.outputChannel.appendLine(`[FRP]   │  Category: ${category} | Mode: ${mode} | Pipeline: ${pipeline || 'none'}`);

  // Phase 8: ReAct pipeline mode
  if (mode === 'pipeline') {
    const pipelineName = (pipeline && PIPELINE_DEFINITIONS[pipeline]) ? pipeline : 'general_reasoning';
    const pipelineDef = PIPELINE_DEFINITIONS[pipelineName];
    if (pipelineDef) {
      shared.outputChannel.appendLine(
        `[FRP]   └─ Routing to ReAct pipeline: ${pipelineDef.displayName}`
      );
      return reactLoop(prompt, pipelineDef, request, context, stream, token, shared);
    }
    shared.outputChannel.appendLine(`[FRP]   │  Pipeline "${pipelineName}" not found — falling to Stage 2`);
  }

  // Phase 7: Single-tool mode
  const result = await routeWithinCategory(category, prompt, request, context, stream, token, shared);
  if (result !== null) {
    return result;
  }
  // Stage 2 failed — tell the user, don't silently degrade
  shared.outputChannel.appendLine(`[FRP]   │  ✗ No tool selected`);
  shared.outputChannel.appendLine(`[FRP]   └─ ROUTING END: Stage 2 failed for "${category}"`);
  stream.markdown(
    `⚠️ I classified your question as **${category}** but could not select the right tool. Please try rephrasing.`
  );
  return { metadata: { command: 'frp' } };
}

// ---------------------------------------------------------------------------
// Model selection
// ---------------------------------------------------------------------------

const MODEL_PREFERENCE = ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini'];

/**
 * Select the best available LLM model.
 * Priority: request.model → user setting → auto-detect from available models.
 */
async function selectModel(request) {
  // 1. If the request already has a model attached, use it
  if (request.model) return request.model;

  // 2. Check user setting
  const config = vscode.workspace.getConfiguration('frpAgent');
  const modelSetting = config.get('model', 'auto');

  if (modelSetting !== 'auto') {
    try {
      const [model] = await vscode.lm.selectChatModels({ family: modelSetting });
      if (model) return model;
    } catch (_) {
      // fall through to auto-detect
    }
  }

  // 3. Auto-detect: try models in preference order
  for (const family of MODEL_PREFERENCE) {
    try {
      const [model] = await vscode.lm.selectChatModels({ family });
      if (model) return model;
    } catch (_) {
      // continue
    }
  }

  // 4. Absolute fallback — grab any available model
  try {
    const all = await vscode.lm.selectChatModels();
    if (all.length > 0) return all[0];
  } catch (_) {
    // nothing available
  }

  return null;
}

// ---------------------------------------------------------------------------
// LLM generation helpers
// ---------------------------------------------------------------------------

/**
 * Stream an LLM answer into the chat response.
 * Uses User() messages only (no System()) for maximum compatibility.
 *
 * @param {string}   prompt   The full prompt including system instructions
 * @param {Object}   request  The chat request
 * @param {Object}   stream   The chat response stream
 * @param {import('vscode').CancellationToken} token
 * @returns {Promise<string>} The full generated text
 */
async function generateAnswer(prompt, request, stream, token) {
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('⚠️ No language model available. Please ensure GitHub Copilot is active.\n');
    return '';
  }

  const messages = [vscode.LanguageModelChatMessage.User(prompt)];

  const chatResponse = await model.sendRequest(messages, {}, token);

  let fullText = '';
  for await (const fragment of chatResponse.text) {
    stream.markdown(fragment);
    fullText += fragment;
  }

  return fullText;
}

/**
 * Build conversation context from recent chat history (last 6 turns).
 */
function buildConversationContext(context) {
  if (!context || !context.history || context.history.length === 0) return '';

  const recent = context.history.slice(-6);
  const lines = ['## Recent conversation'];

  for (const turn of recent) {
    if (turn instanceof vscode.ChatRequestTurn) {
      lines.push(`**User:** ${turn.prompt}`);
    } else if (turn instanceof vscode.ChatResponseTurn) {
      // Extract text parts from the response
      const parts = [];
      for (const part of turn.response) {
        if (part instanceof vscode.ChatResponseMarkdownPart) {
          parts.push(part.value.value);
        }
      }
      if (parts.length) {
        lines.push(`**Assistant:** ${parts.join('').slice(0, 2000)}`);
      }
    }
  }

  return lines.join('\n');
}

/**
 * Build a LanguageModelChatMessage[] array from conversation history.
 * Replaces the plain-string historyContext injection in LLM calls.
 * The LLM receives a proper multi-turn conversation object.
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
    const recent = context.history.slice(-6);
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

/**
 * Extract the current value of a field from a job_detail result.
 * Handles both flat fields and nested fields (scrubber/template).
 */
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

/**
 * Render a before/after diff in the chat stream for a single field edit.
 */
function renderEditDiff(jobName, field, currentValue, newValue, xmlType) {
  const isNested = (field === 'scrubber' || field === 'template');
  let beforeXml, afterXml;

  if (isNested) {
    beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
    afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
  } else {
    const tagMap = {
      // Email fields
      servicer_id:        'ServicerID',
      mailbox:            'MailboxAddress',
      folder:             'Folder',
      sme:                'SME',
      save_location:      'SaveLocation',
      import_did:         'ImportDID',
      subject_filter:     'SubjectFilter',
      sender_filter:      'SenderFilter',
      day_adjust:         'DayAdjust',
      name:               'Name',
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

/**
 * Build a triage prompt string from structured triage_email tool parameters.
 * The result is compatible with handleTriageCommand's sub-command regex dispatch.
 */
function buildTriagePrompt(input) {
  const mode = (input.mode || 'new').toLowerCase();

  if (input.msgPath) {
    return `${mode} ${input.msgPath}`;
  }

  const parts = [mode];
  if (input.sender)  parts.push(`from:${input.sender}`);
  if (input.subject) parts.push(`subject:${input.subject}`);
  if (input.body)    parts.push(`body:${input.body.slice(0, 500)}`);
  return parts.join(' ');
}

/**
 * Execute a confirmed edit_job operation (called after user confirms).
 */
async function executeConfirmedEdit({ jobName, field, value, xmlType }, request, context, stream, token, shared) {
  stream.progress(`Editing job "${jobName}"...`);
  const data = await backendCall('edit_job', { jobName, field, value, xmlType: xmlType || 'email' }, shared);
  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }
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

/**
 * Execute a confirmed create_job operation (called after user confirms).
 */
async function executeConfirmedCreate({ newName, templateJob, overrides, xmlType }, request, context, stream, token, shared) {
  stream.progress('Creating job...');
  const data = await backendCall('create_job', {
    templateJob,
    name: newName,
    overrides: overrides || {},
    xmlType: xmlType || 'email',
  }, shared);
  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }
  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `A new job "${newName}" was created from template "${templateJob}" (${xmlType || 'email'}).`,
    'Show the result with the new job details and validation status.',
    'Use ✅ or ❌ for validation. Show backup file created.',
  ].join('\n');
  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);
  return {
    followUps: [
      { prompt: `/jobs edit "${newName}" set servicer_id `, label: `Edit ${newName}` },
      { prompt: 'validate all jobs', label: 'Validate all jobs' },
    ],
  };
}

/**
 * Execute a confirmed rollback operation (called after user confirms).
 */
async function executeConfirmedRollback({ backupFile }, request, context, stream, token, shared) {
  stream.progress('Rolling back...');
  const data = await backendCall('rollback_xml', { backupFile }, shared);
  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Rollback failed:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }
  const resultPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `Settings.xml was rolled back to "${backupFile}".`,
    'Show: safety backup created, restored from, validation result.',
  ].join('\n');
  await generateOrFallback(resultPrompt, data, 'deploy', request, stream, token);
  return {
    followUps: [
      { prompt: 'what changed since last deploy', label: 'Verify with diff' },
      { prompt: 'validate all jobs', label: 'Validate restored jobs' },
    ],
  };
}

/**
 * Resume a confirmed CRUD planning pipeline — sends "Confirmed. Execute the plan."
 * into the saved message history and relaunches the reactLoop for Phase 2 execution.
 */
async function executeConfirmedCrudPlan({ planText, messages }, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('Unable to select a language model for plan execution.');
    return { followUps: [] };
  }

  const pipelineDef = PIPELINE_DEFINITIONS.crud_planning;
  const scopedTools = FRP_TOOLS.filter(t => pipelineDef.tools.includes(t.name));

  // Append confirmation to saved message history
  messages.push(vscode.LanguageModelChatMessage.User('Confirmed. Execute the plan.'));

  const stepResults = [];
  let step = 0;

  while (step < pipelineDef.maxSteps) {
    step++;

    let response;
    try {
      response = await model.sendRequest(messages, { tools: scopedTools }, token);
    } catch (err) {
      shared.outputChannel.appendLine(`[FRP] CrudPlan: LLM error at step ${step}: ${err.message}`);
      break;
    }

    let toolCallMade = false;
    let finalText = '';

    for await (const part of response.stream) {
      const toolCall = _extractToolCall(part);
      if (toolCall) {
        toolCallMade = true;
        const toolName = toolCall.name;
        const toolInput = toolCall.input || {};

        stream.progress(`Plan step ${step}: ${toolName}...`);

        let result;
        try {
          result = await executePipelineTool(toolName, toolInput, request, stream, token, shared);
        } catch (err) {
          result = { success: false, error: err.message };
        }

        stepResults.push({ step, tool: toolName, input: toolInput, result });

        messages.push(
          vscode.LanguageModelChatMessage.Assistant([
            new vscode.LanguageModelToolCallPart(toolCall.callId, toolName, toolInput)
          ])
        );
        messages.push(
          makeToolResultMessage(
            toolCall.callId,
            typeof result === 'string' ? result : JSON.stringify(result)
          )
        );
      } else {
        const text = typeof part === 'string' ? part : (part.value || '');
        finalText += text;
      }
    }

    if (!toolCallMade) {
      if (finalText.trim()) {
        stream.markdown(finalText);
      } else {
        stream.markdown(compilePipelineReport(stepResults, pipelineDef));
      }
      return buildPipelineResult(stepResults);
    }
  }

  stream.markdown(compilePipelineReport(stepResults, pipelineDef));
  return buildPipelineResult(stepResults);
}

/**
 * Handle a structured impact analysis request directly (bypasses parseChangeIntent).
 */
async function handleAnalyzeImpact(changeSpec, request, context, stream, token, shared) {
  if (!changeSpec.change_type || !changeSpec.target_job) {
    stream.markdown('Missing required parameters: changeType and targetJob are required for impact analysis.\n');
    return { followUps: [] };
  }

  stream.progress('Simulating impact...');
  const data = await backendCall('analyze_impact', changeSpec, shared);
  if (!data?.success) {
    stream.markdown(`❌ **Error:** ${(data?.errors || []).join(', ') || 'Unknown error'}\n`);
    return { followUps: [] };
  }
  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
    'Format this impact analysis as a risk assessment.',
    'Highlight affected entities, coverage changes, and recommendation.',
    'Use risk badges: 🟢 low, 🟡 medium, 🔴 high.',
  ].join('\n');
  await generateOrFallback(llmPrompt, data.data, 'analyze', request, stream, token);
  return {
    followUps: [
      { prompt: 'system health report', label: 'Full health check' },
      { prompt: 'consolidation analysis', label: 'Consolidation' },
    ],
  };
}

// ---------------------------------------------------------------------------
// Raw data formatting (fallback when LLM is unavailable)
// ---------------------------------------------------------------------------

/**
 * Format raw backend data as Markdown when the LLM is not available.
 */
function formatRawData(data, command) {
  if (!data) return '_No data returned._\n';

  // Jobs — render as a table with curated fields
  if (command === 'jobs' && Array.isArray(data.jobs)) {
    if (data.jobs.length === 0) return '_No jobs matched your query._\n';

    // Summary groups if available
    const lines = [`**${data.jobs.length} job(s) found**\n`];
    if (data.groups_by_scrubber) {
      const groups = Object.entries(data.groups_by_scrubber)
        .sort(([, a], [, b]) => b - a)
        .map(([t, n]) => `${t} (${n})`)
        .join(', ');
      lines.push(`**By template:** ${groups}\n`);
    }

    lines.push('| JobName | Sender | ServicerID | Scrubber | MatchMode | SavePath |');
    lines.push('|---------|--------|------------|----------|-----------|----------|');

    const rows = data.jobs.map((j) => {
      const name = j.job_name || j.name || '—';
      const sender = j.sender || '—';
      const sid = j.servicer_id ?? '—';
      const tmpl = j.scrubber || j.template || '—';
      const mode = j.match_mode || '—';
      const path = j.save_path || j.save_location || '—';
      return `| ${name} | ${sender} | ${sid} | ${tmpl} | ${mode} | \`${path}\` |`;
    });

    return [...lines, ...rows, ''].join('\n');
  }

  // Validation results
  if (command === 'validate' && Array.isArray(data.results)) {
    const rows = data.results.map((r) => {
      const icon = r.status === 'pass' || r.passed ? '✅' : '❌';
      const name = r.check || r.rule || r.name || '—';
      const detail = r.message || r.detail || '';
      return `${icon} **${name}** — ${detail}`;
    });
    return rows.join('\n') + '\n';
  }

  // Deals / servicer dossier
  if (command === 'deals' && (data.servicer || data.deals)) {
    const d = data.servicer || data;
    const lines = ['**Servicer Dossier**\n'];
    for (const [key, val] of Object.entries(d)) {
      if (typeof val === 'object' && val !== null) {
        lines.push(`**${key}:**`);
        if (Array.isArray(val)) {
          val.forEach((item) => lines.push(`  - ${typeof item === 'string' ? item : JSON.stringify(item)}`));
        } else {
          for (const [k2, v2] of Object.entries(val)) {
            lines.push(`  - ${k2}: ${v2}`);
          }
        }
      } else {
        lines.push(`- **${key}:** ${val}`);
      }
    }
    return lines.join('\n') + '\n';
  }

  // Logs
  if (command === 'logs' && (data.entries || data.logs)) {
    const entries = data.entries || data.logs || [];
    if (entries.length === 0) return '_No log entries found._\n';
    const rows = entries.slice(0, 30).map((e) => {
      const ts = e.timestamp || e.date || '—';
      const level = e.level || 'INFO';
      const msg = (e.message || '').slice(0, 120);
      return `| ${ts} | ${level} | ${msg} |`;
    });
    return [
      `**${entries.length} log entries** (showing first ${Math.min(entries.length, 30)})\n`,
      '| Timestamp | Level | Message |',
      '|-----------|-------|---------|',
      ...rows,
      '',
    ].join('\n');
  }

  // Deploy / backups
  if (command === 'deploy' && (data.backups || data.result)) {
    if (data.backups) {
      const rows = data.backups.map((b) => `- ${b.filename || b.name} — ${b.date || b.timestamp || ''}`);
      return ['**Available backups:**\n', ...rows, ''].join('\n');
    }
    const msg = data.message || data.result || JSON.stringify(data);
    return `✅ ${msg}\n`;
  }

  // Staging / template runs — table of processing records
  if ((command === 'staging' || command === 'trace') && data.data) {
    const d = data.data;
    // If it has a runs/records array
    const records = d.records || d.runs || d.recent_runs || d.results || [];
    if (Array.isArray(records) && records.length > 0) {
      const lines = [];
      if (d.summary) {
        const s = d.summary;
        lines.push(`**Summary:** ${s.total_runs || s.total || '?'} runs, ${s.success_rate || '?'}% success rate\n`);
      }
      lines.push('| TemplateName | DID | Status | ProcessStarted | Duration | FilePath |');
      lines.push('|-------------|-----|--------|----------------|----------|----------|');
      records.slice(0, 50).forEach((r) => {
        const status = r.success || r.status === 'success' || r.status === 'Success' ? '✅' : '❌';
        lines.push(`| ${r.template_name || r.TemplateName || '—'} | ${r.did || r.DID || '—'} | ${status} | ${r.process_started || r.ProcessStarted || '—'} | ${r.duration || r.ProcessDuration || '—'} | \`${r.filepath || r.FilePath || '—'}\` |`);
      });
      return lines.join('\n') + '\n';
    }
    // Fallback for trace/source data
    if (d.source_type || d.queued_by) {
      return [
        `**Source:** ${d.source_type || '?'}`,
        `**Queued By:** ${d.queued_by || d.QueuedBy || '?'}`,
        `**Template:** ${d.template_name || d.TemplateName || '?'}`,
        `**Status:** ${d.status || '?'}`,
        '',
      ].join('\n');
    }
  }

  // Failures
  if (command === 'failures' && data.data) {
    const d = data.data;
    const lines = [];
    if (d.summary) {
      lines.push(`**${d.summary.total_failures || '?'} failures** (${d.summary.failure_rate || '?'}% failure rate)\n`);
    }
    const groups = d.failure_groups || d.groups || [];
    if (groups.length > 0) {
      lines.push('| Template | Count | Last Failure |');
      lines.push('|----------|-------|-------------|');
      groups.forEach((g) => {
        lines.push(`| ${g.template_name || '—'} | ${g.count || g.failure_count || '—'} | ${g.last_failure || '—'} |`);
      });
    }
    return lines.join('\n') + '\n';
  }

  // Manual queue
  if (command === 'manual_queue' && data.data) {
    const d = data.data;
    const lines = [`**Manual Queue Report**\n`];
    if (d.summary) {
      lines.push(`- Total runs: ${d.summary.total_runs || '?'}`);
      lines.push(`- Manual: ${d.summary.manual_count || '?'} (${d.summary.manual_pct || '?'}%)`);
      lines.push(`- Automated: ${d.summary.automated_count || '?'}\n`);
    }
    const byTemplate = d.by_template || [];
    if (byTemplate.length > 0) {
      lines.push('| Template | Manual | Automated | Manual % |');
      lines.push('|----------|--------|-----------|----------|');
      byTemplate.forEach((t) => {
        lines.push(`| ${t.template_name || '—'} | ${t.manual || '—'} | ${t.automated || '—'} | ${t.manual_pct || '—'}% |`);
      });
    }
    return lines.join('\n') + '\n';
  }

  // Duration
  if (command === 'duration' && data.data) {
    const d = data.data;
    const lines = [`**Processing Duration Analysis**\n`];
    if (d.overall) {
      lines.push(`- Avg: ${d.overall.avg_duration || '?'}s | Min: ${d.overall.min_duration || '?'}s | Max: ${d.overall.max_duration || '?'}s\n`);
    }
    const byTemplate = d.by_template || [];
    if (byTemplate.length > 0) {
      lines.push('| Template | Avg (s) | Min (s) | Max (s) | Runs |');
      lines.push('|----------|---------|---------|---------|------|');
      byTemplate.forEach((t) => {
        lines.push(`| ${t.template_name || '—'} | ${t.avg_seconds || '—'} | ${t.min_seconds || '—'} | ${t.max_seconds || '—'} | ${t.total_runs || '—'} |`);
      });
    }
    return lines.join('\n') + '\n';
  }

  // Pipeline
  if (command === 'pipeline' && data.data) {
    const d = data.data;
    const lines = [`**Pipeline View**\n`];
    if (d.health_score != null) {
      lines.push(`Health Score: **${d.health_score}**/100\n`);
    }
    (d.layers || []).forEach((layer) => {
      const icon = layer.status === 'ok' || layer.status === 'active' ? '✅' : layer.status === 'missing' ? '❌' : '⚠️';
      lines.push(`${icon} **${layer.name || layer.layer || '?'}** — ${layer.status || '?'}`);
      if (layer.detail) lines.push(`  ${layer.detail}`);
    });
    if (d.gaps && d.gaps.length > 0) {
      lines.push('\n**Gaps:**');
      d.gaps.forEach((g) => lines.push(`- ⚠️ ${g}`));
    }
    return lines.join('\n') + '\n';
  }

  // Default: pretty-print JSON
  return '```json\n' + JSON.stringify(data, null, 2) + '\n```\n';
}

/**
 * Try LLM generation; on failure, format raw data as Markdown.
 */
async function generateOrFallback(prompt, rawData, command, request, stream, token) {
  try {
    const text = await generateAnswer(prompt, request, stream, token);
    if (text && text.trim().length > 10) return text;
  } catch (err) {
    // LLM unavailable — fall back
  }

  const md = formatRawData(rawData, command);
  stream.markdown(md);
  return md;
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

/**
 * /jobs — search, filter, validate email/SFTP monitoring jobs
 */
async function handleJobsCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  // Phase 2 subcommands — parse regex HERE, pass structured params to handlers
  if (/^create\s+/i.test(prompt)) {
    const m = prompt.match(/^create\s+(.+?)\s+from\s+["']?(.+?)["']?\s*$/i);
    if (!m) {
      stream.markdown([
        '### Create a New Job\n',
        '**Usage:** `/jobs create <new_name> from "<template_job_name>"`\n',
        '**Example:** `/jobs create "New Exeter Job" from "CSMC 2015-1 rptent"`\n',
        'The new job will be based on the template job\'s configuration.',
      ].join('\n'));
      return { followUps: [{ prompt: 'show template patterns', label: 'List available templates' }] };
    }
    return handleJobCreate(
      m[1].replace(/^["']|["']$/g, ''),
      m[2].replace(/^["']|["']$/g, ''),
      {},
      'email',
      request, context, stream, token, shared
    );
  }
  if (/^edit\s+/i.test(prompt)) {
    const m = prompt.match(/^edit\s+["']?(.+?)["']?\s+set\s+(\w+)\s+(.+)$/i);
    if (!m) {
      stream.markdown([
        '### Edit a Job\n',
        '**Usage:** `/jobs edit "<job_name>" set <field> <value>`\n',
        '**Example:** `/jobs edit "Exeter - rptent" set servicer_id 225`\n',
        '**Editable fields:** name, servicer_id, mailbox, folder, import_did, subject_filter, sender_filter, scrubber, day_adjust, sme, save_location',
      ].join('\n'));
      return { followUps: [] };
    }
    return handleJobEdit(
      m[1].replace(/^["']|["']$/g, ''),
      m[2],
      m[3].trim(),
      'email',
      request, context, stream, token, shared
    );
  }
  if (/^templates?\b/i.test(prompt)) {
    return handleJobTemplates(prompt, request, context, stream, token, shared);
  }

  // Phase 1 subcommands
  if (lower.startsWith('validate sftp') || lower.includes('validate sftp')) {
    return handleJobsValidateSftp(prompt, request, context, stream, token, shared);
  }

  if (lower.startsWith('validate') || lower.includes('validate')) {
    return handleJobsValidate(prompt, request, context, stream, token, shared);
  }

  // Rebuild SQLite cache from XML settings
  if (/^rebuild[-_\s]?db\b/i.test(prompt)) {
    stream.progress('Rebuilding SQLite job cache from XML settings…');
    const data = await backendCall('rebuild_db', { xmlType: 'all' }, shared);
    if (data?.status === 'error' || data?.success === false) {
      stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    } else {
      const rebuilt = data?.data?.rebuilt || data?.rebuilt || {};
      const parts = Object.entries(rebuilt).map(([k, v]) => `**${k}**: ${v} jobs`);
      stream.markdown(`✅ Cache rebuilt successfully.\n\n${parts.join('  \n')}\n`);
    }
    return { followUps: [{ prompt: 'cmbs', label: 'Search jobs' }] };
  }

  // Default: search jobs
  return handleJobsSearch(prompt, request, context, stream, token, shared);
}

/**
 * Build a subtle data-source footer line from the backend response.
 * @param {Object} data — backend response containing data_source field
 * @returns {string} Markdown footer or empty string
 */
function dataSourceFooter(data) {
  const src = data?.data?.data_source || data?.data_source;
  if (!src) return '';
  if (typeof src === 'string') {
    return src === 'sqlite'
      ? '\n\n---\n*📦 Source: SQLite cache*'
      : '\n\n---\n*📄 Source: Settings.xml*';
  }
  // deal_lookup returns { deals: "tblExternalDIDRef", jobs: "sqlite"|"xml" }
  if (typeof src === 'object') {
    const parts = [];
    if (src.deals) parts.push(`Deals: ${src.deals}`);
    if (src.jobs && src.jobs !== 'n/a') {
      parts.push(`Jobs: ${src.jobs === 'sqlite' ? '📦 SQLite cache' : '📄 Settings.xml'}`);
    }
    return parts.length ? `\n\n---\n*${parts.join(' · ')}*` : '';
  }
  return '';
}

async function handleJobsSearch(prompt, request, context, stream, token, shared) {
  stream.progress('Searching jobs...');

  const query = prompt.replace(/^search\s*/i, '').trim() || prompt;
  const data = await backendCall('search_jobs', { query }, shared);

  if (data.status === 'error') {
    stream.markdown(`❌ **Error:** ${data.error}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `The user searched for jobs matching: "${query}"`,
    '',
    'Present the results using ONLY these columns: JobName, Sender, ServicerID, Scrubber, MatchMode, SavePath.',
    'NEVER add DealName or Subject columns — jobs do not have these fields.',
    'The "scrubber" field is the processing template — always label the column "Scrubber".',
    'MatchMode tells whether the ImportDID keyword matches email "Subject" or attachment "Filename".',
    'Show all file paths exactly as-is inside backticks, preserving backslashes and curly brackets.',
    'NEVER show raw JSON to the user.',
    'If groups_by_scrubber or groups_by_source are in the data, show a brief summary at the top (e.g. "10 CMBS scrubbers, 3 SCRT queuers, 15 with no template").',
    'If no results, suggest alternative search terms.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);

  stream.markdown(dataSourceFooter(data));

  const followUps = [];
  if (data.jobs && data.jobs.length > 0) {
    const firstName = data.jobs[0].job_name || data.jobs[0].name || '';
    if (firstName) {
      followUps.push({ prompt: `tell me about job ${firstName}`, label: `Detail: ${firstName}` });
    }
    followUps.push({ prompt: `which jobs handle servicer ${data.jobs[0].servicer_id || query}`, label: `Deal lookup` });
  }

  return { followUps };
}

async function handleJobsValidate(prompt, request, context, stream, token, shared) {
  stream.progress('Validating email jobs...');

  const target = prompt.replace(/^validate\s*/i, '').trim();
  const params = target ? { jobName: target } : {};
  const data = await backendCall('validate_email', params, shared);

  if (data.status === 'error') {
    stream.markdown(`❌ **Validation error:** ${data.error}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `Validation results for email monitoring jobs${target ? ` matching "${target}"` : ''}.`,
    'Format each check with ✅ or ❌ icons. Group by pass/fail. Summarise overall health.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'validate', request, stream, token);

  return {
    followUps: [
      { prompt: 'validate sftp jobs', label: 'Validate SFTP jobs too' },
      { prompt: 'check errors today', label: 'Check today\'s errors' },
    ],
  };
}

async function handleJobsValidateSftp(prompt, request, context, stream, token, shared) {
  stream.progress('Validating SFTP jobs...');

  const target = prompt.replace(/^validate\s*sftp\s*/i, '').trim();
  const params = target ? { jobName: target } : {};
  const data = await backendCall('validate_sftp', params, shared);

  if (data.status === 'error') {
    stream.markdown(`❌ **SFTP validation error:** ${data.error}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `SFTP job validation results${target ? ` for "${target}"` : ''}.`,
    'Format each check with ✅ or ❌ icons. Highlight any configuration issues.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'validate', request, stream, token);

  return {
    followUps: [
      { prompt: 'validate all jobs', label: 'Validate email jobs' },
      { prompt: 'list backups', label: 'List deploy backups' },
    ],
  };
}

/**
 * /deals — query deal coverage, servicer dossiers, DID mappings
 */
async function handleDealsCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  // Phase 2 subcommands
  if (/^gaps?\b/i.test(prompt)) {
    return handleCoverageGaps(prompt, request, context, stream, token, shared);
  }
  if (/^orphans?\b/i.test(prompt)) {
    return handleOrphanDetection(prompt, request, context, stream, token, shared);
  }
  if (/^collisions?\b/i.test(prompt)) {
    return handleCollisionDetection(prompt, request, context, stream, token, shared);
  }

  // Phase 1: deal lookup via tblExternalDIDRef
  stream.progress('Querying deal / DID mapping data...');

  // Extract a clean search term from common user patterns:
  //   "companyID = 569"  → "569"
  //   "companyID 569"    → "569"
  //   "servicer 569"     → "569"
  //   "CMBS"             → "CMBS"  (pass-through)
  let cleanQuery = prompt;
  const cidMatch = prompt.match(/(?:companyID|servicer(?:ID)?|cid)\s*[=:]\s*(\S+)/i);
  if (cidMatch) cleanQuery = cidMatch[1];

  const data = await backendCall('deal_lookup', { query: cleanQuery }, shared);

  if (data.status === 'error' || data.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `The user asked about deals/servicers: "${prompt}"`,
    'Present the deal mappings from tblExternalDIDRef clearly.',
    'Show DID names, ImportDID keywords, and CompanyID in a table.',
    'If matching_jobs are present, list the jobs that serve these deals.',
    'If no results, suggest alternative search terms.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deals', request, stream, token);

  return {
    followUps: [
      { prompt: `/jobs ${cleanQuery}`, label: `Search jobs for "${cleanQuery}"` },
    ],
  };
}

/**
 * /logs — sync and query application logs
 */
async function handleLogsCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  // Handle sync subcommand
  if (lower.startsWith('sync') || lower === '') {
    stream.progress('Syncing logs...');

    const data = await backendCall('sync_logs', {}, shared);

    if (data.status === 'error') {
      stream.markdown(`❌ **Log sync failed:** ${data.error}\n`);
      return { followUps: [] };
    }

    const count = data.files_processed || data.filesProcessed || data.files_synced || data.filesSynced || 0;
    stream.markdown(`✅ **Log sync complete** — ${count} file(s) processed.\n`);

    return {
      followUps: [
        { prompt: 'what happened today', label: 'Daily summary' },
        { prompt: 'show DID failures', label: 'DID failures' },
      ],
    };
  }

  // ── Phase 3: deal activity ─────────────────────────────────────── //
  if (/^deal\b/i.test(prompt)) {
    const rest = prompt.replace(/^deal\s*/i, '').trim();
    if (!rest) {
      stream.markdown('**Usage:** `/logs deal <DID name or number>` — e.g. `/logs deal CSMC`\n');
      return { followUps: [] };
    }
    stream.progress('Querying deal activity...');
    const data = await backendCall('log_deal_activity', { did: rest }, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    // Stale index warning
    if (data.data && data.data.warning) {
      stream.markdown(`> ⚠️ ${data.data.warning}\n\n`);
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user asked for deal activity for "${rest}".`,
      'Summarise the deal events. Group by event type. Show a timeline if useful.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: `/deals gaps`, label: 'Check deal gaps' },
        { prompt: 'show DID failures', label: 'DID failures' },
      ],
    };
  }

  // ── Phase 3: DID failures ─────────────────────────────────────── //
  if (/^fail(ure)?s?\b/i.test(prompt)) {
    stream.progress('Querying DID failures...');
    const params = {};
    const jobMatch = prompt.match(/job[:\s]+(\S+)/i);
    if (jobMatch) params.jobFilter = jobMatch[1];
    const data = await backendCall('log_did_failures', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'The user asked for DID mapping failures.',
      'List the failures sorted by count. Highlight the most impactful ones.',
      'Suggest next steps to fix the top failures.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: 'coverage gaps', label: 'Deal gap analysis' },
        { prompt: 'what happened today', label: 'Daily summary' },
      ],
    };
  }

  // ── Phase 3: job health ───────────────────────────────────────── //
  if (/^health\b/i.test(prompt)) {
    const jobName = prompt.replace(/^health\s*/i, '').trim();
    if (!jobName) {
      stream.markdown('**Usage:** `/logs health <job name>` — e.g. `/logs health TestJob_Alpha`\n');
      return { followUps: [] };
    }
    stream.progress(`Checking health for ${jobName}...`);
    const data = await backendCall('log_job_health', { jobName }, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user asked for the health of job "${jobName}".`,
      'Show a clear health status (healthy/warning/critical) with key metrics.',
      'If there are common errors, list them. Suggest remediation for critical/warning status.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: `/jobs ${jobName}`, label: `View ${jobName} config` },
        { prompt: 'what happened today', label: 'Daily summary' },
      ],
    };
  }

  // ── Phase 3: daily summary ────────────────────────────────────── //
  if (/^summary\b/i.test(prompt)) {
    const dateArg = prompt.replace(/^summary\s*/i, '').trim() || undefined;
    stream.progress('Building daily summary...');
    const params = {};
    if (dateArg) params.date = dateArg;
    const data = await backendCall('log_daily_summary', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user asked for a daily summary${dateArg ? ` for ${dateArg}` : ''}.`,
      'Present a clear operational overview: jobs run, emails processed, errors, DID failures.',
      'Compare with the previous day and highlight any significant changes.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: 'show DID failures', label: 'DID failures' },
        { prompt: 'sync logs', label: 'Re-sync logs' },
      ],
    };
  }

  // ── Phase 4: trends ────────────────────────────────────────────── //
  if (/^trends?\b/i.test(prompt)) {
    const rest = prompt.replace(/^trends?\s*/i, '').trim();
    stream.progress('Analysing trends...');
    const params = {};
    const daysMatch = rest.match(/(?:--days\s+|last\s+)(\d+)/i);
    if (daysMatch) params.days = parseInt(daysMatch[1]);
    const jobMatch = rest.match(/(?:--job\s+|for\s+)(\S+)/i);
    if (jobMatch) params.job = jobMatch[1];
    const data = await backendCall('log_trends', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    if (data.data && data.data.staleness_warning) {
      stream.markdown(`> ⚠️ ${data.data.staleness_warning}\n\n`);
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'Format these daily trends as a timeline summary.',
      'Include trend indicators (↑/↓/→), period totals,',
      'comparison with previous period, best and worst days.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: 'show DID failures', label: 'DID failures' },
        { prompt: 'job performance', label: 'Job performance' },
        { prompt: 'system health report', label: 'Full health check' },
      ],
    };
  }

  // ── Phase 4: performance ──────────────────────────────────────── //
  if (/^performance\b/i.test(prompt)) {
    const rest = prompt.replace(/^performance\s*/i, '').trim();
    stream.progress('Benchmarking job performance...');
    const params = {};
    const sortMatch = rest.match(/--sort\s+(\S+)/i);
    if (sortMatch) params.sort = sortMatch[1];
    const topMatch = rest.match(/(?:--top\s+|top\s+)(\d+)/i);
    if (topMatch) params.top = parseInt(topMatch[1]);
    const daysMatch = rest.match(/(?:--days\s+|last\s+)(\d+)/i);
    if (daysMatch) params.days = parseInt(daysMatch[1]);
    const data = await backendCall('log_performance', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    if (data.data && data.data.staleness_warning) {
      stream.markdown(`> ⚠️ ${data.data.staleness_warning}\n\n`);
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'Format this performance report as a ranked table.',
      'Show job name, status indicator, success rate, volume,',
      'and common errors for problematic jobs.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'logs', request, stream, token);
    const followUps = [
      { prompt: 'show trends', label: 'View trends' },
      { prompt: 'consolidation analysis', label: 'Consolidation analysis' },
    ];
    if (data.data && data.data.entries) {
      const critical = data.data.entries.find(e => e.status === 'critical');
      if (critical) {
        followUps.unshift({ prompt: `/logs health ${critical.job_name}`, label: `Health: ${critical.job_name}` });
      }
    }
    return { followUps };
  }

  // ── Contextual error follow-up detection ───────────────────────── //
  // If the user asks about "errors" / "the errors" / "those 4 errors" without
  // specifying a job name, try to extract the job from conversation history.
  const vagueErrorMatch = lower.match(/^(?:show|tell|what|more|detail|explain).*\b(?:error|errors|failure|failures)\b/);
  if (vagueErrorMatch && !prompt.match(/errors?\s+\S+/i)) {
    // Try to find a job name from the last assistant response in history
    let contextJob = null;
    if (context && context.history) {
      for (let i = context.history.length - 1; i >= 0; i--) {
        const turn = context.history[i];
        if (turn instanceof vscode.ChatResponseTurn) {
          for (const part of turn.response) {
            if (part instanceof vscode.ChatResponseMarkdownPart) {
              const text = part.value.value;
              // Look for a job name in a table or heading
              const jobRef = text.match(/\bJobName\b.*\n\|[-|]+\n\|\s*(\S+)/);
              if (jobRef) { contextJob = jobRef[1]; break; }
              // Look for: Search: "JOB_NAME"
              const searchRef = text.match(/Search:\s*"([^"]+)"/);
              if (searchRef) { contextJob = searchRef[1]; break; }
            }
          }
          if (contextJob) break;
        }
        // Also check what the user asked last time
        if (!contextJob && turn instanceof vscode.ChatRequestTurn) {
          const prevPrompt = turn.prompt || '';
          // e.g. previously: "/logs CMBS_GreyCo"
          const prevJob = prevPrompt.match(/(?:\/logs?\s+)(\S+)/i);
          if (prevJob && !['sync', 'errors', 'health', 'deal', 'summary', 'trends', 'performance', 'activity'].includes(prevJob[1].toLowerCase())) {
            contextJob = prevJob[1];
            break;
          }
        }
      }
    }
    if (contextJob) {
      stream.progress(`Retrieving error details for ${contextJob}…`);
      const data = await backendCall('log_search', { query: contextJob, eventType: 'errors' }, shared);
      if (data.status === 'error' || !data.success) {
        stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
        return { followUps: [] };
      }
      const errData = data.data || data;
      const llmPrompt = [
        SYSTEM_PROMPT, '',
        '<data>', JSON.stringify(errData, null, 2), '</data>', '',
        `The user asked for more details about errors for job "${contextJob}" (continuing from previous search).`,
        'Present each error with its timestamp, error message, and any related context (subject, sender, filename).',
        'Group similar errors together. Identify patterns (recurring errors, time clustering).',
        'Suggest root cause and remediation steps for each error type.',
      ].join('\n');
      await generateOrFallback(llmPrompt, errData, 'logs', request, stream, token);
      return {
        followUps: [
          { prompt: `health ${contextJob}`, label: `Health: ${contextJob}` },
          { prompt: `activity ${contextJob}`, label: `Activity: ${contextJob}` },
        ],
      };
    }
  }

  // ── Error details subcommand ────────────────────────────────── //
  // e.g. "/logs errors CMBS_GreyCo", "/logs CMBS_GreyCo Errors",
  //      "/logs show errors for CMBS_GreyCo"
  // Detect "errors" / "error" anywhere in the prompt; extract the job name
  // from whichever side of the keyword it appears.
  let errorMatch = prompt.match(/^(?:errors?|show\s+errors?\s+(?:for|in|on)?)\s+(.+)/i);
  if (!errorMatch) {
    // Try trailing: "CMBS_GreyCo Errors" → job = CMBS_GreyCo
    const trailingErr = prompt.match(/^(.+?)\s+errors?$/i);
    if (trailingErr) errorMatch = trailingErr;
  }
  if (errorMatch) {
    const jobName = errorMatch[1].trim().replace(/["']/g, '');
    stream.progress(`Retrieving error details for ${jobName}…`);
    const data = await backendCall('log_search', { query: jobName, eventType: 'errors' }, shared);
    if (data.status === 'error' || !data.success) {
      stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
      return { followUps: [] };
    }
    const errData = data.data || data;
    const llmPrompt = [
      SYSTEM_PROMPT, '',
      '<data>', JSON.stringify(errData, null, 2), '</data>', '',
      `The user wants error details for job "${jobName}".`,
      'Present each error with its timestamp, error message, and any related context (subject, sender, filename).',
      'Group similar errors together. Identify patterns (recurring errors, time clustering).',
      'Suggest root cause and remediation steps for each error type.',
      'Do NOT show "total_events" or routine job polling counts — focus only on errors.',
    ].join('\n');
    await generateOrFallback(llmPrompt, errData, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: `health ${jobName}`, label: `Health: ${jobName}` },
        { prompt: `${jobName}`, label: `Full search: ${jobName}` },
      ],
    };
  }

  // ── Activity subcommand ───────────────────────────────────────── //
  // e.g. "/logs activity CMBS_GreyCo" or "/logs CMBS_GreyCo activity"
  let activityMatch = prompt.match(/^activity\s+(.+)/i);
  if (!activityMatch) {
    const trailingAct = prompt.match(/^(.+?)\s+activity$/i);
    if (trailingAct) activityMatch = trailingAct;
  }
  if (activityMatch) {
    const jobName = activityMatch[1].trim().replace(/["']/g, '');
    stream.progress(`Retrieving actionable events for ${jobName}…`);
    const data = await backendCall('log_search', { query: jobName, eventType: 'activity' }, shared);
    if (data.status === 'error' || !data.success) {
      stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
      return { followUps: [] };
    }
    const actData = data.data || data;
    const llmPrompt = [
      SYSTEM_PROMPT, '',
      '<data>', JSON.stringify(actData, null, 2), '</data>', '',
      `The user wants actionable activity for job "${jobName}" (no routine polling noise).`,
      'Show a timeline of meaningful events: emails processed, files loaded, parser matches, template queuing, DID matches, and errors.',
      'Use a table or timeline format. Highlight any errors or failures.',
    ].join('\n');
    await generateOrFallback(llmPrompt, actData, 'logs', request, stream, token);
    return {
      followUps: [
        { prompt: `errors ${jobName}`, label: `Error details` },
        { prompt: `health ${jobName}`, label: `Health: ${jobName}` },
      ],
    };
  }

  // ── Fallback: generic log search ──────────────────────────────── //
  // Extract the actual search keyword from natural language prompts.
  // e.g. "search for a job with 'cmbs' in the job name" → "cmbs"
  //      "find jobs containing SFTP_Alpha"              → "SFTP_Alpha"
  //      "cmbs"                                          → "cmbs"
  let searchQuery = prompt;
  // Try quoted strings first (single or double quotes)
  const quotedMatch = prompt.match(/["']([^"']+)["']/);
  if (quotedMatch) {
    searchQuery = quotedMatch[1];
  } else {
    // Strip common NL preamble: "search for ...", "find jobs with ...", etc.
    searchQuery = prompt
      .replace(/^(?:search|find|look\s*up|show|get|list)\s+(?:for\s+)?/i, '')
      .replace(/\b(?:a\s+)?(?:job|jobs|log|logs|event|events)\s+(?:with|containing|named|called|matching|that\s+(?:have|has|contain|match))\s+/i, '')
      .replace(/\s+in\s+(?:the\s+)?(?:job\s*name|log|logs|name).*$/i, '')
      .replace(/\s+(?:and|then)\s+(?:provide|show|give|display).*$/i, '')
      .trim();
  }

  stream.progress(`Searching logs for "${searchQuery}"...`);

  const data = await backendCall('log_search', { query: searchQuery }, shared);

  if (data.status === 'error') {
    stream.markdown(`❌ **Log search failed:** ${data.error}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `The user searched logs for: "${prompt}"`,
    '',
    '## Presentation rules',
    '- Focus on ACTIONABLE information: errors, files loaded, emails matched, templates queued, DID matches/failures.',
    '- Do NOT highlight "total_events" as a primary metric — most of those are routine polling cycles (job starts with 0 emails found). That count is noise for the end user.',
    '- Instead, lead with: errors (count + details if provided in recent_errors), files loaded, emails found, unique senders, unique parsers.',
    '- If a job has errors, present the error details from "recent_errors" in a table with timestamp and error message.',
    '- If total_files_loaded = 0 and total_emails_found = 0 but the job has been running (high total_events), note that "Job is running but no data has been received/processed" — this may be normal or may indicate a problem.',
    '- For the operational status, use: ✅ Healthy (no errors, files processing), ⚠️ Idle (running but no files/emails), ❌ Errors (errors detected).',
    '- Keep it concise — the user wants signal, not noise.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'logs', request, stream, token);

  // Build contextual follow-ups based on the results
  const followUps = [];
  const jobsData = data?.data?.jobs || data?.jobs || [];
  if (jobsData.length > 0) {
    const firstJob = jobsData[0]?.job_name;
    if (firstJob) {
      if (jobsData[0]?.total_errors > 0) {
        followUps.push({ prompt: `errors ${firstJob}`, label: `Error details: ${firstJob}` });
      }
      followUps.push({ prompt: `activity ${firstJob}`, label: `Activity: ${firstJob}` });
      followUps.push({ prompt: `health ${firstJob}`, label: `Health: ${firstJob}` });
    }
  }
  if (followUps.length === 0) {
    followUps.push(
      { prompt: 'sync logs', label: 'Re-sync logs' },
      { prompt: 'what happened today', label: 'Daily summary' },
    );
  }

  return { followUps };
}

/**
 * /deploy — save Settings.xml, manage backups, list restore points
 */
async function handleDeployCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  // Phase 2 subcommands
  if (/^diff\b/i.test(prompt)) {
    return handleXmlDiff(prompt, request, context, stream, token, shared);
  }
  if (/^rollback\s+/i.test(prompt)) {
    const backupFile = prompt.replace(/^rollback\s+/i, '').trim();
    return handleRollback(backupFile, request, context, stream, token, shared);
  }
  if (/^rollback$/i.test(prompt)) {
    stream.markdown([
      '### Rollback Settings.xml\n',
      '**Usage:** `/deploy rollback <backup_filename>`\n',
      '**Example:** `/deploy rollback Settings_20260201_120000.xml`\n',
      'A diff will be shown first for review before confirming.',
    ].join('\n'));
    return { followUps: [{ prompt: 'list backups', label: 'List available backups' }] };
  }

  // List backups
  if (lower.includes('list') || lower.includes('backup') || lower.includes('restore')) {
    stream.progress('Listing backups...');

    const data = await backendCall('list_backups', {}, shared);

    if (data.status === 'error') {
      stream.markdown(`❌ **Error:** ${data.error}\n`);
      return { followUps: [] };
    }

    const llmPrompt = [
      SYSTEM_PROMPT,
      '',
      '<data>',
      JSON.stringify(data, null, 2),
      '</data>',
      '',
      'List the available Settings.xml backup/restore points.',
      'Format as a chronological list with dates and filenames.',
    ].join('\n');

    await generateOrFallback(llmPrompt, data, 'deploy', request, stream, token);

    return {
      followUps: [
        { prompt: 'save email settings', label: 'Save email Settings.xml' },
        { prompt: 'save sftp settings', label: 'Save SFTP Settings.xml' },
      ],
    };
  }

  // Save email settings
  if (lower.includes('save email') || lower.includes('email')) {
    stream.progress('Saving email Settings.xml...');

    const data = await backendCall('save_email_settings', {}, shared);

    if (data.status === 'error') {
      stream.markdown(`❌ **Save failed:** ${data.error}\n`);
      return { followUps: [] };
    }

    stream.markdown(`✅ **Email Settings.xml saved.**\n`);
    if (data.backup) stream.markdown(`Backup: \`${data.backup}\`\n`);
    if (data.message) stream.markdown(`${data.message}\n`);

    return {
      followUps: [
        { prompt: 'list backups', label: 'List all backups' },
        { prompt: 'validate all jobs', label: 'Validate jobs' },
      ],
    };
  }

  // Save SFTP settings
  if (lower.includes('save sftp') || lower.includes('sftp')) {
    stream.progress('Saving SFTP Settings.xml...');

    const data = await backendCall('save_sftp_settings', {}, shared);

    if (data.status === 'error') {
      stream.markdown(`❌ **Save failed:** ${data.error}\n`);
      return { followUps: [] };
    }

    stream.markdown(`✅ **SFTP Settings.xml saved.**\n`);
    if (data.backup) stream.markdown(`Backup: \`${data.backup}\`\n`);
    if (data.message) stream.markdown(`${data.message}\n`);

    return {
      followUps: [
        { prompt: 'list backups', label: 'List all backups' },
        { prompt: 'validate sftp jobs', label: 'Validate SFTP jobs' },
      ],
    };
  }

  // Generic deploy help
  stream.markdown([
    '### Deploy Commands\n',
    '| Command | Description |',
    '|---------|-------------|',
    '| `/deploy save email` | Save email monitoring Settings.xml with backup |',
    '| `/deploy save sftp` | Save SFTP monitoring Settings.xml with backup |',
    '| `/deploy list backups` | List all available restore points |',
    '| `/deploy diff` | Compare current Settings.xml to latest backup |',
    '| `/deploy diff <file>` | Compare against a specific backup |',
    '| `/deploy rollback <file>` | Restore Settings.xml from a backup |',
    '',
  ].join('\n'));

  return {
    followUps: [
      { prompt: 'list backups', label: 'List backups' },
      { prompt: 'what changed since last deploy', label: 'View changes' },
      { prompt: 'save email settings', label: 'Save email settings' },
    ],
  };
}

/**
 * /triage — Phase 3: triage incoming emails against job configs
 */
async function handleTriageCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  if (!prompt) {
    stream.markdown([
      '### 📧 Email Triage\n',
      'Triage incoming emails against active job configurations.\n',
      '| Subcommand | Description |',
      '|------------|-------------|',
      '| `/triage verify <path.msg>` | Parse .msg file and match against all jobs |',
      '| `/triage match <sender or subject>` | Quick match by sender/subject text |',
      '| `/triage match --file <path.msg>` | Quick match from .msg file |',
      '| `/triage new <path.msg>` | Analyze unmatched email for new job setup |',
      '',
    ].join('\n'));

    return {
      followUps: [
        { prompt: 'list all jobs', label: 'Browse all jobs' },
        { prompt: 'triage verify C:\\emails\\sample.msg', label: 'Try verify' },
      ],
    };
  }

  // ── verify subcommand (E-01) ──────────────────────────────────── //
  if (/^verify\b/i.test(prompt)) {
    const msgPath = extractMsgPath(prompt.replace(/^verify\s*/i, ''));
    if (!msgPath) {
      stream.markdown('**Usage:** `/triage verify <path to .msg file>`\n');
      return { followUps: [] };
    }
    stream.progress('Verifying email against job configurations...');
    const data = await backendCall('triage_verify', { msgPath }, shared);
    if (!data.success) {
      stream.markdown(`❌ **Triage error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user wants to verify whether a .msg email is covered by existing jobs.`,
      'Show the email metadata (sender, subject, date).',
      'List matching jobs ranked by confidence. Show match type (sender/subject/both).',
      'If no matches, explain clearly and suggest next steps.',
      'If there are matches, show coverage status (number of deals).',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'triage', request, stream, token);
    const followUps = [{ prompt: 'triage new job for ' + msgPath, label: 'Analyze for new job' }];
    if (data.data && data.data.matches && data.data.matches.length > 0) {
      followUps.unshift({ prompt: `/jobs ${data.data.matches[0].job_name}`, label: `View ${data.data.matches[0].job_name}` });
    }
    return { followUps };
  }

  // ── match subcommand (E-02) ───────────────────────────────────── //
  if (/^match\b/i.test(prompt)) {
    const rest = prompt.replace(/^match\s*/i, '').trim();
    const params = {};
    const fileMatch = rest.match(/--file\s+(.+\.msg)/i);
    if (fileMatch) {
      params.msgPath = fileMatch[1].trim();
    } else if (rest) {
      // Try to detect if it's an email address (sender) or text (subject)
      if (rest.includes('@')) {
        params.sender = rest;
      } else {
        params.subject = rest;
      }
    } else {
      stream.markdown('**Usage:** `/triage match <sender or subject>` or `/triage match --file <path.msg>`\n');
      return { followUps: [] };
    }
    stream.progress('Matching email criteria against jobs...');
    const data = await backendCall('triage_match', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Match error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user wants to find which jobs would match: "${rest}".`,
      'List matching jobs ranked by confidence. Show match type and the filter that matched.',
      'If no matches, say so clearly.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'triage', request, stream, token);
    return {
      followUps: [
        { prompt: 'list all jobs', label: 'Browse all jobs' },
      ],
    };
  }

  // ── new subcommand (E-03) ─────────────────────────────────────── //
  if (/^new\b/i.test(prompt)) {
    const msgPath = extractMsgPath(prompt.replace(/^new\s*/i, ''));
    if (!msgPath) {
      stream.markdown('**Usage:** `/triage new <path to .msg file>`\n');
      return { followUps: [] };
    }
    stream.progress('Analyzing email for new job setup...');
    const data = await backendCall('triage_new', { msgPath }, shared);
    if (!data.success) {
      stream.markdown(`❌ **Analysis error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      `The user wants to create a new job for an unmatched email.`,
      'Show the email metadata and recommended parser type.',
      'Present the suggested configuration (subject pattern, sender domain, attachment types).',
      'If template suggestions are available, recommend which template to base the new job on.',
      'If potential servicer IDs were found, list them.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'triage', request, stream, token);
    return {
      followUps: [
        { prompt: 'create a new job', label: 'Create new job' },
        { prompt: 'triage verify ' + msgPath, label: 'Verify again' },
      ],
    };
  }

  // ── Fallback: generic triage ──────────────────────────────────── //
  stream.markdown([
    '### 📧 Email Triage\n',
    'Use a subcommand to triage emails:\n',
    '- `/triage verify <path.msg>` — Full verification',
    '- `/triage match <sender or subject>` — Quick match',
    '- `/triage new <path.msg>` — Analyze for new job',
    '',
  ].join('\n'));

  return {
    followUps: [
      { prompt: 'triage verify email', label: 'Verify an email' },
      { prompt: 'triage match criteria', label: 'Match by criteria' },
    ],
  };
}

/**
 * Extract a .msg file path from user input.
 * Handles paths with or without quotes, with spaces.
 */
function extractMsgPath(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return null;
  // Quoted path
  const quoted = trimmed.match(/^["'](.+?\.msg)["']/i);
  if (quoted) return quoted[1];
  // Unquoted — take the whole thing if it ends in .msg
  if (/\.msg$/i.test(trimmed)) return trimmed;
  // Try first token
  const first = trimmed.split(/\s+/)[0];
  if (/\.msg$/i.test(first)) return first;
  return trimmed; // pass as-is, let backend validate
}

/**
 * /analyze — Phase 4 stub: advanced analysis
 */
async function handleAnalyzeCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  if (!prompt) {
    stream.markdown([
      '### 📊 Advanced Analysis\n',
      'Run advanced analytical queries across jobs, deals, and logs.\n',
      '**Usage:**',
      '- `/analyze consolidation` — Find merge opportunities across similar jobs',
      '- `/analyze impact <description>` — Simulate a configuration change',
      '- `/analyze health` — Full system health check (9 sections)',
      '',
      '**Impact examples:**',
      '- `/analyze impact delete job "Ocwen"`',
      '- `/analyze impact rename ImportDID C88 to OCW88`',
      '- `/analyze impact change filter on "rptent" to "*.csv"`',
    ].join('\n'));

    return {
      followUps: [
        { prompt: 'system health report', label: 'Run health check' },
        { prompt: 'consolidation analysis', label: 'Find duplicates' },
        { prompt: 'simulate impact', label: 'Impact simulation' },
      ],
    };
  }

  // ── Consolidation ─────────────────────────────────────────────── //
  if (/^consolidat/i.test(lower)) {
    stream.progress('Analysing consolidation opportunities...');
    const typeMatch = prompt.match(/--type\s+(email|sftp|all)/i);
    const params = { type: typeMatch ? typeMatch[1] : 'all' };
    const data = await backendCall('analyze_consolidation', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'Format this consolidation analysis as a grouped report.',
      'For each group, show shared config, individual jobs, DID counts,',
      'and merge recommendation (safe/review/risky).',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'analyze', request, stream, token);
    const followUps = [
      { prompt: 'system health report', label: 'Full health check' },
    ];
    if (data.data && data.data.groups && data.data.groups.length > 0) {
      const g = data.data.groups[0];
      if (g.jobs && g.jobs.length > 0 && g.jobs[0].servicer_id) {
        followUps.push({ prompt: `servicer dossier ${g.jobs[0].servicer_id}`, label: `Servicer ${g.jobs[0].servicer_id}` });
      }
      followUps.push({ prompt: 'simulate impact', label: 'Simulate a change' });
    }
    return { followUps };
  }

  // ── Impact ────────────────────────────────────────────────────── //
  if (/^impact\b/i.test(lower)) {
    const description = prompt.replace(/^impact\s*/i, '').trim();
    if (!description) {
      stream.markdown([
        'Please describe the change to simulate.\n',
        '**Examples:**',
        '- `/analyze impact delete job "bonds mailbox"`',
        '- `/analyze impact rename ImportDID C88 to OCW88`',
        '- `/analyze impact change filter on "rptent" to "*.csv"`',
        '',
        'Or use flags: `/analyze impact --change-type delete_job --target-job "NAME"`',
      ].join('\n'));
      return { followUps: [] };
    }

    stream.progress('Parsing change intent...');

    // Try structured flags first
    let changeSpec = null;
    const ctMatch = description.match(/--change-type\s+(\S+)/i);
    if (ctMatch) {
      changeSpec = {
        change_type: ctMatch[1],
        target_job: (description.match(/--target-job\s+"?([^"]+)"?/i) || [])[1] || null,
        target_did: (description.match(/--target-did\s+(\S+)/i) || [])[1] || null,
        target_company_id: parseInt((description.match(/--target-company-id\s+(\d+)/i) || [])[1]) || null,
        new_value: (description.match(/--new-value\s+"?([^"]+)"?/i) || [])[1] || null,
      };
    }

    // Fall back to passing raw description to the backend
    if (!changeSpec) {
      changeSpec = {
        change_type: 'unknown',
        raw_description: description,
      };
    }

    if (!changeSpec) {
      stream.markdown([
        '❌ Could not parse the change description.\n',
        'Try a structured command:',
        '`/analyze impact --change-type delete_job --target-job "NAME"`',
        '',
        'Supported change types: `delete_job`, `rename_did`, `change_filter`, `move_servicer`',
      ].join('\n'));
      return { followUps: [] };
    }

    stream.progress('Simulating impact...');
    const params = {
      ...changeSpec,
      raw_description: description,
    };
    const data = await backendCall('analyze_impact', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'Format this impact analysis as a risk assessment.',
      'Highlight affected entities, coverage changes, and recommendation.',
      'Use risk badges: 🟢 low, 🟡 medium, 🔴 high.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'analyze', request, stream, token);
    return {
      followUps: [
        { prompt: 'system health report', label: 'Full health check' },
        { prompt: 'consolidation analysis', label: 'Consolidation' },
      ],
    };
  }

  // ── Health ────────────────────────────────────────────────────── //
  if (/^health\b/i.test(lower)) {
    stream.progress('Running full health check...');
    const typeMatch = prompt.match(/--type\s+(email|sftp|all)/i);
    const params = { type: typeMatch ? typeMatch[1] : 'all' };
    const data = await backendCall('analyze_health', params, shared);
    if (!data.success) {
      stream.markdown(`❌ **Error:** ${(data.errors || []).join(', ') || 'Unknown error'}\n`);
      return { followUps: [] };
    }
    const llmPrompt = [SYSTEM_PROMPT, '', '<data>', JSON.stringify(data.data, null, 2), '</data>', '',
      'Format this health report as a dashboard with section scores,',
      'status indicators (✅ pass / ⚠️ warning / ❌ fail), overall grade,',
      'and recommended action items.',
      'If a processing_health section is present, include it as "Processing Pipeline Health" showing:',
      'success rate, failure count, manual queue percentage, and any concerning templates.',
    ].join('\n');
    await generateOrFallback(llmPrompt, data.data, 'analyze', request, stream, token);
    const followUps = [];
    if (data.data && data.data.sections) {
      for (const section of data.data.sections) {
        if (section.action_items && section.action_items.length > 0) {
          const cmdMatch = section.action_items[0].match(/(@frp\s+\/\S+.*)/);
          if (cmdMatch) {
            followUps.push({ prompt: cmdMatch[1], label: section.name });
          }
          if (followUps.length >= 4) break;
        }
      }
    }
    if (followUps.length === 0) {
      followUps.push({ prompt: 'show trends', label: 'View trends' });
      followUps.push({ prompt: 'job performance', label: 'Job performance' });
    }
    return { followUps };
  }

  // ── Unknown subcommand — show help ────────────────────────────── //
  stream.markdown([
    '**Unknown subcommand.** Usage:',
    '- `/analyze consolidation` — Find merge opportunities',
    '- `/analyze impact <description>` — Simulate a change',
    '- `/analyze health` — Full system health check',
  ].join('\n'));
  return {
    followUps: [
      { prompt: 'system health report', label: 'Health check' },
      { prompt: 'consolidation analysis', label: 'Consolidation' },
    ],
  };
}

/**
 * Lightweight keyword-based routing fallback.
 *
 * Only fires when LLM tool-calling is unavailable (model doesn't
 * support it, VS Code too old, etc.).  Covers the handful of patterns
 * that were historically misrouted by the old regex engine.
 *
 * Returns null if no confident match → falls to plain LLM.
 */
async function keywordFallbackRoute(prompt, request, context, stream, token, shared) {
  const lower = prompt.toLowerCase();

  // ── tblExternalDIDRef / deal table queries ─────────────────── //
  if (/tblexternaldidref|\bdidref\b/i.test(lower)) {
    // "all records" / "all" / wildcard
    const isAll = /\ball\b|\*|all\s+records/i.test(lower);
    const q = isAll ? '*' : lower.replace(/.*tblexternaldidref/i, '').replace(/[?!.'"]/g, '').trim() || '*';
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → deal_lookup(${q}) [tblExternalDIDRef]`);
    return handleDealLookup(q, request, context, stream, token, shared);
  }

  // ── Deal / CompanyID lookup ────────────────────────────────── //
  const companyMatch = lower.match(/company\s*id\s*[=:]?\s*(\d+)/i)
    || lower.match(/servicer\s*(?:id)?\s*[=:]?\s*(\d+)/i);
  if (companyMatch) {
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → deal_lookup(${companyMatch[1]})`);
    return handleDealLookup(companyMatch[1], request, context, stream, token, shared);
  }

  // "deals linked/associated/mapped to <something>"
  const dealLinkedMatch = lower.match(
    /deals?\s+(?:linked|associated|mapped|related)\s+(?:to|with)\s+(.+?)(?:\s+in\s+|$)/i
  );
  if (dealLinkedMatch) {
    const q = dealLinkedMatch[1].replace(/['"]/g, '').trim();
    // Extract number if present
    const numMatch = q.match(/(\d+)/);
    const query = numMatch ? numMatch[1] : q;
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → deal_lookup(${query})`);
    return handleDealLookup(query, request, context, stream, token, shared);
  }

  // "which jobs handle/serve/cover deal X"
  const whichJobsMatch = lower.match(
    /which\s+jobs?\s+(?:handle|serve|cover|process|monitor)\s+(.+)/i
  );
  if (whichJobsMatch) {
    const q = whichJobsMatch[1].replace(/[?!.'"]/g, '').trim();
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → deal_lookup(${q})`);
    return handleDealLookup(q, request, context, stream, token, shared);
  }

  // ── Job detail — "tell me about job X", "details for X" ───── //
  const jobDetailMatch = lower.match(
    /(?:tell\s+me\s+about|details?\s+(?:for|of|on|about))\s+(?:job\s+)?["']?([a-z0-9_\-]+)/i
  );
  if (jobDetailMatch && jobDetailMatch[1].includes('_')) {
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → job_detail(${jobDetailMatch[1]})`);
    return handleJobDetail(jobDetailMatch[1], request, context, stream, token, shared);
  }

  // ── Status ────────────────────────────────────────────────── //
  if (lower === 'status' || /\bagent\s+status\b/i.test(lower)) {
    shared.outputChannel.appendLine('[FRP] Keyword fallback → agent_status');
    return handleStatusIntent(stream, shared);
  }

  // ── Sync logs — unambiguous imperative; never send to LLM ──── //
  if (/\bsync\s+(?:the\s+)?logs?\b|\bindex(?:ing)?\s+(?:the\s+)?logs?\b|\brefresh\s+(?:the\s+)?logs?\b/i.test(lower)) {
    shared.outputChannel.appendLine('[FRP] Keyword fallback → sync_logs');
    stream.progress('Syncing logs...');
    const syncData = await backendCall('sync_logs', {}, shared);
    if (syncData.status === 'error') {
      stream.markdown(`❌ **Log sync failed:** ${syncData.error}\n`);
      return { followUps: [] };
    }
    const processed = syncData.files_processed || syncData.filesProcessed || syncData.files_synced || syncData.filesSynced || 0;
    const skipped   = syncData.files_skipped  || syncData.filesSkipped  || 0;
    stream.markdown(`✅ **Log sync complete** — ${processed} file(s) indexed, ${skipped} already up-to-date.\n`);
    return {
      followUps: [
        { prompt: 'what happened today', label: 'Daily summary' },
        { prompt: 'show DID failures',   label: 'DID failures'  },
      ],
    };
  }

  // ── Phase 5: Template Staging fallbacks ───────────────────── //

  // "what's failing" / "show failures" / "failure report"
  if (/\b(?:what.?s?\s+fail|show\s+fail|failure\s+(?:report|analysis)|broken\s+template)/i.test(lower)) {
    shared.outputChannel.appendLine('[FRP] Keyword fallback → failure_analysis');
    return handleFailureAnalysis({}, request, context, stream, token, shared);
  }

  // "manual queue" / "automation gaps" / "manual vs auto"
  if (/\bmanual\s+queue|automation\s+gap|manual\s+vs/i.test(lower)) {
    shared.outputChannel.appendLine('[FRP] Keyword fallback → manual_queue');
    return handleManualQueue({}, request, context, stream, token, shared);
  }

  // "processing duration" / "slowest templates" / "how long does X take"
  if (/\bprocessing\s+duration|slowest\s+template|how\s+long\s+does/i.test(lower)) {
    shared.outputChannel.appendLine('[FRP] Keyword fallback → processing_duration');
    return handleProcessingDuration({}, request, context, stream, token, shared);
  }

  // "pipeline for X" / "end to end" / "full pipeline"
  const pipelineMatch = lower.match(/(?:pipeline|end.to.end)\s+(?:for\s+)?(.+?)(?:\s*$)/i);
  if (pipelineMatch) {
    const q = pipelineMatch[1].replace(/[?!.'"]/g, '').trim();
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → deal_pipeline(${q})`);
    return handleDealPipeline({ query: q }, request, context, stream, token, shared);
  }

  // "template status X" / "status of template X" / "is X running"
  const templateStatusMatch = lower.match(
    /(?:template\s+status|status\s+of\s+template|is\s+(\S+)\s+running)\s*(.+)?/i
  );
  if (templateStatusMatch) {
    const q = (templateStatusMatch[2] || templateStatusMatch[1] || '').replace(/[?!'"]/g, '').trim();
    if (q) {
      shared.outputChannel.appendLine(`[FRP] Keyword fallback → template_status(${q})`);
      return handleTemplateStatus({ query: q }, request, context, stream, token, shared);
    }
  }

  // "trace file X" / "where did X come from"
  const traceMatch = lower.match(/(?:trace\s+(?:file\s+)?|where\s+did\s+)(.+?)(?:\s+come\s+from)?$/i);
  if (traceMatch && (traceMatch[1].includes('\\') || traceMatch[1].includes('/') || traceMatch[1].includes('.'))) {
    const fp = traceMatch[1].replace(/[?!'"]/g, '').trim();
    shared.outputChannel.appendLine(`[FRP] Keyword fallback → source_trace(${fp})`);
    return handleSourceTrace({ filepath: fp }, request, context, stream, token, shared);
  }

  return null;
}

/**
 * Freeform question handler (no slash command)
 */
async function handleFreeformQuestion(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();

  if (!prompt) {
    stream.markdown([
      '### FRP Agent\n',
      'I can help you manage the File Reception Portal. Just ask in plain English:\n',
      '| Example | What it does |',
      '|---------|-------------|',
      '| "list all email jobs" | Search monitoring jobs |',
      '| "tell me about job CMBS_GreyCo" | Deep-dive into a single job + linked deals |',
      '| "which jobs handle deal CSMC" | Reverse lookup: deal → jobs |',
      '| "validate all configs" | Lint job configurations |',
      '| "show template patterns" | Template inventory |',
      '| "coverage gaps for servicer 569" | Gap analysis |',
      '| "detect orphaned jobs" | Orphan detection |',
      '| "sync logs" | Sync application logs |',
      '| "what happened today" | Daily summary |',
      '| "save email settings" | Deploy Settings.xml |',
      '| "what changed since last deploy" | Diff against backup |',
      '| "triage this email" | Match email against configs |',
      '| "system health report" | Full health analysis |',
      '| "what\'s failing" | Processing failure analysis |',
      '| "manual queue report" | Manual vs automated breakdown |',
      '| "pipeline for CSMC" | End-to-end pipeline view |',
      '',
      'Or use slash commands: `/jobs`, `/deals`, `/logs`, `/deploy`, `/triage`, `/analyze`, `/staging`',
    ].join('\n'));

    return {
      followUps: [
        { prompt: 'list all email jobs', label: 'Browse jobs' },
        { prompt: 'what happened today', label: 'Daily summary' },
        { prompt: 'system health report', label: 'Health check' },
      ],
    };
  }

  // ── LLM Tool-Calling Router ─────────────────────────────────── //
  // ALL routing goes through the Phase 7/8/9 smart path:
  // Stage 1 classifies intent, Stage 2 picks the right tool.
  let toolResult = null;
  try {
    toolResult = await routeWithToolCalling(prompt, request, context, stream, token, shared);
  } catch (routeErr) {
    shared.outputChannel.appendLine(`[FRP]   ✗ routeWithToolCalling threw: ${routeErr.message}`);
  }
  if (toolResult !== null) {
    return toolResult;
  }

  // ── Routing failed — tell the user clearly ────────────────── //
  shared.outputChannel.appendLine('[FRP] ROUTING END: all stages failed');
  stream.markdown(
    '⚠️ I could not route your question to the right tool. Please try rephrasing your question.\n\n' +
    'Some examples I understand well:\n' +
    '- "list all scrubbers queued for DID X in last 25 days"\n' +
    '- "has template TPMT_SPS been processed today"\n' +
    '- "what jobs handle deal CMLTI 2014-A"\n' +
    '- "show processing history for servicer 296"\n'
  );

  return {
    followUps: [
      { prompt: 'list all email jobs', label: 'Search jobs' },
      { prompt: 'system health report', label: 'Health check' },
    ],
  };
}

// ---------------------------------------------------------------------------
// Phase 2: Job CRUD handlers
// ---------------------------------------------------------------------------

/**
 * /jobs create — Create a new job from template
 */
async function handleJobCreate(newName, templateJob, overrides, xmlType, request, context, stream, token, shared) {
  // Validate params
  if (!newName || !templateJob) {
    stream.markdown('Missing required parameters: newName and templateJob are required.\n');
    return { followUps: [{ prompt: 'show template patterns', label: 'List available templates' }] };
  }

  // Preview template
  stream.progress(`Looking up template "${templateJob}"...`);
  const preview = await backendCall('search_jobs', { query: templateJob }, shared);

  if (!preview?.data?.jobs?.length) {
    stream.markdown(`❌ Template job "${templateJob}" not found.\n`);
    return { followUps: [{ prompt: 'show template patterns', label: 'List available templates' }] };
  }

  // Show preview + proposed creation
  const templateData = preview.data.jobs[0];
  stream.markdown(`**Template:** ${templateData.name || templateJob}\n`);
  stream.markdown(`\n**Proposed:** Create new job \`${newName}\` from template \`${templateJob}\` (${xmlType || 'email'})\n`);
  if (overrides && Object.keys(overrides).length > 0) {
    stream.markdown(`**Overrides:** ${Object.entries(overrides).map(([k, v]) => `${k}=${v}`).join(', ')}\n`);
  }

  // Store pending operation for confirmation
  shared.pendingOperation = {
    type: 'create_job',
    params: { newName, templateJob, overrides, xmlType: xmlType || 'email' },
  };

  // Inline confirmation
  stream.markdown('\n**Confirm this creation?**\n');
  if (typeof stream.button === 'function') {
    stream.button({ title: 'Confirm ✓', command: 'frp.confirmPending' });
    stream.button({ title: 'Cancel ✗', command: 'frp.cancelPending' });
  } else {
    stream.markdown('Type **yes** to confirm or **no** to cancel.\n');
  }

  return { followUps: [] };
}

/**
 * /jobs edit — Edit a field on an existing job
 */
async function handleJobEdit(jobName, field, value, xmlType, request, context, stream, token, shared) {
  // Validate params
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

  // Step 2: Render before/after diff
  const currentValue = resolveCurrentFieldValue(currentData, field, xmlType);
  stream.markdown(renderEditDiff(jobName, field, currentValue, value, xmlType));

  // Step 3: Store pending operation for confirmation
  shared.pendingOperation = {
    type: 'edit_job',
    params: { jobName, field, value, xmlType: xmlType || 'email' },
  };

  // Inline confirmation
  stream.markdown('\n**Confirm this change?**\n');
  if (typeof stream.button === 'function') {
    stream.button({ title: 'Confirm ✓', command: 'frp.confirmPending' });
    stream.button({ title: 'Cancel ✗', command: 'frp.cancelPending' });
  } else {
    stream.markdown('Type **yes** to confirm or **no** to cancel.\n');
  }

  return { followUps: [] };
}

/**
 * /jobs templates — List available job templates
 */
async function handleJobTemplates(prompt, request, context, stream, token, shared) {
  const filterPart = prompt.replace(/^templates?\s*/i, '').trim();

  stream.progress('Discovering templates...');
  const params = {};
  if (filterPart) params.filter = filterPart;

  const data = await backendCall('template_inventory', params, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    filterPart ? `Template inventory filtered by "${filterPart}".` : 'Show all discovered job template patterns.',
    'Present as a table with: Pattern Name, Parsers, Templates, Job Count, Has ServicerID, Example Job.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);

  const followUps = [];
  if (data?.data?.templates?.length > 0) {
    const first = data.data.templates[0];
    followUps.push({
      prompt: `/jobs create "New Job" from "${first.example_job_name}"`,
      label: `Create from "${first.example_job_name}"`,
    });
  }
  return { followUps };
}

// ---------------------------------------------------------------------------
// Phase 2: Deal intelligence handlers
// ---------------------------------------------------------------------------

/**
 * /deals gaps — Coverage gap analysis
 */
async function handleCoverageGaps(prompt, request, context, stream, token, shared) {
  const match = prompt.match(/^gaps?\s+(\S+)/i);
  const servicerId = match ? match[1] : 'all';

  stream.progress(`Analyzing coverage gaps${servicerId !== 'all' ? ` for CompanyID ${servicerId}` : ''}...`);

  const data = await backendCall('coverage_gaps', { servicerId }, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `Coverage gap analysis for ${servicerId === 'all' ? 'all servicers' : `CompanyID ${servicerId}`}.`,
    'Show coverage percentage, total/mapped/unmapped DIDs.',
    'If there are unmapped DIDs, list them. Highlight low coverage.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deals', request, stream, token);

  return {
    followUps: [
      { prompt: 'detect orphaned jobs', label: 'Check for orphaned jobs' },
      { prompt: 'detect ImportDID collisions', label: 'Check for ImportDID collisions' },
    ],
  };
}

/**
 * /deals orphans — Orphan detection
 */
async function handleOrphanDetection(prompt, request, context, stream, token, shared) {
  stream.progress('Detecting orphaned jobs...');

  const data = await backendCall('orphan_detection', {}, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    'Show orphan detection results. An orphan is a job with a ServicerID that has no matching database records.',
    'List each orphan with: Job Name, ServicerID, Reason (no_db_match / no_deal_data).',
    'Jobs without ServicerID are NOT orphans — they are shelf-level/process-level.',
    'If no orphans found, confirm that.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deals', request, stream, token);

  return {
    followUps: [
      { prompt: 'coverage gaps', label: 'Check coverage gaps' },
      { prompt: 'detect ImportDID collisions', label: 'Check collisions' },
    ],
  };
}

/**
 * /deals collisions — ImportDID collision detection
 */
async function handleCollisionDetection(prompt, request, context, stream, token, shared) {
  stream.progress('Detecting ImportDID collisions...');

  const data = await backendCall('collision_detection', {}, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    'Show ImportDID collision detection results.',
    'A collision = same ImportDID keyword matches DIFFERENT CompanyIDs (NOT same CompanyID with multiple DIDs).',
    'List each collision with: ImportDID keyword, Matching CompanyIDs, Affected Jobs, Risk Level.',
    'If no collisions found, confirm that.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deals', request, stream, token);

  return {
    followUps: [
      { prompt: 'coverage gaps', label: 'Check coverage gaps' },
      { prompt: 'detect orphaned jobs', label: 'Check orphans' },
    ],
  };
}

// ---------------------------------------------------------------------------
// Phase 2: Deploy diff & rollback handlers
// ---------------------------------------------------------------------------

/**
 * /deploy diff — Compare current Settings.xml to backup
 */
async function handleXmlDiff(prompt, request, context, stream, token, shared) {
  const match = prompt.match(/^diff\s+(.+)/i);
  const params = {};
  if (match) params.backupFile = match[1].trim();

  stream.progress('Computing diff...');
  const data = await backendCall('xml_diff', params, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [{ prompt: 'save email settings', label: 'Create a backup first' }] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    'Show the job-level diff between current Settings.xml and the backup.',
    'List: Added jobs, Removed jobs, Modified jobs (with field changes before→after).',
    'Show unchanged count. Summarise the changes.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deploy', request, stream, token);

  const followUps = [{ prompt: 'list backups', label: 'List all backups' }];
  if (data?.data?.total_changes > 0) {
    const backupFile = data?.data?.backup_file || '';
    if (backupFile) {
      followUps.push({ prompt: `/deploy rollback ${backupFile}`, label: 'Rollback to this backup' });
    }
  }
  return { followUps };
}

/**
 * /deploy rollback — Restore Settings.xml from backup
 */
async function handleRollback(backupFile, request, context, stream, token, shared) {
  // Validate params
  if (!backupFile) {
    stream.markdown([
      '### Rollback Settings.xml\n',
      '**Usage:** `/deploy rollback <backup_filename>`\n',
      '**Example:** `/deploy rollback Settings_20260201_120000.xml`\n',
      'A diff will be shown first for review before confirming.',
    ].join('\n'));
    return { followUps: [{ prompt: 'list backups', label: 'List available backups' }] };
  }

  // Step 1: Show diff first
  stream.progress('Loading diff for review...');
  const diffData = await backendCall('xml_diff', { backupFile }, shared);

  if (diffData?.data) {
    const llmPrompt = [
      SYSTEM_PROMPT, '',
      '<data>', JSON.stringify(diffData, null, 2), '</data>', '',
      `Preview of changes if we rollback to "${backupFile}":`,
      'Show what would change. This is for the user to review before confirming.',
    ].join('\n');
    await generateOrFallback(llmPrompt, diffData, 'deploy', request, stream, token);
  }

  // Step 2: Store pending operation for confirmation
  shared.pendingOperation = {
    type: 'rollback',
    params: { backupFile },
  };

  stream.markdown('\n**Confirm this rollback?**\n');
  if (typeof stream.button === 'function') {
    stream.button({ title: 'Confirm ✓', command: 'frp.confirmPending' });
    stream.button({ title: 'Cancel ✗', command: 'frp.cancelPending' });
  } else {
    stream.markdown('Type **yes** to confirm or **no** to cancel.\n');
  }

  return { followUps: [] };
}

// ---------------------------------------------------------------------------
// New handlers: job_detail, deal_lookup, status
// ---------------------------------------------------------------------------

/**
 * Job Detail — Deep-dive into a single job with tblExternalDIDRef cross-ref.
 */
async function handleJobDetail(jobName, request, context, stream, token, shared) {
  stream.progress(`Looking up "${jobName}"...`);

  const data = await backendCall('job_detail', { jobName }, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return {
      followUps: [
        { prompt: `list all jobs matching ${jobName}`, label: `Search "${jobName}"` },
      ],
    };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `The user asked for complete details on job "${jobName}".`,
    '',
    'Present the job configuration as a clean two-column table (Field | Value). Rules:',
    '- Label the automation workflow field as "Scrubber" (from the template/scrubber field), not "Templates.Main".',
    '- For match_mode, explain in plain English: Subject → "Matches keyword in email subject line"; Filename → "Matches attachment filename".',
    '- Show file paths EXACTLY as-is inside backticks, preserving every backslash (\\) and curly bracket ({}).',
    '- Omit any field that is null or empty (e.g., do not show Day Adjust if null).',
    '- Do NOT show raw JSON snippets or source data.',
    '- Do NOT fabricate DealName or Subject columns.',
    '',
    '**Linked Deals section:**',
    '- If linked_deals array has entries, show a table with columns: DealName (DID), Keyword (ImportDID), CompanyID.',
    '  The ImportDID is the keyword the system searches for in incoming emails to route files to the correct deal.',
    '- If linked_deals is empty AND linked_deal_count is 0, clearly state: "No deal mappings found in tblExternalDIDRef for ServicerID <N>."',
    '  Then suggest the user check the database connection or that this may be a shelf-level/utility job.',
    '',
    '**Recent Processing section:**',
    '- If recent_processing is present and has records, show a section titled "Recent Processing" with a table:',
    '  Status | ProcessStarted | Duration | FilePath.',
    '  Use ✅/❌ for status. Show file paths in backticks.',
    '- If recent_processing is missing or empty, skip this section silently.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'jobs', request, stream, token);

  // Build contextual follow-ups
  const followUps = [
    { prompt: `which jobs handle servicer ${data?.data?.servicer_id || ''}`.trim(), label: 'Related jobs' },
  ];
  if (data?.data?.scrubber) {
    followUps.push({ prompt: `list jobs using scrubber ${data.data.scrubber}`, label: `Jobs using ${data.data.scrubber}` });
  }
  followUps.push({ prompt: `check health for ${jobName}`, label: `Health: ${jobName}` });

  return { followUps };
}

/**
 * Deal Lookup — Reverse query: deal name/DID/CompanyID → matching jobs.
 */
async function handleDealLookup(query, request, context, stream, token, shared) {
  stream.progress(`Looking up deals matching "${query}"...`);

  const data = await backendCall('deal_lookup', { query }, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  // ── Clean "not found" UX — no LLM speculation needed ──
  const deals = data?.data?.deals || [];
  const jobs  = data?.data?.matching_jobs || [];

  if (deals.length === 0 && jobs.length === 0) {
    stream.markdown([
      `### Deal Lookup: "${query}"\n`,
      `❌ **Not found.** No records exist in \`tblExternalDIDRef\` matching \`${query}\`.\n`,
      'This means:',
      '- No keyword (ImportDID) has been configured for this deal',
      '- No CompanyID links this deal to any monitoring job',
      '- Files for this deal **will not be auto-detected** by the system\n',
      '**To set up this deal**, a row must be added to `tblExternalDIDRef` with the deal\'s DID, an ImportDID keyword, and the CompanyID of the servicer whose monitoring job should handle it.',
    ].join('\n'));
    stream.markdown(dataSourceFooter(data));
    return {
      followUps: [
        { prompt: 'coverage gaps', label: 'Check coverage gaps' },
        { prompt: 'list all jobs', label: 'Browse jobs' },
      ],
    };
  }

  const llmPrompt = [
    SYSTEM_PROMPT,
    '',
    '<data>',
    JSON.stringify(data, null, 2),
    '</data>',
    '',
    `The user asked which jobs handle "${query}".`,
    'Present the results in two sections:',
    '1. **Matched Deals** — table of DID, ImportDID (keyword), CompanyID from tblExternalDIDRef',
    '2. **Monitoring Jobs** — table of jobs whose ServicerID matches the CompanyIDs found',
    '   Columns: JobName, Sender, ServicerID, Scrubber, MatchMode, SavePath',
    'RULES:',
    '- Show file paths EXACTLY as provided inside backticks — preserve every backslash and curly bracket.',
    '- NEVER show raw JSON snippets or code blocks with JSON.',
    '- Omit any field whose value is null, empty, or "N/A".',
    '- Do NOT fabricate DealName or Subject columns.',
    'If deals matched but no jobs serve them, note the coverage gap.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'deals', request, stream, token);

  stream.markdown(dataSourceFooter(data));

  const followUps = [{ prompt: `coverage gaps`, label: 'Check gaps' }];
  if (jobs.length > 0) {
    const first = jobs[0];
    followUps.unshift({
      prompt: `tell me about job ${first.job_name || first.name}`,
      label: `Detail: ${first.job_name || first.name}`,
    });
  }

  return { followUps };
}

/**
 * Status — Quick agent status check.
 */
async function handleStatusIntent(stream, shared) {
  try {
    const data = await backendCall('search_jobs', { query: '' }, shared);
    const jobCount = data?.data?.jobs?.length ?? '?';
    stream.markdown([
      '### FRP Agent Status\n',
      `- **Backend:** Connected`,
      `- **Jobs found:** ${jobCount}`,
      `- **Ready:** Yes`,
    ].join('\n'));
  } catch (err) {
    stream.markdown([
      '### FRP Agent Status\n',
      `- **Backend:** ❌ Not responding — ${err.message}`,
    ].join('\n'));
  }
  return {
    followUps: [
      { prompt: 'list all email jobs', label: 'Browse jobs' },
      { prompt: 'system health report', label: 'Health check' },
    ],
  };
}

// ---------------------------------------------------------------------------
// Phase 5: tblTemplateStaging handlers
// ---------------------------------------------------------------------------

/**
 * Template Status — recent runs, success/failure ratio, last run time.
 */
async function handleTemplateStatus(input, request, context, stream, token, shared) {
  const query = input.query || request.prompt;
  stream.progress(`Checking template status for "${query}"...`);

  const args = { query };
  if (input.days) args.days = String(input.days);
  const data = await backendCall('template_status', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [{ prompt: `staging search ${query}`, label: `Search staging for "${query}"` }] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user asked for the processing status of "${query}".`,
    'Present the data in these sections:',
    '1. **Summary** — total runs, success rate %, last run timestamp.',
    '2. **Recent Runs** — table: TemplateName | DID | Status | ProcessStarted | Duration | FilePath.',
    '   Use ✅ for success, ❌ for failure in the Status column.',
    'Show file paths exactly as-is inside backticks. Omit null/empty fields.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'staging', request, stream, token);

  const followUps = [
    { prompt: `failure analysis for ${query}`, label: 'Failure analysis' },
    { prompt: `processing duration for ${query}`, label: 'Duration stats' },
  ];
  return { followUps };
}

/**
 * Processing History — full history for a deal, servicer, or template.
 */
async function handleProcessingHistory(input, request, context, stream, token, shared) {
  const query = input.query || request.prompt;
  stream.progress(`Loading processing history for "${query}"...`);

  const args = { query };
  if (input.startDate) args.startDate = input.startDate;
  if (input.endDate) args.endDate = input.endDate;
  const data = await backendCall('processing_history', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user asked for processing history for "${query}".`,
    'Present a table with columns: TemplateName | DID | ServicerID | Status | ProcessStarted | Duration | FilePath.',
    'Use ✅/❌ for status. Show file paths in backticks. If there is a summary section, show it first.',
    'If date range was applied, mention the date range at the top.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'staging', request, stream, token);

  return {
    followUps: [
      { prompt: `failure analysis for ${query}`, label: 'Analyze failures' },
      { prompt: `template status ${query}`, label: 'Status summary' },
    ],
  };
}

/**
 * Failure Analysis — error patterns, affected deals/templates.
 */
async function handleFailureAnalysis(input, request, context, stream, token, shared) {
  stream.progress('Analyzing processing failures...');

  const args = {};
  if (input.template) args.template = input.template;
  if (input.did) args.did = input.did;
  if (input.days) args.days = String(input.days);
  const data = await backendCall('failure_analysis', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const filterDesc = input.template ? `template "${input.template}"` : input.did ? `DID "${input.did}"` : 'all templates';
  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user asked for failure analysis filtered to ${filterDesc}.`,
    'Present the data in these sections:',
    '1. **Summary** — total failures, failure rate, period covered.',
    '2. **Failure Groups** — table showing error patterns and which templates/deals they affect.',
    '3. **Recent Failures** — table of recent failed runs: TemplateName | DID | ProcessStarted | FilePath | Error.',
    'Highlight the most critical failures (most frequent, most recent). Suggest remediation where possible.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'failures', request, stream, token);

  return {
    followUps: [
      { prompt: 'system health report', label: 'Health check' },
      { prompt: 'manual queue report', label: 'Manual queue stats' },
    ],
  };
}

/**
 * Source Trace — trace where a file came from.
 */
async function handleSourceTrace(input, request, context, stream, token, shared) {
  const filepath = input.filepath || request.prompt;
  stream.progress(`Tracing source for "${filepath}"...`);

  const data = await backendCall('source_trace', { filepath }, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user asked to trace the source of file "${filepath}".`,
    'Present the data showing:',
    '1. **Source** — where the file came from (email mailbox, SFTP, or manual queue).',
    '2. **Processing Details** — which template processed it, when, status, duration.',
    '3. If multiple records match, show a table of all matches.',
    'Show file paths exactly in backticks. Explain the source_type in plain English.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'trace', request, stream, token);

  return {
    followUps: [
      { prompt: `template status for the template that processed this file`, label: 'Template status' },
    ],
  };
}

/**
 * Manual Queue Report — manual vs automated processing breakdown.
 */
async function handleManualQueue(input, request, context, stream, token, shared) {
  stream.progress('Generating manual queue report...');

  const args = {};
  if (input.days) args.days = String(input.days);
  if (input.template) args.template = input.template;
  if (input.servicerId) args.servicerId = input.servicerId;
  const data = await backendCall('manual_queue_report', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    'The user asked for a manual queue report — showing manual vs automated processing breakdown.',
    'Present the data in these sections:',
    '1. **Overview** — total runs, manual count, automated count, manual percentage.',
    '2. **By Template** — table showing which templates have the most manual queuing: TemplateName | Manual | Automated | Manual %.',
    '3. **Top Operators** — who is manually queuing and how often.',
    'Highlight automation gaps — templates with high manual rates are candidates for automation improvement.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'manual_queue', request, stream, token);

  return {
    followUps: [
      { prompt: 'failure analysis', label: 'Failure analysis' },
      { prompt: 'processing duration report', label: 'Duration stats' },
    ],
  };
}

/**
 * Processing Duration — timing analysis with outlier detection.
 */
async function handleProcessingDuration(input, request, context, stream, token, shared) {
  stream.progress('Analyzing processing durations...');

  const args = {};
  if (input.template) args.template = input.template;
  if (input.days) args.days = String(input.days);
  if (input.sort) args.sort = input.sort;
  const data = await backendCall('processing_duration', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    'The user asked for processing duration analysis.',
    'Present the data in these sections:',
    '1. **Overall Stats** — average, min, max, total processing time.',
    '2. **By Template** — table: TemplateName | AvgDuration | MinDuration | MaxDuration | TotalRuns.',
    '   Sort by the requested sort column (default: avg_seconds descending).',
    '3. **Outliers** — if outlier data is present, highlight unusually slow runs.',
    'Format durations as human-readable (e.g., "2m 34s" instead of raw seconds).',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'duration', request, stream, token);

  return {
    followUps: [
      { prompt: 'failure analysis', label: 'Check failures' },
      { prompt: 'system health report', label: 'Health check' },
    ],
  };
}

/**
 * Deal Pipeline — end-to-end three-layer pipeline view.
 */
async function handleDealPipeline(input, request, context, stream, token, shared) {
  const query = input.query || request.prompt;
  stream.progress(`Building pipeline view for "${query}"...`);

  const args = { query };
  if (input.days) args.days = String(input.days);
  const data = await backendCall('deal_pipeline', args, shared);

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [{ prompt: `deal lookup ${query}`, label: `Look up "${query}" in deals` }] };
  }

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user asked for the end-to-end pipeline view of "${query}".`,
    'This combines three layers: Settings.xml config → tblExternalDIDRef mapping → tblTemplateStaging execution.',
    'Present the data in these sections:',
    '1. **Pipeline Overview** — health score, status summary.',
    '2. **Configuration Layer** — Settings.xml job config (if present).',
    '3. **Deal Mapping Layer** — tblExternalDIDRef records (DID, ImportDID, CompanyID).',
    '4. **Execution Layer** — recent processing from tblTemplateStaging (runs, success rate, last run).',
    '5. **Gap Analysis** — highlight gaps: configured but not processing, processing but not configured, etc.',
    'Use ✅/❌/⚠️ indicators. Show file paths in backticks.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'pipeline', request, stream, token);

  const followUps = [
    { prompt: `processing history for ${query}`, label: 'Full history' },
    { prompt: `failure analysis for ${query}`, label: 'Failure analysis' },
  ];
  return { followUps };
}

/**
 * Staging Search — direct search of tblTemplateStaging.
 */
async function handleStagingSearch(input, request, context, stream, token, shared) {
  let query = input.query || request.prompt;

  // ── Extract ALL column = value filters from the prompt ──
  // Matches patterns like: TemplateName = "QueueCMBS_Scrubber_x", DID = 'FREMF 2026-KF169'
  // Supports any tblTemplateStaging column name.
  const validColumns = new Set([
    'templateprocessid', 'templatename', 'filepath', 'did', 'dt',
    'starttime', 'endtime', 'machine', 'username', 'resultcode',
    'comments', 'servicerid', 'sourceprocess', 'job', 'datasource',
    'priority', 'serverside', 'pid', 'notify', 'emaillist',
    'notificationsent',
  ]);

  // Canonical casing map
  const canonicalName = {
    templateprocessid: 'TemplateProcessID', templatename: 'TemplateName',
    filepath: 'FilePath', did: 'DID', dt: 'Dt',
    starttime: 'StartTime', endtime: 'EndTime', machine: 'Machine',
    username: 'UserName', resultcode: 'ResultCode', comments: 'Comments',
    servicerid: 'ServicerID', sourceprocess: 'SourceProcess', job: 'Job',
    datasource: 'DataSource', priority: 'Priority', serverside: 'ServerSide',
    pid: 'PID', notify: 'Notify', emaillist: 'EmailList',
    notificationsent: 'NotificationSent',
  };

  const filters = {};
  const kvRegex = /(\w+)\s*=\s*["']([^"']+)["']/gi;
  let m;
  while ((m = kvRegex.exec(query)) !== null) {
    const colLower = m[1].toLowerCase();
    if (validColumns.has(colLower)) {
      filters[canonicalName[colLower]] = m[2].trim();
    }
  }

  // Also match unquoted numeric values: e.g. ServicerID = 569, ResultCode = 1
  const kvNumRegex = /(\w+)\s*=\s*(\d+)(?:\s|,|$)/gi;
  while ((m = kvNumRegex.exec(query)) !== null) {
    const colLower = m[1].toLowerCase();
    if (validColumns.has(colLower) && !filters[canonicalName[colLower]]) {
      filters[canonicalName[colLower]] = m[2].trim();
    }
  }

  // Extract optional limit from "top N" / "last N" / "limit N"
  const limitMatch = query.match(/\b(?:top|last|limit)\s+(\d+)\b/i);
  const limit = limitMatch ? parseInt(limitMatch[1], 10) : 50;

  const filterCount = Object.keys(filters).length;

  let data;
  if (filterCount > 0) {
    const filterDesc = Object.entries(filters).map(([k, v]) => `${k}="${v}"`).join(', ');
    stream.progress(`Searching tblTemplateStaging where ${filterDesc}…`);
    data = await backendCall('staging_search', {
      filters: JSON.stringify(filters),
      limit,
    }, shared);
  } else {
    // Fallback: single-term search via the existing search() cascade
    stream.progress(`Searching tblTemplateStaging for "${query}"…`);
    data = await backendCall('staging_search', { query }, shared);
  }

  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Error:** ${data.error || (data.errors || []).join(', ')}\n`);
    return { followUps: [] };
  }

  const searchDesc = filterCount > 0
    ? Object.entries(filters).map(([k, v]) => `${k}="${v}"`).join(' AND ')
    : query;

  const llmPrompt = [
    SYSTEM_PROMPT, '',
    '<data>', JSON.stringify(data, null, 2), '</data>', '',
    `The user searched tblTemplateStaging for: ${searchDesc}.`,
    'Present matching records in a table: TemplateProcessID | TemplateName | DID | ServicerID | Status | ProcessStarted | Duration | FilePath.',
    'Use ✅/❌ for status. Show file paths in backticks. If many results, show count and key patterns.',
  ].join('\n');

  await generateOrFallback(llmPrompt, data, 'staging', request, stream, token);

  return {
    followUps: [
      { prompt: `template status ${searchDesc}`, label: 'Status summary' },
      { prompt: `failure analysis`, label: 'Failure analysis' },
    ],
  };
}

/**
 * /staging — slash command handler for tblTemplateStaging operations.
 */
async function handleStagingCommand(request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const lower = prompt.toLowerCase();

  // Route subcommands
  if (/^status\b/i.test(prompt)) {
    const query = prompt.replace(/^status\s*/i, '').trim();
    return handleTemplateStatus({ query: query || '' }, request, context, stream, token, shared);
  }
  if (/^history\b/i.test(prompt)) {
    const query = prompt.replace(/^history\s*/i, '').trim();
    return handleProcessingHistory({ query: query || '' }, request, context, stream, token, shared);
  }
  if (/^fail(?:ure)?s?\b/i.test(prompt)) {
    const rest = prompt.replace(/^fail(?:ure)?s?\s*/i, '').trim();
    return handleFailureAnalysis({ template: rest || undefined }, request, context, stream, token, shared);
  }
  if (/^trace\b/i.test(prompt)) {
    const filepath = prompt.replace(/^trace\s*/i, '').trim();
    return handleSourceTrace({ filepath }, request, context, stream, token, shared);
  }
  if (/^manual\b/i.test(prompt)) {
    return handleManualQueue({}, request, context, stream, token, shared);
  }
  if (/^duration\b/i.test(prompt)) {
    const rest = prompt.replace(/^duration\s*/i, '').trim();
    return handleProcessingDuration({ template: rest || undefined }, request, context, stream, token, shared);
  }
  if (/^pipeline\b/i.test(prompt)) {
    const query = prompt.replace(/^pipeline\s*/i, '').trim();
    return handleDealPipeline({ query: query || '' }, request, context, stream, token, shared);
  }
  if (/^search\b/i.test(prompt)) {
    const query = prompt.replace(/^search\s*/i, '').trim();
    return handleStagingSearch({ query: query || '' }, request, context, stream, token, shared);
  }

  // No recognized subcommand — treat as a search or show help
  if (prompt) {
    return handleStagingSearch({ query: prompt }, request, context, stream, token, shared);
  }

  // Show help
  stream.markdown([
    '### /staging commands\n',
    '| Command | Description |',
    '|---------|-------------|',
    '| `status <query>` | Check processing status for a template or deal |',
    '| `history <query>` | Full processing history for a deal/servicer/template |',
    '| `failures [template]` | Analyze processing failures |',
    '| `trace <filepath>` | Trace where a file came from |',
    '| `manual` | Manual vs automated queue breakdown |',
    '| `duration [template]` | Processing time analysis |',
    '| `pipeline <query>` | End-to-end pipeline view |',
    '| `search <query>` | Search tblTemplateStaging directly |',
    '',
  ].join('\n'));

  return {
    followUps: [
      { prompt: 'failure analysis', label: 'Show failures' },
      { prompt: 'manual queue report', label: 'Manual queue' },
    ],
  };
}

// ---------------------------------------------------------------------------
// Test Bench — classifier accuracy validation
// ---------------------------------------------------------------------------

/**
 * Run the classifier test bench against golden test cases.
 *
 * Reads test cases from extension/test/golden_test_cases.json, runs
 * classifyIntent() against each, and streams a pass/fail report.
 */
async function handleTestBenchCommand(request, context, stream, token, shared) {
  const fs = require('fs');
  const path = require('path');

  // Locate the golden test cases file
  const extensionRoot = shared.context.extensionPath;
  const testFile = path.join(extensionRoot, 'test', 'golden_test_cases.json');

  if (!fs.existsSync(testFile)) {
    stream.markdown('❌ **Test bench error:** `golden_test_cases.json` not found.\n');
    return { followUps: [] };
  }

  let testCases;
  try {
    testCases = JSON.parse(fs.readFileSync(testFile, 'utf8'));
  } catch (err) {
    stream.markdown(`❌ **Test bench error:** Failed to parse test cases: ${err.message}\n`);
    return { followUps: [] };
  }

  // Optional: filter by pattern or id range from prompt
  const filterPrompt = request.prompt.trim().toLowerCase();
  let filtered = testCases;
  if (filterPrompt && filterPrompt !== 'all') {
    // Support: "cross_layer", "1-20", "single_tool", etc.
    const rangeMatch = filterPrompt.match(/^(\d+)\s*-\s*(\d+)$/);
    if (rangeMatch) {
      const lo = parseInt(rangeMatch[1], 10);
      const hi = parseInt(rangeMatch[2], 10);
      filtered = testCases.filter(tc => tc.id >= lo && tc.id <= hi);
    } else {
      filtered = testCases.filter(tc =>
        tc.pattern.toLowerCase().includes(filterPrompt) ||
        tc.description.toLowerCase().includes(filterPrompt)
      );
    }
  }

  if (filtered.length === 0) {
    stream.markdown(`⚠️ No test cases matched filter: "${filterPrompt}"\n`);
    return { followUps: [] };
  }

  const model = await selectModel(request);
  if (!model) {
    stream.markdown('❌ **Test bench error:** No LLM model available.\n');
    return { followUps: [] };
  }

  stream.markdown(`### 🧪 Classifier Test Bench\n\nRunning **${filtered.length}** test cases…\n\n`);

  let passed = 0;
  let failed = 0;
  const failures = [];
  const warnings = [];

  for (const tc of filtered) {
    if (token.isCancellationRequested) {
      stream.markdown('\n⚠️ Test bench cancelled.\n');
      break;
    }

    try {
      const result = await classifyIntent(tc.prompt, '', model, token, shared);

      const catOk = result && (
        result.category === tc.expected_category ||
        (tc.expected_category_any && tc.expected_category_any.includes(result.category))
      );
      const modeOk = result && result.mode === tc.expected_mode;
      const pipeOk = result && (result.pipeline || null) === (tc.expected_pipeline || null);

      // In pipeline mode, category doesn't affect routing (all 36 tools available),
      // so a category mismatch is a soft warning, not a hard failure.
      const isSoftFail = !catOk && modeOk && pipeOk && result && result.mode === 'pipeline';

      if (catOk && modeOk && pipeOk) {
        passed++;
      } else if (isSoftFail) {
        passed++;
        warnings.push({
          id: tc.id,
          prompt: tc.prompt.length > 80 ? tc.prompt.slice(0, 77) + '...' : tc.prompt,
          expected_cat: tc.expected_category,
          actual_cat: result.category,
          description: tc.description,
        });
      } else {
        failed++;
        failures.push({
          id: tc.id,
          prompt: tc.prompt.length > 80 ? tc.prompt.slice(0, 77) + '...' : tc.prompt,
          expected: `${tc.expected_category} / ${tc.expected_mode} / ${tc.expected_pipeline || 'null'}`,
          actual: result
            ? `${result.category} / ${result.mode} / ${result.pipeline || 'null'}`
            : 'null (classifier failed)',
          description: tc.description,
        });
      }
    } catch (err) {
      failed++;
      failures.push({
        id: tc.id,
        prompt: tc.prompt.length > 80 ? tc.prompt.slice(0, 77) + '...' : tc.prompt,
        expected: `${tc.expected_category} / ${tc.expected_mode} / ${tc.expected_pipeline || 'null'}`,
        actual: `ERROR: ${err.message}`,
        description: tc.description,
      });
    }

    // Progress indicator every 10 cases
    if ((passed + failed) % 10 === 0) {
      stream.markdown(`⏳ Progress: ${passed + failed}/${filtered.length} (${passed} ✅ ${failed} ❌)\n\n`);
    }
  }

  // Summary
  const total = passed + failed;
  const pct = total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0';
  stream.markdown(`\n---\n### Results: ${passed}/${total} passed (${pct}%)\n\n`);

  if (failures.length > 0) {
    stream.markdown('### ❌ Failures\n\n');
    stream.markdown('| # | Pattern | Prompt | Expected | Actual |\n');
    stream.markdown('|---|---------|--------|----------|--------|\n');
    for (const f of failures) {
      stream.markdown(`| ${f.id} | ${f.description} | ${f.prompt} | ${f.expected} | ${f.actual} |\n`);
    }
  }

  if (warnings.length > 0) {
    stream.markdown('### ⚠️ Soft Warnings (category mismatch in pipeline mode — no routing impact)\n\n');
    stream.markdown('| # | Pattern | Expected Cat | Actual Cat |\n');
    stream.markdown('|---|---------|-------------|-----------|\n');
    for (const w of warnings) {
      stream.markdown(`| ${w.id} | ${w.description} | ${w.expected_cat} | ${w.actual_cat} |\n`);
    }
    stream.markdown('\n');
  }

  if (failures.length === 0) {
    stream.markdown('**All tests passed!** ✅\n');
  }

  shared.outputChannel.appendLine(`[FRP] Test bench complete: ${passed}/${total} passed (${pct}%), ${warnings.length} soft warnings`);

  return { followUps: [] };
}

// ---------------------------------------------------------------------------
// Command dispatch map
// ---------------------------------------------------------------------------

const COMMAND_HANDLERS = {
  jobs: handleJobsCommand,
  deals: handleDealsCommand,
  logs: handleLogsCommand,
  deploy: handleDeployCommand,
  triage: handleTriageCommand,
  analyze: handleAnalyzeCommand,
  staging: handleStagingCommand,
  testbench: handleTestBenchCommand,
};

// ---------------------------------------------------------------------------
// Chat participant registration
// ---------------------------------------------------------------------------

/**
 * Register the @frp chat participant.
 *
 * @param {typeof import('vscode')} vscode
 * @param {import('vscode').ExtensionContext} ctx
 * @param {Object} shared  Shared state { context, outputChannel, workspaceRoot }
 */
function registerChatParticipant(vscode, ctx, shared) {
  const participant = vscode.chat.createChatParticipant(PARTICIPANT_ID, async (request, context, stream, token) => {
    const commandName = request.command; // e.g. 'jobs', 'deals', etc.

    shared.outputChannel.appendLine(
      `[FRP] Chat request — command: ${commandName || '(none)'}, prompt: "${request.prompt.slice(0, 100)}"`
    );

    // ── Pending confirmation check ──────────────────────────────────
    if (shared.pendingOperation) {
      const lc = request.prompt.toLowerCase().trim();
      const isConfirm = /^(yes|y|confirm|apply|ok|proceed|do\s+it|sure|go ahead)/.test(lc);
      const isCancel  = /^(no|n|cancel|stop|abort|nevermind|nope|don.?t)/.test(lc);

      if (isConfirm || isCancel) {
        const op = shared.pendingOperation;
        shared.pendingOperation = null;

        if (isCancel) {
          stream.markdown('Operation cancelled.\n');
          shared._lastFollowUps = [];
          return;
        }

        let result;
        switch (op.type) {
          case 'edit_job':    result = await executeConfirmedEdit(op.params,     request, context, stream, token, shared); break;
          case 'create_job':  result = await executeConfirmedCreate(op.params,   request, context, stream, token, shared); break;
          case 'rollback':    result = await executeConfirmedRollback(op.params, request, context, stream, token, shared); break;
          case 'crud_plan':   result = await executeConfirmedCrudPlan(op.params, request, context, stream, token, shared); break;
          default:            stream.markdown('Unknown pending operation type.\n'); result = { followUps: [] };
        }

        shared._lastFollowUps = result?.followUps || [];
        return;
      }

      // Unrecognised response — clear pending and route normally
      shared.pendingOperation = null;
    }
    // ── End pending confirmation ─────────────────────────────────────

    let result;

    try {
      if (commandName && COMMAND_HANDLERS[commandName]) {
        result = await COMMAND_HANDLERS[commandName](request, context, stream, token, shared);
      } else {
        result = await handleFreeformQuestion(request, context, stream, token, shared);
      }
    } catch (err) {
      shared.outputChannel.appendLine(`[FRP] Handler error: ${err.message}\n${err.stack}`);

      if (err instanceof vscode.LanguageModelError) {
        stream.markdown(`⚠️ **Model error:** ${err.message}\n\nPlease try again or check your Copilot subscription.`);
      } else {
        stream.markdown(`❌ **Error:** ${err.message}\n`);
      }

      result = { followUps: [] };
    }

    // Stash follow-ups for the followupProvider
    shared._lastFollowUps = result?.followUps || [];

    return;
  });

  // Follow-up provider
  participant.followupProvider = {
    provideFollowups(_result, _context, _token) {
      const followUps = shared._lastFollowUps || [];
      return followUps.map((f) => ({
        prompt: f.prompt,
        label: f.label || f.prompt,
        participant: PARTICIPANT_ID,
      }));
    },
  };

  participant.iconPath = vscode.Uri.joinPath(ctx.extensionUri, 'media', 'icon.png');

  ctx.subscriptions.push(participant);
  shared.outputChannel.appendLine('[FRP] Chat participant registered.');
}

module.exports = { registerChatParticipant };
