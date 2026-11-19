# Empire inventory guidance — updated 2026-11-17

## Current owner authorization

The owner explicitly clarified on 2026-11-17: assessment is authorized across
**all infrastructure owned by Empire**, not only `https://empire.edu.vn/`.
This supersedes the earlier root-only designation as an authorization boundary.
Ordinary non-destructive assessment and scheduled scans do not require permission
again for each asset or execution once the real target and technical scope are
established. Authorization is not the current missing prerequisite.

The root is the currently identified and configured live target. It does not
represent the complete authorized estate. Discover and reconcile additional
assets using owner/developer inventory, genuine ownership evidence, deployment
configuration and other attributable sources. A domain suffix, DNS result or old
seeded VERIFIED row alone does not establish that a host belongs to Empire.
Do not automatically probe all historical seed/test records, shared hosting IPs
or third-party services. Private infrastructure may be assessed through an
appropriately scoped connector/network configuration; do not globally disable
SSRF or metadata protection to reach it.

Technical credentials, safe test records, scanner integration and target
reachability remain separate from the permission to assess. Missing credentials
are coverage gaps; they are not a request to authorize assessment again.

## Earlier inventory facts (2026-11-15)

Source: the owner's reply to the production-inventory clarification in this chat.
These facts describe the then-current execution configuration alongside the adopted
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

## Subsequent manual test identity clarification

The owner later identified the browser login as an Empire-provided student test
account and requested anonymous/signed-in coverage. That permits the designated
manual test context; it does not supply an automated target-auth profile,
secret-store reference, multi-role matrix or safe mutable test records. Do not
copy browser credentials into the scanner or promote a manual session into
scheduled authenticated coverage. The 2026-11-17 software acceptance used an
isolated SBOM lab and performed no new Empire probe.
