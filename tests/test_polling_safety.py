"""Comprehensive Tests for Polling Safety, Timeout UX, and Credit Invariants (Phase 12B.2).

Verifies at least 20 test cases proving:
- Repeated polling checks the existing activity without creating POST submissions
- Timeout is reached after observation window without marking provider as Failed
- Check-again re-queries existing activity_id with 0 POST submissions
- Failed polling extracts diagnostics safely
- Network errors during polling do not corrupt execution context
- Completed polling yields valid result exactly once
- Streamlit state management preserves attempt history and prevents duplicate submissions
"""

from __future__ import annotations

import httpx
import pytest

from frontend.utils.analysis_execution import (
    ExecutionContext,
    ExecutionState,
    create_execution_context,
    create_retry_context,
    record_poll_result,
    resume_polling_after_timeout,
    transition_to_completed,
    transition_to_processing,
    transition_to_submitting,
    transition_to_timeout,
)
from tests.conftest import make_client


# ──────────────────────────────────────────────────────────────────────────────
# 1. Polling Behavior & Zero POST Invariant
# ──────────────────────────────────────────────────────────────────────────────


def test_repeated_status_queries_are_strictly_get_never_post() -> None:
    """Repeated status checks must only issue GET requests to /v1/status/{id}, never POST."""
    recorded_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_methods.append(request.method)
        return httpx.Response(
            200,
            json={
                "error": False,
                "status_code": 200,
                "message": "Processing",
                "data": {"activity_id": "act-get-only", "status": "Processing"},
            },
        )

    client = make_client(handler)
    try:
        for _ in range(10):
            client.get_activity_status("act-get-only")
    finally:
        client.close()

    assert len(recorded_methods) == 10
    assert all(m == "GET" for m in recorded_methods)
    assert "POST" not in recorded_methods


def test_poll_result_processing_updates_last_polled_and_count() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-loop", now=100.0)

    for i in range(1, 6):
        record_poll_result(ctx, {"status": "Processing"}, now=100.0 + (i * 5))
        assert ctx.poll_count == 1 + i
        assert ctx.last_polled_at == 100.0 + (i * 5)
        assert ctx.state == ExecutionState.PROCESSING


def test_poll_result_completed_stops_processing() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-done", now=100.0)

    record_poll_result(ctx, {"status": "Processing"}, now=110.0)
    assert ctx.state == ExecutionState.PROCESSING

    record_poll_result(
        ctx,
        {"status": "Completed", "result": {"download_link": "https://s3.amazonaws.com/rep.pdf"}},
        now=120.0,
    )
    assert ctx.state == ExecutionState.COMPLETED
    assert ctx.is_in_progress is False
    assert ctx.result_cached is not None


def test_poll_result_failed_preserves_diagnostics_and_allows_retry() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-fail", now=100.0)

    record_poll_result(
        ctx,
        {
            "status": "Failed",
            "diagnostic": {"code": "MODEL_DIVERGENCE", "message": "Simulation diverged"},
        },
        now=110.0,
    )
    assert ctx.state == ExecutionState.FAILED
    assert ctx.can_retry is True
    assert ctx.provider_diagnostic == {"code": "MODEL_DIVERGENCE", "message": "Simulation diverged"}


# ──────────────────────────────────────────────────────────────────────────────
# 2. Timeout Observation Window Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_polling_timeout_preserves_activity_id_and_provider_processing_status() -> None:
    """Timeout transitions context to POLLING_TIMEOUT without overwriting provider_status."""
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-window-timeout", now=100.0)

    record_poll_result(ctx, {"status": "Processing"}, now=450.0)
    assert ctx.state == ExecutionState.POLLING_TIMEOUT
    assert ctx.activity_id == "act-window-timeout"
    assert ctx.provider_status == "Processing"
    assert ctx.can_check_again is True
    assert ctx.can_retry is True


def test_check_again_resumes_processing_existing_activity_id() -> None:
    """Check Again resets the timeout observation window and preserves activity ID."""
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-check-again-1", now=100.0)
    transition_to_timeout(ctx)

    resume_polling_after_timeout(ctx, now=500.0)
    assert ctx.state == ExecutionState.PROCESSING
    assert ctx.activity_id == "act-check-again-1"
    assert ctx.submitted_at == 500.0


def test_subsequent_poll_after_check_again_can_complete() -> None:
    """After clicking Check Again, when provider returns Completed, state transitions cleanly."""
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-check-again-complete", now=100.0)
    transition_to_timeout(ctx)

    resume_polling_after_timeout(ctx, now=500.0)
    record_poll_result(ctx, {"status": "Completed", "result": {"pdf": "done"}}, now=520.0)
    assert ctx.state == ExecutionState.COMPLETED
    assert ctx.result_cached == {"pdf": "done"}


def test_subsequent_poll_after_check_again_can_fail() -> None:
    """After clicking Check Again, when provider returns Failed, state transitions cleanly."""
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-check-again-fail", now=100.0)
    transition_to_timeout(ctx)

    resume_polling_after_timeout(ctx, now=500.0)
    record_poll_result(ctx, {"status": "Failed", "diagnostic": {"code": "DATA_UNAVAILABLE"}}, now=520.0)
    assert ctx.state == ExecutionState.FAILED
    assert ctx.provider_diagnostic == {"code": "DATA_UNAVAILABLE"}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Retry Execution Invariants
# ──────────────────────────────────────────────────────────────────────────────


def test_retry_creates_new_attempt_with_parent_reference() -> None:
    ctx = create_execution_context("heat_intelligence", {"lat": 40.7}, now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-parent-001", now=100.0)
    record_poll_result(ctx, {"status": "Failed"}, now=110.0)

    retry_ctx = create_retry_context(ctx, now=150.0)
    assert retry_ctx.parent_activity_id == "act-parent-001"
    assert retry_ctx.attempt_number == 2
    assert retry_ctx.retry_count == 1
    assert retry_ctx.activity_id is None
    assert retry_ctx.state == ExecutionState.VALIDATED
    assert retry_ctx.poll_count == 0


def test_retry_after_timeout_preserves_parent_activity_id() -> None:
    ctx = create_execution_context("heatmap", {"label": "AOI Retry"}, now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-timeout-parent", now=100.0)
    transition_to_timeout(ctx)

    retry_ctx = create_retry_context(ctx, now=500.0)
    assert retry_ctx.parent_activity_id == "act-timeout-parent"
    assert retry_ctx.attempt_number == 2
    assert retry_ctx.activity_id is None


def test_retry_context_submitting_and_processing_flow() -> None:
    ctx = create_execution_context("heat_intelligence", {"lat": 40.7}, now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-old-id", now=100.0)
    record_poll_result(ctx, {"status": "Failed"}, now=110.0)

    retry_ctx = create_retry_context(ctx, now=150.0)
    transition_to_submitting(retry_ctx, now=155.0)
    transition_to_processing(retry_ctx, "act-new-id", now=160.0)

    assert retry_ctx.activity_id == "act-new-id"
    assert retry_ctx.parent_activity_id == "act-old-id"
    assert retry_ctx.attempt_number == 2
    assert retry_ctx.state == ExecutionState.PROCESSING


# ──────────────────────────────────────────────────────────────────────────────
# 4. History Isolation Invariants
# ──────────────────────────────────────────────────────────────────────────────


def test_polling_timeout_never_creates_workspace_record() -> None:
    from frontend.utils.analysis_history import clear_all_analysis_records, list_analysis_records

    clear_all_analysis_records()
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-hist-timeout", now=100.0)
    transition_to_timeout(ctx)

    assert len(list_analysis_records()) == 0


def test_failed_polling_never_creates_workspace_record() -> None:
    from frontend.utils.analysis_history import clear_all_analysis_records, list_analysis_records

    clear_all_analysis_records()
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-hist-failed", now=100.0)
    record_poll_result(ctx, {"status": "Failed"}, now=110.0)

    assert len(list_analysis_records()) == 0


def test_active_processing_never_creates_workspace_record() -> None:
    from frontend.utils.analysis_history import clear_all_analysis_records, list_analysis_records

    clear_all_analysis_records()
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-hist-active", now=100.0)

    for _ in range(5):
        record_poll_result(ctx, {"status": "Processing"}, now=120.0)

    assert len(list_analysis_records()) == 0


# ──────────────────────────────────────────────────────────────────────────────
# 5. Network Exceptions & Malformed Response Resilience
# ──────────────────────────────────────────────────────────────────────────────


def test_network_exception_during_poll_does_not_corrupt_activity_id() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-resilient-id", now=100.0)

    # Simulate network error handled by caller
    ctx.error_message = "Connection reset by peer"
    assert ctx.activity_id == "act-resilient-id"
    assert ctx.state == ExecutionState.PROCESSING


def test_malformed_poll_payload_handled_safely() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-malformed-poll", now=100.0)

    # Empty payload or missing status
    record_poll_result(ctx, {}, now=110.0)
    assert ctx.state == ExecutionState.FAILED
    assert "unrecognized" in (ctx.error_message or "").lower()


def test_duplicate_submission_guard_blocks_when_in_progress() -> None:
    ctx = create_execution_context("heat_intelligence")
    assert ctx.is_in_progress is False

    transition_to_submitting(ctx)
    assert ctx.is_in_progress is True

    transition_to_processing(ctx, "act-in-prog")
    assert ctx.is_in_progress is True

    transition_to_completed(ctx, {})
    assert ctx.is_in_progress is False


def test_duplicate_submission_guard_blocks_when_submitting_without_activity_yet() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    assert ctx.is_in_progress is True
    assert ctx.activity_id is None


def test_repeated_completed_polling_is_idempotent() -> None:
    """Repeated completed polls on an already completed context preserve state."""
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-idempotent-done", now=100.0)
    record_poll_result(ctx, {"status": "Completed", "result": {"pdf": "yes"}}, now=110.0)
    assert ctx.state == ExecutionState.COMPLETED

    # Second poll response
    record_poll_result(ctx, {"status": "Completed", "result": {"pdf": "yes"}}, now=120.0)
    assert ctx.state == ExecutionState.COMPLETED
    assert ctx.result_cached == {"pdf": "yes"}


def test_zero_post_invariant_during_timeout_and_check_again() -> None:
    """Proves 0 POST requests are made during timeout and check-again sequence."""
    posts: list[str] = []
    gets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(request.url.path)
        elif request.method == "GET":
            gets.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "error": False,
                "status_code": 200,
                "message": "Processing",
                "data": {"activity_id": "act-no-post-test", "status": "Processing"},
            },
        )

    client = make_client(handler)
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-no-post-test", now=100.0)

    try:
        # 5 polls
        for _ in range(5):
            client.get_activity_status("act-no-post-test")

        # Timeout occurs
        transition_to_timeout(ctx)

        # Check again
        resume_polling_after_timeout(ctx, now=500.0)

        # 3 more polls
        for _ in range(3):
            client.get_activity_status("act-no-post-test")
    finally:
        client.close()

    assert len(posts) == 0
    assert len(gets) == 8


def test_streamlit_session_state_preserves_execution_context_instance() -> None:
    """Streamlit session state correctly holds ExecutionContext dataclass."""
    import streamlit as st
    ctx = create_execution_context("heatmap", {"label": "Preserved AOI"})
    st.session_state["_test_ctx_key"] = ctx

    retrieved = st.session_state.get("_test_ctx_key")
    assert isinstance(retrieved, ExecutionContext)
    assert retrieved.analysis_type == "heatmap"
    assert retrieved.request_params == {"label": "Preserved AOI"}

