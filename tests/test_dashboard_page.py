"""AppTest tests for the Unified Analysis Dashboard page."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_dashboard() -> None:
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.history import clear_session_history

    clear_session_history()
    render_dashboard_page()


def _run_dashboard_with_history() -> None:
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.history import clear_session_history, record_session_analysis

    clear_session_history()
    record_session_analysis(
        "Heatmap",
        "act-dash-1",
        "Downtown NYC",
        "Completed",
        "150 tiles analyzed",
    )
    record_session_analysis(
        "Heat Intelligence",
        "act-dash-2",
        "40.7050, -74.0090",
        "Completed",
        "Report Ready (PDF)",
    )
    render_dashboard_page()


def test_dashboard_renders_without_crashing() -> None:
    at = _app_test(_run_dashboard)
    at.run()

    assert not at.exception
    # Check that both capabilities are described
    markdown_texts = " ".join(m.value for m in at.markdown)
    assert "Heatmap Analysis" in markdown_texts
    assert "Heat Intelligence" in markdown_texts
    assert "FORTYGUARD HEAT INTELLIGENCE" in markdown_texts


def test_dashboard_renders_session_history() -> None:
    at = _app_test(_run_dashboard_with_history)
    at.run()

    assert not at.exception
    markdown_texts = " ".join(m.value for m in at.markdown)
    assert "Downtown NYC" in markdown_texts
    assert "40.7050, -74.0090" in markdown_texts
