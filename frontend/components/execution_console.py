"""Execution Console UI Component for FortyGuard Asynchronous Analysis.

Provides transparent, credit-conscious observation, timeout handling,
and explicit user-controlled retry for both Heat Intelligence and Heatmap analyses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
import streamlit as st

from frontend.utils.analysis_execution import (
    ExecutionContext,
    ExecutionState,
)


def format_elapsed_time(seconds: float) -> str:
    """Format seconds into human-readable elapsed time e.g. '1m 42s' or '35s'."""
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    rem_secs = secs % 60
    return f"{mins}m {rem_secs}s"


def format_relative_time(timestamp: float | None) -> str:
    """Format an epoch timestamp into relative time e.g. '4s ago' or 'just now'."""
    if timestamp is None:
        return "never"
    import time
    diff = int(time.time() - timestamp)
    if diff < 2:
        return "just now"
    if diff < 60:
        return f"{diff}s ago"
    mins = diff // 60
    return f"{mins}m ago"


def render_execution_console(
    ctx: ExecutionContext,
    *,
    on_refresh: Callable[[], None] | None = None,
    on_poll: Callable[[], None] | None = None,
    on_check_again: Callable[[], None] | None = None,
    on_retry: Callable[[], None] | None = None,
    on_reset: Callable[[], None] | None = None,
    key_prefix: str = "console",
) -> None:
    """Render the standardized Analysis Execution Console."""
    if ctx.state == ExecutionState.NEW:
        return

    st.subheader("Analysis Execution")

    with st.container(border=True):
        # ── State Badge & Top Info ──
        if ctx.state == ExecutionState.SUBMITTING:
            st.info("🚀 **Submitting Analysis Request** to FortyGuard...")

        elif ctx.state == ExecutionState.PROCESSING:
            st.markdown("#### ● Processing")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Elapsed Time", format_elapsed_time(ctx.elapsed_seconds))
            with c2:
                st.metric("Provider Status", ctx.provider_status or "Processing")
            with c3:
                st.metric("Last Checked", format_relative_time(ctx.last_polled_at))
            with c4:
                st.metric("Status Checks", ctx.poll_count)

            st.caption(
                "ℹ️ *Heat Intelligence & Heatmap analyses perform multi-factor cloud modeling and take several minutes.*"
            )

        elif ctx.state == ExecutionState.POLLING_TIMEOUT:
            st.markdown("#### ⏱️ Still Processing")
            st.warning(
                "**Observation Window Elapsed**: The provider has not returned a completed result "
                "within the application's normal observation window (5 min). "
                "The provider may still be processing this analysis."
            )
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Elapsed Time", format_elapsed_time(ctx.elapsed_seconds))
            with c2:
                st.metric("Status Checks", ctx.poll_count)

        elif ctx.state == ExecutionState.FAILED:
            st.markdown("#### ✕ Analysis Failed")
            error_text = ctx.error_message or "FortyGuard reported that the analysis failed on the provider side."
            st.error(f"🔴 **Task Failed**: {error_text}")

            diag = ctx.provider_diagnostic
            with st.expander("🔍 Provider Diagnostic Information", expanded=False):
                st.caption(f"**Activity ID:** `{ctx.activity_id or 'Unknown'}`")
                st.caption(f"**Status:** `Failed`")
                has_diag_info = False
                if isinstance(diag, dict) and diag:
                    if diag.get("code"):
                        st.caption(f"**Error Code:** `{diag['code']}`")
                        has_diag_info = True
                    if diag.get("message") and diag.get("message") != "Failed":
                        st.caption(f"**Message:** {diag['message']}")
                        has_diag_info = True
                    if diag.get("reason"):
                        st.caption(f"**Reason:** {diag['reason']}")
                        has_diag_info = True
                    if diag.get("details"):
                        st.caption(f"**Details:** {diag['details']}")
                        has_diag_info = True
                    for k, v in diag.items():
                        if k not in {"code", "message", "reason", "details"} and v:
                            st.caption(f"**{k.replace('_', ' ').title()}:** {v}")
                            has_diag_info = True

                if not has_diag_info:
                    st.caption("FortyGuard reported that the analysis failed, but did not provide a specific failure reason.")

        elif ctx.state == ExecutionState.COMPLETED:
            st.markdown("#### ✓ Analysis Completed")
            st.success("✓ Result received and validated. Analysis added to your workspace.")

        # ── Technical Details Expander ──
        if ctx.activity_id:
            with st.expander("▸ Technical Polling Details", expanded=False):
                st.caption(f"**Activity ID:** `{ctx.activity_id}`")
                st.caption(f"**Execution State:** `{ctx.state.value}`")
                st.caption(f"**Attempt:** #{ctx.attempt_number} (Retries: {ctx.retry_count})")
                if ctx.parent_activity_id:
                    st.caption(f"**Parent Activity ID:** `{ctx.parent_activity_id}`")
                st.caption(f"**Poll Count:** {ctx.poll_count}")
                if ctx.last_polled_at:
                    poll_time_str = datetime.fromtimestamp(ctx.last_polled_at).strftime("%Y-%m-%d %H:%M:%S")
                    st.caption(f"**Last Poll Timestamp:** `{poll_time_str}`")

        # ── Action Buttons ──
        if ctx.state == ExecutionState.PROCESSING:
            btn_c1, btn_c2, btn_c3 = st.columns(3)
            with btn_c1:
                if st.button("🔄 Refresh Status", key=f"_{key_prefix}_refresh_btn"):
                    if on_refresh:
                        on_refresh()
            with btn_c2:
                if st.button("⏳ Poll Until Complete", key=f"_{key_prefix}_poll_btn"):
                    if on_poll:
                        on_poll()
            with btn_c3:
                if st.button("🔁 New Analysis", key=f"_{key_prefix}_reset_btn"):
                    if on_reset:
                        on_reset()

        elif ctx.state == ExecutionState.POLLING_TIMEOUT:
            act_c1, act_c2 = st.columns(2)
            with act_c1:
                if st.button("🔍 Check Again", key=f"_{key_prefix}_check_again_btn", type="primary"):
                    if on_check_again:
                        on_check_again()
            with act_c2:
                if st.button("🔁 Start New Analysis", key=f"_{key_prefix}_reset_timeout_btn"):
                    if on_reset:
                        on_reset()

        elif ctx.state == ExecutionState.FAILED:
            st.warning(
                "⚠️ **Retry will submit a new analysis request to the provider and may consume API credits.**"
            )
            ret_c1, ret_c2 = st.columns(2)
            with ret_c1:
                if st.button("🔄 Retry Analysis", key=f"_{key_prefix}_retry_btn", type="primary"):
                    if on_retry:
                        on_retry()
            with ret_c2:
                if st.button("🔁 Start New Analysis", key=f"_{key_prefix}_reset_fail_btn"):
                    if on_reset:
                        on_reset()

        elif ctx.state == ExecutionState.COMPLETED:
            if st.button("🔁 Start New Analysis", key=f"_{key_prefix}_reset_done_btn"):
                if on_reset:
                    on_reset()
