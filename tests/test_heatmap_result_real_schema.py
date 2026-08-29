"""
Regression tests against the REAL, sanitized Phase 4 FortyGuard Completed
result (see tests/fixtures/heatmap_results_real.py). These prove the adapter
and renderers actually work against observed reality, not just guesses.
"""

from streamlit.testing.v1 import AppTest

from backend.models.heatmap_result import parse_heatmap_result
from frontend.utils.heatmap import build_temperature_colored_geojson, is_polygon_feature_collection
from tests.fixtures.heatmap_results_real import REAL_COMPLETED_RESULT_SAMPLE


def _app_test(script, **kwargs):
    # See tests/test_heatmap_result_components.py for why this timeout is
    # generous: it's absorbing cold pandas/pydeck import time, not slow test logic.
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def test_real_result_parses_without_error() -> None:
    parsed = parse_heatmap_result(REAL_COMPLETED_RESULT_SAMPLE)

    assert parsed is not None
    assert parsed.map_data == REAL_COMPLETED_RESULT_SAMPLE["map_data"]
    assert parsed.metadata is None  # confirmed: the real response has no metadata key


def test_real_result_statistics_come_from_stats_data_not_guessed_keys() -> None:
    parsed = parse_heatmap_result(REAL_COMPLETED_RESULT_SAMPLE)

    assert parsed is not None
    assert parsed.statistics == REAL_COMPLETED_RESULT_SAMPLE["stats_data"]
    assert isinstance(parsed.statistics, dict)
    assert parsed.statistics["temperature_stats"]["mean"] == 32.255170666666665


def test_real_map_data_is_recognized_as_polygon_feature_collection() -> None:
    assert is_polygon_feature_collection(REAL_COMPLETED_RESULT_SAMPLE["map_data"]) is True


def test_real_map_data_is_not_confused_with_a_point_list() -> None:
    from frontend.utils.heatmap import extract_map_points

    # The real shape has no top-level lon/lat per item, so naive point
    # extraction correctly finds nothing -- the tile-aware path must be
    # tried first by the map renderer, not this fallback.
    assert extract_map_points(REAL_COMPLETED_RESULT_SAMPLE["map_data"]) == []


def test_build_temperature_colored_geojson_colors_every_tile() -> None:
    colored = build_temperature_colored_geojson(REAL_COMPLETED_RESULT_SAMPLE["map_data"])

    assert len(colored["features"]) == len(REAL_COMPLETED_RESULT_SAMPLE["map_data"]["features"])
    for feature in colored["features"]:
        fill_color = feature["properties"]["fill_color"]
        assert len(fill_color) == 4
        assert all(0 <= channel <= 255 for channel in fill_color)


def _run_render_heatmap_result(polygon_aoi, result):
    from frontend.components.heatmap_result import render_heatmap_result

    render_heatmap_result(polygon_aoi, result)


def test_render_heatmap_result_handles_the_real_fixture_without_crashing() -> None:
    aoi = {
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

    at = _app_test(
        _run_render_heatmap_result, args=(aoi, REAL_COMPLETED_RESULT_SAMPLE)
    )
    at.run()

    assert not at.exception
    # 4 temperature_stats scalar cards + 5 overall_temperature_distribution summary cards -> 9 metrics
    assert len(at.metric) == 9
    labels = {metric.label for metric in at.metric}
    assert {
        "Temperature Stats → Minimum",
        "Temperature Stats → Maximum",
        "Temperature Stats → Mean",
        "Temperature Stats → Standard Deviation",
    }.issubset(labels)
    assert {"Point 1", "Point 2", "Point 3", "Point 4", "Point 5"}.issubset(labels)

