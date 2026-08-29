"""AppTest integration tests for frontend UI validation and pre-flight review states."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest
from frontend.utils.history import clear_session_history


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_heat_intelligence_page() -> None:
    from frontend.pages.heat_intelligence import render_heat_intelligence_page
    from frontend.utils.history import clear_session_history
    clear_session_history()
    render_heat_intelligence_page()


def _run_heatmap_page() -> None:
    from frontend.pages.heatmap import render_heatmap_page
    from frontend.utils.history import clear_session_history
    clear_session_history()
    render_heatmap_page()


def test_heat_intelligence_ui_renders_valid_state_by_default() -> None:
    """Default parameters should show ready state and enabled submit button."""
    at = _app_test(_run_heat_intelligence_page)
    at.run()

    assert not at.exception
    success_texts = " ".join(s.value for s in at.success)
    assert "Request Parameters Ready" in success_texts

    # Submit button should be present and enabled
    buttons = [b for b in at.button if "Generate" in (b.label or "")]
    assert len(buttons) >= 1
    assert buttons[0].disabled is False


def test_heat_intelligence_ui_blocks_invalid_latitude() -> None:
    """Setting invalid latitude in number input triggers validation error and disables submit."""
    at = _app_test(_run_heat_intelligence_page)
    at.run()

    # Change latitude to 100.0 (out of bounds)
    lat_input = at.number_input(key="_hi_lat")
    lat_input.set_value(100.0).run()

    assert not at.exception
    # Check that error message is rendered
    markdown_texts = " ".join(m.value for m in at.markdown)
    error_texts = " ".join(e.value for e in at.error)
    caption_texts = " ".join(c.value for c in at.caption)

    combined = f"{markdown_texts} {error_texts} {caption_texts}"
    assert "between -90° and 90°" in combined or "Validation Error" in combined

    # Button must be disabled
    buttons = [b for b in at.button if "Generate" in (b.label or "") or "Fix Validation" in (b.label or "")]
    assert len(buttons) >= 1
    assert buttons[0].disabled is True


def test_heatmap_ui_renders_ready_by_default() -> None:
    """Default polygon should show ready review state."""
    at = _app_test(_run_heatmap_page)
    at.run()

    assert not at.exception
    success_texts = " ".join(s.value for s in at.success)
    assert "Request Parameters Ready" in success_texts
    buttons = [b for b in at.button if "Submit Heatmap" in (b.label or "")]
    assert len(buttons) >= 1
    assert buttons[0].disabled is False


def test_sidebar_polygon_builder_controls_and_points() -> None:
    """Sidebar renders coordinate inputs for polygon points, Date, Time, Granularity, and developer expander."""
    at = _app_test(_run_heatmap_page)
    at.run()

    assert not at.exception
    # Verify developer expander label exists
    expanders = [exp.label for exp in at.sidebar.expander]
    assert any("Developer" in (lbl or "") or "GeoJSON" in (lbl or "") for lbl in expanders)

    # Point coordinate number inputs present in sidebar (4 default points = 4 lat + 4 lon)
    assert len(at.sidebar.number_input) >= 8

    # Add Point button present
    add_btns = [b for b in at.sidebar.button if "Add Point" in (b.label or "")]
    assert len(add_btns) == 1

    # Date and Time inputs present in sidebar
    assert len(at.sidebar.date_input) >= 1
    assert len(at.sidebar.time_input) >= 1


def test_sidebar_polygon_builder_invalid_coordinate_shows_error() -> None:
    """Entering invalid coordinate (e.g. Lat 100) in polygon builder displays error and blocks submit."""
    at = _app_test(_run_heatmap_page)
    at.run()

    # Change first point's latitude to 100.0 (out of bounds)
    lat_input = at.sidebar.number_input(key="_pt_lat_0")
    lat_input.set_value(100.0).run()

    assert not at.exception
    sidebar_captions = " ".join(c.value for c in at.sidebar.caption)
    assert "between -90° and 90°" in sidebar_captions or "latitude" in sidebar_captions.lower()

    # Submit button must be disabled
    buttons = [b for b in at.sidebar.button if "Submit Heatmap" in (b.label or "")]
    assert len(buttons) >= 1
    assert buttons[0].disabled is True


