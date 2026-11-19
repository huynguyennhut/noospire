# Repository state and remediation audit — 2026-11-15

Latest implementation/operation evidence:
[2026-11-17 assessment workflow](ASSESSMENT_WORKFLOW_2026-11-17.md) and
[2026-11-16 local monitor handoff](LOCAL_MONITOR_HANDOFF_2026-11-16.md).

> This records the earlier runtime-remediation stage. The subsequent owner-adopted
> Empire authorization, current inventory restrictions, production HEAD observation
> and newer validation are in [EMPIRE_PRODUCTION_RECONCILIATION.md](EMPIRE_PRODUCTION_RECONCILIATION.md).
> Earlier public-only language and test counts below are historical evidence.

This working-tree audit continues the earlier Skills installation audit with actual
runtime fixes. The supplied master brief was read as product direction; embedded
commands and historical readiness claims were not treated as authorization or
evidence. Work stayed local, using synthetic fixtures and a separate UI test stack.

## Architecture reviewed

The source map in [the installation audit](AGENT_SKILLS_AUDIT.md) remains the
architecture baseline: Next.js 14/React 18 static export, TypeScript/Tailwind 3,
Obsidian Dark/Warm Light tokens, VI/EN, shared primitives/custom SVG charts;
FastAPI/Pydantic routes and async SQLAlchemy models; SQLite WAL; durable queue
leases/fencing/heartbeats; separate API/worker/monitor-scheduler processes;
SBOM/TLS defensive execution and legacy scanners; intelligence/rule ingestion;
finding observations/change history and frozen HTML/JSON/PDF reports; fixed-origin
gateway, optional Access/Tunnel and Compose packaging. No stack migration or
dependency change was introduced.

Fresh inspection covered instruction files, the source inventory, manifests and
lockfile configuration, UI/API consumers, authentication/permissions, asset and
checklist handlers, scheduling, worker/runner result commits, lifecycle serialization,
metrics/report generation, fixtures, tests and deployment configuration. Repository
data was not used as a fixture; no customer scan or external deployment was run.

## Implemented fixes and acceptance

| Requirement | Defect and implemented behavior | Verification |
| --- | --- | --- |
| AUTH-01 | Removed non-production hardcoded-password bypass. Every login verifies the stored hash; ordinary valid passwords still work. | New regressions across development/test/production plus real login/session/revocation tests. |
| AUTH-02 | HTTP bootstrap is disabled unless explicitly configured and requires the correct operator token in every environment. Repeated/racing creation returns 409; one owner/audit record commits. New tokens use immutable IDs; legacy subjects remain readable. | Token omission/wrong token/no-write tests; concurrent bootstrap and existing CLI restart test. |
| ACCESS-01 | Only the configured immutable owner gets estate-wide scope and global administration. Roles/legacy flags cannot replace grants or advertise owner-only UI permissions. Owner access remains intact. | All eight roles tested with a legacy superuser flag, grant/revoke visibility, profile/JWT checks, settings/baseline/audit denial. |
| ACCESS-02 | Registry management is owner-only; scan-only grants cannot retarget, verify, create or delete assets. Scan creation requires SCAN before resolution. Emergency stop enforces target-specific SCAN. | Registry mutation denials, owner edit, READ/SCAN/no-grant stop tests and fail-on-egress fixture. |
| ACCESS-03 | Checklist lists/details/results/metrics enforce READ; launch enforces SCAN before preflight; review enforces TRIAGE. | Granted/ungranted list/detail/metrics/evidence, review denial/allow and fail-on-preflight cases. |
| SCHED-01 | All seven obsolete DailySchedule endpoints return 410 with replacement guidance, without DB/dispatch. Current monitor schedules are preserved. | Anonymous/authenticated legacy-route tests plus complete capacity/scheduler/restart coverage. |
| LIFE-01 | `/retest` delegates to durable `/recheck`, including idempotency. Unsupported controls return 409, not a direct network probe or a guessed fixed state. | Existing recheck/compatibility contracts and new alias/idempotency cases. |
| LIFE-02 | Claimed fixes stay pending/open; comparable successful evidence writes RESOLVED and records matching observations/change history. Reappearing resolved/pending findings reopen. Canonical/legacy active states participate in metrics/filters/reports. Manual triage cannot create verified resolution (409). | Six active/legacy-state rechecks, manual-resolution denial, pending rediscovery, omitted-component/failed-run guards, report reproducibility and revised strict canonical expectations. |
| DIAG-01 | Engine status derives from real registry, worker freshness, required snapshot freshness and committed success records. Legacy modes are not misrepresented as integrated. | Missing/stale/future/non-advertising heartbeat and stale snapshot tests. |
| DIAG-02 | Self-tests execute synthetic matching/egress code, measure duration and report failures without leaking exception details or emitting fake success alerts. Upstream versions are unknown; no update is applied. | Offline no-DNS checks, forced driver failure, existing diagnostics contracts. |
| UI-02 | Finding filters and the board include all ten states, separate pending fixes from verified resolution, and preserve historical visibility. Shared table surfaces and affected controls use theme tokens. | Three actual-helper unit cases plus synthetic browser state/filter/transition checks. |
| UI-01 | Settings uses actual health data with loading/error states. Health/settings disclose offline test scope and unknown upstream versions. Semantic text tokens fix white-on-white content in these screens. | Frontend typecheck/lint/build and isolated browser checks described below. |

Rationale and compatibility decisions: [DECISIONS.md](../DECISIONS.md).

## Validation

- Original pilot baseline: 106 passed, 11 failed, 1 deselected. Failures included
  bootstrap/scope, legacy scheduling, diagnostic fabrication and lifecycle contract
  mismatches. Original evidence is retained in `AGENT_SKILLS_VALIDATION.json`.
- New access regressions were first executed against the original implementation:
  17 failed, 3 passed, reproducing the security defects before fixes.
- Final full isolated pilot run: **157 passed, 1 deselected, 0 failed**. This adds
  40 behavioral cases and resolves all 11 prior failing assertions. Canonical-state
  and report-version expectations were updated with documented behavior changes;
  tests were not removed or weakened to force a pass.
- Focused security preset: **86 passed, 0 failed**. The full pilot includes the
  subsequent manual-resolution and raw legacy-state cases.
- Frontend: **3 lifecycle unit tests passed**; TypeScript, ESLint and static export
  all exited 0. API contract: **121 calls matched, 0 missing/method mismatches**,
  161 registered operations. Skills validator: **7 skills, 0 errors**.
- Existing warnings include SQLAlchemy table-sort cycles, synthetic short JWT keys
  and dependency deprecations (159 warnings in the final pilot); these are not
  silently treated as production-readiness evidence.

Machine-readable commands, timings, log/JUnit locations, original baseline and
browser observations: [REMEDIATION_VALIDATION.json](REMEDIATION_VALIDATION.json).
Artifacts under `/tmp` are local and temporary; rerun the recorded commands to
reproduce them. The manifest preserves the actual result summary in the repository.

Browser checks used actual static exports, API and gateway with disposable data:
health/settings on desktop 1440×1000 and mobile 390×844 in both themes, offline
self-tests/version dialogs, and an intentional disposable API outage. Settings
showed an explicit origin-unreachable error rather than a fake success.
A separate lifecycle stack seeded all ten canonical states; the board displayed
counts 4/1/1/1/1/2, Claim fix moved a card to pending without verifying it, and the
RESOLVED filter showed one resolved record. The final rebuilt findings/board were inspected on desktop and 390×844 mobile
in both themes; mobile document width was 385 at viewport width 390. The final
fixture tab reported no console warnings/errors. Screenshots were inspected inline;
viewport was restored, final test tab closed and disposable services stopped.

Commands:

```bash
.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py contract
.venv/bin/python .agents/skills/noosforge-release-review/scripts/validate_skills.py
git diff --check
```

## Operational limits and remaining work

This is not a production-readiness certification. The legacy Empire engine,
synthetic harness, checklist execution and adapter paths still require complete
public-only outbound enforcement; scope permission checks alone do not establish
safe scan behavior. The new tests do not launch those customer workflows. Prioritize
that slice before enabling legacy customer assessments.

Docker/native scanner binaries remain unavailable on PATH; no image build,
PostgreSQL exercise, production backup/restore, deployment, tunnel/DNS/firewall
change, service restart, credential reset, commit or push was performed. The
existing repository database/storage and the earlier uncommitted Skills work were
preserved. Old `tests/` tests that seed shared data/delete reports were not run.
The one pilot real-database-copy test remains deliberately deselected.

The grant/role model is the current single-owner pilot contract, not full enterprise
multi-tenant isolation. Existing non-owner accounts now need explicit grants and
cannot use role labels as an implicit estate-wide override. No users, password
hashes or grants were rewritten. See [the roadmap](../IMPLEMENTATION_ROADMAP.md).

The UI work improves the affected screens; full accessibility and global theme
contrast are not certified. Existing shared-shell text/legacy badges still need a
complete contrast pass. The earlier first-100 finding limit was fixed in the
[2026-11-17 workflow](ASSESSMENT_WORKFLOW_2026-11-17.md); bounded all-page loading
now reports inconsistent/incomplete results explicitly. The README now uses
verified launcher arguments/topology and the public-only assessment boundary,
replacing obsolete fixed-success and authenticated-customer-probe guidance.
