# NOOSFORGE / Noospire

Self-hosted security intelligence, asset monitoring and evidence-based remediation.
The console uses Obsidian Dark / Warm Light Liquid Glass and Vietnamese/English.

Start with [AGENTS.md](AGENTS.md) for repository boundaries and
[the Skills guide](docs/AGENT_SKILLS.md) for the seven project workflows.
The [current audit](docs/audit/PROJECT_CURRENT_STATE.md) records implemented fixes,
actual validation and remaining gaps. Historical reports are not release evidence.
The latest [local monitor handoff](docs/audit/LOCAL_MONITOR_HANDOFF_2026-11-16.md)
documents the root-only two-hour monitor, measured execution and current limits.
The latest [assessment workflow audit](docs/audit/ASSESSMENT_WORKFLOW_2026-11-17.md)
records the real SBOM UI-to-worker/report/retest acceptance and remaining engine
gaps. Run the [isolated local lab](docs/ASSESSMENT_LAB.md) to reproduce it without
copying customer data.

## Current architecture

| Layer | Implementation |
| --- | --- |
| Console | Next.js 14, React 18, TypeScript, Tailwind 3; static export in `frontend/out` |
| API | FastAPI/Pydantic; `backend.main:app`; same-origin `/api/v1` |
| Persistence | Async SQLAlchemy; SQLite WAL in the shipped deployment; additive boot schema |
| Execution | Persistent DB queue, leases/fencing, worker heartbeats; separate API, worker and monitor-scheduler roles |
| Defensive controls | Exact approved public URL HEAD/TLS/header observations; supplied CycloneDX/SPDX SBOMs with immutable advisory snapshots; separately approved TLS/health measurements |
| Evidence | Execution input/output hashes, observations/change history, frozen HTML/JSON/PDF reports |
| Gateway | Fixed upstream API origin and static console; optional Access/Tunnel; Docker Compose packaging |

Nuclei, ZAP, Trivy and Empire/checklist paths exist in the source but are not all
integrated into the fenced defensive execution flow. Engine health reports actual
worker/feed readiness; offline self-tests do not certify network or worker execution.
No upstream version check or update occurs through the driver-version dialog.

The current pilot uses one immutable configured owner plus explicit per-asset grants.
Legacy role names/superuser flags do not confer global administration or estate scope.
This is not a claim of complete enterprise multi-tenant isolation.

## Customer assessment policy

The owner-adopted [Empire operations brief](docs/EMPIRE_PRODUCTION_AUTHORIZED_OPERATIONS.md)
authorizes non-destructive assessment of verified in-scope production assets,
including authenticated checks when approved target identities and safe test records
are provisioned. Never invent credentials or forward platform credentials to targets.
Approved public media remains `PUBLIC_BY_DESIGN`.

The [current owner clarification](docs/EMPIRE_INVENTORY_GUIDANCE.md) designates only
`https://empire.edu.vn/`; the 399-row database includes seeded/test assets and is not
an approved production inventory. No target-auth profiles, secret-store references
or customer health endpoints are supplied. Current automated checks therefore stay
unauthenticated; authentication-dependent checks are named coverage gaps. See
[inventory reconciliation and measured evidence](docs/audit/EMPIRE_PRODUCTION_RECONCILIATION.md).

Legacy scanner/checklist outbound enforcement is still incomplete. Do not enable
those customer workflows on the strength of old readiness claims. Known fixture
execution and seed-only ownership are rejected; Ultra fixture previews cannot
create or verify production assets. Platform login,
CSRF and authorization regression tests remain required and use synthetic fixtures.

## Local development

Use existing project dependencies and configuration; preserve repository DB/storage.
This checkout was validated with Python 3.12 and Node 20. Container manifests pin
different versions; see [deployment documentation](deploy/README_DEPLOY.md).

With dependencies and operator configuration prepared, the local supervisor
starts the API on loopback port 8000 and the gateway on port 8080:

```bash
./run.sh start                  # console only
./run.sh status
./run.sh stop
./run.sh start --enable-jobs    # also run worker and configured monitor schedules
./run.sh logs worker --follow
```

If the console export is missing, use `./run.sh start --build-console`. Dependencies
must already be installed from the lockfile. All local services bind loopback;
the launcher never seeds accounts/assets or claims legacy scanner jobs. Open
[the local console](http://localhost:8080/). See [local operation, logs and recovery](docs/LOCAL_OPERATIONS.md).
The launcher does not implement
`--check`, `--preset` or a Next.js production server on port 3000.
Windows uses `run.ps1` (`-Role`, `-BuildConsole`) through `run.cmd`.

Owner bootstrap is an operator action on the intended DB, using the CLI's
`bootstrap-owner --password-stdin` command and configured owner identity.
HTTP bootstrap is disabled unless `SENTINEL_BOOTSTRAP_TOKEN` is explicitly set,
and then requires the matching `X-Bootstrap-Token` header in every environment.
Login always verifies the stored password hash. Do not use old fixed test passwords.

## Safe verification

Run from the repository root:

```bash
.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py
.venv/bin/python .agents/skills/noosforge-release-review/scripts/validate_skills.py
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py contract
```

The runner uses disposable DB/storage and records commands, exit codes, logs and
JUnit results. Frontend checks include lifecycle unit tests, TypeScript, ESLint and
static export. The pilot preset excludes a test that copies the repository DB.
It is not a network sandbox: inspect changed tests before execution.

Do not run legacy `pytest tests` or QA seed/setup scripts directly on this checkout;
they can change shared users/data and delete stored reports. No customer scan is
needed for regression verification.

## Operations and lifecycle

Current schedules use `/api/v1/monitor-schedules`. All obsolete `/api/v1/schedules`
operations return 410 and leave historical rows intact.

A claimed fix is `FIXED_PENDING_RETEST` and remains open. `/retest` and `/recheck`
queue the producing defensive control. Only comparable successful engine evidence
can establish `RESOLVED`; manual triage cannot certify resolution. Rediscovery
reopens resolved/pending findings. The board and filters use all ten canonical states.

See [the runbook](docs/pilot/RUNBOOK.md), [deployment guide](deploy/README_DEPLOY.md),
[implementation decisions](docs/DECISIONS.md) and
[remaining work](docs/IMPLEMENTATION_ROADMAP.md). Review exact configuration,
backup/rollback and approval before destructive operations or external deployment.
Docker/scanner images, PostgreSQL and production recovery were not certified by
this local audit.
