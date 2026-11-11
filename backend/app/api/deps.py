"""API Dependency Providers for Noosforge Sentinel.

Exposes standard FastAPI dependency callables for database sessions,
authentication, active user validation, scoped RBAC, and CSRF protection.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import decode_access_token, oauth2_scheme
from backend.app.models.user import RevokedToken, User, UserRole


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Resolves authenticated user from JWT bearer token or session cookie. Returns None if unauthenticated."""
    auth_via_cookie = False
    if not token:
        token = request.cookies.get("sentinel_access_token") or request.cookies.get("access_token")
        if token:
            auth_via_cookie = True

    # Allow query parameter token for native EventSource and stream connections
    if not token and request.query_params.get("token"):
        token = request.query_params.get("token")

    if not token:
        return None

    # If authenticated via cookie on mutation, enforce CSRF (F07)
    if auth_via_cookie and request.method in ("POST", "PUT", "DELETE", "PATCH"):
        csrf_header = request.headers.get("x-csrf-token") or request.headers.get("x-requested-with")
        csrf_cookie = request.cookies.get("csrf_token") or request.cookies.get("sentinel_csrf_token")
        if not csrf_header or (csrf_cookie and csrf_header != csrf_cookie):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed for cookie-authenticated mutation",
            )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check revoked tokens in database (F03)
    jti = payload.get("jti")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if jti:
        revoked = await db.execute(
            select(RevokedToken).where(
                or_(RevokedToken.token_jti == jti, RevokedToken.token_hash == token_hash)
            )
        )
        if revoked.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    username = payload.get("sub") or payload.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(or_(User.username == username, User.email == username))
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
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

    # Extract token from header or cookie for session expiry check
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("sentinel_access_token") or request.cookies.get("access_token")
    if not token and request.query_params.get("token"):
        token = request.query_params.get("token")

    # Enforce session expiry via tokens_valid_after timestamp (F03)
    if token and hasattr(user, "tokens_valid_after") and user.tokens_valid_after:
        payload = decode_access_token(token)
        if payload:
            iat = payload.get("iat")
            if iat:
                if isinstance(iat, (int, float)):
                    token_issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
                elif isinstance(iat, datetime):
                    token_issued_at = iat.replace(tzinfo=timezone.utc) if iat.tzinfo is None else iat.astimezone(timezone.utc)
                else:
                    token_issued_at = None

                tokens_valid_after = user.tokens_valid_after
                if tokens_valid_after is not None:
                    if tokens_valid_after.tzinfo is None:
                        tokens_valid_after = tokens_valid_after.replace(tzinfo=timezone.utc)
                    else:
                        tokens_valid_after = tokens_valid_after.astimezone(timezone.utc)

                if token_issued_at and tokens_valid_after and token_issued_at < tokens_valid_after:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session expired/revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    return user


def require_roles(allowed_roles: List[str]):
    """Scoped RBAC dependency factory (F04)."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
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


require_admin = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN"])
require_operator = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN", "OPERATOR", "SECURITY_LEAD"])
require_viewer = require_roles(["OWNER", "SUPER_ADMIN", "ADMIN", "OPERATOR", "SECURITY_LEAD", "DEVELOPER", "VIEWER", "USER"])


async def verify_csrf(request: Request) -> None:
    """CSRF protection on mutations (F07).
    Validates CSRF tokens or custom headers when browser session cookies are present.
    """
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if request.cookies.get("sentinel_session") or request.cookies.get("access_token"):
            csrf_header = request.headers.get("x-csrf-token") or request.headers.get("x-requested-with")
            csrf_cookie = request.cookies.get("csrf_token")
            if not csrf_header or (csrf_cookie and csrf_header != csrf_cookie):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF verification failed",
                )


__all__ = [
    "get_current_user",
    "get_current_active_user",
    "get_db",
    "require_roles",
    "require_owner",
    "require_admin",
    "require_operator",
    "require_viewer",
    "get_authorized_asset_ids",
    "verify_csrf",
]
