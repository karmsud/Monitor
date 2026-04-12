/**
 * Extension Host Test Runner — launches VS Code with our extension and runs mocha tests.
 *
 * Usage:  node extension/test/runTest.js
 */
const path = require('path');
const { runTests } = require('@vscode/test-electron');

async function main() {
  try {
    const extensionDevelopmentPath = path.resolve(__dirname, '..');
    const extensionTestsPath = path.resolve(__dirname, 'suite', 'index');

    // The workspace to open — our project root
    const workspacePath = path.resolve(__dirname, '..', '..');

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      launchArgs: [
        workspacePath,
        '--disable-extensions',   // disable other extensions to isolate tests
      ],
    });
  } catch (err) {
    console.error('Failed to run tests:', err);
    process.exit(1);
  }
}

main();
