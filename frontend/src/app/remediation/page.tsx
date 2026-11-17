'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  CheckCircle2,
  Clock,
  RotateCcw,
  UserCheck,
  ShieldAlert,
  RefreshCw,
  ChevronRight,
  Eye,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Finding } from '@/lib/types';
import { canonicalFindingStatus, findingStage, TRIAGE_STATUSES } from '@/lib/finding-status';
import { useI18n } from '@/lib/i18n';
import { Badge, Button, Modal } from '@/components/ui';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';

interface KanbanColumnConfig {
  key: string;
  title: string;
  color: string;
  headerBorder: string;
}

const LIFECYCLE_COLUMNS: KanbanColumnConfig[] = [
  {
    key: 'TRIAGE',
    title: 'Triage & Assignment',
    color: 'border-rose-500/50 text-[var(--text-primary)] bg-rose-500/10',
    headerBorder: 'border-rose-500/40',
  },
  {
    key: 'IN_PROGRESS',
    title: 'In Remediation',
    color: 'border-blue-500/50 text-[var(--text-primary)] bg-blue-500/10',
    headerBorder: 'border-blue-500/40',
  },
  {
    key: 'FIXED_PENDING_RETEST',
    title: 'Awaiting Retest',
    color: 'border-amber-500/50 text-[var(--text-primary)] bg-amber-500/10',
    headerBorder: 'border-amber-500/40',
  },
  {
    key: 'RESOLVED',
    title: 'Fixed & Verified',
    color: 'border-emerald-500/50 text-[var(--text-primary)] bg-emerald-500/10',
    headerBorder: 'border-emerald-500/40',
  },
  {
    key: 'REOPENED',
    title: 'Reopened Regressions',
    color: 'border-red-600/50 text-red-500 bg-red-600/10',
    headerBorder: 'border-red-600/40',
  },
  {
    key: 'OTHER',
    title: 'Dismissed / Other',
    color: 'border-slate-500/50 text-slate-400 bg-slate-500/10',
    headerBorder: 'border-slate-500/40',
  },
];

const SLA_HOURS_CONFIG: Record<string, number> = {
  CRITICAL: 48,
  HIGH: 168,
  MEDIUM: 720,
  LOW: 2160,
  INFO: 2160,
};

function calculateSla(finding: Finding) {
  const allowedHours =
    SLA_HOURS_CONFIG[finding.severity?.toUpperCase()] || 720;
  const createdDate = new Date(finding.first_seen_at || Date.now());
  const dueDate = new Date(createdDate.getTime() + allowedHours * 60 * 60 * 1000);
  const now = new Date();
  const diffHours = (dueDate.getTime() - now.getTime()) / (1000 * 60 * 60);
  const diffDays = Math.ceil(diffHours / 24);

  if (diffHours < 0) {
    const overdueDays = Math.abs(diffDays);
    return {
      badgeClass: 'bg-rose-500/10 text-[var(--text-primary)] border-rose-800 animate-pulse font-bold',
      text: `SLA Breached (${overdueDays}d overdue)`,
      isBreached: true,
      diffDays,
    };
  } else if (diffDays <= 2) {
    return {
      badgeClass: 'bg-amber-500/10 text-[var(--text-primary)] border-amber-800 font-semibold',
      text: `SLA Due Soon (${Math.round(diffHours)}h left)`,
      isBreached: false,
      diffDays,
    };
  } else {
    return {
      badgeClass: 'bg-emerald-500/10 text-[var(--text-primary)] border-emerald-800/80',
      text: `SLA On Track (${diffDays}d left)`,
      isBreached: false,
      diffDays,
    };
  }
}

export default function RemediationPage() {
  const { t } = useI18n();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Card Selection & Detail Modal
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [viewEvidenceFinding, setViewEvidenceFinding] = useState<Finding | null>(null);

  // Edit / Triage State
  const [targetStatus, setTargetStatus] = useState('IN_PROGRESS');
  const [assignee, setAssignee] = useState('');
  const [notes, setNotes] = useState('');
  const [updating, setUpdating] = useState(false);

  // Card Retest State
  const [cardRetestingId, setCardRetestingId] = useState<string | null>(null);
  const [cardRetestSuccess, setCardRetestSuccess] = useState<Record<string, string>>({});

  const fetchFindings = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.listAllFindings();
      setFindings(res);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  const handleOpenEdit = (f: Finding) => {
    setSelectedFinding(f);
    setTargetStatus(canonicalFindingStatus(f.status));
    setAssignee(f.assignee || '');
    setNotes(f.remediation_notes || '');
  };

  const handleUpdateLifecycle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFinding) return;
    try {
      setUpdating(true);
      const updated = await api.triageFinding(
        selectedFinding.id,
        targetStatus,
        notes,
        assignee
      );
      setFindings((prev) =>
        prev.map((f) => (f.id === updated.id ? updated : f))
      );
      setSelectedFinding(null);
    } catch (err: unknown) {
      alert(`Lifecycle update failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setUpdating(false);
    }
  };

  // Quick Move Action
  const handleQuickMove = async (
    findingId: string,
    newStatus: string,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    try {
      const updated = await api.triageFinding(
        findingId,
        newStatus,
        `Quick-moved to ${newStatus} via Kanban board`
      );
      setFindings((prev) =>
        prev.map((f) => (f.id === updated.id ? updated : f))
      );
    } catch (err: unknown) {
      alert(`Quick move failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Live Retest from Kanban Card
  const handleCardRetest = async (findingId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setCardRetestingId(findingId);
      const res = await api.retestFinding(findingId);
      const refreshed = await api.getFinding(findingId);

      setCardRetestSuccess((prev) => ({
        ...prev,
        [findingId]: res.retest_status,
      }));

      setFindings((prev) =>
        prev.map((f) => (f.id === findingId ? refreshed : f))
      );

      setTimeout(() => {
        setCardRetestSuccess((prev) => {
          const next = { ...prev };
          delete next[findingId];
          return next;
        });
      }, 5000);
    } catch (err: unknown) {
      alert(`Recheck refused: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setCardRetestingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-6 h-6 text-[var(--text-primary)]" />
            <h1 className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
              {t('remediation.title', 'REMEDIATION TRACKING & SLA BOARD')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t(
              'remediation.subtitle',
              'Track vulnerability lifecycle transitions (TRIAGE → IN PROGRESS → AWAITING RETEST → RESOLVED), monitor SLAs, assign engineers, and queue defensive rechecks.'
            )}
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={fetchFindings}
          loading={loading}
          icon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          {t('common.refresh', 'Refresh Board')}
        </Button>
      </div>

      {loadError && <div role="alert" className="text-[var(--text-primary)]">{loadError}</div>}
      {/* Every lifecycle state remains visible, including historical values. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-4 items-start">
        {LIFECYCLE_COLUMNS.map((col) => {
          const colFindings = findings.filter(
            (f) => findingStage(f.status) === col.key
          );

          return (
            <div
              key={col.key}
              className={`rounded-2xl liquid-glass-card border ${col.headerBorder} p-3.5 flex flex-col min-h-[580px] shadow-xl`}
            >
              {/* Column Header */}
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <span className={`px-2.5 py-1 rounded-lg text-[10px] font-bold border uppercase ${col.color}`}>
                  {col.title}
                </span>
                <span className="font-mono text-xs font-bold text-slate-300 bg-white/[0.04] px-2 py-0.5 rounded-md border border-white/10">
                  {colFindings.length}
                </span>
              </div>

              {/* Cards Container */}
              <div className="space-y-3 mt-3 flex-1 overflow-y-auto max-h-[calc(100vh-280px)] pr-0.5">
                {colFindings.length === 0 ? (
                  <div className="text-center py-16 text-slate-500 text-xs italic">
                    No findings in this stage
                  </div>
                ) : (
                  colFindings.map((f) => {
                    const sla = calculateSla(f);
                    const isRetesting = cardRetestingId === f.id;
                    const retestStatusBadge = cardRetestSuccess[f.id];

                    return (
                      <div
                        key={f.id}
                        onClick={() => handleOpenEdit(f)}
                        className="p-3.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/10 hover:border-white/25 transition-all cursor-pointer shadow-md text-xs space-y-2.5 group"
                      >
                        {/* Top Meta: Severity & Rule */}
                        <div className="flex items-center justify-between gap-1">
                          <Badge severity={f.severity.toLowerCase()} size="sm">
                            {f.severity}
                          </Badge>
                          <span className="text-[10px] text-[var(--text-primary)] font-mono truncate max-w-[120px]">
                            {f.cve_id || f.scanner_rule_id}
                          </span>
                        </div>

                        {/* Title */}
                        <div className="font-bold text-[var(--text-primary)] text-xs leading-snug line-clamp-2 group-hover:text-[var(--text-primary)] transition-colors">
                          {f.title}
                        </div>

                        {/* Endpoint Location */}
                        <div className="text-[11px] text-slate-400 font-mono truncate">
                          {f.target_location}
                        </div>

                        <div className="text-[10px] text-[var(--text-secondary)]">{canonicalFindingStatus(f.status).replaceAll('_', ' ')}</div>

                        {/* SLA Indicator */}
                        {col.key !== 'RESOLVED' && col.key !== 'OTHER' && <div className="pt-1">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] border ${sla.badgeClass}`}>
                            <Clock className="w-2.5 h-2.5" />
                            <span>{sla.text}</span>
                          </span>
                        </div>}

                        {/* Retest Result Badge if triggered */}
                        {retestStatusBadge && (
                          <div
                            className={`p-1.5 rounded-lg border text-[10px] font-bold text-center ${
                              retestStatusBadge === 'RECHECK_QUEUED'
                                ? 'bg-emerald-500/10 text-[var(--text-primary)] border-emerald-800'
                                : 'bg-rose-500/10 text-[var(--text-primary)] border-rose-800'
                            }`}
                          >
                            Retest: {retestStatusBadge}
                          </div>
                        )}

                        {/* Card Footer: Assignee & Action Controls */}
                        <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-400">
                          <div className="flex items-center gap-1 truncate max-w-[100px]">
                            <UserCheck className="w-3 h-3 text-slate-500 shrink-0" />
                            <span className="truncate">{f.assignee || 'Unassigned'}</span>
                          </div>

                          {/* Quick Actions Buttons */}
                          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                            {/* Live Retest Trigger */}
                            <button
                              type="button"
                              onClick={(e) => handleCardRetest(f.id, e)}
                              disabled={isRetesting}
                              title="Queue the same approved defensive control"
                              className="p-1 rounded bg-white/[0.04] hover:bg-white/[0.08] text-[var(--text-primary)] hover:text-[var(--text-primary)] transition"
                            >
                              <RotateCcw
                                className={`w-3 h-3 ${isRetesting ? 'animate-spin text-[var(--text-primary)]' : ''}`}
                              />
                            </button>

                            {/* View Evidence */}
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setViewEvidenceFinding(f);
                              }}
                              title="Inspect forensic evidence"
                              className="p-1 rounded bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-[var(--text-primary)] transition"
                            >
                              <Eye className="w-3 h-3" />
                            </button>

                            {/* Quick Move Forward Button */}
                            {col.key === 'TRIAGE' && (
                              <button
                                type="button"
                                onClick={(e) => handleQuickMove(f.id, 'IN_PROGRESS', e)}
                                title="Move to In Remediation"
                                className="px-1.5 py-0.5 rounded bg-blue-500/10 text-[var(--text-primary)] border border-blue-800 text-[9px] font-bold hover:bg-blue-900 transition flex items-center gap-0.5"
                              >
                                <span>Fix</span>
                                <ChevronRight className="w-2.5 h-2.5" />
                              </button>
                            )}

                            {col.key === 'IN_PROGRESS' && (
                              <button
                                type="button"
                                onClick={(e) => handleQuickMove(f.id, 'FIXED_PENDING_RETEST', e)}
                                title="Claim a fix; engine verification is still required"
                                className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-[var(--text-primary)] border border-emerald-800 text-[9px] font-bold hover:bg-emerald-900 transition flex items-center gap-0.5"
                              >
                                <span>Claim fix</span>
                                <ChevronRight className="w-2.5 h-2.5" />
                              </button>
                            )}

                            {col.key === 'RESOLVED' && (
                              <button
                                type="button"
                                onClick={(e) => handleQuickMove(f.id, 'REOPENED', e)}
                                title="Reopen as Regression"
                                className="px-1.5 py-0.5 rounded bg-rose-500/10 text-[var(--text-primary)] border border-rose-800 text-[9px] font-bold hover:bg-rose-900 transition flex items-center gap-0.5"
                              >
                                <span>Reopen</span>
                                <ChevronRight className="w-2.5 h-2.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal 1: Edit Lifecycle & Reassign Modal */}
      {selectedFinding && (
        <Modal
          isOpen={Boolean(selectedFinding)}
          onClose={() => setSelectedFinding(null)}
          size="lg"
          title={
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-[var(--text-primary)]" />
              <span>Vulnerability Lifecycle Transition</span>
            </div>
          }
          description={`Update assignment, SLA progress, and lifecycle status for ${selectedFinding.scanner_rule_id}`}
        >
          <form onSubmit={handleUpdateLifecycle} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-400 mb-1 font-semibold uppercase text-[10px]">
                Finding Title
              </label>
              <div className="font-bold text-[var(--text-primary)] text-sm bg-white/[0.02] p-3 rounded-xl border border-white/10">
                {selectedFinding.title}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">
                  Target Lifecycle State
                </label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-[var(--bg-surface)] border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500"
                >
                  {canonicalFindingStatus(selectedFinding.status) === 'RESOLVED' && (
                    <option value="RESOLVED">RESOLVED (engine verified)</option>
                  )}
                  {TRIAGE_STATUSES.map((status) => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">
                  Assigned Security Engineer
                </label>
                <input
                  type="text"
                  placeholder="Engineer username or email"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-[var(--bg-surface)] border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-semibold mb-1">
                Remediation & Verification Notes
              </label>
              <textarea
                rows={3}
                placeholder="Describe patch details, commit hash, verification steps, or rationale..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-[var(--bg-surface)] border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500 font-mono text-xs"
              />
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-white/10">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  const target = selectedFinding;
                  setSelectedFinding(null);
                  setViewEvidenceFinding(target);
                }}
                icon={<Eye className="w-3.5 h-3.5" />}
              >
                Inspect Evidence
              </Button>

              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedFinding(null)}
                >
                  {t('common.cancel', 'Cancel')}
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  loading={updating}
                >
                  Update Status
                </Button>
              </div>
            </div>
          </form>
        </Modal>
      )}

      {/* Modal 2: Evidence Drill-Down Modal */}
      {viewEvidenceFinding && (
        <Modal
          isOpen={Boolean(viewEvidenceFinding)}
          onClose={() => setViewEvidenceFinding(null)}
          size="full"
          title={
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-[var(--text-primary)]" />
              <span>{viewEvidenceFinding.title}</span>
            </div>
          }
          description="Forensic investigation and live verification"
        >
          <EvidenceViewer
            finding={viewEvidenceFinding}
            onFindingUpdated={(updated) => {
              setViewEvidenceFinding(updated);
              setFindings((prev) =>
                prev.map((f) => (f.id === updated.id ? updated : f))
              );
            }}
            onClose={() => setViewEvidenceFinding(null)}
          />
        </Modal>
      )}
    </div>
  );
}
