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
const { recordedEvidence, redactEvidence } = load('finding-evidence.ts');
test('missing evidence never fabricates HTTP responses, headers, cURL or matched proof', () => {
  const result = recordedEvidence({});
  assert.equal(result.request, 'No recorded evidence for this field.');
  assert.equal(result.response, 'No recorded evidence for this field.');
  assert.equal(result.curl, 'No recorded evidence for this field.');
  assert.equal(result.proof, 'No recorded evidence for this field.');
  assert.equal(Object.keys(result.headers).length, 0);
  assert.doesNotMatch(JSON.stringify(result), /200 OK|nginx|curl -k|DETECTED_INDICATOR/);
});
test('real component evidence remains visible without pretending it is an HTTP probe', () => {
  const result = recordedEvidence({ component: { name: 'lab', version: '1.0' }, advisory_id: 'LAB-1' });
  assert.match(result.proof, /LAB-1/);
  assert.match(result.proof, /1.0/);
  assert.equal(Object.keys(result.headers).length, 0);
  assert.match(result.response, /No recorded evidence/);
});
test('stored HTTP evidence is shown with credential and cookie redaction', () => {
  const result = recordedEvidence({
    request: 'GET /?token=private-one HTTP/1.1\r\nAuthorization: Basic private-two\r\nCookie: session=private-three',
    response: 'HTTP/1.1 403 Forbidden\r\nSet-Cookie: id=private-four',
    headers: { Authorization: 'private-five', 'Content-Type': 'application/json' },
    proof: { nested: { password: 'private-six' } },
    replay_curl: 'curl https://lab.invalid/?api_key=private-seven',
  });
  const text = JSON.stringify(result);
  assert.doesNotMatch(text, /private-/);
  assert.match(text, /403 Forbidden/);
  assert.match(text, /application\/json/);
  assert.equal(redactEvidence('Bearer secret-lab-value'), 'Bearer [REDACTED]');
});
