const assert = require('assert');
const fs = require('fs');
const path = require('path');

const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

function extractFunction(name) {
  const match = source.match(new RegExp(`function ${name}\\([\\s\\S]*?^}`, 'm'));
  return match ? match[0] : null;
}

for (const fnName of [
  'dedupeDeterministicValues',
  'extractDeterministicEmailAddresses',
  'normalizeDeterministicEmailAddress',
  'normalizeDeterministicMailboxValue',
  'normalizeDeterministicSenderDomain',
  'isDeterministicInlineFilename',
  'selectDeterministicPrimaryFilename',
  'buildDeterministicTriageSubjectSearchValue',
  'getDeterministicTriageEvidenceMailboxes',
  'buildDeterministicTriageDataSourceValues',
  'normalizeDeterministicImportDidValue',
  'buildDeterministicTriageMetadata',
  'selectDeterministicTriageDeals',
  'dedupeDeterministicTriageDidMatches',
  'computeDeterministicTriageDidMatches',
  'stagingRowMatchesEmail',
  'scoreDeterministicTriageMatch',
  'scoreDeterministicResolvedJobVariant',
  'rankDeterministicTriageMatches',
  'matchesDeterministicTriageLogEmailEvent',
  'pickDeterministicResolvedJobVariant',
  'mergeDeterministicResolvedJob',
  'buildDeterministicTriageLogSearchPlans',
  'getDeterministicTriageMailboxCandidates',
]) {
  const fnSource = extractFunction(fnName);
  if (fnSource) {
    // eslint-disable-next-line no-eval
    eval(fnSource);
  }
}

describe('Deterministic triage resolution', function () {
  before(function () {
    if (typeof buildDeterministicTriageMetadata !== 'function' || typeof rankDeterministicTriageMatches !== 'function') {
      this.skip();
    }
  });

  it('normalizes mailbox recipients from display-name format', () => {
    const metadata = buildDeterministicTriageMetadata({}, {
      email_info: {
        sender: 'Phan_Alyssa@usbank.com',
        to: ['US Bank GSF ABS Mailbox Shared <USBankGSFABSMailboxShared@usbank.com>'],
        subject: 'Resend Fortiva 2025-Two',
      },
    });

    assert.strictEqual(metadata.primaryMailbox, 'USBankGSFABSMailboxShared@usbank.com');
    assert.deepStrictEqual(metadata.mailboxes, ['USBankGSFABSMailboxShared@usbank.com']);
  });

  it('includes cc recipients in mailbox candidates', () => {
    const metadata = buildDeterministicTriageMetadata({}, {
      email_info: {
        sender: 'kiersten.martin@trimont.com',
        to: ['ana.carsey@usbank.com'],
        cc: ['rptent@usbank.com'],
        subject: 'Periodic Remit',
      },
    });

    assert.deepStrictEqual(metadata.mailboxes, ['ana.carsey@usbank.com', 'rptent@usbank.com']);
  });

  it('skips inline image attachments when choosing the primary filename', () => {
    const metadata = buildDeterministicTriageMetadata({}, {
      email_info: {
        sender: 'kiersten.martin@trimont.com',
        to: ['rptent@usbank.com'],
        subject: 'Periodic Remit',
        attachment_names: ['image001.png', 'FREMF18KS10_202603_IRP.zip'],
      },
    });

    assert.strictEqual(metadata.primaryFilename, 'FREMF18KS10_202603_IRP.zip');
  });

  it('ranks exact mailbox matches above partial sender matches', () => {
    const metadata = {
      mailboxes: ['USBankGSFABSMailboxShared@usbank.com'],
    };
    const ranked = rankDeterministicTriageMatches([
      {
        job_name: 'BayviewAdditions_4000',
        match_type: 'sender',
        match_confidence: 'partial',
        matched_filter: '@usbank.com',
        email_field_matched: 'Phan_Alyssa@usbank.com',
      },
      {
        job_name: 'ABS_Deals',
        match_type: 'mailbox',
        match_confidence: 'exact',
        matched_filter: 'USBankGSFABSMailboxShared@usbank.com',
        email_field_matched: 'USBankGSFABSMailboxShared@usbank.com',
      },
    ], metadata);

    assert.deepStrictEqual(ranked.map((match) => match.job_name), ['ABS_Deals', 'BayviewAdditions_4000']);
  });

  it('ranks exact cc mailbox matches above partial sender matches', () => {
    const metadata = {
      mailboxes: ['ana.carsey@usbank.com', 'rptent@usbank.com'],
    };
    const ranked = rankDeterministicTriageMatches([
      {
        job_name: 'CMBS_Wells_CMS_Trimont',
        match_type: 'sender',
        match_confidence: 'partial',
        matched_filter: '@trimont.com',
        email_field_matched: 'kiersten.martin@trimont.com',
      },
      {
        job_name: 'CMBS_Wells_Trimont',
        match_type: 'mailbox',
        match_confidence: 'exact',
        matched_filter: 'rptent@usbank.com',
        email_field_matched: 'rptent@usbank.com',
      },
    ], metadata);

    assert.deepStrictEqual(ranked.map((match) => match.job_name), ['CMBS_Wells_Trimont', 'CMBS_Wells_CMS_Trimont']);
  });

  it('prefers mailbox-exact matches whose sender domain matches the email sender', () => {
    const metadata = {
      mailboxes: ['rptent@usbank.com'],
      sender: 'kiersten.martin@trimont.com',
      senderDomain: 'trimont.com',
    };
    const ranked = rankDeterministicTriageMatches([
      {
        job_name: 'CMBS_Wells_CMS_Trimont',
        match_type: 'mailbox',
        match_confidence: 'exact',
        matched_filter: 'rptent@usbank.com',
        email_field_matched: 'rptent@usbank.com',
        sender: '@cms.trimont.com',
      },
      {
        job_name: 'CMBS_Wells_Trimont',
        match_type: 'mailbox',
        match_confidence: 'exact',
        matched_filter: 'rptent@usbank.com',
        email_field_matched: 'rptent@usbank.com',
        sender: '@trimont.com',
      },
    ], metadata);

    assert.deepStrictEqual(ranked.map((match) => match.job_name), ['CMBS_Wells_Trimont', 'CMBS_Wells_CMS_Trimont']);
  });

  it('normalizes ImportDID matching across punctuation in the subject line', () => {
    const matches = computeDeterministicTriageDidMatches([
      { DID: '5065', ImportDID: 'FREMF18KS10', CompanyID: 224 },
    ], {
      subject: '[EXTERNAL] FREMF 18-KS10 Periodic Remit and Supplemental Files',
      filenames: [],
    }, 'subject', []);

    assert.strictEqual(matches.length, 1);
    assert.strictEqual(matches[0].did, '5065');
    assert.strictEqual(matches[0].matched_in, 'subject');
  });

  it('prefers the fullest servicer deal set for DID matching', () => {
    const deals = selectDeterministicTriageDeals(
      [{ DID: '1', ImportDID: 'A' }],
      { deals: Array.from({ length: 50 }, (_, index) => ({ DID: String(index), ImportDID: `D${index}` })) },
      { deals: Array.from({ length: 204 }, (_, index) => ({ DID: String(index), ImportDID: `FULL${index}` })) },
    );

    assert.strictEqual(deals.length, 204);
  });

  it('matches staging datasource rows using mailbox plus cleaned subject', () => {
    const metadata = {
      mailboxes: ['rptent@usbank.com'],
      subject: '[EXTERNAL] FREMF18KS10 Periodic Remit and Supplemental Files',
      filenames: ['image001.png'],
    };

    assert.strictEqual(stagingRowMatchesEmail({
      DataSource: 'rptent@usbank.com: FREMF18KS10 Periodic Remit and Supplemental Files',
      FilePath: 'M:\\PFA\\ignored\\image001.png',
    }, metadata), true);
  });

  it('prefers the duplicate job variant whose sender domain matches the email sender', () => {
    const metadata = {
      mailboxes: ['rptent@usbank.com'],
      senderDomain: 'trimont.com',
    };
    const preferredMatch = {
      job_name: 'CMBS_Wells_Trimont',
      servicer_id: '224',
      matched_filter: 'rptent@usbank.com',
    };

    const variant = pickDeterministicResolvedJobVariant([
      {
        job_name: 'CMBS_Wells_Trimont',
        servicer_id: '224',
        mailbox: 'rptent@usbank.com',
        sender: '@cms.trimont.com',
      },
      {
        job_name: 'CMBS_Wells_Trimont',
        servicer_id: '224',
        mailbox: 'rptent@usbank.com',
        sender: '@trimont.com',
      },
    ], preferredMatch, metadata);

    assert.strictEqual(variant.sender, '@trimont.com');
  });

  it('flags duplicate-name mailbox matches when job detail sender conflicts with the email sender domain', () => {
    const merged = mergeDeterministicResolvedJob({
      job_name: 'CMBS_Wells_Trimont',
      sender: '@cms.trimont.com',
      mailbox: 'rptent@usbank.com',
    }, {
      job_name: 'CMBS_Wells_Trimont',
      sender: '@cms.trimont.com',
      mailbox: 'rptent@usbank.com',
    }, {
      job_name: 'CMBS_Wells_Trimont',
      match_type: 'mailbox',
      match_confidence: 'exact',
      matched_filter: 'rptent@usbank.com',
      email_field_matched: 'rptent@usbank.com',
      servicer_id: '224',
    }, [
      { job_name: 'CMBS_Wells_Trimont' },
      { job_name: 'CMBS_Wells_Trimont' },
    ], {
      senderDomain: 'trimont.com',
    });

    assert.strictEqual(merged.resolved_sender_conflict, true);
    assert.strictEqual(merged.resolved_duplicate_name_count, 2);
  });

  it('uses exact job lookup as the first deterministic log search plan', () => {
    const plans = buildDeterministicTriageLogSearchPlans({
      sender: 'kiersten.martin@trimont.com',
      subject: '[EXTERNAL] FREMF18KS10 Periodic Remit and Supplemental Files Mar 2026',
      mailboxes: ['rptent@usbank.com'],
      primaryFilename: 'FREMF18KS10_202603_IRP.zip',
    }, {
      job_name: 'CMBS_Wells_Trimont',
      mailbox: 'rptent@usbank.com',
    });

    assert.deepStrictEqual(plans[0].filters, [
      { field: 'job', value: 'CMBS_Wells_Trimont' },
    ]);
  });

  it('keeps filename fallback as the second deterministic backend log plan', () => {
    const plans = buildDeterministicTriageLogSearchPlans({
      sender: 'kiersten.martin@trimont.com',
      subject: '[EXTERNAL] FREMF18KS10 Periodic Remit and Supplemental Files Mar 2026',
      mailboxes: ['rptent@usbank.com'],
      primaryFilename: 'FREMF18KS10_202603_IRP.zip',
    }, {
      job_name: 'CMBS_Wells_Trimont',
      mailbox: 'rptent@usbank.com',
    });

    assert.deepStrictEqual(plans[1].filters, [
      { field: 'job', value: 'CMBS_Wells_Trimont' },
      { field: 'filename', value: 'FREMF18KS10_202603_IRP.zip' },
    ]);
  });

  it('matches grouped log email events by subject after an exact job lookup', () => {
    const matched = matchesDeterministicTriageLogEmailEvent({
      mailbox: 'rptent@usbank.com',
      sender: 'kiersten.martin@trimont.com',
      subject: 'FREMF18KS10 Periodic Remit and Supplemental Files Mar 2026',
      files: ['unrelated.txt'],
    }, {
      sender: 'kiersten.martin@trimont.com',
      subject: '[EXTERNAL] FREMF18KS10 Periodic Remit and Supplemental Files Mar 2026',
      mailboxes: ['rptent@usbank.com'],
      primaryFilename: 'FREMF18KS10_202603_IRP.zip',
    }, {
      job_name: 'CMBS_Wells_Trimont',
      mailbox: 'rptent@usbank.com',
    });

    assert.strictEqual(matched, true);
  });
});