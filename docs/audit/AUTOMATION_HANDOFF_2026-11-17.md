# Local automation handoff — 17 November 2026

The owner asked for automatic execution and a direct scan button, without another
assessment-approval workflow. The supplied Empire developer conversation requests
daily security checks and reports; it explicitly treats `/media` as public by
design. It describes intended Nuclei/ZAP/Trivy coverage, not evidence of installed
or operational adapters. This change does not reinterpret stored test assets as
customer targets.

## Implemented and running

- Main installation: `http://localhost:8080/dashboard/`, existing owner account
  `owner_admin`. No accounts or passwords were reset. The synthetic acceptance lab
  at 8082 is separate and is not the customer console; its processes were stopped
  after acceptance, preserving all lab files. Its browser tab now shows the main
  Scan Center.
- Dashboard: direct **Quét ngay**, pause/resume automatic scheduling, saved cadence,
  next ICT execution, last scheduled result and links to run progress/logs.
- Scan Center: **Quét ngay** calls the durable run API directly. Plan details are
  optional. No per-run approval is required. Empty/skipped plans do not produce a
  false “scan queued” message. Retries preserve the intent's idempotency key.
- Fresh scheduler completion telemetry is persisted in the additive
  `scheduler_heartbeats` table. Worker readiness and schedule enablement are shown
  separately; an enabled schedule alone is not advertised as active execution.
- Linux user unit `noospire-local.service` is installed and enabled on this machine,
  supervising loopback API, gateway, worker and scheduler. Its PID file refers to
  the actual supervisor; the unit restarts supervisor failures with a bounded
  restart policy. A controlled unit restart was also verified on this installation:
  all four roles returned ready and the owner session, observations and report
  survived. No external deployment, DNS or tunnel change was performed.
- Existing exact Empire-root schedule `2837dbc3-40e6-4553-9dda-f2170cb56e6f`
  remains active at 120 minutes. No inventory approval/reconciliation is required
  again for that already configured root.

## Real execution evidence (not synthetic tests)

After local startup, the scheduler independently queued and completed batch
`952765fe-fd37-49da-b42e-d5f9200a2ad6`, execution
`47a2fec1-6b5b-44d7-bc01-2685c2be8ce4`, at 15:22 ICT.

The dashboard's direct button then queued batch
`27a44662-550c-4f32-93f7-832d03649770`; execution
`a3450a9c-821b-4e16-9e98-72e86d0b35d6` finished successfully at
15:24:04 ICT. The UI displayed the actual three persisted log entries: queued,
attempt started, succeeded. There was no plan-confirmation step.

This was one unauthenticated HTTPS HEAD to `https://empire.edu.vn/`: HTTP 200,
TLSv1.3 with certificate verification, six evaluated TLS/header checks, zero failed
checks and no observed cookies. It did not crawl the site or assess business logic.
Zero findings means no findings in these six checks; it is not a security verdict.

Using the Reports screen, a frozen report for that exact batch was generated:
`25cdd2c8-ef2b-46b6-a486-af7902b80942`, template
`noospire-pilot-report/1.2`, snapshot SHA-256
`849e6486d50c0eca65bb38c299adcb70d8da4ec33a4ac2247188bf734095671a`.
The HTML preview was inspected; authenticated PDF/HTML/JSON links were present.
The generated one-page PDF was rendered with Poppler and visually checked for
complete hashes, readable coverage exclusions and unclipped text.
The report contains the actual root observation and its named coverage exclusions,
not historical findings from unrelated seeded rows.

At handoff the existing schedule's next slot was **17:00 ICT, 17 November 2026**.
This is a saved next slot, not a claim that a future execution has already passed.

## Verification and operating limits

- Isolated pilot suite: **259 passed, 1 deliberately deselected**, 261 warnings.
  Includes real ASGI/queue/runner tests across twelve two-hour slots, covering ICT
  morning/evening/overnight, a new scheduler instance at every slot, duplicate tick
  suppression, pause, direct run without preview and idempotent request replay.
  The 24-hour clock is simulated; this does not claim a real 24-hour soak.
- Additional DevOps preset after PID-file changes: **25 passed**, plus fresh-schema,
  online backup and scratch restore-check. Includes actual local child-worker crash
  and supervisor recovery with disposable data/ports.
- Frontend and contract results are recorded in the companion validation JSON.
  Browser checks use the running main installation for the specifically requested
  root observation; UI-only responsive checks do not add target probes.
- `systemd-analyze --user verify deploy/noospire-local.service` returned zero. It
  also reported an unrelated existing `spice-vdagent.service` unit warning.
- No Nuclei, ZAP, Trivy or Docker executable was found on this machine. Full API,
  authenticated, source/container, cloud, mobile and server pentest coverage is
  **not delivered by the public-root monitor**. Existing unavailable engine states
  and coverage gaps remain explicit. No authentication credentials were invented.
- `Linger=no` on this host. The user unit starts with the user's service manager;
  it is not guaranteed before login or after the last session exits. A sleeping or
  powered-off computer cannot scan. Host boot/sleep policy was not changed.

## Data preservation and rollback

An online SQLite backup was made and passed `PRAGMA integrity_check` before main
startup, preserving all 399 assets:
`backups/before-automation-handoff-20261117T082216558959Z.db` (mode 0600).
No asset, finding, account or stored evidence was deleted. Old legacy queue rows
remain fenced from the defensive-only worker. No commit or push was made.

To stop/undo this local autostart:

```bash
systemctl --user disable --now noospire-local.service
```

Retain the database, evidence and backup. Code rollback can leave the additive
heartbeat table in place; do not restore over newer observations or reports.
Ordinary detached operation remains available with `./run.sh start --enable-jobs`.
The unit, process/log inspection and restart limits are documented in
[local operations](../LOCAL_OPERATIONS.md).
