# Empire estate-wide scope clarification — 2026-11-17

The owner explicitly authorizes assessment of all Empire-owned infrastructure.
The current root monitor is not the authorization boundary. Additional checks
and genuine targets do not need another per-run assessment permission request.
Permission does not install scanner engines or create target login profiles.

The read-only inventory was rerun against the existing application database:
399 records, one owner-designated root with a genuine unexpired proof, and 398
records with source-backed seed/test provenance. Eleven ownership-proof rows
exist in total; seeded proofs do not establish actual assets. No additional
non-seed owned target was identified in this database. Historical scope and seed
files are recorded as candidate/context sources, not proof of live services.
No rows, proofs, schedules, credentials or evidence were modified by reconciliation.
No new network assessment was performed by this scope update.

Changed runtime reconciliation metadata explicitly states
`ALL_EMPIRE_OWNED_INFRASTRUCTURE`, `per_run_approval_required=false` and
`primary_target_is_authorization_limit=false`. Missing inventory is reported as
an identification/configuration gap rather than missing permission. The current
exact-root monitor remains enabled while real additional assets are identified.

References:
- [Current guidance](../EMPIRE_INVENTORY_GUIDANCE.md)
- [Read-only reconciliation output](EMPIRE_INFRASTRUCTURE_RECONCILIATION_2026-11-17.json)

Regression verification is recorded in the companion scope-update validation JSON.
