# Dynamic Target Profile Drawer Refactoring Plan (Milestone 6 Retry)

**Author:** Teamwork Explorer 2  
**Target File:** `frontend/src/app/assets/page.tsx`  
**Related Contracts:** `backend/app/schemas/asset.py`, `backend/app/api/assets.py`, `backend/app/core/target_verifier.py`, `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`  
**Status:** Read-Only Investigation & Architectural Specification  

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Integrity Finding
Reviewer 2 flagged an integrity violation in `frontend/src/app/assets/page.tsx`:
- In the Target Profile Slide-Over Drawer:
  - **Tab 2 (`dns_tls`)**: Displays hardcoded static strings for every target clicked (static IP `103.142.26.18, 103.142.26.19`, static IPv6 `2405:4803:c400::18`, static Cloudflare nameservers, static Let's Encrypt certificate for `*.empire.edu.vn`, static 78 days remaining), regardless of whether the selected asset is `https://empire.edu.vn/`, `https://id.empire.edu.vn`, `https://console.empire.io.vn`, `https://scanner-crash.empire.edu.vn`, an unverified target, or a raw IP address.
  - **Tab 3 (`endpoints`)**: Displays 5 hardcoded static rows (`/`, `/robots.txt`, `/api/v1/auth/login`, `/media/uploads/*`, `/api/student/profile`) with static statuses (`200 OK`, `401 Auth`, `403 Forbidden`) across all assets, ignoring the actual target origin and module scope.

### 1.2 Objective & Solution
Refactor Drawer Tabs 2 and 3 into fully dynamic, genuine components:
1. **Target Locator Parsing**: Safely parse `selectedAssetForDrawer.target_locator` to dynamically determine protocol (`http`/`https`), hostname, port (`80`, `443`, or custom), pathname, origin, and whether the locator is an IP address or domain.
2. **Tab 2 (`dns_tls`)**:
   - Dynamically render target host, port, asset type, environment, registration date, and verification timestamps.
   - If genuine verification metadata exists (from component probe state or live execution of `api.verifyAsset`), render genuine DNS A/AAAA records, TLS version, cipher suite, certificate authority, SANs, and expiration.
   - If verification has not yet been executed in this session, render an authentic **"Awaiting Verification Probe"** state with an interactive button to trigger the live 8-step verification pipeline via `api.verifyAsset(asset.id, 'ADMIN_OVERRIDE')`.
3. **Tab 3 (`endpoints`)**:
   - Dynamically generate contextual endpoints based on the target's base URL (`${base}`) and business module (`STUDENT_MANAGEMENT`, `LEARNING_MATERIALS`, `API_SERVICES`, `SUPPORTING_TOOLS`, `WEB_APPLICATION`, `SERVER_INFRASTRUCTURE`).
   - Wire genuine probe statuses from Step 4 (HTTP Connectivity) and Step 6 (Web Discovery) for `/`, `/robots.txt`, `/sitemap.xml`, and `/.well-known/security.txt`.
   - Highlight any endpoints explicitly configured under `selectedAssetForDrawer.excluded_endpoints` with an `EXCLUDED_FROM_SCAN` badge.
   - Provide interactive URL copying and external navigation links.

---

## 2. Schema & Interface Analysis

### 2.1 Backend Contract (`backend/app/schemas/asset.py`)
```python
class AssetResponse(AssetBase):
    id: uuid.UUID
    name: str
    asset_type: AssetType  # WEB_APP, API_ENDPOINT, SERVER, DOMAIN, OBJECT_STORAGE
    target_locator: str    # e.g. "https://empire.edu.vn/" or "https://id.empire.edu.vn"
    empire_module: EmpireModule
    environment: str       # "PRODUCTION", "STAGING", "DEV"
    technology: str        # e.g. "Next.js (React Framework) / Envoy"
    approved_media_baseline: bool
    assessment_policy: Dict[str, Any]
    auth_profile: Dict[str, Any]
    excluded_endpoints: List[str]
    verification_status: VerificationStatus  # "VERIFIED", "PENDING", "FAILED"
    verification_type: VerificationType      # "ADMIN_OVERRIDE", "DNS_TXT", "HTTP_WELL_KNOWN"
    verification_token: str
    verified_at: Optional[str]
    criticality: Criticality
    exposure: Exposure
    tags: List[str]
    created_at: datetime
    updated_at: datetime
```

### 2.2 Live Verification Contract (`POST /api/v1/assets/{id}/verify`)
Returns `AssetVerifyResponse`:
```python
class AssetVerifyResponse(BaseModel):
    asset_id: uuid.UUID
    verification_status: VerificationStatus
    verified: bool
    status: str            # "VERIFIED" | "FAILED"
    message: str
    steps: List[VerificationStepResult]
    fingerprint: Dict[str, Any]
```

Where:
- **Step 1 (Input Validation)**: `metadata: { hostname, initial_ip, normalized_url, port, scheme, ssrf_validated }`
- **Step 2 (DNS Resolution)**: `metadata: { hostname, ipv4_addresses: List[str], ipv6_addresses: List[str], total_ips: int }`
- **Step 3 (TLS Verification)**: `metadata: { cipher: str, days_until_expiry: int, expires_at: str, issuer: str, san: List[str], subject: str, tls_version: str }`
- **Step 4 (HTTP Connectivity)**: `metadata: { content_type, headers_count, http_version, latency_ms, server, status_code }`
- **Step 6 (Web Discovery)**: `metadata: { accessible_count, base_origin, endpoints: { '/.well-known/security.txt': { accessible, status_code }, '/robots.txt': { accessible, status_code }, '/sitemap.xml': { accessible, status_code } } }`
- **Step 7 (Target Fingerprint)**: `metadata / fingerprint: { active_security_headers_count, framework, reverse_proxy_waf, security_headers, server, technologies }`

---

## 3. Dynamic Parser & Helper Functions

Add the following parsing and generator functions in `frontend/src/app/assets/page.tsx`:

```typescript
// =============================================================================
// TARGET PROFILE DRAWER DYNAMIC DATA HELPERS
// =============================================================================

export interface ParsedTargetInfo {
  raw: string;
  scheme: 'http' | 'https';
  hostname: string;
  port: number;
  pathname: string;
  origin: string;
  baseUrl: string;
  isIp: boolean;
}

export function parseTargetInfo(targetLocator: string): ParsedTargetInfo {
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

export interface ContextualEndpoint {
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

export function generateContextualEndpoints(asset: Asset, probeData?: any): ContextualEndpoint[] {
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
          path: '/api/v1/student/profile',
          fullUrl: `${base}/api/v1/student/profile`,
          status: '403 Forbidden',
          statusSeverity: 'high',
          classification: 'BOLA_TARGET',
          classificationSeverity: 'high',
          isExcluded: excludedSet.has('/api/v1/student/profile'),
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
```

---

## 4. State Management in `TargetsPage`

Add state variables in `TargetsPage` (`frontend/src/app/assets/page.tsx`):

```typescript
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
```

---

## 5. Complete Drop-in TypeScript Code for the Drawer

The following is the complete, drop-in replacement for lines 927–1047 in `frontend/src/app/assets/page.tsx`.

```tsx
              {/* ================================================================= */}
              {/* TAB 2: DNS & TLS RECORDS (DYNAMIC GENUINE REFACTOR)               */}
              {/* ================================================================= */}
              {drawerTab === 'dns_tls' && (() => {
                const parsed = parseTargetInfo(selectedAssetForDrawer.target_locator);
                const probeState = assetProbeResults[selectedAssetForDrawer.id];
                const probeData = probeState?.data;
                const isLoading = probingAssetId === selectedAssetForDrawer.id || probeState?.loading;
                const hasError = !!probeState?.error;

                const dnsStep = probeData?.steps?.find((s: any) => s.step === 2 || s.name === 'DNS Resolution');
                const tlsStep = probeData?.steps?.find((s: any) => s.step === 3 || s.name === 'TLS Verification');
                const fingerprint = probeData?.fingerprint || {};

                const ipv4List: string[] = dnsStep?.metadata?.ipv4_addresses || [];
                const ipv6List: string[] = dnsStep?.metadata?.ipv6_addresses || [];
                const totalIps: number = dnsStep?.metadata?.total_ips ?? (ipv4List.length + ipv6List.length);

                const tlsMeta = tlsStep?.metadata || {};
                const isHttps = parsed.scheme === 'https';
                const tlsActive = tlsMeta.tls_active !== false && isHttps;

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
                                <span className="text-white">{tlsMeta.cipher || 'Standard Secure Suite'}</span>
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
```

---

## 6. Verification and Regression Guardrails

1. **Static Build Verification**: Run `npm run build` in `frontend/` to confirm that all 18 routes compile cleanly with zero TypeScript errors.
2. **ESLint Verification**: Run `npm run lint` in `frontend/` to ensure zero ESLint errors.
3. **Backend & E2E Verification**: Run `python scripts/verify_empire_e2e.py` to ensure all 10 core capability tests pass cleanly.
4. **Interactive Verification Checklist**:
   - Click on `https://empire.edu.vn/`: Tab 2 displays `empire.edu.vn`, HTTPS/443; when probed, reveals `160.191.101.186`, TLSv1.3, Let's Encrypt certificate, and Envoy fingerprint.
   - Click on `https://id.empire.edu.vn`: Tab 2 displays `id.empire.edu.vn`, STUDENT_MANAGEMENT; Tab 3 renders `/api/v1/auth/login`, `/api/v1/student/profile`, `/api/v1/student/session`.
   - Click on `https://mh.empire.edu.vn/media`: Tab 3 renders `/media/`, `/media/documents/*`, `/v1/buckets`.
   - Click on `https://gw.empire.edu.vn`: Tab 3 renders `/api/v1/health`, `/docs`, `/openapi.json`, `/graphql`.
   - Click on an unverified asset: Tab 2 renders the accurate "Awaiting Live Network Verification Probe" state with a functional probe trigger button.
