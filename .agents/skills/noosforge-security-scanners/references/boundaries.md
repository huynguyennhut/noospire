# Authorized production execution boundaries

Use this reference when changing target network behavior or scanner dispatch.
Root `AGENTS.md` and the adopted Empire operations scope define policy. These are implementation checkpoints,
not a claim that current code already enforces every rule.

| Surface | Required behavior | Inspect |
| --- | --- | --- |
| Platform session | Login, CSRF, revocation and object permission checks remain active | `backend/app/api/deps.py`, `auth.py` |
| Customer HTTP | Approved target identities only through designated secret references, exact-origin binding and safe test records; never reuse platform credentials or real learner accounts | `scanners/empire_engine.py`, `synthetic_harness.py`, `lab_runners.py`, `crawler.py` |
| Auth challenge | Continue other checks; report exact AUTHENTICATED_COVERAGE_NOT_CONFIGURED or other per-check gaps, never generic terminal AUTH_REQUIRED | `core/dispatcher.py`, `api/checklist.py`, `schemas/common.py` |
| Scope/egress | Approved origin/ports/checks, expiry, budget, vetted IPs and redirect hops | `core/scope_gate.py`, `ssrf.py`, `target_verifier.py`, `engines/tls_health.py` |
| Local artifacts | Analyze only supplied approved artifacts; preserve hashes and path bounds | `api/engines.py`, `engines/runner.py`, `sbom.py` |
| Findings/reports | Redact evidence, respect public media baselines, expose gaps and provenance | `scanners/file_policy.py`, `core/lifecycle.py`, `reporting/`, `api/console.py` |
| Execution | Bound subprocess tree and resources; cancellation must stop work and fence stale writes | `core/process_safety.py`, `queue.py`, `engines/runner.py` |

Known audit traps: `api/checklist.py` directly calls `SyntheticTestHarness`;
`empire_engine.py` includes synthetic Authorization and login probes;
`dispatcher.py` still emits `AUTH_REQUIRED`; adapters can fall back to embedded
lab runners. Do not turn these historical behaviors into skill permissions or
describe them as production-safety certification. Fix them only within an actual scoped
implementation task and verify outbound request behavior with local fixtures.

Standing owner authorization covers ordinary scoped assessment. Ownership records,
approved profiles and provisioned target identities are distinct technical facts;
seeded flags do not establish them.
`PUBLIC_BY_DESIGN` media remains a baseline exception, not an automatic exposure
finding. Keep checklist states distinct from execution and finding lifecycle states;
do not silently rename persisted enums to match aspirational brief examples.
