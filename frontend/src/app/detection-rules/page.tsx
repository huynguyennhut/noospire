'use client';

import React, { useEffect, useState } from 'react';
import {
  Code2,
  Plus,
  Play,
  CheckCircle,
  Clock,
  AlertCircle,
  FileText,
  X,
  Send,
  ShieldCheck,
  Ban,
} from 'lucide-react';
import { api } from '@/lib/api';
import { DetectionRule } from '@/lib/types';
import { useI18n } from '@/lib/i18n';

const SAMPLE_YAML_RULE = `id: sentinel-det-custom-injection
info:
  name: Generic SQL Injection Pattern Detection
  author: Security Operations Analyst
  severity: critical
  description: Detects SQL injection tautologies in HTTP request queries.
matchers:
  - type: regex
    part: body
    regex:
      - "(?i)(?:or|and)\\s+\\d+=\\d+"
condition: or
`;

export default function DetectionRulesPage() {
  const { t } = useI18n();
  const [rules, setRules] = useState<DetectionRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [yamlContent, setYamlContent] = useState(SAMPLE_YAML_RULE);
  const [validationResult, setValidationResult] = useState<{ valid: boolean; errors: string[] } | null>(null);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedRule, setSelectedRule] = useState<DetectionRule | null>(null);
  const [testResult, setTestResult] = useState<any>(null);
  const [testing, setTesting] = useState(false);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const res = await api.listRules().catch(() => ({ items: [], total: 0 }));
      setRules(res.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRules();
  }, []);

  const handleValidate = async () => {
    try {
      setValidating(true);
      const res = await api.validateRule(yamlContent);
      setValidationResult(res);
    } catch (err: any) {
      setValidationResult({ valid: false, errors: [err.message] });
    } finally {
      setValidating(false);
    }
  };

  const handleSaveRule = async () => {
    try {
      setSaving(true);
      await api.createRule({ raw_yaml: yamlContent });
      setIsEditorOpen(false);
      setValidationResult(null);
      await fetchRules();
    } catch (err: any) {
      alert(`Save rule failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTransition = async (ruleId: string, toStatus: string) => {
    try {
      await api.transitionRule(ruleId, toStatus, `Transitioned to ${toStatus} via SOC console.`);
      await fetchRules();
      if (selectedRule && selectedRule.id === ruleId) {
        setSelectedRule({ ...selectedRule, status: toStatus as any });
      }
    } catch (err: any) {
      alert(`Transition failed: ${err.message}`);
    }
  };

  const handleTestRule = async (ruleId: string) => {
    try {
      setTesting(true);
      const res = await api.testRule(ruleId);
      setTestResult(res);
    } catch (err: any) {
      alert(`Rule test failed: ${err.message}`);
    } finally {
      setTesting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-emerald-950/80 text-emerald-400 border border-emerald-800';
      case 'approved':
        return 'bg-cyan-950/80 text-cyan-400 border border-cyan-800';
      case 'in_review':
        return 'bg-amber-950/80 text-amber-400 border border-amber-800';
      case 'deprecated':
        return 'bg-white/[0.04] text-slate-400 border border-white/10';
      default:
        return 'bg-white/[0.04] text-slate-300 border border-white/10';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            <Code2 className="w-6 h-6 text-cyan-400" />
            <span>{t('rules.title', 'Detection Rule Manager')}</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            {t('rules.subtitle', 'Declarative YAML detection rules with schema validation, sandbox fixtures, and review gating.')}
          </p>
        </div>

        <button
          onClick={() => setIsEditorOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold text-sm transition shadow-lg shadow-cyan-950/60"
        >
          <Plus className="w-4 h-4" />
          <span>{t('rules.authorNew', 'Author New Rule')}</span>
        </button>
      </div>

      {/* Rules Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-white/10 bg-cyber-950/90 text-[10px] font-mono text-slate-400 uppercase tracking-wider">
              <th className="py-3 px-4 font-bold">Rule Identifier & Name</th>
              <th className="py-3 px-4 font-bold">Severity</th>
              <th className="py-3 px-4 font-bold">Lifecycle State</th>
              <th className="py-3 px-4 font-bold">Author</th>
              <th className="py-3 px-4 font-bold">Version</th>
              <th className="py-3 px-4 text-right font-bold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-sm">
            {rules.length > 0 ? (
              rules.map((rule) => (
                <tr
                  key={rule.id}
                  onClick={() => setSelectedRule(rule)}
                  className="hover:bg-white/[0.02] cursor-pointer transition text-xs"
                >
                  <td className="py-3 px-4">
                    <div className="font-bold text-slate-200">{rule.name}</div>
                    <div className="text-[11px] font-mono text-cyan-400 mt-0.5">{rule.id}</div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-[11px] font-mono font-bold uppercase text-rose-400">
                      {rule.severity}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded-md text-[10px] font-mono font-bold uppercase ${getStatusBadge(
                        rule.status
                      )}`}
                    >
                      {rule.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-xs text-slate-300">{rule.author}</td>
                  <td className="py-3 px-4 text-xs font-mono text-slate-400">{rule.version}</td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                      {rule.status === 'draft' && (
                        <button
                          onClick={() => handleTransition(rule.id, 'in_review')}
                          className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-[11px] text-amber-400 flex items-center gap-1"
                        >
                          <Send className="w-3 h-3" /> {t('common.submit', 'Submit')}
                        </button>
                      )}
                      {rule.status === 'in_review' && (
                        <button
                          onClick={() => handleTransition(rule.id, 'approved')}
                          className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-[11px] text-cyan-400 flex items-center gap-1"
                        >
                          <ShieldCheck className="w-3 h-3" /> {t('common.approve', 'Approve')}
                        </button>
                      )}
                      {rule.status === 'approved' && (
                        <button
                          onClick={() => handleTransition(rule.id, 'active')}
                          className="px-2.5 py-1 rounded-lg bg-emerald-950/80 border border-emerald-800 text-[11px] text-emerald-400 hover:bg-emerald-900/80 flex items-center gap-1 font-bold"
                        >
                          <CheckCircle className="w-3 h-3" /> {t('common.activate', 'Activate')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500 text-xs">
                  {loading ? t('common.loading', 'Loading detection rules...') : 'No detection rules indexed.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Rule Editor */}
      {isEditorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="liquid-glass-modal rounded-2xl max-w-3xl w-full p-6 shadow-2xl relative flex flex-col max-h-[85vh] border border-white/15">
            <button
              onClick={() => setIsEditorOpen(false)}
              className="absolute right-4 top-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06]"
            >
              <X className="w-5 h-5" />
            </button>

            <h2 className="text-lg font-bold text-white mb-1">Author Declarative Detection Rule</h2>
            <p className="text-xs text-slate-400 mb-3">
              Define target matching conditions conforming to Sentinel Rule Spec v1.
            </p>

            <div className="flex-1 min-h-[300px] mb-3">
              <textarea
                value={yamlContent}
                onChange={(e) => setYamlContent(e.target.value)}
                className="w-full h-full bg-cyber-950 border border-white/10 rounded-xl p-3 font-mono text-xs text-slate-200 focus:outline-none focus:border-cyan-500 resize-none leading-relaxed"
                spellCheck={false}
              />
            </div>

            {/* Validation Feedback */}
            {validationResult && (
              <div
                className={`p-3 rounded-xl text-xs font-mono mb-3 ${
                  validationResult.valid
                    ? 'bg-emerald-950/60 border border-emerald-800 text-emerald-300'
                    : 'bg-rose-950/60 border border-rose-800 text-rose-300'
                }`}
              >
                {validationResult.valid ? (
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    Schema validation passed! Syntax is valid.
                  </div>
                ) : (
                  <div>
                    <div className="font-bold mb-1">Schema Validation Errors:</div>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {validationResult.errors.map((e, idx) => (
                        <li key={idx}>{e}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-between items-center pt-3 border-t border-white/10">
              <button
                type="button"
                onClick={handleValidate}
                disabled={validating}
                className="px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs text-slate-300 hover:text-white"
              >
                {validating ? 'Validating...' : 'Validate Schema'}
              </button>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setIsEditorOpen(false)}
                  className="px-4 py-1.5 rounded-xl bg-white/[0.04] text-xs text-slate-400 hover:text-white border border-white/10"
                >
                  {t('common.cancel', 'Cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleSaveRule}
                  disabled={saving}
                  className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold text-xs shadow-md"
                >
                  {saving ? 'Saving...' : 'Save Draft Rule'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Drawer: Selected Rule Details & Sandbox Runner */}
      {selectedRule && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm">
          <div className="liquid-glass-modal border-l border-white/15 w-full max-w-xl h-full p-6 overflow-y-auto shadow-2xl relative flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between pb-3 border-b border-white/10">
                <div>
                  <span
                    className={`px-2 py-0.5 rounded-md text-[10px] font-mono font-bold uppercase ${getStatusBadge(
                      selectedRule.status
                    )}`}
                  >
                    {selectedRule.status}
                  </span>
                  <h2 className="text-lg font-bold text-white mt-1.5">{selectedRule.name}</h2>
                  <div className="text-xs font-mono text-cyan-400">{selectedRule.id}</div>
                </div>
                <button
                  onClick={() => setSelectedRule(null)}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06]"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="my-4">
                <h3 className="text-xs font-mono text-slate-400 uppercase mb-2">RAW YAML DEFINITION</h3>
                <pre className="bg-cyber-950 border border-white/10 rounded-xl p-3 font-mono text-xs text-slate-300 overflow-x-auto max-h-72">
                  {selectedRule.raw_yaml}
                </pre>
              </div>

              {/* Sandbox Tester */}
              <div className="mt-4 p-4 bg-white/[0.02] border border-white/10 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-mono text-slate-300 font-bold">RULE SANDBOX TEST FIXTURE</h3>
                  <button
                    onClick={() => handleTestRule(selectedRule.id)}
                    disabled={testing}
                    className="px-3 py-1 bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-bold text-xs rounded-lg hover:from-cyan-400 hover:to-cyan-300 flex items-center gap-1 shadow-md"
                  >
                    <Play className="w-3 h-3 fill-current" />
                    {testing ? 'Testing...' : 'Execute Test'}
                  </button>
                </div>
                {testResult && (
                  <div className="text-xs font-mono text-emerald-400 mt-2 bg-cyber-950 p-2.5 rounded-lg border border-emerald-900/40">
                    Result: {JSON.stringify(testResult)}
                  </div>
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-white/10">
              <button
                onClick={() => setSelectedRule(null)}
                className="w-full py-2 bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 text-xs font-bold rounded-xl border border-white/10"
              >
                {t('common.close', 'Close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
