"""Comprehensive Unit Tests for Analysis Execution State Machine (Phase 12B.2).

Covers 35+ unit test cases verifying:
- State definitions and initial state
- Valid and invalid state transitions
- Polling counts, timestamps, and elapsed time calculation
- Observation timeout detection and handling (never converting to Failed)
- Retry eligibility, attempt numbering, parent_activity_id linkage
- Check-again resumption of existing activity IDs
- Recursive sanitization of credentials, API keys, tokens, and signed URLs
- Result intelligence validation
"""

from __future__ import annotations

import time
import pytest

from frontend.utils.analysis_execution import (
    DEFAULT_POLLING_TIMEOUT_SECONDS,
    ExecutionContext,
    ExecutionState,
    check_polling_timeout,
    create_execution_context,
    create_retry_context,
    record_poll_result,
    resume_polling_after_timeout,
    sanitize_execution_data,
    transition_state,
    transition_to_completed,
    transition_to_failed,
    transition_to_processing,
    transition_to_submitting,
    transition_to_timeout,
    transition_to_validated,
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Initial State & Context Creation
# ──────────────────────────────────────────────────────────────────────────────


def test_create_execution_context_default_state() -> None:
    """New execution context starts in NEW state with attempt #1 and zero retries."""
    ctx = create_execution_context("heat_intelligence", {"lat": 40.7, "lon": -74.0})
    assert ctx.analysis_type == "heat_intelligence"
    assert ctx.state == ExecutionState.NEW
    assert ctx.activity_id is None
    assert ctx.attempt_number == 1
    assert ctx.retry_count == 0
    assert ctx.poll_count == 0
    assert ctx.parent_activity_id is None
    assert ctx.is_in_progress is False
    assert ctx.can_retry is False
    assert ctx.can_check_again is False


def test_create_execution_context_custom_timeout() -> None:
    """Custom polling timeout is stored correctly."""
    ctx = create_execution_context("heatmap", polling_timeout_seconds=120.0)
    assert ctx.polling_timeout_seconds == 120.0


def test_create_execution_context_with_fixed_time() -> None:
    """Explicit fixed timestamp is recorded as created_at."""
    fixed_time = 1700000000.0
    ctx = create_execution_context("heatmap", now=fixed_time)
    assert ctx.created_at == fixed_time


# ──────────────────────────────────────────────────────────────────────────────
# 2. Valid State Transitions
# ──────────────────────────────────────────────────────────────────────────────


def test_transition_new_to_validated() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    assert ctx.state == ExecutionState.VALIDATED


def test_transition_validated_to_submitting() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    transition_to_submitting(ctx, now=100.0)
    assert ctx.state == ExecutionState.SUBMITTING
    assert ctx.submitted_at == 100.0
    assert ctx.is_in_progress is True


def test_transition_submitting_to_processing() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-test-123", now=105.0)
    assert ctx.state == ExecutionState.PROCESSING
    assert ctx.activity_id == "act-test-123"
    assert ctx.provider_status == "Processing"
    assert ctx.last_polled_at == 105.0
    assert ctx.poll_count == 1
    assert ctx.is_in_progress is True


def test_transition_processing_to_completed() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-test-123")
    transition_to_completed(ctx, {"result": "data"})
    assert ctx.state == ExecutionState.COMPLETED
    assert ctx.provider_status == "Completed"
    assert ctx.result_cached == {"result": "data"}
    assert ctx.is_in_progress is False
    assert ctx.can_retry is False


def test_transition_processing_to_failed() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-test-123")
    transition_to_failed(ctx, diagnostic={"code": "ERR"}, error_message="Task failed")
    assert ctx.state == ExecutionState.FAILED
    assert ctx.provider_status == "Failed"
    assert ctx.provider_diagnostic == {"code": "ERR"}
    assert ctx.error_message == "Task failed"
    assert ctx.is_in_progress is False
    assert ctx.can_retry is True


def test_transition_submitting_directly_to_failed() -> None:
    """If backend submission fails on the initial HTTP POST, transition directly to FAILED."""
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    transition_to_failed(ctx, error_message="Backend connection refused")
    assert ctx.state == ExecutionState.FAILED
    assert ctx.can_retry is True


def test_transition_processing_to_timeout() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_validated(ctx)
    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-test-123")
    transition_to_timeout(ctx)
    assert ctx.state == ExecutionState.POLLING_TIMEOUT
    assert ctx.is_in_progress is False
    assert ctx.can_check_again is True
    assert ctx.can_retry is True


def test_transition_completed_to_new_on_reset() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_state(ctx, ExecutionState.COMPLETED, force=True)
    transition_state(ctx, ExecutionState.NEW)
    assert ctx.state == ExecutionState.NEW


# ──────────────────────────────────────────────────────────────────────────────
# 3. Invalid State Transition Protections
# ──────────────────────────────────────────────────────────────────────────────


def test_invalid_transition_new_to_completed_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    with pytest.raises(ValueError, match="Invalid execution state transition"):
        transition_to_completed(ctx, {})


def test_invalid_transition_submitting_to_completed_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    with pytest.raises(ValueError, match="Invalid execution state transition"):
        transition_to_completed(ctx, {})


def test_invalid_transition_completed_to_processing_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_state(ctx, ExecutionState.COMPLETED, force=True)
    with pytest.raises(ValueError, match="Invalid execution state transition"):
        transition_to_processing(ctx, "act-123")


def test_transition_to_processing_without_activity_id_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    with pytest.raises(ValueError, match="valid activity_id"):
        transition_to_processing(ctx, "")


def test_transition_to_processing_with_whitespace_activity_id_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    with pytest.raises(ValueError, match="valid activity_id"):
        transition_to_processing(ctx, "   ")


# ──────────────────────────────────────────────────────────────────────────────
# 4. Polling Result Recording & State Handling
# ──────────────────────────────────────────────────────────────────────────────


def test_record_poll_processing_increments_count() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-1", now=100.0)
    assert ctx.poll_count == 1

    record_poll_result(ctx, {"status": "Processing"}, now=110.0)
    assert ctx.poll_count == 2
    assert ctx.last_polled_at == 110.0
    assert ctx.state == ExecutionState.PROCESSING


def test_record_poll_completed_transitions_to_completed() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-2", now=100.0)

    record_poll_result(ctx, {"status": "Completed", "result": {"pdf": "ready"}}, now=115.0)
    assert ctx.state == ExecutionState.COMPLETED
    assert ctx.result_cached == {"pdf": "ready"}


def test_record_poll_failed_transitions_to_failed() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-3", now=100.0)

    record_poll_result(
        ctx,
        {"status": "Failed", "diagnostic": {"code": "ERR_GRID"}, "message": "Failed"},
        now=120.0,
    )
    assert ctx.state == ExecutionState.FAILED
    assert ctx.provider_diagnostic == {"code": "ERR_GRID"}


def test_record_poll_unknown_status_transitions_to_failed() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-poll-4", now=100.0)

    record_poll_result(ctx, {"status": "Quarantined"}, now=125.0)
    assert ctx.state == ExecutionState.FAILED
    assert "unrecognized task status" in (ctx.error_message or "")


# ──────────────────────────────────────────────────────────────────────────────
# 5. Observation Timeout & Check Again
# ──────────────────────────────────────────────────────────────────────────────


def test_check_polling_timeout_false_under_limit() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    assert check_polling_timeout(ctx, now=250.0) is False


def test_check_polling_timeout_true_at_or_above_limit() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    assert check_polling_timeout(ctx, now=400.0) is True


def test_record_poll_triggers_timeout_when_observation_window_elapses() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-timeout-1", now=100.0)

    # Poll at 450.0 (350s elapsed >= 300s)
    record_poll_result(ctx, {"status": "Processing"}, now=450.0)
    assert ctx.state == ExecutionState.POLLING_TIMEOUT
    # Invariant: POLLING_TIMEOUT is NOT marked as Failed
    assert ctx.provider_status == "Processing"
    assert ctx.can_check_again is True
    assert ctx.can_retry is True


def test_resume_polling_after_timeout_resets_window_and_preserves_activity_id() -> None:
    """Check Again resumes polling existing activity ID with 0 POST submissions."""
    ctx = create_execution_context("heat_intelligence", now=100.0, polling_timeout_seconds=300.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-resume-1", now=100.0)
    transition_to_timeout(ctx)

    resume_polling_after_timeout(ctx, now=500.0)
    assert ctx.state == ExecutionState.PROCESSING
    assert ctx.activity_id == "act-resume-1"
    assert ctx.submitted_at == 500.0
    assert ctx.last_polled_at == 500.0


def test_resume_polling_when_not_in_timeout_raises() -> None:
    ctx = create_execution_context("heat_intelligence")
    with pytest.raises(ValueError, match="Cannot check again"):
        resume_polling_after_timeout(ctx)


# ──────────────────────────────────────────────────────────────────────────────
# 6. User-Controlled Retry & Identity Tracking
# ──────────────────────────────────────────────────────────────────────────────


def test_create_retry_context_from_failed_attempt() -> None:
    """Retrying from FAILED creates attempt #2 linked to parent activity."""
    ctx = create_execution_context("heat_intelligence", {"lat": 40.7, "lon": -74.0}, now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-attempt-1", now=105.0)
    transition_to_failed(ctx, diagnostic={"code": "ERR"}, error_message="Failed")

    retry_ctx = create_retry_context(ctx, now=200.0)
    assert retry_ctx.analysis_type == "heat_intelligence"
    assert retry_ctx.state == ExecutionState.VALIDATED
    assert retry_ctx.activity_id is None
    assert retry_ctx.parent_activity_id == "act-attempt-1"
    assert retry_ctx.attempt_number == 2
    assert retry_ctx.retry_count == 1
    assert retry_ctx.poll_count == 0
    assert retry_ctx.created_at == 200.0
    assert retry_ctx.request_params == {"lat": 40.7, "lon": -74.0}
    assert retry_ctx.provider_diagnostic is None


def test_create_retry_context_from_timeout_attempt() -> None:
    """Retrying from POLLING_TIMEOUT creates attempt #2 linked to parent activity."""
    ctx = create_execution_context("heatmap", {"label": "AOI 1"}, now=100.0)
    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-timeout-parent", now=105.0)
    transition_to_timeout(ctx)

    retry_ctx = create_retry_context(ctx, now=500.0)
    assert retry_ctx.attempt_number == 2
    assert retry_ctx.parent_activity_id == "act-timeout-parent"
    assert retry_ctx.retry_count == 1
    assert retry_ctx.state == ExecutionState.VALIDATED


def test_create_retry_context_multiple_generations() -> None:
    """Multiple retries increment attempt_number and retry_count accurately."""
    ctx1 = create_execution_context("heat_intelligence")
    transition_state(ctx1, ExecutionState.FAILED, force=True)
    ctx1.activity_id = "act-gen-1"

    ctx2 = create_retry_context(ctx1)
    transition_state(ctx2, ExecutionState.FAILED, force=True)
    ctx2.activity_id = "act-gen-2"

    ctx3 = create_retry_context(ctx2)
    assert ctx3.attempt_number == 3
    assert ctx3.retry_count == 2
    assert ctx3.parent_activity_id == "act-gen-2"


def test_create_retry_when_not_eligible_raises() -> None:
    """Cannot retry when context is in NEW, VALIDATED, SUBMITTING, PROCESSING, or COMPLETED."""
    for invalid_state in (
        ExecutionState.NEW,
        ExecutionState.VALIDATED,
        ExecutionState.SUBMITTING,
        ExecutionState.PROCESSING,
        ExecutionState.COMPLETED,
    ):
        ctx = create_execution_context("heat_intelligence")
        transition_state(ctx, invalid_state, force=True)
        with pytest.raises(ValueError, match="Cannot retry analysis in state"):
            create_retry_context(ctx)


# ──────────────────────────────────────────────────────────────────────────────
# 7. Elapsed Time & Relative Timers
# ──────────────────────────────────────────────────────────────────────────────


def test_elapsed_seconds_calculation() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    transition_to_submitting(ctx, now=110.0)
    assert ctx.elapsed_seconds_at(150.0) == 40.0


def test_seconds_since_last_poll() -> None:
    ctx = create_execution_context("heat_intelligence", now=100.0)
    assert ctx.seconds_since_last_poll(120.0) is None

    transition_to_submitting(ctx, now=100.0)
    transition_to_processing(ctx, "act-timer-1", now=110.0)
    assert ctx.seconds_since_last_poll(125.0) == 15.0


# ──────────────────────────────────────────────────────────────────────────────
# 8. Deep Recursive Credential & Secret Sanitization
# ──────────────────────────────────────────────────────────────────────────────


def test_sanitize_execution_data_removes_api_keys() -> None:
    raw = {
        "api_key": "fg-secret-123",
        "api-key": "fg-secret-456",
        "apiKey": "fg-secret-789",
        "valid_param": 42,
    }
    cleaned = sanitize_execution_data(raw)
    assert "api_key" not in cleaned
    assert "api-key" not in cleaned
    assert "apiKey" not in cleaned
    assert cleaned["valid_param"] == 42


def test_sanitize_execution_data_removes_tokens_and_bearer() -> None:
    raw = {
        "token": "bearer-123",
        "authorization": "Bearer abc",
        "nested": {
            "bearer_token": "secret",
            "password": "pass",
            "safe": "urban",
        },
    }
    cleaned = sanitize_execution_data(raw)
    assert "token" not in cleaned
    assert "authorization" not in cleaned
    assert "bearer_token" not in cleaned.get("nested", {})
    assert "password" not in cleaned.get("nested", {})
    assert cleaned["nested"]["safe"] == "urban"


def test_sanitize_execution_data_redacts_s3_signed_urls() -> None:
    raw = {
        "download_link": "https://bucket.s3.amazonaws.com/report.pdf?X-Amz-Signature=secret",
        "other_url": "https://bucket.s3.amazonaws.com/data.json?Signature=secret",
        "regular_text": "hello world",
    }
    cleaned = sanitize_execution_data(raw)
    assert "download_link" not in cleaned
    assert cleaned["other_url"] == "[REDACTED_SIGNED_URL]"
    assert cleaned["regular_text"] == "hello world"


def test_execution_context_request_params_are_sanitized() -> None:
    raw_params = {
        "latitude": 40.7,
        "longitude": -74.0,
        "api_key": "leak-attempt",
        "token": "secret-token",
    }
    ctx = create_execution_context("heat_intelligence", raw_params)
    assert "api_key" not in ctx.request_params
    assert "token" not in ctx.request_params
    assert ctx.request_params["latitude"] == 40.7
