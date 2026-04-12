# Phase 11 FRD — Functional Requirements Document
## FRP Agent VS Code Extension — Real-Time Backend Progress Feedback

**Document type:** Functional Requirements Document  
**Parent:** Phase 11 PRD (`01_PRD.md`)  
**Status:** Draft  
**Date:** July 2025

---

## 1. Purpose

This document specifies the exact functional behaviour of each Phase 11 change. Where the PRD explains *what* and *why*, this document specifies *how the system behaves* from the user's perspective and from the developer's perspective — inputs, outputs, protocols, and interaction flows. Each section maps to PRD stories (S-1xx through S-3xx).

---

## 2. Current System Behaviour Reference

The following current-code facts are established by reading the extension and backend source and are referenced throughout this document.

| Fact | Location in code | Phase 11 disposition |
|---|---|---|
| `LogIndexer.sync()` loops through files with no progress emission | `backend/logs/indexer.py` line 143–188 | Add `emit_progress()` calls inside loop |
| Backend server stderr handler dumps all lines to output channel | `extension/lib/frp_backend.js` line 237–240 | Parse for `__progress__` lines, route to callback |
| `PersistentProcess.send()` signature: `(command, args, timeoutMs)` | `frp_backend.js` line 338 | Add optional `onProgress` param |
| `runCliJson(args, opts)` — `opts` has `timeoutMs` only | `frp_backend.js` line 412 | Add `opts.onProgress` |
| `_runCliJsonSpawn()` collects stderr in chunks, logs at end | `frp_backend.js` line 470–490 | Parse chunks line-by-line for progress |
| `backendCall(command, params, shared, opts)` — `opts` has `timeoutMs` | `extension/copilot/tool.js` line 172 | Add `opts.onProgress`, forward to `runCliJson` |
| `_autoSync(shared)` calls `runCliJson(args)` with no progress | `tool.js` line 134–140 | Add `onProgress` param, forward to `runCliJson` |
| `executePipelineTool()` calls `backendCall()` | `participant.js` line 1755 | Pass `onProgress: (msg) => stream.progress(msg)` |
| `stream.progress()` accepts a string message | VS Code API | Used for all progress surfacing |
| Python `logging.StreamHandler(sys.stderr)` for all log output | `cli/main.py` line 42–49 | Unchanged — `emit_progress()` uses `sys.stderr.write()` directly |

---

## 3. Functional Requirements — Epic 1: Backend Progress Emission

### FR-1.1 — Progress Event Protocol

**Protocol definition:**

A progress event is a single JSON line written to stderr with the following schema:

```json
{
  "__progress__": true,
  "message": "Syncing logs: 15/40 files...",
  "current": 15,
  "total": 40
}
```

**Field semantics:**

| Field | Type | Required | Description |
|---|---|---|---|
| `__progress__` | `boolean` | Yes | Always `true`. Discriminator that distinguishes progress events from regular log lines. |
| `message` | `string` | Yes | Human-readable progress text, displayed directly to the user. Max 200 characters. |
| `current` | `int \| null` | No | Current item number (1-based). `null` when count is not applicable (e.g., "Initialising..."). |
| `total` | `int \| null` | No | Total item count. `null` when total is unknown. |

**Guarantees:**

1. Each progress event is exactly one line (terminated by `\n`).
2. The line is valid JSON parseable by `json.loads()` and `JSON.parse()`.
3. `__progress__` is always the first key in the JSON object (allows fast prefix-check optimisation).
4. Progress events are rate-limited: at most one event per second per operation to avoid stderr buffer pressure.
5. Regular Python `logging` lines do NOT contain the string `"__progress__"`.

---

### FR-1.2 — `emit_progress()` Utility Function

**Location:** New file `backend/common/progress.py`

**Signature:**
```python
def emit_progress(message: str, current: int | None = None, total: int | None = None) -> None
```

**Behaviour:**
1. Builds the JSON dict `{"__progress__": True, "message": message, "current": current, "total": total}`.
2. Writes `json.dumps(obj) + "\n"` to `sys.stderr`.
3. Calls `sys.stderr.flush()` to ensure immediate delivery.
4. Applies rate-limiting: if called within 1 second of the previous emission (per-thread), the call is silently skipped — **unless** `current == total` (always emit the final event).

**Rate-limiting detail:**

```python
_last_emit_time: float = 0.0  # module-level, per-thread via threading.local if needed

def emit_progress(message, current=None, total=None):
    global _last_emit_time
    now = time.monotonic()
    # Always emit for the final item or if enough time has passed
    if current != total and (now - _last_emit_time) < 1.0:
        return
    _last_emit_time = now
    # ... write to stderr
```

**Edge cases:**
- If `sys.stderr` is closed or unavailable, `emit_progress()` silently returns (no exception).
- `message` is truncated to 200 characters before emission.

---

### FR-1.3 — LogIndexer Sync Progress

**File:** `backend/logs/indexer.py`  
**Function:** `sync()`

**Current loop (lines 143–168):**
```python
for filepath in log_files:
    basename = os.path.basename(filepath)
    if self._is_file_indexed(basename):
        files_skipped += 1
        continue
    # ... process file ...
    files_processed += 1
```

**New behaviour:**

Before entering the loop, calculate the number of files that actually need processing (total minus already-indexed). Emit progress during the processing loop:

```python
# Count files needing work
files_to_process = [f for f in log_files if not self._is_file_indexed(os.path.basename(f))]
total_work = len(files_to_process)

if total_work > 0:
    emit_progress(f"Syncing {log_type} logs: 0/{total_work} files...", current=0, total=total_work)

for i, filepath in enumerate(files_to_process, 1):
    # ... process file ...
    emit_progress(f"Syncing {log_type} logs: {i}/{total_work} files...", current=i, total=total_work)
```

**The progress message includes the log_type** (email or sftp) so the user knows which log folder is being synced.

**No progress is emitted when all files are already indexed** (nothing to do → no noise).

---

### FR-1.4 — XML Cache Rebuild Progress

**File:** `backend/db/xml_index.py`  
**Context:** When `XmlJobIndex` is created with an empty or new database, it parses the XML settings file and inserts all jobs into the cache.

**New behaviour:**
Emit progress during the job insertion loop:
```
"Building XML cache: 15/87 jobs..."
```

---

### FR-1.5 — Startup Initialisation Progress

**File:** `cli/main.py`  
**Context:** In server mode, once the process starts and before the `{"status":"ready"}` signal, the backend initialises shared resources.

**New behaviour:**
Emit a simple progress event when starting heavy initialisation:
```
"Initialising backend..."
```

This gives the user immediate feedback when the extension starts the persistent process for the first time.

---

## 4. Functional Requirements — Epic 2: Extension Progress Detection

### FR-2.1 — PersistentProcess Stderr Line-by-Line Parsing

**File:** `extension/lib/frp_backend.js`  
**Location:** `PersistentProcess._doStart()`, stderr handler (line 237)

**Current handler:**
```javascript
this._proc.stderr.on('data', (chunk) => {
  if (_outputChannel) {
    _outputChannel.appendLine(`[FRP][server-stderr] ${chunk.toString().trim()}`);
  }
});
```

**New handler:**

Replace the raw `data` event with a `readline.Interface` on stderr, enabling proper line-by-line parsing:

```javascript
this._stderrRl = readline.createInterface({ input: this._proc.stderr });
this._stderrRl.on('line', (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;

  // Check for progress event
  if (trimmed.startsWith('{"__progress__"')) {
    try {
      const obj = JSON.parse(trimmed);
      if (obj.__progress__ && this._onProgress) {
        this._onProgress(obj.message);
        return;
      }
    } catch (_) {
      // Not valid JSON — fall through to output channel
    }
  }

  // Regular log line → output channel
  if (_outputChannel) {
    _outputChannel.appendLine(`[FRP][server-stderr] ${trimmed}`);
  }
});
```

**Key design decisions:**

1. **Prefix check first** (`startsWith('{"__progress__"')`) — avoids JSON.parse overhead for the vast majority of stderr lines (debug/info logs).
2. **readline.Interface** — ensures lines are properly delimited. Raw `data` chunks can contain partial lines or multiple lines; `readline` handles this automatically.
3. **Fallback** — if `this._onProgress` is null, the line goes to the output channel (no callback → treat as regular log).

---

### FR-2.2 — PersistentProcess Progress Callback Registration

**File:** `extension/lib/frp_backend.js`

**New property:** `this._onProgress = null` (set in constructor).

**Registration flow:**

When `send()` is called with an `onProgress` callback:
1. Store `this._onProgress = onProgress`
2. On command completion (resolve or reject), clear: `this._onProgress = null`

**Concurrency note:** The persistent process is single-command (one pending request at a time due to the stdin/stdout line protocol). Therefore a simple property is sufficient — no Map/queue needed.

**Updated `send()` signature:**
```javascript
async send(command, args = {}, timeoutMs = 30000, onProgress = null)
```

**Behaviour changes in `send()`:**
1. Before writing to stdin: `this._onProgress = onProgress`
2. In the resolve/reject wrappers: `this._onProgress = null`
3. In the timeout handler: `this._onProgress = null` (clear before rejecting)

---

### FR-2.3 — runCliJson Progress Support

**File:** `extension/lib/frp_backend.js`  
**Function:** `runCliJson(args, opts)`

**Changes:**

1. Extract `opts.onProgress` from the options.
2. **Persistent path:** Pass `onProgress` to `_persistent.send()` as the 4th argument.
3. **Spawn fallback (`_runCliJsonSpawn`):** Parse stderr chunks line-by-line and detect progress events:

```javascript
// In _runCliJsonSpawn, replace:
child.stderr.on('data', (chunk) => stderrChunks.push(chunk));

// With:
let stderrBuffer = '';
child.stderr.on('data', (chunk) => {
  const text = chunk.toString();
  stderrChunks.push(chunk);
  stderrBuffer += text;

  // Process complete lines
  const lines = stderrBuffer.split('\n');
  stderrBuffer = lines.pop(); // Keep incomplete line
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('{"__progress__"') && opts.onProgress) {
      try {
        const obj = JSON.parse(trimmed);
        if (obj.__progress__) {
          opts.onProgress(obj.message);
        }
      } catch (_) { /* not valid progress JSON */ }
    }
  }
});
```

---

### FR-2.4 — Spawn Fallback: _autoSync Progress

**File:** `extension/copilot/tool.js`  
**Function:** `_autoSync(shared)`

**Current behaviour:** `_autoSync` calls `runCliJson(args)` with no progress callback. Any sync progress is invisible.

**New behaviour:** `_autoSync(shared, onProgress)` accepts an optional progress callback and passes it to `runCliJson`:

```javascript
async function _autoSync(shared, onProgress) {
  // ... existing setup ...
  try {
    await runCliJson(args, { onProgress });
  } catch (err) {
    // ... existing error handling ...
  }
}
```

---

## 5. Functional Requirements — Epic 3: Extension Integration

### FR-3.1 — backendCall Accepts onProgress

**File:** `extension/copilot/tool.js`  
**Function:** `backendCall(command, params, shared, opts)`

**Changes:**

1. Extract `onProgress` from `opts`.
2. Pass `onProgress` to `_autoSync`:
   ```javascript
   if (!_SKIP_AUTO_SYNC.has(command)) {
     await _autoSync(shared, opts.onProgress);
   }
   ```
3. Pass `onProgress` to `runCliJson`:
   ```javascript
   const result = await runCliJson(args, {
     timeoutMs: opts.timeoutMs || _COMMAND_TIMEOUTS[command] || 30000,
     onProgress: opts.onProgress,
   });
   ```

**Backward compatibility:** All existing callers pass no `onProgress` (or `opts` without it), so behaviour is unchanged by default.

---

### FR-3.2 — executePipelineTool Surfaces Progress

**File:** `extension/chat/participant.js`  
**Function:** `executePipelineTool()`

**Current call (line 1755):**
```javascript
const result = await backendCall(command, params, shared);
```

**New call:**
```javascript
const result = await backendCall(command, params, shared, {
  onProgress: (msg) => stream.progress(msg),
});
```

This single change connects the entire pipeline: any `backendCall` from `executePipelineTool` — including the `_autoSync` that runs first — will surface progress events to the user's chat panel.

---

### FR-3.3 — Other backendCall Sites

The following `backendCall` call sites in `participant.js` should also pass `onProgress`:

| Call site | Function | Line |
|---|---|---|
| `handleJobEdit` | Edit job | ~1843 |
| `handleJobCreate` | Create job | ~1869 |
| `handleDeployRollback` | Rollback | ~1900 |
| `handleImpactAnalysis` | Impact analysis | ~2011 |
| `handleDestructiveToolCall` — job_detail fetch | Fetch current config | ~2044 |
| `handleDestructiveToolCall` — template preview | Search template | ~2070 |
| `handleDestructiveToolCall` — diff load | Load diff | ~2100 |

All of these already have access to `stream` and should pass `onProgress: (msg) => stream.progress(msg)` in their opts.

---

### FR-3.4 — User-Facing Message Format

The user sees progress messages in the chat panel's progress indicator area (below the "thinking" spinner). Messages are short and descriptive:

| Operation | Example message |
|---|---|
| Log sync (email) | `Syncing email logs: 15/40 files...` |
| Log sync (sftp) | `Syncing sftp logs: 3/8 files...` |
| XML cache rebuild | `Building XML cache: 45/87 jobs...` |
| Backend startup | `Initialising backend...` |
| Actual command | `Searching jobs...` (existing `stream.progress` calls in participant.js) |

The user sees these messages appear and update during the operation. When the operation completes, the normal result replaces the progress area.

---

### FR-3.5 — Timeout Extension for Sync During Progress

**Context:** Currently `_autoSync` uses `runCliJson(args)` with default timeout (30 seconds via `_COMMAND_TIMEOUTS.sync_logs = 180000`, but `_autoSync` doesn't pass this override).

**Issue:** `_autoSync` calls `runCliJson` without specifying `timeoutMs`, so it uses the default 30-second timeout — which is why the first sync times out.

**Fix:** `_autoSync` should pass the `sync_logs` timeout:

```javascript
await runCliJson(args, {
  timeoutMs: _COMMAND_TIMEOUTS.sync_logs || 180000,
  onProgress,
});
```

This ensures auto-sync gets the same 180-second timeout as a direct `sync_logs` call.

---

## 6. Interaction Flow Diagram

```
User types: "list all CMBS jobs"
    │
    ▼
participant.js: agentLoop()
    │ LLM selects tool: search_jobs
    ▼
participant.js: executePipelineTool('search_jobs', ...)
    │ stream.progress("Step 1: calling search_jobs...")
    ▼
tool.js: backendCall('search_jobs', params, shared, { onProgress: stream.progress })
    │
    ├─ _autoSync(shared, stream.progress)
    │   │
    │   ▼
    │   frp_backend.js: runCliJson(['sync_logs', ...], { onProgress: stream.progress })
    │   │
    │   ▼
    │   PersistentProcess.send('sync_logs', args, 180000, stream.progress)
    │   │
    │   │ [Backend emits on stderr]:
    │   │   {"__progress__": true, "message": "Syncing email logs: 1/40 files..."}
    │   │   {"__progress__": true, "message": "Syncing email logs: 5/40 files..."}
    │   │   {"__progress__": true, "message": "Syncing email logs: 15/40 files..."}
    │   │   ...
    │   │   {"__progress__": true, "message": "Syncing email logs: 40/40 files..."}
    │   │
    │   │ [Each line → PersistentProcess stderr handler → stream.progress(msg)]
    │   │ [User sees: "Syncing email logs: 15/40 files..." updating in chat panel]
    │   │
    │   ▼
    │   PersistentProcess receives stdout JSON response → sync complete
    │
    ├─ runCliJson(['search_jobs', ...], { onProgress: stream.progress })
    │   ▼
    │   PersistentProcess.send('search_jobs', args, 30000, stream.progress)
    │   │ [No progress events — search_jobs is fast]
    │   ▼
    │   Returns JSON response with CMBS jobs
    │
    ▼
participant.js: formats result → stream.markdown(table)
    │
    ▼
User sees: table with 11 CMBS jobs
```

---

## 7. Error Handling

| Scenario | Behaviour |
|---|---|
| `emit_progress()` fails (stderr closed) | Silently ignored — no exception propagated |
| Progress JSON parse fails in extension | Line treated as regular log → output channel |
| Callback throws an exception | Caught and logged to output channel; does not crash the command |
| Backend exits mid-progress | Existing PersistentProcess error/exit handlers fire; pending progress callback is cleared |
