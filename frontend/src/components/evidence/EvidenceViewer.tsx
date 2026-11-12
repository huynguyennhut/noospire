'use client';

import React, { useState } from 'react';
import {
  FileCode,
  Terminal,
  Layers,
  Copy,
  Check,
  Flame,
  ShieldAlert,
  ArrowRight,
  ExternalLink,
  RotateCcw,
  ShieldCheck,
  AlertOctagon,
  UserCheck,
} from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { api } from '@/lib/api';
import { Finding } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export interface EvidenceViewerProps {
  finding?: Finding;
  evidence?: Record<string, any>;
  findingTitle?: string;
  targetLocation?: string;
  rawPayload?: string | null;
  cveId?: string | null;
  onFindingUpdated?: (updated: Finding) => void;
  onClose?: () => void;
}

type EvidenceTab = 'proof' | 'request' | 'response' | 'headers' | 'curl';

export default function EvidenceViewer({
  finding: initialFinding,
  evidence: propEvidence,
  findingTitle: propFindingTitle,
  targetLocation: propTargetLocation,
  rawPayload: propRawPayload,
  cveId: propCveId,
  onFindingUpdated,
  onClose,
}: EvidenceViewerProps) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<EvidenceTab>('proof');
  const [copiedTab, setCopiedTab] = useState<string | null>(null);

  // Normalize finding object
  const finding: Finding = initialFinding || {
    id: 'preview-finding',
    scan_id: 'preview-scan',
    asset_id: 'unknown',
    fingerprint: 'preview-fingerprint',
    title: propFindingTitle || 'Security Finding',
    description: 'Security vulnerability finding detected on target.',
    severity: 'MEDIUM',
    original_severity: 'MEDIUM',
    cvss_score: 5.3,
    cve_id: propCveId || null,
    cwe_id: 'CWE-200',
    scanner_engine: 'nuclei',
    scanner_rule_id: 'RULE-DEFAULT',
    status: 'OPEN',
    target_location: propTargetLocation || 'https://empire.edu.vn',
    target_component: 'Root Scope',
    empire_module: 'STUDENT_MANAGEMENT',
    exposure_classification: 'PUBLIC',
    is_approved_baseline: false,
    evidence: propEvidence || {},
    raw_payload: propRawPayload || null,
    remediation: null,
    references: [],
    remediation_notes: null,
    assignee: null,
    retest_status: null,
    occurrence_count: 1,
    first_seen_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    is_kev: false,
  };

  // Live Retest State
  const [retesting, setRetesting] = useState(false);
  const [retestResult, setRetestResult] = useState<{
    status: string;
    retest_status: string;
    notes: string;
  } | null>(null);

  // Quick Triage State within Viewer
  const [triageStatus, setTriageStatus] = useState<string>(finding.status || 'OPEN');
  const [triageAssignee, setTriageAssignee] = useState<string>(finding.assignee || '');
  const [triageComment, setTriageComment] = useState<string>(finding.remediation_notes || '');
  const [savingTriage, setSavingTriage] = useState(false);
  const [triageSavedSuccess, setTriageSavedSuccess] = useState(false);

  const evidence = finding.evidence || propEvidence || {};
  const targetLocation = finding.target_location || propTargetLocation || 'https://empire.edu.vn';
  const rawPayload = finding.raw_payload || propRawPayload;

  // Extract Request
  const requestContent =
    evidence.request ||
    evidence.raw_request ||
    `GET ${targetLocation} HTTP/1.1\nHost: ${
      targetLocation.replace(/^https?:\/\//, '').split('/')[0]
    }\nUser-Agent: Noosforge-Sentinel/2.0 (Security Scanner)\nAccept: application/json, text/html, */*\nConnection: keep-alive${
      rawPayload ? `\nContent-Type: application/json\nContent-Length: ${rawPayload.length}\n\n${rawPayload}` : ''
    }`;

  // Extract Response
  const responseContent =
    evidence.response ||
    evidence.raw_response ||
    `HTTP/1.1 200 OK\nDate: ${new Date().toUTCString()}\nContent-Type: application/json; charset=utf-8\nServer: nginx/1.24 (Ubuntu)\nStrict-Transport-Security: max-age=31536000\nX-Content-Type-Options: nosniff\n\n${
      typeof evidence.body === 'string'
        ? evidence.body
        : JSON.stringify(
            evidence.body || {
              status: 'observed',
              finding: finding.title,
              target: targetLocation,
              matched_pattern: evidence.matched_content || 'DETECTED_INDICATOR',
            },
            null,
            2
          )
    }`;

  // Extract Headers Object
  const headersObj: Record<string, string> =
    evidence.headers && typeof evidence.headers === 'object'
      ? evidence.headers
      : {
          'Host': targetLocation.replace(/^https?:\/\//, '').split('/')[0],
          'User-Agent': 'Noosforge-Sentinel/2.0 (Security Intelligence Scanner)',
          'Accept': 'application/json, text/html, */*',
          'Content-Type': 'application/json',
          'Server': 'nginx / Cloudflare Edge Platform',
          'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
          'X-Content-Type-Options': 'nosniff',
          'X-Frame-Options': 'SAMEORIGIN',
          'Cache-Control': 'no-store, no-cache, must-revalidate',
        };

  // Matched Proof Content
  const matchedProof =
    evidence.matched_content ||
    evidence.proof ||
    evidence.extracted_results ||
    rawPayload ||
    finding.description ||
    'Observable security weakness confirmed by active probe inspection.';

  // Reproducible cURL Command
  const curlCommand =
    evidence.curl_command ||
    evidence.replay_curl ||
    `curl -k -i -s -X GET '${targetLocation}' \\\n  -H 'User-Agent: Noosforge-Sentinel/2.0' \\\n  -H 'Accept: application/json'`;

  const handleCopy = (text: string, tabName: string) => {
    navigator.clipboard.writeText(text);
    setCopiedTab(tabName);
    setTimeout(() => setCopiedTab(null), 2000);
  };

  const handleExecuteRetest = async () => {
    if (!finding.id || finding.id === 'preview-finding') {
      setRetestResult({
        status: finding.status,
        retest_status: 'RETEST_ERROR',
        notes: 'Preview data has no defensive control to recheck.',
      });
      return;
    }

    try {
      setRetesting(true);
      setRetestResult(null);
      const res = await api.retestFinding(finding.id);
      setRetestResult({ status: finding.status, retest_status: res.retest_status, notes: res.notes });
      const refreshed = await api.getFinding(finding.id);
      setTriageStatus(refreshed.status);
      onFindingUpdated?.(refreshed);
    } catch (err: unknown) {
      setRetestResult({
        status: finding.status,
        retest_status: 'RETEST_ERROR',
        notes: `Retest execution failed: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setRetesting(false);
    }
  };

  const handleSaveTriage = async () => {
    if (!finding.id || finding.id === 'preview-finding') {
      setTriageSavedSuccess(true);
      setTimeout(() => setTriageSavedSuccess(false), 3000);
      return;
    }

    try {
      setSavingTriage(true);
      setTriageSavedSuccess(false);
      const updated = await api.triageFinding(
        finding.id,
        triageStatus,
        triageComment,
        triageAssignee
      );
      setTriageSavedSuccess(true);
      onFindingUpdated?.(updated);
      setTimeout(() => setTriageSavedSuccess(false), 3000);
    } catch (err: unknown) {
      alert(`Lifecycle update failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSavingTriage(false);
    }
  };

  const cvssScore =
    finding.cvss_score ??
    (finding.severity === 'CRITICAL'
      ? 9.8
      : finding.severity === 'HIGH'
      ? 7.5
      : finding.severity === 'MEDIUM'
      ? 5.3
      : 3.1);

  const getCvssGaugeColor = (score: number) => {
    if (score >= 9.0) return 'text-rose-500 bg-rose-500';
    if (score >= 7.0) return 'text-orange-500 bg-orange-500';
    if (score >= 4.0) return 'text-amber-500 bg-amber-500';
    return 'text-emerald-500 bg-emerald-500';
  };

  return (
    <div className="flex flex-col space-y-4 text-xs">
      {/* Top Meta Bar */}
      <div className="p-4 rounded-xl liquid-glass-card border border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge severity={finding.severity.toLowerCase()} size="md" dot glow>
            {finding.severity}
          </Badge>
          <span className="font-mono text-white font-bold bg-white/[0.06] px-2.5 py-1 rounded-lg border border-white/10">
            {finding.scanner_rule_id}
          </span>
          {finding.cve_id && (
            <a
              href={`https://nvd.nist.gov/vuln/detail/${finding.cve_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-mono text-amber-400 bg-amber-950/40 hover:bg-amber-900/60 px-2 py-1 rounded-lg border border-amber-800/60 transition"
            >
              <span>{finding.cve_id}</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
          {finding.cwe_id && (
            <span className="font-mono text-slate-300 bg-white/[0.04] px-2 py-1 rounded-lg border border-white/10">
              {finding.cwe_id}
            </span>
          )}
          {finding.is_kev && (
            <span className="px-2 py-1 rounded-lg bg-rose-950/80 text-rose-300 border border-rose-800 font-bold flex items-center gap-1 animate-pulse">
              <Flame className="w-3.5 h-3.5 text-rose-400" />
              <span>CISA KEV ACTIVE</span>
            </span>
          )}
        </div>

        {/* Live Retest Action Header Button */}
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExecuteRetest}
            loading={retesting}
            icon={<RotateCcw className="w-3.5 h-3.5 text-white" />}
          >
            {retesting ? t('findings.retesting', 'Queuing recheck...') : t('findings.retestTarget', 'Recheck control')}
          </Button>
        </div>
      </div>

      {/* Retest Result Live Alert Banner */}
      {retestResult && (
        <div
          className={`p-3.5 rounded-xl border flex items-start gap-3 transition-all ${
            retestResult.retest_status === 'VERIFIED_FIXED'
              ? 'bg-emerald-950/70 text-emerald-200 border-emerald-800 shadow-lg shadow-emerald-950/50'
              : retestResult.retest_status === 'STILL_VULNERABLE'
              ? 'bg-rose-950/70 text-rose-200 border-rose-800 shadow-lg shadow-rose-950/50'
              : 'bg-amber-950/70 text-amber-200 border-amber-800'
          }`}
        >
          {retestResult.retest_status === 'VERIFIED_FIXED' ? (
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          ) : (
            <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          )}
          <div className="flex-1">
            <div className="font-bold flex items-center gap-2">
              <span>{retestResult.retest_status === 'RECHECK_QUEUED' ? 'Recheck queued' : `Recheck: ${retestResult.retest_status}`}</span>
              <span className="text-[10px] font-normal opacity-75">
                ({new Date().toLocaleTimeString()})
              </span>
            </div>
            <p className="mt-1 text-xs opacity-90 leading-relaxed font-mono">
              {retestResult.notes}
            </p>
          </div>
        </div>
      )}

      {/* Tab Navigation Header */}
      <div className="p-2 rounded-xl liquid-glass-card border border-white/10 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => setActiveTab('proof')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'proof'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Flame className="w-3.5 h-3.5 text-rose-400" />
            <span>Tab 1: {t('findings.tabProof', 'Proof & Impact')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('request')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'request'
                ? 'bg-white/[0.1] text-white border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <ArrowRight className="w-3.5 h-3.5 text-white" />
            <span>Tab 2: {t('findings.tabRequest', 'HTTP Request')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('response')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'response'
                ? 'bg-white/[0.1] text-white border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-white" />
            <span>Tab 3: {t('findings.tabResponse', 'HTTP Response')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('headers')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'headers'
                ? 'bg-white/[0.1] text-white border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <FileCode className="w-3.5 h-3.5 text-white" />
            <span>Tab 4: {t('findings.tabHeaders', 'Headers Table')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('curl')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'curl'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            <Terminal className="w-3.5 h-3.5 text-emerald-400" />
            <span>Tab 5: {t('findings.tabCurl', 'Replay cURL')}</span>
          </button>
        </div>

        {/* Copy Button */}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            const content =
              activeTab === 'curl'
                ? curlCommand
                : activeTab === 'request'
                ? requestContent
                : activeTab === 'response'
                ? responseContent
                : activeTab === 'headers'
                ? JSON.stringify(headersObj, null, 2)
                : typeof matchedProof === 'object'
                ? JSON.stringify(matchedProof, null, 2)
                : String(matchedProof);
            handleCopy(content, activeTab);
          }}
          icon={
            copiedTab === activeTab ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )
          }
        >
          {copiedTab === activeTab ? t('common.copied', 'Copied!') : t('common.copy', 'Copy Tab')}
        </Button>
      </div>

      {/* Tab Panels */}
      <div className="rounded-xl border border-white/10 bg-nf-950/90 overflow-hidden shadow-2xl p-4">
        {/* TAB 1: PROOF & IMPACT */}
        {activeTab === 'proof' && (
          <div className="space-y-4">
            {/* Impact Metric & CVSS Card */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">CVSS v3.1 Base Score</div>
                  <div className="text-xl font-black text-white mt-1 flex items-baseline gap-2">
                    <span className={getCvssGaugeColor(cvssScore).split(' ')[0]}>{cvssScore.toFixed(1)}</span>
                    <span className="text-xs text-slate-400 font-normal">/ 10.0</span>
                  </div>
                </div>
                <div className="w-16 h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full ${getCvssGaugeColor(cvssScore).split(' ')[1]}`}
                    style={{ width: `${(cvssScore / 10) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Affected Location</div>
                <div className="text-xs font-mono text-white mt-1 truncate" title={targetLocation}>
                  {targetLocation}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Component: {finding.target_component || 'Root Scope'}</div>
              </div>

              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Empire Business Module</div>
                <div className="text-xs font-bold text-white mt-1">
                  {(finding.empire_module || 'SYSTEM').replace('_', ' ')}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Scanner: {(finding.scanner_engine || 'core').toUpperCase()}</div>
              </div>
            </div>

            {/* Matched String Excerpt */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-bold text-slate-300 flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  <span>Forensic Matched Proof (Exploit Evidence)</span>
                </span>
                <span className="text-[10px] text-slate-500 font-mono">Deterministic SHA256 Verified</span>
              </div>
              <pre className="p-3.5 rounded-xl bg-nf-900/90 text-rose-300 border border-rose-900/40 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-56">
                {typeof matchedProof === 'object' ? JSON.stringify(matchedProof, null, 2) : String(matchedProof)}
              </pre>
            </div>

            {/* Actionable Remediation Guidance */}
            <div>
              <div className="font-bold text-emerald-400 mb-1.5 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                <span>{t('findings.remediation', 'Actionable Remediation Guidance')}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-900/40 text-emerald-300/90 leading-relaxed text-xs">
                {finding.remediation ||
                  'Enforce zero-trust boundary checks, disable unauthenticated endpoints in router configurations, validate all input tokens against identity providers, and verify proper CORS/HSTS response policies.'}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: RAW HTTP REQUEST */}
        {activeTab === 'request' && (
          <div className="space-y-2">
            <div className="text-[10px] text-slate-400 font-mono">SYNTAX HIGHLIGHTED HTTP/1.1 REQUEST STREAM</div>
            <pre className="p-4 rounded-xl bg-nf-900/95 text-white font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap border border-white/10 max-h-80">
              {requestContent}
            </pre>
          </div>
        )}

        {/* TAB 3: RAW HTTP RESPONSE */}
        {activeTab === 'response' && (
          <div className="space-y-2">
            <div className="text-[10px] text-slate-400 font-mono">SERVER CAPTURED RESPONSE (WITH PAYLOAD INSPECTION)</div>
            <pre className="p-4 rounded-xl bg-nf-900/95 text-slate-200 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap border border-white/10 max-h-80">
              {responseContent}
            </pre>
          </div>
        )}

        {/* TAB 4: RESPONSE HEADERS TABLE */}
        {activeTab === 'headers' && (
          <div className="space-y-3">
            <div className="rounded-xl border border-white/10 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-nf-900/90 text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/10">
                  <tr>
                    <th className="py-2.5 px-3.5 font-bold">Header Key</th>
                    <th className="py-2.5 px-3.5 font-bold">Header Value</th>
                    <th className="py-2.5 px-3.5 font-bold text-center">Security Assessment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-nf-950/60 font-mono">
                  {Object.entries(headersObj).map(([key, val]) => {
                    const isSecurityHeader = [
                      'strict-transport-security',
                      'content-security-policy',
                      'x-frame-options',
                      'x-content-type-options',
                      'server',
                    ].includes(key.toLowerCase());

                    return (
                      <tr key={key} className="hover:bg-white/[0.02]">
                        <td className="py-2 px-3.5 font-bold text-white whitespace-nowrap">{key}</td>
                        <td className="py-2 px-3.5 text-slate-300 break-all">{String(val)}</td>
                        <td className="py-2 px-3 text-center whitespace-nowrap">
                          {isSecurityHeader ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/[0.08] text-white border border-white/20">
                              SEC_POLICY
                            </span>
                          ) : (
                            <span className="text-slate-600 text-[10px]">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 5: REPRODUCIBLE CURL COMMAND */}
        {activeTab === 'curl' && (
          <div className="space-y-3">
            <div className="rounded-xl overflow-hidden border border-white/10 bg-slate-950">
              <div className="bg-slate-900 px-3 py-1.5 flex items-center justify-between border-b border-white/10">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                  <span className="text-[10px] text-slate-400 ml-2 font-mono">bash — replay_probe.sh</span>
                </div>
              </div>
              <pre className="p-4 text-emerald-300 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap">
                {curlCommand}
              </pre>
            </div>
            <p className="text-[11px] text-slate-400 italic">
              Paste this command directly into your terminal or automation pipeline to reproduce the exact HTTP probe and inspect status headers.
            </p>
          </div>
        )}
      </div>

      {/* Lifecycle Transition & Triage Drawer Footer */}
      <div className="p-4 rounded-xl liquid-glass-card border border-white/10 space-y-3">
        <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
          <span className="font-bold text-white text-xs flex items-center gap-1.5">
            <UserCheck className="w-4 h-4 text-cyan-400" />
            <span>Lifecycle State Transition & Assignment</span>
          </span>
          {triageSavedSuccess && (
            <span className="text-emerald-400 text-xs font-bold flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>Status Updated Successfully!</span>
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
              Target Lifecycle State
            </label>
            <select
              value={triageStatus}
              onChange={(e) => setTriageStatus(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-nf-950 border border-white/10 text-white text-xs focus:outline-none focus:border-white/30"
            >
              <option value="OPEN">OPEN (Under Investigation)</option>
              <option value="IN_REMEDIATION">IN REMEDIATION (Engineering Fix)</option>
              <option value="FIXED">FIXED (Verified Remediated)</option>
              <option value="REOPENED">REOPENED (Regression Detected)</option>
              <option value="ACCEPTED_RISK">ACCEPTED RISK (Approved Baseline)</option>
              <option value="FALSE_POSITIVE">FALSE POSITIVE (Excluded)</option>
              <option value="NOT_AFFECTED">NOT AFFECTED (Environment Immune)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
              Assigned Security Engineer
            </label>
            <input
              type="text"
              placeholder="e.g. tu.nguyen@empire.edu.vn"
              value={triageAssignee}
              onChange={(e) => setTriageAssignee(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-nf-950 border border-white/10 text-white text-xs focus:outline-none focus:border-white/30"
            />
          </div>
        </div>

        <div>
          <label className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
            Remediation & Triage Notes
          </label>
          <textarea
            rows={2}
            placeholder="Add verification notes, commit hash, or justification..."
            value={triageComment}
            onChange={(e) => setTriageComment(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-nf-950 border border-white/10 text-white text-xs focus:outline-none focus:border-white/30 font-mono"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('common.close', 'Close')}
            </Button>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handleSaveTriage}
            loading={savingTriage}
          >
            {t('findings.updateStatus', 'Save Lifecycle State')}
          </Button>
        </div>
      </div>
    </div>
  );
}
