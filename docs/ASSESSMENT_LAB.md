# Isolated assessment workflow lab

This lab runs the actual NOOSFORGE API, database queue, worker, scheduler and static
console. It uses a separate SQLite database and supplied synthetic SBOM/advisory
files. It does not copy customer records or represent an Empire assessment.

Run from the repository root with the existing Python/Node dependencies:

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
.venv/bin/python scripts/assessment_lab.py start
.venv/bin/python scripts/assessment_lab.py status
.venv/bin/python scripts/assessment_lab.py stop
```

Open <http://127.0.0.1:8082/>. The API binds loopback port 8002. Use `--port` and
`--api-port` on start if those ports are occupied. The supervisor uses the existing
`scripts/local_stack.py`; no Redis, Celery or Next.js runtime server is needed.

The first start creates a private `storage/assessment-lab/lab.json` containing a
generated owner password and session secret. Username: `lab-owner`. Read the file
locally when signing in; do not paste it into chat, reports or Git. The file is mode
0600 and its parent is mode 0700. `checks.db`, evidence and process logs remain in
that lab directory after stop. Start reuses them. The script refuses an existing
nonempty unmarked directory and overrides prefixed/unprefixed database settings
so the repository `.env` cannot redirect it into `noospire.db`.

## Reproduce the accepted flow

1. In Assets, create a DEV target named `SYNTHETIC LAB — supplied SBOM only`, with
   locator `https://sbom-workflow.pilot-test.invalid/`. Keep network ownership
   pending. Do not verify or scan that reserved domain. Supplied-file analysis is
   separate from network admission; known fixture/seed provenance remains denied.
2. In Engine Runs, select SBOM and the lab asset. Upload
   `tests_pilot/data/sbom_vulnerable.cdx.json`. Without an active advisory snapshot,
   a real worker finishes `unavailable / RULES_UNAVAILABLE`; it must not report PASS.
3. Import `tests_pilot/data/advisories_pilot_v1.json`. Import stages the version.
   Review its source/version/digest/count, enter a reason and activate it. The file
   parser/index compatibility and digest are checked; source accuracy is still the
   operator's responsibility. No online template/feed update is implied.
4. Run the vulnerable SBOM. The native engine evaluates 5 of 7 components and
   records 4 synthetic findings. Inspect persisted attempt/worker logs, driver and
   rules versions, input/output hashes and the downloadable normalized output.
5. Open Findings. Component proof is stored evidence, not HTTP capture. Request,
   response, headers and cURL remain explicitly absent when not recorded. Delta
   has no recorded CVSS score. Claim a fix as `FIXED_PENDING_RETEST`; false-positive
   and accepted-risk decisions need a reason of at least 8 characters.
6. In Reports, use the actual batch ID from the run to create a frozen report.
   Preview HTML and download JSON/PDF. The snapshot and each exported file have
   hashes. A later retest must not alter that existing report.
7. Run `tests_pilot/data/sbom_fixed.cdx.json` on the same asset. Alpha, beta and
   gamma become `RESOLVED` only after comparable successful evaluation. Delta is
   omitted from this input and stays open with `changed_scope`, not resolved.
   The finding Recheck button queues the same defensive control with the latest
   supplied artifact. Finding IDs remain stable; normalized output stays immutable.
8. In Schedules, create a daily schedule with only SBOM selected. Daily slots align
   to 00:00 UTC / 07:00 Asia/Ho_Chi_Minh. Existing schedules retain their interval,
   including 120 minutes. The selection is a fixed eligible asset list; SBOM uses
   the latest supplied artifact. Pause the lab schedule after acceptance.
9. In Engine Runs, disable the advisory with a reason, run again, and inspect the
   named unavailable result. Existing findings must keep their lifecycle states.
   Reactivate the reviewed version when finished. Selecting an earlier compatible
   version provides rollback; already stored outputs/reports are not rewritten.

## Evidence and limits

The 2026-11-17 acceptance instance contains one UI-created asset, actual queued
executions and reports; findings were produced by the engine, not manually seeded.
Local artifacts live in `storage/assessment-lab/evidence/`. See the current
[workflow audit](audit/ASSESSMENT_WORKFLOW_2026-11-17.md) and
[validation manifest](audit/ASSESSMENT_WORKFLOW_VALIDATION.json).

The lab does not exercise customer authentication, live Empire web/API flaws,
native Nuclei/ZAP/Trivy, container/app/server scanning, external deployment or
production recovery. No customer scan is needed for this software acceptance.
The public-web control remains a limited HEAD/TLS/header observation, not a
comprehensive application assessment. Read the approved inventory and exact
origin/path/port policy before enabling any customer execution.

To review rollback, inspect the Git diff before applying it elsewhere. These
changes add no persisted schema column or data migration; artifact eligibility is
derived at response time. Preserve existing databases and frozen report files.
Stopping this lab is the runtime rollback and does not delete its evidence.
