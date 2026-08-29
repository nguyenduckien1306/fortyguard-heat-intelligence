"""Unit tests for frontend.utils.colors module."""

from frontend.utils.colors import (
    FALLBACK_RGBA,
    compute_temperature_bounds,
    generate_legend_stops,
    get_temperature_color_scale,
    temperature_to_rgba,
)


def test_get_temperature_color_scale() -> None:
    scale = get_temperature_color_scale()
    assert len(scale) >= 4
    assert scale[0][0] == 0.0
    assert scale[-1][0] == 1.0


def test_compute_temperature_bounds_valid() -> None:
    features = [
        {"properties": {"average_temperature": 25.0}},
        {"properties": {"average_temperature": 35.0}},
        {"properties": {"average_temperature": 30.0}},
    ]
    bounds = compute_temperature_bounds(features)
    assert bounds == (25.0, 35.0)


def test_compute_temperature_bounds_negative_and_mixed() -> None:
    features = [
        {"properties": {"average_temperature": -10.5}},
        {"properties": {"average_temperature": 15.2}},
        {"properties": {"average_temperature": 0.0}},
    ]
    bounds = compute_temperature_bounds(features)
    assert bounds == (-10.5, 15.2)


def test_compute_temperature_bounds_equal_min_max() -> None:
    features = [
        {"properties": {"average_temperature": 28.0}},
        {"properties": {"average_temperature": 28.0}},
    ]
    bounds = compute_temperature_bounds(features)
    assert bounds == (28.0, 28.0)


def test_compute_temperature_bounds_missing_or_non_numeric() -> None:
    features = [
        {"properties": {}},
        {"properties": {"average_temperature": None}},
        {"properties": {"average_temperature": "invalid"}},
        {"properties": {"average_temperature": True}},  # boolean should be ignored
        {},
        "not-a-dict",
    ]
    assert compute_temperature_bounds(features) is None
    assert compute_temperature_bounds([]) is None


def test_temperature_to_rgba_endpoints() -> None:
    min_rgba = temperature_to_rgba(20.0, 20.0, 40.0)
    max_rgba = temperature_to_rgba(40.0, 20.0, 40.0)

    assert len(min_rgba) == 4
    assert len(max_rgba) == 4
    # Min temperature should be blueish (high blue, lower red)
    assert min_rgba[2] > min_rgba[0]
    # Max temperature should be reddish (high red, lower blue)
    assert max_rgba[0] > max_rgba[2]


def test_temperature_to_rgba_midpoint() -> None:
    mid_rgba = temperature_to_rgba(30.0, 20.0, 40.0)
    assert len(mid_rgba) == 4
    assert all(0 <= ch <= 255 for ch in mid_rgba)


def test_temperature_to_rgba_equal_bounds() -> None:
    rgba = temperature_to_rgba(25.0, 25.0, 25.0)
    assert len(rgba) == 4
    assert all(0 <= ch <= 255 for ch in rgba)


def test_temperature_to_rgba_clamping() -> None:
    # Under min
    under_rgba = temperature_to_rgba(10.0, 20.0, 40.0)
    min_rgba = temperature_to_rgba(20.0, 20.0, 40.0)
    assert under_rgba == min_rgba

    # Over max
    over_rgba = temperature_to_rgba(50.0, 20.0, 40.0)
    max_rgba = temperature_to_rgba(40.0, 20.0, 40.0)
    assert over_rgba == max_rgba


def test_temperature_to_rgba_invalid_input() -> None:
    assert temperature_to_rgba(None, 20.0, 40.0) == FALLBACK_RGBA
    assert temperature_to_rgba("bad", 20.0, 40.0) == FALLBACK_RGBA
    assert temperature_to_rgba(True, 20.0, 40.0) == FALLBACK_RGBA


def test_generate_legend_stops() -> None:
    stops = generate_legend_stops(20.0, 40.0, num_stops=5)
    assert len(stops) == 5
    assert stops[0]["value"] == 20.0
    assert stops[-1]["value"] == 40.0
    assert stops[0]["label"] == "20.00 °C"
    assert stops[-1]["label"] == "40.00 °C"
    assert stops[0]["color_hex"].startswith("#")


def test_generate_legend_stops_equal_bounds() -> None:
    stops = generate_legend_stops(30.0, 30.0)
    assert len(stops) == 1
    assert stops[0]["value"] == 30.0
    assert stops[0]["label"] == "30.00 °C"
