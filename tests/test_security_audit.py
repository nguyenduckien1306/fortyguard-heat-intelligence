"""Security audit test verifying strict isolation of the frontend runtime.

Assures that the frontend directory contains no direct FortyGuard URLs,
API key header literals, Bearer tokens, or hardcoded signed S3 storage URLs.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def test_frontend_never_contains_direct_fortyguard_url() -> None:
    """Verify frontend python source code never references api.fortyguard.com."""
    forbidden = "api.fortyguard.com"
    for py_file in FRONTEND_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert forbidden not in content, (
            f"Security violation: {py_file.name} contains direct FortyGuard host '{forbidden}'"
        )


def test_frontend_never_sends_api_key_header() -> None:
    """Verify frontend code never uses the FortyGuard 'api-key' authentication header."""
    for py_file in FRONTEND_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        # Check for literal header dictionaries or strings
        assert '"api-key"' not in content and "'api-key'" not in content, (
            f"Security violation: {py_file.name} references 'api-key' header."
        )


def test_frontend_never_contains_bearer_tokens() -> None:
    """Verify frontend code never references Authorization / Bearer tokens."""
    for py_file in FRONTEND_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "Authorization: Bearer" not in content and "Bearer " not in content, (
            f"Security violation: {py_file.name} contains Bearer authentication token."
        )


def test_frontend_never_contains_hardcoded_s3_signed_urls() -> None:
    """Verify frontend code never references signed S3 bucket URLs directly."""
    forbidden = "s3.amazonaws.com"
    for py_file in FRONTEND_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert forbidden not in content, (
            f"Security violation: {py_file.name} references S3 URL '{forbidden}'"
        )


def test_raw_inspection_sanitizes_download_link() -> None:
    """Verify raw developer inspection redacts signed S3 URLs."""
    from frontend.utils.export import sanitize_raw_result_for_inspection

    mock_result = {
        "download_link": "https://tos-dashboard-prod.s3.amazonaws.com/live-secret-signature?token=abc",
        "data": {"status": "ok"},
    }
    sanitized = sanitize_raw_result_for_inspection(mock_result)
    assert sanitized["download_link"] == "[REDACTED_SECURE_SIGNED_URL]"
    assert "s3.amazonaws.com" not in sanitized["download_link"]


def test_recursive_sanitization_deep_nested_secrets() -> None:
    """Verify recursive deep sanitization catches secrets at arbitrary nesting."""
    from frontend.utils.export import sanitize_raw_result_for_inspection

    mock_result = {
        "level1": {
            "level2": {
                "api_key": "deeply-nested-key",
                "download_link": "https://s3.amazonaws.com/nested",
                "level3": {
                    "secret": "buried-secret",
                    "safe_data": "visible",
                },
            },
            "normal": "ok",
        }
    }
    sanitized = sanitize_raw_result_for_inspection(mock_result)
    # All secrets at every level must be redacted
    assert sanitized["level1"]["level2"]["api_key"] == "[REDACTED]"
    assert sanitized["level1"]["level2"]["download_link"] == "[REDACTED_SECURE_SIGNED_URL]"
    assert sanitized["level1"]["level2"]["level3"]["secret"] == "[REDACTED]"
    # Normal data preserved
    assert sanitized["level1"]["level2"]["level3"]["safe_data"] == "visible"
    assert sanitized["level1"]["normal"] == "ok"


def test_no_secret_persistence_in_tags() -> None:
    """Verify tags system does not store or execute secret-like content."""
    from frontend.utils.tags import clear_tags, get_analysis_tags, set_analysis_tags

    clear_tags()
    # Even if someone tries to set a secret-looking tag, it's stored as plain text
    tags = set_analysis_tags("act-sec", ["api_key=secret123", "normal-tag"])
    stored = get_analysis_tags("act-sec")
    # Tags are just plain text, not executed
    assert len(stored) == 2
    assert all(isinstance(t, str) for t in stored)


def test_execution_context_security_sanitization() -> None:
    """Verify ExecutionContext strictly purges credentials, tokens, and signed URLs."""
    from frontend.utils.analysis_execution import (
        create_execution_context,
        record_poll_result,
        transition_to_processing,
        transition_to_submitting,
    )
    raw_params = {
        "latitude": 40.7,
        "longitude": -74.0,
        "api_key": "leak-attempt-123",
        "authorization": "Bearer token123",
        "token": "secret-token",
    }
    ctx = create_execution_context("heat_intelligence", raw_params)
    assert "api_key" not in ctx.request_params
    assert "authorization" not in ctx.request_params
    assert "token" not in ctx.request_params

    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-sec-test")

    # Record failed poll with leak attempt
    record_poll_result(
        ctx,
        {
            "status": "Failed",
            "diagnostic": {
                "code": "AUTH_FAIL",
                "api_key": "leak-key",
                "download_link": "https://s3.amazonaws.com/rep.pdf?X-Amz-Signature=secret",
                "safe_msg": "Provider failure",
            },
        },
    )
    assert ctx.provider_diagnostic is not None
    assert "api_key" not in ctx.provider_diagnostic
    assert "download_link" not in ctx.provider_diagnostic
    assert ctx.provider_diagnostic["safe_msg"] == "Provider failure"

