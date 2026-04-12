const assert = require('assert');
const fs = require('fs');
const path = require('path');

const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

function extractFunction(name) {
  const match = source.match(new RegExp(`function ${name}\\([\\s\\S]*?^}`, 'm'));
  return match ? match[0] : null;
}

function extractConst(name) {
  const match = source.match(new RegExp(`const ${name} = \\{[\\s\\S]*?\\n\\};`, 'm'));
  return match ? match[0] : null;
}

let DETERMINISTIC_TRIAGE_FIELD_ALIASES;
const aliasesBlock = extractConst('DETERMINISTIC_TRIAGE_FIELD_ALIASES');
if (aliasesBlock) {
  // eslint-disable-next-line no-eval
  eval(aliasesBlock.replace('const DETERMINISTIC_TRIAGE_FIELD_ALIASES =', 'DETERMINISTIC_TRIAGE_FIELD_ALIASES ='));
}

for (const fnName of [
  'splitDeterministicClauses',
  'isSlashHelpPrompt',
  'extractMsgPath',
  'stripDeterministicTriageQuotes',
  'looksLikeMsgPath',
  'normalizeDeterministicTriageField',
  'parseDeterministicTriageFieldClause',
  'parseDeterministicTriageClauses',
  'parseDeterministicTriagePrompt',
]) {
  const fnSource = extractFunction(fnName);
  if (fnSource) {
    // eslint-disable-next-line no-eval
    eval(fnSource);
  }
}

describe('Deterministic triage prompt parsing', function () {
  before(function () {
    if (typeof parseDeterministicTriagePrompt !== 'function') {
      this.skip();
    }
  });

  it('returns help for slash-help prompts', () => {
    const parsed = parseDeterministicTriagePrompt('help');
    assert.deepStrictEqual(parsed, { help: true });
  });

  it('infers trace action from a bare quoted .msg path', () => {
    const parsed = parseDeterministicTriagePrompt('"M:\\Mail\\sample.msg"');
    assert.strictEqual(parsed.action, 'trace');
    assert.strictEqual(parsed.msgPath, 'M:\\Mail\\sample.msg');
    assert.strictEqual(parsed.inferredAction, true);
  });

  it('parses verify with a .msg path', () => {
    const parsed = parseDeterministicTriagePrompt('verify M:\\Mail\\sample.msg');
    assert.strictEqual(parsed.action, 'verify');
    assert.strictEqual(parsed.msgPath, 'M:\\Mail\\sample.msg');
  });

  it('parses match sender and subject metadata', () => {
    const parsed = parseDeterministicTriagePrompt('match sender:reports@fay.com; subject:Monthly Report');
    assert.strictEqual(parsed.action, 'match');
    assert.strictEqual(parsed.sender, 'reports@fay.com');
    assert.strictEqual(parsed.subject, 'Monthly Report');
  });

  it('parses trace metadata with mailbox, filename, and days', () => {
    const parsed = parseDeterministicTriagePrompt('trace sender:reports@fay.com; mailbox:rptent@usbank.com; subject:Monthly Report; filename:deal_20260310.xlsx; days:7');
    assert.strictEqual(parsed.action, 'trace');
    assert.strictEqual(parsed.sender, 'reports@fay.com');
    assert.strictEqual(parsed.mailbox, 'rptent@usbank.com');
    assert.strictEqual(parsed.subject, 'Monthly Report');
    assert.strictEqual(parsed.filename, 'deal_20260310.xlsx');
    assert.strictEqual(parsed.days, '7');
  });

  it('rejects metadata triage without sender or subject', () => {
    const parsed = parseDeterministicTriagePrompt('trace mailbox:rptent@usbank.com; filename:deal_20260310.xlsx');
    assert.ok(parsed.error);
    assert.ok(parsed.error.includes('sender') || parsed.error.includes('subject'));
  });
});