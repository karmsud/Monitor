/**
 * Phase 12 audit script — checks all implementations against the TRD
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'chat', 'participant.js'), 'utf-8');

const checks = [
  // Epic 2: Backend field maps — verified via Python test above, just check renderEditDiff tags
  ['S-201/202: renderEditDiff tagMap uses Mailbox',
    /mailbox:\s+'Mailbox'/.test(src)],
  ['S-203: renderEditDiff tagMap uses Path',
    /path:\s+'Path'/.test(src)],

  // Epic 3: renderEditDiff nested sender_filter
  ['S-301: sender_filter included in isNested check',
    src.includes("field === 'sender_filter'")],
  ['S-301: Filters/From template in renderEditDiff',
    src.includes('<Filters><From>')],

  // Epic 3: resolveCurrentFieldValue correct API keys
  ["S-302: save_location reads save_path (API key)",
    src.includes("job['save_path']")],
  ["S-302: sender_filter reads job.sender (API key)",
    src.includes("job.sender || job.filters")],
  ["S-302: name reads job_name (API key)",
    src.includes("job['job_name']")],
  ["S-302: path reads sftp_path (API key)",
    src.includes("job['sftp_path']")],
  ["S-302: zip_content_filter reads zip_filter (API key)",
    src.includes("job['zip_filter']")],
  ["S-302: last_email added to fieldMap",
    src.includes("last_email:          () =>")],
  ["S-302: queue_one_file added to fieldMap",
    src.includes("queue_one_file:      () =>")],

  // Epic 1: DOMAIN_KNOWLEDGE XML schema
  ['S-101: Settings.xml Job Schema header present',
    src.includes('### Settings.xml Job Schema')],
  ['S-101: Key convention — tag IS the name explained',
    src.includes("job's name IS its XML element tag")],
  ['S-101: Email XML annotated block present',
    src.includes('Mailbox>rptent@usbank.com')],
  ['S-101: Email field-name table present',
    src.includes('sender_filter') && src.includes('Filters><From')],
  ['S-101: Computed fields warning (no match_mode in XML)',
    src.includes('match_mode') && src.includes('does not exist in XML')],
  ['S-101: API key translation table (save_path)',
    src.includes('save_path') && src.includes('SaveLocation')],
  ['S-102: SFTP XML annotated block present',
    src.includes('Path>M')],
  ['S-102: SFTP field-name table (path -> Path)',
    src.includes('sftp_path') && src.includes('sftp_path') ],
  ['S-102: SFTP API key translation table',
    src.includes('zip_filter') && src.includes('ZipContentFilter')],
  ['FR-1.1: Email API table has mailbox entry',
    src.includes('API \\`"mailbox"\\` = XML \\`<Mailbox>\\` = edit field')],
  ['FR-1.1: Email API table has templates dict',
    src.includes('API \\`"templates"\\` dict')],
  ['FR-1.1: SFTP API table has scrubber entry',
    /API.*"scrubber".*Templates.*Main.*edit field.*scrubber[\s\S]*?sftp_path/.test(src)],

  // Epic 4: Tool + playbook updates
  ['S-401: create_job overrides has EMAIL fields list',
    src.includes('EMAIL fields: mailbox, folder')],
  ['S-401: create_job overrides has SFTP fields list',
    src.includes('SFTP fields: path, dsn')],
  ['S-401: create_job warns against display-model names',
    src.includes('NEVER use display-model names')],
  ['S-402: CRUD_PLANNING_PLAYBOOK has Field Reference section',
    src.includes('Field Reference (for create_job overrides=')],
  ['S-402: Field Reference has sender_filter example',
    src.includes('Write \\`sender_filter\\`')],
  // (backticks in participant.js are escaped as \` inside its template literal; readFileSync sees raw backslash bytes)
  ['S-402: Field Reference lists email-only vs SFTP-only',
    src.includes('Email-only fields:') && src.includes('SFTP-only fields:')],
  ['S-403: EMAIL_TRIAGE no-match now shows creation suggestion',
    src.includes('Suggest a similar existing job')],  // capital S
  ['S-403: creation suggestion includes overrides guidance',
    src.includes('Outline the create_job call')],
  ['S-404: JOB_INVESTIGATION domain model has schema ref',
    src.includes('refer to DOMAIN_KNOWLEDGE') && src.includes('Settings.xml Job Schema.')],
  ['S-404: SERVICER_INVESTIGATION domain model has schema ref',
    src.includes('Settings.xml field names and XML structure')],
  ['S-404: GENERAL_REASONING domain model has schema ref',
    src.includes('Settings.xml field names and XML structure')],
  ['S-404: ANALYSIS has Domain Model section',
    src.includes('## Domain Model') && src.includes('Refer to DOMAIN_KNOWLEDGE \\u00a7 Settings.xml Job Schema')],  // literal \u00a7 in the .js source

  // Settings.xml description line updated
  ['S-101: Settings.xml description points to Schema section',
    src.includes('See "Settings.xml Job Schema" section below')],
];

let pass = 0, fail = 0;
for (const [name, ok] of checks) {
  const status = ok ? 'PASS' : 'FAIL';
  console.log(`${status}: ${name}`);
  if (ok) pass++; else fail++;
}
console.log(`\n${pass}/${pass + fail} checks passed`);
if (fail > 0) process.exit(1);
