"""Reusable metric card components."""

from typing import Any, Mapping

import streamlit as st

from frontend.utils.formatting import format_metric, format_result_value, humanize_key

_MAX_INLINE_LIST_VALUES = 12


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (int, float, str, bool))


def _is_numeric_list(values: list[Any]) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _is_xy_axis_series(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    x_axis, y_axis = value.get("x_axis"), value.get("y_axis")
    if not isinstance(x_axis, list) or not isinstance(y_axis, list):
        return False
    if not x_axis or len(x_axis) != len(y_axis):
        return False
    return _is_numeric_list(x_axis) and _is_numeric_list(y_axis)


def render_result_statistics(statistics: dict[str, Any] | None) -> None:
    """
    Render structured statistics and charts for a completed Heatmap result.

    Displays:
    - Primary temperature stats (Minimum, Maximum, Mean, Standard Deviation)
    - 5-point overall temperature distribution summary
    - Validated normal temperature distribution curve
    - Validated temperature frequency bar chart

    Degrades gracefully if any subsection is missing or malformed without crashing.
    """
    st.subheader("Statistics")

    if not statistics:
        st.caption("No statistics were returned for this result.")
        return

    # 1. Primary temperature stats and other scalar metrics
    scalar_items: list[tuple[str, Any]] = []
    list_items: list[tuple[str, list[Any]]] = []
    normal_dist: dict[str, Any] | None = None
    freq_dist: dict[str, Any] | None = None
    other_series: list[tuple[str, list[float], list[float]]] = []

    for key, value in statistics.items():
        label = humanize_key(key)

        if key == "normal_temperature_distribution" and isinstance(value, Mapping):
            normal_dist = value
        elif key == "temperature_frequency" and isinstance(value, Mapping):
            freq_dist = value
        elif _is_xy_axis_series(value):
            other_series.append((label, value["x_axis"], value["y_axis"]))
        elif isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                nested_label = f"{label} → {humanize_key(nested_key)}"
                if _is_scalar(nested_value):
                    scalar_items.append((nested_label, nested_value))
                elif isinstance(nested_value, list):
                    list_items.append((nested_label, nested_value))
        elif isinstance(value, list):
            list_items.append((label, value))
        else:
            scalar_items.append((label, value))

    if scalar_items:
        columns = st.columns(min(len(scalar_items), 4))
        for index, (label, value) in enumerate(scalar_items):
            with columns[index % len(columns)]:
                val_str = format_result_value(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    val_str = f"{value:.2f} °C" if isinstance(value, float) else f"{value}"
                st.metric(label=label, value=val_str)

    # 2. Overall distribution / list summaries
    for label, values in list_items:
        if len(values) == 5 and _is_numeric_list(values):
            st.markdown(f"**{label} (5-Point Distribution Summary)**")
            cols = st.columns(5)
            for idx, val in enumerate(values):
                with cols[idx]:
                    st.metric(label=f"Point {idx + 1}", value=f"{float(val):.2f} °C")
        elif len(values) <= _MAX_INLINE_LIST_VALUES and all(_is_scalar(v) for v in values):
            st.caption(f"{label}: " + ", ".join(format_result_value(v) for v in values))
        else:
            st.caption(f"{label}: {len(values)} values (see raw result for detail).")

    # 3. Normal temperature distribution chart
    if normal_dist is not None:
        x_axis = normal_dist.get("x_axis")
        y_axis = normal_dist.get("y_axis")
        if (
            isinstance(x_axis, list)
            and isinstance(y_axis, list)
            and len(x_axis) == len(y_axis)
            and len(x_axis) > 0
            and _is_numeric_list(x_axis)
            and _is_numeric_list(y_axis)
        ):
            import pandas as pd

            st.markdown("**Normal Temperature Distribution** *(Temperature °C vs Density)*")
            df_norm = pd.DataFrame({"Density": y_axis}, index=x_axis)
            st.line_chart(df_norm, width="stretch")
        else:
            st.warning("Normal temperature distribution contains missing or mismatched axis data.")

    # 4. Temperature frequency chart
    if freq_dist is not None:
        x_axis = freq_dist.get("x_axis")
        y_axis = freq_dist.get("y_axis")
        if (
            isinstance(x_axis, list)
            and isinstance(y_axis, list)
            and len(x_axis) == len(y_axis)
            and len(x_axis) > 0
            and _is_numeric_list(x_axis)
            and _is_numeric_list(y_axis)
        ):
            import pandas as pd

            st.markdown("**Temperature Frequency** *(Temperature °C vs Bin Count)*")
            # Format x-axis temperature labels nicely
            x_labels = [f"{float(x):.1f} °C" for x in x_axis]
            df_freq = pd.DataFrame({"Count": y_axis}, index=x_labels)
            st.bar_chart(df_freq, width="stretch")
        else:
            st.warning("Temperature frequency contains missing or mismatched axis data.")

    # 5. Other generic series if present
    if other_series:
        import pandas as pd

        for label, x_axis, y_axis in other_series:
            st.caption(label)
            st.line_chart(pd.DataFrame({"value": y_axis}, index=x_axis), width="stretch")


def render_metric_cards(
    temperature: float | None = None,
    heat_risk: float | None = None,
    hotspots: int | None = None,
) -> None:
    """Render temperature, heat-risk, and hotspot metric cards."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(label="Temperature", value=format_metric(temperature, "°C"))

    with col2:
        st.metric(label="Heat Risk", value=format_metric(heat_risk))

    with col3:
        st.metric(label="Hotspots", value=format_metric(hotspots))
