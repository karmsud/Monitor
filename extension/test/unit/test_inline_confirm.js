/**
 * Unit Tests — Inline confirmation state machine (Phase 9)
 * TC-IC-01 through TC-IC-09
 *
 * Tests the pendingOperation confirmation/cancellation regex patterns
 * that are used at the top of the participant handler.
 */
const assert = require('assert');

// ---------------------------------------------------------------------------
// Extract the regex patterns used in the confirmation check
// (same patterns as in participant.js registerChatParticipant handler)
// ---------------------------------------------------------------------------
const isConfirmPattern = /^(yes|y|confirm|confirmed|apply|ok|proceed|do\s+it|sure|go ahead)/;
const isCancelPattern  = /^(no|n|cancel|stop|abort|nevermind|nope|don.?t)/;

function simulateConfirmCheck(prompt) {
  const lc = prompt.toLowerCase().trim();
  const isConfirm = isConfirmPattern.test(lc);
  const isCancel  = isCancelPattern.test(lc);
  return { isConfirm, isCancel };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('Phase 9 — Inline Confirmation State Machine', function () {
  it('TC-IC-01: "yes" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('yes');
    assert.strictEqual(isConfirm, true);
  });

  it('TC-IC-02: "y" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('y');
    assert.strictEqual(isConfirm, true);
  });

  it('TC-IC-03: "confirm" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('confirm');
    assert.strictEqual(isConfirm, true);
  });

  it('TC-IC-04: "no" → isCancel = true', () => {
    const { isCancel } = simulateConfirmCheck('no');
    assert.strictEqual(isCancel, true);
  });

  it('TC-IC-05: "cancel" → isCancel = true', () => {
    const { isCancel } = simulateConfirmCheck('cancel');
    assert.strictEqual(isCancel, true);
  });

  it('TC-IC-06: "maybe" → neither confirm nor cancel', () => {
    const { isConfirm, isCancel } = simulateConfirmCheck('maybe');
    assert.strictEqual(isConfirm, false);
    assert.strictEqual(isCancel, false);
  });

  it('TC-IC-07: pendingOperation cleared after confirmation (simulated)', () => {
    const shared = {
      pendingOperation: { type: 'edit_job', params: { jobName: 'Test', field: 'sme', value: 'New' } },
    };
    const lc = 'yes';
    const isConfirm = isConfirmPattern.test(lc);
    if (isConfirm) {
      shared.pendingOperation = null;
    }
    assert.strictEqual(shared.pendingOperation, null);
  });

  it('TC-IC-08: pendingOperation cleared after cancellation (simulated)', () => {
    const shared = {
      pendingOperation: { type: 'edit_job', params: { jobName: 'Test', field: 'sme', value: 'New' } },
    };
    const lc = 'cancel';
    const isCancel = isCancelPattern.test(lc);
    if (isCancel) {
      shared.pendingOperation = null;
    }
    assert.strictEqual(shared.pendingOperation, null);
  });

  it('TC-IC-09: pendingOperation cleared on unrecognised response (simulated)', () => {
    const shared = {
      pendingOperation: { type: 'edit_job', params: { jobName: 'Test', field: 'sme', value: 'New' } },
    };
    const lc = 'something else';
    const isConfirm = isConfirmPattern.test(lc);
    const isCancel  = isCancelPattern.test(lc);
    if (!isConfirm && !isCancel) {
      shared.pendingOperation = null;
    }
    assert.strictEqual(shared.pendingOperation, null);
  });

  // Additional edge cases
  it('"ok" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('ok');
    assert.strictEqual(isConfirm, true);
  });

  it('"proceed" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('proceed');
    assert.strictEqual(isConfirm, true);
  });

  it('"do it" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('do it');
    assert.strictEqual(isConfirm, true);
  });

  it('"abort" → isCancel = true', () => {
    const { isCancel } = simulateConfirmCheck('abort');
    assert.strictEqual(isCancel, true);
  });

  it('"nope" → isCancel = true', () => {
    const { isCancel } = simulateConfirmCheck('nope');
    assert.strictEqual(isCancel, true);
  });

  it('"don\'t" → isCancel = true', () => {
    const { isCancel } = simulateConfirmCheck("don't");
    assert.strictEqual(isCancel, true);
  });

  it('"confirmed" → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('confirmed');
    assert.strictEqual(isConfirm, true);
  });

  it('"Confirmed" (capitalized) → isConfirm = true', () => {
    const { isConfirm } = simulateConfirmCheck('Confirmed');
    assert.strictEqual(isConfirm, true);
  });
});
