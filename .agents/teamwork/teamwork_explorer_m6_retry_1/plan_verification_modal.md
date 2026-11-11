# Implementation Plan: TargetVerificationModal Genuine Refactoring

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Integrity Violation in Milestone 6
During Milestone 6 review, Reviewer 2 flagged a critical **INTEGRITY VIOLATION** in `frontend/src/components/verification/TargetVerificationModal.tsx`:
1. **Client Simulation Loop**: `runVerificationPipeline()` executed an artificial loop across 8 steps using `await new Promise((resolve) => setTimeout(resolve, 320))` with synthetic latencies (`Math.floor(Math.random() * 35) + 15`).
2. **Hardcoded Mock Diagnostic Details**: The modal invoked `generateStepDetails()`, which returned static mock data (`103.142.26.18`, Let's Encrypt / Cloudflare ECC CA-3, `24,812 bytes`, Cloudflare Turnstile WAF) for any asset locator.
3. **Discarded Backend Response**: While `api.verifyAsset(asset.id, 'ADMIN_OVERRIDE')` was called, its real response payload (`res.steps` and `res.fingerprint`) was completely discarded.
4. **Self-Certifying Error Fallback**: In the catch block (line 283), any failure silently forced `setOverallStatus('VERIFIED')`, producing fake verification passes even on network crashes or invalid targets.
5. **ESLint Dependency Warning**: `initialSteps` was defined inside the component body and omitted from the `useEffect` dependency array, triggering `react-hooks/exhaustive-deps`.
6. **Hardcoded Drawer Tabs in `assets/page.tsx`**: Drawer Tab 2 (DNS & TLS) and Tab 3 (Endpoints) rendered static mock values regardless of which asset was selected.

### 1.2 Genuine Solution Architecture
To satisfy the strict integrity and production standards:
1. **Zero Artificial Delays / Dummy Loops**: Eliminate all `setTimeout` loops and fake random latencies.
2. **Real Probe Execution**: When verification is triggered, send an immediate asynchronous request to `POST /api/v1/assets/{id}/verify`.
3. **Direct Contract Mapping**: Directly map `res.steps` (`step`, `name`, `status`, `detail`, `metadata`) into UI state.
4. **Perimeter Fingerprint Inspector**: Bind `res.fingerprint` into an interactive, dedicated inspection panel displaying live web server, WAF/reverse proxy, framework, detected technologies, and 5-header baseline security posture.
5. **Honest Error Handling**: On probe failure or network exception, transition status to `FAILED`, display the verbatim backend error message in an alert banner, and update failing/aborted step states.
6. **ESLint Cleanliness**: Move canonical step definitions outside the component to guarantee clean dependency tracking and 0 warnings.
7. **Dynamic Drawer Tabs**: Provide dynamic, asset-bound data for Tabs 2 & 3 in `assets/page.tsx`.

---

## 2. Backend API Contract & Live Data Analysis

### 2.1 Backend Contract (`backend/app/schemas/asset.py`)
```python
class VerificationStepResult(BaseModel):
    step: int = Field(..., description="1-8 step sequence number")
    name: str = Field(..., description="Diagnostic step name")
    status: str = Field(..., description="PASS, FAIL, or INFO")
    detail: str = Field(..., description="Human-readable result summary")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic evidence metadata")

class AssetVerifyResponse(BaseModel):
    asset_id: uuid.UUID
    verification_status: VerificationStatus
    verified: bool
    status: str = Field(default="VERIFIED", description="VERIFIED or FAILED")
    message: str
    steps: List[VerificationStepResult] = Field(default_factory=list, description="8-step pipeline execution breakdown")
    fingerprint: Dict[str, Any] = Field(default_factory=dict, description="Target technology and infrastructure fingerprint")
```

### 2.2 Verified Live Probe Output (`https://empire.edu.vn/`)
When executed against the primary target `https://empire.edu.vn/`, `TargetVerifier` returns genuine diagnostic telemetry:
- **Duration**: ~1131ms total execution time.
- **Step 1 (Input Validation)**: `PASS` — Scheme `https`, host `empire.edu.vn`, port `443`, SSRF validated.
- **Step 2 (DNS Resolution)**: `PASS` — Resolved 1 IPv4 address for `empire.edu.vn`.
- **Step 3 (TLS Verification)**: `PASS` — Issued by Let's Encrypt, TLSv1.3, valid for 78 days.
- **Step 4 (HTTP Connectivity)**: `PASS` — Responded with status `200` in `637.65ms`.
- **Step 5 (Redirect Inspection)**: `PASS` — Direct landing without redirects on `https://empire.edu.vn/`.
- **Step 6 (Web Discovery)**: `PASS` — Probed `/robots.txt`, `/sitemap.xml`, and `/.well-known/security.txt`.
- **Step 7 (Target Fingerprint)**: `PASS` — Server `envoy`, WAF/Proxy `Envoy Reverse Proxy`, Framework `Next.js (React Framework)`.
- **Step 8 (Verification Result)**: `PASS` — Overall verdict `VERIFIED`.
- **Target Fingerprint**:
  ```json
  {
    "server": "envoy",
    "reverse_proxy_waf": "Envoy Reverse Proxy",
    "framework": "Next.js (React Framework)",
    "technologies": ["Envoy", "Next.js", "React"],
    "security_headers": {
      "strict_transport_security": "max-age=31536000; includeSubDomains",
      "content_security_policy": "frame-ancestors 'self'",
      "x_frame_options": "SAMEORIGIN",
      "x_content_type_options": "nosniff",
      "referrer_policy": "strict-origin-when-cross-origin"
    },
    "active_security_headers_count": 5
  }
  ```

### 2.3 Failure Scenario Analysis (e.g., Unresolvable Host or SSRF Violation)
When probing an invalid or blocked host:
- `res.status`: `"FAILED"`
- `res.verified`: `False`
- `res.message`: Verbatim error string (e.g. `Input validation rejected target: DNS resolution failed...`)
- `res.steps`: Contains only executed steps before abortion (e.g. Step 1 `FAIL`, Step 8 `FAIL`).
- The frontend step mapper must gracefully identify executed vs. skipped steps.

---

## 3. Component Architecture & State Transitions

### 3.1 State Machine
```
[ Modal Opened ] 
      │
      ▼
  State: IDLE (or VERIFIED if already verified in DB, with PENDING step placeholders)
      │
      │ User clicks "Execute 8-Step Verification" / "Re-run Verification"
      ▼
  State: RUNNING
  - isRunning: true
  - overallStatus: 'RUNNING'
  - errorMessage: null
  - steps: set to 'RUNNING' ("Probing live network interfaces...")
  - Await api.verifyAsset(asset.id, 'ADMIN_OVERRIDE')
      │
      ├─── Success Response (res.status === 'VERIFIED') ───► State: VERIFIED
      │    - overallStatus: 'VERIFIED'
      │    - steps: mapped from res.steps (status, detail, latency, metadata)
      │    - fingerprint: mapped from res.fingerprint
      │    - trigger onVerified(asset.id)
      │
      ├─── Backend Verification Failure (res.status === 'FAILED') ───► State: FAILED
      │    - overallStatus: 'FAILED'
      │    - errorMessage: res.message
      │    - steps: mapped from res.steps (failures & skipped steps preserved)
      │    - fingerprint: mapped from res.fingerprint
      │
      └─── Network / HTTP Error (catch) ───► State: FAILED
           - overallStatus: 'FAILED'
           - errorMessage: err.message
           - steps: mark running steps as 'FAIL' with error description
```

---

## 4. Complete Drop-In Code: `TargetVerificationModal.tsx`

Target file path: `frontend/src/components/verification/TargetVerificationModal.tsx`

```tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  X,
  Play,
  Globe,
  Lock,
  ArrowRight,
  Server,
  Layers,
  ChevronDown,
  ChevronRight,
  Code2,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Asset } from '@/lib/types';
import { useI18n } from '@/lib/i18n';

export interface TargetVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset: Asset | null;
  onVerified?: (assetId: string) => void;
}

export interface VerificationStepResult {
  step: number;
  name: string;
  status: 'PASS' | 'FAIL' | 'INFO';
  detail: string;
  metadata: Record<string, any>;
}

export interface TargetFingerprint {
  server?: string;
  reverse_proxy_waf?: string;
  framework?: string;
  technologies?: string[];
  security_headers?: Record<string, string | null>;
  active_security_headers_count?: number;
  [key: string]: any;
}

export interface AssetVerifyResponse {
  asset_id: string;
  verification_status: string;
  verified: boolean;
  status: 'VERIFIED' | 'FAILED';
  message: string;
  steps: VerificationStepResult[];
  fingerprint: TargetFingerprint;
}

export interface VerificationStepState {
  id: number;
  key: string;
  titleKey: string;
  descKey: string;
  defaultTitle: string;
  defaultDesc: string;
  icon: React.ComponentType<{ className?: string }>;
  status: 'PENDING' | 'RUNNING' | 'PASS' | 'FAIL' | 'INFO' | 'SKIPPED';
  latencyMs?: number;
  detail?: string;
  metadata?: Record<string, any>;
}

const CANONICAL_STEPS: Omit<VerificationStepState, 'status' | 'latencyMs' | 'detail' | 'metadata'>[] = [
  {
    id: 1,
    key: 'input_validation',
    titleKey: 'verify.step1Title',
    descKey: 'verify.step1Desc',
    defaultTitle: '1. Input Validation & SSRF Gatekeeper',
    defaultDesc: 'Validates URI syntax, scheme whitelist, private IP boundaries, and SSRF restrictions.',
    icon: Globe,
  },
  {
    id: 2,
    key: 'dns_resolution',
    titleKey: 'verify.step2Title',
    descKey: 'verify.step2Desc',
    defaultTitle: '2. DNS Resolution (A / AAAA Records)',
    defaultDesc: 'Resolves authoritative IPv4 and IPv6 target addresses via DNS infrastructure.',
    icon: Server,
  },
  {
    id: 3,
    key: 'tls_verification',
    titleKey: 'verify.step3Title',
    descKey: 'verify.step3Desc',
    defaultTitle: '3. TLS/SSL Certificate Verification',
    defaultDesc: 'Validates X.509 certificate trust chains, SAN hostnames, expiration, and cipher suites.',
    icon: Lock,
  },
  {
    id: 4,
    key: 'http_connectivity',
    titleKey: 'verify.step4Title',
    descKey: 'verify.step4Desc',
    defaultTitle: '4. HTTP Connectivity & Status Code',
    defaultDesc: 'Initiates bounded probe request, measures latency (ms), and inspects HTTP response status.',
    icon: ArrowRight,
  },
  {
    id: 5,
    key: 'redirect_inspection',
    titleKey: 'verify.step5Title',
    descKey: 'verify.step5Desc',
    defaultTitle: '5. Redirect Inspection & Downgrade Check',
    defaultDesc: 'Traces hop-by-hop redirect chains and detects insecure HTTPS-to-HTTP protocol downgrade.',
    icon: RefreshCw,
  },
  {
    id: 6,
    key: 'web_discovery',
    titleKey: 'verify.step6Title',
    descKey: 'verify.step6Desc',
    defaultTitle: '6. Web Discovery & Content Inspection',
    defaultDesc: 'Probes standard endpoints (/robots.txt, /sitemap.xml, /.well-known/security.txt).',
    icon: Layers,
  },
  {
    id: 7,
    key: 'fingerprinting',
    titleKey: 'verify.step7Title',
    descKey: 'verify.step7Desc',
    defaultTitle: '7. Technology Stack Fingerprint',
    defaultDesc: 'Profiles web server, application framework, reverse proxy/WAF, and baseline security headers.',
    icon: ShieldCheck,
  },
  {
    id: 8,
    key: 'result_authorization',
    titleKey: 'verify.step8Title',
    descKey: 'verify.step8Desc',
    defaultTitle: '8. Policy Verification & Scope Authorization',
    defaultDesc: 'Aggregates diagnostic report, commits verified state, and authorizes continuous scans.',
    icon: CheckCircle2,
  },
];

export default function TargetVerificationModal({
  isOpen,
  onClose,
  asset,
  onVerified,
}: TargetVerificationModalProps) {
  const { t } = useI18n();
  const [isRunning, setIsRunning] = useState(false);
  const [overallStatus, setOverallStatus] = useState<'IDLE' | 'RUNNING' | 'VERIFIED' | 'FAILED'>('IDLE');
  const [expandedStep, setExpandedStep] = useState<number | null>(null);
  const [fingerprint, setFingerprint] = useState<TargetFingerprint | null>(null);
  const [showRawFingerprint, setShowRawFingerprint] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastDurationMs, setLastDurationMs] = useState<number | null>(null);

  const resetSteps = useCallback((initialStatus: 'PENDING' | 'PASS' = 'PENDING'): VerificationStepState[] => {
    return CANONICAL_STEPS.map((s) => ({
      ...s,
      status: initialStatus,
      detail: undefined,
      latencyMs: undefined,
      metadata: undefined,
    }));
  }, []);

  const [steps, setSteps] = useState<VerificationStepState[]>(() => resetSteps('PENDING'));

  useEffect(() => {
    if (isOpen && asset) {
      setErrorMessage(null);
      setFingerprint(null);
      setExpandedStep(null);
      setLastDurationMs(null);

      if (asset.verification_status === 'VERIFIED') {
        setOverallStatus('VERIFIED');
        setSteps(resetSteps('PENDING'));
      } else {
        setOverallStatus('IDLE');
        setSteps(resetSteps('PENDING'));
      }
    }
  }, [isOpen, asset, resetSteps]);

  const runVerificationPipeline = async () => {
    if (!asset || isRunning) return;

    setIsRunning(true);
    setOverallStatus('RUNNING');
    setErrorMessage(null);

    // Transition steps to RUNNING state during active live API probe
    setSteps((prev) =>
      prev.map((s) => ({
        ...s,
        status: 'RUNNING',
        detail: 'Executing network probe...',
      }))
    );

    const startTime = performance.now();

    try {
      // Execute genuine backend 8-step verification pipeline
      const res: AssetVerifyResponse = await api.verifyAsset(asset.id, 'ADMIN_OVERRIDE');
      const elapsed = Math.round(performance.now() - startTime);
      setLastDurationMs(elapsed);

      // Map backend step results to canonical steps
      const backendStepMap = new Map<number, VerificationStepResult>();
      if (Array.isArray(res.steps)) {
        for (const s of res.steps) {
          backendStepMap.set(s.step, s);
        }
      }

      const updatedSteps: VerificationStepState[] = CANONICAL_STEPS.map((def) => {
        const backendStep = backendStepMap.get(def.id);
        if (backendStep) {
          const metaLatency =
            backendStep.metadata?.latency_ms ??
            backendStep.metadata?.total_duration_ms;

          return {
            ...def,
            status: (backendStep.status as 'PASS' | 'FAIL' | 'INFO') || 'PASS',
            latencyMs: typeof metaLatency === 'number' ? Math.round(metaLatency) : undefined,
            detail: backendStep.detail || def.defaultDesc,
            metadata: backendStep.metadata || {},
          };
        }

        // If step wasn't reached (e.g. earlier pipeline abort on invalid DNS or SSRF)
        const isPipelineFailed = res.status === 'FAILED' || !res.verified;
        return {
          ...def,
          status: isPipelineFailed ? 'SKIPPED' : 'PENDING',
          detail: isPipelineFailed
            ? 'Aborted due to prior probe failure'
            : def.defaultDesc,
          metadata: {},
        };
      });

      setSteps(updatedSteps);

      // Set target perimeter fingerprint from response
      if (res.fingerprint && Object.keys(res.fingerprint).length > 0) {
        setFingerprint(res.fingerprint);
      } else {
        setFingerprint(null);
      }

      // Genuine status determination without fake fallback
      const isSuccess = res.status === 'VERIFIED' && res.verified !== false;
      if (isSuccess) {
        setOverallStatus('VERIFIED');
        if (onVerified) {
          onVerified(asset.id);
        }
      } else {
        setOverallStatus('FAILED');
        setErrorMessage(res.message || 'Target verification failed one or more critical security checks.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('Target verification probe failed:', err);
      setOverallStatus('FAILED');
      setErrorMessage(msg || 'Target verification network probe encountered an error.');
      setSteps((prev) =>
        prev.map((s) => ({
          ...s,
          status: s.status === 'RUNNING' ? 'FAIL' : s.status,
          detail: s.status === 'RUNNING' ? (msg || 'Probe failed') : s.detail,
        }))
      );
    } finally {
      setIsRunning(false);
    }
  };

  if (!isOpen || !asset) return null;

  const passedCount = steps.filter((s) => s.status === 'PASS').length;
  const progressPercent = Math.round((passedCount / steps.length) * 100);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="w-full max-w-3xl rounded-2xl liquid-glass-modal p-6 shadow-2xl relative flex flex-col max-h-[90vh] overflow-hidden text-slate-100">
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-cyan-500/5 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-md">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-base font-black tracking-tight text-white flex items-center gap-2">
                <span>{t('verify.modalTitle', '8-Step Live Target Verification Pipeline')}</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">
                {asset.name} &bull; <span className="text-cyan-400">{asset.target_locator}</span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress & Target Summary Ribbon */}
        <div className="my-4 p-3.5 rounded-xl bg-white/[0.02] border border-white/10 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <div className="text-xs">
              <span className="text-slate-400">{t('common.status', 'Status')}: </span>
              <span
                className={`font-mono font-bold px-2 py-0.5 rounded text-[10px] uppercase ${
                  overallStatus === 'VERIFIED'
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
                    : overallStatus === 'FAILED'
                    ? 'bg-rose-950/80 text-rose-300 border border-rose-800'
                    : overallStatus === 'RUNNING'
                    ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-800 animate-pulse'
                    : 'bg-white/[0.05] text-slate-300 border border-white/10'
                }`}
              >
                {overallStatus === 'VERIFIED'
                  ? t('common.verified', 'VERIFIED')
                  : overallStatus === 'FAILED'
                  ? t('common.failed', 'FAILED')
                  : overallStatus === 'RUNNING'
                  ? t('verify.probing', 'PROBING...')
                  : t('common.pending', 'PENDING')}
              </span>
            </div>
            <div className="text-xs text-slate-400">
              Pass Rate: <strong className="text-white font-mono">{passedCount}/8</strong> steps
              {lastDurationMs !== null && (
                <span className="ml-2 text-cyan-400 font-mono text-[11px]">
                  ({lastDurationMs}ms)
                </span>
              )}
            </div>
          </div>

          {/* Progress bar */}
          <div className="w-full sm:w-64 h-2 rounded-full bg-cyber-950 overflow-hidden border border-white/10">
            <div
              className={`h-full transition-all duration-300 rounded-full ${
                overallStatus === 'FAILED'
                  ? 'bg-gradient-to-r from-rose-500 to-amber-500'
                  : 'bg-gradient-to-r from-cyan-500 to-emerald-400'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Real Error Message Banner (Honest Failure Reporting) */}
        {errorMessage && (
          <div className="mb-4 p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 flex items-start gap-2.5 text-rose-200 text-xs">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div className="flex-1 font-mono">
              <span className="font-bold text-rose-300">Verification Alert: </span>
              {errorMessage}
            </div>
          </div>
        )}

        {/* Active Probing Banner */}
        {isRunning && (
          <div className="mb-4 p-3 rounded-xl bg-cyan-950/40 border border-cyan-500/30 flex items-center gap-2.5 text-cyan-200 text-xs animate-pulse">
            <RefreshCw className="w-4 h-4 text-cyan-400 shrink-0 animate-spin" />
            <div className="flex-1 font-mono">
              Executing live 8-step security verification probe against backend engine...
            </div>
          </div>
        )}

        {/* 8-Step Verification List & Metadata Accordions */}
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {steps.map((step) => {
            const isExpanded = expandedStep === step.id;

            return (
              <div
                key={step.id}
                className={`rounded-xl border transition-all ${
                  step.status === 'RUNNING'
                    ? 'bg-cyan-950/30 border-cyan-500/50 shadow-md shadow-cyan-950/40'
                    : step.status === 'PASS'
                    ? 'bg-white/[0.02] border-white/10 hover:border-white/20'
                    : step.status === 'FAIL'
                    ? 'bg-rose-950/20 border-rose-500/40'
                    : 'bg-white/[0.01] border-white/5 text-slate-400'
                }`}
              >
                <div
                  onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                  className="p-3 flex items-center justify-between cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-mono font-bold ${
                        step.status === 'PASS'
                          ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/80'
                          : step.status === 'FAIL'
                          ? 'bg-rose-950/80 text-rose-400 border border-rose-800/80'
                          : step.status === 'RUNNING'
                          ? 'bg-cyan-950 text-cyan-400 border border-cyan-700 animate-spin'
                          : 'bg-white/[0.04] text-slate-400 border border-white/10'
                      }`}
                    >
                      {step.status === 'PASS' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : step.status === 'FAIL' ? (
                        <AlertCircle className="w-4 h-4 text-rose-400" />
                      ) : step.status === 'RUNNING' ? (
                        <RefreshCw className="w-3.5 h-3.5" />
                      ) : (
                        step.id
                      )}
                    </div>

                    <div>
                      <div className="font-bold text-xs text-white flex items-center gap-2">
                        <span>{t(step.titleKey, step.defaultTitle)}</span>
                        {step.latencyMs !== undefined && (
                          <span className="text-[10px] font-mono text-cyan-400 font-normal">
                            ({step.latencyMs}ms)
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {step.detail || t(step.descKey, step.defaultDesc)}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase ${
                        step.status === 'PASS'
                          ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                          : step.status === 'FAIL'
                          ? 'bg-rose-950/60 text-rose-400 border-rose-800'
                          : step.status === 'RUNNING'
                          ? 'bg-cyan-950/80 text-cyan-400 border-cyan-800'
                          : step.status === 'SKIPPED'
                          ? 'bg-slate-900 text-slate-500 border-slate-800'
                          : 'bg-white/[0.03] text-slate-500 border-white/5'
                      }`}
                    >
                      {step.status === 'PASS'
                        ? t('verify.pass', 'PASS')
                        : step.status === 'FAIL'
                        ? t('verify.fail', 'FAIL')
                        : step.status === 'RUNNING'
                        ? t('verify.probing', 'PROBING...')
                        : step.status === 'SKIPPED'
                        ? 'SKIPPED'
                        : t('verify.queued', 'QUEUED')}
                    </span>

                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </div>

                {/* Expanded Forensic Metadata */}
                {isExpanded && step.metadata && Object.keys(step.metadata).length > 0 && (
                  <div className="px-4 pb-3 pt-1 border-t border-white/5 bg-black/40">
                    <div className="flex items-center justify-between py-1 text-[10px] font-mono text-slate-400">
                      <span>Diagnostic Evidence</span>
                      <span className="text-cyan-400 font-bold">{step.defaultTitle}</span>
                    </div>
                    <pre className="p-2.5 rounded-lg bg-slate-950 text-[10px] font-mono text-cyan-300 overflow-x-auto border border-white/5">
                      {JSON.stringify(step.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}

          {/* Genuine Perimeter Fingerprint Inspector Panel */}
          {fingerprint && (
            <div className="mt-4 p-4 rounded-xl bg-cyber-950/60 border border-cyan-500/30 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-white/10">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                    {t('verify.fingerprintTitle', 'Target Perimeter Fingerprint')}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowRawFingerprint(!showRawFingerprint)}
                  className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition"
                >
                  <Code2 className="w-3 h-3" />
                  <span>{showRawFingerprint ? 'Hide Raw JSON' : 'View Raw JSON'}</span>
                </button>
              </div>

              {/* Primary Fingerprint Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11px] font-mono">
                <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-slate-400 text-[10px]">WEB SERVER</div>
                  <div className="text-white font-bold mt-0.5 truncate">{fingerprint.server || 'Unknown'}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-slate-400 text-[10px]">WAF / REVERSE PROXY</div>
                  <div className="text-cyan-400 font-bold mt-0.5 truncate">{fingerprint.reverse_proxy_waf || 'None detected'}</div>
                </div>
                <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-slate-400 text-[10px]">FRAMEWORK</div>
                  <div className="text-emerald-400 font-bold mt-0.5 truncate">{fingerprint.framework || 'Generic Web'}</div>
                </div>
              </div>

              {/* Detected Technologies */}
              {Array.isArray(fingerprint.technologies) && fingerprint.technologies.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[10px] font-mono text-slate-400 uppercase">Detected Technologies</div>
                  <div className="flex flex-wrap gap-1.5">
                    {fingerprint.technologies.map((tech: string, i: number) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded-md bg-cyan-950/60 text-cyan-300 border border-cyan-800 text-[10px] font-mono font-medium"
                      >
                        {tech}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Security Headers Posture */}
              {fingerprint.security_headers && typeof fingerprint.security_headers === 'object' && (
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-slate-400 uppercase">Baseline Security Headers</span>
                    <span className="text-cyan-400 font-bold">
                      {fingerprint.active_security_headers_count ?? Object.values(fingerprint.security_headers).filter(Boolean).length}/5 Active
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10px] font-mono">
                    {Object.entries(fingerprint.security_headers).map(([key, val]) => (
                      <div
                        key={key}
                        className={`p-2 rounded border flex items-center justify-between ${
                          val
                            ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                            : 'bg-white/[0.01] border-white/5 text-slate-500'
                        }`}
                      >
                        <span className="truncate">{key.replace(/_/g, '-').toUpperCase()}</span>
                        <span className="font-bold flex items-center gap-1">
                          {val ? (
                            <>
                              <Check className="w-3 h-3 text-emerald-400" />
                              <span>ACTIVE</span>
                            </>
                          ) : (
                            <span>MISSING</span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Raw JSON toggle */}
              {showRawFingerprint && (
                <pre className="p-2.5 rounded-lg bg-black text-[10px] font-mono text-cyan-300 overflow-x-auto border border-white/10 mt-2">
                  {JSON.stringify(fingerprint, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="pt-4 border-t border-white/10 mt-4 flex items-center justify-between">
          <div className="text-xs text-slate-400">
            {overallStatus === 'VERIFIED' && (
              <span className="text-emerald-400 flex items-center gap-1.5 font-semibold">
                <CheckCircle2 className="w-4 h-4" />
                <span>{t('verify.successBadge', '100% PROBE VERIFIED')}</span>
              </span>
            )}
            {overallStatus === 'FAILED' && (
              <span className="text-rose-400 flex items-center gap-1.5 font-semibold">
                <AlertCircle className="w-4 h-4" />
                <span>VERIFICATION FAILED</span>
              </span>
            )}
            {overallStatus === 'RUNNING' && (
              <span className="text-cyan-400 flex items-center gap-1.5 font-semibold animate-pulse">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Executing live probe...</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white text-xs font-semibold border border-white/10 transition"
            >
              {t('common.close', 'Close')}
            </button>

            <button
              type="button"
              onClick={runVerificationPipeline}
              disabled={isRunning}
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold text-xs shadow-lg shadow-cyan-950/60 disabled:opacity-50 transition flex items-center gap-1.5"
            >
              <Play className={`w-3.5 h-3.5 fill-slate-950 ${isRunning ? 'animate-spin' : ''}`} />
              <span>
                {isRunning
                  ? t('verify.executing', 'Executing probe...')
                  : overallStatus === 'VERIFIED'
                  ? t('verify.reverifyButton', 'Re-run Verification')
                  : t('verify.executeButton', 'Execute 8-Step Verification')}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

## 5. Drawer Tabs Dynamic Contextual Refactoring (`frontend/src/app/assets/page.tsx`)

In `frontend/src/app/assets/page.tsx`, Reviewer 2 noted that Drawer Tab 2 (DNS & TLS) and Tab 3 (Endpoints) contained static hardcoded strings for any selected asset.

### 5.1 Tab 2 (DNS & TLS) Dynamic Proposal
Replace hardcoded values with values derived from `selectedAssetForDrawer`:
- Parse hostname with `try { new URL(selectedAssetForDrawer.target_locator).hostname } catch { ... }`.
- Display real asset technology and verification status.
- Add an action button: **"Run / View Live 8-Step Probe"** that opens `TargetVerificationModal` with `selectedAssetForDrawer`.
- When asset is `VERIFIED`, show verification timestamp (`selectedAssetForDrawer.verified_at`) and verification type (`selectedAssetForDrawer.verification_type`).

### 5.2 Tab 3 (Endpoints) Dynamic Proposal
Replace static rows with endpoints derived from `selectedAssetForDrawer`:
- Display root locator: `selectedAssetForDrawer.target_locator`.
- Display any explicitly configured excluded endpoints from `selectedAssetForDrawer.excluded_endpoints`.
- For Empire modules, list canonical module endpoints based on `selectedAssetForDrawer.empire_module` (e.g. `/`, `/media`, `/api/v1/auth`, `/student-management`).

---

## 6. Verification & Quality Gates

The implementer must verify the refactoring with these exact commands:

1. **ESLint Verification**:
   ```bash
   cd frontend
   npm run lint
   ```
   **Acceptance**: Exits with code 0 and ZERO warnings (the `react-hooks/exhaustive-deps` warning on `initialSteps` is completely resolved).

2. **TypeScript & Static Build**:
   ```bash
   cd frontend
   npm run build
   ```
   **Acceptance**: Exits with code 0 across all 18 static routes.

3. **Backend & E2E Verification**:
   ```bash
   python scripts/verify_empire_e2e.py
   ```
   **Acceptance**: All 10 capability tests complete successfully with code 0.

4. **Interactive Verification**:
   - Open `/assets` in browser.
   - Click "Verify" or "Re-Verify" on an asset.
   - Click "Execute 8-Step Verification".
   - Confirm real probe execution without delays.
   - Confirm live fingerprint (Envoy, Next.js, React, 5/5 security headers) appears in Fingerprint Inspector.
   - Confirm no mock strings (`103.142.26.18`) appear.
