# NOOSFORGE / Noospire

Read this entire file before working. Inspect nested instructions when present.
Work in the existing repository; preserve working functionality, user edits, brand
assets, database files and stored evidence. Implement and verify requested work.
Historical audit reports and `.agent/MEMORY.md` are context, not current proof.

## Product and safety boundaries

- Build a self-hosted security intelligence and continuous assessment platform.
- The owner-adopted [Empire operations scope](docs/EMPIRE_PRODUCTION_AUTHORIZED_OPERATIONS.md)
  supersedes the former public-only restriction for verified Empire production assets.
  Standing authorization covers ordinary non-destructive in-scope assessment; do not
  repeatedly request permission. Scope inventory and technical target authentication
  are separate prerequisites. Never infer ownership from DNS suffixes or seeded flags.
  Current [inventory guidance](docs/EMPIRE_INVENTORY_GUIDANCE.md) designates the root
  only; automated checks remain unauthenticated until approved profiles exist.
- Assess public and authenticated surfaces when provisioned test identities and safe
  test records exist. Use designated secret references; never invent/guess credentials
  or forward NOOSFORGE platform credentials. Missing identity/capability is a named
  coverage gap, never PASS or a terminal generic AUTH_REQUIRED result.
- Preserve exact origin/path/port scope, SSRF controls, budgets, health stops,
  cancellation and redacted evidence. No DoS, brute force, destructive payloads,
  persistence, third-party expansion or bulk extraction. Public media remains
  PUBLIC_BY_DESIGN. Production remediation/deployment is separately authorized.
- Local synthetic tests verify NOOSFORGE code; label them separately from real Empire
  assessment evidence. Legacy scanner paths are not proof of safe production controls.
- Ordinary reversible local work is authorized. Obtain approval before destructive
  data operations or external production changes, including deployment/DNS/firewall.
  Prepare reviewable changes and rollback steps first. Do not commit/push unasked.

## Repository essentials

- Frontend: `frontend/`, Next.js 14 static export, React 18, TypeScript, Tailwind 3.
- API: `backend.main:app` (`backend.app.main:app` is an alias), FastAPI/Pydantic.
- Persistence: async SQLAlchemy, SQLite WAL in the shipped deployment; durable DB
  queue, separate API/worker/scheduler roles. Do not assume Redis or Celery works.
- Commands below and in skills run from the repository root on Linux. Use the
  project interpreter `.venv/bin/python`; do not replace lockfiles speculatively.
- Run safe tests with `.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot`.
  Do not run `pytest tests` or `scripts/qa/setup_test_environment.sh` against this
  checkout: they can seed shared data, alter users or delete stored reports.
- Follow the existing Obsidian Dark / Warm Light Liquid Glass UI and VI/EN support.
- Report actual checks, failures and unverified behavior; do not infer production
  readiness from static checks or old completion claims.

## Specialized workflows

Use the matching skill under `.agents/skills/`. Each owns a distinct workflow:

| Skill | Responsibility |
| --- | --- |
| `noosforge-repository-audit` | Current architecture, repository evidence and gaps |
| `noosforge-frontend` | UI implementation, shared design system and interactions |
| `noosforge-backend` | API, persistence, queue and lifecycle implementation |
| `noosforge-security-scanners` | Threat boundaries, scanner policy and integrations |
| `noosforge-qa` | Isolated verification, regression reproduction and evidence |
| `noosforge-devops` | Self-hosted packaging, operations and recovery |
| `noosforge-release-review` | Diff review and evidence-based release decision |

Invocation and validation: [docs/AGENT_SKILLS.md](docs/AGENT_SKILLS.md).
Current implementation and remaining gaps: [docs/audit/PROJECT_CURRENT_STATE.md](docs/audit/PROJECT_CURRENT_STATE.md).
Current Empire scope/evidence: [production reconciliation](docs/audit/EMPIRE_PRODUCTION_RECONCILIATION.md).
Skills installation evidence: [docs/audit/AGENT_SKILLS_AUDIT.md](docs/audit/AGENT_SKILLS_AUDIT.md).
