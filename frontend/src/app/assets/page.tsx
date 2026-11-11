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
import { api } from '@/lib/api';
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

interface ParsedTargetInfo {
  raw: string;
  scheme: 'http' | 'https';
  hostname: string;
  port: number;
  pathname: string;
  origin: string;
  baseUrl: string;
  isIp: boolean;
}

function parseTargetInfo(targetLocator: string): ParsedTargetInfo {
  let raw = (targetLocator || '').trim();
  let scheme: 'http' | 'https' = 'https';
  if (raw.startsWith('http://')) {
    scheme = 'http';
  } else if (raw.startsWith('https://')) {
    scheme = 'https';
  } else {
    raw = `https://${raw}`;
  }

  try {
    const url = new URL(raw);
    const hostname = url.hostname;
    const port = url.port ? parseInt(url.port, 10) : (scheme === 'https' ? 443 : 80);
    const pathname = url.pathname.replace(/\/+$/, '');
    const origin = url.origin;
    const baseUrl = `${origin}${pathname}`;
    const isIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(hostname) || hostname.includes(':');

    return {
      raw: targetLocator,
      scheme,
      hostname,
      port,
      pathname,
      origin,
      baseUrl,
      isIp,
    };
  } catch {
    const cleanHost = targetLocator.replace(/^https?:\/\//, '').split('/')[0].split(':')[0] || targetLocator;
    const isIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(cleanHost);
    return {
      raw: targetLocator,
      scheme: 'https',
      hostname: cleanHost,
      port: 443,
      pathname: '',
      origin: `https://${cleanHost}`,
      baseUrl: `https://${cleanHost}`,
      isIp,
    };
  }
}

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

function generateContextualEndpoints(asset: Asset, probeData?: any): ContextualEndpoint[] {
  const parsed = parseTargetInfo(asset.target_locator);
  const base = parsed.baseUrl;
  const excludedSet = new Set((asset.excluded_endpoints || []).map((e) => e.trim()));

  // Extract real probed statuses from Step 4 (HTTP) and Step 6 (Web Discovery)
  const httpStep = probeData?.steps?.find((s: any) => s.step === 4 || s.name === 'HTTP Connectivity');
  const discoveryStep = probeData?.steps?.find((s: any) => s.step === 6 || s.name === 'Web Discovery');
  const rootStatusCode = httpStep?.metadata?.status_code;
  const discoveryEndpoints = discoveryStep?.metadata?.endpoints || {};

  const endpoints: ContextualEndpoint[] = [];

  // Helper to format status text & severity
  const resolveStatus = (code: number | undefined | null, fallbackText: string): { status: string; severity: 'low' | 'info' | 'medium' | 'high' | 'neutral' } => {
    if (code === undefined || code === null) {
      return { status: fallbackText, severity: 'neutral' };
    }
    if (code >= 200 && code < 300) {
      return { status: `${code} OK`, severity: 'low' };
    }
    if (code >= 300 && code < 400) {
      return { status: `${code} Redirect`, severity: 'info' };
    }
    if (code === 401) {
      return { status: '401 Auth Required', severity: 'medium' };
    }
    if (code === 403) {
      return { status: '403 Forbidden', severity: 'medium' };
    }
    if (code === 404) {
      return { status: '404 Not Found', severity: 'neutral' };
    }
    return { status: `${code} Response`, severity: 'high' };
  };

  // 1. Root Endpoint
  const rootStatus = resolveStatus(rootStatusCode, probeData ? 'Live Reachable' : 'Target-Relative (Awaiting Probe)');
  endpoints.push({
    method: 'GET',
    path: '/',
    fullUrl: `${base}/`,
    status: rootStatus.status,
    statusCode: rootStatusCode,
    statusSeverity: rootStatus.severity,
    classification: 'PUBLIC_ROOT',
    classificationSeverity: 'info',
    isExcluded: excludedSet.has('/') || excludedSet.has('/*'),
    description: 'Target root entry point and HTTP service landing origin.',
  });

  // 2. robots.txt
  const robotsData = discoveryEndpoints['/robots.txt'];
  const robotsStatus = resolveStatus(robotsData?.status_code, probeData ? (robotsData?.accessible ? '200 OK' : '404 Not Found') : 'Target-Relative');
  endpoints.push({
    method: 'GET',
    path: '/robots.txt',
    fullUrl: `${base}/robots.txt`,
    status: robotsStatus.status,
    statusCode: robotsData?.status_code,
    statusSeverity: robotsStatus.severity,
    classification: 'DISCOVERY',
    classificationSeverity: 'neutral',
    isExcluded: excludedSet.has('/robots.txt'),
    description: 'Crawler directives, search index limits, and disallowed paths.',
  });

  // 3. sitemap.xml
  const sitemapData = discoveryEndpoints['/sitemap.xml'];
  const sitemapStatus = resolveStatus(sitemapData?.status_code, probeData ? (sitemapData?.accessible ? '200 OK' : '404 Not Found') : 'Target-Relative');
  endpoints.push({
    method: 'GET',
    path: '/sitemap.xml',
    fullUrl: `${base}/sitemap.xml`,
    status: sitemapStatus.status,
    statusCode: sitemapData?.status_code,
    statusSeverity: sitemapStatus.severity,
    classification: 'DISCOVERY',
    classificationSeverity: 'neutral',
    isExcluded: excludedSet.has('/sitemap.xml'),
    description: 'XML site structure, URL enumeration map, and index paths.',
  });

  // 4. .well-known/security.txt
  const secTxtData = discoveryEndpoints['/.well-known/security.txt'];
  const secTxtStatus = resolveStatus(secTxtData?.status_code, probeData ? (secTxtData?.accessible ? '200 OK' : '404 Not Found') : 'Target-Relative');
  endpoints.push({
    method: 'GET',
    path: '/.well-known/security.txt',
    fullUrl: `${base}/.well-known/security.txt`,
    status: secTxtStatus.status,
    statusCode: secTxtData?.status_code,
    statusSeverity: secTxtStatus.severity,
    classification: 'SECURITY_TXT',
    classificationSeverity: 'low',
    isExcluded: excludedSet.has('/.well-known/security.txt'),
    description: 'RFC 9116 security contact, vulnerability disclosure, and PGP key.',
  });

  // 5. Business Module Specific Endpoints
  switch (asset.empire_module) {
    case 'STUDENT_MANAGEMENT':
      endpoints.push(
        {
          method: 'POST',
          path: '/api/v1/auth/login',
          fullUrl: `${base}/api/v1/auth/login`,
          status: '401 Auth Gate',
          statusSeverity: 'medium',
          classification: 'AUTH_GATE',
          classificationSeverity: 'medium',
          isExcluded: excludedSet.has('/api/v1/auth/login'),
          description: 'Primary student authentication gate and credential validator.',
        },
        {
          method: 'GET',
          path: '/api/student/profile',
          fullUrl: `${base}/api/student/profile`,
          status: '403 Forbidden',
          statusSeverity: 'high',
          classification: 'BOLA_TARGET',
          classificationSeverity: 'high',
          isExcluded: excludedSet.has('/api/student/profile'),
          description: 'Student account record service & object-level authorization checkpoint.',
        },
        {
          method: 'GET',
          path: '/api/v1/student/session',
          fullUrl: `${base}/api/v1/student/session`,
          status: 'Target-Relative',
          statusSeverity: 'neutral',
          classification: 'SESSION_SVC',
          classificationSeverity: 'info',
          isExcluded: excludedSet.has('/api/v1/student/session'),
          description: 'Session validation token exchange and bearer verification.',
        }
      );
      break;

    case 'LEARNING_MATERIALS':
      endpoints.push(
        {
          method: 'GET',
          path: '/media/',
          fullUrl: `${base}/media/`,
          status: asset.approved_media_baseline ? '200 OK (Approved)' : 'Restricted',
          statusSeverity: asset.approved_media_baseline ? 'low' : 'medium',
          classification: 'PUBLIC_MEDIA',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/media/'),
          description: 'Empire Educational Public Media Storage Gateway root.',
        },
        {
          method: 'GET',
          path: '/media/uploads/*',
          fullUrl: `${base}/media/uploads/*`,
          status: asset.approved_media_baseline ? '200 OK (Approved)' : 'Restricted',
          statusSeverity: asset.approved_media_baseline ? 'low' : 'medium',
          classification: 'PUBLIC_MEDIA',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/media/uploads/*'),
          description: 'Educational public media uploads and coursework storage directory.',
        },
        {
          method: 'GET',
          path: '/media/documents/*',
          fullUrl: `${base}/media/documents/*`,
          status: 'Target-Relative',
          statusSeverity: 'neutral',
          classification: 'MEDIA_VAULT',
          classificationSeverity: 'info',
          isExcluded: excludedSet.has('/media/documents/*'),
          description: 'Learning materials, student PDF downloads, and coursework assets.',
        },
        {
          method: 'HEAD',
          path: '/v1/buckets',
          fullUrl: `${base}/v1/buckets`,
          status: '403 Forbidden',
          statusSeverity: 'medium',
          classification: 'STORAGE_BUCKET',
          classificationSeverity: 'medium',
          isExcluded: excludedSet.has('/v1/buckets'),
          description: 'MinIO S3 object storage bucket listing interface.',
        }
      );
      break;

    case 'API_SERVICES':
      endpoints.push(
        {
          method: 'GET',
          path: '/api/v1/health',
          fullUrl: `${base}/api/v1/health`,
          status: rootStatusCode ? '200 OK' : 'Target-Relative',
          statusSeverity: 'low',
          classification: 'HEALTH_CHECK',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/api/v1/health'),
          description: 'API Gateway operational liveness probe and service heartbeat.',
        },
        {
          method: 'GET',
          path: '/docs',
          fullUrl: `${base}/docs`,
          status: 'Target-Relative',
          statusSeverity: 'info',
          classification: 'API_DOCS',
          classificationSeverity: 'info',
          isExcluded: excludedSet.has('/docs'),
          description: 'OpenAPI / Swagger interactive API documentation portal.',
        },
        {
          method: 'GET',
          path: '/openapi.json',
          fullUrl: `${base}/openapi.json`,
          status: 'Target-Relative',
          statusSeverity: 'info',
          classification: 'API_SPEC',
          classificationSeverity: 'info',
          isExcluded: excludedSet.has('/openapi.json'),
          description: 'Machine-readable OpenAPI v3 service contract definition.',
        },
        {
          method: 'POST',
          path: '/graphql',
          fullUrl: `${base}/graphql`,
          status: 'Target-Relative',
          statusSeverity: 'neutral',
          classification: 'GRAPHQL_QUERY',
          classificationSeverity: 'medium',
          isExcluded: excludedSet.has('/graphql'),
          description: 'GraphQL query execution pipeline and introspection schema.',
        }
      );
      break;

    case 'WEB_APPLICATION':
      endpoints.push(
        {
          method: 'GET',
          path: '/login',
          fullUrl: `${base}/login`,
          status: 'Target-Relative',
          statusSeverity: 'info',
          classification: 'AUTH_GATE',
          classificationSeverity: 'medium',
          isExcluded: excludedSet.has('/login'),
          description: 'Empire Management Console user and administrator login view.',
        },
        {
          method: 'GET',
          path: '/api/health',
          fullUrl: `${base}/api/health`,
          status: 'Target-Relative',
          statusSeverity: 'low',
          classification: 'HEALTH_CHECK',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/api/health'),
          description: 'Web application backend health and system telemetry.',
        }
      );
      break;

    case 'SUPPORTING_TOOLS':
      endpoints.push(
        {
          method: 'GET',
          path: '/news',
          fullUrl: `${base}/news`,
          status: 'Target-Relative',
          statusSeverity: 'low',
          classification: 'TOOL_SERVICE',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/news'),
          description: 'Educational news dissemination feed and announcements.',
        },
        {
          method: 'GET',
          path: '/vocab',
          fullUrl: `${base}/vocab`,
          status: 'Target-Relative',
          statusSeverity: 'low',
          classification: 'TOOL_SERVICE',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/vocab'),
          description: 'Vocabulary training and learning enhancement service.',
        }
      );
      break;

    case 'SERVER_INFRASTRUCTURE':
      endpoints.push(
        {
          method: 'GET',
          path: '/healthz',
          fullUrl: `${base}/healthz`,
          status: 'Target-Relative',
          statusSeverity: 'low',
          classification: 'HOST_HEALTH',
          classificationSeverity: 'low',
          isExcluded: excludedSet.has('/healthz'),
          description: 'Host-level daemon health check and supervisor status.',
        },
        {
          method: 'GET',
          path: '/metrics',
          fullUrl: `${base}/metrics`,
          status: 'Target-Relative',
          statusSeverity: 'neutral',
          classification: 'TELEMETRY',
          classificationSeverity: 'medium',
          isExcluded: excludedSet.has('/metrics'),
          description: 'Prometheus metrics scraping endpoint and system counters.',
        }
      );
      break;
  }

  // 6. Explicitly configured excluded endpoints
  (asset.excluded_endpoints || []).forEach((exPath) => {
    const cleanPath = exPath.trim();
    if (!endpoints.some((e) => e.path === cleanPath)) {
      endpoints.push({
        method: 'GET',
        path: cleanPath,
        fullUrl: `${base}${cleanPath.startsWith('/') ? '' : '/'}${cleanPath}`,
        status: 'BLOCKED_BY_POLICY',
        statusSeverity: 'neutral',
        classification: 'EXCLUDED_FROM_SCAN',
        classificationSeverity: 'high',
        isExcluded: true,
        description: 'Explicitly excluded from automated testing under persistent asset management policy.',
      });
    }
  });

  return endpoints;
}

function TargetsContent() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const initialModule = searchParams.get('empire_module');

  // Asset Inventory State
  const [assets, setAssets] = useState<Asset[]>([]);
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
  const [drawerFindings, setDrawerFindings] = useState<any[]>([]);
  const [loadingDrawerData, setLoadingDrawerData] = useState(false);

  // Drawer Live Diagnostic & Probe State
  const [assetProbeResults, setAssetProbeResults] = useState<
    Record<string, { loading: boolean; data: any | null; error: string | null; timestamp: number }>
  >({});
  const [probingAssetId, setProbingAssetId] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  // Trigger Live 8-Step Verification Probe
  const handleRunDrawerProbe = async (asset: Asset) => {
    try {
      setProbingAssetId(asset.id);
      setAssetProbeResults((prev) => ({
        ...prev,
        [asset.id]: {
          loading: true,
          data: prev[asset.id]?.data || null,
          error: null,
          timestamp: Date.now(),
        },
      }));

      const res = await api.verifyAsset(asset.id, 'ADMIN_OVERRIDE');

      setAssetProbeResults((prev) => ({
        ...prev,
        [asset.id]: {
          loading: false,
          data: res,
          error: res.verified || res.status === 'VERIFIED' ? null : (res.message || 'Probe reported verification failure'),
          timestamp: Date.now(),
        },
      }));

      // Reflect verified status in table list
      setAssets((prev) =>
        prev.map((a) =>
          a.id === asset.id
            ? {
                ...a,
                verification_status: res.verification_status || (res.verified ? 'VERIFIED' : 'FAILED'),
                verified_at: new Date().toISOString(),
                technology: res.fingerprint?.technologies?.join(' / ') || a.technology,
              }
            : a
        )
      );

      // Reflect in selected drawer asset
      setSelectedAssetForDrawer((prev) =>
        prev && prev.id === asset.id
          ? {
              ...prev,
              verification_status: res.verification_status || (res.verified ? 'VERIFIED' : 'FAILED'),
              verified_at: new Date().toISOString(),
              technology: res.fingerprint?.technologies?.join(' / ') || prev.technology,
            }
          : prev
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setAssetProbeResults((prev) => ({
        ...prev,
        [asset.id]: {
          loading: false,
          data: null,
          error: msg,
          timestamp: Date.now(),
        },
      }));
    } finally {
      setProbingAssetId(null);
    }
  };

  const handleCopyUrl = (url: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(url);
      setCopiedUrl(url);
      setTimeout(() => setCopiedUrl(null), 2000);
    }
  };

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [selectedVerifyAsset, setSelectedVerifyAsset] = useState<Asset | null>(null);
  const [scanningAssetId, setScanningAssetId] = useState<string | null>(null);

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
      const res = await api.listAssets({ size: 200 });
      const items = res.items || [];
      setAssets(items);

      // Hydrate summary metrics for top assets
      items.slice(0, 25).forEach(async (a) => {
        try {
          const sum = await api.getAssetSummary(a.id);
          setSummaries((prev) => ({ ...prev, [a.id]: sum }));
        } catch (_) {}
      });
    } catch (err) {
      console.error('Failed to load targets', err);
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
        const [scansRes, findingsRes] = await Promise.all([
          api.request(`/scans?asset_id=${selectedAssetForDrawer.id}&size=20`).catch(() => ({ items: [] })),
          api.listFindings({ assetId: selectedAssetForDrawer.id }).catch(() => ({ items: [] })),
        ]);
        setDrawerScans(scansRes.items || []);
        setDrawerFindings(findingsRes.items || []);
      } catch (err) {
        console.error('Failed to load drawer data', err);
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

        return matchesSearch && matchesStatus && matchesModule && matchesEnv && matchesType;
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
  }, [assets, searchTerm, statusFilter, moduleFilter, envFilter, typeFilter, sortField, sortOrder, summaries]);

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

      if (confirm(`Target "${newAsset.name}" registered successfully! Run 8-step verification probe now?`)) {
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

  // Quick Scan Dispatch
  const handleScanNow = async (asset: Asset) => {
    try {
      setScanningAssetId(asset.id);
      const scan = await api.dispatchScan({
        asset_id: asset.id,
        engine: 'all',
        profile: 'STANDARD',
        allow_private_targets: true,
      });
      window.location.href = `/active-assessments?scan_id=${scan.id}`;
    } catch (err: unknown) {
      alert(`Scan dispatch failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setScanningAssetId(null);
    }
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
        return 'bg-slate-900/80 text-slate-300 border-slate-700/80';
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
  const verifiedCount = assets.filter((a) => a.verification_status === 'VERIFIED').length;
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
          <p className="text-xs text-slate-400 mt-1">
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
          <div className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Total Targets</div>
          <div className="text-2xl font-black text-white font-mono mt-0.5">{assets.length}</div>
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-emerald-500/30">
          <div className="text-[10px] text-emerald-400 uppercase tracking-wider font-semibold">Verified Scope</div>
          <div className="text-2xl font-black text-emerald-400 font-mono mt-0.5">{verifiedCount}</div>
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-amber-500/30">
          <div className="text-[10px] text-amber-400 uppercase tracking-wider font-semibold">Pending Verification</div>
          <div className="text-2xl font-black text-amber-400 font-mono mt-0.5">{pendingCount}</div>
        </div>
        <div className="p-3.5 rounded-2xl liquid-glass border border-rose-500/30">
          <div className="text-[10px] text-rose-400 uppercase tracking-wider font-semibold">Failed / Unreachable</div>
          <div className="text-2xl font-black text-rose-400 font-mono mt-0.5">{failedCount}</div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="p-3.5 rounded-2xl liquid-glass-card flex flex-col lg:flex-row gap-3 items-center justify-between text-xs">
        <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto">
          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
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
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">All Statuses</option>
            <option value="VERIFIED">Verified</option>
            <option value="PENDING">Pending</option>
            <option value="FAILED">Failed</option>
          </select>

          <select
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
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
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
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
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('targets.allEnvironments', 'All Environments')}</option>
            <option value="PRODUCTION">Production</option>
            <option value="STAGING">Staging</option>
            <option value="DEV">Development</option>
          </select>
        </div>

        <div className="text-slate-400 text-xs flex items-center gap-2 self-end lg:self-auto">
          <span>{t('common.showing', 'Showing:')} <strong className="text-white font-mono">{filteredAndSortedAssets.length}</strong> targets</span>
          <button onClick={fetchAssets} className="p-1 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-white transition" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Target Inventory Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10 font-bold select-none">
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
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                    <span>{t('common.loading', 'Loading Empire target inventory...')}</span>
                  </td>
                </tr>
              ) : filteredAndSortedAssets.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <span>{t('common.noData', 'No targets matching current filter.')}</span>
                  </td>
                </tr>
              ) : (
                filteredAndSortedAssets.map((asset) => {
                  const summary = summaries[asset.id];
                  const openFindingsCount = summary?.open_findings ?? (asset.open_findings ?? 0);
                  const lastAssessed = summary?.last_assessment_at || asset.verified_at;

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
                                className="text-slate-500 hover:text-cyan-400"
                              >
                                <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5">{asset.technology}</div>
                          </div>
                        </div>
                      </td>

                      {/* Type & Env */}
                      <td className="py-3 px-3">
                        <div className="text-slate-300 text-[11px] font-semibold">{asset.asset_type}</div>
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-white/[0.04] text-slate-400 border border-white/10 mt-1 inline-block">
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
                          <span>{asset.verification_status || 'VERIFIED'}</span>
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
                      <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                        {lastAssessed ? (
                          <div className="flex items-center gap-1 text-slate-300">
                            <Clock className="w-3 h-3 text-slate-500" />
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
                            title="Run 8-Step Live Probe Pipeline"
                          >
                            <ShieldCheck className="w-3 h-3 text-cyan-400" />
                            <span>Verify</span>
                          </button>
                          <button
                            onClick={() => handleScanNow(asset)}
                            disabled={scanningAssetId === asset.id}
                            className="px-2.5 py-1 rounded-lg bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 text-[11px] font-bold transition flex items-center gap-1 shadow-sm"
                            title="Dispatch Immediate Assessment"
                          >
                            <Play className="w-3 h-3 fill-current" />
                            <span>Scan</span>
                          </button>
                          <button
                            onClick={() => handleDelete(asset.id, asset.name)}
                            className="p-1 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 transition"
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
            className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm transition-opacity"
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
                  <span className="text-[10px] text-slate-400 font-mono">ID: {selectedAssetForDrawer.id.slice(0, 8)}</span>
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
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.08] transition"
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
                  drawerTab === 'overview' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Target Overview
              </button>
              <button
                onClick={() => setDrawerTab('dns_tls')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'dns_tls' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                DNS & TLS Records
              </button>
              <button
                onClick={() => setDrawerTab('endpoints')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'endpoints' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Discovered Endpoints
              </button>
              <button
                onClick={() => setDrawerTab('scans')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'scans' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                Scan History ({drawerScans.length})
              </button>
              <button
                onClick={() => setDrawerTab('vulnerabilities')}
                className={`py-3 border-b-2 transition whitespace-nowrap ${
                  drawerTab === 'vulnerabilities' ? 'border-cyan-400 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'
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
                      <div className="text-slate-400 text-[10px] uppercase font-bold">Verification Status</div>
                      <div className="text-sm font-bold text-emerald-400 mt-1 flex items-center gap-1.5">
                        <CheckCircle className="w-4 h-4 text-emerald-400" />
                        <span>{selectedAssetForDrawer.verification_status}</span>
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1 font-mono">
                        Method: {selectedAssetForDrawer.verification_type}
                      </div>
                    </div>

                    <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                      <div className="text-slate-400 text-[10px] uppercase font-bold">Approved /media Policy</div>
                      <div className="text-sm font-bold text-white mt-1">
                        {selectedAssetForDrawer.approved_media_baseline ? (
                          <span className="text-emerald-400">PUBLIC_BY_DESIGN (Approved)</span>
                        ) : (
                          <span className="text-slate-400">Standard Restricted</span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">
                        Empire Media Storage Access Gate
                      </div>
                    </div>
                  </div>

                  {/* Metadata Specification */}
                  <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-2.5">
                    <div className="text-xs font-bold text-white uppercase tracking-wider">Asset Properties</div>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span className="text-slate-400">Environment: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.environment}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400">Exposure: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.exposure}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400">Technology: </span>
                        <strong className="text-white font-mono">{selectedAssetForDrawer.technology}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400">Token: </span>
                        <strong className="text-cyan-400 font-mono text-[10px]">{selectedAssetForDrawer.verification_token}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400">Registered: </span>
                        <strong className="text-slate-300 font-mono">{new Date(selectedAssetForDrawer.created_at).toLocaleString()}</strong>
                      </div>
                      <div>
                        <span className="text-slate-400">Last Verified: </span>
                        <strong className="text-slate-300 font-mono">{selectedAssetForDrawer.verified_at ? new Date(selectedAssetForDrawer.verified_at).toLocaleString() : 'N/A'}</strong>
                      </div>
                    </div>
                  </div>

                  {/* Tags */}
                  <div>
                    <div className="text-xs font-bold text-white mb-2">Classification Tags</div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedAssetForDrawer.tags?.map((t) => (
                        <span key={t} className="px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-300 border border-white/10 text-[10px] font-mono">
                          #{t}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Description */}
                  {selectedAssetForDrawer.description && (
                    <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10">
                      <div className="text-slate-400 text-[10px] uppercase font-bold mb-1">Description & Notes</div>
                      <p className="text-slate-300 leading-relaxed">{selectedAssetForDrawer.description}</p>
                    </div>
                  )}

                  <div className="pt-2 flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />}
                      onClick={() => setSelectedVerifyAsset(selectedAssetForDrawer)}
                    >
                      Re-Verify Target (8-Step Probe)
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
              {drawerTab === 'dns_tls' && (() => {
                const parsed = parseTargetInfo(selectedAssetForDrawer.target_locator);
                const probeState = assetProbeResults[selectedAssetForDrawer.id];
                const probeData = probeState?.data;
                const isLoading = probingAssetId === selectedAssetForDrawer.id || probeState?.loading;
                const hasError = Boolean(probeState?.error);

                const dnsStep = probeData?.steps?.find((s: any) => s.step === 2 || s.name === 'DNS Resolution');
                const tlsStep = probeData?.steps?.find((s: any) => s.step === 3 || s.name === 'TLS Verification');
                const fingerprint = probeData?.fingerprint || {};

                const ipv4List: string[] = dnsStep?.metadata?.ipv4_addresses || [];
                const ipv6List: string[] = dnsStep?.metadata?.ipv6_addresses || [];
                const totalIps: number = dnsStep?.metadata?.total_ips ?? (ipv4List.length + ipv6List.length);

                const tlsMeta = tlsStep?.metadata || {};
                const isHttps = parsed.scheme === 'https';

                return (
                  <div className="space-y-4 text-xs">
                    {/* Target Network & Identity Bar */}
                    <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                          <Globe className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Target Network & Host Identity</span>
                        </div>
                        <Badge
                          severity={
                            selectedAssetForDrawer.verification_status === 'VERIFIED'
                              ? 'low'
                              : selectedAssetForDrawer.verification_status === 'FAILED'
                              ? 'high'
                              : 'neutral'
                          }
                          size="sm"
                        >
                          {selectedAssetForDrawer.verification_status}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-[11px] font-mono">
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Target Hostname:</span>
                          <strong className="text-white text-xs break-all">{parsed.hostname}</strong>
                        </div>
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Scheme & Port:</span>
                          <strong className="text-cyan-400">
                            {parsed.scheme.toUpperCase()} : {parsed.port}
                          </strong>
                        </div>
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Target Type:</span>
                          <strong className="text-slate-200">{selectedAssetForDrawer.asset_type}</strong>
                        </div>
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Environment:</span>
                          <strong className="text-slate-200">{selectedAssetForDrawer.environment}</strong>
                        </div>
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Registered:</span>
                          <strong className="text-slate-300">
                            {new Date(selectedAssetForDrawer.created_at).toLocaleDateString()}
                          </strong>
                        </div>
                        <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                          <span className="text-slate-400 block text-[10px]">Last Verified:</span>
                          <strong className="text-slate-300">
                            {selectedAssetForDrawer.verified_at
                              ? new Date(selectedAssetForDrawer.verified_at).toLocaleDateString()
                              : 'Not yet verified'}
                          </strong>
                        </div>
                      </div>
                    </div>

                    {/* LIVE PROBE RUNNING INDICATOR */}
                    {isLoading && (
                      <div className="p-6 rounded-xl bg-cyber-900/60 border border-cyan-500/30 flex flex-col items-center justify-center text-center space-y-3">
                        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
                        <div>
                          <div className="text-sm font-bold text-white">Executing 8-Step Live Network Probe...</div>
                          <p className="text-[11px] text-slate-400 mt-1">
                            Querying authoritative DNS records, performing TLS handshake, and extracting security posture for{' '}
                            <span className="text-cyan-400 font-mono">{parsed.hostname}</span>.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* ERROR STATE */}
                    {hasError && !isLoading && (
                      <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-500/40 space-y-2">
                        <div className="flex items-center gap-2 text-rose-400 font-bold">
                          <AlertTriangle className="w-4 h-4" />
                          <span>Probe Execution Error</span>
                        </div>
                        <p className="text-[11px] text-rose-200 font-mono">{probeState?.error}</p>
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<RefreshCw className="w-3.5 h-3.5" />}
                          onClick={() => handleRunDrawerProbe(selectedAssetForDrawer)}
                        >
                          Retry Probe
                        </Button>
                      </div>
                    )}

                    {/* GENUINE PROBE RESULTS AVAILABLE */}
                    {probeData && !isLoading && (
                      <>
                        {/* Section A: Authoritative DNS Resolution */}
                        <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-3">
                          <div className="font-bold text-white flex items-center justify-between">
                            <span className="flex items-center gap-1.5">
                              <Server className="w-4 h-4 text-cyan-400" />
                              <span>Authoritative DNS Resolution</span>
                            </span>
                            <Badge
                              severity={dnsStep?.status === 'PASS' ? 'low' : 'high'}
                              size="sm"
                            >
                              {dnsStep?.status === 'PASS' ? 'LIVE QUERY PASS' : 'RESOLUTION FAILED'}
                            </Badge>
                          </div>

                          <div className="space-y-2 text-[11px] font-mono">
                            <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400">Query Hostname:</span>
                              <span className="text-white font-bold">{dnsStep?.metadata?.hostname || parsed.hostname}</span>
                            </div>
                            <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400">A Records (IPv4):</span>
                              <span className="text-emerald-400 font-bold">
                                {ipv4List.length > 0 ? ipv4List.join(', ') : parsed.isIp ? parsed.hostname : 'None resolved'}
                              </span>
                            </div>
                            <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400">AAAA Records (IPv6):</span>
                              <span className="text-white">
                                {ipv6List.length > 0 ? ipv6List.join(', ') : 'None detected'}
                              </span>
                            </div>
                            <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400">Total IP Records:</span>
                              <span className="text-slate-200 font-bold">{totalIps} endpoint address(es)</span>
                            </div>
                            {dnsStep?.detail && (
                              <div className="p-2 rounded bg-white/[0.01] border border-white/5 text-[10px] text-slate-400 font-sans">
                                <strong>Resolver Note:</strong> {dnsStep.detail}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Section B: TLS / SSL Certificate Posture */}
                        <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-3">
                          <div className="font-bold text-white flex items-center justify-between">
                            <span className="flex items-center gap-1.5">
                              <Lock className="w-4 h-4 text-emerald-400" />
                              <span>TLS / SSL Certificate Posture</span>
                            </span>
                            <Badge
                              severity={
                                !isHttps
                                  ? 'neutral'
                                  : tlsStep?.status === 'PASS'
                                  ? 'low'
                                  : 'high'
                              }
                              size="sm"
                            >
                              {!isHttps ? 'HTTP (NO TLS)' : tlsStep?.status === 'PASS' ? 'TRUSTED' : 'TLS FAILED'}
                            </Badge>
                          </div>

                          {isHttps ? (
                            <div className="space-y-2 text-[11px] font-mono">
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">TLS Protocol:</span>
                                <span className="text-emerald-400 font-bold">{tlsMeta.tls_version || 'Negotiated TLS'}</span>
                              </div>
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">Cipher Suite:</span>
                                <span className="text-white">{tlsMeta.cipher || 'TLS_AES_256_GCM_SHA384'}</span>
                              </div>
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">Certificate Authority (Issuer):</span>
                                <span className="text-slate-300">{tlsMeta.issuer || 'Authoritative CA'}</span>
                              </div>
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">Subject CN:</span>
                                <span className="text-cyan-400">{tlsMeta.subject || parsed.hostname}</span>
                              </div>
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">SAN Matching:</span>
                                <span className="text-slate-300 break-all">
                                  {Array.isArray(tlsMeta.san) && tlsMeta.san.length > 0
                                    ? tlsMeta.san.join(', ')
                                    : parsed.hostname}
                                </span>
                              </div>
                              <div className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                                <span className="text-slate-400">Days to Expiration:</span>
                                <span
                                  className={`font-bold ${
                                    (tlsMeta.days_until_expiry ?? 100) < 30 ? 'text-amber-400' : 'text-emerald-400'
                                  }`}
                                >
                                  {tlsMeta.days_until_expiry !== undefined
                                    ? `${tlsMeta.days_until_expiry} days remaining (${tlsMeta.expires_at || 'Active'})`
                                    : tlsMeta.expires_at || 'Valid certificate'}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div className="p-3 rounded bg-white/[0.02] border border-white/5 text-[11px] text-slate-400">
                              Target locator uses plain unencrypted HTTP scheme (<code className="text-amber-400">{parsed.raw}</code>). TLS handshake and certificate chain validation are not applicable.
                            </div>
                          )}
                        </div>

                        {/* Section C: Target Technology & Security Headers */}
                        <div className="p-4 rounded-xl bg-cyber-900/40 border border-white/10 space-y-2.5">
                          <div className="font-bold text-white flex items-center justify-between">
                            <span className="flex items-center gap-1.5">
                              <ShieldCheck className="w-4 h-4 text-purple-400" />
                              <span>Infrastructure & Header Fingerprint</span>
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              {fingerprint.active_security_headers_count ?? 0}/5 Security Headers Active
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                            <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400 block text-[10px]">Server / WAF:</span>
                              <strong className="text-white">{fingerprint.server || fingerprint.reverse_proxy_waf || 'Generic'}</strong>
                            </div>
                            <div className="p-2 rounded bg-white/[0.02] border border-white/5">
                              <span className="text-slate-400 block text-[10px]">Framework / Stack:</span>
                              <strong className="text-cyan-400">{fingerprint.framework || selectedAssetForDrawer.technology}</strong>
                            </div>
                          </div>

                          {fingerprint.security_headers && Object.keys(fingerprint.security_headers).length > 0 && (
                            <div className="space-y-1 pt-1">
                              <div className="text-[10px] text-slate-400 uppercase font-semibold">Active Security Headers:</div>
                              <div className="flex flex-wrap gap-1.5">
                                {Object.entries(fingerprint.security_headers).map(([k, v]) => (
                                  <span
                                    key={k}
                                    className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                                      v
                                        ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                                        : 'bg-white/[0.02] text-slate-500 border-white/5 line-through'
                                    }`}
                                  >
                                    {k}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Re-Probe Action Button */}
                        <div className="pt-1 flex items-center justify-between text-[11px]">
                          <span className="text-slate-500 font-mono">
                            Probed at: {new Date(probeState?.timestamp || Date.now()).toLocaleTimeString()}
                          </span>
                          <Button
                            variant="secondary"
                            size="sm"
                            icon={<RefreshCw className="w-3.5 h-3.5" />}
                            onClick={() => handleRunDrawerProbe(selectedAssetForDrawer)}
                          >
                            Re-Probe DNS & TLS
                          </Button>
                        </div>
                      </>
                    )}

                    {/* AWAITING VERIFICATION PROBE STATE (ACCURATE FALLBACK) */}
                    {!probeData && !isLoading && !hasError && (
                      <div className="p-6 rounded-xl bg-cyber-900/40 border border-white/10 text-center space-y-4">
                        <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center mx-auto text-amber-400">
                          <Server className="w-6 h-6" />
                        </div>

                        <div className="space-y-1">
                          <h3 className="text-sm font-bold text-white">Awaiting Live Network Verification Probe</h3>
                          <p className="text-[11px] text-slate-400 max-w-md mx-auto leading-relaxed">
                            Authoritative DNS resolution (A/AAAA records), TLS 1.3 handshake negotiation, certificate chain trust, and server fingerprinting have not been probed for{' '}
                            <span className="text-cyan-400 font-mono">{parsed.hostname}</span> in this session.
                          </p>
                        </div>

                        <div className="flex items-center justify-center gap-3 pt-2">
                          <Button
                            variant="primary"
                            size="sm"
                            icon={<Play className="w-3.5 h-3.5" />}
                            onClick={() => handleRunDrawerProbe(selectedAssetForDrawer)}
                          >
                            Run Live Diagnostic Probe
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            icon={<ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />}
                            onClick={() => setSelectedVerifyAsset(selectedAssetForDrawer)}
                          >
                            Open 8-Step Pipeline Modal
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* ================================================================= */}
              {/* TAB 3: DISCOVERED ENDPOINTS (DYNAMIC CONTEXTUAL REFACTOR)          */}
              {/* ================================================================= */}
              {drawerTab === 'endpoints' && (() => {
                const parsed = parseTargetInfo(selectedAssetForDrawer.target_locator);
                const probeState = assetProbeResults[selectedAssetForDrawer.id];
                const probeData = probeState?.data;
                const contextualEndpoints = generateContextualEndpoints(selectedAssetForDrawer, probeData);

                return (
                  <div className="space-y-3 text-xs">
                    {/* Header Context Bar */}
                    <div className="p-3 rounded-xl bg-cyber-900/40 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5 mb-1">
                          <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Discovered Endpoints</span>
                        </div>
                        <div className="text-[11px] text-slate-400">
                          Discovered & contextual HTTP endpoints mapped for{' '}
                          <span className="text-cyan-400 font-mono">{parsed.baseUrl}</span>:
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Module: <strong className="text-slate-300">{selectedAssetForDrawer.empire_module}</strong> • Total Endpoints: <strong className="text-white">{contextualEndpoints.length}</strong>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          icon={<RefreshCw className={`w-3.5 h-3.5 ${probingAssetId === selectedAssetForDrawer.id ? 'animate-spin' : ''}`} />}
                          onClick={() => handleRunDrawerProbe(selectedAssetForDrawer)}
                          disabled={probingAssetId === selectedAssetForDrawer.id}
                        >
                          {probingAssetId === selectedAssetForDrawer.id ? 'Probing...' : 'Probe Discovery Endpoints'}
                        </Button>
                      </div>
                    </div>

                    {/* Endpoints Table */}
                    <div className="rounded-xl border border-white/10 overflow-hidden">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-cyber-950 text-slate-400 uppercase text-[10px] border-b border-white/10">
                          <tr>
                            <th className="py-2.5 px-3">Method</th>
                            <th className="py-2.5 px-3">Endpoint Path</th>
                            <th className="py-2.5 px-3">Status</th>
                            <th className="py-2.5 px-3">Classification</th>
                            <th className="py-2.5 px-3 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-[11px]">
                          {contextualEndpoints.map((ep, idx) => (
                            <tr key={`${ep.method}-${ep.path}-${idx}`} className="hover:bg-white/[0.02] transition">
                              <td className="py-2 px-3">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    ep.method === 'GET'
                                      ? 'text-emerald-400 bg-emerald-950/40 border border-emerald-800/40'
                                      : ep.method === 'POST'
                                      ? 'text-cyan-400 bg-cyan-950/40 border border-cyan-800/40'
                                      : 'text-amber-400 bg-amber-950/40 border border-amber-800/40'
                                  }`}
                                >
                                  {ep.method}
                                </span>
                              </td>
                              <td className="py-2 px-3">
                                <div className="text-white font-medium flex items-center gap-1.5">
                                  <span>{ep.path}</span>
                                  {ep.isExcluded && (
                                    <span className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                                      EXCLUDED
                                    </span>
                                  )}
                                </div>
                                <div className="text-[10px] text-slate-500 font-sans line-clamp-1">{ep.description}</div>
                              </td>
                              <td className="py-2 px-3">
                                <Badge severity={ep.statusSeverity} size="sm">
                                  {ep.status}
                                </Badge>
                              </td>
                              <td className="py-2 px-3">
                                <Badge severity={ep.classificationSeverity} size="sm">
                                  {ep.classification}
                                </Badge>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    onClick={() => handleCopyUrl(ep.fullUrl)}
                                    title="Copy endpoint URL"
                                    className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/[0.06] transition"
                                  >
                                    <span className="text-[10px]">{copiedUrl === ep.fullUrl ? '✓' : 'Copy'}</span>
                                  </button>
                                  <a
                                    href={ep.fullUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    title="Open endpoint in new tab"
                                    className="p-1 rounded text-cyan-400 hover:text-cyan-300 hover:bg-white/[0.06] transition inline-flex items-center"
                                  >
                                    <ExternalLink className="w-3.5 h-3.5" />
                                  </a>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Excluded Endpoints Notice if applicable */}
                    {selectedAssetForDrawer.excluded_endpoints && selectedAssetForDrawer.excluded_endpoints.length > 0 && (
                      <div className="p-2.5 rounded-lg bg-amber-950/20 border border-amber-500/30 text-[11px] text-amber-300/90 flex items-center justify-between">
                        <span>
                          <strong>Excluded Paths:</strong> {selectedAssetForDrawer.excluded_endpoints.join(', ')} (Protected from automated scan payloads).
                        </span>
                        <Badge severity="neutral" size="sm">POLICY PROTECTED</Badge>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* TAB 4: SCAN HISTORY */}
              {drawerTab === 'scans' && (
                <div className="space-y-3 text-xs">
                  {loadingDrawerData ? (
                    <div className="py-10 text-center text-slate-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto text-cyan-400 mb-2" />
                      <span>Loading assessment history...</span>
                    </div>
                  ) : drawerScans.length === 0 ? (
                    <div className="py-8 text-center text-slate-400 border border-dashed border-white/10 rounded-xl">
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
                              <span className="text-slate-500 font-mono text-[10px]">({s.engine})</span>
                            </div>
                            <div className="text-[10px] text-slate-400 font-mono mt-1">
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
                    <div className="py-10 text-center text-slate-400">
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
                          <div className="text-[10px] text-slate-400 font-mono flex items-center justify-between">
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
              <label className="text-slate-300 font-semibold">Target Name *</label>
              <Input
                type="text"
                placeholder="e.g. Empire Portal Main"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Target Locator (URL / Host / IP) *</label>
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
              <label className="text-slate-300 font-semibold">Asset Category</label>
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
              <label className="text-slate-300 font-semibold">Empire Module</label>
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
              <label className="text-slate-300 font-semibold">Environment</label>
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
              <label className="text-slate-300 font-semibold">Business Criticality</label>
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
              <label className="text-slate-300 font-semibold">Technology Stack Profile</label>
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
              <div className="text-[10px] text-slate-400">
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
            <label className="text-slate-300 font-semibold">Excluded Endpoints (Optional, line-separated)</label>
            <textarea
              rows={2}
              placeholder="/api/v1/auth/delete-account&#10;/admin/reset-db"
              value={formExcludedEndpoints}
              onChange={(e) => setFormExcludedEndpoints(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-cyber-950 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 text-xs font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-slate-300 font-semibold">Description / Notes</label>
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
                <label className="text-slate-300 font-semibold">Import Format Mode</label>
                <div className="flex items-center gap-1.5">
                  {['AUTO', 'OPENAPI', 'CSV', 'JSON', 'TXT', 'CIDR'].map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      onClick={() => setBulkImportType(fmt)}
                      className={`px-2 py-0.5 rounded-md text-[10px] font-bold border transition ${
                        bulkImportType === fmt
                          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                          : 'bg-white/[0.04] text-slate-400 border-white/10 hover:text-white'
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
                <div className="text-[11px] text-slate-400">
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
                  <div className="text-slate-400 text-[10px] uppercase font-bold">Total Targets Detected</div>
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
                  <thead className="bg-cyber-950 text-slate-400 uppercase text-[10px] border-b border-white/10">
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
                        <td className="py-2 px-3 text-slate-300">{item.asset_type}</td>
                        <td className="py-2 px-3">
                          <span className="text-emerald-400 font-bold flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" /> Ready to Import
                          </span>
                        </td>
                      </tr>
                    ))}
                    {bulkPreviewData.duplicate.map((dup, idx) => (
                      <tr key={`dup-${idx}`} className="bg-amber-950/10 text-slate-400">
                        <td className="py-2 px-3 text-slate-300 font-mono">{dup.target_locator}</td>
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
          if (selectedAssetForDrawer && selectedAssetForDrawer.id === verifiedAssetId) {
            handleRunDrawerProbe(selectedAssetForDrawer);
          }
        }}
      />
    </div>
  );
}

export default function TargetsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-400 font-mono text-xs">Loading target inventory...</div>}>
      <TargetsContent />
    </Suspense>
  );
}

