import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)


def get_password_hash(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    # Stored as salt_hex:key_hex
    return f"{salt.hex()}:{key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored salt:key hash."""
    try:
        parts = hashed_password.split(":")
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected_key = bytes.fromhex(parts[1])
        calculated_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(expected_key, calculated_key)
    except Exception:
        return False


def create_access_token(
    subject: Union[str, Any],
    role: str = "VIEWER",
    is_superuser: bool = False,
    claims: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Scopes derived from role
    role_upper = role.upper()
    if role_upper in ("ADMIN", "SUPER_ADMIN"):
        scopes = ["admin", "operator", "viewer"]
    elif role_upper in ("OPERATOR", "SECURITY_LEAD"):
        scopes = ["operator", "viewer"]
    else:
        scopes = ["viewer"]

    to_encode = {
        "exp": expire,
        "iat": now_utc,
        "jti": str(uuid.uuid4()),
        "sub": str(subject),
        "username": str(subject),
        "role": role_upper,
        "scopes": scopes,
        "is_superuser": is_superuser or (role_upper in ("ADMIN", "SUPER_ADMIN")),
    }
    if claims:
        to_encode.update(claims)
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

