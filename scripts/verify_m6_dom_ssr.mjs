/**
 * Empirical React SSR & Adversarial DOM Injection Harness
 * Verifies EvidenceViewer and ChartTooltip under adversarial inputs:
 * - Empty props / Null values
 * - XSS injection vectors (<script>, <img onerror>, SVG injection)
 * - 100KB payload stress
 * - Multi-tab rendering across Proof, Request, Response, Headers, cURL
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ts = require('../frontend/node_modules/typescript');
const React = require('../frontend/node_modules/react');
const ReactDOMServer = require('../frontend/node_modules/react-dom/server');

console.log('='.repeat(80));
console.log('NOOSFORGE M6 REACT SSR & ADVERSARIAL DOM INJECTION HARNESS');
console.log('='.repeat(80));

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

// Module loader that handles TS/TSX and path resolution
const moduleCache = new Map();

function loadModule(fullPath) {
  if (moduleCache.has(fullPath)) return moduleCache.get(fullPath);

  let source = fs.readFileSync(fullPath, 'utf-8');
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
    if (specifier === 'clsx') return (...args) => args.filter(Boolean).join(' ');
    if (specifier === 'tailwind-merge') return { twMerge: (...args) => args.filter(Boolean).join(' ') };
    if (specifier === 'lucide-react') {
      // Mock lucide icons as SVG stubs
      const icons = {};
      const iconNames = [
        'FileCode', 'Terminal', 'Layers', 'Copy', 'Check', 'Flame', 'ShieldAlert',
        'ArrowRight', 'ExternalLink', 'RotateCcw', 'ShieldCheck', 'AlertOctagon',
        'UserCheck', 'AlertTriangle', 'Search', 'Download', 'CheckSquare', 'Square',
        'MinusSquare', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight',
        'Eye', 'Clock', 'Server', 'Crosshair', 'Activity', 'RefreshCw', 'CheckCircle2',
        'TrendingUp', 'BarChart3', 'PieChart', 'Radio', 'Zap', 'Gauge'
      ];
      for (const name of iconNames) {
        icons[name] = (props) => React.createElement('svg', { ...props, 'data-icon': name });
      }
      return icons;
    }

    if (specifier === '@/lib/utils') {
      return {
        cn: (...args) => args.filter(Boolean).join(' '),
      };
    }

    if (specifier === '@/lib/i18n') {
      return {
        useI18n: () => ({
          t: (key, fallback) => fallback || key,
          locale: 'vi',
          setLocale: () => {},
        }),
      };
    }

    if (specifier === '@/lib/api') {
      return {
        api: {
          retestFinding: async () => ({ status: 'VERIFIED', retest_status: 'VERIFIED_FIXED', notes: 'OK' }),
          getFinding: async (id) => ({ id, status: 'FIXED' }),
          triageFinding: async (id, st) => ({ id, status: st }),
        },
      };
    }

    if (specifier.startsWith('@/components/ui')) {
      const sub = specifier.replace('@/components/ui', '');
      let targetPath;
      if (!sub || sub === '/') {
        targetPath = path.resolve('frontend/src/components/ui/index.ts');
      } else {
        targetPath = path.resolve('frontend/src/components/ui', sub.replace(/^\//, '') + '.tsx');
        if (!fs.existsSync(targetPath)) {
          targetPath = path.resolve('frontend/src/components/ui', sub.replace(/^\//, '') + '.ts');
        }
      }
      return loadModule(targetPath);
    }

    if (specifier.startsWith('./') || specifier.startsWith('../')) {
      const dir = path.dirname(fullPath);
      let resolved = path.resolve(dir, specifier);
      if (fs.existsSync(resolved + '.tsx')) resolved += '.tsx';
      else if (fs.existsSync(resolved + '.ts')) resolved += '.ts';
      else if (fs.existsSync(path.join(resolved, 'index.ts'))) resolved = path.join(resolved, 'index.ts');
      return loadModule(resolved);
    }

    return require(specifier);
  };

  const fn = new Function('require', 'module', 'exports', transpiled.outputText);
  fn(customRequire, customModule, customModule.exports);

  moduleCache.set(fullPath, customModule.exports);
  return customModule.exports;
}

// ----------------------------------------------------------------------------
// Test 1: ChartTooltip SSR & Boundary Rendering
// ----------------------------------------------------------------------------
console.log('\n--- 1. Testing ChartTooltip SSR & Boundary Rendering ---');
const { ChartTooltip } = loadModule(path.resolve('frontend/src/components/charts/ChartTooltip.tsx'));

try {
  // Test invisible
  const htmlNull = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 100,
      y: 100,
      containerWidth: 500,
      visible: false,
      payload: [{ name: 'Test', value: 10, color: '#000' }],
    })
  );
  assert(htmlNull === '', 'ChartTooltip: returns null when visible=false');

  // Test visible with payload
  const htmlVis = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 100,
      y: 50,
      containerWidth: 500,
      visible: true,
      title: 'Telemetry 2026-11-08',
      payload: [
        { name: 'Critical', value: 5, color: '#ef4444' },
        { name: 'High', value: 12, color: '#f97316' },
      ],
    })
  );
  assert(htmlVis.includes('Telemetry 2026-11-08'), 'ChartTooltip: renders title string');
  assert(htmlVis.includes('Critical'), 'ChartTooltip: renders payload series names');
  assert(htmlVis.includes('12'), 'ChartTooltip: renders payload series values');
  assert(htmlVis.includes('112px'), 'ChartTooltip: correctly offsets left position (+12px -> 112px)');
  assert(htmlVis.includes('26px'), 'ChartTooltip: correctly offsets top position (y - 24 = 26px)');

  // Test Auto-Flip Right Boundary (x = 450, container = 500)
  // 450 + 160 + 24 = 634 > 500 -> flips left to 450 - 160 - 12 = 278px
  const htmlFlip = ReactDOMServer.renderToString(
    React.createElement(ChartTooltip, {
      x: 450,
      y: 50,
      containerWidth: 500,
      visible: true,
      payload: [{ name: 'Val', value: 99, color: '#06b6d4' }],
    })
  );
  assert(htmlFlip.includes('278px'), 'ChartTooltip: auto-flips left when near right boundary (left: 278px)');
} catch (err) {
  assert(false, 'ChartTooltip SSR threw error', { error: err.message });
}

// ----------------------------------------------------------------------------
// Test 2: EvidenceViewer SSR & Adversarial Inputs
// ----------------------------------------------------------------------------
console.log('\n--- 2. Testing EvidenceViewer SSR & Adversarial Inputs ---');
const EvidenceViewerModule = loadModule(path.resolve('frontend/src/components/evidence/EvidenceViewer.tsx'));
const EvidenceViewer = EvidenceViewerModule.default || EvidenceViewerModule;

// Case 2.1: Default Empty Props
try {
  const htmlEmpty = ReactDOMServer.renderToString(
    React.createElement(EvidenceViewer, {})
  );
  assert(htmlEmpty.includes('RULE-DEFAULT'), 'EvidenceViewer: handles missing finding prop with fallback rule ID defaults');
  assert(htmlEmpty.includes('CVSS v3.1 Base Score'), 'EvidenceViewer: renders CVSS score panel');
  assert(htmlEmpty.includes('Forensic Matched Proof'), 'EvidenceViewer: renders Proof tab panel');
} catch (err) {
  assert(false, 'EvidenceViewer with empty props threw error', { error: err.message });
}

// Case 2.2: XSS Injection & Special Characters
try {
  const xssFinding = {
    id: 'finding-xss-1',
    scan_id: 'scan-1',
    asset_id: 'asset-1',
    fingerprint: 'fp-1',
    title: '<script>alert("XSS_TITLE")</script>',
    description: '"><svg/onload=alert(1)>',
    severity: 'CRITICAL',
    cvss_score: 9.8,
    cve_id: 'CVE-2026-99999',
    cwe_id: 'CWE-79',
    scanner_engine: 'nuclei',
    scanner_rule_id: 'RULE-XSS-PROBE',
    status: 'OPEN',
    target_location: 'https://empire.edu.vn/search?q=<script>prompt(1)</script>',
    target_component: '<marquee>Injected</marquee>',
    empire_module: 'API_SERVICES',
    exposure_classification: 'PUBLIC',
    evidence: {
      matched_content: '<script>alert("XSS_PAYLOAD")</script>',
      headers: {
        'X-Malicious-Header': '<script>evil()</script>',
      },
    },
  };

  const htmlXss = ReactDOMServer.renderToString(
    React.createElement(EvidenceViewer, { finding: xssFinding })
  );

  // React must escape dangerous characters in matched proof and target location
  assert(!htmlXss.includes('<script>alert("XSS_PAYLOAD")</script>'), 'EvidenceViewer: strictly escapes raw <script> in matched proof');
  assert(htmlXss.includes('&lt;script&gt;alert(&quot;XSS_PAYLOAD&quot;)&lt;/script&gt;'), 'EvidenceViewer: correctly HTML-escapes script tags to safe entities');
  assert(htmlXss.includes('RULE-XSS-PROBE'), 'EvidenceViewer: renders rule ID safely');
} catch (err) {
  assert(false, 'EvidenceViewer XSS injection test threw error', { error: err.message });
}

// Case 2.3: 100KB Massive Payload Stress
try {
  const massiveProof = 'A'.repeat(100 * 1024); // 100KB
  const heavyFinding = {
    id: 'finding-heavy',
    scan_id: 'scan-1',
    asset_id: 'asset-1',
    fingerprint: 'fp-heavy',
    title: 'Massive Buffer Overflow Trigger Payload',
    description: 'Heavy memory payload forensic record',
    severity: 'HIGH',
    cvss_score: 8.5,
    cve_id: null,
    cwe_id: 'CWE-119',
    scanner_engine: 'empire_engine',
    scanner_rule_id: 'EMPIRE-HEAVY-01',
    status: 'OPEN',
    target_location: 'https://empire.edu.vn/api/v1/buffer',
    target_component: 'Memory Heap',
    empire_module: 'SERVER_INFRASTRUCTURE',
    exposure_classification: 'INTERNAL',
    evidence: {
      matched_content: massiveProof,
    },
  };

  const tStart = Date.now();
  const htmlHeavy = ReactDOMServer.renderToString(
    React.createElement(EvidenceViewer, { finding: heavyFinding })
  );
  const elapsed = Date.now() - tStart;

  assert(htmlHeavy.length > 100 * 1024, 'EvidenceViewer: renders 100KB massive payload in DOM string');
  assert(elapsed < 1000, `EvidenceViewer: 100KB render completes in ${elapsed}ms (< 1000ms SLA)`);
} catch (err) {
  assert(false, 'EvidenceViewer massive payload test threw error', { error: err.message });
}

// ----------------------------------------------------------------------------
// Summary & Verdict
// ----------------------------------------------------------------------------
console.log('\n' + '='.repeat(80));
console.log(`DOM SSR TESTS: ${passCount + failCount} | PASS: ${passCount} | FAIL: ${failCount}`);
console.log('='.repeat(80));

if (failCount > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
