"""Result rendering component for FortyGuard Heat Intelligence."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from backend.models.heat_intelligence_result import parse_heat_intelligence_result
from frontend.services.api import BackendAPIClient, BackendAPIError
from frontend.utils.export import (
    generate_analysis_export_json,
    generate_analysis_export_text,
    sanitize_raw_result_for_inspection,
)
from frontend.utils.formatting import format_result_value, humanize_key


def render_heat_intelligence_result(
    request_params: Mapping[str, Any] | None,
    result: dict[str, Any] | None,
    activity_id: str | None = None,
    api_client: BackendAPIClient | None = None,
) -> None:
    """
    Render a completed Heat Intelligence task result.

    Provides a polished report summary, a secure backend-proxied PDF download,
    local summary export, and sanitized developer inspection tools. The signed S3 URL
    is never exposed to the frontend.
    """
    if not result:
        st.info("This task completed with no result payload.")
        return

    parsed = parse_heat_intelligence_result(result)
    if parsed is None:
        st.info("This task completed with no result payload.")
        return

    st.subheader("📊 Heat Intelligence Report")

    # ── Request summary card ──
    if request_params:
        st.markdown("---")
        st.markdown("##### 📋 Analysis Summary")
        c1, c2, c3 = st.columns(3)
        with c1:
            lat = request_params.get("latitude", "—")
            lon = request_params.get("longitude", "—")
            st.metric("📍 Location", f"{lat}, {lon}")
        with c2:
            temp = request_params.get("temperature", "—")
            st.metric("🌡️ Observed Temp", f"{temp} °C")
        with c3:
            date = request_params.get("date", "—")
            st.metric("📅 Date", str(date))

        analysis = request_params.get("analysis")
        if analysis and isinstance(analysis, list):
            emoji_map = {
                "geographic": "🌍",
                "environmental": "🌿",
                "urban": "🏙️",
                "events": "📈",
                "anthropogenic": "🏭",
            }
            tags = "  ".join(
                f"{emoji_map.get(a, '📊')} **{a.title()}**" for a in analysis
            )
            st.markdown(f"**Analysis dimensions:** {tags}")

    # ── Report download center ──
    if parsed.download_link:
        st.success(
            "✅ Your multi-dimensional Heat Intelligence Report has been generated successfully!"
        )

        st.markdown(
            """
            The Heat Intelligence Report provides comprehensive spatial and temporal analysis across:
            - 🌍 **Geographic & Urban Topology**
            - 🌿 **Environmental Parameters & Microclimates**
            - 🏙️ **Urban Infrastructure & Pavement Heat Absorption**
            - 📈 **Anthropogenic & Event Thermal Profiles**
            """
        )

        # Secure PDF download through backend proxy
        if activity_id:
            _render_pdf_download(activity_id, api_client)
        else:
            st.caption(
                "⚠️ Download is unavailable — no activity ID in session state."
            )
    else:
        st.info("Report generation completed. Please inspect the payload below.")

    # ── Extracted structured data ──
    if parsed.data:
        st.divider()
        st.subheader("Extracted Metrics")
        for k, v in parsed.data.items():
            if isinstance(v, (int, float, str, bool)):
                st.metric(label=humanize_key(k), value=format_result_value(v))
            elif isinstance(v, (dict, list)):
                with st.expander(f"Section: {humanize_key(k)}"):
                    st.json(v)

    st.divider()

    # ── Export Local Summary ──
    _render_export_section(activity_id=activity_id, request_params=request_params, parsed=parsed)

    st.divider()

    # ── Developer raw inspection (sanitized) ──
    with st.expander("🔍 Developer / Raw Provider Response", expanded=False):
        st.json(sanitize_raw_result_for_inspection(parsed.raw))


def _render_pdf_download(
    activity_id: str,
    api_client: BackendAPIClient | None = None,
) -> None:
    """Download PDF bytes via the backend proxy and present a download button."""
    download_key = f"_hi_pdf_{activity_id}"

    # Cache the download in session state to avoid repeat fetches across reruns
    if download_key not in st.session_state:
        try:
            if api_client is not None:
                pdf_bytes = api_client.download_heat_intelligence_report(activity_id)
            else:
                with BackendAPIClient() as client:
                    pdf_bytes = client.download_heat_intelligence_report(activity_id)
            
            # Only cache non-empty valid bytes
            if pdf_bytes and isinstance(pdf_bytes, bytes):
                st.session_state[download_key] = pdf_bytes
            else:
                st.session_state.pop(download_key, None)
        except BackendAPIError as exc:
            st.session_state.pop(download_key, None)
            st.warning(
                f"⚠️ Unable to download the report: {exc}. "
                "The signed link may have expired — please re-submit the analysis."
            )
            return
        except Exception:
            st.session_state.pop(download_key, None)
            st.warning(
                "⚠️ An unexpected error occurred while downloading the report."
            )
            return

    pdf_bytes = st.session_state.get(download_key)
    if pdf_bytes and isinstance(pdf_bytes, bytes):
        col_dl, col_info = st.columns([2, 3])
        with col_dl:
            st.download_button(
                label="📥 Download Report (PDF)",
                data=pdf_bytes,
                file_name=f"heat_intelligence_report_{activity_id}.pdf",
                mime="application/pdf",
                type="primary",
                key=f"_hi_dl_btn_{activity_id}",
            )
        with col_info:
            size_kb = len(pdf_bytes) / 1024
            st.caption(f"📄 Report size: {size_kb:.1f} KB • Proxied via backend")
    else:
        st.warning("⚠️ The downloaded report is empty. Please re-submit the analysis.")


def _render_export_section(
    activity_id: str | None,
    request_params: Mapping[str, Any] | None,
    parsed: Any,
) -> None:
    """Render export buttons for local summary reports."""
    st.subheader("💾 Export Local Analysis Summary")
    st.caption("Download a locally generated structured summary of this Heat Intelligence request.")

    entry_data = {
        "analysis_type": "Heat Intelligence",
        "activity_id": activity_id or "unassigned",
        "status": "Completed",
        "label": f"Coordinates: {request_params.get('latitude', '')}, {request_params.get('longitude', '')}" if request_params else "Heat Intelligence",
        "created_at": "Current Session",
        "updated_at": "Current Session",
        "request_params": request_params,
        "metrics_summary": parsed.data if hasattr(parsed, "data") else {},
    }

    json_str = generate_analysis_export_json(entry_data)
    text_str = generate_analysis_export_text(entry_data)

    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        st.download_button(
            label="📥 Download Summary (JSON)",
            data=json_str,
            file_name=f"heat_intelligence_summary_{activity_id or 'local'}.json",
            mime="application/json",
            key=f"_dl_hi_json_{activity_id or 'local'}",
        )
    with c2:
        st.download_button(
            label="📄 Download Summary (TXT)",
            data=text_str,
            file_name=f"heat_intelligence_summary_{activity_id or 'local'}.txt",
            mime="text/plain",
            key=f"_dl_hi_txt_{activity_id or 'local'}",
        )
