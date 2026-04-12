/**
 * Mocha test suite index — discovers and runs all *.test.js files.
 */
const path = require('path');
const Mocha = require('mocha');
const { glob } = require('glob');

async function run() {
  console.log('[Environment B] Test runner starting…');

  try {
    const mocha = new Mocha({
      ui: 'tdd',          // backend.test.js uses suite/test/suiteSetup (TDD)
      color: true,
      timeout: 30000,     // 30s per test — CLI calls can be slow
    });

    const testsRoot = __dirname;
    const files = await glob('**/*.test.js', { cwd: testsRoot });
    console.log(`[Environment B] Found ${files.length} test file(s):`, files);

    for (const f of files) {
      mocha.addFile(path.resolve(testsRoot, f));
    }

    return new Promise((resolve, reject) => {
      mocha.run((failures) => {
        console.log(`[Environment B] Mocha finished — ${failures} failure(s)`);
        if (failures > 0) {
          reject(new Error(`${failures} test(s) failed.`));
        } else {
          resolve();
        }
      });
    });
  } catch (err) {
    console.error('[Environment B] Runner error:', err);
    throw err;
  }
}

module.exports = { run };
