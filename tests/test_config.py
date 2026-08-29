"""Tests for configuration loading."""

import os
from unittest.mock import patch

from backend.config import PROJECT_ROOT, Settings, get_settings


def test_project_root_points_to_repository_root() -> None:
    assert PROJECT_ROOT.name == "FortyGuard-Heat-Intelligence"
    assert (PROJECT_ROOT / "main.py").exists()


def test_settings_default_base_url() -> None:
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings.from_env()
        assert settings.fortyguard_base_url == "https://api.fortyguard.com"


def test_settings_api_key_not_configured_when_empty() -> None:
    with patch.dict(os.environ, {"FORTYGUARD_API_KEY": ""}, clear=True):
        settings = Settings.from_env()
        assert settings.fortyguard_api_configured is False


def test_settings_api_key_configured_when_present() -> None:
    with patch.dict(
        os.environ,
        {"FORTYGUARD_API_KEY": "test-key", "FORTYGUARD_BASE_URL": "https://api.example.com"},
        clear=True,
    ):
        settings = Settings.from_env()
        assert settings.fortyguard_api_configured is True
        assert settings.fortyguard_base_url == "https://api.example.com"


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
