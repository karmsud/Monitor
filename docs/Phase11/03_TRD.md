# Phase 11 TRD — Technical Requirements Document
## FRP Agent VS Code Extension — Real-Time Backend Progress Feedback

**Document type:** Technical Requirements Document  
**Parent:** Phase 11 PRD (`01_PRD.md`), FRD (`02_FRD.md`)  
**Status:** Draft  
**Date:** July 2025

---

## 1. Purpose

This document specifies exactly which files and functions change, what the before/after code looks like for each change, and the precise sequencing of implementation. Every story from the PRD is mapped to one or more concrete code changes with file paths and test requirements.

---

## 2. Affected Files

| File | Change type | Stories |
|---|---|---|
| `backend/common/progress.py` | **New file** — progress emitter utility | S-101 |
| `backend/logs/indexer.py` | Modify — add `emit_progress()` calls in `sync()` | S-102 |
| `backend/db/xml_index.py` | Modify — add `emit_progress()` calls in `rebuild()` | S-103 |
| `cli/main.py` | Modify — add startup progress in `_run_server()` | S-103 |
| `extension/lib/frp_backend.js` | Modify — stderr progress detection, `send()` + `runCliJson()` progress params | S-201, S-202, S-203 |
| `extension/copilot/tool.js` | Modify — `backendCall()` + `_autoSync()` accept `onProgress` | S-301, S-302 |
| `extension/chat/participant.js` | Modify — thread `stream.progress` through `backendCall` calls | S-303 |
| `tests/` (Python) | New test file for `emit_progress` | S-101–S-103 |
| `extension/test/` | Modify existing or new test file for progress detection | S-201–S-203 |

---

## 3. Implementation Sequence

The three epics must be implemented in this order because later epics depend on earlier ones:

```
Epic 1 (Backend Progress Emission)
  → required by Epic 2 (Extension Detection) because there must be something to detect
  → required by Epic 3 (Integration) because backendCall must have onProgress to forward

Epic 2 (Extension Progress Detection)
  → depends on Epic 1 (needs progress events to parse)
  → required by Epic 3 (runCliJson must support onProgress before backendCall can forward it)

Epic 3 (Extension Integration)
  → depends on Epics 1 + 2
```

**Recommended implementation order:**

```
Step 1: backend/common/progress.py (new file — emit_progress utility)
Step 2: backend/logs/indexer.py (add emit_progress calls)
Step 3: backend/db/xml_index.py (add emit_progress calls)
Step 4: cli/main.py (startup progress)
Step 5: extension/lib/frp_backend.js (stderr detection + send/runCliJson changes)
Step 6: extension/copilot/tool.js (backendCall + _autoSync changes)
Step 7: extension/chat/participant.js (thread onProgress through call sites)
Step 8: Tests (Python + JS)
```

Steps 1–4 (Python backend) can be developed and tested independently of Steps 5–7 (JS extension). The two sides only need to agree on the `{"__progress__": true, ...}` protocol.

---

## 4. Epic 1 Technical Specification — Backend Progress Emission

### 4.1 New file: `backend/common/progress.py`

**Full implementation:**

```python
"""Structured progress events for long-running backend operations.

Emits single-line JSON on stderr with a ``__progress__`` marker so the
VS Code extension can detect and surface them to the user in real time.
"""

from __future__ import annotations

import json
import sys
import time

_last_emit: float = 0.0


def emit_progress(
    message: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    """Write a structured progress event to stderr.

    Rate-limited to at most one event per second, except when
    ``current == total`` (the final event is always emitted).

    Args:
        message: Human-readable progress text (max 200 chars).
        current: Current item number (1-based), or None.
        total:   Total item count, or None.
    """
    global _last_emit

    now = time.monotonic()
    if current != total and (now - _last_emit) < 1.0:
        return
    _last_emit = now

    event = {
        "__progress__": True,
        "message": message[:200],
        "current": current,
        "total": total,
    }

    try:
        sys.stderr.write(json.dumps(event) + "\n")
        sys.stderr.flush()
    except Exception:
        pass  # stderr closed or unavailable — silently skip
```

**Test requirements:**
- `TC-4.1-01`: `emit_progress("test", 5, 10)` writes valid JSON to stderr with `__progress__ == True`
- `TC-4.1-02`: `emit_progress("test")` writes JSON with `current: null, total: null`
- `TC-4.1-03`: Rate-limiting: two calls within 1 second — second is skipped unless `current == total`
- `TC-4.1-04`: Final event (`current == total`) always emitted regardless of rate limit
- `TC-4.1-05`: Message longer than 200 chars is truncated

---

### 4.2 Change: `backend/logs/indexer.py` — `sync()` method

**Location:** `sync()` method, starting at line 123.

**Before (loop structure, lines 143–168):**
```python
for filepath in log_files:
    basename = os.path.basename(filepath)

    if self._is_file_indexed(basename):
        files_skipped += 1
        continue

    try:
        events = parser.parse_file(filepath, log_type=log_type)
        self._bulk_insert_events(events)
        file_size = os.path.getsize(filepath)
        self._record_indexed_file(basename, len(events), file_size)
        files_processed += 1
        events_indexed += len(events)
    except Exception as exc:
        files_errored += 1
        msg = f"Error parsing {basename}: {exc}"
        errors.append(msg)
        logger.exception(msg)
```

**After:**
```python
from backend.common.progress import emit_progress

# ... inside sync() method, before the loop:

# Separate files into skippable vs needing work
files_to_process = []
for filepath in log_files:
    basename = os.path.basename(filepath)
    if self._is_file_indexed(basename):
        files_skipped += 1
    else:
        files_to_process.append(filepath)

total_work = len(files_to_process)
if total_work > 0:
    emit_progress(
        f"Syncing {log_type} logs: 0/{total_work} files...",
        current=0, total=total_work,
    )

for i, filepath in enumerate(files_to_process, 1):
    basename = os.path.basename(filepath)
    try:
        events = parser.parse_file(filepath, log_type=log_type)
        self._bulk_insert_events(events)
        file_size = os.path.getsize(filepath)
        self._record_indexed_file(basename, len(events), file_size)
        files_processed += 1
        events_indexed += len(events)
    except Exception as exc:
        files_errored += 1
        msg = f"Error parsing {basename}: {exc}"
        errors.append(msg)
        logger.exception(msg)

    emit_progress(
        f"Syncing {log_type} logs: {i}/{total_work} files...",
        current=i, total=total_work,
    )
```

**Key changes:**
1. Pre-scan to separate already-indexed files from work files (same total skip count, but up-front)
2. `emit_progress()` at start of loop (0/N) and after each file (i/N)
3. Rate-limiting in `emit_progress()` ensures at most ~1 event/second even with many files

**Import addition at top of file:**
```python
from backend.common.progress import emit_progress
```

---

### 4.3 Change: `backend/db/xml_index.py` — `rebuild()` method

**Location:** `rebuild()` method, line 188.

**Before (email job insertion loop, lines 205–240):**
```python
cur.execute("DELETE FROM email_jobs")
for job in jobs:
    cur.execute(_INSERT_EMAIL_JOB, (...))
```

**After:**
```python
from backend.common.progress import emit_progress

# ... inside rebuild():
total_jobs = len(jobs)

cur.execute("DELETE FROM email_jobs")
for i, job in enumerate(jobs, 1):
    cur.execute(_INSERT_EMAIL_JOB, (...))
    emit_progress(
        f"Building XML cache: {i}/{total_jobs} {xml_type} jobs...",
        current=i, total=total_jobs,
    )
```

The same pattern applies to the SFTP branch of the `rebuild()` method.

---

### 4.4 Change: `cli/main.py` — `_run_server()` startup progress

**Location:** `_run_server()`, line 2146.

**Before (lines 2162–2165):**
```python
logger.info("Server mode started — waiting for JSON commands on stdin")

# Signal readiness to the extension (single line, flushed)
sys.stdout.write('{"status":"ready"}\n')
sys.stdout.flush()
```

**After:**
```python
from backend.common.progress import emit_progress

logger.info("Server mode started — waiting for JSON commands on stdin")

emit_progress("Initialising backend...")

# Signal readiness to the extension (single line, flushed)
sys.stdout.write('{"status":"ready"}\n')
sys.stdout.flush()
```

**Note:** This startup progress event fires before `{"status":"ready"}` — the extension receives the stderr progress line while waiting for the ready signal, and can surface it if a progress callback is registered. If no callback is registered, it goes to the output channel (existing behaviour).

---

## 5. Epic 2 Technical Specification — Extension Progress Detection

### 5.1 Change: `extension/lib/frp_backend.js` — PersistentProcess constructor

**Before (line 200):**
```javascript
constructor(runner) {
    this._runner = runner;
    /** @type {import('child_process').ChildProcess|null} */
    this._proc = null;
    /** @type {readline.Interface|null} */
    this._rl = null;
    /** @type {Array<{resolve: Function, reject: Function}>} */
    this._pending = [];
    this._ready = false;
    this._starting = false;
    /** @type {Promise<void>|null} */
    this._startPromise = null;
  }
```

**After:**
```javascript
constructor(runner) {
    this._runner = runner;
    /** @type {import('child_process').ChildProcess|null} */
    this._proc = null;
    /** @type {readline.Interface|null} */
    this._rl = null;
    /** @type {readline.Interface|null} */
    this._stderrRl = null;
    /** @type {Array<{resolve: Function, reject: Function}>} */
    this._pending = [];
    this._ready = false;
    this._starting = false;
    /** @type {Promise<void>|null} */
    this._startPromise = null;
    /** @type {((msg: string) => void)|null} */
    this._onProgress = null;
  }
```

---

### 5.2 Change: `extension/lib/frp_backend.js` — PersistentProcess._doStart() stderr handler

**Before (lines 237–240):**
```javascript
    // Collect stderr for logging
    this._proc.stderr.on('data', (chunk) => {
      if (_outputChannel) {
        _outputChannel.appendLine(`[FRP][server-stderr] ${chunk.toString().trim()}`);
      }
    });
```

**After:**
```javascript
    // Parse stderr line-by-line for progress events
    this._stderrRl = readline.createInterface({ input: this._proc.stderr });
    this._stderrRl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      // Fast prefix check for structured progress events
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

**Key design notes:**
- `readline.createInterface` ensures proper line splitting (handles partial buffers, multi-line chunks)
- `startsWith('{"__progress__"')` is a fast string prefix check — 99%+ of stderr lines (Python logging) won't match, so `JSON.parse` is almost never called unnecessarily
- If `this._onProgress` is null (no command in flight or caller didn't provide a callback), progress lines fall through to the output channel

---

### 5.3 Change: `extension/lib/frp_backend.js` — PersistentProcess.send()

**Before (line 338):**
```javascript
  async send(command, args = {}, timeoutMs = 30000) {
```

**After:**
```javascript
  async send(command, args = {}, timeoutMs = 30000, onProgress = null) {
```

**Before (return new Promise block, lines 352–385):**
```javascript
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        // Replace with a drain entry that silently absorbs the late response
        // so it doesn't corrupt the next real command's result
        const idx = this._pending.findIndex((p) => p._timer === timer);
        if (idx !== -1) {
          this._pending[idx] = { resolve: () => {}, reject: () => {}, _drain: true, _command: command };
        }
        reject(new Error(`Command '${command}' timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      const entry = { resolve, reject, _timer: timer, _command: command };
      this._pending.push(entry);

      // Wrap resolve/reject to clear timer
      const origResolve = resolve;
      const origReject = reject;
      entry.resolve = (val) => { clearTimeout(timer); origResolve(val); };
      entry.reject = (err) => { clearTimeout(timer); origReject(err); };

      try {
        this._proc.stdin.write(request);
      } catch (err) {
        clearTimeout(timer);
        this._pending.pop();
        reject(new Error(`Failed to write to backend: ${err.message}`));
      }
    });
```

**After:**
```javascript
    // Register progress callback for the duration of this command
    this._onProgress = onProgress;

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._onProgress = null;
        const idx = this._pending.findIndex((p) => p._timer === timer);
        if (idx !== -1) {
          this._pending[idx] = { resolve: () => {}, reject: () => {}, _drain: true, _command: command };
        }
        reject(new Error(`Command '${command}' timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      const entry = { resolve, reject, _timer: timer, _command: command };
      this._pending.push(entry);

      // Wrap resolve/reject to clear timer and unregister progress
      const origResolve = resolve;
      const origReject = reject;
      entry.resolve = (val) => { clearTimeout(timer); this._onProgress = null; origResolve(val); };
      entry.reject = (err) => { clearTimeout(timer); this._onProgress = null; origReject(err); };

      try {
        this._proc.stdin.write(request);
      } catch (err) {
        clearTimeout(timer);
        this._onProgress = null;
        this._pending.pop();
        reject(new Error(`Failed to write to backend: ${err.message}`));
      }
    });
```

**Changes summary:**
1. `this._onProgress = onProgress` before the promise
2. `this._onProgress = null` in timeout, resolve, reject, and catch handlers

---

### 5.4 Change: `extension/lib/frp_backend.js` — PersistentProcess.kill()

**Before (line 390):**
```javascript
  kill() {
    this._ready = false;
    if (this._rl) {
      this._rl.close();
      this._rl = null;
    }
```

**After:**
```javascript
  kill() {
    this._ready = false;
    this._onProgress = null;
    if (this._rl) {
      this._rl.close();
      this._rl = null;
    }
    if (this._stderrRl) {
      this._stderrRl.close();
      this._stderrRl = null;
    }
```

---

### 5.5 Change: `extension/lib/frp_backend.js` — runCliJson()

**Before (persistent path, lines 423–445):**
```javascript
  if (_persistent && _persistent._ready) {
    const command = args[0];
    // Convert CLI flags back to an args object for the server protocol
    const serverArgs = {};
    // ... flag conversion ...

    return _persistent.send(command, serverArgs, timeoutMs).catch((err) => {
```

**After:**
```javascript
  if (_persistent && _persistent._ready) {
    const command = args[0];
    const onProgress = opts.onProgress || null;
    // Convert CLI flags back to an args object for the server protocol
    const serverArgs = {};
    // ... flag conversion (unchanged) ...

    return _persistent.send(command, serverArgs, timeoutMs, onProgress).catch((err) => {
```

---

### 5.6 Change: `extension/lib/frp_backend.js` — _runCliJsonSpawn()

**Before (lines 470–472):**
```javascript
function _runCliJsonSpawn(args, timeoutMs) {
```

**After:**
```javascript
function _runCliJsonSpawn(args, timeoutMs, onProgress) {
```

**Before (stderr handler, line 487):**
```javascript
    child.stderr.on('data', (chunk) => stderrChunks.push(chunk));
```

**After:**
```javascript
    let stderrBuffer = '';
    child.stderr.on('data', (chunk) => {
      stderrChunks.push(chunk);

      // Parse for progress events line-by-line
      if (onProgress) {
        stderrBuffer += chunk.toString();
        const lines = stderrBuffer.split('\n');
        stderrBuffer = lines.pop(); // Keep incomplete last line
        for (const rawLine of lines) {
          const trimmed = rawLine.trim();
          if (trimmed.startsWith('{"__progress__"')) {
            try {
              const obj = JSON.parse(trimmed);
              if (obj.__progress__) {
                onProgress(obj.message);
              }
            } catch (_) { /* not valid progress JSON */ }
          }
        }
      }
    });
```

**Update the two call sites of `_runCliJsonSpawn`:**

In `runCliJson()`, the fallback call:
```javascript
// Before:
return _runCliJsonSpawn(args, timeoutMs);

// After:
return _runCliJsonSpawn(args, timeoutMs, onProgress);
```

And the standalone fallback at the end of `runCliJson()`:
```javascript
// Before:
return _runCliJsonSpawn(args, timeoutMs);

// After:
return _runCliJsonSpawn(args, timeoutMs, opts.onProgress || null);
```

---

## 6. Epic 3 Technical Specification — Extension Integration

### 6.1 Change: `extension/copilot/tool.js` — `_autoSync()`

**Before (line 120):**
```javascript
async function _autoSync(shared) {
```

**After:**
```javascript
async function _autoSync(shared, onProgress) {
```

**Before (runCliJson call, line 139):**
```javascript
    await runCliJson(args);
```

**After:**
```javascript
    await runCliJson(args, {
      timeoutMs: _COMMAND_TIMEOUTS.sync_logs || 180000,
      onProgress,
    });
```

**Note:** This also fixes the existing bug where `_autoSync` used the default 30-second timeout instead of the 180-second timeout configured for `sync_logs`. This was the root cause of the timeout cascade described in the PRD.

---

### 6.2 Change: `extension/copilot/tool.js` — `backendCall()`

**Before (_autoSync call, line 183):**
```javascript
  if (!_SKIP_AUTO_SYNC.has(command)) {
    await _autoSync(shared);
  }
```

**After:**
```javascript
  if (!_SKIP_AUTO_SYNC.has(command)) {
    await _autoSync(shared, opts.onProgress);
  }
```

**Before (runCliJson call, line 270):**
```javascript
    const result = await runCliJson(args, { timeoutMs: opts.timeoutMs || _COMMAND_TIMEOUTS[command] || 30000 });
```

**After:**
```javascript
    const result = await runCliJson(args, {
      timeoutMs: opts.timeoutMs || _COMMAND_TIMEOUTS[command] || 30000,
      onProgress: opts.onProgress,
    });
```

---

### 6.3 Change: `extension/chat/participant.js` — `executePipelineTool()`

**Before (line 1755):**
```javascript
  const result = await backendCall(command, params, shared);
```

**After:**
```javascript
  const result = await backendCall(command, params, shared, {
    onProgress: (msg) => stream.progress(msg),
  });
```

---

### 6.4 Change: `extension/chat/participant.js` — `handleJobEdit()`

**Before (line 1843):**
```javascript
  const data = await backendCall('edit_job', { jobName, field, value, xmlType: xmlType || 'email' }, shared);
```

**After:**
```javascript
  const data = await backendCall('edit_job', { jobName, field, value, xmlType: xmlType || 'email' }, shared, {
    onProgress: (msg) => stream.progress(msg),
  });
```

---

### 6.5 Change: `extension/chat/participant.js` — `handleJobCreate()`

**Before (line 1869):**
```javascript
  const data = await backendCall('create_job', {
```

**After:** Add `onProgress` in opts (4th arg):
```javascript
  const data = await backendCall('create_job', {
    templateJob, name: newName, overrides, xmlType: xmlType || 'email',
  }, shared, { onProgress: (msg) => stream.progress(msg) });
```

---

### 6.6 Change: `extension/chat/participant.js` — `handleDeployRollback()`

**Before (line 1900):**
```javascript
  const data = await backendCall('rollback_xml', { backupFile }, shared);
```

**After:**
```javascript
  const data = await backendCall('rollback_xml', { backupFile }, shared, {
    onProgress: (msg) => stream.progress(msg),
  });
```

---

### 6.7 Change: `extension/chat/participant.js` — `handleImpactAnalysis()`

**Before (line 2011):**
```javascript
  const data = await backendCall('analyze_impact', changeSpec, shared);
```

**After:**
```javascript
  const data = await backendCall('analyze_impact', changeSpec, shared, {
    onProgress: (msg) => stream.progress(msg),
  });
```

---

### 6.8 Change: `extension/chat/participant.js` — `handleDestructiveToolCall()`

Three `backendCall` sites in this function:

**Line ~2044 (job_detail fetch):**
```javascript
// Before:
const currentData = await backendCall('job_detail', { jobName: toolInput.jobName }, shared);
// After:
const currentData = await backendCall('job_detail', { jobName: toolInput.jobName }, shared, {
  onProgress: (msg) => stream.progress(msg),
});
```

**Line ~2070 (template preview):**
```javascript
// Before:
const preview = await backendCall('search_jobs', { query: toolInput.templateJob }, shared);
// After:
const preview = await backendCall('search_jobs', { query: toolInput.templateJob }, shared, {
  onProgress: (msg) => stream.progress(msg),
});
```

**Line ~2100 (diff load):**
```javascript
// Before:
const diffData = await backendCall('xml_diff', { backupFile: toolInput.backupFile }, shared);
// After:
const diffData = await backendCall('xml_diff', { backupFile: toolInput.backupFile }, shared, {
  onProgress: (msg) => stream.progress(msg),
});
```

---

## 7. Testing Strategy

### 7.1 Python Unit Tests

**New test file:** `tests/common/test_progress.py`

| Test ID | Description |
|---|---|
| `test_emit_progress_writes_json` | `emit_progress("test", 5, 10)` writes valid JSON with `__progress__: true` to stderr |
| `test_emit_progress_no_counts` | `emit_progress("msg")` writes JSON with `current: null, total: null` |
| `test_emit_progress_rate_limit` | Two rapid calls → second is skipped |
| `test_emit_progress_final_always_emitted` | Call with `current == total` always emits regardless of rate limit |
| `test_emit_progress_message_truncation` | Message > 200 chars is truncated |
| `test_emit_progress_stderr_closed` | No exception when stderr is closed |

**Approach:** Capture stderr using `io.StringIO` or `unittest.mock.patch('sys.stderr')`.

### 7.2 Python Integration Tests

| Test ID | Description |
|---|---|
| `test_sync_emits_progress` | `LogIndexer.sync()` with test fixtures emits at least one progress event |
| `test_sync_no_progress_when_nothing_to_do` | All files already indexed → no progress events |

### 7.3 JavaScript Unit Tests

**Modify/extend:** `extension/test/` — existing test infrastructure

| Test ID | Description |
|---|---|
| `test_persistent_stderr_progress` | Simulated stderr line with `__progress__` → callback called |
| `test_persistent_stderr_regular` | Regular log line → output channel, no callback |
| `test_send_onProgress` | `send()` with `onProgress` → callback registered during command |
| `test_send_clears_progress_on_resolve` | `_onProgress` is null after command completes |
| `test_backendCall_forwards_progress` | `backendCall(cmd, params, shared, { onProgress })` → `runCliJson` receives `onProgress` |
| `test_autoSync_uses_sync_timeout` | `_autoSync` passes 180000ms timeout (bug fix verification) |

### 7.4 Existing Test Preservation

All 56 existing JS unit tests must continue to pass. The changes are additive (new optional parameters with default `null`), so existing callers are unaffected.

All existing Python tests must continue to pass. The only change is adding `emit_progress()` calls which write to stderr — test fixtures that don't capture stderr won't be affected.

---

## 8. Build and Deployment

No changes to the build pipeline. After implementation:

1. Run Python tests: `pytest` (all existing + new progress tests)
2. Run JS tests: via VS Code test runner (all 56 + new progress tests)
3. Rebuild backend: `.\scripts\build.ps1 -BackendOnly -NoPip`
4. Rebuild VSIX: `.\scripts\build.ps1 -SkipBackend -NoPip`
5. Or full rebuild: `.\scripts\build.ps1 -NoPip`

The new `backend/common/progress.py` file is automatically included by PyInstaller (it's a regular Python module in the `backend` package).

---

## 9. Rollback Plan

If Phase 11 causes issues:

1. **Backend only:** Remove `emit_progress()` calls from `indexer.py` and `xml_index.py`. The `progress.py` module can remain (unused code does no harm).
2. **Extension only:** Remove `onProgress` parameters from `backendCall` and `executePipelineTool` calls. The stderr parsing in `frp_backend.js` can remain (unrecognised progress lines just go to output channel).
3. **Full rollback:** Revert all Phase 11 changes. The `__progress__` protocol is purely additive — removing it restores exact pre-Phase 11 behaviour.

All rollback actions are safe because Phase 11 is strictly additive — it adds an optional progress channel alongside the existing command/response channel.
