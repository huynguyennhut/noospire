# Assessment workflow audit and implementation — 2026-11-17

This continues the supplied software-engineering request. The initial audit was
followed by implementation and browser acceptance on an isolated local stack.
No new Empire/customer probe, production deployment or destructive data operation
was performed. Earlier audit claims and the manual student browser session were
not treated as current automated coverage.

## Initial state and architecture evidence

The repository already had substantial working infrastructure: Next.js 14 static
export, React 18/TypeScript/Tailwind 3, shared Liquid Glass tokens and VI/EN;
FastAPI/Pydantic with cookie/CSRF authentication and per-asset grants; async
SQLAlchemy/SQLite WAL; durable execution records/attempts, leases/fencing and
worker heartbeats; monitor scheduling; SBOM/public-web/TLS controls; finding
observations/change history and frozen report snapshots.

Inspection followed `frontend/src/app`, the layout/theme/i18n providers,
`frontend/src/lib/api.ts`, `backend/app/api`, `backend/app/models`,
`backend/app/engines`, `backend/app/reporting`, scheduler/worker entrypoints,
configuration, `scripts/local_stack.py`, `tests_pilot`, the unsafe legacy test
setup, dependency manifests, Dockerfiles and `deploy/compose` packaging. The
[Skills architecture map](AGENT_SKILLS_AUDIT.md) and
[earlier current-state report](PROJECT_CURRENT_STATE.md) provide the source map.
No stack/dependency/lockfile replacement was needed.

The main defects in this vertical flow were integration and truthfulness:
pending targets could not use offline SBOM through UI despite backend support;
historical run findings disappeared after dedup; defensive logs were read from a
legacy table; run reports could include unrelated asset findings; triage UI
offered misleading verified-fixed language; missing evidence synthesized HTTP,
headers/cURL and severity-derived CVSS; lists stopped at the first 100 findings;
bulk failures were silent; advisory activation had no staged review/disable UI;
daily scheduling was not a usable default. PDF review then reproduced clipped
long titles, reasons, remediation and snapshot hashes.

`nuclei`, `zap.sh`, `trivy` and `docker` were unavailable on PATH. Their legacy
source adapters are not registered in the fenced defensive execution flow.
Health/Integrations correctly expose that limit. Existing checklist names and
report labels do not establish engine or customer coverage.

## Requirements, decisions and acceptance

| Yêu cầu | Bằng chứng hiện trạng | Phần còn thiếu/lỗi | Hướng triển khai / kết quả | Ưu tiên | Cách nghiệm thu / trạng thái |
| --- | --- | --- | --- | --- | --- |
| Target and exact scope | Inventory reconciliation, admission, SSRF/egress and asset grants already exist | Full Empire inventory and approved identities/objects absent | Preserve all network guards; derive separate offline-file eligibility, still deny known fixture/seed provenance | P0 | UI-created pending lab asset analyzed supplied file without network admission; API denial regressions. **Hoàn thành một phần** for product estate |
| Config and real execution | DB queue, attempts, worker and native SBOM/TLS/public-web controls | Proposed native adapters not safely integrated | Use actual registered driver/input, show versions/hashes/unavailable; add persisted execution-log endpoint and UI pagination | P0 | UI upload → queued → actual worker → terminal result/logs/output. **Đã hoàn thành** for native SBOM slice |
| Findings/evidence | Durable normalized finding/observations already exist | UI invented absent HTTP/CVSS; old execution association mutable | Stored-only evidence/redaction, unrated score, immutable observation joins, full paginated loading with consistency errors | P0 | 4 real synthetic findings; missing response explicitly absent; stable IDs across runs; unit/API/browser checks. **Đã hoàn thành** for changed flow |
| Triage and false positives | API forbids manual verified resolution | UI legacy FIXED label, generic dismissal reasons and silent partial bulk errors | Canonical pending state, required reason in API/UI, preserve failed selections and expose failures | P0 | UI reasonless FP save disabled; pending claim and engine resolution accepted; API permission/reason regressions. Bulk partial failure is API/client logic coverage, not a multi-user UI certification. **Hoàn thành một phần** |
| Retest without false resolution | Lifecycle engine had comparable-evidence guard | public_web recheck excluded; historical links lost | Queue public_web via existing safe planner, preserve historical observations/scan links | P0 | UI patched run and Recheck; 3 resolved, omitted delta stays NEW/changed_scope; rules failure preserves state. **Đã hoàn thành** for registered controls |
| Frozen report with exact scope | HTML/JSON/PDF snapshots and hashes exist | Batch could include unrelated findings; legacy scope filters broadened; PDF clipped | Observation-scoped run report, scan/batch/asset grant validation; version 1.2 PDF wraps complete text and includes scope/coverage/evidence refs | P0 | UI creates/previews/downloads report; original JSON byte-identical after retest; scoped report tests; actual PDF layout acceptance. **Đã hoàn thành** for internal template; Empire-approved template still absent |
| Daily scheduling/timezone | Durable monitor schedules with slot coalescing already exist | UI default 120 and no new-schedule engine choice | Daily1440 default for new schedules, explicit 07:00 ICT/00:00 UTC; keep saved intervals/fixed asset selection | P1 | UI create and next-run shown; pause persists after reload; scheduler/process tests. **Đã hoàn thành** for fixed UTC-aligned interval; arbitrary cron/timezone editing not implemented |
| Controlled rule updates | Immutable OSV snapshot imports already exist | No review/disable/rollback UX; no activation integrity recheck | Stage UI imports; owner-only reasoned activation/disable, compatible index/digest validation, one atomic active-version update | P1 | UI import/activate/disable/reactivate; tampered snapshot/rollback/owner/CSRF API tests. **Hoàn thành một phần**: no curated native-template/feed updater |
| Public and authenticated web/API | Exact root-only unauthenticated public_web observation | Full route contracts, automated identity profiles, multiple roles and safe objects absent | Keep named gaps; do not forward platform credentials or invent auth findings | P1 | Legacy native adapters remain NOT_INTEGRATED; no new customer execution. **Bị chặn / chưa triển khai** for comprehensive authenticated coverage |
| App/server/container scope | Some legacy adapters/source categories exist | No approved app/image/repo/server artifacts, suitable registered controls or host binaries | Do not treat Trivy as a URL scanner; keep explicit capability limits | P2 | Source/health review only. **Chưa triển khai** in accepted execution slice |
| Data protection and retention | Scoped permissions, redacted logs/reports and managed hashed artifacts | Full retention/deletion policy and all legacy paths not accepted | Preserve data, require owner/grants, redact stored-display evidence; no destructive cleanup | P1 | Scoped/CSRF/redaction tests pass. **Hoàn thành một phần**; retention/tenant certification remains work |
| UI and deployment | 17 navigation screens, shared responsive shell, loopback gateway and Compose files | Every role/action, WCAG, Docker/PostgreSQL/recovery not fully accepted | Real isolated app lab, 17-route smoke, main flow/actions, themes and mobile checks | P1 | Browser evidence plus build/type/lint/contract; loopback lab stays available. **Hoàn thành một phần**, not release certification |

## Implemented code boundaries

- `backend/app/api/{assets,executions,findings,reports,console}.py` owns derived
  eligibility, staged/atomic advisory activation, scoped persisted logs, historical
  observations, report permissions and recheck admission.
- `backend/app/reporting/{pilot_report,generator}.py` binds run data to observations
  and keeps frozen files unchanged. New internal PDF template 1.2 wraps text by
  page width, includes full hashes, scope/coverage/limits and page numbers.
- Engine Runs, Findings, Remediation, Reports and Schedules share the actual API
  behavior. `frontend/src/lib/finding-evidence.ts` formats only recorded fields;
  `listAllFindings` reads up to 20,000 with explicit consistency/limit failures.
  This bounded client loading is not an unlimited large-estate server UI design.
- `scripts/assessment_lab.py` reuses the existing supervisor with private generated
  lab identity/config, separate database/storage and no seeded targets/findings.
  No schema migration is required: the added asset capability is derived output.

## Verification and browser acceptance

The complete command results, timings and artifact hashes are in
[ASSESSMENT_WORKFLOW_VALIDATION.json](ASSESSMENT_WORKFLOW_VALIDATION.json).
Final backend pilot: **256 passed, 1 deliberately deselected, 0 failed**;
258 existing warnings. Focused post-PDF backend: **114 passed**. Frontend:
**12 unit cases**, TypeScript, ESLint and static export; final API contract:
**124 matched, 0 missing/mismatched**. Skills structure: **7 skills, 0 errors**.
Tests use disposable databases/storage; the legacy shared-data test setup was not
run. One real-database-copy pilot case stays deliberately deselected. Existing
SQLAlchemy table-cycle/deprecation warnings are recorded, not hidden.

The initial unchanged baseline passed 242 tests. An intermediate full run had two
failures: a subprocess API read timeout during competing frontend builds and a
contract scan while source changed. A stable rerun passed all 255 then-present
cases. PDF overflow discovered by later visual acceptance received a further fix
and regression; final post-fix counts are recorded in the manifest.

The actual downloaded template 1.2 PDF was rendered with Poppler and both A4 pages
were visually inspected: complete hashes and wrapped text, no clipping. The
regression also extracts long tail markers and asserts every word's horizontal
page bounds. The old frozen PDF remained byte-identical after renderer upgrade.

The real lab UI flow created one DEV pending target, imported/staged/activated
the synthetic advisory fixture, ran the vulnerable SBOM (4 findings), inspected
worker logs/versions/hashes/evidence, claimed gamma pending retest, created and
downloaded report snapshots, ran the patched SBOM (0 current matches), and used
the Finding Recheck action. There are still exactly 4 finding records: alpha,
beta and gamma RESOLVED; omitted delta NEW with changed_scope observations.
Disabling rules yielded RULES_UNAVAILABLE with no false resolution. The reviewed
snapshot was reactivated. The daily SBOM schedule was created, showed next slot
07:00 ICT, and was paused and reloaded successfully.

The original report JSON was downloaded again after retest and was byte-identical.
Before/after reports and screenshots are synthetic NOOSFORGE validation evidence,
not Empire vulnerability findings. Missing HTTP response is explicit; delta has
no invented CVSS; reasonless false-positive save is disabled. Keyboard Escape
closes the dialog. HIGH filter produces the actual empty state and reset restores
four records. Dark/Warm mobile views at 390×844 have no document overflow
(385/385 for findings, 390/390 for the modal); dense tables scroll internally.
Viewport override was reset. Browser warning/error capture was empty at review.
Warm desktop review also reproduced invisible white shell labels. Brand/context,
origin/role and language text now use theme tokens; API status colors have darker
Warm variants. This targeted fix does not certify all legacy badge contrast.

Selected inspectable synthetic artifacts are retained under
[`evidence/assessment-workflow-2026-11-17/`](evidence/assessment-workflow-2026-11-17/),
including the report JSON/PDF and theme/mobile screenshots. Runtime logs, all
intermediate screenshots and detailed screen text stay in the ignored local lab.

All 17 sidebar destinations rendered with no nonempty alert during navigation
smoke. This is not evidence for every mutation or multi-role interaction on those
screens. Detailed acceptance covers the workflow above; browser grant/invite,
feed synchronization, legacy checklist execution and destructive retention actions
remain unverified. No browser network sandbox or load test is claimed.

## Handover and remaining inputs

Run and reproduce with [ASSESSMENT_LAB.md](../ASSESSMENT_LAB.md). Keep the private
lab configuration out of Git. The lab console is <http://127.0.0.1:8082/>; API,
worker, scheduler and gateway run separately. The lab schedule is paused.

Before broader Empire assessment, supply an authoritative exact asset/route
manifest, approved automated target identity references and role matrix, safe
test records, approved health endpoints/ownership, and relevant API/app/image/repo
artifacts. A student session manually opened in a browser is not an automated
secret-store profile or permission to modify arbitrary learner records. Approved
public `/media` stays PUBLIC_BY_DESIGN. Native adapter containment/reviewed rule
packs and production observability/recovery need implementation and acceptance.
External deployment and destructive changes remain separate approval decisions.
