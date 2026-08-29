"""Reusable chart/analytics placeholder components."""

import streamlit as st


def render_analytics_section(title: str = "Analytics / Charts") -> None:
    """
    Prepare a reusable analytics section.

    Phase 0: placeholder only — no external API calls.
    """
    st.subheader(title)
    st.caption("Temperature trends and heat-risk analytics will appear here.")
    st.bar_chart(
        {"Morning": 0, "Afternoon": 0, "Evening": 0, "Night": 0},
        width="stretch",
    )
