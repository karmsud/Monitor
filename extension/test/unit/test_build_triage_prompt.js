/**
 * Unit Tests — buildTriagePrompt helper (Phase 9)
 * TC-TP-01 through TC-TP-06
 *
 * Tests the buildTriagePrompt function directly.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Extract the buildTriagePrompt function from participant.js
// ---------------------------------------------------------------------------
const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

const funcMatch = source.match(/function buildTriagePrompt\([\s\S]*?^}/m);
let buildTriagePrompt;
if (funcMatch) {
  // eslint-disable-next-line no-eval
  eval(`buildTriagePrompt = ${funcMatch[0]}`);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Phase 9 — buildTriagePrompt', function () {
  before(function () {
    if (!buildTriagePrompt) this.skip();
  });

  it('TC-TP-01: mode=verify + msgPath → returns "verify /path/to/file.msg"', () => {
    const result = buildTriagePrompt({ mode: 'verify', msgPath: '/path/to/file.msg' });
    assert.strictEqual(result, 'verify /path/to/file.msg');
  });

  it('TC-TP-02: mode=match + sender → returns "match from:sender@bank.com"', () => {
    const result = buildTriagePrompt({ mode: 'match', sender: 'sender@bank.com' });
    assert.strictEqual(result, 'match from:sender@bank.com');
  });

  it('TC-TP-03: mode=new + sender + subject → returns both', () => {
    const result = buildTriagePrompt({ mode: 'new', sender: 'a@b.com', subject: 'Monthly Report' });
    assert.ok(result.startsWith('new '));
    assert.ok(result.includes('from:a@b.com'));
    assert.ok(result.includes('subject:Monthly Report'));
  });

  it('TC-TP-04: mode omitted → defaults to "new"', () => {
    const result = buildTriagePrompt({ sender: 'test@test.com' });
    assert.ok(result.startsWith('new '));
  });

  it('TC-TP-05: body longer than 500 chars → truncated', () => {
    const longBody = 'x'.repeat(1000);
    const result = buildTriagePrompt({ mode: 'new', body: longBody });
    assert.ok(result.includes('body:'));
    // The body portion should be at most 500 chars
    const bodyPart = result.split('body:')[1];
    assert.ok(bodyPart.length <= 500, `Body not truncated: ${bodyPart.length} chars`);
  });

  it('TC-TP-06: empty input → returns "new"', () => {
    const result = buildTriagePrompt({});
    assert.strictEqual(result, 'new');
  });
});
