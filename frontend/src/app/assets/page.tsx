'use client';

import React, { useEffect, useState, useMemo, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  Server,
  Plus,
  Search,
  ShieldCheck,
  Clock,
  Trash2,
  Play,
  Globe,
  Radio,
  Box,
  RefreshCw,
  X,
  CheckCircle,
  AlertTriangle,
  UploadCloud,
  ExternalLink,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Lock,
  Eye,
  FileCode,
  Check,
} from 'lucide-react';
import { api, ExecutionDetail } from '@/lib/api';
import { assessmentEligible, assessmentLabel } from '@/lib/assessment';
import { Asset, AssetType, CriticalityTier, EmpireModuleType } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import TargetVerificationModal from '@/components/verification/TargetVerificationModal';

type SortField = 'name' | 'type' | 'status' | 'criticality' | 'findings' | 'created_at';
type SortOrder = 'asc' | 'desc';

interface BulkPreviewItem {
  target_locator: string;
  name: string;
  asset_type: string;
  empire_module: string;
  environment: string;
  criticality: string;
  is_duplicate: boolean;
  existing_asset_id: string | null;
  reason: string | null;
}

// =============================================================================
// TARGET PROFILE DRAWER DYNAMIC DATA HELPERS
// =============================================================================

interface ContextualEndpoint {
  method: 'GET' | 'POST' | 'HEAD' | 'PUT' | 'DELETE';
  path: string;
  fullUrl: string;
  status: string;
  statusCode?: number | null;
  statusSeverity: 'low' | 'info' | 'medium' | 'high' | 'neutral';
  classification: string;
  classificationSeverity: 'critical' | 'high' | 'medium' | 'low' | 'info' | 'neutral';
  isExcluded: boolean;
  description: string;
}

function generateContextualEndpoints(asset: Asset): ContextualEndpoint[] {
  // Configured locators are inventory, not observations. Never synthesize health,
  // auth or module URLs and never invent HTTP status codes for them.
  const candidates = [
    { url: asset.target_locator, classification: 'REGISTERED_TARGET' },
    { url: asset.assessment_policy?.public_web?.url, classification: 'APPROVED_PUBLIC_WEB' },
    { url: asset.assessment_policy?.health_check?.url, classification: 'APPROVED_HEALTH' },
  ];
  const seen = new Set<string>();
  const endpoints: ContextualEndpoint[] = [];
  for (const item of candidates) {
    if (typeof item.url !== 'string' || !/^https?:\/\//.test(item.url) || seen.has(item.url)) continue;
    seen.add(item.url);
    try {
      const url = new URL(item.url);
      if (url.username || url.password) continue;
      endpoints.push({ method: 'HEAD', path: url.pathname, fullUrl: item.url,
        status: 'NOT_OBSERVED', statusSeverity: 'neutral', classification: item.classification,
        classificationSeverity: 'neutral', isExcluded: (asset.excluded_endpoints || []).includes(url.pathname),
        description: 'Configured locator. See engine runs for timestamped HTTP observations and coverage limits.' });
    } catch { /* Non-web inventory is not an HTTP endpoint. */ }
  }
  return endpoints;
}

function TargetsContent() {
  const { t, locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => vi ? a : b;
  const searchParams = useSearchParams();
  const initialModule = searchParams.get('empire_module');

  // Asset Inventory State
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inventoryFilter, setInventoryFilter] = useState(searchParams.get('inventory') === 'all' ? 'all' : 'eligible');
  const [summaries, setSummaries] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  // Filters & Sorting State
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [moduleFilter, setModuleFilter] = useState<string>(initialModule || 'ALL');
  const [envFilter, setEnvFilter] = useState<string>('ALL');

  useEffect(() => {
    const mod = searchParams.get('empire_module');
    if (mod) {
      setModuleFilter(mod);
    }
  }, [searchParams]);
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Drawer & Modals State
  const [selectedAssetForDrawer, setSelectedAssetForDrawer] = useState<Asset | null>(null);
  const [drawerTab, setDrawerTab] = useState('overview');
  const [drawerScans, setDrawerScans] = useState<any[]>([]);
  const [drawerExecutions, setDrawerExecutions] = useState<ExecutionDetail[]>([]);
  const [drawerFindings, setDrawerFindings] = useState<any[]>([]);
  const [loadingDrawerData, setLoadingDrawerData] = useState(false);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [selectedVerifyAsset, setSelectedVerifyAsset] = useState<Asset | null>(null);

  // Single Target Form State
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<AssetType>('WEB_APP');
  const [formTarget, setFormTarget] = useState('');
  const [formModule, setFormModule] = useState<EmpireModuleType>('STUDENT_MANAGEMENT');
  const [formEnv, setFormEnv] = useState('PRODUCTION');
  const [formTech, setFormTech] = useState('Better-Auth / Web Service');
  const [formCriticality, setFormCriticality] = useState<CriticalityTier>('MEDIUM');
  const [formApprovedMedia, setFormApprovedMedia] = useState(false);
  const [formExcludedEndpoints, setFormExcludedEndpoints] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Bulk Import State
  const [bulkImportType, setBulkImportType] = useState('AUTO');
  const [bulkContent, setBulkContent] = useState('');
  const [bulkPreviewData, setBulkPreviewData] = useState<{ total: number; new: BulkPreviewItem[]; duplicate: BulkPreviewItem[] } | null>(null);
  const [previewingBulk, setPreviewingBulk] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);

  const fetchAssets = useCallback(async () => {
    try {
      setLoading(true);
      const items = await api.listAllAssets();
      setLoadError(null);
      setAssets(items);

      // Hydrate summary metrics for top assets
      items.slice(0, 25).forEach(async (a) => {
        try {
          const sum = await api.getAssetSummary(a.id);
          setSummaries((prev) => ({ ...prev, [a.id]: sum }));
        } catch (_) {}
      });
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  // Load Drawer Data when asset is selected
  useEffect(() => {
    if (!selectedAssetForDrawer) return;

    const loadDrawerDetails = async () => {
      try {
        setLoadingDrawerData(true);
        const [scansRes, findingsRes, executionsRes] = await Promise.all([
          api.request(`/scans?asset_id=${selectedAssetForDrawer.id}&size=20`).catch(() => ({ items: [] })),
          api.listFindings({ assetId: selectedAssetForDrawer.id }),
          api.listExecutions({ assetId: selectedAssetForDrawer.id, size: 20 }),
        ]);
        setDrawerScans(scansRes.items || []);
        setDrawerExecutions(executionsRes.items);
        setDrawerFindings(findingsRes.items || []);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingDrawerData(false);
      }
    };

    loadDrawerDetails();
  }, [selectedAssetForDrawer]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  // Filtered & Sorted Assets
  const filteredAndSortedAssets = useMemo(() => {
    return assets
      .filter((a) => {
        const matchesSearch =
          !searchTerm ||
          a.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          a.target_locator.toLowerCase().includes(searchTerm.toLowerCase()) ||
          a.technology.toLowerCase().includes(searchTerm.toLowerCase()) ||
          a.tags.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase()));

        const matchesStatus = statusFilter === 'ALL' || a.verification_status === statusFilter;
        const matchesModule = moduleFilter === 'ALL' || a.empire_module === moduleFilter;
        const matchesEnv = envFilter === 'ALL' || a.environment === envFilter;
        const matchesType = typeFilter === 'ALL' || a.asset_type === typeFilter;

        const matchesInventory = inventoryFilter === 'all' || (inventoryFilter === 'eligible' ? assessmentEligible(a) : !assessmentEligible(a));
        return matchesInventory && matchesSearch && matchesStatus && matchesModule && matchesEnv && matchesType;
      })
      .sort((a, b) => {
        let compare = 0;
        switch (sortField) {
          case 'name':
            compare = a.name.localeCompare(b.name);
            break;
          case 'type':
            compare = a.asset_type.localeCompare(b.asset_type);
            break;
          case 'status':
            compare = (a.verification_status || '').localeCompare(b.verification_status || '');
            break;
          case 'criticality': {
            const weight: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
            compare = (weight[a.criticality] || 0) - (weight[b.criticality] || 0);
            break;
          }
          case 'findings': {
            const countA = summaries[a.id]?.open_findings ?? (a.open_findings ?? 0);
            const countB = summaries[b.id]?.open_findings ?? (b.open_findings ?? 0);
            compare = countA - countB;
            break;
          }
          case 'created_at':
          default:
            compare = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
            break;
        }
        return sortOrder === 'asc' ? compare : -compare;
      });
  }, [assets, inventoryFilter, searchTerm, statusFilter, moduleFilter, envFilter, typeFilter, sortField, sortOrder, summaries]);

  // Single Target Create Handler
  const handleCreateAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim() || !formTarget.trim()) return;

    let locator = formTarget.trim();
    if (!locator.startsWith('http://') && !locator.startsWith('https://')) {
      locator = `https://${locator}`;
    }

    try {
      setSubmitting(true);
      const excluded = formExcludedEndpoints
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      const newAsset = await api.createAsset({
        name: formName.trim(),
        asset_type: formType,
        target_locator: locator,
        empire_module: formModule,
        environment: formEnv,
        technology: formTech,
        criticality: formCriticality,
        approved_media_baseline: formApprovedMedia,
        description: formDescription.trim() || undefined,
        excluded_endpoints: excluded,
        tags: ['empire', formModule.toLowerCase(), formEnv.toLowerCase()],
      });

      setFormName('');
      setFormTarget('');
      setFormDescription('');
      setFormExcludedEndpoints('');
      setIsCreateModalOpen(false);
      await fetchAssets();

      if (confirm(`Target "${newAsset.name}" registered successfully! Open ownership verification now?`)) {
        setSelectedVerifyAsset(newAsset);
      }
    } catch (err: unknown) {
      alert(`Target registration failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSubmitting(false);
    }
  };

  // Bulk Preview Handler
  const handlePreviewBulk = async () => {
    if (!bulkContent.trim()) return;
    try {
      setPreviewingBulk(true);
      // POST /api/v1/assets/bulk-preview
      const data = await api.request('/assets/bulk-preview', {
        method: 'POST',
        body: JSON.stringify({
          import_type: bulkImportType,
          raw_content: bulkContent,
        }),
      });
      setBulkPreviewData(data);
    } catch (err: unknown) {
      alert(`Bulk preview error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPreviewingBulk(false);
    }
  };

  // Bulk Commit Handler
  const handleCommitBulkImport = async () => {
    if (!bulkContent.trim()) return;
    try {
      setBulkImporting(true);
      const res = await api.bulkImportAssets({
        import_type: bulkImportType,
        raw_content: bulkContent,
      });

      alert(`Bulk import completed: ${res.imported_count} targets imported, ${res.skipped_duplicates} duplicates skipped.`);
      setBulkPreviewData(null);
      setBulkContent('');
      setIsBulkModalOpen(false);
      await fetchAssets();
    } catch (err: unknown) {
      alert(`Bulk import commit failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBulkImporting(false);
    }
  };

  // Preview the same server plan used by recurring schedules.
  const handleScanNow = (asset: Asset) => {
    if (!assessmentEligible(asset)) return;
    window.location.href = `/scans/?asset=${encodeURIComponent(asset.id)}`;
  };

  // Delete Target Handler
  const handleDelete = async (id: string, name: string) => {
    if (!confirm(t('targets.deleteConfirm', `Are you sure you want to remove target "${name}" from active management?`))) return;
    try {
      await api.deleteAsset(id);
      if (selectedAssetForDrawer?.id === id) {
        setSelectedAssetForDrawer(null);
      }
      await fetchAssets();
    } catch (err: unknown) {
      alert(`Delete failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const getModuleBadgeColor = (mod: string) => {
    switch (mod) {
      case 'STUDENT_MANAGEMENT':
        return 'bg-purple-950/80 text-purple-300 border-purple-800/80';
      case 'LEARNING_MATERIALS':
        return 'bg-blue-950/80 text-blue-300 border-blue-800/80';
      case 'SUPPORTING_TOOLS':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80';
      case 'API_SERVICES':
        return 'bg-cyan-950/80 text-cyan-300 border-cyan-800/80';
      case 'WEB_APPLICATION':
        return 'bg-amber-950/80 text-amber-300 border-amber-800/80';
      default:
        return 'bg-[var(--bg-surface)]/80 text-[var(--text-primary)] border-[var(--border-subtle)]/80';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'DOMAIN':
        return <Globe className="w-3.5 h-3.5 text-sky-400" />;
      case 'API_ENDPOINT':
        return <FileCode className="w-3.5 h-3.5 text-cyan-400" />;
      case 'SERVER':
        return <Server className="w-3.5 h-3.5 text-purple-400" />;
      case 'OBJECT_STORAGE':
        return <Box className="w-3.5 h-3.5 text-amber-400" />;
      case 'WEB_APP':
      default:
        return <Radio className="w-3.5 h-3.5 text-emerald-400" />;
    }
  };

  // Summary Counters
  const verifiedCount = assets.filter((a) => (a.verification_state || a.verification_status) === 'VERIFIED').length;
  const unprovenCount = assets.filter((a) => a.verification_state === 'UNPROVEN').length;
  const pendingCount = assets.filter((a) => a.verification_status === 'PENDING').length;
  const failedCount = assets.filter((a) => a.verification_status === 'FAILED').length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-6 h-6 text-cyan-400" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('targets.title', 'EMPIRE TARGET MANAGEMENT')}
            </h1>
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            {t('targets.subtitle', 'Register, import, configure, and monitor Empire application attack surface across functional business modules.')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="md"
            icon={<UploadCloud className="w-3.5 h-3.5 text-cyan-400" />}
            onClick={() => {
              setBulkPreviewData(null);
              setIsBulkModalOpen(true);
            }}
          >
            {t('targets.bulkImport', 'Bulk Import Targets')}
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Plus className="w-3.5 h-3.5 text-slate-950" />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            {t('targets.registerTarget', 'Register Target')}
          </Button>
        </div>
      </div>

      {/* Target Inventory KPI Quick-Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-2xl liquid-glass border border-white/10">
          <div className="text-[10px] text-[var(--text-secondary)] uppercase tracking-wider font-semibold">Total Targets</div>
          <div className="text-2xl font-black text-white font-mono mt-0.5">{assets.length}</div>
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-emerald-500/30">
          <div className="text-[10px] text-emerald-400 uppercase tracking-wider font-semibold">Verified Scope</div>
          <div className="text-2xl font-black text-emerald-400 font-mono mt-0.5">{verifiedCount}</div>
          {unprovenCount > 0 && <div className="text-[10px] text-amber-300 font-mono">+{unprovenCount} UNPROVEN (no ownership proof)</div>}
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-amber-500/30">
          <div className="text-[10px] text-amber-400 uppercase tracking-wider font-semibold">Pending Verification</div>
          <div className="text-2xl font-black text-amber-400 font-mono mt-0.5">{pendingCount}</div>
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-rose-500/30">
          <div className="text-[10px] text-rose-400 uppercase tracking-wider font-semibold">Verification failed</div>
          <div className="text-2xl font-black text-rose-400 font-mono mt-0.5">{failedCount}</div>
        </div>
      </div>

      {loadError && <div className="assessment-alert" role="alert">{loadError}<button className="ml-3 underline" onClick={() => void fetchAssets()}>{L('Thử lại', 'Retry')}</button></div>}
      <div className="assessment-panel flex flex-wrap items-center gap-3 text-sm">
        <label htmlFor="inventory-filter">{L('Nguồn kiểm kê', 'Inventory admission')}</label>
        <select id="inventory-filter" value={inventoryFilter} onChange={(e) => setInventoryFilter(e.target.value)} className="assessment-input">
          <option value="eligible">{L('Đủ điều kiện đánh giá', 'Eligible for assessment')} ({assets.filter(assessmentEligible).length})</option>
          <option value="excluded">{L('Mẫu / cần đối chiếu', 'Test / reconciliation required')} ({assets.filter((a) => !assessmentEligible(a)).length})</option>
          <option value="all">{L('Toàn bộ bản ghi', 'All records')} ({assets.length})</option>
        </select>
        <span className="assessment-muted">{L('Dữ liệu kiểm thử được giữ lại và loại khỏi quét khách hàng.', 'Test records are retained and excluded from customer assessments.')}</span>
      </div>
      {/* Filter & Search Bar */}
      <div className="p-3.5 rounded-2xl liquid-glass-card flex flex-col lg:flex-row gap-3 items-center justify-between text-xs">
        <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto">
          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-[var(--text-secondary)] absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder={t('targets.searchPlaceholder', 'Search targets, URLs, tech...')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 text-xs"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">All Statuses</option>
            <option value="VERIFIED">Verified</option>
            <option value="PENDING">Pending</option>
            <option value="FAILED">Failed</option>
          </select>

          <select
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('targets.allModules', 'All Empire Modules')}</option>
            <option value="STUDENT_MANAGEMENT">Student Management</option>
            <option value="LEARNING_MATERIALS">Learning Materials (/media)</option>
            <option value="SUPPORTING_TOOLS">Supporting Tools</option>
            <option value="API_SERVICES">API Services</option>
            <option value="WEB_APPLICATION">Web Application</option>
            <option value="SERVER_INFRASTRUCTURE">Infrastructure</option>
          </select>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">All Target Types</option>
            <option value="WEB_APP">Web App</option>
            <option value="DOMAIN">Domain</option>
            <option value="API_ENDPOINT">API Endpoint</option>
            <option value="SERVER">Server / Host</option>
            <option value="OBJECT_STORAGE">Object Storage</option>
          </select>

          <select
            value={envFilter}
            onChange={(e) => setEnvFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-[var(--text-primary)] focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('targets.allEnvironments', 'All Environments')}</option>
            <option value="PRODUCTION">Production</option>
            <option value="STAGING">Staging</option>
            <option value="DEV">Development</option>
          </select>
        </div>

        <div className="text-[var(--text-secondary)] text-xs flex items-center gap-2 self-end lg:self-auto">
          <span>{t('common.showing', 'Showing:')} <strong className="text-white font-mono">{filteredAndSortedAssets.length}</strong> targets</span>
          <button onClick={fetchAssets} className="p-1 rounded-lg hover:bg-white/[0.06] text-[var(--text-secondary)] hover:text-white transition" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Target Inventory Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-cyber-950/90 text-[var(--text-secondary)] uppercase tracking-wider text-[10px] border-b border-white/10 font-bold select-none">
              <tr>
                <th
                  onClick={() => handleSort('name')}
                  className="py-3 px-4 cursor-pointer hover:text-white transition"
                >
                  <div className="flex items-center gap-1.5">
                    <span>{t('targets.colTarget', 'Target & Identifier')}</span>
                    {sortField === 'name' ? (
                      sortOrder === 'asc' ? <ArrowUp className="w-3 h-3 text-cyan-400" /> : <ArrowDown className="w-3 h-3 text-cyan-400" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-600" />
                    )}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('type')}
                  className="py-3 px-3 cursor-pointer hover:text-white transition"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Type</span>
                    {sortField === 'type' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3 text-cyan-400" /> : <ArrowDown className="w-3 h-3 text-cyan-400" />)}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('status')}
                  className="py-3 px-3 text-center cursor-pointer hover:text-white transition"
                >
                  <div className="flex items-center justify-center gap-1.5">
                    <span>{t('targets.colStatus', 'Status')}</span>
                    {sortField === 'status' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3 text-cyan-400" /> : <ArrowDown className="w-3 h-3 text-cyan-400" />)}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('criticality')}
                  className="py-3 px-3 cursor-pointer hover:text-white transition"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Risk Level</span>
                    {sortField === 'criticality' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3 text-cyan-400" /> : <ArrowDown className="w-3 h-3 text-cyan-400" />)}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('findings')}
                  className="py-3 px-3 text-center cursor-pointer hover:text-white transition"
                >
                  <div className="flex items-center justify-center gap-1.5">
                    <span>Open Findings</span>
                    {sortField === 'findings' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3 text-cyan-400" /> : <ArrowDown className="w-3 h-3 text-cyan-400" />)}
                  </div>
                </th>
                <th className="py-3 px-3 font-bold">Last Assessed</th>
                <th className="py-3 px-4 font-bold text-right">{t('targets.colActions', 'Actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--text-secondary)]">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                    <span>{t('common.loading', 'Loading Empire target inventory...')}</span>
                  </td>
                </tr>
              ) : filteredAndSortedAssets.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--text-secondary)]">
                    <span>{t('common.noData', 'No targets matching current filter.')}</span>
                  </td>
                </tr>
              ) : (
                filteredAndSortedAssets.map((asset) => {
                  const summary = summaries[asset.id];
                  const openFindingsCount = summary?.open_findings ?? (asset.open_findings ?? 0);
                  const lastAssessed = summary?.last_assessment_at;

                  return (
                    <tr
                      key={asset.id}
                      onClick={() => setSelectedAssetForDrawer(asset)}
                      className="hover:bg-white/[0.03] transition cursor-pointer group"
                    >
                      {/* Name & Locator */}
                      <td className="py-3 px-4">
                        <div className="flex items-start gap-2.5">
                          <div className="mt-0.5 p-1 rounded-lg bg-white/[0.04] border border-white/10 shrink-0">
                            {getTypeIcon(asset.asset_type)}
                          </div>
                          <div>
                            <div className="font-bold text-white text-xs group-hover:text-cyan-400 transition flex items-center gap-1.5">
                              <span>{asset.name}</span>
                              <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border uppercase ${getModuleBadgeColor(asset.empire_module)}`}>
                                {asset.empire_module.replace('_', ' ')}
                              </span>
                            </div>
                            <div className="text-[11px] text-cyan-400/90 font-mono mt-0.5 flex items-center gap-1">
                              <span>{asset.target_locator}</span>
                              <a
                                href={asset.target_locator}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-[var(--text-secondary)] hover:text-cyan-400"
                              >
                                <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            </div>
                            <div className="text-[10px] text-[var(--text-secondary)] mt-0.5">{asset.technology}</div><div className="text-[10px] text-[var(--text-secondary)] mt-1" title={asset.inventory_provenance || undefined}>{assessmentLabel(asset, vi)}</div>
                          </div>
                        </div>
                      </td>

                      {/* Type & Env */}
                      <td className="py-3 px-3">
                        <div className="text-[var(--text-primary)] text-[11px] font-semibold">{asset.asset_type}</div>
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/[0.04] text-[var(--text-secondary)] border border-white/10 mt-1 inline-block">
                          {asset.environment}
                        </span>
                      </td>

                      {/* Verification Status */}
                      <td className="py-3 px-3 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedVerifyAsset(asset);
                          }}
                          className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md border transition ${
                            asset.verification_status === 'VERIFIED'
                              ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800/80 hover:bg-emerald-900/60'
                              : asset.verification_status === 'FAILED'
                              ? 'text-rose-400 bg-rose-950/60 border-rose-800/80 hover:bg-rose-900/60'
                              : 'text-amber-400 bg-amber-950/60 border-amber-800/80 hover:bg-amber-900/60'
                          }`}
                          title="Click to view 8-Step Verification Pipeline"
                        >
                          <CheckCircle className="w-2.5 h-2.5" />
                          <span title={asset.verification_proof ? `proof ${asset.verification_proof.method} ${asset.verification_proof.verified_at}` : 'no ownership proof on record'}>{asset.verification_state || asset.verification_status || 'UNKNOWN'}</span>
                        </button>
                      </td>

                      {/* Risk Level / Criticality */}
                      <td className="py-3 px-3">
                        <Badge
                          severity={asset.criticality?.toLowerCase() || 'medium'}
                          size="sm"
                          dot
                        >
                          {asset.criticality || 'MEDIUM'}
                        </Badge>
                      </td>

                      {/* Open Findings Badge */}
                      <td className="py-3 px-3 text-center">
                        <Link
                          href={`/findings?asset_id=${asset.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[11px] font-bold transition ${
                            openFindingsCount > 0
                              ? 'bg-rose-950/60 text-rose-300 border-rose-800/80 hover:bg-rose-900/60'
                              : 'bg-emerald-950/40 text-emerald-400 border-emerald-800/50 hover:bg-emerald-900/40'
                          }`}
                          title="View findings for this target"
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${openFindingsCount > 0 ? 'bg-rose-400 animate-pulse' : 'bg-emerald-400'}`} />
                          <span className="font-mono">{openFindingsCount} open</span>
                        </Link>
                      </td>

                      {/* Last Assessed */}
                      <td className="py-3 px-3 text-[var(--text-secondary)] font-mono text-[11px]">
                        {lastAssessed ? (
                          <div className="flex items-center gap-1 text-[var(--text-primary)]">
                            <Clock className="w-3 h-3 text-[var(--text-secondary)]" />
                            <span>{new Date(lastAssessed).toLocaleDateString()}</span>
                          </div>
                        ) : (
                          <span className="text-slate-600 italic">Never</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => setSelectedVerifyAsset(asset)}
                            className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-cyan-300 border border-white/10 text-[11px] font-semibold transition flex items-center gap-1"
                            title={L("Xem bằng chứng quyền sở hữu", "Inspect ownership verification")}
                          >
                            <ShieldCheck className="w-3 h-3 text-cyan-400" />
                            <span>Verify</span>
                          </button>
                          <button
                            onClick={() => handleScanNow(asset)}
                            disabled={!assessmentEligible(asset)}
                            className="px-2.5 py-1 rounded-lg bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 text-[11px] font-bold transition flex items-center gap-1 shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
                            title={assessmentLabel(asset, vi)}
                          >
                            <Play className="w-3 h-3 fill-current" />
                            <span>{L('Đánh giá', 'Assess')}</span>
                          </button>
                          <button
                            onClick={() => handleDelete(asset.id, asset.name)}
                            className="p-1 rounded-lg text-[var(--text-secondary)] hover:text-rose-400 hover:bg-rose-950/30 transition"
                            title="Remove Target"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TARGET DETAIL PROFILE DRAWER (Slide-Over)                                 */}
      {/* ========================================================================= */}
      {selectedAssetForDrawer && (
        <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
          <div
            className="fixed inset-0 bg-[var(--bg-primary)]/70 backdrop-blur-sm transition-opacity"
            onClick={() => setSelectedAssetForDrawer(null)}
          />

          <div className="relative w-full max-w-2xl sm:max-w-3xl bg-cyber-950 border-l border-white/15 shadow-2xl h-full flex flex-col z-10 overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-5 border-b border-white/10 flex items-start justify-between bg-cyber-900/40">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getModuleBadgeColor(selectedAssetForDrawer.empire_module)}`}>
                    {selectedAssetForDrawer.empire_module.replace('_', ' ')}
                  </span>
                  <Badge severity={selectedAssetForDrawer.criticality.toLowerCase()} size="sm">
                    {selectedAssetForDrawer.criticality}
                  </Badge>
                  <span className="text-[10px] text-[var(--text-secondary)] font-mono">ID: {selectedAssetForDrawer.id.slice(0, 8)}</span>
                </div>
                <h2 className="text-lg font-black text-white">{selectedAssetForDrawer.name}</h2>
                <a
                  href={selectedAssetForDrawer.target_locator}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-cyan-400 font-mono hover:underline flex items-center gap-1"
                >
                  <span>{selectedAssetForDrawer.target_locator}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Play className="w-3 h-3" />}
                  onClick={() => handleScanNow(selectedAssetForDrawer)}
                >
                  Scan Target
                </Button>
                <button
                  onClick={() => setSelectedAssetForDrawer(null)}
                  className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.08] transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Drawer Navigation Tabs */}
            <div className="px-5 border-b border-white/10 flex items-center gap-4 bg-cyber-950/60 overflow-x-auto text-xs font-semibold">
              <button
                onClick={() => setDrawerTab('overview')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'overview' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                Target Overview
              </button>
              <button
                onClick={() => setDrawerTab('dns_tls')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'dns_tls' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                DNS & TLS Records
              </button>
              <button
                onClick={() => setDrawerTab('endpoints')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'endpoints' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                {L('URL đã cấu hình', 'Configured URLs')}
              </button>
              <button
                onClick={() => setDrawerTab('scans')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'scans' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                Scan History ({drawerScans.length})
              </button>
              <button
                onClick={() => setDrawerTab('vulnerabilities')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'vulnerabilities' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                Vulnerabilities ({drawerFindings.length})
              </button>
            </div>

            {/* Drawer Tab Content */}
            <div className="p-5 flex-1 overflow-y-auto space-y-4">
              {/* TAB 1: OVERVIEW */}
              {drawerTab === 'overview' && (
                <div className="space-y-4 text-xs">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                      <div className="text-[var(--text-secondary)] text-[10px] uppercase font-bold">Verification Status</div>
                      <div className="text-sm font-bold text-emerald-400 mt-1 flex items-center gap-1.5">
                        <CheckCircle className="w-4 h-4 text-emerald-400" />
                        <span>{selectedAssetForDrawer.verification_status}</span>
                      </div>
                      <div className="text-[10px] text-[var(--text-secondary)] mt-1 font-mono">
                        Method: {selectedAssetForDrawer.verification_type}
                      </div>
                    </div>

                    <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                      <div className="text-[var(--text-secondary)] text-[10px] uppercase font-bold">Approved /media Policy</div>
                      <div className="text-sm font-bold text-white mt-1">
                        {selectedAssetForDrawer.approved_media_baseline ? (
                          <span className="text-emerald-400">PUBLIC_BY_DESIGN (Approved)</span>
                        ) : (
                          <span className="text-[var(--text-secondary)]">Standard Restricted</span>
                        )}
                      </div>
                      <div className="text-[10px] text-[var(--text-secondary)] mt-1">
                        Empire Media Storage Access Gate
                      </div>
                    </div>
                  </div>

                  {/* Metadata Specification */}
                  <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-2.5">
                    <div className="text-xs font-bold text-white uppercase tracking-wider">Asset Properties</div>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span className="text-[var(--text-secondary)]">Environment: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.environment}</strong>
                      </div>
                      <div>
                        <span className="text-[var(--text-secondary)]">Exposure: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.exposure}</strong>
                      </div>
                      <div>
                        <span className="text-[var(--text-secondary)]">Technology: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.technology}</strong>
                      </div>
                      <div>
                        <span className="text-[var(--text-secondary)]">Token: </span>
                        <strong className="text-cyan-400 font-mono text-[10px]">{selectedAssetForDrawer.verification_token}</strong>
                      </div>
                      <div>
                        <span className="text-[var(--text-secondary)]">Registered: </span>
                        <strong className="text-[var(--text-primary)] font-mono">{new Date(selectedAssetForDrawer.created_at).toLocaleString()}</strong>
                      </div>
                      <div>
                        <span className="text-[var(--text-secondary)]">Last Verified: </span>
                        <strong className="text-[var(--text-primary)] font-mono">{selectedAssetForDrawer.verified_at ? new Date(selectedAssetForDrawer.verified_at).toLocaleString() : 'N/A'}</strong>
                      </div>
                    </div>
                  </div>

                  {/* Tags */}
                  <div>
                    <div className="text-xs font-bold text-white mb-2">Classification Tags</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedAssetForDrawer.tags?.map((t) => (
                        <span key={t} className="px-2 py-0.5 rounded-md bg-white/[0.04] text-[var(--text-primary)] border border-white/10 text-[10px] font-mono">
                          #{t}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Description */}
                  {selectedAssetForDrawer.description && (
                    <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                      <div className="text-[var(--text-secondary)] text-[10px] uppercase font-bold mb-1">Description & Notes</div>
                      <p className="text-[var(--text-primary)] leading-relaxed">{selectedAssetForDrawer.description}</p>
                    </div>
                  )}

                  <div className="pt-2 flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />}
                      onClick={() => setSelectedVerifyAsset(selectedAssetForDrawer)}
                    >
                      {L('Xác minh quyền sở hữu', 'Verify ownership')}
                    </Button>
                    <Link href={`/findings?asset_id=${selectedAssetForDrawer.id}`}>
                      <Button variant="outline" size="sm" icon={<Eye className="w-3.5 h-3.5" />}>
                        View All Findings
                      </Button>
                    </Link>
                  </div>
                </div>
              )}

              {/* ================================================================= */}
              {/* TAB 2: DNS & TLS RECORDS (DYNAMIC GENUINE REFACTOR)               */}
              {/* ================================================================= */}
              {drawerTab === 'dns_tls' && <div className="space-y-4">
                <div className="assessment-panel space-y-2"><h3 className="font-semibold">{L('Danh tính mục tiêu & bằng chứng', 'Target identity & evidence')}</h3><p className="break-all text-sm">{selectedAssetForDrawer.target_locator}</p><p className="assessment-muted">{assessmentLabel(selectedAssetForDrawer, vi)}</p><p className="assessment-muted">{L('Nguồn kiểm kê', 'Inventory provenance')}: {selectedAssetForDrawer.inventory_provenance || selectedAssetForDrawer.inventory_classification || '—'}</p></div>
                <p className="assessment-muted">{L('DNS, TLS và header chỉ được xác nhận bằng kết quả có thời điểm của từng lượt chạy. Trạng thái xác minh quyền sở hữu không phải kết quả sức khỏe ứng dụng.', 'DNS, TLS and headers are established by timestamped execution evidence. Ownership verification is not an application health result.')}</p>
                {drawerExecutions.filter((x) => x.engine_id === 'public_web' || x.engine_id === 'tls_health').slice(0, 3).map((x) => <div key={x.execution_id} className="assessment-panel space-y-2"><div className="text-sm">{x.engine_id} · {x.status} · {x.timestamps_utc.finished_at ? new Date(x.timestamps_utc.finished_at).toLocaleString(locale === 'vi' ? 'vi-VN' : 'en-US', { timeZone: 'Asia/Ho_Chi_Minh' }) + ' ICT' : '—'}</div>{x.status_reason && <p className="assessment-muted">{x.status_reason}</p>}<Link className="assessment-link" href={`/engine-runs/?execution=${x.execution_id}&asset=${selectedAssetForDrawer.id}`}>{L('Xem quan sát và nhật ký', 'Inspect observations and logs')} →</Link></div>)}
                {!loadingDrawerData && !drawerExecutions.some((x) => x.engine_id === 'public_web' || x.engine_id === 'tls_health') && <p className="assessment-muted">{L('Chưa có quan sát mạng được ghi nhận.', 'No network observations recorded.')}</p>}
                {assessmentEligible(selectedAssetForDrawer) && <Link className="assessment-link" href={`/scans/?asset=${selectedAssetForDrawer.id}`}>{L('Xem kế hoạch đánh giá', 'Preview assessment plan')} →</Link>}
              </div>}

              {drawerTab === 'endpoints' && <div className="space-y-4">
                <h3 className="font-semibold">{L('URL đã đăng ký / cấu hình', 'Registered / configured URLs')}</h3>
                <p className="assessment-muted">{L('Không suy diễn endpoint theo tên module. Cấu hình URL không khẳng định endpoint hoạt động; xem bằng chứng của lượt chạy để biết phản hồi thực tế.', 'No endpoints are inferred from a module name. A configured URL does not establish availability; execution evidence records the actual response.')}</p>
                <div className="overflow-x-auto"><table className="assessment-table"><thead><tr><th>URL</th><th>{L('Nguồn', 'Source')}</th><th>{L('Trạng thái quan sát', 'Observation')}</th></tr></thead><tbody>{generateContextualEndpoints(selectedAssetForDrawer).map((ep) => <tr key={ep.fullUrl}><td className="break-all">{ep.fullUrl}</td><td>{ep.classification}</td><td>{ep.isExcluded ? 'EXCLUDED_BY_POLICY' : L('Xem lượt chạy', 'See execution evidence')}</td></tr>)}</tbody></table></div>
                {(selectedAssetForDrawer.excluded_endpoints || []).length > 0 && <p className="assessment-muted">{L('Đường dẫn loại trừ', 'Excluded paths')}: {selectedAssetForDrawer.excluded_endpoints?.join(', ')}</p>}
                <Link className="assessment-link" href={`/engine-runs/?asset=${selectedAssetForDrawer.id}`}>{L('Lượt chạy & bằng chứng', 'Runs & evidence')} →</Link>
              </div>}

              {drawerTab === 'scans' && (
                <div className="space-y-3 text-xs">
                  {loadingDrawerData ? (
                    <div className="py-10 text-center text-[var(--text-secondary)]">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                      <span>Loading assessment history...</span>
                    </div>
                  ) : drawerScans.length === 0 ? (
                    <div className="py-8 text-center text-[var(--text-secondary)] border border-dashed border-white/10 rounded-xl">
                      No assessment jobs recorded on this target yet.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {drawerScans.map((s) => (
                        <div key={s.id} className="p-3 rounded-xl bg-cyber-900/40 border border-white/10 flex items-center justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <Badge severity={s.status === 'COMPLETED' ? 'low' : s.status === 'RUNNING' ? 'info' : 'neutral'} size="sm" dot>
                                {s.status}
                              </Badge>
                              <span className="font-bold text-white text-xs">{s.profile}</span>
                              <span className="text-[var(--text-secondary)] font-mono text-[10px]">({s.engine})</span>
                            </div>
                            <div className="text-[10px] text-[var(--text-secondary)] font-mono mt-1">
                              Started: {new Date(s.created_at).toLocaleString()}
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="font-mono text-cyan-400 font-bold text-xs">{s.progress_percentage}%</span>
                            <Link href={`/active-assessments?scan_id=${s.id}`}>
                              <Button variant="outline" size="sm" icon={<ExternalLink className="w-3 h-3" />}>
                                View
                              </Button>
                            </Link>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: VULNERABILITIES BREAKDOWN */}
              {drawerTab === 'vulnerabilities' && (
                <div className="space-y-3 text-xs">
                  {loadingDrawerData ? (
                    <div className="py-10 text-center text-[var(--text-secondary)]">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                      <span>Loading vulnerabilities...</span>
                    </div>
                  ) : drawerFindings.length === 0 ? (
                    <div className="py-8 text-center text-emerald-400 border border-dashed border-emerald-500/30 rounded-xl bg-emerald-950/20">
                      Zero active findings detected on this target!
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {drawerFindings.map((f) => (
                        <div key={f.id} className="p-3 rounded-xl bg-cyber-900/40 border border-white/10 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <Badge severity={f.severity.toLowerCase()} size="sm">
                                {f.severity}
                              </Badge>
                              <span className="font-bold text-white text-xs">{f.title}</span>
                            </div>
                            <Badge severity="neutral" size="sm">{f.status}</Badge>
                          </div>
                          <div className="text-[10px] text-[var(--text-secondary)] font-mono flex items-center justify-between">
                            <span>Rule: {f.scanner_rule_id}</span>
                            <span className="text-cyan-400">{f.scanner_engine}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* ADD SINGLE TARGET MODAL                                                   */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title={t('targets.registerTarget', 'Register Security Target')}
        description="Add a new target endpoint, domain, or IP address under continuous Empire management."
        size="lg"
      >
        <form onSubmit={handleCreateAsset} className="space-y-4 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Target Name *</label>
              <Input
                type="text"
                placeholder="e.g. Empire Portal Main"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Target Locator (URL / Host / IP) *</label>
              <Input
                type="text"
                placeholder="e.g. https://empire.edu.vn"
                value={formTarget}
                onChange={(e) => setFormTarget(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Asset Category</label>
              <select
                value={formType}
                onChange={(e) => setFormType(e.target.value as AssetType)}
                className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-xs"
              >
                <option value="WEB_APP">Web Application</option>
                <option value="DOMAIN">Domain / Hostname</option>
                <option value="API_ENDPOINT">API Service</option>
                <option value="SERVER">Server / Host</option>
                <option value="OBJECT_STORAGE">Object Storage</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Empire Module</label>
              <select
                value={formModule}
                onChange={(e) => setFormModule(e.target.value as EmpireModuleType)}
                className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-xs"
              >
                <option value="STUDENT_MANAGEMENT">Student Management</option>
                <option value="LEARNING_MATERIALS">Learning Materials (/media)</option>
                <option value="SUPPORTING_TOOLS">Supporting Tools</option>
                <option value="API_SERVICES">API Services</option>
                <option value="WEB_APPLICATION">Web Application</option>
                <option value="SERVER_INFRASTRUCTURE">Infrastructure</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Environment</label>
              <select
                value={formEnv}
                onChange={(e) => setFormEnv(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-xs"
              >
                <option value="PRODUCTION">Production</option>
                <option value="STAGING">Staging</option>
                <option value="DEV">Development</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Business Criticality</label>
              <select
                value={formCriticality}
                onChange={(e) => setFormCriticality(e.target.value as CriticalityTier)}
                className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-xs"
              >
                <option value="CRITICAL">Critical (P1)</option>
                <option value="HIGH">High (P2)</option>
                <option value="MEDIUM">Medium (P3)</option>
                <option value="LOW">Low (P4)</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-[var(--text-primary)] font-semibold">Technology Stack Profile</label>
              <Input
                type="text"
                placeholder="e.g. Next.js 14 / Better-Auth / Node.js"
                value={formTech}
                onChange={(e) => setFormTech(e.target.value)}
              />
            </div>
          </div>

          <div className="p-3 rounded-xl bg-cyber-950/80 border border-white/10 flex items-center justify-between">
            <div>
              <div className="font-bold text-white text-xs">Approved Public /media Baseline Policy</div>
              <div className="text-[10px] text-[var(--text-secondary)]">
                Grant approved anonymous access to public course assets and prevent false-positive media exposure alerts.
              </div>
            </div>
            <input
              type="checkbox"
              checked={formApprovedMedia}
              onChange={(e) => setFormApprovedMedia(e.target.checked)}
              className="w-4 h-4 rounded text-cyan-500 focus:ring-cyan-500 bg-cyber-950 border-white/20"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[var(--text-primary)] font-semibold">Excluded Endpoints (Optional, line-separated)</label>
            <textarea
              rows={2}
              placeholder="/api/v1/auth/delete-account&#10;/admin/reset-db"
              value={formExcludedEndpoints}
              onChange={(e) => setFormExcludedEndpoints(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-cyber-950 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 text-xs font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[var(--text-primary)] font-semibold">Description / Notes</label>
            <textarea
              rows={2}
              placeholder="Primary public frontend for Empire students..."
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-cyber-950 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 text-xs"
            />
          </div>

          <div className="pt-3 border-t border-white/10 flex items-center justify-end gap-2">
            <Button variant="ghost" size="md" onClick={() => setIsCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="md" loading={submitting} type="submit">
              Register Target
            </Button>
          </div>
        </form>
      </Modal>

      {/* ========================================================================= */}
      {/* BULK IMPORT MODAL WITH 2-STAGE PREVIEW                                    */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        title={t('targets.bulkImport', 'Bulk Import Security Targets')}
        description="Ingest OpenAPI, CSV, JSON, TXT lines, or CIDR blocks with automated duplicate detection."
        size="xl"
      >
        <div className="space-y-4 text-xs">
          {!bulkPreviewData ? (
            /* STAGE 1: INPUT FORM */
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-[var(--text-primary)] font-semibold">Import Format Mode</label>
                <div className="flex items-center gap-1.5">
                  {['AUTO', 'OPENAPI', 'CSV', 'JSON', 'TXT', 'CIDR'].map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      onClick={() => setBulkImportType(fmt)}
                      className={`px-2 py-0.5 rounded-md text-[10px] font-bold border transition ${
                        bulkImportType === fmt
                          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                          : 'bg-white/[0.04] text-[var(--text-secondary)] border-white/10 hover:text-white'
                      }`}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                rows={10}
                placeholder={
                  bulkImportType === 'OPENAPI'
                    ? 'Paste OpenAPI / Swagger JSON or YAML specification...'
                    : bulkImportType === 'CSV'
                    ? 'target_locator,name,environment,module\nhttps://id.empire.edu.vn,Empire Auth,PRODUCTION,STUDENT_MANAGEMENT'
                    : bulkImportType === 'JSON'
                    ? '[\n  {"target_locator": "https://empire.edu.vn", "name": "Empire Main"}\n]'
                    : 'https://empire.edu.vn\nhttps://id.empire.edu.vn\n103.142.26.18/29'
                }
                value={bulkContent}
                onChange={(e) => setBulkContent(e.target.value)}
                className="w-full p-3 rounded-xl bg-cyber-950 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 text-xs font-mono"
              />

              <div className="flex items-center justify-between pt-2">
                <div className="text-[11px] text-[var(--text-secondary)]">
                  Duplicates against existing targets and within the import batch will be highlighted before commit.
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="md" onClick={() => setIsBulkModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    loading={previewingBulk}
                    disabled={!bulkContent.trim()}
                    onClick={handlePreviewBulk}
                  >
                    Preview & Validate Targets
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            /* STAGE 2: DUPLICATE PREVIEW & COMMIT */
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-xl bg-cyber-950 border border-white/10">
                  <div className="text-[var(--text-secondary)] text-[10px] uppercase font-bold">Total Targets Detected</div>
                  <div className="text-xl font-black text-white font-mono mt-0.5">{bulkPreviewData.total}</div>
                </div>
                <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30">
                  <div className="text-emerald-400 text-[10px] uppercase font-bold">New Valid Candidates</div>
                  <div className="text-xl font-black text-emerald-400 font-mono mt-0.5">{bulkPreviewData.new.length}</div>
                </div>
                <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/30">
                  <div className="text-amber-400 text-[10px] uppercase font-bold">Duplicates Skipped</div>
                  <div className="text-xl font-black text-amber-400 font-mono mt-0.5">{bulkPreviewData.duplicate.length}</div>
                </div>
              </div>

              {/* Candidates Table */}
              <div className="max-h-60 overflow-y-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-cyber-950 text-[var(--text-secondary)] uppercase text-[10px] border-b border-white/10">
                    <tr>
                      <th className="py-2.5 px-3">Target Locator</th>
                      <th className="py-2.5 px-3">Auto Module</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Validation Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-[11px]">
                    {bulkPreviewData.new.map((item, idx) => (
                      <tr key={`new-${idx}`} className="bg-emerald-950/10">
                        <td className="py-2 px-3 text-white font-bold">{item.target_locator}</td>
                        <td className="py-2 px-3 text-cyan-400">{item.empire_module}</td>
                        <td className="py-2 px-3 text-[var(--text-primary)]">{item.asset_type}</td>
                        <td className="py-2 px-3">
                          <span className="text-emerald-400 font-bold flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" /> Ready to Import
                          </span>
                        </td>
                      </tr>
                    ))}
                    {bulkPreviewData.duplicate.map((dup, idx) => (
                      <tr key={`dup-${idx}`} className="bg-amber-950/10 text-[var(--text-secondary)]">
                        <td className="py-2 px-3 text-[var(--text-primary)] font-mono">{dup.target_locator}</td>
                        <td className="py-2 px-3">{dup.empire_module}</td>
                        <td className="py-2 px-3">{dup.asset_type}</td>
                        <td className="py-2 px-3 text-amber-400 text-[10px]">
                          <span className="flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" /> {dup.reason || 'Duplicate'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between pt-2">
                <Button variant="ghost" size="md" onClick={() => setBulkPreviewData(null)}>
                  Back to Edit
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  loading={bulkImporting}
                  disabled={bulkPreviewData.new.length === 0}
                  onClick={handleCommitBulkImport}
                >
                  Import {bulkPreviewData.new.length} Valid Targets
                </Button>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* ========================================================================= */}
      {/* 8-STEP LIVE TARGET VERIFICATION PIPELINE MODAL                            */}
      {/* ========================================================================= */}
      <TargetVerificationModal
        isOpen={Boolean(selectedVerifyAsset)}
        onClose={() => setSelectedVerifyAsset(null)}
        asset={selectedVerifyAsset}
        onVerified={(verifiedAssetId) => {
          fetchAssets();
          if (selectedAssetForDrawer?.id === verifiedAssetId) setSelectedAssetForDrawer(null);
        }}
      />
    </div>
  );
}

export default function TargetsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-[var(--text-secondary)] font-mono text-xs">Loading target inventory...</div>}>
      <TargetsContent />
    </Suspense>
  );
}

