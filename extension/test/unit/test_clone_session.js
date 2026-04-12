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

const parseCloneSourceServicerId = extractFunction('parseCloneSourceServicerId');
const parseCloneFieldReply = extractFunction('parseCloneFieldReply');
const isValidCloneJobName = extractFunction('isValidCloneJobName');

describe('Deterministic clone session helpers', function () {
  before(function () {
    if (!parseCloneSourceServicerId || !parseCloneFieldReply || !isValidCloneJobName) {
      this.skip();
    }
  });

  it('parses servicer id from keyed /clone prompts', () => {
    assert.strictEqual(parseCloneSourceServicerId('servicerID:150'), 150);
    assert.strictEqual(parseCloneSourceServicerId('servicer=275'), 275);
  });

  it('classifies clone field control replies', () => {
    assert.deepStrictEqual(parseCloneFieldReply('keep'), { action: 'keep' });
    assert.deepStrictEqual(parseCloneFieldReply('clear'), { action: 'clear' });
    assert.deepStrictEqual(parseCloneFieldReply('back'), { action: 'back' });
    assert.deepStrictEqual(parseCloneFieldReply('cancel'), { action: 'cancel' });
    assert.deepStrictEqual(parseCloneFieldReply('custom-value'), { action: 'value', value: 'custom-value' });
  });

  it('validates clone job names as XML-safe tags', () => {
    assert.strictEqual(isValidCloneJobName('CMBS_151'), true);
    assert.strictEqual(isValidCloneJobName('151_CMBS'), false);
    assert.strictEqual(isValidCloneJobName('CMBS Job'), false);
  });
});