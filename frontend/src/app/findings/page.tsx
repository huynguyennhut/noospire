'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  AlertTriangle,
  Search,
  ShieldAlert,
  RefreshCw,
  RotateCcw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Download,
  CheckSquare,
  Square,
  MinusSquare,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Eye,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Finding } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import EvidenceViewer from '@/components/evidence/EvidenceViewer';
import {
  Button,
  Badge,
  Input,
  Modal,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableEmpty,
} from '@/components/ui';

type SortField =
  | 'severity'
  | 'title'
  | 'target_location'
  | 'target_component'
  | 'status'
  | 'first_seen_at';
type SortDirection = 'asc' | 'desc' | null;

const SEVERITY_RANK: Record<string, number> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
  INFO: 1,
};

function FindingsContent() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const initialModule = searchParams?.get('module');
  const initialAssetId = searchParams?.get('assetId');

  // Core Data
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [moduleFilter, setModuleFilter] = useState<string>(initialModule || 'ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Sorting
  const [sortField, setSortField] = useState<SortField>('severity');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Bulk Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState<string>('IN_REMEDIATION');
  const [bulkAssignee, setBulkAssignee] = useState<string>('');
  const [bulkProcessing, setBulkProcessing] = useState(false);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Modal / Detail Drill-Down
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [rowRetestingId, setRowRetestingId] = useState<string | null>(null);

  const fetchFindings = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.listFindings({
        assetId: initialAssetId || undefined,
        module: moduleFilter !== 'ALL' ? moduleFilter : undefined,
      });
      setFindings(res.items || []);
    } catch (err) {
      console.error('Failed to fetch findings:', err);
    } finally {
      setLoading(false);
    }
  }, [initialAssetId, moduleFilter]);

  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  // Handle Sort Toggle
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      if (sortDirection === 'asc') setSortDirection('desc');
      else if (sortDirection === 'desc') {
        setSortField('first_seen_at');
        setSortDirection('desc');
      }
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Filtered Findings
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const term = searchTerm.toLowerCase();
      const matchesSearch =
        !searchTerm ||
        (f.title || '').toLowerCase().includes(term) ||
        (f.description || '').toLowerCase().includes(term) ||
        (f.target_location || '').toLowerCase().includes(term) ||
        (f.target_component && f.target_component.toLowerCase().includes(term)) ||
        (f.cve_id && f.cve_id.toLowerCase().includes(term)) ||
        (f.scanner_rule_id || '').toLowerCase().includes(term);

      const matchesSeverity =
        severityFilter === 'ALL' || (f.severity || '').toUpperCase() === severityFilter;
      const matchesStatus =
        statusFilter === 'ALL' || (f.status || '').toUpperCase() === statusFilter;
      const matchesModule =
        moduleFilter === 'ALL' || f.empire_module === moduleFilter;

      return matchesSearch && matchesSeverity && matchesStatus && matchesModule;
    });
  }, [findings, searchTerm, severityFilter, statusFilter, moduleFilter]);

  // Sorted Findings
  const sortedFindings = useMemo(() => {
    if (!sortField || !sortDirection) return filteredFindings;

    return [...filteredFindings].sort((a, b) => {
      let cmp = 0;
      if (sortField === 'severity') {
        const rankA = SEVERITY_RANK[a.severity?.toUpperCase()] || 0;
        const rankB = SEVERITY_RANK[b.severity?.toUpperCase()] || 0;
        cmp = rankA - rankB;
      } else if (sortField === 'first_seen_at') {
        const timeA = new Date(a.first_seen_at || 0).getTime();
        const timeB = new Date(b.first_seen_at || 0).getTime();
        cmp = timeA - timeB;
      } else if (sortField === 'title') {
        cmp = (a.title || '').localeCompare(b.title || '');
      } else if (sortField === 'target_location') {
        cmp = (a.target_location || '').localeCompare(b.target_location || '');
      } else if (sortField === 'target_component') {
        cmp = (a.target_component || '').localeCompare(b.target_component || '');
      } else if (sortField === 'status') {
        cmp = (a.status || '').localeCompare(b.status || '');
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });
  }, [filteredFindings, sortField, sortDirection]);

  // Paginated Slice
  const totalPages = Math.ceil(sortedFindings.length / pageSize) || 1;
  const paginatedFindings = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedFindings.slice(start, start + pageSize);
  }, [sortedFindings, currentPage, pageSize]);

  // Checkbox Selection
  const allCurrentPageSelected =
    paginatedFindings.length > 0 &&
    paginatedFindings.every((f) => selectedIds.has(f.id));
  const someCurrentPageSelected =
    paginatedFindings.some((f) => selectedIds.has(f.id)) && !allCurrentPageSelected;

  const toggleSelectAllPage = () => {
    const next = new Set(selectedIds);
    if (allCurrentPageSelected) {
      paginatedFindings.forEach((f) => next.delete(f.id));
    } else {
      paginatedFindings.forEach((f) => next.add(f.id));
    }
    setSelectedIds(next);
  };

  const toggleSelectRow = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  // Bulk Triage Apply
  const handleApplyBulkStatus = async (overrideStatus?: string) => {
    if (selectedIds.size === 0) return;
    const targetStatus = overrideStatus || bulkStatus;
    try {
      setBulkProcessing(true);
      const updates = Array.from(selectedIds).map((id) =>
        api.triageFinding(
          id,
          targetStatus,
          `Bulk updated via Command Center`,
          bulkAssignee || undefined
        )
      );
      await Promise.allSettled(updates);
      await fetchFindings();
      setSelectedIds(new Set());
    } catch (err) {
      alert(`Bulk triage failed: ${err}`);
    } finally {
      setBulkProcessing(false);
    }
  };

  // Live Retest on Single Row
  const handleRowRetest = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setRowRetestingId(id);
      await api.retestFinding(id);
      const refreshed = await api.getFinding(id);
      setFindings((prev) => prev.map((f) => (f.id === id ? refreshed : f)));
      if (selectedFinding?.id === id) {
        setSelectedFinding(refreshed);
      }
    } catch (err) {
      alert(`Live retest failed: ${err}`);
    } finally {
      setRowRetestingId(null);
    }
  };

  // Export to CSV
  const handleExportCsv = () => {
    const exportItems =
      selectedIds.size > 0
        ? findings.filter((f) => selectedIds.has(f.id))
        : sortedFindings;

    const headers = [
      'ID',
      'Severity',
      'Title',
      'Scanner Engine',
      'Rule ID',
      'Empire Module',
      'Target Location',
      'Target Component',
      'Lifecycle Status',
      'Assignee',
      'CVE ID',
      'CWE ID',
      'CVSS Score',
      'Retest Status',
      'First Seen At',
    ];

    const rows = exportItems.map((f) => [
      f.id,
      f.severity,
      `"${(f.title || '').replace(/"/g, '""')}"`,
      f.scanner_engine || '',
      f.scanner_rule_id || '',
      f.empire_module || 'CORE',
      `"${(f.target_location || '').replace(/"/g, '""')}"`,
      `"${(f.target_component || '').replace(/"/g, '""')}"`,
      f.status || 'OPEN',
      `"${(f.assignee || '').replace(/"/g, '""')}"`,
      f.cve_id || '',
      f.cwe_id || '',
      f.cvss_score ?? '',
      f.retest_status || '',
      f.first_seen_at || '',
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `noosforge_findings_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export to JSON
  const handleExportJson = () => {
    const exportItems =
      selectedIds.size > 0
        ? findings.filter((f) => selectedIds.has(f.id))
        : sortedFindings;

    const payload = {
      exported_at: new Date().toISOString(),
      platform: 'NOOSFORGE Security Intelligence',
      total_findings: exportItems.length,
      findings: exportItems,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8;',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `noosforge_findings_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getSortIcon = (field: SortField) => {
    if (sortField !== field) {
      return <ArrowUpDown className="w-3 h-3 text-slate-600 group-hover:text-slate-400" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="w-3 h-3 text-cyan-400" />
    ) : (
      <ArrowDown className="w-3 h-3 text-cyan-400" />
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-rose-500" />
            <h1 className="text-2xl font-black tracking-tight text-white">
              {t('findings.title', 'FINDINGS & EVIDENCE COMMAND CENTER')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t(
              'findings.subtitle',
              'Enterprise vulnerability management, multi-column sorting, bulk lifecycle triage, live forensic drill-down, and verification.'
            )}
          </p>
        </div>

        {/* Top Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportCsv}
            icon={<Download className="w-3.5 h-3.5" />}
          >
            Export CSV {selectedIds.size > 0 && `(${selectedIds.size})`}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportJson}
            icon={<Download className="w-3.5 h-3.5" />}
          >
            Export JSON
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={fetchFindings}
            loading={loading}
            icon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            {t('common.refresh', 'Refresh')}
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="p-3.5 rounded-2xl liquid-glass-card flex flex-wrap gap-3 items-center justify-between text-xs border border-white/10 shadow-lg">
        <div className="flex flex-wrap items-center gap-2.5 flex-1">
          <div className="w-full sm:w-64">
            <Input
              type="text"
              placeholder={t('findings.searchPlaceholder', 'Search CVE, endpoint, title, rule...')}
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              onClear={() => setSearchTerm('')}
              icon={<Search className="w-3.5 h-3.5" />}
            />
          </div>

          <select
            value={severityFilter}
            onChange={(e) => {
              setSeverityFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('findings.allSeverities', 'All Severities')}</option>
            <option value="CRITICAL">{t('severity.critical', 'Critical')}</option>
            <option value="HIGH">{t('severity.high', 'High')}</option>
            <option value="MEDIUM">{t('severity.medium', 'Medium')}</option>
            <option value="LOW">{t('severity.low', 'Low')}</option>
            <option value="INFO">{t('severity.info', 'Informational')}</option>
          </select>

          <select
            value={moduleFilter}
            onChange={(e) => {
              setModuleFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('targets.allModules', 'All Empire Modules')}</option>
            <option value="STUDENT_MANAGEMENT">Student Management</option>
            <option value="LEARNING_MATERIALS">Learning Materials</option>
            <option value="SUPPORTING_TOOLS">Supporting Tools</option>
            <option value="API_SERVICES">API Services</option>
            <option value="WEB_APPLICATION">Web Application</option>
            <option value="SERVER_INFRASTRUCTURE">Infrastructure</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-1.5 rounded-xl bg-cyber-950/80 border border-white/10 text-slate-300 focus:outline-none focus:border-cyan-500 text-xs"
          >
            <option value="ALL">{t('findings.allLifecycle', 'All Lifecycle States')}</option>
            <option value="OPEN">OPEN</option>
            <option value="IN_REMEDIATION">IN REMEDIATION</option>
            <option value="FIXED">FIXED</option>
            <option value="REOPENED">REOPENED</option>
            <option value="ACCEPTED_RISK">ACCEPTED RISK</option>
            <option value="FALSE_POSITIVE">FALSE POSITIVE</option>
          </select>

          {(searchTerm || severityFilter !== 'ALL' || moduleFilter !== 'ALL' || statusFilter !== 'ALL') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearchTerm('');
                setSeverityFilter('ALL');
                setModuleFilter('ALL');
                setStatusFilter('ALL');
                setCurrentPage(1);
              }}
            >
              Reset Filters
            </Button>
          )}
        </div>

        {/* Results Counter & Page Size Selector */}
        <div className="flex items-center gap-3 text-slate-400 text-xs">
          <div>
            Showing <strong className="text-white font-mono">{sortedFindings.length}</strong> matching
          </div>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="px-2 py-1 rounded-lg bg-cyber-950/80 border border-white/10 text-slate-300 text-xs focus:outline-none"
          >
            <option value={10}>10 / page</option>
            <option value={25}>25 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
          </select>
        </div>
      </div>

      {/* Main Sortable Table */}
      <div className="rounded-2xl liquid-glass-card border border-white/10 shadow-2xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              {/* Checkbox Col */}
              <TableHead className="w-10 text-center">
                <button
                  type="button"
                  onClick={toggleSelectAllPage}
                  className="p-1 rounded text-slate-400 hover:text-white"
                  title="Select all on current page"
                >
                  {allCurrentPageSelected ? (
                    <CheckSquare className="w-4 h-4 text-cyan-400" />
                  ) : someCurrentPageSelected ? (
                    <MinusSquare className="w-4 h-4 text-cyan-400" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-600" />
                  )}
                </button>
              </TableHead>

              {/* Severity Col */}
              <TableHead
                onClick={() => handleSort('severity')}
                className="cursor-pointer group select-none w-28"
              >
                <div className="flex items-center gap-1.5">
                  <span>{t('findings.colSeverity', 'Severity')}</span>
                  {getSortIcon('severity')}
                </div>
              </TableHead>

              {/* Title & Rule Col */}
              <TableHead
                onClick={() => handleSort('title')}
                className="cursor-pointer group select-none"
              >
                <div className="flex items-center gap-1.5">
                  <span>{t('findings.colTitle', 'Finding Title & Rule')}</span>
                  {getSortIcon('title')}
                </div>
              </TableHead>

              {/* Target / Asset Col */}
              <TableHead
                onClick={() => handleSort('target_location')}
                className="cursor-pointer group select-none hidden md:table-cell"
              >
                <div className="flex items-center gap-1.5">
                  <span>Target / Asset</span>
                  {getSortIcon('target_location')}
                </div>
              </TableHead>

              {/* Component Col */}
              <TableHead
                onClick={() => handleSort('target_component')}
                className="cursor-pointer group select-none hidden lg:table-cell"
              >
                <div className="flex items-center gap-1.5">
                  <span>Component</span>
                  {getSortIcon('target_component')}
                </div>
              </TableHead>

              {/* Lifecycle Status Col */}
              <TableHead
                onClick={() => handleSort('status')}
                className="cursor-pointer group select-none text-center w-32"
              >
                <div className="flex items-center justify-center gap-1.5">
                  <span>Lifecycle</span>
                  {getSortIcon('status')}
                </div>
              </TableHead>

              {/* Detected Date Col */}
              <TableHead
                onClick={() => handleSort('first_seen_at')}
                className="cursor-pointer group select-none hidden xl:table-cell w-32"
              >
                <div className="flex items-center gap-1.5">
                  <span>Detected</span>
                  {getSortIcon('first_seen_at')}
                </div>
              </TableHead>

              {/* Actions Col */}
              <TableHead className="text-right w-28">Actions</TableHead>
            </TableRow>
          </TableHeader>

          <TableBody>
            {paginatedFindings.length === 0 ? (
              <TableEmpty
                colSpan={8}
                message={
                  loading
                    ? 'Loading security findings...'
                    : 'No vulnerabilities match the selected filters.'
                }
              />
            ) : (
              paginatedFindings.map((f) => {
                const isSelected = selectedIds.has(f.id);
                return (
                  <TableRow
                    key={f.id}
                    onClick={() => setSelectedFinding(f)}
                    className={`cursor-pointer transition ${
                      isSelected
                        ? 'bg-cyan-950/40 border-l-2 border-l-cyan-400'
                        : selectedFinding?.id === f.id
                        ? 'bg-white/[0.04]'
                        : 'hover:bg-white/[0.02]'
                    }`}
                  >
                    {/* Checkbox */}
                    <TableCell className="text-center" onClick={(e) => toggleSelectRow(f.id, e)}>
                      <button
                        type="button"
                        className="p-1 rounded text-slate-400 hover:text-white"
                      >
                        {isSelected ? (
                          <CheckSquare className="w-4 h-4 text-cyan-400" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-600" />
                        )}
                      </button>
                    </TableCell>

                    {/* Severity Badge */}
                    <TableCell>
                      <Badge severity={f.severity.toLowerCase()} size="sm" dot>
                        {f.severity}
                      </Badge>
                    </TableCell>

                    {/* Title & Rule */}
                    <TableCell>
                      <div className="font-bold text-white text-xs">{f.title}</div>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-[11px] text-slate-400">
                        <span className="font-mono text-cyan-400 font-semibold">
                          {f.scanner_rule_id}
                        </span>
                        {f.cve_id && (
                          <span className="px-1.5 py-0.2 rounded bg-white/[0.04] text-slate-300 border border-white/10 font-mono text-[10px]">
                            {f.cve_id}
                          </span>
                        )}
                        {f.cvss_score && (
                          <span className="font-mono text-[10px] text-amber-400">
                            CVSS {f.cvss_score}
                          </span>
                        )}
                      </div>
                    </TableCell>

                    {/* Target / Asset */}
                    <TableCell className="hidden md:table-cell font-mono text-[11px] text-slate-300 max-w-[200px] truncate">
                      <span title={f.target_location}>{f.target_location}</span>
                    </TableCell>

                    {/* Component */}
                    <TableCell className="hidden lg:table-cell text-slate-400 font-mono text-[11px]">
                      {f.target_component || f.empire_module || 'ROOT'}
                    </TableCell>

                    {/* Lifecycle Status */}
                    <TableCell className="text-center">
                      <span
                        className={`px-2 py-0.5 rounded-md text-[10px] font-bold border uppercase ${
                          f.status === 'FIXED'
                            ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800'
                            : f.status === 'REOPENED'
                            ? 'bg-rose-950/80 text-rose-400 border-rose-800 animate-pulse'
                            : f.status === 'IN_REMEDIATION'
                            ? 'bg-blue-950/80 text-blue-400 border-blue-800'
                            : f.status === 'ACCEPTED_RISK'
                            ? 'bg-slate-900/80 text-slate-400 border-slate-700'
                            : f.status === 'FALSE_POSITIVE'
                            ? 'bg-slate-950/80 text-slate-500 border-slate-800 line-through'
                            : 'bg-rose-950/60 text-rose-300 border-rose-900/60'
                        }`}
                      >
                        {f.status || 'OPEN'}
                      </span>
                    </TableCell>

                    {/* Detected Date */}
                    <TableCell className="hidden xl:table-cell text-slate-400 font-mono text-[10px]">
                      {f.first_seen_at
                        ? new Date(f.first_seen_at).toLocaleDateString()
                        : 'Recent'}
                    </TableCell>

                    {/* Row Quick Actions */}
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={(e) => handleRowRetest(f.id, e)}
                          disabled={rowRetestingId === f.id}
                          title="Execute live probe retest against target"
                          className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-cyan-400 border border-white/10 hover:border-cyan-500/40 transition"
                        >
                          <RotateCcw
                            className={`w-3.5 h-3.5 ${
                              rowRetestingId === f.id ? 'animate-spin text-cyan-400' : ''
                            }`}
                          />
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedFinding(f)}
                          title="View forensic evidence & details"
                          className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 hover:text-white border border-white/10 transition"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {/* Pagination Controls Footer */}
        <div className="p-3.5 bg-cyber-950/80 border-t border-white/10 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="text-slate-400">
            Page <strong className="text-white font-mono">{currentPage}</strong> of{' '}
            <strong className="text-white font-mono">{totalPages}</strong> (
            {sortedFindings.length} findings)
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] disabled:opacity-30 disabled:pointer-events-none text-slate-300 border border-white/10"
            >
              <ChevronsLeft className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] disabled:opacity-30 disabled:pointer-events-none text-slate-300 border border-white/10"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>

            <span className="px-3 py-1 text-slate-300 font-mono text-xs">
              {currentPage} / {totalPages}
            </span>

            <button
              type="button"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] disabled:opacity-30 disabled:pointer-events-none text-slate-300 border border-white/10"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] disabled:opacity-30 disabled:pointer-events-none text-slate-300 border border-white/10"
            >
              <ChevronsRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Floating Bulk Action Bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 w-full max-w-3xl px-4 animate-fadeIn">
          <div className="p-3.5 rounded-2xl liquid-glass-modal border border-cyan-400/40 shadow-2xl flex flex-wrap items-center justify-between gap-3 text-xs bg-cyber-950/95 backdrop-blur-xl">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              <strong className="text-white font-mono">{selectedIds.size}</strong>
              <span className="text-slate-300">findings selected</span>
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="text-[11px] text-slate-400 hover:text-white underline ml-1"
              >
                Clear
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={bulkStatus}
                onChange={(e) => setBulkStatus(e.target.value)}
                className="px-2.5 py-1.5 rounded-xl bg-cyber-900 border border-white/20 text-white text-xs focus:outline-none focus:border-cyan-400"
              >
                <option value="OPEN">Mark as OPEN</option>
                <option value="IN_REMEDIATION">Mark as IN REMEDIATION</option>
                <option value="FIXED">Mark as FIXED</option>
                <option value="ACCEPTED_RISK">Mark as ACCEPTED RISK</option>
                <option value="FALSE_POSITIVE">Mark as FALSE POSITIVE</option>
              </select>

              <input
                type="text"
                placeholder="Assignee email..."
                value={bulkAssignee}
                onChange={(e) => setBulkAssignee(e.target.value)}
                className="w-36 px-2.5 py-1.5 rounded-xl bg-cyber-900 border border-white/20 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-400"
              />

              <Button
                variant="primary"
                size="sm"
                onClick={() => handleApplyBulkStatus()}
                loading={bulkProcessing}
              >
                Apply Triage
              </Button>

              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleApplyBulkStatus('FALSE_POSITIVE')}
                disabled={bulkProcessing}
              >
                False Positive
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Forensic Drill-Down Modal */}
      {selectedFinding && (
        <Modal
          isOpen={Boolean(selectedFinding)}
          onClose={() => setSelectedFinding(null)}
          size="full"
          title={
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-cyan-400" />
              <span>{selectedFinding.title}</span>
            </div>
          }
          description={`Forensic analysis, HTTP evidence, reproduction steps, and live verification for ${selectedFinding.scanner_rule_id}`}
        >
          <EvidenceViewer
            finding={selectedFinding}
            onFindingUpdated={(updated) => {
              setSelectedFinding(updated);
              setFindings((prev) =>
                prev.map((f) => (f.id === updated.id ? updated : f))
              );
            }}
            onClose={() => setSelectedFinding(null)}
          />
        </Modal>
      )}
    </div>
  );
}

export default function FindingsPage() {
  return (
    <React.Suspense
      fallback={
        <div className="p-8 text-slate-400 font-mono text-sm animate-pulse">
          Loading NOOSFORGE findings center...
        </div>
      }
    >
      <FindingsContent />
    </React.Suspense>
  );
}
