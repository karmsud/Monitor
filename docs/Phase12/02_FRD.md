# Phase 12 FRD — Functional Requirements Document
## FRP Agent VS Code Extension — Settings.xml Schema Centralization & Field Mapping Correctness

**Document type:** Functional Requirements Document
**Parent:** Phase 12 PRD (`01_PRD.md`)
**Status:** Draft
**Date:** March 2026

---

## 1. Purpose

This document specifies the exact functional behaviour of each Phase 12 change.  Where the PRD explains *what* and *why*, this document specifies *how the system behaves* after the change — inputs, outputs, protocols, and the precise content of every modified constant or function.  Each section maps to PRD stories (S-1xx through S-4xx).

---

## 2. Current System Behaviour Reference

The following facts are established by reading source code and are referenced throughout this document.

| Fact | Location | Phase 12 disposition |
|---|---|---|
| `DOMAIN_KNOWLEDGE` describes Settings.xml in one line: `"Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation"` | `participant.js` lines 62–65 | Replaced with full two-section XML schema |
| `EMAIL_FIELD_MAP["mailbox"]` = `"MailboxAddress"` but parser reads `<Mailbox>` | `crud.py` line 22 | Fix: `"Mailbox"` |
| `EMAIL_FIELD_MAP["mailbox_address"]` = `"MailboxAddress"` | `crud.py` line 23 | Fix: `"Mailbox"` (keep alias, fix target) |
| `EMAIL_FIELD_MAP["sender_filter"]` = `"SenderFilter"` but parser reads `Filters["From"]` | `crud.py` line 33 | Fix: `"Filters/From"` |
| `SFTP_FIELD_MAP["path"]` = `"RemotePath"` but parser reads `<Path>` | `crud.py` line 44 | Fix: `"Path"` |
| `renderEditDiff()` `tagMap` has `mailbox → 'MailboxAddress'` and `path → 'RemotePath'`; `sender_filter` rendered as flat tag not nested | `participant.js` lines 1490–1507 | Fix tag names; add nested rendering for `sender_filter` |
| `resolveCurrentFieldValue()` reads `job.save_location` but `job_detail` returns `"save_path"` | `participant.js` lines 1455–1458 | Fix 5 broken property lookups |
| `create_job` `overrides` parameter has no field enum | `participant.js` lines 676–697 | Add enumerated description |
| `CRUD_PLANNING_PLAYBOOK` has no XML field knowledge | `participant.js` lines 447–474 | Add field reference |
| `EMAIL_TRIAGE_PLAYBOOK` has no "no match → suggest create" pathway | `participant.js` lines 172–285 | Add pathway |
| All other playbooks reference DOMAIN_KNOWLEDGE for tblTemplateStaging but not XML schema | Multiple locations | Add XML schema references |

---

## 3. Functional Requirements — Epic 1: XML Schema in DOMAIN_KNOWLEDGE

### FR-1.1 — New "Settings.xml Job Schema" Section Content

**Location:** `participant.js` — `DOMAIN_KNOWLEDGE` constant, appended after the "Cross-Reference Chains" section.

The new content adds two sub-sections: one for email jobs, one for SFTP jobs. Each sub-section contains:
1. Full annotated XML structure
2. A field-name → XML element mapping table
3. Key conventions and computed-field warnings

**Full content of the new section:**

```
### Settings.xml Job Schema

**Key convention:** A job's name IS its XML element tag. Jobs live inside a collection:
- Email: <MailboxCollection><JOB_NAME>...</JOB_NAME></MailboxCollection>
- SFTP:  <FolderCollection><JOB_NAME>...</JOB_NAME></FolderCollection>
There is NO <Job Name="..."> wrapper. The tag IS the name.

#### Email Job — XML Structure
\`\`\`xml
<JOB_NAME>
  <Mailbox>rptent@usbank.com</Mailbox>          <!-- monitoring mailbox address -->
  <Folder>Inbox</Folder>                         <!-- mailbox subfolder to watch -->
  <SME>analyst@company.com</SME>                 <!-- subject matter expert -->
  <LastEmail>2/13/2026 12:07:15 PM</LastEmail>   <!-- auto-updated by system -->
  <SaveLocation>M:\{DealFolder}\Data\{YYYY}\{M}\EmailExtract\</SaveLocation>
  <Filters>
    <From>@selenefinance</From>                  <!-- sender email filter (partial match) -->
    <Attachments>True</Attachments>              <!-- require attachments: True/False -->
  </Filters>
  <Parsers>
    <DetachFileSubject>.*</DetachFileSubject>     <!-- regex matched against email SUBJECT LINE -->
    <!-- OR: <DetachFile>.*</DetachFile>  — regex matched against attachment FILENAME -->
    <!-- OR both present → MatchMode = "Both" -->
  </Parsers>
  <ServicerID>6007</ServicerID>                  <!-- links to tblExternalDIDRef.CompanyID -->
  <QueueOneFile>True</QueueOneFile>              <!-- process one attachment at a time -->
  <DayAdjust>0</DayAdjust>                       <!-- day offset for report date -->
  <Templates>
    <Main>Outlook_Queuer_x</Main>                <!-- scrubber/template that processes the file -->
  </Templates>
</JOB_NAME>
\`\`\`

**Email field name → XML element (for edit_job and create_job overrides):**
| Field name | XML element | Notes |
|---|---|---|
| `mailbox` | `<Mailbox>` | Direct child |
| `folder` | `<Folder>` | Direct child |
| `sme` | `<SME>` | Direct child |
| `save_location` | `<SaveLocation>` | Direct child |
| `servicer_id` | `<ServicerID>` | Direct child |
| `last_email` | `<LastEmail>` | Direct child (auto-updated) |
| `queue_one_file` | `<QueueOneFile>` | Direct child; values: "True"/"False" |
| `day_adjust` | `<DayAdjust>` | Direct child; integer as string |
| `sender_filter` | `<Filters><From>` | **Nested** under <Filters> block |
| `scrubber` / `template` | `<Templates><Main>` | **Nested** under <Templates> block |

**Computed fields (NEVER stored as XML — do not write these elements):**
- `match_mode` — derived from Parsers: DetachFileSubject→"Subject", DetachFile→"Filename", both→"Both". Writing <MatchMode> to XML creates a phantom element the system ignores.
- `sender` — display alias for <Filters><From>; same as sender_filter
- `scrubber` — display alias for <Templates><Main>; same as template

**Display model→XML translation (job_detail API key → real XML element):**
- API `"sender"` = XML `<Filters><From>` = edit field `sender_filter`
- API `"save_path"` = XML `<SaveLocation>` = edit field `save_location`
- API `"scrubber"` = XML `<Templates><Main>` = edit field `scrubber` or `template`
- API `"mailbox"` = XML `<Mailbox>` = edit field `mailbox`
- API `"filters"` dict = full contents of `<Filters>` block
- API `"parsers"` dict = full contents of `<Parsers>` block
- API `"templates"` dict = full contents of `<Templates>` block

#### SFTP Job — XML Structure
\`\`\`xml
<JOB_NAME>
  <Path>M:\!Sweeps\SPS\In\</Path>               <!-- SFTP source folder path to monitor -->
  <ServicerID>3702</ServicerID>                  <!-- links to tblExternalDIDRef.CompanyID -->
  <DSN>xf00.sps2.iman</DSN>                     <!-- data source name for DB connection -->
  <SME>analyst@company.com</SME>                 <!-- subject matter expert -->
  <SaveLocation>M:\{DealFolder}\Data\...</SaveLocation>
  <SkipList>N:\...\SkipListOCW.txt</SkipList>   <!-- path to skip-list file (exact match) -->
  <IgnoreList>N:\...\IgnoreListOCW.txt</IgnoreList> <!-- path to ignore-list file (pattern) -->
  <Parsers>
    <MoveFile2>.*</MoveFile2>                    <!-- filename filter regex; MoveFile2 or MoveFile -->
  </Parsers>
  <ZipContentFilter>.*</ZipContentFilter>        <!-- regex for filtering zip file contents -->
  <DayAdjust>0</DayAdjust>                       <!-- day offset for report date -->
  <!-- <Templates><Main>scrubber</Main></Templates>  optional post-download processing -->
</JOB_NAME>
\`\`\`

**SFTP field name → XML element (for edit_job and create_job overrides):**
| Field name | XML element | Notes |
|---|---|---|
| `path` | `<Path>` | Direct child — SFTP source folder |
| `servicer_id` | `<ServicerID>` | Direct child |
| `dsn` | `<DSN>` | Direct child |
| `sme` | `<SME>` | Direct child |
| `save_location` | `<SaveLocation>` | Direct child |
| `skip_list` | `<SkipList>` | Direct child |
| `ignore_list` | `<IgnoreList>` | Direct child |
| `zip_content_filter` | `<ZipContentFilter>` | Direct child |
| `day_adjust` | `<DayAdjust>` | Direct child |
| `scrubber` / `template` | `<Templates><Main>` | **Nested** — optional |

**Display model→XML translation (job_detail API key → real XML element):**
- API `"sftp_path"` = XML `<Path>` = edit field `path`
- API `"save_path"` = XML `<SaveLocation>` = edit field `save_location`
- API `"zip_filter"` = XML `<ZipContentFilter>` = edit field `zip_content_filter`
- API `"scrubber"` = XML `<Templates><Main>` = edit field `scrubber` or `template`
```

**Placement in DOMAIN_KNOWLEDGE:** After the existing "Cross-Reference Chains" section, immediately before the closing backtick of the template literal.

---

### FR-1.2 — DOMAIN_KNOWLEDGE Settings.xml Line Update

The existing brief description of Settings.xml in DOMAIN_KNOWLEDGE must be updated to point forward to the new schema section rather than attempt to summarise it:

**Before:**
```
   - Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation
   - Parsers configured per job: DetachFile, DetachFileSubject (email), MoveFile, MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script), or custom names
```

**After:**
```
   - See "Settings.xml Job Schema" section below for full field and element reference
   - Parsers per job: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script)
```

This removes the incomplete/misleading list and replaces it with a forward pointer, ensuring the schema section is the single authoritative source.

---

## 4. Functional Requirements — Epic 2: Backend Field Map Corrections

### FR-2.1 — EMAIL_FIELD_MAP Corrections

**File:** `backend/xml/crud.py`

**Change 1 — `mailbox` and `mailbox_address` targets:**

```python
# Before:
"mailbox":         "MailboxAddress",
"mailbox_address": "MailboxAddress",

# After:
"mailbox":         "Mailbox",
"mailbox_address": "Mailbox",
```

**Change 2 — `sender_filter` target:**

```python
# Before:
"sender_filter": "SenderFilter",

# After:
"sender_filter": "Filters/From",
```

The `edit_job` method already handles the `"/"` separator in XML paths via find-or-create traversal (lines 187–198 of `crud.py`). No logic change needed — the string change alone activates the existing nested path handling.

**No change to `subject_filter` in Phase 12.** The mapping `"subject_filter": "SubjectFilter"` remains. The `<SubjectFilter>` top-level element is not read by the parser, meaning `subject_filter` is effectively write-only. This is a known gap documented in the PRD "Out of Scope" section and deferred to a future data model phase.

---

### FR-2.2 — SFTP_FIELD_MAP Correction

**File:** `backend/xml/crud.py`

```python
# Before:
"path": "RemotePath",

# After:
"path": "Path",
```

---

### FR-2.3 — Behaviour After Fixes

**`create_job` with mailbox override (after fix):**
```xml
<!-- Input: create_job(templateJob="PRET2024RPL2_Selene_6007",
                       newName="TestDeal1",
                       overrides={"mailbox": "new@usbank.com"}) -->
<!-- Result: TestDeal1 has <Mailbox>new@usbank.com</Mailbox> (correct) -->
<!-- Not: <MailboxAddress>new@usbank.com</MailboxAddress> (old wrong behaviour) -->
```

**`edit_job` with sender_filter (after fix):**
```xml
<!-- Input: edit_job("TestDeal1", "sender_filter", "earl.cruz@usbank.com") -->
<!-- Result: <Filters><From>earl.cruz@usbank.com</From></Filters> -->
<!-- Not: top-level <SenderFilter>earl.cruz@usbank.com</SenderFilter> -->
```

---

## 5. Functional Requirements — Epic 3: Frontend Code Corrections

### FR-3.1 — `renderEditDiff()` — Full Corrected Behaviour

**File:** `extension/chat/participant.js`

**Nested field detection** — expand from scrubber/template only to include sender_filter:

```javascript
// Before: only scrubber/template treated as nested
const isNested = (field === 'scrubber' || field === 'template');

// After: also sender_filter
const isNested = (field === 'scrubber' || field === 'template' || field === 'sender_filter');
```

**Nested rendering** — add the `sender_filter` case:

```javascript
if (isNested) {
  if (field === 'scrubber' || field === 'template') {
    beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
    afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
  } else if (field === 'sender_filter') {
    beforeXml = `<Filters><From>${currentValue || '(not set)'}</From></Filters>`;
    afterXml  = `<Filters><From>${newValue}</From></Filters>`;
  }
}
```

**`tagMap` corrections:**

| Field | Before | After | Reason |
|---|---|---|---|
| `mailbox` | `'MailboxAddress'` | `'Mailbox'` | Bug fix — parser reads `<Mailbox>` |
| `path` | `'RemotePath'` | `'Path'` | Bug fix — parser reads `<Path>` |
| `sender_filter` | (had entry, now removed from flat tagMap) | (handled in nested branch) | Bug fix — nested element |
| `save_location` | (missing — fell back to field name as tag) | `'SaveLocation'` | Fix missing entry |

**Complete corrected `tagMap`:**
```javascript
const tagMap = {
  servicer_id:        'ServicerID',
  mailbox:            'Mailbox',        // FIXED (was 'MailboxAddress')
  folder:             'Folder',
  sme:                'SME',
  save_location:      'SaveLocation',   // ADDED (was missing)
  import_did:         'ImportDID',
  subject_filter:     'SubjectFilter',
  day_adjust:         'DayAdjust',
  name:               'Name',
  // SFTP fields
  path:               'Path',           // FIXED (was 'RemotePath')
  dsn:                'DSN',
  skip_list:          'SkipList',
  ignore_list:        'IgnoreList',
  zip_content_filter: 'ZipContentFilter',
};
// NOTE: sender_filter removed from tagMap — it is handled in the isNested branch above
```

---

### FR-3.2 — `resolveCurrentFieldValue()` — Full Corrected Behaviour

**File:** `extension/chat/participant.js`

The function reads from `jobDetailResult.data.job`. The `job_detail` API uses different key names for some fields than the edit field names. Below is the complete corrected `fieldMap`:

```javascript
const fieldMap = {
  // Email fields
  scrubber:            () => job.scrubber || '',
  template:            () => job.scrubber || '',
  servicer_id:         () => String(job.servicer_id ?? ''),
  mailbox:             () => job.mailbox || '',
  folder:              () => job.folder || '',
  sme:                 () => job.sme || '',
  save_location:       () => job['save_path'] || '',           // FIXED: API returns 'save_path'
  import_did:          () => job['import_did'] || '',          // not returned by API; always ''
  subject_filter:      () => job['subject_filter'] || '',      // not returned by API; always ''
  sender_filter:       () => job.sender || job.filters?.From || '', // FIXED: API returns 'sender'
  day_adjust:          () => String(job.day_adjust ?? ''),
  name:                () => job['job_name'] || '',            // FIXED: API returns 'job_name'
  last_email:          () => job.last_email || '',
  queue_one_file:      () => String(job.queue_one_file ?? ''),
  // SFTP-only fields
  path:                () => job['sftp_path'] || '',           // FIXED: API returns 'sftp_path'
  dsn:                 () => job.dsn || '',
  skip_list:           () => job.skip_list || '',
  ignore_list:         () => job.ignore_list || '',
  zip_content_filter:  () => job['zip_filter'] || '',          // FIXED: API returns 'zip_filter'
};
```

**Known limitations that are NOT fixed in Phase 12:**
- `import_did` — not returned by `job_detail` API (not in DB cache schema); will always show `(not set)` as before
- `subject_filter` — not returned by `job_detail` API; will always show `(not set)` as before
These are noted in the before/after diff with a `// not returned by API` comment so future work can address the data model gap.

---

## 6. Functional Requirements — Epic 4: Tool Descriptions and Playbook Updates

### FR-4.1 — `create_job` Tool `overrides` Description

**File:** `extension/chat/participant.js`

**Before:**
```javascript
overrides: {
  type: 'object',
  description: 'Optional field overrides to apply (e.g. {"servicer_id": "999"}).',
  additionalProperties: { type: 'string' },
},
```

**After:**
```javascript
overrides: {
  type: 'object',
  description: [
    'Optional field overrides. Keys must be valid field names from this list:',
    'EMAIL fields: mailbox (<Mailbox>), folder (<Folder>), sme (<SME>), save_location (<SaveLocation>),',
    'servicer_id (<ServicerID>), sender_filter (<Filters><From>), scrubber (<Templates><Main>),',
    'queue_one_file (<QueueOneFile>), day_adjust (<DayAdjust>), last_email (<LastEmail>).',
    'SFTP fields: path (<Path>), dsn (<DSN>), skip_list (<SkipList>), ignore_list (<IgnoreList>),',
    'zip_content_filter (<ZipContentFilter>), scrubber (<Templates><Main>), day_adjust (<DayAdjust>).',
    'NEVER use display-model names: match_mode, sender, save_path, sftp_path, zip_filter.',
    'Example: {"servicer_id": "6009", "sender_filter": "earl.cruz@usbank.com"}',
  ].join(' '),
  additionalProperties: { type: 'string' },
},
```

---

### FR-4.2 — `CRUD_PLANNING_PLAYBOOK` XML Field Reference

**File:** `extension/chat/participant.js`

Add a "Field Reference" sub-section to `CRUD_PLANNING_PLAYBOOK` after the existing `## RULES` block:

```
## Field Reference (consult when planning create_job or edit_job steps)

Refer to DOMAIN_KNOWLEDGE § "Settings.xml Job Schema" for the full XML structure.

Key rules for planning:
- Use edit_job FIELD NAMES (not XML element names and not display-model names):
  sender_filter (not "SenderFilter", not "sender"), mailbox (not "MailboxAddress"),
  save_location (not "save_path"), path (not "RemotePath", not "sftp_path").
- NEVER plan a step that sets match_mode — it is computed from Parsers, not stored.
- Nested fields (sender_filter, scrubber/template) are handled by the backend automatically.
- Email-only fields: mailbox, folder, sender_filter, queue_one_file, last_email, import_did.
- SFTP-only fields: path, dsn, skip_list, ignore_list, zip_content_filter.
- Both types: servicer_id, sme, save_location, day_adjust, scrubber/template.
```

---

### FR-4.3 — `EMAIL_TRIAGE_PLAYBOOK` No-Match Creation Pathway

**File:** `extension/chat/participant.js`

**Current Step 3 behaviour (no match):** When no email job matches the incoming email, the triage report states "no matching job found" and ends.

**New behaviour:**  When Step 3 (job matching) finds no match, the report should include a "Suggested Remediation" section structured as follows:

```
## Suggested Remediation — No Matching Job Found

The incoming email has no configured monitoring job. To add coverage:

1. Identify a similar existing job to use as a template (search_jobs with the mailbox or servicer).
2. Plan a create_job call with these overrides derived from the email metadata:
   - sender_filter: <From header value, e.g. "earl.cruz@domain.com">
   - mailbox: <mailbox this email arrived at>
   - servicer_id: <CompanyID from tblExternalDIDRef if the deal exists; else "TBD">
   - scrubber: <template name from similar job>
3. After creation, confirm the new job appears in search_jobs results.
```

Add a reference to DOMAIN_KNOWLEDGE § Settings.xml Job Schema in the domain model section of the playbook: `"Refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema for field names and XML structure."`

---

### FR-4.4 — Remaining Playbook Updates

**File:** `extension/chat/participant.js`

Each of the following playbooks has a "Domain Model" or knowledge section. Add one line to each:

**`JOB_INVESTIGATION_PLAYBOOK`** (domain model section):
```
- Settings.xml field names and XML structure: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

**`SERVICER_INVESTIGATION_PLAYBOOK`** (domain model section):
```
- Settings.xml field names and XML structure: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

**`GENERAL_REASONING_PLAYBOOK`** (domain model section):
```
- Settings.xml field names and XML structure: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

**`ANALYSIS_PLAYBOOK`** (after the tool selection table):
```
Note: For questions about job field names, XML structure, or valid edit_job fields,
refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

---

## 7. Interaction and Flow Changes

### 7.1 Clone/Create Confirmation Flow — Before vs After

**Before (S-202, S-102):**
```
User: Clone PRET2024RPL2_Selene_6007 as TestDeal1 with ServicerID 6009
Agent: [searches for template, finds job]
Agent: Proposed: Create new job `TestDeal1` from template `PRET2024RPL2_Selene_6007`
Agent: Overrides: servicer_id=6009

[After confirm]
Agent: Preview XML:
<Job Name="TestDeal1">        ← WRONG: invented wrapper
  <ServicerID>6009</ServicerID>
  <Mailbox>rptent@usbank.com</Mailbox>
  <SenderFilter>...</SenderFilter>  ← WRONG: phantom element
  <Scrubber>Outlook_Queuer_x</Scrubber>  ← WRONG: phantom element
  <MatchMode>Subject</MatchMode>  ← WRONG: computed, not stored
</Job>
```

**After:**
The LLM has DOMAIN_KNOWLEDGE § Settings.xml Job Schema and knows:
- The wrapper IS the job name (`<TestDeal1>`)
- Sender is `<Filters><From>`, not `<SenderFilter>`
- Scrubber is `<Templates><Main>`, not `<Scrubber>`
- `<MatchMode>` does not exist
```
Agent: Proposed XML (the deep copy preserves all fields from template; overrides applied):
<TestDeal1>
  <Mailbox>rptent@usbank.com</Mailbox>    ← preserved from template
  <Folder>Inbox</Folder>                   ← preserved
  <SME>sudhanwa.karmarkar@usbank.com</SME> ← preserved
  <Filters>
    <From>@selenefinance</From>            ← preserved (use edit_job to change)
    <Attachments>True</Attachments>
  </Filters>
  <Parsers>
    <DetachFileSubject>.*</DetachFileSubject>
  </Parsers>
  <ServicerID>6009</ServicerID>            ← OVERRIDDEN from 6007
  ...
</TestDeal1>
```

### 7.2 Edit Job Diff — Before vs After for `sender_filter`

**Before:**
```xml
<!-- renderEditDiff with field="sender_filter", currentValue="@oldomain.com", newValue="@newdomain.com" -->
Before: <SenderFilter>@oldomain.com</SenderFilter>   ← WRONG element name
After:  <SenderFilter>@newdomain.com</SenderFilter>  ← WRONG element name
```

**After (FR-3.1):**
```xml
Before: <Filters><From>@oldomain.com</From></Filters>
After:  <Filters><From>@newdomain.com</From></Filters>
```

### 7.3 Triage No-Match Flow — Before vs After

**Before (no pathway existed):**
```
Triage result: No matching job found for sender earl.cruz@usbank.com on mailbox rptent@usbank.com.
[End of report]
```

**After (FR-4.3):**
```
Triage result: No matching job found.

## Suggested Remediation — No Matching Job Found
1. Search for a similar job: search_jobs("rptent") to find jobs on this mailbox
2. Create a new job:
   create_job(templateJob="<similar_job>", newName="<new_name>",
              overrides={"sender_filter": "earl.cruz@usbank.com",
                         "servicer_id": "<TBD or matched CompanyID>"})
3. Confirm the new job catches future emails from this sender.
```

---

## 8. Test Specifications

### FR-2: Backend Field Map Tests (Python)

**TC-FR201-01:** `edit_job(job_name, "mailbox", "new@usbank.com")` on an email job → saved XML has `<Mailbox>new@usbank.com</Mailbox>`, no `<MailboxAddress>` element.

**TC-FR201-02:** `edit_job(job_name, "sender_filter", "@newdomain.com")` → saved XML has `<Filters><From>@newdomain.com</From></Filters>`, no `<SenderFilter>` element.

**TC-FR202-01:** `edit_job(job_name, "path", "M:\\NewPath\\")` on SFTP job → saved XML has `<Path>M:\NewPath\</Path>`, no `<RemotePath>` element.

**TC-FR201-03:** `create_job(template, new_name, overrides={"mailbox": "new@usbank.com"})` → cloned job has `<Mailbox>new@usbank.com</Mailbox>`.

### FR-3: Frontend Helper Tests (JS)

**TC-FR301-01:** `renderEditDiff("job", "mailbox", "old@usbank.com", "new@usbank.com", "email")` → output contains `<Mailbox>old@usbank.com</Mailbox>` and `<Mailbox>new@usbank.com</Mailbox>`. No `MailboxAddress`.

**TC-FR301-02:** `renderEditDiff("job", "sender_filter", "@old.com", "@new.com", "email")` → output contains `<Filters><From>@old.com</From></Filters>` and `<Filters><From>@new.com</From></Filters>`. No `SenderFilter`.

**TC-FR301-03:** `renderEditDiff("job", "path", "M:\\Old\\", "M:\\New\\", "sftp")` → output contains `<Path>M:\Old\</Path>` and `<Path>M:\New\</Path>`. No `RemotePath`.

**TC-FR302-01:** `resolveCurrentFieldValue({data:{job:{save_path:"M:\\Data\\"}}}, "save_location")` → returns `"M:\\Data\\"`.

**TC-FR302-02:** `resolveCurrentFieldValue({data:{job:{sender:"@domain.com"}}}, "sender_filter")` → returns `"@domain.com"`.

**TC-FR302-03:** `resolveCurrentFieldValue({data:{job:{job_name:"TestJob"}}}, "name")` → returns `"TestJob"`.

**TC-FR302-04:** `resolveCurrentFieldValue({data:{job:{sftp_path:"M:\\Sweeps\\SPS\\"}}}, "path")` → returns `"M:\\Sweeps\\SPS\\"`.

**TC-FR302-05:** `resolveCurrentFieldValue({data:{job:{zip_filter:".*"}}}, "zip_content_filter")` → returns `".*"`.
