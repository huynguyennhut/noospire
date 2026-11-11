/**
 * Empirical React SSR Stress-Testing Harness for Interactive SVG Charts
 * Transpiles TypeScript/TSX chart components with TypeScript API and renders via ReactDOMServer
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('../frontend/node_modules/typescript');
const React = require('../frontend/node_modules/react');
const ReactDOMServer = require('../frontend/node_modules/react-dom/server');

console.log('='.repeat(70));
console.log('NOOSFORGE REACT SSR EMPIRICAL RENDERING HARNESS');
console.log('='.repeat(70));

let passCount = 0;
let failCount = 0;
const failures = [];

function assert(condition, message, detail = {}) {
  if (condition) {
    passCount++;
    console.log(`  [PASS] ${message}`);
  } else {
    failCount++;
    failures.push({ message, detail });
    console.error(`  [FAIL] ${message}`, detail);
  }
}

// Module loader that transpiles TS/TSX on the fly
const moduleCache = new Map();

function loadModule(relativePath) {
  const fullPath = path.resolve('frontend/src/components/charts', relativePath);
  if (moduleCache.has(fullPath)) return moduleCache.get(fullPath);

  let source = fs.readFileSync(fullPath, 'utf-8');
  // Strip 'use client';
  source = source.replace(/['"]use client['"];?/g, '');

  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.React,
      esModuleInterop: true,
    },
  });

  const customModule = { exports: {} };
  const customRequire = (specifier) => {
    if (specifier === 'react') return React;
    if (specifier === 'react-dom/server') return ReactDOMServer;
    if (specifier.startsWith('./')) {
      const target = specifier.endsWith('.ts') || specifier.endsWith('.tsx')
        ? specifier
        : fs.existsSync(path.resolve('frontend/src/components/charts', specifier + '.tsx'))
        ? specifier + '.tsx'
        : specifier + '.ts';
      return loadModule(target);
    }
    return require(specifier);
  };

  const fn = new Function('require', 'module', 'exports', transpiled.outputText);
  fn(customRequire, customModule, customModule.exports);

  moduleCache.set(fullPath, customModule.exports);
  return customModule.exports;
}

// Load chart components
const { ChartTooltip } = loadModule('ChartTooltip.tsx');
const { InteractiveAreaChart } = loadModule('InteractiveAreaChart.tsx');
const { InteractiveBarChart } = loadModule('InteractiveBarChart.tsx');
const { InteractiveDonutChart } = loadModule('InteractiveDonutChart.tsx');
const { InteractiveGaugeChart } = loadModule('InteractiveGaugeChart.tsx');

console.log('\n--- 1. Testing InteractiveAreaChart SSR Rendering ---');

// Area Chart: Empty dataset
try {
  const htmlEmpty = ReactDOMServer.renderToString(
    React.createElement(InteractiveAreaChart, {
      data: [],
      xKey: 'date',
      series: [{ id: 's1', name: 'Series 1', color: '#06B6D4', dataKey: 'val' }],
    })
  );
  assert(!htmlEmpty.includes('NaN'), 'AreaChart (empty data): Renders without NaN in SVG');
  assert(!htmlEmpty.includes('undefined'), 'AreaChart (empty data): Renders without undefined in SVG');
  assert(htmlEmpty.includes('<svg'), 'AreaChart (empty data): Contains root <svg>');
} catch (err) {
  assert(false, 'AreaChart (empty data): Threw exception', { error: err.message });
}

// Area Chart: Single data point
try {
  const htmlSingle = ReactDOMServer.renderToString(
    React.createElement(InteractiveAreaChart, {
      data: [{ date: 'Day 1', val: 50 }],
      xKey: 'date',
      series: [{ id: 's1', name: 'Series 1', color: '#06B6D4', dataKey: 'val' }],
    })
  );
  assert(!htmlSingle.includes('NaN'), 'AreaChart (single point): Renders without NaN in SVG');
  assert(htmlSingle.includes('<path'), 'AreaChart (single point): Renders fallback single-point path');
  assert(htmlSingle.includes('Day 1'), 'AreaChart (single point): Renders x-axis label');
} catch (err) {
  assert(false, 'AreaChart (single point): Threw exception', { error: err.message });
}

// Area Chart: All-zero dataset
try {
  const htmlZero = ReactDOMServer.renderToString(
    React.createElement(InteractiveAreaChart, {
      data: [
        { date: 'Day 1', val: 0 },
        { date: 'Day 2', val: 0 },
        { date: 'Day 3', val: 0 },
      ],
      xKey: 'date',
      series: [{ id: 's1', name: 'Series 1', color: '#06B6D4', dataKey: 'val' }],
    })
  );
  assert(!htmlZero.includes('NaN'), 'AreaChart (all zeros): Renders without NaN in SVG');
  assert(htmlZero.includes('grid-lines'), 'AreaChart (all zeros): Renders grid lines');
} catch (err) {
  assert(false, 'AreaChart (all zeros): Threw exception', { error: err.message });
}

// Area Chart: Extreme values
try {
  const htmlExtreme = ReactDOMServer.renderToString(
    React.createElement(InteractiveAreaChart, {
      data: [
        { date: 'Day 1', val: 0 },
        { date: 'Day 2', val: 1000000 },
        { date: 'Day 3', val: 5 },
      ],
      xKey: 'date',
      series: [{ id: 's1', name: 'Series 1', color: '#06B6D4', dataKey: 'val' }],
    })
  );
  assert(!htmlExtreme.includes('NaN'), 'AreaChart (extreme 0 vs 1M): Renders without NaN in SVG');
} catch (err) {
  assert(false, 'AreaChart (extreme 0 vs 1M): Threw exception', { error: err.message });
}

console.log('\n--- 2. Testing InteractiveBarChart SSR Rendering ---');

// Bar Chart: Empty dataset
try {
  const htmlBarEmpty = ReactDOMServer.renderToString(
    React.createElement(InteractiveBarChart, {
      data: [],
      categoryKey: 'cat',
      series: [{ id: 's1', name: 'Series 1', color: '#10B981', dataKey: 'val' }],
    })
  );
  assert(!htmlBarEmpty.includes('NaN'), 'BarChart (empty data): Renders without NaN in SVG');
  assert(htmlBarEmpty.includes('<svg'), 'BarChart (empty data): Contains root <svg>');
} catch (err) {
  assert(false, 'BarChart (empty data): Threw exception', { error: err.message });
}

// Bar Chart: Single data point
try {
  const htmlBarSingle = ReactDOMServer.renderToString(
    React.createElement(InteractiveBarChart, {
      data: [{ cat: 'App 1', val: 42 }],
      categoryKey: 'cat',
      series: [{ id: 's1', name: 'Series 1', color: '#10B981', dataKey: 'val' }],
    })
  );
  assert(!htmlBarSingle.includes('NaN'), 'BarChart (single point): Renders without NaN in SVG');
  assert(htmlBarSingle.includes('App 1'), 'BarChart (single point): Contains category label');
} catch (err) {
  assert(false, 'BarChart (single point): Threw exception', { error: err.message });
}

// Bar Chart: All zeros
try {
  const htmlBarZero = ReactDOMServer.renderToString(
    React.createElement(InteractiveBarChart, {
      data: [{ cat: 'A', val: 0 }, { cat: 'B', val: 0 }],
      categoryKey: 'cat',
      series: [{ id: 's1', name: 'Series 1', color: '#10B981', dataKey: 'val' }],
    })
  );
  assert(!htmlBarZero.includes('NaN'), 'BarChart (all zeros): Renders without NaN in SVG');
} catch (err) {
  assert(false, 'BarChart (all zeros): Threw exception', { error: err.message });
}

// Bar Chart: Stacked & Horizontal
try {
  const htmlBarStacked = ReactDOMServer.renderToString(
    React.createElement(InteractiveBarChart, {
      data: [{ cat: 'A', s1: 30, s2: 70 }, { cat: 'B', s1: 40, s2: 60 }],
      categoryKey: 'cat',
      mode: 'stacked',
      series: [
        { id: 's1', name: 'Series 1', color: '#10B981', dataKey: 's1' },
        { id: 's2', name: 'Series 2', color: '#EF4444', dataKey: 's2' },
      ],
    })
  );
  assert(!htmlBarStacked.includes('NaN'), 'BarChart (stacked mode): Renders without NaN');

  const htmlBarHoriz = ReactDOMServer.renderToString(
    React.createElement(InteractiveBarChart, {
      data: [{ cat: 'Module 1', val: 95 }, { cat: 'Module 2', val: 40 }],
      categoryKey: 'cat',
      orientation: 'horizontal',
      series: [{ id: 's1', name: 'Val', color: '#06B6D4', dataKey: 'val' }],
    })
  );
  assert(!htmlBarHoriz.includes('NaN'), 'BarChart (horizontal mode): Renders without NaN');
} catch (err) {
  assert(false, 'BarChart (stacked/horizontal): Threw exception', { error: err.message });
}

console.log('\n--- 3. Testing InteractiveDonutChart SSR Rendering ---');

// Donut Chart: Empty data
try {
  const htmlDonutEmpty = ReactDOMServer.renderToString(
    React.createElement(InteractiveDonutChart, {
      data: [],
    })
  );
  assert(!htmlDonutEmpty.includes('NaN'), 'DonutChart (empty data): Renders without NaN in SVG');
  assert(htmlDonutEmpty.includes('0'), 'DonutChart (empty data): Center readout defaults to 0');
} catch (err) {
  assert(false, 'DonutChart (empty data): Threw exception', { error: err.message });
}

// Donut Chart: All zeros
try {
  const htmlDonutZero = ReactDOMServer.renderToString(
    React.createElement(InteractiveDonutChart, {
      data: [
        { id: 'c', label: 'Critical', value: 0, color: '#EF4444' },
        { id: 'h', label: 'High', value: 0, color: '#F97316' },
      ],
    })
  );
  assert(!htmlDonutZero.includes('NaN'), 'DonutChart (all zeros): Renders without NaN in SVG');
  console.log('  [DEBUG htmlDonutZero snippet]:', htmlDonutZero.substring(htmlDonutZero.indexOf('<button'), htmlDonutZero.indexOf('</button>') + 9));
  assert(htmlDonutZero.includes('(<!-- -->0<!-- -->%)') || htmlDonutZero.includes('(0%)'), 'DonutChart (all zeros): Legend percentages display 0% safely', { snippet: htmlDonutZero.substring(htmlDonutZero.indexOf('<button'), htmlDonutZero.indexOf('</button>') + 9) });
} catch (err) {
  assert(false, 'DonutChart (all zeros): Threw exception', { error: err.message });
}

// Donut Chart: Single 100% slice
try {
  const htmlDonutSolo = ReactDOMServer.renderToString(
    React.createElement(InteractiveDonutChart, {
      data: [{ id: 'solo', label: 'Clean', value: 100, color: '#10B981' }],
    })
  );
  assert(!htmlDonutSolo.includes('NaN'), 'DonutChart (100% slice): Renders concentric ring without NaN');
  assert(htmlDonutSolo.includes('Clean'), 'DonutChart (100% slice): Contains slice label');
} catch (err) {
  assert(false, 'DonutChart (100% slice): Threw exception', { error: err.message });
}

console.log('\n--- 4. Testing InteractiveGaugeChart SSR Rendering ---');

// Gauge Chart: 0, 50, 100, underflow, overflow
for (const val of [0, 50, 100, -25, 250]) {
  try {
    const htmlGauge = ReactDOMServer.renderToString(
      React.createElement(InteractiveGaugeChart, {
        value: val,
        minValue: 0,
        maxValue: 100,
      })
    );
    assert(!htmlGauge.includes('NaN'), `GaugeChart (val=${val}): Renders without NaN in SVG`);
    assert(htmlGauge.includes('animate-ping'), `GaugeChart (val=${val}): Contains glowing indicator pip`);
  } catch (err) {
    assert(false, `GaugeChart (val=${val}): Threw exception`, { error: err.message });
  }
}

console.log('\n--- 5. Testing ChartTooltip SSR Rendering ---');

try {
  const htmlTip = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 100,
      y: 50,
      containerWidth: 500,
      visible: true,
      title: 'Tooltip Title',
      payload: [{ name: 'Metric', value: '42', color: '#06B6D4' }],
    })
  );
  assert(htmlTip.includes('Tooltip Title'), 'ChartTooltip: Renders title');
  assert(htmlTip.includes('42'), 'ChartTooltip: Renders metric value');
  assert(htmlTip.includes('left:112px'), 'ChartTooltip: Positions left at x + 12');

  const htmlTipFlipped = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 450,
      y: 50,
      containerWidth: 500,
      visible: true,
      title: 'Flipped',
      payload: [{ name: 'Metric', value: '10', color: '#06B6D4' }],
    })
  );
  assert(htmlTipFlipped.includes('left:278px'), 'ChartTooltip: Auto-flips left near right edge (x - 160 - 12 = 278px)');

  const htmlTipHidden = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 100,
      y: 50,
      containerWidth: 500,
      visible: false,
    })
  );
  assert(htmlTipHidden === '', 'ChartTooltip: Returns null when visible=false');
} catch (err) {
  assert(false, 'ChartTooltip: Threw exception', { error: err.message });
}

// -----------------------------------------------------------------------------
// SUMMARY
// -----------------------------------------------------------------------------
console.log('\n' + '='.repeat(70));
console.log(`TOTAL PASSES: ${passCount}`);
console.log(`TOTAL FAILURES: ${failCount}`);
console.log('='.repeat(70));

if (failCount > 0) {
  console.error('\nFailures summary:');
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
} else {
  console.log('\nALL REACT SSR EMPIRICAL RENDERING TESTS PASSED CLEANLY.');
  process.exit(0);
}
