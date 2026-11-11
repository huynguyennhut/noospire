# Dispatch: E2E Testing Orchestrator (Dual Track)

## Objective
You are the E2E Testing Track Orchestrator for Noospire (assessing Empire education platform).
Your task is to independently design and implement a comprehensive, requirement-driven, opaque-box E2E test suite covering Features F01–F48 from `PROJECT.md` and user requirements in `ORIGINAL_REQUEST.md`.

## Working Directory
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\e2e_testing_orchestrator\`

## Reference Documents
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (authoritative)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\PROJECT.md` (Feature Inventory, Architecture, Contracts)

## Requirements & Methodology
1. Create `c:\Users\nguye\Desktop\noospire\TEST_INFRA.md` documenting test philosophy, test architecture, runner commands, and coverage thresholds.
2. Design and implement 4-Tier test cases:
   - Tier 1: Feature Coverage (>=5 test cases per feature across student access, learning records, public/private materials, login defense, control plane, workers, reports).
   - Tier 2: Boundary & Corner Cases (>=5 per feature: empty inputs, limits, overflows, negative values).
   - Tier 3: Cross-Feature Combinations (pairwise interactions: schedule + worker + finding + report).
   - Tier 4: Real-World Scenarios (>=5 realistic end-to-end workflows: synthetic students, verified asset, daily schedule, report download).
3. Implement tests in `tests/e2e/` or dedicated test files.
4. Verify tests execute cleanly against local synthetic staging fixtures with zero external network egress.
5. Publish `c:\Users\nguye\Desktop\noospire\TEST_READY.md` summarizing coverage when complete.

## Output
Write progress and handoff to your working directory and notify the parent orchestrator via `send_message`.
