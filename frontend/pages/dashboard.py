"""Operational Intelligence Command Center for FortyGuard Heat Intelligence.

Transforms session analyses into a proactive operational command center with
threshold monitoring, alerting, queue management, and what-if scenario exploration.

Strict Invariants:
- Zero new FortyGuard API calls: opening, inspecting, searching, filtering,
  prioritizing, alerting, scenario sandbox, or queue actions trigger ZERO network requests.
- Session-only storage in st.session_state.
- Zero secret / credentials persistence or exposure.
- Zero causal, predictive, or medical claims.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when run directly as a Streamlit page
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from frontend.components.alert_center import render_alert_center, render_signal_card
from frontend.components.heatmap_result import render_heatmap_result
from frontend.components.sidebar import SidebarSelections, render_sidebar
from frontend.components.signal_center import render_signal_center
from frontend.components.watchlist_dashboard import render_watchlist_dashboard
from frontend.utils.phase15_orchestrator import reset_phase15_state, run_phase15_intelligence
from frontend.utils.alert_engine import (
    evaluate_alert_policies,
    get_active_signals,
    get_signal_lifecycle_status,
)
from frontend.utils.alert_policies import get_alert_policies
from frontend.utils.analysis_history import (
    AnalysisRecord,
    add_tag_to_analysis_record,
    clear_all_analysis_records,
    delete_analysis_record,
    get_analysis_record,
    list_analysis_records,
    pin_analysis_record,
    remove_tag_from_analysis_record,
    search_and_filter_records,
    unpin_analysis_record,
)
from frontend.utils.comparison import can_compare_heatmap_analyses, compare_heatmap_analyses
from frontend.utils.export import (
    generate_analysis_export_json,
    generate_analysis_export_text,
    generate_analytical_brief,
    generate_investigation_brief,
)
from frontend.utils.history import find_related_analyses
from frontend.utils.insights import (
    ANALYTICS_DISCLAIMER,
    generate_comparison_insights,
    generate_heatmap_insights,
    insight_severity_to_icon,
)
from frontend.utils.investigation import build_investigation_timeline
from frontend.utils.investigation_queue import (
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    STATUS_RESOLVED,
    add_to_investigation_queue,
    clear_investigation_queue,
    get_investigation_queue,
    list_open_queue,
    mark_in_review,
    mark_resolved,
    remove_from_investigation_queue,
)
from frontend.utils.operational_intelligence import (
    OperationalSignal,
    generate_operational_signals,
)
from frontend.utils.priority import (
    get_signal_priority,
    sort_signals_by_priority,
)
from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE
from frontend.utils.scenario_engine import (
    SCENARIO_ANALYTICS_DISCLAIMER,
    compare_scenario_to_observed,
    create_scenario_adjustments,
)
from frontend.utils.operational_summary import build_operational_summary
from frontend.utils.pattern_detection import detect_all_patterns
from frontend.utils.latest_change import compute_latest_change
from frontend.utils.location_intelligence import build_location_summaries
from frontend.utils.alert_grouping import group_alerts
from frontend.utils.attention_score import rank_by_attention
from frontend.utils.operator_actions import generate_all_actions
from frontend.utils.review_delta import compute_review_delta
from frontend.utils.export import generate_operational_decision_case_brief

_ACTIVE_DETAIL_KEY = "_active_detail_analysis_id"
_ACTIVE_INVESTIGATION_KEY = "_active_investigation_signal"
_USER_LAST_SEEN_KEY = "_user_last_seen_timestamp"


def render_dashboard_page(selections: SidebarSelections | None = None) -> SidebarSelections:
    """Render the FortyGuard Operational Intelligence Command Center."""
    if selections is None:
        selections = render_sidebar()

    st.session_state.setdefault(_ACTIVE_DETAIL_KEY, None)
    st.session_state.setdefault(_ACTIVE_INVESTIGATION_KEY, None)
    active_detail_id = st.session_state.get(_ACTIVE_DETAIL_KEY)

    # If an analysis is actively opened in detail inspection mode, render the Full Console
    if active_detail_id:
        record = get_analysis_record(active_detail_id)
        if record:
            _render_analysis_detail_view(record)
            return selections
        else:
            st.session_state[_ACTIVE_DETAIL_KEY] = None

    # Otherwise render the Command Center
    _render_command_center()
    return selections


# ──────────────────────────────────────────────────────────────────────────────
# Main Operational Command Center View
# ──────────────────────────────────────────────────────────────────────────────


def _render_command_center() -> None:
    """Render the top-level Operational Intelligence Command Center."""
    # ── Hero Banner ──
    from frontend.components.design_system import render_hero_header
    render_hero_header(
        "FortyGuard Heat Intelligence — Operational Command Center",
        "Proactive operational intelligence, threshold alerting, investigation prioritization, and what-if scenario sandbox — zero redundant API requests.",
        badge_label="Enterprise",
    )

    all_records = list_analysis_records()

    if not all_records:
        _render_empty_workspace_state()
        return

    # Generate signals dynamically from completed analyses + policy evaluations
    base_signals = generate_operational_signals(all_records)
    policies = get_alert_policies()
    policy_signals = evaluate_alert_policies(all_records, policies)
    all_signals = sort_signals_by_priority(base_signals + policy_signals)
    active_signals = get_active_signals(all_signals, include_acknowledged=True)
    critical_signals = [s for s in active_signals if s.severity == "CRITICAL"]

    open_queue = list_open_queue()
    unique_locations = {r.location_label for r in all_records if r.location_label}

    pinned_count = sum(1 for r in all_records if r.pinned)

    # ── Executive Metrics Strip ──
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    with m1:
        st.metric("Total Analyses", len(all_records))
    with m2:
        st.metric("Pinned", pinned_count)
    with m3:
        st.metric("Active Signals", len(active_signals))
    with m4:
        crit_color = "🔴" if critical_signals else "🟢"
        st.metric(f"{crit_color} Critical", len(critical_signals))
    with m5:
        st.metric("Queue Items", len(open_queue))
    with m6:
        st.metric("Locations", len(unique_locations))
    with m7:
        latest_date = max([r.date for r in all_records if r.date] or ["N/A"])
        st.metric("Latest Date", latest_date)

    st.divider()

    # Execute canonical Phase 15 Intelligence snapshot
    snapshot = run_phase15_intelligence(all_records)

    # ── Navigation Tabs ──
    tab_cc, tab_wl, tab_sig, tab_alerts, tab_queue, tab_ws, tab_scenario, tab_diag = st.tabs([
        "Command Center",
        "Watchlists",
        "Signal Center",
        "Alert Center",
        "Investigation Queue",
        "Analysis Workspace",
        "Scenario Sandbox",
        "Intelligence Diagnostics",
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 1: Command Center Home
    # ──────────────────────────────────────────────────────────────────────────
    with tab_cc:
        # ── 1. Operational Executive Summary ──
        from frontend.utils.watchlists import get_watchlists
        op_summary = build_operational_summary(
            records=all_records,
            watchlists=get_watchlists(),
            watchlist_evaluations=snapshot.watchlist_evaluations,
            signals=all_signals,
            alerts=snapshot.alerts,
            queue_items=open_queue,
        )

        with st.container(border=True):
            st.markdown("#### Operational Posture & Executive Summary")
            st.markdown(f"> *{op_summary.summary_narrative}*")

            # Review Delta Tracker
            last_review = st.session_state.get(_USER_LAST_SEEN_KEY)
            delta = compute_review_delta(
                last_review_timestamp=last_review,
                records=all_records,
                signals=all_signals,
                alerts=snapshot.alerts,
                queue_items=open_queue,
                watchlist_evaluations=snapshot.watchlist_evaluations,
            )

            c_delta_info, c_delta_ack = st.columns([7, 3])
            with c_delta_info:
                if not last_review:
                    st.caption("Session initialized. All recorded items are new in this session.")
                elif delta.has_changes:
                    change_parts = []
                    if delta.new_analyses:
                        change_parts.append(f"{len(delta.new_analyses)} new analyses")
                    if delta.new_alerts:
                        change_parts.append(f"{len(delta.new_alerts)} new alerts")
                    if delta.new_signals:
                        change_parts.append(f"{len(delta.new_signals)} new signals")
                    if delta.investigations_resolved:
                        change_parts.append(f"{len(delta.investigations_resolved)} resolved")
                    st.caption(f"**Since Last Review:** {', '.join(change_parts)}")
                else:
                    st.caption(f"Zero changes since last review (`{last_review[:19]}`).")
            with c_delta_ack:
                if st.button("Mark as Reviewed", key="_btn_mark_reviewed", use_container_width=True):
                    st.session_state[_USER_LAST_SEEN_KEY] = delta.current_timestamp
                    st.rerun()

        # ── 2. What Changed? (Latest vs Previous Observation) ──
        latest_change = compute_latest_change(all_records, signals=all_signals)
        st.markdown("---")
        st.markdown("### What Changed Since Previous Observation?")
        if latest_change.is_first_analysis:
            st.info(f"Analysis `{latest_change.latest_analysis_id}` is the initial session observation for this dataset. Predecessor baseline not yet recorded.")
        else:
            with st.container(border=True):
                st.markdown(
                    f"**Comparing:** Latest `{latest_change.latest_analysis_id}` vs. Previous `{latest_change.baseline_analysis_id}`"
                )
                if latest_change.changed_metrics:
                    cols_ch = st.columns(len(latest_change.changed_metrics) if len(latest_change.changed_metrics) <= 4 else 4)
                    for idx, cm in enumerate(latest_change.changed_metrics[:4]):
                        with cols_ch[idx % 4]:
                            diff_str = f"{cm.difference:+.2f}" if cm.difference is not None else "—"
                            pct_str = f" ({cm.percentage_change:+.1f}%)" if cm.percentage_change is not None else ""
                            st.metric(
                                cm.metric_name,
                                f"{cm.latest_value:.2f}" if isinstance(cm.latest_value, (int, float)) else str(cm.latest_value),
                                delta=f"{diff_str}{pct_str}",
                            )
                else:
                    st.caption("No significant metric variations between consecutive observations.")

                if latest_change.newly_triggered_conditions:
                    st.markdown(f"**Newly Triggered Conditions:** `{'`, `'.join(latest_change.newly_triggered_conditions)}`")
                if latest_change.data_quality_change and latest_change.data_quality_change != "unchanged":
                    st.caption(f"**Data Quality Transition:** `{latest_change.data_quality_change.upper()}`")

        # ── 3. Repeated Patterns Across Analyses ──
        patterns = detect_all_patterns(
            records=all_records,
            signals=all_signals,
            alerts=snapshot.alerts,
            watchlist_evaluations=snapshot.watchlist_evaluations,
        )
        st.markdown("---")
        st.markdown("### Cross-Analysis Patterns Detected")
        if not patterns:
            st.info("No recurring patterns detected across completed session analyses.")
        else:
            p_cols = st.columns(min(len(patterns), 2))
            for p_idx, pat in enumerate(patterns[:4]):
                with p_cols[p_idx % 2]:
                    with st.container(border=True):
                        sev_color = "red" if pat.severity == "CRITICAL" else ("orange" if pat.severity == "ELEVATED" else "blue")
                        st.markdown(f"**:{sev_color}[{pat.pattern_type.replace('_', ' ').title()}]** · `{pat.severity}`")
                        st.markdown(f"{pat.explanation}")
                        if pat.evidence:
                            st.caption(f"*Evidence:* {pat.evidence[0]}")
                        st.caption(f"Analyses: `{'`, `'.join(pat.analysis_ids[:3])}` ({pat.count} occurrences)")

        # ── 4. Recommended Operator Workflow Actions ──
        operator_actions = generate_all_actions(
            alerts=snapshot.alerts,
            queue_items=open_queue,
            records=all_records,
            watchlist_evaluations=snapshot.watchlist_evaluations,
        )
        st.markdown("---")
        st.markdown("### Recommended Operator Workflow Actions")
        if not operator_actions:
            st.info("All active items investigated and reviewed.")
        else:
            for act in operator_actions[:3]:
                with st.container(border=True):
                    c_act_t, c_act_btn = st.columns([7, 3])
                    with c_act_t:
                        st.markdown(f"**{act.title}**")
                        st.caption(f"*Rationale:* {act.reason}")
                    with c_act_btn:
                        st.caption(f"Priority: `{act.priority:.0f}`")

        # ── 5. Top Items Requiring Operator Attention (Attention Ranking) ──
        if snapshot.alerts:
            ranked_attention = rank_by_attention(snapshot.alerts, item_type="alert")
            st.markdown("---")
            st.markdown("### Top Alerts Ranked by Operator Attention Score")
            st.caption("Attention score combines priority, recency, recurrence, investigation state, and evidence completeness.")
            for att in ranked_attention[:3]:
                with st.container(border=True):
                    c_att1, c_att2 = st.columns([7, 3])
                    with c_att1:
                        st.markdown(f"**Alert `{att.item_id}`** · Attention Score: **`{att.attention_score:.1f} / 100`**")
                        st.caption(f"Factors: {att.explanation}")
                    with c_att2:
                        st.caption(f"Priority: `{att.priority_component:.0f}` | Recency: `{att.age_component:.1f}`")

        # ── 6. Priority Operational Signals ──
        st.markdown("---")
        st.markdown("### Priority Operational Signals")
        if not active_signals:
            st.info("No active operational signals detected from your completed analyses.")
        else:
            top_signals = active_signals[:3]
            for sig in top_signals:
                render_signal_card(sig, lifecycle_context="active", prefix="_cc_home")

            if len(active_signals) > 3:
                st.caption(f"Showing top **3** of **{len(active_signals)}** active signals. Visit **Alert Center** to view all.")

        # ── 7. Active Investigation Queue ──
        st.markdown("---")
        st.markdown("### Active Investigation Queue")
        if not open_queue:
            st.info("Your investigation queue is empty. Use **[ Add to Queue ]** on any signal to prioritize an investigation.")
        else:
            for item in open_queue[:4]:
                with st.container(border=True):
                    c_q1, c_q2 = st.columns([7, 3])
                    with c_q1:
                        st.markdown(f"**{item.reason or 'Investigation Item'}** · `{item.priority.upper()}` · `{item.status}`")
                        st.caption(f"**Analysis ID:** `{item.analysis_id}` · **Location:** {item.location} · Added: {item.created_at[:10]}")
                        if item.notes:
                            st.caption(f"*Notes:* {item.notes}")
                    with c_q2:
                        c_act1, c_act2 = st.columns(2)
                        with c_act1:
                            if item.status == STATUS_OPEN:
                                if st.button("Review", key=f"_cc_q_rev_{item.queue_id}", use_container_width=True):
                                    mark_in_review(item.queue_id)
                                    st.rerun()
                            else:
                                if st.button("Resolve", key=f"_cc_q_res_{item.queue_id}", use_container_width=True):
                                    mark_resolved(item.queue_id)
                                    st.rerun()
                        with c_act2:
                            if st.button("Inspect", key=f"_cc_q_open_{item.queue_id}", type="primary", use_container_width=True):
                                st.session_state[_ACTIVE_DETAIL_KEY] = item.analysis_id
                                st.rerun()


    # ──────────────────────────────────────────────────────────────────────────
    # TAB 2: Watchlists
    # ──────────────────────────────────────────────────────────────────────────
    with tab_wl:
        render_watchlist_dashboard(all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 3: Signal Center
    # ──────────────────────────────────────────────────────────────────────────
    with tab_sig:
        render_signal_center(snapshot.signals, all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 4: Alert Center
    # ──────────────────────────────────────────────────────────────────────────
    with tab_alerts:
        render_alert_center(all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 5: Investigation Queue & Console
    # ──────────────────────────────────────────────────────────────────────────
    with tab_queue:
        _render_investigation_queue_tab(all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 6: Analysis Workspace (Phases 11-13)
    # ──────────────────────────────────────────────────────────────────────────
    with tab_ws:
        _render_workspace_tab_content(all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 7: Scenario Sandbox
    # ──────────────────────────────────────────────────────────────────────────
    with tab_scenario:
        _render_scenario_sandbox_tab(all_records)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 8: Intelligence Diagnostics & Observability
    # ──────────────────────────────────────────────────────────────────────────
    with tab_diag:
        _render_diagnostics_tab(snapshot)


def _render_diagnostics_tab(snapshot: Any) -> None:
    """Render the Intelligence Diagnostics, Observability, and Provenance panel."""
    st.markdown("### Intelligence Diagnostics & Observability")
    st.caption("Real-time verification of session intelligence state, cryptographic hashes, and zero-network invariants.")

    diag = snapshot.diagnostics_summary
    snap_dict = snapshot.to_dict()

    # Provenance Badges Strip
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Snapshot ID", snap_dict.get("snapshot_id", "N/A")[:14])
    with c2:
        st.metric("Schema Version", f"v{snap_dict.get('schema_version', 1)}")
    with c3:
        st.metric("HTTP Calls Made", f"{diag.get('http_calls', 0)} (Verified 0)")
    with c4:
        st.metric("Analyses Evaluated", diag.get("analyses_evaluated", 0))

    st.markdown("---")

    # Cryptographic Hash & Pipeline Observability
    col_hash, col_acts = st.columns([6, 4])
    with col_hash:
        st.markdown("#### Cryptographic Provenance")
        canonical_h = snapshot.canonical_hash()
        st.code(f"Canonical SHA-256 Hash:\n{canonical_h}", language="text")
        st.caption(f"Generated At: `{snapshot.generated_at}` | Engine: FortyGuard Heat Intelligence v15.0")

    with col_acts:
        st.markdown("#### Session Actions")
        from frontend.utils.export import generate_command_center_decision_brief
        brief_txt = generate_command_center_decision_brief(snapshot, format="brief")
        brief_json = generate_command_center_decision_brief(snapshot, format="json")

        b1, b2 = st.columns(2)
        with b1:
            st.download_button(
                "Download Decision Brief (TXT)",
                data=brief_txt,
                file_name="command_center_brief.txt",
                mime="text/plain",
                key="_diag_dl_brief_txt",
                use_container_width=True,
            )
        with b2:
            st.download_button(
                "Download Decision Brief (JSON)",
                data=brief_json,
                file_name="command_center_brief.json",
                mime="application/json",
                key="_diag_dl_brief_json",
                use_container_width=True,
            )

        if st.button("Reset Phase 15 State", key="_diag_reset_state_btn", use_container_width=True):
            reset_phase15_state()
            st.success("Phase 15 intelligence state cleared. Analysis records history preserved.")
            st.rerun()

    st.markdown("---")
    st.markdown("#### Real-Time Diagnostic Counters")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.metric("Watchlists Evaluated", diag.get("watchlists_evaluated", 0))
    with d2:
        st.metric("Watchlist Matches", diag.get("watchlist_matches", 0))
    with d3:
        st.metric("Signals Detected", diag.get("signals_generated", 0))
    with d4:
        st.metric("Alerts Promoted", diag.get("alerts_promoted", 0))

    d5, d6, d7, d8 = st.columns(4)
    with d5:
        st.metric("Alerts Suppressed", diag.get("alerts_suppressed", 0))
    with d6:
        st.metric("Cooldown Suppressions", diag.get("cooldown_suppressions", 0))
    with d7:
        st.metric("Low DQ Suppressions", diag.get("low_quality_suppressions", 0))
    with d8:
        st.metric("Open Queue Items", diag.get("open_investigations", 0))

    st.markdown("---")
    st.markdown("#### Session Observability Event Log")
    st.caption("Local audit trail only. Credentials and signed URLs are redacted. Streamlit reruns do not duplicate identical pipeline hashes.")
    try:
        from frontend.utils.observability import get_observability_events

        obs_events = get_observability_events(limit=25)
    except Exception:
        obs_events = []

    if not obs_events:
        st.info("No observability events recorded in this session yet.")
    else:
        for ev in reversed(obs_events[-15:]):
            with st.expander(f"{ev.event_name} · {ev.status} · {ev.timestamp}", expanded=False):
                st.write(
                    {
                        "analysis_id": ev.analysis_id,
                        "activity_id": ev.activity_id,
                        "attempt_number": ev.attempt_number,
                        "duration_ms": ev.duration_ms,
                        "metadata": ev.metadata,
                    }
                )



# ──────────────────────────────────────────────────────────────────────────────
# Investigation Queue & Deep-Dive Tab
# ──────────────────────────────────────────────────────────────────────────────


def _render_investigation_queue_tab(all_records: list[AnalysisRecord]) -> None:
    """Render complete investigation queue management and detail brief view."""
    st.markdown("### Investigation Queue & Console")
    st.caption("Manage prioritized investigation assignments, review historical context, and export sanitized investigation briefs.")

    queue_items = get_investigation_queue()

    col_q_info, col_q_clear = st.columns([7, 3])
    with col_q_info:
        st.markdown(f"**Total Queue Items:** `{len(queue_items)} / 100`")
    with col_q_clear:
        if st.button("Clear Resolved Items", key="_btn_clear_resolved_q", type="secondary"):
            for item in queue_items:
                if item.status == STATUS_RESOLVED:
                    remove_from_investigation_queue(item.queue_id)
            st.rerun()

    st.divider()

    if not queue_items:
        st.info("Your investigation queue is currently empty. Click **[ Add to Queue ]** from any operational signal card to begin.")
        return

    # List queue items with full action controls
    for item in queue_items:
        with st.container(border=True):
            col_info, col_actions = st.columns([6, 4])
            with col_info:
                status_icon = "🔵 Open" if item.status == STATUS_OPEN else ("🟠 In Review" if item.status == STATUS_IN_REVIEW else "🟢 Resolved")
                pri_color = "red" if item.priority == "Critical" else ("orange" if item.priority == "High" else ("blue" if item.priority == "Medium" else "gray"))
                st.markdown(f"**{item.reason or 'Investigation Item'}** · :{pri_color}[● {item.priority}] · `{status_icon}`")
                st.caption(f"**Analysis:** `{item.analysis_id}` · **Location:** {item.location} · **Created:** {item.created_at[:16]}")
                if item.notes:
                    st.caption(f"*Notes:* {item.notes}")

            with col_actions:
                c1, c2, c3 = st.columns(3)
                with c1:
                    if item.status == STATUS_OPEN:
                        if st.button("In Review", key=f"_q_rev_{item.queue_id}", use_container_width=True):
                            mark_in_review(item.queue_id)
                            st.rerun()
                    elif item.status == STATUS_IN_REVIEW:
                        if st.button("Resolve", key=f"_q_res_{item.queue_id}", use_container_width=True):
                            mark_resolved(item.queue_id)
                            st.rerun()
                with c2:
                    if st.button("Open", key=f"_q_insp_{item.queue_id}", type="primary", use_container_width=True):
                        st.session_state[_ACTIVE_DETAIL_KEY] = item.analysis_id
                        st.rerun()
                with c3:
                    if st.button("Remove", key=f"_q_rm_{item.queue_id}", type="secondary", use_container_width=True):
                        remove_from_investigation_queue(item.queue_id)
                        st.rerun()

    # ── Export Investigation Brief ──
    st.markdown("---")
    st.markdown("#### Export Selected Investigation Brief")

    open_items = list_open_queue()
    if open_items:
        item_options = {f"{i.reason or i.analysis_id} ({i.location}) - [{i.queue_id}]": i for i in open_items}
        sel_label = st.selectbox("Select Queue Item to Export", options=list(item_options.keys()), key="_sel_exp_q_item")
        sel_item = item_options[sel_label]
        target_rec = get_analysis_record(sel_item.analysis_id)

        if target_rec:
            brief_txt = generate_investigation_brief(sel_item, target_rec, format="brief")
            brief_json = generate_investigation_brief(sel_item, target_rec, format="json")

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.download_button(
                    "Download Investigation Brief (TXT)",
                    data=brief_txt,
                    file_name=f"investigation_brief_{sel_item.queue_id}.txt",
                    mime="text/plain",
                    key=f"_dl_inv_txt_{sel_item.queue_id}",
                    use_container_width=True,
                )
            with col_b2:
                st.download_button(
                    "Download Investigation Brief (JSON)",
                    data=brief_json,
                    file_name=f"investigation_brief_{sel_item.queue_id}.json",
                    mime="application/json",
                    key=f"_dl_inv_json_{sel_item.queue_id}",
                    use_container_width=True,
                )


# ──────────────────────────────────────────────────────────────────────────────
# Scenario Sandbox Tab
# ──────────────────────────────────────────────────────────────────────────────


def _render_scenario_sandbox_tab(all_records: list[AnalysisRecord]) -> None:
    """Render the interactive what-if Scenario Analysis Sandbox."""
    st.markdown("### Scenario / What-If — Hypothetical")
    st.caption(
        "Scenario / What-If — Hypothetical mathematical adjustments on completed analyses. "
        "Outputs are not provider observations, forecasts, or predictions. "
        "Historical AnalysisRecords are never mutated and no FortyGuard API calls are made."
    )

    completed = [r for r in all_records if r.status == "Completed"]
    if not completed:
        st.info("No completed analyses available for scenario exploration.")
        return

    # Select analysis
    options = {f"{r.location_label} ({r.date or 'N/A'} - `{r.analysis_id}`)": r for r in completed}
    sel_label = st.selectbox("Select Baseline Analysis", options=list(options.keys()), key="_scen_sel_rec")
    selected_rec = options[sel_label]

    # Disclaimer Banner
    st.info(f"**SCENARIO ONLY**: {SCENARIO_ANALYTICS_DISCLAIMER}")

    # Slider adjustments
    with st.container(border=True):
        st.markdown("#### Scenario Parameter Adjustments")
        c_s1, c_s2 = st.columns(2)
        with c_s1:
            temp_adj = st.slider("Temperature Adjustment (Δ °C)", min_value=-5.0, max_value=5.0, value=2.0, step=0.5, key="_scen_temp_adj")
            thresh_adj = st.slider("Policy Threshold Adjustment (Δ °C)", min_value=-5.0, max_value=5.0, value=0.0, step=0.5, key="_scen_th_adj")
        with c_s2:
            spread_adj = st.slider("Spatial Spread Adjustment (Δ °C)", min_value=-5.0, max_value=5.0, value=1.0, step=0.5, key="_scen_sp_adj")
            prop_adj = st.slider("Above-Threshold Proportion Adjustment (Δ %)", min_value=-50.0, max_value=50.0, value=10.0, step=5.0, key="_scen_pr_adj")

    adjustments = create_scenario_adjustments(
        temperature_delta=temp_adj,
        threshold_delta=thresh_adj,
        spread_delta=spread_adj,
        proportion_delta=prop_adj,
    )

    comparison = compare_scenario_to_observed(selected_rec, adjustments, base_threshold=35.0)

    # ── Before / After Delta Display ──
    st.markdown("#### Observed State vs. Scenario State")
    with st.container(border=True):
        st.markdown(f"**What-If Observation:** {comparison.narrative_summary}")
        st.divider()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            obs_m = f"{comparison.observed_mean_temp:.1f}°C" if comparison.observed_mean_temp is not None else "N/A"
            scen_m = f"{comparison.scenario_mean_temp:.1f}°C" if comparison.scenario_mean_temp is not None else "N/A"
            st.metric("Mean Temperature", scen_m, delta=f"{adjustments.temperature_delta:+.1f}°C" if adjustments.temperature_delta else None)
        with c2:
            obs_th = f"{comparison.threshold_observed:.1f}°C"
            scen_th = f"{comparison.threshold_scenario:.1f}°C"
            st.metric("Effective Threshold", scen_th, delta=f"{adjustments.threshold_delta:+.1f}°C" if adjustments.threshold_delta else None)
        with c3:
            obs_sp = f"{comparison.observed_spread:.1f}°C" if comparison.observed_spread is not None else "N/A"
            scen_sp = f"{comparison.scenario_spread:.1f}°C" if comparison.scenario_spread is not None else "N/A"
            st.metric("Spatial Spread", scen_sp, delta=f"{adjustments.spread_delta:+.1f}°C" if adjustments.spread_delta else None)
        with c4:
            obs_pr = f"{comparison.observed_hot_proportion:.1f}%" if comparison.observed_hot_proportion is not None else "N/A"
            scen_pr = f"{comparison.scenario_hot_proportion:.1f}%" if comparison.scenario_hot_proportion is not None else "N/A"
            st.metric("Hot Proportion", scen_pr, delta=f"{adjustments.proportion_delta:+.1f}%" if adjustments.proportion_delta else None)

    # Threshold Exceedance Card
    with st.container(border=True):
        col_status, col_delta = st.columns([6, 4])
        with col_status:
            status_text = "🚨 **EXCEEDS THRESHOLD**" if comparison.scenario_exceeds_threshold else "🟢 **WITHIN THRESHOLD**"
            status_color = "red" if comparison.scenario_exceeds_threshold else "green"
            st.markdown(f":{status_color}[{status_text}]")
            st.caption(f"Observed state was: `{'Exceeded' if comparison.observed_exceeds_threshold else 'Within'}` threshold.")
        with col_delta:
            if comparison.threshold_delta_exceedance is not None:
                st.metric("Margin to Threshold", f"{comparison.threshold_delta_exceedance:+.2f}°C")


# ──────────────────────────────────────────────────────────────────────────────
# Analysis Workspace Tab Content (Phases 11-13)
# ──────────────────────────────────────────────────────────────────────────────


def _render_workspace_tab_content(all_records: list[AnalysisRecord]) -> None:
    """Render the Analysis Workspace search, filter, card grid, and comparison."""
    st.markdown("### Analysis Workspace")
    st.caption(
        "Session-local completed analyses — search, filter, pin, tag, compare, and inspect "
        "without triggering FortyGuard API requests."
    )

    # Search & Filter
    st.markdown("#### Search & Filter Workspace")
    search_query = st.text_input(
        "Search analyses",
        placeholder="Search by ID, location, tags, category, or date...",
        key="_ws_search_input",
        label_visibility="collapsed",
    )

    all_tags = sorted({t for r in all_records for t in r.tags})
    tag_options = ["All"] + all_tags

    c_type, c_status, c_date, c_tag, c_sort = st.columns(5)
    with c_type:
        type_filter = st.selectbox("Type", options=["All", "Heatmap", "Heat Intelligence"], index=0, key="_ws_type_filter")
    with c_status:
        status_filter = st.selectbox("Status", options=["All", "Completed", "Processing", "Failed"], index=0, key="_ws_status_filter")
    with c_date:
        date_filter = st.selectbox("Date", options=["All", "Today", "Last 7 Days"], index=0, key="_ws_date_filter")
    with c_tag:
        tag_filter = st.selectbox("Tag", options=tag_options, index=0, key="_ws_tag_filter")
    with c_sort:
        sort_by = st.selectbox("Sort by", options=["Newest", "Oldest", "Pinned First", "Location A–Z"], index=0, key="_ws_sort_by")

    pinned_only = st.checkbox("Pinned only", value=False, key="_ws_pinned_only")

    filtered_records = search_and_filter_records(
        query=search_query,
        type_filter=type_filter,
        status_filter=status_filter,
        pinned_only=pinned_only,
        tag_filter=tag_filter if tag_filter != "All" else None,
        date_filter=date_filter,
        sort_by=sort_by,
    )

    st.markdown(f"**Showing {len(filtered_records)} of {len(all_records)} session analyses**")

    if not filtered_records:
        st.info("No session analyses match your search and filter criteria.")
    else:
        for rec in filtered_records:
            _render_analysis_card(rec)

    st.divider()

    # ── Heatmap Comparison Tool ──
    _render_heatmap_comparison_section(all_records)

    # ── Decision Intelligence & Investigation Console (Phase 13) ──
    _render_decision_intelligence_section(all_records)

    st.divider()

    # ── Workspace Danger Zone ──
    with st.expander("Workspace Management (Clear History)", expanded=False):
        st.warning("**Clear All Session History**: This will remove all completed analyses, pins, and tags from your active browser session.")
        if st.button("Clear Entire Workspace History", type="secondary", key="_ws_clear_all_btn"):
            clear_all_analysis_records()
            st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Empty State View
# ──────────────────────────────────────────────────────────────────────────────


def _render_empty_workspace_state() -> None:
    """Render a clean empty state when no session analyses exist."""
    with st.container(border=True):
        st.markdown("### Operational Command Center: No Analyses Yet")
        st.markdown(
            """
            Your **Analysis Workspace** is empty — this active browser session does not
            contain any recorded analyses yet.

            **To get started:**
            1. Run a **Heatmap Analysis** or **Heat Intelligence Report** from the sidebar.
            2. Completed analyses will automatically populate this Command Center.
            3. Configure custom alert policies in the **Alert Center** to monitor operational thresholds.
            """
        )


# ──────────────────────────────────────────────────────────────────────────────
# Analysis Card Item
# ──────────────────────────────────────────────────────────────────────────────


def _render_analysis_card(rec: AnalysisRecord) -> None:
    """Render a single interactive summary card for an AnalysisRecord."""
    is_hi = "heat_intelligence" in rec.analysis_type.lower()
    icon = ""
    type_label = "Heat Intelligence" if is_hi else "Heatmap"

    with st.container(border=True):
        col_main, col_metrics, col_actions = st.columns([4, 4, 2])

        with col_main:
            pin_badge = "● " if rec.pinned else ""
            st.markdown(f"**{pin_badge}{rec.location_label}**")
            st.caption(f"ID: `{rec.analysis_id}` · {type_label} · {rec.date or 'N/A'} {rec.time or ''}")

            if rec.tags:
                tag_str = " ".join([f"`{t}`" for t in rec.tags])
                st.markdown(tag_str)

        with col_metrics:
            if is_hi:
                temp_val = f"{rec.observed_temperature:.1f} °C" if rec.observed_temperature is not None else "N/A"
                st.markdown(f"**Observed:** `{temp_val}`")
                if rec.categories:
                    st.caption(f"Categories: {', '.join(rec.categories)}")
            else:
                m_temp = rec.metrics.get("mean_temp") or rec.metrics.get("mean_temperature")
                m_spread = rec.metrics.get("temp_spread") or rec.metrics.get("temperature_spread")
                m_tiles = rec.metrics.get("total_tiles") or rec.metrics.get("tile_count")

                temp_str = f"{m_temp:.1f} °C" if m_temp is not None else "N/A"
                spread_str = f"{m_spread:.1f} °C" if m_spread is not None else "—"
                tiles_str = str(m_tiles) if m_tiles is not None else "—"

                st.markdown(f"**Mean:** `{temp_str}` · Spread: `{spread_str}` · Tiles: `{tiles_str}`")

        with col_actions:
            # Stable AppTest-compatible key: _open_btn_{analysis_id}
            if st.button(
                "Open Analysis",
                key=f"_open_btn_{rec.analysis_id}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state[_ACTIVE_DETAIL_KEY] = rec.analysis_id
                st.rerun()

            c_pin, c_del = st.columns(2)
            with c_pin:
                pin_label = "Unpin" if rec.pinned else "Pin"
                if st.button(pin_label, key=f"_btn_pin_{rec.analysis_id}", use_container_width=True):
                    if rec.pinned:
                        unpin_analysis_record(rec.analysis_id)
                    else:
                        pin_analysis_record(rec.analysis_id)
                    st.rerun()
            with c_del:
                if st.button("Delete", key=f"_btn_del_{rec.analysis_id}", use_container_width=True):
                    delete_analysis_record(rec.analysis_id)
                    st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Full Investigation Console / Analysis Detail View
# ──────────────────────────────────────────────────────────────────────────────


def _render_analysis_detail_view(rec: AnalysisRecord) -> None:
    """Render the complete investigation console for a single analysis with 0 network calls."""
    is_hi = "heat_intelligence" in rec.analysis_type.lower()
    icon = ""
    type_title = "Heat Intelligence" if is_hi else "Heatmap Analysis"

    # Navigation back to workspace
    col_back, col_title = st.columns([2, 8])
    with col_back:
        if st.button("← Back to Command Center", key="_btn_back_to_ws", type="primary"):
            st.session_state[_ACTIVE_DETAIL_KEY] = None
            st.rerun()

    with col_title:
        st.markdown(f"### {rec.location_label} — Investigation Console")

    st.caption(f"**Analysis ID:** `{rec.analysis_id}` · **Activity ID:** `{rec.activity_id or 'N/A'}` · **Type:** {type_title} · **Recorded:** {rec.created_at}")

    # Status & Pin/Tag strip
    c_status, c_pin, c_tag_mgmt = st.columns([3, 2, 4])
    with c_status:
        status_color = "green" if rec.status == "Completed" else "orange"
        st.markdown(f"**Status:** :{status_color}[● {rec.status}]")
    with c_pin:
        if rec.pinned:
            if st.button("Pinned (Click to unpin)", key=f"_dt_unpin_{rec.analysis_id}"):
                unpin_analysis_record(rec.analysis_id)
                st.rerun()
        else:
            if st.button("Pin to Favorites", key=f"_dt_pin_{rec.analysis_id}"):
                ok, err = pin_analysis_record(rec.analysis_id)
                if not ok and err:
                    st.error(err)
                else:
                    st.rerun()

    with c_tag_mgmt:
        new_tag = st.text_input(
            "Add Tag",
            placeholder="+ tag (e.g. baseline, downtown)",
            key=f"_dt_newtag_{rec.analysis_id}",
            label_visibility="collapsed",
        )
        if new_tag:
            ok, err = add_tag_to_analysis_record(rec.analysis_id, new_tag)
            if not ok and err:
                st.error(err)
            else:
                st.rerun()

    if rec.tags:
        st.markdown("**Tags:**")
        tag_cols = st.columns(len(rec.tags) if len(rec.tags) <= 5 else 5)
        for i, t in enumerate(rec.tags):
            col_target = tag_cols[i % len(tag_cols)]
            with col_target:
                c_chip, c_x = st.columns([3, 1])
                c_chip.caption(f"`{t}`")
                if c_x.button("✕", key=f"_rm_tag_dt_{rec.analysis_id}_{t}"):
                    remove_tag_from_analysis_record(rec.analysis_id, t)
                    st.rerun()

    st.divider()

    # ── Parameters & Confirmed Inputs ──
    with st.container(border=True):
        st.markdown("#### Confirmed Analysis Parameters")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.markdown(f"**Location / Label:** {rec.location_label}")
            if rec.latitude is not None and rec.longitude is not None:
                st.caption(f"Coordinates: ({rec.latitude:.4f}, {rec.longitude:.4f})")
        with p2:
            st.markdown(f"**Date:** {rec.date or 'N/A'}")
            if rec.time:
                st.caption(f"Time: {rec.time}")
        with p3:
            if is_hi:
                st.markdown(f"**Observed Temp:** {rec.observed_temperature if rec.observed_temperature is not None else 'N/A'} °C")
                st.caption(f"Categories: {', '.join(rec.categories)}")
            else:
                st.markdown(f"**Spatial Granularity:** {rec.granularity or 100}m")
                if rec.polygon_summary:
                    st.caption(f"AOI: {rec.polygon_summary}")

    # ── Derived Metrics & Statistics ──
    if rec.metrics:
        with st.container(border=True):
            st.markdown("#### Derived Thermal Statistics")
            m_cols = st.columns(len(rec.metrics) if len(rec.metrics) <= 5 else 4)
            for idx, (k, v) in enumerate(rec.metrics.items()):
                with m_cols[idx % len(m_cols)]:
                    val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                    lbl = k.replace("_", " ").title()
                    st.metric(lbl, val_str)

    # ── Analytical Insights ──
    insights_to_show = rec.insights
    if not insights_to_show and rec.metrics and not is_hi:
        from dataclasses import asdict
        insights_to_show = [asdict(ins) for ins in generate_heatmap_insights(rec.metrics)]

    if insights_to_show:
        with st.container(border=True):
            st.markdown("#### Analytical Observations & Insights")
            for ins in insights_to_show:
                sev = ins.get("severity", "info")
                icon = insight_severity_to_icon(sev)
                title = ins.get("title", "Observation")
                summary = ins.get("summary", "")
                evidence = ins.get("evidence", "")

                st.markdown(f"**{icon} {title}** — {summary}")
                if evidence:
                    st.caption(f"*Evidence:* {evidence}")

            st.caption(ANALYTICS_DISCLAIMER)

    # ── Cached Visualization ──
    if rec.result_cached:
        if not is_hi and "Heatmap" in type_title:
            st.markdown("---")
            st.markdown("#### Spatial Heatmap Visualization")
            render_heatmap_result(
                rec.polygon_aoi,
                rec.result_cached,
                activity_id=rec.activity_id,
                request_params={
                    "label": rec.location_label,
                    "date": rec.date,
                    "time": rec.time,
                    "granularity": rec.granularity,
                    "polygon_aoi": rec.polygon_aoi,
                },
            )
        elif is_hi:
            st.markdown("---")
            st.markdown("#### Heat Intelligence Report Intelligence")
            st.success("Multi-dimensional point intelligence report generated.")
            if rec.activity_id:
                st.caption(f"PDF download available via backend proxy for activity `{rec.activity_id}`.")

    # ── Unified Investigation Context Panel (Phase 17) ──
    st.markdown("---")
    st.markdown("#### Unified Investigation Context Panel")
    with st.container(border=True):
        ctx_tab1, ctx_tab2, ctx_tab3, ctx_tab4, ctx_tab5 = st.tabs([
            "Source & Identity",
            "Change vs. Baseline",
            "Evidence & Audit",
            "Cross-Analysis Context",
            "Operational Decision Brief",
        ])

        with ctx_tab1:
            st.markdown("##### Source Identification")
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                st.markdown(f"**Analysis ID:** `{rec.analysis_id}`")
                st.markdown(f"**Location Label:** `{rec.location_label}`")
                st.markdown(f"**Date / Time:** `{rec.date or 'N/A'}` `{rec.time or ''}`")
            with c_s2:
                st.markdown(f"**Analysis Type:** `{type_title}`")
                st.markdown(f"**Status:** `{rec.status}`")
                st.markdown(f"**Data Quality:** `{'HIGH' if is_hi or (rec.metrics and rec.metrics.get('total_tiles', 0) > 10) else 'MEDIUM'}`")

        with ctx_tab2:
            st.markdown("##### Change vs. Previous Observation")
            all_recs = list_analysis_records()
            ch_summary = compute_latest_change(all_recs)
            if ch_summary.is_first_analysis:
                st.info("Initial session observation. No historical predecessor recorded.")
            else:
                if ch_summary.changed_metrics:
                    for cm in ch_summary.changed_metrics:
                        st.markdown(f"* **{cm.metric_name}:** `{cm.baseline_value}` → `{cm.latest_value}` ({cm.direction}, Δ `{cm.difference}`)")
                else:
                    st.caption("No significant metric variation detected.")

        with ctx_tab3:
            st.markdown("##### Observed Evidence & Data Quality")
            c_ev1, c_ev2 = st.columns(2)
            with c_ev1:
                obs_t = rec.observed_temperature or (rec.metrics.get("mean_temp") if rec.metrics else None)
                st.metric("Evaluated Temperature", f"{obs_t:.2f} °C" if obs_t is not None else "N/A")
            with c_ev2:
                st.metric("Data Quality Standard", "HIGH" if is_hi else "STANDARD")
            st.caption("Deterministic telemetry snapshot collected under FortyGuard Responsible Analytics guidelines.")

        with ctx_tab4:
            st.markdown("##### Related Analyses & Patterns")
            rel_recs = find_related_analyses(rec, all_recs)
            if rel_recs:
                for rel in rel_recs[:3]:
                    st.caption(f"🔗 Related Analysis `{rel.get('analysis_id')}` ({rel.get('location_label', 'Analysis Area')}) — Date `{rel.get('date', 'N/A')}`")
            else:
                st.caption("Zero related analyses for this coordinate in current session.")

        with ctx_tab5:
            st.markdown("##### Operational Decision Case Brief")
            case_brief_text = generate_operational_decision_case_brief(
                source_record=rec,
                latest_change_summary=ch_summary,
                format="text",
            )
            case_brief_json = generate_operational_decision_case_brief(
                source_record=rec,
                latest_change_summary=ch_summary,
                format="json",
            )
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                st.download_button(
                    "Download Decision Brief (TXT)",
                    data=case_brief_text,
                    file_name=f"decision_brief_{rec.analysis_id}.txt",
                    mime="text/plain",
                    key=f"_dt_dl_case_brief_txt_{rec.analysis_id}",
                    use_container_width=True,
                )
            with b_col2:
                st.download_button(
                    "Download Decision Brief (JSON)",
                    data=case_brief_json,
                    file_name=f"decision_brief_{rec.analysis_id}.json",
                    mime="application/json",
                    key=f"_dt_dl_case_brief_json_{rec.analysis_id}",
                    use_container_width=True,
                )

    # ── Export Integration ──
    st.markdown("---")
    st.markdown("#### Export Analysis & Investigation Brief")
    col_exp_json, col_exp_txt, col_exp_brief = st.columns(3)

    export_dict = rec.to_dict()
    export_dict["label"] = rec.location_label
    export_dict["metrics_summary"] = rec.metrics
    export_dict["request_params"] = {
        "latitude": rec.latitude,
        "longitude": rec.longitude,
        "date": rec.date,
        "time": rec.time,
        "analysis": rec.categories,
        "granularity": rec.granularity,
    }

    json_data = generate_analysis_export_json(export_dict)
    text_data = generate_analysis_export_text(export_dict)
    brief_data = generate_analytical_brief(export_dict)

    with col_exp_json:
        st.download_button(
            "Export JSON",
            data=json_data,
            file_name=f"analysis_{rec.analysis_id}.json",
            mime="application/json",
            key=f"_dt_exp_json_{rec.analysis_id}",
        )
    with col_exp_txt:
        st.download_button(
            "Export TXT",
            data=text_data,
            file_name=f"analysis_{rec.analysis_id}.txt",
            mime="text/plain",
            key=f"_dt_exp_txt_{rec.analysis_id}",
        )
    with col_exp_brief:
        st.download_button(
            "Export Analytical Brief",
            data=brief_data,
            file_name=f"brief_{rec.analysis_id}.md",
            mime="text/markdown",
            key=f"_dt_exp_brief_{rec.analysis_id}",
        )

    # Developer Raw Payload Expander
    with st.expander("Developer / Raw Payload Details (Scrubbed)"):
        st.json(rec.to_dict())


# ──────────────────────────────────────────────────────────────────────────────
# Heatmap Comparison Section
# ──────────────────────────────────────────────────────────────────────────────


def _render_heatmap_comparison_section(all_records: list[AnalysisRecord]) -> None:
    """Render side-by-side comparative analytics for completed Heatmaps."""
    st.subheader("Heatmap Comparative Analytics")
    st.caption("Compare two completed Heatmap analyses from your session workspace to evaluate temperature deltas.")

    completed_heatmaps = [
        r for r in all_records
        if "heatmap" in r.analysis_type.lower() and r.status == "Completed" and r.metrics
    ]

    if len(completed_heatmaps) < 2:
        st.info("At least two completed Heatmap analyses with metrics are required in session history to perform a comparative analysis.")
        return

    options = {f"{r.location_label} (`{r.analysis_id}` / `{r.activity_id}`)": r for r in completed_heatmaps}
    opt_keys = list(options.keys())

    c_sel1, c_sel2 = st.columns(2)
    with c_sel1:
        sel_a_label = st.selectbox("Baseline Analysis (A)", options=opt_keys, index=0, key="_ws_cmp_sel_a")
    with c_sel2:
        sel_b_label = st.selectbox("Comparison Analysis (B)", options=opt_keys, index=1 if len(opt_keys) > 1 else 0, key="_ws_cmp_sel_b")

    rec_a = options[sel_a_label]
    rec_b = options[sel_b_label]

    dict_a = rec_a.to_dict()
    dict_a["label"] = rec_a.location_label
    dict_a["metrics_summary"] = rec_a.metrics

    dict_b = rec_b.to_dict()
    dict_b["label"] = rec_b.location_label
    dict_b["metrics_summary"] = rec_b.metrics

    is_compatible, reason = can_compare_heatmap_analyses(dict_a, dict_b)
    if not is_compatible:
        st.warning(f"⚠️ {reason}")
        return

    comparison = compare_heatmap_analyses(dict_a, dict_b)
    if not comparison.get("is_valid"):
        st.info("No common numerical metrics found between the selected analyses.")
        return

    st.markdown("#### Metric-by-Metric Comparison (Δ = B − A)")

    with st.container(border=True):
        st.markdown(
            f"**Baseline (A):** {rec_a.location_label} (`{rec_a.analysis_id}`)  \n"
            f"**Comparison (B):** {rec_b.location_label} (`{rec_b.analysis_id}`)"
        )
        st.divider()

        header_cols = st.columns([3, 2, 2, 2, 3])
        header_cols[0].markdown("**Metric**")
        header_cols[1].markdown(f"**A: {rec_a.location_label}**")
        header_cols[2].markdown(f"**B: {rec_b.location_label}**")
        header_cols[3].markdown("**Difference (Δ)**")
        header_cols[4].markdown("**Interpretation**")

        for m in comparison["compared_metrics"]:
            cols = st.columns([3, 2, 2, 2, 3])
            cols[0].markdown(f"**{m['label']}**")
            cols[1].markdown(f"`{m['value_a']}`")
            cols[2].markdown(f"`{m['value_b']}`")

            diff_val = m["raw_diff"]
            diff_color = "green" if diff_val < 0 else ("red" if diff_val > 0 else "gray")
            cols[3].markdown(f":{diff_color}[**{m['diff_formatted']}**]")
            cols[4].caption(m.get("interpretation", ""))

    comp_insights = generate_comparison_insights(comparison)
    if comp_insights:
        st.markdown("##### Comparison Observations")
        with st.container(border=True):
            for ins in comp_insights:
                icon = insight_severity_to_icon(ins.severity)
                st.caption(f"{icon} {ins.summary}")
        st.caption(ANALYTICS_DISCLAIMER)


# ──────────────────────────────────────────────────────────────────────────────
# Decision Intelligence Section (Phase 13)
# ──────────────────────────────────────────────────────────────────────────────


def _render_decision_intelligence_section(all_records: list[AnalysisRecord]) -> None:
    """Render the Decision Intelligence & Comparative Analytics Console from Phase 13."""
    from frontend.utils.decision_intelligence import (
        RESPONSIBLE_ANALYTICS_DISCLAIMER,
        compare_analysis_records,
    )
    from frontend.utils.export import (
        generate_comparison_brief,
        generate_comparison_json,
        generate_comparison_txt,
    )
    from frontend.utils.investigation import (
        build_investigation_timeline,
        build_multi_analysis_matrix,
        calculate_timeline_trend,
    )
    from frontend.utils.narrative import generate_comparison_narrative

    st.markdown("---")
    st.subheader("Decision Intelligence & Comparative Investigation")
    st.caption(
        "Deterministic comparison, chronological investigation, and evidence-backed narratives "
        "derived exclusively from completed session analyses with zero external network calls."
    )

    completed_records = [r for r in all_records if r.status == "Completed"]

    if len(completed_records) < 2:
        st.info("At least two completed analyses are required in session history to perform comparative decision intelligence.")
        return

    tab_pair, tab_timeline, tab_matrix = st.tabs([
        "Pairwise Comparison",
        "Investigation Timeline & Trends",
        "Multi-Analysis Matrix",
    ])

    with tab_pair:
        options = {f"{r.location_label} ({r.date or 'N/A'} - `{r.analysis_id}`)": r for r in completed_records}
        opt_keys = list(options.keys())

        c_sel1, c_sel2 = st.columns(2)
        with c_sel1:
            sel_a_label = st.selectbox("Baseline Analysis (A)", options=opt_keys, index=0, key="_di_sel_a")
        with c_sel2:
            sel_b_label = st.selectbox("Comparison Analysis (B)", options=opt_keys, index=1 if len(opt_keys) > 1 else 0, key="_di_sel_b")

        rec_a = options[sel_a_label]
        rec_b = options[sel_b_label]

        comparison_result = compare_analysis_records(rec_a, rec_b)
        narrative = generate_comparison_narrative(comparison_result)

        with st.container(border=True):
            st.markdown(f"#### {comparison_result['headline']}")
            col_b_info, col_c_info = st.columns(2)
            with col_b_info:
                st.markdown(f"**Baseline (A):** {rec_a.location_label}  \n`{rec_a.analysis_id}` · Date: `{rec_a.date or 'N/A'}`")
            with col_c_info:
                st.markdown(f"**Comparison (B):** {rec_b.location_label}  \n`{rec_b.analysis_id}` · Date: `{rec_b.date or 'N/A'}`")

        st.markdown("##### Metric-by-Metric Comparison (Δ = B − A)")
        with st.container(border=True):
            header_cols = st.columns([3, 2, 2, 2, 3])
            header_cols[0].markdown("**Metric**")
            header_cols[1].markdown("**A: Baseline**")
            header_cols[2].markdown("**B: Comparison**")
            header_cols[3].markdown("**Difference (Δ)**")
            header_cols[4].markdown("**Interpretation**")

            for m in comparison_result["metrics"]:
                cols = st.columns([3, 2, 2, 2, 3])
                cols[0].markdown(f"**{m.label}**")
                if not m.available:
                    cols[1].markdown("`—`")
                    cols[2].markdown("`—`")
                    cols[3].markdown("`—`")
                    cols[4].caption(f":gray[{m.interpretation}]")
                else:
                    unit_str = f" {m.unit}" if m.unit else ""
                    b_str = f"{m.baseline_value:.2f}{unit_str}" if isinstance(m.baseline_value, (int, float)) else str(m.baseline_value)
                    c_str = f"{m.comparison_value:.2f}{unit_str}" if isinstance(m.comparison_value, (int, float)) else str(m.comparison_value)
                    cols[1].markdown(f"`{b_str}`")
                    cols[2].markdown(f"`{c_str}`")

                    diff_color = "red" if m.direction == "increase" else ("green" if m.direction == "decrease" else "gray")
                    delta_str = f"+{m.delta:.2f}" if m.delta is not None and m.delta > 0 else (f"{m.delta:.2f}" if m.delta is not None else "—")
                    pct_str = f" ({'+' if m.percent_change and m.percent_change > 0 else ''}{m.percent_change:.1f}%)" if m.percent_change is not None else ""
                    cols[3].markdown(f":{diff_color}[**{delta_str}{unit_str}{pct_str}**]")
                    cols[4].caption(m.interpretation)

        st.markdown("##### Change Detection Breakdown")
        with st.container(border=True):
            bd1, bd2, bd3, bd4 = st.columns(4)
            bd1.metric("Increased", len(comparison_result["increased"]))
            bd2.metric("Decreased", len(comparison_result["decreased"]))
            bd3.metric("Unchanged", len(comparison_result["unchanged"]))
            bd4.metric("Insufficient Data", len(comparison_result["missing"]))
            if comparison_result["increased"]:
                st.caption(
                    "Increased: "
                    + ", ".join(m.label for m in comparison_result["increased"])
                )
            if comparison_result["decreased"]:
                st.caption(
                    "Decreased: "
                    + ", ".join(m.label for m in comparison_result["decreased"])
                )
            if comparison_result["unchanged"]:
                st.caption(
                    "Unchanged: "
                    + ", ".join(m.label for m in comparison_result["unchanged"])
                )
            st.caption(
                "Classifications are descriptive numerical comparisons of observed metrics only. "
                "They do not establish causation or predict future conditions."
            )

        st.markdown("##### Evidence-Backed Analytical Narrative")
        with st.container(border=True):
            st.markdown(f"**What Changed?**  \n{narrative['what_changed']}")
            st.markdown(f"**What Stayed Similar?**  \n{narrative['what_stayed_similar']}")
            st.markdown(f"**Data Limitations:**  \n{narrative['data_limitations']}")
            st.divider()
            st.caption(RESPONSIBLE_ANALYTICS_DISCLAIMER)

        # Local sanitized comparison exports (0 HTTP)
        brief_txt = generate_comparison_brief(comparison_result, narrative)
        cmp_json = generate_comparison_json(comparison_result, narrative)
        cmp_txt = generate_comparison_txt(comparison_result, narrative)
        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button(
                "Analytical Brief",
                data=brief_txt,
                file_name=f"comparison_brief_{rec_a.analysis_id}_{rec_b.analysis_id}.txt",
                mime="text/plain",
                key="_di_dl_brief",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Comparison JSON",
                data=cmp_json,
                file_name=f"comparison_{rec_a.analysis_id}_{rec_b.analysis_id}.json",
                mime="application/json",
                key="_di_dl_json",
                use_container_width=True,
            )
        with dl3:
            st.download_button(
                "Comparison TXT",
                data=cmp_txt,
                file_name=f"comparison_{rec_a.analysis_id}_{rec_b.analysis_id}.txt",
                mime="text/plain",
                key="_di_dl_txt",
                use_container_width=True,
            )

    with tab_timeline:
        timeline_events = build_investigation_timeline(completed_records, ascending=True)
        if timeline_events:
            trend_data = calculate_timeline_trend(timeline_events)
            with st.container(border=True):
                st.markdown(f"#### Observed Trend: **{trend_data['trend']}**")
                st.caption(trend_data["summary"])

    with tab_matrix:
        matrix_data = build_multi_analysis_matrix(completed_records, max_analyses=5)
        if matrix_data["count"] >= 2:
            st.markdown("#### Longitudinal Comparison Matrix")
            headers = ["Metric"] + matrix_data["headers"]
            h_cols = st.columns(len(headers))
            for i, h in enumerate(headers):
                h_cols[i].markdown(f"**{h}**")
            for r in matrix_data["rows"]:
                r_cols = st.columns(len(headers))
                r_cols[0].markdown(f"**{r['metric']}**")
                for j, v in enumerate(r["values"]):
                    r_cols[j + 1].markdown(f"`{v}`")


if __name__ == "__main__":
    from frontend.components.design_system import inject_design_system
    inject_design_system()
    st.title("FortyGuard Heat Intelligence")
    st.caption("Comprehensive Urban Thermal Analytics & Multi-Factor Resilience Platform")
    render_dashboard_page()

