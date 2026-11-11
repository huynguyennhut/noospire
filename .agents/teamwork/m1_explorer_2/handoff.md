# Implementation Strategy & Action Plan: Milestone 1 (Backend Auth, Bootstrap & RBAC)

## 1. Observation

Direct code examination and automated test audits across the Noospire backend codebase revealed the following exact facts, line locations, and architectural state:

### 1.1 `backend/app/core/config.py`
- **Lines 25**:
  ```python
  SECRET_KEY: str = os.getenv("SENTINEL_SECRET_KEY", "noospire-super-secret-key-change-in-production-2026")
  ```
  Contains a static default fallback secret key string in the codebase.
- **Lines 30-35**:
  ```python
  ADMIN_USERNAME: str = os.getenv("SENTINEL_ADMIN_USER", "admin")
  ADMIN_PASSWORD: Optional[str] = os.getenv("SENTINEL_ADMIN_PASS")
  ULTRA_ADMIN_EMAIL: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_EMAIL")
  ULTRA_ADMIN_PASS: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_PASS")
  ULTRA_ADMIN_ROLE: str = os.getenv("SENTINEL_ULTRA_ADMIN_ROLE", "SUPER_ADMIN")
  ```
  Default password references (`ADMIN_PASSWORD`, `ULTRA_ADMIN_PASS`) persist in settings.
- **Lines 55-56**:
  ```python
  AUTH_ENABLED: bool = os.getenv("SENTINEL_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
  DEV_AUTH_BYPASS: bool = os.getenv("SENTINEL_DEV_AUTH_BYPASS", "false").lower() in ("true", "1", "yes")
  ```
  Contains flags permitting authentication disabling and bypass.
- **Lines 61-74**: `validate_production_secrets` checks for 32 chars in production, but development still permits insecure static default.

### 1.2 `backend/app/core/database.py`
- **Lines 93-113**:
  ```python
  async with AsyncSessionLocal() as session:
      if not settings.is_production and settings.ADMIN_PASSWORD:
          result = await session.execute(
              select(User).where(User.username == settings.ADMIN_USERNAME)
          )
          admin = result.scalars().first()
          if not admin:
              admin = User(...)
  ```
  Auto-seeds an admin account on non-production boot whenever `ADMIN_PASSWORD` is defined.
- Server boot must NEVER create default credentials or alter account passwords automatically. All initial administrator onboarding must proceed through an explicit, one-time bootstrap binding sole owner authority to `dangnhutnguyen0910@gmail.com`.

### 1.3 `backend/app/core/security.py` & `backend/app/api/deps.py`
- `DEV_MOCK_SUPERUSER` has been removed from `security.py` and `deps.py`.
- **`backend/app/api/deps.py` (Lines 91-130)**:
  `get_current_active_user` validates:
  - Account existence in database.
  - `user.is_active` check in database (raises 403 if inactive).
  - `RevokedToken` table check (raises 401 if token jti or hash is revoked).
  - `user.tokens_valid_after` timestamp check (raises 401 if token issued before invalidation timestamp).
  *Defect in `get_current_active_user`*:
  Line 93: `token: Optional[str] = Depends(oauth2_scheme)`. If a client authenticates via session cookie (`sentinel_access_token`), `oauth2_scheme` returns `None`. Line 96 checks `if not user or not token: raise 401`. This causes cookie-authenticated users to be rejected with 401 even though `user` was resolved by `get_current_user`.
- **RBAC Role Model**:
  `UserRole` currently defines `ADMIN`, `SUPER_ADMIN`, `OPERATOR`, `SECURITY_LEAD`, `VIEWER`, `USER`.
  Missing explicit `OWNER` (sole owner) and `DEVELOPER` (scoped asset access) roles.
  Missing database model for developer asset-level permission grants (`UserAssetGrant`).

### 1.4 API Routers Authentication Audit (AST Static Analysis)
An automated AST audit across all 16 routers under `backend/app/api/` identified that **28 routes across 6 routers are completely unauthenticated (`NO AUTH (OPEN)`)**:
- **`alerts.py` (6 routes OPEN)**: `list_alerts`, `get_unread_alerts_count`, `mark_alert_read`, `mark_all_alerts_read`, `delete_alert`, `delete_all_alerts`.
- **`empire_modules.py` (1 route OPEN)**: `list_empire_modules`.
- **`engines.py` (3 routes OPEN)**: `get_engines_health`, `check_engine_updates`, `test_all_engines`.
- **`intel.py` (6 routes OPEN)**: `get_threat_intel_summary`, `trigger_threat_intel_sync`, `get_cve_details`, `list_cves`, `list_cisa_kev_catalog`, `query_epss_batch`.
- **`logs.py` (3 routes OPEN)**: `list_logs`, `export_logs`, `purge_logs` (unauthenticated log purging!).
- **`metrics.py` (9 routes OPEN)**: `get_overview_metrics`, `get_severity_distribution`, `get_vulnerability_trend`, `get_module_risk_chart`, `get_coverage_chart`, `get_risk_score_trend`, `get_scanner_performance`, `get_intelligence_activity`, `get_remediation_progress`.
- **`scans.py` (`create_batch_scan`)**: Allows any operator to launch an estate-wide scan; missing owner-only restriction on estate-wide Ultra Scans. Missing scoped-developer asset access filtering.
- **User Management**: No endpoints exist to allow the owner to invite developers, activate/deactivate accounts, or grant/revoke asset permissions.

### 1.5 Test Baseline Diagnostics
Running `pytest tests/test_milestone_a_control_plane.py`:
- 13 out of 14 tests PASSED.
- 1 test FAILED: `test_f04_scoped_rbac_enforcement` due to `ResponseValidationError` in `list_assets`:
  `Input should be 'DNS_TXT', 'HTTP_WELL_KNOWN' or 'ADMIN_OVERRIDE', input: 'NONE'`.
  Root Cause: `empire_seeder.py` seeds initial targets with `verification_type = "NONE"`, but `VerificationType` enum in `backend/app/schemas/common.py` lacked `NONE`.

---

## 2. Logic Chain

1. **Premise**: Requirement R1 & R5 mandate zero hardcoded secrets, elimination of auth bypass flags, and dynamic secrets.
   - **Observation**: `config.py` contains static default secret strings and `DEV_AUTH_BYPASS` / `AUTH_ENABLED` flags.
   - **Deduction**: In production, `SECRET_KEY` must be mandated via environment. In development/testing, generating a cryptographically secure key at runtime via `secrets.token_urlsafe(32)` removes static secrets from repository files. Removing `DEV_AUTH_BYPASS` and hardcoding `AUTH_ENABLED = True` eliminates bypass risks.

2. **Premise**: Requirement R5 dictates binding sole owner authority to `dangnhutnguyen0910@gmail.com` with an immutable server-side account ID via one-time bootstrap.
   - **Observation**: `database.py` currently auto-seeds an admin account with default credentials during non-production boots. `auth.py`'s `/bootstrap` endpoint allows any email.
   - **Deduction**: Remove auto-seeding from `init_db()`. Require bootstrap to bind strictly to `dangnhutnguyen0910@gmail.com` with a fixed deterministic server UUID (`00000000-0000-0000-0000-000000000001` or `uuid5(NAMESPACE_DNS, "dangnhutnguyen0910@gmail.com")`). Once any admin/owner exists, bootstrap is permanently locked.

3. **Premise**: Only the sole owner may invite users/developers, manage accounts, grant capabilities, and configure or manually launch an estate-wide Ultra Scan.
   - **Observation**: There are no user management endpoints, no `OWNER` role, and batch scans on all targets are open to any operator.
   - **Deduction**: Add `OWNER` to `UserRole`. Create dedicated owner-only endpoints for user invitations, status toggling, and asset grants. Restrict `create_batch_scan` with `scan_all=True` to `require_owner`.

4. **Premise**: Scoped developers must see only explicitly granted assets, actions, and assigned work.
   - **Observation**: Assets and findings queries are global; there is no model associating users to specific assets.
   - **Deduction**: Create a `UserAssetGrant` table (`user_id`, `asset_id`, `permissions`, `granted_by`). In asset and scan endpoints, if `current_user.role == UserRole.DEVELOPER.value`, filter queries to granted assets only, and block scan dispatches to ungranted assets with HTTP 403.

5. **Premise**: Disabling an account must immediately invalidate active sessions.
   - **Observation**: `get_current_active_user` queries the DB on every request.
   - **Deduction**: When `user.is_active` is set to `False`, all subsequent requests fail immediately with HTTP 403. Setting `user.tokens_valid_after = datetime.now(timezone.utc)` and writing to `RevokedToken` ensures all issued JWTs are rejected.

6. **Premise**: All operational endpoints must be protected with authentication and permission guards; audit actors must be server-derived.
   - **Observation**: 28 routes across 6 routers currently lack `Depends(...)`.
   - **Deduction**: Enforce router-level or endpoint-level dependencies (`require_viewer`, `require_operator`, `require_admin`). Bind audit log entries exclusively to `current_user.username` and `current_user.id`.

---

## 3. Caveats

1. **Existing Test Suite Authorization**:
   - Some legacy tests in `tests/` make anonymous calls against `/api/v1/assets` or `/api/v1/metrics`. Tests in `tests/test_milestone_a_control_plane.py` and `tests/test_empire_e2e_opaque_box.py` already use authenticated headers (`admin_headers`, `operator_headers`, `viewer_headers`). Any older tests calling newly protected endpoints will need test client authentication headers.
2. **Deterministic Owner UUID & Foreign Keys**:
   - Using a deterministic UUID for the sole owner (`00000000-0000-0000-0000-000000000001`) guarantees that audit logs, grants, and database dumps have consistent referential integrity across restarts and database migrations.
3. **Database Dialect Compatibility**:
   - `UserAssetGrant` must use `GUID()` (which maps to `String(36)`) and `TimestampMixin` to ensure 100% parity across SQLite (local dev) and PostgreSQL (production).

---

## 4. Conclusion & Actionable Implementation Plan

The Worker should apply the following concrete code changes:

### Phase 1: `backend/app/core/config.py`
**Goal**: Remove hardcoded passwords, remove auth bypass flags, enforce dynamic secret keys and sole owner identity.

```python
# --- BEFORE (Lines 24-35, 55-58) ---
    # Security & JWT
    SECRET_KEY: str = os.getenv("SENTINEL_SECRET_KEY", "noospire-super-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Initial Admin Seed (No hardcoded fallback secrets in production)
    ADMIN_USERNAME: str = os.getenv("SENTINEL_ADMIN_USER", "admin")
    ADMIN_PASSWORD: Optional[str] = os.getenv("SENTINEL_ADMIN_PASS")
    ULTRA_ADMIN_EMAIL: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_EMAIL")
    ULTRA_ADMIN_PASS: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_PASS")
    ULTRA_ADMIN_ROLE: str = os.getenv("SENTINEL_ULTRA_ADMIN_ROLE", "SUPER_ADMIN")
...
    AUTH_ENABLED: bool = os.getenv("SENTINEL_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
    DEV_AUTH_BYPASS: bool = os.getenv("SENTINEL_DEV_AUTH_BYPASS", "false").lower() in ("true", "1", "yes")
    DEMO_MODE: bool = os.getenv("SENTINEL_DEMO_MODE", "false").lower() in ("true", "1", "yes")

# --- AFTER ---
    # Security & JWT: Dynamic Secret Key (zero hardcoded static keys in codebase)
    SECRET_KEY: str = os.getenv("SENTINEL_SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Sole Owner Authority (R5)
    SOLE_OWNER_EMAIL: str = os.getenv("SENTINEL_SOLE_OWNER_EMAIL", "dangnhutnguyen0910@gmail.com")
    SOLE_OWNER_ACCOUNT_ID: str = os.getenv(
        "SENTINEL_SOLE_OWNER_ACCOUNT_ID", "00000000-0000-0000-0000-000000000001"
    )

    # Initial Admin Seed (No default passwords in source code)
    ADMIN_USERNAME: str = os.getenv("SENTINEL_ADMIN_USER", "admin")
...
    # Authentication is permanently enforced (Bypass flags eliminated)
    AUTH_ENABLED: bool = True
    DEMO_MODE: bool = os.getenv("SENTINEL_DEMO_MODE", "false").lower() in ("true", "1", "yes")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.is_production:
            if (
                not self.SECRET_KEY
                or self.SECRET_KEY in (
                    "noospire-super-secret-key-change-in-production-2026",
                    "dev_insecure_default_secret_key_change_in_production",
                    "secret",
                )
                or len(self.SECRET_KEY) < 32
            ):
                raise ValueError(
                    "Production environment requires SENTINEL_SECRET_KEY to be explicitly configured with a cryptographically secure key of at least 32 characters."
                )
        else:
            # In non-production, generate dynamic cryptographic secret if not provided
            if not self.SECRET_KEY or self.SECRET_KEY == "noospire-super-secret-key-change-in-production-2026":
                import secrets
                self.SECRET_KEY = secrets.token_urlsafe(32)
        return self
```

---

### Phase 2: `backend/app/models/user.py` & `UserAssetGrant`
**Goal**: Add `OWNER` and `DEVELOPER` roles, and create `UserAssetGrant` model for scoped developer isolation.

In `backend/app/models/user.py`:
```python
class UserRole(str, Enum):
    OWNER = "OWNER"
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    DEVELOPER = "DEVELOPER"
    SECURITY_LEAD = "SECURITY_LEAD"
    VIEWER = "VIEWER"
    USER = "USER"


class UserAssetGrant(Base, TimestampMixin):
    """Scoped developer asset access grants (R5).
    Controls explicit asset visibility, scan execution, and triage rights.
    """
    __tablename__ = "user_asset_grants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    permissions: Mapped[str] = mapped_column(String(64), default="READ,SCAN", nullable=False)
    granted_by: Mapped[str] = mapped_column(String(128), nullable=False)
```

In `backend/app/models/base.py`:
Ensure `tokens_valid_after` is explicitly typed in `User`:
```python
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(256), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(64), default="USER", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tokens_valid_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

---

### Phase 3: `backend/app/core/database.py` & Clean Boot
**Goal**: Eliminate unconditional password resets and auto-seeding of admin credentials on server boot.

In `backend/app/core/database.py`:
Replace lines 93-113:
```python
# --- REMOVE ---
    # Check and seed default admin user only if explicitly configured in non-production environments
    # In production, initial admin MUST be established via explicit one-time bootstrap (F02)
    async with AsyncSessionLocal() as session:
        if not settings.is_production and settings.ADMIN_PASSWORD:
            ...

# --- REPLACE WITH ---
    # Register user_asset_grants in auto-migration for SQLite
    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Invariant (R5): NEVER seed default passwords or reset accounts on server boot!
    # Initial administrator onboarding is handled exclusively via one-time bootstrap (F02).
    async with AsyncSessionLocal() as session:
        # Seed Empire ecosystem targets, findings, baselines, and schedules
        await seed_empire_ecosystem(session)
```

---

### Phase 4: `backend/app/api/deps.py` & Scoped RBAC
**Goal**: Fix token extraction bug for cookie auth, add `require_owner` dependency, and provide scoped developer filtering.

In `backend/app/api/deps.py`:
1. Fix `get_current_active_user`:
```python
async def get_current_active_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that ensures the authenticated user is present, active, and unexpired."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce active user status in DB (F03) - Immediate invalidation
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    # Extract token from header or cookie
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("sentinel_access_token") or request.cookies.get("access_token")

    # Enforce session expiry via tokens_valid_after timestamp (F03)
    if token and hasattr(user, "tokens_valid_after") and user.tokens_valid_after:
        payload = decode_access_token(token)
        if payload:
            iat = payload.get("iat")
            if iat:
                token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc) if isinstance(iat, (int, float)) else iat
                if token_issued_at and token_issued_at < user.tokens_valid_after:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session expired/revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    return user
```

2. Add Role Dependencies:
```python
def require_roles(allowed_roles: List[str]):
    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        user_role = (current_user.role or "").upper()
        allowed = [r.upper() for r in allowed_roles]
        if current_user.is_superuser or user_role in ("OWNER", "SUPER_ADMIN", "ADMIN"):
            return current_user
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user

    return role_checker

async def require_owner(current_user: User = Depends(get_current_active_user)) -> User:
    """Sole Owner Enforcement (R5)."""
    user_role = (current_user.role or "").upper()
    is_owner = (
        user_role == UserRole.OWNER.value
        or (current_user.email and current_user.email.lower() == settings.SOLE_OWNER_EMAIL.lower())
        or str(current_user.id) == settings.SOLE_OWNER_ACCOUNT_ID
    )
    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation restricted solely to the system owner.",
        )
    return current_user

require_admin = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])
require_operator = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN", "OPERATOR", "SECURITY_LEAD"])
require_viewer = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN", "OPERATOR", "SECURITY_LEAD", "DEVELOPER", "VIEWER", "USER"])
```

3. Add Scoped Developer Asset Filter Helper:
```python
async def get_authorized_asset_ids(user: User, db: AsyncSession) -> Optional[List[uuid.UUID]]:
    """Returns list of allowed asset IDs for scoped developer, or None if user has estate-wide access."""
    user_role = (user.role or "").upper()
    if user.is_superuser or user_role in ("OWNER", "SUPER_ADMIN", "ADMIN", "SECURITY_LEAD"):
        return None  # Full estate-wide access
    if user_role == UserRole.DEVELOPER.value:
        from backend.app.models.user import UserAssetGrant
        res = await db.execute(select(UserAssetGrant.asset_id).where(UserAssetGrant.user_id == user.id))
        return res.scalars().all()
    return None
```

---

### Phase 5: One-Time Bootstrap & User Management in `auth.py`
**Goal**: Bind bootstrap to `dangnhutnguyen0910@gmail.com` with immutable account ID; provide owner-only user management endpoints.

In `backend/app/api/auth.py`:
1. Update `bootstrap_initial_admin`:
```python
@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_initial_admin(
    payload: BootstrapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    # 1. Permanently lock if any admin or owner already exists
    existing_admin_res = await db.execute(
        select(User).where(
            or_(
                User.role.in_([UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, "OWNER", "ADMIN", "SUPER_ADMIN"]),
                User.is_superuser == True,
            )
        )
    )
    if existing_admin_res.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System bootstrap has already been completed and is permanently locked.",
        )

    # 2. Bind sole owner authority to dangnhutnguyen0910@gmail.com (R5)
    owner_email = payload.email.strip().lower()
    if owner_email != settings.SOLE_OWNER_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bootstrap is restricted solely to the designated owner '{settings.SOLE_OWNER_EMAIL}'.",
        )

    # 3. Create Sole Owner with Immutable Server-Side Account ID
    sole_owner_uuid = uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID)
    new_owner = User(
        id=sole_owner_uuid,
        username=payload.username.strip(),
        email=owner_email,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.OWNER.value,
        is_active=True,
        is_superuser=True,
    )
    db.add(new_owner)

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = AdminAuditLog(
        user_id=str(new_owner.id),
        username=new_owner.username,
        action="SYSTEM_BOOTSTRAP",
        details=f"Sole owner account bound to {owner_email} with immutable ID {new_owner.id}. Bootstrap permanently locked.",
        ip_address=client_ip,
    )
    db.add(audit)
    await db.commit()

    return BootstrapResponse(
        message="System successfully bootstrapped. Sole owner authority established and bootstrap locked.",
        username=new_owner.username,
        email=new_owner.email,
    )
```

2. Add Owner-Only User Management Endpoints:
```python
# GET /api/v1/auth/users — List all users (require_owner)
# POST /api/v1/auth/users/invite — Create/invite developer or user (require_owner)
# PATCH /api/v1/auth/users/{user_id}/status — Activate/deactivate user (require_owner; cannot deactivate sole owner)
# POST /api/v1/auth/users/{user_id}/grants — Grant asset access to developer (require_owner)
# DELETE /api/v1/auth/users/{user_id}/grants/{grant_id} — Revoke asset access (require_owner)
```

---

### Phase 6: Router-Level Protection & Estate-Wide Scan Enforcement
**Goal**: Secure all 28 open routes across `alerts.py`, `empire_modules.py`, `engines.py`, `intel.py`, `logs.py`, `metrics.py`, and restrict estate-wide scans to the sole owner.

1. **Mount Authentication on All Open Routers**:
   - `alerts.py`:
     `router = APIRouter(prefix="/alerts", tags=["Security Alerts"], dependencies=[Depends(require_viewer)])`
     `delete_alert` and `delete_all_alerts` add `current_user: User = Depends(require_admin)`.
     `mark_alert_read` and `mark_all_alerts_read` add `current_user: User = Depends(require_operator)`.
   - `empire_modules.py`:
     `router = APIRouter(prefix="/empire-modules", tags=["Empire Business Modules"], dependencies=[Depends(require_viewer)])`.
   - `engines.py`:
     `router = APIRouter(prefix="/engines", tags=["Engine Diagnostics & Adapters"], dependencies=[Depends(require_viewer)])`.
     `test_all_engines` and `check_engine_updates` add `current_user: User = Depends(require_operator)`.
   - `intel.py`:
     `router = APIRouter(prefix="/intel", tags=["Threat Intelligence"], dependencies=[Depends(require_viewer)])`.
     `trigger_threat_intel_sync` adds `current_user: User = Depends(require_operator)`.
   - `logs.py`:
     `router = APIRouter(prefix="/logs", tags=["Audit & System Logs"], dependencies=[Depends(require_viewer)])`.
     `purge_logs` adds `current_user: User = Depends(require_admin)`.
   - `metrics.py`:
     `router = APIRouter(prefix="/metrics", tags=["Analytics & Intelligence Metrics"], dependencies=[Depends(require_viewer)])`.

2. **Restrict Estate-Wide Scans in `backend/app/api/scans.py`**:
   In `create_batch_scan`:
   ```python
   # Enforce R5: Only the owner can manually launch an estate-wide Ultra Scan
   if batch_in.scan_all or getattr(batch_in, "is_ultra_scan", False) or not batch_in.asset_ids:
       user_role = (current_user.role or "").upper()
       is_owner = (
           user_role == UserRole.OWNER.value
           or (current_user.email and current_user.email.lower() == settings.SOLE_OWNER_EMAIL.lower())
           or str(current_user.id) == settings.SOLE_OWNER_ACCOUNT_ID
       )
       if not is_owner:
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="Launching estate-wide Ultra Scan across the entire inventory is restricted solely to the system owner.",
           )
   ```

3. **Enforce Scoped Developer Visibility in `backend/app/api/assets.py`**:
   In `list_assets` and `get_asset`:
   ```python
   allowed_ids = await get_authorized_asset_ids(current_user, db)
   if allowed_ids is not None:
       stmt = stmt.where(Asset.id.in_(allowed_ids))
   ```

4. **Enum Schema Fix in `backend/app/schemas/common.py`**:
   ```python
   class VerificationType(str, Enum):
       NONE = "NONE"
       DNS_TXT = "DNS_TXT"
       HTTP_WELL_KNOWN = "HTTP_WELL_KNOWN"
       ADMIN_OVERRIDE = "ADMIN_OVERRIDE"
   ```

---

## 5. Verification Method

To independently verify all features of Milestone 1 Backend Auth & RBAC:

### 5.1 Automated Test Execution Commands
```bash
# 1. Run Control Plane & Auth Tests (M1 Feature Baseline)
pytest tests/test_milestone_a_control_plane.py -v

# 2. Run Opaque-Box E2E Tests (Tier 1 RBAC Boundaries)
pytest tests/test_empire_e2e_opaque_box.py -k "rbac or auth or login or secrets" -v

# 3. Run SSRF and Egress Policy Checks
pytest tests/test_milestone_a_control_plane.py -k "egress or ssrf" -v
```

### 5.2 Direct API Probes to Validate Acceptance Criteria
1. **Unauthenticated Access Rejection (All 28 Open Routes Now Blocked)**:
   ```bash
   # Verify alerts, metrics, logs, intel, empire-modules, engines reject anonymous calls
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/alerts
   # Expected: 401
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/metrics/overview
   # Expected: 401
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/logs
   # Expected: 401
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/intel/summary
   # Expected: 401
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/empire-modules
   # Expected: 401
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/engines/health
   # Expected: 401
   ```

2. **One-Time Bootstrap Sole Owner Enforcement**:
   ```bash
   # Attacker attempts bootstrap with arbitrary email -> 400 Bad Request
   curl -s -X POST http://localhost:8000/api/v1/auth/bootstrap \
     -H "Content-Type: application/json" \
     -d '{"username": "attacker", "email": "attacker@evil.com", "password": "Password123!"}'
   # Expected: 400 (Restricted to dangnhutnguyen0910@gmail.com)

   # Valid bootstrap creates sole owner with ID 00000000-0000-0000-0000-000000000001 -> 201 Created
   curl -s -X POST http://localhost:8000/api/v1/auth/bootstrap \
     -H "Content-Type: application/json" \
     -d '{"username": "dangnhutnguyen", "email": "dangnhutnguyen0910@gmail.com", "password": "StrongPassword123!"}'
   # Expected: 201

   # Second attempt permanently locked -> 400 Bad Request
   curl -s -X POST http://localhost:8000/api/v1/auth/bootstrap \
     -H "Content-Type: application/json" \
     -d '{"username": "second", "email": "dangnhutnguyen0910@gmail.com", "password": "StrongPassword123!"}'
   # Expected: 400 (Permanently locked)
   ```

3. **Immediate Session Invalidation on Account Deactivation**:
   ```bash
   # Deactivate user account -> subsequent API call with existing valid JWT must return 403 Forbidden immediately
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/auth/me \
     -H "Authorization: Bearer <deactivated_user_token>"
   # Expected: 403 Forbidden
   ```

4. **Estate-wide Scan Owner Restriction**:
   ```bash
   # Operator attempts estate-wide batch scan -> 403 Forbidden
   curl -s -X POST http://localhost:8000/api/v1/scans/batches \
     -H "Authorization: Bearer <operator_token>" \
     -H "Content-Type: application/json" \
     -d '{"scan_all": true, "profile": "QUICK"}'
   # Expected: 403 Forbidden (Restricted solely to system owner)
   ```

### 5.3 Invalidation Conditions
- Any operational API route returning HTTP 200 without Authorization header or session cookie.
- Server restart auto-generating or overwriting any user password.
- Any non-owner user successfully creating users, deactivating accounts, or launching estate-wide scans.
- Deactivated user account accessing any API endpoint before token expiration.
