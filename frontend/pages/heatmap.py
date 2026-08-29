"""Streamlit workflow for submitting and tracking a FortyGuard heatmap."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when run directly as a Streamlit page
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from backend.mock_data.heatmap_results import ALL_MOCK_RESULT_FIXTURES
from frontend.components.execution_console import render_execution_console
from frontend.components.heatmap_result import render_heatmap_result
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
from frontend.utils.heatmap import build_heatmap_request_payload
from frontend.utils.history import update_session_analysis_status

READY = "READY"
SUBMITTING = "SUBMITTING"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
POLLING_TIMEOUT = "POLLING_TIMEOUT"
ERROR = "ERROR"

_STATE_KEY = "heatmap_workflow_state"
_ACTIVITY_ID_KEY = "heatmap_activity_id"
_STATUS_KEY = "heatmap_status"
_RESULT_KEY = "heatmap_result"
_DIAGNOSTIC_KEY = "heatmap_diagnostic"
_ERROR_KEY = "heatmap_error"
_SUBMITTED_AOI_KEY = "heatmap_submitted_aoi"
_SUBMIT_GUARD_KEY = "heatmap_submit_guard"
_EXECUTION_CTX_KEY = "heatmap_execution_context"


def _get_execution_context() -> ExecutionContext:
    if _EXECUTION_CTX_KEY not in st.session_state or not isinstance(
        st.session_state[_EXECUTION_CTX_KEY], ExecutionContext
    ):
        st.session_state[_EXECUTION_CTX_KEY] = create_execution_context("heatmap")
    return st.session_state[_EXECUTION_CTX_KEY]


def _initialise_state() -> None:
    st.session_state.setdefault(_STATE_KEY, READY)
    st.session_state.setdefault(_ACTIVITY_ID_KEY, None)
    st.session_state.setdefault(_STATUS_KEY, None)
    st.session_state.setdefault(_RESULT_KEY, None)
    st.session_state.setdefault(_DIAGNOSTIC_KEY, None)
    st.session_state.setdefault(_ERROR_KEY, None)
    st.session_state.setdefault(_SUBMITTED_AOI_KEY, None)
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


def _apply_status_response(payload: dict[str, Any], activity_id: str, label: str = "Heatmap Analysis") -> None:
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
        ctx = create_execution_context("heatmap")
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
        summary_text = ""
        metrics_summary: dict[str, Any] = {}
        if isinstance(result, dict):
            map_data = result.get("map_data")
            from frontend.utils.heatmap_analytics import compute_tile_metrics
            metrics_summary = compute_tile_metrics(map_data)
            if metrics_summary.get("total_tiles"):
                summary_text = f"{metrics_summary['total_tiles']} tiles • Mean {metrics_summary.get('mean_temp', '—')}°C"
            elif isinstance(map_data, dict) and "features" in map_data:
                summary_text = f"{len(map_data['features'])} tiles analyzed"

        # Result Intelligence check for spatial result
        if not isinstance(result, dict) or (not metrics_summary and "map_data" not in result):
            st.warning("Analysis completed but the returned result could not be rendered safely.")
            return

        update_session_analysis_status(
            activity_id,
            status,
            summary=summary_text,
            metrics_summary=metrics_summary,
            result_cached=result if isinstance(result, dict) else None,
        )

        from dataclasses import asdict
        from frontend.utils.analysis_history import (
            AnalysisRecord,
            add_analysis_record,
            get_analysis_record_by_activity_id,
        )
        submitted_req = st.session_state.get("_heatmap_submitted_req") or {}
        existing_rec = get_analysis_record_by_activity_id(activity_id)

        loc_label = submitted_req.get("label") or label or "Heatmap AOI"
        polygon_aoi = submitted_req.get("polygon_aoi") or st.session_state.get(_SUBMITTED_AOI_KEY)

        from frontend.utils.insights import generate_heatmap_insights
        insights = [asdict(ins) for ins in generate_heatmap_insights(metrics_summary)]

        rec = AnalysisRecord(
            analysis_id=existing_rec.analysis_id if existing_rec else "",
            activity_id=activity_id,
            analysis_type="heatmap",
            created_at=existing_rec.created_at if existing_rec else "",
            updated_at="",
            location_label=loc_label,
            date=str(submitted_req.get("date", "")),
            time=str(submitted_req.get("time", "")),
            granularity=submitted_req.get("granularity"),
            polygon_summary="Polygon AOI" if isinstance(polygon_aoi, dict) else "",
            polygon_aoi=polygon_aoi,
            status="Completed",
            summary=summary_text,
            metrics=metrics_summary,
            insights=insights,
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

    render_execution_console(
        ctx,
        on_refresh=lambda: _handle_status_check(api_client, activity_id, is_poll=False),
        on_poll=lambda: _handle_status_check(api_client, activity_id, is_poll=True),
        on_check_again=lambda: _handle_check_again(api_client, activity_id),
        on_retry=lambda: _handle_retry(api_client),
        on_reset=_handle_reset,
        key_prefix="hm",
    )

    if state == COMPLETED and isinstance(result, dict):
        submitted_req = st.session_state.get("_heatmap_submitted_req")
        render_heatmap_result(submitted_req, result)


def _handle_status_check(
    api_client: BackendAPIClient | None,
    activity_id: str | None,
    *,
    is_poll: bool = False,
) -> None:
    if not activity_id:
        return
    ctx = _get_execution_context()
    operation = "poll_heatmap" if is_poll else "get_heatmap_status"
    try:
        with st.spinner("Checking heatmap status..."):
            response = _call_backend(
                api_client,
                operation,
                activity_id,
                **(
                    {
                        "max_attempts": 30,
                        "poll_interval_seconds": 2.0,
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
    if not activity_id:
        return
    ctx = _get_execution_context()
    resume_polling_after_timeout(ctx)
    _set_state(PROCESSING, activity_id=activity_id, status="Processing")
    _handle_status_check(api_client, activity_id, is_poll=False)


def _handle_retry(api_client: BackendAPIClient | None) -> None:
    ctx = _get_execution_context()
    if not ctx.can_retry or not ctx.request_params:
        return
    retry_ctx = create_retry_context(ctx)
    transition_to_submitting(retry_ctx)
    st.session_state[_EXECUTION_CTX_KEY] = retry_ctx
    _set_state(SUBMITTING, activity_id=None, status=None, error=None)

    try:
        response = _call_backend(api_client, "submit_heatmap", retry_ctx.request_params)
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
    st.session_state[_EXECUTION_CTX_KEY] = create_execution_context("heatmap")
    _set_state(READY, activity_id=None, status=None, result=None, error=None)
    st.session_state[_SUBMITTED_AOI_KEY] = None
    st.session_state[_SUBMIT_GUARD_KEY] = False
    st.rerun()


def _render_mock_preview(current_aoi: dict[str, Any] | None) -> None:
    """Developer-only preview of the result UI using local mock fixtures."""
    with st.expander("🧪 Preview with mock result (dev only)", expanded=False):
        st.info(
            "🧪 **SIMULATION / DEV ONLY** — This preview renders the UI against a local mock fixture. "
            "No FortyGuard API request will be made, and no session analysis will be recorded."
        )
        enabled = st.checkbox("Enable mock preview", value=False, key="_mock_preview_enabled")
        if not enabled:
            return

        variant = st.selectbox(
            "Fixture variant",
            options=list(ALL_MOCK_RESULT_FIXTURES.keys()),
            key="_mock_preview_variant",
        )
        st.warning("⚠️ **MOCK PREVIEW ACTIVE** — Viewing simulation fixture, not real FortyGuard data.")
        render_heatmap_result(current_aoi, ALL_MOCK_RESULT_FIXTURES[variant])


def render_heatmap_page(
    api_client: BackendAPIClient | None = None,
) -> None:
    """Render the full heatmap submit and status tracking workflow."""
    _initialise_state()
    ctx = _get_execution_context()

    st.header("FortyGuard Heatmap Analysis")
    st.caption("Submit an Area of Interest (AOI) to generate high-resolution urban surface heatmaps.")

    selections = render_sidebar()
    from frontend.utils.validation import validate_heatmap_request

    # Pre-flight pure validation
    val_res = validate_heatmap_request(
        polygon_aoi=selections.polygon_aoi,
        date_val=selections.selected_date,
        time_val=selections.selected_time,
        granularity=selections.granularity,
        location_label=selections.location_label,
    )

    request_payload: dict[str, Any] | None = None
    if val_res.is_valid and selections.polygon_aoi is not None:
        request_payload = build_heatmap_request_payload(
            polygon_aoi=selections.polygon_aoi,
            selected_date=selections.selected_date,
            selected_time=selections.selected_time,
            granularity=selections.granularity,
        )
        ctx.request_params = request_payload

    # ── Pre-flight Review & Validation State ──
    with st.expander("📋 Review Heatmap Request", expanded=True):
        if val_res.is_valid and request_payload is not None:
            st.success("✓ **Request Parameters Ready** — All inputs are valid.")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"**Location:** `{selections.location_label or 'Unnamed Area'}`")
                st.markdown(f"**Points:** `{len(st.session_state.get('_polygon_points', []))} coordinates`")
            with c2:
                st.markdown(f"**Date:** `{selections.selected_date}`")
                st.markdown(f"**Time:** `{selections.selected_time}`")
            with c3:
                st.markdown(f"**Granularity:** `{selections.granularity}m`")
                st.markdown(f"**Filter Type:** `1 (Single Point)`")
            for warn in val_res.warnings:
                st.caption(f"ℹ️ *Notice:* {warn}")

            with st.expander("▸ View GeoJSON Payload Details", expanded=False):
                st.json(request_payload)
        else:
            st.error(f"⚠️ **Fix {len(val_res.errors)} Validation Error{'s' if len(val_res.errors) != 1 else ''} Before Submission:**")
            for err in val_res.errors:
                st.markdown(f"• {err}")

    # ── Submission with duplicate guard ──
    is_in_progress = ctx.is_in_progress or st.session_state.get(_STATE_KEY, READY) in {PROCESSING, SUBMITTING}

    if is_in_progress:
        submit_btn_label = "⏳ Analysis in Progress..."
        submit_disabled = True
    elif val_res.is_valid:
        submit_btn_label = "🚀 Submit Heatmap Analysis"
        submit_disabled = False
    else:
        submit_btn_label = "⚠️ Fix Validation Errors to Submit"
        submit_disabled = True

    submit_clicked = st.button(
        submit_btn_label,
        type="primary",
        key="_heatmap_submit_btn",
        disabled=submit_disabled,
    )

    # SUBMISSION BOUNDARY RULE: Zero network I/O if validation fails or in progress
    if (submit_clicked or selections.generate_clicked) and val_res.is_valid and request_payload is not None and not is_in_progress:
        if st.session_state.get(_SUBMIT_GUARD_KEY):
            st.warning("⚠️ A submission is already in progress. Please wait.")
        else:
            st.session_state[_SUBMIT_GUARD_KEY] = True
            transition_to_submitting(ctx)
            _set_state(SUBMITTING, activity_id=None, status=None, error=None)
            try:
                response = _call_backend(api_client, "submit_heatmap", request_payload)
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
                st.session_state[_SUBMITTED_AOI_KEY] = request_payload.get("polygon_aoi")
                st.session_state["_heatmap_submitted_req"] = {
                    "label": selections.location_label,
                    "date": str(selections.selected_date),
                    "time": str(selections.selected_time),
                    "granularity": selections.granularity,
                    "polygon_aoi": request_payload.get("polygon_aoi"),
                }
                _set_state(
                    PROCESSING,
                    activity_id=activity_id,
                    status="Processing",
                )
                st.success(f"Heatmap task submitted successfully! Activity ID: `{activity_id}`")

    _render_workflow_state(api_client=api_client)


if __name__ == "__main__":
    from frontend.components.design_system import inject_design_system
    inject_design_system()
    st.title("FortyGuard Heat Intelligence")
    st.caption("Comprehensive Urban Thermal Analytics & Multi-Factor Resilience Platform")
    render_heatmap_page()

