const vscode = require('vscode');
const { registerChatParticipant } = require('./chat/participant');
const { initBackendRunner, startPersistentBackend, shutdownBackend } = require('./lib/frp_backend');
const { backendCall } = require('./copilot/tool');

/**
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('FRP Agent', { log: true });
  outputChannel.appendLine('[FRP] Activating...');

  const shared = {
    context,
    outputChannel,
    workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '',
    pendingOperation: null,
  };

  // Initialize backend runner (venv or exe based on settings)
  await initBackendRunner(vscode, context, outputChannel);

  // Start the persistent backend process (keeps it warm for fast responses)
  await startPersistentBackend();

  // Register chat participant
  registerChatParticipant(vscode, context, shared);

  // Register VS Code commands
  function register(command, handler) {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, async () => {
        try {
          await handler(shared);
        } catch (err) {
          outputChannel.appendLine(`[FRP] ${command} failed: ${err.message}`);
          vscode.window.showErrorMessage(`Command failed: ${err.message}`);
        }
      })
    );
  }

  register('frp-agent.syncLogs', require('./commands/sync'));
  register('frp-agent.status', require('./commands/status'));

  context.subscriptions.push(
    vscode.commands.registerCommand('frp.runInlineChatAction', async (arg) => {
      const prompt = typeof arg === 'string' ? arg : arg?.prompt;
      if (!prompt || !String(prompt).trim()) {
        vscode.window.showWarningMessage('No FRP chat action was provided.');
        return;
      }

      const normalizedPrompt = String(prompt).trim();
      const chatPrompt = normalizedPrompt.startsWith('@frp') ? normalizedPrompt : `@frp ${normalizedPrompt}`;
      outputChannel.appendLine(`[FRP] Inline chat action: ${chatPrompt}`);

      try {
        await vscode.commands.executeCommand('workbench.action.chat.open', {
          query: chatPrompt,
          isPartialQuery: false,
        });
        return;
      } catch (err) {
        outputChannel.appendLine(`[FRP] Inline chat action open-submit failed: ${err.message}`);
      }

      try {
        await vscode.commands.executeCommand('workbench.action.chat.focusInput');
        await vscode.commands.executeCommand('workbench.action.chat.submit', {
          inputValue: chatPrompt,
        });
        return;
      } catch (err) {
        outputChannel.appendLine(`[FRP] Inline chat action direct submit failed: ${err.message}`);
      }

      try {
        await vscode.commands.executeCommand('workbench.action.chat.openNewSessionSidebar.local', {
          prompt: chatPrompt,
        });
        return;
      } catch (err) {
        outputChannel.appendLine(`[FRP] Inline chat action fallback triggered: ${err.message}`);
      }

      await vscode.commands.executeCommand('workbench.action.chat.newChat');
      await vscode.env.clipboard.writeText(chatPrompt);
      vscode.window.showInformationMessage('FRP action copied to clipboard. Paste it into chat and send.');
    })
  );

  // ── Confirmation button commands ─────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('frp.confirmPending', async () => {
      const op = shared.pendingOperation;
      if (!op) {
        vscode.window.showWarningMessage('No pending FRP operation to confirm.');
        return;
      }
      shared.pendingOperation = null;
      outputChannel.appendLine(`[FRP] Button confirm: executing ${op.type}`);
      try {
        let result;
        switch (op.type) {
          case 'edit_job':
            result = await backendCall('edit_job', {
              jobName: op.params.jobName, field: op.params.field,
              value: op.params.value, xmlType: op.params.xmlType || 'email',
            }, shared);
            break;
          case 'create_job': {
            // Flatten overrides into individual CLI flags
            const createParams = {
              templateJob: op.params.templateJob, name: op.params.newName,
              xmlType: op.params.xmlType || 'email',
            };
            if (op.params.overrides && typeof op.params.overrides === 'object') {
              for (const [k, v] of Object.entries(op.params.overrides)) {
                if (v !== undefined && v !== null && v !== '') {
                  const camelKey = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
                  createParams[camelKey] = String(v);
                }
              }
            }
            result = await backendCall('create_job', createParams, shared);
            break;
          }
          case 'rollback':
            result = await backendCall('rollback_xml', { backupFile: op.params.backupFile }, shared);
            break;
          default:
            vscode.window.showWarningMessage(`Unknown operation type: ${op.type}`);
            return;
        }
        if (result?.status === 'error' || result?.success === false) {
          vscode.window.showErrorMessage(`FRP operation failed: ${result.error || 'unknown error'}`);
        } else {
          vscode.window.showInformationMessage(`FRP ${op.type} completed successfully.`);
        }
        outputChannel.appendLine(`[FRP] Button confirm result: ${JSON.stringify(result).slice(0, 500)}`);
      } catch (err) {
        outputChannel.appendLine(`[FRP] Button confirm error: ${err.message}`);
        vscode.window.showErrorMessage(`FRP operation failed: ${err.message}`);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('frp.cancelPending', () => {
      if (shared.pendingOperation) {
        shared.pendingOperation = null;
        outputChannel.appendLine('[FRP] Button cancel: pending operation cleared.');
        vscode.window.showInformationMessage('FRP operation cancelled.');
      } else {
        vscode.window.showWarningMessage('No pending FRP operation to cancel.');
      }
    })
  );

  outputChannel.appendLine('[FRP] Activated successfully.');
}

function deactivate() {
  shutdownBackend();
}

module.exports = { activate, deactivate };
