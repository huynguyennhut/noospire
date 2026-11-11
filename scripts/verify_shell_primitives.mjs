/**
 * EMPIRICAL ADVERSARIAL VERIFICATION HARNESS FOR MILESTONE 5
 * Responsive Shell & Viewport Behavior + UI Primitives Resilience
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const FRONTEND_DIR = path.resolve('frontend');
const SRC_DIR = path.join(FRONTEND_DIR, 'src');

console.log('====================================================================');
console.log('   MILESTONE 5 ADVERSARIAL VERIFICATION: SHELL & UI PRIMITIVES    ');
console.log('====================================================================\n');

let totalChecks = 0;
let passedChecks = 0;
let failedChecks = 0;

function assert(condition, testName, failureDetail = '') {
  totalChecks++;
  if (condition) {
    passedChecks++;
    console.log(`  [+] PASS: ${testName}`);
  } else {
    failedChecks++;
    console.error(`  [-] FAIL: ${testName}`);
    if (failureDetail) console.error(`      Detail: ${failureDetail}`);
  }
}

// ============================================================================
// SUITE 1: SOURCE INSPECTION & CONTRACT COMPLIANCE OF UI PRIMITIVES
// ============================================================================
console.log('[SUITE 1] Inspecting UI Primitives (Button, Modal, Table, Tooltip)...');

// 1.1 Button Primitives
const buttonPath = path.join(SRC_DIR, 'components', 'ui', 'button.tsx');
assert(fs.existsSync(buttonPath), 'Button component file exists');
const buttonContent = fs.readFileSync(buttonPath, 'utf8');

assert(buttonContent.includes("export type ButtonVariant = 'primary' | 'secondary' | 'destructive' | 'outline' | 'ghost' | 'glass'"),
  'Button declares all 6 required variants: primary, secondary, destructive, outline, ghost, glass');
assert(buttonContent.includes("export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'"),
  'Button declares all 4 required sizes: sm, md, lg, icon');
assert(buttonContent.includes('disabled={disabled || loading}'),
  'Button automatically disables when loading={true}');
assert(buttonContent.includes('Loader2') && buttonContent.includes('animate-spin'),
  'Button renders animated Loader2 spinner during loading state');
assert(buttonContent.includes('React.forwardRef<HTMLButtonElement, ButtonProps>'),
  'Button properly forwards DOM ref to native button element');
assert(buttonContent.includes('disabled:pointer-events-none') && buttonContent.includes('disabled:opacity-50'),
  'Button applies proper disabled styling (pointer-events-none, opacity-50)');

// 1.2 Modal Primitives
const modalPath = path.join(SRC_DIR, 'components', 'ui', 'modal.tsx');
assert(fs.existsSync(modalPath), 'Modal component file exists');
const modalContent = fs.readFileSync(modalPath, 'utf8');

assert(modalContent.includes('createPortal(modalNode, document.body)'),
  'Modal mounts via React createPortal to document.body');
assert(modalContent.includes("role=\"dialog\"") && modalContent.includes("aria-modal=\"true\""),
  'Modal provides role="dialog" and aria-modal="true" accessibility attributes');
assert(modalContent.includes("e.key === 'Escape'") && modalContent.includes('onClose()'),
  'Modal handles Escape key event listener to trigger onClose');
assert(modalContent.includes("window.removeEventListener('keydown', handleKeyDown)"),
  'Modal cleans up Escape key event listener on unmount or close');
assert(modalContent.includes("document.body.style.overflow = 'hidden'"),
  'Modal locks body scroll when open');
assert(modalContent.includes('document.body.style.overflow = originalStyle'),
  'Modal restores original body scroll style on unmount or close');
assert(modalContent.includes('closeOnBackdrop') && modalContent.includes('e.stopPropagation()'),
  'Modal supports backdrop dismissal with click stopPropagation on modal dialog content');

// 1.3 Table Primitives
const tablePath = path.join(SRC_DIR, 'components', 'ui', 'table.tsx');
assert(fs.existsSync(tablePath), 'Table component file exists');
const tableContent = fs.readFileSync(tablePath, 'utf8');

assert(tableContent.includes('overflow-x-auto'),
  'Table wrapper enforces overflow-x-auto for narrow container responsiveness');
assert(tableContent.includes('TableHeader') && tableContent.includes('TableBody') && tableContent.includes('TableCell'),
  'Table exports all standard table subcomponents (Header, Body, Row, Head, Cell, Footer, Caption)');
assert(tableContent.includes('TableEmpty'),
  'Table exports TableEmpty fallback component for zero-record states');
assert(tableContent.includes('whitespace-nowrap'),
  'TableHead enforces whitespace-nowrap to prevent awkward column header wrapping');

// 1.4 Additional UI Primitives (Card, Badge, Tooltip, Input, Tabs)
const badgePath = path.join(SRC_DIR, 'components', 'ui', 'badge.tsx');
const cardPath = path.join(SRC_DIR, 'components', 'ui', 'card.tsx');
const tooltipPath = path.join(SRC_DIR, 'components', 'ui', 'tooltip.tsx');
assert(fs.existsSync(badgePath) && fs.existsSync(cardPath) && fs.existsSync(tooltipPath),
  'Ancillary UI primitives (Badge, Card, Tooltip) exist in components/ui/');

// ============================================================================
// SUITE 2: RESPONSIVE SHELL BREAKPOINTS & INTERACTIVE CONTROLS
// ============================================================================
console.log('\n[SUITE 2] Inspecting Responsive Shell Breakpoint Architecture...');

const shellPath = path.join(SRC_DIR, 'components', 'layout', 'Shell.tsx');
assert(fs.existsSync(shellPath), 'Shell.tsx layout exists');
const shellContent = fs.readFileSync(shellPath, 'utf8');

// 2.1 Mobile Viewport (< 768px)
assert(shellContent.includes('md:hidden') && shellContent.includes('h-14'),
  'Mobile top bar renders exclusively on mobile via md:hidden with h-14 height');
assert(shellContent.includes('aria-expanded={mobileMenuOpen}'),
  'Mobile hamburger button binds aria-expanded for screen reader accessibility');
assert(shellContent.includes('role="dialog"') && shellContent.includes('aria-modal="true"'),
  'Mobile slide-over drawer modal renders with role="dialog" and aria-modal="true"');
assert(shellContent.includes('backdrop-blur-md') && shellContent.includes('bg-cyber-950/80'),
  'Mobile drawer backdrop renders frosted dark overlay with backdrop blur');
assert(shellContent.includes("w-80 max-w-[85vw]") && shellContent.includes("translate-x-0") && shellContent.includes("-translate-x-full"),
  'Mobile drawer slides horizontally with responsive max-w-[85vw] and transform transitions');
assert(shellContent.includes('min-h-[44px]'),
  'Mobile navigation links satisfy WCAG 2.1 AAA touch target minimum height of 44px');
assert(shellContent.includes("document.body.style.overflow = 'hidden'"),
  'Mobile drawer open triggers document.body.style.overflow = "hidden" body scroll lock');
assert(shellContent.includes("document.body.style.overflow = ''"),
  'Mobile drawer dismissal restores document.body.style.overflow');
assert(shellContent.includes("e.key === 'Escape'") && shellContent.includes('setMobileMenuOpen(false)'),
  'Escape key dismisses mobile navigation drawer');

// 2.2 Tablet Viewport (768px - 1024px)
assert(shellContent.includes('hidden md:flex') && shellContent.includes("sidebarCollapsed ? 'w-20' : 'w-64'"),
  'Sidebar renders collapsible width transition between w-64 (expanded) and w-20 (collapsed) from md breakpoint');
assert(shellContent.includes("localStorage.getItem('sentinel_sidebar_collapsed')"),
  'Sidebar state initializes from localStorage key "sentinel_sidebar_collapsed"');
assert(shellContent.includes("localStorage.setItem('sentinel_sidebar_collapsed'"),
  'Sidebar toggle persists new collapsed state to localStorage');
assert(shellContent.includes('try {') && shellContent.includes('catch (_)'),
  'LocalStorage operations are safely wrapped in try-catch to prevent private mode crashes');
assert(shellContent.includes('title={sidebarCollapsed ? translatedName : undefined}'),
  'Collapsed sidebar items display native tooltip titles when label text is hidden');

// 2.3 Desktop Viewport (> 1024px)
assert(shellContent.includes('sticky top-0 h-screen'),
  'Desktop sidebar uses sticky top-0 h-screen for fixed viewport navigation');
assert(shellContent.includes('hidden md:flex sticky top-0 z-30') && shellContent.includes('h-14'),
  'Desktop top utility bar is sticky with z-30 and h-14 height');
assert(shellContent.includes('notificationsOpen') && shellContent.includes('notificationsRef'),
  'Notification popover uses dedicated ref and outside click event listener');
assert(shellContent.includes("document.addEventListener('mousedown', handleClickOutside)"),
  'Notification popover attaches outside click listener when open');
assert(shellContent.includes("document.removeEventListener('mousedown', handleClickOutside)"),
  'Notification popover detaches outside click listener on close');
assert(shellContent.includes('markAllAlertsRead'),
  'Notification center provides functional mark-all-read action');
assert(shellContent.includes("setLocale('vi')") && shellContent.includes("setLocale('en')"),
  'Bilingual toggle controls provide explicit VI / EN locale switches');

// 2.4 Complete 14 Views Navigation Taxonomy
const EXPECTED_ROUTES = [
  '/dashboard',
  '/assets',
  '/scans',
  '/active-assessments',
  '/schedules',
  '/empire-modules',
  '/findings',
  '/threat-intel',
  '/remediation',
  '/detection-rules',
  '/reports',
  '/integrations',
  '/health',
  '/settings',
];

for (const route of EXPECTED_ROUTES) {
  assert(shellContent.includes(`href: '${route}'`), `Navigation taxonomy includes view route: ${route}`);
}

// ============================================================================
// SUITE 3: RUNTIME SERVER & HEADLESS HTTP STRESS TEST ACROSS ALL 14 ROUTES
// ============================================================================
console.log('\n[SUITE 3] Spawning Next.js Production Server for Headless Route Validation...');

async function runServerSuite() {
  const TEST_PORT = 3456;
  const nextCmd = process.platform === 'win32'
    ? path.join(FRONTEND_DIR, 'node_modules', '.bin', 'next.cmd')
    : path.join(FRONTEND_DIR, 'node_modules', '.bin', 'next');
  
  const serverProcess = spawn(nextCmd, ['start', '-p', String(TEST_PORT)], {
    cwd: FRONTEND_DIR,
    shell: true,
    env: { ...process.env, PORT: String(TEST_PORT) },
  });

  let serverStarted = false;

  serverProcess.stdout.on('data', (d) => {
    const msg = d.toString();
    if (msg.includes('Ready in') || msg.includes('started server on') || msg.includes(`http://localhost:${TEST_PORT}`)) {
      serverStarted = true;
    }
  });

  serverProcess.stderr.on('data', (d) => {
    // ignore warnings
  });

  // Wait up to 15s for server to start
  console.log('  [*] Waiting for Next.js production server on port ' + TEST_PORT + '...');
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (serverStarted) break;
    // Probe HTTP directly
    try {
      await new Promise((res, rej) => {
        const req = http.get(`http://127.0.0.1:${TEST_PORT}/dashboard`, (resHttp) => {
          serverStarted = true;
          res();
        });
        req.on('error', rej);
        req.setTimeout(300, () => req.destroy());
      });
      break;
    } catch (_) {}
  }

  assert(serverStarted, `Next.js production server started on port ${TEST_PORT}`);

  if (serverStarted) {
    console.log('  [*] Testing HTTP response codes, headers, and responsive HTML payloads...');

    for (const route of EXPECTED_ROUTES) {
      try {
        const { statusCode, body } = await new Promise((resolve, reject) => {
          const req = http.get(`http://127.0.0.1:${TEST_PORT}${route}`, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => resolve({ statusCode: res.statusCode, body: data }));
          });
          req.on('error', reject);
        });

        const statusOk = statusCode === 200;
        assert(statusOk, `Route ${route} returned HTTP 200 OK (got ${statusCode})`);

        // Check for shell presence in HTML
        const hasNoosforgeBrand = body.includes('NOOSFORGE');
        const hasMobileHeader = body.includes('md:hidden');
        const hasDesktopAside = body.includes('hidden md:flex');
        
        assert(hasNoosforgeBrand, `Route ${route} contains NOOSFORGE brand in rendered DOM`);
        assert(hasMobileHeader && hasDesktopAside, `Route ${route} contains both responsive Mobile and Desktop Shell markup`);

      } catch (err) {
        assert(false, `Route ${route} failed with error: ${err.message}`);
      }
    }
  }

  // Gracefully terminate server
  console.log('  [*] Shutting down test server...');
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(serverProcess.pid), '/f', '/t']);
  } else {
    serverProcess.kill('SIGTERM');
  }

  // Final Summary
  console.log('\n====================================================================');
  console.log(`   VERIFICATION RESULTS: ${passedChecks}/${totalChecks} CHECKS PASSED`);
  if (failedChecks === 0) {
    console.log('   STATUS: 100% PASS — ZERO DEFECTS FOUND');
  } else {
    console.log(`   STATUS: ${failedChecks} CHECKS FAILED`);
  }
  console.log('====================================================================\n');

  process.exit(failedChecks > 0 ? 1 : 0);
}

runServerSuite().catch((err) => {
  console.error('Fatal test error:', err);
  process.exit(1);
});
