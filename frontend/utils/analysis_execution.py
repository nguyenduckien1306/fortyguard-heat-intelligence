"""Centralized Analysis Execution State Machine and Lifecycle Controller.

Strict Boundaries & Invariants:
1. One user submission creates at most one provider activity.
2. Polling, refreshing, or 'Check Again' NEVER creates a new provider activity.
3. Only an explicit, user-confirmed retry creates a new provider activity.
4. Polling timeout is an application UX observation heuristic, NOT a provider failure.
5. Incomplete, failed, or timed-out analyses NEVER enter session history.
6. ExecutionContext is strictly sanitized: never contains API keys, tokens, or signed URLs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Mapping

logger = logging.getLogger("fortyguard.analysis_execution")

# Application-level polling observation timeout (default: 5 minutes)
DEFAULT_POLLING_TIMEOUT_SECONDS: float = 300.0

_SECRET_KEYS_REGEX = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|signed[_-]?url|download[_-]?link|credentials|bearer|headers|cookies)"
)


def _record_execution_event(
    event_name: str,
    ctx: ExecutionContext,
    *,
    status: str = "SUCCESS",
) -> None:
    """Best-effort local observability hook. Never raises into the execution path."""
    try:
        from frontend.utils.observability import record_event

        record_event(
            event_name=event_name,
            activity_id=ctx.activity_id,
            attempt_number=ctx.attempt_number,
            status=status,
            metadata={
                "analysis_type": ctx.analysis_type,
                "state": ctx.state.value,
                "poll_count": ctx.poll_count,
            },
        )
    except Exception:
        logger.debug("Observability recording skipped for %s", event_name, exc_info=True)


_record_execution_event = _record_execution_event


class ExecutionState(str, Enum):
    """Lifecycle states for asynchronous FortyGuard analysis execution."""

    NEW = "NEW"
    VALIDATED = "VALIDATED"
    SUBMITTING = "SUBMITTING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    POLLING_TIMEOUT = "POLLING_TIMEOUT"


# Valid state transitions
_VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.NEW: {
        ExecutionState.NEW,
        ExecutionState.VALIDATED,
        ExecutionState.SUBMITTING,
        ExecutionState.PROCESSING,
    },
    ExecutionState.VALIDATED: {
        ExecutionState.VALIDATED,
        ExecutionState.SUBMITTING,
        ExecutionState.NEW,
    },
    ExecutionState.SUBMITTING: {
        ExecutionState.SUBMITTING,
        ExecutionState.PROCESSING,
        ExecutionState.FAILED,
        ExecutionState.NEW,
    },
    ExecutionState.PROCESSING: {
        ExecutionState.PROCESSING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.POLLING_TIMEOUT,
        ExecutionState.NEW,
    },
    ExecutionState.COMPLETED: {
        ExecutionState.COMPLETED,
        ExecutionState.NEW,
    },
    ExecutionState.FAILED: {
        ExecutionState.FAILED,
        ExecutionState.PROCESSING,
        ExecutionState.COMPLETED,
        ExecutionState.SUBMITTING,
        ExecutionState.NEW,
    },
    ExecutionState.POLLING_TIMEOUT: {
        ExecutionState.POLLING_TIMEOUT,
        ExecutionState.PROCESSING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.SUBMITTING,
        ExecutionState.NEW,
    },
}


def sanitize_execution_data(data: Any) -> Any:
    """Recursively purge any credential, token, or signed URL before storage."""
    if isinstance(data, Mapping):
        clean: dict[str, Any] = {}
        for k, v in data.items():
            if _SECRET_KEYS_REGEX.search(str(k)):
                continue
            clean[k] = sanitize_execution_data(v)
        return clean
    elif isinstance(data, (list, tuple)):
        return [sanitize_execution_data(item) for item in data]
    elif isinstance(data, str):
        if "X-Amz-Signature=" in data or "Signature=" in data:
            return "[REDACTED_SIGNED_URL]"
        return data
    return data


@dataclass
class ExecutionContext:
    """Session-local context tracking the execution of an individual analysis attempt."""

    analysis_type: str  # "heat_intelligence" | "heatmap"
    state: ExecutionState = ExecutionState.NEW
    activity_id: str | None = None
    created_at: float = field(default_factory=time.time)
    submitted_at: float | None = None
    last_polled_at: float | None = None
    poll_count: int = 0
    provider_status: str | None = None
    provider_diagnostic: dict[str, Any] | None = None
    retry_count: int = 0
    attempt_number: int = 1
    parent_activity_id: str | None = None
    error_message: str | None = None
    request_params: dict[str, Any] | None = None
    result_cached: dict[str, Any] | None = None
    polling_timeout_seconds: float = DEFAULT_POLLING_TIMEOUT_SECONDS

    @property
    def is_in_progress(self) -> bool:
        """Whether a submission or active processing is currently executing."""
        return self.state in {ExecutionState.SUBMITTING, ExecutionState.PROCESSING}

    @property
    def can_retry(self) -> bool:
        """Retry is strictly permitted only when Failed or abandoning a Polling Timeout."""
        return self.state in {ExecutionState.FAILED, ExecutionState.POLLING_TIMEOUT}

    @property
    def can_check_again(self) -> bool:
        """Check Again is available during Polling Timeout to resume without a new activity."""
        return self.state == ExecutionState.POLLING_TIMEOUT and bool(self.activity_id)

    @property
    def elapsed_seconds(self) -> float:
        """Total time elapsed since execution was created/submitted."""
        base_time = self.submitted_at or self.created_at
        return max(0.0, time.time() - base_time)

    def elapsed_seconds_at(self, current_time: float) -> float:
        """Total time elapsed at a specific point in time (for deterministic testing)."""
        base_time = self.submitted_at or self.created_at
        return max(0.0, current_time - base_time)

    def seconds_since_last_poll(self, current_time: float | None = None) -> float | None:
        """Seconds since last poll attempt was recorded."""
        if self.last_polled_at is None:
            return None
        now = current_time if current_time is not None else time.time()
        return max(0.0, now - self.last_polled_at)


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle State Transition Helpers
# ──────────────────────────────────────────────────────────────────────────────


def create_execution_context(
    analysis_type: str,
    request_params: dict[str, Any] | None = None,
    *,
    polling_timeout_seconds: float = DEFAULT_POLLING_TIMEOUT_SECONDS,
    now: float | None = None,
) -> ExecutionContext:
    """Create a new, clean ExecutionContext in NEW state."""
    current_time = now if now is not None else time.time()
    sanitized_params = sanitize_execution_data(request_params) if request_params else None
    return ExecutionContext(
        analysis_type=analysis_type,
        state=ExecutionState.NEW,
        created_at=current_time,
        request_params=sanitized_params,
        polling_timeout_seconds=polling_timeout_seconds,
    )


def transition_state(
    ctx: ExecutionContext,
    target_state: ExecutionState,
    *,
    force: bool = False,
) -> ExecutionContext:
    """Transition the ExecutionContext to a target state, validating against allowed transitions."""
    if not force:
        allowed = _VALID_TRANSITIONS.get(ctx.state, set())
        if target_state not in allowed:
            raise ValueError(
                f"Invalid execution state transition from {ctx.state.value} to {target_state.value}."
            )
    ctx.state = target_state
    return ctx


def transition_to_validated(ctx: ExecutionContext) -> ExecutionContext:
    """Transition context from NEW to VALIDATED."""
    return transition_state(ctx, ExecutionState.VALIDATED)


def transition_to_submitting(
    ctx: ExecutionContext,
    *,
    now: float | None = None,
) -> ExecutionContext:
    """Transition context to SUBMITTING before backend request is sent."""
    current_time = now if now is not None else time.time()
    ctx.submitted_at = current_time
    result = transition_state(ctx, ExecutionState.SUBMITTING)
    _record_execution_event("analysis_submitted", result)
    return result


def transition_to_processing(
    ctx: ExecutionContext,
    activity_id: str,
    *,
    provider_status: str = "Processing",
    now: float | None = None,
) -> ExecutionContext:
    """Transition context to PROCESSING with confirmed activity ID."""
    if not activity_id or not isinstance(activity_id, str) or not activity_id.strip():
        raise ValueError("Cannot transition to PROCESSING without a valid activity_id.")
    current_time = now if now is not None else time.time()
    ctx.activity_id = activity_id.strip()
    ctx.provider_status = provider_status
    ctx.last_polled_at = current_time
    ctx.poll_count = max(1, ctx.poll_count)
    result = transition_state(ctx, ExecutionState.PROCESSING)
    _record_execution_event("analysis_poll_started", result)
    return result


def record_poll_result(
    ctx: ExecutionContext,
    status_payload: dict[str, Any],
    *,
    now: float | None = None,
) -> ExecutionContext:
    """Record a status check without creating a new activity."""
    current_time = now if now is not None else time.time()
    ctx.last_polled_at = current_time
    ctx.poll_count += 1

    if ctx.state in {ExecutionState.NEW, ExecutionState.VALIDATED, ExecutionState.SUBMITTING}:
        ctx.state = ExecutionState.PROCESSING

    status = status_payload.get("status")
    ctx.provider_status = status

    if status == "Completed":
        result = status_payload.get("result")
        return transition_to_completed(ctx, result if isinstance(result, dict) else {})
    elif status == "Failed":
        diagnostic = status_payload.get("diagnostic")
        if not isinstance(diagnostic, dict):
            # Check result / payload for diagnostic info
            res = status_payload.get("result")
            if isinstance(res, dict):
                diagnostic = res
        return transition_to_failed(
            ctx,
            diagnostic=diagnostic if isinstance(diagnostic, dict) else None,
            error_message=status_payload.get("message"),
        )
    elif status == "Processing":
        # Check if observation timeout elapsed
        if check_polling_timeout(ctx, now=current_time):
            return transition_to_timeout(ctx)
        return ctx
    else:
        # Unknown status -> treat as failure with diagnostic
        return transition_to_failed(
            ctx,
            diagnostic={"status": status},
            error_message=f"FortyGuard returned an unrecognized task status: {status}.",
        )


def transition_to_completed(
    ctx: ExecutionContext,
    result: dict[str, Any],
) -> ExecutionContext:
    """Transition context to COMPLETED with sanitized result payload."""
    ctx.provider_status = "Completed"
    ctx.result_cached = sanitize_execution_data(result)
    ctx.error_message = None
    result = transition_state(ctx, ExecutionState.COMPLETED)
    _record_execution_event("analysis_poll_completed", result)
    return result


def transition_to_failed(
    ctx: ExecutionContext,
    *,
    diagnostic: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> ExecutionContext:
    """Transition context to FAILED with sanitized diagnostics."""
    ctx.provider_status = "Failed"
    ctx.provider_diagnostic = sanitize_execution_data(diagnostic) if diagnostic else None
    ctx.error_message = error_message
    result = transition_state(ctx, ExecutionState.FAILED)
    _record_execution_event("analysis_failed", result, status="FAILED")
    return result


def check_polling_timeout(
    ctx: ExecutionContext,
    *,
    now: float | None = None,
) -> bool:
    """Determine whether the configured observation window has elapsed."""
    current_time = now if now is not None else time.time()
    elapsed = ctx.elapsed_seconds_at(current_time)
    return elapsed >= ctx.polling_timeout_seconds


def transition_to_timeout(ctx: ExecutionContext) -> ExecutionContext:
    """Transition context to POLLING_TIMEOUT (never converts to FAILED)."""
    result = transition_state(ctx, ExecutionState.POLLING_TIMEOUT)
    _record_execution_event("analysis_timeout", result, status="TIMEOUT")
    return result


def resume_polling_after_timeout(
    ctx: ExecutionContext,
    *,
    now: float | None = None,
) -> ExecutionContext:
    """Resume polling an existing activity_id after a timeout without creating a new activity."""
    if not ctx.can_check_again:
        raise ValueError("Cannot check again: context is not in POLLING_TIMEOUT or lacks activity_id.")
    current_time = now if now is not None else time.time()
    ctx.last_polled_at = current_time
    # Extend observation window from this point
    ctx.submitted_at = current_time
    return transition_state(ctx, ExecutionState.PROCESSING)


def create_retry_context(
    ctx: ExecutionContext,
    *,
    now: float | None = None,
) -> ExecutionContext:
    """Create a new ExecutionContext representing Attempt N+1 linked to the parent activity."""
    if not ctx.can_retry:
        raise ValueError(
            f"Cannot retry analysis in state {ctx.state.value}. Retry is only allowed when FAILED or POLLING_TIMEOUT."
        )

    current_time = now if now is not None else time.time()
    new_ctx = ExecutionContext(
        analysis_type=ctx.analysis_type,
        state=ExecutionState.VALIDATED,
        activity_id=None,
        created_at=current_time,
        submitted_at=None,
        last_polled_at=None,
        poll_count=0,
        provider_status=None,
        provider_diagnostic=None,
        retry_count=ctx.retry_count + 1,
        attempt_number=ctx.attempt_number + 1,
        parent_activity_id=ctx.activity_id,
        error_message=None,
        request_params=ctx.request_params,
        result_cached=None,
        polling_timeout_seconds=ctx.polling_timeout_seconds,
    )
    _record_execution_event("analysis_retry", new_ctx)
    return new_ctx
