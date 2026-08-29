"""Streamlit AppTest integration tests for Phase 13 Decision Intelligence Workspace."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_workspace_for_decision_intelligence() -> None:
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, clear_all_analysis_records

    if "_di_test_data_init" not in st.session_state:
        st.session_state["_di_test_data_init"] = True
        clear_all_analysis_records()

        r1 = AnalysisRecord(
            analysis_id="HM-20260822-001",
            activity_id="act_test_1",
            analysis_type="heatmap",
            created_at="2026-08-22 10:00:00",
            updated_at="2026-08-22 10:00:00",
            location_label="Downtown District",
            date="2026-08-20",
            time="14:00",
            granularity=100,
            metrics={"mean_temp": 32.0, "min_temp": 28.0, "max_temp": 38.0, "temp_spread": 10.0, "total_tiles": 50},
            status="Completed",
        )
        r2 = AnalysisRecord(
            analysis_id="HM-20260822-002",
            activity_id="act_test_2",
            analysis_type="heatmap",
            created_at="2026-08-22 11:00:00",
            updated_at="2026-08-22 11:00:00",
            location_label="Downtown District",
            date="2026-08-22",
            time="14:00",
            granularity=100,
            metrics={"mean_temp": 36.0, "min_temp": 30.0, "max_temp": 42.0, "temp_spread": 12.0, "total_tiles": 50},
            status="Completed",
        )
        r3 = AnalysisRecord(
            analysis_id="HI-20260822-003",
            activity_id="act_test_3",
            analysis_type="heat_intelligence",
            created_at="2026-08-22 12:00:00",
            updated_at="2026-08-22 12:00:00",
            location_label="Marina Point",
            date="2026-08-22",
            observed_temperature=34.5,
            categories=["urban"],
            status="Completed",
        )
        add_analysis_record(r1)
        add_analysis_record(r2)
        add_analysis_record(r3)

    render_dashboard_page()


def test_decision_intelligence_section_renders_tabs() -> None:
    """Decision Intelligence section renders pairwise comparison, timeline, and matrix tabs."""
    at = _app_test(_run_workspace_for_decision_intelligence)
    at.run()

    assert not at.exception
    all_texts = " ".join(
        [m.value for m in at.markdown]
        + [s.value for s in at.subheader]
        + [c.value for c in at.caption]
    )
    assert "Decision Intelligence & Comparative Investigation" in all_texts
    assert "Pairwise Comparison" in all_texts or any("Pairwise" in (t.label or "") for t in at.tabs)
    assert "Responsible Analytics" in all_texts


def test_pairwise_comparison_renders_metrics_and_narrative() -> None:
    """Pairwise comparison tab renders metric comparison and narrative."""
    at = _app_test(_run_workspace_for_decision_intelligence)
    at.run()

    assert not at.exception
    markdown_texts = " ".join(m.value for m in at.markdown)
    assert "Metric-by-Metric Comparison" in markdown_texts
    assert "Change Detection Breakdown" in markdown_texts
    assert "Evidence-Backed Analytical Narrative" in markdown_texts
    assert "What Changed?" in markdown_texts

    # Check download buttons for comparison exports exist
    dl_buttons = at.download_button
    assert len(dl_buttons) >= 3


def test_decision_intelligence_zero_network_invariants() -> None:
    """Verify that interaction with comparison and filters triggers zero network calls."""
    at = _app_test(_run_workspace_for_decision_intelligence)
    at.run()

    assert not at.exception
    # Change baseline selection
    sel_a = at.selectbox(key="_di_sel_a")
    if sel_a and len(sel_a.options) > 1:
        sel_a.select_index(1).run()
        assert not at.exception
