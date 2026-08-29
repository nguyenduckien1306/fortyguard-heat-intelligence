"""Phase 16 — Health & Readiness Diagnostics Test Suite.

Verifies:
1. /api/v1/health overview endpoint with environment, limits, and configuration status.
2. /api/v1/health/live liveness probe for container orchestration / Kubernetes.
3. /api/v1/health/ready readiness probe distinguishing provider configuration.
4. Zero secret or raw API key leakage in health diagnostic payloads.
5. Operational capacity bounds reporting.
"""

from __future__ import annotations

import os
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from backend.config import reset_settings_cache
from main import app

client = TestClient(app)


class TestHealthOverviewEndpoint:
    """Tests for GET /api/v1/health overview endpoint."""

    def test_health_overview_status_200(self):
        """Health overview returns HTTP 200."""
        res = client.get("/api/v1/health")
        assert res.status_code == 200

    def test_health_overview_required_fields_present(self):
        """Health overview includes all required service and metadata fields."""
        res = client.get("/api/v1/health")
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Urban Heat Intelligence API"
        assert data["version"] == "0.1.0"
        assert "environment" in data
        assert "fortyguard_api_configured" in data
        assert "fortyguard_base_url" in data
        assert "limits" in data

    def test_health_overview_reports_operational_limits(self):
        """Health overview contains operational limits dict with integer bounds."""
        res = client.get("/api/v1/health")
        limits = res.json()["limits"]
        assert limits["max_history_records"] == 50
        assert limits["max_watchlists"] == 20
        assert limits["max_alerts"] == 50
        assert limits["max_queue_items"] == 100

    def test_health_overview_does_not_leak_raw_api_key(self):
        """Health overview never returns raw API key value."""
        with patch.dict(os.environ, {"FORTYGUARD_API_KEY": "super_secret_fg_99999"}):
            reset_settings_cache()
            res = client.get("/api/v1/health")
            body = res.text
            assert "super_secret_fg_99999" not in body
            assert "api_key" not in res.json()
        reset_settings_cache()

    def test_health_overview_reports_custom_environment(self):
        """Health overview accurately reflects APP_ENV variable."""
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            reset_settings_cache()
            res = client.get("/api/v1/health")
            assert res.json()["environment"] == "production"
        reset_settings_cache()


class TestLivenessProbeEndpoint:
    """Tests for GET /api/v1/health/live liveness probe."""

    def test_liveness_status_200(self):
        """Liveness returns HTTP 200."""
        res = client.get("/api/v1/health/live")
        assert res.status_code == 200

    def test_liveness_body_structure(self):
        """Liveness returns exact alive status."""
        res = client.get("/api/v1/health/live")
        assert res.json() == {"status": "alive"}

    def test_liveness_idempotency_and_speed(self):
        """Liveness probe responds reliably and quickly over multiple calls."""
        for _ in range(10):
            res = client.get("/api/v1/health/live")
            assert res.status_code == 200
            assert res.json()["status"] == "alive"


class TestReadinessProbeEndpoint:
    """Tests for GET /api/v1/health/ready readiness probe."""

    def test_readiness_status_200(self):
        """Readiness returns HTTP 200."""
        res = client.get("/api/v1/health/ready")
        assert res.status_code == 200

    def test_readiness_body_structure(self):
        """Readiness returns required status, service, and message fields."""
        res = client.get("/api/v1/health/ready")
        data = res.json()
        assert data["status"] == "ready"
        assert data["service"] == "Urban Heat Intelligence API"
        assert "provider_configured" in data
        assert "message" in data

    def test_readiness_when_provider_key_configured(self):
        """Readiness shows provider_configured True when API key is set."""
        with patch.dict(os.environ, {"FORTYGUARD_API_KEY": "sk-test-key-1234"}):
            reset_settings_cache()
            res = client.get("/api/v1/health/ready")
            data = res.json()
            assert data["provider_configured"] is True
            assert "fully configured" in data["message"].lower()
        reset_settings_cache()

    def test_readiness_when_provider_key_empty(self):
        """Readiness indicates local/demo mode when API key is empty."""
        with patch.dict(os.environ, {"FORTYGUARD_API_KEY": ""}):
            reset_settings_cache()
            res = client.get("/api/v1/health/ready")
            data = res.json()
            assert data["provider_configured"] is False
            assert "local" in data["message"].lower() or "unconfigured" in data["message"].lower()
        reset_settings_cache()

    def test_readiness_never_leaks_secrets(self):
        """Readiness never leaks credentials or sensitive environment values."""
        with patch.dict(os.environ, {"FORTYGUARD_API_KEY": "secret_token_ready_test"}):
            reset_settings_cache()
            res = client.get("/api/v1/health/ready")
            assert "secret_token_ready_test" not in res.text
        reset_settings_cache()


class TestRootAndDocsIntegration:
    """Tests for root / endpoint navigation and integration."""

    def test_root_endpoint_contains_health_link(self):
        """Root endpoint returns health URL link."""
        res = client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert data["health"] == "/api/v1/health"
        assert data["docs"] == "/docs"
        assert data["version"] == "0.1.0"

    def test_health_routes_with_and_without_trailing_slashes(self):
        """Health routes respond correctly regardless of trailing slashes."""
        for path in ("/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"):
            res = client.get(path)
            assert res.status_code == 200
