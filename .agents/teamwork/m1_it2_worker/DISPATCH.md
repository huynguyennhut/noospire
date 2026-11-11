## 2026-11-10T19:55:52Z
You are M1 It2 Remediation Worker (m1_it2_worker).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_worker
Your parent is the Project Orchestrator (eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY READING (Read these files first):
1. c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
2. c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md
3. c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_explorer_1\handoff.md
4. c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_explorer_2\handoff.md
5. c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_explorer_3\handoff.md
6. c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\GATE_STATUS.md

EXCLUSIVE FILE BOUNDARIES:
You exclusively own and may edit:
- `frontend/src/lib/api.ts`
- `backend/app/api/deps.py`
- `backend/app/models/base.py`
- `backend/app/models/user.py`
- `backend/app/core/scheduler.py`
- `backend/app/intel/nvd.py`
- `backend/app/core/ssrf.py`
- `backend/app/core/target_verifier.py`
- `tests/test_m1_adversarial_challenge.py`
Do NOT edit any files outside these boundaries.

TASKS TO IMPLEMENT:
1. `frontend/src/lib/api.ts` (lines 162-166):
   Rename `const module = params;` to `const empireModule = params;` and update line 164 accordingly, exactly per `m1_it2_explorer_1/handoff.md`.
2. `backend/app/models/base.py`:
   Add `UTCDateTime(TypeDecorator)` subclassing `DateTime(timezone=True)` that normalizes `tzinfo` to `timezone.utc` in both `process_bind_param` and `process_result_value`. Update `User.tokens_valid_after` to use `UTCDateTime`.
3. `backend/app/models/user.py`:
   Import `UTCDateTime` and use it for `User.tokens_valid_after`.
4. `backend/app/api/deps.py` (lines 119-167):
   Defensively normalize both `token_issued_at` and `tokens_valid_after` to UTC timezone before comparing `token_issued_at < tokens_valid_after`, exactly per `m1_it2_explorer_2/handoff.md`.
5. `backend/app/core/scheduler.py` (lines 155-160):
   Defensively normalize `sched.next_run_at` to UTC before `if next_run <= now:`.
6. `backend/app/intel/nvd.py` (lines 244-256):
   Defensively normalize `start_date` and `end_date` to UTC in `chunk_date_range`.
7. `backend/app/core/ssrf.py`:
   - Add `ipaddress.ip_network("ff00::/8")` (IPv6 multicast), `2002::/16` (6to4), `64:ff9b:1::/48`, and `3fff::/20` to `BLOCKED_NETWORKS`.
   - Define `ALLOWED_LAB_NETWORKS` (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1/128`, `fc00::/7`).
   - In `validate_target`:
     - Add unconditional block for `str(ip_obj) in cls.CLOUD_METADATA_IPS`, `ip_obj.is_link_local`, `ip_obj.is_unspecified`, `ip_obj.is_multicast`, and `ip_obj in ipaddress.ip_network("0.0.0.0/8")`.
     - In general blocked networks check, permit lab bypass only if `allow_private and not settings.is_production and any(ip_obj in lab_net for lab_net in cls.ALLOWED_LAB_NETWORKS)`.
     - In `normalized_url`, ensure IPv6 bracket representation: `host_repr = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname`.
8. `backend/app/core/target_verifier.py`:
   In `verify_ownership_challenge` (line 711), validate `target_locator` with `SSRFProtector.validate_target(target_locator, allow_private=allow_private)` to prevent SSRF probes.
9. `tests/test_m1_adversarial_challenge.py`:
   Update `test_bug_offset_naive_datetime_comparison_in_tokens_valid_after` (lines 451-458) to assert that expired tokens now return HTTP 401 Unauthorized with "Session expired/revoked" instead of raising TypeError.
