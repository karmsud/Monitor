# Phase 12 PRD — Settings.xml Schema Centralization & Field Mapping Correctness
## FRP Agent VS Code Extension

**Document type:** Product Requirements Document
**Phase:** 12
**Status:** Draft — awaiting approval before implementation begins
**Date:** March 2026
**Author:** Engineering (GitHub Copilot assisted)

---

## 1. Executive Summary

Phase 12 gives the FRP Agent accurate, centralised knowledge of how Settings.xml jobs are structured as XML. Today the agent invents XML element names from abstract model labels, contains confirmed bugs that silently write the wrong XML element during create/edit operations, and has no consistent mechanism for any pipeline to suggest job creation using correct field names. After this phase, every tool, handler, and playbook draws from a single authoritative XML schema in `DOMAIN_KNOWLEDGE`, backend field maps produce structurally correct XML, and the LLM can reason about job configuration with the same accuracy it reasons about tblTemplateStaging.

---

## 2. Problem Statement

### 2.1 The Abstraction Gap

The FRP Agent represents each job as a display model — a simplified, human-readable dict returned by `job_detail`. This model uses renamed keys for developer convenience (e.g., `"sender"`, `"save_path"`, `"sftp_path"`) but these keys differ from the actual XML element names (`<Filters><From>`, `<SaveLocation>`, `<Path>`). Neither `DOMAIN_KNOWLEDGE` nor any playbook explains this mapping.

When the LLM is asked to confirm a job clone or produce a preview, it reverse-engineers XML structure from display model key names — and gets it wrong every time.

**Example: cloning `PRET2024RPL2_Selene_6007` (observed agent output):**

```
Agent produced:                   Correct XML:
<Job Name="TestDeal1">            <TestDeal1>
  <ServicerID>6009</ServicerID>     <ServicerID>6009</ServicerID>
  <Mailbox>rptent@usbank.com</Mailbox>  <Mailbox>rptent@usbank.com</Mailbox>
  <SenderFilter>earl.cruz@...</SenderFilter>  <Filters>
  <Scrubber>Outlook_Queuer_x</Scrubber>    <From>earl.cruz@...</From>
  <MatchMode>Subject</MatchMode>        <Attachments>True</Attachments>
  <SaveLocation>M:\...</SaveLocation>  </Filters>
</Job>                              <Parsers>
                                      <DetachFileSubject>.*</DetachFileSubject>
                                    </Parsers>
                                    ...
                                  </TestDeal1>
```

Specific errors: `<Job Name="...">` wrapper doesn't exist; `<SenderFilter>`, `<Scrubber>`, and `<MatchMode>` are all invented; `<Filters>`, `<Parsers>`, `<Templates>`, `<Folder>`, `<SME>`, `<QueueOneFile>`, and `<DayAdjust>` are missing entirely.

### 2.2 Confirmed Backend Bugs — Wrong XML Tags Written

The backend `EMAIL_FIELD_MAP` and `SFTP_FIELD_MAP` in `crud.py` are the definitive field-name-to-XML-element mappings used by `create_job` and `edit_job`. Three of these mappings are wrong — the map targets a different element name than the parser reads:

| Field | Map writes | Parser reads | Effect |
|---|---|---|---|
| `mailbox` (email) | `<MailboxAddress>` | `<Mailbox>` | `edit_job(mailbox=X)` creates orphan `<MailboxAddress>X</MailboxAddress>` while the real `<Mailbox>` retains the old value |
| `sender_filter` (email) | `<SenderFilter>` | `<Filters><From>` | Creates orphan `<SenderFilter>`, actual sender filter unchanged |
| `path` (SFTP) | `<RemotePath>` | `<Path>` | Creates orphan `<RemotePath>`, actual path unchanged |

These bugs mean any create or edit operation targeting these three fields produces a silently wrong result — the XML is written without error, but the intended field is not changed.

### 2.3 Duplicated and Inconsistent Client-Side Mappings

The frontend has its own copies of the field→XML mappings in two separate functions:

- `renderEditDiff()` contains a hardcoded `tagMap` (11 entries) that duplicates the backend's `EMAIL_FIELD_MAP` — including the same wrong tag names
- `resolveCurrentFieldValue()` contains a second set of field-to-property lookups that use the wrong property names from the `job_detail` API response

Because these live in three separate files and have never been synchronised against the actual XML, they have independently drifted into inconsistency. There is no test that validates frontend↔backend↔XML alignment.

### 2.4 No Knowledge = Invented Tags and Silent Failures

With no XML schema in `DOMAIN_KNOWLEDGE`, the LLM has no reference for:

- What the XML element wrapper for a job looks like (job name IS the element tag)
- Which fields are nested vs direct (`sender_filter` is `<Filters><From>`, not a top-level element)
- Which fields are computed from the XML and never stored (`match_mode` is derived from Parsers; writing `<MatchMode>` to XML would create a phantom element)
- Which fields exist for email-only vs SFTP-only jobs
- What the display-model key names (`"sender"`, `"save_path"`, `"sftp_path"`) correspond to in XML

This knowledge gap affects every pipeline. Triage can't intelligently suggest creating a new job because it doesn't know what fields are required. The CRUD planner can't validate override field names before sending them to the backend. The clone preview is fabricated.

### 2.5 Why Centralise Rather Than Fix Per-Pipeline?

Phase 12 deliberately mirrors the approach of Phase 10's tblTemplateStaging knowledge update: add the definitive reference to `DOMAIN_KNOWLEDGE` once, then have every pipeline consume it by reference. This approach was proved effective for tblTemplateStaging — all five playbooks were updated to reference the shared block rather than maintain private copies of field semantics.

The XML schema knowledge is of the same category: it belongs to the data model layer, not to any single pipeline.

---

## 3. Goals

### 3.1 In Scope (Phase 12)

| ID | Goal |
|---|---|
| G-1 | Centralise the authoritative Settings.xml job schema (email and SFTP) in `DOMAIN_KNOWLEDGE` so all LLM contexts share the same reference. |
| G-2 | Fix the three confirmed backend field map bugs (`mailbox`, `sender_filter`, `path`) so create/edit operations write to the correct XML elements. |
| G-3 | Fix the frontend `renderEditDiff()` tagMap and nested-field handling to produce correct before/after XML previews. |
| G-4 | Fix `resolveCurrentFieldValue()` to use the correct property names from the `job_detail` API response. |
| G-5 | Update the `create_job` tool's `overrides` parameter description with an enumerated list of valid field names and their XML element targets. |
| G-6 | Update `CRUD_PLANNING_PLAYBOOK` with XML structural awareness so the LLM can plan create/edit operations without inventing field names. |
| G-7 | Update `EMAIL_TRIAGE_PLAYBOOK` with a "no matching job" pathway that can suggest job creation using the correct XML fields. |
| G-8 | Update all remaining playbooks to reference the shared XML schema from `DOMAIN_KNOWLEDGE`. |
| G-9 | All existing JS tests (56) and Python tests pass unchanged after the changes. |

### 3.2 Out of Scope (Phase 12)

- `subject_filter` round-trip fix — this field has a write-only bug (can be written via `edit_job` but `EmailJob` model and DB schema have no corresponding field to read it back). Fixing requires schema migration; deferred to a future phase.
- `import_did` round-trip fix — same issue as `subject_filter`; deferred.
- Raw XML preview endpoint — a backend endpoint that returns the literal XML string for a job. Highly desirable and referenced in analysis but deferred to allow Phase 12 to ship the foundational knowledge layer first.
- Cancellation, progress, or other Phase 11-category concerns.
- New tools or commands.

---

## 4. User Stories

### Epic 1 — Global XML Schema in DOMAIN_KNOWLEDGE (S-1xx)

**Epic goal:** Add a "Settings.xml Job Schema" section to `DOMAIN_KNOWLEDGE` that every LLM context can reference.

---

**S-101 — Email job XML structure reference**

> *As the FRP Agent LLM I need to know the exact XML element hierarchy for an email job so that any output I produce about job structure (previews, suggestions, confirmations) uses real element names, not invented aliases.*

**Current state:** `DOMAIN_KNOWLEDGE` describes Settings.xml in one line: `"Fields: JobName, ServicerID, Sender, Scrubber (template), MatchMode, SaveLocation"`. These are display-model labels, not XML element names. The element `<Filters><From>` is completely absent; the concept that `<MatchMode>` does not exist is not mentioned; the job-name-as-tag convention is nowhere documented.

**Target state:** A new sub-section "Settings.xml Job Schema — Email Jobs" documents:
- The `<MailboxCollection><JOB_NAME>...</JOB_NAME></MailboxCollection>` outer structure
- Every XML child element of an email job with its meaning
- Which fields are nested under `<Filters>`, `<Parsers>`, and `<Templates>`
- A field-name → XML element mapping table
- Computed vs stored field distinction (match_mode, sender, scrubber as aliases)
- Display model key names vs XML element names (the full translation table)

**Acceptance criteria:**

```gherkin
Feature: LLM XML structural knowledge

  Scenario: LLM is asked to show the XML for a cloned job
    Given the LLM has been given DOMAIN_KNOWLEDGE with the XML schema section
    When it produces a job clone preview
    Then the wrapper element IS the job name (<TestDeal1>...</TestDeal1>)
    And sender filter appears as <Filters><From>...</From></Filters>
    And scrubber appears as <Templates><Main>...</Main></Templates>
    And <SenderFilter>, <Scrubber>, <MatchMode> do NOT appear

  Scenario: LLM is asked about job fields
    Given the LLM has DOMAIN_KNOWLEDGE
    When asked "what fields does an email job have?"
    Then the response lists real XML element names
    And notes that match_mode is computed, not a stored element
```

---

**S-102 — SFTP job XML structure reference**

> *As the FRP Agent LLM I need to know the XML element hierarchy for an SFTP job, including that `<Path>` (not `<RemotePath>`) is the source folder element and that `<SkipList>` and `<IgnoreList>` are direct elements.*

**Target state:** A new sub-section "Settings.xml Job Schema — SFTP Jobs" documents the `<FolderCollection><JOB_NAME>...</JOB_NAME></FolderCollection>` structure and every child element with its meaning.

---

### Epic 2 — Backend Field Map Bug Fixes (S-2xx)

**Epic goal:** Three confirmed wrong XML element names in the backend cause silent data corruption during create/edit operations. These must be corrected.

---

**S-201 — Fix `EMAIL_FIELD_MAP["mailbox"]`**

> *As a user who edits a job's mailbox via the FRP Agent I want the correct `<Mailbox>` element to be updated, not a phantom `<MailboxAddress>` element that the system ignores.*

**Current code (`crud.py` line 22):**
```python
"mailbox":         "MailboxAddress",
"mailbox_address": "MailboxAddress",
```
**Parser reads:** `self._text(element, "Mailbox")`

**Fix:** Change to:
```python
"mailbox":         "Mailbox",
"mailbox_address": "Mailbox",   # keep alias, fix target
```

**Acceptance criteria:**
```gherkin
  Scenario: edit_job with field=mailbox updates <Mailbox> element
    Given a job with <Mailbox>old@usbank.com</Mailbox>
    When edit_job is called with field="mailbox", value="new@usbank.com"
    Then the saved XML contains <Mailbox>new@usbank.com</Mailbox>
    And no <MailboxAddress> element exists in the job
```

---

**S-202 — Fix `EMAIL_FIELD_MAP["sender_filter"]`**

> *As a user who sets a job's sender filter via the FRP Agent I want `<Filters><From>` to be updated, not a phantom `<SenderFilter>` element.*

**Current code (`crud.py` line 33):**
```python
"sender_filter": "SenderFilter",
```
**Parser reads:** `_child_dict(element, "Filters")["From"]`

**Fix:**
```python
"sender_filter": "Filters/From",
```

The backend's `edit_job` already handles nested paths (splits on `"/"`) — this change requires no logic changes, only the mapping string.

**Acceptance criteria:**
```gherkin
  Scenario: edit_job with field=sender_filter updates <Filters><From>
    Given a job with <Filters><From>@oldomain.com</From></Filters>
    When edit_job is called with field="sender_filter", value="@newdomain.com"
    Then the saved XML contains <Filters><From>@newdomain.com</From></Filters>
    And no top-level <SenderFilter> element exists
```

---

**S-203 — Fix `SFTP_FIELD_MAP["path"]`**

> *As a user who changes an SFTP job's source folder via the FRP Agent I want `<Path>` to be updated, not a phantom `<RemotePath>` element.*

**Current code (`crud.py` line 44):**
```python
"path": "RemotePath",
```
**Parser reads:** `self._text(element, "Path")`

**Fix:**
```python
"path": "Path",
```

---

### Epic 3 — Frontend Code Correctness (S-3xx)

**Epic goal:** Fix the two helper functions in `participant.js` that independently duplicate and misuse field-to-XML mappings.

---

**S-301 — Fix `renderEditDiff()` tag map and nested handling**

> *As a user confirming a job edit I want the XML preview to show the real XML element names and structure so I can visually verify the change is correct.*

**Current problems:**
1. `tagMap` has `mailbox → 'MailboxAddress'` (wrong — should be `'Mailbox'`)
2. `tagMap` has `path → 'RemotePath'` (wrong — should be `'Path'`)
3. `sender_filter` is in `tagMap` as `'SenderFilter'` but should render as nested `<Filters><From>`, same as how `scrubber` renders as nested `<Templates><Main>`
4. There is no `save_location` entry in `tagMap` (falls back to the field name as tag)

**Target state:** All tag names corrected; `sender_filter` rendered as nested XML; `save_location` entry added.

**Acceptance criteria:**
```gherkin
  Scenario: Edit mailbox shows <Mailbox> in before/after
    Given a job with mailbox = "old@usbank.com"
    When renderEditDiff is called with field="mailbox", newValue="new@usbank.com"
    Then the preview contains <Mailbox>old@usbank.com</Mailbox>
    And <MailboxAddress> does NOT appear

  Scenario: Edit sender_filter renders nested XML
    Given a job with sender = "@olddomain.com"
    When renderEditDiff is called with field="sender_filter", newValue="@newdomain.com"
    Then the preview shows <Filters><From>@olddomain.com</From></Filters>
    And <Filters><From>@newdomain.com</From></Filters>
    And <SenderFilter> does NOT appear

  Scenario: Edit SFTP path shows <Path> element
    Given an SFTP job
    When renderEditDiff is called with field="path"
    Then the preview shows <Path>...</Path>
    And <RemotePath> does NOT appear
```

---

**S-302 — Fix `resolveCurrentFieldValue()` property lookups**

> *As a developer calling `resolveCurrentFieldValue()` I want it to correctly read the current value from the `job_detail` API response so the before/after diff shows the real current value, not an empty placeholder.*

**Current problems** — the `job_detail` response uses different property keys than what `resolveCurrentFieldValue` expects:

| Edit field | Current code looks for | `job_detail` actually returns | Effect |
|---|---|---|---|
| `save_location` | `job.save_location` | `job.save_path` | Always returns `''` |
| `sender_filter` | `job.sender_filter` | `job.sender` (or `job.filters?.From`) | Always returns `''` |
| `name` | `job.name` | `job['job_name']` | Always returns `''` |
| `path` (SFTP) | `job.path` | `job['sftp_path']` | Always returns `''` |
| `zip_content_filter` (SFTP) | `job.zip_content_filter` | `job['zip_filter']` | Always returns `''` |

**Target state:** Each entry in `fieldMap` reads from the correct property that `job_detail` actually returns.

---

### Epic 4 — Tool Descriptions and Playbook Updates (S-4xx)

**Epic goal:** Every tool description and playbook that could need XML knowledge references the centralised schema.

---

**S-401 — Enhance `create_job` tool `overrides` parameter description**

> *As the FRP Agent LLM I need to know which field names are valid as `overrides` keys so I don't pass invented names like `"sender_filter_address"` or `"template"` without understanding the XML mapping.*

**Current state:** `overrides` description says only `'Optional field overrides to apply (e.g. {"servicer_id": "999"}).'`

**Target state:** The description explicitly lists all valid override field names with their XML element targets, separated by email-only and SFTP-only fields.

---

**S-402 — Update `CRUD_PLANNING_PLAYBOOK` with XML structural awareness**

> *As the FRP Agent CRUD planner I need to know the real field names before I output a plan step invoking `create_job` or `edit_job`, so the plan shows correct values.*

**Current state:** `CRUD_PLANNING_PLAYBOOK` has no XML knowledge — just generic plan/execute instructions.

**Target state:** A "Field Reference" section inside the playbook (or a reference to DOMAIN_KNOWLEDGE) enumerates valid edit_job fields and their XML targets, notes which are email-only/SFTP-only, and explicitly forbids using display-model names (`match_mode`, `sender`) as override keys.

---

**S-403 — Update `EMAIL_TRIAGE_PLAYBOOK` with a "no matching job" creation pathway**

> *As a triage analyst I want the FRP Agent to suggest a concrete job creation plan when no matching job is found for a new sender/mailbox, using correct field names and XML element references.*

**Current state:** The triage playbook has no guidance for the "no matching job found" outcome — the agent currently reports "no match found" and stops.

**Target state:** Step 3 (or a new Step 7) includes: when no email job matches the sender/mailbox, formulate a `create_job` suggestion using the correct fields — mailbox, sender_filter (`<Filters><From>`), parser type (DetachFileSubject for subject-matching or DetachFile for filename-matching), scrubber/template, and servicer_id.

---

**S-404 — Update remaining playbooks to reference XML schema**

> *As the FRP Agent operating in any pipeline I want the XML schema to be available in my prompt context so I can answer schema-related questions accurately regardless of which pipeline I'm in.*

**Affected playbooks:** `JOB_INVESTIGATION_PLAYBOOK`, `SERVICER_INVESTIGATION_PLAYBOOK`, `GENERAL_REASONING_PLAYBOOK`, `ANALYSIS_PLAYBOOK`. Each should have its domain model section updated with a reference to DOMAIN_KNOWLEDGE's XML schema section, the same way they currently reference DOMAIN_KNOWLEDGE for tblTemplateStaging.

---

## 5. Success Criteria

| Criterion | Measurement |
|---|---|
| No invented XML tags in clone/edit previews | LLM produces `<Mailbox>`, `<Filters><From>`, `<Templates><Main>` — not `<MailboxAddress>`, `<SenderFilter>`, `<Scrubber>` |
| Backend write correctness | `edit_job(mailbox=X)` writes `<Mailbox>X</Mailbox>`; `edit_job(sender_filter=X)` writes `<Filters><From>X</From></Filters>`; `edit_job(path=X)` on SFTP writes `<Path>X</Path>` |
| renderEditDiff accuracy | XML diff preview shows correct element names and nesting for all 17 editable fields |
| resolveCurrentFieldValue accuracy | Before value is always populated (not `''`) for all fields that `job_detail` returns |
| Triage can suggest job creation | Triage pipeline produces a valid `create_job` plan with correct field names when no match is found |
| All 56 JS unit tests pass | No regressions in test suite |
| All Python tests pass | No regressions in backend test suite |

---

## 6. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Existing jobs with phantom `<MailboxAddress>` elements** — if deploy has previously run `edit_job(mailbox=...)`, those jobs have both a correct `<Mailbox>` and a wrong `<MailboxAddress>`. Fixing the map doesn't clean up old data. | Low (feature likely rarely used before this fix) | Medium | Document the rollback path; note that `<MailboxAddress>` elements are ignored by the parser so they're cosmetic noise, not functional corruption |
| **`Filters/From` nested path creates wrong structure if `<Filters>` block absent** | Low | High | Backend `edit_job` already handles "find-or-create" for nested paths — verified in code review. If `<Filters>` is absent, it will be created. |
| **test suite catches tagMap changes** | Low | Low | renderEditDiff is covered by tests that check the before/after strings — these will need update to reflect correct tags |
| **DOMAIN_KNOWLEDGE increase raises prompt token count** | Medium | Low | XML schema addition is estimated +80-100 tokens — within acceptable range; schema section is reference material, concisely written |

---

## 7. Dependencies

- **Phase 10 complete** — unified `agentLoop`, `TOOL_REGISTRY`, and `executePipelineTool` are prerequisites (already done)
- **Phase 11 complete** — progress feedback (already done, no interaction with Phase 12)
- **No new packages** — all changes are to existing FRP Agent files
- **No database migrations** — the `subject_filter`/`import_did` round-trip fixes are explicitly deferred; no schema changes in Phase 12
