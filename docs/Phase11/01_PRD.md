# Phase 11 PRD — Real-Time Backend Progress Feedback
## FRP Agent VS Code Extension

**Document type:** Product Requirements Document  
**Phase:** 11  
**Status:** Draft — awaiting approval before implementation begins  
**Date:** July 2025  
**Author:** Engineering (GitHub Copilot assisted)

---

## 1. Executive Summary

Phase 11 adds real-time progress feedback from the Python backend to the VS Code chat panel. After this phase, any long-running backend operation — log sync, XML cache rebuild, database queries — will emit structured progress events on stderr that the extension surfaces to the user via `stream.progress()`. Users will never again experience unexplained silent waits.

---

## 2. Problem Statement

### 2.1 Current Behaviour (as-is)

The FRP Agent backend performs an **automatic log sync** (`_autoSync`) before every backend command. This keeps the SQLite log index up-to-date with the latest log files from the network share (jobs run every 10 minutes, so incremental sync is the correct strategy).

However, the first sync after a cold start (or when new log files have accumulated) can take 30–90+ seconds — parsing 40+ log files and indexing ~9,000 events. During this time:

1. **The user sees nothing.** The chat panel shows `"Step 1: calling search_jobs..."` and then silence for up to 90 seconds.
2. **The persistent backend's 30-second timeout fires.** `PersistentProcess.send()` rejects with a timeout error, but the backend is still working.
3. **The timeout cascade triggers a spawn fallback** — but the fallback is skipped for `sync_logs` to avoid SQLite locking. The sync eventually completes and the data arrives, but the user has no visibility into what is happening.

The same problem applies to any backend operation that takes more than a few seconds:
- First-time XML cache rebuild (`rebuild_db`)
- Large XML file parsing (100+ jobs)
- Cross-database MSSQL joins (`staging_search`)

**The root cause is architectural:** the backend-to-extension communication channel is one-way (stdin request → stdout response). There is no mechanism for the backend to emit intermediate progress updates during a long operation.

### 2.2 User Impact

| Symptom | User experience | Root cause |
|---|---|---|
| 90-second silence on first query | User thinks the agent is broken, considers cancelling | No progress mechanism |
| Timeout error followed by correct result | Confusing — "error" then "success" | 30s timeout too short for sync, no streaming |
| No visibility into sync status | User doesn't know if 5 files or 500 files are being processed | Backend logs go to output channel, not chat |
| Same problem on any slow command | Large staging searches, MSSQL joins — no feedback | Same architectural gap |

### 2.3 Why Not Lazy-Loading?

An alternative would be to skip auto-sync for non-log queries (e.g., `search_jobs` doesn't need log data). This was discussed and **rejected** because:

- Jobs run every 10 minutes — syncing on every command keeps the index incremental (1–2 new files per command)
- Lazy-loading creates "log debt" — when the user finally runs a log query, they'd face an even larger backlog
- The first query is the worst case precisely because no prior syncs have occurred — distributing the work across all queries is the correct approach

The correct fix is to **make the work visible, not to defer it**.

---

## 3. Goals

### 3.1 In Scope (Phase 11)

| ID | Goal |
|---|---|
| G-1 | The backend emits structured progress events on stderr during any operation lasting more than ~1 second. |
| G-2 | The extension detects these progress events and surfaces them to the user via `stream.progress()` in the chat panel. |
| G-3 | Progress is surfaced for log sync, XML cache rebuild, and any backend operation that iterates over files or records. |
| G-4 | The `_autoSync` flow surfaces progress to the user, not just to the output channel. |
| G-5 | All existing functionality is preserved. Existing test suites pass unchanged. |
| G-6 | The progress protocol is generic — new backend commands can emit progress without any extension-side changes. |

### 3.2 Out of Scope (Phase 11)

- Progress bars (percentage-based UI) — VS Code's `stream.progress()` is text-only; no graphical progress bar is available in the chat panel
- Cancellation — the user cannot cancel a running backend operation (this would require a bidirectional control channel; deferred to a future phase if needed)
- Backend architectural changes beyond progress emission — no new commands, no changes to the JSON-RPC response format
- Changes to the `_autoSync` strategy (it remains "sync before every command")

---

## 4. User Stories

### Epic 1 — Backend Progress Emission (S-1xx)

**Epic goal:** The Python backend emits structured JSON progress lines on stderr so the extension can detect and surface them.

---

**S-101 — Progress emitter utility**

> *As a developer I want a simple utility function that emits a progress event on stderr so I can add progress to any long-running operation with a single function call.*

**Current state:** Backend operations write unstructured log lines to stderr via Python's `logging` module (e.g., `[2025-07-01 12:00:00] INFO frp.logs.indexer — Sync complete: {...}`). The extension's `PersistentProcess` reads these lines and writes them to the output channel. There is no way to distinguish a "progress update for the user" from a "debug log for the developer".

**Target state:** A new `emit_progress(message, current=None, total=None)` function writes a single-line JSON object to stderr with a distinguishing marker. The extension detects lines containing `"__progress__"` and routes them to the user instead of the output channel.

**Acceptance criteria (Gherkin):**

```gherkin
Feature: Backend progress emission

  Scenario: Progress event emitted during sync
    Given the LogIndexer is syncing 40 log files
    When it starts processing file #15
    Then stderr receives a line: {"__progress__": true, "message": "Syncing logs: 15/40 files...", "current": 15, "total": 40}

  Scenario: Progress event is valid JSON on a single line
    Given a progress event is emitted
    Then the line is valid JSON parseable by JSON.parse()
    And the line contains no newlines (except the trailing \n)

  Scenario: Regular log lines are unchanged
    Given a debug log line is written via logger.info()
    Then the line does NOT contain "__progress__"
    And the extension routes it to the output channel as before
```

**Test cases:**
- `TC-S101-01`: `emit_progress("test", 5, 10)` writes valid JSON to stderr with `__progress__: true`
- `TC-S101-02`: `emit_progress("no counts")` writes JSON with `current: null, total: null`
- `TC-S101-03`: Regular `logger.info()` lines do not contain `__progress__`

---

**S-102 — LogIndexer sync progress**

> *As a user I want to see how many log files have been processed during log sync so I know the operation is working and how much remains.*

**Current state:** `LogIndexer.sync()` loops through `*.log` files, processes them one-by-one, and writes a single summary log line at the end.

**Target state:** `LogIndexer.sync()` emits a progress event every N files (or every file when the total is small), showing `"Syncing logs: 15/40 files..."`.

**Acceptance criteria:**

```gherkin
Feature: Log sync progress

  Scenario: Progress during file iteration
    Given there are 40 new log files to process
    When sync() runs
    Then progress events are emitted at regular intervals
    And each event includes the current file count and total

  Scenario: No progress for skipped files
    Given all 40 log files are already indexed
    When sync() runs
    Then no progress events are emitted (nothing to do)

  Scenario: First sync shows progress immediately
    Given this is the first sync (cold start)
    When sync() starts processing the first file
    Then a progress event is emitted within the first 2 seconds
```

**Test cases:**
- `TC-S102-01`: `sync()` with 10 new files emits at least 2 progress events
- `TC-S102-02`: `sync()` with 0 new files emits no progress events
- `TC-S102-03`: Progress message format is `"Syncing logs: N/M files..."`

---

**S-103 — XML cache rebuild progress**

> *As a user I want to see progress during XML cache rebuilds so I know why it's taking a moment.*

**Target state:** When `XmlJobIndex.rebuild()` or initial population runs, progress events are emitted showing how many jobs have been indexed.

---

### Epic 2 — Extension Progress Detection (S-2xx)

**Epic goal:** The extension's `frp_backend.js` detects structured progress lines from stderr and exposes them via a callback mechanism.

---

**S-201 — PersistentProcess stderr progress detection**

> *As a developer I want the PersistentProcess to detect progress JSON on stderr and call a callback, instead of just dumping everything to the output channel.*

**Current state:** `PersistentProcess._doStart()` registers `this._proc.stderr.on('data', ...)` which writes all stderr content to the output channel. No parsing, no distinction between log lines and progress events.

**Target state:** The stderr handler parses each line. Lines containing `"__progress__"` are routed to a registered progress callback. All other lines continue going to the output channel.

**Acceptance criteria:**

```gherkin
Feature: Persistent process stderr progress detection

  Scenario: Progress line detected
    Given the backend emits {"__progress__": true, "message": "Syncing: 5/10"}
    When the stderr handler processes this line
    Then the registered progress callback is called with message "Syncing: 5/10"
    And the line is NOT written to the output channel

  Scenario: Regular log line unchanged
    Given the backend emits "[2025-07-01] INFO frp.logs.indexer — Sync complete"
    When the stderr handler processes this line
    Then the line IS written to the output channel
    And the progress callback is NOT called

  Scenario: No progress callback registered
    Given no progress callback is currently registered
    When a progress line arrives on stderr
    Then the line is written to the output channel as fallback
```

**Test cases:**
- `TC-S201-01`: Progress JSON line → callback called with parsed message
- `TC-S201-02`: Non-JSON stderr line → output channel, no callback
- `TC-S201-03`: No callback registered → progress line written to output channel

---

**S-202 — PersistentProcess.send() accepts onProgress**

> *As a developer I want to pass an `onProgress` callback to `send()` so that progress events arriving during that command are forwarded to the caller.*

**Current state:** `send(command, args, timeoutMs)` — no progress support.

**Target state:** `send(command, args, timeoutMs, onProgress)` — while the command is pending, stderr progress events are routed to `onProgress(message)`. When the command completes, the callback is unregistered.

---

**S-203 — runCliJson accepts onProgress**

> *As a developer I want `runCliJson(args, opts)` to accept `opts.onProgress` and forward it to PersistentProcess or the spawn fallback.*

**Target state:** Both the persistent path and the spawn fallback detect progress lines on stderr and call `opts.onProgress(message)`.

---

### Epic 3 — Extension Integration (S-3xx)

**Epic goal:** `backendCall()` in `tool.js` and the agent loop in `participant.js` thread the progress callback so the user sees live updates.

---

**S-301 — backendCall accepts onProgress**

> *As a developer I want to pass `onProgress` through `backendCall()` so any caller can receive progress updates.*

**Current state:** `backendCall(command, params, shared, opts)` — `opts` supports `timeoutMs`.

**Target state:** `opts.onProgress` is forwarded to `runCliJson`.

---

**S-302 — _autoSync surfaces progress**

> *As a user I want to see log sync progress in the chat panel, not just in the hidden output channel.*

**Current state:** `_autoSync(shared)` calls `runCliJson(args)` silently. If it fails, it logs to the output channel.

**Target state:** `_autoSync(shared, onProgress)` passes the progress callback to `runCliJson`. The caller (backendCall) passes `opts.onProgress` through.

---

**S-303 — agentLoop and executePipelineTool thread progress**

> *As a user I want to see progress messages in the chat panel during any backend call made by the agent.*

**Current state:** `executePipelineTool()` calls `backendCall()` with standard params. `agentLoop()` calls `executePipelineTool()`.

**Target state:** Both pass `onProgress: (msg) => stream.progress(msg)` in the opts to `backendCall()`.

---

## 5. Success Criteria

| Criterion | Measurement |
|---|---|
| No silent waits > 3 seconds | During any backend operation, the user sees at least one progress message within 3 seconds of the operation starting |
| Log sync progress visible | User sees "Syncing logs: N/M files..." messages during auto-sync |
| Existing tests pass | All 56 JS unit tests + all Python tests pass unchanged |
| No performance regression | Progress emission adds < 1ms overhead per event |
| Protocol is generic | Adding progress to a new backend command requires only adding `emit_progress()` calls — no extension changes |

---

## 6. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| stderr buffer pressure from too many progress events | Low | Medium | Rate-limit emission to max 1 event per second per operation |
| Progress callback not unregistered → stale callbacks | Medium | Medium | Auto-clear callback on command completion; use a Map keyed by pending request |
| Spawn fallback doesn't surface progress | Medium | Low | Parse stderr lines in spawn handler the same way as persistent |
| Progress events interleaved with log lines mid-buffer | Low | Low | Split stderr data on newlines; only parse complete lines |

---

## 7. Dependencies

- **Phase 10 complete** — unified `agentLoop`, `TOOL_REGISTRY`, `executePipelineTool` are all in place
- **No external dependencies** — this phase modifies only FRP Agent code (Python backend + JS extension)
- **No new packages** — uses existing `sys.stderr`, `JSON.parse`, `stream.progress()`
