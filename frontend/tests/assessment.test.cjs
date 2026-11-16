const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');
function load(file) {
  const { outputText } = ts.transpileModule(readFileSync(resolve(__dirname, '../src/lib', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const exports = {};
  runInNewContext(outputText, { exports, URLSearchParams });
  return exports;
}
const { assessmentEligible, eligibleAssetIds, assessmentLabel } = load('assessment.ts');
test('historical VERIFIED flags cannot admit a synthetic target or a response missing admission data', () => {
  const fixtures = [
    { id: 'seed', verification_status: 'VERIFIED', assessment_eligible: false, assessment_block_reason: 'SYNTHETIC_INVENTORY' },
    { id: 'legacy', verification_status: 'VERIFIED' },
    { id: 'approved', assessment_eligible: true },
  ];
  assert.equal(assessmentEligible(fixtures[0]), false);
  assert.equal(assessmentEligible(fixtures[1]), false);
  assert.deepEqual(Array.from(eligibleAssetIds(fixtures)), ['approved']);
  assert.match(assessmentLabel(fixtures[0], false), /Seeded \/ test/);
  assert.match(assessmentLabel({ assessment_block_reason: 'TARGET_EMERGENCY_STOP' }, false), /stop active/);
});
test('the actual inventory API helper includes records past row 200 and preserves eligible filtering on every page', async () => {
  const { api } = load('api.ts');
  const calls = [];
  api.listAssets = async (params) => {
    calls.push(params);
    return { total: 399, items: Array.from({ length: params.page === 1 ? 200 : 199 }, (_, i) => ({ id: `${(params.page - 1) * 200 + i}` })) };
  };
  const rows = await api.listAllAssets(true);
  assert.equal(rows.length, 399);
  assert.equal(rows[398].id, '398');
  assert.deepEqual(calls.map((c) => c.page), [1, 2]);
  assert.ok(calls.every((c) => c.assessment_eligible === true));
});
test('an inconsistent inventory page is reported rather than silently presenting a partial estate', async () => {
  const { api } = load('api.ts');
  api.listAssets = async () => ({ total: 399, items: [] });
  await assert.rejects(api.listAllAssets(), /Inventory changed/);
});
