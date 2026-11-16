# NOOSFORGE project skills

The seven skills in [`.agents/skills/`](../.agents/skills/) support the existing
project. [AGENTS.md](../AGENTS.md) holds shared policy; specialized instructions
live in each skill. The library uses the repository discovery location documented
by [OpenAI](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills).
Each skill has YAML `name`/`description`, instructions and `agents/openai.yaml`
display metadata. Implicit selection stays enabled; no plugin, remote service,
global install, symlink or account connection is required.

Open Codex in this repository or a subdirectory. Explicitly mention `$skill-name`
in a prompt, or describe the matching task for automatic selection. Codex discovers
skill changes automatically; if the selector is stale, restart Codex. This session
validated discovery with the installed Codex app-server's native `skills/list`
from the root, `frontend/` and `backend/` (seven enabled skills in each), in addition
to filesystem checks. The desktop selector UI was not inspected. `/skills` or
`$` in Codex CLI/IDE can be used to inspect the available skills.

## Invocation and ownership

| Skill | Example prompt | Owns / boundary |
| --- | --- | --- |
| [noosforge-repository-audit](../.agents/skills/noosforge-repository-audit/SKILL.md) | `$noosforge-repository-audit Trace a scan from UI to persisted findings and list source-backed gaps.` | Architecture and impact mapping; hands implementation to the relevant domain. |
| [noosforge-frontend](../.agents/skills/noosforge-frontend/SKILL.md) | `$noosforge-frontend Improve the findings drawer using existing tokens; check both themes and mobile.` | UI/components/client behavior; server permission policy stays backend/security. |
| [noosforge-backend](../.agents/skills/noosforge-backend/SKILL.md) | `$noosforge-backend Fix the requested execution lifecycle bug and add an isolated API regression.` | API, DB, queue, scheduler and finding lifecycle; scanner-specific policy stays security. |
| [noosforge-security-scanners](../.agents/skills/noosforge-security-scanners/SKILL.md) | `$noosforge-security-scanners Audit authorized scope, target identity binding and egress using local fixtures.` | Threat boundaries and adapters; skill activation does not expand the owner's assessment scope. |
| [noosforge-qa](../.agents/skills/noosforge-qa/SKILL.md) | `$noosforge-qa Run the isolated pilot checks and frontend build; report failures and skipped coverage.` | Reproduction, test execution and evidence; does not decide release readiness. |
| [noosforge-devops](../.agents/skills/noosforge-devops/SKILL.md) | `$noosforge-devops Verify gateway packaging and synthetic SQLite backup recovery without deploying.` | Packaging/operations/recovery; production changes still need authorization. |
| [noosforge-release-review](../.agents/skills/noosforge-release-review/SKILL.md) | `$noosforge-release-review Review this diff and evidence; give a scoped ready/hold decision.` | Review and release assessment; does not deploy or rewrite the implementation. |

Use more than one skill only when a task crosses those boundaries. Ordinary
domain-specific verification stays with the implementation skill; QA owns the
broader reproducible verification workflow. Skill activation is not permission for
destructive operations or external changes. Shared authorized-production scope and safety policy applies to all.

## Working helpers

Run commands from the repository root with installed dependencies. The inspected
Linux environment provides `.venv/bin/python` and Node 20. For another OS use its
equivalent project interpreter. The validator uses existing PyYAML; no new package
is introduced. Frontend commands use `frontend/package-lock.json` and installed npm
dependencies. No helper installs packages, changes production or starts scanners.

```bash
# Source inventory: no application imports, runtime data or network
.venv/bin/python .agents/skills/noosforge-repository-audit/scripts/inventory.py

# YAML/discovery structure, links, script syntax and invocation routing
.venv/bin/python .agents/skills/noosforge-release-review/scripts/validate_skills.py

# Full synthetic pilot suite; excludes the test that copies the repository DB
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py pilot

# Lifecycle unit checks, npm typecheck, lint and static export build
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend

# OpenAPI/client source contract audit, without startup or --write
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py contract
```

Focused runner presets:

| Preset | Checks |
| --- | --- |
| `backend` | Pilot identity/scope, inventory/fixture dispatch, root-observer isolation, verified rechecks, SBOM flow and console lifecycle |
| `security` | Pilot identity/CSRF/access, inventory/fixture dispatch, root-observer isolation, diagnostics, SBOM drivers, TLS/egress and API/Access contract |
| `devops` | Loopback gateway, restart persistence, smoke; fresh synthetic schema, SQLite backup and restore-check |

The runner writes `results.json`, logs and JUnit XML to a printed temporary
directory. Its exit code is nonzero if a command fails or a required executable is
missing. A failing baseline is reported, never changed into a pass. The runner is
not a network sandbox; inspect changed tests before reuse. Browser visual QA,
native scanner execution, Docker builds and external deployments are separate
checks and are never inferred from these results.

Do not use legacy `pytest tests`, QA setup/seed or live scan scripts directly on
the working checkout. See the QA skill for observed data/credential side effects.
For production operations use approved scope and review the exact target config.

## Maintenance and acceptance

Update the owning skill when entrypoints, interfaces or test behavior change.
Keep names unique and folders named after their frontmatter `name`. Keep
descriptions focused enough to select one primary workflow. Link optional
references from `SKILL.md`; add scripts only for repeated deterministic work.
No generic templates or scaffold resources are included in this library.

Run the library validator after every skill edit. For a workflow change, perform
a realistic task using the referenced current code/commands and record actual
outcomes. Structural validation cannot prove automatic model selection or host
refresh. Current architecture, practical checks for every skill are recorded in [the Skills installation audit](audit/AGENT_SKILLS_AUDIT.md).
The subsequent runtime fixes and remaining gaps are in
[the current project audit](audit/PROJECT_CURRENT_STATE.md).
The adopted Empire authorization and current inventory limitations are recorded in
[the production reconciliation](audit/EMPIRE_PRODUCTION_RECONCILIATION.md).
