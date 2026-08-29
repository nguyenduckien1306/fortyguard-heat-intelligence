"""Map visualization components for heatmap rendering."""

from __future__ import annotations

from typing import Any, Mapping

import pydeck as pdk
import streamlit as st

from frontend.utils.colors import compute_temperature_bounds, generate_legend_stops
from frontend.utils.heatmap import (
    build_temperature_colored_geojson,
    compute_aoi_centroid,
    extract_map_points,
    is_polygon_feature_collection,
)

_DEFAULT_VIEW_LAT = 40.7128
_DEFAULT_VIEW_LON = -74.0060


def render_temperature_legend(
    min_val: float,
    max_val: float,
    metric_label: str = "Temperature Range",
) -> None:
    """Render a visual continuous temperature gradient legend with numeric bounds and °C."""
    stops = generate_legend_stops(min_val, max_val, num_stops=5)
    if not stops:
        return

    if min_val == max_val:
        st.markdown(
            f"""
            <div style="margin-top: 8px; padding: 8px 12px; background: rgba(120, 120, 120, 0.1); border-radius: 6px;">
                <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px;">{metric_label} Scale</div>
                <div style="font-size: 13px;">Uniform Temperature: <strong>{min_val:.2f} °C</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    labels_html = "".join(
        f"<span>{stop['label']}</span>" for stop in stops
    )

    st.markdown(
        f"""
        <div style="margin-top: 8px; padding: 10px 14px; background: rgba(120, 120, 120, 0.08); border-radius: 6px; border: 1px solid rgba(120, 120, 120, 0.2);">
            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; margin-bottom: 6px;">
                <span>❄️ Cooler</span>
                <span>{metric_label} (°C)</span>
                <span>🔥 Hotter</span>
            </div>
            <div style="height: 14px; border-radius: 7px; background: linear-gradient(to right, rgb(40, 120, 240), rgb(60, 200, 180), rgb(245, 190, 40), rgb(235, 50, 35)); box-shadow: inset 0 1px 2px rgba(0,0,0,0.2);"></div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 5px; opacity: 0.85;">
                {labels_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_map_placeholder(title: str = "Heatmap") -> None:
    """
    Prepare a reusable map rendering area.
    """
    st.subheader(title)
    st.info(
        "Map visualization placeholder. "
        "Interactive AOI and heatmap layers will be displayed once an analysis is submitted."
    )
    st.map(
        data={"lat": [40.7128], "lon": [-74.0060]},
        zoom=11,
        width="stretch",
    )


def render_heatmap_result_map(
    polygon_aoi: Mapping[str, Any] | None,
    map_data: Any | None,
    property_key: str = "average_temperature",
) -> None:
    """
    Render the AOI polygon and temperature-colored GeoJSON polygon tile layer.

    Supports custom property color mapping (average_temperature, min_temperature, max_temperature)
    with dynamic recalculation of legend bounds and rich tooltips.
    """
    st.subheader("Map Visualization")

    layers: list[pdk.Layer] = []
    if polygon_aoi is not None:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=dict(polygon_aoi),
                stroked=True,
                filled=False,
                get_line_color=[255, 140, 0],
                line_width_min_pixels=2,
            )
        )

    tooltip: dict[str, Any] | None = None
    recognized_map_data = False
    temp_bounds: tuple[float, float] | None = None

    metric_name_map = {
        "average_temperature": "Average Temperature",
        "min_temperature": "Minimum Temperature",
        "max_temperature": "Maximum Temperature",
    }
    metric_label = metric_name_map.get(property_key, "Temperature")

    if isinstance(map_data, Mapping) and is_polygon_feature_collection(map_data):
        recognized_map_data = True
        features = map_data.get("features", [])
        temp_bounds = compute_temperature_bounds(features, property_key=property_key)
        colored = build_temperature_colored_geojson(map_data, property_key=property_key)
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=colored,
                stroked=True,
                filled=True,
                get_fill_color="properties.fill_color",
                get_line_color=[255, 255, 255, 60],
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            )
        )
        tooltip = {
            "html": (
                f"<b>Tile ID:</b> {{properties.tile_id_str}}<br/>"
                f"<span style='color: #F5BE28;'><b>● {metric_label}:</b> {{properties.{property_key}_str}}</span><br/>"
                f"<hr style='margin: 4px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.2);'/>"
                "<b>Avg:</b> {properties.average_temperature_str} | "
                "<b>Min:</b> {properties.min_temperature_str} | "
                "<b>Max:</b> {properties.max_temperature_str}"
            ),
            "style": {
                "backgroundColor": "rgba(20, 25, 35, 0.95)",
                "color": "white",
                "fontSize": "12px",
                "padding": "8px 12px",
                "borderRadius": "6px",
            },
        }
    else:
        points = extract_map_points(map_data)
        if points:
            recognized_map_data = True
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=points,
                    get_position="[lon, lat]",
                    get_radius=40,
                    get_fill_color=[220, 60, 20, 180],
                    pickable=True,
                )
            )
            tooltip = {"html": "<b>Value:</b> {value}"}

    centroid = compute_aoi_centroid(polygon_aoi) if polygon_aoi is not None else None
    view_lat, view_lon = centroid if centroid is not None else (_DEFAULT_VIEW_LAT, _DEFAULT_VIEW_LON)

    if layers:
        st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(
                    latitude=view_lat,
                    longitude=view_lon,
                    zoom=13,
                ),
                tooltip=tooltip,
            )
        )
        if temp_bounds is not None:
            render_temperature_legend(temp_bounds[0], temp_bounds[1], metric_label=metric_label)
    else:
        st.info("No map data available to render for this result.")

    if map_data is not None and not recognized_map_data:
        with st.expander("Raw map data (unrecognized structure)", expanded=False):
            st.json(map_data)
