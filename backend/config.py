"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

VALID_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test", "production", "staging"})
VALID_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigurationError(ValueError):
    """Raised when an application setting or environment configuration is invalid."""


class Settings(BaseModel):
    """Typed and hardened application settings."""

    fortyguard_api_key: str = Field(default="", alias="FORTYGUARD_API_KEY")
    fortyguard_base_url: str = Field(
        default="https://api.fortyguard.com",
        alias="FORTYGUARD_BASE_URL",
    )
    app_version: str = "0.1.0"
    service_name: str = "Urban Heat Intelligence API"
    environment: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Operational Capacities & Limits
    max_history_records: int = Field(default=50, alias="MAX_HISTORY_RECORDS")
    max_watchlists: int = Field(default=20, alias="MAX_WATCHLISTS")
    max_alerts: int = Field(default=50, alias="MAX_ALERTS")
    max_queue_items: int = Field(default=100, alias="MAX_QUEUE_ITEMS")

    # Polling & Execution Timeouts
    polling_timeout_seconds: float = Field(default=120.0, alias="POLLING_TIMEOUT_SECONDS")
    polling_interval_seconds: float = Field(default=2.0, alias="POLLING_INTERVAL_SECONDS")

    model_config = {"populate_by_name": True}

    @field_validator("fortyguard_base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate that base_url has a valid http/https scheme and host."""
        if not v or not v.strip():
            raise ConfigurationError("FORTYGUARD_BASE_URL cannot be empty.")
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConfigurationError(f"Invalid FORTYGUARD_BASE_URL scheme or host: '{v}'")
        return v.rstrip("/")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        norm = v.lower().strip()
        if norm not in VALID_ENVIRONMENTS:
            raise ConfigurationError(
                f"Invalid APP_ENV: '{v}'. Must be one of {sorted(VALID_ENVIRONMENTS)}"
            )
        return norm

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        norm = v.upper().strip()
        if norm not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid LOG_LEVEL: '{v}'. Must be one of {sorted(VALID_LOG_LEVELS)}"
            )
        return norm

    @field_validator("max_history_records", "max_watchlists", "max_alerts", "max_queue_items")
    @classmethod
    def validate_positive_capacity(cls, v: int) -> int:
        """Validate positive integer capacity."""
        if v <= 0:
            raise ConfigurationError(f"Capacity limit must be positive, got {v}")
        return v

    @field_validator("polling_timeout_seconds", "polling_interval_seconds")
    @classmethod
    def validate_positive_timeout(cls, v: float) -> float:
        """Validate positive timeout value."""
        if v <= 0:
            raise ConfigurationError(f"Timeout values must be positive, got {v}")
        return float(v)

    @property
    def fortyguard_api_configured(self) -> bool:
        """Return True when a FortyGuard API key is present."""
        return bool(self.fortyguard_api_key.strip())

    def get_redacted_api_key(self) -> str:
        """Return a safely masked representation of the API key."""
        key = self.fortyguard_api_key.strip()
        if not key:
            return "[NOT_CONFIGURED]"
        if len(key) <= 6:
            return "[REDACTED]"
        return f"{key[:3]}...{key[-3:]}"

    def to_sanitized_dict(self) -> dict[str, Any]:
        """Return dictionary representation with all sensitive secrets redacted."""
        return {
            "service_name": self.service_name,
            "app_version": self.app_version,
            "environment": self.environment,
            "log_level": self.log_level,
            "fortyguard_base_url": self.fortyguard_base_url,
            "fortyguard_api_configured": self.fortyguard_api_configured,
            "fortyguard_api_key": self.get_redacted_api_key(),
            "max_history_records": self.max_history_records,
            "max_watchlists": self.max_watchlists,
            "max_alerts": self.max_alerts,
            "max_queue_items": self.max_queue_items,
            "polling_timeout_seconds": self.polling_timeout_seconds,
            "polling_interval_seconds": self.polling_interval_seconds,
        }

    def __repr__(self) -> str:
        """Safe representation hiding secrets."""
        return (
            f"Settings(service='{self.service_name}', version='{self.app_version}', "
            f"env='{self.environment}', base_url='{self.fortyguard_base_url}', "
            f"api_key='{self.get_redacted_api_key()}')"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables with fail-fast validation."""
        def _get_int(key: str, default: int) -> int:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                raise ConfigurationError(f"Environment variable {key} must be an integer, got '{raw}'")

        def _get_float(key: str, default: float) -> float:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError:
                raise ConfigurationError(f"Environment variable {key} must be a number, got '{raw}'")

        return cls(
            FORTYGUARD_API_KEY=os.getenv("FORTYGUARD_API_KEY", ""),
            FORTYGUARD_BASE_URL=os.getenv("FORTYGUARD_BASE_URL", "https://api.fortyguard.com"),
            APP_ENV=os.getenv("APP_ENV", "development"),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
            MAX_HISTORY_RECORDS=_get_int("MAX_HISTORY_RECORDS", 50),
            MAX_WATCHLISTS=_get_int("MAX_WATCHLISTS", 20),
            MAX_ALERTS=_get_int("MAX_ALERTS", 50),
            MAX_QUEUE_ITEMS=_get_int("MAX_QUEUE_ITEMS", 100),
            POLLING_TIMEOUT_SECONDS=_get_float("POLLING_TIMEOUT_SECONDS", 120.0),
            POLLING_INTERVAL_SECONDS=_get_float("POLLING_INTERVAL_SECONDS", 2.0),
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings.from_env()


def reset_settings_cache() -> None:
    """Clear cached settings instance (useful for testing environment changes)."""
    get_settings.cache_clear()
