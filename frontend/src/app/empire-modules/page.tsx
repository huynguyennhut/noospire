'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Layers,
  Users,
  BookOpen,
  Wrench,
  Cpu,
  Globe,
  Server,
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  Calendar,
  ArrowRight,
  RefreshCw,
  Play,
} from 'lucide-react';
import { api } from '@/lib/api';
import { EmpireModuleSummary } from '@/lib/types';
import { useI18n } from '@/lib/i18n';

export default function EmpireModulesPage() {
  const { t } = useI18n();
  const [modules, setModules] = useState<EmpireModuleSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchModules = async () => {
    try {
      setLoading(true);
      const res = await api.getEmpireModules();
      const items = Array.isArray(res) ? res : ((res as any)?.items || []);
      setModules(items);
    } catch (err) {
      console.error('Failed to load Empire modules', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModules();
  }, []);

  const getModuleIcon = (iconName: string) => {
    switch (iconName) {
      case 'Users':
        return <Users className="w-5 h-5 text-purple-400" />;
      case 'BookOpen':
        return <BookOpen className="w-5 h-5 text-blue-400" />;
      case 'Wrench':
        return <Wrench className="w-5 h-5 text-emerald-400" />;
      case 'Cpu':
        return <Cpu className="w-5 h-5 text-cyan-400" />;
      case 'Globe':
        return <Globe className="w-5 h-5 text-amber-400" />;
      default:
        return <Server className="w-5 h-5 text-slate-400" />;
    }
  };

  const getRiskColor = (tier: string) => {
    switch (tier) {
      case 'CRITICAL':
        return 'text-rose-400 border-rose-800 bg-rose-950/60';
      case 'HIGH':
        return 'text-orange-400 border-orange-800 bg-orange-950/60';
      case 'MEDIUM':
        return 'text-amber-400 border-amber-800 bg-amber-950/60';
      default:
        return 'text-emerald-400 border-emerald-800 bg-emerald-950/60';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('modules.title', 'EMPIRE BUSINESS MODULE SECURITY')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('modules.subtitle', "Continuous threat posture, access control boundary verification, and vulnerability distribution across Empire's operational domains.")}
          </p>
        </div>

        <button
          onClick={fetchModules}
          className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          <span>{t('common.refresh', 'Refresh Telemetry')}</span>
        </button>
      </div>

      {/* Module Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {modules.map((mod) => (
          <div
            key={mod.module_key}
            className="rounded-2xl liquid-glass-card border border-white/10 hover:border-white/20 transition-all flex flex-col justify-between overflow-hidden shadow-xl"
          >
            {/* Card Header */}
            <div className="p-5 border-b border-white/10 bg-white/[0.02]">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center shadow-md">
                    {getModuleIcon(mod.icon)}
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-white tracking-wide">{mod.title}</h2>
                    <span className="text-[10px] text-slate-400 font-mono uppercase">{mod.module_key}</span>
                  </div>
                </div>

                <div className={`px-2.5 py-1 rounded-md text-xs font-black border ${getRiskColor(mod.risk_tier)}`}>
                  {mod.risk_tier}
                </div>
              </div>

              <p className="text-xs text-slate-400 mt-3 leading-relaxed line-clamp-2">
                {mod.description}
              </p>
            </div>

            {/* Metrics Breakdown */}
            <div className="p-5 space-y-4 text-xs">
              {/* Risk Score Meter */}
              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-slate-400 font-medium">Domain Risk Score:</span>
                  <span className="text-sm font-black text-rose-400 font-mono">{mod.risk_score} / 100</span>
                </div>
                <div className="w-full h-2 rounded-full bg-cyber-950 overflow-hidden border border-white/5">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-rose-500 to-rose-400 transition-all duration-500"
                    style={{ width: `${mod.risk_score}%` }}
                  />
                </div>
              </div>

              {/* Counts Grid */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                  <div className="text-[10px] text-slate-400">Targets</div>
                  <div className="text-base font-bold text-white mt-0.5">{mod.asset_count}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                  <div className="text-[10px] text-rose-400">Critical</div>
                  <div className="text-base font-bold text-rose-400 mt-0.5">{mod.critical_count}</div>
                </div>
                <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                  <div className="text-[10px] text-amber-400">High</div>
                  <div className="text-base font-bold text-amber-400 mt-0.5">{mod.high_count}</div>
                </div>
              </div>

              {/* Assessment Status */}
              <div className="space-y-1.5 pt-1 text-[11px] text-slate-400 border-t border-white/10">
                <div className="flex justify-between">
                  <span>Open Remediation Tasks:</span>
                  <strong className="text-white font-mono">{mod.open_remediation_count}</strong>
                </div>
                <div className="flex justify-between">
                  <span>Last Assessment:</span>
                  <strong className="text-slate-300">
                    {mod.latest_assessment ? new Date(mod.latest_assessment).toLocaleDateString() : 'Awaiting Run'}
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span>Next Automated Scan:</span>
                  <strong className="text-cyan-400">{mod.next_scheduled_assessment}</strong>
                </div>
              </div>
            </div>

            {/* Actions Footer */}
            <div className="p-3 bg-cyber-950/80 border-t border-white/10 flex items-center justify-between text-xs">
              <Link
                href={`/assets?empire_module=${mod.module_key}`}
                className="text-slate-400 hover:text-white font-medium flex items-center gap-1 transition"
              >
                <span>Targets ({mod.asset_count})</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
              <Link
                href={`/findings?module=${mod.module_key}`}
                className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-cyan-400 font-bold transition flex items-center gap-1 border border-white/10"
              >
                <span>{t('targets.findingsButton', 'View Findings')} ({mod.total_findings})</span>
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
