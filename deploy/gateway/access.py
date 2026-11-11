"""Cloudflare Access verification at the origin (Milestone 6).

When configured, every request reaching the gateway (console pages, API, SSE) must carry a
Cloudflare Access JWT — header `Cf-Access-Jwt-Assertion` or cookie `CF_Authorization` — that:
  * is RS256-signed by a key from the team's JWKS (`https://<team>/cdn-cgi/access/certs`)
  * has `aud` containing the Access application AUD tag
  * has `iss` equal to `https://<team>`
  * is within `nbf`/`exp` (60 s leeway)
The application still enforces its own session, role and asset grants; Access is an outer gate.

Configuration (environment):
  NOOSPIRE_ACCESS_TEAM_DOMAIN   e.g. empire.cloudflareaccess.com   (enables verification)
  NOOSPIRE_ACCESS_AUD           Access application AUD tag
  NOOSPIRE_ACCESS_REQUIRED      "true" -> refuse all traffic if the two values above are missing
  NOOSPIRE_ACCESS_CERTS_URL     override of the JWKS URL (tests / private mirrors)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import httpx
import jwt
from jwt import PyJWK

LEEWAY = 60
JWKS_TTL = 600


class AccessDenied(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class AccessVerifier:
    team_domain: Optional[str] = None
    audience: Optional[str] = None
    required: bool = False
    certs_url: Optional[str] = None
    _keys: Dict[str, PyJWK] = field(default_factory=dict)
    _fetched_at: float = 0.0

    @classmethod
    def from_env(cls) -> "AccessVerifier":
        team = (os.getenv("NOOSPIRE_ACCESS_TEAM_DOMAIN") or "").strip().removeprefix("https://").rstrip("/") or None
        return cls(team_domain=team, audience=(os.getenv("NOOSPIRE_ACCESS_AUD") or "").strip() or None,
                   required=os.getenv("NOOSPIRE_ACCESS_REQUIRED", "false").lower() == "true",
                   certs_url=os.getenv("NOOSPIRE_ACCESS_CERTS_URL") or None)

    @property
    def enabled(self) -> bool:
        return bool(self.team_domain and self.audience)

    @property
    def misconfigured(self) -> bool:
        return self.required and not self.enabled

    @property
    def issuer(self) -> str:
        return f"https://{self.team_domain}"

    def describe(self) -> dict:
        return {"enabled": self.enabled, "required": self.required, "team_domain": self.team_domain,
                "audience_configured": bool(self.audience)}

    async def _jwks(self, force: bool = False) -> Dict[str, PyJWK]:
        if self._keys and not force and time.monotonic() - self._fetched_at < JWKS_TTL:
            return self._keys
        url = self.certs_url or f"{self.issuer}/cdn-cgi/access/certs"
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as c:
            r = await c.get(url)
        r.raise_for_status()
        keys = {}
        for k in r.json().get("keys", []):
            if k.get("kid") and k.get("kty") == "RSA":
                keys[k["kid"]] = PyJWK(k, algorithm="RS256")
        if not keys:
            raise AccessDenied("ACCESS_CERTS_UNAVAILABLE", "Access signing keys could not be loaded")
        self._keys, self._fetched_at = keys, time.monotonic()
        return keys

    def set_keys(self, keys: Dict[str, PyJWK]) -> None:
        """Test hook: preload the key set."""
        self._keys, self._fetched_at = keys, time.monotonic()

    async def verify(self, token: Optional[str]) -> dict:
        if not token:
            raise AccessDenied("ACCESS_TOKEN_MISSING", "Cloudflare Access token missing")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AccessDenied("ACCESS_TOKEN_MALFORMED", "Cloudflare Access token is malformed")
        if header.get("alg") != "RS256":
            raise AccessDenied("ACCESS_TOKEN_ALG", "Unexpected token algorithm")
        kid = header.get("kid")
        try:
            keys = await self._jwks()
            if kid not in keys:
                keys = await self._jwks(force=True)  # key rotation
        except AccessDenied:
            raise
        except Exception:
            raise AccessDenied("ACCESS_CERTS_UNAVAILABLE", "Access signing keys could not be loaded")
        key = keys.get(kid)
        if key is None:
            raise AccessDenied("ACCESS_TOKEN_KID", "Token signed by an unknown key")
        try:
            claims = jwt.decode(token, key=key.key, algorithms=["RS256"], audience=self.audience,
                                issuer=self.issuer, leeway=LEEWAY,
                                options={"require": ["exp", "iat", "iss", "aud"]})
        except jwt.ExpiredSignatureError:
            raise AccessDenied("ACCESS_TOKEN_EXPIRED", "Cloudflare Access session expired; sign in again")
        except jwt.InvalidAudienceError:
            raise AccessDenied("ACCESS_TOKEN_AUDIENCE", "Token audience does not match this application")
        except jwt.InvalidIssuerError:
            raise AccessDenied("ACCESS_TOKEN_ISSUER", "Token issuer does not match the Access team")
        except jwt.PyJWTError:
            raise AccessDenied("ACCESS_TOKEN_INVALID", "Cloudflare Access token is invalid")
        return claims
