# Local operation and tracking

Run these commands from the repository root using the installed `.venv`. The local
supervisor binds API and gateway to **127.0.0.1 only**. It does not deploy externally,
seed users/assets, reconcile inventory or approve customer endpoints.

```bash
./run.sh start                    # API + gateway, no automatic jobs
./run.sh start --build-console    # rebuild the static console before starting
./run.sh status
./run.sh stop
./run.sh start --enable-jobs      # API + gateway + durable worker + monitor scheduler
```

`start` is detached, so closing the initiating terminal does not stop the services.
It refuses occupied ports and does not replace unrelated processes. When changing
from console-only to jobs enabled, stop the managed stack first. Default addresses
are [console](http://localhost:8080/) and API `127.0.0.1:8000`; use `--port` and
`--api-port` for separate local instances, along with separate database/storage and
`NOOSPIRE_LOCAL_STATE_DIR` settings. An existing export is needed unless building.
Install frontend dependencies from the existing lockfile with `npm ci` in
`frontend/` when they are absent; the launcher does not silently reinstall them.

The launcher always sets `SENTINEL_DEFENSIVE_ONLY=true` and its legacy unprefixed
equivalent. Only scans with a durable `ExecutionRecord` can be claimed or recovered;
old legacy scanner queue rows stay untouched. API dispatch cannot run a worker or
create a lease. Database atomic claims remain the only worker entry. A new local
start never replays legacy jobs merely because they were left queued historically.

The worker executes the existing approved monitor schedules. The launcher does not
create a schedule or expand its scope. For the designated Empire root, verify the
monitor schedule selects only that reconciled asset, uses `public_web`, and has
`interval_minutes=120`. Schedules align to UTC epoch slots; the UI displays local
time. A powered-off/suspended computer cannot execute a slot: existing scheduler
catch-up semantics coalesce missed slots rather than running every missed scan.

For the current owner-designated installation, `scripts/configure_empire_monitor.py`
provides a read-only preview with `--database <path> --schedule-id <existing-id>`.
`--apply` first creates and checks a private SQLite online backup, then validates
the configured owner and existing genuine root ownership proof, adds a dedicated
exact-root scope and updates that schedule to 120 minutes. `--queue-first-run`
adds one idempotent initial job to the existing queue. It performs no network
request itself and cannot replace a missing ownership proof. Inspect the preview
and [current handoff](audit/LOCAL_MONITOR_HANDOFF_2026-11-16.md) before using it.

Use the console's Assets, Scan Center, Schedules, Operations and Health screens to
track eligibility, planned checks, individual execution attempts, observed findings,
worker freshness, next slot and operational errors. The `public_web` engine is a
bounded unauthenticated observation of the approved exact URL. It does not establish
application health, authenticated coverage, vulnerability absence or a comprehensive
assessment of undiscovered assets.

## Logs and readiness

```bash
./run.sh logs api --lines 80
./run.sh logs worker --follow
./run.sh logs scheduler --follow
./run.sh logs gateway
./run.sh logs supervisor
```

Each role has its own append-only log under `storage/local-stack/`. `status` returns
process identities, API/gateway readiness, enabled roles and log paths without
printing secrets. The state directory is mode 0700 and files are mode 0600. Keep
logs on the local machine; authenticated target secrets must never be added to
operational logs. Logs are retained across restarts; archive them locally according
to available disk space while services are stopped.

API readiness checks the database; it does not prove worker execution succeeded.
The supervisor restarts a crashed child up to three times within a rolling minute,
then stops the managed stack and records `failed`. Execution results and worker
heartbeats are the evidence for successful processing. Check `status` plus role
logs after a fault. The supervisor itself is a local process, not a system service:
reboot requires running `start --enable-jobs` again. An always-on deployment uses
reviewed Docker/service configuration separately.

A local signing key is reused from configured environment/`.env` when suitable; if
absent, a generated private `storage/local-stack/session.key` is retained across
restarts. Never publish this file. The launcher does not reset passwords or create
accounts; use the existing owner account, or the documented one-time bootstrap CLI
on an empty database.

## Pause, backup and recovery

The owner can set `PUT /api/v1/operations/emergency-stop` with `{"active":true}` to
persistently prevent new claims. Public web execution also observes this flag while
running. Resume with `{"active":false}` after inspecting the cause. Pausing a
schedule prevents future scheduled work; it does not erase history. `./run.sh stop`
stops every managed role; an interrupted durable job is recovered under its lease
and retry rules at a later start.

Before schema/configuration changes, take a SQLite online backup with
`.venv/bin/python -m backend.app.cli backup --out <backup-path>`. Do not copy a live
WAL database using ordinary file copy. Preserve evidence storage alongside database
backups. Do not restore over customer data without approval. See
[the deployment runbook](../deploy/README_DEPLOY.md) for backup/restore verification.

Practical verification uses disposable data and random loopback ports:

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py devops
```

The suite verifies console-only startup, opt-in roles, occupied-port protection,
worker crash recovery, status/logs/stop, no implicit asset seeding, queue isolation,
stop enforcement and refusal to create/steal leases outside the atomic claim path.

## Managed local operation (Linux user service)

`deploy/noospire-local.service` runs the same supervisor, API, gateway, worker and
scheduler with restart on supervisor failure. It expects this checkout at
`~/noospire`, an existing frontend export and the current application configuration.
It does not create accounts or change target scope. The supervisor writes its own
private `storage/local-stack/supervisor.pid` and removes it on clean shutdown.

After verifying the export and taking an online database backup:

```bash
./run.sh stop
install -Dm644 deploy/noospire-local.service ~/.config/systemd/user/noospire-local.service
systemctl --user daemon-reload
systemctl --user enable --now noospire-local.service
systemctl --user status noospire-local.service
./run.sh status
```

Use `systemctl --user stop noospire-local.service` to stop a managed installation;
use `disable --now` to undo autostart. Preserve the application DB and evidence.
The unit's failure restart observes systemd's configured burst limit; persistent
failures remain visible instead of restarting endlessly.

A user service starts with the user's service manager. Without user lingering it
is **not** guaranteed to run before login or after the last session ends. Inspect
`loginctl show-user "$USER" -p Linger`; enabling host-level lingering, preventing
sleep, or deploying to an always-on server is an explicit host operation separate
from this local unit. A suspended or powered-off host cannot perform scans.

The dashboard now reports a fresh completed **scheduler tick**, separately from
worker heartbeats. Enabled schedules without these signals display a warning.
“Scan now” queues the saved selection/engines directly; plan preview is optional.
No per-run permission approval is required. Existing scope/egress and emergency
stop controls still apply. Scheduled and manual executions share the same durable
planner and worker path.

## Bounded public-surface mode and passive Nuclei (Linux x86-64)

`public_web` retains the original `head` configuration. Its explicit `surface`
mode performs serial, verified-TLS GETs to discovered same-origin HTML links: at
most 12 request attempts, one-second spacing, 1 MB of HTTP bytes including framing,
96 KiB per body and 75 seconds total. Queries, forms, logout/action paths, media,
static files, private DNS addresses and redirects are excluded. It revalidates
persisted scope and emergency stops before writing each request. A 429/5xx or
slow response stops the traversal. Raw HTML and cookies are not stored.

Preview the current root configuration without changing it:

```bash
.venv/bin/python scripts/configure_empire_monitor.py \
  --database noospire.db --schedule-id <existing-schedule-id> --mode surface
```

Adding `--apply` takes an online backup first and changes only the dedicated
`noosforge:public-monitor` grant for the already proven root origin. It enables
`/*`, 12 attempts and the 1 MB budget; existing unrelated grants and fixtures remain
untouched. `--queue-first-run` adds one durable idempotent job. This is local
monitor configuration under the owner's standing Empire authorization, not an
external deployment or permission to treat every database row as production.

The optional native subdriver analyzes only sanitized `Server`/`X-Powered-By`
headers already captured by that GET. Provision it locally with:

```bash
.venv/bin/python scripts/install_nuclei.py
```

The installer downloads the pinned official Nuclei 3.11.1 Linux amd64 archive and
checks its SHA-256. Runtime independently checks the binary and both repository
header templates. `bubblewrap` must support unprivileged namespaces on this host.
The process has no network interface or host home/environment mounts, no target
URL, no body, cookies or credentials; templates and input are read-only. It cannot
update templates, use Interactsh, execute arbitrary supplied templates or perform
active CVE checks. Timeout, resource/output bounds and process-tree cancellation
apply. Missing binary/sandbox or rejected input produces an explicit coverage gap
and no fabricated negative check. The legacy standalone Nuclei adapter still has
`NOT_INTEGRATED` status; this bounded passive subdriver does not change that claim.
This local installer does not provision Docker images or non-amd64 hosts.

Scheduled `public_web` slots now create one frozen JSON/HTML/PDF snapshot on
finalization, including partial/failed execution evidence when available. The
dashboard links to it; manual runs offer a report form prefilled with the actual
batch ID. Two schedulers race through one atomic slot claim before creating the
snapshot. Report creation failure rolls the finalization back for a later retry.
Old frozen snapshots retain their original template and hashes.
