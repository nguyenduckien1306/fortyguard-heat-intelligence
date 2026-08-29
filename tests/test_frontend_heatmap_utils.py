"""Tests for pure frontend helpers used to render a completed Heatmap result."""

from frontend.utils.heatmap import compute_aoi_centroid, extract_map_points

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
                        [0.0, 0.0],
                        [10.0, 0.0],
                        [10.0, 10.0],
                        [0.0, 10.0],
                        [0.0, 0.0],
                    ]
                ],
            },
        }
    ],
}


def test_extract_map_points_from_plain_list() -> None:
    points = extract_map_points([{"lon": 1.0, "lat": 2.0, "value": 30.0}])

    assert points == [{"lon": 1.0, "lat": 2.0, "value": 30.0}]


def test_extract_map_points_from_wrapped_dict_variants() -> None:
    for key in ("points", "features", "data"):
        points = extract_map_points({key: [{"lon": 1.0, "lat": 2.0}]})
        assert points == [{"lon": 1.0, "lat": 2.0, "value": None}]


def test_extract_map_points_accepts_key_spelling_variants() -> None:
    points = extract_map_points([{"lng": 5.0, "latitude": 6.0}])

    assert points == [{"lon": 5.0, "lat": 6.0, "value": None}]


def test_extract_map_points_skips_entries_missing_coordinates() -> None:
    points = extract_map_points([{"lon": 1.0}, {"lat": 2.0}, {"foo": "bar"}])

    assert points == []


def test_extract_map_points_returns_empty_for_unrecognized_shapes() -> None:
    assert extract_map_points("not-a-list-or-dict") == []
    assert extract_map_points(None) == []
    assert extract_map_points({"unrelated": "structure"}) == []


def test_compute_aoi_centroid_of_square_polygon() -> None:
    centroid = compute_aoi_centroid(_SAMPLE_AOI)

    assert centroid == (5.0, 5.0)


def test_compute_aoi_centroid_returns_none_for_missing_features() -> None:
    assert compute_aoi_centroid({"type": "FeatureCollection"}) is None


def test_build_temperature_colored_geojson_adds_fill_color_and_tooltip_strings() -> None:
    from frontend.utils.heatmap import build_temperature_colored_geojson

    raw_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tile_id": 101,
                    "average_temperature": 30.5,
                    "min_temperature": 29.0,
                    "max_temperature": 32.0,
                },
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            },
            {
                "type": "Feature",
                "properties": {
                    "tile_id": 102,
                    "average_temperature": 35.5,
                    "min_temperature": 34.0,
                    "max_temperature": 36.0,
                },
                "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]]},
            },
        ],
    }

    result = build_temperature_colored_geojson(raw_geojson)
    features = result["features"]
    assert len(features) == 2

    f1_props = features[0]["properties"]
    assert len(f1_props["fill_color"]) == 4
    assert f1_props["average_temperature_str"] == "30.50 °C"
    assert f1_props["min_temperature_str"] == "29.00 °C"
    assert f1_props["max_temperature_str"] == "32.00 °C"
    assert f1_props["tile_id_str"] == "101"

    # Feature 2 should have a hotter color (higher red) than feature 1
    f2_props = features[1]["properties"]
    assert f2_props["fill_color"][0] >= f1_props["fill_color"][0]


def test_build_temperature_colored_geojson_handles_missing_and_malformed() -> None:
    from frontend.utils.colors import FALLBACK_RGBA
    from frontend.utils.heatmap import build_temperature_colored_geojson

    raw_geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": []}},
            {"type": "Feature", "properties": {"average_temperature": None}},
            "malformed-feature",
        ],
    }

    result = build_temperature_colored_geojson(raw_geojson)
    assert len(result["features"]) == 2
    assert result["features"][0]["properties"]["fill_color"] == FALLBACK_RGBA
    assert result["features"][0]["properties"]["average_temperature_str"] == "N/A"
    assert result["features"][0]["properties"]["tile_id_str"] == "N/A"


def test_build_temperature_colored_geojson_handles_empty_collection() -> None:
    from frontend.utils.heatmap import build_temperature_colored_geojson

    assert build_temperature_colored_geojson({}) == {"type": "FeatureCollection", "features": []}
    assert build_temperature_colored_geojson({"features": "not-a-list"}) == {"type": "FeatureCollection", "features": []}

