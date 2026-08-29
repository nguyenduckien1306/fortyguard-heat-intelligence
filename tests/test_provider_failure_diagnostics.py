"""Unit and AppTest tests for Phase 12B.1 Provider Failure Diagnostics.

Tests:
1. Failed status is preserved with rich diagnostics.
2. Provider error code is extracted when present.
3. Provider message is extracted when present.
4. Nested error structures (details/reason) are extracted.
5. Missing diagnostics are handled safely without crashing.
6. Sensitive fields (api_key, token, secret, Authorization) are recursively stripped.
7. Signed URLs (X-Amz-Signature) are redacted/removed.
8. Failed analyses NEVER enter session history.
9. Processing analyses NEVER enter session history.
10. Completed analyses ARE added exactly once.
11. Diagnostic logging for provider failure works properly.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from backend.api.client import FortyGuardClient
from backend.models.common import ActivityStatusResponse
from tests.conftest import make_client
from frontend.utils.analysis_history import (
    clear_all_analysis_records,
    get_analysis_record_by_activity_id,
    list_analysis_records,
)
from frontend.utils.history import clear_session_history, get_session_history


# ──────────────────────────────────────────────────────────────────────────────
# 1. Backend Parser Diagnostic Extraction & Sanitization Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_failed_status_extracts_code_and_message() -> None:
    """Error code and message in data are extracted into ActivityStatusResponse.diagnostic."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-fail-001",
            "status": "Failed",
            "code": "OUT_OF_BOUNDS",
            "message": "Coordinate point is outside supported urban bounds",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-fail-001")
    finally:
        client.close()

    assert resp.status == "Failed"
    assert resp.diagnostic is not None
    assert resp.diagnostic.get("code") == "OUT_OF_BOUNDS"
    assert resp.diagnostic.get("message") == "Coordinate point is outside supported urban bounds"


def test_failed_status_extracts_nested_reason_and_details() -> None:
    """Nested reason and details dictionaries are preserved in diagnostic."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-fail-002",
            "status": "Failed",
            "failure_reason": "Insufficient spatial resolution",
            "details": {
                "grid_cells": 0,
                "coverage_pct": 0.0,
            },
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-fail-002")
    finally:
        client.close()

    assert resp.status == "Failed"
    assert resp.diagnostic is not None
    assert resp.diagnostic.get("reason") == "Insufficient spatial resolution"
    assert resp.diagnostic.get("details") == {"grid_cells": 0, "coverage_pct": 0.0}


def test_failed_status_without_extra_fields_returns_none_diagnostic() -> None:
    """When provider returns status 'Failed' with no extra diagnostic fields, diagnostic is None."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-fail-bare",
            "status": "Failed",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-fail-bare")
    finally:
        client.close()

    assert resp.status == "Failed"
    assert resp.diagnostic is None


def test_recursive_sanitization_removes_secrets_and_signed_urls() -> None:
    """Diagnostic extraction recursively purges API keys, tokens, and signed S3 URLs."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-fail-leak",
            "status": "Failed",
            "code": "AUTH_ERROR",
            "message": "Provider authentication failed",
            "api_key": "fg-secret-leak-12345",
            "token": "bearer-secret-token",
            "details": {
                "download_link": "https://s3.amazonaws.com/bucket/report.pdf?X-Amz-Signature=secret123",
                "authorization": "Basic secret_creds",
                "safe_info": "Urban analysis failed at tier 2",
            },
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-fail-leak")
    finally:
        client.close()

    diag = resp.diagnostic
    assert diag is not None
    assert diag.get("code") == "AUTH_ERROR"
    assert diag.get("message") == "Provider authentication failed"
    # Verify sensitive keys are stripped
    assert "api_key" not in diag
    assert "token" not in diag
    assert "download_link" not in diag.get("details", {})
    assert "authorization" not in diag.get("details", {})
    assert diag["details"]["safe_info"] == "Urban analysis failed at tier 2"


def test_provider_failure_developer_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Verifies that provider failure generates a sanitized HEAT_INTELLIGENCE_PROVIDER_FAILURE log."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-log-fail",
            "status": "Failed",
            "code": "MODEL_FAILED",
            "reason": "Simulation diverged",
            "api_key": "secret-key-do-not-log",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    with caplog.at_level(logging.WARNING):
        try:
            client.get_activity_status("act-log-fail")
        finally:
            client.close()

    assert "HEAT_INTELLIGENCE_PROVIDER_FAILURE" in caplog.text
    assert "activity_id=act-log-fail" in caplog.text
    assert "status=Failed" in caplog.text
    assert "code=MODEL_FAILED" in caplog.text
    assert "secret-key-do-not-log" not in caplog.text


# ──────────────────────────────────────────────────────────────────────────────
# 2. History Isolation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_failed_analysis_never_enters_completed_history() -> None:
    """Failed status response never creates an AnalysisRecord or enters session history."""
    clear_all_analysis_records()
    clear_session_history()

    from frontend.pages.heat_intelligence import _apply_status_response, _initialise_state

    _initialise_state()
    st.session_state["heat_intelligence_submitted_req"] = {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2026-08-22",
        "analysis": ["environmental"],
    }

    failed_payload = {
        "activity_id": "act-failed-hist-check",
        "status": "Failed",
        "diagnostic": {
            "code": "GRID_EMPTY",
            "message": "No tiles found in AOI",
        },
    }

    _apply_status_response(failed_payload, "act-failed-hist-check")

    assert get_analysis_record_by_activity_id("act-failed-hist-check") is None
    assert len(list_analysis_records()) == 0


def test_processing_analysis_never_enters_completed_history() -> None:
    """Processing status response never creates an AnalysisRecord or enters session history."""
    clear_all_analysis_records()
    clear_session_history()

    from frontend.pages.heat_intelligence import _apply_status_response, _initialise_state

    _initialise_state()
    st.session_state["heat_intelligence_submitted_req"] = {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2026-08-22",
        "analysis": ["environmental"],
    }

    proc_payload = {
        "activity_id": "act-proc-hist-check",
        "status": "Processing",
    }

    _apply_status_response(proc_payload, "act-proc-hist-check")

    assert get_analysis_record_by_activity_id("act-proc-hist-check") is None
    assert len(list_analysis_records()) == 0


def test_completed_analysis_enters_history_exactly_once() -> None:
    """Completed status response creates exactly one AnalysisRecord."""
    clear_all_analysis_records()
    clear_session_history()

    from frontend.pages.heat_intelligence import _apply_status_response, _initialise_state

    _initialise_state()
    st.session_state["heat_intelligence_submitted_req"] = {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2026-08-22",
        "analysis": ["environmental"],
    }

    comp_payload = {
        "activity_id": "act-done-hist-check",
        "status": "Completed",
        "result": {},
    }

    _apply_status_response(comp_payload, "act-done-hist-check")

    recs = list_analysis_records()
    assert len(recs) == 1
    assert recs[0].activity_id == "act-done-hist-check"
    assert recs[0].status == "Completed"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Streamlit UI Rendering Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_ui_renders_diagnostic_fields_when_present() -> None:
    """Streamlit UI renders Error Code, Message, and Reason in the Provider Diagnostic Information panel."""
    def _run() -> None:
        from frontend.pages.heat_intelligence import (
            _apply_status_response,
            _initialise_state,
            _render_workflow_state,
        )
        _initialise_state()
        payload = {
            "activity_id": "act-ui-diag",
            "status": "Failed",
            "diagnostic": {
                "code": "TEMPORAL_OUT_OF_RANGE",
                "message": "Historical data unavailable for requested date",
                "reason": "Archive limit exceeded",
            },
        }
        _apply_status_response(payload, "act-ui-diag")
        _render_workflow_state()

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    # Verify error banner and captions in expander
    captions = [c.value for c in at.caption]
    caption_text = " ".join(captions)
    assert "Activity ID:" in caption_text
    assert "Failed" in caption_text
    assert "TEMPORAL_OUT_OF_RANGE" in caption_text
    assert "Historical data unavailable for requested date" in caption_text
    assert "Archive limit exceeded" in caption_text


def test_ui_renders_fallback_when_no_diagnostic_info() -> None:
    """Streamlit UI renders clear fallback message when Failed response contains no diagnostic details."""
    def _run() -> None:
        from frontend.pages.heat_intelligence import (
            _apply_status_response,
            _initialise_state,
            _render_workflow_state,
        )
        _initialise_state()
        payload = {
            "activity_id": "act-ui-bare",
            "status": "Failed",
            "diagnostic": None,
        }
        _apply_status_response(payload, "act-ui-bare")
        _render_workflow_state()

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    captions = [c.value for c in at.caption]
    caption_text = " ".join(captions)
    assert (
        "FortyGuard reported that the analysis failed, but did not provide a specific failure reason." in caption_text
        or "FortyGuard returned Failed without additional diagnostic information." in caption_text
    )
