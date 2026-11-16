---
name: noosforge-devops
description: Prepare and verify NOOSFORGE self-hosted Docker packaging, fixed-origin gateway, process roles, backup and recovery. Use for infrastructure and operational changes; external production mutations require approval.
---

# Self-hosted DevOps and infrastructure

Read root `AGENTS.md`, `deploy/README_DEPLOY.md` and relevant `docs/pilot/RUNBOOK.md`
sections. Own packaging and operations. A local build/test is not a deployment.

## Workflow

1. Inspect `deploy/docker-compose.yml`, both Dockerfiles, `.dockerignore`,
   `deploy/.env.example` and `core/config.py`. Do not print real `.env` files,
   resolved secret-bearing Compose output or tunnel credentials.
2. Preserve topology: static Next export → Python gateway → fixed API origin;
   API/worker/scheduler share SQLite `/data` and use separate process roles.
   Compose publishes only gateway `127.0.0.1:8080`; API has no host port. The
   connector network must not expose the DB/control plane to cloudflared.
3. Preserve Access signature/audience/issuer/expiry validation and fail-closed
   configuration in `deploy/gateway/access.py`. Keep gateway status/JSON error,
   cookie forwarding, timeout, cache and SSE behavior in `gateway.py`.
4. Check runtime/build assumptions: backend Dockerfile uses pinned Python 3.14,
   gateway build uses pinned Node 22; local interpreter may differ. Do not claim
   runtime parity from manifest comments. Preserve non-root users and deliberate
   image digests. Scanner binaries are not installed by the backend Dockerfile.
5. For local start, `./run.sh start` starts detached API+gateway on loopback only;
   `--enable-jobs` adds separate worker/scheduler and always restricts workers to
   durable defensive executions. Use `status`, `stop`, and `logs <role> --follow`;
   see `docs/LOCAL_OPERATIONS.md`. `--build-console` rebuilds the existing export.
   Use dedicated test database/storage/state and free ports for validation. The
   supervisor refuses occupied ports and never takes over unrelated processes.
6. For data operations use `backend.app.cli backup` (SQLite online backup) and
   `restore-check` on synthetic data first. Never copy a live WAL database with
   ordinary file copy. `restore-check` verifies a temporary restore; it does not
   perform a production restore. Prepare backup/schema/rollback compatibility
   before upgrades. PostgreSQL backup is not implemented by this CLI.
7. Prepare concrete config diffs and validation before asking for any required
   production approval. Do not independently alter DNS/firewall/tunnels, deploy,
   restart production or restore over customer data.

## Practical validation

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py devops
```

This runs loopback gateway, process restart and smoke tests with temporary data.
When Docker is available, validate `docker compose ... config --quiet` using
throwaway environment values, then build locally if requested. Never present YAML
parsing as a successful Compose/image build. For post-deploy checks inspect
`deploy/smoke.py`: without credentials its signed-in checks are skipped even though
the script counts them as pass. Report that limitation explicitly.

Deliver configuration changes, operational verification, backup/rollback evidence,
and exact external steps awaiting approval or infrastructure.
