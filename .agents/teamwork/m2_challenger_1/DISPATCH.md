## 2026-11-10T21:52:50Z
You are m2_challenger_1, an adversarial testing and verification agent for Milestone 2 (Durable Queue, Scheduling & Eventing).

## Working Directory
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_challenger_1\
All metadata, analysis, and handoff files you create MUST reside in this directory.

## Mission
Empirically stress-test the Queue Persistence, Worker Leases, Split-Brain Fencing, and Overrun Coalescing subsystems implemented in Milestone 2.

## Mandatory Files to Read First
1. c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md
3. c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_worker\handoff.md

## Empirical Stress-Testing Requirements
Author an adversarial challenge test suite (e.g. `tests/test_m2_challenger1_queue_stress.py`) and execute it against the codebase. Your tests must rigorously stress:
1. **Split-Brain Zombie Worker Protection**:
   - Worker A claims job J (fencing_token = 1). Worker A pauses.
   - Lease expires. Lease reaper reclaims job J (fencing_token = 2).
   - Worker B claims job J (fencing_token = 2) and finishes successfully.
   - Worker A wakes up and attempts to complete job J presenting fencing_token = 1.
   - Assert: Worker A's write is strictly rejected (raises exception or returns False), leaving Worker B's completion intact without database corruption.
2. **Concurrent Multi-Worker Claim Race**:
   - 5 concurrent workers simultaneously attempt to claim a single queued job.
   - Assert: Exactly ONE worker succeeds; the other 4 receive None. No double claims, no deadlocks.
3. **Lease Heartbeat Renewal**:
   - Worker claims a job with a 5-second lease.
   - Worker periodically renews heartbeat before lease expiration.
   - Assert: Lease reaper does NOT pre-empt the job as long as heartbeats are renewed within lease window.
4. **Overrun Coalescing under Multi-Hour Overrun**:
   - Create an active scheduled scan batch. Simulate 3 consecutive missed hourly slots.
   - Assert: `missed_slots_count == 3` and `pending_followup == True`.
   - When the active batch finishes, trigger the scheduler loop.
   - Assert: Exactly ONE follow-up batch is dispatched (coalescing the 3 missed slots into at most 1 follow-up batch, NOT 3 separate stampede batches).
5. **Bounded Exponential Backoff Retries**:
   - Worker reports transient failure on a job with `max_retries = 3`.
   - Verify job is rescheduled with exponential backoff delay (`available_at` in the future).
   - Fail it 3 times; verify after the 3rd failure it is transitioned to terminal `FAILED` status and no longer claimed.

## Verification
Run your new stress suite and existing M1/M2 suites:
`python -m pytest tests/test_m2_challenger1_queue_stress.py -v`
`python -m pytest tests/test_milestone_b_queue_and_scheduler.py -v`

## Deliverable
Write your report to `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_challenger_1\handoff.md` with:
- Observation (test results, execution outputs)
- Logic Chain (stress scenarios tested, empirical verification of safety guarantees)
- Defect Report (if any defect found) or Confirmation of Robustness
- Clear verdict: APPROVE or DEFECT_FOUND
Then send a completion message with your verdict and report path back to the orchestrator.
