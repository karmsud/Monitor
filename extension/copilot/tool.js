const vscode = require('vscode');
const { runCliJson } = require('../lib/frp_backend');

/**
 * Convert a camelCase key to --kebab-case CLI flag.
 * e.g. "settingsPath" → "--settings-path"
 */
function toKebabFlag(key) {
  const kebab = key.replace(/([A-Z])/g, '-$1').toLowerCase();
  return `--${kebab}`;
}

// ---------------------------------------------------------------------------
// Per-command whitelist — only inject a global flag when the command accepts it
// ---------------------------------------------------------------------------
const _ACCEPTS = {
  settingsPath: new Set([
    'search_jobs', 'job_detail', 'deal_lookup', 'validate_xml', 'servicer_dossier', 'list_backups', 'save_xml',
    'create_job', 'edit_job', 'template_inventory', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'xml_diff', 'rollback_xml', 'triage_verify', 'triage_match',
    'triage_new', 'log_performance', 'analyze_consolidation', 'analyze_impact', 'analyze_health',
    'deal_pipeline', 'staging_linkage', 'staging_audit', 'log_linkage', 'rebuild_db',
    'clone_prepare', 'clone_preview', 'clone_apply',
  ]),
  sftpSettingsPath: new Set([
    'search_jobs', 'job_detail', 'deal_lookup', 'servicer_dossier', 'staging_linkage', 'staging_audit', 'log_linkage', 'rebuild_db',
    'clone_prepare', 'clone_preview', 'clone_apply',
  ]),
  dbMode: new Set([
    'job_detail', 'deal_lookup', 'validate_xml', 'servicer_dossier', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'log_deal_activity', 'triage_verify', 'triage_new',
    'analyze_consolidation', 'analyze_impact', 'analyze_health',
    'template_status', 'processing_history', 'failure_analysis', 'source_trace',
    'manual_queue_report', 'processing_duration', 'deal_pipeline', 'staging_search',
    'staging_linkage', 'staging_audit', 'log_linkage',
  ]),
  logFolder: new Set([
    'sync_logs',
  ]),
  sftpLogFolder: new Set([
    'sync_logs',
  ]),
  retentionMonths: new Set([
    'sync_logs',
  ]),
  // --db-path for log SQLite commands
  dbPath: new Set([
    'sync_logs', 'log_deal_activity', 'log_did_failures', 'log_job_health',
    'log_daily_summary', 'log_trends', 'log_performance', 'log_search', 'log_linkage',
    'analyze_impact', 'analyze_health',
  ]),
  // --log-db-path (different flag name for servicer_dossier)
  logDbPath: new Set([
    'servicer_dossier',
  ]),
  // --cache-db-path for XML cache SQLite
  cacheDbPath: new Set([
    'search_jobs', 'job_detail', 'deal_lookup', 'create_job', 'edit_job', 'rebuild_db',
    'next_servicer_id', 'staging_linkage', 'staging_audit', 'log_linkage', 'clone_apply',
  ]),
  secretsPath: new Set([
    'job_detail', 'deal_lookup', 'validate_xml', 'servicer_dossier', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'log_deal_activity', 'triage_verify', 'triage_new',
    'analyze_consolidation', 'analyze_impact', 'analyze_health',
    'template_status', 'processing_history', 'failure_analysis', 'source_trace',
    'manual_queue_report', 'processing_duration', 'deal_pipeline', 'staging_search',
    'staging_linkage', 'staging_audit', 'log_linkage',
  ]),
  mssqlServer: new Set([
    'job_detail', 'deal_lookup', 'validate_xml', 'servicer_dossier', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'log_deal_activity', 'triage_verify', 'triage_new',
    'analyze_consolidation', 'analyze_impact', 'analyze_health',
    'template_status', 'processing_history', 'failure_analysis', 'source_trace',
    'manual_queue_report', 'processing_duration', 'deal_pipeline', 'staging_search',
    'staging_linkage', 'staging_audit', 'log_linkage',
  ]),
  mssqlDatabase: new Set([
    'job_detail', 'deal_lookup', 'validate_xml', 'servicer_dossier', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'log_deal_activity', 'triage_verify', 'triage_new',
    'analyze_consolidation', 'analyze_impact', 'analyze_health',
    'template_status', 'processing_history', 'failure_analysis', 'source_trace',
    'manual_queue_report', 'processing_duration', 'deal_pipeline', 'staging_search',
    'staging_linkage', 'staging_audit', 'log_linkage',
  ]),
  xmlType: new Set([
    'search_jobs', 'validate_xml', 'list_backups', 'save_xml', 'create_job',
    'edit_job', 'template_inventory', 'coverage_gaps', 'orphan_detection',
    'collision_detection', 'xml_diff', 'rollback_xml', 'triage_verify',
    'triage_match', 'triage_new', 'staging_linkage', 'staging_audit', 'log_linkage',
  ]),
};

/** Return true if `command` accepts the given auto-injected param key. */
function _commandAccepts(command, paramKey) {
  const set = _ACCEPTS[paramKey];
  return set ? set.has(command) : true; // unknown keys pass through
}

// ---------------------------------------------------------------------------
// Auto-sync — currently disabled. Users must run explicit log sync commands.
// ---------------------------------------------------------------------------

/**
 * Automatic log sync is intentionally disabled for all commands.
 * Users must refresh explicitly with `/sync_logs` or `/logs sync` when they
 * want a fresh index.
 */
const _AUTO_SYNC_COMMANDS = new Set();

function _shouldAutoSync(command) {
  return _AUTO_SYNC_COMMANDS.has(command);
}

function _hasExplicitParam(params, key) {
  return Object.prototype.hasOwnProperty.call(params, key);
}

/** Per-command timeout overrides (ms). Commands not listed use the 30 s default. */
const _COMMAND_TIMEOUTS = {
  sync_logs: 180000,   // can take up to ~2 min indexing thousands of log files
  log_search: 90000,   // LIKE queries on network-mounted SQLite can be slow
  staging_search: 90000, // MSSQL cross-database joins can be slow
};

/**
 * Run an incremental log sync if log-related settings are configured.
 * This helper is retained for potential future opt-in behavior, but the
 * current command set does not invoke it because `_AUTO_SYNC_COMMANDS` is empty.
 */
async function _autoSync(shared) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const logDbPath = config.get('logDbPath', '');
  if (!logDbPath) return;

  const emailFolder = config.get('emailLogFolder', '');
  const sftpFolder = config.get('sftpLogFolder', '');
  if (!emailFolder && !sftpFolder) return;

  const retentionMonths = config.get('logRetentionMonths', 3);
  const args = ['sync_logs'];
  if (emailFolder) args.push('--log-folder', emailFolder);
  if (sftpFolder) args.push('--sftp-log-folder', sftpFolder);
  args.push('--db-path', logDbPath);
  args.push('--retention-months', String(retentionMonths));

  try {
    await runCliJson(args);
  } catch (err) {
    if (shared.outputChannel) {
      shared.outputChannel.appendLine(`[FRP] Auto-sync: ${err.message}`);
    }
  }
}

// ---------------------------------------------------------------------------
// backendCall — main entry point for the extension → CLI bridge
// ---------------------------------------------------------------------------

/**
 * Call the FRP Agent backend CLI with a command and parameters.
 *
 * Auto-populates common settings from VS Code configuration:
 *   - settingsPath (outlookSettingsPath)
 *   - sftpSettingsPath
 *   - dbMode (prod → mssql / mysql)
 *   - logFolder (emailLogFolder)
 *   - sftpLogFolder
 *   - retentionMonths (logRetentionMonths)
 *   - dbPath / logDbPath (logDbPath setting)
 *
 * Automatic pre-query log sync is disabled. Users must call explicit sync
 * commands when they need the SQLite log index refreshed.
 *
 * Only injects a global flag when the target command actually accepts it.
 *
 * @param {string}  command  CLI command name (e.g. 'search_jobs', 'servicer_dossier')
 * @param {Object}  params   Additional key-value params to pass as CLI flags
 * @param {Object}  shared   Shared context { context, outputChannel, workspaceRoot }
 * @returns {Promise<Object>} Parsed JSON result from the CLI
 */
async function backendCall(command, params = {}, shared = {}, opts = {}) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const verbose = config.get('logLevel', 'normal') === 'verbose';
  const outputChannel = shared.outputChannel;

  // ── Auto-sync log index (disabled unless `_AUTO_SYNC_COMMANDS` is populated) ── //
  if (_shouldAutoSync(command)) {
    await _autoSync(shared);
  }

  // Auto-populate settings from VS Code config if not already specified.
  // Each block is guarded by _commandAccepts so we never inject a flag
  // the target sub-command doesn't recognise.
  const merged = { ...params };

  if (!_hasExplicitParam(merged, 'settingsPath') && _commandAccepts(command, 'settingsPath')) {
    const outlookPath = config.get('outlookSettingsPath', '');
    if (outlookPath) merged.settingsPath = outlookPath;
  }

  if (!_hasExplicitParam(merged, 'sftpSettingsPath') && _commandAccepts(command, 'sftpSettingsPath')) {
    const sftpPath = config.get('sftpSettingsPath', '');
    if (sftpPath) merged.sftpSettingsPath = sftpPath;
  }

  if (!_hasExplicitParam(merged, 'dbMode') && _commandAccepts(command, 'dbMode')) {
    const prod = config.get('prod', false);
    merged.dbMode = prod ? 'mssql' : 'mysql';
  }

  if (!_hasExplicitParam(merged, 'logFolder') && _commandAccepts(command, 'logFolder')) {
    const emailLog = config.get('emailLogFolder', '');
    if (emailLog) merged.logFolder = emailLog;
  }

  if (!_hasExplicitParam(merged, 'sftpLogFolder') && _commandAccepts(command, 'sftpLogFolder')) {
    const sftpLog = config.get('sftpLogFolder', '');
    if (sftpLog) merged.sftpLogFolder = sftpLog;
  }

  if (!_hasExplicitParam(merged, 'retentionMonths') && _commandAccepts(command, 'retentionMonths')) {
    const retention = config.get('logRetentionMonths', 3);
    if (retention) merged.retentionMonths = retention;
  }

  // logDbPath → --db-path for log commands
  if (!_hasExplicitParam(merged, 'dbPath') && _commandAccepts(command, 'dbPath')) {
    const logDb = config.get('logDbPath', '');
    if (logDb) merged.dbPath = logDb;
  }

  // logDbPath → --log-db-path for servicer_dossier
  if (!_hasExplicitParam(merged, 'logDbPath') && _commandAccepts(command, 'logDbPath')) {
    const logDb = config.get('logDbPath', '');
    if (logDb) merged.logDbPath = logDb;
  }

  // cacheDbPath → --cache-db-path for XML cache SQLite
  if (!_hasExplicitParam(merged, 'cacheDbPath') && _commandAccepts(command, 'cacheDbPath')) {
    const cacheDb = config.get('cacheDbPath', '');
    if (cacheDb) merged.cacheDbPath = cacheDb;
  }

  if (!_hasExplicitParam(merged, 'secretsPath') && _commandAccepts(command, 'secretsPath')) {
    const prod = config.get('prod', false);
    const defaultSecretsFile = prod ? 'secrets_mssql.json' : 'secrets_mysql.json';
    // Resolve relative to workspace root so it works in both dev and VSIX mode
    const workspaceRoot = shared.workspaceRoot
      || (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0]
        ? vscode.workspace.workspaceFolders[0].uri.fsPath : '');
    if (workspaceRoot) {
      const path = require('path');
      const candidate = path.join(workspaceRoot, 'config', defaultSecretsFile);
      if (require('fs').existsSync(candidate)) {
        merged.secretsPath = candidate;
      }
    }
  }

  if (!_hasExplicitParam(merged, 'mssqlServer') && _commandAccepts(command, 'mssqlServer')) {
    const mssqlServer = config.get('mssqlServer', '');
    if (mssqlServer) merged.mssqlServer = mssqlServer;
  }

  if (!_hasExplicitParam(merged, 'mssqlDatabase') && _commandAccepts(command, 'mssqlDatabase')) {
    const mssqlDatabase = config.get('mssqlDatabase', '');
    if (mssqlDatabase) merged.mssqlDatabase = mssqlDatabase;
  }

  // Build CLI args array
  const args = [command];
  for (const [key, value] of Object.entries(merged)) {
    if (value === undefined || value === null || value === '') continue;
    const flag = toKebabFlag(key);
    if (typeof value === 'boolean') {
      if (value) args.push(flag);
    } else {
      args.push(flag, String(value));
    }
  }

  if (verbose && outputChannel) {
    outputChannel.appendLine(`[FRP][verbose] backendCall → ${args.join(' ')}`);
  }

  try {
    const timeoutMs = Object.prototype.hasOwnProperty.call(opts, 'timeoutMs')
      ? opts.timeoutMs
      : (_COMMAND_TIMEOUTS[command] || 30000);
    const result = await runCliJson(args, { timeoutMs });

    if (verbose && outputChannel) {
      outputChannel.appendLine(`[FRP][verbose] backendCall result: ${JSON.stringify(result).slice(0, 500)}`);
    }

    return result;
  } catch (err) {
    if (outputChannel) {
      outputChannel.appendLine(`[FRP] backendCall error (${command}): ${err.message}`);
    }
    return { status: 'error', error: err.message };
  }
}

module.exports = { backendCall, toKebabFlag };
