"""Streamlit workflow for submitting and tracking a FortyGuard Heat Intelligence task."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from typing import Any

# Ensure project root is on sys.path when run directly as a Streamlit page
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from frontend.components.execution_console import render_execution_console
from frontend.components.heat_intelligence_result import render_heat_intelligence_result
from frontend.components.sidebar import render_sidebar
from frontend.components.status import render_task_status
from frontend.services.api import BackendAPIClient, BackendAPIError
from frontend.utils.analysis_execution import (
    ExecutionContext,
    ExecutionState,
    create_execution_context,
    create_retry_context,
    record_poll_result,
    resume_polling_after_timeout,
    transition_to_processing,
    transition_to_submitting,
)
from frontend.utils.errors import classify_user_error
from frontend.utils.heatmap import compute_aoi_centroid
from frontend.utils.history import update_session_analysis_status

READY = "READY"
SUBMITTING = "SUBMITTING"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
POLLING_TIMEOUT = "POLLING_TIMEOUT"
ERROR = "ERROR"

_STATE_KEY = "heat_intelligence_workflow_state"
_ACTIVITY_ID_KEY = "heat_intelligence_activity_id"
_STATUS_KEY = "heat_intelligence_status"
_RESULT_KEY = "heat_intelligence_result"
_DIAGNOSTIC_KEY = "heat_intelligence_diagnostic"
_ERROR_KEY = "heat_intelligence_error"
_SUBMITTED_REQ_KEY = "heat_intelligence_submitted_req"
_SUBMIT_GUARD_KEY = "heat_intelligence_submit_guard"
_EXECUTION_CTX_KEY = "heat_intelligence_execution_context"


def _get_execution_context() -> ExecutionContext:
    if _EXECUTION_CTX_KEY not in st.session_state or not isinstance(
        st.session_state[_EXECUTION_CTX_KEY], ExecutionContext
    ):
        st.session_state[_EXECUTION_CTX_KEY] = create_execution_context("heat_intelligence")
    return st.session_state[_EXECUTION_CTX_KEY]


def _initialise_state() -> None:
    st.session_state.setdefault(_STATE_KEY, READY)
    st.session_state.setdefault(_ACTIVITY_ID_KEY, None)
    st.session_state.setdefault(_STATUS_KEY, None)
    st.session_state.setdefault(_RESULT_KEY, None)
    st.session_state.setdefault(_DIAGNOSTIC_KEY, None)
    st.session_state.setdefault(_ERROR_KEY, None)
    st.session_state.setdefault(_SUBMITTED_REQ_KEY, None)
    st.session_state.setdefault(_SUBMIT_GUARD_KEY, False)
    _get_execution_context()


def _set_state(
    state: str,
    *,
    activity_id: str | None = None,
    status: str | None = None,
    result: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    st.session_state[_STATE_KEY] = state
    if activity_id is not None or state in {READY, SUBMITTING}:
        st.session_state[_ACTIVITY_ID_KEY] = activity_id
    st.session_state[_STATUS_KEY] = status
    st.session_state[_RESULT_KEY] = result
    st.session_state[_DIAGNOSTIC_KEY] = diagnostic
    st.session_state[_ERROR_KEY] = error


def _apply_status_response(payload: dict[str, Any], activity_id: str) -> None:
    response_activity_id = payload.get("activity_id")
    status = payload.get("status")
    result = payload.get("result")
    diagnostic = payload.get("diagnostic")

    if response_activity_id != activity_id:
        raise BackendAPIError("The backend returned a different activity ID.")
    if not isinstance(status, str) or not status.strip():
        raise BackendAPIError("The backend returned no activity status.")

    ctx = _get_execution_context()
    if response_activity_id and ctx.activity_id != response_activity_id:
        ctx = create_execution_context("heat_intelligence")
        ctx.activity_id = response_activity_id
        st.session_state[_EXECUTION_CTX_KEY] = ctx
    record_poll_result(ctx, payload)

    if ctx.state == ExecutionState.POLLING_TIMEOUT:
        state = POLLING_TIMEOUT
        error = None
    elif status == "Processing":
        state = PROCESSING
        error = None
    elif status == "Completed":
        state = COMPLETED
        error = None
        st.session_state[_SUBMIT_GUARD_KEY] = False
    elif status == "Failed":
        state = FAILED
        st.session_state[_SUBMIT_GUARD_KEY] = False
        diag_msg = None
        if isinstance(diagnostic, dict):
            diag_msg = diagnostic.get("message") or diagnostic.get("reason") or diagnostic.get("details")
        if not diag_msg and isinstance(result, dict):
            diag_msg = (
                result.get("message")
                or result.get("error")
                or result.get("reason")
                or result.get("details")
                or result.get("failure_reason")
            )
        if not diag_msg and payload.get("message") and payload.get("message") != "Failed":
            diag_msg = payload.get("message")
        error = str(diag_msg) if diag_msg else None
    else:
        state = ERROR
        st.session_state[_SUBMIT_GUARD_KEY] = False
        error = f"FortyGuard returned an unrecognized task status: {status}."

    _set_state(
        state,
        activity_id=activity_id,
        status=status,
        result=result if isinstance(result, dict) else None,
        diagnostic=diagnostic if isinstance(diagnostic, dict) else None,
        error=error,
    )

    if state == COMPLETED:
        if not isinstance(result, dict):
            st.warning("Analysis completed but the returned result could not be rendered safely.")
            return

        submitted_req = st.session_state.get(_SUBMITTED_REQ_KEY) or {}
        lat = submitted_req.get("latitude", 40.7050)
        lon = submitted_req.get("longitude", -74.0090)
        date_str = str(submitted_req.get("date") or "2026-08-22")
        temp = float(submitted_req.get("temperature", 32.5))
        cats = submitted_req.get("analysis") or submitted_req.get("categories") or ["environmental", "urban"]

        update_session_analysis_status(
            activity_id,
            status,
            summary="Report Ready (PDF)",
            result_cached=result if isinstance(result, dict) else None,
        )

        from frontend.utils.analysis_history import (
            AnalysisRecord,
            add_analysis_record,
            get_analysis_record_by_activity_id,
        )
        existing_rec = get_analysis_record_by_activity_id(activity_id)
        loc_str = f"Heat Intelligence ({lat}, {lon})" if lat and lon else "Heat Intelligence Point"

        rec = AnalysisRecord(
            analysis_id=existing_rec.analysis_id if existing_rec else "",
            activity_id=activity_id,
            analysis_type="heat_intelligence",
            created_at=existing_rec.created_at if existing_rec else "",
            updated_at="",
            location_label=loc_str,
            latitude=lat,
            longitude=lon,
            date=str(date_str),
            observed_temperature=temp,
            categories=cats,
            status="Completed",
            summary="Report Ready (PDF)",
            result_cached=result if isinstance(result, dict) else None,
        )
        add_analysis_record(rec)


def _call_backend(
    api_client: BackendAPIClient | None,
    operation: str,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run one backend operation, allowing an injected client in tests."""
    if api_client is not None:
        return getattr(api_client, operation)(*args, **kwargs)
    with BackendAPIClient() as client:
        return getattr(client, operation)(*args, **kwargs)


def _render_workflow_state(
    api_client: BackendAPIClient | None = None,
) -> None:
    ctx = _get_execution_context()
    state = st.session_state.get(_STATE_KEY, READY)
    activity_id = st.session_state.get(_ACTIVITY_ID_KEY)
    result = st.session_state.get(_RESULT_KEY)

    # Render standardized Execution Console
    render_execution_console(
        ctx,
        on_refresh=lambda: _handle_status_check(api_client, activity_id, is_poll=False),
        on_poll=lambda: _handle_status_check(api_client, activity_id, is_poll=True),
        on_check_again=lambda: _handle_check_again(api_client, activity_id),
        on_retry=lambda: _handle_retry(api_client),
        on_reset=_handle_reset,
        key_prefix="hi",
    )

    if state == COMPLETED and isinstance(result, dict):
        submitted_req = st.session_state.get(_SUBMITTED_REQ_KEY)
        render_heat_intelligence_result(
            submitted_req,
            result,
            activity_id=activity_id,
            api_client=api_client,
        )


def _handle_status_check(
    api_client: BackendAPIClient | None,
    activity_id: str | None,
    *,
    is_poll: bool = False,
) -> None:
    if not activity_id:
        return
    ctx = _get_execution_context()
    operation = "poll_heat_intelligence" if is_poll else "get_heat_intelligence_status"
    try:
        with st.spinner("Checking Heat Intelligence status..."):
            response = _call_backend(
                api_client,
                operation,
                activity_id,
                **(
                    {
                        "max_attempts": 40,
                        "poll_interval_seconds": 3.0,
                    }
                    if is_poll
                    else {}
                ),
            )
        _apply_status_response(response, activity_id)
    except BackendAPIError as exc:
        _set_state(
            ERROR,
            activity_id=activity_id,
            status=st.session_state.get(_STATUS_KEY),
            error=str(exc),
        )
        ctx.error_message = str(exc)
        update_session_analysis_status(activity_id, "Error")
        st.session_state[_SUBMIT_GUARD_KEY] = False


def _handle_check_again(
    api_client: BackendAPIClient | None,
    activity_id: str | None,
) -> None:
    """Resume polling an existing activity after timeout (zero new activities)."""
    if not activity_id:
        return
    ctx = _get_execution_context()
    resume_polling_after_timeout(ctx)
    _set_state(PROCESSING, activity_id=activity_id, status="Processing")
    _handle_status_check(api_client, activity_id, is_poll=False)


def _handle_retry(api_client: BackendAPIClient | None) -> None:
    """Execute explicit user-controlled retry (submits exactly 1 new activity)."""
    ctx = _get_execution_context()
    if not ctx.can_retry or not ctx.request_params:
        return
    retry_ctx = create_retry_context(ctx)
    transition_to_submitting(retry_ctx)
    st.session_state[_EXECUTION_CTX_KEY] = retry_ctx
    _set_state(SUBMITTING, activity_id=None, status=None, error=None)

    try:
        response = _call_backend(api_client, "submit_heat_intelligence", retry_ctx.request_params)
        new_activity_id = response.get("activity_id")
        if not isinstance(new_activity_id, str) or not new_activity_id.strip():
            raise BackendAPIError("The backend returned no activity ID.")
    except BackendAPIError as exc:
        retry_ctx.state = ExecutionState.FAILED
        retry_ctx.error_message = str(exc)
        _set_state(ERROR, error=str(exc))
        st.session_state[_SUBMIT_GUARD_KEY] = False
    else:
        transition_to_processing(retry_ctx, new_activity_id)
        _set_state(
            PROCESSING,
            activity_id=new_activity_id,
            status="Processing",
        )
        st.success(f"Retry task submitted! New Activity ID: `{new_activity_id}`")


def _handle_reset() -> None:
    """Reset the execution workflow to NEW."""
    st.session_state[_EXECUTION_CTX_KEY] = create_execution_context("heat_intelligence")
    _set_state(READY, activity_id=None, status=None, result=None, error=None)
    st.session_state[_SUBMITTED_REQ_KEY] = None
    st.session_state[_SUBMIT_GUARD_KEY] = False
    for key in list(st.session_state.keys()):
        if key.startswith("_hi_pdf_"):
            del st.session_state[key]
    st.rerun()


def render_heat_intelligence_page(
    api_client: BackendAPIClient | None = None,
) -> None:
    """Render the Heat Intelligence submit and status tracking workflow."""
    _initialise_state()
    ctx = _get_execution_context()

    st.header("Heat Intelligence Reports")
    st.caption("Generate multi-dimensional urban heat intelligence and resilience reports (PDF) via FortyGuard.")

    selections = render_sidebar()

    # Extract location coordinates from AOI or sidebar
    default_lat, default_lon = 40.7050, -74.0090
    if selections.polygon_aoi is not None:
        centroid = compute_aoi_centroid(selections.polygon_aoi)
        if centroid:
            default_lat, default_lon = centroid

    from frontend.utils.validation import validate_heat_intelligence_request

    # ── Section 1: Grouped Input Form ──
    st.subheader("Analysis Parameters")

    with st.container(border=True):
        st.markdown("##### 📍 Location & Observation")
        col1, col2 = st.columns(2)
        with col1:
            latitude = st.number_input("Latitude", value=default_lat, format="%.6f", key="_hi_lat")
            if latitude < -90.0 or latitude > 90.0:
                st.caption(f":red[⚠️ Latitude must be between -90° and 90° (entered {latitude}).]")

            longitude = st.number_input("Longitude", value=default_lon, format="%.6f", key="_hi_lon")
            if longitude < -180.0 or longitude > 180.0:
                st.caption(f":red[⚠️ Longitude must be between -180° and 180° (entered {longitude}).]")

            analysis_date = st.date_input("Analysis Date", value=date.today(), key="_hi_date")

        with col2:
            temperature = st.number_input("Observed Temperature (°C)", value=32.5, min_value=-100.0, max_value=100.0, step=0.5, key="_hi_temp")
            if temperature < -100.0 or temperature > 100.0:
                st.caption(f":red[⚠️ Observed temperature must be between -100°C and 100°C.]")

            analysis_types = st.multiselect(
                "Analysis Categories",
                options=["geographic", "environmental", "urban", "events", "anthropogenic"],
                default=["environmental", "urban"],
                key="_hi_analysis",
            )
            if not analysis_types:
                st.caption(":red[⚠️ Select at least one analysis category.]")

    # Centralized pure validation
    val_res = validate_heat_intelligence_request(
        latitude=latitude,
        longitude=longitude,
        temperature=temperature,
        date_val=analysis_date,
        categories=analysis_types,
    )

    request_payload: dict[str, Any] | None = None
    if val_res.is_valid:
        request_payload = {
            "latitude": round(float(latitude), 6),
            "longitude": round(float(longitude), 6),
            "temperature": round(float(temperature), 2),
            "date": str(analysis_date),
            "analysis": list(analysis_types),
        }
        ctx.request_params = request_payload

    # ── Section 2: Pre-flight Review & Validation State ──
    with st.expander("📋 Review Heat Intelligence Request", expanded=True):
        if val_res.is_valid and request_payload is not None:
            st.success("✓ **Request Parameters Ready** — All inputs are valid.")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"**Location:** `{request_payload['latitude']}, {request_payload['longitude']}`")
            with c2:
                st.markdown(f"**Observed Temp:** `{request_payload['temperature']} °C`")
                st.markdown(f"**Date:** `{request_payload['date']}`")
            with c3:
                st.markdown(f"**Dimensions:** `{', '.join(request_payload['analysis'])}`")
            for warn in val_res.warnings:
                st.caption(f"ℹ️ *Notice:* {warn}")
        else:
            st.error(f"⚠️ **Fix {len(val_res.errors)} Validation Error{'s' if len(val_res.errors) != 1 else ''} Before Submission:**")
            for err in val_res.errors:
                st.markdown(f"• {err}")

    # ── Section 3: Submission with duplicate guard ──
    is_in_progress = ctx.is_in_progress or st.session_state.get(_STATE_KEY, READY) in {PROCESSING, SUBMITTING}

    if is_in_progress:
        submit_btn_label = "⏳ Analysis in Progress..."
        submit_disabled = True
    elif val_res.is_valid:
        submit_btn_label = "🚀 Generate Heat Intelligence Report"
        submit_disabled = False
    else:
        submit_btn_label = "⚠️ Fix Validation Errors to Submit"
        submit_disabled = True

    submit_clicked = st.button(
        submit_btn_label,
        type="primary",
        key="_hi_submit_btn",
        disabled=submit_disabled,
    )

    # SUBMISSION BOUNDARY RULE: Zero network I/O if validation fails or in progress
    if (submit_clicked or selections.generate_clicked) and val_res.is_valid and request_payload is not None and not is_in_progress:
        if st.session_state.get(_SUBMIT_GUARD_KEY):
            st.warning("⚠️ A submission is already in progress. Please wait for it to complete.")
        else:
            st.session_state[_SUBMIT_GUARD_KEY] = True
            transition_to_submitting(ctx)
            _set_state(SUBMITTING, activity_id=None, status=None, error=None)
            try:
                response = _call_backend(api_client, "submit_heat_intelligence", request_payload)
                activity_id = response.get("activity_id")
                if not isinstance(activity_id, str) or not activity_id.strip():
                    raise BackendAPIError("The backend returned no activity ID.")
            except BackendAPIError as exc:
                ctx.state = ExecutionState.FAILED
                ctx.error_message = str(exc)
                _set_state(ERROR, error=str(exc))
                st.session_state[_SUBMIT_GUARD_KEY] = False
            else:
                transition_to_processing(ctx, activity_id)
                st.session_state[_SUBMITTED_REQ_KEY] = request_payload
                _set_state(
                    PROCESSING,
                    activity_id=activity_id,
                    status="Processing",
                )
                st.success(f"Heat Intelligence task submitted successfully! Activity ID: `{activity_id}`")

    _render_workflow_state(api_client=api_client)


if __name__ == "__main__":
    from frontend.components.design_system import inject_design_system
    inject_design_system()
    st.title("FortyGuard Heat Intelligence")
    st.caption("Comprehensive Urban Thermal Analytics & Multi-Factor Resilience Platform")
    render_heat_intelligence_page()



