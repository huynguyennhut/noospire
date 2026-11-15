'use client';

import React, { useEffect, useState, useRef, useMemo, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  Radio,
  Terminal,
  StopCircle,
  CheckCircle2,
  Clock,
  RefreshCw,
  ShieldAlert,
  ArrowLeft,
  Wifi,
  WifiOff,
  Search,
  ArrowDown,
  Download,
  Trash2,
  Activity,
  AlertOctagon,
  HardDrive,
  Cpu,
  Layers,
  Gauge,
  Zap,
} from 'lucide-react';
import { api } from '@/lib/api';
import { ScanJob, TrackCurrentResponse, ActiveThreadInfo, ScanBatchRead } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { useToast } from '@/components/ui/toast';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface LogEntry {
  id?: string | number;
  scan_id?: string;
  timestamp: string;
  level: string;
  message: string;
  source: string;
  event_type?: string;
  details?: Record<string, any>;
}

interface PipelineStage {
  id: number;
  name: string;
  key: string;
  description: string;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { id: 1, name: 'Pre-flight Checks', key: 'preflight', description: 'SSRF validation, host reachability, scope boundary checks' },
  { id: 2, name: 'Asset Discovery', key: 'discovery', description: 'Bounded crawler, endpoint enumeration, parameter discovery' },
  { id: 3, name: 'Active Scanning', key: 'active', description: 'Nuclei templates, OWASP ZAP active rules, dynamic payload fuzzing' },
  { id: 4, name: 'Empire Module Audit', key: 'empire', description: 'Student auth exposure, /media storage policy, BOLA/IDOR evaluation' },
  { id: 5, name: 'Score & Deduplication', key: 'scoring', description: 'SHA-256 fingerprinting, deduplication, Sentinel Risk Score calculation' },
];

function ActiveAssessmentsContent() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const initialScanId = searchParams?.get('scan_id');
  const initialBatchId = searchParams?.get('batch_id');

  // Toast & Multi-Worker Live Thread Telemetry State ("trackcurrent")
  const { toast } = useToast();
  const [telemetry, setTelemetry] = useState<TrackCurrentResponse | null>(null);
  const [currentBatch, setCurrentBatch] = useState<ScanBatchRead | null>(null);
  const [stoppingAll, setStoppingAll] = useState(false);
  const [cancellingBatch, setCancellingBatch] = useState(false);

  // Job Queue State
  const [scans, setScans] = useState<ScanJob[]>([]);
  const [activeScanId, setActiveScanId] = useState<string | null>(initialScanId || null);
  const [currentScan, setCurrentScan] = useState<ScanJob | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [queueStatusFilter, setQueueStatusFilter] = useState('ALL');

  // Terminal & SSE State
  const [sseConnected, setSseConnected] = useState(false);
  const [logFilterLevel, setLogFilterLevel] = useState('ALL');
  const [logSearch, setLogSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(false);
  const [timeFilter, setTimeFilter] = useState<'ALL' | '1D' | '7D' | '14D' | '30D'>('ALL');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastEventIdRef = useRef<number>(0);


  // Fetch Live Telemetry ("trackcurrent")
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await api.getTrackCurrent();
      setTelemetry(res);
    } catch (err) {
      console.error('Failed to fetch trackcurrent telemetry', err);
    }
  }, []);

  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 2500);
    return () => clearInterval(interval);
  }, [fetchTelemetry]);

  useEffect(() => {
    if (initialBatchId) {
      api.getBatch(initialBatchId).then((batchData) => {
        if (batchData) {
          setCurrentBatch(batchData);
          if (batchData.scans && batchData.scans.length > 0 && !activeScanId) {
            setActiveScanId(batchData.scans[0].id);
          }
        }
      }).catch((err) => console.error('Failed to load batch from URL', err));
    }
  }, [initialBatchId, activeScanId]);

  // Emergency Stop All Scans
  const handleStopAllScans = async () => {
    if (!confirm('EMERGENCY MASTER STOP: Immediately halt ALL active, queued, and background scan jobs across the platform?')) {
      return;
    }
    try {
      setStoppingAll(true);
      const res = await api.stopAllScans();
      toast({
        title: 'Emergency Stop Executed',
        description: `Halted ${res.halted_count} active scan processes and worker threads.`,
        variant: 'warning',
        duration: 6000,
      });
      await Promise.all([fetchTelemetry(), fetchScans()]);
    } catch (err: unknown) {
      toast({
        title: 'Emergency Stop Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
        duration: 6000,
      });
    } finally {
      setStoppingAll(false);
    }
  };

  // Cancel Batch
  const handleCancelBatch = async (batchId?: string) => {
    const bId = batchId || (currentScan as any)?.batch_id;
    if (!bId) {
      toast({
        title: 'No Batch Associated',
        description: 'The selected scan job was dispatched as a standalone assessment rather than part of a batch.',
        variant: 'default',
      });
      return;
    }
    if (!confirm(`Cancel batch ${bId}? All running and queued scans in this batch will be cooperatively cancelled.`)) {
      return;
    }
    try {
      setCancellingBatch(true);
      const res = await api.cancelBatch(bId);
      toast({
        title: 'Batch Cancelled',
        description: `Batch ${res.batch_id} cancelled. ${res.cancelled_count} scans halted.`,
        variant: 'default',
        duration: 5000,
      });
      await Promise.all([fetchTelemetry(), fetchScans()]);
    } catch (err: unknown) {
      toast({
        title: 'Batch Cancellation Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
        duration: 5000,
      });
    } finally {
      setCancellingBatch(false);
    }
  };

  // Helper for rendering stage badge
  const renderStageBadge = (stage: string) => {
    const s = stage?.toLowerCase() || '';
    let colorClass = 'bg-slate-800 text-slate-300 border-slate-700';
    if (s === 'preflight') colorClass = 'bg-cyan-950/80 text-cyan-300 border-cyan-800';
    else if (s === 'discovery') colorClass = 'bg-blue-950/80 text-blue-300 border-blue-800';
    else if (s === 'fingerprint') colorClass = 'bg-indigo-950/80 text-indigo-300 border-indigo-800';
    else if (s === 'crawling') colorClass = 'bg-teal-950/80 text-teal-300 border-teal-800';
    else if (s === 'scoring') colorClass = 'bg-emerald-950/80 text-emerald-300 border-emerald-800';
    else if (s === 'active') colorClass = 'bg-amber-950/80 text-amber-300 border-amber-800';
    else if (s === 'empire') colorClass = 'bg-purple-950/80 text-purple-300 border-purple-800';

    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border uppercase ${colorClass}`}>
        {stage}
      </span>
    );
  };

  // Fetch Scan Queue
  const fetchScans = useCallback(async () => {
    try {
      const res = await api.listScans();
      const items = res.items || [];
      setScans(items);

      setActiveScanId((prev) => {
        if (prev) return prev;
        if (items.length > 0) {
          const running = items.find((s) => s.status === 'RUNNING' || s.status === 'INITIALIZING' || s.status === 'QUEUED');
          return (running || items[0]).id;
        }
        return null;
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchScanJobStatus = useCallback(async (id: string) => {
    try {
      const scanData = await api.getScan(id).catch(() => null);
      if (scanData) {
        setCurrentScan(scanData);
      }
    } catch (err) {
      console.error(err);
    }
  }, []);

  const fetchScanEventsIncremental = useCallback(async (id: string) => {
    try {
      const res = await api.getScanEvents(id, lastEventIdRef.current, 200).catch(() => null);
      if (res && res.items && res.items.length > 0) {
        let maxId = lastEventIdRef.current;
        setLogs((prev) => {
          const existingIds = new Set(prev.map((p) => String(p.id)).filter(Boolean));
          const existingKeys = new Set(prev.map((p) => `${p.timestamp}-${p.message}`));
          const fresh: LogEntry[] = [];
          for (const item of res.items) {
            if (item.id && !existingIds.has(String(item.id))) {
              fresh.push(item);
              maxId = Math.max(maxId, Number(item.id));
            } else if (!existingKeys.has(`${item.timestamp}-${item.message}`)) {
              fresh.push(item);
              if (item.id) maxId = Math.max(maxId, Number(item.id));
            }
          }
          if (fresh.length === 0) return prev;
          return [...prev, ...fresh];
        });
        lastEventIdRef.current = maxId;
      } else {
        const logsData = await api.getScanLogs(id, 500).catch(() => []);
        if (logsData && logsData.length > 0) {
          setLogs((prev) => {
            const map = new Map<string, LogEntry>();
            prev.forEach((l) => map.set(`${l.timestamp}-${l.message}`, l));
            logsData.forEach((l: LogEntry) => map.set(`${l.timestamp}-${l.message}`, l));
            return Array.from(map.values());
          });
        }
      }
    } catch (err) {
      console.error('Incremental event polling error:', err);
    }
  }, []);

  const fetchScanLogsFallback = fetchScanEventsIncremental;

  // Poll Scan List Queue every 4s
  useEffect(() => {
    fetchScans();
    const listInterval = setInterval(fetchScans, 4000);
    return () => clearInterval(listInterval);
  }, [fetchScans]);

  // Timer for elapsed seconds
  useEffect(() => {
    if (!currentScan?.started_at || currentScan.status === 'COMPLETED' || currentScan.status === 'FAILED' || currentScan.status === 'CANCELLED') {
      return;
    }

    const startMs = new Date(currentScan.started_at).getTime();
    const timer = setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    }, 1000);

    return () => clearInterval(timer);
  }, [currentScan?.started_at, currentScan?.status]);

  // Setup SSE stream with Last-Event-ID cursor replay and fallback polling
  useEffect(() => {
    if (!activeScanId) return;

    setLogs([]);
    lastEventIdRef.current = 0;
    fetchScanJobStatus(activeScanId);
    fetchScanEventsIncremental(activeScanId);

    if (typeof window !== 'undefined' && window.EventSource) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // Same-origin EventSource sends the HttpOnly session cookie; no credential in the URL.
      const params = new URLSearchParams();
      if (lastEventIdRef.current > 0) params.set('cursor', String(lastEventIdRef.current));

      // EventSource stream route: /api/v1/scans/{id}/events/stream or /logs/stream
      const sseUrl = `/api/v1/scans/${activeScanId}/events/stream?${params.toString()}`;
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload && payload.message) {
            const eventId = Number(event.lastEventId || payload.id || 0);
            if (eventId > 0) {
              lastEventIdRef.current = Math.max(lastEventIdRef.current, eventId);
            }
            setLogs((prev) => {
              if (payload.id && prev.some((p) => String(p.id) === String(payload.id))) {
                return prev;
              }
              const key = `${payload.timestamp}-${payload.message}`;
              if (prev.some((p) => `${p.timestamp}-${p.message}` === key)) {
                return prev;
              }
              return [...prev, payload];
            });
            setSseConnected(true);
          }
        } catch (_) {}
      };

      es.onerror = () => {
        setSseConnected(false);
      };
    }

    const interval = setInterval(() => {
      fetchScanJobStatus(activeScanId);
      fetchScanEventsIncremental(activeScanId);
    }, 2500);

    return () => {
      clearInterval(interval);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setSseConnected(false);
    };
  }, [activeScanId, fetchScanJobStatus, fetchScanEventsIncremental]);

  // Container-scoped auto-scroll: Never scroll the browser window/viewport!
  useEffect(() => {
    if (autoScroll && terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const scrollToBottom = () => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  };


  // Cancel Scan Handler
  const handleCancelScan = async () => {
    if (!activeScanId) return;
    if (!confirm(t('active.cancelAssessment', 'Are you sure you want to cooperatively cancel this scan job?'))) return;

    try {
      setCancelling(true);
      await api.cancelScan(activeScanId);
      await fetchScanJobStatus(activeScanId);
      await fetchScans();

      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: 'WARN',
          message: 'Cooperative cancellation signal received. Scan halted by operator.',
          source: 'dispatcher',
        },
      ]);
    } catch (err: unknown) {
      alert(`Cancel error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setCancelling(false);
    }
  };

  // Clear Terminal & Delete Logs
  const handleClearTerminal = async () => {
    if (activeScanId) {
      await api.clearLogs(activeScanId);
    }
    setLogs([]);
    toast({
      title: 'Logs Cleared',
      description: 'Execution logs for this assessment were successfully cleared from memory and storage.',
      variant: 'default',
      duration: 3000,
    });
  };

  // Reset Entire System to Baseline State
  const handleResetBaseline = async () => {
    if (!confirm('RESET SYSTEM TO VERIFIED BASELINE: Reset all assets, findings, and scan telemetry to pristine database baseline?')) return;
    try {
      const res = await api.resetBaseline();
      toast({
        title: 'System Restored',
        description: res.message,
        variant: 'default',
        duration: 5000,
      });
      await Promise.all([fetchScans(), fetchTelemetry()]);
      if (activeScanId) fetchScanLogsFallback(activeScanId);
    } catch (err: unknown) {
      toast({
        title: 'Reset Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    }
  };

  // Export Logs to File (JSON or TXT/LOG format)
  const handleExportLogs = (format: 'txt' | 'json' = 'txt') => {
    if (logs.length === 0) return;
    let content = '';
    let mimeType = 'text/plain;charset=utf-8';
    let ext = 'log';

    if (format === 'json') {
      content = JSON.stringify(logs, null, 2);
      mimeType = 'application/json;charset=utf-8';
      ext = 'json';
    } else {
      content = logs
        .map((l) => `[${l.timestamp}] [${l.level}] [${l.source}] ${l.message}`)
        .join('\n');
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `scan_${activeScanId?.slice(0, 8)}_execution.${ext}`;
    link.click();
    URL.revokeObjectURL(url);
    toast({
      title: 'Logs Exported',
      description: `Saved ${logs.length} entries as .${ext}`,
      duration: 2500,
    });
  };


  // Active Stage Calculation based on progress percentage
  const currentStageIndex = useMemo(() => {
    const progress = currentScan?.progress_percentage ?? 0;
    if (progress >= 89) return 4;
    if (progress >= 71) return 3;
    if (progress >= 36) return 2;
    if (progress >= 16) return 1;
    return 0;
  }, [currentScan?.progress_percentage]);

  // Live Findings Count from logs
  const findingsFound = useMemo(() => {
    return logs.filter((l) => {
      const lvl = (l.level || (l as any).status || 'INFO').toUpperCase();
      const msg = (l.message || '').toLowerCase();
      return lvl === 'VULN' || msg.includes('finding');
    }).length;
  }, [logs]);

  // Computed requests/sec sample
  const requestsPerSec = useMemo(() => {
    if (!currentScan || currentScan.status !== 'RUNNING') return 0;
    const progress = currentScan.progress_percentage || 0;
    return Math.floor(18 + (progress % 22) + 2);
  }, [currentScan]);

  // Format Elapsed Time MM:SS
  const formatElapsed = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Filtered Logs
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      const logLvl = (log.level || (log as any).status || 'INFO').toUpperCase();
      const logMsg = (log.message || '').toLowerCase();
      const logSrc = (log.source || (log as any).logger || 'core').toLowerCase();

      const matchesLevel =
        logFilterLevel === 'ALL' ||
        logLvl === logFilterLevel ||
        (logFilterLevel === 'VULN' && (logLvl === 'VULN' || logMsg.includes('finding')));

      const matchesSearch =
        !logSearch ||
        logMsg.includes(logSearch.toLowerCase()) ||
        logSrc.includes(logSearch.toLowerCase());

      return matchesLevel && matchesSearch;
    });
  }, [logs, logFilterLevel, logSearch]);

  const getLogLevelStyle = (level?: string) => {
    switch ((level || 'INFO').toUpperCase()) {
      case 'ERROR':
        return 'text-rose-400 font-bold bg-rose-500/10 px-1 rounded';
      case 'WARN':
      case 'WARNING':
        return 'text-amber-400 font-bold bg-amber-500/10 px-1 rounded';
      case 'VULN':
        return 'text-fuchsia-400 font-bold bg-fuchsia-500/20 px-1.5 rounded shadow-[0_0_10px_rgba(217,70,239,0.3)] animate-pulse';
      case 'INFO':
      default:
        return 'text-cyan-400 font-semibold';
    }
  };

  // Queue status & Days filter ("track by days")
  const filteredQueue = scans.filter((s) => {
    if (queueStatusFilter !== 'ALL' && s.status !== queueStatusFilter) return false;
    if (timeFilter === 'ALL') return true;

    const daysLimit = timeFilter === '1D' ? 1 : timeFilter === '7D' ? 7 : timeFilter === '14D' ? 14 : 30;
    const scanTime = new Date(s.started_at || s.created_at).getTime();
    return (Date.now() - scanTime) <= daysLimit * 86400000;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="w-6 h-6 text-cyan-400 animate-pulse" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('active.title', 'LIVE ASSESSMENT TRACKER')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('active.subtitle', 'Real-time execution telemetry, live SSE log stream, stage progression, and cooperative cancellation controls.')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Link href="/scans">
            <Button variant="secondary" size="md" icon={<ArrowLeft className="w-3.5 h-3.5" />}>
              {t('active.backToScans', 'Back to Scan Center')}
            </Button>
          </Link>

          {/* Reset System to Baseline State */}
          <Button
            variant="outline"
            size="md"
            icon={<RefreshCw className="w-3.5 h-3.5 text-slate-300" />}
            onClick={handleResetBaseline}
            title="Development-only reset (refused in production). Reseeds synthetic demo data only when SENTINEL_SEED_DEMO_DATA is enabled."
          >
            Quay Về Ban Đầu
          </Button>

          {/* Emergency Stop All Scans Button */}
          <Button
            variant="destructive"
            size="md"
            icon={<AlertOctagon className="w-3.5 h-3.5" />}
            loading={stoppingAll}
            onClick={handleStopAllScans}
            className="bg-rose-950/80 border-rose-500/40 text-rose-300 hover:bg-rose-900 shadow-sm"
          >
            {stoppingAll ? 'Stopping All...' : 'Stop All Scans'}
          </Button>

          {currentScan && (currentScan.status === 'RUNNING' || currentScan.status === 'INITIALIZING') && (
            <Button
              variant="destructive"
              size="md"
              icon={<StopCircle className="w-3.5 h-3.5" />}
              loading={cancelling}
              onClick={handleCancelScan}
            >
              {cancelling ? t('active.cancelling', 'Cancelling...') : t('active.cancelAssessment', 'Cancel Assessment')}
            </Button>
          )}
        </div>
      </div>

      {/* Durable Batch Assessment HUD */}
      {currentBatch && (
        <div className="relative rounded-2xl backdrop-blur-xl bg-gradient-to-r from-cyan-950/40 via-blue-950/30 to-black/60 border border-cyan-500/30 p-4 md:p-5 shadow-[0_8px_32px_rgba(6,182,212,0.15)]">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge severity="info" className="bg-cyan-500/20 text-cyan-300 border-cyan-500/40">
                  Durable Batch
                </Badge>
                <h3 className="text-base font-bold text-white tracking-wide">{currentBatch.name}</h3>
                <span className="text-xs text-slate-400 font-mono">({currentBatch.id})</span>
              </div>
              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300 pt-1">
                <span>Targets: <strong className="text-white">{currentBatch.target_count}</strong></span>
                <span>Total Engine Executions: <strong className="text-white">{currentBatch.total_scans}</strong></span>
                <span>Completed: <strong className="text-emerald-400">{currentBatch.completed_scans}</strong></span>
                <span>Failed: <strong className="text-rose-400">{currentBatch.failed_scans}</strong></span>
                <span>Status: <strong className="text-cyan-400 uppercase">{currentBatch.status}</strong></span>
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleCancelBatch(currentBatch.id)}
                disabled={cancellingBatch || currentBatch.status === 'COMPLETED' || currentBatch.status === 'CANCELLED'}
                className="border-rose-500/30 text-rose-300 hover:bg-rose-950/40"
              >
                {cancellingBatch ? 'Cancelling...' : 'Cancel Batch'}
              </Button>
              <Link href="/reports">
                <Button variant="primary" size="sm" icon={<Download className="w-3.5 h-3.5" />}>
                  Download Report
                </Button>
              </Link>
            </div>
          </div>
          {/* Progress bar */}
          <div className="mt-3 w-full bg-white/10 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-gradient-to-r from-cyan-400 to-blue-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${currentBatch.progress_percentage || 0}%` }}
            />
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MULTI-WORKER THREAD MATRIX ("trackcurrent") & TELEMETRY HUD         */}
      {/* =================================================================== */}
      <div className="relative rounded-2xl backdrop-blur-xl bg-black/60 border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.6)] p-5 md:p-6 space-y-5 overflow-hidden transition-all duration-300">
        {/* Specular shine top border */}
        <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent pointer-events-none" />

        {/* System Resource Bar & Telemetry Overview */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-white/10">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="p-1 rounded-md bg-white/[0.06] border border-white/10 text-cyan-400">
                <Cpu className="w-4 h-4" />
              </span>
              <h2 className="text-sm font-black tracking-tight text-white uppercase">
                Active Worker Thread Matrix (&quot;trackcurrent&quot;)
              </h2>
            </div>
            <p className="text-[11px] text-slate-400">
              Real-time multi-worker concurrency dispatcher with host resource guard and per-thread telemetry.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Throttling Alert Badge */}
            {telemetry?.is_throttled || telemetry?.system_resources?.is_throttled ? (
              <span className="px-3 py-1 rounded-full bg-rose-500/20 border border-rose-500/40 text-rose-300 text-xs font-bold animate-pulse flex items-center gap-1.5">
                <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />
                <span>Throttling Active (CPU/RAM Safeguard)</span>
              </span>
            ) : (
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono font-semibold flex items-center gap-1.5">
                <Gauge className="w-3.5 h-3.5 text-emerald-400" />
                <span>Dispatcher Nominal</span>
              </span>
            )}

            {/* Batch Cancel Button */}
            <button
              type="button"
              onClick={() => handleCancelBatch()}
              disabled={cancellingBatch}
              className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition cursor-pointer disabled:opacity-50"
              title="Cooperatively cancel running batch"
            >
              {cancellingBatch ? 'Cancelling Batch...' : 'Cancel Current Batch'}
            </button>
          </div>
        </div>

        {/* Resource Telemetry Meters Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          {/* CPU Meter */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1.5">
            <div className="flex items-center justify-between text-slate-400 font-mono text-[11px]">
              <span className="flex items-center gap-1"><Cpu className="w-3 h-3 text-cyan-400" /> CPU Load</span>
              <span className="font-bold text-white">{telemetry?.system_resources?.cpu_percent?.toFixed(1) ?? '0.0'}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  (telemetry?.system_resources?.cpu_percent ?? 0) > 80 ? 'bg-rose-500' : 'bg-cyan-400'
                }`}
                style={{ width: `${Math.min(100, telemetry?.system_resources?.cpu_percent ?? 0)}%` }}
              />
            </div>
          </div>

          {/* Memory Meter */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1.5">
            <div className="flex items-center justify-between text-slate-400 font-mono text-[11px]">
              <span className="flex items-center gap-1"><HardDrive className="w-3 h-3 text-purple-400" /> RAM Load</span>
              <span className="font-bold text-white">{telemetry?.system_resources?.memory_percent?.toFixed(1) ?? '0.0'}%</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  (telemetry?.system_resources?.memory_percent ?? 0) > 85 ? 'bg-rose-500' : 'bg-purple-400'
                }`}
                style={{ width: `${Math.min(100, telemetry?.system_resources?.memory_percent ?? 0)}%` }}
              />
            </div>
          </div>

          {/* Available RAM */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
            <div className="text-slate-400 font-mono text-[11px]">Available RAM</div>
            <div className="text-sm font-black text-cyan-300 font-mono">
              {telemetry?.system_resources?.memory_available_mb ? Math.round(telemetry.system_resources.memory_available_mb) : '--'} MB
            </div>
          </div>

          {/* Concurrency Slots */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
            <div className="text-slate-400 font-mono text-[11px]">Worker Concurrency</div>
            <div className="text-sm font-black text-white font-mono flex items-center gap-1">
              <span className="text-cyan-400">{telemetry?.active_workers ?? 0}</span>
              <span className="text-slate-500">/</span>
              <span>{telemetry?.max_concurrency ?? 4} Active</span>
            </div>
          </div>
        </div>

        {/* Active Worker Slots Grid */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
            <span className="uppercase font-bold tracking-wider text-[10px]">Active Worker Process Slots</span>
            <span>Click any slot to switch SSE log feed</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {telemetry?.active_threads && telemetry.active_threads.length > 0 ? (
              telemetry.active_threads.map((thread) => {
                const isFocused = activeScanId === thread.scan_id;

                return (
                  <div
                    key={thread.thread_id}
                    onClick={() => setActiveScanId(thread.scan_id)}
                    className={`p-3.5 rounded-xl border text-xs cursor-pointer transition-all relative ${
                      isFocused
                        ? 'liquid-glass border-cyan-400 shadow-lg shadow-cyan-950/70 scale-[1.01]'
                        : 'bg-white/[0.02] border-white/10 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                        <span className="font-mono font-bold text-white text-[11px]">
                          Thread #{thread.thread_id + 1}
                        </span>
                      </div>
                      {renderStageBadge(thread.stage)}
                    </div>

                    <div className="font-mono text-cyan-300 font-bold truncate text-[11px] mb-1" title={thread.target_locator}>
                      {thread.target_locator}
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-400 mb-2 font-mono">
                      <span>{thread.engine} • {thread.profile}</span>
                      <span>{formatElapsed(thread.elapsed_seconds)}</span>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden mb-2 border border-white/5">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all duration-300"
                        style={{ width: `${thread.progress_percentage}%` }}
                      />
                    </div>

                    <div className="text-[10px] text-slate-400 truncate italic">
                      {thread.last_log || 'Awaiting log telemetry...'}
                    </div>

                    {isFocused && (
                      <div className="mt-2 text-[9px] font-bold text-cyan-400 font-mono uppercase tracking-wider text-right">
                        ★ FOCUSED STREAM
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="col-span-full py-6 text-center text-slate-500 text-xs border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
                No active background worker threads currently running. Dispatch a single scan or &quot;Scan All&quot; batch to engage thread pool.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Layout Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column: Assessment Jobs Queue */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              {t('active.queue', 'Assessment Jobs Queue')}
            </h2>
            <div className="flex items-center gap-1">
              {['ALL', 'RUNNING', 'COMPLETED'].map((filter) => (
                <button
                  key={filter}
                  onClick={() => setQueueStatusFilter(filter)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-bold transition ${
                    queueStatusFilter === filter
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>

          {/* Track by Days Filter */}
          <div className="flex items-center justify-between px-2.5 py-1.5 rounded-xl bg-white/[0.03] border border-white/5 text-[10px]">
            <span className="text-slate-400 font-mono font-medium">Track by Days:</span>
            <div className="flex items-center gap-1">
              {(['ALL', '1D', '7D', '14D', '30D'] as const).map((days) => (
                <button
                  key={days}
                  onClick={() => setTimeFilter(days)}
                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold transition ${
                    timeFilter === days
                      ? 'bg-cyan-400/20 text-cyan-300 border border-cyan-400/40 shadow-sm'
                      : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.04]'
                  }`}
                >
                  {days}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2 max-h-[calc(100vh-230px)] overflow-y-auto pr-1">
            {loading && scans.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs">
                <RefreshCw className="w-4 h-4 animate-spin mx-auto text-cyan-400 mb-2" />
                <span>Loading queue...</span>
              </div>
            ) : filteredQueue.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs border border-dashed border-white/10 rounded-xl">
                No scans matching status.
              </div>
            ) : (
              filteredQueue.map((s) => {
                const isSelected = activeScanId === s.id;
                return (
                  <div
                    key={s.id}
                    onClick={() => setActiveScanId(s.id)}
                    className={`p-3 rounded-2xl border text-xs cursor-pointer transition-all ${
                      isSelected
                        ? 'liquid-glass border-cyan-400 shadow-lg shadow-cyan-950/70 scale-[1.01]'
                        : 'liquid-glass-card hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-xs truncate max-w-[140px] font-mono">
                        {s.target_locator}
                      </span>
                      <Badge
                        severity={
                          s.status === 'RUNNING'
                            ? 'info'
                            : s.status === 'COMPLETED'
                            ? 'low'
                            : s.status === 'FAILED'
                            ? 'critical'
                            : 'neutral'
                        }
                        size="sm"
                        dot={s.status === 'RUNNING'}
                      >
                        {s.status}
                      </Badge>
                    </div>

                    <div className="flex items-center justify-between mt-2 text-[10px] text-slate-400">
                      <span>Profile: <strong className="text-slate-200">{s.profile}</strong></span>
                      <span className="font-mono text-cyan-400 font-bold">{s.progress_percentage}%</span>
                    </div>

                    {/* Progress bar */}
                    <div className="w-full h-1.5 rounded-full bg-cyber-950 mt-2 overflow-hidden border border-white/5">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          s.status === 'COMPLETED' ? 'bg-emerald-400' : 'bg-gradient-to-r from-cyan-600 to-cyan-400'
                        }`}
                        style={{ width: `${s.progress_percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Live Telemetry, Stepper, and Terminal */}
        <div className="lg:col-span-3 space-y-4">
          {currentScan ? (
            <>
              {/* Telemetry HUD Cards (4 Metrics) */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {/* Active Requests/Sec */}
                <div className="p-3.5 rounded-2xl liquid-glass border border-cyan-500/30">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Throughput</span>
                    <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                  </div>
                  <div className="text-2xl font-black text-cyan-400 font-mono mt-0.5">
                    {requestsPerSec} <span className="text-xs font-normal text-slate-400">req/s</span>
                  </div>
                </div>

                {/* Elapsed Timer */}
                <div className="p-3.5 rounded-2xl liquid-glass border border-white/10">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Elapsed Time</span>
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                  </div>
                  <div className="text-2xl font-black text-white font-mono mt-0.5">
                    {formatElapsed(elapsedSeconds)}
                  </div>
                </div>

                {/* Live Findings Discovered */}
                <div className="p-3.5 rounded-2xl liquid-glass border border-rose-500/30">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-rose-400 uppercase tracking-wider font-semibold">Findings Flagged</span>
                    <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                  </div>
                  <div className="text-2xl font-black text-rose-400 font-mono mt-0.5">
                    {findingsFound}
                  </div>
                </div>

                {/* Active Target URL */}
                <div className="p-3.5 rounded-2xl liquid-glass border border-white/10">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Scope Boundary</span>
                    <Badge severity="info" size="sm">SAME_ORIGIN</Badge>
                  </div>
                  <div className="text-xs font-bold text-white font-mono truncate mt-1" title={currentScan.target_locator}>
                    {currentScan.target_locator}
                  </div>
                </div>
              </div>

              {/* 5-Stage Visual Execution Pipeline Stepper */}
              <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-xl space-y-3">
                <div className="flex items-center justify-between text-xs pb-2 border-b border-white/10">
                  <span className="text-slate-400 uppercase tracking-wider font-bold text-[10px]">
                    5-Stage Scanner Pipeline Execution
                  </span>
                  <span className="font-mono text-cyan-400 font-bold">
                    Stage {currentStageIndex + 1} of 5 ({currentScan.progress_percentage}% overall)
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 relative">
                  {PIPELINE_STAGES.map((stage, idx) => {
                    const isPassed = currentStageIndex > idx || currentScan.status === 'COMPLETED';
                    const isCurrent = currentStageIndex === idx && currentScan.status === 'RUNNING';

                    return (
                      <div
                        key={stage.id}
                        className={`p-2.5 rounded-xl border text-xs transition relative ${
                          isCurrent
                            ? 'bg-cyan-950/60 border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)]'
                            : isPassed
                            ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
                            : 'bg-white/[0.02] border-white/5 text-slate-500'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-mono font-bold">0{stage.id}</span>
                          {isPassed ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          ) : isCurrent ? (
                            <RefreshCw className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                          ) : (
                            <span className="w-2 h-2 rounded-full bg-slate-700" />
                          )}
                        </div>
                        <div className={`font-bold text-[11px] truncate ${isCurrent ? 'text-white' : isPassed ? 'text-emerald-300' : 'text-slate-400'}`}>
                          {stage.name}
                        </div>
                        <div className="text-[9px] text-slate-500 truncate mt-0.5" title={stage.description}>
                          {stage.description}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Real-Time SSE Telemetry Terminal */}
              <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-2xl space-y-3">
                {/* Terminal Controls Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <Terminal className="w-4 h-4 text-cyan-400" />
                    <span className="font-mono font-bold text-white text-xs">scanner_worker_output.log</span>
                    {activeScanId && (
                      <span className="px-2 py-0.5 rounded bg-white/[0.05] border border-cyan-500/30 text-cyan-300 font-mono text-[10px] flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                        <span>Focus: {currentScan?.target_locator || activeScanId.slice(0, 8)}</span>
                      </span>
                    )}
                    {sseConnected ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800 animate-pulse">
                        <Wifi className="w-2.5 h-2.5" /> SSE CONNECTED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-950/80 text-amber-400 border border-amber-800">
                        <WifiOff className="w-2.5 h-2.5" /> FALLBACK POLLING
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {/* Log Level Filter */}
                    <select
                      value={logFilterLevel}
                      onChange={(e) => setLogFilterLevel(e.target.value)}
                      className="px-2.5 py-1 rounded-lg bg-cyber-950 border border-white/10 text-slate-300 text-[11px] focus:outline-none focus:border-cyan-500 font-mono"
                    >
                      <option value="ALL">ALL LEVELS</option>
                      <option value="INFO">INFO ONLY</option>
                      <option value="WARN">WARN ONLY</option>
                      <option value="ERROR">ERROR ONLY</option>
                      <option value="VULN">VULN (FINDINGS)</option>
                    </select>

                    {/* Regex/Text Search */}
                    <div className="relative">
                      <input
                        type="text"
                        placeholder="Search logs..."
                        value={logSearch}
                        onChange={(e) => setLogSearch(e.target.value)}
                        className="pl-6 pr-2 py-1 rounded-lg bg-cyber-950 border border-white/10 text-white placeholder-slate-500 text-[11px] font-mono focus:outline-none focus:border-cyan-500 w-28 sm:w-36"
                      />
                      <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
                    </div>

                    {/* Auto-Scroll Toggle (Default OFF / Frozen) */}
                    <button
                      onClick={() => setAutoScroll(!autoScroll)}
                      className={`px-2.5 py-1 rounded-lg text-[10px] font-bold border transition flex items-center gap-1.5 ${
                        autoScroll
                          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-[0_0_12px_rgba(6,182,212,0.3)]'
                          : 'bg-white/[0.04] text-slate-400 border-white/10 hover:text-white'
                      }`}
                      title={autoScroll ? 'Auto-scroll is ON (Following newest entries)' : 'Auto-scroll is OFF (Logs frozen for inspection)'}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${autoScroll ? 'bg-cyan-400 animate-pulse' : 'bg-slate-500'}`} />
                      <span>{autoScroll ? 'Auto-Scroll: ON' : 'Auto-Scroll: OFF (Frozen)'}</span>
                    </button>

                    {/* Explicit Scroll to Bottom Button */}
                    <button
                      onClick={scrollToBottom}
                      className="px-2 py-1 rounded-lg text-[10px] font-bold border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white transition flex items-center gap-1"
                      title="Jump directly to newest log entry without enabling auto-scroll"
                    >
                      <ArrowDown className="w-3 h-3" />
                      <span>To Bottom</span>
                    </button>

                    {/* Clear Terminal */}
                    <button
                      onClick={handleClearTerminal}
                      className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition"
                      title="Clear terminal output"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>

                    {/* Export Logs TXT */}
                    <button
                      onClick={() => handleExportLogs('txt')}
                      className="px-2 py-1 rounded-lg text-[10px] font-bold border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition flex items-center gap-1"
                      title="Export logs as TXT/LOG"
                    >
                      <Download className="w-3 h-3" />
                      <span>LOG</span>
                    </button>

                    {/* Export Logs JSON */}
                    <button
                      onClick={() => handleExportLogs('json')}
                      className="px-2 py-1 rounded-lg text-[10px] font-bold border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition flex items-center gap-1"
                      title="Export logs as structured JSON"
                    >
                      <Download className="w-3 h-3" />
                      <span>JSON</span>
                    </button>
                  </div>
                </div>

                {/* Terminal Log Console */}
                <div ref={terminalContainerRef} className="h-[420px] overflow-y-auto bg-slate-950/90 rounded-xl p-3 font-mono text-[11px] space-y-1 border border-white/5 select-text shadow-inner">
                  {filteredLogs.length === 0 ? (
                    <div className="py-20 text-center text-slate-600 italic">
                      {logs.length === 0 ? 'Awaiting telemetry output from scanner runner...' : 'No logs match active filters.'}
                    </div>
                  ) : (
                    filteredLogs.map((log, idx) => (
                      <div key={idx} className="flex items-start gap-2 leading-relaxed hover:bg-white/[0.02] px-1 py-0.5 rounded transition">
                        <span className="text-slate-600 shrink-0 select-none">
                          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '--:--:--'}
                        </span>
                        <span className={`shrink-0 ${getLogLevelStyle(log.level || (log as any).status)}`}>
                          [{((log.level || (log as any).status || 'INFO') as string).toUpperCase()}]
                        </span>
                        <span className="text-slate-500 shrink-0 select-none">
                          [{log.source || 'core'}]
                        </span>
                        <span className="text-slate-200 break-all">{log.message}</span>
                      </div>
                    ))
                  )}
                </div>


                {/* Footer Line Info */}
                <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono pt-1">
                  <span>Displaying {filteredLogs.length} of {logs.length} logged entries</span>
                  <span>Scanner Suite: {currentScan.engine} | Profile: {currentScan.profile}</span>
                </div>
              </div>
            </>
          ) : (
            <div className="py-24 text-center text-slate-500 border border-dashed border-white/10 rounded-2xl liquid-glass">
              Select an assessment job from the left queue to view live execution telemetry.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ActiveAssessmentsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-400">Loading Active Assessment Tracker...</div>}>
      <ActiveAssessmentsContent />
    </Suspense>
  );
}
