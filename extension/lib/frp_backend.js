const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
let _runner = null;
let _outputChannel = null;
/** @type {PersistentProcess|null} */
let _persistent = null;

// ---------------------------------------------------------------------------
// ExeRunner — spawns the PyInstaller-compiled executable
// ---------------------------------------------------------------------------
class ExeRunner {
  constructor(exePath) {
    this.exePath = exePath;
  }

  /** @returns {{ cmd: string, args: string[] }} */
  buildSpawn(cliArgs) {
    return { cmd: this.exePath, args: cliArgs };
  }

  toString() {
    return `ExeRunner(${this.exePath})`;
  }
}

// ---------------------------------------------------------------------------
// VenvRunner — spawns python -m cli.main inside the project virtualenv
// ---------------------------------------------------------------------------
class VenvRunner {
  /**
   * @param {string} pythonPath  Absolute path to the python executable inside the venv
   * @param {string} projectRoot Absolute path to the FRP_Agent project root
   */
  constructor(pythonPath, projectRoot) {
    this.pythonPath = pythonPath;
    this.projectRoot = projectRoot;
  }

  /** @returns {{ cmd: string, args: string[], cwd: string }} */
  buildSpawn(cliArgs) {
    return {
      cmd: this.pythonPath,
      args: ['-m', 'cli.main', ...cliArgs],
      cwd: this.projectRoot,
    };
  }

  toString() {
    return `VenvRunner(${this.pythonPath})`;
  }
}

// ---------------------------------------------------------------------------
// initBackendRunner — detect the best backend mode and store it
// ---------------------------------------------------------------------------

/**
 * Initialise the backend runner once during extension activation.
 *
 * Resolution order controlled by the `frpAgent.backendMode` setting:
 *   "auto" (default) → prefer exe, fall back to venv
 *   "exe"            → exe only
 *   "venv"           → venv only
 *
 * @param {typeof import('vscode')} vscode
 * @param {import('vscode').ExtensionContext} context
 * @param {import('vscode').OutputChannel} outputChannel
 */
async function initBackendRunner(vscode, context, outputChannel) {
  _outputChannel = outputChannel;

  const config = vscode.workspace.getConfiguration('frpAgent');
  const mode = config.get('backendMode', 'auto');

  const extensionRoot = context.extensionPath;

  // When running in dev (F5) the extension lives inside the project tree,
  // so the project root is one level up.  When installed as a VSIX the
  // extension is in ~/.vscode/extensions — there is no project root.
  const projectRoot = resolveProjectRoot(extensionRoot);

  // PyInstaller exe sits inside extension/bin/win-x64/frp-backend/
  const exePath = path.join(extensionRoot, 'bin', 'win-x64', 'frp-backend', 'frp-backend.exe');
  const venvPython = projectRoot ? resolveVenvPython(projectRoot) : null;

  outputChannel.appendLine(`[FRP] Backend mode setting: ${mode}`);

  if (mode === 'exe' || mode === 'auto') {
    if (fs.existsSync(exePath)) {
      _runner = new ExeRunner(exePath);
      outputChannel.appendLine(`[FRP] Using ExeRunner: ${exePath}`);
      return;
    }
    if (mode === 'exe') {
      outputChannel.appendLine(`[FRP] WARNING: exe not found at ${exePath}, falling back to venv.`);
    }
  }

  if (venvPython && projectRoot) {
    _runner = new VenvRunner(venvPython, projectRoot);
    outputChannel.appendLine(`[FRP] Using VenvRunner: ${venvPython}`);
    return;
  }

  if (projectRoot) {
    // Last resort — try bare 'python' on PATH with project root as cwd
    _runner = new VenvRunner('python', projectRoot);
    outputChannel.appendLine('[FRP] WARNING: No venv found, using system python.');
    return;
  }

  // Installed as VSIX with no exe — cannot run
  outputChannel.appendLine('[FRP] ERROR: No backend available. Rebuild the VSIX with the backend exe included.');
  _runner = null;
}

/**
 * Start (or restart) the persistent backend process.
 * Called automatically during activation; can also be called to force restart.
 */
async function startPersistentBackend() {
  if (!_runner) return;
  if (_persistent) _persistent.kill();
  _persistent = new PersistentProcess(_runner);
  try {
    await _persistent.start();
  } catch (err) {
    if (_outputChannel) {
      _outputChannel.appendLine(`[FRP] Persistent start failed, will use spawn fallback: ${err.message}`);
    }
    _persistent = null;
  }
}

/**
 * Gracefully shut down the persistent backend.
 * Called from extension deactivate().
 */
function shutdownBackend() {
  if (_persistent) {
    _persistent.kill();
    _persistent = null;
  }
}

/**
 * Resolve the python executable inside a virtualenv adjacent to the project.
 * Checks: .venv/Scripts/python.exe (Windows), .venv/bin/python (Unix)
 */
function resolveVenvPython(projectRoot) {
  const candidates = [
    path.join(projectRoot, '.venv', 'Scripts', 'python.exe'),
    path.join(projectRoot, '.venv', 'bin', 'python'),
    path.join(projectRoot, 'venv', 'Scripts', 'python.exe'),
    path.join(projectRoot, 'venv', 'bin', 'python'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/**
 * Determine the FRP_Agent project root.
 * In dev mode the extension dir is <projectRoot>/extension — verify by
 * checking for cli/main.py.  When installed as a VSIX the parent won't
 * have cli/main.py so we return null.
 */
function resolveProjectRoot(extensionDir) {
  const candidate = path.resolve(extensionDir, '..');
  if (fs.existsSync(path.join(candidate, 'cli', 'main.py'))) {
    return candidate;
  }
  return null;
}

// ---------------------------------------------------------------------------
// PersistentProcess — keep a single backend alive for the VS Code session
// ---------------------------------------------------------------------------

class PersistentProcess {
  /**
   * @param {object} runner ExeRunner or VenvRunner
   */
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

  /** Spawn the backend with --server flag and wait for the ready signal. */
  async start() {
    if (this._ready && this._proc && !this._proc.killed) return;
    if (this._starting && this._startPromise) return this._startPromise;

    this._starting = true;
    this._startPromise = this._doStart();
    try {
      await this._startPromise;
    } finally {
      this._starting = false;
      this._startPromise = null;
    }
  }

  async _doStart() {
    // Kill any lingering process
    this.kill();

    const spec = this._runner.buildSpawn(['--server']);
    if (_outputChannel) {
      _outputChannel.appendLine(`[FRP] Persistent: starting ${spec.cmd} --server`);
    }

    this._proc = spawn(spec.cmd, spec.args || [], {
      cwd: spec.cwd || undefined,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });

    // Collect stderr for logging
    this._proc.stderr.on('data', (chunk) => {
      if (_outputChannel) {
        _outputChannel.appendLine(`[FRP][server-stderr] ${chunk.toString().trim()}`);
      }
    });

    this._proc.on('error', (err) => {
      if (_outputChannel) {
        _outputChannel.appendLine(`[FRP] Persistent process error: ${err.message}`);
      }
      this._ready = false;
      // Reject all pending requests
      for (const p of this._pending) {
        p.reject(new Error(`Backend process error: ${err.message}`));
      }
      this._pending = [];
    });

    this._proc.on('exit', (code) => {
      if (_outputChannel) {
        _outputChannel.appendLine(`[FRP] Persistent process exited (code ${code})`);
      }
      this._ready = false;
      // Reject all pending requests
      for (const p of this._pending) {
        p.reject(new Error(`Backend process exited (code ${code})`));
      }
      this._pending = [];
    });

    // Read line-by-line from stdout
    this._rl = readline.createInterface({ input: this._proc.stdout });

    this._rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const obj = JSON.parse(trimmed);
        // If this is the ready signal, resolve the start promise
        if (obj.status === 'ready' && !this._ready) {
          this._ready = true;
          return;  // Don't deliver to pending — this is internal
        }
        // Skip drain entries (late responses from timed-out commands)
        while (this._pending.length > 0 && this._pending[0]._drain) {
          const drain = this._pending.shift();
          if (_outputChannel) {
            _outputChannel.appendLine(`[FRP] Discarding late response for timed-out command: ${drain._command}`);
          }
          return;  // This response was for the timed-out command — consumed
        }
        // Deliver to the oldest pending request
        const p = this._pending.shift();
        if (p) p.resolve(obj);
      } catch (_) {
        if (_outputChannel) {
          _outputChannel.appendLine(`[FRP][server-stdout] non-JSON: ${trimmed}`);
        }
      }
    });

    // Wait for the ready signal (timeout 10s)
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        if (!this._ready) {
          this.kill();
          reject(new Error('Backend server did not become ready within 10s'));
        }
      }, 10000);

      const check = setInterval(() => {
        if (this._ready) {
          clearInterval(check);
          clearTimeout(timeout);
          resolve();
        }
      }, 50);
    });

    if (_outputChannel) {
      _outputChannel.appendLine('[FRP] Persistent backend ready');
    }
  }

  /**
   * Send a command to the persistent process and return the JSON response.
   * @param {string} command  e.g. "search_jobs"
   * @param {Object} args     key-value pairs (snake_case keys)
   * @param {number} [timeoutMs=30000]
   * @returns {Promise<Object>}
   */
  async send(command, args = {}, timeoutMs = 30000) {
    // Auto-start / restart if needed
    if (!this._ready || !this._proc || this._proc.killed) {
      await this.start();
    }

    const request = JSON.stringify({ command, args }) + '\n';

    return new Promise((resolve, reject) => {
      const useTimeout = Number.isFinite(timeoutMs) && timeoutMs > 0;
      let timer = null;
      if (useTimeout) {
        timer = setTimeout(() => {
          // Replace with a drain entry that silently absorbs the late response
          // so it doesn't corrupt the next real command's result
          const idx = this._pending.findIndex((p) => p._timer === timer);
          if (idx !== -1) {
            this._pending[idx] = { resolve: () => {}, reject: () => {}, _drain: true, _command: command };
          }
          reject(new Error(`Command '${command}' timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      }

      const entry = { resolve, reject, _timer: timer, _command: command };
      this._pending.push(entry);

      // Wrap resolve/reject to clear timer
      const origResolve = resolve;
      const origReject = reject;
      entry.resolve = (val) => { if (timer) clearTimeout(timer); origResolve(val); };
      entry.reject = (err) => { if (timer) clearTimeout(timer); origReject(err); };

      try {
        this._proc.stdin.write(request);
      } catch (err) {
        if (timer) clearTimeout(timer);
        this._pending.pop();
        reject(new Error(`Failed to write to backend: ${err.message}`));
      }
    });
  }

  /** Send __ping__ to check liveness. */
  async ping() {
    const result = await this.send('__ping__', {}, 5000);
    return result && result.pong === true;
  }

  /** Kill the backend process. */
  kill() {
    this._ready = false;
    if (this._rl) {
      this._rl.close();
      this._rl = null;
    }
    if (this._proc && !this._proc.killed) {
      try {
        this._proc.stdin.end();
        this._proc.kill('SIGTERM');
      } catch (_) { /* already dead */ }
    }
    this._proc = null;
    // Reject any pending
    for (const p of this._pending) {
      p.reject(new Error('Backend killed'));
    }
    this._pending = [];
  }
}

// ---------------------------------------------------------------------------
// runCliJson — spawn the CLI, capture output, parse JSON
// ---------------------------------------------------------------------------

/**
 * Run a CLI command and return the parsed JSON result.
 *
 * Prefers the persistent (stdin/stdout) process for speed.
 * Falls back to spawning a fresh process if the persistent channel
 * is unavailable or errored.
 *
 * @param {string[]} args  CLI arguments (e.g. ['search_jobs', '--query', 'BofA'])
 * @param {Object}   [opts]
 * @param {number}   [opts.timeoutMs=30000]  Timeout in milliseconds
 * @returns {Promise<Object>}
 */
function runCliJson(args, opts = {}) {
  const timeoutMs = Object.prototype.hasOwnProperty.call(opts, 'timeoutMs') ? opts.timeoutMs : 30000;

  // --- Try persistent process first ---------------------------------- //
  if (_persistent && _persistent._ready) {
    const command = args[0];
    // Convert CLI flags back to an args object for the server protocol
    const serverArgs = {};
    for (let i = 1; i < args.length; i++) {
      const flag = args[i];
      if (flag.startsWith('--')) {
        const key = flag.slice(2).replace(/-/g, '_');
        const next = args[i + 1];
        if (next !== undefined && !next.startsWith('--')) {
          serverArgs[key] = next;
          i++; // skip the value
        } else {
          serverArgs[key] = true; // boolean flag
        }
      }
    }

    return _persistent.send(command, serverArgs, timeoutMs).catch((err) => {
      if (_outputChannel) {
        _outputChannel.appendLine(`[FRP] Persistent send failed, falling back to spawn: ${err.message}`);
      }
      // Do NOT spawn a fallback for sync_logs — the persistent process is
      // still finishing the work and a parallel spawn causes
      // "sqlite3.OperationalError: database is locked".
      if (command === 'sync_logs') {
        if (_outputChannel) {
          _outputChannel.appendLine(`[FRP] Skipping spawn fallback for sync_logs (persistent still running)`);
        }
        return { status: 'ok', command: 'sync_logs', skipped: true };
      }
      return _runCliJsonSpawn(args, timeoutMs);
    });
  }

  // --- Fallback: spawn a fresh process ------------------------------- //
  return _runCliJsonSpawn(args, timeoutMs);
}

/**
 * Spawn a one-shot process (original behavior, used as fallback).
 */
function _runCliJsonSpawn(args, timeoutMs) {

  if (!_runner) {
    return Promise.reject(new Error('Backend runner not initialised. Call initBackendRunner first.'));
  }

  const spawnSpec = _runner.buildSpawn(args);

  return new Promise((resolve, reject) => {
    const stdoutChunks = [];
    const stderrChunks = [];

    if (_outputChannel) {
      _outputChannel.appendLine(`[FRP] Spawning: ${spawnSpec.cmd} ${(spawnSpec.args || []).join(' ')}`);
    }

    const child = spawn(spawnSpec.cmd, spawnSpec.args || [], {
      cwd: spawnSpec.cwd || undefined,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });

    const useTimeout = Number.isFinite(timeoutMs) && timeoutMs > 0;
    const timer = useTimeout ? setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`CLI timed out after ${timeoutMs}ms`));
    }, timeoutMs) : null;

    child.stdout.on('data', (chunk) => stdoutChunks.push(chunk));
    child.stderr.on('data', (chunk) => stderrChunks.push(chunk));

    child.on('error', (err) => {
      if (timer) clearTimeout(timer);
      reject(new Error(`Failed to spawn backend: ${err.message}`));
    });

    child.on('close', (code) => {
      if (timer) clearTimeout(timer);

      const stdout = Buffer.concat(stdoutChunks).toString('utf-8').trim();
      const stderr = Buffer.concat(stderrChunks).toString('utf-8').trim();

      if (stderr && _outputChannel) {
        _outputChannel.appendLine(`[FRP][stderr] ${stderr.slice(0, 1000)}`);
      }

      if (code !== 0 && !stdout) {
        reject(new Error(`CLI exited with code ${code}: ${stderr || '(no output)'}`));
        return;
      }

      // Find the first line that looks like JSON
      const lines = stdout.split('\n');
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i].trim();
        if (line.startsWith('{') || line.startsWith('[')) {
          try {
            resolve(JSON.parse(line));
            return;
          } catch (_) {
            // continue searching
          }
        }
      }

      // Didn't find JSON — try parsing full stdout
      try {
        resolve(JSON.parse(stdout));
      } catch (_) {
        reject(new Error(`CLI returned non-JSON output: ${stdout.slice(0, 300)}`));
      }
    });
  });
}

module.exports = {
  ExeRunner,
  VenvRunner,
  initBackendRunner,
  startPersistentBackend,
  shutdownBackend,
  runCliJson,
};
