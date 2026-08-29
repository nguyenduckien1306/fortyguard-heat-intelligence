"""Pure, deterministic color mapping and legend utilities for temperature visualization.

Independent of Streamlit and external APIs to remain fully unit-testable.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Multi-stop thermal color scale:
# 0.0 (Cool Cyan/Blue) -> 0.33 (Teal/Green) -> 0.66 (Amber/Yellow) -> 1.0 (Vibrant Red)
THERMAL_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (40, 120, 240)),    # Cool Blue
    (0.33, (60, 200, 180)),   # Teal / Cyan
    (0.66, (245, 190, 40)),   # Amber / Yellow
    (1.0, (235, 50, 35)),     # Deep Red
]

DEFAULT_ALPHA: int = 180
FALLBACK_RGBA: list[int] = [120, 120, 120, 140]  # Neutral gray for missing/invalid data


def get_temperature_color_scale() -> list[tuple[float, tuple[int, int, int]]]:
    """Return the multi-stop thermal color palette."""
    return list(THERMAL_STOPS)


def compute_temperature_bounds(
    features: Sequence[Any],
    property_key: str = "average_temperature",
) -> tuple[float, float] | None:
    """
    Extract numeric min and max temperatures from a collection of GeoJSON features.

    Returns ``(min_val, max_val)`` or ``None`` if no valid numeric values are found.
    Handles negative numbers, equal min/max, and ignores non-numeric or missing properties.
    """
    values: list[float] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        props = feature.get("properties")
        if not isinstance(props, Mapping):
            continue
        val = props.get(property_key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            values.append(float(val))

    if not values:
        return None

    return min(values), max(values)


def temperature_to_rgba(
    value: float | None,
    min_val: float,
    max_val: float,
    alpha: int = DEFAULT_ALPHA,
) -> list[int]:
    """
    Map a temperature value to an RGBA color list [R, G, B, A] scaled between min_val and max_val.

    Handles:
    - ``None`` or non-numeric: returns neutral fallback RGBA.
    - ``min_val == max_val``: returns midpoint color.
    - Values out of bounds: clamped safely to 0.0..1.0.
    """
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return list(FALLBACK_RGBA)

    val = float(value)
    if max_val <= min_val:
        ratio = 0.5
    else:
        ratio = (val - min_val) / (max_val - min_val)

    ratio = max(0.0, min(1.0, ratio))

    # Interpolate along multi-stop palette
    stops = THERMAL_STOPS
    for i in range(len(stops) - 1):
        pos0, rgb0 = stops[i]
        pos1, rgb1 = stops[i + 1]
        if pos0 <= ratio <= pos1:
            segment_span = pos1 - pos0
            segment_ratio = (ratio - pos0) / segment_span if segment_span > 0 else 0.0
            r = int(rgb0[0] + segment_ratio * (rgb1[0] - rgb0[0]))
            g = int(rgb0[1] + segment_ratio * (rgb1[1] - rgb0[1]))
            b = int(rgb0[2] + segment_ratio * (rgb1[2] - rgb0[2]))
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            a = max(0, min(255, alpha))
            return [r, g, b, a]

    # Boundary fallback
    last_rgb = stops[-1][1]
    return [last_rgb[0], last_rgb[1], last_rgb[2], max(0, min(255, alpha))]


def generate_legend_stops(
    min_val: float,
    max_val: float,
    num_stops: int = 5,
) -> list[dict[str, Any]]:
    """
    Generate evenly spaced temperature markers and corresponding RGBA/hex colors for legend display.

    Returns a list of dicts: ``[{"value": float, "color_rgba": list[int], "color_hex": str, "label": str}]``.
    """
    if num_stops < 2:
        num_stops = 2

    stops: list[dict[str, Any]] = []
    if max_val == min_val:
        rgba = temperature_to_rgba(min_val, min_val, max_val)
        hex_color = f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
        return [
            {
                "value": min_val,
                "color_rgba": rgba,
                "color_hex": hex_color,
                "label": f"{min_val:.2f} °C",
            }
        ]

    step = (max_val - min_val) / (num_stops - 1)
    for i in range(num_stops):
        val = min_val + i * step
        rgba = temperature_to_rgba(val, min_val, max_val)
        hex_color = f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
        stops.append(
            {
                "value": val,
                "color_rgba": rgba,
                "color_hex": hex_color,
                "label": f"{val:.2f} °C",
            }
        )

    return stops
