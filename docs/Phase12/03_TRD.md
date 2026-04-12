# Phase 12 TRD — Technical Requirements Document
## FRP Agent VS Code Extension — Settings.xml Schema Centralization & Field Mapping Correctness

**Document type:** Technical Requirements Document
**Parent:** Phase 12 PRD (`01_PRD.md`), FRD (`02_FRD.md`)
**Status:** Draft
**Date:** March 2026

---

## 1. Purpose

This document specifies exactly which files and functions change, what the before/after code looks like for each change, and the precise sequencing of implementation. Every story from the PRD is mapped to one or more concrete code changes with exact file paths, function names, and surrounding context lines.

---

## 2. Affected Files

| File | Change type | Stories | Estimated lines changed |
|---|---|---|---|
| `backend/xml/crud.py` | Modify — fix 3 wrong XML tag names in `EMAIL_FIELD_MAP` and `SFTP_FIELD_MAP` | S-201, S-202, S-203 | ~4 lines |
| `extension/chat/participant.js` | Modify — 7 separate changes across `DOMAIN_KNOWLEDGE`, helpers, tool definition, and playbooks | S-101, S-102, S-301, S-302, S-401, S-402, S-403, S-404 | ~120 lines |
| `tests/xml/` | Modify — update edit_job tests to assert correct XML element names; add 3 new test cases | S-201, S-202, S-203 | ~30 lines |
| `extension/test/` | Modify — update renderEditDiff and resolveCurrentFieldValue tests | S-301, S-302 | ~40 lines |

**No new files are created. No database migrations. No new Python packages.**

---

## 3. Implementation Sequence

```
Step 1: backend/xml/crud.py         — Fix EMAIL_FIELD_MAP and SFTP_FIELD_MAP (S-201–S-203)
Step 2: participant.js              — Fix resolveCurrentFieldValue() (S-302)
Step 3: participant.js              — Fix renderEditDiff() (S-301)
Step 4: participant.js              — Update DOMAIN_KNOWLEDGE (S-101, S-102)
Step 5: participant.js              — Update create_job overrides description (S-401)
Step 6: participant.js              — Update CRUD_PLANNING_PLAYBOOK (S-402)
Step 7: participant.js              — Update EMAIL_TRIAGE_PLAYBOOK (S-403)
Step 8: participant.js              — Update remaining playbooks (S-404)
Step 9: Tests                       — Backend and frontend tests
```

Steps 1–3 are code bug fixes and can be validated immediately against the existing test suite.
Steps 4–8 are knowledge changes to constants (strings) and can be deployed atomically.
Step 9 validates all changes.

Rationale for ordering: fix the code before updating the knowledge, so that by the time the LLM has correct XML knowledge, the backend is already writing the correct XML.

---

## 4. Epic 2: Backend Field Map Corrections — `backend/xml/crud.py`

### 4.1 Change: `EMAIL_FIELD_MAP` — `mailbox` and `mailbox_address` targets

**File:** `backend/xml/crud.py`
**Lines:** 20–38 (EMAIL_FIELD_MAP constant)

**Before:**
```python
EMAIL_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "mailbox": "MailboxAddress",
    "mailbox_address": "MailboxAddress",
    "folder": "Folder",
    "sme": "SME",
    "save_location": "SaveLocation",
    "last_email": "LastEmail",
    "queue_one_file": "QueueOneFile",
    "day_adjust": "DayAdjust",
    "import_did": "ImportDID",
    "subject_filter": "SubjectFilter",
    "sender_filter": "SenderFilter",
    # Scrubber / template — stored as <Templates><Main>VALUE</Main></Templates>
    "scrubber": "Templates/Main",
    "template": "Templates/Main",
    "templates_main": "Templates/Main",
}
```

**After:**
```python
EMAIL_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "mailbox": "Mailbox",
    "mailbox_address": "Mailbox",
    "folder": "Folder",
    "sme": "SME",
    "save_location": "SaveLocation",
    "last_email": "LastEmail",
    "queue_one_file": "QueueOneFile",
    "day_adjust": "DayAdjust",
    "import_did": "ImportDID",
    "subject_filter": "SubjectFilter",
    "sender_filter": "Filters/From",
    # Scrubber / template — stored as <Templates><Main>VALUE</Main></Templates>
    "scrubber": "Templates/Main",
    "template": "Templates/Main",
    "templates_main": "Templates/Main",
}
```

**Verification:** `SettingsXmlParser._parse_email_job()` reads `self._text(element, "Mailbox")` — confirmed in `backend/xml/parser.py` line 416. After this fix, `edit_job(mailbox=X)` and `create_job(overrides={"mailbox": X})` will find and update the correct element.

---

### 4.2 Change: `SFTP_FIELD_MAP` — `path` target

**File:** `backend/xml/crud.py`
**Lines:** 40–52 (SFTP_FIELD_MAP constant)

**Before:**
```python
SFTP_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "path": "RemotePath",
    "dsn": "DSN",
    "sme": "SME",
    "save_location": "SaveLocation",
    "skip_list": "SkipList",
    "ignore_list": "IgnoreList",
    "zip_content_filter": "ZipContentFilter",
    "day_adjust": "DayAdjust",
}
```

**After:**
```python
SFTP_FIELD_MAP: Dict[str, str] = {
    "name": "Name",
    "servicer_id": "ServicerID",
    "path": "Path",
    "dsn": "DSN",
    "sme": "SME",
    "save_location": "SaveLocation",
    "skip_list": "SkipList",
    "ignore_list": "IgnoreList",
    "zip_content_filter": "ZipContentFilter",
    "day_adjust": "DayAdjust",
}
```

**Verification:** `SettingsXmlParser._parse_sftp_job()` reads `self._text(element, "Path")` — confirmed in `backend/xml/parser.py` line 431.

---

### 4.3 No Logic Changes to `edit_job()` or `create_job()`

The `edit_job()` method at `crud.py` lines 159–240 already handles nested paths via the `"/"` split logic (lines 187–198). The `sender_filter → "Filters/From"` fix requires no changes to this method — the new string value `"Filters/From"` activates the existing find-or-create traversal automatically.

---

## 5. Epic 3: Frontend Code Corrections — `resolveCurrentFieldValue()`

### 5.1 Change: `resolveCurrentFieldValue()` — Fix 5 broken property lookups

**File:** `extension/chat/participant.js`
**Function:** `resolveCurrentFieldValue()` at line 1444
**Root cause:** `job_detail` returns different property names than the function expects.

**API response key facts** (from `backend/db/xml_index.py` `_email_row_to_detail()` and `_sftp_row_to_detail()`):
- `"save_path"` (not `"save_location"`, not `"SaveLocation"`)
- `"sender"` (not `"sender_filter"`, not `"SenderFilter"`) — also available as `filters.From`
- `"job_name"` (not `"name"`, not `"Name"`)
- `"sftp_path"` for SFTP jobs (not `"path"`, not `"RemotePath"`)
- `"zip_filter"` for SFTP jobs (not `"zip_content_filter"`, not `"ZipContentFilter"`)

**Before:**
```javascript
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
```

**After:**
```javascript
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
```

**Fields added that were missing:** `last_email`, `queue_one_file` (were not in the original fieldMap at all).

---

## 6. Epic 3: Frontend Code Corrections — `renderEditDiff()`

### 6.1 Change: `renderEditDiff()` — Correct tag names and add sender_filter nested handling

**File:** `extension/chat/participant.js`
**Function:** `renderEditDiff()` at line 1473

**Before:**
```javascript
function renderEditDiff(jobName, field, currentValue, newValue, xmlType) {
  const isNested = (field === 'scrubber' || field === 'template');
  let beforeXml, afterXml;

  if (isNested) {
    beforeXml = `<Templates><Main>${currentValue || '(not set)'}</Main></Templates>`;
    afterXml  = `<Templates><Main>${newValue}</Main></Templates>`;
  } else {
    const tagMap = {
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
```

**After:**
```javascript
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
      mailbox:            'Mailbox',         // FIXED: was 'MailboxAddress'
      folder:             'Folder',
      sme:                'SME',
      save_location:      'SaveLocation',    // ADDED: was missing
      import_did:         'ImportDID',
      subject_filter:     'SubjectFilter',
      day_adjust:         'DayAdjust',
      name:               'Name',
      path:               'Path',            // FIXED: was 'RemotePath'
      dsn:                'DSN',
      skip_list:          'SkipList',
      ignore_list:        'IgnoreList',
      zip_content_filter: 'ZipContentFilter',
    };
    const tag = tagMap[field] || field;
    beforeXml = `<${tag}>${currentValue || '(not set)'}</${tag}>`;
    afterXml  = `<${tag}>${newValue}</${tag}>`;
  }
```

**Key changes summary:**
- `isNested` expanded to include `sender_filter`
- `if (isNested)` block now has a conditional inside for which nested template to use
- `tagMap.mailbox`: `'MailboxAddress'` → `'Mailbox'`
- `tagMap.path`: `'RemotePath'` → `'Path'`
- `tagMap.save_location`: added (was missing, would have fallen back to field name `'save_location'` as the tag)
- `tagMap.sender_filter`: removed (now handled in nested branch)

---

## 7. Epic 1: DOMAIN_KNOWLEDGE Update — `participant.js`

### 7.1 Change: Update the Settings.xml description line and add XML Schema section

**File:** `extension/chat/participant.js`
**Location:** `DOMAIN_KNOWLEDGE` constant — the "Settings.xml" bullet under "Three-Table Pipeline" and the end of the constant (before the closing backtick).

**Change 1 — Update the Settings.xml fields line:**

**Before (lines 63–65):**
```javascript
   - Email/SFTP monitoring job definitions (one XML element per job)
   - Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation
   - Parsers configured per job: DetachFile, DetachFileSubject (email), MoveFile, MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script), or custom names
```

**After:**
```javascript
   - Email/SFTP monitoring job definitions (one XML element per job)
   - See "Settings.xml Job Schema" section below for full field and element reference
   - Parsers per job: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script)
```

**Change 2 — Append XML Schema section before closing backtick:**

**Before (end of DOMAIN_KNOWLEDGE, closing lines):**
```javascript
- Full pipeline: all three layers combined for one entity`;
```

**After:**
```javascript
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
    <!-- OR: <DetachFile>.*</DetachFile>  — regex matched against attachment FILENAME -->
    <!-- OR both present → MatchMode = "Both" -->
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
- API \`"filters"\` dict = full contents of \`<Filters>\` block
- API \`"parsers"\` dict = full contents of \`<Parsers>\` block

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
- API \`"zip_filter"\` = XML \`<ZipContentFilter>\` = edit field \`zip_content_filter\``;
```

---

## 8. Epic 4: Tool and Playbook Updates — `participant.js`

### 8.1 Change: `create_job` overrides parameter description

**File:** `extension/chat/participant.js`
**Location:** `create_job` tool definition in `FRP_TOOLS` array, `overrides` property (around line 683)

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
          description: 'Optional field overrides to apply to the new job after cloning. ' +
            'Keys MUST be valid field names (see DOMAIN_KNOWLEDGE § Settings.xml Job Schema for full list). ' +
            'EMAIL fields: mailbox, folder, sme, save_location, servicer_id, sender_filter, ' +
            'scrubber (or template), queue_one_file, day_adjust, last_email. ' +
            'SFTP fields: path, dsn, sme, save_location, servicer_id, skip_list, ignore_list, ' +
            'zip_content_filter, day_adjust, scrubber (or template). ' +
            'NEVER use display-model names as keys: do NOT use match_mode, sender, save_path, sftp_path, zip_filter. ' +
            'Example: {"servicer_id": "6009", "sender_filter": "earl.cruz@usbank.com"}',
          additionalProperties: { type: 'string' },
        },
```

---

### 8.2 Change: `CRUD_PLANNING_PLAYBOOK` — Add field reference

**File:** `extension/chat/participant.js`
**Location:** `CRUD_PLANNING_PLAYBOOK` constant — after the `## RULES` block, before `.trim()`

**Before:**
```javascript
## RULES
- Never merge multiple edits into a single tool call.
- Always call job_detail before edit_job to verify the job exists.
- If any required parameter is unknown, ask BEFORE presenting the plan.
- The plan confirmation is done by the FRP agent infrastructure — you do not ask again.
`.trim();
```

**After:**
```javascript
## RULES
- Never merge multiple edits into a single tool call.
- Always call job_detail before edit_job to verify the job exists.
- If any required parameter is unknown, ask BEFORE presenting the plan.
- The plan confirmation is done by the FRP agent infrastructure — you do not ask again.

## Field Reference (for create_job overrides= and edit_job field=)

Refer to DOMAIN_KNOWLEDGE § "Settings.xml Job Schema" for the full XML structure and field list.

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
```

---

### 8.3 Change: `EMAIL_TRIAGE_PLAYBOOK` — Add no-match creation pathway and schema reference

**File:** `extension/chat/participant.js`
**Location:** `EMAIL_TRIAGE_PLAYBOOK` — two changes: (1) update Domain Model section, (2) update Step 2 no-match branch.

**Change 1 — Add XML schema reference to Domain Model section:**

**Before (lines ~175–183):**
```javascript
## Domain Model

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for full column semantics, trigger identification, and cross-reference chains. Key reminders for triage:
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- ImportDID keywords are matched against email subject lines to identify deals
- **Not all jobs have DIDs** — process/shelf-level jobs (e.g. ABS_Deals_Queuer_x) have empty DIDs and that is normal
- **DataSource** in tblTemplateStaging is the definitive way to confirm an email was processed: it contains \`<mailbox>: <subject>\`
- **Job** column shows the parser used: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script), etc.
```

**After:**
```javascript
## Domain Model

Refer to the **FRP Data Model Reference** (DOMAIN_KNOWLEDGE) for full column semantics, trigger identification, and cross-reference chains. Key reminders for triage:
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- ImportDID keywords are matched against email subject lines to identify deals
- **Not all jobs have DIDs** — process/shelf-level jobs (e.g. ABS_Deals_Queuer_x) have empty DIDs and that is normal
- **DataSource** in tblTemplateStaging is the definitive way to confirm an email was processed: it contains \`<mailbox>: <subject>\`
- **Job** column shows the parser used: DetachFile/DetachFileSubject (email), MoveFile/MoveFile2 (SFTP), DownloadAutomationv2.ps1 (script), etc.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema for field names, nested elements, and create_job parameter guidance.
```

**Change 2 — Expand Step 2 no-match branch with creation suggestion:**

**Before (Step 2 no-match text):**
```javascript
- If NOT FOUND: Report "No matching job found for sender domain." Offer: "Would you like to create a new job for this sender?" STOP here — do not continue to Step 3.
```

**After:**
```javascript
- If NOT FOUND: Report "No matching job found for sender domain." Then provide a creation suggestion using the following structure (refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema for field names):
  1. Suggest a similar existing job as a template (e.g., another job on the same mailbox): search_jobs with the mailbox address.
  2. Outline the create_job call with these overrides derived from the email metadata:
     - \`sender_filter\`: the sender email or domain from Step 1
     - \`mailbox\`: the destination mailbox this email arrived at
     - \`servicer_id\`: CompanyID from tblExternalDIDRef if the deal already exists; otherwise note it as "TBD — must be set after deal is registered"
     - \`scrubber\`: template name from a similar job (copy from the suggested template job)
  3. Remind the user that the backend will deep-copy the template job's full XML structure and apply only the specified overrides.
  STOP after presenting this suggestion — do not continue to Step 3.
```

---

### 8.4 Change: Remaining Playbook Domain Model references

**File:** `extension/chat/participant.js`

These are small one-line additions to each playbook's Domain Model section.

**Change: `JOB_INVESTIGATION_PLAYBOOK` Domain Model section:**

**Before:**
```javascript
- **tblTemplateStaging**: TemplateName = job's Scrubber. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name. See DOMAIN_KNOWLEDGE for the processing state machine.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics, DID match failures, daily activity events.
```

**After:**
```javascript
- **tblTemplateStaging**: TemplateName = job's Scrubber. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name. See DOMAIN_KNOWLEDGE for the processing state machine.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics, DID match failures, daily activity events.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

**Change: `SERVICER_INVESTIGATION_PLAYBOOK` Domain Model section:**

**Before:**
```javascript
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- **tblTemplateStaging**: query by ServicerID or TemplateName. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics and DID failure events.
```

**After:**
```javascript
- ServicerID (Settings.xml) = CompanyID (tblExternalDIDRef)
- **tblTemplateStaging**: query by ServicerID or TemplateName. Use DataSource to identify trigger type (email/SFTP/manual). Use Job column for parser name.
- Not all jobs have DIDs — process/shelf-level jobs have empty DIDs and that is normal.
- **Application logs** — job health metrics and DID failure events.
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

**Change: `GENERAL_REASONING_PLAYBOOK` and `ANALYSIS_PLAYBOOK`:**
Add the same single line to the domain model / guidance section of each:
```javascript
- **Settings.xml field names and XML structure**: refer to DOMAIN_KNOWLEDGE § Settings.xml Job Schema.
```

---

## 9. Test Specifications

### 9.1 Backend Tests — `tests/xml/`

Existing `test_crud.py` tests that exercise `edit_job` and `create_job` must be updated and extended.

**New test: `test_edit_mailbox_writes_correct_element()`**
```python
def test_edit_mailbox_writes_correct_element(tmp_xml_path):
    engine = JobCrudEngine(tmp_xml_path, xml_type="email")
    engine.edit_job("PRET2024RPL2_Selene_6007", "mailbox", "new@usbank.com")
    tree = ET.parse(tmp_xml_path)
    job_el = tree.getroot().find(".//PRET2024RPL2_Selene_6007")
    assert job_el.findtext("Mailbox") == "new@usbank.com"
    assert job_el.find("MailboxAddress") is None  # no phantom element
```

**New test: `test_edit_sender_filter_writes_nested_element()`**
```python
def test_edit_sender_filter_writes_nested_element(tmp_xml_path):
    engine = JobCrudEngine(tmp_xml_path, xml_type="email")
    engine.edit_job("PRET2024RPL2_Selene_6007", "sender_filter", "earl.cruz@usbank.com")
    tree = ET.parse(tmp_xml_path)
    job_el = tree.getroot().find(".//PRET2024RPL2_Selene_6007")
    filters = job_el.find("Filters")
    assert filters is not None
    assert filters.findtext("From") == "earl.cruz@usbank.com"
    assert job_el.find("SenderFilter") is None  # no phantom top-level element
```

**New test: `test_edit_sftp_path_writes_correct_element()`**
```python
def test_edit_sftp_path_writes_correct_element(tmp_sftp_xml_path):
    engine = JobCrudEngine(tmp_sftp_xml_path, xml_type="sftp")
    engine.edit_job("SPS_TPMT_3702", "path", "M:\\NewPath\\")
    tree = ET.parse(tmp_sftp_xml_path)
    job_el = tree.getroot().find(".//SPS_TPMT_3702")
    assert job_el.findtext("Path") == "M:\\NewPath\\"
    assert job_el.find("RemotePath") is None  # no phantom element
```

**Existing tests that must still pass:** All `test_crud.py` tests that exercise `ServicerID`, `SME`, `SaveLocation`, `DayAdjust`, `Templates/Main` edits. No changes to those expected values.

---

### 9.2 Frontend Tests — `extension/test/`

Files affected: any test that calls `resolveCurrentFieldValue()` or `renderEditDiff()`.

**New tests for `resolveCurrentFieldValue()`:**
```javascript
// TC-FR302-01
it('save_location reads save_path from job_detail response', () => {
  const result = resolveCurrentFieldValue(
    { data: { job: { save_path: 'M:\\Data\\' } } }, 'save_location'
  );
  expect(result).toBe('M:\\Data\\');
});

// TC-FR302-02
it('sender_filter reads sender from job_detail response', () => {
  const result = resolveCurrentFieldValue(
    { data: { job: { sender: '@olddomain.com' } } }, 'sender_filter'
  );
  expect(result).toBe('@olddomain.com');
});

// TC-FR302-03
it('name reads job_name from job_detail response', () => {
  const result = resolveCurrentFieldValue(
    { data: { job: { job_name: 'TestJob' } } }, 'name'
  );
  expect(result).toBe('TestJob');
});

// TC-FR302-04
it('path reads sftp_path from job_detail response', () => {
  const result = resolveCurrentFieldValue(
    { data: { job: { sftp_path: 'M:\\Sweeps\\' } } }, 'path'
  );
  expect(result).toBe('M:\\Sweeps\\');
});

// TC-FR302-05
it('zip_content_filter reads zip_filter from job_detail response', () => {
  const result = resolveCurrentFieldValue(
    { data: { job: { zip_filter: '.*' } } }, 'zip_content_filter'
  );
  expect(result).toBe('.*');
});
```

**New tests for `renderEditDiff()`:**
```javascript
// TC-FR301-01
it('mailbox field renders <Mailbox> tag (not MailboxAddress)', () => {
  const diff = renderEditDiff('TestJob', 'mailbox', 'old@usbank.com', 'new@usbank.com', 'email');
  expect(diff).toContain('<Mailbox>old@usbank.com</Mailbox>');
  expect(diff).toContain('<Mailbox>new@usbank.com</Mailbox>');
  expect(diff).not.toContain('MailboxAddress');
});

// TC-FR301-02
it('sender_filter field renders nested <Filters><From> structure', () => {
  const diff = renderEditDiff('TestJob', 'sender_filter', '@old.com', '@new.com', 'email');
  expect(diff).toContain('<Filters><From>@old.com</From></Filters>');
  expect(diff).toContain('<Filters><From>@new.com</From></Filters>');
  expect(diff).not.toContain('SenderFilter');
});

// TC-FR301-03
it('path field renders <Path> tag (not RemotePath) for SFTP', () => {
  const diff = renderEditDiff('TestJob', 'path', 'M:\\Old\\', 'M:\\New\\', 'sftp');
  expect(diff).toContain('<Path>M:\\Old\\</Path>');
  expect(diff).toContain('<Path>M:\\New\\</Path>');
  expect(diff).not.toContain('RemotePath');
});

// TC-FR301-04
it('save_location field renders <SaveLocation> tag', () => {
  const diff = renderEditDiff('TestJob', 'save_location', 'M:\\Old\\', 'M:\\New\\', 'email');
  expect(diff).toContain('<SaveLocation>M:\\Old\\</SaveLocation>');
  expect(diff).not.toContain('<save_location>');
});
```

**Existing tests that exercise `renderEditDiff`** with `scrubber` and `servicer_id` should still pass without modification — those paths are unchanged.

---

## 10. Rollback Notes

All changes in Phase 12 are reversible by reverting the relevant lines:

- `crud.py` field map changes: reverting the 4 string changes restores prior behaviour
- `participant.js` function changes: reverting `resolveCurrentFieldValue` and `renderEditDiff` bodies restores prior display
- `DOMAIN_KNOWLEDGE` addition: the appended section can be removed without affecting any logic
- Tool description / playbook string changes: purely LLM-context changes with no runtime effects

No database migrations, no new files, and no changes to the `job_detail` API response format are included in Phase 12.

---

## 11. Known Gaps Deferred to Future Phases

| Gap | Description | Suggested Phase |
|---|---|---|
| `subject_filter` round-trip | `EmailJob` model and DB schema lack this field; `edit_job(subject_filter=X)` writes `<SubjectFilter>` but parser never reads it back | Phase 13: EmailJob schema expansion |
| `import_did` round-trip | Same write-only issue; `ImportDID` is not in the DB cache, so `resolveCurrentFieldValue` always returns `''` for this field | Phase 13: EmailJob schema expansion |
| Raw XML preview endpoint | A backend endpoint returning the literal XML string for a job would allow accurate clone confirmation instead of LLM-reconstructed XML | Phase 13 or separate |
| `last_email` and `queue_one_file` in `job_detail` | These are returned by the API fallback but may not always be populated from SQLite cache — minor inconsistency | Phase 13: cache completeness audit |
