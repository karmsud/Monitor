/**
 * Extension Host Integration Tests — "Environment B"
 * ====================================================
 * 120 tests mirroring the CLI bench (Environment A) test cases.
 * Run via F5 → "Extension Tests (Environment B)" or `node extension/test/runTest.js`.
 *
 * These tests run INSIDE a VS Code Extension Development Host.
 * They exercise the full stack: extension activation → backendCall → CLI → JSON.
 */
const assert = require('assert');
const vscode = require('vscode');
const path   = require('path');

// ---------------------------------------------------------------------------
// Paths — must match Environment A
// ---------------------------------------------------------------------------
const PROJECT_ROOT   = path.resolve(__dirname, '..', '..', '..');
const EMAIL_SETTINGS = path.join(PROJECT_ROOT, 'Email Settings', 'Settings.ps1');
const SFTP_SETTINGS  = path.join(PROJECT_ROOT, 'SFTP Settings', 'Settings.ps1');
const EMAIL_LOGS     = path.join(PROJECT_ROOT, 'Email Logs');
const SFTP_LOGS      = path.join(PROJECT_ROOT, 'SFTP Logs');
const TEMP_DB        = path.join(PROJECT_ROOT, 'tests', 'e2e', '_test_logs.sqlite');

// ---------------------------------------------------------------------------
// Backend init helpers
// ---------------------------------------------------------------------------
let _backendCall = null;

function getBackendCall() {
  if (!_backendCall) {
    const tool = require('../../copilot/tool');
    _backendCall = tool.backendCall;
  }
  return _backendCall;
}

async function ensureBackendInit() {
  const ext = vscode.extensions.getExtension('your-publisher-id.frp-agent-extension');
  if (ext && !ext.isActive) await ext.activate();
  const { initBackendRunner } = require('../../lib/frp_backend');
  const outputChannel = vscode.window.createOutputChannel('FRP Test', { log: true });
  const fakeContext = { extensionPath: path.resolve(__dirname, '..', '..') };
  await initBackendRunner(vscode, fakeContext, outputChannel);
}

// ---------------------------------------------------------------------------
// Assertion helpers
// ---------------------------------------------------------------------------
function assertSuccess(r)            { assert.strictEqual(r.success, true, `expected success=true, got ${r.success}`); }
function assertFail(r)               { assert.strictEqual(r.success, false, 'expected success=false'); }
function assertHasData(r)            { assert.ok(r.data, 'data should be present'); }
function assertJobsArray(r)          { assert.ok(Array.isArray((r.data || {}).jobs), 'data.jobs should be array'); }
function assertJobCount(r, n)        { assert.strictEqual(r.data.jobs.length, n, `job count ${r.data.jobs.length} != expected ${n}`); }
function assertJobCountMin(r, n)     { assert.ok(r.data.jobs.length >= n, `job count ${r.data.jobs.length} < min ${n}`); }
function assertJobNamesContain(r, ...names) {
  const actual = r.data.jobs.map(j => j.name);
  names.forEach(n => assert.ok(actual.includes(n), `missing job name: ${n}`));
}
function assertHasValidation(r) {
  const d = r.data;
  assert.ok(d.errors !== undefined || d.warnings !== undefined || d.is_valid !== undefined || d.summary !== undefined, 'validation fields');
}
function assertXmlType(r, t)  { assert.strictEqual(r.data.xml_type, t, `xml_type ${r.data.xml_type} != ${t}`); }
function assertFieldExists(r, ...keys) {
  let cur = r;
  for (const k of keys) {
    assert.ok(cur && typeof cur === 'object' && k in cur, `field ${keys.join('→')} missing at '${k}'`);
    cur = cur[k];
  }
}

// ---------------------------------------------------------------------------
// Test Suite — 120 tests
// ---------------------------------------------------------------------------
suite('Environment B — Extension Host Tests (120)', function () {
  this.timeout(30000);

  suiteSetup(async function () {
    this.timeout(60000);
    const config = vscode.workspace.getConfiguration('frpAgent');
    await config.update('outlookSettingsPath', EMAIL_SETTINGS, vscode.ConfigurationTarget.Global);
    await config.update('sftpSettingsPath',    SFTP_SETTINGS,  vscode.ConfigurationTarget.Global);
    await config.update('emailLogFolder',      EMAIL_LOGS,     vscode.ConfigurationTarget.Global);
    await config.update('prod', false, vscode.ConfigurationTarget.Global);
    await ensureBackendInit();
    console.log('[Environment B] suiteSetup complete — 120 tests queued');
  });

  // =======================================================================
  //  TIER 1 — Core smoke tests (B-01 … B-05)
  // =======================================================================
  test('B-01: search tpmt (keyword)', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'tpmt' });
    assertSuccess(r); assertHasData(r); assertJobsArray(r);
    assertJobCount(r, 8);
    assertJobNamesContain(r, 'TOWD_Carrignton_6501', 'TPMT_SLS_6601');
  });

  test('B-02: search tpmt (natural language)', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'list all jobs that have save location tpmt' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 8);
  });

  test('B-03: search cmbs', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'cmbs' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 9);
    assertJobNamesContain(r, 'CMBS_GreyCo', 'CMBS_Wells');
  });

  test('B-04: validate email XML', async function () {
    const r = await getBackendCall()('validate_xml', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r); assertHasValidation(r);
  });

  test('B-05: status check', async function () {
    const r = await getBackendCall()('status', {});
    assertSuccess(r); assertHasData(r);
  });

  // =======================================================================
  //  TIER 2 — Expanded search (B-06 … B-25)
  // =======================================================================
  const t2Search = [
    { id: 'B-06', name: 'search fayservicing',          q: 'fayservicing',   min: 3, inc: ['Plaza_RTL_Fay_3003_2', 'CMLTI_Fay'] },
    { id: 'B-07', name: 'search towdpoint mailbox',     q: 'towdpoint',      min: 5 },
    { id: 'B-08', name: 'search servicer ID 6501',      q: '6501',           min: 1, inc: ['TOWD_Carrignton_6501'] },
    { id: 'B-09', name: 'search Chase jobs',            q: 'chase',          min: 3, inc: ['Chase_EMC_6901', 'CSFB_CF_Chase_3712'] },
    { id: 'B-10', name: 'search SCRT_Queuer template',  q: 'SCRT_Queuer',    min: 2, inc: ['FMSCRT_NewRez', 'FMSCRT_MrCooper'] },
    { id: 'B-11', name: 'search COOFS',                 q: 'COOFS',          exact: 4, inc: ['COOFS_LateMoney', 'COOFS_MidMonthly'] },
    { id: 'B-12', name: 'search SME sudhanwa',          q: 'sudhanwa',       min: 30 },
    { id: 'B-13', name: 'search SME ilya',              q: 'ilya',           min: 4 },
    { id: 'B-14', name: 'NL: show me fay servicing',    q: 'show me fay servicing jobs',      min: 3 },
    { id: 'B-15', name: 'NL: which jobs use newrez',    q: 'which jobs use newrez sender',     min: 3 },
    { id: 'B-16', name: 'search ABS_Deals',             q: 'ABS_Deals',      min: 1, inc: ['ABS_Deals'] },
    { id: 'B-17', name: 'search Neuberger',             q: 'neuberger',      min: 1 },
    { id: 'B-18', name: 'search save location EmailExtract', q: 'EmailExtract', min: 10 },
    { id: 'B-19', name: 'NL: freddie mac jobs',         q: 'find all freddie mac related jobs', min: 1 },
    { id: 'B-20', name: 'search rptent mailbox',        q: 'rptent',         min: 25 },
    { id: 'B-21', name: 'search nonexistent → 0',       q: 'zzz_no_such_job_999', exact: 0 },
    { id: 'B-24', name: 'search @wellsfargo sender',    q: 'wellsfargo',     min: 3 },
    { id: 'B-25', name: 'search CMLTI jobs',            q: 'CMLTI',          min: 3, inc: ['CMLTI_Fay', 'CMLTI_Fay_1770', 'CMLTI_Pennymac_6031'] },
  ];
  t2Search.forEach(({ id, name, q, min, exact, inc }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('search_jobs', { query: q });
      assertSuccess(r); assertJobsArray(r);
      if (exact !== undefined) assertJobCount(r, exact);
      if (min  !== undefined) assertJobCountMin(r, min);
      if (inc) assertJobNamesContain(r, ...inc);
    });
  });

  // B-22: search email type filter
  test('B-22: search email type filter tpmt', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'tpmt', xmlType: 'email' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 8); assertXmlType(r, 'email');
  });

  // B-23: search SFTP settings (all types)
  test('B-23: search SFTP Ocwen (all types)', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'Ocwen', xmlType: 'all' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
  });

  // --- Validate & template commands ---
  test('B-26: validate SFTP XML', async function () {
    const r = await getBackendCall()('validate_xml', { settingsPath: SFTP_SETTINGS, xmlType: 'sftp' });
    assertSuccess(r); assertHasData(r); assertHasValidation(r);
  });

  test('B-27: template_inventory email', async function () {
    const r = await getBackendCall()('template_inventory', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-28: list_backups email', async function () {
    const r = await getBackendCall()('list_backups', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r);
  });

  // --- Log commands ---
  test('B-29: sync_logs email', async function () {
    const r = await getBackendCall()('sync_logs', { logFolder: EMAIL_LOGS, dbPath: TEMP_DB });
    assertSuccess(r); assertHasData(r);
  });

  test('B-30: log_daily_summary', async function () {
    const r = await getBackendCall()('log_daily_summary', { dbPath: TEMP_DB });
    assertSuccess(r); assertHasData(r);
  });

  // =======================================================================
  //  TIER 3 — NL search stress (B-31 … B-50)
  // =======================================================================
  const t3NL = [
    { id: 'B-31', name: 'NL: jobs from bnymellon',              q: 'jobs from bnymellon',                    min: 1 },
    { id: 'B-32', name: 'NL: sba.gov emails',                   q: 'what jobs monitor sba.gov emails',       min: 3 },
    { id: 'B-33', name: 'NL: carrington job details',           q: 'show carrington job details',            min: 1 },
    { id: 'B-34', name: 'NL: mr cooper jobs',                   q: 'mr cooper jobs',                         min: 2 },
    { id: 'B-35', name: 'NL: BATCH folder jobs',                q: 'all jobs sending to BATCH folder',       min: 5 },
    { id: 'B-36', name: 'NL: rabs 3723 job',                    q: 'rabs 3723 job',                          min: 1 },
    { id: 'B-37', name: 'NL: bayview jobs',                     q: 'find bayview jobs',                      min: 1 },
    { id: 'B-38', name: 'NL: pennymac config',                  q: 'pennymac related configuration',         min: 1 },
    { id: 'B-39', name: 'NL: selene finance jobs',              q: 'list all jobs for selene finance',       min: 2 },
    { id: 'B-40', name: 'NL: servicer 132',                     q: 'jobs with servicer 132',                 min: 2 },
    { id: 'B-41', name: 'NL: spservicing sender',               q: 'spservicing sender jobs',                min: 3 },
    { id: 'B-42', name: 'NL: freddie RMBS mailbox',             q: 'show freddie RMBS mailbox jobs',         min: 2 },
    { id: 'B-43', name: 'NL: ghfta mailbox',                    q: 'ghfta mailbox jobs',                     min: 4 },
    { id: 'B-44', name: 'NL: Late Money folder',                q: 'jobs configured for Late Money folder',  min: 2 },
    { id: 'B-45', name: 'NL: Plaza RTL jobs',                   q: 'Plaza RTL jobs',                         min: 3 },
    { id: 'B-46', name: 'NL: trimont job',                      q: 'trimont job configuration',              min: 1 },
    { id: 'B-47', name: 'NL: harvest credit',                   q: 'harvest credit jobs',                    min: 1 },
    { id: 'B-48', name: 'NL: SLS TPMT jobs',                    q: 'SLS TPMT jobs',                          min: 2 },
    { id: 'B-49', name: 'NL: jpmchase sender',                  q: 'jpmchase sender configurations',         min: 3 },
    { id: 'B-50', name: 'NL: computershare',                    q: 'computershare email jobs',               min: 1 },
  ];
  t3NL.forEach(({ id, name, q, min }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('search_jobs', { query: q });
      assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, min);
    });
  });

  // =======================================================================
  //  TIER 4 — Full command coverage (B-51 … B-70)
  // =======================================================================

  // --- servicer_dossier ---
  test('B-51: servicer_dossier by job name', async function () {
    const r = await getBackendCall()('servicer_dossier', { jobName: 'TPMT_SLS_6601' });
    assertSuccess(r); assertHasData(r); assertFieldExists(r, 'data', 'jobs');
  });

  test('B-52: servicer_dossier by servicer ID', async function () {
    const r = await getBackendCall()('servicer_dossier', { servicerId: '6501' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-53: servicer_dossier CMBS job', async function () {
    const r = await getBackendCall()('servicer_dossier', { jobName: 'CMBS_Wells' });
    assertSuccess(r); assertHasData(r);
  });

  // --- xml_diff (expected failure — no backups) ---
  test('B-54: xml_diff email (expected fail — no backup)', async function () {
    const r = await getBackendCall()('xml_diff', { xmlType: 'email' });
    assertFail(r);
    assert.ok(JSON.stringify(r.errors || []).toLowerCase().includes('backup'), 'error should mention backup');
  });

  test('B-55: xml_diff SFTP (expected fail — no backup)', async function () {
    const r = await getBackendCall()('xml_diff', { settingsPath: SFTP_SETTINGS, xmlType: 'sftp' });
    assertFail(r);
    assert.ok(JSON.stringify(r.errors || []).toLowerCase().includes('backup'), 'error should mention backup');
  });

  // --- log commands with synced DB ---
  test('B-56: log_did_failures (empty DB)', async function () {
    const r = await getBackendCall()('log_did_failures', { dbPath: TEMP_DB, days: '7' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-57: log_job_health TPMT_SLS_6601', async function () {
    const r = await getBackendCall()('log_job_health', { jobName: 'TPMT_SLS_6601', dbPath: TEMP_DB, days: '7' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-58: log_trends default', async function () {
    const r = await getBackendCall()('log_trends', { dbPath: TEMP_DB, days: '7' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-59: log_trends specific job', async function () {
    const r = await getBackendCall()('log_trends', { dbPath: TEMP_DB, days: '7', job: 'CMBS_GreyCo' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-60: log_performance default', async function () {
    const r = await getBackendCall()('log_performance', { dbPath: TEMP_DB, days: '7' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-61: log_performance sort total_files', async function () {
    const r = await getBackendCall()('log_performance', { dbPath: TEMP_DB, sort: 'total_files', top: '5' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-62: log_deal_activity', async function () {
    const r = await getBackendCall()('log_deal_activity', { did: 'TPMT_SLS_6601', dbPath: TEMP_DB, days: '14' });
    assertSuccess(r); assertHasData(r);
  });

  // --- analyze commands ---
  test('B-63: analyze_consolidation email', async function () {
    const r = await getBackendCall()('analyze_consolidation', { type: 'email' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-64: analyze_health email', async function () {
    const r = await getBackendCall()('analyze_health', { type: 'email', dbPath: TEMP_DB });
    assertSuccess(r); assertHasData(r);
  });

  test('B-65: analyze_impact delete_job', async function () {
    const r = await getBackendCall()('analyze_impact', { changeType: 'delete_job', targetJob: 'ABS_Deals' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-66: analyze_impact rename_did', async function () {
    const r = await getBackendCall()('analyze_impact', { changeType: 'rename_did', targetDid: 'CMBS_Wells', newValue: 'CMBS_Wells_New' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-67: analyze_consolidation all types', async function () {
    const r = await getBackendCall()('analyze_consolidation', { type: 'all' });
    assertSuccess(r); assertHasData(r);
  });

  // --- template / validate / backups ---
  test('B-68: template_inventory SFTP', async function () {
    const r = await getBackendCall()('template_inventory', { settingsPath: SFTP_SETTINGS, xmlType: 'sftp' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-69: validate email XML detailed', async function () {
    const r = await getBackendCall()('validate_xml', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r); assertHasValidation(r); assertXmlType(r, 'email');
  });

  test('B-70: sync_logs SFTP', async function () {
    const r = await getBackendCall()('sync_logs', { logFolder: SFTP_LOGS, dbPath: TEMP_DB, logType: 'sftp' });
    assertSuccess(r); assertHasData(r);
  });

  // =======================================================================
  //  TIER 5 — Edge cases, stress, consistency (B-71 … B-120)
  // =======================================================================

  // --- Case sensitivity ---
  test('B-71: search UPPER case TPMT', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'TPMT' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 8);
  });

  test('B-72: search lower case tpmt', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'tpmt' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 8);
  });

  test('B-73: search mixed case TpMt', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'TpMt' });
    assertSuccess(r); assertJobsArray(r); assertJobCount(r, 8);
  });

  // --- Short / edge queries ---
  test('B-74: search single char z', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'z' });
    assertSuccess(r); assertJobsArray(r);
  });

  test('B-75: search numeric 6601', async function () {
    const r = await getBackendCall()('search_jobs', { query: '6601' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
    assertJobNamesContain(r, 'TPMT_SLS_6601');
  });

  test('B-76: search numeric 3712', async function () {
    const r = await getBackendCall()('search_jobs', { query: '3712' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
    assertJobNamesContain(r, 'CSFB_CF_Chase_3712');
  });

  test('B-77: search with @ symbol', async function () {
    const r = await getBackendCall()('search_jobs', { query: '@fayservicing.com' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 3);
  });

  test('B-78: search with backslash path', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'TPMT\\Data' });
    assertSuccess(r); assertJobsArray(r);
  });

  // --- Compound NL ---
  const t5NL = [
    { id: 'B-79',  name: 'NL: how many jobs use mr cooper',       q: 'how many jobs use mr cooper as servicer', min: 2 },
    { id: 'B-80',  name: 'NL: CMBS securities data',              q: 'jobs that process CMBS securities data',  min: 5 },
    { id: 'B-81',  name: 'NL: rptent active jobs',                q: 'all rptent mailbox configurations with active jobs', min: 10 },
    { id: 'B-82',  name: 'NL: WFServicing mailbox',               q: 'WFServicing mailbox email monitoring',     min: 1 },
    { id: 'B-83',  name: 'NL: quarterly report jobs',             q: 'quarterly report processing jobs',         min: 0 },
    { id: 'B-84',  name: 'NL: SLS servicer TPMT template',       q: 'SLS servicer with TPMT template',          min: 1 },
    { id: 'B-85',  name: 'NL: towdpoint plaza',                   q: 'towdpoint plaza jobs configuration',       min: 1 },
    { id: 'B-86',  name: 'NL: verbose CMBS prompt',               q: 'I need to find all the jobs that are related to CMBS commercial mortgage backed securities data processing in our email monitoring system', min: 5 },
    { id: 'B-87',  name: 'NL: verbose newrez prompt',             q: 'can you show me every job that involves newrez or new residential as the email sender for our file reception portal', min: 2 },
  ];
  t5NL.forEach(({ id, name, q, min }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('search_jobs', { query: q });
      assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, min);
    });
  });

  // --- Validate edge ---
  test('B-88: validate nonexistent file', async function () {
    const r = await getBackendCall()('validate_xml', { settingsPath: 'C:\\nonexistent\\Settings.ps1', xmlType: 'email' });
    assert.ok(r.success === false || JSON.stringify(r).toLowerCase().includes('error'), 'expected failure for nonexistent file');
  });

  // --- Status ---
  test('B-89: status repeated call', async function () {
    const r = await getBackendCall()('status', {});
    assertSuccess(r); assertHasData(r); assertFieldExists(r, 'data', 'version');
  });

  // --- More dossiers ---
  const t5Dossier = [
    { id: 'B-90', name: 'dossier servicer 150',     p: { servicerId: '150' } },
    { id: 'B-91', name: 'dossier COOFS_LateMoney',  p: { jobName: 'COOFS_LateMoney' } },
    { id: 'B-92', name: 'dossier FMSCRT_NewRez',    p: { jobName: 'FMSCRT_NewRez' } },
  ];
  t5Dossier.forEach(({ id, name, p }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('servicer_dossier', p);
      assertSuccess(r); assertHasData(r);
    });
  });

  // --- More analyze ---
  test('B-93: analyze_impact change_filter', async function () {
    const r = await getBackendCall()('analyze_impact', { changeType: 'change_filter', targetJob: 'TPMT_SLS_6601', newValue: '@newdomain.com' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-94: analyze_health SFTP', async function () {
    const r = await getBackendCall()('analyze_health', { settingsPath: SFTP_SETTINGS, type: 'sftp', dbPath: TEMP_DB });
    assertSuccess(r); assertHasData(r);
  });

  // --- More NL ---
  const t5NLExtra = [
    { id: 'B-95',  name: 'NL: USBankGSFA shared mailbox', q: 'USBankGSFABSMailboxShared',   min: 1 },
    { id: 'B-96',  name: 'NL: NBResiFunds monitoring',    q: 'NBResiFunds monitoring',       min: 1 },
    { id: 'B-97',  name: 'NL: EmailExtract subfolder',    q: 'saving EmailExtract subfolder', min: 5 },
    { id: 'B-98',  name: 'NL: QueueOneFile True',         q: 'QueueOneFile True',            min: 5 },
    { id: 'B-100', name: 'NL: Scrubber template',         q: 'Scrubber template',            min: 5 },
  ];
  t5NLExtra.forEach(({ id, name, q, min }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('search_jobs', { query: q });
      assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, min);
    });
  });

  // B-99: Ocwen SFTP-only search
  test('B-99: Ocwen SFTP search (all types)', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'Ocwen', xmlType: 'all' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
  });

  // --- Cross-command consistency ---
  test('B-101: validate then search same file', async function () {
    const r = await getBackendCall()('validate_xml', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r); assertHasValidation(r);
  });

  test('B-102: list_backups SFTP', async function () {
    const r = await getBackendCall()('list_backups', { settingsPath: SFTP_SETTINGS, xmlType: 'sftp' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-103: log_performance with settings', async function () {
    const r = await getBackendCall()('log_performance', { dbPath: TEMP_DB, sort: 'success_rate', top: '10' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-104: log_daily_summary with date', async function () {
    const r = await getBackendCall()('log_daily_summary', { dbPath: TEMP_DB, date: '2026-02-10' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-105: log_daily_summary future date', async function () {
    const r = await getBackendCall()('log_daily_summary', { dbPath: TEMP_DB, date: '2099-01-01' });
    assertSuccess(r); assertHasData(r);
  });

  // --- SFTP combined searches ---
  test('B-106: search all types Sweep', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'Sweep', xmlType: 'all' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
  });

  test('B-107: search sftp-only type Ocwen', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'Ocwen', xmlType: 'sftp' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 1);
  });

  // --- NL with punctuation and questions ---
  const t5Questions = [
    { id: 'B-108', name: 'NL: what is CMLTI?',                q: 'what is CMLTI',                    min: 3 },
    { id: 'B-109', name: 'NL: where do chase emails go?',     q: 'where do chase emails go',         min: 3 },
    { id: 'B-110', name: 'NL: who manages tpmt jobs?',        q: 'who manages tpmt',                 min: 5 },
    { id: 'B-111', name: 'NL: tell about COOFS monitoring',   q: 'tell about COOFS monitoring',      min: 3 },
    { id: 'B-112', name: 'NL: Plaza RTL Fay overlap',         q: 'Plaza RTL Fay servicing',          min: 3 },
  ];
  t5Questions.forEach(({ id, name, q, min }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('search_jobs', { query: q });
      assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, min);
    });
  });

  // --- Dossier for major servicer categories ---
  const t5DossierExtra = [
    { id: 'B-113', name: 'dossier Chase_EMC_6901',    p: { jobName: 'Chase_EMC_6901' } },
    { id: 'B-114', name: 'dossier ABS_Deals',         p: { jobName: 'ABS_Deals' } },
    { id: 'B-115', name: 'dossier FMSCRT_MrCooper',   p: { jobName: 'FMSCRT_MrCooper' } },
  ];
  t5DossierExtra.forEach(({ id, name, p }) => {
    test(`${id}: ${name}`, async function () {
      const r = await getBackendCall()('servicer_dossier', p);
      assertSuccess(r); assertHasData(r);
    });
  });

  // --- More log variants ---
  test('B-116: log_job_health CMBS_Wells', async function () {
    const r = await getBackendCall()('log_job_health', { jobName: 'CMBS_Wells', dbPath: TEMP_DB, days: '30' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-117: log_did_failures job filter', async function () {
    const r = await getBackendCall()('log_did_failures', { dbPath: TEMP_DB, days: '30', jobFilter: 'TPMT' });
    assertSuccess(r); assertHasData(r);
  });

  test('B-118: log_trends 30 days', async function () {
    const r = await getBackendCall()('log_trends', { dbPath: TEMP_DB, days: '30' });
    assertSuccess(r); assertHasData(r);
  });

  // --- Search with xml_type filter ---
  test('B-119: search chase xml_type email', async function () {
    const r = await getBackendCall()('search_jobs', { query: 'chase', xmlType: 'email' });
    assertSuccess(r); assertJobsArray(r); assertJobCountMin(r, 3); assertXmlType(r, 'email');
  });

  test('B-120: template_inventory with settings', async function () {
    const r = await getBackendCall()('template_inventory', { xmlType: 'email' });
    assertSuccess(r); assertHasData(r);
  });
});
