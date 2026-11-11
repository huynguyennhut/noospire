import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    oauth2_scheme,
    verify_password,
)
from backend.app.models.base import AdminAuditLog
from backend.app.models.user import RevokedToken, User, UserAssetGrant, UserRole
from backend.app.api.deps import (
    get_current_active_user,
    get_current_user,
    require_admin,
    require_owner,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    account: Optional[str] = None
    password: str


class BootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., max_length=256)
    password: str = Field(..., min_length=8, max_length=128)


class BootstrapResponse(BaseModel):
    message: str
    username: str
    email: str


class UserProfile(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str = "VIEWER"
    is_superuser: bool = False
    is_ultra_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class AdminAuditResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[str] = None
    username: str
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: str


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_initial_admin(
    payload: BootstrapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Explicit one-time bootstrap mechanism permanently locking after initial admin setup (F02/R5)."""
    # 1. Check if any admin or superuser or owner already exists in inventory
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

    # 3. Check duplicate username/email
    dup = await db.execute(
        select(User).where(
            or_(User.username == payload.username.strip(), User.email == owner_email)
        )
    )
    if dup.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists.",
        )

    sole_owner_uuid = uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID)
    new_admin = User(
        id=sole_owner_uuid,
        username=payload.username.strip(),
        email=owner_email,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.OWNER.value,
        is_active=True,
        is_superuser=True,
    )
    db.add(new_admin)

    # Record permanent bootstrap audit trail
    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = AdminAuditLog(
        user_id=str(new_admin.id),
        username=new_admin.username,
        action="SYSTEM_BOOTSTRAP",
        details=f"Sole owner account bound to {owner_email} with immutable ID {new_admin.id}. Bootstrap permanently locked.",
        ip_address=client_ip,
    )
    db.add(audit)
    await db.commit()

    return BootstrapResponse(
        message="System successfully bootstrapped. Initial administrator account created and bootstrap locked.",
        username=new_admin.username,
        email=new_admin.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    identifier = None
    password = None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            identifier = body.get("email") or body.get("username") or body.get("account")
            password = body.get("password")
        except Exception:
            pass
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            identifier = form.get("email") or form.get("username") or form.get("account")
            password = form.get("password")
        except Exception:
            pass
    else:
        try:
            body = await request.json()
            identifier = body.get("email") or body.get("username") or body.get("account")
            password = body.get("password")
        except Exception:
            try:
                form = await request.form()
                identifier = form.get("email") or form.get("username") or form.get("account")
                password = form.get("password")
            except Exception:
                pass

    if not identifier or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username/email and password are required",
        )

    identifier = identifier.strip()

    # Query database strictly for registered user
    result = await db.execute(
        select(User).where(or_(User.username == identifier, User.email == identifier))
    )
    user = result.scalars().first()

    client_ip = request.client.host if request.client else "127.0.0.1"

    if not user or not verify_password(password, user.hashed_password):
        # Record failed authentication attempt in audit log
        audit_entry = AdminAuditLog(
            user_id=str(user.id) if user else None,
            username=identifier,
            action="LOGIN_FAILED",
            details="Invalid authentication credentials provided",
            ip_address=client_ip,
        )
        db.add(audit_entry)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce active user status in database (F03)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive. Please contact system administrator.",
        )

    # Success audit trail
    user_role = (user.role or "VIEWER").upper()
    audit_entry = AdminAuditLog(
        user_id=str(user.id),
        username=user.username,
        action="LOGIN_SUCCESS",
        details=f"Authenticated as role={user_role}, superuser={user.is_superuser}",
        ip_address=client_ip,
    )
    db.add(audit_entry)
    await db.commit()

    is_ultra = user_role in ("SUPER_ADMIN", "ADMIN") and user.is_superuser

    token = create_access_token(
        subject=user.username,
        role=user_role,
        is_superuser=user.is_superuser,
        claims={"email": user.email, "id": str(user.id), "role": user_role},
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user_role,
            "is_superuser": user.is_superuser,
            "is_ultra_admin": is_ultra,
        },
    }


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Explicit session revocation and token invalidation (F03)."""
    if token:
        payload = decode_access_token(token)
        jti = payload.get("jti") if payload else str(uuid.uuid4())
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = None
        if payload and payload.get("exp"):
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        revocation = RevokedToken(
            id=uuid.uuid4(),
            token_jti=jti,
            token_hash=token_hash,
            revoked_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            user_id=str(current_user.id),
            reason="USER_LOGOUT",
        )
        db.add(revocation)

    # Invalidate all prior sessions issued before this instant
    current_user.tokens_valid_after = datetime.now(timezone.utc)

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit_entry = AdminAuditLog(
        user_id=str(current_user.id),
        username=current_user.username,
        action="LOGOUT",
        details="User logged out; active session and JWT token revoked.",
        ip_address=client_ip,
    )
    db.add(audit_entry)
    await db.commit()

    return {"message": "Successfully logged out and session revoked."}


@router.get("/me", response_model=UserProfile)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Retrieve the authenticated principal profile directly from database."""
    user_role = (current_user.role or "VIEWER").upper()
    is_ultra = user_role in ("SUPER_ADMIN", "ADMIN") and current_user.is_superuser
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "role": user_role,
        "is_superuser": current_user.is_superuser,
        "is_ultra_admin": is_ultra,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Issue a renewed JWT access token for active authenticated user."""
    user_role = (current_user.role or "VIEWER").upper()
    is_ultra = user_role in ("SUPER_ADMIN", "ADMIN") and current_user.is_superuser

    new_token = create_access_token(
        subject=current_user.username,
        role=user_role,
        is_superuser=current_user.is_superuser,
        claims={"email": current_user.email, "id": str(current_user.id), "role": user_role},
    )

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "user": {
            "id": str(current_user.id),
            "username": current_user.username,
            "email": current_user.email,
            "role": user_role,
            "is_superuser": current_user.is_superuser,
            "is_ultra_admin": is_ultra,
        },
    }


@router.get("/audit")
async def list_admin_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve administrator and operator audit trails (Requires ADMIN role)."""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit)
    res = await db.execute(stmt)
    items = res.scalars().all()
    return [
        {
            "id": str(item.id),
            "user_id": item.user_id,
            "username": item.username,
            "action": item.action,
            "details": item.details,
            "ip_address": item.ip_address,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in items
    ]


class UserInviteRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., max_length=256)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="DEVELOPER")


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class AssetGrantRequest(BaseModel):
    asset_id: uuid.UUID
    permissions: str = Field(default="READ,SCAN")


@router.get("/users", dependencies=[Depends(require_owner)])
async def list_users(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all user accounts in the platform (Sole Owner only)."""
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    users = res.scalars().all()
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/invite", dependencies=[Depends(require_owner)], status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: UserInviteRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create or invite a new user/developer account (Sole Owner only)."""
    clean_username = payload.username.strip()
    clean_email = payload.email.strip().lower()

    dup = await db.execute(
        select(User).where(or_(User.username == clean_username, User.email == clean_email))
    )
    if dup.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this username or email already exists.",
        )

    role_str = payload.role.upper()
    if role_str == UserRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign OWNER role. Sole owner authority is immutable.",
        )

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

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = AdminAuditLog(
        user_id=str(current_user.id),
        username=current_user.username,
        action="USER_INVITE",
        details=f"Owner invited user {clean_username} ({clean_email}) with role {role_str}",
        ip_address=client_ip,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_user)

    return {
        "id": str(new_user.id),
        "username": new_user.username,
        "email": new_user.email,
        "role": new_user.role,
        "is_active": new_user.is_active,
    }


@router.patch("/users/{user_id}/status", dependencies=[Depends(require_owner)])
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Activate or deactivate a user account with immediate session invalidation (Sole Owner only)."""
    if str(user_id) == settings.SOLE_OWNER_ACCOUNT_ID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sole owner account cannot be deactivated.",
        )

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = payload.is_active
    if not payload.is_active:
        # Immediate session invalidation (R5 / F03)
        user.tokens_valid_after = datetime.now(timezone.utc)
        revocation = RevokedToken(
            id=uuid.uuid4(),
            token_jti=f"user-deactivated-{uuid.uuid4().hex[:16]}",
            token_hash=f"account-disabled-{user_id}",
            revoked_at=datetime.now(timezone.utc),
            user_id=str(user.id),
            reason="ACCOUNT_DEACTIVATED",
        )
        db.add(revocation)

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = AdminAuditLog(
        user_id=str(current_user.id),
        username=current_user.username,
        action="USER_STATUS_CHANGE",
        details=f"User {user.username} active status set to {payload.is_active}",
        ip_address=client_ip,
    )
    db.add(audit)
    await db.commit()

    return {
        "id": str(user.id),
        "username": user.username,
        "is_active": user.is_active,
        "message": f"User account {'activated' if user.is_active else 'deactivated with sessions revoked'}.",
    }


@router.post("/users/{user_id}/grants", dependencies=[Depends(require_owner)], status_code=status.HTTP_201_CREATED)
async def create_asset_grant(
    user_id: uuid.UUID,
    payload: AssetGrantRequest,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Grant scoped developer explicit access to an asset (Sole Owner only)."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    grant = UserAssetGrant(
        id=uuid.uuid4(),
        user_id=user.id,
        asset_id=payload.asset_id,
        permissions=payload.permissions,
        granted_by=current_user.username,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return {
        "id": str(grant.id),
        "user_id": str(grant.user_id),
        "asset_id": str(grant.asset_id),
        "permissions": grant.permissions,
    }


@router.delete("/users/{user_id}/grants/{grant_id}", dependencies=[Depends(require_owner)], status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_grant(
    user_id: uuid.UUID,
    grant_id: uuid.UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke scoped developer asset access grant (Sole Owner only)."""
    res = await db.execute(select(UserAssetGrant).where(UserAssetGrant.id == grant_id, UserAssetGrant.user_id == user_id))
    grant = res.scalars().first()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await db.delete(grant)
    await db.commit()


@router.get("/users/{user_id}/grants", dependencies=[Depends(require_owner)])
async def list_user_grants(
    user_id: uuid.UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all asset grants for a developer (Sole Owner only)."""
    res = await db.execute(select(UserAssetGrant).where(UserAssetGrant.user_id == user_id))
    grants = res.scalars().all()
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
