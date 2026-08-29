"""Smoke tests for the Phase 3 result-rendering components via Streamlit AppTest."""

from streamlit.testing.v1 import AppTest


def _app_test(script, **kwargs):
    # A cold interpreter's first pandas/pydeck import can take a few
    # seconds; the library's 3s default is too tight for that, independent
    # of whether the script under test is actually slow.
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_render_heatmap_result(polygon_aoi, result):
    from frontend.components.heatmap_result import render_heatmap_result

    render_heatmap_result(polygon_aoi, result)


def _run_render_result_statistics(statistics):
    from frontend.components.metrics import render_result_statistics

    render_result_statistics(statistics)


_SAMPLE_AOI = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.0170, 40.7050],
                        [-74.0030, 40.7050],
                        [-74.0030, 40.7180],
                        [-74.0170, 40.7180],
                        [-74.0170, 40.7050],
                    ]
                ],
            },
        }
    ],
}


def _fixture(name: str) -> dict:
    from backend.mock_data.heatmap_results import ALL_MOCK_RESULT_FIXTURES

    return ALL_MOCK_RESULT_FIXTURES[name]


def test_render_heatmap_result_handles_no_result() -> None:
    at = _app_test(_run_render_heatmap_result, args=(_SAMPLE_AOI, None))
    at.run()

    assert not at.exception
    assert any("no result payload" in info.value.lower() for info in at.info)


def test_render_heatmap_result_full_fixture_renders_without_crashing() -> None:
    at = _app_test(
        _run_render_heatmap_result, args=(_SAMPLE_AOI, _fixture("Full result"))
    )
    at.run()

    assert not at.exception
    assert len(at.metric) == 4  # avg_temp_c, max_temp_c, min_temp_c, data_points


def test_render_heatmap_result_missing_map_data_still_renders_statistics() -> None:
    at = _app_test(
        _run_render_heatmap_result, args=(_SAMPLE_AOI, _fixture("Missing map data"))
    )
    at.run()

    assert not at.exception
    # AOI outline still renders even without map_data; no "unrecognized structure"
    # expander should appear since map_data is simply absent, not malformed.
    assert not any("Raw map data" in expander.label for expander in at.expander)
    assert len(at.metric) == 2


def test_render_heatmap_result_missing_statistics_shows_notice_not_fabricated_metrics() -> None:
    at = _app_test(
        _run_render_heatmap_result, args=(_SAMPLE_AOI, _fixture("Missing statistics"))
    )
    at.run()

    assert not at.exception
    assert len(at.metric) == 0
    assert any("no statistics" in caption.value.lower() for caption in at.caption)


def test_render_heatmap_result_empty_result_is_safe() -> None:
    at = _app_test(
        _run_render_heatmap_result, args=(_SAMPLE_AOI, _fixture("Empty result"))
    )
    at.run()

    assert not at.exception
    assert len(at.metric) == 0


def test_render_heatmap_result_malformed_result_does_not_crash() -> None:
    at = _app_test(
        _run_render_heatmap_result, args=(_SAMPLE_AOI, _fixture("Malformed result"))
    )
    at.run()

    assert not at.exception
    assert len(at.metric) == 0


def test_render_result_statistics_absent_shows_notice() -> None:
    at = _app_test(_run_render_result_statistics, args=(None,))
    at.run()

    assert not at.exception
    assert len(at.metric) == 0
    assert any("no statistics" in caption.value.lower() for caption in at.caption)


def test_render_result_statistics_never_fabricates_unknown_fields() -> None:
    at = _app_test(
        _run_render_result_statistics, args=({"data_points": 3},)
    )
    at.run()

    assert not at.exception
    labels = {metric.label for metric in at.metric}
    assert labels == {"Data Points"}
    assert "Temperature" not in labels
    assert "Heat Risk" not in labels
    assert "Hotspots" not in labels


def test_render_result_statistics_handles_mismatched_distribution_axes() -> None:
    mismatched_stats = {
        "temperature_stats": {"minimum": 20.0, "maximum": 30.0, "mean": 25.0, "standard_deviation": 2.5},
        "normal_temperature_distribution": {
            "x_axis": [20.0, 25.0, 30.0],
            "y_axis": [0.1, 0.5],  # Mismatched length
        },
        "temperature_frequency": {
            "x_axis": [20.0, 30.0],
            "y_axis": [10],  # Mismatched length
        },
    }
    at = _app_test(_run_render_result_statistics, args=(mismatched_stats,))
    at.run()

    assert not at.exception
    # The 4 temperature stats scalar metrics still render safely
    assert len(at.metric) == 4
    assert any("mismatched axis data" in warning.value.lower() for warning in at.warning)


def test_render_result_statistics_partial_data_renders_available_sections() -> None:
    partial_stats = {
        "temperature_stats": {"minimum": 15.0, "maximum": 25.0, "mean": 20.0, "standard_deviation": 1.2},
    }
    at = _app_test(_run_render_result_statistics, args=(partial_stats,))
    at.run()

    assert not at.exception
    assert len(at.metric) == 4
    # No warning or error
    assert len(at.warning) == 0


def test_render_result_statistics_5_point_summary_renders_metrics() -> None:
    stats_with_5point = {
        "overall_temperature_distribution": [20.0, 22.5, 25.0, 27.5, 30.0],
    }
    at = _app_test(_run_render_result_statistics, args=(stats_with_5point,))
    at.run()

    assert not at.exception
    assert len(at.metric) == 5
    assert {m.label for m in at.metric} == {"Point 1", "Point 2", "Point 3", "Point 4", "Point 5"}

