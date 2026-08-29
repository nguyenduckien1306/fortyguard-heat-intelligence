"""
FortyGuard Heat Intelligence — Streamlit frontend entry point.

Run with:
    streamlit run frontend/app.py

Communicates with the FastAPI backend only — never with FortyGuard directly.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when run via `streamlit run frontend/app.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from frontend.components.design_system import inject_design_system
from frontend.pages.dashboard import render_dashboard_page
from frontend.pages.heat_intelligence import render_heat_intelligence_page
from frontend.pages.heatmap import render_heatmap_page
from frontend.utils.history import get_session_history

st.set_page_config(
    page_title="FortyGuard Heat Intelligence",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_design_system()

# ── Branded App Header ──
st.markdown("""
<div style="margin-bottom: 4px;">
    <h1 style="margin-bottom: 2px !important;">FortyGuard Heat Intelligence</h1>
    <p style="font-family: 'Plus Jakarta Sans', sans-serif; color: #64748B; font-size: 13px; margin: 0; font-weight: 500; letter-spacing: 0.01em;">
        Comprehensive Urban Thermal Analytics & Multi-Factor Resilience Platform
    </p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar Navigation ──
st.sidebar.markdown("""
<div style="margin-bottom: 16px; padding: 12px 0;">
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: #818CF8; margin-bottom: 4px;">FortyGuard</div>
    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 16px; font-weight: 700; color: #F8FAFC; letter-spacing: -0.03em;">Heat Intelligence</div>
    <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 11px; color: #475569; margin-top: 2px;">v2.0 Enterprise</div>
</div>
""", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigation",
    options=["Dashboard", "Heatmap Analysis", "Heat Intelligence"],
    index=0,
    help="Select an analysis workflow",
)

# Render session history counter in sidebar footer
from frontend.utils.analysis_history import list_analysis_records
records = list_analysis_records()
if records:
    st.sidebar.divider()
    st.sidebar.markdown(f"""
    <div style="padding: 10px 12px; background: rgba(99, 102, 241, 0.06); border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.1);">
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748B; font-weight: 700; margin-bottom: 4px;">Session History</div>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 600; color: #A5B4FC;">{len(records)}</div>
        <div style="font-size: 11px; color: #475569;">analyses recorded</div>
    </div>
    """, unsafe_allow_html=True)

if page == "Dashboard":
    render_dashboard_page()
elif page == "Heatmap Analysis":
    render_heatmap_page()
else:
    render_heat_intelligence_page()
