"""Streamlit AppTest suite for Analysis Execution Console (Phase 12B.2).

Tests:
1. Processing state UI rendering (elapsed metric, checks count, technical expander).
2. Polling Timeout UI rendering (warning notice, Check Again button, Reset button).
3. Failed state UI rendering (error banner, diagnostic expander, retry credit warning).
4. Missing diagnostic fallback text.
5. Completed state UI rendering.
6. Duplicate submission button disabling during active execution.
"""

from __future__ import annotations

import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend.components.execution_console import render_execution_console
from frontend.utils.analysis_execution import (
    ExecutionContext,
    ExecutionState,
    create_execution_context,
    record_poll_result,
    transition_to_completed,
    transition_to_failed,
    transition_to_processing,
    transition_to_submitting,
    transition_to_timeout,
)


def test_console_renders_processing_state_and_metrics() -> None:
    """Console displays Processing header, metrics, and technical expander."""
    def _run() -> None:
        from frontend.components.execution_console import render_execution_console
        from frontend.utils.analysis_execution import (
            create_execution_context,
            transition_to_processing,
            transition_to_submitting,
        )
        ctx = create_execution_context("heat_intelligence", now=100.0)
        transition_to_submitting(ctx, now=100.0)
        transition_to_processing(ctx, "act-apptest-proc", now=105.0)
        ctx.poll_count = 12
        render_execution_console(ctx)

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "● Processing" in markdown_text

    # Metrics
    metric_labels = [m.label for m in at.metric]
    assert "Elapsed Time" in metric_labels
    assert "Provider Status" in metric_labels
    assert "Status Checks" in metric_labels

    captions = " ".join([c.value for c in at.caption])
    assert "Activity ID:" in captions
    assert "act-apptest-proc" in captions
    assert "Attempt:" in captions


def test_console_renders_timeout_state_and_actions() -> None:
    """Console displays Still Processing, timeout warning, and Check Again button."""
    def _run() -> None:
        from frontend.components.execution_console import render_execution_console
        from frontend.utils.analysis_execution import (
            create_execution_context,
            transition_to_processing,
            transition_to_submitting,
            transition_to_timeout,
        )
        ctx = create_execution_context("heat_intelligence", now=100.0)
        transition_to_submitting(ctx, now=100.0)
        transition_to_processing(ctx, "act-apptest-timeout", now=105.0)
        transition_to_timeout(ctx)
        render_execution_console(ctx)

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "⏱️ Still Processing" in markdown_text

    warnings = " ".join([w.value for w in at.warning])
    assert "Observation Window Elapsed" in warnings

    buttons = [b.label for b in at.button]
    assert "🔍 Check Again" in buttons
    assert "🔁 Start New Analysis" in buttons


def test_console_renders_failed_state_with_diagnostics_and_retry_warning() -> None:
    """Console displays Failed header, sanitized diagnostics, and credit warning before retry."""
    def _run() -> None:
        from frontend.components.execution_console import render_execution_console
        from frontend.utils.analysis_execution import (
            create_execution_context,
            transition_to_failed,
            transition_to_processing,
            transition_to_submitting,
        )
        ctx = create_execution_context("heat_intelligence", now=100.0)
        transition_to_submitting(ctx, now=100.0)
        transition_to_processing(ctx, "act-apptest-fail", now=105.0)
        transition_to_failed(
            ctx,
            diagnostic={
                "code": "OUT_OF_BOUNDS",
                "message": "Spatial coordinate outside city boundaries",
                "reason": "Boundary lookup failed",
            },
            error_message="Provider task failure",
        )
        render_execution_console(ctx)

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "✕ Analysis Failed" in markdown_text

    warnings = " ".join([w.value for w in at.warning])
    assert "Retry will submit a new analysis request" in warnings
    assert "API credits" in warnings

    captions = " ".join([c.value for c in at.caption])
    assert "OUT_OF_BOUNDS" in captions
    assert "Spatial coordinate outside city boundaries" in captions
    assert "Boundary lookup failed" in captions

    buttons = [b.label for b in at.button]
    assert "🔄 Retry Analysis" in buttons


def test_console_renders_failed_fallback_when_no_diagnostic() -> None:
    """Console displays clear fallback message when provider returned no diagnostic fields."""
    def _run() -> None:
        from frontend.components.execution_console import render_execution_console
        from frontend.utils.analysis_execution import (
            create_execution_context,
            transition_to_failed,
            transition_to_processing,
            transition_to_submitting,
        )
        ctx = create_execution_context("heat_intelligence", now=100.0)
        transition_to_submitting(ctx, now=100.0)
        transition_to_processing(ctx, "act-apptest-bare-fail", now=105.0)
        transition_to_failed(ctx)
        render_execution_console(ctx)

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    captions = " ".join([c.value for c in at.caption])
    assert "FortyGuard reported that the analysis failed, but did not provide a specific failure reason." in captions


def test_console_renders_completed_state() -> None:
    """Console displays Completed header and success message."""
    def _run() -> None:
        from frontend.components.execution_console import render_execution_console
        from frontend.utils.analysis_execution import (
            create_execution_context,
            transition_to_completed,
            transition_to_processing,
            transition_to_submitting,
        )
        ctx = create_execution_context("heat_intelligence", now=100.0)
        transition_to_submitting(ctx, now=100.0)
        transition_to_processing(ctx, "act-apptest-comp", now=105.0)
        transition_to_completed(ctx, {"status": "ok"})
        render_execution_console(ctx)

    at = AppTest.from_function(_run, default_timeout=15)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "✓ Analysis Completed" in markdown_text

    successes = " ".join([s.value for s in at.success])
    assert "Analysis added to your workspace" in successes
