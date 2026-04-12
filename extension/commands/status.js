const vscode = require('vscode');
const { backendCall } = require('../copilot/tool');

/**
 * Command handler: FRP Agent: Status
 * Queries the backend for current status and version info.
 */
module.exports = async function showStatus(shared) {
  shared.outputChannel.appendLine('[FRP] Checking backend status...');

  const result = await backendCall('status', {}, shared);

  if (result && result.success) {
    const d = result.data || {};
    const version = d.version || 'unknown';
    const config = vscode.workspace.getConfiguration('frpAgent');
    const dbMode = config.get('prod', false) ? 'mssql' : 'mysql';
    const backendMode = config.get('backendMode', 'venv');
    const msg = `FRP Agent v${version} | DB: ${dbMode} | Backend: ${backendMode}`;
    vscode.window.showInformationMessage(msg);
    shared.outputChannel.appendLine(`[FRP] Status: ${msg}`);
  } else {
    const errors = (result && result.errors) || [];
    const msg = errors.length ? errors.join('; ') : (result && result.error) || 'Backend not reachable.';
    vscode.window.showWarningMessage(`FRP Agent: ${msg}`);
    shared.outputChannel.appendLine(`[FRP] Status check failed: ${msg}`);
  }
};
