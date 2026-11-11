# Orchestrator Execution Plan: NOOSFORGE Security Intelligence

## Target Objective
Build a production-oriented, UI-first security assessment and continuous monitoring platform (NOOSFORGE Security Intelligence) for Empire Education Platform (`https://empire.edu.vn/`), integrating real scanners, verifiable evidence, and a Next.js 14 Black/White/Liquid Glass command center.

## Phase Breakdown
### Phase 0: Survey & Codebase Reconnaissance
- Dispatch 3 Explorers in parallel:
  - `explorer_1`: Backend architecture, target models, database schemas, FastAPI API contracts, `scripts/verify_empire_e2e.py`.
  - `explorer_2`: Security scanner integration layer (ProjectDiscovery, ZAP, httpx, nuclei), process runners, evidence logging, quality states.
  - `explorer_3`: Frontend Next.js 14 App Router, existing components, 14 navigation views, Liquid Glass theme, bilingual i18n support.
- Synthesize reports into `PROJECT.md` at root.

### Phase 1: Implementation & Parallel Tracks
- AGENT 1 (Platform Core): Target Management, 8-step live verification pipeline, URL normalization, bulk import preview, persistence.
- AGENT 2 (Scanning & Intelligence): Real scanner engine, execution records, raw HTTP evidence storage, Empire module taxonomy, finding deduplication & remediation.
- AGENT 3 (UI & Product Experience): Next.js 14 frontend, 14 views, Vietnamese/English i18n, evidence viewer, real-time scan monitoring.
- E2E Testing Track: Requirements-driven test suite validating all R1-R5 requirements.

### Phase 2: Verification, Challenging & Forensic Audit
- Reviewers verify code quality and interface conformance.
- Challengers execute stress tests and boundary edge cases.
- Forensic Auditor performs integrity verification.

### Phase 3: Final Acceptance & Baseline Scan Execution
- Run `scripts/verify_empire_e2e.py` (ensure 10/10 tests pass).
- Execute real baseline assessment against `https://empire.edu.vn/`.
- Present final report to user/parent.
