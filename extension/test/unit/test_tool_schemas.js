/**
 * Unit Tests — Tool Schema Validation (Phase 9)
 * TC-SCHEMA-01 through TC-SCHEMA-05, TC-S501-01 through TC-S501-05
 * TC-S601-01 through TC-S604-02
 *
 * These tests validate the FRP_TOOLS schema definitions by examining
 * participant.js source text directly with regex.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Read participant.js source
// ---------------------------------------------------------------------------
const participantPath = path.resolve(__dirname, '..', '..', 'chat', 'participant.js');
const source = fs.readFileSync(participantPath, 'utf-8');

/**
 * Extract the tool definition block (from `name: 'toolName'` through the
 * closing of the FRP_TOOLS array entry) from the source.
 */
function getToolBlock(toolName) {
  const start = source.indexOf(`name: '${toolName}'`);
  if (start === -1) return '';

  // Find the inputSchema block
  const schemaStart = source.indexOf('inputSchema:', start);
  if (schemaStart === -1 || schemaStart - start > 2000) return '';

  // Go forward until we find the matching close of the tool object
  // (next `},` followed by `{` or `]` at similar indent)
  let depth = 0;
  let blockEnd = schemaStart;
  for (let i = schemaStart; i < source.length && i < schemaStart + 5000; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}') {
      depth--;
      if (depth === 0) {
        blockEnd = i + 1;
        break;
      }
    }
  }

  return source.slice(start, blockEnd);
}

/**
 * Check if any tool in FRP_TOOLS has only a `prompt` property with type 'string'.
 */
function hasPromptOnlySchemas() {
  // Find all tool names in FRP_TOOLS
  const toolNames = [];
  const nameRe = /name:\s*'(\w+)'/g;
  let m;
  // Only scan within FRP_TOOLS array
  const frpStart = source.indexOf('const FRP_TOOLS = [');
  const frpSection = source.slice(frpStart, frpStart + 50000);
  while ((m = nameRe.exec(frpSection)) !== null) {
    toolNames.push(m[1]);
  }

  const promptOnly = [];
  for (const name of toolNames) {
    const block = getToolBlock(name);
    // Check if properties has ONLY prompt
    if (block.includes("prompt:") && block.includes("type: 'string'")) {
      // Make sure it's the only property by checking there's no other property
      const propsMatch = block.match(/properties:\s*\{([\s\S]*?)\}/);
      if (propsMatch) {
        const propsContent = propsMatch[1].trim();
        // Count property definitions (word followed by colon and {)
        const propNames = propsContent.match(/(\w+)\s*:\s*\{/g) || [];
        if (propNames.length === 1 && propNames[0].startsWith('prompt')) {
          promptOnly.push(name);
        }
      }
    }
  }
  return promptOnly;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Phase 9 — Tool Schema Validation', function () {
  // ── Epic 1: Core schemas ──
  describe('edit_job schema', () => {
    const block = getToolBlock('edit_job');

    it('TC-SCHEMA-01: has required=[jobName, field, value]', () => {
      assert.ok(block, 'edit_job tool block not found');
      assert.ok(block.includes("'jobName'"), 'jobName not in required');
      assert.ok(block.includes("'field'"), 'field not in required');
      assert.ok(block.includes("'value'"), 'value not in required');
    });

    it('TC-SCHEMA-02: field enum contains all 19 field names', () => {
      const expected = [
        'name', 'servicer_id', 'mailbox', 'folder', 'sme', 'save_location',
        'last_email', 'queue_one_file', 'day_adjust', 'import_did',
        'subject_filter', 'sender_filter', 'scrubber', 'template',
        'path', 'dsn', 'skip_list', 'ignore_list', 'zip_content_filter',
      ];
      for (const f of expected) {
        assert.ok(block.includes(`'${f}'`), `field enum missing: ${f}`);
      }
    });
  });

  describe('create_job schema', () => {
    const block = getToolBlock('create_job');

    it('TC-SCHEMA-03: has required=[newName, templateJob]', () => {
      assert.ok(block, 'create_job tool block not found');
      assert.ok(block.includes("'newName'"), 'newName not in required');
      assert.ok(block.includes("'templateJob'"), 'templateJob not in required');
    });
  });

  describe('rollback schema', () => {
    const block = getToolBlock('rollback');

    it('TC-SCHEMA-04: has required=[backupFile]', () => {
      assert.ok(block, 'rollback tool block not found');
      assert.ok(block.includes("'backupFile'"), 'backupFile not in required');
    });
  });

  describe('no prompt-only schemas', () => {
    it('TC-SCHEMA-05: no FRP_TOOLS entry has { prompt: string } as sole property', () => {
      const promptOnly = hasPromptOnlySchemas();
      assert.deepStrictEqual(promptOnly, [], `These tools still have prompt-only schemas: ${promptOnly.join(', ')}`);
    });
  });

  // ── Epic 5: SFTP schemas ──
  describe('SFTP parity', () => {
    const editBlock = getToolBlock('edit_job');
    const createBlock = getToolBlock('create_job');

    it('TC-S501-01: edit_job field enum contains 5 SFTP fields', () => {
      for (const f of ['path', 'dsn', 'skip_list', 'ignore_list', 'zip_content_filter']) {
        assert.ok(editBlock.includes(`'${f}'`), `SFTP field missing from enum: ${f}`);
      }
    });

    it('TC-S501-02: edit_job has xmlType enum=[email, sftp]', () => {
      assert.ok(editBlock.includes('xmlType'), 'xmlType property missing from edit_job');
      assert.ok(editBlock.includes("'email'"), 'xmlType missing email enum value');
      assert.ok(editBlock.includes("'sftp'"), 'xmlType missing sftp enum value');
    });

    it('TC-S501-03: create_job has xmlType property', () => {
      assert.ok(createBlock.includes('xmlType'), 'create_job missing xmlType property');
    });
  });

  // ── Epic 6: Command Intelligence schemas ──
  describe('triage_email schema', () => {
    const block = getToolBlock('triage_email');

    it('TC-S601-01: has no prompt property', () => {
      assert.ok(block, 'triage_email tool block not found');
      // Check that 'prompt' is not a property key in the schema
      assert.ok(!block.match(/prompt:\s*\{/), 'triage_email should not have prompt property');
    });

    it('TC-S601-02: mode enum = [new, verify, match]', () => {
      assert.ok(block.includes("'new'"), 'mode missing new');
      assert.ok(block.includes("'verify'"), 'mode missing verify');
      assert.ok(block.includes("'match'"), 'mode missing match');
    });

    it('TC-S601-03: required = [] (all optional)', () => {
      assert.ok(block.includes('required: []'), 'triage_email required should be empty array');
    });
  });

  describe('impact_analysis schema', () => {
    const block = getToolBlock('impact_analysis');

    it('TC-S602-01: has no prompt property', () => {
      assert.ok(block, 'impact_analysis tool block not found');
      assert.ok(!block.match(/prompt:\s*\{/), 'impact_analysis should not have prompt property');
    });

    it('TC-S602-02: changeType enum has 9 values', () => {
      const changeTypes = [
        'servicer_change', 'scrubber_change', 'template_change',
        'job_disable', 'job_create', 'job_delete',
        'sender_filter_change', 'subject_filter_change', 'sftp_path_change',
      ];
      for (const ct of changeTypes) {
        assert.ok(block.includes(`'${ct}'`), `changeType enum missing: ${ct}`);
      }
    });

    it('TC-S602-03: required = [changeType, targetJob]', () => {
      assert.ok(block.includes("'changeType'"), 'changeType not in required');
      assert.ok(block.includes("'targetJob'"), 'targetJob not in required');
    });
  });

  describe('coverage_gaps schema', () => {
    const block = getToolBlock('coverage_gaps');

    it('TC-S602-04: focus enum = [email, sftp, all]', () => {
      assert.ok(block, 'coverage_gaps tool block not found');
      assert.ok(block.includes("'email'"), 'focus missing email');
      assert.ok(block.includes("'sftp'"), 'focus missing sftp');
      assert.ok(block.includes("'all'"), 'focus missing all');
    });
  });

  describe('pipeline definitions', () => {
    it('TC-S603-01: analysis_pipeline exists in PIPELINE_DEFINITIONS', () => {
      assert.ok(source.includes("name: 'analysis_pipeline'"), 'analysis_pipeline not found');
    });

    it('TC-S603-02: crud_planning exists in PIPELINE_DEFINITIONS', () => {
      assert.ok(source.includes("name: 'crud_planning'"), 'crud_planning not found');
    });
  });
});
