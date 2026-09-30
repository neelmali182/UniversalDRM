"""Application configuration loaded from environment variables (§22.3)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "")
    if val == "":
        return default
    return val.lower() in ("1", "true", "yes")


@dataclass
class Settings:
    """Runtime settings, sourced from environment variables.

    All secrets must come from env vars or a secrets manager — never
    committed to source control (§22.3, §28 rule 2).
    """
    # Application
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))

    # Database
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql+asyncpg://udrm:udrm@localhost:5432/universaldrm"
    ))

    # Redis
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))

    # Object storage
    storage_provider: str = field(default_factory=lambda: _env("STORAGE_PROVIDER", "local"))
    storage_endpoint: str = field(default_factory=lambda: _env("STORAGE_ENDPOINT", "http://minio:9000"))
    storage_bucket: str = field(default_factory=lambda: _env("STORAGE_BUCKET", "universaldrm"))
    storage_local_dir: str = field(default_factory=lambda: _env(
        "STORAGE_LOCAL_DIR", str(Path.home() / ".universaldrm" / "objects")
    ))

    # Key management
    kms_provider: str = field(default_factory=lambda: _env("KMS_PROVIDER", "local"))

    # TTLs (seconds)
    session_ttl: int = field(default_factory=lambda: _env_int("SESSION_TTL", 600))
    resource_token_ttl: int = field(default_factory=lambda: _env_int("RESOURCE_TOKEN_TTL", 60))
    share_ttl: int = field(default_factory=lambda: _env_int("SHARE_TTL", 3600))
    otp_ttl: int = field(default_factory=lambda: _env_int("OTP_TTL", 600))

    # Upload limits
    max_upload_mb: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_MB", 500))

    # Security
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "change-me-in-production"))
    allowed_origins: list[str] = field(default_factory=lambda: [
        o.strip() for o in _env("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    ])

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


# Module-level singleton — import this in routes and services
settings = Settings()
