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
import { canonicalFindingStatus, TRIAGE_STATUSES } from '@/lib/finding-status';
import { recordedEvidence, redactEvidence } from '@/lib/finding-evidence';
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
  const { t, locale } = useI18n();
  const L = (vi: string, en: string) => locale === 'vi' ? vi : en;
  const [activeTab, setActiveTab] = useState<EvidenceTab>('proof');
  const [copiedTab, setCopiedTab] = useState<string | null>(null);

  // Normalize finding object
  const finding: Finding = initialFinding || {
    id: 'preview-finding',
    scan_id: 'preview-scan',
    asset_id: 'unknown',
    fingerprint: 'preview-fingerprint',
    title: propFindingTitle || 'Evidence preview',
    description: 'No finding metadata supplied.',
    severity: 'INFO',
    original_severity: 'INFO',
    cvss_score: null,
    cve_id: propCveId || null,
    cwe_id: null,
    scanner_engine: 'unknown',
    scanner_rule_id: 'Not recorded',
    status: 'NEW',
    target_location: propTargetLocation || '',
    target_component: '',
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
    first_seen_at: '',
    last_seen_at: '',
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
  const [triageStatus, setTriageStatus] = useState<string>(canonicalFindingStatus(finding.status));
  const [triageAssignee, setTriageAssignee] = useState<string>(finding.assignee || '');
  const [triageComment, setTriageComment] = useState<string>(finding.remediation_notes || '');
  const [savingTriage, setSavingTriage] = useState(false);
  const [triageSavedSuccess, setTriageSavedSuccess] = useState(false);

  const evidence = finding.evidence || propEvidence || {};
  const targetLocation = finding.target_location || propTargetLocation || '';
  const rawPayload = finding.raw_payload || propRawPayload;

  const missingEvidence = L('Chưa có bằng chứng được ghi nhận cho mục này.', 'No recorded evidence for this field.');
  const shown = recordedEvidence(evidence, rawPayload, missingEvidence);
  const requestContent = shown.request;
  const responseContent = shown.response;
  const headersObj = shown.headers;
  const matchedProof = shown.proof;
  const curlCommand = shown.curl;

  const handleCopy = (text: string, tabName: string) => {
    navigator.clipboard.writeText(String(redactEvidence(text)));
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
      setTriageStatus(canonicalFindingStatus(refreshed.status));
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

  const cvssScore = finding.cvss_score;

  const getCvssGaugeColor = (score: number) => {
    if (score >= 9.0) return 'text-rose-500 bg-rose-500';
    if (score >= 7.0) return 'text-orange-500 bg-orange-500';
    if (score >= 4.0) return 'text-amber-500 bg-amber-500';
    return 'text-emerald-500 bg-emerald-500';
  };

  return (
    <div className="flex flex-col space-y-4 text-xs">
      {/* Top Meta Bar */}
      <div className="p-4 rounded-xl liquid-glass-card border border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge severity={finding.severity.toLowerCase()} size="md" dot glow>
            {finding.severity}
          </Badge>
          <span className="font-mono text-[var(--text-primary)] font-bold bg-white/[0.06] px-2.5 py-1 rounded-lg border border-[var(--border-subtle)]">
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
            <span className="font-mono text-[var(--text-secondary)] bg-white/[0.04] px-2 py-1 rounded-lg border border-[var(--border-subtle)]">
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
            icon={<RotateCcw className="w-3.5 h-3.5 text-[var(--text-primary)]" />}
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
      <div className="p-2 rounded-xl liquid-glass-card border border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => setActiveTab('proof')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'proof'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                : 'text-slate-400 hover:text-[var(--text-primary)] hover:bg-white/[0.04]'
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
                ? 'bg-white/[0.1] text-[var(--text-primary)] border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-[var(--text-primary)] hover:bg-white/[0.04]'
            }`}
          >
            <ArrowRight className="w-3.5 h-3.5 text-[var(--text-primary)]" />
            <span>Tab 2: {t('findings.tabRequest', 'HTTP Request')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('response')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'response'
                ? 'bg-white/[0.1] text-[var(--text-primary)] border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-[var(--text-primary)] hover:bg-white/[0.04]'
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-[var(--text-primary)]" />
            <span>Tab 3: {t('findings.tabResponse', 'HTTP Response')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('headers')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'headers'
                ? 'bg-white/[0.1] text-[var(--text-primary)] border border-white/20 shadow-sm'
                : 'text-slate-400 hover:text-[var(--text-primary)] hover:bg-white/[0.04]'
            }`}
          >
            <FileCode className="w-3.5 h-3.5 text-[var(--text-primary)]" />
            <span>Tab 4: {t('findings.tabHeaders', 'Headers Table')}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('curl')}
            className={`px-3 py-1.5 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
              activeTab === 'curl'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                : 'text-slate-400 hover:text-[var(--text-primary)] hover:bg-white/[0.04]'
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
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] overflow-hidden shadow-2xl p-4">
        {/* TAB 1: PROOF & IMPACT */}
        {activeTab === 'proof' && (
          <div className="space-y-4">
            {/* Impact Metric & CVSS Card */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-[var(--border-subtle)] flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Recorded CVSS Base Score</div>
                  <div className="text-xl font-black text-[var(--text-primary)] mt-1 flex items-baseline gap-2">
                    <span className={cvssScore == null ? 'text-[var(--text-secondary)]' : getCvssGaugeColor(cvssScore).split(' ')[0]}>{cvssScore == null ? L('Chưa chấm điểm', 'Unrated') : cvssScore.toFixed(1)}</span>
                    <span className="text-xs text-slate-400 font-normal">/ 10.0</span>
                  </div>
                </div>
                <div className="w-16 h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full ${cvssScore == null ? '' : getCvssGaugeColor(cvssScore).split(' ')[1]}`}
                    style={{ width: `${((cvssScore ?? 0) / 10) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-3 rounded-xl bg-white/[0.02] border border-[var(--border-subtle)]">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Affected Location</div>
                <div className="text-xs font-mono text-[var(--text-primary)] mt-1 truncate" title={targetLocation}>
                  {targetLocation}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Component: {finding.target_component || 'Root Scope'}</div>
              </div>

              <div className="p-3 rounded-xl bg-white/[0.02] border border-[var(--border-subtle)]">
                <div className="text-[10px] text-slate-400 uppercase font-semibold">Empire Business Module</div>
                <div className="text-xs font-bold text-[var(--text-primary)] mt-1">
                  {(finding.empire_module || 'SYSTEM').replace('_', ' ')}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Scanner: {(finding.scanner_engine || 'core').toUpperCase()}</div>
              </div>
            </div>

            {/* Matched String Excerpt */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-bold text-[var(--text-secondary)] flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  <span>{L('Bằng chứng đã ghi nhận', 'Recorded evidence')}</span>
                </span>
                <span className="text-[10px] text-slate-500 font-mono">{evidence.output_sha256 ? `Output SHA256: ${String(evidence.output_sha256).slice(0, 16)}…` : L('Chưa ghi nhận hash đầu ra', 'No recorded output hash')}</span>
              </div>
              <pre className="p-3.5 rounded-xl bg-[var(--bg-surface)] text-rose-300 border border-rose-900/40 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-56">
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
                  L('Chưa có khuyến nghị riêng cho phát hiện này.', 'No finding-specific remediation recorded.')}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: RAW HTTP REQUEST */}
        {activeTab === 'request' && (
          <div className="space-y-2">
            <div className="text-[10px] text-slate-400 font-mono">RECORDED REQUEST — REDACTED</div>
            <pre className="p-4 rounded-xl bg-[var(--bg-surface)] text-[var(--text-primary)] font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap border border-[var(--border-subtle)] max-h-80">
              {requestContent}
            </pre>
          </div>
        )}

        {/* TAB 3: RAW HTTP RESPONSE */}
        {activeTab === 'response' && (
          <div className="space-y-2">
            <div className="text-[10px] text-slate-400 font-mono">RECORDED RESPONSE — REDACTED</div>
            <pre className="p-4 rounded-xl bg-[var(--bg-surface)] text-slate-200 font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap border border-[var(--border-subtle)] max-h-80">
              {responseContent}
            </pre>
          </div>
        )}

        {/* TAB 4: RESPONSE HEADERS TABLE */}
        {activeTab === 'headers' && (
          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--border-subtle)] overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-[var(--bg-surface)] text-slate-400 uppercase text-[10px] tracking-wider border-b border-[var(--border-subtle)]">
                  <tr>
                    <th className="py-2.5 px-3.5 font-bold">Header Key</th>
                    <th className="py-2.5 px-3.5 font-bold">Header Value</th>
                    <th className="py-2.5 px-3.5 font-bold text-center">Header classification</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-[var(--bg-primary)] font-mono">
                  {!Object.keys(headersObj).length && <tr><td colSpan={3} className="p-3 text-[var(--text-secondary)]">{missingEvidence}</td></tr>}
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
                        <td className="py-2 px-3.5 font-bold text-[var(--text-primary)] whitespace-nowrap">{key}</td>
                        <td className="py-2 px-3.5 text-[var(--text-secondary)] break-all">{String(val)}</td>
                        <td className="py-2 px-3 text-center whitespace-nowrap">
                          {isSecurityHeader ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/[0.08] text-[var(--text-primary)] border border-white/20">
                              SECURITY_RELATED
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
            <div className="rounded-xl overflow-hidden border border-[var(--border-subtle)] bg-slate-950">
              <div className="bg-slate-900 px-3 py-1.5 flex items-center justify-between border-b border-[var(--border-subtle)]">
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
              {L('Chỉ hiển thị lệnh đã được lưu; dữ liệu nhạy cảm được che. Đọc lại phạm vi và lệnh trước khi sử dụng.', 'Only stored commands are shown; sensitive values are redacted. Review scope and command before use.')}
            </p>
          </div>
        )}
      </div>

      {/* Lifecycle Transition & Triage Drawer Footer */}
      <div className="p-4 rounded-xl liquid-glass-card border border-[var(--border-subtle)] space-y-3">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5">
          <span className="font-bold text-[var(--text-primary)] text-xs flex items-center gap-1.5">
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
            <label htmlFor={`triage-state-${finding.id}`} className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
              Target Lifecycle State
            </label>
            <select
              id={`triage-state-${finding.id}`}
              value={triageStatus}
              onChange={(e) => setTriageStatus(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-xs focus:outline-none focus:border-white/30"
            >
              {triageStatus === 'RESOLVED' && <option value="RESOLVED" disabled>RESOLVED — {L('engine đã xác minh', 'engine verified')}</option>}
              {TRIAGE_STATUSES.map((state) => <option key={state} value={state}>{state.replaceAll('_', ' ')}{state === 'FIXED_PENDING_RETEST' ? L(' — chờ engine xác minh', ' — awaiting engine verification') : ''}</option>)}
            </select>
          </div>

          <div>
            <label htmlFor={`triage-assignee-${finding.id}`} className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
              Assigned Security Engineer
            </label>
            <input
              id={`triage-assignee-${finding.id}`}
              type="text"
              placeholder="e.g. tu.nguyen@empire.edu.vn"
              value={triageAssignee}
              onChange={(e) => setTriageAssignee(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-xs focus:outline-none focus:border-white/30"
            />
          </div>
        </div>

        <div>
          <label htmlFor={`triage-notes-${finding.id}`} className="block text-slate-400 text-[10px] uppercase font-semibold mb-1">
            Remediation & Triage Notes — {L('cần lý do cho false positive / ngoại lệ', 'a reason is required for false positives / exceptions')}
          </label>
          <textarea
            id={`triage-notes-${finding.id}`}
            rows={2}
            placeholder="Add verification notes, commit hash, or justification..."
            value={triageComment}
            onChange={(e) => setTriageComment(e.target.value)}
            className="w-full px-3 py-2 rounded-xl bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-xs focus:outline-none focus:border-white/30 font-mono"
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
            disabled={finding.id === 'preview-finding' || (['FALSE_POSITIVE', 'ACCEPTED_RISK'].includes(triageStatus) && triageComment.trim().length < 8)}
          >
            {t('findings.updateStatus', 'Save Lifecycle State')}
          </Button>
        </div>
      </div>
    </div>
  );
}
