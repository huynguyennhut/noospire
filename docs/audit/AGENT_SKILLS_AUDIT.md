# Project skills implementation audit — 2026-11-15

> Historical installation baseline. Subsequent runtime fixes and current test
> results are recorded in [PROJECT_CURRENT_STATE.md](PROJECT_CURRENT_STATE.md).
> The 11 failures below describe the initial audit, not the current working tree.
> Subsequent Empire policy and inventory evidence:
> [EMPIRE_PRODUCTION_RECONCILIATION.md](EMPIRE_PRODUCTION_RECONCILIATION.md).

Scope: repository discovery, seven executable agent workflows and practical local
validation. This is a current skills-system audit, not a production certification.
Starting revision: `cc3a5e0` on `main`; tracked working tree was clean. No existing
`AGENTS.md` was found in the checkout or parent directories. Existing `.agents/`
contained historical teamwork artifacts; these were preserved.

The supplied `NOOSFORGE_CODEX_PROJECT_MASTER_PROMPT.md` was used as product context
(self-hosted security intelligence, premium UI, public-only assessment). Embedded
commands, role assignments and old completion claims were not treated as independent
authorization or proof. This task implemented the requested Skills system rather
than launching unrelated feature rewrites or customer assessments.

## Current architecture and evidence

Source inventory is reproducible using
`.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py`.
It found 19 Next page files, 162 HTTP decorator declarations, 41 ORM table
declarations, 12 pilot test files and 29 legacy test files. Decorator counts include
local router paths and differ from the registered OpenAPI operation count. Scanner
class declarations include helpers; they do not count working integrations.

| Layer | Verified source and workflow |
| --- | --- |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind 3, Lucide; `frontend/package.json` and lockfile. App Router uses `output: 'export'`, trailing slashes, unoptimized images; deployment serves `frontend/out`. |
| UI/design | `app/layout.tsx` wraps `components/layout/Shell.tsx` in theme/i18n/toast providers. Root component wrappers are compatibility exports. Shared UI and custom SVG charts live under `components/`. Obsidian Dark and Warm Light tokens are in `styles/globals.css`/Tailwind; warm theme applies `data-theme=warm`. Official assets remain under `public/brand`. |
| Client/API | `lib/api.ts`, `lib/types.ts`, `lib/events.ts` use same-origin `/api/v1`, session/CSRF, distinct errors, event cursor/SSE/polling. Registered routers and common JSON error/request-ID middleware are in `backend/main.py`; `backend/app/main.py` is an alias. |
| Platform security | `api/auth.py`, `api/deps.py`, `core/security.py`, user/grant/revocation models. Cookie mutation CSRF, JWT validation, sole-owner identity and grant logic exist. Actual scope behavior differs from owner-only docstrings; see failures below. |
| Database | Async SQLAlchemy with SQLite WAL/busy timeout by default, asyncpg branch available. `core/database.py` uses metadata creation plus additive SQLite alterations and catalog seeding; no Alembic chain found. PostgreSQL runtime was not exercised. |
| Durable work | `core/planner.py` materializes execution records and queue rows; `core/queue.py` claims with leases, fencing, heartbeat/retries. Dispatcher routes defensive execution through `engines/runner.py`. Separate worker and scheduler entrypoints; current scheduler is `core/monitor_scheduler.py`, not the older daily scheduler. |
| Defensive engines | `sbom` uses supplied CycloneDX/SPDX artifacts and immutable advisory snapshots; `tls_health` uses approved endpoints/vetted IPs. Results, hashes, attempts and observations persist. Tests cover local TLS and synthetic SBOMs. |
| Legacy scanners | `scanners/base.py` defines adapter types/fingerprints. Nuclei/ZAP/Trivy adapters, embedded lab fallbacks, crawler, Empire engine and synthetic checklist harness remain. Native binaries (`nuclei`, `zap.sh`, `zaproxy`, `trivy`) were absent from PATH during this audit. No target scans were run. |
| Evidence/reporting | `models/lifecycle.py`, `core/lifecycle.py`, console/engine runners track observations, changes, notifications, hidden records and snapshots. Reporting uses Jinja2 HTML, ReportLab PDF and JSON. Persisted legacy and current state vocabularies coexist; tests expose mismatches. |
| Intelligence/rules | `app/intel/` has NVD/OSV/GHSA/KEV/EPSS ingestion and aliases; `app/rules/` has validator/test/lifecycle code, with rule fixtures under `fixtures/rules`. No feed or rule updates were triggered. |
| Deployment | Compose ships API/worker/scheduler/gateway sharing SQLite `/data`; optional cloudflared Named Tunnel, origin Access validation and separated networks. Gateway-only host publish is loopback. Dockerfiles pin Python 3.14 and Node 22 images; local environment is Python 3.12.14 / Node 20.18.0. Docker was absent. |
| Development/tests | Existing npm `typecheck`, `lint`, `build`; default pytest points to `tests_pilot`. No configured frontend component/E2E npm runner or `.github/workflows` CI found. Existing browser scripts require review for fixed ports/credentials and output paths. |

## Findings that change skill behavior

| Priority | Evidence | Decision incorporated into skills |
| --- | --- | --- |
| High | `tests/conftest.py` seeds configured DB/users, enables private targets and deletes repository report files at session start. `scripts/qa/setup_test_environment.sh` mutates owner state. | Do not run these in the working checkout; use inspected synthetic pilot presets. |
| High | One pilot migration test copies repository `noospire.db` with `shutil.copy2`, ignoring WAL consistency and importing existing data into tests. | New QA runner deselects that test and validates schema/backup on a fresh synthetic DB. Initial baseline was run before this exception was identified; it did not modify the original DB. |
| High | `api/deps.py:load_scope` grants estate-wide access to multiple roles including VIEWER; tests reproduce visibility outside grants. | Backend/security skills require actual object-scope checks and record this as an unresolved policy gap. No permission model was silently rewritten in a skills-only change. |
| High | `scanners/empire_engine.py` includes synthetic Authorization and account/login probes; `api/checklist.py` invokes `SyntheticTestHarness`; dispatcher still emits `AUTH_REQUIRED`. | Preserve public-only requirement explicitly. Never certify legacy execution from old audit claims; use local outbound-request tests for future fixes. |
| High | Native adapters can report embedded lab fallback; Nuclei broad tags do not establish safe template selection. Engine health test reports HEALTHY where it expects UNAVAILABLE. | Distinguish installed binary/native execution, lab mode, unavailable and genuine coverage. |
| Medium | README launcher flags and stack description differ from `run.sh`; launcher gateway defaults to `0.0.0.0` while Compose publishes loopback. | DevOps instructions use actual `--build-console` flag and explicit local bind, not obsolete README commands. |
| Medium | Local Python 3.12 / Node 20 differs from Docker Python 3.14 / Node 22. Docker unavailable; no verified PostgreSQL/Redis/Celery deployment. | Skills document runtime differences and avoid unverified infrastructure claims. |
| Medium | Historical traceability references nonexistent `app/engines/*_engine.py` and `core/ssrf_protector.py`, and blanket verification claims. | Retain historical record but add a dated scope note; map new skills to real files and fresh evidence. |
| Medium | `deploy/smoke.py` counts missing-credential checks as passed with “skipped” detail. | DevOps/release review must report signed-in checks as skipped unless credentials were supplied in an isolated test. |

## Implemented system

- Root `AGENTS.md`: shared product/safety rules, stack pointers, safe test command,
  concise routing table; specialized procedures live in seven skill folders.
- Every skill has validated YAML metadata and generated `agents/openai.yaml` with
  a concrete `$skill-name` prompt. Implicit selection remains enabled.
- Three helpers: read-only AST/source inventory; isolated allowlisted check runner
  with real exit codes/logs/JUnit; library validator for metadata, links, routing and
  script syntax. The security reference adds boundary checkpoints without copying
  general engineering manuals. No placeholders or unused templates are included.
- [Invocation guide](../AGENT_SKILLS.md) documents all seven entrypoints and commands.
  No remote plugin/service, package dependency, global skill installation or app
  configuration change is required.

## Validation record

A workflow correctly reporting an existing failure is different from the underlying
platform passing that workflow's acceptance checks. Each workflow was applied to a
real repository task; related suite results below are subsets of the same full
pilot run and must not be added together as independent coverage.

| Skill | Practical task and observed result |
| --- | --- |
| Repository audit | Ran the bundled inventory and cross-checked API, table and scanner class source coordinates. Traced actual layout, API registration, planner/queue/runner and process entrypoints. PASS: inventory ran without app startup or data access. |
| Frontend | Followed theme/layout/static-export instructions, then ran existing npm typecheck, lint and build. PASS: all three exited 0; ESLint reported no warnings/errors; static export completed. No browser/visual verification was claimed. |
| Backend | Applied API/queue/lifecycle verification to pilot identity, SBOM and console suites within the full runner. 27 passed / 8 failed; failures preserve actual contract/state disagreements. This validates the workflow's ability to expose defects, not server acceptance. |
| Security/scanners | Inspected actual legacy outbound probes, scope and mode boundaries. Pilot identity, driver, TLS and contract subsets: 48 passed / 6 failed. In particular 23 driver tests and 7 TLS/egress tests passed; VIEWER exposure and engine-health mismatch remained visible. No customer/native scanner execution. |
| QA | Executed the new `pilot` runner with sanitized settings: 106 passed / 11 failed / 1 deselected; it wrote logs/JUnit/results and returned 1. Compared failures to initial pre-edit baseline (107 passed / 11 failed); the sole count difference is deliberate exclusion of the real-DB-copy test. |
| DevOps | Executed the new `devops` preset: 17 gateway/restart/smoke tests passed; CLI init-db, online backup and restore-check on fresh synthetic schema each exited 0; integrity_check=ok. Static Compose checks confirmed intended network/publish/volume topology. Docker build/config CLI blocked because Docker is absent. |
| Release review | Validated all metadata/resources and invocation routing, checked the diff, inspected failures and ran the client/server contract audit: 121 matched calls, zero missing/method mismatch, 161 registered operations. Decision: skills implementation validated; platform release remains on hold for material baseline findings. |

Commands executed from the repository root:

```bash
# Initial baseline, before helpers (also ran the legacy DB-copy pilot case)
.venv/bin/python -m pytest -q tests_pilot --junitxml=/tmp/noosforge-skills-pilot.xml

.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py
.venv/bin/python .agents/skills/noosforge-release-review/scripts/validate_skills.py
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py contract
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py devops
git diff --check
```

Additional skill-system checks:

- Bundled skill-creator `scripts/quick_validate.py`: 7/7 manifests passed.
- Disposable copies with malformed YAML, duplicate YAML keys, folder/name mismatch
  and a broken reference were correctly rejected by the project validator.
- All six runner presets constructed valid argv/cwd selections; synthetic inherited
  prefixed and unprefixed database/storage/bootstrap/role settings were sanitized.
  The contract preset was rerun after hardening this environment filtering and passed.
- Installed Codex native app-server `skills/list` with `forceReload=true` discovered
  all seven enabled project skills from root, `frontend/` and `backend/`, with no
  project skill errors. This used local JSON-RPC initialization/listing only: no
  agent task, model request, new chat or global configuration change. The desktop
  selector UI and automatic model routing were not exercised.

Durable sanitized command/results/discovery summary:
[AGENT_SKILLS_VALIDATION.json](AGENT_SKILLS_VALIDATION.json). Raw local artifacts:

| Run | Logs/results/JUnit directory |
| --- | --- |
| Pilot | `/tmp/noosforge-pilot-a2ib2g9t/` |
| Frontend | `/tmp/noosforge-frontend-b0k9ic26/` |
| Contract (final) | `/tmp/noosforge-contract-tducuibg/` |
| DevOps | `/tmp/noosforge-devops-y8u5tims/` |
| Native discovery | `/tmp/noosforge-skills-discovery.json` |

Temporary files can be removed by the OS; the JSON summary above preserves commands,
exit statuses, counts, failing test names and native discovery results in the repo.

## Remaining platform failures and release limits

The same 11 failures reproduced before and after implementation:

- HTTP bootstrap without an operator token returns 201 instead of expected 404;
  repeated bootstrap returns 400 instead of expected 409.
- A developer's ungranted scan returns 403 instead of expected opaque 404.
- VIEWER without grants can list assets; a related proof/visibility test receives
  200 for an ungranted asset instead of expected 404.
- SBOM and console lifecycle checks disagree with `FIXED_PENDING_RETEST` versus
  `FIXED`; triage checks disagree on `IN_PROGRESS` versus `IN_REMEDIATION`.
- Invalid-state retest responds 400 instead of expected 409.
- Legacy schedule trigger responds 200 instead of expected retired-route 410.
- Engine health reports HEALTHY where the fixture expects UNAVAILABLE.

These require scoped behavior/policy reconciliation and regression work, not weaker
assertions. Highest-value follow-up is to enforce and test public-only customer
execution and server object-scope boundaries. No runtime application source was
changed as part of establishing this Skills system.

Not executed: browser visual QA (no UI code changed), Docker images/Compose runtime,
PostgreSQL, native Nuclei/ZAP/Trivy, customer assessments, external pilot deployment,
production backup/restore, DNS/firewall/tunnel changes. No production readiness claim
is made. Shared existing data, brand assets and historical teamwork artifacts were
preserved; no commit or push was performed.
