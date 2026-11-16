// Exercise the actual TypeScript helper using the already installed compiler.
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');
const source = readFileSync(resolve(__dirname, '../src/lib/finding-status.ts'), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
});
const exportsObject = {};
runInNewContext(outputText, { exports: exportsObject });
const { FINDING_STATUSES, TRIAGE_STATUSES, canonicalFindingStatus, findingStage } = exportsObject;

test('all ten API states remain visible in their lifecycle columns', () => {
  const expected = {
    NEW: 'TRIAGE', NEEDS_TRIAGE: 'TRIAGE', CONFIRMED: 'TRIAGE', ASSIGNED: 'TRIAGE',
    IN_PROGRESS: 'IN_PROGRESS', FIXED_PENDING_RETEST: 'FIXED_PENDING_RETEST',
    RESOLVED: 'RESOLVED', REOPENED: 'REOPENED', ACCEPTED_RISK: 'OTHER', FALSE_POSITIVE: 'OTHER',
  };
  assert.equal(FINDING_STATUSES.length, 10);
  assert.deepEqual(new Set(FINDING_STATUSES), new Set(Object.keys(expected)));
  for (const [status, column] of Object.entries(expected)) assert.equal(findingStage(status), column);
});

test('legacy FIXED means a claim awaiting retest; only RESOLVED is verified', () => {
  assert.equal(canonicalFindingStatus('fixed'), 'FIXED_PENDING_RETEST');
  assert.equal(findingStage('FIXED'), 'FIXED_PENDING_RETEST');
  assert.equal(findingStage('RESOLVED'), 'RESOLVED');
  assert.ok(!TRIAGE_STATUSES.includes('RESOLVED'));
  assert.ok(TRIAGE_STATUSES.includes('FIXED_PENDING_RETEST'));
});

test('compatibility aliases and unknown historical states stay visible', () => {
  for (const alias of ['OPEN', 'POTENTIAL']) assert.equal(findingStage(alias), 'TRIAGE');
  assert.equal(findingStage('IN_REMEDIATION'), 'IN_PROGRESS');
  assert.equal(canonicalFindingStatus('NOT_AFFECTED'), 'FALSE_POSITIVE');
  assert.equal(canonicalFindingStatus('MUTED'), 'ACCEPTED_RISK');
  assert.equal(findingStage('HISTORICAL_UNKNOWN'), 'OTHER');
  assert.equal(findingStage(null), 'TRIAGE');
});
