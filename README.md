# NOOSFORGE Security Intelligence — Empire Platform
## Continuous Security Assessment, Attack Surface Monitoring & Vulnerability Management

---

## 1. Executive Summary & Product Architecture

**NOOSFORGE Security Intelligence** is an enterprise-grade, continuous security assessment and attack surface management platform purpose-built for the **Empire Educational Ecosystem**. 

Unlike generic vulnerability scanners that blindly execute network requests against arbitrary hostnames, NOOSFORGE deeply understands the **Empire business architecture**, mapping technical attack vectors directly to functional educational units. It continuously evaluates security posture, detects regressions, prevents credential leaks, enforces approved baseline exposure policies, and delivers multi-format audit-grade reporting strictly backed 1:1 by real persisted database findings (**Zero-Fabrication Guarantee**).

```
                      +---------------------------------------+
                      |   NOOSFORGE SECURITY INTELLIGENCE     |
                      |   Empire Mission Control Hub (v16.0)  |
                      +---------------------------------------+
                                          |
        +---------------------------------+---------------------------------+
        |                                 |                                 |
+---------------+                 +---------------+                 +---------------+
|   MODULE A    |                 |   MODULE B    |                 |   MODULE C    |
| Student Mgmt  |                 | Learning Mat. |                 | Support Tools |
| Better-Auth   |                 | MinIO CDN     |                 | News / Dict   |
| id.empire     |                 | voh.empire    |                 | gw.empire     |
+---------------+                 +---------------+                 +---------------+
        |                                 |                                 |
+---------------+                 +---------------+                 +---------------+
|   MODULE D    |                 |   MODULE E    |                 |   MODULE F/G  |
| API Security  |                 | Web Console   |                 | Brute Force & |
| Gateway BFLA  |                 | RBAC Bypass   |                 | Infrastructure|
| gw.empire     |                 | console.io    |                 | Daily Sched.  |
+---------------+                 +---------------+                 +---------------+
```

---

## 2. Empire Business Architecture Mapping

### Module A — Student Management (`id.empire.edu.vn`)
- **Core Technology**: Better-Auth authentication endpoints (`/api/auth/*`), Next.js 14 frontend.
- **Audit Focus**: Account enumeration, registration validation, negative-authentication error parity, BOLA/IDOR on student identity endpoints, session lifetime, and synthetic student credential testing (`studenttu1`).
- **Safety Policy**: Strictly bounded negative-auth probes (max 5 attempts); zero mass extraction of real student accounts.

### Module B — Educational Material Management (`voh.empire.edu.vn`, `mh.empire.edu.vn/media/*`)
- **Core Technology**: MinIO S3 Object Storage, Course Content Delivery Service.
- **Audit Focus**: S3 anonymous bucket listing, directory indexing, unpublished curriculum leakage (`/courses/*`), and unintended exposure of internal database backups (`.env`, `.sql`, `.zip`).
- **Approved Public Exposure Policy**: `/media/*` educational assets (course thumbnails, public lectures, and syllabi) are classified as **`PUBLIC_BY_DESIGN`**. The assessment engine validates against registered `BaselineException` entities, completely eliminating false-positive alarms for approved public materials.

### Module C — Supporting Educational Tools (`gw.empire.edu.vn/news/*`, Dictionary, Vocabulary)
- **Core Technology**: Microservice API integrations, RSS/News aggregation engines.
- **Audit Focus**: Server-Side Request Forgery (SSRF) in news aggregator fetchers, blind out-of-band data exfiltration, DOM/Reflected Cross-Site Scripting (XSS) in vocabulary search tools.

### Module D — API Security (`gw.empire.edu.vn`)
- **Core Technology**: API Gateway routing to educational services.
- **Audit Focus**: OWASP API Top 10 vulnerabilities, Broken Object Level Authorization (BOLA), Broken Function-Level Authorization (BFLA) on administrative endpoints (`/api/v1/admin/*`), rate-limiting bypasses, and unauthorized social graph harvesting (`/social/v2/*`).

### Module E — Web Application Security (`console.empire.io.vn`)
- **Core Technology**: Administrative Single Page Application (SPA).
- **Audit Focus**: Client-side Role-Based Access Control (RBAC) bypass, administrative route leakage, hardcoded API tokens in compiled JavaScript bundles, CORS origin validation, and CSP enforcement.

### Module F & G — Brute Force Defense & Server Infrastructure
- **Audit Focus**: Rate limiting, IP throttling, HTTP 429 enforcement on authentication endpoints, TLS cipher suites, security response headers (`HSTS`, `X-Frame-Options`, `Content-Security-Policy`), server fingerprinting, and automated daily assessment scheduling.

---

## 3. Core Capabilities & Architectural Subsystems

### 3.1. Zero-Fabrication Assessment Engine (`EmpireAssessmentEngine`)
- Direct integration with target APIs using safe, non-destructive probe payloads.
- Bounded 5-probe negative authentication test with zero credential spraying.
- Real-time event and audit log emission streamed live via Server-Sent Events (SSE).
- Automatic regression detection: if a previously marked `FIXED` finding is rediscovered, it is immediately transitioned to **`REOPENED`** and a High-Severity security alert is generated.

### 3.2. Approved Public Exposure Policy Manager (`BaselineException`)
- Allows security administrators to register whitelisted public paths (e.g. `https://mh.empire.edu.vn/media/*`).
- Findings matching an approved baseline are classified as `PUBLIC_BY_DESIGN` with an audit record, preventing false positives while auditing against accidental leakage of sensitive files (`.csv`, `.xlsx`, `.pem`, `.env`).

### 3.3. Vulnerability Triage & Lifecycle Engine
- Supports all 10 standard vulnerability lifecycle states:
  - `NEW` ➔ `POTENTIAL` ➔ `CONFIRMED` ➔ `OPEN` ➔ `IN_REMEDIATION` ➔ `FIXED` ➔ `REOPENED` ➔ `ACCEPTED_RISK` ➔ `FALSE_POSITIVE` ➔ `NOT_AFFECTED`.
- Live **One-Click Retest Engine**: Re-evaluates live endpoints against original forensic evidence to automatically verify fixes or confirm ongoing exposure.

### 3.4. Daily Assessment Scheduler (`Asia/Ho_Chi_Minh` ICT)
- Pre-configured to execute full security assessments across all Empire targets daily at **02:00 AM ICT** (`0 2 * * *`).
- Provides one-click instant manual trigger with live progress tracking across all targets.

### 3.5. Multi-Format Audit-Grade Reporting
- Multi-format generation in **Vector PDF** (via ReportLab with custom cybersecurity theme), **HTML**, and **JSON**.
- 10 comprehensive report templates (Executive Summary, Technical Vulnerability Report, Module-Specific Audits, Compliance Reports).
- 100% backed by database records — zero mock or placeholder findings.

---

## 4. SOC Console: 13 Unified Navigation Views

The web frontend is built with **Next.js 14 (App Router)**, **TypeScript**, and **Tailwind CSS** using a high-density, **Cyber-Slate Dark Mode** design language.

| # | Route | Module Name | Primary Operational Capabilities |
|---|---|---|---|
| 1 | `/dashboard` | **Security Overview** | 10 KPI Summary Cards (Risk Score, Active Scans, Findings) + 8 real DB-backed charts |
| 2 | `/assets` | **Target Management** | Asset inventory table, live health badges, and Bulk Importer (CSV/JSON/OpenAPI deduplication) |
| 3 | `/empire-modules` | **Empire Modules** | 6 Business Unit cards (Student Mgmt, Materials, Tools, APIs, Web App, Infra) with risk scoring |
| 4 | `/scans` | **Scan Center** | Launch assessments across 7 profiles (Daily Security, Thorough, API, Authenticated, etc.) |
| 5 | `/active-assessments` | **Active Tracker** | Real-time SSE terminal log streaming, scan stage progress, and emergency job cancellation |
| 6 | `/findings` | **Findings Explorer** | Comprehensive vulnerability triage table, forensic drawer, and one-click live retest |
| 7 | `/remediation` | **Remediation Board** | 5-column Kanban board mapping findings from OPEN to VERIFIED_RESOLVED |
| 8 | `/reports` | **Report Center** | 10 audit report templates with multi-format download (Vector PDF, HTML, JSON) |
| 9 | `/schedules` | **Daily Scheduler** | Asia/Ho_Chi_Minh (02:00 AM ICT) assessment pipeline configuration and manual dispatch |
| 10 | `/threat-intel` | **Threat Intelligence** | CVE search, CISA KEV catalog sync, EPSS exploitation scores, and vulnerability feeds |
| 11 | `/detection-rules` | **Detection Rules** | Declarative YAML detection rules with syntax validation, test runners, and lifecycle gating |
| 12 | `/integrations` | **Integrations & Scanners** | Status of integrated scanners (Nuclei, Empire Engine, Better-Auth Prober) & Webhooks |
| 13 | `/health` & `/settings` | **Diagnostics & Settings** | System telemetry, /media Approved Baseline Policy manager, and Synthetic Student Identities |

---

## 5. Quick Start & Operational Commands

### 5.1. System Verification & Self-Test (Doctor Mode)
Run the automated End-to-End Vertical Slice Verifier testing all 10 core capabilities:

**Windows**:
```cmd
run.cmd --check
```

**Linux / macOS**:
```bash
chmod +x run.sh
./run.sh --check
```

### 5.2. Launch Platform (Full Stack)
Start both the FastAPI backend (Port 8000) and Next.js frontend (Port 3000):

**Windows**:
```cmd
run.cmd --preset all -y
```

**Linux / macOS**:
```bash
./run.sh --preset all
```

Access the user interfaces:
- **Web Mission Control**: [http://localhost:3000/dashboard](http://localhost:3000/dashboard)
- **Empire Module Hub**: [http://localhost:3000/empire-modules](http://localhost:3000/empire-modules)
- **Interactive OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 6. Directory Structure

```text
noospire/
├── run.cmd                       # Unified Windows Launcher (interactive menu & CLI flags)
├── run.sh                        # Unified Linux/macOS Shell Launcher
├── README.md                     # Master Architecture & Technical Operations Manual
├── noospire.db                   # SQLite Async Database with seeded Empire ecosystem
│
├── backend/                      # FastAPI Python 3.14 Async Engine
│   ├── main.py                   # Application entrypoint & CORS middleware configuration
│   └── app/
│       ├── api/                  # 11 REST API Routers
│       │   ├── assets.py         # Target onboarding & CSV/JSON bulk import deduplication
│       │   ├── empire_modules.py # Empire business module health & risk metrics
│       │   ├── baselines.py      # Approved Public Media (/media) policy exceptions
│       │   ├── scans.py          # Assessment dispatch & SSE live log streaming
│       │   ├── findings.py       # Vulnerability triage (10 states) & Live Retest engine
│       │   ├── schedules.py      # Daily assessment scheduler (Asia/Ho_Chi_Minh)
│       │   ├── alerts.py         # Security notifications & in-app alerts
│       │   ├── metrics.py        # 10 Overview KPIs & 8 database-backed chart datasets
│       │   ├── rules.py          # Declarative YAML detection rules & syntax validator
│       │   └── intelligence.py   # CVE lookup & CISA KEV threat intelligence feeds
│       ├── core/                 # Config, DB async engine, security, and seeder
│       ├── models/               # SQLAlchemy ORM models (Asset, Finding, Baseline, Schedule, Alert)
│       ├── scanners/             # EmpireAssessmentEngine & Nuclei integration
│       └── reporting/            # Multi-format ReportLab PDF, HTML, & JSON builder
│
├── frontend/                     # Next.js 14 Cyber-Slate Dark UI
│   ├── src/
│   │   ├── app/                  # 13 Application Views (Dashboard, Assets, Modules, Scans, etc.)
│   │   ├── components/           # UI Shell, Navigation, Notifications, Charts
│   │   └── lib/                  # TypeScript Types & unified ApiClient
│   └── package.json
│
└── scripts/                      # Operational Scripts & Test Harnesses
    └── verify_empire_e2e.py      # 10-Step Automated Vertical Slice Verification Suite
```

---

## 7. Verified Empire Historical Vulnerability Inventory

The initial database seed incorporates confirmed technical findings from previous security assessments of Empire targets, ensuring immediate operational visibility:

| ID | Title | Target Module | Endpoint / Target | Severity | CVSS | Status |
|---|---|---|---|---|---|---|
| **VULN-01** | MinIO Anonymous Bucket Access & Data Exposure | Learning Materials | `https://voh.empire.edu.vn` | **CRITICAL** | 9.8 | CONFIRMED |
| **VULN-02** | Client-Side RBAC Enforcement Bypass | Web Application | `https://console.empire.io.vn` | **HIGH** | 8.8 | CONFIRMED |
| **VULN-03** | User Enumeration via Inconsistent Auth Responses | Student Management | `https://id.empire.edu.vn/api/auth/*` | **HIGH** | 8.2 | CONFIRMED |
| **VULN-04** | Unauthorized Social Graph Harvesting via IDOR | API Services | `https://gw.empire.edu.vn/social/v2/*` | **HIGH** | 7.5 | CONFIRMED |
| **VULN-05** | Course & Video Curriculum Content Leakage | Learning Materials | `https://gw.empire.edu.vn/courses/*` | **HIGH** | 7.5 | CONFIRMED |
| **VULN-06** | Hardcoded API Keys & Secrets in Frontend Bundle | Web Application | `https://console.empire.io.vn` | **MEDIUM** | 6.5 | CONFIRMED |

---
**NOOSFORGE Security Intelligence** — *Continuous Attack Surface Superiority for Educational Platforms.*
