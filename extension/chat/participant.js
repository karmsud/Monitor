const vscode = require('vscode');
const { backendCall } = require('../copilot/tool');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PARTICIPANT_ID = 'frp-agent.assistant';
const INLINE_CHAT_ACTION_COMMAND = 'frp.runInlineChatAction';
const TRUSTED_CHAT_COMMANDS = [INLINE_CHAT_ACTION_COMMAND];
const DETERMINISTIC_COMMAND_SPECS = {
  jobXML: {
    sourceKind: 'xml',
    sourceLabel: 'Settings.xml',
    xmlType: 'email',
    kindLabel: 'Email',
    preferredCommand: 'jobXMLEmail',
  },
  jobSQLite: {
    sourceKind: 'sqlite',
    sourceLabel: 'SQLite cache',
    xmlType: 'email',
    kindLabel: 'Email',
    preferredCommand: 'jobSQLiteEmail',
  },
  jobXMLEmail: {
    sourceKind: 'xml',
    sourceLabel: 'Settings.xml',
    xmlType: 'email',
    kindLabel: 'Email',
  },
  jobSQLiteEmail: {
    sourceKind: 'sqlite',
    sourceLabel: 'SQLite cache',
    xmlType: 'email',
    kindLabel: 'Email',
  },
  jobXMLSftp: {
    sourceKind: 'xml',
    sourceLabel: 'Settings.xml',
    xmlType: 'sftp',
    kindLabel: 'SFTP',
  },
  jobSQLiteSftp: {
    sourceKind: 'sqlite',
    sourceLabel: 'SQLite cache',
    xmlType: 'sftp',
    kindLabel: 'SFTP',
  },
};

const DETERMINISTIC_FIELD_ALIASES = {
  email: {
    job: { key: 'job_name', label: 'JobName' },
    jobname: { key: 'job_name', label: 'JobName' },
    name: { key: 'job_name', label: 'JobName' },
    mailbox: { key: 'mailbox', label: 'Mailbox' },
    sender: { key: 'sender', label: 'Sender' },
    servicer: { key: 'servicer_id', label: 'ServicerID' },
    servicerid: { key: 'servicer_id', label: 'ServicerID' },
    scrubber: { key: 'scrubber', label: 'Scrubber' },
    save: { key: 'save_path', label: 'SavePath' },
    savepath: { key: 'save_path', label: 'SavePath' },
  },
  sftp: {
    job: { key: 'job_name', label: 'JobName' },
    jobname: { key: 'job_name', label: 'JobName' },
    name: { key: 'job_name', label: 'JobName' },
    path: { key: 'sftp_path', label: 'Path' },
    sftppath: { key: 'sftp_path', label: 'Path' },
    dsn: { key: 'dsn', label: 'DSN' },
    servicer: { key: 'servicer_id', label: 'ServicerID' },
    servicerid: { key: 'servicer_id', label: 'ServicerID' },
    scrubber: { key: 'scrubber', label: 'Scrubber' },
    save: { key: 'save_path', label: 'SavePath' },
    savepath: { key: 'save_path', label: 'SavePath' },
    zip: { key: 'zip_filter', label: 'ZipFilter' },
    zipfilter: { key: 'zip_filter', label: 'ZipFilter' },
  },
};

const DETERMINISTIC_DEAL_MODE_ALIASES = {
  did: { mode: 'did', label: 'DID' },
  deal: { mode: 'did', label: 'DID' },
  keyword: { mode: 'keyword', label: 'ImportDID keyword' },
  importdid: { mode: 'keyword', label: 'ImportDID keyword' },
  company: { mode: 'company', label: 'CompanyID' },
  companyid: { mode: 'company', label: 'CompanyID' },
  servicer: { mode: 'servicer', label: 'ServicerID' },
  servicerid: { mode: 'servicer', label: 'ServicerID' },
  dossier: { mode: 'dossier', label: 'Servicer dossier' },
};

const DETERMINISTIC_STAGING_FIELD_ALIASES = {
  template: { field: 'template', label: 'TemplateName', kind: 'filter' },
  templatename: { field: 'template', label: 'TemplateName', kind: 'filter' },
  scrubber: { field: 'scrubber', label: 'Scrubber', kind: 'filter' },
  did: { field: 'did', label: 'DID', kind: 'filter' },
  deal: { field: 'did', label: 'DID', kind: 'filter' },
  servicer: { field: 'servicer', label: 'ServicerID', kind: 'filter' },
  servicerid: { field: 'servicer', label: 'ServicerID', kind: 'filter' },
  filepath: { field: 'filepath', label: 'FilePath', kind: 'filter' },
  path: { field: 'filepath', label: 'FilePath', kind: 'filter' },
  file: { field: 'filepath', label: 'FilePath', kind: 'filter' },
  source: { field: 'source', label: 'Source', kind: 'filter' },
  result: { field: 'result', label: 'Result', kind: 'filter' },
  state: { field: 'result', label: 'Result', kind: 'filter' },
  job: { field: 'job', label: 'Job', kind: 'filter' },
  datasource: { field: 'datasource', label: 'DataSource', kind: 'filter' },
  machine: { field: 'machine', label: 'Machine', kind: 'filter' },
  user: { field: 'user', label: 'UserName', kind: 'filter' },
  username: { field: 'user', label: 'UserName', kind: 'filter' },
  days: { field: 'days', label: 'Days', kind: 'control' },
  start: { field: 'start', label: 'StartDate', kind: 'control' },
  end: { field: 'end', label: 'EndDate', kind: 'control' },
};

const DETERMINISTIC_STAGING_AUDIT_SCOPES = new Set(['all', 'templates', 'jobs', 'filepath', 'process', 'servicers']);

const DETERMINISTIC_LOG_FIELD_ALIASES = {
  job: { field: 'job', label: 'JobName', kind: 'filter' },
  jobname: { field: 'job', label: 'JobName', kind: 'filter' },
  name: { field: 'job', label: 'JobName', kind: 'filter' },
  event: { field: 'event', label: 'EventType', kind: 'filter' },
  eventtype: { field: 'event', label: 'EventType', kind: 'filter' },
  type: { field: 'event', label: 'EventType', kind: 'filter' },
  sender: { field: 'sender', label: 'Sender', kind: 'filter' },
  mailbox: { field: 'mailbox', label: 'Mailbox', kind: 'filter' },
  parser: { field: 'parser', label: 'Parser', kind: 'filter' },
  filename: { field: 'filename', label: 'Filename', kind: 'filter' },
  file: { field: 'filename', label: 'Filename', kind: 'filter' },
  subject: { field: 'subject', label: 'Subject', kind: 'filter' },
  template: { field: 'template', label: 'Template', kind: 'filter' },
  scrubber: { field: 'template', label: 'Template', kind: 'filter' },
  log: { field: 'log', label: 'LogType', kind: 'filter' },
  logtype: { field: 'log', label: 'LogType', kind: 'filter' },
  days: { field: 'days', label: 'Days', kind: 'control' },
  start: { field: 'start', label: 'StartDate', kind: 'control' },
  end: { field: 'end', label: 'EndDate', kind: 'control' },
  limit: { field: 'limit', label: 'Limit', kind: 'control' },
  mode: { field: 'mode', label: 'Mode', kind: 'control' },
  view: { field: 'mode', label: 'Mode', kind: 'control' },
  sort: { field: 'sort', label: 'Sort', kind: 'control' },
  top: { field: 'top', label: 'Top', kind: 'control' },
  order: { field: 'order', label: 'Order', kind: 'control' },
  date: { field: 'date', label: 'Date', kind: 'control' },
};

const DETERMINISTIC_TRIAGE_FIELD_ALIASES = {
  from: { field: 'sender', label: 'Sender', kind: 'filter' },
  sender: { field: 'sender', label: 'Sender', kind: 'filter' },
  mailbox: { field: 'mailbox', label: 'Mailbox', kind: 'filter' },
  to: { field: 'mailbox', label: 'Mailbox', kind: 'filter' },
  subject: { field: 'subject', label: 'Subject', kind: 'filter' },
  filename: { field: 'filename', label: 'Filename', kind: 'filter' },
  file: { field: 'filename', label: 'Filename', kind: 'filter' },
  attachment: { field: 'filename', label: 'Filename', kind: 'filter' },
  body: { field: 'body', label: 'Body', kind: 'filter' },
  days: { field: 'days', label: 'Days', kind: 'control' },
  start: { field: 'start', label: 'StartDate', kind: 'control' },
  end: { field: 'end', label: 'EndDate', kind: 'control' },
};

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
   - See "Settings.xml Job Schema" section below for full field and element reference
   - Parsers per job: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script)

2. **tblExternalDIDRef** — Deal Reference Layer
   - Maps CompanyID → DealID (DID) + ImportDID (the keyword the system searches for in emails/files)
   - Key relationship: Job.ServicerID = tblExternalDIDRef.CompanyID
   - **Not all jobs have DIDs.** Process-level and shelf-level jobs (e.g. ABS_Deals_Queuer_x) legitimately have no deal mappings — they detach/move files without DID matching. An empty DID is normal for these jobs, not an error.

3. **tblTemplateStaging** — Processing Execution History
   - Every file the system has ever processed: timestamp, scrubber/template, success/failure, duration, filepath
   - Relationships: TemplateName = job's scrubber; DID/ServicerID link to deals

### tblTemplateStaging — Column Semantics

**Core identification columns:**
- **TemplateProcessID** — unique row identifier (PK)
- **TemplateName** — scrubber/template name from the job's settings.xml config
- **FilePath** — full path of the processed file (matches email attachment filename for email triggers)
- **DID** — Deal ID. Populated for deal-level jobs. **Empty for process/shelf-level jobs** — this is normal, not an error.
- **ServicerID** — links to tblExternalDIDRef.CompanyID and Settings.xml.ServicerID

**Timing & result columns:**
- **Dt** — report date / processing period
- **StartTime** — when processing began (NULL = queued but not started)
- **EndTime** — when processing finished (NULL = still in progress)
- **ResultCode** — 0 = Success ("Ok"), 1 = Failed (error detail in Comments)
- **Comments** — "Ok" on success; detailed error message on failure

**Processing state machine:**
| State | StartTime | EndTime | ResultCode | Comments |
|---|---|---|---|---|
| Never queued | *(no row)* | — | — | — |
| Queued, not started | NULL | NULL | — | — |
| In progress | NOT NULL | NULL | — | — |
| Success | NOT NULL | NOT NULL | 0 | "Ok" |
| Failed | NOT NULL | NOT NULL | 1 | error message |

**Trigger identification columns (critical for tracing):**

- **SourceProcess** — identifies the queuing mechanism, NOT the trigger type:
  - \`ActiveBatch\` = processed by ActiveBatch automation (covers ALL automated triggers: email, SFTP, and script-based)
  - \`ManualQueue\` = manually queued by a human user

- **Job** — the parser/script name from the job's settings.xml. Common patterns:
  - \`DetachFile\` — email attachment extraction parser (matches by filename)
  - \`DetachFileSubject\` — email parser that matches by subject line keyword
  - \`MoveFile\` / \`MoveFile2\` — SFTP file transfer parsers
  - \`DownloadAutomationv2.ps1 .\\settings\\<settingsFile>\` — PowerShell download automation script (email-triggered)
  - \`ManualJob\` — manually queued (pairs with SourceProcess=ManualQueue)
  - Other values may appear — custom parser/script names from settings.xml

- **DataSource** — the **definitive trigger type indicator**. This is the ONLY reliable way to determine how a file entered the system:
  - \`<mailbox@domain>: <email subject>\` → **Email-triggered** (e.g. \`USBankGSFABSMailboxShared@usbank.com: [EXTERNAL] SRL I Monthly Report...\`)
  - \`SFTPMonitor: <folder_path>\` → **SFTP-triggered** (e.g. \`SFTPMonitor: M:\\!Sweeps\\Ocwen\\In\`)
  - \`Queued via macro by <username>\` → **Manually queued** (e.g. \`Queued via macro by jmho\`)
  - Empty/null → unknown origin (secondary/child records)

**How to trace an email to its tblTemplateStaging record:**
1. Find TemplateName matching the job's scrubber (e.g. \`ABS_Deals_Queuer_x\`)
2. Check DataSource contains the mailbox AND email subject (confirms email trigger)
3. Check FilePath matches the expected attachment filename
4. Check Dt matches the expected processing date
5. Read ResultCode + Comments for outcome

**Other columns:** Machine (server hostname), UserName (service account), Priority, PID, Notify, EmailList, NotificationSent

### Cross-Reference Chains (how tables connect)
- Job→Deals: ServicerID → tblExternalDIDRef.CompanyID → all deals
- Deal→Jobs: CompanyID → Settings.xml jobs that use it as ServicerID
- Job→Processing: processing history by scrubber/TemplateName or ServicerID
- Deal→Processing: processing history by DID
- Email→Processing: DataSource contains \`<mailbox>: <subject>\` → matches the email to its staging record
- SFTP→Processing: DataSource contains \`SFTPMonitor: <path>\` → matches SFTP source to staging record
- Full pipeline: all three layers combined for one entity

### Settings.xml Job Schema

**Key convention:** A job's name IS its XML element tag. Jobs live inside a collection:
- Email: \`<MailboxCollection><JOB_NAME>...</JOB_NAME></MailboxCollection>\`
- SFTP:  \`<FolderCollection><JOB_NAME>...</JOB_NAME></FolderCollection>\`
There is NO \`<Job Name="...">\` wrapper. The tag IS the name.

#### Email Job — XML Structure
\`\`\`xml
<JOB_NAME>
  <Mailbox>rptent@usbank.com</Mailbox>          <!-- monitoring mailbox address -->
  <Folder>Inbox</Folder>                         <!-- mailbox subfolder to watch -->
  <SME>analyst@company.com</SME>                 <!-- subject matter expert -->
  <LastEmail>2/13/2026 12:07:15 PM</LastEmail>   <!-- auto-updated by system -->
  <SaveLocation>M:\\{DealFolder}\\Data\\{YYYY}\\{M}\\EmailExtract\\</SaveLocation>
  <Filters>
    <From>@selenefinance</From>                  <!-- sender email filter (partial match) -->
    <Attachments>True</Attachments>              <!-- require attachments: True/False -->
  </Filters>
  <Parsers>
    <DetachFileSubject>.*</DetachFileSubject>     <!-- regex matched against email SUBJECT LINE -->
    <!-- OR: <DetachFile>.*</DetachFile>  -- regex matched against attachment FILENAME -->
    <!-- OR both present -- MatchMode = "Both" -->
  </Parsers>
  <ServicerID>6007</ServicerID>
  <QueueOneFile>True</QueueOneFile>
  <DayAdjust>0</DayAdjust>
  <Templates>
    <Main>Outlook_Queuer_x</Main>                <!-- scrubber/template name -->
  </Templates>
</JOB_NAME>
\`\`\`

**Email field name → XML element (for edit_job field= and create_job overrides= keys):**
| Field name | XML element | Notes |
|---|---|---|
| \`mailbox\` | \`<Mailbox>\` | Direct child |
| \`folder\` | \`<Folder>\` | Direct child |
| \`sme\` | \`<SME>\` | Direct child |
| \`save_location\` | \`<SaveLocation>\` | Direct child |
| \`servicer_id\` | \`<ServicerID>\` | Direct child |
| \`last_email\` | \`<LastEmail>\` | Direct child (auto-updated by system) |
| \`queue_one_file\` | \`<QueueOneFile>\` | Direct child; values: "True"/"False" |
| \`day_adjust\` | \`<DayAdjust>\` | Direct child; integer as string |
| \`sender_filter\` | \`<Filters><From>\` | **Nested** under \\<Filters\\> |
| \`scrubber\` / \`template\` | \`<Templates><Main>\` | **Nested** under \\<Templates\\> |

**Computed fields (NEVER stored as XML — do not write these elements):**
- \`match_mode\` — derived from Parsers: DetachFileSubject→"Subject", DetachFile→"Filename", both→"Both". \\<MatchMode\\> does not exist in XML.
- \`sender\` — display alias for \\<Filters\\>\\<From\\>; use \`sender_filter\` as edit field name
- \`scrubber\` — display alias for \\<Templates\\>\\<Main\\>; same as \`template\`

**Display model → XML translation (job_detail API keys vs real XML elements):**
- API \`"sender"\` = XML \`<Filters><From>\` = edit field \`sender_filter\`
- API \`"save_path"\` = XML \`<SaveLocation>\` = edit field \`save_location\`
- API \`"scrubber"\` = XML \`<Templates><Main>\` = edit field \`scrubber\` or \`template\`
- API \`"mailbox"\` = XML \`<Mailbox>\` = edit field \`mailbox\`
- API \`"filters"\` dict = full contents of \`<Filters>\` block
- API \`"parsers"\` dict = full contents of \`<Parsers>\` block
- API \`"templates"\` dict = full contents of \`<Templates>\` block

#### SFTP Job — XML Structure
\`\`\`xml
<JOB_NAME>
  <Path>M:\\!Sweeps\\SPS\\In\\</Path>               <!-- SFTP source folder path -->
  <ServicerID>3702</ServicerID>
  <DSN>xf00.sps2.iman</DSN>                         <!-- data source name -->
  <SME>analyst@company.com</SME>
  <SaveLocation>M:\\{DealFolder}\\Data\\{YYYY}\\{M}\\EmailExtract\\</SaveLocation>
  <SkipList>N:\\...\\SkipListOCW.txt</SkipList>     <!-- exact filenames to skip -->
  <IgnoreList>N:\\...\\IgnoreListOCW.txt</IgnoreList>
  <Parsers>
    <MoveFile2>.*</MoveFile2>                        <!-- filename filter regex -->
    <!-- OR: <MoveFile>.*</MoveFile> -->
  </Parsers>
  <ZipContentFilter>.*</ZipContentFilter>
  <DayAdjust>0</DayAdjust>
  <!-- <Templates><Main>scrubber</Main></Templates>  optional -->
</JOB_NAME>
\`\`\`

**SFTP field name → XML element (for edit_job field= and create_job overrides= keys):**
| Field name | XML element | Notes |
|---|---|---|
| \`path\` | \`<Path>\` | Direct child — SFTP source folder |
| \`servicer_id\` | \`<ServicerID>\` | Direct child |
| \`dsn\` | \`<DSN>\` | Direct child |
| \`sme\` | \`<SME>\` | Direct child |
| \`save_location\` | \`<SaveLocation>\` | Direct child |
| \`skip_list\` | \`<SkipList>\` | Direct child |
| \`ignore_list\` | \`<IgnoreList>\` | Direct child |
| \`zip_content_filter\` | \`<ZipContentFilter>\` | Direct child |
| \`day_adjust\` | \`<DayAdjust>\` | Direct child |
| \`scrubber\` / \`template\` | \`<Templates><Main>\` | **Nested** — optional |

**Display model → XML translation (job_detail API keys vs real XML elements):**
- API \`"sftp_path"\` = XML \`<Path>\` = edit field \`path\`
- API \`"save_path"\` = XML \`<SaveLocation>\` = edit field \`save_location\`
- API \`"zip_filter"\` = XML \`<ZipContentFilter>\` = edit field \`zip_content_filter\`
- API \`"scrubber"\` = XML \`<Templates><Main>\` = edit field \`scrubber\` or \`template\``;

// ---------------------------------------------------------------------------
// Routing Guidance — brief instruction for tool selection (replaces the old
// 150-line buildClassifierPrompt). The LLM sees all 36 tools and picks.
// ---------------------------------------------------------------------------

const ROUTING_GUIDANCE = `## Tool Usage Guidance

You have access to tools for querying and managing FRP data. Call the appropriate tool(s) to answer the user's question.

### Routing Strategy
- **Simple queries** (list, lookup, search, detail): Call ONE tool, then present the result.
- **Complex queries** (investigate, audit, what's wrong, end-to-end, compare): Call MULTIPLE tools step-by-step — call one, review the result, then decide the next.
- **Cross-layer queries** (mention multiple data sources): Use cross-reference chains:
  - Job → Deals: job_detail returns linked deals in one call
  - Deal → Jobs: deal_lookup returns matching jobs
  - Servicer → Everything: servicer_dossier returns jobs + deals + coverage

### Parameter Extraction
- Extract ONLY identifiers: "CompanyID 296" → "296", "job CMBS_GreyCo" → "CMBS_GreyCo"
- Resolve anaphoric references ("this job", "it", "that deal") from conversation history
- For date-based queries, extract dates in YYYY-MM-DD format when provided
- "all" / "*" / "list everything" → pass query "*"

### Job Clone / Create Shortcut
When user asks to clone, copy, or create a job from an existing one:
1. **search_jobs** with the servicer ID or job name to find the template job
2. **next_servicer_id** with \`{ baseId: <templateServicerID> }\` to get the guaranteed-next unused ServicerID (queries both email and SFTP SQLite tables — never guesses)
3. **create_job** with the template name, new name, and any field overrides (servicer_id = the value from step 2, mailbox, sender_filter, etc.)
That's it — THREE steps maximum. The create_job confirmation flow will show the user the details and ask for confirmation.

**"Next highest number" / "next in the series":** Always call **next_servicer_id** — do NOT infer the next ID from search_jobs results. The search results only show jobs for the queried series; a completely different job could be using the "obvious" next number. The tool checks both email and SFTP jobs and walks the gap to find the true first-unused integer.

**Strict rules for clone/create:**
- Do NOT call servicer_dossier — it is not needed for cloning.
- Do NOT call job_detail — search_jobs gives you enough to clone.
- Do NOT produce a text preview of the XML — the confirmation flow handles that.
- Do NOT ask the user clarifying questions — use the data from search_jobs / next_servicer_id to fill in any gaps.
- Do NOT show internal reasoning or planning text. Act, don't narrate.

### Important Rules
- Call ONE tool at a time. Review the result before deciding the next step.
- When you have enough information, produce your FINAL ANSWER as text — do not call another tool.
- Do NOT call the same tool with identical parameters twice.
- If a tool returns no data or errors, note it and try an alternative approach.`;

// ---------------------------------------------------------------------------
// Email Triage Pipeline — Playbook (system prompt for ReAct loop)
// ---------------------------------------------------------------------------

const EMAIL_TRIAGE_PLAYBOOK = `You are the FRP Email Triage Analyst. Your job is to analyze an incoming email and trace it through the full FRP processing pipeline: job configuration → deal mapping → log verification → template staging.

## Domain Model

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for full column semantics, trigger identification, and cross-reference chains. Key reminders for triage:
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- ImportDID keywords are matched against email subject lines to identify deals
- **Not all jobs have DIDs** — process/shelf-level jobs (e.g. ABS_Deals_Queuer_x) have empty DIDs and that is normal
- **DataSource** in tblTemplateStaging is the definitive way to confirm an email was processed: it contains \`<mailbox>: <subject>\`
- **Job** column shows the parser used: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script), etc.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema for field names, nested elements, and create_job parameter guidance.

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
- If NOT FOUND: Report "No matching job found for sender domain." Then provide a creation suggestion using the following structure (refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema for field names):
  1. Suggest a similar existing job as a template (e.g., another job on the same mailbox): search_jobs with the mailbox address.
  2. Outline the create_job call with these overrides derived from the email metadata:
     - \`sender_filter\`: the sender email or domain from Step 1
     - \`mailbox\`: the destination mailbox this email arrived at
     - \`servicer_id\`: CompanyID from tblExternalDIDRef if the deal already exists; otherwise note it as "TBD — must be set after deal is registered"
     - \`scrubber\`: template name from a similar job (copy from the suggested template job)
  3. Remind the user that the backend will deep-copy the template job's full XML structure and apply only the specified overrides.
  STOP after presenting this suggestion — do not continue to Step 3.
- If MULTIPLE matches: List all matches. Pick the best match (highest relevance). Continue with that match.

### Step 3: DID Lookup
Find all deals mapped to this job's ServicerID.
- Call **deal_lookup** with the ServicerID from Step 2 (as CompanyID).
- If DIDs FOUND: List the count and ImportDID keywords. Continue to Step 4.
- If NO DIDs: This is **normal for process-level and shelf-level jobs** (e.g. ABS_Deals_Queuer_x, SFTP_Queuer_x). These jobs detach attachments, save files, and queue scrubbers without needing DID mappings. Report: "Job found — this is a process-level job with no DID mappings (this is expected)." **Skip Step 4** (keyword matching is not applicable) and **continue directly to Steps 5 and 6** to verify processing via logs and tblTemplateStaging.

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

### Step 6: Template Staging Verification
Check tblTemplateStaging for actual processing evidence. This is where you definitively answer: "Was this email processed? When? Did it succeed?"

**Search strategy:**
- Call **staging_search** with the job's TemplateName/scrubber (e.g. \`ABS_Deals_Queuer_x\`) or **template_status** for recent run summary.
- For deal-level jobs: also search by DID from Step 4.
- For process-level jobs (no DIDs): search by TemplateName only.

**Cross-reference the results using these columns (refer to DOMAIN_KNOWLEDGE for full details):**
- **TemplateName** — must match the job's scrubber from Step 2
- **DataSource** — for email triage, must contain the sender mailbox AND email subject (e.g. \`USBankGSFABSMailboxShared@usbank.com: [EXTERNAL] SRL I Monthly Report...\`). This is the **definitive proof** the specific email was processed.
- **Job** — corroborates trigger type: \`DetachFile\`/\`DetachFileSubject\` = email parser, \`MoveFile\`/\`MoveFile2\` = SFTP, \`DownloadAutomationv2.ps1\` = script-based
- **FilePath** — should match the expected attachment filename from the email
- **Dt** — should match the expected processing date
- **ResultCode + Comments** — 0/"Ok" = success, 1/error message = failure

**Interpret processing state per the DOMAIN_KNOWLEDGE state machine** (Never queued → Queued → In progress → Success/Failed).

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

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for the complete three-table pipeline, tblTemplateStaging column semantics (SourceProcess, Job, DataSource trigger identification, processing state machine), and cross-reference chains.

Key reminders:
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- **DataSource** in tblTemplateStaging is the definitive trigger type indicator: email (\`<mailbox>: <subject>\`), SFTP (\`SFTPMonitor: <path>\`), or manual (\`Queued via macro by <user>\`)
- **Job** column shows the parser/script from settings.xml (DetachFile, MoveFile, DownloadAutomationv2.ps1, etc.)
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal
- Application logs (EmailMonitor/SFTP logs) are indexed in SQLite and provide: daily summaries, DID failure events, job health metrics, deal-level activity, volume trends, and performance rankings.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema.

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

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for full column semantics, trigger identification, and cross-reference chains. Key reminders:
- **tblTemplateStaging**: TemplateName = job's Scrubber. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name. See DOMAIN_KNOWLEDGE for the processing state machine.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics, DID match failures, daily activity events.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema.

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

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for full column semantics, trigger identification, and cross-reference chains. Key reminders:
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- **tblTemplateStaging**: query by ServicerID or TemplateName. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics and DID failure events.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema.

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
// CRUD Planning Playbook
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

## Field Reference (for create_job overrides= and edit_job field=)

Refer to DOMAIN_KNOWLEDGE \u00a7 "Settings.xml Job Schema" for the full XML structure and field list.

Critical rules for planning:
- Use FIELD NAMES (not XML element names, not API display-model names):
  Write \`sender_filter\` — not "SenderFilter", not "sender", not "Filters/From"
  Write \`mailbox\` — not "MailboxAddress"
  Write \`save_location\` — not "save_path", not "SaveLocation"
  Write \`path\` (SFTP) — not "RemotePath", not "sftp_path"
  Write \`zip_content_filter\` (SFTP) — not "zip_filter", not "ZipContentFilter"
- NEVER plan a step that sets \`match_mode\` — it is computed from Parsers, not a stored field.
- Nested fields (sender_filter, scrubber/template) are written correctly by the backend automatically.
- Email-only fields: mailbox, folder, sender_filter, queue_one_file, last_email, import_did.
- SFTP-only fields: path, dsn, skip_list, ignore_list, zip_content_filter.
- Both types: servicer_id, sme, save_location, day_adjust, scrubber/template.
`.trim();

// ---------------------------------------------------------------------------
// Analysis Playbook
// ---------------------------------------------------------------------------

const ANALYSIS_PLAYBOOK = `
You are the FRP System Analysis agent. Your role is to investigate health, coverage, performance,
and configuration quality across the email and SFTP processing pipelines.

## Domain Model
Refer to DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema for XML field names and structure when the user asks about job configuration, create/edit operations, or field names.

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

// ---------------------------------------------------------------------------
// Pipeline Definitions — registry of all ReAct-capable pipelines
// ---------------------------------------------------------------------------

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
    tools: ['search_jobs', 'job_detail', 'create_job', 'next_servicer_id', 'edit_job', 'validate_email', 'validate_sftp'],
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
          description: 'Optional field overrides to apply to the new job after cloning. ' +
            'Keys MUST be valid field names (see DOMAIN_KNOWLEDGE \u00a7 Settings.xml Job Schema for full list). ' +
            'EMAIL fields: mailbox, folder, sme, save_location, servicer_id, sender_filter, ' +
            'scrubber (or template), queue_one_file, day_adjust, last_email. ' +
            'SFTP fields: path, dsn, sme, save_location, servicer_id, skip_list, ignore_list, ' +
            'zip_content_filter, day_adjust, scrubber (or template). ' +
            'NEVER use display-model names as keys: do NOT use match_mode, sender, save_path, sftp_path, zip_filter. ' +
            'Example: {"servicer_id": "6009", "sender_filter": "earl.cruz@usbank.com"}',
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
    name: 'next_servicer_id',
    description: 'Find the next unused ServicerID starting after a given base value. ' +
      'Checks BOTH email and SFTP jobs in the SQLite cache so no existing ID is ever reused. ' +
      'Always call this before create_job when a "next in series" ServicerID is needed — ' +
      'never infer the next ID manually from search results.',
    inputSchema: {
      type: 'object',
      properties: {
        baseId: {
          type: 'integer',
          description: 'ServicerID of the template / series anchor (e.g. 6007). ' +
            'The tool returns the first integer > baseId not already in use.',
        },
      },
      required: ['baseId'],
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
        filters: {
          type: 'string',
          description: 'Optional JSON string representing semantic filters, for example [{"field":"source","value":"manual"},{"field":"result","value":"failed"}]',
        },
        days: { type: 'number', description: 'Optional look-back window in days.' },
        startDate: { type: 'string', description: 'Optional start date in YYYY-MM-DD format.' },
        endDate: { type: 'string', description: 'Optional end date in YYYY-MM-DD format.' },
        limit: { type: 'number', description: 'Optional row limit.' },
      },
    },
  },
  {
    name: 'staging_linkage',
    description: 'Cross-link tblTemplateStaging records to matching Settings.xml or SQLite jobs and related tblExternalDIDRef deals. Use when user asks which job produced a staging row, how a template links to jobs, or how filepath/template/did connect across the pipeline.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Template name, DID, filepath token, or servicer-related query to correlate.' },
        days: { type: 'number', description: 'Optional look-back window in days (default 30).' },
        limit: { type: 'number', description: 'Optional staging row limit (default 25).' },
      },
      required: ['query'],
    },
  },
  {
    name: 'staging_audit',
    description: 'Audit tblTemplateStaging against Settings.xml/SQLite jobs and tblExternalDIDRef. Highlights templates with no configured job, jobs with no recent staging activity, filepath/source mismatches, process-level runs, and unmapped servicers.',
    inputSchema: {
      type: 'object',
      properties: {
        days: { type: 'number', description: 'Optional look-back window in days (default 30).' },
        limit: { type: 'number', description: 'Optional sample size per audit section (default 100).' },
      },
    },
  },
];

// ---------------------------------------------------------------------------
// Tool Registry — single map replacing buildToolArgs + executeToolCall + 28
// handler functions. Each entry maps a tool name to its backend command and
// parameter builder.
// ---------------------------------------------------------------------------

const TOOL_REGISTRY = {
  search_jobs: {
    command: 'search_jobs',
    buildParams: (input) => ({ query: input.query || '' }),
  },
  job_detail: {
    command: 'job_detail',
    buildParams: (input) => ({ jobName: input.jobName || '' }),
  },
  deal_lookup: {
    command: 'deal_lookup',
    buildParams: (input) => ({ query: input.query || '' }),
  },
  staging_search: {
    command: 'staging_search',
    buildParams: (input) => {
      const params = { query: input.query || '' };
      if (input.filters) params.filters = input.filters;
      if (input.days) params.days = String(input.days);
      if (input.startDate) params.startDate = input.startDate;
      if (input.endDate) params.endDate = input.endDate;
      if (input.limit) params.limit = String(input.limit);
      return params;
    },
  },
  staging_linkage: {
    command: 'staging_linkage',
    buildParams: (input) => {
      const params = { query: input.query || '' };
      if (input.days) params.days = String(input.days);
      if (input.limit) params.limit = String(input.limit);
      return params;
    },
  },
  staging_audit: {
    command: 'staging_audit',
    buildParams: (input) => {
      const params = {};
      if (input.days) params.days = String(input.days);
      if (input.limit) params.limit = String(input.limit);
      return params;
    },
  },
  template_status: {
    command: 'template_status',
    buildParams: (input) => {
      const args = { query: input.query || '' };
      if (input.days) args.days = String(input.days);
      return args;
    },
  },
  daily_summary: {
    command: 'log_daily_summary',
    buildParams: (input) => {
      const params = {};
      if (input.date) params.date = input.date;
      return params;
    },
  },
  job_health: {
    command: 'log_job_health',
    buildParams: (input) => ({ jobName: input.jobName || '' }),
  },
  did_failures: {
    command: 'log_did_failures',
    buildParams: () => ({}),
  },
  deal_activity: {
    command: 'log_deal_activity',
    buildParams: (input) => ({ did: input.did || '' }),
  },
  create_job: {
    command: 'create_job',
    destructive: true,
    buildParams: (input) => {
      const p = {
        name: input.newName || '',
        templateJob: input.templateJob || '',
        xmlType: input.xmlType || 'email',
      };
      // Flatten overrides into individual CLI flags
      if (input.overrides && typeof input.overrides === 'object') {
        for (const [k, v] of Object.entries(input.overrides)) {
          if (v !== undefined && v !== null && v !== '') {
            const camelKey = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
            p[camelKey] = String(v);
          }
        }
      }
      return p;
    },
  },
  edit_job: {
    command: 'edit_job',
    destructive: true,
    buildParams: (input) => ({
      jobName: input.jobName || '',
      field: input.field || '',
      value: input.value || '',
      xmlType: input.xmlType || 'email',
    }),
  },
  validate_email: {
    command: 'validate_email',
    buildParams: (input) => ({ jobName: input.jobName || '' }),
  },
  validate_sftp: {
    command: 'validate_sftp',
    buildParams: (input) => ({ jobName: input.jobName || '' }),
  },
  templates: {
    command: 'template_inventory',
    buildParams: (input) => ({ filter: input.filter || '' }),
  },
  next_servicer_id: {
    command: 'next_servicer_id',
    buildParams: (input) => ({ baseId: String(input.baseId) }),
  },
  servicer_dossier: {
    command: 'servicer_dossier',
    buildParams: (input) => ({ query: input.query || '' }),
  },
  coverage_gaps: {
    command: 'coverage_gaps',
    buildParams: (input) => ({ focus: input.focus || 'all' }),
  },
  orphan_detection: {
    command: 'orphan_detection',
    buildParams: () => ({}),
  },
  collision_detection: {
    command: 'collision_detection',
    buildParams: () => ({}),
  },
  sync_logs: {
    command: 'sync_logs',
    buildParams: () => ({}),
  },
  log_trends: {
    command: 'log_trends',
    buildParams: (input) => {
      const params = {};
      if (input.days) params.days = String(input.days);
      if (input.job) params.job = input.job;
      return params;
    },
  },
  log_performance: {
    command: 'log_performance',
    buildParams: (input) => {
      const params = {};
      if (input.sort) params.sort = input.sort;
      if (input.top) params.top = String(input.top);
      if (input.days) params.days = String(input.days);
      return params;
    },
  },
  save_settings: {
    getCommand: (input) => input.type === 'sftp' ? 'save_sftp_settings' : 'save_email_settings',
    buildParams: () => ({}),
  },
  list_backups: {
    command: 'list_backups',
    buildParams: () => ({}),
  },
  xml_diff: {
    command: 'xml_diff',
    buildParams: (input) => {
      const params = {};
      if (input.backupFile) params.backupFile = input.backupFile;
      return params;
    },
  },
  rollback: {
    command: 'rollback_xml',
    destructive: true,
    buildParams: (input) => ({ backupFile: input.backupFile || '' }),
  },
  triage_email: {
    special: true,
    buildParams: (input) => input,
  },
  consolidation_analysis: {
    command: 'analyze_consolidation',
    buildParams: (input) => ({ type: input.type || 'all' }),
  },
  impact_analysis: {
    command: 'analyze_impact',
    buildParams: (input) => ({
      change_type: input.changeType || '',
      target_job: input.targetJob || '',
      new_value: input.newValue || '',
      current_value: input.currentValue || '',
      affected_servicers: input.affectedServicers || [],
      dry_run: input.dryRun !== false,
    }),
  },
  system_health: {
    command: 'analyze_health',
    buildParams: (input) => ({ type: input.type || 'all' }),
  },
  agent_status: {
    command: 'search_jobs',
    buildParams: () => ({ query: '' }),
  },
  processing_history: {
    command: 'processing_history',
    buildParams: (input) => {
      const params = { query: input.query || '' };
      if (input.startDate) params.startDate = input.startDate;
      if (input.endDate) params.endDate = input.endDate;
      return params;
    },
  },
  failure_analysis: {
    command: 'failure_analysis',
    buildParams: (input) => {
      const params = {};
      if (input.template) params.template = input.template;
      if (input.did) params.did = input.did;
      if (input.days) params.days = String(input.days);
      return params;
    },
  },
  source_trace: {
    command: 'source_trace',
    buildParams: (input) => ({ filepath: input.filepath || '' }),
  },
  manual_queue: {
    command: 'manual_queue_report',
    buildParams: (input) => {
      const params = {};
      if (input.days) params.days = String(input.days);
      if (input.template) params.template = input.template;
      if (input.servicerId) params.servicerId = input.servicerId;
      return params;
    },
  },
  processing_duration: {
    command: 'processing_duration',
    buildParams: (input) => {
      const params = {};
      if (input.template) params.template = input.template;
      if (input.days) params.days = String(input.days);
      if (input.sort) params.sort = input.sort;
      return params;
    },
  },
  deal_pipeline: {
    command: 'deal_pipeline',
    buildParams: (input) => {
      const params = { query: input.query || '' };
      if (input.days) params.days = String(input.days);
      return params;
    },
  },
};

// ---------------------------------------------------------------------------
// Core Utilities
// ---------------------------------------------------------------------------

/**
 * Extract a JSON object from an LLM response that may contain surrounding
 * prose, markdown fences, or chain-of-thought text.
 *
 * Tries, in order:
 *   1. Direct JSON.parse of the full trimmed text
 *   2. Content inside markdown code fences (```json ... ```)
 *   3. First { ... } substring (greedy, handles nested braces)
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

/**
 * Extract a tool call from a stream part. Handles both official API and
 * duck-typing fallback.
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
 * Build a tool-result message for the LLM conversation history.
 */
function makeToolResultMessage(callId, content) {
  return vscode.LanguageModelChatMessage.User([
    new vscode.LanguageModelToolResultPart(callId, [
      new vscode.LanguageModelTextPart(content)
    ])
  ]);
}

// ---------------------------------------------------------------------------
// Model selection
// ---------------------------------------------------------------------------

const MODEL_PREFERENCE = ['gpt-4.1', 'gpt-4o', 'claude-sonnet-4', 'gpt-4o-mini'];

/**
 * Select the best available LLM model.
 */
async function selectModel(request) {
  if (request.model) return request.model;

  const config = vscode.workspace.getConfiguration('frpAgent');
  const modelSetting = config.get('model', 'auto');

  if (modelSetting !== 'auto') {
    try {
      const [model] = await vscode.lm.selectChatModels({ family: modelSetting });
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

// ---------------------------------------------------------------------------
// LLM generation helpers
// ---------------------------------------------------------------------------

/**
 * Stream an LLM answer into the chat response.
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

// ---------------------------------------------------------------------------
// CRUD helpers
// ---------------------------------------------------------------------------

/**
 * Extract the current value of a field from a job_detail result.
 */
function resolveCurrentFieldValue(jobDetailResult, fieldName, xmlType) {
  const job = jobDetailResult?.data?.job || {};
  const fieldMap = {
    // Email fields
    scrubber:            () => job.scrubber || '',
    template:            () => job.scrubber || '',
    servicer_id:         () => String(job.servicer_id ?? ''),
    mailbox:             () => job.mailbox || '',
    folder:              () => job.folder || '',
    sme:                 () => job.sme || '',
    save_location:       () => job['save_path'] || '',              // API returns 'save_path'
    import_did:          () => job['import_did'] || '',             // not returned by API; shows (not set)
    subject_filter:      () => job['subject_filter'] || '',         // not returned by API; shows (not set)
    sender_filter:       () => job.sender || job.filters?.From || '', // API returns 'sender'
    day_adjust:          () => String(job.day_adjust ?? ''),
    name:                () => job['job_name'] || '',               // API returns 'job_name'
    last_email:          () => job.last_email || '',
    queue_one_file:      () => String(job.queue_one_file ?? ''),
    // SFTP-only fields
    path:                () => job['sftp_path'] || '',              // API returns 'sftp_path'
    dsn:                 () => job.dsn || '',
    skip_list:           () => job.skip_list || '',
    ignore_list:         () => job.ignore_list || '',
    zip_content_filter:  () => job['zip_filter'] || '',             // API returns 'zip_filter'
  };
  return (fieldMap[fieldName] || (() => ''))();
}

/**
 * Render a before/after diff in the chat stream for a single field edit.
 */
function renderEditDiff(jobName, field, currentValue, newValue, xmlType) {
  const isNested = (field === 'scrubber' || field === 'template' || field === 'sender_filter');
  let beforeXml, afterXml;

  if (isNested) {
    if (field === 'scrubber' || field === 'template') {
      beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
      afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
    } else if (field === 'sender_filter') {
      beforeXml = `<Filters><From>${currentValue || '(not set)'}</From></Filters>`;
      afterXml  = `<Filters><From>${newValue}</From></Filters>`;
    }
  } else {
    const tagMap = {
      servicer_id:        'ServicerID',
      mailbox:            'Mailbox',          // FIXED: was 'MailboxAddress'
      folder:             'Folder',
      sme:                'SME',
      save_location:      'SaveLocation',
      import_did:         'ImportDID',
      subject_filter:     'SubjectFilter',
      day_adjust:         'DayAdjust',
      name:               'Name',
      last_email:         'LastEmail',
      queue_one_file:     'QueueOneFile',
      path:               'Path',             // FIXED: was 'RemotePath'
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
 * Extract a .msg file path from user text.
 */
function extractMsgPath(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return null;
  const quoted = trimmed.match(/^["'](.+?\.msg)["']/i);
  if (quoted) return quoted[1];
  if (/\.msg$/i.test(trimmed)) return trimmed;
  const first = trimmed.split(/\s+/)[0];
  if (/\.msg$/i.test(first)) return first;
  return trimmed;
}

function stripDeterministicTriageQuotes(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1).trim();
  }
  return text;
}

function looksLikeMsgPath(value) {
  const text = stripDeterministicTriageQuotes(value);
  return /\.msg$/i.test(text);
}

function normalizeDeterministicTriageField(fieldName) {
  return DETERMINISTIC_TRIAGE_FIELD_ALIASES[String(fieldName || '').toLowerCase()] || null;
}

function parseDeterministicTriageFieldClause(clause) {
  const separatorMatch = clause.match(/^([a-z_]+)\s*[:=\-]\s*(.+)$/i);
  const tokenMatch = separatorMatch || clause.match(/^([a-z_]+)\s+(.+)$/i);
  if (!tokenMatch) {
    return { kind: 'text', query: stripDeterministicTriageQuotes(clause), rawQuery: clause };
  }

  const normalized = normalizeDeterministicTriageField(tokenMatch[1]);
  if (!normalized) {
    return { kind: 'text', query: stripDeterministicTriageQuotes(clause), rawQuery: clause };
  }

  const value = stripDeterministicTriageQuotes(tokenMatch[2]);
  if (!value) {
    return { error: `Filter \`${tokenMatch[1]}\` requires a value.` };
  }

  if (normalized.kind === 'control') {
    return {
      kind: 'control',
      control: normalized.field,
      fieldLabel: normalized.label,
      query: value,
      rawQuery: clause,
    };
  }

  return {
    kind: 'filter',
    fieldName: normalized.field,
    fieldLabel: normalized.label,
    query: value,
    rawQuery: clause,
  };
}

function parseDeterministicTriageClauses(remainder, options = {}) {
  const clauses = splitDeterministicClauses(remainder);
  if (!clauses.length) {
    return { error: 'Use a .msg path or deterministic triage fields such as `sender:`, `mailbox:`, `subject:`, or `filename:`.' };
  }

  let textQuery = null;
  const filters = [];
  const seenFields = new Set();
  let days = null;
  let startDate = null;
  let endDate = null;

  for (const clause of clauses) {
    const parsedClause = parseDeterministicTriageFieldClause(clause);
    if (parsedClause.error) return parsedClause;

    if (parsedClause.kind === 'text') {
      if (!options.allowTextQuery) {
        return { error: 'This deterministic triage action requires fielded metadata such as `sender:` or `subject:`.' };
      }
      if (textQuery) {
        return { error: 'Use at most one unfielded search term in deterministic /triage metadata mode.' };
      }
      textQuery = parsedClause.query;
      continue;
    }

    if (parsedClause.kind === 'control') {
      if (parsedClause.control === 'days') {
        const num = Number(parsedClause.query);
        if (!Number.isFinite(num) || num <= 0) {
          return { error: '`days` must be a positive number.' };
        }
        days = String(Math.trunc(num));
      } else if (parsedClause.control === 'start') {
        startDate = parsedClause.query;
      } else if (parsedClause.control === 'end') {
        endDate = parsedClause.query;
      }
      continue;
    }

    if (seenFields.has(parsedClause.fieldName)) {
      return { error: `Filter \`${parsedClause.fieldLabel}\` can only be supplied once per deterministic triage request.` };
    }

    seenFields.add(parsedClause.fieldName);
    filters.push(parsedClause);
  }

  const valueFor = (fieldName) => {
    const match = filters.find((filter) => filter.fieldName === fieldName);
    return match ? match.query : '';
  };

  return {
    textQuery,
    filters,
    sender: valueFor('sender'),
    mailbox: valueFor('mailbox'),
    subject: valueFor('subject') || textQuery || '',
    filename: valueFor('filename'),
    body: valueFor('body'),
    days,
    startDate,
    endDate,
  };
}

function parseDeterministicTriagePrompt(prompt) {
  const trimmed = String(prompt || '').trim();
  if (!trimmed) return { help: true };
  if (isSlashHelpPrompt(trimmed)) return { help: true };

  const match = trimmed.match(/^(trace|verify|match|new)(?:\s+(.+))?$/i);
  if (!match) {
    if (looksLikeMsgPath(trimmed)) {
      return {
        action: 'trace',
        msgPath: stripDeterministicTriageQuotes(extractMsgPath(trimmed)),
        rawQuery: trimmed,
        inferredAction: true,
      };
    }
    return null;
  }

  const action = String(match[1] || '').toLowerCase();
  const remainder = String(match[2] || '').trim();
  if (!remainder) {
    return { error: 'Use `trace <path.msg>`, `trace sender:...; subject:...`, `verify <path.msg>`, `match sender:...; subject:...`, or `new <path.msg>`.' };
  }

  if (action === 'verify' || action === 'new' || (action === 'trace' && looksLikeMsgPath(remainder))) {
    const msgPath = stripDeterministicTriageQuotes(extractMsgPath(remainder));
    if (!looksLikeMsgPath(msgPath)) {
      return { error: `\`${action}\` requires a .msg file path.` };
    }
    return { action, msgPath, rawQuery: trimmed };
  }

  const parsed = parseDeterministicTriageClauses(remainder, { allowTextQuery: true });
  if (parsed.error) return parsed;
  if (!parsed.sender && !parsed.subject) {
    return { error: 'Deterministic metadata triage requires at least `sender:` or `subject:`.' };
  }

  return { action, rawQuery: trimmed, ...parsed };
}

function buildDeterministicTriageHelpText() {
  const examples = [
    { prompt: '/triage "M:\\Mail\\report.msg"', label: 'trace "M:\\Mail\\report.msg"' },
    { prompt: '/triage trace "M:\\Mail\\report.msg"', label: 'trace "M:\\Mail\\report.msg"' },
    { prompt: '/triage verify "M:\\Mail\\report.msg"', label: 'verify "M:\\Mail\\report.msg"' },
    { prompt: '/triage match sender:reports@fay.com; subject:Monthly Report', label: 'match sender:reports@fay.com; subject:Monthly Report' },
    { prompt: '/triage trace sender:reports@fay.com; mailbox:rptent@usbank.com; subject:Monthly Report; filename:deal_20260310.xlsx', label: 'trace sender:reports@fay.com; mailbox:rptent@usbank.com; subject:Monthly Report; filename:deal_20260310.xlsx' },
    { prompt: '/triage new "M:\\Mail\\unknown.msg"', label: 'new "M:\\Mail\\unknown.msg"' },
  ];

  return [
    '### /triage — Deterministic Email Triage',
    '',
    'Deterministic `/triage` uses direct backend triage commands plus deterministic `/jobXMLEmail`, `/deals`, `/logs`, and `/staging` style orchestration.',
    'If your prompt does not match these forms, `/triage` falls back to the existing agentic triage pipeline.',
    '',
    'Supported forms:',
    '- `trace <path.msg>`',
    '- `<path.msg>` (shorthand for `trace <path.msg>`) ',
    '- `trace sender:<...>; mailbox:<...>; subject:<...>; filename:<...>`',
    '- `verify <path.msg>`',
    '- `match sender:<...>; subject:<...>`',
    '- `new <path.msg>`',
    '- Time controls for `trace` and `match`: `days`, `start`, `end`',
    '',
    'Field meanings:',
    '- `Sender`: the inbound sender or sender domain.',
    '- `Mailbox`: the FRP mailbox on our side.',
    '- `Subject`: the inbound email subject.',
    '- `Filename`: an attachment filename clue.',
    '- `trace`: full deterministic triage report using triage seed data plus jobs, deals, logs, and staging.',
    '- `verify`: parse and verify a concrete `.msg` file against existing jobs.',
    '- `match`: match sender/subject metadata against existing jobs without a `.msg` file.',
    '- `new`: analyze an unmatched email for new-job creation suggestions.',
    '',
    'Examples:',
    ...examples.map((example) => `- ${buildInlinePromptLink(example.prompt, example.label)}`),
  ].join('\n');
}

function buildDeterministicTriageFollowUps() {
  return [
    { prompt: 'trace "M:\\Mail\\report.msg"', label: 'Trace a .msg file' },
    { prompt: 'match sender:reports@fay.com; subject:Monthly Report', label: 'Match sender/subject' },
    { prompt: 'new "M:\\Mail\\unknown.msg"', label: 'Analyze unmatched email' },
  ];
}

function dedupeDeterministicValues(values) {
  const seen = new Set();
  const output = [];
  for (const value of values) {
    const text = String(value || '').trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(text);
  }
  return output;
}

function dedupeDeterministicJobsByName(jobs) {
  const seen = new Set();
  const output = [];
  for (const job of Array.isArray(jobs) ? jobs : []) {
    const jobName = String(job?.job_name || job?.name || '').trim();
    if (!jobName) continue;
    const key = jobName.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(job);
  }
  return output;
}

function normalizeDeterministicSenderDomain(value) {
  const email = normalizeDeterministicEmailAddress(value);
  if (email.includes('@')) return email.split('@').pop().trim().toLowerCase();
  const text = String(value || '').trim().toLowerCase().replace(/^@+/, '');
  const match = text.match(/[a-z0-9.-]+\.[a-z]{2,}/i);
  return match ? match[0].toLowerCase() : text;
}

function extractDeterministicEmailAddresses(value) {
  const text = String(value || '').trim();
  if (!text) return [];
  const matches = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig);
  return dedupeDeterministicValues(matches || []);
}

function normalizeDeterministicEmailAddress(value) {
  const addresses = extractDeterministicEmailAddresses(value);
  if (addresses.length) return addresses[0];
  return String(value || '').trim();
}

function normalizeDeterministicMailboxValue(value) {
  return normalizeDeterministicEmailAddress(value);
}

function getDeterministicTriageMailboxCandidates(metadata) {
  if (Array.isArray(metadata?.mailboxes) && metadata.mailboxes.length) {
    return metadata.mailboxes
      .map((value) => String(normalizeDeterministicMailboxValue(value)).toLowerCase())
      .filter(Boolean);
  }
  const mailbox = String(normalizeDeterministicMailboxValue(metadata?.primaryMailbox || '')).toLowerCase();
  return mailbox ? [mailbox] : [];
}

function isDeterministicInlineFilename(filename) {
  const normalized = String(filename || '').trim().toLowerCase();
  if (!normalized) return false;
  return /^image\d+\.(png|jpe?g|gif|bmp|tiff?|webp)$/i.test(normalized)
    || /^attachment\d+\./i.test(normalized);
}

function selectDeterministicPrimaryFilename(filenames) {
  const values = (Array.isArray(filenames) ? filenames : []).filter(Boolean);
  return values.find((value) => !isDeterministicInlineFilename(value)) || values[0] || '';
}

function buildDeterministicTriageSubjectSearchValue(metadata) {
  const subject = String(metadata?.subject || '').trim();
  if (!subject) return '';
  return subject
    .replace(/^\s*(\[[^\]]+\]\s*)+/g, '')
    .replace(/^\s*(re|fw|fwd)\s*:\s*/ig, '')
    .trim();
}

function getDeterministicTriageEvidenceMailboxes(metadata, resolvedJob = null) {
  const resolvedMailbox = normalizeDeterministicMailboxValue(resolvedJob?.mailbox || '');
  if (resolvedMailbox) return [String(resolvedMailbox).toLowerCase()];
  return getDeterministicTriageMailboxCandidates(metadata);
}

function buildDeterministicTriageDataSourceValues(metadata, resolvedJob = null) {
  const subject = buildDeterministicTriageSubjectSearchValue(metadata) || String(metadata?.subject || '').trim();
  if (!subject) return [];
  return dedupeDeterministicValues(
    getDeterministicTriageEvidenceMailboxes(metadata, resolvedJob)
      .map((mailbox) => (mailbox ? `${mailbox}: ${subject}` : ''))
      .filter(Boolean),
  );
}

function normalizeDeterministicImportDidValue(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function selectDeterministicTriageDeals(seedDeals, linkedDeals = [], dealLookup = null, servicerDossier = null) {
  const candidates = [
    Array.isArray(linkedDeals) ? linkedDeals : [],
    Array.isArray(servicerDossier?.deals) ? servicerDossier.deals : [],
    Array.isArray(dealLookup?.deals) ? dealLookup.deals : [],
    Array.isArray(seedDeals) ? seedDeals : [],
  ];
  return candidates.reduce((best, current) => (current.length > best.length ? current : best), []);
}

function buildDeterministicTriageMetadata(parsed, payload) {
  const emailInfo = payload?.email_info || {};
  const sender = normalizeDeterministicEmailAddress(parsed?.sender || emailInfo.sender || '');
  const senderDomain = sender.includes('@') ? sender.split('@').pop().trim() : sender;
  const subject = String(parsed?.subject || emailInfo.subject || parsed?.textQuery || '').trim();
  const mailboxes = dedupeDeterministicValues([
    normalizeDeterministicMailboxValue(parsed?.mailbox),
    ...(Array.isArray(emailInfo.to) ? emailInfo.to.map((value) => normalizeDeterministicMailboxValue(value)) : []),
    ...(Array.isArray(emailInfo.cc) ? emailInfo.cc.map((value) => normalizeDeterministicMailboxValue(value)) : []),
  ].filter(Boolean));
  const filenames = dedupeDeterministicValues([
    parsed?.filename,
    ...(Array.isArray(emailInfo.attachment_names) ? emailInfo.attachment_names : []),
  ]);
  const primaryFilename = selectDeterministicPrimaryFilename(filenames);

  return {
    sender,
    senderDomain,
    subject,
    mailboxes,
    primaryMailbox: mailboxes[0] || '',
    filenames,
    primaryFilename,
    body: String(parsed?.body || emailInfo.body_preview || '').trim(),
    date: String(emailInfo.date || '').trim(),
    filePath: String(emailInfo.file_path || parsed?.msgPath || '').trim(),
  };
}

function buildDeterministicJobFilter(fieldFilter, fieldLabel, query) {
  return {
    fieldFilter,
    fieldLabel,
    query,
    rawQuery: `${String(fieldLabel || fieldFilter).toLowerCase()}:${query}`,
  };
}

async function safeDeterministicBackendCall(command, params, shared, opts = {}) {
  try {
    const result = await backendCall(command, params, shared, opts);
    if (isDeterministicFailure(result)) {
      return {
        ok: false,
        result,
        data: result?.data || {},
        error: result?.error || (result?.errors || []).join(', ') || 'Unknown error',
      };
    }
    return { ok: true, result, data: result?.data || {}, error: null };
  } catch (error) {
    return { ok: false, result: null, data: {}, error: error.message };
  }
}

async function searchDeterministicEmailJobs(query, filters, shared) {
  if (!query) return [];
  const searchResult = await safeDeterministicBackendCall('search_jobs', { query, xmlType: 'email' }, shared, { timeoutMs: 0 });
  if (!searchResult.ok) return [];
  const jobs = Array.isArray(searchResult.data.jobs) ? searchResult.data.jobs : [];
  return dedupeDeterministicJobsByName(applyDeterministicFieldFilter(jobs, { filters }));
}

async function searchDeterministicEmailJobsRaw(query, filters, shared) {
  if (!query) return [];
  const searchResult = await safeDeterministicBackendCall('search_jobs', { query, xmlType: 'email' }, shared, { timeoutMs: 0 });
  if (!searchResult.ok) return [];
  const jobs = Array.isArray(searchResult.data.jobs) ? searchResult.data.jobs : [];
  return applyDeterministicFieldFilter(jobs, { filters });
}

async function enrichDeterministicTriageMatches(matches, metadata, shared) {
  const entries = Array.isArray(matches) ? matches : [];
  if (!entries.length) return [];

  const jobNames = dedupeDeterministicValues(entries.map((match) => match?.job_name));
  const variantsByName = new Map();

  for (const jobName of jobNames) {
    const variants = await searchDeterministicEmailJobsRaw(
      jobName,
      [buildDeterministicJobFilter('job_name', 'Job Name', jobName)],
      shared,
    );
    const key = String(jobName || '').trim().toLowerCase();
    variantsByName.set(
      key,
      variants.filter((job) => String(job?.job_name || job?.name || '').trim().toLowerCase() === key),
    );
  }

  return entries.map((match) => {
    const key = String(match?.job_name || '').trim().toLowerCase();
    const variant = pickDeterministicResolvedJobVariant(variantsByName.get(key) || [], match, metadata);
    if (!variant) return match;
    return {
      ...variant,
      ...match,
      mailbox: String(variant?.mailbox || match?.mailbox || '').trim(),
      sender: String(variant?.sender || match?.sender || '').trim(),
      scrubber: String(variant?.scrubber || variant?.template || match?.scrubber || '').trim(),
      save_path: String(variant?.save_path || match?.save_path || '').trim(),
      xml_type: String(variant?.xml_type || match?.xml_type || '').trim(),
    };
  });
}

function intersectDeterministicTriageMatches(matches, jobs) {
  if (!Array.isArray(matches) || !matches.length || !Array.isArray(jobs) || !jobs.length) {
    return Array.isArray(matches) ? matches : [];
  }
  const names = new Set(jobs.map((job) => String(job?.job_name || job?.name || '').trim().toLowerCase()).filter(Boolean));
  return matches.filter((match) => names.has(String(match?.job_name || '').trim().toLowerCase()));
}

function scoreDeterministicTriageMatch(match, metadata) {
  const mailboxes = new Set(getDeterministicTriageMailboxCandidates(metadata));
  const matchedFilter = String(normalizeDeterministicEmailAddress(match?.matched_filter || '')).toLowerCase();
  const matchedField = String(normalizeDeterministicEmailAddress(match?.email_field_matched || '')).toLowerCase();
  const matchType = String(match?.match_type || '').toLowerCase();
  const confidence = String(match?.match_confidence || '').toLowerCase();
  const senderDomain = normalizeDeterministicSenderDomain(match?.sender || '');
  const emailSenderDomain = normalizeDeterministicSenderDomain(metadata?.sender || metadata?.senderDomain || '');

  let score = 0;
  if (mailboxes.size && (mailboxes.has(matchedFilter) || mailboxes.has(matchedField))) score += 1000;
  if (matchType === 'both') score += 400;
  else if (matchType === 'mailbox') score += 300;
  else if (matchType === 'sender') score += 200;
  else if (matchType === 'subject') score += 100;

  if (confidence === 'exact') score += 20;
  else if (confidence === 'partial') score += 10;

  if (senderDomain && emailSenderDomain) {
    if (senderDomain === emailSenderDomain) score += 80;
    else if (senderDomain.endsWith(`.${emailSenderDomain}`)) score += 35;
    else if (emailSenderDomain.endsWith(`.${senderDomain}`)) score += 20;
  }

  return score;
}

function rankDeterministicTriageMatches(matches, metadata) {
  return (Array.isArray(matches) ? matches : [])
    .slice()
    .sort((left, right) => scoreDeterministicTriageMatch(right, metadata) - scoreDeterministicTriageMatch(left, metadata));
}

function collectDeterministicExactMailboxMatches(matches, metadata) {
  const mailboxes = new Set(getDeterministicTriageMailboxCandidates(metadata));
  if (!mailboxes.size) return [];
  return (Array.isArray(matches) ? matches : []).filter((match) => {
    const matchedFilter = String(normalizeDeterministicEmailAddress(match?.matched_filter || '')).toLowerCase();
    const matchedField = String(normalizeDeterministicEmailAddress(match?.email_field_matched || '')).toLowerCase();
    return mailboxes.has(matchedFilter) || mailboxes.has(matchedField);
  });
}

async function narrowDeterministicTriageMatches(seedPayload, metadata, shared) {
  const matches = Array.isArray(seedPayload?.matches) ? seedPayload.matches : [];
  if (!matches.length) return [];

  const exactMailboxMatches = collectDeterministicExactMailboxMatches(matches, metadata);
  if (getDeterministicTriageMailboxCandidates(metadata).length && !exactMailboxMatches.length) {
    return [];
  }

  let narrowed = rankDeterministicTriageMatches(exactMailboxMatches.length ? exactMailboxMatches : matches, metadata);

  const mailboxCandidates = getDeterministicTriageMailboxCandidates(metadata);
  if (mailboxCandidates.length) {
    const mailboxJobs = dedupeDeterministicJobsByName((await Promise.all(mailboxCandidates.map((mailbox) => searchDeterministicEmailJobs(
      mailbox,
      [buildDeterministicJobFilter('mailbox', 'Mailbox', mailbox)],
      shared,
    )))).flat());
    const byMailbox = intersectDeterministicTriageMatches(narrowed, mailboxJobs);
    if (byMailbox.length) narrowed = rankDeterministicTriageMatches(byMailbox, metadata);
  }

  if (metadata.sender) {
    const senderJobs = await searchDeterministicEmailJobs(
      metadata.sender,
      [buildDeterministicJobFilter('sender', 'Sender', metadata.sender)],
      shared,
    );
    const bySender = intersectDeterministicTriageMatches(narrowed, senderJobs);
    if (bySender.length) narrowed = rankDeterministicTriageMatches(bySender, metadata);
  }

  if (metadata.senderDomain && metadata.senderDomain !== metadata.sender && narrowed.length > 1) {
    const senderDomainJobs = await searchDeterministicEmailJobs(
      metadata.senderDomain,
      [buildDeterministicJobFilter('sender', 'Sender', metadata.senderDomain)],
      shared,
    );
    const byDomain = intersectDeterministicTriageMatches(narrowed, senderDomainJobs);
    if (byDomain.length) narrowed = rankDeterministicTriageMatches(byDomain, metadata);
  }

  return rankDeterministicTriageMatches(await enrichDeterministicTriageMatches(narrowed, metadata, shared), metadata);
}

async function buildDeterministicCloneSuggestions(seedPayload, metadata, shared) {
  const suggestions = [];
  const seen = new Set();

  const pushJobs = (jobs, reason) => {
    for (const job of Array.isArray(jobs) ? jobs : []) {
      const jobName = String(job?.job_name || job?.name || '').trim();
      const servicerId = String(job?.servicer_id ?? '').trim();
      if (!jobName || !servicerId) continue;
      const key = `${jobName.toLowerCase()}|${servicerId}`;
      if (seen.has(key)) continue;
      seen.add(key);
      suggestions.push({
        job_name: jobName,
        servicer_id: servicerId,
        mailbox: String(job?.mailbox || '').trim(),
        scrubber: String(job?.scrubber || job?.template || '').trim(),
        reason,
      });
    }
  };

  const suggestion = seedPayload?.suggested_config || {};
  const servicerIds = Array.isArray(suggestion.potential_servicer_ids) ? suggestion.potential_servicer_ids : [];
  for (const servicerId of servicerIds.slice(0, 3)) {
    const jobs = await searchDeterministicEmailJobs(
      String(servicerId),
      [buildDeterministicJobFilter('servicer_id', 'ServicerID', String(servicerId))],
      shared,
    );
    pushJobs(jobs, 'Sender domain maps to this servicer ID.');
  }

  const templateName = String(seedPayload?.suggested_template || '').trim();
  if (templateName) {
    const jobs = await searchDeterministicEmailJobs(
      templateName,
      [buildDeterministicJobFilter('scrubber', 'Scrubber', templateName)],
      shared,
    );
    pushJobs(jobs, 'Uses the suggested scrubber/template.');
  }

  if (!suggestions.length && metadata?.senderDomain) {
    const jobs = await searchDeterministicEmailJobs(
      metadata.senderDomain,
      [buildDeterministicJobFilter('sender', 'Sender', metadata.senderDomain)],
      shared,
    );
    pushJobs(jobs.slice(0, 2), 'Closest sender-domain pattern; verify before cloning.');
  }

  return suggestions.slice(0, 5);
}

function buildDeterministicCloneFollowUps(cloneSuggestions) {
  const actions = [];
  const seen = new Set();
  for (const suggestion of Array.isArray(cloneSuggestions) ? cloneSuggestions : []) {
    const servicerId = String(suggestion?.servicer_id || '').trim();
    const jobName = String(suggestion?.job_name || '').trim();
    if (!servicerId) continue;
    pushUniqueDeterministicAction(actions, seen, `/clone servicerID:${servicerId}`, `Clone from ${jobName || servicerId}`);
    if (jobName) {
      pushUniqueDeterministicAction(actions, seen, `/jobXMLEmail detail ${jobName}`, `Inspect ${jobName}`);
    }
  }
  return actions.slice(0, 6);
}

function renderDeterministicCloneSuggestions(lines, cloneSuggestions) {
  lines.push('**Suggested Clone Sources**');
  if (!Array.isArray(cloneSuggestions) || !cloneSuggestions.length) {
    lines.push('- No deterministic clone source was identified. Start from the closest known job manually if needed.');
    lines.push('');
    return;
  }

  lines.push('| JobName | ServicerID | Mailbox | Scrubber | Why Suggested |');
  lines.push('|---------|------------|---------|----------|---------------|');
  for (const suggestion of cloneSuggestions) {
    lines.push(`| ${linkOrText(suggestion.job_name || '—', `/jobXMLEmail detail ${suggestion.job_name || ''}`)} | ${linkOrText(suggestion.servicer_id || '—', `/clone servicerID:${suggestion.servicer_id || ''}`)} | ${escapeMarkdownText(suggestion.mailbox || '—')} | ${escapeMarkdownText(suggestion.scrubber || '—')} | ${escapeMarkdownText(suggestion.reason || '—')} |`);
  }
  lines.push('');
  lines.push('- Start with `/clone servicerID:<id>` to open the guided clone draft and walk field-by-field through the new job.');
  lines.push('');
}

async function loadDeterministicTriageJobDetails(matches, shared, limit = 3) {
  const uniqueNames = dedupeDeterministicValues((Array.isArray(matches) ? matches : []).map((match) => match?.job_name));
  const details = [];
  const errors = [];

  for (const jobName of uniqueNames.slice(0, limit)) {
    const detailResult = await safeDeterministicBackendCall('job_detail', { jobName }, shared, { timeoutMs: 0 });
    if (!detailResult.ok) {
      errors.push(`job_detail(${jobName}): ${detailResult.error}`);
      continue;
    }
    details.push(detailResult.data);
  }

  return { details, errors };
}

async function loadDeterministicTriageJobVariants(matches, shared, limit = 3) {
  const uniqueNames = dedupeDeterministicValues((Array.isArray(matches) ? matches : []).map((match) => match?.job_name));
  const jobs = [];
  const errors = [];

  for (const jobName of uniqueNames.slice(0, limit)) {
    const variants = await searchDeterministicEmailJobsRaw(
      jobName,
      [buildDeterministicJobFilter('job_name', 'JobName', jobName)],
      shared,
    );
    if (!variants.length) {
      errors.push(`search_jobs(${jobName}): no exact job variants returned`);
      continue;
    }
    jobs.push(...variants.filter((job) => String(job?.job_name || job?.name || '').trim().toLowerCase() === String(jobName).trim().toLowerCase()));
  }

  return { jobs, errors };
}

function dedupeDeterministicTriageDidMatches(matches) {
  const seen = new Set();
  const output = [];
  for (const match of Array.isArray(matches) ? matches : []) {
    const did = String(match?.did || '').trim();
    const importDid = String(match?.import_did || '').trim();
    const matchedIn = String(match?.matched_in || '').trim();
    const key = `${did}|${importDid}|${matchedIn}`.toLowerCase();
    if (!did || seen.has(key)) continue;
    seen.add(key);
    output.push(match);
  }
  return output;
}

function pickDeterministicResolvedMatch(matches, didMatches = []) {
  const ranked = Array.isArray(matches) ? matches : [];
  if (!ranked.length) return null;
  if (ranked.length === 1) return ranked[0];
  return ranked[0];
}

function computeDeterministicTriageDidMatches(deals, metadata, matchMode, seedDidMatches = []) {
  const seeded = dedupeDeterministicTriageDidMatches(seedDidMatches);
  if (seeded.length) return seeded;
  if (!Array.isArray(deals) || !deals.length) return [];

  const normalizedMode = String(matchMode || '').trim().toLowerCase();
  const checkSubject = normalizedMode === 'subject' || normalizedMode === 'both';
  const checkFilename = normalizedMode === 'filename' || normalizedMode === 'both';
  if (!checkSubject && !checkFilename) return [];

  const subjectText = String(metadata.subject || '');
  const subjectLower = subjectText.toLowerCase();
  const subjectNormalized = normalizeDeterministicImportDidValue(subjectText);
  const filenames = Array.isArray(metadata.filenames) ? metadata.filenames : [];
  const filenamePairs = filenames.map((filename) => ({
    raw: filename,
    lower: String(filename || '').toLowerCase(),
    normalized: normalizeDeterministicImportDidValue(filename),
  }));
  const matches = [];

  for (const deal of deals) {
    const keyword = String(deal?.ImportDID || deal?.import_did || '').trim();
    const did = String(deal?.DID || deal?.did || '').trim();
    if (!keyword || !did) continue;

    const keywordLower = keyword.toLowerCase();
    const keywordNormalized = normalizeDeterministicImportDidValue(keyword);
    if (checkSubject && subjectLower && (
      subjectLower.includes(keywordLower)
      || (keywordNormalized && subjectNormalized.includes(keywordNormalized))
    )) {
      matches.push({ did, import_did: keyword, matched_in: 'subject', matched_value: metadata.subject });
      continue;
    }

    if (checkFilename) {
      const filenameHit = filenamePairs.find((pair) => pair.lower.includes(keywordLower)
        || (keywordNormalized && pair.normalized.includes(keywordNormalized)));
      if (filenameHit) {
        matches.push({ did, import_did: keyword, matched_in: 'filename', matched_value: filenameHit.raw });
      }
    }
  }

  return dedupeDeterministicTriageDidMatches(matches);
}

function pickDeterministicResolvedJob(jobDetails, didMatches) {
  if (!Array.isArray(jobDetails) || !jobDetails.length) return null;
  if (jobDetails.length === 1) return jobDetails[0];
  if (Array.isArray(didMatches) && didMatches.length === 1) {
    const did = String(didMatches[0]?.did || '').trim().toLowerCase();
    const matchedJob = jobDetails.find((detail) => Array.isArray(detail?.linked_deals)
      && detail.linked_deals.some((deal) => String(deal?.DID || deal?.did || '').trim().toLowerCase() === did));
    if (matchedJob) return matchedJob;
  }
  return jobDetails[0];
}

function scoreDeterministicResolvedJobVariant(job, preferredMatch, metadata) {
  if (!job) return 0;
  let score = 0;
  const mailboxCandidates = new Set(getDeterministicTriageMailboxCandidates(metadata));
  const jobMailbox = String(normalizeDeterministicMailboxValue(job?.mailbox || '')).toLowerCase();
  const jobSenderDomain = normalizeDeterministicSenderDomain(job?.sender || '');
  const preferredJobName = String(preferredMatch?.job_name || '').trim().toLowerCase();
  const preferredServicerId = String(preferredMatch?.servicer_id || '').trim();
  const preferredFilter = String(normalizeDeterministicEmailAddress(preferredMatch?.matched_filter || '')).toLowerCase();

  if (preferredJobName && String(job?.job_name || job?.name || '').trim().toLowerCase() === preferredJobName) score += 200;
  if (preferredServicerId && String(job?.servicer_id ?? '').trim() === preferredServicerId) score += 100;
  if (jobMailbox && mailboxCandidates.has(jobMailbox)) score += 75;
  if (preferredFilter && jobMailbox && preferredFilter === jobMailbox) score += 50;
  if (metadata?.senderDomain && jobSenderDomain && jobSenderDomain === String(metadata.senderDomain).trim().toLowerCase()) score += 40;
  return score;
}

function pickDeterministicResolvedJobVariant(jobVariants, preferredMatch, metadata) {
  const variants = Array.isArray(jobVariants) ? jobVariants : [];
  if (!variants.length) return null;
  return variants
    .slice()
    .sort((left, right) => scoreDeterministicResolvedJobVariant(right, preferredMatch, metadata) - scoreDeterministicResolvedJobVariant(left, preferredMatch, metadata))[0] || null;
}

function mergeDeterministicResolvedJob(detailJob, variantJob, preferredMatch, allMatches, metadata) {
  const merged = {
    ...(detailJob || {}),
    ...(variantJob || {}),
  };
  const jobName = String(preferredMatch?.job_name || merged?.job_name || '').trim().toLowerCase();
  const duplicateCount = (Array.isArray(allMatches) ? allMatches : []).filter((match) => String(match?.job_name || '').trim().toLowerCase() === jobName).length;
  const matchType = String(preferredMatch?.match_type || '').trim().toLowerCase();
  const senderDomain = normalizeDeterministicSenderDomain(merged?.sender || '');
  const emailSenderDomain = String(metadata?.senderDomain || '').trim().toLowerCase();

  merged.job_name = preferredMatch?.job_name || merged.job_name;
  merged.servicer_id = preferredMatch?.servicer_id ?? merged.servicer_id;
  merged.resolved_match_type = preferredMatch?.match_type || '';
  merged.resolved_match_confidence = preferredMatch?.match_confidence || '';
  merged.resolved_matched_filter = preferredMatch?.matched_filter || '';
  merged.resolved_email_field = preferredMatch?.email_field_matched || '';
  merged.resolved_duplicate_name_count = duplicateCount;
  merged.resolved_sender_conflict = Boolean(
    duplicateCount > 1
    && matchType === 'mailbox'
    && senderDomain
    && emailSenderDomain
    && senderDomain !== emailSenderDomain,
  );
  return merged;
}

function buildDeterministicTriageTimeControls(parsed) {
  return {
    days: String(parsed?.days || '30'),
    startDate: parsed?.startDate || null,
    endDate: parsed?.endDate || null,
  };
}

function buildDeterministicTriageDataSourceValue(metadata, resolvedJob = null) {
  return buildDeterministicTriageDataSourceValues(metadata, resolvedJob)[0] || '';
}

function buildDeterministicTriageLogAnchor(metadata, resolvedJob, resolvedDid) {
  const subject = buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject;
  if (subject) return subject;
  if (metadata?.primaryFilename) return metadata.primaryFilename;
  if (resolvedDid?.did) return resolvedDid.did;
  if (resolvedJob?.job_name) return resolvedJob.job_name;
  return resolvedJob?.scrubber || '';
}

function buildDeterministicTriageStagingAnchor(metadata, resolvedJob, resolvedDid) {
  const dataSourceValue = buildDeterministicTriageDataSourceValue(metadata, resolvedJob);
  if (dataSourceValue) return dataSourceValue;
  const subject = buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject;
  if (subject) return subject;
  if (resolvedDid?.did) return resolvedDid.did;
  if (metadata?.primaryFilename) return metadata.primaryFilename;
  if (resolvedJob?.scrubber) return resolvedJob.scrubber;
  if (resolvedJob?.servicer_id !== undefined && resolvedJob?.servicer_id !== null && resolvedJob?.servicer_id !== '') {
    return String(resolvedJob.servicer_id);
  }
  return '';
}

function buildDeterministicTriageLogFilters(metadata, resolvedJob) {
  const filters = [];
  const subject = buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject;
  if (resolvedJob?.job_name) filters.push({ field: 'job', value: resolvedJob.job_name });
  if (subject) filters.push({ field: 'subject', value: subject });
  return filters;
}

function buildDeterministicTriageLogSearchPlans(metadata, resolvedJob) {
  const subject = buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject;
  const jobName = String(resolvedJob?.job_name || '').trim();
  const filename = metadata?.primaryFilename && !isDeterministicInlineFilename(metadata.primaryFilename)
    ? String(metadata.primaryFilename).trim()
    : '';
  const sender = String(metadata?.sender || '').trim();
  const mailbox = getDeterministicTriageEvidenceMailboxes(metadata, resolvedJob)[0] || '';
  const plans = [];
  const seen = new Set();

  const pushPlan = (filters = [], query = '') => {
    const normalizedFilters = (Array.isArray(filters) ? filters : []).filter((filter) => filter?.field && filter?.value);
    const key = JSON.stringify({
      filters: normalizedFilters.map((filter) => ({ field: filter.field, value: String(filter.value) })),
      query: String(query || ''),
    });
    if (seen.has(key)) return;
    seen.add(key);
    plans.push({ filters: normalizedFilters, query: String(query || '') });
  };

  if (jobName) pushPlan([{ field: 'job', value: jobName }]);
  if (jobName && filename) pushPlan([{ field: 'job', value: jobName }, { field: 'filename', value: filename }]);
  if (jobName && subject) pushPlan([{ field: 'job', value: jobName }, { field: 'subject', value: subject }]);
  if (subject && mailbox) pushPlan([{ field: 'subject', value: subject }, { field: 'mailbox', value: mailbox }]);
  if (subject && sender) pushPlan([{ field: 'subject', value: subject }, { field: 'sender', value: sender }]);
  if (subject) pushPlan([{ field: 'subject', value: subject }]);
  if (filename) pushPlan([{ field: 'filename', value: filename }]);
  if (!plans.length && subject) pushPlan([], subject);
  return plans;
}

function matchesDeterministicTriageLogEmailEvent(emailEvent, metadata, resolvedJob) {
  const subjectNeedle = String(buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject || '').trim().toLowerCase();
  const senderNeedle = String(normalizeDeterministicEmailAddress(metadata?.sender || '')).toLowerCase();
  const mailboxCandidates = new Set(getDeterministicTriageEvidenceMailboxes(metadata, resolvedJob).map((value) => String(value || '').trim().toLowerCase()));
  const filenameNeedles = dedupeDeterministicValues([
    ...(Array.isArray(metadata?.filenames) ? metadata.filenames : []),
    metadata?.primaryFilename,
  ].filter((filename) => filename && !isDeterministicInlineFilename(filename))).map((filename) => String(filename || '').trim().toLowerCase());

  const rowSubject = String(emailEvent?.subject || '').toLowerCase();
  const rowSender = String(normalizeDeterministicEmailAddress(emailEvent?.sender || '')).toLowerCase();
  const rowMailbox = String(normalizeDeterministicEmailAddress(emailEvent?.mailbox || '')).toLowerCase();
  const rowFiles = [
    ...(Array.isArray(emailEvent?.files) ? emailEvent.files : []),
    emailEvent?.filename,
  ].filter(Boolean).map((value) => String(value || '').toLowerCase());

  const subjectMatch = subjectNeedle ? rowSubject.includes(subjectNeedle) : false;
  const senderMatch = senderNeedle ? rowSender === senderNeedle : false;
  const mailboxMatch = mailboxCandidates.size ? mailboxCandidates.has(rowMailbox) : false;
  const filenameMatch = filenameNeedles.some((needle) => rowFiles.some((value) => value.includes(needle)));

  if (subjectMatch || filenameMatch) return true;
  if (!subjectNeedle && !filenameNeedles.length) return senderMatch || mailboxMatch;
  return senderMatch && mailboxMatch;
}

function filterDeterministicTriageLogLinkage(payload, metadata, resolvedJob) {
  if (!payload || !Array.isArray(payload.email_events)) return payload;
  const emailEvents = payload.email_events.filter((row) => matchesDeterministicTriageLogEmailEvent(row, metadata, resolvedJob));
  return {
    ...payload,
    email_events: emailEvents,
    email_count: emailEvents.length,
    event_count: emailEvents.length,
  };
}

function collectDeterministicTriageStagingRows(linkagePayload, searchPayloads) {
  const seen = new Set();
  const rows = [];
  const pushRows = (values) => {
    for (const row of Array.isArray(values) ? values : []) {
      const rowId = row?.TemplateProcessID;
      const key = rowId !== undefined && rowId !== null ? String(rowId) : JSON.stringify(row);
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(row);
    }
  };

  pushRows(linkagePayload?.records || linkagePayload?.recent_staging || []);
  for (const payload of Array.isArray(searchPayloads) ? searchPayloads : []) {
    pushRows(payload?.results || payload?.runs || payload?.traces || []);
  }
  return rows;
}

function stagingRowMatchesEmail(row, metadata, resolvedJob = null) {
  const filePath = String(row?.FilePath || row?.file_path || '').toLowerCase();
  const dataSource = String(row?.DataSource || '').toLowerCase();
  const filenameMatch = Array.isArray(metadata?.filenames)
    && metadata.filenames
      .filter((filename) => !isDeterministicInlineFilename(filename))
      .some((filename) => filePath.includes(String(filename || '').toLowerCase()));
  const dataSourceValues = buildDeterministicTriageDataSourceValues(metadata, resolvedJob);
  const dataSourceMatch = dataSourceValues.some((value) => dataSource.includes(String(value || '').toLowerCase()));
  return filenameMatch || dataSourceMatch;
}

function classifyDeterministicTriageOutcome(context) {
  if (!context.candidateMatches.length) {
    return {
      status: 'potential_new',
      heading: 'Potentially New Email',
      summary: 'No configured job matched this email strongly enough to continue deterministic tracing.',
    };
  }

  const exactRows = context.matchingStagingRows;
  const failedRow = exactRows.find((row) => Number(row?.ResultCode) === 1);
  if (failedRow) {
    return {
      status: 'failed',
      heading: 'Matched And Failed Downstream',
      summary: 'The email matched a configured job and reached template staging, but the downstream template run failed.',
    };
  }

  const successRow = exactRows.find((row) => Number(row?.ResultCode) === 0);
  if (successRow) {
    return {
      status: 'processed',
      heading: 'Processed Successfully',
      summary: 'The email matched a configured job and a staging row confirms successful downstream processing.',
    };
  }

  if ((context.logLinkage?.event_count || 0) > 0) {
    return {
      status: 'seen_not_proven',
      heading: 'Seen In Logs, Not Proven In Staging',
      summary: 'Log evidence shows the email was observed or matched, but no staging row definitively proves the downstream file processing.',
    };
  }

  if (context.resolvedJob && !context.deals.length) {
    return {
      status: 'process_level',
      heading: 'Process-Level Candidate',
      summary: 'A job matched, but no deal mappings were found. This can be normal for process-level or shelf-level jobs.',
    };
  }

  return {
    status: 'configured_unproven',
    heading: 'Configured But Unproven',
    summary: 'A job appears to match, but deterministic log and staging evidence could not yet prove what happened downstream.',
  };
}

function renderDeterministicTriageMatchTable(lines, matches) {
  if (!Array.isArray(matches) || !matches.length) {
    lines.push('_No candidate jobs were retained after deterministic narrowing._');
    lines.push('');
    return;
  }

  lines.push('| JobName | MatchType | Confidence | ServicerID | Matched Filter |');
  lines.push('|---------|-----------|------------|------------|----------------|');
  for (const match of matches.slice(0, 10)) {
    const jobName = String(match?.job_name || '—');
    const servicerId = match?.servicer_id ?? '—';
    lines.push(`| ${linkOrText(jobName, `/jobXMLEmail detail ${jobName}`)} | ${escapeMarkdownText(match?.match_type || '—')} | ${escapeMarkdownText(match?.match_confidence || '—')} | ${linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${escapeMarkdownText(match?.matched_filter || '—')} |`);
  }
  lines.push('');
}

function renderDeterministicTriageEmailMetadata(lines, metadata) {
  lines.push('**Email Metadata**');
  lines.push(`- Sender: ${escapeMarkdownText(metadata.sender || '—')}`);
  lines.push(`- Mailboxes: ${Array.isArray(metadata?.mailboxes) && metadata.mailboxes.length ? metadata.mailboxes.map((value) => escapeMarkdownText(value)).join(', ') : escapeMarkdownText(metadata.primaryMailbox || '—')}`);
  lines.push(`- Subject: ${escapeMarkdownText(metadata.subject || '—')}`);
  lines.push(`- Filenames: ${metadata.filenames.length ? metadata.filenames.map((value) => escapeMarkdownText(value)).join(', ') : '—'}`);
  if (metadata.filePath) lines.push(`- Msg Path: ${escapeMarkdownText(metadata.filePath)}`);
  if (metadata.date) lines.push(`- Email Date: ${escapeMarkdownText(metadata.date)}`);
  lines.push('');
}

function renderDeterministicTriageResolvedJob(lines, resolvedJob) {
  if (!resolvedJob) {
    lines.push('**Resolved Job**');
    lines.push('- No exact job was resolved yet.');
    lines.push('');
    return;
  }

  lines.push('**Resolved Job**');
  lines.push(`- JobName: ${linkOrText(resolvedJob.job_name || '—', `/jobXMLEmail detail ${resolvedJob.job_name || ''}`)}`);
  if (resolvedJob.mailbox) lines.push(`- Mailbox: ${escapeMarkdownText(resolvedJob.mailbox)}`);
  if (resolvedJob.resolved_match_type || resolvedJob.resolved_matched_filter) {
    lines.push(`- Match Evidence: ${escapeMarkdownText(resolvedJob.resolved_match_type || 'match')} ${escapeMarkdownText(resolvedJob.resolved_match_confidence || '').trim() ? `(${resolvedJob.resolved_match_confidence})` : ''} on ${escapeMarkdownText(resolvedJob.resolved_matched_filter || resolvedJob.resolved_email_field || '—')}`.replace(/\s+on\s+$/, ''));
  }
  if (resolvedJob.sender && !resolvedJob.resolved_sender_conflict) {
    lines.push(`- Sender Filter: ${escapeMarkdownText(resolvedJob.sender)}`);
  }
  if (resolvedJob.resolved_sender_conflict) {
    lines.push('- Sender Filter: omitted because multiple jobs share this name and the name-only detail lookup returned a conflicting sender domain.');
  }
  if (Number(resolvedJob.resolved_duplicate_name_count || 0) > 1) {
    lines.push(`- Duplicate Job Names: ${resolvedJob.resolved_duplicate_name_count} matched rows share this job name; mailbox-backed evidence was used as the tie-breaker.`);
  }
  if (resolvedJob.servicer_id !== undefined && resolvedJob.servicer_id !== null && resolvedJob.servicer_id !== '') lines.push(`- ServicerID: ${linkOrText(resolvedJob.servicer_id, `/deals dossier ${resolvedJob.servicer_id}`)}`);
  if (resolvedJob.scrubber) lines.push(`- Scrubber: ${linkOrText(resolvedJob.scrubber, `/staging linkage ${resolvedJob.scrubber}`)}`);
  if (resolvedJob.match_mode) lines.push(`- MatchMode: ${escapeMarkdownText(resolvedJob.match_mode)}`);
  if (resolvedJob.save_path) lines.push(`- SavePath: ${escapeMarkdownText(resolvedJob.save_path)}`);
  lines.push('');
}

function renderDeterministicTriageDealCoverage(lines, deals, didMatches) {
  lines.push('**Deal Coverage**');
  if (!Array.isArray(deals) || !deals.length) {
    lines.push('- No deal rows were returned for the resolved servicer. This can be normal for process-level jobs.');
    lines.push('');
    return;
  }

  lines.push(`- Company deal rows inspected for DID keywords: ${deals.length}`);
  lines.push('');

  lines.push('**DID Resolution**');
  if (!Array.isArray(didMatches) || !didMatches.length) {
    lines.push('- No deterministic ImportDID keyword matched the email subject or filenames.');
  } else {
    lines.push('| DID | ImportDID | Matched In | Matched Value |');
    lines.push('|-----|-----------|------------|---------------|');
    for (const match of didMatches.slice(0, 8)) {
      lines.push(`| ${linkOrText(match.did || '—', `/deals did:${match.did || ''}`)} | ${linkOrText(match.import_did || '—', `/deals keyword:${match.import_did || ''}`)} | ${escapeMarkdownText(match.matched_in || '—')} | ${escapeMarkdownText(match.matched_value || '—')} |`);
    }
  }
  lines.push('');
}

function renderDeterministicTriageLogEvidence(lines, context, parsed) {
  lines.push('**Log Evidence**');
  if (context.logErrors.length) {
    lines.push(`- Log lookup warnings: ${escapeMarkdownText(context.logErrors.join('; '))}`);
  }
  const logPayload = context.logLinkage || {};
  lines.push(`- Linkage Query: ${escapeMarkdownText(context.logAnchor || '—')}`);
  if (Array.isArray(context.logSearchCriteria) && context.logSearchCriteria.length) {
    lines.push(`- Search Basis: ${context.logSearchCriteria.map((entry) => escapeMarkdownText(entry)).join(' | ')}`);
  }
  lines.push(`- Matching Email Events: ${logPayload.email_count || logPayload.event_count || 0}`);
  if (context.jobHealth?.status) lines.push(`- Job Health: ${escapeMarkdownText(context.jobHealth.status)} (${context.jobHealth.success_rate || 0}% success)`);
  if (context.dealActivity?.total_events !== undefined) lines.push(`- Deal Activity Events: ${context.dealActivity.total_events}`);
  if (context.didFailures?.total_failures !== undefined) lines.push(`- DID Failures: ${context.didFailures.total_failures}`);
  lines.push('');

  const emailEvents = Array.isArray(logPayload.email_events) ? logPayload.email_events.slice(0, 6) : [];
  if (emailEvents.length) {
    lines.push('| First Seen | JobName | Mailbox | Subject |');
    lines.push('|------------|---------|---------|---------|');
    for (const row of emailEvents) {
      lines.push(`| ${escapeMarkdownText(row.first_seen || row.last_seen || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name || ''}; days:${parsed.days || 30}`)} | ${escapeMarkdownText(row.mailbox || '—')} | ${escapeMarkdownText(row.subject || '—')} |`);
    }
    lines.push('');
    return;
  }

  const events = Array.isArray(logPayload.events) ? logPayload.events.slice(0, 6) : [];
  if (events.length) {
    lines.push('| Timestamp | JobName | EventType | Evidence |');
    lines.push('|-----------|---------|-----------|----------|');
    for (const row of events) {
      const evidence = buildDeterministicLogEventEvidence(row);
      lines.push(`| ${escapeMarkdownText(row.timestamp || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name || ''}; days:${parsed.days || 30}`)} | ${escapeMarkdownText(row.event_type || '—')} | ${escapeMarkdownText(evidence.compact || '—')} |`);
    }
    lines.push('');
  }
}

function renderDeterministicTriageStagingEvidence(lines, context) {
  lines.push('**Staging Evidence**');
  if (context.stagingErrors.length) {
    lines.push(`- Staging lookup warnings: ${escapeMarkdownText(context.stagingErrors.join('; '))}`);
  }
  lines.push(`- Linkage Query: ${escapeMarkdownText(context.stagingAnchor || '—')}`);
  if (Array.isArray(context.stagingSearchCriteria) && context.stagingSearchCriteria.length) {
    lines.push(`- Search Basis: ${context.stagingSearchCriteria.map((entry) => escapeMarkdownText(entry)).join(' | ')}`);
  }
  lines.push(`- Matching Staging Rows: ${context.stagingRows.length}`);
  lines.push(`- Exact Email / File Matches: ${context.matchingStagingRows.length}`);
  lines.push('');

  if (context.matchingStagingRows.length) {
    renderDeterministicStagingRowsTable(context.matchingStagingRows, lines, { limit: 10 });
  } else if (context.stagingRows.length) {
    renderDeterministicStagingRowsTable(context.stagingRows, lines, { limit: 10 });
  } else {
    lines.push('_No deterministic staging rows matched the current trace window._');
  }
  lines.push('');
}

function buildDeterministicTriageActions(context) {
  const actions = [];
  const seen = new Set();

  for (const action of buildDeterministicJobDetailActions(context.resolvedJob || {})) {
    pushUniqueDeterministicAction(actions, seen, action.prompt, action.label);
  }
  for (const action of buildDeterministicLogsSearchActions(context.logLinkage || {})) {
    pushUniqueDeterministicAction(actions, seen, action.prompt, action.label);
  }
  for (const action of buildDeterministicStagingLinkageActions(context.stagingLinkage || {})) {
    pushUniqueDeterministicAction(actions, seen, action.prompt, action.label);
  }

  if (!actions.length) {
    if (context.metadata?.sender) {
      pushUniqueDeterministicAction(actions, seen, `/jobXMLEmail list sender:${context.metadata.senderDomain || context.metadata.sender}`, 'Inspect sender jobs');
    }
    if (context.metadata?.primaryMailbox) {
      pushUniqueDeterministicAction(actions, seen, `/jobXMLEmail list mailbox:${context.metadata.primaryMailbox}`, 'Inspect mailbox jobs');
    }
  }

  return actions.slice(0, 6);
}

function renderDeterministicTriageTraceResult(context, parsed) {
  const outcome = classifyDeterministicTriageOutcome(context);
  const lines = [
    '### Email Triage Trace',
    '',
    '> Deterministic path · Seed: triage backend + deterministic jobs/deals/logs/staging',
    '',
  ];

  renderDeterministicTriageEmailMetadata(lines, context.metadata);
  lines.push('**Candidate Jobs**');
  renderDeterministicTriageMatchTable(lines, context.candidateMatches);
  renderDeterministicTriageResolvedJob(lines, context.resolvedJob);
  renderDeterministicTriageDealCoverage(lines, context.deals, context.didMatches);
  renderDeterministicTriageLogEvidence(lines, context, parsed);
  renderDeterministicTriageStagingEvidence(lines, context);
  lines.push('**Outcome**');
  lines.push(`- Status: ${escapeMarkdownText(outcome.heading)}`);
  lines.push(`- Summary: ${escapeMarkdownText(outcome.summary)}`);
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicTriageActions(context));
  return lines.join('\n');
}

function renderDeterministicTriageMatchResult(seedPayload, metadata, matches) {
  const lines = [
    '### Email Triage Match',
    '',
    '> Deterministic path · Seed: triage_match',
    '',
  ];
  renderDeterministicTriageEmailMetadata(lines, metadata);
  lines.push('**Candidate Jobs**');
  renderDeterministicTriageMatchTable(lines, matches);
  return lines.join('\n');
}

function renderDeterministicTriageNewResult(seedPayload, metadata, cloneSuggestions = []) {
  const suggestion = seedPayload?.suggested_config || {};
  const lines = [
    '### Email Triage — New Job Suggestion',
    '',
    '> Deterministic path · Seed: triage_new',
    '',
  ];
  renderDeterministicTriageEmailMetadata(lines, metadata);
  lines.push('**Recommendation**');
  lines.push(`- ${escapeMarkdownText(seedPayload?.recommendation || 'No recommendation returned.')}`);
  if (seedPayload?.suggested_template) lines.push(`- Suggested Template: ${escapeMarkdownText(seedPayload.suggested_template)}`);
  if (Object.keys(suggestion).length) {
    lines.push('- Suggested Config:');
    for (const [key, value] of Object.entries(suggestion)) {
      if (Array.isArray(value)) {
        lines.push(`  - ${key}: ${value.join(', ')}`);
      } else {
        lines.push(`  - ${key}: ${value}`);
      }
    }
  }
  lines.push('');
  renderDeterministicCloneSuggestions(lines, cloneSuggestions);
  return lines.join('\n');
}

function renderDeterministicTriageNoExactMatchResult(metadata, newSeedPayload, cloneSuggestions) {
  const lines = [
    '### Email Triage — No Exact Match',
    '',
    '> Deterministic path · No exact mailbox-backed match was found, so triage switched to new-job guidance.',
    '',
  ];
  renderDeterministicTriageEmailMetadata(lines, metadata);
  lines.push('**Outcome**');
  lines.push('- Status: Potentially New Email');
  lines.push('- Summary: No exact mailbox match was found. Sender-domain or other partial matches were ignored for detail-email triage.');
  lines.push('');
  lines.push('**Recommendation**');
  lines.push(`- ${escapeMarkdownText(newSeedPayload?.recommendation || 'No recommendation returned.')}`);
  if (newSeedPayload?.suggested_template) {
    lines.push(`- Suggested Template: ${escapeMarkdownText(newSeedPayload.suggested_template)}`);
  }
  lines.push('');
  renderDeterministicCloneSuggestions(lines, cloneSuggestions);
  return lines.join('\n');
}

async function handleDeterministicTriageCommand(request, stream, shared) {
  const parsed = parseDeterministicTriagePrompt(request.prompt);
  if (!parsed) return null;

  if (!isDeterministicExperimentEnabled()) {
    streamTrustedMarkdown(stream, [
      '### /triage',
      '',
      'The deterministic triage shortcuts are currently disabled.',
      'Enable `frpAgent.enableDeterministicJobExperiment` to use deterministic `/triage` trace mode.',
      '',
      buildDeterministicTriageHelpText(),
    ].join('\n'));
    return { followUps: [] };
  }

  if (parsed.help) {
    streamTrustedMarkdown(stream, buildDeterministicTriageHelpText());
    return { followUps: buildDeterministicTriageFollowUps() };
  }

  if (parsed.error) {
    streamTrustedMarkdown(stream, [
      '### /triage',
      '',
      parsed.error,
      '',
      buildDeterministicTriageHelpText(),
    ].join('\n'));
    return { followUps: buildDeterministicTriageFollowUps() };
  }

  shared.outputChannel.appendLine(`[FRP] Deterministic triage: action=${parsed.action} raw=${parsed.rawQuery || ''}`);

  if (parsed.action === 'new') {
    const seedResult = await safeDeterministicBackendCall('triage_new', { msgPath: parsed.msgPath }, shared, { timeoutMs: 0 });
    if (!seedResult.ok) {
      stream.markdown(`❌ **Deterministic /triage new failed:** ${seedResult.error}\n`);
      return { followUps: [] };
    }

    const metadata = buildDeterministicTriageMetadata(parsed, seedResult.data);
    const cloneSuggestions = await buildDeterministicCloneSuggestions(seedResult.data, metadata, shared);
    streamTrustedMarkdown(stream, renderDeterministicTriageNewResult(seedResult.data, metadata, cloneSuggestions));
    return {
      followUps: buildDeterministicCloneFollowUps(cloneSuggestions).length
        ? buildDeterministicCloneFollowUps(cloneSuggestions)
        : [
            { prompt: `/triage trace ${parsed.msgPath}`, label: 'Trace again' },
            { prompt: 'list all email jobs', label: 'Browse jobs' },
          ],
    };
  }

  const seedCommand = parsed.msgPath ? 'triage_verify' : 'triage_match';
  const seedParams = parsed.msgPath
    ? { msgPath: parsed.msgPath }
    : {
        sender: parsed.sender || undefined,
        subject: parsed.subject || undefined,
      };

  const seedResult = await safeDeterministicBackendCall(seedCommand, seedParams, shared, { timeoutMs: 0 });
  if (!seedResult.ok) {
    stream.markdown(`❌ **Deterministic /triage ${parsed.action} failed:** ${seedResult.error}\n`);
    return { followUps: [] };
  }

  const metadata = buildDeterministicTriageMetadata(parsed, seedResult.data);
  const candidateMatches = await narrowDeterministicTriageMatches(seedResult.data, metadata, shared);

  if (parsed.action === 'match') {
    streamTrustedMarkdown(stream, renderDeterministicTriageMatchResult(seedResult.data, metadata, candidateMatches));
    const firstMatch = candidateMatches[0];
    return {
      followUps: firstMatch
        ? [
            { prompt: `/jobXMLEmail detail ${firstMatch.job_name}`, label: `Job detail: ${firstMatch.job_name}` },
            { prompt: `/triage trace sender:${metadata.sender}; subject:${metadata.subject}`, label: 'Run full trace' },
          ]
        : buildDeterministicTriageFollowUps(),
    };
  }

  if (!candidateMatches.length && parsed.msgPath) {
    const newSeedResult = await safeDeterministicBackendCall('triage_new', { msgPath: parsed.msgPath }, shared, { timeoutMs: 0 });
    if (newSeedResult.ok) {
      const cloneSuggestions = await buildDeterministicCloneSuggestions(newSeedResult.data, metadata, shared);
      streamTrustedMarkdown(stream, renderDeterministicTriageNoExactMatchResult(metadata, newSeedResult.data, cloneSuggestions));
      const followUps = buildDeterministicCloneFollowUps(cloneSuggestions);
      return {
        followUps: followUps.length
          ? followUps
          : [
              { prompt: '/triage new "' + parsed.msgPath + '"', label: 'Show new-job guidance' },
              { prompt: 'list all email jobs', label: 'Browse jobs' },
            ],
      };
    }
  }

  const traceErrors = [];
  const resolvedMatch = pickDeterministicResolvedMatch(candidateMatches, seedResult.data?.did_matches || []);
  const jobDetailBundle = await loadDeterministicTriageJobDetails(candidateMatches, shared, 3);
  traceErrors.push(...jobDetailBundle.errors);
  const jobVariantBundle = await loadDeterministicTriageJobVariants(candidateMatches, shared, 3);
  traceErrors.push(...jobVariantBundle.errors);

  let deals = Array.isArray(seedResult.data?.deals) ? seedResult.data.deals : [];
  let resolvedJob = null;
  let didMatches = dedupeDeterministicTriageDidMatches(seedResult.data?.did_matches || []);

  const resolvedVariant = pickDeterministicResolvedJobVariant(jobVariantBundle.jobs, resolvedMatch, metadata);
  resolvedJob = mergeDeterministicResolvedJob(pickDeterministicResolvedJob(jobDetailBundle.details, didMatches), resolvedVariant, resolvedMatch, candidateMatches, metadata);
  const linkedDeals = jobDetailBundle.details.flatMap((detail) => (Array.isArray(detail?.linked_deals) ? detail.linked_deals : []));
  deals = selectDeterministicTriageDeals(deals, linkedDeals);

  if (!didMatches.length) {
    didMatches = computeDeterministicTriageDidMatches(deals, metadata, resolvedJob?.match_mode, []);
  }
  const resolvedDid = didMatches.length === 1 ? didMatches[0] : null;
  if (!resolvedJob) {
    resolvedJob = mergeDeterministicResolvedJob(pickDeterministicResolvedJob(jobDetailBundle.details, didMatches), resolvedVariant, resolvedMatch, candidateMatches, metadata);
  }

  const timeControls = buildDeterministicTriageTimeControls(parsed);
  let logLinkage = null;
  let jobHealth = null;
  let dealActivity = null;
  let didFailures = null;
  const logErrors = [];
  const logSearchCriteria = [];
  const logAnchor = buildDeterministicTriageLogAnchor(metadata, resolvedJob, resolvedDid);

  if (resolvedJob && logAnchor) {
    const logSearchPlans = buildDeterministicTriageLogSearchPlans(metadata, resolvedJob);
    for (const plan of logSearchPlans) {
      const criteria = Array.isArray(plan.filters) && plan.filters.length
        ? plan.filters.map((filter) => `${filter.field}=${filter.value}`)
        : [`query=${plan.query || logAnchor}`];
      const evidenceCriteria = [];
      const subjectBasis = buildDeterministicTriageSubjectSearchValue(metadata) || metadata?.subject;
      if (subjectBasis) evidenceCriteria.push(`match_subject=${subjectBasis}`);
      if (metadata?.primaryFilename && !isDeterministicInlineFilename(metadata.primaryFilename)) {
        evidenceCriteria.push(`match_filename=${metadata.primaryFilename}`);
      }
      const effectiveCriteria = dedupeDeterministicValues([...criteria, ...evidenceCriteria]);
      const logSearchParams = {
        query: '',
        mode: 'emails',
        days: timeControls.days,
        limit: '10',
      };
      if (timeControls.startDate) logSearchParams.startDate = timeControls.startDate;
      if (timeControls.endDate) logSearchParams.endDate = timeControls.endDate;
      if (Array.isArray(plan.filters) && plan.filters.length) logSearchParams.filters = JSON.stringify(plan.filters);
      else logSearchParams.query = plan.query || logAnchor;

      const logSearchResult = await safeDeterministicBackendCall('log_search', logSearchParams, shared, { timeoutMs: 0 });
      if (!logSearchResult.ok) {
        logErrors.push(`log_search(${effectiveCriteria.join(', ')}): ${logSearchResult.error}`);
        continue;
      }

      const payload = filterDeterministicTriageLogLinkage({
        ...logSearchResult.data,
        query: logAnchor,
        event_count: logSearchResult.data?.email_count ?? logSearchResult.data?.event_count ?? 0,
      }, metadata, resolvedJob);
      if (!logLinkage) {
        logLinkage = payload;
        logSearchCriteria.splice(0, logSearchCriteria.length, ...effectiveCriteria);
      }
      if ((payload.email_count || payload.event_count || 0) > 0) {
        logLinkage = payload;
        logSearchCriteria.splice(0, logSearchCriteria.length, ...effectiveCriteria);
        break;
      }
    }

    const jobHealthResult = await safeDeterministicBackendCall('log_job_health', {
      jobName: resolvedJob.job_name,
      days: timeControls.days,
    }, shared, { timeoutMs: 0 });
    if (jobHealthResult.ok) {
      jobHealth = jobHealthResult.data;
    } else {
      logErrors.push(`log_job_health(${resolvedJob.job_name}): ${jobHealthResult.error}`);
    }

    if (resolvedDid?.did) {
      const dealActivityResult = await safeDeterministicBackendCall('log_deal_activity', {
        did: resolvedDid.did,
        days: timeControls.days,
      }, shared, { timeoutMs: 0 });
      if (dealActivityResult.ok) {
        dealActivity = dealActivityResult.data;
      } else {
        logErrors.push(`log_deal_activity(${resolvedDid.did}): ${dealActivityResult.error}`);
      }
    } else if (resolvedJob.job_name) {
      const didFailuresResult = await safeDeterministicBackendCall('log_did_failures', {
        jobFilter: resolvedJob.job_name,
        days: timeControls.days,
      }, shared, { timeoutMs: 0 });
      if (didFailuresResult.ok) {
        didFailures = didFailuresResult.data;
      } else {
        logErrors.push(`log_did_failures(${resolvedJob.job_name}): ${didFailuresResult.error}`);
      }
    }
  }

  let stagingLinkage = null;
  const stagingSearchPayloads = [];
  const stagingErrors = [];
  const stagingSearchCriteria = [];
  const stagingAnchor = buildDeterministicTriageStagingAnchor(metadata, resolvedJob, resolvedDid);

  if (resolvedJob && stagingAnchor) {
    const searchSpecs = [];
    for (const dataSourceValue of buildDeterministicTriageDataSourceValues(metadata, resolvedJob).slice(0, 3)) {
      searchSpecs.push({ label: 'datasource', filters: [{ field: 'datasource', value: dataSourceValue }] });
    }
    if (metadata.primaryFilename && !isDeterministicInlineFilename(metadata.primaryFilename)) {
      searchSpecs.push({ label: 'filepath', filters: [{ field: 'filepath', value: metadata.primaryFilename }] });
    }
    if (resolvedDid?.did) {
      searchSpecs.push({ label: 'did', filters: [{ field: 'did', value: resolvedDid.did }] });
    } else if (resolvedJob.scrubber) {
      searchSpecs.push({ label: 'template', filters: [{ field: 'template', value: resolvedJob.scrubber }] });
    }

    for (const spec of searchSpecs.slice(0, 3)) {
      if (Array.isArray(spec.filters) && spec.filters.length) {
        for (const filter of spec.filters) {
          stagingSearchCriteria.push(`${filter.field}=${filter.value}`);
        }
      } else if (spec.query) {
        stagingSearchCriteria.push(`query=${spec.query}`);
      }
      const searchParams = {
        query: spec.query || '',
        filters: JSON.stringify(spec.filters),
        days: timeControls.days,
        limit: '15',
      };
      if (timeControls.startDate) searchParams.startDate = timeControls.startDate;
      if (timeControls.endDate) searchParams.endDate = timeControls.endDate;

      const searchResult = await safeDeterministicBackendCall('staging_search', searchParams, shared, { timeoutMs: 0 });
      if (searchResult.ok) {
        stagingSearchPayloads.push(searchResult.data);
      } else {
        stagingErrors.push(`staging_search(${spec.label}): ${searchResult.error}`);
      }
    }

    stagingLinkage = {
      query: stagingAnchor,
      records: collectDeterministicTriageStagingRows(null, stagingSearchPayloads),
    };
  }

  const stagingRows = collectDeterministicTriageStagingRows(stagingLinkage, stagingSearchPayloads);
  const matchingStagingRows = stagingRows.filter((row) => stagingRowMatchesEmail(row, metadata, resolvedJob));

  const traceContext = {
    metadata,
    candidateMatches,
    resolvedJob,
    deals,
    didMatches,
    resolvedDid,
    logAnchor,
    logLinkage,
    logSearchCriteria,
    jobHealth,
    dealActivity,
    didFailures,
    logErrors,
    stagingAnchor,
    stagingLinkage,
    stagingSearchCriteria,
    stagingRows,
    matchingStagingRows,
    stagingErrors,
    traceErrors,
  };

  streamTrustedMarkdown(stream, renderDeterministicTriageTraceResult(traceContext, parsed));
  return { followUps: buildDeterministicTriageActions(traceContext) };
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

  // Staging / template runs
  if ((command === 'staging' || command === 'trace') && data.data) {
    const d = data.data;
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

function isDeterministicExperimentEnabled() {
  const config = vscode.workspace.getConfiguration('frpAgent');
  return config.get('enableDeterministicJobExperiment', false) === true;
}

function getDeterministicCommandSpec(commandName) {
  return DETERMINISTIC_COMMAND_SPECS[commandName] || null;
}

function escapeMarkdownText(value) {
  return String(value ?? '—')
    .replace(/\\/g, '\\\\')
    .replace(/\r?\n/g, ' ')
    .replace(/\|/g, '\\|')
    .replace(/\[/g, '\\[')
    .replace(/\]/g, '\\]');
}

function buildInlineActionUri(prompt) {
  return `command:${INLINE_CHAT_ACTION_COMMAND}?${encodeURIComponent(JSON.stringify([{ prompt }]))}`;
}

function buildInlinePromptLink(prompt, label) {
  return `[${escapeMarkdownText(label)}](${buildInlineActionUri(prompt)})`;
}

function linkOrText(label, prompt) {
  if (label === undefined || label === null || label === '') return '—';
  const text = String(label);
  return prompt ? buildInlinePromptLink(prompt, text) : escapeMarkdownText(text);
}

function toTrustedMarkdown(text) {
  const markdown = new vscode.MarkdownString(text);
  markdown.isTrusted = { enabledCommands: TRUSTED_CHAT_COMMANDS };
  markdown.supportThemeIcons = true;
  return markdown;
}

function streamTrustedMarkdown(stream, text) {
  stream.markdown(toTrustedMarkdown(text));
}

function listDeterministicFields(xmlType) {
  const aliases = DETERMINISTIC_FIELD_ALIASES[xmlType] || {};
  return [...new Set(Object.values(aliases).map((entry) => entry.label))];
}

function splitDeterministicClauses(text) {
  return String(text || '')
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean);
}

function buildDeterministicHelpText(commandName) {
  const spec = getDeterministicCommandSpec(commandName);
  if (!spec) return null;

  const examples = spec.xmlType === 'email'
    ? [
        'list CMBS',
        'list mailbox:rptent@usbank.com',
        'list CMBS; mailbox:rptent@usbank.com; servicer:569',
        'list sender:@fay.com',
        'detail CMBS_GreyCo',
      ]
    : [
        'list SPS',
        'list path:SPS',
        'list SPS; dsn:prod; servicer:569',
        'list dsn:prod',
        'detail Some_SFTP_Job',
      ];

  const lines = [
    `### /${commandName} — Deterministic ${spec.kindLabel} Jobs`,
    '',
    `Runs directly against ${spec.sourceLabel} with no LLM generation.`,
  ];

  if (spec.preferredCommand) {
    lines.push(`Legacy email alias. Prefer \`/${spec.preferredCommand}\` for clarity.`);
  }

  lines.push('');
  lines.push('Supported forms:');
  lines.push('- `list <query>`');
  lines.push('- `list <query>; field:value; field:value`');
  lines.push('- `detail <jobName>`');
  lines.push(`- Optional field filters for list: ${listDeterministicFields(spec.xmlType).map((field) => `\`${field}\``).join(', ')}`);
  lines.push('- Semicolon-separated filters are combined with AND logic.');
  lines.push('- Legacy compatibility: `list-CMBS` also works.');
  lines.push('');
  lines.push('Field meanings:');
  if (spec.xmlType === 'email') {
    lines.push('- `JobName`: the XML element name under `MailboxCollection`.');
    lines.push('- `Mailbox`: the monitored mailbox address.');
    lines.push('- `Sender`: the email sender/domain filter from `Filters.From`.');
    lines.push('- `ServicerID`: the operational key that links this job to `tblExternalDIDRef.CompanyID`.');
    lines.push('- `Scrubber`: the workflow/template name that later appears as `tblTemplateStaging.TemplateName`.');
    lines.push('- `MatchMode`: how FRP detects the file. `Subject` means keyword in subject, `Filename` means attachment filename, `Both` means both signals are used.');
    lines.push('- `SavePath`: where the detached file lands before downstream processing.');
  } else {
    lines.push('- `JobName`: the XML element name under `FolderCollection`.');
    lines.push('- `Path`: the monitored SFTP/drop location.');
    lines.push('- `DSN`: the configured source connection name.');
    lines.push('- `ServicerID`: the operational key that links this job to `tblExternalDIDRef.CompanyID`.');
    lines.push('- `Scrubber`: the workflow/template name that later appears as `tblTemplateStaging.TemplateName`.');
    lines.push('- `MatchMode`: the file matching behavior configured for this job.');
    lines.push('- `SavePath`: where the moved/downloaded file lands before downstream processing.');
  }
  lines.push('');
  lines.push('Cross-table mental model:');
  lines.push('- `Settings.xml / SQLite job` → `ServicerID` links to `/deals` via `CompanyID`.');
  lines.push('- `Settings.xml / SQLite job` → `Scrubber` links to `/staging` via `TemplateName`.');
  lines.push('');
  lines.push('Examples:');
  for (const example of examples) {
    lines.push(`- ${buildInlinePromptLink(`/${commandName} ${example}`, example)}`);
  }

  return lines.join('\n');
}

function normalizeDeterministicField(xmlType, fieldName) {
  const aliases = DETERMINISTIC_FIELD_ALIASES[xmlType] || {};
  return aliases[fieldName.toLowerCase()] || null;
}

function buildDeterministicJobFilterPrompt(commandName, filter) {
  const fieldToken = String(filter?.fieldLabel || filter?.fieldFilter || '').toLowerCase();
  return `/${commandName} list ${fieldToken}:${filter.query}`;
}

function describeDeterministicJobFilter(filter, commandName) {
  const operator = filter.fieldFilter === 'servicer_id' ? '=' : 'contains';
  const valueText = commandName
    ? buildInlinePromptLink(buildDeterministicJobFilterPrompt(commandName, filter), String(filter.query))
    : `\`${filter.query}\``;
  return `${filter.fieldLabel} ${operator} ${valueText}`;
}

function getDeterministicJobFilters(parsed) {
  if (Array.isArray(parsed?.filters) && parsed.filters.length) {
    return parsed.filters;
  }
  if (parsed?.fieldFilter && parsed?.query) {
    return [{
      fieldFilter: parsed.fieldFilter,
      fieldLabel: parsed.fieldLabel,
      query: parsed.query,
      rawQuery: parsed.rawQuery || parsed.query,
    }];
  }
  return [];
}

function isSlashHelpPrompt(prompt) {
  const text = prompt.trim().toLowerCase();
  if (!text) return false;
  return [
    'help',
    '?',
    'what does this do',
    'what will this do',
    'how do i use this',
    'how can i use this',
    'how do i ask questions',
    'how can i ask questions',
    'what can i ask',
    'show examples',
    'examples',
  ].some((phrase) => text === phrase || text.includes(phrase));
}

function getSlashHelpText(commandName, deterministicSpec) {
  if (deterministicSpec) {
    return buildDeterministicHelpText(commandName);
  }
  if (commandName === 'triage' && isDeterministicExperimentEnabled()) {
    return buildDeterministicTriageHelpText();
  }
  if (commandName === 'logs' && isDeterministicExperimentEnabled()) {
    return buildDeterministicLogsHelpText();
  }
  if (commandName === 'staging' && isDeterministicExperimentEnabled()) {
    return buildDeterministicStagingHelpText();
  }
  if (commandName === 'deals' && isDeterministicExperimentEnabled()) {
    return buildDeterministicDealsHelpText();
  }
  return SLASH_HELP[commandName] || `### /${commandName}\n\nType your query after the command.\n`;
}

function getSlashHelpFollowUps(commandName, deterministicSpec) {
  if (deterministicSpec) {
    return buildDeterministicHelpFollowUps(deterministicSpec);
  }
  if (commandName === 'triage' && isDeterministicExperimentEnabled()) {
    return buildDeterministicTriageFollowUps();
  }
  if (commandName === 'logs' && isDeterministicExperimentEnabled()) {
    return buildDeterministicLogsFollowUps();
  }
  if (commandName === 'staging' && isDeterministicExperimentEnabled()) {
    return buildDeterministicStagingFollowUps();
  }
  if (commandName === 'deals' && isDeterministicExperimentEnabled()) {
    return buildDeterministicDealsFollowUps();
  }
  return SLASH_FOLLOWUPS[commandName] || [];
}

function parseDeterministicFieldClause(clause, xmlType) {
  const separatorMatch = clause.match(/^([a-z_]+)\s*[:=\-]\s*(.+)$/i);
  if (separatorMatch) {
    const normalized = normalizeDeterministicField(xmlType, separatorMatch[1]);
    if (!normalized) {
      return {
        error: `Unsupported filter \`${separatorMatch[1]}\` for ${xmlType.toUpperCase()} jobs. Supported fields: ${listDeterministicFields(xmlType).join(', ')}.`,
      };
    }

    const value = separatorMatch[2].trim();
    if (!value) {
      return { error: `Filter \`${separatorMatch[1]}\` requires a value.` };
    }

    return {
      query: value,
      rawQuery: clause,
      fieldFilter: normalized.key,
      fieldLabel: normalized.label,
    };
  }

  const tokenMatch = clause.match(/^([a-z_]+)\s+(.+)$/i);
  if (tokenMatch) {
    const normalized = normalizeDeterministicField(xmlType, tokenMatch[1]);
    if (normalized) {
      const value = tokenMatch[2].trim();
      if (!value) {
        return { error: `Filter \`${tokenMatch[1]}\` requires a value.` };
      }

      return {
        query: value,
        rawQuery: clause,
        fieldFilter: normalized.key,
        fieldLabel: normalized.label,
      };
    }
  }

  return { query: clause, rawQuery: clause };
}

function parseDeterministicListClauses(remainder, xmlType) {
  const clauses = splitDeterministicClauses(remainder);
  if (!clauses.length) {
    return { error: 'Use `list <query>` or `list field:value`.' };
  }

  let textQuery = null;
  const filters = [];
  const seenFields = new Set();

  for (const clause of clauses) {
    const parsedClause = parseDeterministicFieldClause(clause, xmlType);
    if (parsedClause.error) {
      return parsedClause;
    }

    if (!parsedClause.fieldFilter) {
      if (textQuery) {
        return {
          error: 'Use at most one unfielded search term before semicolon filters.',
        };
      }
      textQuery = parsedClause.query;
      continue;
    }

    if (seenFields.has(parsedClause.fieldFilter)) {
      return {
        error: `Filter \`${parsedClause.fieldLabel}\` can only be supplied once per deterministic job lookup.`,
      };
    }

    seenFields.add(parsedClause.fieldFilter);
    filters.push(parsedClause);
  }

  if (!textQuery && !filters.length) {
    return { error: 'Use `list <query>` or `list field:value`.' };
  }

  return {
    query: textQuery || filters[0].query,
    rawQuery: remainder,
    textQuery,
    filters,
    fieldFilter: filters.length === 1 ? filters[0].fieldFilter : null,
    fieldLabel: filters.length === 1 ? filters[0].fieldLabel : null,
  };
}

function parseDeterministicPrompt(prompt, xmlType) {
  const trimmed = prompt.trim();
  if (!trimmed) {
    return { error: 'Use `list <query>` or `detail <jobName>`.' };
  }

  if (isSlashHelpPrompt(trimmed)) {
    return { help: true };
  }

  let action;
  let remainder;

  const legacyMatch = trimmed.match(/^(list|detail)\s*-(.+)$/i);
  if (legacyMatch) {
    action = legacyMatch[1].toLowerCase();
    remainder = legacyMatch[2].trim();
  } else {
    const standardMatch = trimmed.match(/^(list|detail)\s+(.+)$/i);
    if (!standardMatch) {
      return { error: 'Use `list <query>` or `detail <jobName>`.' };
    }
    action = standardMatch[1].toLowerCase();
    remainder = standardMatch[2].trim();
  }

  if (!remainder) {
    return { error: 'The command requires a value. Use `list <query>` or `detail <jobName>`.' };
  }

  if (action === 'detail') {
    return { action, jobName: remainder };
  }

  const parsedField = parseDeterministicListClauses(remainder, xmlType);
  return {
    action,
    ...parsedField,
  };
}

function buildDeterministicCommonParams(spec) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const outlookSettingsPath = config.get('outlookSettingsPath', '');
  const sftpSettingsPath = config.get('sftpSettingsPath', '');
  const cacheDbPath = config.get('cacheDbPath', '');

  if (spec.xmlType === 'email' && !outlookSettingsPath) {
    throw new Error('frpAgent.outlookSettingsPath must be configured for deterministic email job commands.');
  }

  if (spec.xmlType === 'sftp' && !sftpSettingsPath) {
    throw new Error('frpAgent.sftpSettingsPath must be configured for deterministic SFTP job commands.');
  }

  if (spec.sourceKind === 'sqlite' && !cacheDbPath) {
    throw new Error(`frpAgent.cacheDbPath must be configured for /${spec.xmlType === 'email' ? 'jobSQLiteEmail' : 'jobSQLiteSftp'} deterministic searches.`);
  }

  return {
    xmlType: spec.xmlType,
    settingsPath: spec.xmlType === 'email' ? outlookSettingsPath : (outlookSettingsPath || sftpSettingsPath),
    sftpSettingsPath,
    cacheDbPath: spec.sourceKind === 'sqlite' ? cacheDbPath : '',
  };
}

function buildDeterministicSearchParams(spec, query) {
  return {
    ...buildDeterministicCommonParams(spec),
    query,
  };
}

function buildDeterministicDetailParams(spec, jobName) {
  return {
    ...buildDeterministicCommonParams(spec),
    jobName,
  };
}

function isDeterministicFailure(result) {
  return !result || result.status === 'error' || result.success === false;
}

function applyDeterministicFieldFilter(jobs, parsed) {
  const filters = getDeterministicJobFilters(parsed);
  if (!filters.length) return jobs;

  return jobs.filter((job) => filters.every((filter) => {
    const actual = job?.[filter.fieldFilter];
    if (actual === undefined || actual === null) return false;
    const expected = String(filter.query).trim().toLowerCase();
    const actualText = String(actual).trim().toLowerCase();
    if (filter.fieldFilter === 'servicer_id') {
      return actualText === expected;
    }
    return actualText.includes(expected);
  }));
}

function pickDominantValue(jobs, fieldName) {
  const counts = new Map();
  for (const job of jobs) {
    const value = job?.[fieldName];
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  const ranked = [...counts.entries()].sort((left, right) => right[1] - left[1]);
  return ranked[0] || null;
}

function renderDeterministicJobsResult(result, spec, parsed, commandName) {
  const payload = result?.data || {};
  const jobs = applyDeterministicFieldFilter(Array.isArray(payload.jobs) ? payload.jobs : [], parsed);
  const filters = getDeterministicJobFilters(parsed);
  const byScrubber = pickDominantValue(jobs, 'scrubber');
  const sourceField = spec.xmlType === 'email' ? 'mailbox' : 'dsn';
  const bySource = pickDominantValue(jobs, sourceField);
  const title = spec.xmlType === 'email' ? 'Email Monitoring Jobs' : 'SFTP Monitoring Jobs';

  const lines = [
    `### ${title}`,
    '',
    `> Deterministic path · Source: ${spec.sourceLabel} · Type: ${spec.kindLabel}`,
    '',
  ];

  if (jobs.length === 0) {
    lines.push(`_No ${spec.kindLabel.toLowerCase()} jobs matched \`${parsed.rawQuery || parsed.query}\`._`);
    return lines.join('\n');
  }

  lines.push('**Summary**');
  lines.push(`- Total Jobs: ${jobs.length}`);
  if (parsed.textQuery) {
    lines.push(`- Base Query: ${buildInlinePromptLink(`/${commandName} list ${parsed.textQuery}`, parsed.textQuery)}`);
  }
  if (filters.length) {
    lines.push(`- Field Filters: ${filters.map((filter) => describeDeterministicJobFilter(filter, commandName)).join('; ')}`);
  }
  if (byScrubber) lines.push(`- Top Scrubber: ${byScrubber[0]} (${byScrubber[1]} jobs)`);
  if (bySource) {
    const sourceLabel = spec.xmlType === 'email' ? 'Mailbox' : 'DSN';
    lines.push(`- Top ${sourceLabel}: ${bySource[0]} (${bySource[1]} jobs)`);
  }
  lines.push('');

  if (spec.xmlType === 'email') {
    lines.push('| JobName | Mailbox | Sender | ServicerID | Scrubber | MatchMode | SavePath |');
    lines.push('|---------|---------|--------|------------|----------|-----------|----------|');

    for (const job of jobs) {
      const name = job.job_name || job.name || '—';
      const mailbox = job.mailbox || '—';
      const sender = job.sender || '—';
      const servicerId = job.servicer_id ?? '—';
      const scrubber = job.scrubber || job.template || '—';
      const matchMode = job.match_mode || '—';
      const savePath = job.save_path || job.save_location || '—';
      const detailPrompt = `/${commandName} detail ${name}`;
      lines.push(`| ${linkOrText(name, detailPrompt)} | ${linkOrText(mailbox, `/${commandName} list mailbox:${mailbox}`)} | ${linkOrText(sender, `/${commandName} list sender:${sender}`)} | ${linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${linkOrText(scrubber, `/${commandName} list scrubber:${scrubber}`)} | ${linkOrText(matchMode, detailPrompt)} | ${linkOrText(savePath, detailPrompt)} |`);
    }
  } else {
    lines.push('| JobName | Path | DSN | ServicerID | Scrubber | MatchMode | SavePath |');
    lines.push('|---------|------|-----|------------|----------|-----------|----------|');

    for (const job of jobs) {
      const name = job.job_name || job.name || '—';
      const path = job.sftp_path || job.path || '—';
      const dsn = job.dsn || '—';
      const servicerId = job.servicer_id ?? '—';
      const scrubber = job.scrubber || job.template || '—';
      const matchMode = job.match_mode || '—';
      const savePath = job.save_path || job.save_location || '—';
      const detailPrompt = `/${commandName} detail ${name}`;
      lines.push(`| ${linkOrText(name, detailPrompt)} | ${linkOrText(path, `/${commandName} list path:${path}`)} | ${linkOrText(dsn, `/${commandName} list dsn:${dsn}`)} | ${linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${linkOrText(scrubber, `/${commandName} list scrubber:${scrubber}`)} | ${linkOrText(matchMode, detailPrompt)} | ${linkOrText(savePath, detailPrompt)} |`);
    }
  }

  lines.push('');
  lines.push('Click any job row value to open or refine a deterministic query.');
  return lines.join('\n');
}

function renderDeterministicDetailResult(result, spec, commandName) {
  const data = result?.data || {};
  if (!data.job_name) {
    return '_No deterministic job detail was returned._';
  }

  const linkedDeals = Array.isArray(data.linked_deals) ? data.linked_deals : [];
  const nextActions = buildDeterministicJobDetailActions(data);

  const lines = [
    `### ${data.job_name}`,
    '',
    `> Deterministic path · Source: ${spec.sourceLabel} · Type: ${spec.kindLabel}`,
    '',
    '**Details**',
  ];

  const pushDetail = (label, value) => {
    if (value === undefined || value === null || value === '') return;
    if (typeof value === 'boolean') {
      lines.push(`- ${label}: ${value ? 'Yes' : 'No'}`);
      return;
    }
    let prompt = null;
    if (label === 'Mailbox') prompt = `/${commandName} list mailbox:${value}`;
    else if (label === 'Sender') prompt = `/${commandName} list sender:${value}`;
    else if (label === 'SFTP Path') prompt = `/${commandName} list path:${value}`;
    else if (label === 'DSN') prompt = `/${commandName} list dsn:${value}`;
    else if (label === 'Servicer ID') prompt = `/deals servicer:${value}`;
    else if (label === 'Scrubber') prompt = `/${commandName} list scrubber:${value}`;
    else if (label === 'Save Path' || label === 'Match Mode' || label === 'Match Behavior') prompt = `/${commandName} detail ${data.job_name}`;

    if (prompt) {
      lines.push(`- ${label}: ${linkOrText(value, prompt)}`);
      return;
    }
    lines.push(`- ${label}: ${escapeMarkdownText(value)}`);
  };

  if (spec.xmlType === 'email') {
    pushDetail('Mailbox', data.mailbox);
    pushDetail('Folder', data.folder);
    pushDetail('Sender', data.sender);
  } else {
    pushDetail('SFTP Path', data.sftp_path);
    pushDetail('DSN', data.dsn);
    pushDetail('Zip Filter', data.zip_filter);
  }

  pushDetail('Servicer ID', data.servicer_id);
  pushDetail('Scrubber', data.scrubber);
  pushDetail('Match Mode', data.match_mode);
  pushDetail('Match Behavior', data.match_mode_description);
  pushDetail('Save Path', data.save_path);
  pushDetail('SME', data.sme);
  pushDetail('Last Email', data.last_email);
  pushDetail('Queue One File', data.queue_one_file);
  pushDetail('Day Adjust', data.day_adjust);
  pushDetail('Linked Deals', data.linked_deal_count);

  if (data.note) {
    lines.push(`- Note: ${data.note}`);
  }

  if (linkedDeals.length) {
    lines.push('');
    lines.push('**Linked Deals**');
    lines.push('| DID | ImportDID | CompanyID |');
    lines.push('|-----|-----------|-----------|');
    for (const deal of linkedDeals.slice(0, 10)) {
      const did = deal.DID || deal.did || '—';
      const importDid = deal.ImportDID || deal.import_did || '—';
      const companyId = deal.CompanyID || deal.company_id || '—';
      lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
    }
    if (linkedDeals.length > 10) {
      lines.push('');
      lines.push(`- Showing first 10 of ${linkedDeals.length} linked deals.`);
    }
  }

  const recent = data.recent_processing || {};
  if (recent.total_runs) {
    lines.push('');
    lines.push('**Recent Processing (30 days)**');
    lines.push(`- Total Runs: ${recent.total_runs}`);
    lines.push(`- Success Rate: ${recent.success_rate}%`);
    if (recent.last_success) lines.push(`- Last Success: ${recent.last_success}`);
    if (recent.last_failure) lines.push(`- Last Failure: ${recent.last_failure}`);
  }

  lines.push('');
  lines.push(`Use ${buildInlinePromptLink(`/deals dossier ${data.job_name}`, `/deals dossier ${data.job_name}`)} when you want the broader business context for this job.`);
  lines.push('');
  appendDeterministicNextActions(lines, nextActions);

  return lines.join('\n');
}

function buildDeterministicHelpFollowUps(spec) {
  if (spec.xmlType === 'email') {
    return [
      { prompt: 'list CMBS', label: 'Example: list CMBS' },
      { prompt: 'list mailbox:rptent@usbank.com', label: 'Example: mailbox filter' },
      { prompt: 'list CMBS; mailbox:rptent@usbank.com; servicer:569', label: 'Example: combined filters' },
      { prompt: 'detail CMBS_GreyCo', label: 'Example: detail' },
    ];
  }

  return [
    { prompt: 'list SPS', label: 'Example: list SPS' },
    { prompt: 'list path:SPS', label: 'Example: path filter' },
    { prompt: 'list SPS; dsn:prod; servicer:569', label: 'Example: combined filters' },
    { prompt: 'detail Some_SFTP_Job', label: 'Example: detail' },
  ];
}

function normalizeDeterministicDealMode(modeName) {
  return DETERMINISTIC_DEAL_MODE_ALIASES[modeName.toLowerCase()] || null;
}

function canonicalDeterministicDealFilterKey(lookupType) {
  return lookupType === 'servicer' ? 'company' : lookupType;
}

function getDeterministicDealFilters(parsed) {
  if (Array.isArray(parsed?.filters) && parsed.filters.length) {
    return parsed.filters;
  }
  if (parsed?.lookupType && parsed?.query) {
    return [{
      lookupType: parsed.lookupType,
      modeLabel: parsed.modeLabel,
      query: parsed.query,
      rawQuery: parsed.rawQuery || parsed.query,
    }];
  }
  return [];
}

function describeDeterministicDealFilter(filter) {
  const operator = canonicalDeterministicDealFilterKey(filter.lookupType) === 'company' ? '=' : 'contains';
  const prompt = `/deals ${filter.lookupType}:${filter.query}`;
  return `${filter.modeLabel} ${operator} ${buildInlinePromptLink(prompt, String(filter.query))}`;
}

function buildDeterministicDealsHelpText() {
  const examples = [
    { prompt: '/deals did:FREMF 2026-KF169', label: 'did:FREMF 2026-KF169' },
    { prompt: '/deals keyword:FREMF', label: 'keyword:FREMF' },
    { prompt: '/deals keyword:KF169; company:569', label: 'keyword:KF169; company:569' },
    { prompt: '/deals company 569', label: 'company 569' },
    { prompt: '/deals servicer=569', label: 'servicer=569' },
    { prompt: '/deals dossier CMBS_GreyCo', label: 'dossier CMBS_GreyCo' },
    { prompt: '/deals dossier 569', label: 'dossier 569' },
  ];

  return [
    '### /deals — Deterministic tblExternalDIDRef Queries',
    '',
    'Deterministic `/deals` shortcuts query `tblExternalDIDRef` directly and can also surface linked jobs.',
    '',
    'Supported forms:',
    '- `did <value>`',
    '- `keyword <value>`',
    '- `keyword <value>; company <id>`',
    '- `company <id>`',
    '- `servicer <id>`',
    '- `dossier <servicerId-or-jobName>`',
    '- forgiving separators: `:`, `=`, `-`, or plain space',
    '- semicolon-separated lookup filters are combined with AND logic',
    '',
    'Column meanings:',
    '- `DID`: the business-facing deal name.',
    '- `ImportDID`: the keyword FRP searches for in email subjects, filenames, or other inbound identifiers.',
    '- `CompanyID`: the servicer/company dimension used by jobs and staging. `company` and `servicer` are the same deterministic lookup dimension.',
    '- `dossier`: the joined business view that combines DID rows, linked jobs, and staging summary for one servicer or job.',
    '',
    'Examples of what to ask:',
    '- “Which deals use keyword KF169?” → `keyword:KF169`',
    '- “Show me everything for servicer 569” → `dossier 569`',
    '- “Which CompanyID is job CMBS_GreyCo tied to?” → `dossier CMBS_GreyCo`',
    '',
    'Examples:',
    ...examples.map((example) => `- ${buildInlinePromptLink(example.prompt, example.label)}`),
    '',
    'Anything outside these shortcuts still falls back to the normal agentic `/deals` flow.',
  ].join('\n');
}

function buildDeterministicDealsFollowUps() {
  return [
    { prompt: 'did:FREMF 2026-KF169', label: 'Lookup DID' },
    { prompt: 'keyword:FREMF', label: 'Lookup keyword' },
    { prompt: 'keyword:KF169; company:569', label: 'Combine keyword + company' },
    { prompt: 'servicer:569', label: 'Lookup servicer' },
    { prompt: 'dossier 569', label: 'Servicer dossier' },
  ];
}

function normalizeDeterministicStagingField(fieldName) {
  return DETERMINISTIC_STAGING_FIELD_ALIASES[String(fieldName || '').toLowerCase()] || null;
}

function listDeterministicStagingFields() {
  const entries = Object.values(DETERMINISTIC_STAGING_FIELD_ALIASES)
    .filter((entry) => entry.kind === 'filter')
    .map((entry) => entry.label);
  return [...new Set(entries)];
}

function buildDeterministicStagingHelpText() {
  const examples = [
    { prompt: '/staging list QueueCMBS', label: 'list QueueCMBS' },
    { prompt: '/staging filepath:022026 Juniper Receivables 2022-2 DAC.xlsx', label: 'filepath:022026 Juniper Receivables 2022-2 DAC.xlsx' },
    { prompt: '/staging list source:manual; result:failed; days:7', label: 'list source:manual; result:failed; days:7' },
    { prompt: '/staging detail 12345', label: 'detail 12345' },
    { prompt: '/staging status FREMF 2026-KF169', label: 'status FREMF 2026-KF169' },
    { prompt: '/staging history QueueCMBS; start:2026-01-01; end:2026-01-31', label: 'history QueueCMBS; start:2026-01-01; end:2026-01-31' },
    { prompt: '/staging source M:\\!Sweeps\\Ocwen\\In', label: 'source M:\\!Sweeps\\Ocwen\\In' },
    { prompt: '/staging linkage QueueCMBS', label: 'linkage QueueCMBS' },
    { prompt: '/staging audit', label: 'audit' },
  ];

  return [
    '### /staging — Deterministic tblTemplateStaging Queries',
    '',
    'Deterministic `/staging` shortcuts query tblTemplateStaging directly and link results back to Settings.xml/SQLite jobs plus deterministic `/deals` lookups.',
    'If your prompt does not match these shortcuts, `/staging` still falls back to the normal freeform agentic flow.',
    'Most deterministic staging lookups default to a **30-day window**. If you are investigating older history, add `days:<n>` or `start:` / `end:`.',
    '',
    'Supported forms:',
    '- `list <query>`',
    '- `list <query>; field:value; field:value`',
    '- `field:value; field:value` (shorthand for `list ...` when every clause is a deterministic filter/control)',
    '- `detail <TemplateProcessID-or-query>`',
    '- `status <template|did|servicer>`',
    '- `history <query>; start:YYYY-MM-DD; end:YYYY-MM-DD`',
    '- `source <filepath-pattern>`',
    '- `linkage <template|did|filepath>`',
    '- `audit`',
    `- Filter fields for list/history: ${listDeterministicStagingFields().map((field) => `\`${field}\``).join(', ')}`,
    '- Time controls: `days`, `start`, `end`',
    '- Semicolon-separated filters use AND logic.',
    '',
    'Column meanings:',
    '- `TemplateProcessID`: the unique staging row ID. Use it with `detail <id>`.',
    '- `TemplateName`: the scrubber/workflow that processed the file. This links back to deterministic job `Scrubber`.',
    '- `DID`: the deal name. This may be blank for process-level or shelf-level jobs.',
    '- `ServicerID`: the operational key linking staging to `/deals` `CompanyID` and to jobs.',
    '- `Dt`: the report / processing date used for most date filters.',
    '- `StartTime`, `EndTime`: execution timestamps. Missing `EndTime` usually means still running or not fully completed.',
    '- `ResultCode`: `0 = success`, `1 = failed`.',
    '- `Comments`: usually `Ok` on success, or the detailed error text on failure.',
    '- `FilePath`: the processed file path on disk/network.',
    '',
    'Source fields and how to read them:',
    '- `SourceProcess`: the queuing mechanism. Common values are `ActiveBatch` and `ManualQueue`.',
    '- `Job`: the parser/script family that queued or processed the file, such as `DetachFile`, `DetachFileSubject`, `MoveFile`, `MoveFile2`, or `ManualJob`.',
    '- `DataSource`: the best field for the real origin of the file.',
    '  Email example: `mailbox@domain: subject line`',
    '  SFTP example: `SFTPMonitor: M:\\!Sweeps\\Ocwen\\In`',
    '  Manual example: `Queued via macro by jmho`',
    '',
    'Why your screenshot returned no rows in chat:',
    '- `status VCC` and `list did:VCC` were valid syntax.',
    '- Deterministic `/staging` now treats recency as execution time first: `StartTime`, then `EndTime`, with `Dt` only as a fallback when execution timestamps are missing.',
    '- If you still see empty results for a recent row, compare the exact DID/template text and whether the row has unusual null execution timestamps.',
    '- Historical lookups like `status VCC; days:1500` or `list did:VCC; days:1500` are still useful when you want older execution history too.',
    '',
    'Examples:',
    ...examples.map((example) => `- ${buildInlinePromptLink(example.prompt, example.label)}`),
    `- ${buildInlinePromptLink('/staging status VCC; days:1500', 'status VCC; days:1500')}`,
    `- ${buildInlinePromptLink('/staging list did:VCC; days:1500', 'list did:VCC; days:1500')}`,
  ].join('\n');
}

function buildDeterministicStagingFollowUps() {
  return [
    { prompt: 'list QueueCMBS', label: 'Browse staging rows' },
    { prompt: 'list source:manual; result:failed; days:7', label: 'Manual failures' },
    { prompt: 'status FREMF 2026-KF169', label: 'Status by DID' },
    { prompt: 'status VCC; days:1500', label: 'Historical DID search' },
    { prompt: 'linkage QueueCMBS', label: 'Link to jobs' },
    { prompt: 'audit', label: 'Audit gaps' },
  ];
}

function normalizeDeterministicLogField(fieldName) {
  return DETERMINISTIC_LOG_FIELD_ALIASES[String(fieldName || '').toLowerCase()] || null;
}

function listDeterministicLogFields() {
  const fields = Object.values(DETERMINISTIC_LOG_FIELD_ALIASES)
    .filter((entry) => entry.kind === 'filter')
    .map((entry) => entry.label);
  return [...new Set(fields)];
}

function buildDeterministicLogsHelpText() {
  const examples = [
    { prompt: '/logs summary today', label: 'summary today' },
    { prompt: '/logs health CMBS_GreyCo; days:30', label: 'health CMBS_GreyCo; days:30' },
    { prompt: '/logs failures job:CMBS_GreyCo; days:30', label: 'failures job:CMBS_GreyCo; days:30' },
    { prompt: '/logs deal FREMF 2026-KF169; days:30', label: 'deal FREMF 2026-KF169; days:30' },
    { prompt: '/logs search queue; sender:@usbank.com; mode:events; days:14', label: 'search queue; sender:@usbank.com; mode:events; days:14' },
    { prompt: '/logs search mailbox:ops@example.com; mode:details; limit:10; days:3', label: 'search mailbox:ops@example.com; mode:details; limit:10; days:3' },
    { prompt: '/logs linkage CMBS_GreyCo; days:30', label: 'linkage CMBS_GreyCo; days:30' },
    { prompt: '/logs trends job:CMBS_GreyCo; days:14', label: 'trends job:CMBS_GreyCo; days:14' },
    { prompt: '/logs performance sort:total_errors; order:desc; top:10; days:30', label: 'performance sort:total_errors; order:desc; top:10; days:30' },
  ];

  return [
    '### /logs — Deterministic Processing Log Queries',
    '',
    'Deterministic `/logs` shortcuts query the SQLite processing-log index directly and then bridge the result back to jobs, deals, and staging.',
    'Log queries do **not** auto-sync the index. Run `/sync_logs` or `/logs sync` first when freshness matters.',
    'If a prompt does not match one of these shortcuts, `/logs` still falls back to the existing freeform log workflow.',
    '',
    'Supported forms:',
    '- `summary [today|YYYY-MM-DD]`',
    '- `health <jobName>; days:<n>`',
    '- `failures [job:<jobName>; days:<n>]`',
    '- `deal <did-or-keyword>; days:<n>`',
    '- `search <query>; field:value; mode:summary|emails|events|details|errors|activity`',
    '- `linkage <job|did|servicer|clue>; days:<n>`',
    '- `trends [job:<jobName>; days:<n>]`',
    '- `performance [sort:<metric>; order:asc|desc; top:<n>; days:<n>]`',
    '- `sync`',
    `- Search filter fields: ${listDeterministicLogFields().map((field) => `\`${field}\``).join(', ')}`,
    '- Control fields: `days`, `start`, `end`, `limit`, `mode`, `sort`, `top`, `order`, `date`',
    '- Semicolon-separated filters use AND logic. Write control clauses as separate `; field:value` segments, for example `subject:FREMF25K548; days:3`.',
    '',
    'Log field meanings:',
    '- `JobName`: the monitoring job that emitted the log line. This is the bridge back to deterministic job detail and servicer dossiers.',
    '- `EventType`: the pipeline step or error category, such as `job_start`, `processing`, `parser_match`, `file_load`, `template_queue`, or `did_mapping_failed`.',
    '- `Mailbox`: the monitored mailbox or SFTP location captured when the job started.',
    '- `Sender`: the email sender seen on the inbound message.',
    '- `Parser`: the parser or script chosen for the item, which often hints at the downstream scrubber path.',
    '- `Filename` and `Subject`: the inbound file or email clue that lets you bridge into deal keywords and staging records.',
    '- `Template`: the queued scrubber/template name when the log line already knows the downstream processing target.',
    '- Use `mode:events` for a compact event table and `mode:details` for fuller email/file evidence including subject, sender, attachment/file name, scrubber, and DID clues when present.',
    '',
    'Cross-table mental model:',
    '- `Logs.JobName` -> deterministic job detail -> `ServicerID` -> `/deals`',
    '- `Logs.Template` or parser/file clues -> `/staging` recent executions',
    '- `Logs.Subject` / `Filename` / DID-failure text -> deterministic `/deals keyword:` or `/deals did:`',
    '',
    'Examples:',
    ...examples.map((example) => `- ${buildInlinePromptLink(example.prompt, example.label)}`),
  ].join('\n');
}

function buildDeterministicLogsFollowUps() {
  return [
    { prompt: 'summary today', label: 'Today summary' },
    { prompt: 'health CMBS_GreyCo; days:30', label: 'Job health' },
    { prompt: 'failures days:30', label: 'DID failures' },
    { prompt: 'search queue; mode:events; days:14', label: 'Search events' },
    { prompt: 'linkage CMBS_GreyCo; days:30', label: 'Cross-linkage' },
  ];
}

function parseDeterministicLogFieldClause(clause) {
  const separatorMatch = clause.match(/^([a-z_]+)\s*[:=\-]\s*(.+)$/i);
  const tokenMatch = separatorMatch || clause.match(/^([a-z_]+)\s+(.+)$/i);
  if (!tokenMatch) {
    return { kind: 'text', query: clause, rawQuery: clause };
  }

  const normalized = normalizeDeterministicLogField(tokenMatch[1]);
  if (!normalized) {
    return { kind: 'text', query: clause, rawQuery: clause };
  }

  const value = tokenMatch[2].trim();
  if (!value) {
    return { error: `Filter \`${tokenMatch[1]}\` requires a value.` };
  }

  if (normalized.kind === 'control') {
    return { kind: 'control', control: normalized.field, controlLabel: normalized.label, value };
  }

  return {
    kind: 'filter',
    fieldName: normalized.field,
    fieldLabel: normalized.label,
    query: value,
    rawQuery: clause,
  };
}

function parseDeterministicLogClauses(remainder, options = {}) {
  const clauses = splitDeterministicClauses(remainder);
  if (!clauses.length) {
    return options.allowEmpty ? { query: '', rawQuery: remainder, filters: [] } : { error: 'Add a query or at least one structured filter.' };
  }

  const filters = [];
  const controls = {};
  const seenFilters = new Set();
  const seenControls = new Set();
  let textQuery = null;

  for (const clause of clauses) {
    const parsedClause = parseDeterministicLogFieldClause(clause);
    if (parsedClause.error) return parsedClause;

    if (parsedClause.kind === 'text') {
      if (options.allowText === false) {
        return { error: `Use structured filters only for this /logs form. Unsupported clause: \`${clause}\`.` };
      }
      if (textQuery) {
        return { error: 'Use at most one unfielded search term before semicolon filters.' };
      }
      textQuery = parsedClause.query;
      continue;
    }

    if (parsedClause.kind === 'control') {
      if (seenControls.has(parsedClause.control)) {
        return { error: `Control \`${parsedClause.controlLabel}\` can only be supplied once.` };
      }
      seenControls.add(parsedClause.control);
      controls[parsedClause.control] = parsedClause.value;
      continue;
    }

    if (seenFilters.has(parsedClause.fieldName)) {
      return { error: `Filter \`${parsedClause.fieldLabel}\` can only be supplied once.` };
    }

    seenFilters.add(parsedClause.fieldName);
    filters.push(parsedClause);
  }

  if (options.requireText && !textQuery && !filters.length) {
    return { error: 'This /logs form requires a target query.' };
  }

  return {
    query: textQuery || '',
    textQuery,
    rawQuery: remainder,
    filters,
    ...controls,
  };
}

function parseDeterministicLogsPrompt(prompt) {
  const trimmed = prompt.trim();
  if (!trimmed) return null;
  if (isSlashHelpPrompt(trimmed)) return { help: true };

  const lower = trimmed.toLowerCase();
  if (['sync', 'sync logs', 'refresh', 'refresh logs'].includes(lower)) {
    return { action: 'sync', rawQuery: trimmed };
  }
  if (['today', 'what happened today', 'daily summary', 'summary today'].includes(lower)) {
    return { action: 'summary', date: null, rawQuery: trimmed };
  }

  let match = trimmed.match(/^summary(?:\s+(.+))?$/i);
  if (match) {
    const remainder = (match[1] || '').trim();
    if (!remainder) return { action: 'summary', date: null, rawQuery: trimmed };
    const parsed = parseDeterministicLogClauses(remainder, { allowText: true, allowEmpty: true });
    if (parsed.error) return parsed;
    return {
      action: 'summary',
      rawQuery: trimmed,
      date: parsed.date || parsed.textQuery || null,
    };
  }

  match = trimmed.match(/^health\s+(.+)$/i);
  if (match) {
    const parsed = parseDeterministicLogClauses(match[1].trim(), { allowText: true, requireText: true });
    if (parsed.error) return parsed;
    return { action: 'health', rawQuery: trimmed, query: parsed.textQuery || parsed.query, days: parsed.days };
  }

  match = trimmed.match(/^(?:failures|didfailures|did-failures)(?:\s+(.+))?$/i);
  if (match) {
    const remainder = (match[1] || '').trim();
    const parsed = remainder
      ? parseDeterministicLogClauses(remainder, { allowText: true, allowEmpty: true })
      : { query: '', filters: [], rawQuery: '' };
    if (parsed.error) return parsed;
    const jobFilter = parsed.filters?.find((filter) => filter.fieldName === 'job');
    return {
      action: 'failures',
      rawQuery: trimmed,
      jobQuery: jobFilter?.query || parsed.textQuery || null,
      days: parsed.days,
    };
  }

  match = trimmed.match(/^(?:deal|did)\s+(.+)$/i);
  if (match) {
    const parsed = parseDeterministicLogClauses(match[1].trim(), { allowText: true, requireText: true });
    if (parsed.error) return parsed;
    return { action: 'deal', rawQuery: trimmed, query: parsed.textQuery || parsed.query, days: parsed.days };
  }

  match = trimmed.match(/^trends(?:\s+(.+))?$/i);
  if (match) {
    const remainder = (match[1] || '').trim();
    const parsed = remainder
      ? parseDeterministicLogClauses(remainder, { allowText: true, allowEmpty: true })
      : { query: '', filters: [], rawQuery: '' };
    if (parsed.error) return parsed;
    const jobFilter = parsed.filters?.find((filter) => filter.fieldName === 'job');
    return {
      action: 'trends',
      rawQuery: trimmed,
      jobQuery: jobFilter?.query || parsed.textQuery || null,
      days: parsed.days || '14',
    };
  }

  match = trimmed.match(/^performance(?:\s+(.+))?$/i);
  if (match) {
    const remainder = (match[1] || '').trim();
    const parsed = remainder
      ? parseDeterministicLogClauses(remainder, { allowText: false, allowEmpty: true })
      : { query: '', filters: [], rawQuery: '' };
    if (parsed.error) return parsed;
    return {
      action: 'performance',
      rawQuery: trimmed,
      sort: parsed.sort || 'success_rate',
      order: parsed.order || 'asc',
      top: parsed.top || null,
      days: parsed.days || '30',
    };
  }

  match = trimmed.match(/^search\s+(.+)$/i);
  if (match) {
    const parsed = parseDeterministicLogClauses(match[1].trim(), { allowText: true, requireText: true });
    if (parsed.error) return parsed;
    return {
      action: 'search',
      rawQuery: trimmed,
      query: parsed.textQuery || parsed.query,
      filters: parsed.filters,
      days: parsed.days,
      startDate: parsed.start,
      endDate: parsed.end,
      limit: parsed.limit,
      mode: parsed.mode || 'summary',
    };
  }

  match = trimmed.match(/^(?:linkage|trace)\s+(.+)$/i);
  if (match) {
    const parsed = parseDeterministicLogClauses(match[1].trim(), { allowText: true, requireText: true });
    if (parsed.error) return parsed;
    return {
      action: 'linkage',
      rawQuery: trimmed,
      query: parsed.textQuery || parsed.query,
      filters: parsed.filters,
      days: parsed.days || '30',
      startDate: parsed.start,
      endDate: parsed.end,
      limit: parsed.limit,
    };
  }

  return null;
}

function describeDeterministicLogFilter(filter) {
  const prompt = `/logs search ${String(filter.fieldName || '').toLowerCase()}:${filter.query}`;
  return `${filter.fieldLabel} contains ${buildInlinePromptLink(prompt, String(filter.query))}`;
}

function buildDeterministicLogsSearchParams(parsed, overrides = {}) {
  const requestedMode = normalizeDeterministicLogMode(overrides.mode || parsed.mode || 'summary');
  const params = {
    query: parsed.query,
    mode: requestedMode,
    limit: String(overrides.limit || parsed.limit || 25),
  };

  if (parsed.days || overrides.days) params.days = String(overrides.days || parsed.days);
  if (parsed.startDate || overrides.startDate) params.startDate = overrides.startDate || parsed.startDate;
  if (parsed.endDate || overrides.endDate) params.endDate = overrides.endDate || parsed.endDate;
  if (Array.isArray(parsed.filters) && parsed.filters.length) {
    params.filters = JSON.stringify(parsed.filters.map((filter) => ({ field: filter.fieldName, value: filter.query })));
  }
  return params;
}

function pushDeterministicLogJobActions(actions, seen, jobName) {
  if (!jobName) return;
  pushUniqueDeterministicAction(actions, seen, `/logs health ${jobName}; days:30`, `Health: ${jobName}`);
  pushUniqueDeterministicAction(actions, seen, `/logs linkage ${jobName}; days:30`, `Linkage: ${jobName}`);
  pushUniqueDeterministicAction(actions, seen, `/deals dossier ${jobName}`, `Dossier: ${jobName}`);
}

function buildDeterministicLogsSummaryActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstJob = Array.isArray(payload?.top_jobs_by_volume) ? payload.top_jobs_by_volume[0]?.job_name : null;
  pushDeterministicLogJobActions(actions, seen, firstJob);
  if ((payload?.total_did_failures || 0) > 0) {
    pushUniqueDeterministicAction(actions, seen, '/logs failures days:30', 'Inspect DID failures');
  }
  pushUniqueDeterministicAction(actions, seen, '/logs performance sort:total_errors; order:desc; top:10; days:30', 'Performance ranking');
  return actions.slice(0, 5);
}

function buildDeterministicLogsHealthActions(payload) {
  const actions = [];
  const seen = new Set();
  pushDeterministicLogJobActions(actions, seen, payload?.job_name);
  pushUniqueDeterministicAction(actions, seen, `/logs search ${payload?.job_name}; mode:errors; days:30`, 'Recent errors');
  return actions.slice(0, 5);
}

function buildDeterministicLogsFailuresActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstFailure = Array.isArray(payload?.failures) ? payload.failures[0] : null;
  const firstKeyword = firstFailure?.import_did;
  if (firstKeyword) {
    pushUniqueDeterministicAction(actions, seen, `/deals keyword:${firstKeyword}`, `Keyword: ${firstKeyword}`);
  }
  const firstJob = Array.isArray(firstFailure?.affected_jobs) ? firstFailure.affected_jobs[0] : null;
  pushDeterministicLogJobActions(actions, seen, firstJob);
  return actions.slice(0, 5);
}

function buildDeterministicLogsDealActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstEvent = Array.isArray(payload?.events) ? payload.events[0] : null;
  pushDeterministicLogJobActions(actions, seen, firstEvent?.job_name);
  if (payload?.query) {
    pushUniqueDeterministicAction(actions, seen, `/logs search ${payload.query}; mode:details; limit:10`, 'Event details');
  }
  const keyword = payload?.resolved_import_did;
  if (keyword) {
    pushUniqueDeterministicAction(actions, seen, `/deals keyword:${keyword}`, `Keyword: ${keyword}`);
  }
  return actions.slice(0, 5);
}

function normalizeDeterministicLogMode(mode) {
  const normalized = String(mode || 'summary').trim().toLowerCase();
  if (normalized === 'detail') return 'details';
  if (normalized === 'email') return 'emails';
  return normalized || 'summary';
}

function extractDeterministicDidClue(event) {
  const eventType = String(event?.event_type || '').toLowerCase();
  if (eventType === 'did_match') {
    const value = String(event?.filename || '').trim();
    return value || null;
  }

  const source = String(event?.error_message || event?.raw_line || '');
  const match = source.match(/Did not find DID mapping for\s+\[(.+?)\]/i);
  return match ? match[1].trim() : null;
}

function buildDeterministicLogEventEvidence(event) {
  const eventType = String(event?.event_type || '').toLowerCase();
  const summary = [];
  const subject = String(event?.subject || '').trim();
  const sender = String(event?.sender || '').trim();
  const mailbox = String(event?.mailbox || '').trim();
  const parser = String(event?.parser || '').trim();
  const filename = String(event?.filename || '').trim();
  const template = String(event?.template || '').trim();
  const did = extractDeterministicDidClue(event);
  const errorMessage = String(event?.error_message || '').trim();
  const rawLine = String(event?.raw_line || '').trim();

  if (subject) summary.push(`Subject: ${subject}`);
  if (sender) summary.push(`Sender: ${sender}`);
  if (mailbox && mailbox.toLowerCase() !== sender.toLowerCase()) summary.push(`Mailbox: ${mailbox}`);

  const fileLabel = eventType === 'did_match' ? 'Matched DID' : eventType === 'template_queue' ? 'Queued File' : 'File';
  if (filename) summary.push(`${fileLabel}: ${filename}`);
  if (template) summary.push(`Scrubber: ${template}`);
  if (parser) summary.push(`Parser: ${parser}`);
  if (did && (!filename || eventType !== 'did_match')) summary.push(`DID: ${did}`);
  if (errorMessage) summary.push(`Error: ${errorMessage}`);

  let rawDetail = rawLine;
  const timestampSplit = rawDetail.split(':\t');
  if (timestampSplit.length > 1) rawDetail = timestampSplit.slice(1).join(':\t').trim();
  if (!rawDetail && !summary.length) rawDetail = 'No additional detail captured.';

  return {
    eventType,
    subject,
    sender,
    mailbox,
    parser,
    filename,
    template,
    did,
    errorMessage,
    rawDetail,
    compact: summary.length ? summary.join(' | ') : rawDetail,
  };
}

function getDeterministicLogRowFields(event) {
  const preferredOrder = [
    'id',
    'timestamp',
    'log_file',
    'log_type',
    'job_name',
    'mailbox',
    'event_type',
    'emails_found',
    'subject',
    'sender',
    'parser',
    'filename',
    'template',
    'error_message',
    'raw_line',
  ];
  const seen = new Set();
  const fields = [];

  for (const key of preferredOrder) {
    if (!Object.prototype.hasOwnProperty.call(event || {}, key)) continue;
    seen.add(key);
    fields.push({ key, value: event[key] });
  }

  const extras = Object.keys(event || {})
    .filter((key) => !seen.has(key))
    .sort((left, right) => left.localeCompare(right));

  for (const key of extras) {
    fields.push({ key, value: event[key] });
  }

  return fields;
}

function renderDeterministicLogEventTable(lines, events, parsed, options = {}) {
  const mode = normalizeDeterministicLogMode(options.mode || parsed?.mode || 'events');
  const limit = Number(options.limit || parsed?.limit || (mode === 'details' ? 10 : 15)) || (mode === 'details' ? 10 : 15);
  const rows = Array.isArray(events) ? events.slice(0, limit) : [];

  if (!rows.length) {
    lines.push('_No event-level rows matched this deterministic search._');
    lines.push('');
    return;
  }

  if (mode === 'details') {
    lines.push('**Detailed Event Evidence**');
    lines.push(`_Showing full captured log columns for up to ${limit} events._`);
    lines.push('');
    rows.forEach((row, index) => {
      const evidence = buildDeterministicLogEventEvidence(row);
      const jobPrompt = row?.job_name ? `/logs health ${row.job_name}; days:${parsed?.days || 30}` : null;
      lines.push(`**${index + 1}. ${escapeMarkdownText(row?.timestamp || '—')} · ${linkOrText(row?.job_name || '—', jobPrompt)} · ${escapeMarkdownText(row?.event_type || '—')}**`);
      for (const field of getDeterministicLogRowFields(row)) {
        const label = field.key.replace(/_/g, ' ');
        const rawValue = field.value;
        const hasValue = rawValue !== undefined && rawValue !== null && String(rawValue) !== '';
        let renderedValue = escapeMarkdownText(hasValue ? String(rawValue) : '—');
        if (field.key === 'job_name' && hasValue) {
          renderedValue = linkOrText(String(rawValue), `/logs health ${rawValue}; days:${parsed?.days || 30}`);
        }
        lines.push(`- ${label}: ${renderedValue}`);
      }
      if (evidence.did) lines.push(`- derived did clue: ${linkOrText(evidence.did, `/deals did:${evidence.did}`)}`);
      lines.push('');
    });
    return;
  }

  lines.push('| Timestamp | JobName | EventType | Evidence |');
  lines.push('|-----------|---------|-----------|----------|');
  for (const row of rows) {
    const evidence = buildDeterministicLogEventEvidence(row);
    lines.push(`| ${escapeMarkdownText(row.timestamp || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed?.days || 30}`)} | ${escapeMarkdownText(row.event_type || '—')} | ${escapeMarkdownText(evidence.compact || '—')} |`);
  }
  lines.push('');
}

function buildDeterministicLogsTrendsActions(payload) {
  const actions = [];
  const seen = new Set();
  pushDeterministicLogJobActions(actions, seen, payload?.job_filter);
  pushUniqueDeterministicAction(actions, seen, '/logs performance sort:success_rate; order:asc; top:10; days:30', 'Performance summary');
  return actions.slice(0, 5);
}

function buildDeterministicLogsPerformanceActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstEntry = Array.isArray(payload?.entries) ? payload.entries[0] : null;
  pushDeterministicLogJobActions(actions, seen, firstEntry?.job_name);
  pushUniqueDeterministicAction(actions, seen, '/logs trends days:14', 'Volume trends');
  return actions.slice(0, 5);
}

function buildDeterministicLogsSearchActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstJob = Array.isArray(payload?.jobs)
    ? payload.jobs[0]?.job_name
    : Array.isArray(payload?.email_events)
      ? payload.email_events[0]?.job_name
      : null;
  pushDeterministicLogJobActions(actions, seen, firstJob);
  if (payload?.query) {
    pushUniqueDeterministicAction(actions, seen, `/logs search ${payload.query}; mode:emails; limit:10`, 'Email groups');
    pushUniqueDeterministicAction(actions, seen, `/logs search ${payload.query}; mode:details; limit:10`, 'Event details');
  }
  pushUniqueDeterministicAction(actions, seen, `/logs linkage ${payload?.query || firstJob || ''}; days:30`, 'Cross-link result');
  return actions.slice(0, 5);
}

function buildDeterministicLogsLinkageActions(payload) {
  const actions = [];
  const seen = new Set();
  const firstJob = Array.isArray(payload?.log_jobs) ? payload.log_jobs[0]?.job_name : null;
  pushDeterministicLogJobActions(actions, seen, firstJob);
  const firstDeal = Array.isArray(payload?.linked_deals) ? payload.linked_deals[0] : null;
  const firstDid = firstDeal?.DID || firstDeal?.did;
  if (firstDid) {
    pushUniqueDeterministicAction(actions, seen, `/deals did:${firstDid}`, `DID: ${firstDid}`);
  }
  const firstStaging = Array.isArray(payload?.recent_staging) ? payload.recent_staging[0] : null;
  if (firstStaging?.TemplateProcessID !== undefined && firstStaging?.TemplateProcessID !== null) {
    pushUniqueDeterministicAction(actions, seen, `/staging detail ${firstStaging.TemplateProcessID}`, `Open staging row: ${firstStaging.TemplateProcessID}`);
  }
  return actions.slice(0, 5);
}

function renderDeterministicLogsSummaryResult(result) {
  const payload = result?.data || {};
  const lines = [
    '### Daily Log Summary',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    '**Summary**',
    `- Date: ${escapeMarkdownText(payload.date || 'today')}`,
    `- Jobs Run: ${payload.total_jobs_run || 0}`,
    `- Emails Processed: ${payload.total_emails_processed || 0}`,
    `- Files Loaded: ${payload.total_files_loaded || 0}`,
    `- Errors: ${payload.total_errors || 0}`,
    `- DID Failures: ${payload.total_did_failures || 0}`,
  ];

  if (payload.comparison?.previous_date) {
    lines.push(`- Previous Day Error Delta: ${payload.comparison.error_change >= 0 ? '+' : ''}${payload.comparison.error_change || 0}`);
  }
  lines.push('');

  if (Array.isArray(payload.top_jobs_by_volume) && payload.top_jobs_by_volume.length) {
    lines.push('**Top Jobs By Volume**');
    lines.push('| JobName | Event Count |');
    lines.push('|---------|-------------|');
    for (const row of payload.top_jobs_by_volume) {
      lines.push(`| ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:30`)} | ${row.event_count || 0} |`);
    }
    lines.push('');
  }

  if (Array.isArray(payload.top_error_sources) && payload.top_error_sources.length) {
    lines.push('**Top Error Sources**');
    lines.push('| JobName | Error Count |');
    lines.push('|---------|-------------|');
    for (const row of payload.top_error_sources) {
      lines.push(`| ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:30`)} | ${row.error_count || 0} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicLogsSummaryActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsHealthResult(result, parsed) {
  const payload = result?.data || {};
  const lines = [
    '### Job Log Health',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- Job: ${linkOrText(payload.job_name || parsed.query, `/logs health ${payload.job_name || parsed.query}; days:${parsed.days || '30'}`)}`,
    `- Date Range: ${escapeMarkdownText(payload.date_range || `Last ${parsed.days || 30} days`)}`,
    `- Total Runs: ${payload.total_runs || 0}`,
    `- Successful Runs: ${payload.successful_runs || 0}`,
    `- Error Count: ${payload.error_count || 0}`,
    `- Success Rate: ${payload.success_rate || 0}%`,
    `- Status: ${escapeMarkdownText(payload.status || 'unknown')}`,
  ];
  if (payload.last_run) lines.push(`- Last Run: ${escapeMarkdownText(payload.last_run)}`);
  if (payload.avg_emails_per_run !== undefined) lines.push(`- Avg Emails Per Run: ${payload.avg_emails_per_run}`);
  if (payload.last_error) lines.push(`- Last Error: ${escapeMarkdownText(payload.last_error)}`);
  lines.push('');

  if (Array.isArray(payload.common_errors) && payload.common_errors.length) {
    lines.push('**Common Errors**');
    lines.push('| Message | Count |');
    lines.push('|---------|-------|');
    for (const row of payload.common_errors) {
      lines.push(`| ${escapeMarkdownText(row.message || '—')} | ${row.count || 0} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicLogsHealthActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsFailuresResult(result, parsed) {
  const payload = result?.data || {};
  const failures = Array.isArray(payload.failures) ? payload.failures : [];
  const lines = [
    '### DID Mapping Failures',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- Period: ${escapeMarkdownText(payload.date_range || `Last ${parsed.days || 30} days`)}`,
    `- Unique Keywords: ${payload.total_unique_dids || failures.length}`,
    `- Total Failures: ${payload.total_failures || 0}`,
    '',
  ];

  if (!failures.length) {
    lines.push('_No DID failures matched this filter window._');
    appendDeterministicNextActions(lines, buildDeterministicLogsFollowUps().map((item) => ({ prompt: `/logs ${item.prompt}`, label: item.label })));
    return lines.join('\n');
  }

  lines.push('| ImportDID | Failure Count | Affected Jobs | Last Seen |');
  lines.push('|-----------|---------------|---------------|-----------|');
  for (const row of failures.slice(0, 15)) {
    const jobs = Array.isArray(row.affected_jobs) ? row.affected_jobs : [];
    lines.push(`| ${linkOrText(row.import_did || '—', `/deals keyword:${row.import_did || ''}`)} | ${row.failure_count || 0} | ${jobs.slice(0, 3).map((job) => linkOrText(job, `/logs health ${job}; days:${parsed.days || 30}`)).join(', ') || '—'} | ${escapeMarkdownText(row.last_seen || '—')} |`);
  }
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicLogsFailuresActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsDealResult(result, parsed) {
  const payload = result?.data || {};
  const events = Array.isArray(payload.events) ? payload.events : [];
  const lines = [
    '### Deal Activity',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- DID / Query: ${linkOrText(payload.did_identifier || parsed.query, `/logs deal ${payload.did_identifier || parsed.query}; days:${parsed.days || 30}`)}`,
    `- Resolved Keyword: ${linkOrText(payload.resolved_import_did || parsed.query, `/deals keyword:${payload.resolved_import_did || parsed.query}`)}`,
    `- Period: ${escapeMarkdownText(payload.date_range || `Last ${parsed.days || 30} days`)}`,
    `- Matching Events: ${payload.total_events || events.length}`,
    '',
  ];

  if (!events.length) {
    lines.push('_No log activity matched this deal clue in the selected window._');
    appendDeterministicNextActions(lines, buildDeterministicLogsDealActions(payload));
    return lines.join('\n');
  }

  lines.push('| Timestamp | JobName | EventType | Detail |');
  lines.push('|-----------|---------|-----------|--------|');
  for (const row of events.slice(0, 15)) {
    lines.push(`| ${escapeMarkdownText(row.timestamp || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed.days || 30}`)} | ${escapeMarkdownText(row.event_type || '—')} | ${escapeMarkdownText(row.detail || '—')} |`);
  }
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicLogsDealActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsTrendsResult(result, parsed) {
  const payload = result?.data || {};
  const days = Array.isArray(payload.days) ? payload.days : [];
  const lines = [
    '### Log Trends',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- Period: ${payload.period_days || parsed.days || 14} days`,
    `- Range: ${escapeMarkdownText(payload.period_start || '—')} to ${escapeMarkdownText(payload.period_end || '—')}`,
    `- Job Filter: ${payload.job_filter ? linkOrText(payload.job_filter, `/logs health ${payload.job_filter}; days:${payload.period_days || parsed.days || 14}`) : 'All jobs'}`,
    `- Avg Files / Day: ${payload.avg_files_per_day || 0}`,
    '',
  ];

  if (days.length) {
    lines.push('| Date | Files | Errors | DID Failures | Job Runs |');
    lines.push('|------|-------|--------|--------------|----------|');
    for (const row of days.slice(0, 14)) {
      lines.push(`| ${escapeMarkdownText(row.date || '—')} | ${row.total_files || 0} | ${row.total_errors || 0} | ${row.did_failures || 0} | ${row.job_runs || 0} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicLogsTrendsActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsPerformanceResult(result, parsed) {
  const payload = result?.data || {};
  const entries = Array.isArray(payload.entries) ? payload.entries : [];
  const lines = [
    '### Log Performance',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- Period: ${payload.period_days || parsed.days || 30} days`,
    `- Sort: ${escapeMarkdownText(payload.sort_key || parsed.sort || 'success_rate')}`,
    `- Total Jobs: ${payload.total_jobs || entries.length}`,
    `- Average Success Rate: ${payload.avg_success_rate || 0}%`,
    '',
  ];

  if (!entries.length) {
    lines.push('_No performance entries matched this window._');
    appendDeterministicNextActions(lines, buildDeterministicLogsPerformanceActions(payload));
    return lines.join('\n');
  }

  lines.push('| JobName | Status | Success Rate | Runs | Errors | Last Run |');
  lines.push('|---------|--------|--------------|------|--------|----------|');
  for (const row of entries.slice(0, Number(parsed.top || 12) || 12)) {
    lines.push(`| ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${payload.period_days || parsed.days || 30}`)} | ${escapeMarkdownText(row.status || '—')} | ${row.success_rate || 0}% | ${row.total_runs || 0} | ${row.total_errors || 0} | ${escapeMarkdownText(row.last_run || '—')} |`);
  }
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicLogsPerformanceActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsSearchResult(result, parsed) {
  const payload = result?.data || {};
  const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
  const events = Array.isArray(payload.events) ? payload.events : [];
  const emailEvents = Array.isArray(payload.email_events) ? payload.email_events : [];
  const mode = normalizeDeterministicLogMode(payload.mode || parsed.mode || 'summary');
  const lines = [
    '### Log Search',
    '',
    '> Deterministic path · Source: SQLite processing log index',
    '',
    `- Query: ${buildInlinePromptLink(`/logs search ${payload.query || parsed.query}`, payload.query || parsed.query)}`,
    `- Mode: ${escapeMarkdownText(mode)}`,
  ];

  if (Array.isArray(parsed.filters) && parsed.filters.length) {
    lines.push(`- Filters: ${parsed.filters.map((filter) => describeDeterministicLogFilter(filter)).join('; ')}`);
  }
  if (parsed.days || parsed.startDate || parsed.endDate) {
    const periodBits = [];
    if (parsed.days) periodBits.push(`days=${parsed.days}`);
    if (parsed.startDate) periodBits.push(`start=${parsed.startDate}`);
    if (parsed.endDate) periodBits.push(`end=${parsed.endDate}`);
    lines.push(`- Time Controls: ${periodBits.join('; ')}`);
  }
  if (payload.summary?.total_events !== undefined) {
    lines.push(`- Matching Events: ${payload.summary.total_events}`);
  }
  if (payload.email_count !== undefined) {
    lines.push(`- Matching Emails: ${payload.email_count}`);
  }
  lines.push('');

  if (mode === 'summary' && jobs.length) {
    lines.push('| JobName | Events | Errors | Files Loaded | Last Seen |');
    lines.push('|---------|--------|--------|--------------|-----------|');
    for (const row of jobs.slice(0, 15)) {
      lines.push(`| ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed.days || 30}`)} | ${row.total_events || 0} | ${row.total_errors || 0} | ${row.total_files_loaded || 0} | ${escapeMarkdownText(row.last_seen || '—')} |`);
    }
    lines.push('');
  } else if (mode === 'emails' && emailEvents.length) {
    lines.push('| First Seen | JobName | Email # | Subject | Sender | Pipeline Rows | Files | Scrubbers |');
    lines.push('|------------|---------|---------|---------|--------|---------------|-------|-----------|');
    for (const row of emailEvents.slice(0, Number(parsed.limit || 10) || 10)) {
      lines.push(`| ${escapeMarkdownText(row.first_seen || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed.days || 30}`)} | ${escapeMarkdownText(row.email_event_index ?? '—')} | ${escapeMarkdownText(row.subject || '—')} | ${escapeMarkdownText(row.sender || '—')} | ${row.pipeline_event_count || 0} | ${escapeMarkdownText(Array.isArray(row.files) && row.files.length ? row.files.join(', ') : '—')} | ${escapeMarkdownText(Array.isArray(row.templates) && row.templates.length ? row.templates.join(', ') : '—')} |`);
    }
    lines.push('');
  } else if (events.length) {
    renderDeterministicLogEventTable(lines, events, parsed, { mode, limit: parsed.limit || 15 });
  } else {
    lines.push('_No log rows matched this deterministic search._');
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicLogsSearchActions(payload));
  return lines.join('\n');
}

function renderDeterministicLogsLinkageResult(result, parsed) {
  const payload = result?.data || {};
  const events = Array.isArray(payload.events) ? payload.events : [];
  const logJobs = Array.isArray(payload.log_jobs) ? payload.log_jobs : [];
  const linkedJobs = Array.isArray(payload.linked_jobs) ? payload.linked_jobs : [];
  const linkedDeals = Array.isArray(payload.linked_deals) ? payload.linked_deals : [];
  const stagingRows = Array.isArray(payload.recent_staging) ? payload.recent_staging : [];
  const jobsSource = payload?.data_source?.jobs || 'xml';
  const splitJobs = splitDeterministicJobsByType(linkedJobs);
  const lines = [
    '### Log Linkage',
    '',
    `> Deterministic path · Source: SQLite logs · Jobs: ${jobsSource === 'sqlite' ? 'SQLite cache' : jobsSource === 'xml' ? 'Settings.xml' : 'Unavailable'}`,
    '',
    '**Summary**',
    `- Query: ${buildInlinePromptLink(`/logs linkage ${payload.query || parsed.query}; days:${parsed.days || 30}`, payload.query || parsed.query)}`,
    `- Matching Events: ${payload.event_count || events.length}`,
    `- Linked Jobs: ${payload.linked_job_count || linkedJobs.length}`,
    `- Linked Deals: ${payload.linked_deal_count || linkedDeals.length}`,
    `- Recent Staging Rows: ${stagingRows.length}`,
    '',
  ];

  if (logJobs.length) {
    lines.push('**Log Jobs**');
    lines.push('| JobName | Events | Errors | Last Seen |');
    lines.push('|---------|--------|--------|-----------|');
    for (const row of logJobs.slice(0, 10)) {
      lines.push(`| ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed.days || 30}`)} | ${row.total_events || 0} | ${row.total_errors || 0} | ${escapeMarkdownText(row.last_seen || '—')} |`);
    }
    lines.push('');
  }

  if (events.length) {
    lines.push('**Event Evidence**');
    lines.push('| Timestamp | JobName | EventType | Detail |');
    lines.push('|-----------|---------|-----------|--------|');
    for (const row of events.slice(0, 10)) {
      const detail = row.error_message || row.raw_line || row.subject || row.filename || '—';
      lines.push(`| ${escapeMarkdownText(row.timestamp || '—')} | ${linkOrText(row.job_name || '—', `/logs health ${row.job_name}; days:${parsed.days || 30}`)} | ${escapeMarkdownText(row.event_type || '—')} | ${escapeMarkdownText(detail)} |`);
    }
    lines.push('');
  }

  if (linkedJobs.length) {
    lines.push('**Linked Jobs**');
    lines.push('');
    lines.push(...renderDeterministicJobSection('Email Jobs', splitJobs.emailJobs, jobsSource));
    lines.push(...renderDeterministicJobSection('SFTP Jobs', splitJobs.sftpJobs, jobsSource));
  }

  if (linkedDeals.length) {
    lines.push('**Linked Deals**');
    lines.push('| DID | ImportDID | CompanyID |');
    lines.push('|-----|-----------|-----------|');
    for (const deal of linkedDeals.slice(0, 12)) {
      const did = deal.DID || deal.did || '—';
      const importDid = deal.ImportDID || deal.import_did || '—';
      const companyId = deal.CompanyID || deal.company_id || '—';
      lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
    }
    lines.push('');
  }

  if (stagingRows.length) {
    lines.push('**Recent Staging Evidence**');
    renderDeterministicStagingRowsTable(stagingRows, lines, { limit: 10 });
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicLogsLinkageActions(payload));
  return lines.join('\n');
}

async function handleDeterministicLogsCommand(request, stream, shared) {
  const parsed = parseDeterministicLogsPrompt(request.prompt);
  if (!parsed) return null;

  if (!isDeterministicExperimentEnabled()) {
    streamTrustedMarkdown(stream, [
      '### /logs',
      '',
      'The deterministic log shortcuts are currently disabled.',
      'Enable `frpAgent.enableDeterministicJobExperiment` to use deterministic `/logs` lookups.',
      '',
      buildDeterministicLogsHelpText(),
    ].join('\n'));
    return { followUps: [] };
  }

  if (parsed.help) {
    streamTrustedMarkdown(stream, buildDeterministicLogsHelpText());
    return { followUps: buildDeterministicLogsFollowUps() };
  }

  if (parsed.error) {
    streamTrustedMarkdown(stream, [
      '### /logs',
      '',
      parsed.error,
      '',
      buildDeterministicLogsHelpText(),
    ].join('\n'));
    return { followUps: buildDeterministicLogsFollowUps() };
  }

  shared.outputChannel.appendLine(`[FRP] Deterministic logs: ${parsed.action} query=${parsed.query || parsed.rawQuery || ''}`);

  try {
    if (parsed.action === 'sync') {
      return handleSyncLogsSlashCommand(stream, shared);
    }

    if (parsed.action === 'summary') {
      const result = await backendCall('log_daily_summary', { date: parsed.date || undefined }, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsSummaryResult(result));
      return { followUps: buildDeterministicLogsSummaryActions(result?.data || {}) };
    }

    if (parsed.action === 'health') {
      const result = await backendCall('log_job_health', { jobName: parsed.query, days: String(parsed.days || '30') }, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsHealthResult(result, parsed));
      return { followUps: buildDeterministicLogsHealthActions(result?.data || {}) };
    }

    if (parsed.action === 'failures') {
      const params = { days: String(parsed.days || '30') };
      if (parsed.jobQuery) params.jobFilter = parsed.jobQuery;
      const result = await backendCall('log_did_failures', params, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsFailuresResult(result, parsed));
      return { followUps: buildDeterministicLogsFailuresActions(result?.data || {}) };
    }

    if (parsed.action === 'deal') {
      const result = await backendCall('log_deal_activity', { did: parsed.query, days: String(parsed.days || '30') }, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsDealResult(result, parsed));
      return { followUps: buildDeterministicLogsDealActions(result?.data || {}) };
    }

    if (parsed.action === 'trends') {
      const params = { days: String(parsed.days || '14') };
      if (parsed.jobQuery) params.job = parsed.jobQuery;
      const result = await backendCall('log_trends', params, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsTrendsResult(result, parsed));
      return { followUps: buildDeterministicLogsTrendsActions(result?.data || {}) };
    }

    if (parsed.action === 'performance') {
      const result = await backendCall('log_performance', {
        sort: parsed.sort || 'success_rate',
        ascending: String((parsed.order || 'asc').toLowerCase() !== 'desc'),
        top: parsed.top || undefined,
        days: String(parsed.days || '30'),
      }, shared, { timeoutMs: 20000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsPerformanceResult(result, parsed));
      return { followUps: buildDeterministicLogsPerformanceActions(result?.data || {}) };
    }

    if (parsed.action === 'search') {
      const result = await backendCall('log_search', buildDeterministicLogsSearchParams(parsed), shared);
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsSearchResult(result, parsed));
      return { followUps: buildDeterministicLogsSearchActions(result?.data || {}) };
    }

    if (parsed.action === 'linkage') {
      const linkageParams = {
        query: parsed.query,
        days: String(parsed.days || '30'),
        limit: String(parsed.limit || 25),
      };
      if (parsed.startDate) linkageParams.startDate = parsed.startDate;
      if (parsed.endDate) linkageParams.endDate = parsed.endDate;
      if (Array.isArray(parsed.filters) && parsed.filters.length) {
        linkageParams.filters = JSON.stringify(parsed.filters.map((filter) => ({ field: filter.fieldName, value: filter.query })));
      }
      const result = await backendCall('log_linkage', linkageParams, shared, { timeoutMs: 20000 });
      if (isDeterministicFailure(result)) throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      streamTrustedMarkdown(stream, renderDeterministicLogsLinkageResult(result, parsed));
      return { followUps: buildDeterministicLogsLinkageActions(result?.data || {}) };
    }

    return null;
  } catch (err) {
    stream.markdown(`❌ **Deterministic /logs failed:** ${err.message}\n`);
    return { followUps: [] };
  }
}

function buildDeterministicStagingFilterPrompt(filter) {
  return `/staging list ${String(filter.fieldName || '').toLowerCase()}:${filter.query}`;
}

function describeDeterministicStagingFilter(filter) {
  const operator = String(filter.fieldName || '').toLowerCase() === 'servicer' ? '=' : 'contains';
  return `${filter.fieldLabel} ${operator} ${buildInlinePromptLink(buildDeterministicStagingFilterPrompt(filter), String(filter.query))}`;
}

function parseDeterministicStagingFieldClause(clause) {
  const separatorMatch = clause.match(/^([a-z_]+)\s*[:=\-]\s*(.+)$/i);
  const tokenMatch = separatorMatch || clause.match(/^([a-z_]+)\s+(.+)$/i);
  if (!tokenMatch) {
    return { kind: 'text', query: clause, rawQuery: clause };
  }

  const normalized = normalizeDeterministicStagingField(tokenMatch[1]);
  if (!normalized) {
    return { kind: 'text', query: clause, rawQuery: clause };
  }

  const value = tokenMatch[2].trim();
  if (!value) {
    return { error: `Filter \`${tokenMatch[1]}\` requires a value.` };
  }

  if (normalized.kind === 'control') {
    return {
      kind: 'control',
      control: normalized.field,
      fieldLabel: normalized.label,
      query: value,
      rawQuery: clause,
    };
  }

  return {
    kind: 'filter',
    fieldName: normalized.field,
    fieldLabel: normalized.label,
    query: value,
    rawQuery: clause,
  };
}

function parseDeterministicStagingClauses(remainder, options = {}) {
  const clauses = splitDeterministicClauses(remainder);
  if (!clauses.length) {
    return { error: 'Provide a query or at least one staging filter.' };
  }

  let textQuery = null;
  const filters = [];
  const seenFilters = new Set();
  let days = null;
  let startDate = null;
  let endDate = null;

  for (const clause of clauses) {
    const parsedClause = parseDeterministicStagingFieldClause(clause);
    if (parsedClause.error) {
      return parsedClause;
    }

    if (parsedClause.kind === 'text') {
      if (!options.allowTextQuery) {
        return { error: 'This deterministic staging action does not accept semicolon text filters.' };
      }
      if (textQuery) {
        return { error: 'Use at most one unfielded search term before semicolon filters.' };
      }
      textQuery = parsedClause.query;
      continue;
    }

    if (parsedClause.kind === 'control') {
      if (parsedClause.control === 'days') {
        const num = Number(parsedClause.query);
        if (!Number.isFinite(num) || num <= 0) {
          return { error: '`days` must be a positive number.' };
        }
        days = String(Math.trunc(num));
      } else if (parsedClause.control === 'start') {
        startDate = parsedClause.query;
      } else if (parsedClause.control === 'end') {
        endDate = parsedClause.query;
      }
      continue;
    }

    if (seenFilters.has(parsedClause.fieldName)) {
      return { error: `Filter \`${parsedClause.fieldLabel}\` can only be supplied once per deterministic staging lookup.` };
    }

    seenFilters.add(parsedClause.fieldName);
    filters.push(parsedClause);
  }

  if (options.requireQuery && !textQuery) {
    return { error: 'This deterministic staging action requires a query value.' };
  }

  if (!textQuery && !filters.length && !options.allowControlOnly) {
    return { error: 'Provide a query or at least one staging filter.' };
  }

  return {
    query: textQuery || (filters[0] ? filters[0].query : ''),
    rawQuery: remainder,
    textQuery,
    filters,
    days,
    startDate,
    endDate,
  };
}

function parseDeterministicStagingPrompt(prompt) {
  const trimmed = prompt.trim();
  if (!trimmed) return { help: true };
  if (isSlashHelpPrompt(trimmed)) return { help: true };

  const match = trimmed.match(/^(list|detail|status|history|source|trace|linkage|audit)(?:\s+(.+))?$/i);
  if (!match) {
    const inferred = parseDeterministicStagingClauses(trimmed, { allowTextQuery: true, allowControlOnly: false });
    if (!inferred.error && !inferred.textQuery && Array.isArray(inferred.filters) && inferred.filters.length) {
      return { action: 'list', inferredAction: true, ...inferred };
    }
    return null;
  }

  const rawAction = match[1].toLowerCase();
  const action = rawAction === 'trace' ? 'source' : rawAction;
  const remainder = (match[2] || '').trim();

  if (action === 'audit') {
    if (!remainder) {
      return { action, scope: 'all', days: '30' };
    }
    const parsed = parseDeterministicStagingClauses(remainder, { allowTextQuery: true, allowControlOnly: true });
    if (parsed.error) return parsed;
    const scope = String(parsed.textQuery || parsed.query || 'all').toLowerCase();
    if (!DETERMINISTIC_STAGING_AUDIT_SCOPES.has(scope)) {
      return { error: '`audit` supports scopes: all, templates, jobs, filepath, process, servicers.' };
    }
    return { action, scope, days: parsed.days || '30' };
  }

  if (!remainder) {
    return { error: `Use \`${action} <value>\` for deterministic /staging.` };
  }

  if (action === 'detail' || action === 'source') {
    return { action, query: remainder, rawQuery: remainder };
  }

  if (action === 'status' || action === 'linkage') {
    const parsed = parseDeterministicStagingClauses(remainder, { allowTextQuery: true, requireQuery: true, allowControlOnly: true });
    if (parsed.error) return parsed;
    if (parsed.filters.length) {
      return { error: `\`${action}\` accepts a query plus optional time controls only.` };
    }
    return { action, ...parsed };
  }

  const parsed = parseDeterministicStagingClauses(remainder, { allowTextQuery: true, allowControlOnly: false });
  if (parsed.error) return parsed;
  return { action, ...parsed };
}

function buildDeterministicStagingSearchParams(parsed, defaults = {}) {
  const params = {
    query: parsed.textQuery || parsed.query || defaults.query || '',
  };

  const filters = Array.isArray(parsed.filters) ? parsed.filters : [];
  if (filters.length) {
    params.filters = JSON.stringify(filters.map((filter) => ({
      field: filter.fieldName,
      value: filter.query,
    })));
  }

  const days = parsed.days || defaults.days;
  if (days) params.days = String(days);
  if (parsed.startDate || defaults.startDate) params.startDate = parsed.startDate || defaults.startDate;
  if (parsed.endDate || defaults.endDate) params.endDate = parsed.endDate || defaults.endDate;
  if (defaults.limit) params.limit = String(defaults.limit);
  return params;
}

function normalizeStagingRecordState(record) {
  const state = String(record?.processing_state || record?.state || '').toLowerCase();
  if (state) return state;
  if (record?.ResultCode === 0) return 'success';
  if (record?.ResultCode === 1) return 'failed';
  return 'unknown';
}

function normalizeStagingRecordSource(record) {
  const source = String(record?.source_type || record?.SourceType || '').toLowerCase();
  if (source) return source;
  const ds = String(record?.DataSource || '').toLowerCase();
  if (ds.includes('sftpmonitor:')) return 'sftp';
  if (ds.includes('queued via macro')) return 'manual';
  return ds ? 'email' : 'unknown';
}

function renderDeterministicStagingRowsTable(rows, lines, options = {}) {
  const limit = options.limit || 15;
  const limitedRows = Array.isArray(rows) ? rows.slice(0, limit) : [];
  if (!limitedRows.length) return;

  lines.push('| ID | Template | DID | ServicerID | State | Source | Dt | Comments | FilePath |');
  lines.push('|----|----------|-----|------------|-------|--------|----|----------|----------|');
  for (const row of limitedRows) {
    const id = row.TemplateProcessID ?? row.template_process_id ?? '—';
    const templateName = row.TemplateName || row.template_name || '—';
    const did = row.DID || row.did || '—';
    const servicerId = row.ServicerID ?? row.servicer_id ?? '—';
    const state = normalizeStagingRecordState(row) || '—';
    const source = normalizeStagingRecordSource(row) || '—';
    const dt = row.Dt || row.dt || '—';
    const comments = row.Comments || row.comments || '—';
    const filePath = row.FilePath || row.file_path || '—';
    lines.push(`| ${linkOrText(id, `/staging detail ${id}`)} | ${linkOrText(templateName, `/staging linkage ${templateName}`)} | ${did === '—' ? '—' : linkOrText(did, `/deals did:${did}`)} | ${servicerId === '—' ? '—' : linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${linkOrText(state, `/staging list result:${state}`)} | ${linkOrText(source, `/staging list source:${source}`)} | ${escapeMarkdownText(dt)} | ${escapeMarkdownText(comments)} | ${filePath === '—' ? '—' : linkOrText(filePath, `/staging source ${filePath}`)} |`);
  }
  if (rows.length > limit) {
    lines.push('');
    lines.push(`- Showing first ${limit} of ${rows.length} rows.`);
  }
}

function buildDeterministicStagingListActions(payload, parsed) {
  const actions = [];
  const seen = new Set();
  const rows = Array.isArray(payload?.results) ? payload.results : [];
  const first = rows[0] || null;
  if (first?.TemplateProcessID !== undefined && first?.TemplateProcessID !== null) {
    pushUniqueDeterministicAction(actions, seen, `/staging detail ${first.TemplateProcessID}`, `Open row: ${first.TemplateProcessID}`);
  }
  if (first?.TemplateName) {
    pushUniqueDeterministicAction(actions, seen, `/staging linkage ${first.TemplateName}`, `Linkage: ${first.TemplateName}`);
    pushUniqueDeterministicAction(actions, seen, `/staging status ${first.TemplateName}`, `Status: ${first.TemplateName}`);
  }
  if (first?.DID) {
    pushUniqueDeterministicAction(actions, seen, `/deals did:${first.DID}`, `DID: ${first.DID}`);
  }
  if (first?.ServicerID !== undefined && first?.ServicerID !== null && first?.ServicerID !== '') {
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${first.ServicerID}`, `Dossier: ${first.ServicerID}`);
  }
  if ((payload?.summary?.by_state || {}).failed > 0) {
    pushUniqueDeterministicAction(actions, seen, '/staging list result:failed; days:30', 'Recent failures');
  }
  if (parsed?.action !== 'audit') {
    pushUniqueDeterministicAction(actions, seen, '/staging audit', 'Audit staging gaps');
  }
  return actions.slice(0, 5);
}

function buildDeterministicStagingDetailActions(detail, linkagePayload) {
  const actions = [];
  const seen = new Set();
  if (detail?.TemplateName) {
    pushUniqueDeterministicAction(actions, seen, `/staging status ${detail.TemplateName}`, `Status: ${detail.TemplateName}`);
    pushUniqueDeterministicAction(actions, seen, `/staging linkage ${detail.TemplateName}`, `Linkage: ${detail.TemplateName}`);
  }
  if (detail?.FilePath) {
    pushUniqueDeterministicAction(actions, seen, `/staging source ${detail.FilePath}`, 'Trace source');
  }
  if (detail?.DID) {
    pushUniqueDeterministicAction(actions, seen, `/deals did:${detail.DID}`, `DID: ${detail.DID}`);
  }
  if (detail?.ServicerID !== undefined && detail?.ServicerID !== null && detail?.ServicerID !== '') {
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${detail.ServicerID}`, `Dossier: ${detail.ServicerID}`);
  }
  const linkedJobs = Array.isArray(linkagePayload?.linked_jobs) ? linkagePayload.linked_jobs : [];
  const jobsSource = linkagePayload?.data_source?.jobs || 'xml';
  const firstJob = linkedJobs[0];
  if (firstJob) {
    const command = deterministicJobCommandForSource(firstJob, jobsSource);
    const jobName = firstJob.job_name || firstJob.name;
    pushUniqueDeterministicAction(actions, seen, `/${command} detail ${jobName}`, `Job detail: ${jobName}`);
  }
  return actions.slice(0, 5);
}

function buildDeterministicStagingLinkageActions(payload) {
  const actions = [];
  const seen = new Set();
  const rows = Array.isArray(payload?.records) ? payload.records : [];
  const linkedJobs = Array.isArray(payload?.linked_jobs) ? payload.linked_jobs : [];
  const linkedDeals = Array.isArray(payload?.linked_deals) ? payload.linked_deals : [];
  const jobsSource = payload?.data_source?.jobs || 'xml';
  const firstRow = rows[0];
  const firstJob = linkedJobs[0];
  const firstDeal = linkedDeals[0];

  if (firstRow?.TemplateProcessID !== undefined && firstRow?.TemplateProcessID !== null) {
    pushUniqueDeterministicAction(actions, seen, `/staging detail ${firstRow.TemplateProcessID}`, `Open row: ${firstRow.TemplateProcessID}`);
  }
  if (firstJob) {
    const command = deterministicJobCommandForSource(firstJob, jobsSource);
    const jobName = firstJob.job_name || firstJob.name;
    pushUniqueDeterministicAction(actions, seen, `/${command} detail ${jobName}`, `Job detail: ${jobName}`);
  }
  if (firstDeal?.DID || firstDeal?.did) {
    const did = firstDeal.DID || firstDeal.did;
    pushUniqueDeterministicAction(actions, seen, `/deals did:${did}`, `DID: ${did}`);
  }
  if (firstDeal?.CompanyID || firstDeal?.company_id) {
    const companyId = firstDeal.CompanyID || firstDeal.company_id;
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${companyId}`, `Dossier: ${companyId}`);
  }
  if (Array.isArray(payload?.missing_templates) && payload.missing_templates.length) {
    pushUniqueDeterministicAction(actions, seen, '/staging audit templates', 'Audit templates');
  }
  return actions.slice(0, 5);
}

function buildDeterministicStagingAuditActions(payload, scope) {
  const actions = [];
  const seen = new Set();
  if (scope !== 'templates') {
    pushUniqueDeterministicAction(actions, seen, '/staging audit templates', 'Template audit');
  }
  if (scope !== 'filepath') {
    pushUniqueDeterministicAction(actions, seen, '/staging audit filepath', 'Filepath audit');
  }
  if (scope !== 'process') {
    pushUniqueDeterministicAction(actions, seen, '/staging audit process', 'Process-level audit');
  }
  const firstTemplate = Array.isArray(payload?.templates_without_jobs) ? payload.templates_without_jobs[0] : null;
  if (firstTemplate?.TemplateName) {
    pushUniqueDeterministicAction(actions, seen, `/staging linkage ${firstTemplate.TemplateName}`, `Inspect: ${firstTemplate.TemplateName}`);
  }
  const firstServicer = Array.isArray(payload?.unmapped_servicers) ? payload.unmapped_servicers[0] : null;
  if (firstServicer?.ServicerID !== undefined && firstServicer?.ServicerID !== null) {
    pushUniqueDeterministicAction(actions, seen, `/deals servicer:${firstServicer.ServicerID}`, `Servicer: ${firstServicer.ServicerID}`);
  }
  return actions.slice(0, 5);
}

function renderDeterministicStagingSearchResult(result, parsed) {
  const payload = result?.data || {};
  const rows = Array.isArray(payload.results) ? payload.results : [];
  const summary = payload.summary || {};
  const title = parsed.action === 'history' ? 'Processing History' : 'Staging Search';
  const lines = [
    `### ${title}`,
    '',
    '> Deterministic path · Source: tblTemplateStaging',
    '',
  ];

  if (!rows.length) {
    lines.push(`_No staging rows matched \`${parsed.rawQuery || parsed.query || payload.query || ''}\`._`);
    lines.push('');
    lines.push('Tip: deterministic `/staging list` and `/staging history` use a 30-day window unless you add `days:`, `start:`, or `end:`.');
    lines.push(`- Try ${buildInlinePromptLink('/staging list did:VCC; days:1500', '/staging list did:VCC; days:1500')} for older matches.`);
    appendDeterministicNextActions(lines, buildDeterministicStagingFollowUps().map((item) => ({ prompt: `/staging ${item.prompt}`, label: item.label })));
    return lines.join('\n');
  }

  lines.push('**Summary**');
  if (payload.query) lines.push(`- Query: ${buildInlinePromptLink(`/staging ${parsed.action} ${payload.query}`, payload.query)}`);
  if (Array.isArray(parsed.filters) && parsed.filters.length) {
    lines.push(`- Filters: ${parsed.filters.map((filter) => describeDeterministicStagingFilter(filter)).join('; ')}`);
  }
  if (parsed.days || parsed.startDate || parsed.endDate) {
    const periodBits = [];
    if (parsed.days) periodBits.push(`days=${parsed.days}`);
    if (parsed.startDate) periodBits.push(`start=${parsed.startDate}`);
    if (parsed.endDate) periodBits.push(`end=${parsed.endDate}`);
    lines.push(`- Time Controls: ${periodBits.join('; ')}`);
  }
  lines.push(`- Matching Rows: ${payload.match_count || rows.length}`);
  lines.push(`- Unique Templates: ${summary.unique_templates || 0}`);
  lines.push(`- Unique DIDs: ${summary.unique_dids || 0}`);
  lines.push(`- Source Mix: ${Object.entries(summary.by_source || {}).map(([key, value]) => `${key}=${value}`).join(', ') || '—'}`);
  lines.push(`- State Mix: ${Object.entries(summary.by_state || {}).map(([key, value]) => `${key}=${value}`).join(', ') || '—'}`);
  lines.push('');

  renderDeterministicStagingRowsTable(rows, lines, { limit: parsed.action === 'history' ? 25 : 15 });
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicStagingListActions(payload, parsed));
  return lines.join('\n');
}

function renderDeterministicStagingStatusResult(result, parsed) {
  const payload = result?.data || {};
  const rows = Array.isArray(payload.runs) ? payload.runs : [];
  const lines = [
    '### Processing Status',
    '',
    '> Deterministic path · Source: tblTemplateStaging',
    '',
    '**Summary**',
    `- Scope: ${buildInlinePromptLink(`/staging status ${payload.scope || parsed.query}`, payload.scope || parsed.query)}`,
    `- Period: ${payload.period_days || parsed.days || '30'} days`,
    `- Total Runs: ${payload.total_runs || 0}`,
    `- Successes: ${payload.successes || 0}`,
    `- Failures: ${payload.failures || 0}`,
    `- Success Rate: ${payload.success_rate || 0}%`,
  ];

  if (!rows.length) {
    lines.push('');
    lines.push('Tip: deterministic `/staging status` defaults to 30 days. If your SQL results are older, add `days:<n>` or a date range.');
    lines.push(`- Example: ${buildInlinePromptLink('/staging status VCC; days:1500', '/staging status VCC; days:1500')}`);
  }

  if (payload.last_success) lines.push(`- Last Success: ${escapeMarkdownText(payload.last_success)}`);
  if (payload.last_failure) lines.push(`- Last Failure: ${escapeMarkdownText(payload.last_failure)}`);
  lines.push('');

  if (rows.length) {
    lines.push('**Recent Runs**');
    renderDeterministicStagingRowsTable(rows.map((row) => ({ ...row, processing_state: normalizeStagingRecordState(row), source_type: normalizeStagingRecordSource(row) })), lines, { limit: 10 });
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicStagingListActions({ results: rows, summary: { by_state: { failed: payload.failures || 0 } } }, parsed));
  return lines.join('\n');
}

function renderDeterministicStagingSourceResult(result, parsed) {
  const payload = result?.data || {};
  const traces = Array.isArray(payload.traces) ? payload.traces : [];
  const lines = [
    '### Source Trace',
    '',
    '> Deterministic path · Source: tblTemplateStaging',
    '',
  ];

  if (!traces.length) {
    lines.push(`_No staged files matched \`${parsed.query}\`._`);
    appendDeterministicNextActions(lines, [{ prompt: '/staging audit filepath', label: 'Audit filepath gaps' }]);
    return lines.join('\n');
  }

  lines.push(`- Matches: ${payload.match_count || traces.length}`);
  lines.push('');
  renderDeterministicStagingRowsTable(traces.map((row) => ({ ...row, processing_state: normalizeStagingRecordState(row), source_type: normalizeStagingRecordSource(row) })), lines, { limit: 15 });
  lines.push('');
  appendDeterministicNextActions(lines, buildDeterministicStagingListActions({ results: traces, summary: {} }, parsed));
  return lines.join('\n');
}

function renderDeterministicStagingLinkageResult(result, parsed) {
  const payload = result?.data || {};
  const rows = Array.isArray(payload.records) ? payload.records : [];
  const linkedJobs = Array.isArray(payload.linked_jobs) ? payload.linked_jobs : [];
  const linkedDeals = Array.isArray(payload.linked_deals) ? payload.linked_deals : [];
  const jobsSource = payload?.data_source?.jobs || 'xml';
  const splitJobs = splitDeterministicJobsByType(linkedJobs);
  const lines = [
    '### Staging Linkage',
    '',
    `> Deterministic path · Source: tblTemplateStaging · Linked Jobs: ${jobsSource === 'sqlite' ? 'SQLite cache' : jobsSource === 'xml' ? 'Settings.xml' : 'Unavailable'}`,
    '',
    '**Summary**',
    `- Query: ${buildInlinePromptLink(`/staging linkage ${payload.query || parsed.query}`, payload.query || parsed.query)}`,
    `- Matching Rows: ${payload.match_count || rows.length}`,
    `- Linked Jobs: ${payload.linked_job_count || linkedJobs.length}`,
    `- Linked Deals: ${payload.linked_deal_count || linkedDeals.length}`,
  ];

  if (Array.isArray(payload.missing_templates) && payload.missing_templates.length) {
    lines.push(`- Missing Templates: ${payload.missing_templates.map((templateName) => buildInlinePromptLink(`/staging linkage ${templateName}`, templateName)).join(', ')}`);
  }
  lines.push('');

  if (rows.length) {
    lines.push('**Staging Rows**');
    renderDeterministicStagingRowsTable(rows, lines, { limit: 12 });
    lines.push('');
  }

  if (linkedJobs.length) {
    lines.push('**Linked Jobs**');
    lines.push('');
    lines.push(...renderDeterministicJobSection('Email Jobs', splitJobs.emailJobs, jobsSource));
    lines.push(...renderDeterministicJobSection('SFTP Jobs', splitJobs.sftpJobs, jobsSource));
  }

  if (linkedDeals.length) {
    lines.push('**Linked Deals**');
    lines.push('| DID | ImportDID | CompanyID |');
    lines.push('|-----|-----------|-----------|');
    for (const deal of linkedDeals.slice(0, 12)) {
      const did = deal.DID || deal.did || '—';
      const importDid = deal.ImportDID || deal.import_did || '—';
      const companyId = deal.CompanyID || deal.company_id || '—';
      lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicStagingLinkageActions(payload));
  return lines.join('\n');
}

function renderDeterministicStagingAuditResult(result, parsed) {
  const payload = result?.data || {};
  const summary = payload.summary || {};
  const scope = parsed.scope || 'all';
  const showSection = (section) => scope === 'all' || scope === section;
  const lines = [
    '### Staging Audit',
    '',
    `> Deterministic path · Source: tblTemplateStaging · Jobs: ${payload.reference_job_source === 'sqlite' ? 'SQLite cache' : payload.reference_job_source === 'xml' ? 'Settings.xml' : 'Unavailable'}`,
    '',
    '**Summary**',
    `- Period: ${payload.period_days || '30'} days`,
    `- Templates without jobs: ${summary.templates_without_jobs || 0}`,
    `- Jobs without recent runs: ${summary.jobs_without_recent_runs || 0}`,
    `- Process-level runs: ${summary.process_level_runs || 0}`,
    `- Filepath gaps: ${summary.filepath_gaps || 0}`,
    `- Unmapped servicers: ${summary.unmapped_servicers || 0}`,
    '',
  ];

  if (showSection('templates') && Array.isArray(payload.templates_without_jobs) && payload.templates_without_jobs.length) {
    lines.push('**Templates Without Configured Jobs**');
    lines.push('| TemplateName | Runs |');
    lines.push('|--------------|------|');
    for (const row of payload.templates_without_jobs.slice(0, 12)) {
      lines.push(`| ${linkOrText(row.TemplateName, `/staging linkage ${row.TemplateName}`)} | ${row.run_count || 0} |`);
    }
    lines.push('');
  }

  if (showSection('jobs') && Array.isArray(payload.jobs_without_recent_runs) && payload.jobs_without_recent_runs.length) {
    lines.push('**Jobs Without Recent Staging Activity**');
    lines.push('| JobName | Type | Scrubber | ServicerID |');
    lines.push('|---------|------|----------|------------|');
    for (const row of payload.jobs_without_recent_runs.slice(0, 12)) {
      const jobName = row.job_name || row.name || '—';
      const xmlType = row.xml_type || 'email';
      const command = xmlType === 'sftp' ? 'jobXMLSftp' : 'jobXMLEmail';
      lines.push(`| ${linkOrText(jobName, `/${command} detail ${jobName}`)} | ${escapeMarkdownText(xmlType)} | ${linkOrText(row.scrubber || '—', `/staging linkage ${row.scrubber || ''}`)} | ${linkOrText(row.servicer_id ?? '—', `/deals servicer:${row.servicer_id}`)} |`);
    }
    lines.push('');
  }

  if (showSection('process') && Array.isArray(payload.recent_process_level_runs) && payload.recent_process_level_runs.length) {
    lines.push('**Recent Process-Level Runs**');
    renderDeterministicStagingRowsTable(payload.recent_process_level_runs, lines, { limit: 12 });
    lines.push('');
  }

  if (showSection('filepath') && Array.isArray(payload.filepath_gaps) && payload.filepath_gaps.length) {
    lines.push('**Filepath / Origin Gaps**');
    lines.push('| ID | Template | Source | FilePath |');
    lines.push('|----|----------|--------|----------|');
    for (const row of payload.filepath_gaps.slice(0, 12)) {
      lines.push(`| ${linkOrText(row.TemplateProcessID, `/staging detail ${row.TemplateProcessID}`)} | ${linkOrText(row.TemplateName, `/staging linkage ${row.TemplateName}`)} | ${linkOrText(row.source_type || '—', `/staging list source:${row.source_type || 'unknown'}`)} | ${linkOrText(row.FilePath || '—', `/staging source ${row.FilePath || ''}`)} |`);
    }
    lines.push('');
  }

  if (showSection('servicers') && Array.isArray(payload.unmapped_servicers) && payload.unmapped_servicers.length) {
    lines.push('**Servicers Without Deal Mappings**');
    lines.push('| ServicerID | Template | Sample FilePath |');
    lines.push('|------------|----------|-----------------|');
    for (const row of payload.unmapped_servicers.slice(0, 12)) {
      lines.push(`| ${linkOrText(row.ServicerID, `/deals servicer:${row.ServicerID}`)} | ${linkOrText(row.TemplateName, `/staging linkage ${row.TemplateName}`)} | ${linkOrText(row.sample_filepath || '—', `/staging source ${row.sample_filepath || ''}`)} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicStagingAuditActions(payload, scope));
  return lines.join('\n');
}

function renderDeterministicStagingDetailResult(searchResult, linkageResult, parsed) {
  const searchPayload = searchResult?.data || {};
  const rows = Array.isArray(searchPayload.results) ? searchPayload.results : [];
  const detail = rows.find((row) => String(row.TemplateProcessID) === String(parsed.query)) || rows[0] || null;
  const linkagePayload = linkageResult?.data || {};
  const lines = [
    '### Staging Detail',
    '',
    '> Deterministic path · Source: tblTemplateStaging',
    '',
  ];

  if (!detail) {
    lines.push(`_No staging row matched \`${parsed.query}\`._`);
    appendDeterministicNextActions(lines, [{ prompt: '/staging audit', label: 'Audit staging gaps' }]);
    return lines.join('\n');
  }

  lines.push(`**TemplateProcessID**: ${linkOrText(detail.TemplateProcessID, `/staging detail ${detail.TemplateProcessID}`)}`);
  lines.push(`- TemplateName: ${linkOrText(detail.TemplateName || '—', `/staging linkage ${detail.TemplateName || ''}`)}`);
  if (detail.DID) lines.push(`- DID: ${linkOrText(detail.DID, `/deals did:${detail.DID}`)}`);
  if (detail.ServicerID !== undefined && detail.ServicerID !== null && detail.ServicerID !== '') lines.push(`- ServicerID: ${linkOrText(detail.ServicerID, `/deals dossier ${detail.ServicerID}`)}`);
  if (detail.Dt) lines.push(`- Dt: ${escapeMarkdownText(detail.Dt)}`);
  if (detail.StartTime) lines.push(`- StartTime: ${escapeMarkdownText(detail.StartTime)}`);
  if (detail.EndTime) lines.push(`- EndTime: ${escapeMarkdownText(detail.EndTime)}`);
  if (detail.processing_state) lines.push(`- State: ${linkOrText(detail.processing_state, `/staging list result:${detail.processing_state}`)}`);
  if (detail.source_type) lines.push(`- Source: ${linkOrText(detail.source_type, `/staging list source:${detail.source_type}`)}`);
  if (detail.Job) lines.push(`- Job: ${escapeMarkdownText(detail.Job)}`);
  if (detail.SourceProcess) lines.push(`- SourceProcess: ${escapeMarkdownText(detail.SourceProcess)}`);
  if (detail.DataSource) lines.push(`- DataSource: ${escapeMarkdownText(detail.DataSource)}`);
  if (detail.FilePath) lines.push(`- FilePath: ${linkOrText(detail.FilePath, `/staging source ${detail.FilePath}`)}`);
  if (detail.Comments) lines.push(`- Comments: ${escapeMarkdownText(detail.Comments)}`);
  lines.push('');

  const linkedJobs = Array.isArray(linkagePayload.linked_jobs) ? linkagePayload.linked_jobs : [];
  if (linkedJobs.length) {
    const jobsSource = linkagePayload?.data_source?.jobs || 'xml';
    const splitJobs = splitDeterministicJobsByType(linkedJobs);
    lines.push('**Linked Jobs**');
    lines.push('');
    lines.push(...renderDeterministicJobSection('Email Jobs', splitJobs.emailJobs, jobsSource));
    lines.push(...renderDeterministicJobSection('SFTP Jobs', splitJobs.sftpJobs, jobsSource));
  }

  const linkedDeals = Array.isArray(linkagePayload.linked_deals) ? linkagePayload.linked_deals : [];
  if (linkedDeals.length) {
    lines.push('**Linked Deals**');
    lines.push('| DID | ImportDID | CompanyID |');
    lines.push('|-----|-----------|-----------|');
    for (const deal of linkedDeals.slice(0, 10)) {
      const did = deal.DID || deal.did || '—';
      const importDid = deal.ImportDID || deal.import_did || '—';
      const companyId = deal.CompanyID || deal.company_id || '—';
      lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
    }
    lines.push('');
  }

  appendDeterministicNextActions(lines, buildDeterministicStagingDetailActions(detail, linkagePayload));
  return lines.join('\n');
}

function parseDeterministicDealsPrompt(prompt) {
  const trimmed = prompt.trim();
  if (!trimmed) return null;

  if (isSlashHelpPrompt(trimmed)) {
    return { help: true };
  }

  const clauses = splitDeterministicClauses(trimmed);
  const filters = [];
  let dossierFilter = null;
  const seenModes = new Set();

  for (const clause of clauses) {
    const match = clause.match(/^([a-z_]+)(?:\s*[:=\-]\s*|\s+)(.+)$/i);
    if (!match) {
      return clauses.length === 1
        ? null
        : { error: 'Each semicolon clause must use `did`, `keyword`, `company`, `servicer`, or `dossier` followed by a value.' };
    }

    const normalized = normalizeDeterministicDealMode(match[1]);
    if (!normalized) {
      return clauses.length === 1
        ? null
        : { error: `Unsupported deterministic /deals filter \`${match[1]}\`.` };
    }

    const value = match[2].trim();
    if (!value) {
      return { error: `The \`${match[1]}\` lookup requires a value.` };
    }

    const canonicalMode = normalized.mode === 'dossier'
      ? 'dossier'
      : canonicalDeterministicDealFilterKey(normalized.mode);
    if (seenModes.has(canonicalMode)) {
      return { error: `Filter \`${normalized.label}\` can only be supplied once per deterministic /deals lookup.` };
    }

    seenModes.add(canonicalMode);
    const filter = {
      lookupType: normalized.mode,
      modeLabel: normalized.label,
      query: value,
      rawQuery: clause,
    };

    if (normalized.mode === 'dossier') {
      dossierFilter = filter;
    } else {
      filters.push(filter);
    }
  }

  if (dossierFilter) {
    if (filters.length) {
      return { error: '`dossier` cannot be combined with other deterministic /deals filters.' };
    }
    return {
      action: 'dossier',
      query: dossierFilter.query,
      modeLabel: dossierFilter.modeLabel,
      rawQuery: trimmed,
      filters: [dossierFilter],
    };
  }

  if (!filters.length) {
    return null;
  }

  return {
    action: 'lookup',
    query: filters.length === 1 ? filters[0].query : trimmed,
    rawQuery: trimmed,
    filters,
    lookupType: filters.length === 1 ? filters[0].lookupType : null,
    modeLabel: filters.length === 1 ? filters[0].modeLabel : 'Combined filters',
  };
}

function splitDeterministicJobsByType(jobs) {
  const emailJobs = [];
  const sftpJobs = [];

  for (const job of jobs) {
    if ((job?.xml_type || '').toLowerCase() === 'sftp' || job?.sftp_path || job?.path) {
      sftpJobs.push(job);
    } else {
      emailJobs.push(job);
    }
  }

  return { emailJobs, sftpJobs };
}

function deterministicJobCommandForSource(job, jobsSource) {
  const prefix = jobsSource === 'sqlite' ? 'jobSQLite' : 'jobXML';
  return (job?.xml_type || '').toLowerCase() === 'sftp' || job?.sftp_path || job?.path
    ? `${prefix}Sftp`
    : `${prefix}Email`;
}

function renderDeterministicJobSection(title, jobs, jobsSource) {
  if (!jobs.length) return [];

  const lines = [
    `**${title}**`,
  ];

  const isSftp = title.toLowerCase().includes('sftp');
  if (isSftp) {
    lines.push('| JobName | Path | DSN | ServicerID | Scrubber | Detail |');
    lines.push('|---------|------|-----|------------|----------|--------|');
    for (const job of jobs) {
      const command = deterministicJobCommandForSource(job, jobsSource);
      const jobName = job.job_name || '—';
      const path = job.sftp_path || job.path || '—';
      const dsn = job.dsn || '—';
      const servicerId = job.servicer_id ?? '—';
      const scrubber = job.scrubber || '—';
      lines.push(`| ${linkOrText(jobName, `/${command} detail ${jobName}`)} | ${linkOrText(path, `/${command} list path:${path}`)} | ${linkOrText(dsn, `/${command} list dsn:${dsn}`)} | ${linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${linkOrText(scrubber, `/${command} list scrubber:${scrubber}`)} | ${buildInlinePromptLink(`/${command} detail ${jobName}`, 'Open detail')} |`);
    }
  } else {
    lines.push('| JobName | Mailbox | Sender | ServicerID | Scrubber | Detail |');
    lines.push('|---------|---------|--------|------------|----------|--------|');
    for (const job of jobs) {
      const command = deterministicJobCommandForSource(job, jobsSource);
      const jobName = job.job_name || '—';
      const mailbox = job.mailbox || '—';
      const sender = job.sender || '—';
      const servicerId = job.servicer_id ?? '—';
      const scrubber = job.scrubber || '—';
      lines.push(`| ${linkOrText(jobName, `/${command} detail ${jobName}`)} | ${linkOrText(mailbox, `/${command} list mailbox:${mailbox}`)} | ${linkOrText(sender, `/${command} list sender:${sender}`)} | ${linkOrText(servicerId, `/deals servicer:${servicerId}`)} | ${linkOrText(scrubber, `/${command} list scrubber:${scrubber}`)} | ${buildInlinePromptLink(`/${command} detail ${jobName}`, 'Open detail')} |`);
    }
  }

  lines.push('');
  return lines;
}

function pushUniqueDeterministicAction(actions, seen, prompt, label) {
  const normalizedPrompt = (prompt || '').trim();
  const normalizedLabel = (label || '').trim();
  if (!normalizedPrompt || !normalizedLabel) return;

  const key = `${normalizedPrompt}::${normalizedLabel}`.toLowerCase();
  if (seen.has(key)) return;

  seen.add(key);
  actions.push({ prompt: normalizedPrompt, label: normalizedLabel });
}

function formatDeterministicActionMarkdown(action) {
  return `- ${buildInlinePromptLink(action.prompt, action.label)}`;
}

function buildDeterministicLookupActions(payload, parsed) {
  const actions = [];
  const seen = new Set();
  const deals = Array.isArray(payload?.deals) ? payload.deals : [];
  const matchingJobs = Array.isArray(payload?.matching_jobs) ? payload.matching_jobs : [];
  const jobsSource = payload?.data_source?.jobs || 'xml';
  const parsedFilters = getDeterministicDealFilters(parsed);
  const companyIds = [...new Set(deals.map((deal) => deal.CompanyID || deal.company_id).filter((value) => value !== undefined && value !== null))];

  for (const job of matchingJobs.slice(0, 3)) {
    const jobName = job?.job_name || job?.name;
    if (!jobName) continue;
    const command = deterministicJobCommandForSource(job, jobsSource);
    const channelLabel = command.toLowerCase().includes('sftp') ? 'SFTP detail' : 'Email detail';
    pushUniqueDeterministicAction(actions, seen, `/${command} detail ${jobName}`, `${channelLabel}: ${jobName}`);
  }

  if (companyIds.length) {
    pushUniqueDeterministicAction(actions, seen, `/deals company ${companyIds[0]}`, `Company: ${companyIds[0]}`);
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${companyIds[0]}`, `Dossier: ${companyIds[0]}`);
  }

  if (parsedFilters.length === 1 && parsedFilters[0].lookupType !== 'did' && parsedFilters[0].query) {
    const query = parsedFilters[0].query;
    pushUniqueDeterministicAction(actions, seen, `/deals did:${query}`, `Try as DID: ${query}`);
  }

  return actions.slice(0, 5);
}

function buildDeterministicDossierActions(payload) {
  const actions = [];
  const seen = new Set();
  const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
  const deals = Array.isArray(payload?.deals) ? payload.deals : [];
  const servicerId = payload?.servicer_id;

  for (const job of jobs.slice(0, 3)) {
    const jobName = job?.name || job?.job_name;
    if (!jobName) continue;
    const isSftp = Boolean(job?.path || job?.sftp_path);
    const command = isSftp ? 'jobXMLSftp' : 'jobXMLEmail';
    pushUniqueDeterministicAction(actions, seen, `/${command} detail ${jobName}`, `${isSftp ? 'SFTP' : 'Email'} detail: ${jobName}`);
  }

  if (servicerId !== undefined && servicerId !== null) {
    pushUniqueDeterministicAction(actions, seen, `/deals servicer:${servicerId}`, `Servicer: ${servicerId}`);
  }

  const firstKeyword = deals.map((deal) => deal.ImportDID || deal.import_did).find(Boolean);
  if (firstKeyword) {
    pushUniqueDeterministicAction(actions, seen, `/deals keyword:${firstKeyword}`, `Keyword: ${firstKeyword}`);
  }

  return actions.slice(0, 5);
}

function appendDeterministicNextActions(lines, actions) {
  if (!actions.length) return;
  lines.push('**Next Actions**');
  for (const action of actions) {
    lines.push(formatDeterministicActionMarkdown(action));
  }
  lines.push('');
}

function toChatResult(commandName, result) {
  return {
    metadata: {
      command: commandName || '',
      followUps: result?.followUps || [],
    },
  };
}

function buildDeterministicJobDetailActions(data) {
  const actions = [];
  const seen = new Set();
  const linkedDeals = Array.isArray(data?.linked_deals) ? data.linked_deals : [];
  const jobName = data?.job_name;
  const servicerId = data?.servicer_id;

  if (jobName) {
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${jobName}`, `Dossier by job: ${jobName}`);
  }

  if (servicerId !== undefined && servicerId !== null && servicerId !== '') {
    pushUniqueDeterministicAction(actions, seen, `/deals dossier ${servicerId}`, `Dossier: ${servicerId}`);
    pushUniqueDeterministicAction(actions, seen, `/deals servicer:${servicerId}`, `Servicer: ${servicerId}`);
  }

  const firstDid = linkedDeals.map((deal) => deal.DID || deal.did).find(Boolean);
  if (firstDid) {
    pushUniqueDeterministicAction(actions, seen, `/deals did:${firstDid}`, `DID: ${firstDid}`);
  }

  const firstKeyword = linkedDeals.map((deal) => deal.ImportDID || deal.import_did).find(Boolean);
  if (firstKeyword) {
    pushUniqueDeterministicAction(actions, seen, `/deals keyword:${firstKeyword}`, `Keyword: ${firstKeyword}`);
  }

  const firstCompany = linkedDeals
    .map((deal) => deal.CompanyID || deal.company_id)
    .find((value) => value !== undefined && value !== null && value !== '');
  if (firstCompany !== undefined) {
    pushUniqueDeterministicAction(actions, seen, `/deals company ${firstCompany}`, `Company: ${firstCompany}`);
  }

  return actions.slice(0, 5);
}

function renderDeterministicDealLookupResult(result, parsed) {
  const payload = result?.data || {};
  const deals = Array.isArray(payload.deals) ? payload.deals : [];
  const matchingJobs = Array.isArray(payload.matching_jobs) ? payload.matching_jobs : [];
  const jobsSource = payload?.data_source?.jobs || 'xml';
  const filters = getDeterministicDealFilters(parsed);
  const companyIds = [...new Set(deals.map((deal) => deal.CompanyID || deal.company_id).filter((value) => value !== undefined && value !== null))];
  const keywords = [...new Set(deals.map((deal) => deal.ImportDID || deal.import_did).filter(Boolean))];
  const splitJobs = splitDeterministicJobsByType(matchingJobs);
  const nextActions = buildDeterministicLookupActions(payload, parsed);

  const lines = [
    '### Deal Lookup',
    '',
    `> Deterministic path · Source: tblExternalDIDRef · Linked Jobs: ${jobsSource === 'sqlite' ? 'SQLite cache' : 'Settings.xml'}`,
    '',
  ];

  if (!deals.length) {
    lines.push(`_No tblExternalDIDRef rows matched \`${parsed.query}\`._`);
    appendDeterministicNextActions(lines, buildDeterministicDealsFollowUps().map((item) => ({ prompt: `/deals ${item.prompt}`, label: item.label })));
    return lines.join('\n');
  }

  lines.push('**Summary**');
  lines.push(`- Filters: ${filters.map((filter) => describeDeterministicDealFilter(filter)).join('; ')}`);
  lines.push(`- Matching DID Rows: ${payload.deal_count || deals.length}`);
  lines.push(`- Unique CompanyIDs: ${companyIds.length ? companyIds.map((id) => buildInlinePromptLink(`/deals company ${id}`, String(id))).join(', ') : '—'}`);
  lines.push(`- Unique Keywords: ${keywords.length}`);
  lines.push(`- Linked Jobs: ${payload.matching_job_count || matchingJobs.length}`);
  lines.push('');
  lines.push('**tblExternalDIDRef Matches**');
  lines.push('| DID | ImportDID | CompanyID |');
  lines.push('|-----|-----------|-----------|');
  for (const deal of deals) {
    const did = deal.DID || deal.did || '—';
    const importDid = deal.ImportDID || deal.import_did || '—';
    const companyId = deal.CompanyID || deal.company_id || '—';
    lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
  }
  lines.push('');

  if (matchingJobs.length) {
    lines.push('**Linked Jobs**');
    lines.push('');
    lines.push(...renderDeterministicJobSection('Email Jobs', splitJobs.emailJobs, jobsSource));
    lines.push(...renderDeterministicJobSection('SFTP Jobs', splitJobs.sftpJobs, jobsSource));
  }

  appendDeterministicNextActions(lines, nextActions);

  return lines.join('\n');
}

function extractDossierJobRows(jobs) {
  const emailJobs = [];
  const sftpJobs = [];

  for (const job of jobs) {
    const template = job?.templates && typeof job.templates === 'object'
      ? (job.templates.Main || Object.values(job.templates).find(Boolean) || '—')
      : '—';

    const common = {
      job_name: job?.name || job?.job_name || '—',
      servicer_id: job?.servicer_id ?? '—',
      scrubber: template,
      save_path: job?.save_location || job?.save_path || '—',
    };

    if (job?.path) {
      sftpJobs.push({
        ...common,
        sftp_path: job.path,
        dsn: job.dsn || '—',
      });
    } else {
      emailJobs.push({
        ...common,
        mailbox: job?.mailbox || '—',
        sender: (job?.filters && job.filters.From) || job?.sender || '—',
      });
    }
  }

  return { emailJobs, sftpJobs };
}

function renderDeterministicDossierResult(result, parsed) {
  const payload = result?.data || {};
  const deals = Array.isArray(payload.deals) ? payload.deals : [];
  const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
  const summary = payload.company_summary || {};
  const splitJobs = extractDossierJobRows(jobs);
  const nextActions = buildDeterministicDossierActions(payload);

  const lines = [
    '### Servicer Dossier',
    '',
    '> Deterministic path · Source: tblExternalDIDRef + Settings.xml',
    '',
    '**Summary**',
    `- Query: ${buildInlinePromptLink(`/deals dossier ${parsed.query}`, parsed.query)}`,
    `- Resolved Servicer ID: ${payload.servicer_id !== undefined && payload.servicer_id !== null ? buildInlinePromptLink(`/deals servicer:${payload.servicer_id}`, String(payload.servicer_id)) : '—'}`,
    `- DID Rows: ${summary.total_rows ?? deals.length}`,
    `- Unique DIDs: ${summary.unique_deals ?? [...new Set(deals.map((deal) => deal.DID || deal.did).filter(Boolean))].length}`,
    `- Unique Keywords: ${summary.unique_keywords ?? [...new Set(deals.map((deal) => deal.ImportDID || deal.import_did).filter(Boolean))].length}`,
    `- Jobs: ${jobs.length}`,
    '',
  ];

  if (deals.length) {
    lines.push('**tblExternalDIDRef Rows**');
    lines.push('| DID | ImportDID | CompanyID |');
    lines.push('|-----|-----------|-----------|');
    for (const deal of deals) {
      const did = deal.DID || deal.did || '—';
      const importDid = deal.ImportDID || deal.import_did || '—';
      const companyId = deal.CompanyID || deal.company_id || '—';
      lines.push(`| ${linkOrText(did, `/deals did:${did}`)} | ${linkOrText(importDid, `/deals keyword:${importDid}`)} | ${linkOrText(companyId, `/deals company ${companyId}`)} |`);
    }
    lines.push('');
  }

  if (jobs.length) {
    lines.push('**Jobs**');
    lines.push('');
    lines.push(...renderDeterministicJobSection('Email Jobs', splitJobs.emailJobs, 'xml'));
    lines.push(...renderDeterministicJobSection('SFTP Jobs', splitJobs.sftpJobs, 'xml'));
  }

  const stagingSummary = payload?.template_staging?.summary || {};
  if (Object.keys(stagingSummary).length > 0) {
    lines.push('**Template Staging**');
    if (stagingSummary.total_runs !== undefined) lines.push(`- Total Runs: ${stagingSummary.total_runs}`);
    if (stagingSummary.success_rate !== undefined) lines.push(`- Success Rate: ${stagingSummary.success_rate}%`);
    lines.push('');
  }

  appendDeterministicNextActions(lines, nextActions);

  return lines.join('\n');
}

async function handleDeterministicDealsCommand(request, stream, shared) {
  const parsed = parseDeterministicDealsPrompt(request.prompt);
  if (!parsed) return null;

  if (!isDeterministicExperimentEnabled()) {
    streamTrustedMarkdown(stream, [
      '### /deals',
      '',
      'The deterministic deal shortcuts are currently disabled.',
      'Enable `frpAgent.enableDeterministicJobExperiment` to use deterministic `/deals` lookups.',
      '',
      buildDeterministicDealsHelpText(),
    ].join('\n'));
    return { followUps: [] };
  }

  if (parsed.help) {
    streamTrustedMarkdown(stream, buildDeterministicDealsHelpText());
    return { followUps: buildDeterministicDealsFollowUps() };
  }

  if (parsed.error) {
    streamTrustedMarkdown(stream, [
      '### /deals',
      '',
      parsed.error,
      '',
      buildDeterministicDealsHelpText(),
    ].join('\n'));
    return { followUps: buildDeterministicDealsFollowUps() };
  }

  const filterLog = getDeterministicDealFilters(parsed)
    .map((filter) => `${filter.lookupType}=${filter.query}`)
    .join('; ');
  shared.outputChannel.appendLine(
    `[FRP] Deterministic deals: ${parsed.action} query=${parsed.rawQuery || parsed.query}${filterLog ? ` filters=${filterLog}` : ''}`
  );

  try {
    if (parsed.action === 'lookup') {
      const lookupFilters = getDeterministicDealFilters(parsed).map((filter) => ({
        type: filter.lookupType,
        value: filter.query,
      }));
      const lookupParams = {
        query: parsed.query,
        xmlType: 'all',
        filtersJson: JSON.stringify(lookupFilters),
      };
      if (parsed.lookupType) {
        lookupParams.lookupType = parsed.lookupType;
      }
      const result = await backendCall('deal_lookup', lookupParams, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicDealLookupResult(result, parsed));
      return { followUps: buildDeterministicLookupActions(result?.data || {}, parsed) };
    }

    const result = await backendCall('servicer_dossier', { query: parsed.query }, shared, { timeoutMs: 20000 });
    if (isDeterministicFailure(result)) {
      throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
    }
    streamTrustedMarkdown(stream, renderDeterministicDossierResult(result, parsed));
    return { followUps: buildDeterministicDossierActions(result?.data || {}) };
  } catch (err) {
    stream.markdown(`❌ **Deterministic /deals failed:** ${err.message}\n`);
    return { followUps: [] };
  }
}

async function handleDeterministicStagingCommand(request, stream, shared) {
  const parsed = parseDeterministicStagingPrompt(request.prompt);
  if (!parsed) return null;

  if (!isDeterministicExperimentEnabled()) {
    streamTrustedMarkdown(stream, [
      '### /staging',
      '',
      'The deterministic staging shortcuts are currently disabled.',
      'Enable `frpAgent.enableDeterministicJobExperiment` to use deterministic `/staging` lookups.',
      '',
      buildDeterministicStagingHelpText(),
    ].join('\n'));
    return { followUps: [] };
  }

  if (parsed.help) {
    streamTrustedMarkdown(stream, buildDeterministicStagingHelpText());
    return { followUps: buildDeterministicStagingFollowUps() };
  }

  if (parsed.error) {
    streamTrustedMarkdown(stream, [
      '### /staging',
      '',
      parsed.error,
      '',
      buildDeterministicStagingHelpText(),
    ].join('\n'));
    return { followUps: buildDeterministicStagingFollowUps() };
  }

  shared.outputChannel.appendLine(
    `[FRP] Deterministic staging: ${parsed.action} query=${parsed.rawQuery || parsed.query || ''}`
  );

  try {
    if (parsed.action === 'list' || parsed.action === 'history') {
      const result = await backendCall(
        'staging_search',
        buildDeterministicStagingSearchParams(parsed, { days: parsed.days || '30', limit: parsed.action === 'history' ? '50' : '25' }),
        shared,
        { timeoutMs: 20000 }
      );
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicStagingSearchResult(result, parsed));
      return { followUps: buildDeterministicStagingListActions(result?.data || {}, parsed) };
    }

    if (parsed.action === 'detail') {
      const searchResult = await backendCall(
        'staging_search',
        { query: parsed.query, limit: '20' },
        shared,
        { timeoutMs: 20000 }
      );
      if (isDeterministicFailure(searchResult)) {
        throw new Error(searchResult?.error || (searchResult?.errors || []).join(', ') || 'Unknown error');
      }

      const detailRows = Array.isArray(searchResult?.data?.results) ? searchResult.data.results : [];
      const detail = detailRows.find((row) => String(row.TemplateProcessID) === String(parsed.query)) || detailRows[0] || null;
      let linkageResult = null;
      if (detail) {
        const linkageQuery = detail.TemplateName || detail.DID || detail.FilePath || parsed.query;
        try {
          linkageResult = await backendCall(
            'staging_linkage',
            { query: linkageQuery, days: '30', limit: '10' },
            shared,
            { timeoutMs: 20000 }
          );
        } catch (err) {
          linkageResult = null;
        }
      }

      streamTrustedMarkdown(stream, renderDeterministicStagingDetailResult(searchResult, linkageResult, parsed));
      return {
        followUps: buildDeterministicStagingDetailActions(
          detail,
          linkageResult?.data || {}
        ),
      };
    }

    if (parsed.action === 'status') {
      const result = await backendCall(
        'template_status',
        { query: parsed.query, days: parsed.days || '30' },
        shared,
        { timeoutMs: 15000 }
      );
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicStagingStatusResult(result, parsed));
      return { followUps: buildDeterministicStagingListActions({ results: result?.data?.runs || [], summary: { by_state: { failed: result?.data?.failures || 0 } } }, parsed) };
    }

    if (parsed.action === 'source') {
      const result = await backendCall('source_trace', { filepath: parsed.query }, shared, { timeoutMs: 15000 });
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicStagingSourceResult(result, parsed));
      return { followUps: buildDeterministicStagingListActions({ results: result?.data?.traces || [], summary: {} }, parsed) };
    }

    if (parsed.action === 'linkage') {
      const result = await backendCall(
        'staging_linkage',
        { query: parsed.query, days: parsed.days || '30', limit: '25' },
        shared,
        { timeoutMs: 20000 }
      );
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicStagingLinkageResult(result, parsed));
      return { followUps: buildDeterministicStagingLinkageActions(result?.data || {}) };
    }

    if (parsed.action === 'audit') {
      const result = await backendCall(
        'staging_audit',
        { days: parsed.days || '30', limit: '100' },
        shared,
        { timeoutMs: 20000 }
      );
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicStagingAuditResult(result, parsed));
      return { followUps: buildDeterministicStagingAuditActions(result?.data || {}, parsed.scope || 'all') };
    }

    return null;
  } catch (err) {
    stream.markdown(`❌ **Deterministic /staging failed:** ${err.message}\n`);
    return { followUps: [] };
  }
}

async function handleDeterministicCommand(commandName, request, stream, shared) {
  if (!isDeterministicExperimentEnabled()) {
    stream.markdown([
      `### /${commandName}`,
      '',
      'The deterministic job experiment is currently disabled.',
      'Enable `frpAgent.enableDeterministicJobExperiment` to use this command.',
    ].join('\n'));
    return { followUps: [] };
  }

  const spec = getDeterministicCommandSpec(commandName);
  const parsed = parseDeterministicPrompt(request.prompt, spec.xmlType);
  if (parsed.help) {
    streamTrustedMarkdown(stream, buildDeterministicHelpText(commandName));
    return { followUps: buildDeterministicHelpFollowUps(spec) };
  }

  if (parsed.error) {
    streamTrustedMarkdown(stream, [
      `### /${commandName}`,
      '',
      parsed.error,
      '',
      buildDeterministicHelpText(commandName),
    ].join('\n'));
    return { followUps: buildDeterministicHelpFollowUps(spec) };
  }

  const logTarget = parsed.action === 'detail' ? `job=${parsed.jobName}` : `query=${parsed.rawQuery || parsed.query}`;
  const filterNote = getDeterministicJobFilters(parsed).length
    ? ` filters=${getDeterministicJobFilters(parsed).map((filter) => `${filter.fieldFilter}=${filter.query}`).join('; ')}`
    : '';
  shared.outputChannel.appendLine(
    `[FRP] Deterministic ${commandName}: ${parsed.action} ${logTarget} source=${spec.sourceLabel} xmlType=${spec.xmlType}${filterNote}`
  );

  try {
    if (parsed.action === 'list') {
      const result = await backendCall('search_jobs', buildDeterministicSearchParams(spec, parsed.query), shared, { timeoutMs: 10000 });
      if (isDeterministicFailure(result)) {
        throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
      }
      streamTrustedMarkdown(stream, renderDeterministicJobsResult(result, spec, parsed, commandName));
      return { followUps: [] };
    }

    const result = await backendCall('job_detail', buildDeterministicDetailParams(spec, parsed.jobName), shared, { timeoutMs: 15000 });
    if (isDeterministicFailure(result)) {
      throw new Error(result?.error || (result?.errors || []).join(', ') || 'Unknown error');
    }

    streamTrustedMarkdown(stream, renderDeterministicDetailResult(result, spec, commandName));
    return { followUps: buildDeterministicJobDetailActions(result?.data || {}) };
  } catch (err) {
    stream.markdown(`❌ **Deterministic ${commandName} failed:** ${err.message}\n`);
    return { followUps: [] };
  }
}

async function handleSyncLogsSlashCommand(stream, shared) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const emailLogFolder = config.get('emailLogFolder', '');
  const sftpLogFolder = config.get('sftpLogFolder', '');
  const retentionMonths = config.get('logRetentionMonths', 3);

  if (!emailLogFolder && !sftpLogFolder) {
    stream.markdown('⚠️ No log folders are configured. Set `frpAgent.emailLogFolder` or `frpAgent.sftpLogFolder`.\n');
    return { followUps: [] };
  }

  stream.progress('Syncing logs...');
  const params = {};
  if (emailLogFolder) params.logFolder = emailLogFolder;
  if (sftpLogFolder) params.sftpLogFolder = sftpLogFolder;
  params.retentionMonths = retentionMonths;

  const result = await backendCall('sync_logs', params, shared);
  if (!result?.success) {
    stream.markdown(`❌ **Log sync failed:** ${result?.error || (result?.errors || []).join(', ') || 'Unknown error'}\n`);
    return { followUps: [] };
  }

  const data = result.data || {};
  stream.markdown([
    '### Log Sync Complete ✓',
    '',
    `- Files processed: ${data.files_processed || 0}`,
    `- Events indexed: ${data.events_indexed || 0}`,
    `- Events purged: ${data.events_purged || 0}`,
  ].join('\n'));

  return {
    followUps: [
      { prompt: 'what happened today', label: 'Daily summary' },
      { prompt: 'show trends', label: 'Log trends' },
    ],
  };
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

/**
 * Build a data-source footer from backend response metadata.
 */
function dataSourceFooter(data) {
  const src = data?.data?.data_source || data?.data_source;
  if (!src) return '';
  if (typeof src === 'string') {
    return src === 'sqlite'
      ? '\n\n---\n*📦 Source: SQLite cache*'
      : '\n\n---\n*📄 Source: Settings.xml*';
  }
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

// ---------------------------------------------------------------------------
// Pipeline tool execution
// ---------------------------------------------------------------------------

/**
 * Execute a tool and return the raw result (for use inside the agentic loop).
 */
async function executePipelineTool(toolName, toolInput, request, stream, token, shared) {
  // Special case: triage_email routes through backendCall('triage_verify')
  if (toolName === 'triage_email') {
    const triagePrompt = buildTriagePrompt(toolInput);
    const msgPath = extractMsgPath(triagePrompt.replace(/^(new|verify|match)\s*/i, ''));
    if (msgPath) {
      return await backendCall('triage_verify', { msgPath }, shared);
    }
    return { success: false, error: 'triage_email requires a .msg file path in the prompt' };
  }

  const entry = TOOL_REGISTRY[toolName];
  if (!entry) {
    return { success: false, error: `Unknown tool: ${toolName}` };
  }

  const command = entry.getCommand ? entry.getCommand(toolInput) : entry.command;
  const params = entry.buildParams(toolInput);
  const result = await backendCall(command, params, shared);

  return result;
}

/**
 * Compile a markdown report from accumulated step results.
 * Used when the agentic loop hits maxSteps without the LLM producing
 * a final text answer.
 */
function compilePipelineReport(stepResults, pipelineDef) {
  const lines = [
    `## ${pipelineDef.displayName || 'Query'} — Partial Report`,
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

    const inputStr = Object.entries(sr.input)
      .map(([k, v]) => `\`${k}\`: ${v}`)
      .join(', ');
    if (inputStr) {
      lines.push(`**Input:** ${inputStr}`);
    }

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
 * Build a ChatResult from pipeline step results.
 */
function buildPipelineResult(stepResults) {
  return {};
}

// ---------------------------------------------------------------------------
// CRUD confirmation handlers
// ---------------------------------------------------------------------------

/**
 * Execute a confirmed edit_job operation.
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
 * Execute a confirmed create_job operation.
 */
async function executeConfirmedCreate({ newName, templateJob, overrides, xmlType }, request, context, stream, token, shared) {
  stream.progress('Creating job...');
  // Flatten overrides into individual CLI flags (the backend expects
  // --servicer-id, --mailbox, etc. — NOT a serialised object)
  const params = { templateJob, name: newName, xmlType: xmlType || 'email' };
  if (overrides && typeof overrides === 'object') {
    for (const [k, v] of Object.entries(overrides)) {
      if (v !== undefined && v !== null && v !== '') {
        const camelKey = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
        params[camelKey] = String(v);
      }
    }
  }
  const data = await backendCall('create_job', params, shared);
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
 * Execute a confirmed rollback operation.
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
 * Resume a confirmed CRUD planning pipeline.
 */
async function executeConfirmedCrudPlan({ planText, messages }, request, context, stream, token, shared) {
  const model = await selectModel(request);
  if (!model) {
    stream.markdown('Unable to select a language model for plan execution.');
    return { followUps: [] };
  }

  const pipelineDef = PIPELINE_DEFINITIONS.crud_planning;
  const scopedTools = FRP_TOOLS.filter(t => pipelineDef.tools.includes(t.name));

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
 * Handle a structured impact analysis request directly.
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
// Destructive tool handler — confirmation flow for edit/create/rollback
// ---------------------------------------------------------------------------

async function handleDestructiveToolCall(toolName, toolInput, request, context, stream, token, shared) {
  switch (toolName) {
    case 'edit_job': {
      if (!toolInput.jobName || !toolInput.field || !toolInput.value) {
        stream.markdown('Missing required parameters: jobName, field, and value are all required.\n');
        return { followUps: [] };
      }
      stream.progress(`Fetching current config for "${toolInput.jobName}"...`);
      const currentData = await backendCall('job_detail', { jobName: toolInput.jobName }, shared);
      if (!currentData || currentData.status === 'error') {
        stream.markdown(`❌ Could not retrieve current config for "${toolInput.jobName}": ${currentData?.error || 'unknown error'}. Edit aborted.\n`);
        return { followUps: [] };
      }
      const currentValue = resolveCurrentFieldValue(currentData, toolInput.field, toolInput.xmlType);
      stream.markdown(renderEditDiff(toolInput.jobName, toolInput.field, currentValue, toolInput.value, toolInput.xmlType));
      shared.pendingOperation = {
        type: 'edit_job',
        params: { jobName: toolInput.jobName, field: toolInput.field, value: toolInput.value, xmlType: toolInput.xmlType || 'email' },
      };
      stream.markdown('\n**Confirm this change?**\n');
      return {
        followUps: [
          { prompt: 'Confirm', label: 'Confirm ✓' },
          { prompt: 'Cancel', label: 'Cancel ✗' },
        ],
      };
    }
    case 'create_job': {
      if (!toolInput.newName || !toolInput.templateJob) {
        stream.markdown('Missing required parameters: newName and templateJob are required.\n');
        return { followUps: [{ prompt: 'show template patterns', label: 'List available templates' }] };
      }
      stream.progress(`Looking up template "${toolInput.templateJob}"...`);
      const preview = await backendCall('search_jobs', { query: toolInput.templateJob }, shared);
      if (!preview?.data?.jobs?.length) {
        stream.markdown(`❌ Template job "${toolInput.templateJob}" not found.\n`);
        return { followUps: [{ prompt: 'show template patterns', label: 'List available templates' }] };
      }
      const templateData = preview.data.jobs[0];
      stream.markdown(`**Template:** ${templateData.name || toolInput.templateJob}\n`);
      stream.markdown(`\n**Proposed:** Create new job \`${toolInput.newName}\` from template \`${toolInput.templateJob}\` (${toolInput.xmlType || 'email'})\n`);
      if (toolInput.overrides && Object.keys(toolInput.overrides).length > 0) {
        stream.markdown(`**Overrides:** ${Object.entries(toolInput.overrides).map(([k, v]) => `${k}=${v}`).join(', ')}\n`);
      }
      shared.pendingOperation = {
        type: 'create_job',
        params: { newName: toolInput.newName, templateJob: toolInput.templateJob, overrides: toolInput.overrides, xmlType: toolInput.xmlType || 'email' },
      };
      shared.outputChannel.appendLine(`[FRP] pendingOperation SET: create_job (newName=${toolInput.newName}, template=${toolInput.templateJob})`);
      stream.markdown('\n**Confirm this creation?**\n');
      return {
        followUps: [
          { prompt: 'Confirm', label: 'Confirm ✓' },
          { prompt: 'Cancel', label: 'Cancel ✗' },
        ],
      };
    }
    case 'rollback': {
      if (!toolInput.backupFile) {
        stream.markdown('Missing required parameter: backupFile. Use `rollback <filename>`.\n');
        return { followUps: [{ prompt: 'list backups', label: 'List available backups' }] };
      }
      stream.progress('Loading diff for review...');
      const diffData = await backendCall('xml_diff', { backupFile: toolInput.backupFile }, shared);
      if (diffData?.data) {
        const llmPrompt = [
          SYSTEM_PROMPT, '',
          '<data>', JSON.stringify(diffData, null, 2), '</data>', '',
          `Preview of changes if we rollback to "${toolInput.backupFile}":`,
          'Show what would change. This is for the user to review before confirming.',
        ].join('\n');
        await generateOrFallback(llmPrompt, diffData, 'deploy', request, stream, token);
      }
      shared.pendingOperation = {
        type: 'rollback',
        params: { backupFile: toolInput.backupFile },
      };
      stream.markdown('\n**Confirm this rollback?**\n');
      return {
        followUps: [
          { prompt: 'Confirm', label: 'Confirm ✓' },
          { prompt: 'Cancel', label: 'Cancel ✗' },
        ],
      };
    }
    default:
      stream.markdown(`⚠️ Unknown destructive operation: ${toolName}\n`);
      return { followUps: [] };
  }
}

// ---------------------------------------------------------------------------
// The Unified Agentic Loop — Phase 10
//
// ALL queries (freeform + slash commands) converge here. The LLM sees the
// full tool set, picks tools, observes results, and produces a final answer.
// No classifiers, no category routing, no handler functions.
// ---------------------------------------------------------------------------

/**
 * @param {string}  prompt   The user's question
 * @param {Object}  options  { playbook?, tools?, maxSteps?, pipelineName? }
 * @param {Object}  request  VS Code ChatRequest
 * @param {Object}  context  VS Code ChatContext
 * @param {Object}  stream   VS Code ChatResponseStream
 * @param {Object}  token    CancellationToken
 * @param {Object}  shared   Shared extension context
 */
async function agentLoop(prompt, options, request, context, stream, token, shared) {
  const {
    playbook = null,
    tools = null,
    maxSteps = 8,
    pipelineName = null,
  } = options;

  const model = await selectModel(request);
  if (!model) {
    stream.markdown('⚠️ No language model available. Please ensure GitHub Copilot is active.\n');
    return { followUps: [] };
  }

  // Build scoped tool set
  const scopedTools = tools
    ? FRP_TOOLS.filter(t => tools.includes(t.name))
    : FRP_TOOLS;

  // Build system content
  const systemParts = [SYSTEM_PROMPT, '', DOMAIN_KNOWLEDGE];
  if (playbook) {
    systemParts.push('', '---', '', playbook);
  } else {
    systemParts.push('', '---', '', ROUTING_GUIDANCE);
  }
  const systemContent = systemParts.join('\n');

  const messages = buildMessageHistory(context, systemContent, prompt);
  const stepResults = [];
  let step = 0;

  shared.outputChannel.appendLine(
    `[FRP] agentLoop: starting (${pipelineName || 'freeform'}, max ${maxSteps} steps, ${scopedTools.length} tools)`
  );

  // ── Main agentic loop ──
  while (step < maxSteps) {
    step++;

    let response;
    try {
      response = await model.sendRequest(messages, { tools: scopedTools }, token);
    } catch (err) {
      shared.outputChannel.appendLine(`[FRP] agentLoop: LLM error at step ${step}: ${err.message}`);
      break;
    }

    let toolCallMade = false;
    let finalText = '';
    let reasoningText = '';

    for await (const part of response.stream) {
      const toolCall = _extractToolCall(part);
      if (toolCall) {
        // Log reasoning to output channel only — do not show to user
        if (reasoningText.trim()) {
          shared.outputChannel.appendLine(
            `[FRP] agentLoop step ${step} reasoning: ${reasoningText.trim().slice(0, 200)}`
          );
          reasoningText = '';
        }

        toolCallMade = true;
        const toolName = toolCall.name;
        const toolInput = toolCall.input || {};

        shared.outputChannel.appendLine(
          `[FRP] agentLoop step ${step}: ${toolName}(${JSON.stringify(toolInput)})`
        );
        stream.progress(`Step ${step}: calling ${toolName}...`);

        // Check for destructive operations — pause for confirmation
        const registryEntry = TOOL_REGISTRY[toolName];
        if (registryEntry && registryEntry.destructive) {
          shared.outputChannel.appendLine(`[FRP] agentLoop: destructive tool ${toolName} — pausing for confirmation`);
          return handleDestructiveToolCall(toolName, toolInput, request, context, stream, token, shared);
        }

        // Execute the tool
        let result;
        try {
          result = await executePipelineTool(toolName, toolInput, request, stream, token, shared);
        } catch (err) {
          result = { success: false, error: err.message };
          shared.outputChannel.appendLine(
            `[FRP] agentLoop step ${step}: tool error: ${err.message}`
          );
        }

        stepResults.push({ step, tool: toolName, input: toolInput, result });

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
        const text = typeof part === 'string' ? part : (part.value || '');
        if (toolCallMade) {
          reasoningText += text;
        } else {
          finalText += text;
          reasoningText += text;
        }
      }
    }

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
  }

  // Hit maxSteps without a final text response
  shared.outputChannel.appendLine(`[FRP] agentLoop: hit max steps (${maxSteps})`);
  stream.markdown(compilePipelineReport(stepResults, { displayName: pipelineName || 'Query', maxSteps }));
  return buildPipelineResult(stepResults);
}

// ---------------------------------------------------------------------------
// Slash command handlers — thin dispatchers that enrich the prompt and call
// agentLoop with optional playbook/tool scoping.
// ---------------------------------------------------------------------------

const SLASH_HELP = {
  sync_logs: [
    '### /sync_logs — Explicit Log Sync\n',
    'Runs a manual log synchronization on demand.\n',
    'Automatic log sync is disabled for all commands, so use this when you want to refresh the log index explicitly.',
  ].join('\n'),
  'rebuild-db': [
    '### /rebuild-db — Rebuild SQLite Cache\n',
    'Rebuilds the SQLite job-config cache from both the email and SFTP `Settings.xml` files.\n',
    'This is required after manually editing either XML file outside of the FRP Agent, or when\n',
    '`next_servicer_id` / `search_jobs` results appear stale.\n',
    '> **Tip:** After `create_job` or `edit_job` the cache is rebuilt automatically.',
  ].join('\n'),
  jobs: [
    '### /jobs — Job Management\n',
    'Ask anything about email/SFTP monitoring jobs:\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `list all email jobs` | Browse all jobs |',
    '| `tell me about CMBS_GreyCo` | Full job detail + linked deals |',
    '| `validate` | Lint all job configurations |',
    '| `show template patterns` | Scrubber inventory |',
    '| `create "NewJob" from "CMBS_GreyCo"` | Create job from template |',
    '| `edit CMBS_GreyCo set scrubber Outlook_Queuer_x` | Edit a field |',
  ].join('\n'),
  jobXML: [
    '### /jobXML — Deterministic XML Email Alias\n',
    'Legacy deterministic email alias using Settings.xml directly.\n',
    'Use `list <query>` or `detail <jobName>`. Prefer `/jobXMLEmail` for clarity.',
  ].join('\n'),
  jobSQLite: [
    '### /jobSQLite — Deterministic SQLite Email Alias\n',
    'Legacy deterministic email alias using the SQLite cache directly.\n',
    'Use `list <query>` or `detail <jobName>`. Prefer `/jobSQLiteEmail` for clarity.',
  ].join('\n'),
  deals: [
    '### /deals — Deal Intelligence\n',
    'Query deal mappings, coverage, and servicer data. Deterministic shortcuts are also available:\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `did:FREMF 2026-KF169` | Deterministic DID lookup |',
    '| `keyword:FREMF` | Deterministic ImportDID keyword lookup |',
    '| `company 296` | Deterministic CompanyID lookup |',
    '| `servicer:296` | Deterministic servicer lookup |',
    '| `dossier 296` | Deterministic servicer dossier |',
    '| `lookup CMLTI 2014-A` | Reverse lookup: deal → jobs |',
    '| `coverage gaps` | Find missing DID mappings |',
    '| `detect orphaned jobs` | Jobs with no deal mapping |',
    '| `detect collisions` | ImportDID conflicts |',
    '| `servicer dossier 296` | Full servicer report |',
  ].join('\n'),
  logs: [
    '### /logs — Log Analytics\n',
    'Query application logs and processing metrics:\n',
    'Log queries do not auto-refresh the index. Use `/sync_logs` or `/logs sync` when you need fresh log data.\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `what happened today` | Daily summary |',
    '| `sync logs` | Sync/index log files |',
    '| `show DID failures` | DID match failures |',
    '| `health CMBS_GreyCo` | Job health metrics |',
    '| `show trends` | Volume trends |',
    '| `job performance` | Performance rankings |',
  ].join('\n'),
  deploy: [
    '### /deploy — Deployment Management\n',
    'Manage Settings.xml deployment, backups, and rollback:\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `save email settings` | Deploy email Settings.xml |',
    '| `save sftp settings` | Deploy SFTP Settings.xml |',
    '| `list backups` | Show backup/restore points |',
    '| `diff` | Show changes since last backup |',
    '| `rollback Settings_20260201.xml` | Restore from backup |',
  ].join('\n'),
  clone: [
    '### /clone — Deterministic Job Clone\n',
    'Clone a job by unique `ServicerID` with no agentic planning.\n',
    '| Step | What happens |',
    '|------|---------------|',
    '| `/clone servicerID:150` | Resolve the source job deterministically |',
    '| Auto-pick new ServicerID | First unused upward from the source across configured XML files |',
    '| Per-field chat edit | Every source leaf tag is offered in source order, plus JobName |',
    '| Preview | Show the exact cloned XML block before writing |',
    '| Confirm | Save through the normal XML writer, which creates a backup first |',
    '',
    'While the draft is active, reply with a new value, `keep`, `clear`, `back`, or `cancel`. At preview time, reply with `Confirm` to write the clone.',
  ].join('\n'),
  triage: [
    '### /triage — Email Triage Pipeline\n',
    'Analyze an incoming email through the full FRP processing pipeline.\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `verify C:\\path\\to\\email.msg` | Parse and trace a .msg file |',
    '| `noreply@bank.com sent email about CMBS` | Trace from metadata |',
    '',
    'The triage pipeline checks: job match → deal mapping → keyword match → log verification → template staging.',
  ].join('\n'),
  analyze: [
    '### /analyze — Advanced Analysis\n',
    'Run advanced analytical queries across jobs, deals, and logs.\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `consolidation` | Find merge opportunities |',
    '| `impact delete job "Ocwen"` | Simulate a configuration change |',
    '| `health` | Full system health check |',
  ].join('\n'),
  staging: [
    '### /staging — tblTemplateStaging\n',
    'Query the processing execution history table directly.\n',
    '| Example | What it does |',
    '|---------|-------------|',
    '| `status TPMT_SPS` | Check template processing status |',
    '| `history FREMF 2026-KF169` | Processing history for a deal |',
    '| `failures` | Failure analysis |',
    '| `manual` | Manual vs automated breakdown |',
    '| `duration` | Processing time analysis |',
    '| `pipeline CSMC` | End-to-end pipeline view |',
    '| `search QueueCMBS_Scrubber_x` | Direct staging search |',
  ].join('\n'),
};

const SLASH_FOLLOWUPS = {
  sync_logs: [],
  'rebuild-db': [],
  jobs: [
    { prompt: 'list all email jobs', label: 'Browse jobs' },
    { prompt: 'validate all jobs', label: 'Validate' },
    { prompt: 'show template patterns', label: 'Templates' },
  ],
  jobXML: [],
  jobSQLite: [],
  deals: [
    { prompt: 'did:FREMF 2026-KF169', label: 'Lookup DID' },
    { prompt: 'servicer:296', label: 'Lookup servicer' },
    { prompt: 'dossier 296', label: 'Servicer dossier' },
    { prompt: 'coverage gaps', label: 'Coverage gaps' },
    { prompt: 'detect orphaned jobs', label: 'Orphan check' },
  ],
  logs: [
    { prompt: 'what happened today', label: 'Daily summary' },
    { prompt: 'sync logs', label: 'Sync logs' },
  ],
  deploy: [
    { prompt: 'list backups', label: 'List backups' },
    { prompt: 'what changed since last deploy', label: 'View diff' },
  ],
  clone: [],
  triage: [
    { prompt: 'list all email jobs', label: 'Browse jobs' },
  ],
  analyze: [
    { prompt: 'system health report', label: 'Health check' },
    { prompt: 'consolidation analysis', label: 'Consolidation' },
    { prompt: 'simulate impact', label: 'Impact simulation' },
  ],
  staging: [
    { prompt: 'failure analysis', label: 'Show failures' },
    { prompt: 'manual queue report', label: 'Manual queue' },
  ],
};

/**
 * /rebuild-db — rebuild the SQLite job-config cache from both XML files.
 * Takes no arguments; fires immediately and reports the result.
 */
async function handleRebuildDbCommand(request, context, stream, token, shared) {
  stream.progress('Rebuilding SQLite cache from Settings.xml…');

  let emailResult, sftpResult;

  try {
    emailResult = await backendCall('rebuild_db', { xmlType: 'email' }, shared);
  } catch (err) {
    stream.markdown(`❌ **Email cache rebuild failed:** ${err.message}\n`);
    return { followUps: [] };
  }

  try {
    sftpResult = await backendCall('rebuild_db', { xmlType: 'sftp' }, shared);
  } catch (err) {
    // Non-fatal — SFTP Settings.xml may not be configured
    sftpResult = null;
    shared.outputChannel.appendLine(`[FRP] rebuild-db: SFTP rebuild skipped — ${err.message}`);
  }

  const emailCount = emailResult?.data?.rebuilt?.email_jobs ?? '?';
  const sftpCount  = sftpResult?.data?.rebuilt?.sftp_jobs  ?? (sftpResult ? '?' : 'skipped');

  stream.markdown([
    '### SQLite Cache Rebuilt ✓\n',
    `| Source | Jobs loaded |`,
    `|--------|-------------|`,
    `| Email \`Settings.xml\` | **${emailCount}** |`,
    `| SFTP \`Settings.xml\`  | **${sftpCount}** |`,
    '',
    '_The cache is now up to date. `search_jobs` and `next_servicer_id` will reflect the latest XML._',
  ].join('\n'));

  return {
    followUps: [
      { prompt: 'list all email jobs', label: 'Browse jobs' },
      { prompt: 'validate all jobs',   label: 'Validate' },
    ],
  };
}

function parseCloneSourceServicerId(prompt) {
  const text = String(prompt || '').trim();
  const keyedMatch = text.match(/(?:^|\s)(?:servicerid|servicer|sid)\s*[:=]\s*(\d+)\b/i);
  if (keyedMatch) return Number(keyedMatch[1]);
  const bareMatch = text.match(/^(\d+)$/);
  if (bareMatch) return Number(bareMatch[1]);
  return null;
}

function normalizeCloneFieldValue(value) {
  return value === undefined || value === null ? '' : String(value);
}

function formatCloneFieldValue(value) {
  const normalized = normalizeCloneFieldValue(value);
  return normalized ? escapeMarkdownText(normalized) : '_(blank)_';
}

function isValidCloneJobName(value) {
  return /^[A-Za-z_][A-Za-z0-9_.-]*$/.test(String(value || ''));
}

function getCloneFieldEffectiveValue(field) {
  if (field.draftValue !== undefined) {
    return normalizeCloneFieldValue(field.draftValue);
  }
  if (field.path === '@job_name') {
    return normalizeCloneFieldValue(field.suggestedValue || field.currentValue);
  }
  return normalizeCloneFieldValue(field.currentValue);
}

function getCloneDraftJobName(session) {
  const jobField = session?.fields?.[0];
  return jobField ? getCloneFieldEffectiveValue(jobField).trim() : '';
}

function buildCloneDraftOverrides(session) {
  const overrides = {};
  for (const field of session.fields || []) {
    if (!field || field.path === '@job_name') continue;
    const currentValue = normalizeCloneFieldValue(field.currentValue);
    const nextValue = getCloneFieldEffectiveValue(field);
    if (nextValue !== currentValue) {
      overrides[field.path] = nextValue;
    }
  }
  return overrides;
}

function buildCloneBackendParams(session) {
  const params = {
    sourceServicerId: session.sourceServicerId,
    cloneJobName: getCloneDraftJobName(session),
    assignedServicerId: session.assignedServicerId,
  };
  const overrides = buildCloneDraftOverrides(session);
  if (Object.keys(overrides).length > 0) {
    params.overridesJson = JSON.stringify(overrides);
  }
  return params;
}

function parseCloneFieldReply(prompt) {
  const text = String(prompt || '').trim();
  if (!text) return { action: 'invalid' };

  const lowered = text.toLowerCase();
  if (/^(cancel|stop|abort|nevermind|quit|exit|nope|don.?t)$/.test(lowered)) {
    return { action: 'cancel' };
  }
  if (/^(back|previous|prev|go back)$/.test(lowered)) {
    return { action: 'back' };
  }
  if (/^(keep|same|skip|default|use current|use suggested)$/.test(lowered)) {
    return { action: 'keep' };
  }
  if (/^(clear|blank|empty|remove)$/.test(lowered)) {
    return { action: 'clear' };
  }
  return { action: 'value', value: text };
}

function isCloneConfirmReply(prompt) {
  return /^(yes|y|confirm|confirmed|apply|ok|proceed|do\s+it|sure|go ahead|create|clone|execute)$/.test(
    String(prompt || '').trim().toLowerCase()
  );
}

function buildCloneFieldFollowUps(session) {
  const field = session?.fields?.[session.index];
  if (!field) return [];

  const keepValue = field.path === '@job_name'
    ? normalizeCloneFieldValue(field.suggestedValue || field.currentValue)
    : normalizeCloneFieldValue(field.currentValue);

  const followUps = [
    { prompt: 'keep', label: keepValue ? 'Keep value' : 'Keep blank' },
    { prompt: 'clear', label: 'Clear' },
  ];

  if (session.index > 0) {
    followUps.push({ prompt: 'back', label: 'Back' });
  }
  followUps.push({ prompt: 'cancel', label: 'Cancel' });
  return followUps;
}

function buildCloneConfirmFollowUps() {
  return [
    { prompt: 'Confirm', label: 'Confirm ✓' },
    { prompt: 'back', label: 'Back' },
    { prompt: 'cancel', label: 'Cancel ✗' },
  ];
}

function renderCloneFieldPrompt(session) {
  const field = session?.fields?.[session.index];
  if (!field) {
    return 'Clone session is missing field metadata. Start again with `/clone servicerID:<id>`.\n';
  }

  const lines = [
    '### /clone draft',
    '',
    `Source job: **${escapeMarkdownText(session.sourceJobName)}** (${escapeMarkdownText(session.sourceXmlType)})`,
    `Assigned ServicerID: **${escapeMarkdownText(session.assignedServicerId)}**`,
    '',
    `Field ${session.index + 1} of ${session.fields.length}: **${escapeMarkdownText(field.path === '@job_name' ? 'JobName' : field.path)}**`,
    `Current value: ${formatCloneFieldValue(field.currentValue)}`,
  ];

  if (field.path === '@job_name') {
    lines.push(`Suggested value: ${formatCloneFieldValue(field.suggestedValue)}`);
    lines.push('Reply with a new job name, `keep` to accept the suggestion, `back`, or `cancel`.');
  } else {
    lines.push('Reply with a new value, `keep`, `clear`, `back`, or `cancel`.');
  }

  return lines.join('\n') + '\n';
}

function renderClonePreview(previewData) {
  const lines = [
    '### Clone Preview',
    '',
    `Source job: **${escapeMarkdownText(previewData.source_job_name || '—')}**`,
    `Cloned job: **${escapeMarkdownText(previewData.job_name || '—')}**`,
    `XML type: **${escapeMarkdownText(previewData.xml_type || 'email')}**`,
    `Assigned ServicerID: **${escapeMarkdownText(previewData.assigned_servicer_id || '—')}**`,
    '',
    '**Changes**',
  ];

  const changes = Array.isArray(previewData.changes) ? previewData.changes : [];
  if (changes.length === 0) {
    lines.push('- No field values changed beyond the cloned copy.');
  } else {
    for (const change of changes) {
      lines.push(`- **${escapeMarkdownText(change.field || 'field')}**: ${formatCloneFieldValue(change.old_value)} -> ${formatCloneFieldValue(change.new_value)}`);
    }
  }

  lines.push('');
  lines.push('```xml');
  lines.push(previewData.preview_xml || '');
  lines.push('```');
  lines.push('');
  lines.push('Reply with `Confirm` to write the clone, `back` to revise the last field, or `cancel` to stop.');
  return lines.join('\n') + '\n';
}

function renderCloneApplyResult(result) {
  const validation = result.validation || {};
  const errors = Array.isArray(validation.errors) ? validation.errors : [];
  const warnings = Array.isArray(validation.warnings) ? validation.warnings : [];

  const lines = [
    '### Clone Applied ✓',
    '',
    `Created **${escapeMarkdownText(result.job_name || '—')}** from **${escapeMarkdownText(result.source_job_name || '—')}**.`,
    `XML type: **${escapeMarkdownText(result.xml_type || 'email')}**`,
    `Assigned ServicerID: **${escapeMarkdownText(result.assigned_servicer_id || '—')}**`,
    `Backup file: ${formatCloneFieldValue(result.backup_file)}`,
    `Validation: **${validation.valid === false ? 'invalid' : 'valid'}** (${errors.length} error(s), ${warnings.length} warning(s))`,
  ];

  if (errors.length > 0) {
    lines.push('');
    lines.push('**Validation errors**');
    for (const error of errors.slice(0, 5)) {
      lines.push(`- ${escapeMarkdownText(error)}`);
    }
  }
  if (warnings.length > 0) {
    lines.push('');
    lines.push('**Validation warnings**');
    for (const warning of warnings.slice(0, 5)) {
      lines.push(`- ${escapeMarkdownText(warning)}`);
    }
  }

  return lines.join('\n') + '\n';
}

async function handleCloneCommand(request, stream, shared) {
  const sourceServicerId = parseCloneSourceServicerId(request.prompt);
  if (!Number.isInteger(sourceServicerId)) {
    stream.markdown('Use `/clone servicerID:<id>` to start a deterministic clone. Example: `/clone servicerID:150`.\n');
    return { followUps: [] };
  }

  stream.progress(`Loading source job for ServicerID ${sourceServicerId}...`);
  const data = await backendCall('clone_prepare', { sourceServicerId }, shared, { timeoutMs: 60000 });
  if (data?.status === 'error' || data?.success === false) {
    stream.markdown(`❌ **Clone start failed:** ${data.error || (data.errors || []).join(', ') || 'Unknown error'}\n`);
    return { followUps: [] };
  }

  shared.cloneSession = {
    phase: 'editing',
    sourceServicerId,
    sourceJobName: data.data?.source_job_name || String(sourceServicerId),
    sourceXmlType: data.data?.source_xml_type || 'email',
    assignedServicerId: String(data.data?.assigned_servicer_id || ''),
    fields: (data.data?.editable_fields || []).map((field) => ({
      path: field.path,
      label: field.label,
      currentValue: normalizeCloneFieldValue(field.current_value),
      suggestedValue: normalizeCloneFieldValue(field.suggested_value),
    })),
    index: 0,
    previewData: null,
  };

  stream.markdown(renderCloneFieldPrompt(shared.cloneSession));
  return { followUps: buildCloneFieldFollowUps(shared.cloneSession) };
}

async function buildClonePreviewResult(stream, shared) {
  const session = shared.cloneSession;
  if (!session) {
    return { followUps: [] };
  }

  const cloneJobName = getCloneDraftJobName(session);
  if (!cloneJobName) {
    session.index = 0;
    stream.markdown('❌ **Clone preview failed:** JobName cannot be empty.\n\n');
    stream.markdown(renderCloneFieldPrompt(session));
    return { followUps: buildCloneFieldFollowUps(session) };
  }

  stream.progress(`Building clone preview for "${cloneJobName}"...`);
  const data = await backendCall('clone_preview', buildCloneBackendParams(session), shared, { timeoutMs: 60000 });
  if (data?.status === 'error' || data?.success === false) {
    const error = data.error || (data.errors || []).join(', ') || 'Unknown error';
    session.phase = 'editing';
    if (/job name|already exists|valid xml tag/i.test(error)) {
      session.index = 0;
    }
    stream.markdown(`❌ **Clone preview failed:** ${error}\n\n`);
    stream.markdown(renderCloneFieldPrompt(session));
    return { followUps: buildCloneFieldFollowUps(session) };
  }

  session.phase = 'confirm';
  session.previewData = data.data;
  stream.markdown(renderClonePreview(data.data));
  return { followUps: buildCloneConfirmFollowUps() };
}

async function handleActiveCloneSession(request, stream, shared) {
  const session = shared.cloneSession;
  if (!session) {
    return { followUps: [] };
  }

  const reply = parseCloneFieldReply(request.prompt);

  if (reply.action === 'cancel') {
    shared.cloneSession = null;
    stream.markdown('✗ **Clone cancelled** — no changes were made.\n');
    return { followUps: [] };
  }

  if (session.phase === 'confirm') {
    if (reply.action === 'back') {
      session.phase = 'editing';
      session.previewData = null;
      session.index = Math.max(0, session.fields.length - 1);
      stream.markdown(renderCloneFieldPrompt(session));
      return { followUps: buildCloneFieldFollowUps(session) };
    }

    if (!isCloneConfirmReply(request.prompt)) {
      stream.markdown(renderClonePreview(session.previewData || {}));
      return { followUps: buildCloneConfirmFollowUps() };
    }

    stream.progress(`Applying clone "${getCloneDraftJobName(session)}"...`);
    const data = await backendCall('clone_apply', buildCloneBackendParams(session), shared, { timeoutMs: 60000 });
    if (data?.status === 'error' || data?.success === false) {
      const error = data.error || (data.errors || []).join(', ') || 'Unknown error';
      if (/already in use|restart \/clone/i.test(error)) {
        shared.cloneSession = null;
        stream.markdown(
          `❌ **Clone failed:** ${error}\n\nStart a fresh /clone servicerID:${session.sourceServicerId} draft to recalculate the clone.\n`
        );
        return { followUps: [] };
      }
      stream.markdown(`❌ **Clone failed:** ${error}\n\n`);
      stream.markdown(renderClonePreview(session.previewData || {}));
      return { followUps: buildCloneConfirmFollowUps() };
    }

    shared.cloneSession = null;
    stream.markdown(renderCloneApplyResult(data.data || {}));
    return {
      followUps: [
        { prompt: 'list backups', label: 'List backups' },
        { prompt: `tell me about job ${data.data?.job_name || getCloneDraftJobName(session)}`, label: 'Inspect cloned job' },
      ],
    };
  }

  if (reply.action === 'back') {
    session.index = Math.max(0, session.index - 1);
    stream.markdown(renderCloneFieldPrompt(session));
    return { followUps: buildCloneFieldFollowUps(session) };
  }

  if (reply.action === 'invalid') {
    stream.markdown(renderCloneFieldPrompt(session));
    return { followUps: buildCloneFieldFollowUps(session) };
  }

  const field = session.fields[session.index];
  let nextValue;
  if (reply.action === 'keep') {
    nextValue = field.path === '@job_name'
      ? normalizeCloneFieldValue(field.suggestedValue || field.currentValue)
      : normalizeCloneFieldValue(field.currentValue);
  } else if (reply.action === 'clear') {
    nextValue = '';
  } else {
    nextValue = normalizeCloneFieldValue(reply.value);
  }

  if (field.path === '@job_name') {
    const trimmed = String(nextValue || '').trim();
    if (!trimmed) {
      stream.markdown('❌ **JobName cannot be empty.**\n\n');
      stream.markdown(renderCloneFieldPrompt(session));
      return { followUps: buildCloneFieldFollowUps(session) };
    }
    if (!isValidCloneJobName(trimmed)) {
      stream.markdown('❌ **JobName must be a valid XML tag.** Use letters, numbers, underscore, dot, or hyphen, and do not start with a number.\n\n');
      stream.markdown(renderCloneFieldPrompt(session));
      return { followUps: buildCloneFieldFollowUps(session) };
    }
    nextValue = trimmed;
  }

  field.draftValue = nextValue;

  if (session.index >= session.fields.length - 1) {
    return buildClonePreviewResult(stream, shared);
  }

  session.index += 1;
  stream.markdown(renderCloneFieldPrompt(session));
  return { followUps: buildCloneFieldFollowUps(session) };
}

async function handleSlashCommand(commandName, request, context, stream, token, shared) {
  const prompt = request.prompt.trim();
  const deterministicSpec = getDeterministicCommandSpec(commandName);

  if (commandName === 'sync_logs') {
    if (prompt && isSlashHelpPrompt(prompt)) {
      stream.markdown(getSlashHelpText(commandName, deterministicSpec));
      return { followUps: getSlashHelpFollowUps(commandName, deterministicSpec) };
    }
    return handleSyncLogsSlashCommand(stream, shared);
  }

  if (commandName === 'rebuild-db') {
    if (prompt && isSlashHelpPrompt(prompt)) {
      stream.markdown(getSlashHelpText(commandName, deterministicSpec));
      return { followUps: getSlashHelpFollowUps(commandName, deterministicSpec) };
    }
    return handleRebuildDbCommand(request, context, stream, token, shared);
  }

  // No arguments or explicit help prompt — show help
  if (!prompt || isSlashHelpPrompt(prompt)) {
    const helpText = getSlashHelpText(commandName, deterministicSpec);
    if (deterministicSpec || (commandName === 'deals' && isDeterministicExperimentEnabled())) {
      streamTrustedMarkdown(stream, helpText);
    } else {
      stream.markdown(helpText);
    }
    return { followUps: getSlashHelpFollowUps(commandName, deterministicSpec) };
  }

  if (commandName === 'deals') {
    const deterministicDealsResult = await handleDeterministicDealsCommand(request, stream, shared);
    if (deterministicDealsResult) {
      return deterministicDealsResult;
    }
  }

  if (commandName === 'logs') {
    const deterministicLogsResult = await handleDeterministicLogsCommand(request, stream, shared);
    if (deterministicLogsResult) {
      return deterministicLogsResult;
    }
  }

  if (commandName === 'staging') {
    const deterministicStagingResult = await handleDeterministicStagingCommand(request, stream, shared);
    if (deterministicStagingResult) {
      return deterministicStagingResult;
    }
  }

  if (commandName === 'triage') {
    const deterministicTriageResult = await handleDeterministicTriageCommand(request, stream, shared);
    if (deterministicTriageResult) {
      return deterministicTriageResult;
    }
  }

  if (commandName === 'clone') {
    return handleCloneCommand(request, stream, shared);
  }

  if (deterministicSpec) {
    return handleDeterministicCommand(commandName, request, stream, shared);
  }

  // Route through agentLoop with optional pipeline enrichment
  const pipelineMap = {
    triage: 'email_triage',
    analyze: 'analysis_pipeline',
  };

  const pipelineName = pipelineMap[commandName];
  if (pipelineName && PIPELINE_DEFINITIONS[pipelineName]) {
    const pipeline = PIPELINE_DEFINITIONS[pipelineName];
    return agentLoop(prompt, {
      playbook: pipeline.playbook,
      tools: pipeline.tools,
      maxSteps: pipeline.maxSteps,
      pipelineName: pipeline.name,
    }, request, context, stream, token, shared);
  }

  // All other slash commands — direct to agentLoop with full tools
  return agentLoop(prompt, {}, request, context, stream, token, shared);
}

// ---------------------------------------------------------------------------
// Test Bench — tool selection validation (Phase 10)
// ---------------------------------------------------------------------------

async function handleTestBenchCommand(request, context, stream, token, shared) {
  const fs = require('fs');
  const path = require('path');

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

  const filterPrompt = request.prompt.trim().toLowerCase();
  let filtered = testCases;
  if (filterPrompt && filterPrompt !== 'all') {
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

  const systemContent = [SYSTEM_PROMPT, '', DOMAIN_KNOWLEDGE, '', ROUTING_GUIDANCE].join('\n');

  stream.markdown(`### 🧪 Tool Selection Test Bench (Phase 10)\n\nRunning **${filtered.length}** test cases…\n\n`);

  const results = [];

  for (const tc of filtered) {
    if (token.isCancellationRequested) {
      stream.markdown('\n⚠️ Test bench cancelled.\n');
      break;
    }

    try {
      const messages = [
        vscode.LanguageModelChatMessage.User(systemContent),
        vscode.LanguageModelChatMessage.User(tc.prompt),
      ];

      const response = await model.sendRequest(messages, { tools: FRP_TOOLS }, token);

      let selectedTool = null;
      for await (const part of response.stream) {
        const toolCall = _extractToolCall(part);
        if (toolCall) {
          selectedTool = toolCall.name;
          break;
        }
      }

      results.push({
        id: tc.id,
        prompt: tc.prompt.length > 60 ? tc.prompt.slice(0, 57) + '...' : tc.prompt,
        tool: selectedTool || '(text)',
        description: tc.description,
      });
    } catch (err) {
      results.push({
        id: tc.id,
        prompt: tc.prompt.length > 60 ? tc.prompt.slice(0, 57) + '...' : tc.prompt,
        tool: `ERROR: ${err.message}`,
        description: tc.description,
      });
    }

    if (results.length % 10 === 0) {
      stream.markdown(`⏳ Progress: ${results.length}/${filtered.length}\n\n`);
    }
  }

  const total = results.length;
  stream.markdown(`\n---\n### Results: ${total} test cases evaluated\n\n`);
  stream.markdown('| # | Pattern | Prompt | Selected Tool |\n');
  stream.markdown('|---|---------|--------|---------------|\n');
  for (const r of results) {
    stream.markdown(`| ${r.id} | ${r.description} | ${r.prompt} | ${r.tool} |\n`);
  }

  shared.outputChannel.appendLine(`[FRP] Test bench complete: ${total} cases evaluated`);

  return { followUps: [] };
}

// ---------------------------------------------------------------------------
// Command dispatch map
// ---------------------------------------------------------------------------

const COMMAND_HANDLERS = {
  jobs:         (req, ctx, stream, token, shared) => handleSlashCommand('jobs', req, ctx, stream, token, shared),
  jobXML:       (req, ctx, stream, token, shared) => handleSlashCommand('jobXML', req, ctx, stream, token, shared),
  jobSQLite:    (req, ctx, stream, token, shared) => handleSlashCommand('jobSQLite', req, ctx, stream, token, shared),
  jobXMLEmail:  (req, ctx, stream, token, shared) => handleSlashCommand('jobXMLEmail', req, ctx, stream, token, shared),
  jobSQLiteEmail:(req, ctx, stream, token, shared) => handleSlashCommand('jobSQLiteEmail', req, ctx, stream, token, shared),
  jobXMLSftp:   (req, ctx, stream, token, shared) => handleSlashCommand('jobXMLSftp', req, ctx, stream, token, shared),
  jobSQLiteSftp:(req, ctx, stream, token, shared) => handleSlashCommand('jobSQLiteSftp', req, ctx, stream, token, shared),
  deals:        (req, ctx, stream, token, shared) => handleSlashCommand('deals', req, ctx, stream, token, shared),
  logs:         (req, ctx, stream, token, shared) => handleSlashCommand('logs', req, ctx, stream, token, shared),
  sync_logs:    (req, ctx, stream, token, shared) => handleSlashCommand('sync_logs', req, ctx, stream, token, shared),
  deploy:       (req, ctx, stream, token, shared) => handleSlashCommand('deploy', req, ctx, stream, token, shared),
  clone:        (req, ctx, stream, token, shared) => handleSlashCommand('clone', req, ctx, stream, token, shared),
  triage:       (req, ctx, stream, token, shared) => handleSlashCommand('triage', req, ctx, stream, token, shared),
  analyze:      (req, ctx, stream, token, shared) => handleSlashCommand('analyze', req, ctx, stream, token, shared),
  staging:      (req, ctx, stream, token, shared) => handleSlashCommand('staging', req, ctx, stream, token, shared),
  testbench:    handleTestBenchCommand,
  'rebuild-db': handleRebuildDbCommand,
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
    const commandName = request.command;
    const cloneSessionState = shared.cloneSession
      ? `${shared.cloneSession.phase}:${shared.cloneSession.sourceServicerId}`
      : 'null';

    shared.outputChannel.appendLine(
      `[FRP] Chat request — command: ${commandName || '(none)'}, prompt: "${request.prompt.slice(0, 100)}", pendingOp: ${shared.pendingOperation ? shared.pendingOperation.type : 'null'}, cloneSession: ${cloneSessionState}`
    );

    if (shared.cloneSession && commandName && commandName !== 'clone') {
      shared.outputChannel.appendLine(`[FRP] Clearing clone session for new slash command: ${commandName}`);
      shared.cloneSession = null;
    }

    if (shared.cloneSession) {
      if (commandName === 'clone') {
        shared.outputChannel.appendLine('[FRP] Restarting clone session from fresh /clone command');
        shared.cloneSession = null;
      } else {
        const cloneResult = await handleActiveCloneSession(request, stream, shared);
        shared._lastFollowUps = cloneResult?.followUps || [];
        return toChatResult(commandName, cloneResult);
      }
    }

    // ── Pending confirmation check ──────────────────────────────────
    if (shared.pendingOperation) {
      const lc = request.prompt.toLowerCase().trim();
      const isConfirm = /^(yes|y|confirm|confirmed|apply|ok|proceed|do\s+it|sure|go ahead|create|clone|execute)/.test(lc);
      const isCancel  = /^(no|n|cancel|stop|abort|nevermind|nope|don.?t)/.test(lc);

      shared.outputChannel.appendLine(
        `[FRP] Pending check — lc: "${lc}", isConfirm: ${isConfirm}, isCancel: ${isCancel}, opType: ${shared.pendingOperation.type}`
      );

      if (isConfirm || isCancel) {
        const op = shared.pendingOperation;
        shared.pendingOperation = null;

        if (isCancel) {
          stream.markdown(`✗ **${op.type.replace('_', ' ')} cancelled** — no changes were made.\n`);
          shared._lastFollowUps = [];
          return toChatResult(commandName, { followUps: [] });
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
        return toChatResult(commandName, result);
      }

      // Unrecognised response — clear pending and route normally
      shared.outputChannel.appendLine(`[FRP] Pending check — unrecognised response, clearing pendingOperation`);
      shared.pendingOperation = null;
    }
    // ── End pending confirmation ─────────────────────────────────────

    let result;

    try {
      if (commandName && COMMAND_HANDLERS[commandName]) {
        result = await COMMAND_HANDLERS[commandName](request, context, stream, token, shared);
      } else {
        // ── Freeform query — unified agentic loop ──
        const prompt = request.prompt.trim();

        if (!prompt) {
          stream.markdown([
            '### FRP Agent\n',
            'I can help you manage the File Reception Portal. Just ask in plain English:\n',
            '| Example | What it does |',
            '|---------|-------------|',
            '| "list all email jobs" | Search monitoring jobs |',
            '| "tell me about job CMBS_GreyCo" | Job detail + linked deals |',
            '| "which jobs handle deal CSMC" | Reverse lookup: deal → jobs |',
            '| "validate all configs" | Lint job configurations |',
            '| "coverage gaps for servicer 569" | Gap analysis |',
            '| "/clone servicerID:150" | Deterministically clone a job |',
            '| "what happened today" | Daily summary |',
            '| "system health report" | Full health analysis |',
            '| "what\'s failing" | Processing failure analysis |',
            '| "triage this email" | Trace email through pipeline |',
            '',
            'Or use slash commands: `/jobs`, `/deals`, `/logs`, `/deploy`, `/clone`, `/triage`, `/analyze`, `/staging`',
          ].join('\n'));

          result = {
            followUps: [
              { prompt: 'list all email jobs', label: 'Browse jobs' },
              { prompt: 'what happened today', label: 'Daily summary' },
              { prompt: 'system health report', label: 'Health check' },
            ],
          };
        } else {
          result = await agentLoop(prompt, {}, request, context, stream, token, shared);
        }
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

    return toChatResult(commandName, result);
  });

  // Follow-up provider
  participant.followupProvider = {
    provideFollowups(result, _context, _token) {
      const followUps = result?.metadata?.followUps || shared._lastFollowUps || [];
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
