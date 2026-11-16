# Implementation status — 2026-11-15

The product direction is a self-hosted security intelligence platform with scoped,
authorized production assessment, honest evidence and a premium dual-theme console.
The shipped Next.js/FastAPI/SQLAlchemy/SQLite durable-queue architecture is retained.
The adopted Empire brief permits approved target identities when provisioned.
Current owner guidance designates the primary root only and supplies no approved
auth profiles or customer health manifest; current automation stays unauthenticated.

| Priority | Slice | Status and evidence |
| --- | --- | --- |
| P0 | Project Skills library and source-backed architecture map | Implemented; seven discoverable skills, validator and isolated QA runner. See `docs/AGENT_SKILLS.md`. |
| P1 | Stored-hash login, token-gated bootstrap and immutable owner/asset grants | Implemented; access regression suite covers all eight roles, legacy flags, concurrent bootstrap and unauthorized operations before egress. |
| P1 | Asset/checklist authorization and obsolete scheduler retirement | Implemented; registry/baseline administration owner-only, checklist READ/SCAN/TRIAGE enforced, old scheduler endpoints return 410 without dispatch. |
| P1 | Durable recheck and canonical verified resolution | Implemented; active/pending/legacy claimed fixes stay open until equivalent successful evidence; manual resolution rejected; board/filters/audit/metrics/reports agree. |
| P1 | Measured diagnostics and honest health/settings UI | Implemented; worker/input-derived status, synthetic self-test outcomes, unknown upstream versions and semantic text colors. |
| P1 | Reconcile production inventory and prevent fixture promotion | Implemented read-only CLI/owner API, provenance report and dispatch/worker guards. Ultra fixture/empty-inventory dispatch no longer creates VERIFIED production assets. Root-only HEAD evidence is separately recorded. Full estate remains incomplete. |
| P1 | Production safety across legacy scan/checklist entrypoints | Remaining implementation. Real origin/port/path binding, reviewed templates, budgets, telemetry stops and provisioned identity/test-object controls must reach every outbound client. Legacy synthetic credentials, brute-force probes and unsafe redirects remain unsuitable for production. |
| P2 | Full role-specific workflows and grant-aware legacy API review | Remaining implementation. Current protections cover the audited asset/checklist/defensive flow, not a complete multi-tenant security certification. |
| P2 | Complete console accessibility, theme contrast and server pagination | Remaining implementation. Changed diagnostics/finding screens were exercised in both themes; shared shell/legacy badges and list loading beyond the existing 100-record API request need further work. No WCAG certification is claimed. |
| P2 | Synthetic migration fixture replacing the real-DB-copy pilot case | Remaining implementation. That one test stays deselected; schema/backup/recovery tests run on synthetic data. |
| P3 | Self-hosted production acceptance | Blocked by missing Docker/native scanner binaries and external deployment authorization/infrastructure. PostgreSQL, image builds, egress containment and production backup/restore are unverified. |

Current commands/results, compatibility notes and operational limits:
[repository state and remediation audit](audit/PROJECT_CURRENT_STATE.md).
Current inventory, executed production observation and requirement gaps:
[Empire production reconciliation](audit/EMPIRE_PRODUCTION_RECONCILIATION.md).
The next engineering slice is safe outbound policy across legacy adapters, verified
with local fixtures. Broad production execution also needs the authoritative asset
manifest, approved health checks and test-identity configuration where applicable.
