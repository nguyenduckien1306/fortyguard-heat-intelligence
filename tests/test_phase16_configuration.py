"""Phase 16 — Configuration & Environment Hardening Test Suite.

Verifies:
1. Strict fail-fast validation for invalid URLs, schemes, environments, log levels, and timeouts.
2. Safe redaction of API keys in __repr__, __str__, and dictionary exports.
3. Capacity limits and operational boundaries enforcement.
4. Parsing from environment variables with type safety.
5. Cache clearing and dynamic environment reloading.
"""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from backend.config import (
    VALID_ENVIRONMENTS,
    VALID_LOG_LEVELS,
    ConfigurationError,
    Settings,
    get_settings,
    reset_settings_cache,
)


class TestSettingsDefaultsAndTypes:
    """Test default values and field types of Settings."""

    def test_default_settings_instantiation(self):
        """Default Settings instantiates cleanly with valid defaults."""
        s = Settings()
        assert s.app_version == "0.1.0"
        assert s.service_name == "Urban Heat Intelligence API"
        assert s.environment == "development"
        assert s.log_level == "INFO"
        assert s.max_history_records == 50
        assert s.max_watchlists == 20
        assert s.max_alerts == 50
        assert s.max_queue_items == 100
        assert s.polling_timeout_seconds == 120.0
        assert s.polling_interval_seconds == 2.0

    def test_api_configured_property_false_when_empty(self):
        """fortyguard_api_configured is False when api_key is empty."""
        s = Settings(FORTYGUARD_API_KEY="")
        assert s.fortyguard_api_configured is False

    def test_api_configured_property_true_when_set(self):
        """fortyguard_api_configured is True when api_key is non-empty string."""
        s = Settings(FORTYGUARD_API_KEY="sk-test-key-12345")
        assert s.fortyguard_api_configured is True


class TestBaseUrlValidation:
    """Test validation of FortyGuard provider base URL."""

    @pytest.mark.parametrize("valid_url", [
        "https://api.fortyguard.com",
        "http://localhost:8000",
        "https://stage.api.fortyguard.com/v1",
        "http://127.0.0.1:8080",
    ])
    def test_valid_base_urls_accepted(self, valid_url: str):
        """Valid http and https URLs are accepted without error."""
        s = Settings(FORTYGUARD_BASE_URL=valid_url)
        assert s.fortyguard_base_url == valid_url.rstrip("/")

    def test_trailing_slash_stripped(self):
        """Trailing slashes are automatically stripped from base_url."""
        s = Settings(FORTYGUARD_BASE_URL="https://api.fortyguard.com/")
        assert s.fortyguard_base_url == "https://api.fortyguard.com"

    @pytest.mark.parametrize("invalid_url", [
        "",
        "   ",
        "ftp://api.fortyguard.com",
        "file:///path/to/api",
        "not_a_url",
        "http://",
    ])
    def test_invalid_base_urls_raise_configuration_error(self, invalid_url: str):
        """Invalid base URLs raise ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(FORTYGUARD_BASE_URL=invalid_url)


class TestEnvironmentAndLogLevelValidation:
    """Test validation of environment and logging level."""

    @pytest.mark.parametrize("env", ["development", "test", "production", "staging"])
    def test_valid_environments_accepted(self, env: str):
        """All valid environment strings are accepted."""
        s = Settings(APP_ENV=env)
        assert s.environment == env

    def test_environment_case_insensitivity(self):
        """Environment names are normalized to lowercase."""
        s = Settings(APP_ENV="PRODUCTION")
        assert s.environment == "production"

    def test_invalid_environment_raises_configuration_error(self):
        """Invalid environment raises ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(APP_ENV="invalid_env_name")

    @pytest.mark.parametrize("lvl", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels_accepted(self, lvl: str):
        """All standard log levels are accepted."""
        s = Settings(LOG_LEVEL=lvl)
        assert s.log_level == lvl

    def test_log_level_case_insensitivity(self):
        """Log levels are normalized to uppercase."""
        s = Settings(LOG_LEVEL="debug")
        assert s.log_level == "DEBUG"

    def test_invalid_log_level_raises_configuration_error(self):
        """Invalid log level raises ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(LOG_LEVEL="VERBOSE")


class TestCapacityAndTimeoutValidation:
    """Test validation of operational capacities and timeouts."""

    @pytest.mark.parametrize("field_name", [
        "MAX_HISTORY_RECORDS",
        "MAX_WATCHLISTS",
        "MAX_ALERTS",
        "MAX_QUEUE_ITEMS",
    ])
    def test_non_positive_capacity_raises_error(self, field_name: str):
        """Zero or negative capacities raise ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(**{field_name: 0})
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(**{field_name: -5})

    def test_non_positive_timeout_raises_error(self):
        """Zero or negative polling timeout raises ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(POLLING_TIMEOUT_SECONDS=0.0)
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(POLLING_TIMEOUT_SECONDS=-10.0)

    def test_non_positive_interval_raises_error(self):
        """Zero or negative polling interval raises ConfigurationError."""
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(POLLING_INTERVAL_SECONDS=0.0)
        with pytest.raises((ConfigurationError, ValueError)):
            Settings(POLLING_INTERVAL_SECONDS=-1.0)


class TestSecretRedactionAndSafety:
    """Test that API keys and secrets are never leaked in representations."""

    def test_empty_api_key_redaction(self):
        """Empty API key displays [NOT_CONFIGURED]."""
        s = Settings(FORTYGUARD_API_KEY="")
        assert s.get_redacted_api_key() == "[NOT_CONFIGURED]"

    def test_short_api_key_redaction(self):
        """Short API key displays [REDACTED]."""
        s = Settings(FORTYGUARD_API_KEY="12345")
        assert s.get_redacted_api_key() == "[REDACTED]"

    def test_standard_api_key_masking(self):
        """Standard API key masks middle characters."""
        s = Settings(FORTYGUARD_API_KEY="fg_secret_token_987654321")
        masked = s.get_redacted_api_key()
        assert masked == "fg_...321"
        assert "secret_token" not in masked

    def test_repr_hides_full_secret(self):
        """__repr__ contains only masked key."""
        s = Settings(FORTYGUARD_API_KEY="super_secret_api_key_xyz999")
        r = repr(s)
        assert "super_secret_api_key_xyz999" not in r
        assert "sup...999" in r

    def test_str_hides_full_secret(self):
        """__str__ contains only masked key."""
        s = Settings(FORTYGUARD_API_KEY="super_secret_api_key_xyz999")
        st = str(s)
        assert "super_secret_api_key_xyz999" not in st

    def test_to_sanitized_dict_redacts_api_key(self):
        """to_sanitized_dict produces safe dictionary without raw secret."""
        s = Settings(FORTYGUARD_API_KEY="super_secret_api_key_xyz999")
        d = s.to_sanitized_dict()
        assert d["fortyguard_api_key"] == "sup...999"
        assert "super_secret_api_key_xyz999" not in str(d)


class TestEnvironmentParsingAndCaching:
    """Test Settings.from_env() and caching semantics."""

    def test_from_env_loads_environment_variables(self):
        """Settings.from_env() reads custom values from environment."""
        with patch.dict(os.environ, {
            "FORTYGUARD_API_KEY": "env_key_test_12345",
            "FORTYGUARD_BASE_URL": "https://custom.api.fortyguard.com",
            "APP_ENV": "production",
            "MAX_ALERTS": "75",
        }):
            s = Settings.from_env()
            assert s.fortyguard_api_key == "env_key_test_12345"
            assert s.fortyguard_base_url == "https://custom.api.fortyguard.com"
            assert s.environment == "production"
            assert s.max_alerts == 75

    def test_from_env_malformed_integer_raises_configuration_error(self):
        """Non-integer in integer environment variable raises ConfigurationError."""
        with patch.dict(os.environ, {"MAX_ALERTS": "not_an_int"}):
            with pytest.raises(ConfigurationError):
                Settings.from_env()

    def test_from_env_malformed_float_raises_configuration_error(self):
        """Non-float in float environment variable raises ConfigurationError."""
        with patch.dict(os.environ, {"POLLING_TIMEOUT_SECONDS": "not_a_float"}):
            with pytest.raises(ConfigurationError):
                Settings.from_env()

    def test_get_settings_cached_and_reset_cache(self):
        """get_settings() returns cached instance, reset_settings_cache() refreshes it."""
        reset_settings_cache()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

        with patch.dict(os.environ, {"APP_ENV": "staging"}):
            reset_settings_cache()
            s3 = get_settings()
            assert s3.environment == "staging"
        reset_settings_cache()
