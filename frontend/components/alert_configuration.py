"""Streamlit UI Component for Alert Policy Configuration.

Allows analysts to create, edit, toggle, delete, and reset session-local alert policies.

Strict Invariants:
1. Zero HTTP / Network I/O — policies are stored purely in st.session_state.
2. Rejects invalid thresholds, duplicate conditions, and enforces the 20-policy limit.
"""

from __future__ import annotations

import streamlit as st

from frontend.utils.alert_policies import (
    MAX_ALERT_POLICIES,
    SUPPORTED_METRICS,
    SUPPORTED_OPERATORS,
    SUPPORTED_SEVERITIES,
    AlertPolicy,
    delete_alert_policy,
    get_alert_policies,
    reset_default_alert_policies,
    save_alert_policy,
    toggle_alert_policy,
)


def render_alert_configuration_panel() -> None:
    """Render the Alert Policy configuration and management view."""
    st.markdown("### ⚙️ Alert Policy Management")
    st.caption("Configure session-local threshold rules that automatically generate operational signals on completed analyses.")

    current_policies = get_alert_policies()
    active_count = len(current_policies)

    col_info, col_reset = st.columns([7, 3])
    with col_info:
        st.markdown(f"**Configured Policies:** `{active_count} / {MAX_ALERT_POLICIES}`")
    with col_reset:
        if st.button("↺ Reset Default Policies", key="_btn_reset_policies", type="secondary"):
            reset_default_alert_policies()
            st.success("Alert policies reset to system defaults.")
            st.rerun()

    st.divider()

    # ── Policy Creation Form ──
    with st.expander("➕ Create New Alert Policy", expanded=False):
        with st.form(key="_form_create_policy"):
            c_name, c_metric = st.columns([5, 5])
            with c_name:
                pol_name = st.text_input("Policy Name", placeholder="e.g. Extreme Heat Watch", max_chars=60)
            with c_metric:
                metric_options = sorted(list(SUPPORTED_METRICS))
                metric_labels = [m.replace("_", " ").title() for m in metric_options]
                selected_metric_idx = st.selectbox(
                    "Target Metric",
                    options=range(len(metric_options)),
                    format_func=lambda i: metric_labels[i],
                    index=0,
                )
                pol_metric = metric_options[selected_metric_idx]

            c_op, c_thresh, c_sev = st.columns([3, 4, 3])
            with c_op:
                pol_op = st.selectbox("Condition Operator", options=[">=", ">", "<=", "<", "=="], index=0)
            with c_thresh:
                default_thresh = 35.0 if "temp" in pol_metric else (40.0 if "prop" in pol_metric else 50.0)
                pol_thresh = st.number_input("Threshold Value", value=default_thresh, step=0.5)
            with c_sev:
                pol_sev = st.selectbox("Signal Severity", options=["CRITICAL", "ELEVATED", "WATCH", "INFO"], index=1)

            c_scope, c_enabled = st.columns([7, 3])
            with c_scope:
                pol_scope = st.text_input("Applies To (Scope)", value="all", placeholder="all | heatmap | heat_intelligence | Location")
            with c_enabled:
                st.write("")
                st.write("")
                pol_enabled = st.checkbox("Enabled", value=True)

            btn_submit = st.form_submit_button("Create Alert Policy", type="primary")

            if btn_submit:
                new_pol = AlertPolicy(
                    policy_id="",
                    name=pol_name,
                    metric=pol_metric,
                    operator=pol_op,
                    threshold=float(pol_thresh),
                    severity=pol_sev,
                    applies_to=pol_scope or "all",
                    enabled=pol_enabled,
                )
                ok, err = save_alert_policy(new_pol)
                if not ok and err:
                    st.error(f"⚠️ {err}")
                else:
                    st.success(f"✓ Alert policy '{pol_name}' created successfully.")
                    st.rerun()

    # ── Policy List & Management ──
    st.markdown("#### Active & Inactive Policies")

    if not current_policies:
        st.info("No alert policies currently configured. Create a policy above or reset to defaults.")
        return

    for pol in current_policies:
        with st.container(border=True):
            col_header, col_actions = st.columns([7, 3])
            with col_header:
                sev_color = "red" if pol.severity == "CRITICAL" else ("orange" if pol.severity == "ELEVATED" else ("blue" if pol.severity == "WATCH" else "gray"))
                status_icon = "🟢 Enabled" if pol.enabled else "⚪ Disabled"
                metric_label = pol.metric.replace("_", " ").title()
                unit = "°C" if "temp" in pol.metric else ("%" if "proportion" in pol.metric else "tiles")

                st.markdown(f"**{pol.name}** · :{sev_color}[● {pol.severity}] · `{status_icon}`")
                st.caption(
                    f"**Condition:** `{metric_label}` `{pol.operator}` `{pol.threshold}{unit}` · "
                    f"**Scope:** `{pol.applies_to}` · **ID:** `{pol.policy_id}`"
                )

            with col_actions:
                c_toggle, c_del = st.columns(2)
                with c_toggle:
                    toggle_label = "Disable" if pol.enabled else "Enable"
                    if st.button(toggle_label, key=f"_btn_tog_{pol.policy_id}", use_container_width=True):
                        toggle_alert_policy(pol.policy_id)
                        st.rerun()
                with c_del:
                    if st.button("Delete", key=f"_btn_del_{pol.policy_id}", type="secondary", use_container_width=True):
                        delete_alert_policy(pol.policy_id)
                        st.rerun()
