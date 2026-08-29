"""Session-Local Signal Center UI Component.

Renders prioritized operational signal triage, precedence ranking, inline
"Why am I seeing this?" evidence bundles, and disposition state controls.

Strict Invariants:
1. Pure session-local state in st.session_state (zero network requests).
2. Unique namespaced widget keys prefixed with 'signal:'.
3. Precedence hierarchy: WATCHLIST_MATCH > THRESHOLD_BREACH > RAPID_CHANGE > SIGNIFICANT_CHANGE > REPEATED_HEAT > DATA_ANOMALY.
4. Non-causal, responsible analytics presentation.
"""

from __future__ import annotations

from typing import Any, Sequence
import streamlit as st

from frontend.utils.evidence import build_evidence_bundle
from frontend.utils.investigation_queue import add_to_investigation_queue
from frontend.utils.priority import get_signal_priority
from frontend.utils.signal_pipeline import (
    DISPOSITION_ACKNOWLEDGED,
    DISPOSITION_DISMISSED,
    DISPOSITION_NEW,
    DISPOSITION_RESOLVED,
    SIGNAL_TYPE_PRECEDENCE,
    update_signal_disposition,
)


def render_signal_center(
    signals: Sequence[Any],
    records: Sequence[Any] | None = None,
) -> None:
    """Render the Signal Center with triage filtering, precedence, and evidence cards."""
    st.markdown("### Operational Signal Center")
    st.markdown(
        "Deterministic signal triage engine with strict precedence ranking, "
        "evidence explainability, and operator lifecycle dispositions."
    )

    if not signals:
        st.info("No operational signals detected in completed session analyses.")
        return

    # ── Filter Bar ──
    c1, c2, c3 = st.columns(3)
    with c1:
        sig_types = ["ALL"] + sorted(list(SIGNAL_TYPE_PRECEDENCE.keys()))
        type_filter = st.selectbox("Filter by Signal Type", sig_types, index=0, key="signal:filter:type")
    with c2:
        sev_filter = st.selectbox(
            "Filter by Severity",
            ["ALL", "CRITICAL", "ELEVATED", "WATCH", "INFO"],
            index=0,
            key="signal:filter:sev",
        )
    with c3:
        disp_filter = st.selectbox(
            "Filter by Disposition",
            ["ALL", "NEW", "ACKNOWLEDGED", "LINKED_TO_ALERT", "RESOLVED", "DISMISSED"],
            index=0,
            key="signal:filter:disp",
        )

    # Apply Filters
    filtered_signals: list[dict[str, Any]] = []
    for s in signals:
        s_dict = s if isinstance(s, dict) else s.to_dict()
        if type_filter != "ALL" and s_dict.get("signal_type") != type_filter:
            continue
        if sev_filter != "ALL" and s_dict.get("severity", "").upper() != sev_filter:
            continue
        if disp_filter != "ALL" and s_dict.get("disposition", "NEW").upper() != disp_filter:
            continue
        filtered_signals.append(s_dict)

    st.caption(f"Showing **{len(filtered_signals)} / {len(signals)}** detected signals.")
    st.markdown("---")

    if not filtered_signals:
        st.info("No signals match the selected filters.")
        return

    # Build record lookup map for evidence bundling
    rec_by_id = {}
    if records:
        for r in records:
            r_dict = r.to_dict() if hasattr(r, "to_dict") else dict(r)
            rec_by_id[r_dict.get("analysis_id")] = r

    # ── Render Signal Cards ──
    for idx, sig in enumerate(filtered_signals):
        _render_signal_triage_card(sig, rec_by_id.get(sig.get("analysis_id")), index=idx)


def _render_signal_triage_card(
    sig: dict[str, Any],
    record: Any | None = None,
    index: int = 0,
) -> None:
    """Render an individual operational signal card with disposition and evidence details."""
    sig_id = str(sig.get("signal_id", f"SIG-{index}"))
    title = str(sig.get("title", "Operational Signal"))
    severity = str(sig.get("severity", "INFO")).upper()
    sig_type = str(sig.get("signal_type", "THRESHOLD_BREACH"))
    disposition = str(sig.get("disposition", DISPOSITION_NEW)).upper()
    analysis_id = str(sig.get("analysis_id", "N/A"))
    rank = sig.get("precedence_rank", SIGNAL_TYPE_PRECEDENCE.get(sig_type, 1))
    dq = str(sig.get("data_quality", "HIGH")).upper()

    sev_color = {
        "CRITICAL": "#FF5252",
        "ELEVATED": "#FF9800",
        "WATCH": "#FFEB3B",
        "INFO": "#29B6F6",
    }.get(severity, "#9E9E9E")

    disp_color = {
        DISPOSITION_NEW: "#00E676",
        DISPOSITION_ACKNOWLEDGED: "#29B6F6",
        DISPOSITION_RESOLVED: "#9E9E9E",
        DISPOSITION_DISMISSED: "#757575",
    }.get(disposition, "#FFFFFF")

    with st.container():
        st.markdown(
            f"""
            <div style="background: rgba(255, 255, 255, 0.03); border-left: 4px solid {sev_color}; border-radius: 6px; padding: 12px 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; font-size: 15px; color: #FFFFFF;">{title}</span>
                    <div>
                        <span style="font-size: 11px; background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; color: #E0E0E0; margin-right: 6px;">
                            Precedence: #{rank} ({sig_type})
                        </span>
                        <span style="font-size: 11px; font-weight: 700; color: {sev_color}; background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 4px;">
                            {severity}
                        </span>
                    </div>
                </div>
                <div style="font-size: 13px; color: #CFD8DC; margin-top: 6px;">
                    {sig.get('description', '')}
                </div>
                <div style="font-size: 11px; color: #90A4AE; margin-top: 8px;">
                    Analysis ID: <code>{analysis_id}</code> | Quality: <code>{dq}</code> | Disposition: <b style="color: {disp_color};">{disposition}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Expandable Evidence & "Why am I seeing this?"
        with st.expander(f"Evidence Details & Why Am I Seeing This? (#{sig_id})", expanded=False):
            bundle = build_evidence_bundle(sig, analysis_record=record)
            st.markdown(bundle.why_am_i_seeing_this)
            st.caption(f"Canonical Evidence Hash: `{bundle.evidence_hash[:16]}...` | As of: `{bundle.evidence_as_of}`")

        # Disposition Controls Bar
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        with col1:
            notes_input = st.text_input(
                "Operator Note",
                value=str(sig.get("disposition_notes", "")),
                placeholder="Optional operator notes...",
                key=f"signal:{sig_id}:note_input",
                label_visibility="collapsed",
            )
        with col2:
            if st.button("Acknowledge", key=f"signal:{sig_id}:ack_btn", use_container_width=True):
                update_signal_disposition(sig_id, DISPOSITION_ACKNOWLEDGED, notes=notes_input)
                st.rerun()
        with col3:
            if st.button("Investigate", key=f"signal:{sig_id}:inv_btn", use_container_width=True):
                add_to_investigation_queue(
                    analysis_id=analysis_id,
                    signal_id=sig_id,
                    priority=severity if severity in ("Critical", "High") else "Medium",
                    reason=title,
                    notes=notes_input,
                    source_signal=sig,
                )
                update_signal_disposition(sig_id, DISPOSITION_ACKNOWLEDGED, notes=notes_input)
                st.success("Added to Investigation Queue.")
                st.rerun()
        with col4:
            if st.button("Resolve", key=f"signal:{sig_id}:res_btn", use_container_width=True):
                update_signal_disposition(sig_id, DISPOSITION_RESOLVED, notes=notes_input)
                st.rerun()
        with col5:
            if st.button("Dismiss", key=f"signal:{sig_id}:dis_btn", use_container_width=True):
                update_signal_disposition(sig_id, DISPOSITION_DISMISSED, notes=notes_input)
                st.rerun()
