# Phase 9 PRD — Conversational Intelligence Upgrade
## FRP Agent VS Code Extension

**Document type:** Product Requirements Document  
**Phase:** 9  
**Status:** Draft — awaiting approval before implementation begins  
**Date:** March 7, 2026  
**Author:** Engineering (GitHub Copilot assisted)

---

## 1. Executive Summary

Phase 9 replaces the @frp agent's regex-based command parsing with a fully conversational, context-aware, LLM-driven interaction model. After this phase, users can speak to @frp in natural English — exactly as they would speak to a knowledgeable colleague — without memorizing command syntax. The agent will ask clarifying questions when intent is ambiguous, resolve references from conversation history ("that job", "the one we just looked at"), present before/after previews for destructive operations, and require explicit confirmation before any write occurs.

---

## 2. Problem Statement

### 2.1 Current Behaviour (as-is)

The @frp agent today has two interaction modes that create friction:

**Slash-command mode** (e.g., `/jobs edit CMBS_GreyCo set scrubber Outlook_Queuer_x`)  
Every handler — `handleJobEdit`, `handleJobCreate`, `handleDeployRollback` — parses its input with a hardcoded `RegExp`. If the user's phrasing doesn't match the pattern exactly, the handler silently falls through to showing a help block. Users must memorise syntax.

**Natural-language mode** (e.g., `update the scrubber on CMBS_GreyCo`)  
Routing works (Stage 1 classifies, Stage 2 calls the LLM with a scoped tool set), but the `edit_job` tool schema accepts only `prompt: string`. The LLM stuffs job name, field, and value into a single string, which `handleJobEdit` must then parse with the same regex. Any variation in the LLM's phrasing breaks extraction.

Both modes share the same root failure: **LLM intelligence is bypassed at the parameter extraction step by literal string matching**.

Three additional gaps compound the problem:

1. **History is flattened to a string and injected only into Stage 1 and Stage 2 routing prompts**, not into the post-routing tool-call step. The LLM that ultimately calls a tool cannot resolve contextual references like "that job".

2. **Destructive operations use `vscode.window.showWarningMessage({modal: true})`**, a system modal dialog that interrupts VS Code's window focus and provides no preview of what is about to change.

3. **Multi-step CRUD requires the user to issue multiple separate commands**. There is no way to say "create a job from CSMC_Template, rename it GreyCo_v2, and set the scrubber to Outlook_Queuer_x" in a single prompt and have the agent plan and execute all three steps.

### 2.2 User Impact

| Symptom | User experience | Root cause |
|---|---|---|
| `/jobs edit ... set scrubber X` is the only way to edit | Users must look up syntax in help text every time | Regex-gated handler |
| "fix the scrubber on GreyCo" fails silently | User sees help block, no indication of what went wrong | `prompt: string` tool schema |
| "update that job's scrubber" fails even after discussing the job | Agent doesn't know "that job" referred to in history | History not passed to tool-calling LLM |
| Confirmation dialog disrupts window | User loses focus when approving an edit | `showWarningMessage` modal |
| Multi-step CRUD requires multiple commands | High cognitive load for compound operations | No agentic planning |
| SFTP jobs can't be edited via NL or LLM tool | "change the path on SFTPJob_Wells" silently fails | `edit_job` schema has no `xmlType` param; SFTP field enum missing |
| `/triage` requires exact sub-command syntax | "is this email monitored?" with no sub-command gets a help block | Sub-command regex in `handleTriageCommand` |
| `/analyze impact` runs a hidden second LLM call | Brittle; fails on unusual phrasing; extra latency | `impact_analysis` schema `{prompt: string}` forces internal `parseChangeIntent()` LLM parse |

---

## 3. Goals

### 3.1 In Scope (Phase 9)

| ID | Goal |
|---|---|
| G-1 | All CRUD operations (create_job, edit_job, rollback_xml) accept structured LLM-extracted parameters. No regex in any handler. |
| G-2 | The tool-calling LLM always receives full conversation history as structured messages, enabling contextual reference resolution. |
| G-3 | All destructive operations surface a native VS Code diff-style confirmation inside the chat panel before executing. |
| G-4 | The agent can plan and execute multi-step CRUD tasks (e.g., create + edit + validate) from a single natural-language prompt. |
| G-5 | When required information is missing (job name, target value), the agent asks a clarifying question in the chat panel — it never guesses. |
| G-6 | All existing functionality (read queries, pipeline analysis, log search, staging search) is preserved and unaffected. |
| G-7 | 719+ existing tests continue to pass. New tests cover all Phase 9 stories. |
| G-8 | SFTP job configuration operations (create, edit, rollback) are exposed to the LLM with SFTP-specific structured schemas, matching the parity already present in the Python backend. |
| G-9 | The `/triage` and `/analyze` commands become conversational: users can express triage requests and analysis requests in natural English without knowing sub-command syntax. Internal sub-command parsing regex is eliminated from both handlers. |

### 3.2 Out of Scope (Phase 9)

- Hybrid LLM/table rendering (discussed and deferred in Phase 8)
- Any changes to the Python backend — the backend already supports email AND SFTP for all CRUD, triage, and analysis operations
- New slash commands — existing slash commands remain as optional power-user shortcuts; they get smarter (no regex) but their surface doesn't change
- Mobile or web interface
- Full replacement of the Stage-1/Stage-2 classifier with a single unified agentic loop (that is Phase 10's architectural change; Phase 9 makes the pipeline path the preferred path and makes Stage 1 more accurate)

---

## 4. User Stories

### Epic 1 — Structured Tool Schemas (S-1xx)

**Epic goal:** Remove all regex from CRUD handlers by giving the LLM structured output schemas so it extracts `jobName`, `field`, and `value` directly instead of putting everything into a `prompt: string`.

---

**S-101 — edit_job: structured input schema**

> *As a user I want to say "change the scrubber on CMBS_GreyCo to Outlook_Queuer_x" and have it just work, without memorising the `/jobs edit X set Y Z` syntax.*

**Current state:** `edit_job` tool schema accepts `{ prompt: string }`. `handleJobEdit` runs `prompt.match(/^edit\s+["']?(.+?)["']?\s+set\s+(\w+)\s+(.+)$/i)`. Any phrasing that doesn't match this pattern shows the help block.

**Target state:** `edit_job` schema becomes `{ jobName: string, field: string (enum), value: string }`. `handleJobEdit` receives three clean parameters. No regex. The LLM's `enum` constraint on `field` means it will only produce valid field names.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: edit_job structured schema

  Scenario: Natural-language edit with all three parts present
    Given the user types "change the scrubber on CMBS_GreyCo to Outlook_Queuer_x"
    When the NL router calls the edit_job tool
    Then the LLM provides jobName = "CMBS_GreyCo"
    And field = "scrubber"
    And value = "Outlook_Queuer_x"
    And handleJobEdit receives these three values without any regex processing

  Scenario: Variant phrasing — "update", "swap", "set"
    Given the user says "update the template on CMBS_GreyCo to Outlook_Queuer_x"
    When the NL router calls edit_job
    Then field = "scrubber" OR field = "template" (both map to Templates/Main)
    And the edit succeeds

  Scenario: Field name outside the enum
    Given the user says "change the foobar on CMBS_GreyCo to xyz"
    When the LLM cannot map "foobar" to a valid field enum value
    Then the agent asks a clarifying question: "Which field did you want to update?"
    And no backend call is made

  Scenario: Explicit slash command still works
    Given the user types "/jobs edit CMBS_GreyCo set scrubber Outlook_Queuer_x"
    When handleJobCreate is invoked directly
    Then the command succeeds identically to the NL path
```

**Test cases:**
- `TC-S101-01`: LLM tool call produces `{jobName, field, value}` — assert all three non-empty
- `TC-S101-02`: `handleJobEdit({ jobName, field, value })` calls `backendCall('edit_job', ...)` with correct params
- `TC-S101-03`: Missing `value` → clarifying question emitted, no backend call
- `TC-S101-04`: Missing `jobName` → clarifying question emitted, no backend call
- `TC-S101-05`: Unknown `field` value → agent asks which field
- `TC-S101-06`: Slash command path (`/jobs edit X set Y Z`) still routes to same handler and succeeds

---

**S-102 — create_job: structured input schema**

> *As a user I want to say "create a new job from CSMC_Template and name it GreyCo_v2" without quoting syntax.*

**Current state:** `create_job` schema `{ prompt: string }`, handler regex `^create\s+(.+?)\s+from\s+["']?(.+?)["']?\s*$`.

**Target state:** Schema `{ newName: string, templateJob: string, overrides?: object }`.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: create_job structured schema

  Scenario: Create from template in natural language
    Given the user says "create a new job from CSMC_Template and call it GreyCo_v2"
    When the NL router calls create_job
    Then newName = "GreyCo_v2"
    And templateJob = "CSMC_Template"
    And handleJobCreate receives both values without regex

  Scenario: Template job not specified
    Given the user says "create a new job called GreyCo_v2"
    When the LLM cannot determine templateJob
    Then the agent asks "Which existing job should I use as the template?"

  Scenario: Template job does not exist in XML
    Given the user says "create GreyCo_v2 from NonExistentTemplate"
    When backendCall('create_job') returns an error
    Then the agent shows the error message
    And no file is modified
```

**Test cases:**
- `TC-S102-01`: Structured params extracted correctly by LLM
- `TC-S102-02`: Missing `templateJob` → clarifying question
- `TC-S102-03`: Non-existent template → error surfaced, no state change
- `TC-S102-04`: Existing slash command path still works

---

**S-103 — rollback_xml: structured input schema**

> *As a user I want to say "roll back to the backup from this morning" and have the agent resolve which backup file to use.*

**Current state:** `rollback` tool takes `{ prompt: string }`, handler regex parses out the filename.

**Target state:** Schema `{ backupFile: string }`. LLM resolves from backup list context if user says "this morning's backup".

**Acceptance criteria (Gherkin):**

```gherkin
Feature: rollback structured schema

  Scenario: Explicit backup file name
    Given the user says "roll back to Settings_20260307_092000.xml"
    When the NL router calls rollback
    Then backupFile = "Settings_20260307_092000.xml"

  Scenario: Ambiguous backup reference
    Given the user says "roll back to this morning's backup"
    And conversation history contains a list_backups result showing "Settings_20260307_092000.xml"
    When the LLM resolves the reference
    Then backupFile = "Settings_20260307_092000.xml"
    And the agent shows a confirmation diff before executing

  Scenario: No backup files available
    Given the user says "roll back"
    And there are no backup files
    Then the agent says "No backup files found. Nothing to roll back to."
```

**Test cases:**
- `TC-S103-01`: Explicit filename extracted without regex
- `TC-S103-02`: Reference resolved from conversation history
- `TC-S103-03`: Missing file list → helpful error message

---

### Epic 2 — Conversation History in Tool-Calling LLM (S-2xx)

**Epic goal:** Build full conversation history as structured `LanguageModelChatMessage` arrays and pass them to every LLM call that selects or calls tools, enabling contextual reference resolution.

---

**S-201 — buildMessageHistory: structured message array**

> *As a developer I want a function that converts `context.history` (VS Code `ChatRequestTurn[]` / `ChatResponseTurn[]`) into a properly ordered array of `LanguageModelChatMessage` objects that the model's `sendRequest()` accepts.*

**Current state:** `buildConversationContext()` at line 1981 flattens history into a markdown string (`## Recent conversation\n**User:** ...\n**Assistant:** ...`). This string is injected as plain text into Stage 1 and Stage 2 routing prompts, but **not** into the actual tool-calling LLM call in `routeWithinCategory` or the ReAct loop seed messages.

**Target state:** New function `buildMessageHistory(context, systemPrompt)` returns `LanguageModelChatMessage[]`:
```
[ User(systemPrompt), User(turn1), Assistant(turn2), User(turn3), ... User(currentPrompt) ]
```
This replace the `historyContext` string injection in Stage 2 and `reactLoop`. The model now sees a proper multi-turn conversation and can resolve "that job", "it", "the scrubber we just discussed".

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Structured history message array

  Scenario: History turns are correctly typed
    Given the conversation has 3 prior turns
    When buildMessageHistory(context, systemPrompt) is called
    Then the result is an array of LanguageModelChatMessage
    And turn types alternate User → Assistant → User correctly
    And response text is truncated to 2000 chars per turn (same as today)

  Scenario: Empty history
    Given no prior conversation turns exist
    When buildMessageHistory is called
    Then the result contains only [User(systemPrompt), User(currentPrompt)]

  Scenario: History passed to tool-calling LLM in Stage 2
    Given the user previously asked about CMBS_GreyCo
    And now says "update its scrubber to Outlook_Queuer_x"
    When Stage 2 calls model.sendRequest(messages, {tools})
    Then messages includes the prior turns as structured messages
    And the LLM resolves "its" to CMBS_GreyCo
    And edit_job is called with jobName = "CMBS_GreyCo"
```

**Test cases:**
- `TC-S201-01`: `buildMessageHistory` with 6-turn history → 8 messages (system + 6 turns + current)
- `TC-S201-02`: Response text > 2000 chars is truncated
- `TC-S201-03`: `ChatResponseTurn` with no markdown parts is skipped (no empty Assistant message)
- `TC-S201-04`: Stage 2 `routeWithinCategory` passes structured messages (not string) to model
- `TC-S201-05`: `reactLoop` passes structured messages to model

---

**S-202 — Contextual reference resolution: job names**

> *As a user, when I ask about CMBS_GreyCo in one turn and then say "update its scrubber" in the next, the agent resolves "its" to CMBS_GreyCo without me having to repeat the name.*

**Current state:** Stage 2 anaphora resolution note exists in `routingPrompt` (line 1444: *"IMPORTANT — Anaphora resolution: resolve pronouns to explicit entity in SAME message"*) but only applies to within-message references. Cross-turn resolution fails because history is injected as plain text and the model doesn't treat it as conversational context.

**Target state:** With S-201 in place (structured messages), this story is largely achieved automatically. The LLM natively resolves pronoun references across turns when given proper message history. This story adds a targeted integration test and a jitter test (what if the job name is ambiguous across history).

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Cross-turn contextual reference resolution

  Scenario: Pronoun resolved from prior turn
    Given turn N-1: user asked "show me details for CMBS_GreyCo"
    And turn N: user says "update its scrubber to Outlook_Queuer_x"
    When the NL router processes turn N with full history
    Then edit_job is called with jobName = "CMBS_GreyCo"
    And no clarifying question is asked

  Scenario: Ambiguous reference — two jobs mentioned in history
    Given turn N-2: "show details for CMBS_GreyCo"
    And turn N-1: "now show me RMBS_Fay"
    And turn N: "update its scrubber to Outlook_Queuer_x"
    When the LLM cannot confidently resolve "its"
    Then the agent asks "Which job — CMBS_GreyCo or RMBS_Fay?"
    And waits for user response before calling edit_job

  Scenario: "That job" resolved from tool result context
    Given the prior Assistant turn contains a job_detail result for CMBS_GreyCo
    And the user says "fix the scrubber on that job to Outlook_Queuer_x"
    Then jobName = "CMBS_GreyCo" is resolved from the tool result
```

**Test cases:**
- `TC-S202-01`: Single prior job reference → resolved, no clarifying question
- `TC-S202-02`: Two conflicts in history → clarifying question emitted
- `TC-S202-03`: Reference resolved from tool result body (not just user message)

---

**S-203 — Clarifying question flow**

> *As a user, when I give an incomplete command (no job name, no value), the agent asks me the missing piece in the chat panel — it does not show a regex fallback help block.*

**Current state:** When regex fails in `handleJobEdit`, a help block is shown:
```
### Edit a Job
**Usage:** `/jobs edit "<job_name>" set <field> <value>`
```
There is no interactive question-asking; the conversation is terminal.

**Target state:** The LLM, given a structured schema with `required` fields, will naturally ask clarifying questions when it cannot populate required parameters from the prompt and history. The VS Code Chat API streams these as normal markdown text. No "Usage:" help block is shown unless the user explicitly types "help".

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Clarifying questions replace help blocks

  Scenario: Missing job name — agent asks
    Given the user says "update the scrubber to Outlook_Queuer_x"
    And no job name is in conversation history
    When the router processes the prompt
    Then the agent responds with "Which job should I update the scrubber for?"
    And does NOT show the Usage help block
    And does NOT call backendCall

  Scenario: Missing value — agent asks
    Given the user says "fix the scrubber on CMBS_GreyCo"
    When the router processes the prompt
    Then the agent responds "What should the scrubber be changed to?"

  Scenario: User provides the missing piece in next turn
    Given the agent asked "Which job?"
    And the user replies "CMBS_GreyCo"
    Then the agent resolves the pending intent from history
    And calls edit_job with the complete parameters
    And shows the confirmation diff (Story S-303)
```

**Test cases:**
- `TC-S203-01`: No jobName, no history → clarifying question
- `TC-S203-02`: No value → value clarifying question
- `TC-S203-03`: Clarifying answer in next turn → intent completed
- `TC-S203-04`: Help block is NOT shown when LLM succeeds

---

### Epic 3 — Native Confirmation UX (S-3xx)

**Epic goal:** Replace `vscode.window.showWarningMessage({modal: true})` in all three destructive handlers with native VS Code chat confirmation that shows a before/after XML diff inside the chat panel.

---

**S-301 — Before/after XML diff in chat panel**

> *As a user, before approving an edit, I want to see exactly what the XML will look like before and after the change — in the chat panel, not in a system dialog.*

**Current state:** `handleJobEdit` (line 3722) calls `vscode.window.showWarningMessage(...)` showing only the field name and new value. No XML context is shown. The modal grabs window focus away from the chat panel.

**Target state:** Immediately before asking for confirmation, the agent fetches the current job XML via `job_detail`, renders a fenced XML block showing the old value, and a second fenced block showing what the job element will look like after the change. Both blocks appear inline in the chat response stream before the user is asked to confirm.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Before/after XML diff in chat

  Scenario: Edit confirmation shows before and after
    Given the user has confirmed the job name and field to edit
    When the agent is about to call edit_job
    Then it first calls job_detail to get current XML
    And renders:
      **Current value:**
      ```xml
      <Templates><Main>QueueCMBS_Scrubber_x</Main></Templates>
      ```
      **After this change:**
      ```xml
      <Templates><Main>Outlook_Queuer_x</Main></Templates>
      ```
    And asks "Confirm this change? (yes / no)"

  Scenario: User says "no" or "cancel"
    Given the before/after diff was shown
    And the user says "no" or "cancel"
    Then no backend call is made
    And the agent says "Edit cancelled."

  Scenario: job_detail fails before confirmation
    Given job_detail returns an error
    Then the agent shows the error
    And does NOT proceed to the confirmation step
```

**Test cases:**
- `TC-S301-01`: job_detail called before confirmation step
- `TC-S301-02`: Before XML block shown with correct current value
- `TC-S301-03`: After XML block shows correct projected value
- `TC-S301-04`: "no" / "cancel" in response → no backend write

---

**S-302 — Inline confirmation via follow-up prompt (chat-native)**

> *As a user I want to approve or cancel an operation inside the chat panel — not via a system modal dialog that interrupts my workflow.*

**Current state:** Three handlers use `vscode.window.showWarningMessage({modal: true})`: `handleJobCreate` (line 3662), `handleJobEdit` (line 3722), `handleDeployRollback` (line 3972).

**Target state:** Replace all three with an in-chat confirmation pattern. The agent streams the diff/preview, then emits a follow-up suggestion using `stream.button()` (VS Code 1.95+) with "Confirm" and "Cancel" options. The next user turn is checked: if it matches "yes"/"confirm"/"apply" the operation proceeds; any other response cancels.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: In-chat confirmation replaces system modal

  Scenario: Confirm via button click
    Given the agent has shown the before/after diff
    And rendered "Confirm" and "Cancel" buttons in the chat stream
    When the user clicks "Confirm"
    Then the next user turn is "Confirm"
    And the agent proceeds with the backend call

  Scenario: Cancel via button click
    Given the confirm/cancel buttons are shown
    When the user clicks "Cancel"
    Then the agent responds "Operation cancelled."
    And no backend call is made

  Scenario: User ignores buttons and types "yes"
    Given the confirm/cancel buttons are shown
    When the user types "yes"
    Then the agent proceeds with the backend call

  Scenario: showWarningMessage is NOT called
    Given any create, edit, or rollback operation
    When the confirmation workflow runs
    Then vscode.window.showWarningMessage is never invoked
```

**Test cases:**
- `TC-S302-01`: "yes"/"confirm"/"apply" → operation proceeds
- `TC-S302-02`: "no"/"cancel"/"stop" → operation aborted
- `TC-S302-03`: `showWarningMessage` not called in any handler
- `TC-S302-04`: Confirm flow works for create_job
- `TC-S302-05`: Confirm flow works for edit_job
- `TC-S302-06`: Confirm flow works for rollback_xml

---

**S-303 — Automatic backup before every write**

> *As a user I want the agent to automatically create a timestamped backup of Settings.xml before every confirmed write operation, without me having to ask.*

**Current state:** The backend's `edit_job` and `create_job` commands already create backups (confirmed by `test_edit_backup_created`, `test_create_backup_created`). The backup file path is returned in the result's `backup_file` field. However, the chat response does not always surface this to the user.

**Target state:** The LLM final-answer prompt for every write operation explicitly includes the `backup_file` value from the result and instructs the LLM to state it clearly: *"A backup was saved at `Settings_YYYYMMDD_HHmmss.xml`."*

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Backup confirmation surfaced in every write response

  Scenario: Successful edit shows backup path
    Given edit_job returns { success: true, backup_file: "Settings_20260307_120824.xml" }
    When the LLM formats the response
    Then the chat response includes the backup file name
    And the response says the backup was created before the change

  Scenario: Successful create shows backup path
    Given create_job returns { success: true, backup_file: "Settings_20260307_120900.xml" }
    When the LLM formats the response
    Then the backup file name is mentioned in the response
```

**Test cases:**
- `TC-S303-01`: edit_job result with backup_file → response mentions it
- `TC-S303-02`: create_job result with backup_file → response mentions it

---

### Epic 4 — Multi-Step CRUD via Agentic Planning (S-4xx)

**Epic goal:** Extend the existing ReAct loop to handle CRUD operations in multi-step sequences, so a single prompt can trigger create + edit + validate without multiple user turns.

---

**S-401 — CRUD tools available in general_reasoning pipeline**

> *As a user I want to say "create a job from CSMC_Template, call it GreyCo_v2, and set the scrubber to Outlook_Queuer_x" and have all three operations execute in sequence with a single confirmation.*

**Current state:** `general_reasoning` pipeline tool list (line 403–416) explicitly excludes CRUD tools:
```javascript
// Deliberately excludes niche CRUD tools (create_job, edit_job, rollback, etc.)
// that should never be invoked in an open-ended reasoning loop.
```
This was a deliberate Phase 8 safety decision. The reason was valid but too restrictive for compound user intents.

**Target state:** Create a new pipeline `crud_planning` with a dedicated playbook and tool set: `[create_job, edit_job, validate_email, job_detail, search_jobs]`. Stage 1 classifier is updated with a trigger description for this pipeline. `general_reasoning` retains its CRUD exclusion.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: crud_planning pipeline

  Scenario: Multi-step create + edit detected
    Given the user says "create a job from CSMC, call it GreyCo_v2, and set the scrubber to Outlook_Queuer_x"
    When Stage 1 classifies the intent
    Then category = "job_config"
    And mode = "pipeline"
    And pipeline = "crud_planning"

  Scenario: crud_planning pipeline executes in order
    Given the crud_planning pipeline is running
    When the ReAct loop processes the prompt
    Then create_job is called first (step 1)
    Then edit_job is called second with the new job's name (step 2)
    Then validate_email is called third (step 3)
    And the LLM presents a single consolidated confirmation before step 1

  Scenario: Step 2 fails — no partial state
    Given create_job succeeded
    And edit_job fails
    Then the agent reports the failure
    And the backup from step 1 is mentioned as the restore point

  Scenario: general_reasoning DOES NOT have CRUD tools
    Given a general reasoning pipeline query like "morning report"
    When the ReAct loop runs
    Then create_job and edit_job are NOT in the tool set
```

**Test cases:**
- `TC-S401-01`: "create + edit" → Stage 1 produces pipeline = "crud_planning"
- `TC-S401-02`: crud_planning tools list contains exactly the expected set
- `TC-S401-03`: ReAct loop calls tools in correct order
- `TC-S401-04`: general_reasoning tool list does not contain create_job or edit_job
- `TC-S401-05`: Step failure → consolidated error with backup reference

---

**S-402 — Consolidated confirmation for multi-step CRUD**

> *As a user I want to see all planned changes in one confirmation block, not a separate modal for each step.*

**Current state:** Each step in a pipeline calls its own handler, and each handler calls `showWarningMessage` independently. A 3-step CRUD sequence would show 3 separate modals.

**Target state:** The `crud_planning` ReAct loop collects the planned operations into a summary (job name, each field change with before/after) and presents a single confirmation block before executing any step. After user confirmation, all steps execute sequentially with no further interruptions.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Consolidated CRUD confirmation

  Scenario: Multi-step plan presented before execution
    Given the user approved a 3-step plan
    When the crud_planning pipeline prepares to execute
    Then a single confirmation block is shown:
      "I will:
       1. Create job GreyCo_v2 from CSMC_Template
       2. Set scrubber → Outlook_Queuer_x
       3. Validate GreyCo_v2
       Confirm? (yes / no)"
    And no modals are shown

  Scenario: User cancels the plan
    Given the plan was shown
    And the user says "no"
    Then no backend calls are made
    And "Plan cancelled." is shown
```

**Test cases:**
- `TC-S402-01`: Plan summary shows all steps before execution
- `TC-S402-02`: Cancel → zero backend writes
- `TC-S402-03`: Confirm → all steps execute in sequence

---

## 5. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Response latency for single tool operations (edit, create) does not increase by more than 1 LLM call vs. today |
| NFR-2 | Clarifying question responses must appear within the existing model response timeout (90s) |
| NFR-3 | All existing 719 pytest tests continue to pass after Phase 9 changes |
| NFR-4 | No new Python backend changes required for Phase 9 (all changes are in `extension/chat/participant.js`) |
| NFR-5 | `showWarningMessage` is called zero times for any of the three operations covered in S-302 after Phase 9 |
| NFR-6 | History passed to model is capped at 6 turns (existing behaviour) to prevent context bloat |

---

## 6. Success Metrics

| Metric | Baseline (Phase 8) | Target (Phase 9) |
|---|---|---|
| Regex patterns in CRUD handlers | 3 (edit, create, rollback) | 0 |
| `showWarningMessage` calls for CRUD | 3 | 0 |
| % of NL edit prompts that succeed without explicit syntax | ~40% (only when phrasing matches LLM reformatting exactly) | >95% |
| Multi-step CRUD from single prompt | Not possible | Supported (up to 5 steps) |
| Contextual reference resolution ("that job") | Fails (history not in tool LLM) | Works when unambiguous |

---

## 7. Dependencies

| Dependency | Status |
|---|---|
| VS Code API `^1.95.0` (already in `package.json`) | Met — confirmed in `extension/package.json` |
| `vscode.LanguageModelToolCallPart` available | Runtime-checked at line 1837 (guard exists) |
| `stream.button()` for in-chat confirm buttons | Available in 1.95+ — requires validation |
| Python backend `edit_job`, `create_job`, `rollback_xml` commands | Already implemented and tested |
| `EMAIL_FIELD_MAP` includes `scrubber`/`template` | Done in Phase 8.5 |
| Python backend `SFTP_FIELD_MAP` and `JobCrudEngine(xml_type='sftp')` | Already implemented — no changes needed |
| `parseChangeIntent()` function to delete | In `handleAnalyzeCommand` at ~line 3350 |

---

## 8. Goal × Tool Applicability Matrix

This matrix answers: *which of the 4 goals touches which of the 36 tools, and why?*

| Tool | Category | G1: Structured Schema | G2: History | G3: Confirmation | G4: Agentic |
|---|---|---|---|---|---|
| `search_jobs` | job_config | Already structured | ✓ "search jobs like that one" | — | ✓ |
| `job_detail` | job_config | Already structured | ✓ | — | ✓ |
| `validate_email` | job_config | Already structured | ✓ | — | ✓ analysis_pipeline |
| `validate_sftp` | job_config | Already structured | ✓ | — | ✓ analysis_pipeline |
| `templates` | job_config | Already structured | ✓ | — | ✓ |
| `create_job` | job_config | **Yes — prompt→{newName,templateJob,xmlType}** | ✓ "that template" | **Yes — confirm before create** | ✓ crud_planning |
| `edit_job` | job_config | **Yes — prompt→{jobName,field,value,xmlType}** | ✓ "that job"/"its" | **Yes — diff + confirm** | ✓ crud_planning |
| `deal_lookup` | deal_mapping | Already structured | ✓ "that servicer" | — | ✓ |
| `servicer_dossier` | deal_mapping | Already structured | ✓ | — | ✓ servicer_investigation |
| `coverage_gaps` | deal_mapping | **Yes — drop prompt:string** | ✓ | — | ✓ analysis_pipeline |
| `orphan_detection` | deal_mapping | Already structured (no params) | — | — | ✓ |
| `collision_detection` | deal_mapping | Already structured (no params) | — | — | ✓ |
| `template_status` | processing | Already structured | ✓ "same template" | — | ✓ |
| `processing_history` | processing | Already structured | ✓ | — | ✓ |
| `failure_analysis` | processing | Already structured | ✓ | — | ✓ analysis_pipeline |
| `source_trace` | processing | Already structured | ✓ | — | ✓ |
| `manual_queue` | processing | Already structured | ✓ | — | ✓ |
| `processing_duration` | processing | Already structured | ✓ | — | ✓ |
| `deal_pipeline` | processing | Already structured | ✓ "same deal" | — | ✓ |
| `staging_search` | processing | Already structured | ✓ | — | ✓ |
| `sync_logs` | logs_ops | Already structured (no params) | — | — | — |
| `daily_summary` | logs_ops | Already structured | ✓ | — | ✓ |
| `did_failures` | logs_ops | Already structured | ✓ | — | ✓ |
| `job_health` | logs_ops | Already structured | ✓ "that job" | — | ✓ analysis_pipeline |
| `deal_activity` | logs_ops | Already structured | ✓ "same deal" | — | ✓ |
| `log_trends` | logs_ops | Already structured | ✓ | — | ✓ |
| `log_performance` | logs_ops | Already structured | ✓ | — | ✓ analysis_pipeline |
| `save_settings` | deployment | Already structured | ✓ | **Yes — diff + confirm** | ✓ deploy_pipeline |
| `list_backups` | deployment | Already structured | ✓ | — | ✓ |
| `xml_diff` | deployment | Already structured | ✓ | — | ✓ |
| `rollback` | deployment | **Yes — prompt→{backupFile}** | ✓ "this morning's backup" | **Yes — diff + confirm** | ✓ deploy_pipeline |
| `triage_email` | system_admin | **Yes — prompt→{sender,subject,msgPath,mode}** | ✓ "that sender again" | — | ✓ email_triage (already has pipeline) |
| `consolidation_analysis` | system_admin | Already structured (no params) | — | — | ✓ analysis_pipeline |
| `impact_analysis` | system_admin | **Yes — prompt→{changeType,targetJob,...}** | ✓ "that servicer" | — | ✓ analysis_pipeline |
| `system_health` | system_admin | Already structured (no params) | — | — | ✓ analysis_pipeline |
| `agent_status` | system_admin | Already structured (no params) | — | — | — |

**Summary counts:**
- G1 (structured schemas needed): **6 tools** — `create_job`, `edit_job`, `rollback`, `triage_email`, `impact_analysis`, `coverage_gaps`
- G2 (history benefits routing): **~28 tools** — all entity-specific tools where pronouns/references can appear
- G3 (confirmation needed): **5 operations** — `create_job`, `edit_job`, `rollback`, `save_settings(email)`, `save_settings(sftp)`
- G4 (agentic loop participant): **34 tools** — all except `sync_logs` and `agent_status` (stateless/administrative)

---

## 9. User Stories (continued)

### Epic 5 — SFTP CRUD Parity (S-5xx)

**Epic goal:** Expose SFTP job create/edit/rollback to the LLM with distinct SFTP field schemas, matching the backend capability already present in `SFTP_FIELD_MAP`. A user should be able to say *"change the remote path on SFTPJob_Wells to /data/bonds/wells/"* and have it route to an SFTP edit with `xmlType=sftp`.

**Why this was missing:** The Phase 8 TRD TRD exposed `xmlType` only in `buildToolArgs` (defaulting to `'email'`) but never added `xmlType` to the LLM-facing tool schema. The LLM had no way to signal "sftp". SFTP fields (`path`, `dsn`, `skip_list`) were never in the field enum.

---

**S-501 — edit_job: add xmlType + SFTP field enum**

> *As a user I want to edit SFTP monitoring jobs with the same NL flexibility as email jobs.*

**Target state:**
- `edit_job` schema gains required `xmlType: enum('email','sftp')`
- `field` enum becomes type-dependent (described in tool description text; schema uses a combined flat enum including all email AND SFTP fields; the LLM selects the correct subset based on `xmlType`)
- SFTP-only fields: `path`, `dsn`, `sme`, `save_location`, `skip_list`, `ignore_list`, `zip_content_filter`, `day_adjust`
- Email-only fields: `mailbox`, `folder`, `subject_filter`, `sender_filter`, `scrubber`, `template`, `import_did`, `last_email`, `queue_one_file`
- Shared fields: `name`, `servicer_id`

**Acceptance criteria (Gherkin):**

```gherkin
Feature: SFTP job editing via NL

  Scenario: Edit SFTP job remote path
    Given the user says "change the remote path on SFTPJob_Wells to /data/bonds/wells/"
    When the NL router calls edit_job
    Then xmlType = "sftp"
    And field = "path"
    And value = "/data/bonds/wells/"
    And backendCall('edit_job', {jobName, field, value, xmlType: 'sftp'}) is called

  Scenario: Edit SFTP job DSN
    Given the user says "update the DSN on SFTPJob_Ocwen to PROD_SFTP_OCWEN"
    When the NL router processes the request
    Then xmlType = "sftp"
    And field = "dsn"
    And value = "PROD_SFTP_OCWEN"

  Scenario: Confirmation shows SFTP XML structure
    Given the user is editing an SFTP job
    When the before/after diff is rendered
    Then the diff shows <RemotePath> and <DSN> elements (not email elements)
```

**Test cases:**
- `TC-S501-01`: SFTP NL phrase → xmlType=sftp extracted by LLM
- `TC-S501-02`: SFTP field name resolved to SFTP_FIELD_MAP key
- `TC-S501-03`: `resolveCurrentFieldValue` returns SFTP field values for xmlType=sftp
- `TC-S501-04`: `renderEditDiff` renders SFTP XML tags not email XML tags

---

**S-502 — create_job: add xmlType for SFTP job creation**

> *As a user I want to say "create an SFTP job from SFTPJob_Template and call it SFTPJob_NewServicer" and have it create an SFTP job, not an email job.*

**Target state:** `create_job` schema gains `xmlType: enum('email','sftp')` defaulting to `'email'`. The LLM infers `xmlType` from context (if the template job name starts with `SFTP` or if the user says "SFTP job", the LLM provides `xmlType=sftp`).

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Create SFTP job via NL

  Scenario: Create SFTP job from template
    Given the user says "create an SFTP job from SFTPJob_Template and call it SFTPJob_NewServicer"
    When the NL router calls create_job
    Then xmlType = "sftp"
    And newName = "SFTPJob_NewServicer"
    And templateJob = "SFTPJob_Template"
```

**Test cases:**
- `TC-S502-01`: "SFTP job" in prompt → xmlType=sftp
- `TC-S502-02`: Email default → xmlType=email when not mentioned
- `TC-S502-03`: Confirmation diff shows SFTP template XML structure

---

**S-503 — Confirmation UX for SFTP operations**

Same as S-301/S-302 but explicitly verified for SFTP operations (job name, SFTP-specific XML fields, backup created from SFTP Settings.xml path).

**Test cases:**
- `TC-S503-01`: SFTP edit confirmation shows `<RemotePath>` before/after
- `TC-S503-02`: SFTP create confirmation shows SFTP template job XML
- `TC-S503-03`: Backup created at SFTP Settings.xml path (not email path)

---

### Epic 6 — Command Intelligence: /triage and /analyze (S-6xx)

**Epic goal:** Eliminate internal sub-command parsing regex from `handleTriageCommand` and `handleAnalyzeCommand`, replace with structured tool schemas and (for complex health/analysis) a new `analysis_pipeline`. Users can interact with `/triage` and `/analyze` in natural English — the agent figures out the operation from context.

---

**S-601 — triage_email: structured schema**

> *As a user I want to say "is this email from reports@wellsfargo.com about Q4 Bonds monitored?" without knowing `/triage verify` or `/triage match`.*

**Current state:** `triage_email` tool schema is `{prompt: string}`. `handleTriageCommand` uses regex patterns (`/^verify\b/i`, `/^match\b/i`, `/^new\b/i`) to route to sub-operations. Natural language triage without a verb prefix gets the help block.

**Target state:** `triage_email` tool schema becomes:
```json
{
  "sender":  {"type": "string", "description": "Sender email address"},
  "subject": {"type": "string", "description": "Email subject line"},
  "msgPath": {"type": "string", "description": "Path to .msg file"},
  "mode":    {"type": "string", "enum": ["verify","match","new"], "description": "defaults to 'match' if sender/subject provided, 'verify' if msgPath provided"}
}
```
`handleTriageCommand` retains its internal sub-command logic for `required` fields but also handles the tool-call path without regex.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Conversational triage via structured schema

  Scenario: Sender-only triage (no sub-command required)
    Given the user says "is reports@wellsfargo.com monitored?"
    When the NL router calls triage_email
    Then sender = "reports@wellsfargo.com"
    And mode = "match"
    And backendCall('triage_match', {sender}) is called

  Scenario: .msg file path extracted implicitly
    Given the user says "check this email: C:\\emails\\wf_q4.msg"
    When the NL router calls triage_email
    Then msgPath = "C:\\emails\\wf_q4.msg"
    And mode = "verify"

  Scenario: Slash command still works
    Given the user types "/triage verify C:\\emails\\wf_q4.msg"
    Then the slash command path executes correctly
    And the tool-call path is not needed
```

**Test cases:**
- `TC-S601-01`: Sender extracted without sub-command
- `TC-S601-02`: Subject extracted without sub-command
- `TC-S601-03`: .msg path → mode=verify auto-inferred
- `TC-S601-04`: Slash sub-command path still routes correctly via `handleTriageCommand`

---

**S-602 — impact_analysis: structured schema, delete parseChangeIntent()**

> *As a user I want to say "what if we delete job Ocwen" without needing `--change-type` flags. As a developer, the `parseChangeIntent()` internal LLM call is eliminated.*

**Current state:** `impact_analysis` tool schema `{prompt: string}`. `handleAnalyzeCommand` calls `parseChangeIntent(description, token)` which makes a **second LLM call** to `gpt-4o` to parse the description into a ChangeSpec. This adds latency and can fail on unusual phrasing.

**Target state:** `impact_analysis` tool schema becomes:
```json
{
  "changeType":      {"type": "string", "enum": ["delete_job","rename_did","change_filter","move_servicer","change_servicer_id"]},
  "targetJob":       {"type": "string"},
  "targetDid":       {"type": "string"},
  "targetCompanyId": {"type": "number"},
  "newValue":        {"type": "string"},
  "description":     {"type": "string", "description": "Human-readable description of the proposed change (shown in output)"}
}
```
`parseChangeIntent()` is **deleted**. The routing LLM extracts the structured parameters directly.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Structured impact analysis schema

  Scenario: Delete job expressed in natural language
    Given the user says "what if we delete the Ocwen job?"
    When the NL router calls impact_analysis
    Then changeType = "delete_job"
    And targetJob = "Ocwen" (or resolved job name from search)
    And parseChangeIntent() is never called

  Scenario: Rename DID impact
    Given the user says "simulate renaming ImportDID C88 to OCW88"
    When impact_analysis is called
    Then changeType = "rename_did"
    And targetDid = "C88"
    And newValue = "OCW88"
```

**Test cases:**
- `TC-S602-01`: NL delete job → changeType extracted by router LLM, not internal LLM
- `TC-S602-02`: `parseChangeIntent` function does not exist after Phase 9
- `TC-S602-03`: Slash command `/analyze impact --change-type delete_job` still works

---

**S-603 — analysis_pipeline: agentic health and analysis**

> *As a user I want to say "how is the system doing?" and receive a comprehensive health report that the agent assembled by calling multiple checks, not a single monolithic backend call.*

**Current state:** `/analyze health` → one `backendCall('analyze_health')` → large aggregated JSON → one LLM summary. The LLM cannot drill in, ask follow-up questions, or cross-reference findings.

**Target state:** New `analysis_pipeline` in `PIPELINE_DEFINITIONS` with tools:
```
['validate_email', 'validate_sftp', 'coverage_gaps', 'failure_analysis',
 'log_performance', 'system_health', 'job_health', 'daily_summary']
```
Stage 1 classifier routes broad health/analysis queries to this pipeline. The LLM calls tools in whatever order is most relevant, aggregates findings, prioritizes issues, and synthesizes a rich response. The `system_health` backend tool remains available for backwards-compat but is no longer the only path.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Agentic health analysis

  Scenario: "How is the system doing?" routes to analysis_pipeline
    Given the user asks "how is the system doing overall?"
    When Stage 1 classifies intent
    Then pipeline = "analysis_pipeline"
    And the ReAct loop starts with tools from analysis_pipeline tool set

  Scenario: LLM calls multiple tools to assemble health report
    Given the analysis_pipeline is running
    When the ReAct loop processes "system health check"
    Then validate_email is called (finds issues)
    And failure_analysis is called (finds recent failures)
    And log_performance is called (finds underperforming jobs)
    And the LLM synthesizes a prioritized action list from the combined results

  Scenario: Targeted analysis still works
    Given the user asks "what's the consolidation status?"
    When Stage 1 classifies intent
    Then pipeline = "analysis_pipeline"
    And the LLM calls only consolidation_analysis (not all tools)
```

**Test cases:**
- `TC-S603-01`: "system health" → pipeline=analysis_pipeline (classifier test)
- `TC-S603-02`: analysis_pipeline tool list contains all expected tools
- `TC-S603-03`: ReAct loop calls ≥ 2 tools for broad health query
- `TC-S603-04`: Single-topic analysis → only relevant tool called

---

## 10. Revised Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Response latency for single tool operations (edit, create) does not increase by more than 1 LLM call vs. today |
| NFR-2 | Clarifying question responses appear within the existing model response timeout (90s) |
| NFR-3 | All existing 719 pytest tests continue to pass after Phase 9 changes |
| NFR-4 | No new Python backend changes required for Phase 9 (all changes are in `extension/chat/participant.js`) |
| NFR-5 | `showWarningMessage` is called zero times for create, edit, rollback, or save_settings operations after Phase 9 |
| NFR-6 | History passed to model is capped at 6 turns to prevent context bloat |
| NFR-7 | `parseChangeIntent()` function is deleted from participant.js — zero impact/analysis queries use a second internal LLM call |
| NFR-8 | Zero regex patterns in `handleJobEdit`, `handleJobCreate`, `handleDeployRollback`, `handleTriageCommand` (sub-command parse), and `handleAnalyzeCommand` (change type parse) after Phase 9 |

---

## 11. Updated Success Metrics

| Metric | Baseline (Phase 8) | Target (Phase 9) |
|---|---|---|
| Regex patterns in CRUD handlers | 3 (edit, create, rollback) | 0 |
| Regex patterns in triage/analyze handlers | 4 (verify/match/new/impact) | 0 for tool-call path; slash-command path retains as shortcut |
| `showWarningMessage` calls for write operations | 3 | 0 |
| Hidden internal LLM calls in handlers | 1 (parseChangeIntent) | 0 |
| % of NL edit prompts that succeed without explicit syntax | ~40% | >95% |
| % of NL triage prompts that route correctly without sub-command | ~20% | >90% |
| SFTP job NL edit success rate | 0% (not supported) | >90% |
| Multi-step CRUD from single prompt | Not possible | Supported (up to 5 steps) |
| Contextual reference resolution ("that job") | Fails | Works when unambiguous |
