const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const ts = require('typescript');
const { outputText } = ts.transpileModule(readFileSync(resolve(__dirname, '../src/components/console/DashboardSummaryPanel.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true },
});
const exportsObject = {};
runInNewContext(outputText, { exports: exportsObject, require(name) {
  // Only loader boundaries are inert; assertions render the actual view with React/Next Link.
  if (name === '@/lib/api') return { ApiError: class extends Error {} };
  if (name === '@/lib/events') return {};
  if (name === '@/lib/i18n') return {};
  return require(name);
}});
const { DashboardSummaryContent } = exportsObject;
function summary() { return {
  as_of:'2026-11-17T07:00:00Z', last_real_data_at:null, data_state:'partial',
  data_state_reasons:['1 service(s) without a fresh measurement'], window:{days:7},
  services:{counts:{up:0,degraded:0,down:0,unknown:1,stale:1},items:[{asset_id:'lab',name:'SYNTHETIC LAB',status:'unknown',observed_at:null,execution_id:null,stale:true,reason:'no approved health endpoint'}]},
  workers:{online:1,total:4,throttled:0},risk:{open_total:1,open_by_severity:{CRITICAL:0,HIGH:0,MEDIUM:1,LOW:0,INFO:0}},new_today:0,
  findings_per_day:[{day:'2026-11-17',new:4,reopened:2,fixed:3}],
}; }
function render(data,vi=true,cached=false) {return renderToStaticMarkup(React.createElement(DashboardSummaryContent,{summary:data,vi,cached}));}
test('missing health configuration and historical worker records are explicit without an online ratio or raw English reason',()=>{
  const html=render(summary());
  assert.match(html,/Chưa cấu hình điểm đo sức khỏe/);
  assert.match(html,/worker đang hoạt động/);
  assert.match(html,/3 bản ghi worker không còn gửi tín hiệu/);
  assert.doesNotMatch(html,/1\/4|no approved health endpoint|service\(s\) without|>unknown</);
  assert.match(html,/href="\/engine-runs\/?\?asset=lab"/);
});
test('each plotted lifecycle outcome opens its own observation filter, including reopened and verified fixes',()=>{
  const html=render(summary());
  for(const [outcome,count] of [['new',4],['reopened',2],['fixed',3]]) {
    assert.match(html,new RegExp(`href="/findings/?\\?outcome=${outcome}&amp;day=2026-11-17"`));
    assert.match(html,new RegExp(`aria-label="2026-11-17: ${count} `));
  }
});
test('an expired healthy measurement remains unknown instead of advertising current uptime',()=>{
  const data=summary();
  data.services.counts={up:1,degraded:0,down:0,unknown:0,stale:1};
  Object.assign(data.services.items[0],{status:'up',observed_at:'2026-11-16T00:00:00Z',reason:'last measurement older than 2 h'});
  const health=render(data).split('Tiến trình xử lý')[0];
  assert.match(health,/Hoạt động<\/dt><dd[^>]*>0<\/dd>/);
  assert.match(health,/Chưa xác định<\/dt><dd[^>]*>1<\/dd>/);
  assert.match(health,/Phép đo đã quá 2 giờ/);
});
test('empty activity, no workers, cached data and English labels retain honest states',()=>{
  const data=summary();data.workers={online:0,total:0,throttled:0};data.services.items=[];
  data.findings_per_day=[{day:'2026-11-17',new:0,reopened:0,fixed:0}];
  const html=render(data,false,true);
  assert.match(html,/Cached figures from the previous load/);
  assert.match(html,/No worker heartbeat/);
  assert.match(html,/No targets in your scope/);
  assert.match(html,/No events recorded in this window. This does not establish security/);
  assert.doesNotMatch(html,/outcome=fixed|outcome=new|outcome=reopened/);
});
