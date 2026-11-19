const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const ts = require('typescript');
const { outputText } = ts.transpileModule(readFileSync(resolve(__dirname, '../src/components/console/MonitoringReadinessPanel.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
});
const moduleExports = {};
runInNewContext(outputText, { exports: moduleExports, require(name) {
  if (name === '@/lib/api' || name === '@/lib/i18n' || name === '@/components/ui/button') return {};
  return require(name);
}});
const schedule={id:'test',name:'SYNTHETIC overnight',is_active:true,interval_minutes:120,next_run_at:'2026-11-17T12:00:00Z',last_run_at:'2026-11-17T10:00:00Z',running:false,latest_result:{status:'completed'},last_batch_id:'batch-test',backlog:0};
function render(value,vi=true){return renderToStaticMarkup(React.createElement(moduleExports.ScheduleStatus,{schedule:value,vi}));}
test('automation shows saved interval, ICT next run and persisted batch link',()=>{
  const html=render(schedule);
  assert.match(html,/Tự động quét: Bật/);
  assert.match(html,/120 phút/);
  assert.match(html,/19:00:00/);
  assert.match(html,/ICT/);
  assert.match(html,/\/engine-runs\/?\?run=batch-test/);
});
test('paused schedule never advertises the old next slot as a future execution',()=>{
  const html=render({...schedule,is_active:false},false);
  assert.match(html,/Automatic scanning: Paused/);
  assert.match(html,/Next run: Paused/);
  assert.doesNotMatch(html,/19:00:00/);
});
test('a completed scheduled run links to its actual immutable report',()=>{
  const html=render({...schedule,latest_result:{status:'completed',report_id:'saved-report-id'}});
  assert.match(html,/\/reports\/?\?report=saved-report-id/);
  assert.match(html,/Báo cáo tự động/);
  assert.doesNotMatch(render(schedule),/saved-report-id/);
});
