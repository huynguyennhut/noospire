'use client';

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Crosshair,
  Play,
  Clock,
  Radio,
  ShieldCheck,
  Cpu,
  Server,
  Zap,
  AlertCircle,
  ExternalLink,
  Layers,
  Sliders,
  Check,
  Sparkles,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Asset, ScanJob, BatchScanResponse } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { useToast } from '@/components/ui/toast';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import TargetVerificationModal from '@/components/verification/TargetVerificationModal';

interface ScanProfileConfig {
  key: string;
  title: string;
  tagline: string;
  description: string;
  engines: string[];
  engineIcons: ('nuclei' | 'zap' | 'empire')[];
  riskLevel: 'ZERO' | 'LOW' | 'CONTROLLED' | 'COMPREHENSIVE';
  estimatedDuration: string;
  keyChecks: string[];
}

const SCAN_PROFILES: ScanProfileConfig[] = [
  {
    key: 'BASELINE',
    title: 'Baseline Discovery',
    tagline: 'Fast Non-Destructive Passive Reconnaissance',
    description: 'Rapid baseline verification, HTTP header security posture, SSL/TLS parameter validation, and robots/sitemaps discovery.',
    engines: ['Nuclei (Fast)', 'Empire Engine'],
    engineIcons: ['nuclei', 'empire'],
    riskLevel: 'ZERO',
    estimatedDuration: '< 30s',
    keyChecks: ['DNS/TLS Baseline', 'Server Headers', 'Basic Exposure', 'Robots & Sitemaps'],
  },
  {
    key: 'DEEP_ACTIVE',
    title: 'Deep Active Assessment',
    tagline: 'Comprehensive Active Exploit & Injection Probes',
    description: 'Thorough vulnerability testing against SQLi, SSRF, XSS, RCE, and authorization flaws. Strictly gated for verified targets.',
    engines: ['Nuclei (Active)', 'OWASP ZAP', 'Empire Engine'],
    engineIcons: ['nuclei', 'zap', 'empire'],
    riskLevel: 'CONTROLLED',
    estimatedDuration: '10 - 25 min',
    keyChecks: ['SQLi / Command Injection', 'SSRF Validation', 'Active Payload Fuzzing', 'CORS & Auth Bypass'],
  },
  {
    key: 'DAILY_SECURITY',
    title: 'Empire Business Logic',
    tagline: 'Tailored Empire Education Platform Audit',
    description: 'Specialized business logic assessment across Student Management, Learning Materials (/media policy), and Better-Auth routes.',
    engines: ['Empire Custom Engine', 'Nuclei'],
    engineIcons: ['empire', 'nuclei'],
    riskLevel: 'LOW',
    estimatedDuration: '2 - 5 min',
    keyChecks: ['Student Auth Exposure', 'Public /media Baseline', 'BOLA / IDOR Student Records', 'CISA KEV Correlation'],
  },
  {
    key: 'STANDARD',
    title: 'OWASP Top 10 Web',
    tagline: 'Standard Industry Web Application Audit',
    description: 'Balanced vulnerability assessment combining OWASP ZAP baseline rules and Nuclei core application security templates.',
    engines: ['OWASP ZAP', 'Nuclei'],
    engineIcons: ['zap', 'nuclei'],
    riskLevel: 'LOW',
    estimatedDuration: '5 - 10 min',
    keyChecks: ['Broken Access Control', 'Cryptographic Failures', 'Security Misconfiguration', 'Vulnerable Components'],
  },
  {
    key: 'INFRASTRUCTURE',
    title: 'Network & Port Audit',
    tagline: 'Perimeter Network & Service Exposure Inspection',
    description: 'Assesses externally observable ports, TLS ciphers, MinIO object storage permissions, and reverse proxy / WAF setups.',
    engines: ['Nuclei Network', 'Empire Infra'],
    engineIcons: ['nuclei', 'empire'],
    riskLevel: 'LOW',
    estimatedDuration: '3 - 8 min',
    keyChecks: ['Public Port Exposure', 'MinIO Bucket ACLs', 'Weak TLS Ciphers', 'Reverse Proxy Leakage'],
  },
  {
    key: 'LIGHT_PASSIVE',
    title: 'Stealth Passive Recon',
    tagline: 'Zero-Impact OSINT & Attack Surface Profiling',
    description: 'Completely passive observation with zero active payload dispatch, ensuring no traffic alerts or rate-limiting tripwires.',
    engines: ['Empire Passive Recon'],
    engineIcons: ['empire'],
    riskLevel: 'ZERO',
    estimatedDuration: '< 45s',
    keyChecks: ['OSINT Subdomains', 'Certificate Transparency', 'Technology Fingerprinting', 'DNS History'],
  },
  {
    key: 'AUTHENTICATED',
    title: 'Continuous Compliance',
    tagline: 'Scheduled Governance & Configuration Drift Tracking',
    description: 'Validates persistent security posture, student credential safety, approved public media baselines, and CVE remediation integrity.',
    engines: ['Empire Compliance', 'Nuclei'],
    engineIcons: ['empire', 'nuclei'],
    riskLevel: 'ZERO',
    estimatedDuration: '1 - 3 min',
    keyChecks: ['Media Policy Drift', 'Authentication Guards', 'CVE Remediation Retest', 'Audit Trail Recording'],
  },
];

export default function ScansPage() {
  const { t } = useI18n();

  // Core Data State
  const [scans, setScans] = useState<ScanJob[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [, setLoading] = useState(true);

  // Form Configuration State
  const [selectedAssetId, setSelectedAssetId] = useState('');
  const [selectedProfile, setSelectedProfile] = useState('DAILY_SECURITY');
  const [engineNuclei, setEngineNuclei] = useState(true);
  const [engineZap, setEngineZap] = useState(true);
  const [engineEmpire, setEngineEmpire] = useState(true);
  const [customDescription, setCustomDescription] = useState('');
  const [allowPrivate, setAllowPrivate] = useState(true);
  const [timeoutSeconds, setTimeoutSeconds] = useState(600);
  const [dispatching, setDispatching] = useState(false);

  // Verification Prompt Modal
  const [verifyModalAsset, setVerifyModalAsset] = useState<Asset | null>(null);

  // Batch "Scan All" State
  const router = useRouter();
  const { toast } = useToast();
  const [batchConcurrency, setBatchConcurrency] = useState(2);
  const [batchEngines, setBatchEngines] = useState<string[]>(['all']);
  const [batchProfiles, setBatchProfiles] = useState<string[]>(['DAILY_SECURITY']);
  const [batchLaunching, setBatchLaunching] = useState(false);
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [lastBatchResult, setLastBatchResult] = useState<BatchScanResponse | null>(null);

  const toggleBatchEngine = (engine: string) => {
    if (engine === 'all') {
      setBatchEngines(['all']);
      return;
    }
    setBatchEngines((prev) => {
      const withoutAll = prev.filter((e) => e !== 'all');
      if (withoutAll.includes(engine)) {
        const next = withoutAll.filter((e) => e !== engine);
        return next.length === 0 ? ['all'] : next;
      } else {
        return [...withoutAll, engine];
      }
    });
  };

  const toggleBatchProfile = (profileKey: string) => {
    setBatchProfiles((prev) => {
      if (prev.includes(profileKey)) {
        if (prev.length === 1) return prev;
        return prev.filter((p) => p !== profileKey);
      } else {
        return [...prev, profileKey];
      }
    });
  };

  const handleLaunchBatchScan = async () => {
    try {
      setBatchLaunching(true);
      const enginesToSend = batchEngines.includes('all') ? ['all'] : batchEngines;
      const res = await api.createBatchScan({
        targets: 'ALL',
        profiles: batchProfiles.length > 0 ? batchProfiles : ['DAILY_SECURITY'],
        engines: enginesToSend.length > 0 ? enginesToSend : ['all'],
        concurrency_limit: batchConcurrency,
        name: `Full Ecosystem Sweep (${new Date().toLocaleDateString()})`,
      });
      setLastBatchResult(res);
      toast({
        title: 'Batch Scan Dispatched',
        description: `Dispatched ${res.total_scans} scan jobs across ${res.target_count} targets with concurrency ${batchConcurrency}.`,
        variant: 'success',
        duration: 6000,
      });
      fetchData();
    } catch (err: unknown) {
      toast({
        title: 'Batch Scan Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
        duration: 6000,
      });
    } finally {
      setBatchLaunching(false);
    }
  };

  const handleRunUltraScan = async () => {
    try {
      setBatchLaunching(true);
      const idempotencyKey = `ultra-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const res = await api.launchUltraScan({
        scope: 'ALL',
        idempotency_key: idempotencyKey,
        initiator: 'scans_page_owner_action',
      });
      toast({
        title: 'Ultra Scan Dispatched',
        description: `Batch ${res.batch_id} initiated across ${res.independent_execution_targets} targets (${res.engine_executions_count} engine executions).`,
        variant: 'success',
        duration: 5000,
      });
      router.push(res.tracker_link);
    } catch (err: unknown) {
      toast({
        title: 'Ultra Scan Launch Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
        duration: 6000,
      });
    } finally {
      setBatchLaunching(false);
    }
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [scansRes, assetsRes] = await Promise.all([
        api.listScans().catch(() => ({ items: [], total: 0 })),
        api.listAssets().catch(() => ({ items: [], total: 0 })),
      ]);
      setScans(scansRes.items || []);
      const assetItems = assetsRes.items || [];
      setAssets(assetItems);
      if (assetItems.length > 0) {
        setSelectedAssetId((prev) => prev || assetItems[0].id);
      }
    } catch (err) {
      console.error('Failed to load scan center data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const selectedTarget = assets.find((a) => a.id === selectedAssetId);
  const selectedProfileObj = SCAN_PROFILES.find((p) => p.key === selectedProfile) || SCAN_PROFILES[2];

  // Resolve engine selection string
  const getSelectedEngineParam = () => {
    const activeCount = [engineNuclei, engineZap, engineEmpire].filter(Boolean).length;
    if (activeCount === 3 || activeCount === 0) return 'all';
    if (engineNuclei && !engineZap && !engineEmpire) return 'nuclei';
    if (!engineNuclei && engineZap && !engineEmpire) return 'zap';
    if (!engineNuclei && !engineZap && engineEmpire) return 'empire';
    return 'all';
  };

  // Dispatch Assessment Handler
  const handleLaunchScan = async () => {
    if (!selectedAssetId) return;

    // Security Gate: Check DEEP_ACTIVE requirements
    if (selectedProfile === 'DEEP_ACTIVE' && selectedTarget && selectedTarget.verification_status !== 'VERIFIED') {
      alert('Active scanning (DEEP_ACTIVE) is prohibited on unverified targets. Please verify asset ownership first.');
      setVerifyModalAsset(selectedTarget);
      return;
    }

    try {
      setDispatching(true);
      const scan = await api.dispatchScan({
        asset_id: selectedAssetId,
        engine: getSelectedEngineParam(),
        profile: selectedProfile,
        allow_private_targets: allowPrivate,
        timeout_seconds: timeoutSeconds,
      });

      // Redirect immediately to live tracker
      window.location.href = `/active-assessments?scan_id=${scan.id}`;
    } catch (err: unknown) {
      alert(`Assessment dispatch failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setDispatching(false);
    }
  };

  const getRiskBadge = (level: ScanProfileConfig['riskLevel']) => {
    switch (level) {
      case 'ZERO':
        return <Badge severity="low" size="sm">Zero Impact (Passive)</Badge>;
      case 'LOW':
        return <Badge severity="info" size="sm">Production Safe</Badge>;
      case 'CONTROLLED':
        return <Badge severity="high" size="sm">Controlled Active</Badge>;
      case 'COMPREHENSIVE':
        return <Badge severity="critical" size="sm">Comprehensive</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Crosshair className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('scans.title', 'SCAN DISPATCH CENTER')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('scans.subtitle', 'Orchestrate real ProjectDiscovery Nuclei, OWASP ZAP, and custom Empire business logic security engines.')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/active-assessments"
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 text-xs font-semibold text-slate-300 hover:text-white transition shadow-sm"
          >
            <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span>Live Telemetry Tracker</span>
          </Link>
          <Button
            variant="glass"
            size="md"
            onClick={handleRunUltraScan}
            disabled={batchLaunching}
            className="border-cyan-500/40 text-cyan-300 hover:bg-cyan-950/40 hover:text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
            icon={<Zap className={`w-3.5 h-3.5 text-cyan-400 ${batchLaunching ? 'animate-pulse' : ''}`} />}
          >
            <span>{batchLaunching ? 'Launching Ultra Scan...' : 'Run Ultra Scan'}</span>
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Play className="w-3.5 h-3.5 text-slate-950 fill-current" />}
            loading={dispatching}
            onClick={handleLaunchScan}
          >
            Launch Assessment Now
          </Button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* "SCAN ALL" HERO CARD / BATCH DISPATCH CONTROLS                      */}
      {/* =================================================================== */}
      <div className="relative rounded-2xl backdrop-blur-xl bg-black/60 border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden transition-all duration-300">
        {/* Specular shine top border */}
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent pointer-events-none" />

        <div className="p-5 md:p-6 space-y-5">
          {/* Hero Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-white/[0.06] border border-white/10 text-white shadow-[0_0_15px_rgba(255,255,255,0.1)]">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                </span>
                <h2 className="text-base md:text-lg font-black tracking-tight text-white uppercase">
                  Scan All Targets — Full-Spectrum Batch Orchestration
                </h2>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Automated multi-worker sweep across all registered targets, engines, and profiles with CPU/RAM optimization.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-mono font-bold flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5 text-cyan-400" />
                <span>{assets.length} Registered Targets</span>
              </div>
              <div className="px-3 py-1 rounded-full bg-white/[0.04] border border-white/10 text-slate-300 text-xs font-mono font-bold flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-slate-400" />
                <span>Throttle: {batchConcurrency}x</span>
              </div>
            </div>
          </div>

          {/* Configuration Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 pt-4 border-t border-white/10">
            {/* 1. Concurrency Throttle Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <label className="text-slate-200 font-bold">
                  Worker Concurrency Throttle
                </label>
                <span className="font-mono text-cyan-400 font-extrabold text-sm">
                  {batchConcurrency} Workers
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="4"
                step="1"
                value={batchConcurrency}
                onChange={(e) => setBatchConcurrency(Number(e.target.value))}
                className="w-full accent-cyan-400 cursor-pointer"
                title="Throttle max parallel worker processes"
              />
              <div className="flex justify-between text-[10px] text-slate-400 font-mono">
                <span>1 (Conserve CPU)</span>
                <span>2 (Recommended)</span>
                <span>4 (Max Safe)</span>
              </div>
              <p className="text-[10px] text-slate-400 leading-tight">
                Throttles concurrent background scan jobs to protect CPU and memory from load spikes.
              </p>
            </div>

            {/* 2. Engine Selectors */}
            <div className="space-y-2">
              <label className="text-slate-200 font-bold text-xs block">
                Scanning Engines
              </label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { id: 'all', label: 'All Engines' },
                  { id: 'nuclei', label: 'Nuclei' },
                  { id: 'zap', label: 'OWASP ZAP' },
                  { id: 'trivy', label: 'Trivy' },
                ].map((engine) => {
                  const isChecked = batchEngines.includes(engine.id);
                  return (
                    <button
                      key={engine.id}
                      type="button"
                      onClick={() => toggleBatchEngine(engine.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition border cursor-pointer flex items-center gap-1 ${
                        isChecked
                          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-sm'
                          : 'bg-white/[0.03] text-slate-400 border-white/10 hover:text-white hover:bg-white/[0.06]'
                      }`}
                    >
                      {isChecked && <Check className="w-3 h-3 text-cyan-400" />}
                      <span>{engine.label}</span>
                    </button>
                  );
                })}
              </div>
              <p className="text-[10px] text-slate-400 leading-tight">
                Combines active heuristic probes, vulnerability templates, and container audits.
              </p>
            </div>

            {/* 3. Assessment Profile Selectors */}
            <div className="space-y-2">
              <label className="text-slate-200 font-bold text-xs block">
                Assessment Profiles
              </label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  'BASELINE',
                  'DEEP_ACTIVE',
                  'DAILY_SECURITY',
                  'STANDARD',
                  'INFRASTRUCTURE',
                  'LIGHT_PASSIVE',
                  'AUTHENTICATED',
                ].map((pKey) => {
                  const isSelected = batchProfiles.includes(pKey);
                  return (
                    <button
                      key={pKey}
                      type="button"
                      onClick={() => toggleBatchProfile(pKey)}
                      className={`px-2 py-1 rounded-lg text-[11px] font-mono font-bold transition border cursor-pointer flex items-center gap-1 ${
                        isSelected
                          ? 'bg-white text-black border-white shadow-sm'
                          : 'bg-white/[0.03] text-slate-400 border-white/10 hover:text-white hover:bg-white/[0.06]'
                      }`}
                    >
                      {isSelected && <Check className="w-3 h-3 text-black" />}
                      <span>{pKey}</span>
                    </button>
                  );
                })}
              </div>
              <p className="text-[10px] text-slate-400 leading-tight">
                Profiles determine test coverage, payload aggressiveness, and compliance depth.
              </p>
            </div>
          </div>

          {/* Security Gate Warning for DEEP_ACTIVE */}
          {batchProfiles.includes('DEEP_ACTIVE') && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed">
                <span className="font-bold">Security Gate Notice:</span> DEEP_ACTIVE is selected.
                Unverified assets in the batch will be automatically downgraded or gated to AUTH_REQUIRED per platform policy to prevent unauthorized testing.
              </div>
            </div>
          )}

          {/* Action Row & Feedback */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-white/10">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleLaunchBatchScan}
                disabled={batchLaunching}
                className="bg-white text-black hover:bg-neutral-200 shadow-[0_0_20px_rgba(255,255,255,0.2)] font-black text-xs px-5 py-2.5 rounded-xl transition duration-200 flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:pointer-events-none"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{batchLaunching ? 'Dispatching Batch...' : 'Launch Full Sweep'}</span>
              </button>

              <button
                type="button"
                onClick={handleRunUltraScan}
                disabled={batchLaunching}
                className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.2)] font-black text-xs px-5 py-2.5 rounded-xl transition duration-200 flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:pointer-events-none"
              >
                <Zap className="w-3.5 h-3.5 text-cyan-400 fill-current" />
                <span>Run Ultra Scan (Estate-Wide)</span>
              </button>

              <button
                type="button"
                onClick={() => setBatchModalOpen(true)}
                className="px-3.5 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition cursor-pointer"
              >
                Inspect Batch Matrix ({assets.length * batchProfiles.length} scan jobs)
              </button>
            </div>

            <Link
              href="/active-assessments"
              className="text-xs text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1.5 transition"
            >
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              <span>Track Worker Thread Matrix (&quot;trackcurrent&quot;) →</span>
            </Link>
          </div>

          {/* Success Banner if lastBatchResult */}
          {lastBatchResult && (
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3">
              <div>
                <span className="font-bold">Batch Dispatched:</span>{' '}
                <span className="font-mono">{lastBatchResult.batch_id}</span> •{' '}
                <span>{lastBatchResult.total_scans} scans across {lastBatchResult.target_count} targets</span>
              </div>
              <Link
                href="/active-assessments"
                className="px-3 py-1 rounded-lg bg-emerald-500 text-slate-950 font-bold hover:bg-emerald-400 transition shrink-0"
              >
                View Live Telemetry →
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Batch Matrix Modal */}
      {batchModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in"
          role="dialog"
          aria-modal="true"
        >
          <div className="relative w-full max-w-2xl rounded-2xl backdrop-blur-2xl bg-cyber-900/95 border border-white/15 p-6 shadow-2xl space-y-4 text-white">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-cyan-400" />
                <h3 className="font-bold text-sm">Batch Execution Plan Matrix</h3>
              </div>
              <button
                type="button"
                onClick={() => setBatchModalOpen(false)}
                className="text-slate-400 hover:text-white text-xs px-2 py-1 rounded-lg bg-white/[0.04]"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-3 gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/5 font-mono">
                <div>Total Targets: <strong className="text-white">{assets.length}</strong></div>
                <div>Profiles: <strong className="text-white">{batchProfiles.length}</strong></div>
                <div>Calculated Jobs: <strong className="text-cyan-400">{assets.length * batchProfiles.length}</strong></div>
              </div>

              <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1 font-mono text-[11px]">
                {assets.map((a, i) => (
                  <div key={a.id} className="p-2 rounded-lg bg-white/[0.02] border border-white/5 flex items-center justify-between">
                    <span className="truncate max-w-[280px]">#{i + 1} {a.name} ({a.target_locator})</span>
                    <Badge severity={a.verification_status === 'VERIFIED' ? 'low' : 'medium'} size="sm">
                      {a.verification_status}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-white/10">
              <button
                type="button"
                onClick={() => setBatchModalOpen(false)}
                className="px-4 py-2 rounded-xl bg-white/[0.04] text-slate-300 text-xs font-semibold cursor-pointer"
              >
                Back to Controls
              </button>
              <button
                type="button"
                onClick={() => {
                  setBatchModalOpen(false);
                  handleLaunchBatchScan();
                }}
                disabled={batchLaunching}
                className="bg-white text-black hover:bg-neutral-200 font-bold text-xs px-5 py-2 rounded-xl shadow-lg cursor-pointer"
              >
                Confirm & Launch Sweep
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Target & Dispatch Configuration Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Target Selector & Parameters */}
        <div className="lg:col-span-1 space-y-4">
          <Card glow="cyan">
            <CardHeader>
              <CardTitle>
                <Server className="w-4 h-4 text-cyan-400" />
                <span>Target Selection & Policy</span>
              </CardTitle>
              <CardDescription>
                Select the target asset and verify authorization credentials before launching.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              {/* Target Selector Dropdown */}
              <div className="space-y-1.5">
                <label className="text-slate-300 font-bold">Target Asset *</label>
                <select
                  value={selectedAssetId}
                  onChange={(e) => setSelectedAssetId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
                >
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.target_locator})
                    </option>
                  ))}
                </select>
              </div>

              {/* Selected Target Preview Card */}
              {selectedTarget && (
                <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/10 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white text-xs">{selectedTarget.name}</span>
                    <Badge
                      severity={selectedTarget.verification_status === 'VERIFIED' ? 'low' : 'medium'}
                      size="sm"
                    >
                      {selectedTarget.verification_status}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-cyan-400 font-mono">{selectedTarget.target_locator}</div>
                  <div className="grid grid-cols-2 gap-1 text-[10px] text-slate-400 pt-1 border-t border-white/5">
                    <div>Module: <strong className="text-slate-200">{selectedTarget.empire_module}</strong></div>
                    <div>Env: <strong className="text-slate-200">{selectedTarget.environment}</strong></div>
                  </div>

                  {/* Warning if unverified & active scan */}
                  {selectedProfile === 'DEEP_ACTIVE' && selectedTarget.verification_status !== 'VERIFIED' && (
                    <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] space-y-1 mt-2">
                      <div className="font-bold flex items-center gap-1">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>Verification Required for Active Scan</span>
                      </div>
                      <p>Active exploits require proof of ownership. Click below to verify now:</p>
                      <button
                        onClick={() => setVerifyModalAsset(selectedTarget)}
                        className="text-cyan-400 font-bold underline hover:text-cyan-300"
                      >
                        Launch 8-Step Verification Pipeline →
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Scanner Engine Toggles */}
              <div className="space-y-2 pt-2 border-t border-white/10">
                <label className="text-slate-300 font-bold">Enabled Scanner Engines</label>
                <div className="space-y-2">
                  <label className="flex items-center justify-between p-2 rounded-xl bg-cyber-950 border border-white/5 cursor-pointer hover:border-white/15 transition">
                    <div className="flex items-center gap-2">
                      <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                      <div>
                        <div className="font-bold text-white text-xs">Nuclei CLI (v3.11.1)</div>
                        <div className="text-[10px] text-slate-400">Template-driven fast vulnerability scanner</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={engineNuclei}
                      onChange={(e) => setEngineNuclei(e.target.checked)}
                      className="w-4 h-4 rounded text-cyan-500 bg-cyber-950 border-white/20"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-xl bg-cyber-950 border border-white/5 cursor-pointer hover:border-white/15 transition">
                    <div className="flex items-center gap-2">
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      <div>
                        <div className="font-bold text-white text-xs">OWASP ZAP Core</div>
                        <div className="text-[10px] text-slate-400">Automated spider & active web application proxy</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={engineZap}
                      onChange={(e) => setEngineZap(e.target.checked)}
                      className="w-4 h-4 rounded text-amber-500 bg-cyber-950 border-white/20"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-xl bg-cyber-950 border border-white/5 cursor-pointer hover:border-white/15 transition">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                      <div>
                        <div className="font-bold text-white text-xs">Empire Custom Engine</div>
                        <div className="text-[10px] text-slate-400">Empire business logic & student auth module</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={engineEmpire}
                      onChange={(e) => setEngineEmpire(e.target.checked)}
                      className="w-4 h-4 rounded text-purple-500 bg-cyber-950 border-white/20"
                    />
                  </label>
                </div>
              </div>

              {/* Advanced Parameters */}
              <div className="space-y-3 pt-2 border-t border-white/10">
                <div className="space-y-1">
                  <label className="text-slate-300 font-bold">Audit Description (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Pre-release sprint assessment"
                    value={customDescription}
                    onChange={(e) => setCustomDescription(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-xl bg-cyber-950 border border-white/10 text-white text-xs focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-white font-bold">Allow Private / Lab Targets</div>
                    <div className="text-[10px] text-slate-400">Permits RFC1918 loopback / local IP scan dispatch</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={allowPrivate}
                    onChange={(e) => setAllowPrivate(e.target.checked)}
                    className="w-4 h-4 rounded text-cyan-500 bg-cyber-950 border-white/20"
                  />
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-slate-400 text-[10px]">
                    <span>Execution Timeout:</span>
                    <span className="text-cyan-400 font-mono font-bold">{Math.round(timeoutSeconds / 60)} minutes</span>
                  </div>
                  <input
                    type="range"
                    min="60"
                    max="1800"
                    step="60"
                    value={timeoutSeconds}
                    onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
                    className="w-full accent-cyan-400"
                  />
                </div>
              </div>

              <Button
                variant="primary"
                size="lg"
                className="w-full mt-4"
                icon={<Play className="w-4 h-4 fill-current" />}
                loading={dispatching}
                onClick={handleLaunchScan}
              >
                Dispatch Security Assessment
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: 7 Scan Profile Cards */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                Select Assessment Profile (7 Standard Suites)
              </h2>
              <p className="text-xs text-slate-400">
                Each profile optimizes scanner depth, rate-limiting, and test coverage for specific operational needs.
              </p>
            </div>
            <Badge severity="status" size="sm">
              Selected: {selectedProfileObj.title}
            </Badge>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {SCAN_PROFILES.map((profile) => {
              const isSelected = selectedProfile === profile.key;

              return (
                <div
                  key={profile.key}
                  onClick={() => setSelectedProfile(profile.key)}
                  className={`p-4 rounded-2xl cursor-pointer transition-all duration-200 border relative ${
                    isSelected
                      ? 'liquid-glass border-cyan-400 shadow-lg shadow-cyan-950/70 scale-[1.01]'
                      : 'liquid-glass-card hover:border-white/20'
                  }`}
                >
                  {/* Top Bar: Title & Risk Badge */}
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-black text-white text-sm flex items-center gap-1.5">
                        <span>{profile.title}</span>
                      </h3>
                      <div className="text-[10px] text-cyan-400/90 font-medium mt-0.5">{profile.tagline}</div>
                    </div>
                    {getRiskBadge(profile.riskLevel)}
                  </div>

                  <p className="text-xs text-slate-300 mt-2.5 leading-relaxed line-clamp-2">
                    {profile.description}
                  </p>

                  {/* Engine Badges & Estimated Duration */}
                  <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1 text-slate-400">
                      <Cpu className="w-3 h-3 text-slate-500" />
                      <span>{profile.engines.join(' + ')}</span>
                    </div>
                    <div className="text-slate-400 font-mono flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      <span>{profile.estimatedDuration}</span>
                    </div>
                  </div>

                  {/* Key Checks Pills */}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {profile.keyChecks.slice(0, 3).map((check) => (
                      <span
                        key={check}
                        className="px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/5 text-[9px] font-mono"
                      >
                        ✓ {check}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recent Scans Table */}
      <div className="space-y-3 pt-4 border-t border-white/10">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider">
            {t('scans.scanHistory', 'Recent Scan Dispatch History')}
          </h2>
          <Link href="/active-assessments" className="text-xs text-cyan-400 hover:underline">
            View Live Tracker Queue →
          </Link>
        </div>

        <div className="rounded-2xl liquid-glass-card overflow-hidden border border-white/10">
          <table className="w-full text-left text-xs">
            <thead className="bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10">
              <tr>
                <th className="py-3 px-4">Target Locator</th>
                <th className="py-3 px-3">Profile</th>
                <th className="py-3 px-3">Engine</th>
                <th className="py-3 px-3 text-center">Status</th>
                <th className="py-3 px-3">Progress</th>
                <th className="py-3 px-3">Started At</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {scans.slice(0, 6).map((scan) => (
                <tr key={scan.id} className="hover:bg-white/[0.02] transition">
                  <td className="py-3 px-4 font-mono text-white text-xs font-bold truncate max-w-xs">
                    {scan.target_locator}
                  </td>
                  <td className="py-3 px-3 text-slate-300 font-semibold">{scan.profile}</td>
                  <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">{scan.engine}</td>
                  <td className="py-3 px-3 text-center">
                    <Badge
                      severity={
                        scan.status === 'COMPLETED'
                          ? 'low'
                          : scan.status === 'RUNNING'
                          ? 'info'
                          : scan.status === 'FAILED'
                          ? 'critical'
                          : 'neutral'
                      }
                      size="sm"
                      dot={scan.status === 'RUNNING'}
                    >
                      {scan.status}
                    </Badge>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 rounded-full bg-cyber-950 overflow-hidden border border-white/5">
                        <div
                          className={`h-full rounded-full ${
                            scan.status === 'COMPLETED' ? 'bg-emerald-400' : 'bg-cyan-400'
                          }`}
                          style={{ width: `${scan.progress_percentage}%` }}
                        />
                      </div>
                      <span className="font-mono text-[10px] text-cyan-400">{scan.progress_percentage}%</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                    {new Date(scan.created_at).toLocaleTimeString()}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <Link href={`/active-assessments?scan_id=${scan.id}`}>
                      <Button variant="ghost" size="sm" icon={<ExternalLink className="w-3 h-3" />}>
                        Track Live
                      </Button>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Target Verification Modal */}
      <TargetVerificationModal
        isOpen={Boolean(verifyModalAsset)}
        onClose={() => setVerifyModalAsset(null)}
        asset={verifyModalAsset}
        onVerified={() => {
          fetchData();
        }}
      />
    </div>
  );
}
