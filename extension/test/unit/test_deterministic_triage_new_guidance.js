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
  const match = source.match(new RegExp(`const ${name} = \[[\\s\\S]*?\n\];|const ${name} = \{[\\s\\S]*?\n\};`, 'm'));
  return match ? match[0] : null;
}

const inlineCommandBlock = extractConst('INLINE_CHAT_ACTION_COMMAND');
if (inlineCommandBlock) {
  // eslint-disable-next-line no-eval
  eval(inlineCommandBlock.replace('const INLINE_CHAT_ACTION_COMMAND =', 'INLINE_CHAT_ACTION_COMMAND ='));
}

for (const fnName of [
  'escapeMarkdownText',
  'buildInlineActionUri',
  'buildInlinePromptLink',
  'linkOrText',
  'dedupeDeterministicValues',
  'extractDeterministicEmailAddresses',
  'normalizeDeterministicEmailAddress',
  'normalizeDeterministicMailboxValue',
  'buildDeterministicTriageMetadata',
  'pushUniqueDeterministicAction',
  'buildDeterministicCloneFollowUps',
  'renderDeterministicTriageEmailMetadata',
  'renderDeterministicCloneSuggestions',
  'renderDeterministicTriageNoExactMatchResult',
]) {
  const fnSource = extractFunction(fnName);
  if (fnSource) {
    // eslint-disable-next-line no-eval
    eval(fnSource);
  }
}

describe('Deterministic triage new-job guidance', function () {
  before(function () {
    if (typeof renderDeterministicTriageNoExactMatchResult !== 'function' || typeof buildDeterministicCloneFollowUps !== 'function') {
      this.skip();
    }
  });

  it('renders clone guidance when no exact match is found', () => {
    const markdown = renderDeterministicTriageNoExactMatchResult(
      {
        sender: 'earl.cruz@usbank.com',
        primaryMailbox: 'Pascale',
        subject: 'RE: HET 2024 A1/A2 and B Invoices',
        filenames: ['2890-624294 inv 8039219.pdf'],
        filePath: 'N:\\Projects\\test1.msg',
        date: '2026-01-22T05:13:20-08:00',
      },
      {
        recommendation: 'No existing jobs match. Suggested parser: pdf.',
        suggested_template: 'Bayview_Queuer_x',
      },
      [
        {
          job_name: 'BayviewAdditions_4000',
          servicer_id: '4000',
          mailbox: 'bayview@usbank.com',
          scrubber: 'Bayview_Queuer_x',
          reason: 'Uses the suggested scrubber/template.',
        },
      ],
    );

    assert.ok(markdown.includes('No exact mailbox-backed match was found'));
    assert.ok(markdown.includes('Suggested Clone Sources'));
    assert.ok(markdown.includes('BayviewAdditions_4000'));
    assert.ok(markdown.includes('Start with `/clone servicerID:<id>`'));
  });

  it('builds clone follow-ups from suggested source jobs', () => {
    const followUps = buildDeterministicCloneFollowUps([
      { job_name: 'BayviewAdditions_4000', servicer_id: '4000' },
    ]);

    assert.strictEqual(followUps[0].prompt, '/clone servicerID:4000');
    assert.ok(followUps[0].label.includes('BayviewAdditions_4000'));
  });
});