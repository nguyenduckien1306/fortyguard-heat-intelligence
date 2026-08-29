"""Unit and AppTest tests for Phase 12A Corrections.

Validates:
1. Heat Intelligence editable date selector & default date behavior.
2. Selected date propagation to centralized validation and request payload.
3. Provider failure diagnostics surfacing without exposing secrets.
4. Provider failure does NOT create an AnalysisRecord.
5. Processing state does NOT create a completed history record.
6. Successful completion creates exactly one AnalysisRecord.
7. Duplicate polling / reruns on the same activity_id do not create duplicate AnalysisRecords.
8. Legacy history bridge ignores non-completed records.
"""

from __future__ import annotations

from datetime import date
from typing import Any
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend.utils.analysis_history import (
    AnalysisRecord,
    add_analysis_record,
    clear_all_analysis_records,
    get_analysis_record_by_activity_id,
    list_analysis_records,
)
from frontend.utils.history import clear_session_history, get_session_history, record_session_analysis
from frontend.utils.validation import validate_heat_intelligence_request


# ──────────────────────────────────────────────────────────────────────────────
# 1. Date Selector & Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_heat_intelligence_date_validation_accepts_date_today() -> None:
    """Verifies that date.today() is valid and properly formatted."""
    today = date.today()
    res = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date_val=today,
        categories=["environmental", "urban"],
    )
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_heat_intelligence_date_validation_rejects_invalid_dates() -> None:
    """Verifies that invalid dates fail validation cleanly."""
    res_str = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date_val="not-a-date",
        categories=["environmental"],
    )
    assert res_str.is_valid is False
    assert "date" in res_str.field_errors

    res_none = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date_val=None,
        categories=["environmental"],
    )
    assert res_none.is_valid is False
    assert "date" in res_none.field_errors


# ──────────────────────────────────────────────────────────────────────────────
# 2. History Integrity & Failed/Processing Non-Creation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_provider_failure_does_not_create_analysis_record() -> None:
    """Verifies that when a task status is 'Failed', no AnalysisRecord is added."""
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
        "activity_id": "act_failed_test_123",
        "status": "Failed",
        "result": {
            "error": "Location outside provider coverage zone",
            "code": "OUT_OF_BOUNDS",
        },
    }

    _apply_status_response(failed_payload, "act_failed_test_123")

    # Assert no canonical record was created
    assert get_analysis_record_by_activity_id("act_failed_test_123") is None
    assert len(list_analysis_records()) == 0


def test_processing_task_does_not_create_completed_history() -> None:
    """Verifies that processing tasks do not appear in list_analysis_records."""
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

    processing_payload = {
        "activity_id": "act_processing_456",
        "status": "Processing",
    }

    _apply_status_response(processing_payload, "act_processing_456")

    assert get_analysis_record_by_activity_id("act_processing_456") is None
    assert len(list_analysis_records()) == 0


def test_successful_completion_creates_exactly_one_record() -> None:
    """Verifies that COMPLETED status creates exactly 1 AnalysisRecord."""
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

    completed_payload = {
        "activity_id": "act_success_789",
        "status": "Completed",
        "result": {
            "download_link": "https://s3.amazonaws.com/bucket/report.pdf?X-Amz-Signature=secret",
        },
    }

    _apply_status_response(completed_payload, "act_success_789")

    recs = list_analysis_records()
    assert len(recs) == 1
    assert recs[0].activity_id == "act_success_789"
    assert recs[0].status == "Completed"
    # Result cached must be sanitized (no secret download link)
    assert recs[0].result_cached is not None
    assert "download_link" not in recs[0].result_cached


def test_duplicate_polling_is_idempotent() -> None:
    """Repeated calls to _apply_status_response with the same activity_id do not create duplicate records."""
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

    completed_payload = {
        "activity_id": "act_idempotent_999",
        "status": "Completed",
        "result": {},
    }

    # First completion call
    _apply_status_response(completed_payload, "act_idempotent_999")
    assert len(list_analysis_records()) == 1

    # Second completion call (e.g. user clicks Refresh again)
    _apply_status_response(completed_payload, "act_idempotent_999")
    assert len(list_analysis_records()) == 1


def test_legacy_bridge_ignores_non_completed_records() -> None:
    """Verifies that the legacy history bridge ignores Processing and Failed records."""
    clear_all_analysis_records()
    clear_session_history()

    # Record legacy entries of various statuses
    record_session_analysis("Heatmap", "act_leg_proc", "Proc AOI", "Processing")
    record_session_analysis("Heatmap", "act_leg_fail", "Fail AOI", "Failed")
    record_session_analysis("Heatmap", "act_leg_done", "Done AOI", "Completed")

    recs = list_analysis_records()
    assert len(recs) == 1
    assert recs[0].activity_id == "act_leg_done"
    assert recs[0].status == "Completed"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Provider Failure Diagnostics Sanitization
# ──────────────────────────────────────────────────────────────────────────────


def test_provider_failure_diagnostic_extraction_is_sanitized() -> None:
    """Verifies that failure diagnostic extraction preserves useful messages without leaking tokens."""
    clear_all_analysis_records()
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
        "activity_id": "act_diag_safe",
        "status": "Failed",
        "result": {
            "message": "Thermal calculation error: Insufficient resolution tiles",
            "token": "fg-secret-12345",
        },
    }

    _apply_status_response(failed_payload, "act_diag_safe")
    err = st.session_state.get("heat_intelligence_error")
    assert err == "Thermal calculation error: Insufficient resolution tiles"
    assert "fg-secret-12345" not in err


# ──────────────────────────────────────────────────────────────────────────────
# 4. Streamlit AppTest for UI Date Selector and Submit Guard
# ──────────────────────────────────────────────────────────────────────────────


def _run_hi_page() -> None:
    from frontend.pages.heat_intelligence import render_heat_intelligence_page
    render_heat_intelligence_page()


def test_heat_intelligence_ui_renders_date_input() -> None:
    """Verifies that the Heat Intelligence page renders a visible date input."""
    at = AppTest.from_function(_run_hi_page, default_timeout=15)
    at.run()

    assert not at.exception
    # Verify date_input exists in the page
    date_inputs = at.date_input
    assert len(date_inputs) >= 1
    # Check that the default value is a valid date object
    hi_date = at.date_input(key="_hi_date")
    assert hi_date is not None
    assert isinstance(hi_date.value, date)
