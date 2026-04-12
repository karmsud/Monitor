const assert = require('assert');
const fs = require('fs');
const path = require('path');

const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

function extractFunction(name) {
  const match = source.match(new RegExp(`function ${name}\\([\\s\\S]*?^}`, 'm'));
  if (!match) return null;
  let fn;
  // eslint-disable-next-line no-eval
  eval(`fn = ${match[0]}`);
  return fn;
}

const normalizeDeterministicLogMode = extractFunction('normalizeDeterministicLogMode');
const extractDeterministicDidClue = extractFunction('extractDeterministicDidClue');
const buildDeterministicLogEventEvidence = extractFunction('buildDeterministicLogEventEvidence');
const getDeterministicLogRowFields = extractFunction('getDeterministicLogRowFields');

describe('Deterministic log rendering helpers', function () {
  before(function () {
    if (!normalizeDeterministicLogMode || !extractDeterministicDidClue || !buildDeterministicLogEventEvidence || !getDeterministicLogRowFields) {
      this.skip();
    }
  });

  it('normalizes detail alias to details', () => {
    assert.strictEqual(normalizeDeterministicLogMode('detail'), 'details');
    assert.strictEqual(normalizeDeterministicLogMode('email'), 'emails');
    assert.strictEqual(normalizeDeterministicLogMode('events'), 'events');
  });

  it('extracts subject, file, scrubber, and sender evidence from queued email events', () => {
    const evidence = buildDeterministicLogEventEvidence({
      event_type: 'template_queue',
      subject: 'Monthly remittance package',
      sender: 'ops@usbank.com',
      mailbox: 'ops@usbank.com',
      filename: 'ABS_20260310.zip',
      template: 'QueueCMBS',
      parser: 'DetachFileSubject',
      raw_line: '2026-03-10 10:00:00.000:\tQueue file [ABS_20260310.zip] for [QueueCMBS] template',
    });

    assert.strictEqual(evidence.subject, 'Monthly remittance package');
    assert.strictEqual(evidence.sender, 'ops@usbank.com');
    assert.strictEqual(evidence.filename, 'ABS_20260310.zip');
    assert.strictEqual(evidence.template, 'QueueCMBS');
    assert.strictEqual(evidence.parser, 'DetachFileSubject');
    assert.ok(evidence.compact.includes('Subject: Monthly remittance package'));
    assert.ok(evidence.compact.includes('Scrubber: QueueCMBS'));
  });

  it('extracts matched DID from did_match events', () => {
    const evidence = buildDeterministicLogEventEvidence({
      event_type: 'did_match',
      filename: 'FREMF 2026-KF169',
      raw_line: '2026-03-10 11:00:00.000:\tMatched DID to [FREMF 2026-KF169] and updated save location to [M:\\Deals\\KF169]'
    });

    assert.strictEqual(evidence.did, 'FREMF 2026-KF169');
    assert.ok(evidence.compact.includes('Matched DID: FREMF 2026-KF169'));
  });

  it('extracts unmapped DID clue from failure messages', () => {
    const did = extractDeterministicDidClue({
      event_type: 'did_mapping_failed',
      error_message: 'Did not find DID mapping for [VCC-12345]',
    });

    assert.strictEqual(did, 'VCC-12345');
  });

  it('returns full captured row fields in stable detail order', () => {
    const fields = getDeterministicLogRowFields({
      timestamp: '2026-03-10 10:00:00.000',
      log_file: 'Email Logs\\2026-03-10.log',
      log_type: 'email',
      job_name: 'CMBS_FreddieMac',
      mailbox: 'ops@example.com',
      event_type: 'template_queue',
      emails_found: 1,
      subject: 'Monthly remittance package',
      sender: 'ops@usbank.com',
      parser: 'DetachFileSubject',
      filename: 'ABS_20260310.zip',
      template: 'QueueCMBS',
      error_message: '',
      raw_line: 'Queue file [ABS_20260310.zip] for [QueueCMBS] template',
      extra_hint: 'custom',
    });

    assert.deepStrictEqual(fields.map((field) => field.key), [
      'timestamp',
      'log_file',
      'log_type',
      'job_name',
      'mailbox',
      'event_type',
      'emails_found',
      'subject',
      'sender',
      'parser',
      'filename',
      'template',
      'error_message',
      'raw_line',
      'extra_hint',
    ]);
  });
});