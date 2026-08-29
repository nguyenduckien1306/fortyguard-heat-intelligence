"""Tests for error classification and status UX consistency."""

from __future__ import annotations

from frontend.utils.errors import classify_user_error


def test_classify_expired_error() -> None:
    err = classify_user_error("The report download link has expired.", status_code=410)
    assert err.category == "Report Expired"
    assert "expired" in err.message.lower()
    assert err.icon == "⌛"


def test_classify_auth_error() -> None:
    err = classify_user_error("FortyGuard API key is not configured.", status_code=401)
    assert err.category == "Authentication Error"
    assert err.icon == "🔑"


def test_classify_not_found_error() -> None:
    err = classify_user_error("Endpoint not found", status_code=404)
    assert err.category == "Resource Not Found"
    assert err.icon == "🔍"


def test_classify_network_error() -> None:
    err = classify_user_error("Unable to reach the FastAPI backend.")
    assert err.category == "Network Error"
    assert err.icon == "📡"


def test_classify_rate_limit_error() -> None:
    err = classify_user_error("Rate limit exceeded", status_code=429)
    assert err.category == "Rate Limited"
    assert err.icon == "⏱️"


def test_classify_processing_error() -> None:
    err = classify_user_error("Task is still processing. Report is not ready yet.", status_code=409)
    assert err.category == "Processing"
    assert err.icon == "⏳"


def test_classify_validation_error() -> None:
    err = classify_user_error("Please select at least one analysis category.", status_code=422)
    assert err.category == "Validation Error"
    assert err.icon == "⚠️"
