"""Tests for the Analysis Workspace filtering, sorting, and AppTest rendering."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest
from frontend.utils.history import (
    clear_session_history,
    filter_session_history,
    find_related_analyses,
    record_session_analysis,
)


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 30)
    return AppTest.from_function(script, **kwargs)


def test_workspace_filtering_and_sorting() -> None:
    clear_session_history()
    record_session_analysis("Heatmap", "act-1", "AOI 1", "Completed", request_params={"date": "2024-07-15"})
    record_session_analysis("Heat Intelligence", "act-2", "Point 1", "Processing", request_params={"date": "2024-07-15"})
    record_session_analysis("Heatmap", "act-3", "AOI 2", "Failed", request_params={"date": "2024-07-16"})

    # Filter by type
    hm_only = filter_session_history(analysis_type="Heatmap")
    assert len(hm_only) == 2
    assert all(e["analysis_type"] == "Heatmap" for e in hm_only)

    hi_only = filter_session_history(analysis_type="Heat Intelligence")
    assert len(hi_only) == 1
    assert hi_only[0]["activity_id"] == "act-2"

    # Filter by status
    completed_only = filter_session_history(status="Completed")
    assert len(completed_only) == 1
    assert completed_only[0]["activity_id"] == "act-1"

    # Sort
    oldest_first = filter_session_history(sort_order="Oldest")
    assert oldest_first[0]["activity_id"] == "act-1"


def test_find_related_analyses() -> None:
    clear_session_history()
    target = {
        "activity_id": "act-target",
        "analysis_type": "Heatmap",
        "label": "Lower Manhattan",
        "request_params": {"date": "2024-07-15"},
    }
    all_entries = [
        target,
        {
            "activity_id": "act-other-1",
            "analysis_type": "Heat Intelligence",
            "label": "Nearby Point",
            "request_params": {"date": "2024-07-15"},
        },
        {
            "activity_id": "act-other-2",
            "analysis_type": "Heatmap",
            "label": "Brooklyn",
            "request_params": {"date": "2024-08-01"},
        },
    ]
    related = find_related_analyses(target, all_entries)
    assert len(related) == 1
    assert related[0]["activity_id"] == "act-other-1"


def _run_workspace_app() -> None:
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.history import clear_session_history, record_session_analysis

    clear_session_history()
    record_session_analysis(
        "Heatmap",
        "act-ws-1",
        "Midtown Manhattan",
        "Completed",
        metrics_summary={"mean_temp": 32.0, "tile_count": 100},
        request_params={"date": "2024-07-15"},
    )
    record_session_analysis(
        "Heatmap",
        "act-ws-2",
        "Downtown Manhattan",
        "Completed",
        metrics_summary={"mean_temp": 31.0, "tile_count": 120},
        request_params={"date": "2024-07-16"},
    )
    render_dashboard_page()


def test_workspace_app_renders_filters_and_comparison() -> None:
    at = _app_test(_run_workspace_app)
    at.run()

    assert not at.exception
    markdown_str = " ".join(m.value for m in at.markdown)
    assert "Analysis Workspace" in markdown_str or "ANALYSIS WORKSPACE" in markdown_str
    assert "Metric-by-Metric Comparison" in markdown_str
    assert "Midtown Manhattan" in markdown_str
    assert "Downtown Manhattan" in markdown_str


def test_get_analysis_by_id_found_and_not_found() -> None:
    from frontend.utils.history import get_analysis_by_id

    clear_session_history()
    record_session_analysis("Heatmap", "act-lookup-1", "Lookup AOI", "Completed")

    entry = get_analysis_by_id("act-lookup-1")
    assert entry is not None
    assert entry["label"] == "Lookup AOI"

    assert get_analysis_by_id("non-existent") is None
    assert get_analysis_by_id("") is None
