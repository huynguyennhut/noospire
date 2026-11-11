'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  CalendarClock,
  Play,
  Plus,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertCircle,
  X,
  Server,
  Layers,
  Power,
  Trash2,
  FileText,
} from 'lucide-react';

import { api } from '@/lib/api';
import { DailyScheduleItem } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { useToast } from '@/components/ui/toast';

export default function SchedulesPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const [schedules, setSchedules] = useState<DailyScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  // Form State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [profile, setProfile] = useState('DAILY_SECURITY');
  const [cron, setCron] = useState('0 2 * * *');
  const [tz, setTz] = useState('Asia/Ho_Chi_Minh');
  const [submitting, setSubmitting] = useState(false);

  const fetchSchedules = async () => {
    try {
      setLoading(true);
      const res = await api.listSchedules();
      const scheduleItems = Array.isArray(res) ? res : ((res as any)?.items || []);
      setSchedules(scheduleItems);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, []);

  const handleTrigger = async (id: string) => {
    try {
      setTriggeringId(id);
      const res = await api.triggerSchedule(id);
      await fetchSchedules();
      toast({
        title: 'Schedule Dispatched',
        description: `Daily assessment pipeline successfully triggered for target perimeter!`,
        variant: 'default',
        duration: 4000,
      });
    } catch (err) {
      toast({
        title: 'Trigger Failed',
        description: String(err),
        variant: 'destructive',
      });
    } finally {
      setTriggeringId(null);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      const updated = await api.toggleSchedule(id);
      await fetchSchedules();
      toast({
        title: 'Schedule Status Updated',
        description: `Schedule is now ${updated?.is_active ? 'ACTIVE' : 'PAUSED'}.`,
        variant: 'default',
        duration: 3000,
      });
    } catch (err) {
      toast({
        title: 'Toggle Failed',
        description: String(err),
        variant: 'destructive',
      });
    }
  };

  const handleDeleteSchedule = async (id: string, schedName: string) => {
    if (!confirm(`Are you sure you want to permanently delete schedule "${schedName}"?`)) return;
    try {
      await api.deleteSchedule(id);
      await fetchSchedules();
      toast({
        title: 'Schedule Deleted',
        description: `Schedule "${schedName}" was permanently removed.`,
        duration: 3000,
      });
    } catch (err) {
      toast({
        title: 'Delete Failed',
        description: String(err),
        variant: 'destructive',
      });
    }
  };


  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setSubmitting(true);
      await api.createSchedule({
        name,
        profile,
        cron_expression: cron,
        timezone: tz,
        is_active: true,
        target_ids: ['ALL'],
      });
      setIsModalOpen(false);
      setName('');
      await fetchSchedules();
      toast({
        title: 'Schedule Created',
        description: `New recurring schedule "${name}" successfully registered.`,
        variant: 'default',
        duration: 4000,
      });
    } catch (err) {
      toast({
        title: 'Create Failed',
        description: String(err),
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <CalendarClock className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('schedules.title', 'DAILY ASSESSMENT SCHEDULES')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('schedules.subtitle', 'Automated continuous security monitoring pipeline configured in Asia/Ho_Chi_Minh (ICT) timezone.')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 text-xs font-bold shadow-lg shadow-cyan-950/60 hover:from-cyan-400 hover:to-cyan-300 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{t('schedules.createButton', 'Create Schedule')}</span>
          </button>
        </div>
      </div>

      {/* Information Box */}
      <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md text-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="font-bold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-cyan-400" />
            <span>Configured Operating Timezone: <strong className="text-cyan-400 font-mono">Asia/Ho_Chi_Minh (UTC+7)</strong></span>
          </div>
          <p className="text-slate-400 text-[11px] mt-1">
            The daily pipeline verifies target availability, updates asset inventories, assesses Better-Auth routes, verifies the /media baseline, and correlates newly disclosed CVEs.
          </p>
        </div>
        <div className="px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 font-mono text-emerald-400 font-bold">
          Cron Daemon: ACTIVE
        </div>
      </div>

      {/* Schedules List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {schedules.map((sched) => (
          <div key={sched.id} className="rounded-2xl liquid-glass-card border border-white/10 p-5 shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-white/10">
                <div>
                  <h2 className="text-sm font-bold text-white">{sched.name}</h2>
                  <div className="text-[11px] text-cyan-400 font-mono mt-0.5">Profile: {sched.profile}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(sched.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-bold flex items-center gap-1.5 border transition ${
                      sched.is_active
                        ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800'
                        : 'bg-white/[0.04] text-slate-500 border-white/10'
                    }`}
                  >
                    <Power className="w-3 h-3" />
                    <span>{sched.is_active ? 'ACTIVE' : 'PAUSED'}</span>
                  </button>
                  <button
                    onClick={() => handleDeleteSchedule(sched.id, sched.name)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 border border-white/10 hover:border-rose-500/30 transition cursor-pointer"
                    title="Delete Schedule"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Cron Schedule:</span>
                  <span className="font-mono text-white font-bold">{sched.cron_expression} (02:00 AM ICT)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Target Scope:</span>
                  <strong className="text-cyan-400">
                    {sched.target_ids && sched.target_ids.length > 0 ? sched.target_ids.join(', ') : 'All 368 Targets'} (Entire Portfolio)
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Timezone:</span>
                  <span className="text-slate-300 font-mono">{sched.timezone}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Last Execution:</span>
                  <strong className="text-slate-300">
                    {sched.last_run_at ? new Date(sched.last_run_at).toLocaleString() : 'Pending Next Window'}
                  </strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Pipeline Status:</span>
                  <span className="px-2 py-0.2 rounded-md bg-white/[0.04] border border-white/10 text-emerald-400 font-mono text-[11px] font-bold">
                    {sched.last_status || 'READY'}
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-white/10 mt-4 flex flex-wrap items-center justify-between gap-2 text-xs">
              <Link
                href="/active-assessments"
                className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white transition flex items-center gap-1.5 text-xs font-semibold"
                title="View execution logs for scheduled runs"
              >
                <FileText className="w-3.5 h-3.5 text-cyan-400" />
                <span>View Execution Logs</span>
              </Link>
              <button
                onClick={() => handleTrigger(sched.id)}
                disabled={triggeringId === sched.id}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold transition flex items-center gap-1.5 shadow-md"
              >
                <Play className="w-3.5 h-3.5 fill-slate-950" />
                <span>{triggeringId === sched.id ? 'Launching Pipeline...' : 'Run Daily Pipeline Now'}</span>
              </button>
            </div>

          </div>
        ))}
      </div>

      {/* Modal: Create Schedule */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-2xl liquid-glass-modal p-6 shadow-2xl border border-white/15">
            <div className="flex items-center justify-between pb-4 border-b border-white/10">
              <h2 className="text-base font-bold text-white">Create Assessment Schedule</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSchedule} className="space-y-4 mt-4 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Schedule Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Daily Asia/Ho_Chi_Minh Pipeline"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-semibold mb-1">Assessment Profile</label>
                  <select
                    value={profile}
                    onChange={(e) => setProfile(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="DAILY_SECURITY">Daily Security Profile</option>
                    <option value="STANDARD">Standard Profile</option>
                    <option value="QUICK">Quick Profile</option>
                    <option value="AUTHENTICATED">Authenticated Profile</option>
                    <option value="INFRASTRUCTURE">Infrastructure Profile</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-semibold mb-1">Cron Expression</label>
                  <input
                    type="text"
                    required
                    value={cron}
                    onChange={(e) => setCron(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Timezone</label>
                <input
                  type="text"
                  required
                  value={tz}
                  onChange={(e) => setTz(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 font-mono"
                />
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
                  disabled={submitting}
                  className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 hover:from-cyan-400 hover:to-cyan-300 text-slate-950 font-bold transition shadow-md"
                >
                  {submitting ? 'Saving...' : 'Register Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
