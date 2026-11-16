"""Authentication, sole-owner bootstrap, users and asset grants.

- Browser sessions: HttpOnly session cookie + double-submit CSRF cookie.
- Programmatic clients: Authorization: Bearer <token> (never via URL).
- Only the sole owner manages users, grants and the audit trail.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import (
    extract_token,
    get_current_active_user,
    is_sole_owner,
    require_admin,
    require_owner,
)
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.user import RevokedToken, User, UserAssetGrant, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Roles the owner may assign. OWNER is unique; legacy ADMIN/SUPER_ADMIN are not issuable.
ASSIGNABLE_ROLES = {
    UserRole.DEVELOPER.value,
    UserRole.VIEWER.value,
    UserRole.OPERATOR.value,
    UserRole.SECURITY_LEAD.value,
}
GRANT_ACTIONS = {"READ", "SCAN", "TRIAGE", "REPORT"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., max_length=256)
    password: str = Field(..., min_length=12, max_length=128)


class BootstrapResponse(BaseModel):
    message: str
    username: str
    email: str
    id: str


class UserProfile(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str = "VIEWER"
    is_superuser: bool = False
    is_ultra_admin: bool = False
    is_owner: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class UserInviteRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., max_length=256)
    password: str = Field(..., min_length=12, max_length=128)
    role: str = Field(default="DEVELOPER")


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class AssetGrantRequest(BaseModel):
    asset_id: uuid.UUID
    permissions: str = Field(default="READ,SCAN")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _audit(db: AsyncSession, actor: Optional[User], action: str, details: str, request: Request,
           username: Optional[str] = None) -> None:
    db.add(AdminAuditLog(
        user_id=str(actor.id) if actor else None,
        username=(actor.username if actor else (username or "anonymous"))[:128],
        action=action,
        details=details[:1024],
        ip_address=_client_ip(request),
    ))


def _set_session_cookies(response: Response, token: str) -> None:
    common = dict(
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        secure=settings.session_cookie_secure,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    response.set_cookie(settings.SESSION_COOKIE_NAME, token, httponly=True, **common)
    # Readable by same-origin JS so it can echo it back in the X-CSRF-Token header.
    response.set_cookie(settings.CSRF_COOKIE_NAME, secrets.token_urlsafe(32), httponly=False, **common)
    response.headers["Cache-Control"] = "no-store"


def _clear_session_cookies(response: Response) -> None:
    for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
        response.delete_cookie(name, path="/", secure=settings.session_cookie_secure,
                               samesite=settings.SESSION_COOKIE_SAMESITE)


def _profile(user: User) -> dict:
    owner = is_sole_owner(user)
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": (user.role or "VIEWER").upper(),
        "is_superuser": owner,
        "is_ultra_admin": owner,
        "is_owner": owner,
    }


def _issue(user: User) -> str:
    owner = is_sole_owner(user)
    return create_access_token(
        subject=str(user.id),
        role=(user.role or "VIEWER").upper(),
        is_superuser=owner,
        claims={"username": user.username, "email": user.email},
    )


async def bootstrap_owner(db: AsyncSession, username: str, email: str, password: str) -> User:
    """Atomic one-time creation of the sole owner. Shared by HTTP (token-gated) and CLI."""
    existing = await db.execute(
        select(User.id).where(or_(
            User.role.in_([UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]),
            User.is_superuser == True,  # noqa: E712
            User.id == uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID),
        )).limit(1)
    )
    if existing.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="System bootstrap has already been completed and is permanently locked.")
    owner_email = email.strip().lower()
    if owner_email != settings.SOLE_OWNER_EMAIL.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Bootstrap is restricted solely to the configured sole owner identity.")
    if len(password) < 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Owner password must be at least 12 characters.")
    dup = await db.execute(select(User.id).where(or_(User.username == username.strip(), User.email == owner_email)))
    if dup.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists.")
    owner = User(
        id=uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID),
        username=username.strip(),
        email=owner_email,
        hashed_password=get_password_hash(password),
        role=UserRole.OWNER.value,
        is_active=True,
        is_superuser=True,
    )
    db.add(owner)
    db.add(AdminAuditLog(
        user_id=str(owner.id), username=owner.username, action="SYSTEM_BOOTSTRAP",
        details=f"Sole owner bound to immutable id={owner.id}. Bootstrap locked.", ip_address="local",
    ))
    # Primary-key uniqueness on the fixed owner ID makes concurrent bootstraps atomic.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # The immutable owner primary key arbitrates concurrent first requests.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="System bootstrap has already been completed or the account already exists.")
    return owner


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_initial_admin(
    payload: BootstrapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_bootstrap_token: Optional[str] = Header(default=None),
) -> Any:
    """Disabled (404) unless the operator configured SENTINEL_BOOTSTRAP_TOKEN out-of-band.
    Preferred path: `python -m backend.app.cli bootstrap-owner` on the private host."""
    expected = settings.BOOTSTRAP_TOKEN
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not x_bootstrap_token or not hmac.compare_digest(x_bootstrap_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")
    owner = await bootstrap_owner(db, payload.username, payload.email, payload.password)
    return BootstrapResponse(message="Sole owner created; bootstrap locked.", username=owner.username,
                             email=owner.email, id=str(owner.id))


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Any:
    identifier = password = None
    content_type = request.headers.get("content-type", "")
    try:
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            identifier = form.get("email") or form.get("username") or form.get("account")
            password = form.get("password")
        else:
            body = await request.json()
            if isinstance(body, dict):
                identifier = body.get("email") or body.get("username") or body.get("account")
                password = body.get("password")
    except Exception:
        pass

    if not identifier or not password or not isinstance(identifier, str) or not isinstance(password, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Username/email and password are required")

    identifier = identifier.strip()
    result = await db.execute(select(User).where(or_(User.username == identifier, User.email == identifier.lower())))
    user = result.scalars().first()

    if not user or not verify_password(password, user.hashed_password):
        _audit(db, user, "LOGIN_FAILED", "Invalid credentials", request, username="unknown" if not user else None)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username/email or password",
                            headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active:
        _audit(db, user, "LOGIN_DENIED_DISABLED", "Login attempt on disabled account", request)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="User account is inactive. Please contact the system owner.")

    _audit(db, user, "LOGIN_SUCCESS", f"role={(user.role or '').upper()}", request)
    await db.commit()

    token = _issue(user)
    _set_session_cookies(response, token)
    # access_token is returned for programmatic bearer clients; the web console relies
    # on the HttpOnly cookie and never stores it.
    return {"access_token": token, "token_type": "bearer", "user": _profile(user)}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Server-side revocation of the presented session and every earlier session of this
    user; applies equally to API calls, SSE streams and downloads."""
    token, _ = extract_token(request)
    now = datetime.now(timezone.utc)
    if token:
        payload = decode_access_token(token) or {}
        db.add(RevokedToken(
            id=uuid.uuid4(),
            token_jti=payload.get("jti") or str(uuid.uuid4()),
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            revoked_at=now,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if payload.get("exp") else None,
            user_id=str(current_user.id),
            reason="USER_LOGOUT",
        ))
    current_user.tokens_valid_after = now
    _audit(db, current_user, "LOGOUT", "Session revoked server-side", request)
    await db.commit()
    _clear_session_cookies(response)
    return {"message": "Successfully logged out and session revoked."}


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_active_user)) -> Any:
    return _profile(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(response: Response, current_user: User = Depends(get_current_active_user)) -> Any:
    token = _issue(current_user)
    _set_session_cookies(response, token)
    return {"access_token": token, "token_type": "bearer", "user": _profile(current_user)}


# ---------------------------------------------------------------------------
# Owner-only administration
# ---------------------------------------------------------------------------

@router.get("/audit")
async def list_admin_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    user_id: Optional[str] = Query(None, description="Only activity performed by this user ID"),
    action: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Who did what, and when (sole owner only)."""
    stmt = select(AdminAuditLog)
    if user_id:
        stmt = stmt.where(AdminAuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action.upper())
    stmt = stmt.order_by(AdminAuditLog.created_at.desc()).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(i.id),
            "user_id": i.user_id,
            "username": i.username,
            "action": i.action,
            "details": i.details,
            "ip_address": i.ip_address,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


@router.get("/users")
async def list_users(current_user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)) -> Any:
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "is_owner": is_sole_owner(u),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/invite", status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: UserInviteRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    clean_username = payload.username.strip()
    clean_email = payload.email.strip().lower()
    role_str = payload.role.upper()
    if role_str not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Role must be one of {sorted(ASSIGNABLE_ROLES)}. OWNER is unique and immutable.")
    dup = await db.execute(select(User.id).where(or_(User.username == clean_username, User.email == clean_email)))
    if dup.first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this username or email already exists.")

    new_user = User(
        id=uuid.uuid4(),
        username=clean_username,
        email=clean_email,
        hashed_password=get_password_hash(payload.password),
        role=role_str,
        is_active=True,
        is_superuser=False,
    )
    db.add(new_user)
    _audit(db, current_user, "USER_INVITE", f"user_id={new_user.id} role={role_str}", request)
    await db.commit()
    return {"id": str(new_user.id), "username": new_user.username, "email": new_user.email,
            "role": new_user.role, "is_active": new_user.is_active}


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Enable/disable an account. Disabling invalidates every session immediately."""
    if str(user_id) == settings.SOLE_OWNER_ACCOUNT_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sole owner account cannot be deactivated.")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = payload.is_active
    if not payload.is_active:
        user.tokens_valid_after = datetime.now(timezone.utc)
    _audit(db, current_user, "USER_STATUS_CHANGE", f"user_id={user.id} is_active={payload.is_active}", request)
    await db.commit()
    return {
        "id": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "message": f"User account {'activated' if user.is_active else 'deactivated with sessions revoked'}.",
    }


@router.post("/users/{user_id}/grants", status_code=status.HTTP_201_CREATED)
async def create_asset_grant(
    user_id: uuid.UUID,
    payload: AssetGrantRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Grant a user explicit actions (READ, SCAN, TRIAGE, REPORT) on one asset."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if is_sole_owner(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner already has estate-wide access.")
    if await db.get(Asset, payload.asset_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    perms = {p.strip().upper() for p in payload.permissions.split(",") if p.strip()} | {"READ"}
    unknown = perms - GRANT_ACTIONS
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Unknown permissions {sorted(unknown)}; allowed {sorted(GRANT_ACTIONS)}")
    grant = UserAssetGrant(
        id=uuid.uuid4(),
        user_id=user.id,
        asset_id=payload.asset_id,
        permissions=",".join(sorted(perms)),
        granted_by=str(current_user.id),
    )
    db.add(grant)
    _audit(db, current_user, "GRANT_CREATE",
           f"grant_id={grant.id} user_id={user.id} asset_id={payload.asset_id} perms={grant.permissions}", request)
    await db.commit()
    return {"id": str(grant.id), "user_id": str(grant.user_id), "asset_id": str(grant.asset_id),
            "permissions": grant.permissions}


@router.delete("/users/{user_id}/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_grant(
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    res = await db.execute(select(UserAssetGrant).where(UserAssetGrant.id == grant_id, UserAssetGrant.user_id == user_id))
    grant = res.scalars().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    _audit(db, current_user, "GRANT_REVOKE", f"grant_id={grant.id} user_id={user_id} asset_id={grant.asset_id}", request)
    await db.delete(grant)
    await db.commit()


@router.get("/users/{user_id}/grants")
async def list_user_grants(
    user_id: uuid.UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    grants = (await db.execute(select(UserAssetGrant).where(UserAssetGrant.user_id == user_id))).scalars().all()
    return [
        {
            "id": str(g.id),
            "user_id": str(g.user_id),
            "asset_id": str(g.asset_id),
            "permissions": g.permissions,
            "granted_by": g.granted_by,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        }
        for g in grants
    ]
