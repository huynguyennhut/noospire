# Implementation decisions

## 2026-11-15 — Adopt authorized production scope without trusting seeded inventory

The owner adopted the Empire production operations brief and then clarified that
only the primary root is designated, with no authoritative full estate manifest,
approved target identities, customer health endpoints or secret-store references.
Assessment permission remains standing; current automation stays unauthenticated
until the required configuration exists.

Decision: retain exact-scope/SSRF/secret/process protections, classify stored rows
from source provenance, reject known fixtures and seed-only ownership at execution
boundaries, and stop Ultra Scan from inventing VERIFIED production assets. Preserve
stored history and read-only fixture previews. Keep a bounded root HEAD observation
separate from broad vulnerability assessment and synthetic software regressions.
Current evidence and remaining brief requirements are in
[the production reconciliation](audit/EMPIRE_PRODUCTION_RECONCILIATION.md).

## 2026-11-15 — Restore the configured-owner and asset-grant boundary

Observed: login accepted two fixed test passwords independently of stored hashes
outside production; role/superuser flags bypassed asset grants; HTTP bootstrap was
open without an operator token in development/test. Existing pilot contracts and
`api/deps.py` explicitly describe a unique configured owner plus per-asset grants.

Decision: verify the stored password in every environment. Require explicit
bootstrap opt-in/token in every environment, use conflict responses for repeated
or racing bootstrap, and issue new JWT subjects using immutable user IDs. Retain
legacy token lookup compatibility. Estate-wide scope and global administration
require the configured owner identity. Roles remain useful for action gates, while
every non-owner needs asset grants. Asset registry/baseline policy administration
has no management grant in this schema and therefore remains owner-only.

Existing owner IDs, password hashes, users, grants and stored evidence are not
rewritten. Accounts that relied on an authentication bypass must use their actual
stored password. No password reset or service restart is performed by this change.

## 2026-11-15 — Retire the obsolete scheduler API without deleting data

Observed: the current worker/scheduler uses monitor schedules and fenced execution
records, while old `/schedules` handlers still read estate data and launch legacy
jobs. Frontend scheduling already uses `/monitor-schedules`; existing pilot tests
expect the legacy API to be retired.

Decision: keep all seven legacy method/path combinations as explicit HTTP 410
responses with replacement guidance. They perform no DB reads/writes or dispatch.
Do not delete historical schedule rows or change active monitor schedules.

## 2026-11-15 — Distinguish claimed fixes from verified resolution

Observed: persisted `FIXED` was serialized as canonical `FIXED_PENDING_RETEST`;
canonical in-progress/assigned findings were omitted from some open-state queries.
The legacy retest URL inferred remediation from HTTP status instead of executing
the producing control.

Decision: keep the ten canonical states and legacy input aliases. Human claims of
a fix remain `FIXED_PENDING_RETEST` and count as open. Only successful comparable
engine evidence can write `RESOLVED`; manual triage cannot create verified
resolution (409). Existing resolved findings can still be assigned or annotated. Rediscovery reopens resolved
or pending-retest findings. Both `/recheck` and `/retest` use the same durable,
idempotent execution flow. Failed/missing/changed-scope evaluation cannot resolve a
finding. Share open/resolved classifications across API metrics and pilot reports.

Historical raw `FIXED` rows follow the existing API alias: pending retest, not
verified resolution. Their original values and evidence stay on disk; metrics,
filters and the board agree until a new comparable recheck resolves or reopens them.

New report snapshots record template version `noospire-pilot-report/1.1` for the
corrected lifecycle summaries; existing snapshots and their rendered bytes remain
immutable. Pilot assertions were updated to strict canonical states, not relaxed
to accept multiple outcomes.

The console uses all ten canonical states, keeps pending retests separate from
verified resolution, and retains visibility of dismissed/historical states. Manual
status selectors omit RESOLVED as a new transition. Legacy aliases remain accepted.

## 2026-11-15 — Diagnostics report evidence, not fixed success

Observed: engine diagnostics returned hardcoded online states, versions, current
success timestamps, passing tests and up-to-date claims. Settings repeated these
claims in a static card list.

Decision: derive readiness from registered drivers, fresh advertising worker
heartbeats, active advisory snapshot freshness and actual committed success times.
List legacy adapters as not integrated into the fenced execution flow. Self-tests
exercise real synthetic SBOM matching and pre-network TLS egress rejection, and
state that worker/network execution was not tested. Upstream versions remain
unknown unless queried; this workflow does not query or update them. Render the
same results in health/settings and preserve theme tokens and brand assets.
