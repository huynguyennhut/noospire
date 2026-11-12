# Handoff Report — Backend Technical Gap Analysis for NOOSFORGE Enhancement

**Agent:** Survey Explorer (`teamwork_explorer_enh_1`)  
**Working Directory:** `c:\Users\nguye\Desktop\noospire\.agents\teamwork\teamwork_explorer_enh_1\`  
**Date:** 2026-11-09T19:25:00Z  
**Recipient:** Orchestrator (`5b9071b1-5f25-4b8f-b59a-d9eaa63264da`)  

---

## 1. Observation

### Observation 1: Scan Execution, Queue & Scheduling Infrastructure
- `DailySchedule` model exists in `backend/app/models/schedule.py` (lines 11–25) with columns `id`, `name`, `profile`, `cron_expression` (`0 2 * * *`), `timezone` (`Asia/Ho_Chi_Minh`), `is_active`, `target_ids`, `last_run_at`, `next_run_at`, and `last_status`.
- `backend/app/api/schedules.py` defines `GET /api/v1/schedules`, `POST /api/v1/schedules`, `POST /api/v1/schedules/{id}/trigger`, and `PUT /api/v1/schedules/{id}/toggle`.
- **Grep search for `DailySchedule`** across `backend/` showed occurrences only in:
  - `backend/app/models/schedule.py` (line 11)
  - `backend/app/core/empire_seeder.py` (lines 16, 436, 438)
  - `backend/app/models/__init__.py` (lines 8, 26)
  - `backend/app/api/schedules.py` (lines 13, 44, 54, 73, 121)
- **FastAPI Lifespan** in `backend/main.py` (lines 32–60) starts `AsyncWorkerDispatcher` but **starts no cron runner or scheduler loop task**.
- `backend/app/api/scans.py` (lines 128–260) supports single scans (`POST /api/v1/scans`) and batch sweeps (`POST /api/v1/scans/batch`), but neither `Scan` nor `ScanBatch` possesses a `scheduled_at` field for one-time future scheduling.

### Observation 2: Log Storage, Day Tracking, Purging & State Reset
- `ScanLog` is defined in `backend/app/models/scan.py` (lines 123–138): table `scan_logs` with `id`, `scan_id` (FK to `scans.id` with `CASCADE`), `timestamp`, `level`, `message`, `source`.
- `backend/app/api/scans.py` (lines 396–419) defines `GET /api/v1/scans/{scan_id}/logs` accepting only `scan_id`, `page`, and `size`. No date/time query parameters exist.
- No unified endpoint exists to list or filter logs across all scans (e.g. `GET /api/v1/logs`).
- `SecurityAlert` in `backend/app/models/alert.py` (lines 11–22) stores alerts with `category="VULN"` or `"SCAN"`. `backend/app/api/alerts.py` (lines 26–58) provides `GET /alerts`, `POST /alerts/{id}/read`, `POST /alerts/read-all`.
- Grep search for `"purge"` in `backend/` yielded only in-memory queue purge and vulnerability remediation text strings.
- Grep search for `"reset"` in `backend/` yielded only password reset strings and GHSA rate-limit reset strings. No system state reset endpoint (`POST /api/v1/system/reset`) exists.

### Observation 3: Scanner Engines & CLI Host Audit
- `NucleiAdapter` in `backend/app/scanners/nuclei.py` (lines 31–36) checks `shutil.which("nuclei")` or `shutil.which("nuclei.exe")`.
- Command execution `powershell -Command "Get-Command nuclei, zap, trivy | Select-Object Name, Source"` and `nuclei -version` returned:
  ```
  Name: nuclei.exe
  Source: C:\Users\nguye\go\bin\nuclei.exe
  Nuclei Engine Version: v3.11.1
  Nuclei Config Directory: C:\Users\nguye\AppData\Roaming\nuclei
  ```
- `zap` and `trivy` binaries are absent on PATH; fallback `ZAPLabRunner` and `TrivyLabRunner` are active.
- `backend/main.py` (lines 80–93) lists all 13 mounted API routers: `auth`, `assets`, `scans`, `findings`, `settings`, `reports`, `metrics`, `intel`, `rules`, `empire_modules`, `baselines`, `schedules`, `alerts`.
- **There is NO engine router** (`api/engines.py`) mounted under `/api/v1/engines`, nor any `/api/v1/engines/health` endpoint.

### Observation 4: User Authentication & Ultra Admin
- `backend/app/models/base.py` (lines 48–56): `User` model defines `id`, `username`, `hashed_password`, `is_active`, `is_superuser`. It lacks `email` and `role` columns.
- `backend/app/core/config.py` (lines 30–31): `ADMIN_USERNAME = os.getenv("SENTINEL_ADMIN_USER", "admin")`, `ADMIN_PASSWORD = os.getenv("SENTINEL_ADMIN_PASS", "admin123")`.
- `backend/app/core/database.py` (lines 78–92): `init_db()` checks and seeds only `settings.ADMIN_USERNAME` (`"admin"` / `"admin123"`).
- `frontend/src/app/login/page.tsx` (lines 23–28): Hardcodes:
  ```typescript
  const ULTRA_ADMIN_CREDENTIALS = {
    email: 'dangnhutnguyen0910@gmail.com',
    password: 'REDACTED-ROTATE-ME',
    role: 'SUPER_ADMIN',
    name: 'Đại Ca Tú (Ultra Admin)',
  };
  ```
  The login form handles authentication in local storage without submitting an HTTP request to `/api/v1/auth/login`.

### Observation 5: Loop Testing & Notification Tracking
- Grep search for `"loop"` in `backend/` revealed event loops in dispatcher and target verifier, but no loop testing harness or endpoint.
- `SecurityAlert` notifications are generated in `backend/app/core/dispatcher.py` (lines 876–887 and 934–949) on High/Critical findings and scan lifecycle changes.
- `backend/app/api/alerts.py` provides no SSE stream (`/alerts/stream`), no alert deletion (`DELETE /alerts/{id}`), and no unread count endpoint.

---

## 2. Logic Chain

1. **Scheduling Logic:**
   - From Observation 1: `DailySchedule` exists in the database schema, but is never queried by any periodic worker or background loop in `main.py` or `dispatcher.py`.
   - Inferences: The scheduler is entirely passive. Without an active asyncio ticker loop evaluating cron expressions, daily or scheduled scans cannot run without manual intervention.

2. **Log Management & State Reset Logic:**
   - From Observation 2: `scan_logs` table records logs, but querying is strictly scoped to `/{scan_id}/logs` without date filters.
   - Inferences: Operators cannot track activity by day or export logs. Furthermore, the complete absence of purge/reset endpoints prevents operators from resetting the system back to its initial clean seeded state ("quay về trạng thái ban đầu").

3. **Scanner Engine Management Logic:**
   - From Observation 3: Real `nuclei.exe` v3.11.1 is installed on the host, but the backend lacks any engine router (`/api/v1/engines`).
   - Inferences: The platform cannot report engine health, detect versions dynamically, or trigger updates (`nuclei -ut`, `nuclei -up`) via API.

4. **Ultra Admin Authentication Logic:**
   - From Observation 4: The database only seeds user `"admin"`. The Ultra Admin (`dangnhutnguyen0910@gmail.com` / `REDACTED-ROTATE-ME`) exists only in frontend client-side constants and is missing from `noospire.db`.
   - Inferences: When dev bypass is disabled or production auth is enforced, Ultra Admin login against backend fails with 401. Seeding Ultra Admin in `init_db()` is mandatory.

5. **Loop Testing & Notifications Logic:**
   - From Observation 5: The user explicitly requires loop testing and notification tracking.
   - Inferences: A dedicated loop testing runner (`/api/v1/scans/loop-test`) and real-time alert streaming (`/api/v1/alerts/stream`) must be added to provide continuous verification and immediate incident feedback.

---

## 3. Caveats

- **External CLI Dependability:** On this Windows machine, `nuclei.exe` v3.11.1 is available on PATH, but `zap` and `trivy` are not. The platform relies on `ZAPLabRunner` and `TrivyLabRunner` for those engines, which perform real HTTP checks with high fidelity.
- **Frontend Alignment:** The frontend `frontend/src/app/login/page.tsx` was tested client-side; aligning it with backend auth requires both backend seeding and frontend API integration.

---

## 4. Conclusion

The NOOSFORGE backend architecture possesses strong foundations (async SQLAlchemy ORM, process safety manager, multi-engine runner, SQLite WAL mode), but exhibits five distinct architectural gaps preventing full compliance with the user request:
1. **Passive Scheduler:** Needs an active asyncio background cron runner and full schedule CRUD.
2. **Log Management & State Reset:** Needs a unified log query API with date/day filtering, log export (CSV/JSON), log purge, and a platform state reset endpoint (`POST /api/v1/system/reset`).
3. **Engine Health & Update API:** Needs an `/api/v1/engines` router with `/health`, `/versions`, and template/binary update triggers.
4. **Ultra Admin Provisioning:** Needs `dangnhutnguyen0910@gmail.com` / `REDACTED-ROTATE-ME` seeded in `init_db()` and supported in `auth.py`.
5. **Loop Testing & Alerts Stream:** Needs `/api/v1/scans/loop-test` with drift analysis and SSE alert streaming (`/api/v1/alerts/stream`).

Full technical designs and API contracts are documented in:
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\teamwork_explorer_enh_1\analysis.md`.

---

## 5. Verification Method

1. **Verify Existing Tests Pass:**
   ```powershell
   pytest tests/test_scan_all_batch_orchestration.py -v
   ```
2. **Verify Engine Detection:**
   ```powershell
   nuclei -version
   ```
3. **Verify Database Seeding & Models:**
   ```powershell
   python scripts/verify_empire_e2e.py
   ```
4. **Inspect Analysis Report:**
   View `c:\Users\nguye\Desktop\noospire\.agents\teamwork\teamwork_explorer_enh_1\analysis.md`.
