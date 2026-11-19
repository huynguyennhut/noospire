'use client';

import React, { useEffect, useState } from 'react';
import {
  FileText,
  Plus,
  Download,
  Eye,
  Trash2,
  RefreshCw,
  X,
  CheckCircle,
  FileCode,
  Shield,
  Layers,
  Sparkles,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Asset, ReportItem } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { HistoryPanel, SnapshotsPanel } from '@/components/console/HistoryAndSnapshots';

const REPORT_TEMPLATES = [
  { key: 'daily_summary', label: 'Daily Security Summary', desc: 'Stored findings and execution coverage for the selected scope; no new assessment is performed.' },
  { key: 'weekly_report', label: 'Weekly Assessment Report', desc: 'A report label for stored results; select the relevant scope and review recorded observation dates.' },
  { key: 'monthly_posture', label: 'Monthly Security Posture Report', desc: 'Stored severity/lifecycle metrics. This label does not certify monthly coverage or compliance.' },
  { key: 'technical', label: 'Full Technical Assessment Report', desc: 'Recorded findings and available evidence only; missing captures and coverage gaps remain explicit.' },
  { key: 'executive', label: 'Executive Leadership Summary', desc: 'Stored severity distribution and remediation guidance; unknown scores remain unrated.' },
  { key: 'student_management', label: 'Student Management Security Report', desc: 'Stored findings for your chosen student-management scope; no identity/BOLA tests are implied by this label.' },
  { key: 'materials_exposure', label: 'Learning Materials & /media Exposure Report', desc: 'Stored material-related findings; approved public media is not automatically a vulnerability.' },
  { key: 'api_security', label: 'API Security Assessment Report', desc: 'Stored API-related findings; this label does not establish OWASP API Top 10 coverage.' },
  { key: 'infrastructure', label: 'Infrastructure & Server Report', desc: 'Stored infrastructure results; port scans and container analysis require separately integrated controls.' },
  { key: 'remediation', label: 'Vulnerability Remediation Report', desc: 'Stored lifecycle states; FIXED_PENDING_RETEST is a claim, RESOLVED requires equivalent engine verification.' },
];

export default function ReportsPage() {
  const { t } = useI18n();
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Generation Form State
  const [formTitle, setFormTitle] = useState('');
  const [formType, setFormType] = useState<string>('daily_summary');
  const [formAssetId, setFormAssetId] = useState<string>('');
  const [formatPdf, setFormatPdf] = useState(true);
  const [formatHtml, setFormatHtml] = useState(true);
  const [formatJson, setFormatJson] = useState(true);
  const [generating, setGenerating] = useState(false);

  const fetchReports = async () => {
    try {
      setLoading(true);
      const [repRes, assetRes] = await Promise.all([
        api.listReports().catch(() => []),
        api.listAssets().catch(() => ({ items: [], total: 0 })),
      ]);
      const reportItems = Array.isArray(repRes) ? repRes : ((repRes as any)?.items || []);
      setReports(reportItems);
      setAssets(assetRes.items || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    const formats: string[] = [];
    if (formatPdf) formats.push('pdf');
    if (formatHtml) formats.push('html');
    if (formatJson) formats.push('json');

    if (formats.length === 0) {
      alert('Please select at least one format (PDF, HTML, or JSON).');
      return;
    }

    try {
      setGenerating(true);
      const chosenTemplate = REPORT_TEMPLATES.find((tmpl) => tmpl.key === formType);
      const title = formTitle.trim() || `Empire ${chosenTemplate?.label || 'Security Report'}`;

      await api.generateReport({
        title,
        report_type: formType,
        asset_id: formAssetId || undefined,
        formats,
      });

      setIsModalOpen(false);
      setFormTitle('');
      await fetchReports();
      alert('Report generated successfully with authentic database evidence!');
    } catch (err) {
      alert(`Report generation failed: ${err}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this report artifact?')) return;
    try {
      await api.deleteReport(id);
      await fetchReports();
    } catch (err) {
      alert(`Delete error: ${err}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Milestone 5: snapshot reports (template version + checksum) and run history */}
      <React.Suspense fallback={null}><SnapshotsPanel /></React.Suspense>
      <React.Suspense fallback={null}>
        <HistoryPanel />
      </React.Suspense>
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('reports.title', 'REPORTS & EXPORT ENGINE')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('reports.subtitle', 'Generate professional zero-fabrication security reports in vector PDF, self-contained HTML, and JSON export formats.')}
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 text-xs font-bold shadow-lg shadow-cyan-950/60 hover:from-cyan-400 hover:to-cyan-300 transition"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{t('reports.generateButton', 'Generate New Report')}</span>
        </button>
      </div>

      {/* Available Report Types Overview */}
      <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
        <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Supported Empire Report Types</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2.5 text-xs">
          {REPORT_TEMPLATES.map((tmpl) => (
            <div
              key={tmpl.key}
              onClick={() => {
                setFormType(tmpl.key);
                setIsModalOpen(true);
              }}
              className="p-3 rounded-xl bg-white/[0.02] border border-white/10 hover:border-cyan-500/60 cursor-pointer transition text-left"
            >
              <div className="font-bold text-white text-xs">{tmpl.label}</div>
              <div className="text-[10px] text-slate-400 mt-1 line-clamp-2">{tmpl.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Reports Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <div className="p-4 bg-cyber-950/90 border-b border-white/10 flex items-center justify-between">
          <span className="text-xs font-bold text-white uppercase tracking-wider">Generated Report Artifacts</span>
          <span className="text-xs text-slate-400 font-mono">{t('common.showing', 'Total:')} {reports.length}</span>
        </div>

        <table className="w-full text-left text-xs">
          <thead className="bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10">
            <tr>
              <th className="py-3 px-4 font-bold">Report Title & Type</th>
              <th className="py-3 px-3 font-bold">Scope</th>
              <th className="py-3 px-3 font-bold text-center">Risk Score</th>
              <th className="py-3 px-3 font-bold">Generated At</th>
              <th className="py-3 px-4 font-bold text-right">{t('common.download', 'Downloads & Formats')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {loading ? (
              <tr>
                <td colSpan={5} className="py-12 text-center text-slate-400">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                  <span>{t('common.loading', 'Loading generated reports...')}</span>
                </td>
              </tr>
            ) : reports.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-12 text-center text-slate-400">
                  <span>{t('common.noData', 'No reports generated yet. Click "Generate New Report" to create one.')}</span>
                </td>
              </tr>
            ) : (
              reports.map((rep) => (
                <tr key={rep.id} className="hover:bg-white/[0.02] transition">
                  <td className="py-3 px-4">
                    <div className="font-bold text-white text-xs">{rep.title}</div>
                    <div className="text-[10px] text-cyan-400 uppercase font-mono mt-0.5">{rep.report_type.replace('_', ' ')}</div>
                  </td>

                  <td className="py-3 px-3 text-slate-300 font-mono text-[11px]">
                    {rep.target_scope}
                  </td>

                  <td className="py-3 px-3 text-center">
                    <span className="px-2 py-0.5 rounded-md text-[11px] font-mono font-bold bg-white/[0.04] text-rose-400 border border-white/10">
                      {rep.summary?.overall_risk_score ?? 0}
                    </span>
                  </td>

                  <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                    {rep.created_at ? new Date(rep.created_at).toLocaleString() : 'N/A'}
                  </td>

                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {rep.formats.includes('pdf') && (
                        <a
                          href={api.getDownloadUrl(rep.id, 'pdf')}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 text-[11px] font-bold transition flex items-center gap-1 shadow-sm"
                        >
                          <Download className="w-3 h-3" />
                          <span>PDF</span>
                        </a>
                      )}
                      {rep.formats.includes('html') && (
                        <a
                          href={api.getDownloadUrl(rep.id, 'html')}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/20 text-[11px] font-bold transition flex items-center gap-1 shadow-sm"
                        >
                          <Download className="w-3 h-3" />
                          <span>HTML</span>
                        </a>
                      )}
                      {rep.formats.includes('json') && (
                        <a
                          href={api.getDownloadUrl(rep.id, 'json')}
                          target="_blank"
                          rel="noreferrer"
                          className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/20 text-[11px] font-bold transition flex items-center gap-1 shadow-sm"
                        >
                          <Download className="w-3 h-3" />
                          <span>JSON</span>
                        </a>
                      )}
                      <button
                        onClick={() => handleDelete(rep.id)}
                        className="p-1 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 ml-1 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Generate Report */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl liquid-glass-modal p-6 shadow-2xl border border-white/15">
            <div className="flex items-center justify-between pb-4 border-b border-white/10">
              <h2 className="text-base font-bold text-white">Generate Empire Security Report</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleGenerate} className="space-y-4 mt-4 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Report Template & Focus</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
                >
                  {REPORT_TEMPLATES.map((tmpl) => (
                    <option key={tmpl.key} value={tmpl.key}>
                      {tmpl.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Custom Title (Optional)</label>
                <input
                  type="text"
                  placeholder="Leave blank for automatic default title"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Target Scope</label>
                <select
                  value={formAssetId}
                  onChange={(e) => setFormAssetId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="">All stored targets (coverage limits apply)</option>
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.target_locator})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-2">Export Formats</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formatPdf}
                      onChange={(e) => setFormatPdf(e.target.checked)}
                      className="rounded border-cyber-700 text-cyan-500"
                    />
                    <span className="text-slate-300">Vector PDF (ReportLab)</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formatHtml}
                      onChange={(e) => setFormatHtml(e.target.checked)}
                      className="rounded border-cyber-700 text-cyan-500"
                    />
                    <span className="text-slate-300">Standalone HTML</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formatJson}
                      onChange={(e) => setFormatJson(e.target.checked)}
                      className="rounded border-cyber-700 text-cyan-500"
                    />
                    <span className="text-slate-300">Raw JSON</span>
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-white/[0.04] text-slate-300 hover:text-white border border-white/10"
                >
                  {t('common.cancel', 'Cancel')}
                </button>
                <button
                  type="submit"
                  disabled={generating}
                  className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold transition shadow-md"
                >
                  {generating ? 'Building Vector PDF...' : 'Compile Report'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
