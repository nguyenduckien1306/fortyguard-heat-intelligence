"""FortyGuard Product Design System — Presentation Layer Only.

Provides cohesive, enterprise-grade styling, layout tokens, and UI helpers
for the FortyGuard Heat Intelligence platform.

Strict Invariants:
1. Zero business logic — pure presentational styling and HTML/CSS generation.
2. Zero network calls or external data fetching.
3. Completely responsive, accessible, and restrained.
"""

from __future__ import annotations

import streamlit as st


# ── Design Tokens ─────────────────────────────────────────────────────────────
FONT_HEADING = "'Space Grotesk', 'Inter', sans-serif"
FONT_BODY = "'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace"

# Enterprise Palette
COLOR_BG_PRIMARY = "#0B0F19"
COLOR_BG_SURFACE = "#111827"
COLOR_BG_CARD = "#1E293B"
COLOR_BG_CARD_HOVER = "#243248"
COLOR_BORDER = "#334155"
COLOR_BORDER_SUBTLE = "#1E293B"
COLOR_TEXT_PRIMARY = "#F8FAFC"
COLOR_TEXT_SECONDARY = "#94A3B8"
COLOR_TEXT_MUTED = "#64748B"

# Accent Gradient
COLOR_ACCENT_PRIMARY = "#6366F1"  # Indigo
COLOR_ACCENT_SECONDARY = "#8B5CF6"  # Violet
COLOR_ACCENT_TERTIARY = "#38BDF8"  # Sky

# Semantic Status Colors
COLOR_CRITICAL = "#EF4444"
COLOR_CRITICAL_BG = "rgba(239, 68, 68, 0.12)"
COLOR_WARNING = "#F59E0B"
COLOR_WARNING_BG = "rgba(245, 158, 11, 0.12)"
COLOR_SUCCESS = "#10B981"
COLOR_SUCCESS_BG = "rgba(16, 185, 129, 0.12)"
COLOR_INFO = "#3B82F6"
COLOR_INFO_BG = "rgba(59, 130, 246, 0.12)"
COLOR_NEUTRAL = "#64748B"
COLOR_NEUTRAL_BG = "rgba(100, 116, 139, 0.12)"


def inject_design_system() -> None:
    """Inject cohesive global enterprise styling for Streamlit."""
    custom_css = """
    <style>
        /* ═══════════════════════════════════════════════════════════════════
           TYPOGRAPHY & ICONS
           Space Grotesk  → Headings (geometric, bold, distinctive)
           Plus Jakarta Sans → Body (premium, warm, readable)
           JetBrains Mono → Data values, code, metrics
           Material Symbols Rounded → Streamlit native icons & chevrons
           ═══════════════════════════════════════════════════════════════════ */
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

        html, body, .stApp {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            letter-spacing: -0.011em;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            font-feature-settings: 'cv11' 1, 'ss01' 1;
        }

        /* ── Protect Streamlit Material Icons & Chevrons ── */
        [data-testid="stIconMaterial"],
        [data-testid="stExpanderToggleIcon"],
        [data-testid="stSidebarCollapseButton"] span,
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="collapsedControl"] span,
        [data-testid="stHeader"] span,
        [data-testid="stToolbar"] span,
        [data-baseweb="icon"],
        .material-symbols-rounded,
        .material-symbols-outlined,
        .material-icons,
        [class*="material-symbols"],
        [class*="material-icons"],
        summary svg,
        summary [data-testid="stIconMaterial"],
        summary span:first-child {
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
            font-style: normal !important;
            font-weight: normal !important;
            text-transform: none !important;
            letter-spacing: normal !important;
            line-height: 1 !important;
            white-space: nowrap !important;
            direction: ltr !important;
            -webkit-font-smoothing: antialiased !important;
        }

        /* Headings use Space Grotesk — geometric and distinctive */
        h1, h2, h3, h4, h5, h6,
        .stTabs [data-baseweb="tab"],
        .fg-hero h2,
        [data-testid="stMetricLabel"] {
            font-family: 'Space Grotesk', sans-serif !important;
        }

        /* Code, data, and metric values use JetBrains Mono */
        code, pre, .stCode, [data-testid="stCode"],
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
            font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           APP SHELL — Background & Base
           ═══════════════════════════════════════════════════════════════════ */
        .stApp {
            background: #0B0F19;
            color: #F8FAFC;
        }

        /* Page title styling — Space Grotesk hero */
        .stApp h1 {
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 700 !important;
            letter-spacing: -0.04em !important;
            background: linear-gradient(135deg, #F8FAFC 0%, #A5B4FC 50%, #94A3B8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 2.1rem !important;
            margin-bottom: 0 !important;
            line-height: 1.15 !important;
        }

        /* Subheaders — Space Grotesk */
        h2, h3 {
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 700 !important;
            letter-spacing: -0.03em !important;
            color: #E2E8F0 !important;
            line-height: 1.2 !important;
        }

        h4, h5 {
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
            color: #CBD5E1 !important;
            line-height: 1.25 !important;
        }

        /* Caption text — Plus Jakarta Sans (lighter weight) */
        .stCaption, [data-testid="stCaptionContainer"] {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            color: #64748B !important;
            font-size: 12px !important;
            font-weight: 400 !important;
            line-height: 1.55 !important;
        }

        /* Body elements */
        .stMarkdown p, .stMarkdown li,
        .stTextInput label, .stNumberInput label, .stSelectbox label,
        .stSlider label, .stCheckbox label {
            font-family: 'Plus Jakarta Sans', sans-serif;
        }

        /* Strong/bold text gets slightly heavier */
        strong, b {
            font-weight: 700 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           SCROLLBAR — Minimal & Dark
           ═══════════════════════════════════════════════════════════════════ */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: #334155;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #475569;
        }

        /* ═══════════════════════════════════════════════════════════════════
           SIDEBAR — Premium Navigation
           ═══════════════════════════════════════════════════════════════════ */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0F172A 0%, #0B1120 100%) !important;
            border-right: 1px solid rgba(99, 102, 241, 0.15) !important;
        }
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 11px !important;
            text-transform: uppercase !important;
            letter-spacing: 0.1em !important;
            color: #64748B !important;
            margin-top: 12px !important;
            font-weight: 700 !important;
        }

        /* Sidebar radio buttons */
        [data-testid="stSidebar"] .stRadio > div {
            gap: 2px !important;
        }
        [data-testid="stSidebar"] .stRadio label {
            padding: 8px 12px !important;
            border-radius: 8px !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            font-size: 13px !important;
            font-weight: 500 !important;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
            background: rgba(99, 102, 241, 0.08) !important;
        }
        [data-testid="stSidebar"] .stRadio label[data-checked="true"],
        [data-testid="stSidebar"] .stRadio label:has(input:checked) {
            background: rgba(99, 102, 241, 0.12) !important;
            border-left: 3px solid #6366F1 !important;
        }

        /* Sidebar divider */
        [data-testid="stSidebar"] hr {
            border-color: rgba(99, 102, 241, 0.12) !important;
            margin: 16px 0 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           TABS — Clean Segmented Control
           ═══════════════════════════════════════════════════════════════════ */
        .stTabs [data-baseweb="tab-list"] {
            gap: 2px;
            background-color: rgba(15, 23, 42, 0.6);
            border: 1px solid #1E293B;
            border-radius: 10px;
            padding: 4px;
            backdrop-filter: blur(8px);
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 12px !important;
            font-weight: 500 !important;
            color: #64748B !important;
            padding: 8px 14px !important;
            border-radius: 8px !important;
            border: none !important;
            background: transparent !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            white-space: nowrap !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #CBD5E1 !important;
            background-color: rgba(99, 102, 241, 0.06) !important;
        }
        .stTabs [aria-selected="true"] {
            color: #F8FAFC !important;
            font-weight: 600 !important;
            background: rgba(99, 102, 241, 0.15) !important;
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.1);
        }
        /* Remove the default bottom highlight bar */
        .stTabs [data-baseweb="tab-highlight"] {
            display: none !important;
        }
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           METRIC CARDS — Premium Data Display
           ═══════════════════════════════════════════════════════════════════ */
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #1E293B 0%, #172033 100%) !important;
            border: 1px solid rgba(99, 102, 241, 0.12) !important;
            border-radius: 12px !important;
            padding: 16px 18px !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2),
                        inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }
        [data-testid="stMetric"]:hover {
            border-color: rgba(99, 102, 241, 0.25) !important;
            box-shadow: 0 4px 20px rgba(99, 102, 241, 0.08),
                        0 8px 24px rgba(0, 0, 0, 0.25),
                        inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
            transform: translateY(-1px) !important;
        }
        [data-testid="stMetricLabel"] {
            font-family: 'Inter', sans-serif !important;
            font-size: 10.5px !important;
            text-transform: uppercase !important;
            letter-spacing: 0.08em !important;
            color: #64748B !important;
            font-weight: 700 !important;
        }
        [data-testid="stMetricValue"] {
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 24px !important;
            font-weight: 600 !important;
            color: #F8FAFC !important;
            line-height: 1.1 !important;
            letter-spacing: -0.02em !important;
        }
        [data-testid="stMetricDelta"] {
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 11px !important;
            font-weight: 500 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           CONTAINERS & CARDS — Glassmorphism
           ═══════════════════════════════════════════════════════════════════ */
        [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid rgba(99, 102, 241, 0.1) !important;
            border-radius: 12px !important;
            background: rgba(30, 41, 59, 0.5) !important;
            backdrop-filter: blur(12px) !important;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15) !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: rgba(99, 102, 241, 0.18) !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
        }

        /* Custom card classes */
        .fg-card {
            background: linear-gradient(145deg, rgba(30, 41, 59, 0.8) 0%, rgba(23, 32, 51, 0.8) 100%);
            border: 1px solid rgba(99, 102, 241, 0.1);
            border-radius: 12px;
            padding: 18px 22px;
            margin-bottom: 14px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
            backdrop-filter: blur(12px);
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .fg-card:hover {
            border-color: rgba(99, 102, 241, 0.2);
            box-shadow: 0 6px 24px rgba(0, 0, 0, 0.2);
            transform: translateY(-1px);
        }
        .fg-card-subtle {
            background: rgba(21, 30, 46, 0.6);
            border: 1px solid rgba(36, 50, 72, 0.6);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 8px;
            backdrop-filter: blur(8px);
        }

        /* Hero banner */
        .fg-hero {
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.9) 0%, rgba(30, 41, 59, 0.9) 50%, rgba(49, 46, 129, 0.3) 100%);
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 16px;
            padding: 28px 32px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(99, 102, 241, 0.06),
                        0 2px 8px rgba(0, 0, 0, 0.2);
            position: relative;
            overflow: hidden;
        }
        .fg-hero::before {
            content: '';
            position: absolute;
            top: 0;
            right: 0;
            width: 200px;
            height: 200px;
            background: radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%);
            pointer-events: none;
        }

        /* Scenario banner */
        .fg-scenario-banner {
            background: rgba(245, 158, 11, 0.06);
            border: 1px solid rgba(245, 158, 11, 0.2);
            border-left: 4px solid #F59E0B;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 16px;
            backdrop-filter: blur(8px);
        }

        /* ═══════════════════════════════════════════════════════════════════
           STATUS BADGES — Refined Pills
           ═══════════════════════════════════════════════════════════════════ */
        .fg-badge {
            display: inline-flex;
            align-items: center;
            font-family: 'Inter', sans-serif;
            font-size: 10px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 6px;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            line-height: 1.4;
        }
        .fg-badge-critical {
            background: rgba(239, 68, 68, 0.12);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.25);
            box-shadow: 0 0 8px rgba(239, 68, 68, 0.08);
        }
        .fg-badge-elevated {
            background: rgba(249, 115, 22, 0.12);
            color: #FB923C;
            border: 1px solid rgba(249, 115, 22, 0.25);
        }
        .fg-badge-watch {
            background: rgba(245, 158, 11, 0.12);
            color: #FBBF24;
            border: 1px solid rgba(245, 158, 11, 0.25);
        }
        .fg-badge-info {
            background: rgba(99, 102, 241, 0.12);
            color: #A5B4FC;
            border: 1px solid rgba(99, 102, 241, 0.25);
            box-shadow: 0 0 8px rgba(99, 102, 241, 0.06);
        }
        .fg-badge-success {
            background: rgba(16, 185, 129, 0.12);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.25);
        }
        .fg-badge-neutral {
            background: rgba(100, 116, 139, 0.12);
            color: #94A3B8;
            border: 1px solid rgba(100, 116, 139, 0.25);
        }
        .fg-badge-hypothetical {
            background: rgba(168, 85, 247, 0.12);
            color: #C084FC;
            border: 1px solid rgba(168, 85, 247, 0.25);
        }

        /* ═══════════════════════════════════════════════════════════════════
           BUTTONS — Polished Hierarchy
           ═══════════════════════════════════════════════════════════════════ */
        .stButton > button {
            border-radius: 8px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 12.5px !important;
            font-weight: 600 !important;
            padding: 8px 16px !important;
            letter-spacing: 0.01em !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            border: 1px solid #334155 !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15) !important;
        }
        .stButton > button:hover {
            border-color: rgba(99, 102, 241, 0.4) !important;
            background-color: rgba(99, 102, 241, 0.08) !important;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1) !important;
            transform: translateY(-1px) !important;
        }
        .stButton > button:active {
            transform: translateY(0) !important;
        }

        /* Primary buttons */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
            border: none !important;
            color: white !important;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25) !important;
        }
        .stButton > button[kind="primary"]:hover {
            box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35) !important;
            background: linear-gradient(135deg, #7C7FF7 0%, #9D78F8 100%) !important;
        }

        /* Download buttons */
        .stDownloadButton > button {
            border-radius: 8px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 12px !important;
            font-weight: 600 !important;
            border: 1px solid #334155 !important;
            transition: all 0.2s ease !important;
        }
        .stDownloadButton > button:hover {
            border-color: rgba(99, 102, 241, 0.4) !important;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1) !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           FORM INPUTS — Refined & Cohesive
           ═══════════════════════════════════════════════════════════════════ */
        .stTextInput input, .stNumberInput input, .stSelectbox select {
            border-radius: 8px !important;
            border: 1px solid #334155 !important;
            background-color: rgba(15, 23, 42, 0.8) !important;
            color: #F8FAFC !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 13px !important;
            padding: 8px 12px !important;
            transition: all 0.2s ease !important;
        }
        .stTextInput input:focus, .stNumberInput input:focus {
            border-color: rgba(99, 102, 241, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1) !important;
        }

        /* Selectbox dropdown */
        [data-baseweb="select"] > div {
            border-radius: 8px !important;
            border-color: #334155 !important;
            background-color: rgba(15, 23, 42, 0.8) !important;
        }

        /* Slider styling */
        .stSlider [data-baseweb="slider"] [role="slider"] {
            background-color: #6366F1 !important;
            border: 2px solid #818CF8 !important;
        }
        .stSlider [data-testid="stTickBar"] > div {
            background-color: #6366F1 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           EXPANDERS — Refined
           ═══════════════════════════════════════════════════════════════════ */
        .streamlit-expanderHeader {
            font-size: 13px !important;
            font-weight: 600 !important;
            color: #94A3B8 !important;
            border-radius: 8px !important;
            transition: color 0.2s ease !important;
        }
        .streamlit-expanderHeader p {
            font-family: 'Space Grotesk', sans-serif !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            margin: 0 !important;
        }
        .streamlit-expanderHeader:hover {
            color: #CBD5E1 !important;
        }
        .streamlit-expanderContent {
            border-top: 1px solid rgba(99, 102, 241, 0.1) !important;
            padding-top: 14px !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           DIVIDERS — Subtle & Clean
           ═══════════════════════════════════════════════════════════════════ */
        hr {
            border-color: rgba(51, 65, 85, 0.5) !important;
            margin: 20px 0 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           ALERTS / INFO BOXES — Refined
           ═══════════════════════════════════════════════════════════════════ */
        .stAlert {
            border-radius: 10px !important;
            border: 1px solid rgba(99, 102, 241, 0.15) !important;
            font-size: 13px !important;
            backdrop-filter: blur(8px) !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           DATAFRAMES & TABLES — Dark Theme
           ═══════════════════════════════════════════════════════════════════ */
        .stDataFrame {
            border-radius: 10px !important;
            overflow: hidden !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           CHECKBOX & RADIO — Accent Color
           ═══════════════════════════════════════════════════════════════════ */
        .stCheckbox label span[data-checked="true"]::before,
        .stRadio label span[data-checked="true"]::before {
            background-color: #6366F1 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           TOOLTIP & HELP — Refined
           ═══════════════════════════════════════════════════════════════════ */
        [data-testid="stTooltipIcon"] {
            color: #475569 !important;
        }

        /* ═══════════════════════════════════════════════════════════════════
           ANIMATION KEYFRAMES
           ═══════════════════════════════════════════════════════════════════ */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes subtlePulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .fg-animate-in {
            animation: fadeInUp 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }
        .fg-pulse {
            animation: subtlePulse 2s ease-in-out infinite;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)


def render_hero_header(
    title: str,
    subtitle: str,
    badge_label: str | None = None,
) -> None:
    """Render a clean, modern analytical hero banner."""
    badge_html = (
        f'<span class="fg-badge fg-badge-info" style="margin-left: 10px;">{badge_label}</span>'
        if badge_label
        else ""
    )
    st.markdown(
        f"""
        <div class="fg-hero fg-animate-in">
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; color: #818CF8; margin-bottom: 8px;">FORTYGUARD HEAT INTELLIGENCE</div>
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <h2 style="margin: 0; font-family: 'Space Grotesk', sans-serif; color: #F8FAFC; font-size: 20px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.3;">
                    {title} {badge_html}
                </h2>
            </div>
            <p style="margin: 0; font-family: 'Plus Jakarta Sans', sans-serif; color: #94A3B8; font-size: 13px; line-height: 1.6; max-width: 700px;">
                {subtitle}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(
    title: str,
    subtitle: str | None = None,
    badge_text: str | None = None,
    badge_type: str = "neutral",
) -> None:
    """Render a consistent section header with optional subtitle and badge."""
    badge_html = f'<span class="fg-badge fg-badge-{badge_type}">{badge_text}</span>' if badge_text else ""
    sub_html = f'<p style="margin: 4px 0 0 0; font-family: \'Plus Jakarta Sans\', sans-serif; color: #64748B; font-size: 12px; line-height: 1.4;">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div style="display: flex; align-items: baseline; justify-content: space-between; margin-top: 16px; margin-bottom: 10px; border-bottom: 1px solid rgba(99, 102, 241, 0.1); padding-bottom: 8px;">
            <div>
                <span style="font-family: 'Space Grotesk', sans-serif; font-size: 15px; font-weight: 700; color: #E2E8F0; letter-spacing: -0.02em;">{title}</span>
                {sub_html}
            </div>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(
    title: str,
    description: str,
    action_suggestion: str | None = None,
) -> None:
    """Render a calm, professional empty state container."""
    action_html = (
        f'<div style="margin-top: 12px; font-size: 12px; color: #818CF8; font-weight: 600; letter-spacing: 0.01em;">Next action: {action_suggestion}</div>'
        if action_suggestion
        else ""
    )
    st.markdown(
        f"""
        <div class="fg-card fg-animate-in" style="text-align: center; padding: 40px 28px; border: 1px dashed rgba(99, 102, 241, 0.2);">
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 15px; font-weight: 700; color: #E2E8F0; margin-bottom: 8px;">{title}</div>
            <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 13px; color: #94A3B8; max-width: 500px; margin: 0 auto; line-height: 1.6;">{description}</div>
            {action_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_scenario_callout(
    title: str = "Hypothetical Scenario Simulation",
    subtitle: str = "Parameter adjustments represent hypothetical what-if states and never alter historical observations or provider records.",
) -> None:
    """Render a distinct, standardized visual container for scenario sandbox outputs."""
    st.markdown(
        f"""
        <div class="fg-scenario-banner fg-animate-in">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-family: 'Space Grotesk', sans-serif; font-size: 12px; font-weight: 700; color: #F59E0B; text-transform: uppercase; letter-spacing: 0.08em;">
                    {title}
                </span>
                <span class="fg-badge fg-badge-hypothetical">What-If Only</span>
            </div>
            <div style="font-size: 12px; color: #D1D5DB; margin-top: 6px; line-height: 1.5;">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
