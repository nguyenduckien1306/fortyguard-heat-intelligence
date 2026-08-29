"""Streamlit Alert Center Component.

Provides a unified interface for operational signals:
- Active signals with priority badges and quick actions
- Acknowledged signals
- Dismissed signals archive
- Integrated alert policy configuration

Strict Invariants:
1. Zero HTTP / Network I/O — operates purely on in-memory session records and signals.
2. Actions (Acknowledge, Dismiss, Restore, Investigate) generate zero network calls.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence
import streamlit as st

from frontend.components.alert_configuration import render_alert_configuration_panel
from frontend.utils.alert_engine import (
    LIFECYCLE_ACKNOWLEDGED,
    LIFECYCLE_DISMISSED,
    LIFECYCLE_INVESTIGATING,
    LIFECYCLE_NEW,
    acknowledge_signal,
    dismiss_signal,
    evaluate_alert_policies,
    filter_signals_by_lifecycle,
    get_signal_lifecycle_status,
    restore_signal,
)
from frontend.utils.alert_policies import get_alert_policies
from frontend.utils.investigation_queue import add_to_investigation_queue
from frontend.utils.operational_intelligence import (
    OperationalSignal,
    generate_operational_signals,
)
from frontend.utils.priority import explain_priority_score, get_signal_priority, sort_signals_by_priority


def render_alert_center(
    records: Sequence[Any],
    on_investigate: Callable[[OperationalSignal], None] | None = None,
) -> None:
    """Render the full Alert Center management hub."""
    st.markdown("### Operational Alert Center")
    st.caption("Active monitoring, signal lifecycle management, and policy enforcement across completed session analyses.")

    # Generate signals dynamically from completed analyses + policy evaluations
    base_signals = generate_operational_signals(records)
    policies = get_alert_policies()
    policy_signals = evaluate_alert_policies(records, policies)

    # Combine and sort by priority
    combined_signals = sort_signals_by_priority(base_signals + policy_signals)

    tab_active, tab_ack, tab_dsm, tab_policies = st.tabs([
        "Active Signals",
        "Acknowledged",
        "Dismissed Archive",
        "Alert Policies",
    ])

    with tab_active:
        active_signals = [
            s for s in combined_signals
            if get_signal_lifecycle_status(s.signal_id) in (LIFECYCLE_NEW, LIFECYCLE_INVESTIGATING)
        ]
        _render_signals_list(
            active_signals,
            lifecycle_context="active",
            on_investigate=on_investigate,
        )

    with tab_ack:
        ack_signals = filter_signals_by_lifecycle(combined_signals, LIFECYCLE_ACKNOWLEDGED)
        _render_signals_list(
            ack_signals,
            lifecycle_context="acknowledged",
            on_investigate=on_investigate,
        )

    with tab_dsm:
        dsm_signals = filter_signals_by_lifecycle(combined_signals, LIFECYCLE_DISMISSED)
        _render_signals_list(
            dsm_signals,
            lifecycle_context="dismissed",
            on_investigate=on_investigate,
        )

    with tab_policies:
        render_alert_configuration_panel()


def _render_signals_list(
    signals: list[OperationalSignal],
    lifecycle_context: str,
    on_investigate: Callable[[OperationalSignal], None] | None = None,
) -> None:
    """Render a filterable, interactive list of signals."""
    if not signals:
        if lifecycle_context == "active":
            st.info("🟢 No active operational signals detected from your completed analyses.")
        elif lifecycle_context == "acknowledged":
            st.info("No acknowledged signals in the current session.")
        else:
            st.info("No dismissed signals in archive.")
        return

    # ── Search & Filter Controls ──
    c_search, c_sev_filter = st.columns([6, 4])
    with c_search:
        search_q = st.text_input(
            "Search signals",
            placeholder="Search by location, signal ID, or keyword...",
            key=f"_sig_search_{lifecycle_context}",
            label_visibility="collapsed",
        )
    with c_sev_filter:
        sev_filter = st.selectbox(
            "Filter Severity",
            options=["All", "CRITICAL", "ELEVATED", "WATCH", "INFO"],
            key=f"_sig_sev_{lifecycle_context}",
            label_visibility="collapsed",
        )

    # Filter
    filtered = signals
    if search_q:
        q_lower = search_q.lower()
        filtered = [
            s for s in filtered
            if (q_lower in s.title.lower() or q_lower in s.description.lower() or q_lower in s.analysis_id.lower() or q_lower in s.signal_id.lower())
        ]
    if sev_filter != "All":
        filtered = [s for s in filtered if s.severity.upper() == sev_filter.upper()]

    st.caption(f"Showing **{len(filtered)}** of **{len(signals)}** {lifecycle_context} signals")

    for sig in filtered:
        render_signal_card(sig, lifecycle_context=lifecycle_context, on_investigate=on_investigate)


def render_signal_card(
    sig: OperationalSignal,
    lifecycle_context: str = "active",
    on_investigate: Callable[[OperationalSignal], None] | None = None,
    prefix: str = "",
) -> None:
    """Render a single high-visibility operational signal card."""
    score, priority_label = get_signal_priority(sig)

    sev_color = "red" if sig.severity == "CRITICAL" else ("orange" if sig.severity == "ELEVATED" else ("blue" if sig.severity == "WATCH" else "gray"))
    pri_badge = f":{sev_color}[**{priority_label.upper()}** ({score:.0f})]"

    with st.container(border=True):
        col_main, col_btns = st.columns([7, 3])

        with col_main:
            st.markdown(f"#### :{sev_color}[● {sig.severity}] {sig.title} · {pri_badge}")
            st.markdown(f"{sig.description}")

            # Evidence chips & metadata
            meta_parts: list[str] = [f"**Analysis ID:** `{sig.analysis_id}`"]
            if sig.observed_value is not None:
                meta_parts.append(f"**Observed:** `{sig.observed_value:.1f}`")
            if sig.threshold_value is not None:
                meta_parts.append(f"**Threshold:** `{sig.threshold_value:.1f}`")
            meta_parts.append(f"**Data Quality:** `{sig.data_quality}`")

            st.caption(" · ".join(meta_parts))

            if sig.evidence:
                with st.expander("▸ Evidence & Audit Trail", expanded=False):
                    for ev in sig.evidence:
                        st.markdown(f"• {ev}")

            explanation = explain_priority_score(sig)
            with st.expander("▸ Why this priority?", expanded=False):
                st.caption(explanation["explanation"])
                factors = explanation["factors"]
                st.caption(
                    f"Severity base: {factors['severity_base']} · "
                    f"Magnitude: {factors['magnitude_points']} · "
                    f"Recency: {factors['recency_points']} · "
                    f"Persistence: {factors['persistence_points']} · "
                    f"Data quality ×{factors['data_quality_multiplier']}"
                )

        with col_btns:
            # Action Buttons
            if st.button("Investigate", key=f"{prefix}_btn_inv_{sig.signal_id}_{lifecycle_context}", type="primary", use_container_width=True):
                # Ensure InvestigationItem exists in queue with source_signal
                add_to_investigation_queue(
                    analysis_id=sig.analysis_id,
                    signal_id=sig.signal_id,
                    priority=priority_label,
                    reason=sig.title,
                    source_signal=sig,
                )
                # Set active investigation in session state
                st.session_state["_active_investigation_signal"] = sig.to_dict()
                st.session_state["_active_detail_analysis_id"] = sig.analysis_id
                if on_investigate:
                    on_investigate(sig)
                st.rerun()

            if st.button("Add to Queue", key=f"{prefix}_btn_q_{sig.signal_id}_{lifecycle_context}", use_container_width=True):
                ok, err, _ = add_to_investigation_queue(
                    analysis_id=sig.analysis_id,
                    signal_id=sig.signal_id,
                    priority=priority_label,
                    reason=sig.title,
                    source_signal=sig,
                )
                if not ok and err:
                    st.warning(f"⚠️ {err}")
                else:
                    st.success("✓ Added to investigation queue.")

            if lifecycle_context == "active":
                c_ack, c_dsm = st.columns(2)
                with c_ack:
                    if st.button("Ack", key=f"{prefix}_btn_ack_{sig.signal_id}", use_container_width=True):
                        acknowledge_signal(sig.signal_id)
                        st.rerun()
                with c_dsm:
                    if st.button("Dismiss", key=f"{prefix}_btn_dsm_{sig.signal_id}", type="secondary", use_container_width=True):
                        dismiss_signal(sig.signal_id)
                        st.rerun()
            elif lifecycle_context == "acknowledged":
                c_inv, c_dsm = st.columns(2)
                with c_inv:
                    if st.button("Mark Investigating", key=f"{prefix}_btn_lifecycle_inv_{sig.signal_id}", use_container_width=True):
                        from frontend.utils.alert_engine import start_investigating_signal

                        start_investigating_signal(sig.signal_id)
                        st.rerun()
                with c_dsm:
                    if st.button("Dismiss", key=f"{prefix}_btn_dsm_ack_{sig.signal_id}", type="secondary", use_container_width=True):
                        dismiss_signal(sig.signal_id)
                        st.rerun()
                if st.button("Un-ack", key=f"{prefix}_btn_unack_{sig.signal_id}", use_container_width=True):
                    restore_signal(sig.signal_id)
                    st.rerun()
            elif lifecycle_context == "dismissed":
                if st.button("Restore to Active", key=f"{prefix}_btn_res_{sig.signal_id}", use_container_width=True):
                    restore_signal(sig.signal_id)
                    st.rerun()

