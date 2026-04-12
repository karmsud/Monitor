const vscode = require('vscode');
const { backendCall } = require('../copilot/tool');

/**
 * Command handler: FRP Agent: Sync Logs
 * Triggers a log sync operation via the backend CLI.
 */
module.exports = async function syncLogs(shared) {
  const config = vscode.workspace.getConfiguration('frpAgent');
  const emailLogFolder = config.get('emailLogFolder', '');
  const sftpLogFolder = config.get('sftpLogFolder', '');
  const retentionMonths = config.get('logRetentionMonths', 3);

  if (!emailLogFolder && !sftpLogFolder) {
    vscode.window.showWarningMessage(
      'FRP Agent: No log folders configured. Set frpAgent.emailLogFolder or frpAgent.sftpLogFolder in settings.'
    );
    return;
  }

  shared.outputChannel.appendLine('[FRP] Syncing logs...');

  const params = {};
  if (emailLogFolder) params.logFolder = emailLogFolder;
  if (sftpLogFolder) params.sftpLogFolder = sftpLogFolder;
  params.retentionMonths = retentionMonths;

  const result = await backendCall('sync_logs', params, shared);

  if (result && result.success) {
    const d = result.data || {};
    const processed = d.files_processed || 0;
    const indexed = d.events_indexed || 0;
    const purged = d.events_purged || 0;
    const msg = `Synced ${processed} file(s) — ${indexed} events indexed, ${purged} old events purged.`;
    vscode.window.showInformationMessage(`FRP Agent: ${msg}`);
    shared.outputChannel.appendLine(`[FRP] Log sync complete — ${msg}`);
  } else {
    const errors = (result && result.errors) || [];
    const msg = errors.length ? errors.join('; ') : (result && result.error) || 'Unknown error during log sync.';
    vscode.window.showErrorMessage(`FRP Agent: Log sync failed — ${msg}`);
    shared.outputChannel.appendLine(`[FRP] Log sync failed: ${msg}`);
  }
};
