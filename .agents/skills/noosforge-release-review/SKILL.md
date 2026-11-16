---
name: noosforge-release-review
description: Review NOOSFORGE changes and audit release evidence, regressions, data compatibility and operational readiness. Use for technical review or release decisions, not ordinary feature implementation or deployment execution.
---

# Technical review and release audit

Read root `AGENTS.md`. Own assessment of a concrete diff and its evidence; do not
substitute a historical “production ready” report for fresh verification.

## Review

1. Inspect status plus staged/unstaged diff and untracked deliverables. Determine
   the actual requested behavior and ownership of existing edits. Follow changed
   behavior through frontend, server, models, queue/engines, reports and deployment.
2. Check compatibility of API shapes, stored states, fresh/existing schema,
   idempotency and lease fencing. Inspect object permissions, authorized target
   scope and provisioned identity boundaries with the security skill when changed.
3. Assess functional controls, loading/errors, both themes, VI/EN, cancellation,
   report provenance and secret redaction where affected. Prioritize exploitable
   boundary errors, data loss and concrete regressions over stylistic preferences.
4. Use QA evidence appropriate to the diff. For cross-layer releases obtain
   frontend build, contract, pilot API/worker/scheduler/egress and recovery evidence.
   Record skipped browser, native scanner, Docker, PostgreSQL and external pilot
   checks separately; passing a subset cannot certify the entire platform.
5. Check deployment/secrets/backup/rollback readiness with DevOps where applicable.
   Separate “changes validated” from “platform release ready”. Stop the release
   recommendation on unresolved material security/data failures. Continue safe
   local review; release/deployment itself is a separate authorized action.

## Skill-library validation

When skills or `AGENTS.md` change, run:

```bash
.venv/bin/python .agents/skills/noosforge-release-review/scripts/validate_skills.py
git diff --check
```

The validator checks all project skills, YAML metadata, unique names, local links,
syntax of bundled Python scripts and invocation routing from AGENTS/docs. It does
not execute workflows or prove that the host has refreshed its skill selector.
Run a realistic practical task for each changed workflow and record evidence.

For client/server release evidence:

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py contract
```

Deliver actionable findings with verified file/line and impact, tests executed,
unresolved blockers and a scoped ready/hold decision. Do not silently fix unrelated
policy or product issues during review; route concrete fixes to the owning skill.
