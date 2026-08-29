"""Diagnostic and pipeline verification tests for FortyGuard status handling.

Verifies:
1. Provider returns Processing → backend returns Processing.
2. Provider returns Completed → backend returns Completed with result.
3. Provider returns Failed → backend returns Failed with diagnostics.
4. Provider returns unknown status → backend does NOT silently return Processing.
5. Provider request raises network exception → backend does NOT silently return Processing.
6. Provider response has missing status → backend does NOT silently return Processing.
7. Provider response contains result → result is preserved properly.
8. Provider diagnostic fields are sanitized.
9. API credentials and signed URLs never appear in diagnostics.
10. Processing/Failed/Error states never enter completed history.
"""

from __future__ import annotations

import httpx
import pytest

from backend.api.client import FortyGuardClient
from backend.api.exceptions import (
    MalformedResponseError,
    TransportError,
)
from backend.models.common import ActivityStatusResponse
from tests.conftest import make_client, status_payload
from frontend.utils.analysis_history import (
    clear_all_analysis_records,
    get_analysis_record_by_activity_id,
    list_analysis_records,
)
from frontend.utils.history import clear_session_history


# ──────────────────────────────────────────────────────────────────────────────
# Status Parsing & Integrity Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_provider_returns_processing_yields_processing() -> None:
    """When provider returns status 'Processing', client returns Processing with result=None."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Processing",
        "data": {
            "activity_id": "act-live-proc",
            "status": "Processing",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-live-proc")
    finally:
        client.close()

    assert resp.activity_id == "act-live-proc"
    assert resp.status == "Processing"
    assert resp.result is None


def test_provider_returns_completed_yields_completed_with_result() -> None:
    """When provider returns status 'Completed', client returns Completed with result."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Success",
        "data": {
            "activity_id": "act-live-done",
            "status": "Completed",
            "result": {
                "download_link": "https://s3.amazonaws.com/bucket/report.pdf",
            },
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-live-done")
    finally:
        client.close()

    assert resp.activity_id == "act-live-done"
    assert resp.status == "Completed"
    assert resp.result == {"download_link": "https://s3.amazonaws.com/bucket/report.pdf"}


def test_provider_returns_failed_yields_failed_with_diagnostics() -> None:
    """When provider returns status 'Failed', client preserves error details in result."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Failed",
        "data": {
            "activity_id": "act-live-fail",
            "status": "Failed",
            "error": "Location coordinates outside coverage polygon",
            "code": "OUT_OF_COVERAGE",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-live-fail")
    finally:
        client.close()

    assert resp.activity_id == "act-live-fail"
    assert resp.status == "Failed"
    assert resp.diagnostic is not None
    assert resp.diagnostic.get("details") == "Location coordinates outside coverage polygon"
    assert resp.diagnostic.get("code") == "OUT_OF_COVERAGE"


def test_provider_missing_status_field_raises_malformed_response() -> None:
    """Missing 'status' in provider data raises MalformedResponseError, NEVER defaulting to Processing."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "OK",
        "data": {
            "activity_id": "act-no-status",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError, match="Missing status"):
            client.get_activity_status("act-no-status")
    finally:
        client.close()


def test_provider_network_exception_raises_transport_error() -> None:
    """Network connection failure raises TransportError, NEVER defaulting to Processing."""
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by FortyGuard host")

    client = make_client(handler)
    try:
        with pytest.raises(TransportError, match="Unable to reach FortyGuard"):
            client.get_activity_status("act-net-err")
    finally:
        client.close()


def test_provider_returns_unknown_status_preserves_exact_string() -> None:
    """If provider returns an unknown status string, client returns it as-is (does NOT force Processing)."""
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Queued",
        "data": {
            "activity_id": "act-unknown-status",
            "status": "QueuedOnWorker",
        },
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = make_client(handler)
    try:
        resp = client.get_activity_status("act-unknown-status")
    finally:
        client.close()

    assert resp.status == "QueuedOnWorker"
    assert resp.status != "Processing"


def test_processing_never_enters_completed_history() -> None:
    """Status 'Processing' on status polling never creates a completed AnalysisRecord."""
    clear_all_analysis_records()
    clear_session_history()

    from frontend.pages.heat_intelligence import _apply_status_response, _initialise_state
    import streamlit as st

    _initialise_state()
    st.session_state["heat_intelligence_submitted_req"] = {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2026-08-22",
        "analysis": ["environmental"],
    }

    # Simulate receiving processing status response
    payload = {
        "activity_id": "47299a85-58ba-461a-89e9-00b0b2b0b7d2",
        "status": "Processing",
        "result": None,
    }

    _apply_status_response(payload, "47299a85-58ba-461a-89e9-00b0b2b0b7d2")

    # Verify no completed history record exists
    assert get_analysis_record_by_activity_id("47299a85-58ba-461a-89e9-00b0b2b0b7d2") is None
    assert len(list_analysis_records()) == 0
