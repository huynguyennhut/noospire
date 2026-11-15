# EMPIRE EDUCATIONAL PLATFORM — NOOSPIRE DEPLOYMENT & OPERATIONS RUNBOOK

**Runbook Version**: 2.4.0  
**Target Environments**: Production Linux / Docker Compose / Kubernetes  
**Default Port Layout**: Frontend `3000`, Backend API `8000`, PostgreSQL `5432`  
**Security Standard**: Non-Root Execution (`uid=1000`), Least Privilege, Zero Hardcoded Secrets  

---

## 1. System Architecture & Prerequisites

The NOOSFORGE Security Intelligence / Noospire enterprise platform comprises three primary runtime layers:

```
+-------------------------------------------------------------------------+
|                        DEPLOYMENT ARCHITECTURE                          |
+-------------------------------------------------------------------------+
| [Reverse Proxy: Nginx / Envoy]  -->  Terminates TLS (Port 443)          |
|         |                                                               |
|         +---> [Frontend Container] : Next.js 14 Liquid Glass (Port 3000)|
|         |                                                               |
|         +---> [Backend Container]  : FastAPI / Uvicorn (Port 8000)      |
|                     |                                                   |
|                     +---> [Database] : PostgreSQL 16 (or SQLite WAL)    |
|                     +---> [Engines]  : ZAP / Nuclei / Trivy (Sandboxed) |
+-------------------------------------------------------------------------+
```

### 1.1 Minimum System Requirements
- **Operating System**: Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9)
- **CPU**: Minimum 4 physical cores (8 vCPUs recommended for concurrent scanning)
- **RAM**: Minimum 8 GB (16 GB recommended for concurrent ZAP and Nuclei instances)
- **Disk Storage**: 50 GB NVMe SSD (dedicated volume for report artifacts and database)
- **Software Dependencies**: Docker 24+, Docker Compose v2.20+, Python 3.12+, Node.js 20+

---

## 2. Environment Variables & Configuration Matrix

All configuration parameters must be supplied via secure environment variables. **Hardcoding secrets in source files, Dockerfiles, or git repositories is strictly prohibited.**

```
+--------------------------------+----------------------------------------------------+--------------------------+
| Variable Name                  | Description & Purpose                             | Production Example       |
+--------------------------------+----------------------------------------------------+--------------------------+
| `SENTINEL_DATABASE_URL`        | Async SQLAlchemy database connection string        | postgresql+asyncpg://... |
| `SENTINEL_SECRET_KEY`          | 256-bit cryptographically random secret for JWT    | [RANDOM_HEX_64_CHARS]    |
| `SENTINEL_SOLE_OWNER_EMAIL`    | Verified Sole Owner account email address          | dangnhutnguyen0910@...   |
| `SENTINEL_SOLE_OWNER_ACCOUNT_ID| Immutable Sole Owner UUID identifier               | 00000000-0000-0000-...   |
| `SENTINEL_PROCESS_ROLE`        | Process role: `all` | `api` | `worker` | `scheduler` | all                      |
| `SENTINEL_SEED_DEMO_DATA`      | Seed demonstration fixtures (disable in production)| false                    |
| `SENTINEL_ENVIRONMENT`        | Deployment tier: `production` | `staging` | `dev`   | production               |
| `SSRF_ALLOW_PRIVATE_TARGETS`   | Permit scans of RFC 1918 subnets (NEVER in prod)   | false                    |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | JWT token lifespan before re-authentication        | 60                       |
| `DEFAULT_TIMEZONE`             | Primary operational display timezone               | Asia/Ho_Chi_Minh         |
+--------------------------------+----------------------------------------------------+--------------------------+
```

---

## 3. Docker Compose Production Deployment

### 3.1 Docker Compose Configuration (`docker-compose.prod.yml`)
```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    container_name: noospire-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: noospire
      POSTGRES_USER: noospire_user
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    secrets:
      - db_password
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U noospire_user -d noospire"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4096M

  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    container_name: noospire-backend
    restart: unless-stopped
    user: "1000:1000"
    environment:
      SENTINEL_DATABASE_URL: postgresql+asyncpg://noospire_user:${DB_PASSWORD}@db:5432/noospire
      SENTINEL_SECRET_KEY: ${SECRET_KEY}
      SENTINEL_SOLE_OWNER_EMAIL: dangnhutnguyen0910@gmail.com
      SENTINEL_SOLE_OWNER_ACCOUNT_ID: 00000000-0000-0000-0000-000000000001
      SENTINEL_ENVIRONMENT: production
      SENTINEL_SEED_DEMO_DATA: "false"
      SSRF_ALLOW_PRIVATE_TARGETS: "false"
      SENTINEL_PROCESS_ROLE: "all"
    volumes:
      - reports_data:/home/nhut-nguyen/noospire/storage/reports
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "4.0"
          memory: 8192M

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: noospire-frontend
    restart: unless-stopped
    user: "1000:1000"
    environment:
      NEXT_PUBLIC_API_URL: https://security.empire.edu.vn/api/v1
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - backend

volumes:
  postgres_data:
  reports_data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

### 3.2 Non-Root Execution & Container Hardening
All production images enforce:
1. `USER 1000:1000` (non-root `noospire` user).
2. `security_opt: ["no-new-privileges:true"]`.
3. Read-only container root filesystems with ephemeral `tmpfs` mounts for `/tmp` and scanner scratch spaces.
4. Dropped Linux capabilities: `cap_drop: ["ALL"]`, keeping only `NET_BIND_SERVICE`.

---

## 4. Local Development Deployment (SQLite WAL Mode)

For local development and testing, Noospire supports SQLite with Write-Ahead Logging (WAL):

```bash
# 1. Clone repository and setup environment
cd /home/nhut-nguyen/noospire

# 2. Setup Python virtual environment
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Configure local environment variables
export SENTINEL_DATABASE_URL="sqlite+aiosqlite:///./data/noospire.db"
export SENTINEL_SECRET_KEY="dev-secret-key-do-not-use-in-production-vault"
export SENTINEL_SOLE_OWNER_EMAIL="dangnhutnguyen0910@gmail.com"
export SENTINEL_SOLE_OWNER_ACCOUNT_ID="00000000-0000-0000-0000-000000000001"
export SENTINEL_SEED_DEMO_DATA="true"
export SENTINEL_ENVIRONMENT="development"
export SSRF_ALLOW_PRIVATE_TARGETS="true"

# 4. Initialize Database & Seed Ecosystem
python scripts/verify_empire_e2e.py

# 5. Launch Backend Service
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 6. Launch Frontend Interface (in second terminal)
cd frontend
npm install
npm run dev
```

---

## 5. Backup & Disaster Recovery Procedures

### 5.1 Database Backup
- **PostgreSQL Production**:
  ```bash
  # Execute transactional online backup
  docker exec -t noospire-postgres pg_dump -U noospire_user -d noospire -Fc > backup_noospire_$(date +%Y%m%d_%H%M%S).dump
  ```
- **SQLite Development**:
  ```bash
  sqlite3 data/noospire.db ".backup data/backup_noospire_$(date +%Y%m%d_%H%M%S).sqlite"
  ```

### 5.2 Report Artifact Storage Backup
```bash
# Archive immutable reports snapshot directory
tar -czvf reports_backup_$(date +%Y%m%d_%H%M%S).tar.gz storage/reports/
```

---

## 6. Rollback & Failover Procedures

If a newly deployed release exhibits instability, high error rates, or database schema deadlocks:

1. **Stop Traffic**:
   ```bash
   docker-compose -f docker-compose.prod.yml stop backend frontend
   ```
2. **Revert Application Containers**:
   ```bash
   docker tag noospire-backend:previous noospire-backend:latest
   docker tag noospire-frontend:previous noospire-frontend:latest
   ```
3. **Database Schema Rollback** (if migrations were applied):
   ```bash
   docker-compose -f docker-compose.prod.yml run --rm backend alembic downgrade -1
   ```
4. **Restart Services & Verify**:
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   curl -f http://127.0.0.1:8000/healthz/ready || exit 1
   ```
5. **Run E2E Smoke Verification**:
   ```bash
   python scripts/verify_empire_e2e.py
   ```
