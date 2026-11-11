# NOOSFORGE Security Intelligence — Empire Platform Memory Graph

## 1. Project Context & Authority
- **Primary Operator**: Đại Ca (Chủ nhân tối thượng duy nhất).
- **Agent Identity**: Đệ gác cổng kiêm Lead Systems & Security Architect.
- **Tone & Style**: Giang hồ bựa bãi siêu hài hước v9.0, trung thành tuyệt đối, chú thích thuật ngữ kỹ thuật gốc `(...)` liền kề từ lóng, Zero-Truncation 100%.

## 2. Architecture & Modules (Empire Educational Platform)
- **Module A (Student Management)**: `https://id.empire.edu.vn` (Better-Auth, BOLA, User Enum, synthetic credentials).
- **Module B (Learning Materials)**: `https://voh.empire.edu.vn`, `https://mh.empire.edu.vn/media/*` (MinIO S3, `/media` Approved Public Exposure Baseline `PUBLIC_BY_DESIGN`).
- **Module C (Supporting Tools)**: `https://gw.empire.edu.vn/news/*` (News RSS SSRF, Dictionary XSS).
- **Module D (API Services)**: `https://gw.empire.edu.vn` (BFLA `/api/v1/admin/*`, Rate Limit, Social Graph IDOR).
- **Module E (Web Application)**: `https://console.empire.io.vn` (Client-side RBAC bypass, hardcoded secrets).
- **Module F & G (Brute Force Defense & Server Infrastructure)**: Throttling 429, TLS/Headers, Daily Scheduler `Asia/Ho_Chi_Minh` (02:00 AM ICT).

## 3. Persistent Decisions & Verification Artifacts
- **Zero Fabrication**: All metrics, charts, findings, and reports are backed 1:1 by SQLite async database (`noospire.db`).
- **Approved Public Baseline**: `/media` registered under `BaselineException` to prevent false positives.
- **Frontend**: Next.js 14 App Router (Cyber-Slate Dark Mode) with 13 unified navigation views. Build is 100% verified (`npm run build` PASS, 18/18 static pages generated).
- **E2E Test Suite**: `scripts/verify_empire_e2e.py` validates all 10 core capabilities (10/10 PASS).
- **One-Click Launchers**:
  - `run.cmd --check` (Doctor & E2E Verification)
  - `run.cmd --preset all -y` (Launches Backend FastAPI :8000 + Frontend Next.js :3000)
  - `run.sh` for Linux/macOS

## 4. Final Sign-Off & Verification Verdict (Milestones M1–M10)
- **Status**: VICTORY CONFIRMED (100% PASS by Independent Victory Auditor).
- **Backend Suite**: 244/244 pytest tests passed (14 test modules, 0 failures).
- **Live E2E Suite**: 10/10 checks passed cleanly on live target `https://empire.edu.vn/`.
- **Frontend Build**: Next.js 14.2.35 statically compiled 18/18 routes with exit code 0.
- **Frontend Linter**: ESLint & TypeScript strict check passed with 0 errors, 0 warnings.
- **Milestone Coverage**:
  - M1–M7: Core targets, engines, taxonomy, liquid glass shell, primitives, live tracking, E2E assessment.
  - M8: "Scan All" batch scan, adaptive thread scheduler, psutil CPU/RAM throttling.
  - M9: Modern liquid glass UI, brand logo (SHA-256 verified), live multi-worker HUD, toast notifications.
  - M10: Full dual-track regression & acceptance verification, signed off under `FINAL_PROJECT_SIGN_OFF.md`.
