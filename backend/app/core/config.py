import os
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    PROJECT_NAME: str = "NOOSFORGE Security Intelligence"
    PLATFORM_TARGET: str = "Empire Educational Ecosystem"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    DEFAULT_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # Persistence Layer: SQLite (zero external dep) or PostgreSQL
    DATABASE_URL: str = os.getenv("SENTINEL_DATABASE_URL", "sqlite+aiosqlite:///./noospire.db")

    # Security & JWT: Dynamic Secret Key (zero hardcoded static keys in codebase)
    SECRET_KEY: str = os.getenv("SENTINEL_SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Sole Owner Authority (R5)
    SOLE_OWNER_EMAIL: str = os.getenv("SENTINEL_SOLE_OWNER_EMAIL", "dangnhutnguyen0910@gmail.com")
    SOLE_OWNER_ACCOUNT_ID: str = os.getenv(
        "SENTINEL_SOLE_OWNER_ACCOUNT_ID", "00000000-0000-0000-0000-000000000001"
    )

    # Initial Admin Configuration (No hardcoded passwords in source code)
    ADMIN_USERNAME: str = os.getenv("SENTINEL_ADMIN_USER", "admin")
    ADMIN_PASSWORD: Optional[str] = os.getenv("SENTINEL_ADMIN_PASSWORD", None)
    ULTRA_ADMIN_EMAIL: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_EMAIL", None)
    ULTRA_ADMIN_PASS: Optional[str] = os.getenv("SENTINEL_ULTRA_ADMIN_PASS", None)
    ULTRA_ADMIN_ROLE: str = os.getenv("SENTINEL_ULTRA_ADMIN_ROLE", "SUPER_ADMIN")

    # Task Dispatcher Mode: "async_worker" or "celery"
    DISPATCHER_MODE: str = os.getenv("SENTINEL_DISPATCHER_MODE", "async_worker")
    MAX_CONCURRENT_SCANS: int = int(os.getenv("SENTINEL_MAX_CONCURRENT_SCANS", "4"))
    DEFAULT_SCAN_TIMEOUT: int = int(os.getenv("SENTINEL_SCAN_TIMEOUT", "600"))

    # SSRF & Egress Protection (Defaults strictly to False for security)
    SSRF_ALLOW_PRIVATE_TARGETS: bool = os.getenv("SENTINEL_SSRF_ALLOW_PRIVATE", "false").lower() in ("true", "1", "yes")

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # Environment & Development Mode
    ENVIRONMENT: str = os.getenv("SENTINEL_ENV", os.getenv("ENVIRONMENT", "development"))
    DEBUG: bool = os.getenv("SENTINEL_DEBUG", os.getenv("DEBUG", "false" if os.getenv("SENTINEL_ENV", os.getenv("ENVIRONMENT", "development")).lower() in ("production", "prod") else "true")).lower() in ("true", "1", "yes")
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
            # In non-production, generate dynamic cryptographic secret if not provided or insecure default
            if not self.SECRET_KEY or self.SECRET_KEY in (
                "noospire-super-secret-key-change-in-production-2026",
                "dev_insecure_default_secret_key_change_in_production",
                "secret",
            ):
                import secrets
                self.SECRET_KEY = secrets.token_urlsafe(32)
        return self

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in ("development", "dev", "test")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")


settings = Settings()
