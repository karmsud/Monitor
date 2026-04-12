/**
 * Unit Tests — resolveCurrentFieldValue helper (Phase 9)
 * TC-RFV-01 through TC-RFV-04, TC-S503-01 through TC-S503-06
 *
 * Tests the resolveCurrentFieldValue function directly.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Extract the resolveCurrentFieldValue function from participant.js
// ---------------------------------------------------------------------------
const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

const funcMatch = source.match(/function resolveCurrentFieldValue\([\s\S]*?^}/m);
let resolveCurrentFieldValue;
if (funcMatch) {
  // eslint-disable-next-line no-eval
  eval(`resolveCurrentFieldValue = ${funcMatch[0]}`);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Phase 9 — resolveCurrentFieldValue', function () {
  before(function () {
    if (!resolveCurrentFieldValue) this.skip();
  });

  const emailJob = {
    data: {
      job: {
        scrubber: 'Outlook_Queuer',
        servicer_id: 296,
        mailbox: 'test@example.com',
        folder: 'Inbox',
        sme: 'JohnDoe',
        save_path: 'M:\\Data',          // API returns 'save_path'
        sender: 'reports@bank.com',      // API returns 'sender'
        day_adjust: 5,
        job_name: 'TestJob',             // API returns 'job_name'
        last_email: '2/13/2026',
        queue_one_file: true,
      },
    },
  };

  const sftpJob = {
    data: {
      job: {
        sftp_path: '/Inbox/Reports',     // API returns 'sftp_path'
        dsn: 'MyDSN',
        skip_list: 'skip1.txt',
        ignore_list: 'ignore1.txt',
        zip_filter: '*.csv',             // API returns 'zip_filter'
      },
    },
  };

  // ── Email field tests ──
  it('TC-RFV-01: field=scrubber → returns job.scrubber', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'scrubber', 'email'), 'Outlook_Queuer');
  });

  it('TC-RFV-02: field=servicer_id → returns string of job.servicer_id', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'servicer_id', 'email'), '296');
  });

  it('TC-RFV-03: field=scrubber with no scrubber key → returns empty string', () => {
    assert.strictEqual(resolveCurrentFieldValue({ data: { job: {} } }, 'scrubber', 'email'), '');
  });

  it('TC-RFV-04: unknown field → returns empty string', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'nonexistent_field', 'email'), '');
  });

  // ── SFTP field tests ──
  it('TC-S503-01: field=path → returns job.sftp_path (API key)', () => {
    assert.strictEqual(resolveCurrentFieldValue(sftpJob, 'path', 'sftp'), '/Inbox/Reports');
  });

  it('TC-S503-02: field=dsn → returns job.dsn', () => {
    assert.strictEqual(resolveCurrentFieldValue(sftpJob, 'dsn', 'sftp'), 'MyDSN');
  });

  it('TC-S503-03: field=skip_list → returns job.skip_list', () => {
    assert.strictEqual(resolveCurrentFieldValue(sftpJob, 'skip_list', 'sftp'), 'skip1.txt');
  });

  it('TC-S503-04: field=ignore_list → returns job.ignore_list', () => {
    assert.strictEqual(resolveCurrentFieldValue(sftpJob, 'ignore_list', 'sftp'), 'ignore1.txt');
  });

  it('TC-S503-05: field=zip_content_filter → returns job.zip_filter (API key)', () => {
    assert.strictEqual(resolveCurrentFieldValue(sftpJob, 'zip_content_filter', 'sftp'), '*.csv');
  });

  it('TC-S503-06: SFTP field with no value → returns empty string', () => {
    assert.strictEqual(resolveCurrentFieldValue({ data: { job: {} } }, 'path', 'sftp'), '');
  });

  // ── Phase 12 correctness tests ──
  it('TC-P12-RFV-01: save_location reads save_path (API key)', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'save_location', 'email'), 'M:\\Data');
  });

  it('TC-P12-RFV-02: sender_filter reads sender (API key)', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'sender_filter', 'email'), 'reports@bank.com');
  });

  it('TC-P12-RFV-03: name reads job_name (API key)', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'name', 'email'), 'TestJob');
  });

  it('TC-P12-RFV-04: sender_filter falls back to filters.From when sender absent', () => {
    const jobWithFilters = {
      data: { job: { filters: { From: '@selenefinance.com' } } },
    };
    assert.strictEqual(resolveCurrentFieldValue(jobWithFilters, 'sender_filter', 'email'), '@selenefinance.com');
  });

  it('TC-P12-RFV-05: last_email field is resolved correctly', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'last_email', 'email'), '2/13/2026');
  });

  it('TC-P12-RFV-06: queue_one_file field returns stringified boolean', () => {
    assert.strictEqual(resolveCurrentFieldValue(emailJob, 'queue_one_file', 'email'), 'true');
  });
});
