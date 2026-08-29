"""Reusable formatting helpers for the Streamlit frontend."""

from typing import Any


def format_metric(value: float | int | None, unit: str = "") -> str:
    """Format a numeric metric for display, or '--' when unavailable."""
    if value is None:
        return "--"
    formatted = f"{value:.1f}" if isinstance(value, float) else str(value)
    return f"{formatted}{unit}" if unit else formatted


def format_status_label(status: str) -> str:
    """Normalize task status labels for display."""
    return status.strip().title() if status else "Idle"


def humanize_key(key: str) -> str:
    """Turn a snake_case result key into a display label, e.g. 'avg_temp_c' -> 'Avg Temp C'."""
    return key.replace("_", " ").strip().title() or key


def format_result_value(value: Any) -> str:
    """Format an arbitrary result value for display, or '--' when unavailable."""
    if value is None:
        return "--"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (int, str)):
        return str(value)
    return repr(value)
