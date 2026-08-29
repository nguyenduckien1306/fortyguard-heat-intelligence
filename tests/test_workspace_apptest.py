"""Streamlit AppTest integration tests for the Analysis Workspace and Investigation Console."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_workspace_empty() -> None:
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import clear_all_analysis_records
    clear_all_analysis_records()
    render_dashboard_page()


def _run_workspace_with_data() -> None:
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record

    if "_init_test_data" not in st.session_state:
        st.session_state["_init_test_data"] = True
        r1 = AnalysisRecord(
            analysis_id="HM-20260822-001",
            activity_id="act_test_1",
            analysis_type="heatmap",
            created_at="2026-08-22 10:00:00",
            updated_at="2026-08-22 10:00:00",
            location_label="Financial District AOI",
            date="2026-08-22",
            time="14:00",
            granularity=100,
            metrics={"mean_temp": 32.5, "total_tiles": 40},
            status="Completed",
            tags=["baseline", "summer"],
            pinned=True,
        )
        r2 = AnalysisRecord(
            analysis_id="HI-20260822-002",
            activity_id="act_test_2",
            analysis_type="heat_intelligence",
            created_at="2026-08-22 11:00:00",
            updated_at="2026-08-22 11:00:00",
            location_label="Midtown Point",
            latitude=40.7580,
            longitude=-73.9855,
            date="2026-08-22",
            observed_temperature=34.2,
            categories=["urban", "events"],
            status="Completed",
        )
        add_analysis_record(r1)
        add_analysis_record(r2)

    render_dashboard_page()


def test_workspace_empty_state_renders_cleanly() -> None:
    """Empty workspace renders clean guidance with no exceptions."""
    at = _app_test(_run_workspace_empty)
    at.run()

    assert not at.exception
    markdown_texts = " ".join(m.value for m in at.markdown)
    assert "No Analyses Recorded Yet" in markdown_texts or "Heatmap Analysis" in markdown_texts


def test_workspace_with_data_renders_summary_and_cards() -> None:
    """Workspace with data displays summary metrics and analysis cards."""
    at = _app_test(_run_workspace_with_data)
    at.run()

    assert not at.exception
    # Verify metric components (Total, Pinned, Heat Intelligence, Heatmap)
    metric_labels = [m.label for m in at.metric]
    assert "Total Analyses" in metric_labels
    assert any("Pinned" in lbl for lbl in metric_labels)

    # Verify search input is present
    assert len(at.text_input) >= 1

    # Verify open buttons exist
    open_btns = [b for b in at.button if "Open Analysis" in (b.label or "")]
    assert len(open_btns) == 2


def test_workspace_search_filters_cards() -> None:
    """Typing into search input filters down the displayed cards."""
    at = _app_test(_run_workspace_with_data)
    at.run()

    # Search for Midtown
    search_input = at.text_input(key="_ws_search_input")
    search_input.set_value("Midtown").run()

    assert not at.exception
    # Should only show 1 Open Analysis button for Midtown
    open_btns = [b for b in at.button if "Open Analysis" in (b.label or "")]
    assert len(open_btns) == 1


def test_workspace_open_detail_and_back() -> None:
    """Opening an analysis opens the Investigation Console, and clicking Back returns to workspace."""
    at = _app_test(_run_workspace_with_data)
    at.run()

    # Click Open Analysis on first card
    open_btn = at.button(key="_open_btn_HM-20260822-001")
    open_btn.click().run()

    assert not at.exception
    # Detail view header
    markdown_texts = " ".join(m.value for m in at.markdown)
    assert "Investigation Console" in markdown_texts or "Financial District" in markdown_texts

    # Click Back to Workspace
    back_btn = at.button(key="_btn_back_to_ws")
    back_btn.click().run()

    assert not at.exception
    # Should be back at workspace
    metric_labels = [m.label for m in at.metric]
    assert "Total Analyses" in metric_labels


def test_workspace_filter_by_type_dropdown() -> None:
    """Selecting Heat Intelligence in the Type filter shows only Heat Intelligence cards."""
    at = _app_test(_run_workspace_with_data)
    at.run()

    type_sel = at.selectbox(key="_ws_type_filter")
    type_sel.select("Heat Intelligence").run()

    assert not at.exception
    open_btns = [b for b in at.button if "Open Analysis" in (b.label or "")]
    assert len(open_btns) == 1


def test_workspace_filter_by_pinned_checkbox() -> None:
    """Checking Pinned Only displays only pinned analyses."""
    at = _app_test(_run_workspace_with_data)
    at.run()

    pin_cb = at.checkbox(key="_ws_pinned_only")
    pin_cb.check().run()

    assert not at.exception
    open_btns = [b for b in at.button if "Open Analysis" in (b.label or "")]
    assert len(open_btns) == 1

