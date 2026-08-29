"""Task status display for async FortyGuard jobs across all workflows."""

import streamlit as st

from frontend.utils.formatting import format_status_label

_STATUS_CONFIG = {
    "idle": ("gray", "○", "No active task."),
    "ready": ("blue", "●", "Ready to submit. Configure parameters and submit to begin."),
    "submitting": ("orange", "◌", "Submitting task to FastAPI backend..."),
    "processing": ("orange", "●", "Task is processing on FortyGuard. Use controls below to poll for completion."),
    "completed": ("green", "✓", "Analysis completed successfully."),
    "succeeded": ("green", "✓", "Analysis completed successfully."),
    "failed": ("red", "✕", "FortyGuard processing failed on the provider side."),
    "error": ("red", "!", "The workflow encountered an error."),
}


def render_task_status(status: str = "Idle", activity_id: str | None = None) -> None:
    """
    Render the current workflow state, badge, and optional activity ID.

    Maintains visual consistency between Heatmap and Heat Intelligence workflows.
    """
    normalized = status.strip().lower()
    color, icon, description = _STATUS_CONFIG.get(
        normalized, ("gray", "●", f"Task status: {status}")
    )
    label = format_status_label(status)

    st.markdown(f"**Task status:** :{color}[{icon} {label}]")
    if activity_id:
        st.caption(f"Activity ID: `{activity_id}` — {description}")
    else:
        st.caption(description)
