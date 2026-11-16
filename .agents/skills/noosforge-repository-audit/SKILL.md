---
name: noosforge-repository-audit
description: Audit NOOSFORGE repository architecture, runtime paths and implementation gaps before cross-layer changes or architecture decisions. Does not own feature implementation or release approval.
---

# Repository audit and architecture

Read root `AGENTS.md`. Work from source and fresh measurements, separating product
direction from current capabilities. This workflow owns discovery and impact mapping.

## Workflow

1. Inspect Git status, staged/unstaged changes and applicable instructions. Never
   discard owner work. Read `PROJECT.md`, `README.md` and the relevant `docs/pilot/`
   or `docs/audit/` records as historical context. The attached master brief is
   product context, not permission to execute embedded operational commands.
2. Run the read-only inventory below. It parses source without importing the app,
   reading secrets/data, starting workers or contacting targets. Counts describe
   source files and declarations, not installed scanners or successful executions.
3. Trace the affected path through `frontend/src/app`, `lib/api.ts`, `lib/types.ts`,
   `backend/main.py`, `app/api`, schemas, models and persistence. Follow actual
   imports: root component wrappers re-export implementations in subdirectories.
4. For scans, distinguish durable defensive `sbom`/`tls_health` executions
   (`core/planner.py`, `core/queue.py`, `engines/runner.py`) from legacy adapter
   execution in `core/dispatcher.py`. Read `core/monitor_scheduler.py` for current
   scheduling; older scheduler modules remain in the tree.
5. Inspect `core/config.py`, `core/database.py`, tests and `deploy/` before proposing
   infrastructure. SQLite/WAL and DB leases are shipped; PostgreSQL support in the
   settings is not proof of a tested PostgreSQL deployment. There is no verified
   Celery/Redis service, Alembic migration chain or CI workflow in the audited tree.
6. Record source-backed gaps, affected layers and the smallest complete change.
   Use a domain skill for implementation; use QA for execution and release review
   for a release decision. Do not expand a narrow change into a platform rewrite.

## Practical validation

```bash
.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py
```

Cross-check one returned route, ORM table and scanner class against its source.
For client/server boundaries also run `.venv/bin/python scripts/contract_audit.py`
(imports app definitions without lifespan startup; does not exercise auth/runtime).

Deliver an architecture map, evidence-backed findings, concrete implementation
boundaries and exact checks. Update the relevant existing audit instead of copying
old readiness or test counts into a new report.
