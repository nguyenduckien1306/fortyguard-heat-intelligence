"""Session-Local Watchlist Management and Live Evaluation UI Component.

Renders interactive watchlist configuration, multi-criteria builders,
live evaluation results against session analyses, and export features.

Strict Invariants:
1. Pure session-local state in st.session_state (zero network requests).
2. Unique namespaced widget keys prefixed with 'watchlist:'.
3. Real-time evaluation against completed session AnalysisRecord objects.
4. Non-causal, responsible analytics presentation.
"""

from __future__ import annotations

from typing import Any, Sequence
import streamlit as st

from frontend.utils.export import generate_watchlist_evaluation_export
from frontend.utils.watchlist_engine import evaluate_all_watchlists, evaluate_watchlist
from frontend.utils.watchlists import (
    MAX_CRITERIA_PER_WATCHLIST,
    MAX_WATCHLISTS,
    SUPPORTED_COMPARISON_MODES,
    SUPPORTED_CRITERIA_METRICS,
    SUPPORTED_OPERATORS,
    Watchlist,
    WatchlistCriterion,
    delete_watchlist,
    duplicate_watchlist,
    get_watchlists,
    reset_default_watchlists,
    save_watchlist,
    toggle_watchlist,
)


def render_watchlist_dashboard(records: Sequence[Any]) -> None:
    """Render the complete Watchlist management and evaluation interface."""
    st.markdown("### Proactive Watchlist Manager")
    st.markdown(
        "Configure automated thermal criteria and track threshold conditions "
        "across completed session analyses without manual re-calculation."
    )

    watchlists = get_watchlists()
    evaluations = evaluate_all_watchlists(watchlists, records)

    # ── Top Action Bar ──
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.caption(f"Active Watchlists: **{len(watchlists)} / {MAX_WATCHLISTS}**")
    with col2:
        if st.button("Reset Defaults", key="watchlist:action:reset_defaults", use_container_width=True):
            reset_default_watchlists()
            st.rerun()
    with col3:
        export_format = st.selectbox(
            "Export Format",
            ["JSON", "Brief"],
            key="watchlist:export:format",
            label_visibility="collapsed",
        )
        if st.button("Export Evaluations", key="watchlist:action:export", use_container_width=True):
            exp_text = generate_watchlist_evaluation_export(evaluations, format=export_format.lower())
            mime_type = "application/json" if export_format == "JSON" else "text/plain"
            ext = "json" if export_format == "JSON" else "txt"
            st.download_button(
                label=f"Download {export_format}",
                data=exp_text,
                file_name=f"watchlist_evaluations.{ext}",
                mime=mime_type,
                key="watchlist:export:download_btn",
                use_container_width=True,
            )

    st.markdown("---")

    # ── Create New Watchlist Expander ──
    with st.expander("Create New Watchlist", expanded=False):
        if len(watchlists) >= MAX_WATCHLISTS:
            st.warning(f"Maximum watchlist limit ({MAX_WATCHLISTS}) reached. Delete an existing watchlist to create a new one.")
        else:
            _render_create_watchlist_form()

    # ── Watchlists & Evaluation Results List ──
    if not watchlists:
        st.info("No watchlists configured. Click 'Reset Defaults' to load standard thermal monitoring watchlists.")
        return

    st.markdown("#### Configured Watchlists & Live Match Status")

    # Map evaluations by watchlist_id
    eval_by_id = {e.watchlist_id: e for e in evaluations}

    for idx, wl in enumerate(watchlists):
        ev = eval_by_id.get(wl.watchlist_id)
        _render_watchlist_card(wl, ev, idx)


def _render_create_watchlist_form() -> None:
    """Render the interactive form to configure and create a new Watchlist."""
    with st.form(key="watchlist:create:form"):
        st.markdown("##### Watchlist Configuration")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Watchlist Name", placeholder="e.g. Extreme Heat Alert", key="watchlist:create:name")
            location_scope = st.text_input("Location Scope (optional)", value="all", key="watchlist:create:loc")
        with c2:
            comparison_mode = st.selectbox(
                "Temporal Comparison Mode",
                list(SUPPORTED_COMPARISON_MODES),
                index=0,
                key="watchlist:create:comp_mode",
            )
            analysis_type_scope = st.selectbox(
                "Analysis Type Scope",
                ["all", "heatmap", "heat_intelligence"],
                index=0,
                key="watchlist:create:type_scope",
            )

        description = st.text_area("Description", placeholder="Describe the monitoring purpose...", key="watchlist:create:desc")

        st.markdown("##### Criteria Definition (Rule 1)")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            metric = st.selectbox("Metric", sorted(SUPPORTED_CRITERIA_METRICS), index=0, key="watchlist:create:metric_0")
        with rc2:
            operator = st.selectbox("Condition Operator", list(SUPPORTED_OPERATORS), index=1, key="watchlist:create:op_0")
        with rc3:
            threshold = st.number_input("Threshold Value", value=38.0, step=0.5, key="watchlist:create:th_0")

        # Hysteresis optional settings
        use_hysteresis = st.checkbox("Enable Anti-Flapping Hysteresis", value=False, key="watchlist:create:use_hyst")
        trig_val = None
        clr_val = None
        if use_hysteresis:
            hc1, hc2 = st.columns(2)
            with hc1:
                trig_val = st.number_input("Trigger Threshold (Activation)", value=float(threshold), step=0.5, key="watchlist:create:trig")
            with hc2:
                clr_val = st.number_input("Clear Threshold (Deactivation)", value=float(threshold) - 2.0, step=0.5, key="watchlist:create:clr")

        submit = st.form_submit_button("Create Watchlist", use_container_width=True)

        if submit:
            criterion = WatchlistCriterion(
                metric=metric,
                operator=operator,
                threshold=float(threshold),
                trigger_threshold=trig_val,
                clear_threshold=clr_val,
            )
            new_wl = Watchlist(
                watchlist_id="",
                name=name,
                description=description,
                criteria=[criterion],
                location_scope=location_scope or "all",
                analysis_type_scope=analysis_type_scope or "all",
                comparison_mode=comparison_mode,
            )
            ok, err, saved = save_watchlist(new_wl)
            if ok and saved:
                st.success(f"Watchlist '{saved.name}' created successfully (ID: {saved.watchlist_id}).")
                st.rerun()
            else:
                st.error(err or "Failed to create watchlist.")


def _render_watchlist_card(wl: Watchlist, ev: Any | None, index: int) -> None:
    """Render an individual Watchlist card with status, criteria, and live evaluation results."""
    is_matched = ev.matched if ev else False
    dq = ev.data_quality if ev else "UNKNOWN"

    match_badge = "🟢 MATCHED" if is_matched else "⚪ NO MATCH"
    status_pill = "🟢 Active" if wl.enabled else "🔴 Disabled"

    container_border = "1px solid rgba(0, 230, 118, 0.4)" if is_matched else "1px solid rgba(255, 255, 255, 0.1)"

    with st.container():
        st.markdown(
            f"""
            <div style="background: rgba(255, 255, 255, 0.03); border: {container_border}; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 600; font-size: 15px; color: #FFFFFF;">
                        {wl.name} <span style="font-size: 11px; color: #9E9E9E; background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px;">v{wl.version}</span>
                        <span style="font-size: 12px; margin-left: 8px; color: {'#00E676' if wl.enabled else '#FF5252'};">{status_pill}</span>
                    </div>
                    <div>
                        <span style="font-weight: 700; font-size: 12px; padding: 3px 8px; border-radius: 4px; background: {'rgba(0, 230, 118, 0.15)' if is_matched else 'rgba(255, 255, 255, 0.05)'}; color: {'#00E676' if is_matched else '#9E9E9E'};">
                            {match_badge}
                        </span>
                    </div>
                </div>
                <div style="font-size: 13px; color: #B0BEC5; margin-top: 4px;">{wl.description or 'No description provided.'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Details and action controls
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        with c1:
            crits_desc = []
            for c in wl.criteria:
                hyst_str = f" [Hysteresis: {c.trigger_threshold}/{c.clear_threshold}]" if c.trigger_threshold is not None else ""
                crits_desc.append(f"**{c.metric}** {c.operator} {c.threshold}{hyst_str}")
            st.caption(f"Criteria: {', '.join(crits_desc)} | Mode: `{wl.comparison_mode}` | Scope: `{wl.location_scope}`")

            # Show live evidence or limitations
            if ev:
                if is_matched and ev.evidence_list:
                    for item in ev.evidence_list:
                        st.markdown(f"- 🔎 <span style='font-size: 12px; color: #E0E0E0;'>{item}</span>", unsafe_allow_html=True)
                elif ev.limitations:
                    for lim in ev.limitations:
                        st.caption(f"ℹ️ {lim}")

        with c2:
            toggle_label = "Disable" if wl.enabled else "Enable"
            if st.button(toggle_label, key=f"watchlist:{wl.watchlist_id}:toggle", use_container_width=True):
                toggle_watchlist(wl.watchlist_id)
                st.rerun()
        with c3:
            if st.button("Duplicate", key=f"watchlist:{wl.watchlist_id}:dup", use_container_width=True):
                duplicate_watchlist(wl.watchlist_id)
                st.rerun()
        with c4:
            if st.button("Delete", key=f"watchlist:{wl.watchlist_id}:del", use_container_width=True):
                delete_watchlist(wl.watchlist_id)
                st.rerun()
