---
name: noosforge-security-scanners
description: Review NOOSFORGE threat boundaries and integrate scanner adapters or defensive engines with authorized Empire production scope, approved target identities, SSRF, process safety and evidence controls. Excludes routine UI and operations work.
---

# Security engineering and scanner integration

Read root `AGENTS.md` and, before changing target execution,
[the boundary reference](references/boundaries.md). Own threat modeling, scanner
policy and adapter integration; backend owns general queue/API implementation.

## Workflow

1. Classify the path: platform session authorization, uploaded artifact analysis,
   approved `tls_health`, legacy adapter, or legacy checklist harness. Identify each
   network client/subprocess and all credentials it could inherit. Do not execute
   a target scan merely to discover its behavior.
2. Read `api/deps.py`, `core/scope_gate.py`, `core/ssrf.py`, `core/target_verifier.py`
   and the actual caller. Require approved origin/ports/checks/expiry and budgets
   at dispatch and execution. Verify redirects and resolved addresses at connection
   time; existence of a preflight helper alone does not establish safe egress.
3. For adapters use `scanners/base.py` request/result types and fingerprint helper.
   Inspect `nuclei.py`, `zap.py`, `trivy.py`, `lab_runners.py` and dispatch wiring.
   Distinguish native CLI, daemon and embedded lab modes; verify binary availability
   locally without probing targets. Missing tools or lab fallback must not be
   advertised as verified native scanner coverage. Safe production template selection needs actual review; broad tags such as
   `cve,exposure` are not a reviewed production allowlist.
4. Preserve structured argv, non-root execution, process group registration,
   resource/time/output bounds and cleanup in `core/process_safety.py`. Verify
   cooperative and process-tree cancellation. Do not fetch/update scanner rules or
   intelligence feeds during an offline integration test.
5. For defensive engines follow `engines/runner.py` registry, `sbom.py`,
   `advisories.py`, `versions.py`, `tls_health.py` and `api/engines.py`. Preserve
   approved endpoint proof, immutable artifact/output hashes, snapshot digest,
   unavailable states, lease fencing and sanitized evidence.
6. Verify positive and negative boundaries with synthetic fixtures: platform credentials absent from target requests; target credentials bound to
   approved origin/role/test objects; auth challenges and missing identities become
   per-check coverage gaps; private/metadata and cross-origin redirects blocked, cancellation,
   missing binary, invalid artifact, redaction and no false resolution. Use mocks
   or local TLS/HTTP services; no real learner accounts. Local tests are not production assessment evidence.

## Practical validation

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py security
```

This exercises pilot identity/CSRF/Access, egress and SBOM driver tests; it does not
certify all legacy adapters as production-safe. Add focused regression cases for the
actual changed adapter; the audit records known legacy gaps. Deliver a concrete
threat boundary, implemented controls and verified limitations, with minimal
sanitized evidence and honest coverage.
