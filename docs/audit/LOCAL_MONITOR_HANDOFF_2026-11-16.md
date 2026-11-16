# Local monitor handoff — 2026-11-16

The current owner request authorizes the repository changes, local execution and
GitHub push. Customer assessment follows the owner-designated root in
[inventory guidance](../EMPIRE_INVENTORY_GUIDANCE.md). This handoff does not certify
the legacy scanner paths or an entire undiscovered production estate.

## Delivered behavior

- Assets derives eligibility from fixture provenance, genuine ownership proof and
  current scope. Seed/test records remain inspectable; their assessment buttons
  are disabled with a reason. Filtering happens before pagination.
- Dashboard, Assets and Scan Center use the same durable plan/run flow. Historical
  chart totals are distinguished from approved production coverage. Fabricated
  health URLs and feed connectivity/security-posture claims were removed.
- `public_web` performs one unauthenticated HEAD at the exact approved HTTPS URL.
  DNS addresses are vetted and pinned; TLS hostname/chain verification stays on.
  It sends no platform/target credentials, follows no redirects and stores no
  response body, raw cookies or redirect values. Seven versioned rules cover TLS,
  expiry, applicable response headers and observed cookie Secure attributes.
- Ownership, URL/revision, origin/path/port, allowed checks, expiry, windows and
  budgets are revalidated before transport. Persisted stop/cancellation/lease
  state is checked during execution. Missing capabilities remain coverage gaps.
- SQLite claims reserve public-host concurrency and at least 20 seconds between
  claims. A zero retry budget stays zero, including crash recovery. Lease claims
  remain the only execution entry. The local worker excludes legacy queue rows.
- Owner-only global stop is persistent and audited. Schedule/worker/log/result
  screens use actual API records. Execution details expose persisted scan logs.
- Detached local supervision provides separate API, gateway, worker and scheduler
  logs, process status, bounded child crash recovery and safe stop/restart. All
  listeners bind loopback; credentials/runtime/evidence/DB/backups are gitignored.

## Configured installation

The operator ran `scripts/configure_empire_monitor.py` against the existing
`noospire.db`, with explicit schedule ID and `--apply --queue-first-run`. It made
a mode-0600 SQLite online backup, verified integrity, applied the additive global
stop column and recorded the configuration audit. No asset, user, ownership proof
or target-auth credential was created. A dedicated exact-root scope was added;
existing scope/proof/history rows were preserved.

- Target: `https://empire.edu.vn/` only; 399 inventory rows remain present.
- Schedule: `2837dbc3-40e6-4553-9dda-f2170cb56e6f`, **120 minutes**,
  `public_web`, slow profile, one selected asset and one worker slot.
- Estate capacity: one simultaneous defensive execution; existing host quotas and
  emergency stop are retained.
- First batch: `7a426179-bfb8-4f4a-ab88-fca6a484b19f`.
- First measured execution: **2026-11-16 22:48:37 ICT**, HTTP **200**,
  verified **TLSv1.3**, six evaluated checks, zero failed checks, no cookies observed.
  One HEAD request, 112 application bytes sent and 728 response-header bytes read.
  Certificate expiry was 2027-01-25. These observations describe that response only.
- Next configured slot after setup: **2026-11-16 23:00 ICT** (16:00 UTC).
  Slots align to UTC epoch; subsequent slots are two hours apart. Missed slots
  coalesce after restart rather than generating a burst of historical requests.
- Local console: [http://localhost:8080/](http://localhost:8080/).

No approved target identities, test records, customer application-health endpoint,
source/container artifacts or external native scanner tools were provided. The
execution therefore explicitly reports authenticated, application-health,
crawling/injection and source/container/cloud/mobile coverage as unassessed. Zero
findings and successful monitoring do not establish comprehensive security.

## Validation and operation

Commands and current results are recorded in
[LOCAL_MONITOR_VALIDATION.json](LOCAL_MONITOR_VALIDATION.json). Local raw test logs,
backup references and synthetic UI data are retained under ignored
`storage/qa-handoff/`; no database or secret files are published.

The first full pilot run found three regressions: listener TIME_WAIT prevented
immediate local restart; a registry contract assumed engine ordering; a new
end-to-end test ignored the required public-host spacing. Restart binding was
corrected to match the server's SO_REUSEADDR behavior while retaining occupied-port
protection. Registry membership is asserted independently of presentation order.
The execution test now verifies the spacing block before advancing synthetic DB
timestamps. The affected 56-test group subsequently passed.

Earlier hydrated browser checks inspected the eligible/all inventory filter,
disabled fixture action and actual server plan in Obsidian Dark. The new dashboard
panel showed real inventory/worker/schedule state. Further browser verification
was blocked by the browser tool's URL-policy gate; final Warm Light, responsive and
interactive global-stop checks are not claimed as completed. Frontend compilation,
unit tests and API/worker tests are separate evidence.

```bash
./run.sh status
./run.sh logs worker --follow
./run.sh logs scheduler --lines 80
./run.sh stop
./run.sh start --enable-jobs
```

The machine must remain on and awake for local schedules. This is a detached local
supervisor, not an installed boot service. After reboot, run the last command.
Use the existing owner account; passwords have not been reset. See
[LOCAL_OPERATIONS.md](../LOCAL_OPERATIONS.md) for pause, backup and recovery.
Docker/image builds, PostgreSQL concurrency, external deployment and full Empire
assessment remain unverified.
