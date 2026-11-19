> Current scope update (2026-11-17): the owner authorizes all Empire-owned infrastructure. Root-only wording below records the earlier configured inventory and execution, not the current authorization boundary. See [current inventory guidance](../EMPIRE_INVENTORY_GUIDANCE.md).

# Empire production inventory and execution reconciliation

Recorded 2026-11-15. This continues the [repository audit](PROJECT_CURRENT_STATE.md)
using the owner-adopted [operations brief](../EMPIRE_PRODUCTION_AUTHORIZED_OPERATIONS.md)
and subsequent [inventory guidance](../EMPIRE_INVENTORY_GUIDANCE.md). Standing
assessment authorization is retained. Missing inventory, credentials and telemetry
are technical configuration gaps, not requests to reconfirm that authorization.

## Inventory result

The existing SQLite database was opened read-only, without importing application
startup, seeding records, changing stored flags or resolving target hosts.
[The complete sanitized row-level JSON](EMPIRE_INVENTORY_RECONCILIATION.json)
records classifications, provenance, stored flags and limitations.

| Classification | Rows | Decision |
| --- | ---: | --- |
| Owner-designated primary production target | 1 | `https://empire.edu.vn/` only; designation does not establish readiness for every scanner/check. |
| Seeded or test assets | 398 | Preserve history; exclude from production execution. Six historical seed candidates can be reconciled if independent ownership/scope evidence is supplied. |
| Unknown or unverified provenance | 0 | All existing rows matched a source. This does not establish a complete production estate. |
| Total | 399 | No rows promoted, deleted or retargeted. |

The database stores 395 VERIFIED and four PENDING flags, 11 ownership-proof rows
and 19 assessment-scope rows. Flags alone are not ownership evidence. Seven proofs
contain `initial_seed: true`; the root also has a later owner-attestation record.
The report distinguishes a non-seed unexpired proof record from actual assessment
coverage. Four emergency-stop scope rows exist; no stop was cleared.

Provenance accounts for all 399 rows:

| Source | Rows | Evidence |
| --- | ---: | --- |
| Initial Empire seed | 7 | `backend/app/core/empire_seeder.py`, `initial_seed` proof data; includes the separately owner-designated root. |
| Persisted execution targets from the 379-row acceptance fixture | 368 | Exact deterministic IDs and locators from `core/ultra_planner.py::generate_acceptance_fixture_379`; 350 web, ten API and eight image targets. Six alias and five excluded fixture rows are not independent persisted execution targets. |
| Legacy test locators | 24 | Twelve from `tests/test_scope_gate.py`, `test_scan_intelligence_m2.py` and the constrained UUID-suffix pattern in `test_tier3_cross_feature.py`; twelve reserved/local hosts corroborated in `test_milestone_a_control_plane.py` and `test_milestone_b_queue_and_scheduler.py`. Includes metadata/private-address test cases; none were probed. |

The seven historical scope candidates are listed below to make the distinction
reviewable. Their technology descriptions in old documents were not independently
verified against production.

| Historical locator | Current decision |
| --- | --- |
| `https://empire.edu.vn/` | Owner-designated root; one bounded HEAD observation recorded below. |
| `https://id.empire.edu.vn` | Initial seed; no independent current inventory corroboration. |
| `https://gw.empire.edu.vn` | Initial seed; no approved API-route manifest supplied. |
| `https://mh.empire.edu.vn/media` | Initial seed; preserve PUBLIC_BY_DESIGN policy, no media request performed. |
| `https://voh.empire.edu.vn` | Initial seed; storage ownership/access configuration not supplied. |
| `https://console.empire.io.vn` | Initial seed; no approved administrator test identity supplied. |
| `https://gw.empire.edu.vn/news` | Initial seed; path is not expanded to the gateway root or third-party feeds. |

No independent authoritative CSV, JSON or OpenAPI production inventory was found.
`backend/app/api/assets.py` supports ingestion, but capability is not a designated
source. `EMPIRE_PENTEST_SCOPE.md` is historical context; its wildcard and readiness
claims do not promote generated targets. No duplicate normalized locators were
found among these 399 rows. IPs, DNS suffixes, certificate SANs, aliases and links
were not used to expand scope.

## Health, authentication and missing configuration

| Item | Actual discovery |
| --- | --- |
| Configured customer health endpoints | **0** in asset assessment policies. No `/health` or `/healthz` request sent. |
| Existing platform health endpoints | NOOSFORGE `/healthz/live` and `/healthz/ready`, documented in `deploy/README_DEPLOY.md`; these are not Empire application-health approvals. |
| Target-auth profile content | **0** configured profiles in the 399 assets. |
| Non-secret target credential references | **0** designated references found. No secret-store path was invented. |
| Platform configuration | `deploy/.env.example` describes NOOSFORGE settings; it does not supply an approved customer secret store or customer identity. |

Configuration needed to extend coverage:

1. An authoritative asset manifest with exact domains, paths, ports/ranges,
   environment, ownership source and inclusion/exclusion decisions. Include provided
   OpenAPI/GraphQL documents and any approved infrastructure vantage points.
2. Approved customer health endpoints with purpose, ownership, expected response,
   baseline, thresholds and incident-stop integration. Target CPU/memory/queue
   telemetry and low-traffic windows are currently unavailable.
3. For authenticated coverage, designated non-secret secret-store references,
   dedicated role/tenant test identities, login mechanisms and harmless test-object
   records. Do not put secret values in this report or prompts.
4. Approved source/dependency/SBOM/container/cloud/mobile artifacts or read-only
   access where those categories are in scope.

Until provided, BOLA/IDOR, BFLA, RBAC, tenant isolation, authenticated sessions and
account-security checks are `AUTHENTICATED_COVERAGE_NOT_CONFIGURED`. They are
excluded checks, not vulnerabilities or passes. The current automation sends no
target credentials. A root response is not proof of any of these controls.

## Implemented behavior

- Added `core/inventory_reconciliation.py`, a source-backed classifier and dispatch
  guard, plus `scripts/reconcile_production_inventory.py`. The CLI uses SQLite
  `mode=ro`/`query_only`, selected columns and no application startup. Its connection
  recorded zero changes and zero network requests. Synthetic tests verify DB bytes
  remain unchanged and output cannot replace the DB.
- Added owner-only `GET /api/v1/assets/reconciliation`. Responses omit credential
  values and URL userinfo/query strings. Stored verification flags remain intact;
  seed-only/expired proof does not become derived VERIFIED ownership in asset views.
- Known acceptance fixtures and unproven seeded ownership are rejected at scan,
  defensive execution, planner, scope and worker boundaries before target egress.
  The planner explains skips; stale queued TLS and legacy jobs recheck provenance.
  This is a concrete provenance guard, not a complete security policy for every
  possible unrecognized asset.
  The twelve reserved/local records were additionally matched to their exact
  legacy test sources, so the execution guard covers all 398 seeded/test records
  found in this database without treating every `.local` or `.invalid` name as a
  known fixture solely by its suffix.
- Closed Ultra Scan's fixture promotion path. `FIXTURE_379`/`EMPIRE_ESTATE_379`
  launch requests return 409. Empty ALL requests do not generate an inventory.
  Missing IDs are not provisioned. Explicit lists and recovered batches require
  current SCAN grants. Known fixtures in ALL reject the batch before writes.
  Read-only 379-row previews remain available and are labelled SYNTHETIC.
- Added explicit HEAD support to native TLS driver 1.1.0, retaining existing GET
  behavior. The root-only operator script previews by default; execution requires
  `--execute`, an existing root record and an unexpired exact HTTPS/443 root scope.
  It honors recorded target stops and a local global stop file, uses vetted public
  IPs, one HTTP request, concurrency one, five-second I/O timeouts and a 12-second
  total deadline. No redirects, retries, response body retention or credentials.
  Cancellation awaits cleanup. Its local process lock is not a distributed lock
  or a full platform emergency-stop implementation.
- Updated AGENTS and specialized skills to reflect adopted authorization while
  retaining secret, ownership, SSRF, redaction and destructive-change boundaries.
  Current root-only unauthenticated guidance is linked explicitly.

No schema, production application, DNS, firewall, tunnel or deployment mutation was
performed. Existing DB/storage, prior working-tree changes and historical evidence
were preserved. No commit or push was made.

## Real production observation

[Recorded evidence](EMPIRE_ROOT_OBSERVATION.json), observed at
**2026-11-15 13:05:29 UTC**, contains one `HEAD https://empire.edu.vn/`:

| Check | Recorded outcome | Limit |
| --- | --- | --- |
| Root reachability | HTTP **200**, 454 ms measured response latency | One sample, not an availability baseline or application health check. |
| TLS verification | Certificate chain/hostname verified, **TLSv1.3** negotiated | No protocol/cipher enumeration or weak-version assessment. |
| Certificate expiry | **2027-01-25 21:47:54 UTC**, 71.36 days remaining at observation | Point-in-time certificate observation only. |

The evidence identifies the native driver/version, exact scope, request limits,
measurement and observation SHA-256. No external scanner ran, no bodies were
retained, no findings were fabricated and no other route/host was tested. The
response establishes neither full application assessment nor authenticated coverage.
The live request was not repeated to validate subsequent software edits.

Reproducible local commands (the second command only previews):

```bash
.venv/bin/python scripts/reconcile_production_inventory.py --database noospire.db --output docs/audit/EMPIRE_INVENTORY_RECONCILIATION.json
.venv/bin/python scripts/observe_empire_root.py --database noospire.db --output /tmp/empire-root-observation.json
```

The production evidence was obtained by the second command with `--execute` and
the repository evidence output path. This command is an operator observation, not
an automatically enabled schedule or a replacement for the durable assessment UI.

## Requirements and capability gaps

The table maps every numbered section of the adopted brief. “Partial” means
existing code or bounded evidence is present; it does not mean product acceptance.

| Brief section | Evidence / status | Remaining gap |
| --- | --- | --- |
| 0 Scope update | Adopted in AGENTS, security skill and current guidance. | Only the root currently owner-designated; broader inventory incomplete. |
| 1 Terminology | Assessment permission, target identity and authorization tests separated in instructions and report. | Legacy dispatcher still has AUTH_REQUIRED branches; not certified for production. |
| 2 Production and safety | Actual root-only observation; local tests separately labelled. Native vetted-IP/cancellation and bounded script verified. | Full adapter-wide budgets, degradation baselines, host telemetry and incident wiring absent. |
| 3 Inventory | Read-only classification of all 399 rows, source provenance and gaps; no promotion. | No authoritative full estate, continuous discovery/history reconciliation or dashboard gap view yet. |
| 4.1 Web | Root chain/negotiated TLS/expiry only. | Headers/cookies/CORS/XSS/CSRF/injection/redirect/cache/business-logic checks not executed. |
| 4.2 API | No approved API manifest or target test identity supplied. | API route, schema, GraphQL, mass-assignment and access-control coverage absent. |
| 4.3 Authentication/authorization | Explicit excluded-check gap list; no invented identities or credential probes. | Provisioned paired roles/tenants/objects and safe account-flow configuration required. |
| 4.4 Media/files | Existing PUBLIC_BY_DESIGN policy preserved. | No production media policy verification, upload/download or storage check performed. |
| 4.5 Infrastructure | Root TLS endpoint only; observed IP not promoted into network scope. | Owned ranges, ports/vantage, server/cloud config and read-only access not supplied. |
| 4.6 Source/dependencies/containers | Existing supplied-artifact SBOM engine and synthetic tests remain functional. | No customer artifacts supplied; no Empire dependency/container/source assessment performed. |
| 4.7 Supporting modules | Historical `/news` seed identified. | No supporting-service execution; third-party feeds excluded. |
| 5 Scanners | Source audit and PATH capability records; native TLS driver version 1.1.0. | No Nuclei/ZAP/Trivy/Nmap/Greenbone/Semgrep/Prowler/MobSF/Docker executable found. Native versions, installation/licensing and production adapter runs unverified. Embedded fallback is not native scanner coverage. |
| 6 Profiles/scheduler | Existing durable queue/scheduler retained; root script has fixed version/limits and local overlap guard. | Production profiles A–D, their full check allowlists, distributed per-profile controls and change-triggered production coverage not implemented. |
| 7 Findings/evidence | Prior canonical lifecycle, immutable observations and pending-retest controls retained; root evidence minimal and hashed. | Complete brief schema/confidence mapping, encrypted raw evidence/retention and every legacy parser not certified. No new vulnerability asserted from root reachability. |
| 8 Dashboards/roles | Existing owner/grant and measured diagnostics fixes retained. Reconciliation is available via owner API. | No new dashboard UI for inventory gaps; complete persona/multi-tenant coverage unverified. |
| 9 Reporting | Row-level inventory JSON, root execution evidence, this limitations report and validation JSON. | Full estate executive/technical findings register, scanner-version matrix and coverage report cannot be generated truthfully without executions. |
| 10 Engineering | Existing stack reused; isolated regressions and contract checks, no schema change. | Real scanner binaries, Docker/PostgreSQL acceptance and customer production recovery unverified. |
| 11 Autonomy | Actual code fixes and bounded production observation completed without repeated authorization requests. | Missing owner configuration documented; unsafe legacy workflows were not run. |
| 12 Milestones | Detailed status below. | Full end-to-end production acceptance remains incomplete. |
| 13 Non-negotiable rules | Scope, credentials, safety, redaction and evidence boundaries retained. | Adapter-wide enforcement is still incomplete; instructions alone do not implement it. |

Legacy audit blockers remain concrete: `scanners/empire_engine.py` contains
synthetic Authorization values, account probes and a brute-force-defense probe;
`synthetic_harness.py` manufactures bearer tokens; several legacy clients disable
TLS verification or follow redirects. Broad Nuclei tags are not a reviewed safe
allowlist. A preflight helper does not pin every external tool's actual connection.
These paths were inspected, not executed against Empire. Do not enable them on the
strength of this limited acceptance report.

| Milestone | Current result |
| --- | --- |
| M0 Repository/scope audit | Current architecture, instructions, source paths and requirement gaps recorded; conflicting active instructions updated. |
| M1 Inventory | Existing 399 rows reconciled; full production source remains missing. |
| M2 Scanner audit | Source/capability audit recorded; no executable versions or real external-tool acceptance available. |
| M3 Safe configuration | Limited root observation and fixture guards implemented/tested; full production profiles/telemetry/orchestration incomplete. |
| M4 Execution | One real unauthenticated root HEAD with TLS evidence. All broader/authenticated checks unexecuted. |
| M5 Reporting | This scoped report plus actual inventory/observation evidence. No full security assessment or new confirmed vulnerabilities claimed. |
| M6 Regression | Isolated checks and skill validation recorded in the linked validation JSON; platform production release remains on hold for the gaps above. |

## Verification and acceptance

Exact commands, exit codes, test counts and artifact paths are preserved in
[EMPIRE_PRODUCTION_VALIDATION.json](EMPIRE_PRODUCTION_VALIDATION.json).
The final isolated pilot run passed **189 tests**, with **one deliberately
deselected** real-DB-copy case and zero failures. The API contract audit matched
121 calls with zero missing/method mismatches across 162 registered operations.
All seven project skills passed the library validator and bundled frontmatter
validator; `git diff --check` passed. Existing synthetic-suite warnings are recorded
in the validation JSON rather than hidden.
Regression cases exercise fixture provenance, seed/expiry handling, sanitized
reconciliation, owner/grant boundaries, no automatic asset creation, scoped
idempotency, worker rechecks, HEAD transport, scope/stop/deadline cancellation and
truthful auth/redirect/error gaps. All test targets are local or mocked.

The seven project skills remain available under `.agents/skills/`; invocation and
the original practical validation for each are in [the Skills guide](../AGENT_SKILLS.md)
and [installation evidence](AGENT_SKILLS_AUDIT.md). Current policy edits received
fresh structure/frontmatter checks and practical backend/security/review use.
No frontend code changed in this inventory stage, so prior browser/build evidence
is retained as historical evidence rather than claimed as a fresh UI run.

Acceptance: the local inventory and fixture-dispatch changes are reviewable with
regression evidence. **Full Empire assessment and production release are not
accepted**: authoritative estate configuration, identities where required, health
telemetry and safe real scanner integrations are still incomplete.
