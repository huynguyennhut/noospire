"""API dependency providers: authentication, sole-owner enforcement, object scope, CSRF.

Authorization model (pilot):
- FastAPI is the only issuer of identity and permissions. JWT claims are never
  trusted for authorization; the user row and asset grants are re-read per request.
- OWNER: exactly one account, bound to SOLE_OWNER_ACCOUNT_ID + SOLE_OWNER_EMAIL.
  Only the owner manages users/grants and launches estate-wide runs.
- Every other role sees and acts only on assets explicitly granted to it
  (UserAssetGrant.permissions, e.g. "READ,SCAN,TRIAGE").
- Browser sessions use an HttpOnly cookie; cookie-authenticated mutations require a
  double-submit CSRF token. Bearer tokens are accepted only in the Authorization
  header (never in URL query strings).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from datetime import timezone
from typing import FrozenSet, List, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import decode_access_token, token_issued_at_ms
from backend.app.models.user import RevokedToken, User, UserAssetGrant, UserRole

MUTATING_METHODS = ("POST", "PUT", "DELETE", "PATCH")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def extract_token(request: Request) -> tuple[Optional[str], bool]:
    """Return (token, via_cookie). Only Authorization header or the session cookie."""
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        tok = auth_header[7:].strip()
        if tok:
            return tok, False
    cookie_tok = request.cookies.get(settings.SESSION_COOKIE_NAME) or request.cookies.get("sentinel_access_token")
    if cookie_tok:
        return cookie_tok, True
    return None, False


def enforce_csrf(request: Request) -> None:
    """Strict double-submit CSRF check for cookie-authenticated mutations."""
    header = request.headers.get(settings.CSRF_HEADER_NAME) or ""
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME) or ""
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed for cookie-authenticated mutation",
        )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Resolve the authenticated user, or None when no credential is presented."""
    token, via_cookie = extract_token(request)
    if not token:
        return None

    if via_cookie and request.method.upper() in MUTATING_METHODS:
        enforce_csrf(request)

    payload = decode_access_token(token)
    if not payload:
        raise _unauthorized("Could not validate credentials")

    jti = payload.get("jti")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conds = [RevokedToken.token_hash == token_hash]
    if jti:
        conds.append(RevokedToken.token_jti == jti)
    revoked = await db.execute(select(RevokedToken.id).where(or_(*conds)).limit(1))
    if revoked.first() is not None:
        raise _unauthorized("Token has been revoked")

    subject = payload.get("sub")
    if not subject:
        raise _unauthorized("Could not validate credentials")

    user: Optional[User] = None
    try:
        user = await db.get(User, uuid.UUID(str(subject)))
    except (ValueError, TypeError):
        res = await db.execute(select(User).where(or_(User.username == str(subject), User.email == str(subject))))
        user = res.scalars().first()
    if user is None:
        raise _unauthorized("User not found")

    # Session invalidation (logout everywhere / disable / role change).
    if user.tokens_valid_after is not None:
        issued_ms = token_issued_at_ms(payload)
        tva = user.tokens_valid_after
        if tva.tzinfo is None:
            tva = tva.replace(tzinfo=timezone.utc)
        if issued_ms is None or issued_ms < int(tva.timestamp() * 1000):
            raise _unauthorized("Session expired/revoked")

    request.state.token_payload = payload
    request.state.token_hash = token_hash
    request.state.auth_via_cookie = via_cookie
    return user


async def session_still_valid(request: Request, asset_id: Optional[uuid.UUID] = None) -> bool:
    """Re-check a long-lived request (SSE stream) against current server state:
    token not revoked, user active, session not invalidated, asset still granted."""
    from backend.app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            user = await get_current_user(request, db)
        except HTTPException:
            return False
        if user is None or not user.is_active:
            return False
        if asset_id is not None:
            return (await load_scope(user, db)).can(asset_id, "READ")
        return True


async def get_current_active_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    if user is None:
        raise _unauthorized("Not authenticated")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account")
    return user


def is_sole_owner(user: Optional[User]) -> bool:
    """True only for the single bootstrapped owner (immutable ID + verified email + role)."""
    if user is None or not user.is_active:
        return False
    return (
        str(user.id) == settings.SOLE_OWNER_ACCOUNT_ID
        and (user.role or "").upper() in (UserRole.OWNER.value, UserRole.SUPER_ADMIN.value)
        and (user.email or "").lower() == settings.SOLE_OWNER_EMAIL.lower()
    )


def require_roles(allowed_roles: List[str]):
    """Role gate. The sole owner always passes; nobody else gets an implicit bypass."""
    allowed = {r.upper() for r in allowed_roles}

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if is_sole_owner(current_user):
            return current_user
        if (current_user.role or "").upper() not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_user

    return role_checker


async def require_owner(current_user: User = Depends(get_current_active_user)) -> User:
    if not is_sole_owner(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation restricted solely to the system owner.",
        )
    return current_user


# ---------------------------------------------------------------------------
# Object scope (asset grants)
# ---------------------------------------------------------------------------

@dataclass
class AccessScope:
    """Resolved per-request object scope. `estate_wide` only for the sole owner."""
    user: User
    estate_wide: bool
    grants: dict = field(default_factory=dict)  # asset_id -> frozenset(perms)

    @property
    def asset_ids(self) -> Optional[List[uuid.UUID]]:
        return None if self.estate_wide else list(self.grants.keys())

    def can(self, asset_id: Optional[uuid.UUID], action: str = "READ") -> bool:
        if self.estate_wide:
            return True
        if asset_id is None:
            return False
        perms: FrozenSet[str] = self.grants.get(asset_id, frozenset())
        return action.upper() in perms

    def ids_with(self, action: str) -> Optional[List[uuid.UUID]]:
        if self.estate_wide:
            return None
        return [a for a, p in self.grants.items() if action.upper() in p]

    def require(self, asset_id: Optional[uuid.UUID], action: str = "READ") -> None:
        """Raise 404 for unreadable objects (no existence leak), 403 for missing action."""
        if self.estate_wide:
            return
        if not self.can(asset_id, "READ"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        if action.upper() != "READ" and not self.can(asset_id, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing '{action.upper()}' grant for this asset",
            )


async def load_scope(user: User, db: AsyncSession) -> AccessScope:
    if is_sole_owner(user):
        return AccessScope(user=user, estate_wide=True)
    if not user.is_active:
        return AccessScope(user=user, estate_wide=False)
    res = await db.execute(
        select(UserAssetGrant.asset_id, UserAssetGrant.permissions).where(UserAssetGrant.user_id == user.id)
    )
    grants: dict = {}
    for asset_id, perms in res.all():
        p = {x.strip().upper() for x in (perms or "").split(",") if x.strip()}
        p.add("READ")  # any grant implies read
        grants[asset_id] = frozenset(grants.get(asset_id, frozenset()) | p)
    return AccessScope(user=user, estate_wide=False, grants=grants)


async def get_scope(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccessScope:
    return await load_scope(current_user, db)


async def get_authorized_asset_ids(user: User, db: AsyncSession) -> Optional[List[uuid.UUID]]:
    """Backward-compatible helper: None = estate-wide (owner only), else granted IDs."""
    return (await load_scope(user, db)).asset_ids


# Global administration has no per-asset grant. Legacy role names or superuser
# flags cannot confer it; keep the dependency name for existing route imports.
require_admin = require_owner
require_operator = require_roles(
    [
        UserRole.OWNER.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.ADMIN.value,
        UserRole.OPERATOR.value,
        UserRole.SECURITY_LEAD.value,
        UserRole.DEVELOPER.value,
    ]
)
require_viewer = require_roles(
    [
        UserRole.OWNER.value,
        UserRole.SUPER_ADMIN.value,
        UserRole.ADMIN.value,
        UserRole.OPERATOR.value,
        UserRole.SECURITY_LEAD.value,
        UserRole.DEVELOPER.value,
        UserRole.VIEWER.value,
        UserRole.USER.value,
    ]
)


async def verify_csrf(request: Request) -> None:
    """Explicit dependency variant (kept for existing callers)."""
    if request.method.upper() in MUTATING_METHODS and (request.cookies.get(settings.SESSION_COOKIE_NAME) or request.cookies.get("sentinel_access_token")):
        if not (request.headers.get("authorization") or "").lower().startswith("bearer "):
            enforce_csrf(request)


__all__ = [
    "AccessScope",
    "extract_token",
    "get_current_user",
    "get_current_active_user",
    "get_db",
    "get_scope",
    "is_sole_owner",
    "load_scope",
    "require_roles",
    "require_owner",
    "require_admin",
    "require_operator",
    "require_viewer",
    "get_authorized_asset_ids",
    "verify_csrf",
]
