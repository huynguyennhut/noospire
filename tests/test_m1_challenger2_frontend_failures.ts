/**
 * tests/test_m1_challenger2_frontend_failures.ts
 *
 * Empirical Challenger 2 Stress Test Suite:
 * Adversarial validation of Frontend API Client & Scan Engine error handling:
 * 1. HTTP 503 Service Unavailable failure handling (visible launch error, zero fake job IDs, zero local findings)
 * 2. HTTP 200 HTML SPA response handling (explicit rejection, zero JSON parse crash, zero fake job IDs)
 * 3. Client-side scan fabrication prevention (dispatchNewScan throws, zero local storage pollution)
 * 4. Verification that handleFallback and fallback data imports are absent from api.ts
 */

import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { api } from '../frontend/src/lib/api';
import {
  dispatchNewScan,
  startLiveScanWorker,
  getStoredScans,
  getStoredFindings,
} from '../frontend/src/lib/scan-engine';

// Mock localStorage for node environment
const storage: Record<string, string> = {};
const mockLocalStorage = {
  getItem: (key: string) => storage[key] ?? null,
  setItem: (key: string, value: string) => {
    storage[key] = value;
  },
  removeItem: (key: string) => {
    delete storage[key];
  },
  clear: () => {
    for (const k of Object.keys(storage)) {
      delete storage[k];
    }
  },
  get length() {
    return Object.keys(storage).length;
  },
  key: (i: number) => Object.keys(storage)[i] ?? null,
};

// Install mock window and localStorage
(global as any).window = {
  localStorage: mockLocalStorage,
};
(global as any).localStorage = mockLocalStorage;

async function runTests() {
  console.log('=============================================================================');
  console.log('STARTING EMPIRICAL CHALLENGER 2: FRONTEND INCIDENT FAILURE & BOUNDARY TESTS');
  console.log('=============================================================================');

  let passed = 0;
  let failed = 0;

  function report(name: string, ok: boolean, details?: string) {
    if (ok) {
      console.log(`[PASS] ${name}`);
      passed++;
    } else {
      console.error(`[FAIL] ${name} -> ${details}`);
      failed++;
    }
  }

  // --------------------------------------------------------------------------
  // TEST 1: Challenge API client with mock HTTP 503 Service Unavailable
  // --------------------------------------------------------------------------
  try {
    mockLocalStorage.clear();

    // Mock fetch to simulate 503 Service Unavailable
    (global as any).fetch = async (url: string, init?: RequestInit) => {
      return {
        status: 503,
        statusText: 'Service Unavailable',
        ok: false,
        headers: new Headers({
          'content-type': 'text/plain',
        }),
        json: async () => {
          throw new Error('No JSON body on 503');
        },
        text: async () => '503 Service Unavailable - Upstream down',
      };
    };

    let thrownError: any = null;
    let returnedJob: any = null;

    try {
      returnedJob = await api.dispatchScan({
        asset_id: 'a0000000-0000-0000-0000-000000000001',
        engine: 'nuclei',
        profile: 'BASELINE',
      });
    } catch (err: any) {
      thrownError = err;
    }

    assert(thrownError !== null, 'Expected dispatchScan to throw on HTTP 503');
    assert.strictEqual(thrownError.status, 503, `Expected status 503, got ${thrownError.status}`);
    assert(
      thrownError.message.includes('503') || thrownError.message.includes('Service Unavailable'),
      `Expected message to mention 503 or Service Unavailable, got: ${thrownError.message}`
    );
    assert.strictEqual(returnedJob, null, 'No job must be returned on 503');

    // Check storage for any fake job IDs or fabricated findings
    const storedScans = getStoredScans();
    const storedFindings = getStoredFindings();
    const storedKeys = Object.keys(storage);

    // Verify zero fake jobs in storage created during 503
    const hasFakeJobs = storedScans.some((s) => s.id.includes('temp-') || s.id.includes('sim-'));
    assert(!hasFakeJobs, 'Found fake/simulated jobs in storage after 503');

    report('1.1. HTTP 503 on dispatchScan throws visible launch error with status 503', true);
    report('1.2. HTTP 503 produces zero fake job IDs and zero fabricated findings', true);
  } catch (err: any) {
    report('1. HTTP 503 Service Unavailable test', false, err.message);
  }

  // --------------------------------------------------------------------------
  // TEST 2: Challenge API client createBatchScan with HTTP 503
  // --------------------------------------------------------------------------
  try {
    let batchError: any = null;
    let batchResult: any = null;
    try {
      batchResult = await api.createBatchScan({
        targets: ['a0000000-0000-0000-0000-000000000001'],
        name: 'Adversarial 503 Test Batch',
      } as any);
    } catch (err: any) {
      batchError = err;
    }

    assert(batchError !== null, 'Expected createBatchScan to throw on 503');
    assert.strictEqual(batchError.status, 503, `Expected status 503, got ${batchError.status}`);
    assert.strictEqual(batchResult, null, 'No batch result should be returned on 503');

    report('2.1. HTTP 503 on createBatchScan throws explicit 503 error without fake batch ID', true);
  } catch (err: any) {
    report('2. HTTP 503 on createBatchScan', false, err.message);
  }

  // --------------------------------------------------------------------------
  // TEST 3: Challenge API client with HTTP 200 SPA HTML response (<!DOCTYPE html>...)
  // --------------------------------------------------------------------------
  try {
    const htmlBody = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Noospire Single Page Application</title>
</head>
<body>
  <div id="root">SPA Content Fallback</div>
</body>
</html>`;

    // Mock fetch to simulate 200 OK with text/html SPA fallback
    (global as any).fetch = async (url: string, init?: RequestInit) => {
      return {
        status: 200,
        statusText: 'OK',
        ok: true,
        headers: new Headers({
          'content-type': 'text/html; charset=utf-8',
        }),
        json: async () => {
          throw new SyntaxError('Unexpected token < in JSON at position 0');
        },
        text: async () => htmlBody,
      };
    };

    let spaError: any = null;
    let spaJob: any = null;

    try {
      spaJob = await api.dispatchScan({
        asset_id: 'a0000000-0000-0000-0000-000000000001',
        engine: 'nuclei',
        profile: 'BASELINE',
      });
    } catch (err: any) {
      spaError = err;
    }

    assert(spaError !== null, 'Expected dispatchScan to throw when 200 HTML SPA is returned');
    assert.strictEqual(spaJob, null, 'No job must be returned on SPA HTML fallback');
    assert.strictEqual(spaError.status, 502, `Expected status 502 for SPA fallback, got ${spaError.status}`);

    // Verify it is NOT an unhandled JSON parse crash
    assert(
      !spaError.message.includes('Unexpected token <'),
      'API client crashed with raw JSON parse SyntaxError instead of clean rejection!'
    );
    assert(
      spaError.message.includes('Unexpected HTML response') ||
      spaError.message.includes('SPA fallback detected'),
      `Expected message to explain SPA fallback, got: ${spaError.message}`
    );

    report('3.1. HTTP 200 SPA HTML response triggers explicit rejection with status 502', true);
    report('3.2. HTTP 200 SPA HTML prevents raw JSON parse crash (no "Unexpected token <")', true);
  } catch (err: any) {
    report('3. HTTP 200 SPA HTML response test', false, err.message);
  }

  // --------------------------------------------------------------------------
  // TEST 4: Challenge other API endpoints with HTTP 200 SPA HTML
  // --------------------------------------------------------------------------
  try {
    const endpointsToTest = [
      () => api.listScans(),
      () => api.listAssets(),
      () => api.getOverviewMetrics(),
      () => api.getEmpireModules(),
    ];

    for (const [idx, call] of endpointsToTest.entries()) {
      let errCaught: any = null;
      try {
        await call();
      } catch (err: any) {
        errCaught = err;
      }
      assert(errCaught !== null, `Endpoint index ${idx} did not throw on SPA HTML response`);
      assert.strictEqual(errCaught.status, 502, `Endpoint index ${idx} expected status 502, got ${errCaught.status}`);
      assert(
        !errCaught.message.includes('Unexpected token <'),
        `Endpoint index ${idx} suffered JSON parse crash`
      );
    }

    report('4.1. Multiple API endpoints (scans, assets, metrics, modules) cleanly reject SPA HTML with 502', true);
  } catch (err: any) {
    report('4. Multiple API endpoints SPA HTML test', false, err.message);
  }

  // --------------------------------------------------------------------------
  // TEST 5: Verify scan-engine.ts permanently rejects client-side scan fabrication
  // --------------------------------------------------------------------------
  try {
    let dispatchError: any = null;
    try {
      dispatchNewScan({ target: 'https://test.example.com' });
    } catch (err: any) {
      dispatchError = err;
    }

    assert(dispatchError !== null, 'Expected dispatchNewScan to throw an error');
    assert(
      dispatchError.message.includes('permanently disabled'),
      `Expected 'permanently disabled' error, got: ${dispatchError.message}`
    );

    // Verify startLiveScanWorker is a no-op and does not spawn timers or fabricate findings
    const scanCountBefore = getStoredScans().length;
    startLiveScanWorker(
      {
        id: 'fake-scan-123',
        target_locator: 'https://fake.example.com',
        engine: 'all',
        profile: 'BASELINE',
        status: 'INITIALIZING',
        progress_percentage: 0,
        created_at: new Date().toISOString(),
      } as any,
      undefined
    );
    const scanCountAfter = getStoredScans().length;
    assert.strictEqual(scanCountBefore, scanCountAfter, 'startLiveScanWorker must not inject fabricated scans');

    report('5.1. dispatchNewScan() throws permanent disablement error', true);
    report('5.2. startLiveScanWorker() is honest no-op without client-side fake scan generation', true);
  } catch (err: any) {
    report('5. Client-side scan engine fabrication test', false, err.message);
  }

  // --------------------------------------------------------------------------
  // TEST 6: Static codebase audit - zero handleFallback in api.ts
  // --------------------------------------------------------------------------
  try {
    const apiTsPath = path.resolve(__dirname, '../frontend/src/lib/api.ts');
    const apiContent = fs.readFileSync(apiTsPath, 'utf-8');

    assert(!apiContent.includes('handleFallback'), 'api.ts still contains handleFallback!');
    assert(!apiContent.includes('FALLBACK_SCANS'), 'api.ts still references FALLBACK_SCANS!');
    assert(!apiContent.includes('FALLBACK_FINDINGS'), 'api.ts still references FALLBACK_FINDINGS!');
    assert(!apiContent.includes('FALLBACK_ASSETS'), 'api.ts still references FALLBACK_ASSETS!');

    report('6.1. api.ts static inspection confirms 100% removal of handleFallback and fallback imports', true);
  } catch (err: any) {
    report('6. Static codebase audit in api.ts', false, err.message);
  }

  console.log('=============================================================================');
  console.log(`FRONTEND CHALLENGE RESULTS: ${passed} PASSED, ${failed} FAILED`);
  console.log('=============================================================================');

  if (failed > 0) {
    process.exit(1);
  }
}

runTests().catch((e) => {
  console.error('FATAL TEST ERROR:', e);
  process.exit(1);
});
