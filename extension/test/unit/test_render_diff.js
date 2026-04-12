/**
 * Unit Tests — renderEditDiff helper (Phase 9)
 * TC-RD-01 through TC-RD-04, TC-S502-01 through TC-S502-04
 *
 * Tests the renderEditDiff function directly by extracting it from
 * participant.js source and evaluating it in isolation.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Extract the renderEditDiff function from participant.js
// ---------------------------------------------------------------------------
const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

// Extract the function body
const funcMatch = source.match(/function renderEditDiff\([\s\S]*?^}/m);
let renderEditDiff;
if (funcMatch) {
  // eslint-disable-next-line no-eval
  eval(`renderEditDiff = ${funcMatch[0]}`);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Phase 9 — renderEditDiff', function () {
  before(function () {
    if (!renderEditDiff) this.skip();
  });

  it('TC-RD-01: scrubber field → renders <Templates><Main> blocks', () => {
    const result = renderEditDiff('TestJob', 'scrubber', 'OldScrubber', 'NewScrubber', 'email');
    assert.ok(result.includes('<Templates><Main>OldScrubber</Main></Templates>'), 'Before block missing');
    assert.ok(result.includes('<Templates><Main>NewScrubber</Main></Templates>'), 'After block missing');
  });

  it('TC-RD-02: flat field (servicer_id) → renders <ServicerID> blocks', () => {
    const result = renderEditDiff('TestJob', 'servicer_id', '100', '200', 'email');
    assert.ok(result.includes('<ServicerID>100</ServicerID>'), 'Before ServicerID missing');
    assert.ok(result.includes('<ServicerID>200</ServicerID>'), 'After ServicerID missing');
  });

  it('TC-RD-03: empty currentValue → shows "(not set)"', () => {
    const result = renderEditDiff('TestJob', 'mailbox', '', 'new@test.com', 'email');
    assert.ok(result.includes('(not set)'), 'Missing "(not set)" for empty current value');
  });

  it('TC-RD-04: job name appears in diff title', () => {
    const result = renderEditDiff('CMBS_GreyCo', 'folder', 'Old', 'New', 'email');
    assert.ok(result.includes('CMBS_GreyCo'), 'Job name missing from diff');
  });

  // ── Epic 5 SFTP tests ──
  it('TC-S502-01: SFTP field path → renders <Path> tags (not RemotePath)', () => {
    const result = renderEditDiff('SFTP_Test', 'path', '/old/path', '/new/path', 'sftp');
    assert.ok(result.includes('<Path>/old/path</Path>'), 'Before Path missing');
    assert.ok(result.includes('<Path>/new/path</Path>'), 'After Path missing');
    assert.ok(!result.includes('RemotePath'), 'RemotePath must not appear');
  });

  it('TC-S502-02: SFTP field dsn → renders <DSN> tags', () => {
    const result = renderEditDiff('SFTP_Test', 'dsn', 'OldDSN', 'NewDSN', 'sftp');
    assert.ok(result.includes('<DSN>OldDSN</DSN>'));
    assert.ok(result.includes('<DSN>NewDSN</DSN>'));
  });

  it('TC-S502-03: SFTP field skip_list → renders <SkipList> tags', () => {
    const result = renderEditDiff('SFTP_Test', 'skip_list', '', 'file1.csv', 'sftp');
    assert.ok(result.includes('<SkipList>'));
  });

  it('TC-S502-04: diff title includes (sftp) when xmlType=sftp', () => {
    const result = renderEditDiff('SFTP_Test', 'path', '/old', '/new', 'sftp');
    assert.ok(result.includes('(sftp)'), 'Missing (sftp) in diff title');
  });

  // ── Phase 12 correctness tests ──
  it('TC-P12-RD-01: mailbox field renders <Mailbox> tag, not MailboxAddress', () => {
    const result = renderEditDiff('TestJob', 'mailbox', 'old@usbank.com', 'new@usbank.com', 'email');
    assert.ok(result.includes('<Mailbox>old@usbank.com</Mailbox>'), 'Before Mailbox missing');
    assert.ok(result.includes('<Mailbox>new@usbank.com</Mailbox>'), 'After Mailbox missing');
    assert.ok(!result.includes('MailboxAddress'), 'MailboxAddress must not appear');
  });

  it('TC-P12-RD-02: sender_filter field renders nested <Filters><From> structure', () => {
    const result = renderEditDiff('TestJob', 'sender_filter', '@old.com', '@new.com', 'email');
    assert.ok(result.includes('<Filters><From>@old.com</From></Filters>'), 'Before Filters/From missing');
    assert.ok(result.includes('<Filters><From>@new.com</From></Filters>'), 'After Filters/From missing');
    assert.ok(!result.includes('SenderFilter'), 'SenderFilter must not appear');
  });

  it('TC-P12-RD-03: save_location field renders <SaveLocation> tag, not bare field name', () => {
    const result = renderEditDiff('TestJob', 'save_location', 'M:\\Old\\', 'M:\\New\\', 'email');
    assert.ok(result.includes('<SaveLocation>'), 'SaveLocation tag missing');
    assert.ok(!result.includes('<save_location>'), 'Bare field name must not appear as tag');
  });

  it('TC-P12-RD-04: scrubber field still renders <Templates><Main> (regression)', () => {
    const result = renderEditDiff('TestJob', 'scrubber', 'OldScrubber', 'NewScrubber', 'email');
    assert.ok(result.includes('<Templates><Main>OldScrubber</Main></Templates>'), 'Templates/Main before missing');
    assert.ok(result.includes('<Templates><Main>NewScrubber</Main></Templates>'), 'Templates/Main after missing');
  });
});
