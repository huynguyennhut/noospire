---
name: noosforge-qa
description: Reproduce NOOSFORGE bugs and execute isolated API, worker, security, frontend and local-stack checks with truthful evidence. Owns verification and regression testing, not feature design or release approval.
---

# QA and autonomous testing

Read root `AGENTS.md`. Own reproducible checks and their evidence. Inspect fixtures
and scripts before execution; a filename containing “test” is not an isolation guarantee.

## Choose safe coverage

- `pytest.ini` defaults to `tests_pilot`. Its conftest sets a temporary SQLite DB
  and storage before importing settings and disables in-process workers.
- `tests/conftest.py` instead seeds the configured DB, elevates a known user, turns
  on private targets, and deletes files in repository `storage/reports` even if
  storage is configured elsewhere. Do not run that suite in a normal checkout.
  For required legacy coverage, use a disposable copy with synthetic data and
  inspect each selected test for external targets and startup side effects.
- One pilot test, `test_legacy_database_upgrades_in_place_and_backup_restores`,
  copies the repository DB. The runner below deselects it; use synthetic schema
  fixtures for migration tests instead of copying customer data.
- `scripts/qa/setup_test_environment.sh` mutates users/shared DB. Browser/live and
  seed scripts often use hardcoded ports, credentials, artifacts or customer URLs.
  They are not default QA entry points. Inspect and adapt before isolated use.

## Execution

Run from the repository root with installed dependencies:

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
```

Focused presets: `backend`, `security`, `devops`, `contract`. `pilot` includes
loopback subprocess/TLS tests; it does not require Docker or native scanner binaries.
The runner sanitizes inherited application settings, disables plugin autoload except
pytest-asyncio, sets temporary data/storage, records commands and genuine exit codes,
and never accepts arbitrary shell commands or legacy test paths. It is an isolation
aid for these inspected presets, not an OS network sandbox. Reinspect tests after
changes; use host network containment when validating unfamiliar scanner code.

Choose focused coverage for a narrow change. For a cross-layer change run the full
pilot preset plus frontend and contract checks. Add behavioral regressions where
needed; do not add tests that merely assert documentation headings or copied logic.
Read the JUnit details on failure and distinguish pre-existing defects from changes.

For UI changes, separately use a synthetic local stack, browser console/network
inspection and hydrated screenshots across both themes and relevant viewports.
Compile/build success does not establish visual or accessibility quality.

## Evidence

The runner prints an artifact directory containing `results.json`, per-command logs
and JUnit XML for pytest presets. Record PASS/FAIL/SKIPPED/BLOCKED honestly, including
deselections and environment blockers. Fix regressions caused by the change and
rerun affected checks; report unrelated failures without weakening assertions.
