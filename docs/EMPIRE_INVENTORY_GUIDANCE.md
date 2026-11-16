# Empire inventory guidance — 2026-11-15

Source: the owner's reply to the production-inventory clarification in this chat.
This guidance narrows current execution configuration alongside the adopted
[operations brief](EMPIRE_PRODUCTION_AUTHORIZED_OPERATIONS.md). It is not a new
request for authorization.

- There is no separately designated authoritative production inventory, approved
  customer health-endpoint manifest or target-auth profile registry.
- `noospire.db` is the existing application database. Its 399 entries include
  seeded/test assets; stored rows and VERIFIED flags do not constitute approval.
- `https://empire.edu.vn/` is the explicitly designated primary target.
- Inspect repository/configuration/deployment files and database provenance for
  existing inventory sources. CSV, JSON and OpenAPI ingestion capabilities do not
  establish an authoritative inventory by themselves.
- No approved target secret-store path/reference, test accounts or test-object
  records have been supplied. Do not invent references, expose secrets or assume
  credentials exist.
- Do not assume `/health`, `/healthz` or other paths are approved Empire health
  checks without verifying purpose and ownership.
- Current automated checks follow the configured unauthenticated scanning policy.
  Exclude checks requiring customer authentication when no approved profile exists;
  do not generate fabricated AUTH_REQUIRED findings.
- Do not promote seeded/test assets into production inventory.
- Standing authorization remains in effect for the designated Empire assessment
  scope; do not repeatedly request confirmation.

The requested reconciliation covers production, seeded/test and unknown assets;
existing health endpoints and non-secret credential references; missing
configuration and required owner inputs. Results and implementation evidence:
[production reconciliation](audit/EMPIRE_PRODUCTION_RECONCILIATION.md).
