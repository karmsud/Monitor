/**
 * Activation Smoke Test
 * =====================
 * Verifies the FRP Agent extension activates successfully and registers
 * its chat participant + commands. Run via F5 → "Extension Tests (Environment B)".
 */
const assert = require('assert');
const vscode = require('vscode');

const EXTENSION_ID = 'your-publisher-id.frp-agent-extension';
const PARTICIPANT_ID = 'frp-agent.assistant';

suite('Activation Smoke Tests', function () {
  this.timeout(30000);

  test('Extension is present and can activate', async function () {
    const ext = vscode.extensions.getExtension(EXTENSION_ID);
    assert.ok(ext, `Extension ${EXTENSION_ID} should be present`);

    if (!ext.isActive) {
      await ext.activate();
    }
    assert.strictEqual(ext.isActive, true, 'Extension should be active');
  });

  test('Chat participant commands are registered', async function () {
    const commands = await vscode.commands.getCommands(true);
    const frpCommands = commands.filter(c => c.startsWith('frp'));
    assert.ok(frpCommands.length >= 2, `Expected at least 2 frp commands, got ${frpCommands.length}: ${frpCommands.join(', ')}`);
  });

  test('participant.js loads without SyntaxError', function () {
    // Direct require — will throw SyntaxError if backticks are broken
    assert.doesNotThrow(() => {
      require('../../chat/participant');
    }, SyntaxError, 'participant.js should load without SyntaxError');
  });
});
