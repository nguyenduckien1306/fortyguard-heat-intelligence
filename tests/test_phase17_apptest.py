"""Streamlit AppTest suite for Phase 17 Command Center features."""

from __future__ import annotations

import streamlit as st
from streamlit.testing.v1 import AppTest


def _run_phase17_command_center() -> None:
    """Render Command Center seeded with test records for AppTest."""
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import (
        AnalysisRecord,
        add_analysis_record,
        clear_all_analysis_records,
    )
    from frontend.utils.investigation_queue import clear_investigation_queue

    if "_phase17_test_init" not in st.session_state:
        st.session_state["_phase17_test_init"] = True
        clear_all_analysis_records()
        clear_investigation_queue()

        r1 = AnalysisRecord(
            analysis_id="HI-20260827-001",
            activity_id="act_p17_1",
            analysis_type="heat_intelligence",
            created_at="2026-08-27 10:00:00",
            updated_at="2026-08-27 10:00:00",
            location_label="Downtown Central",
            date="2026-08-27",
            time="14:00",
            observed_temperature=32.5,
            status="Completed",
        )
        r2 = AnalysisRecord(
            analysis_id="HI-20260828-001",
            activity_id="act_p17_2",
            analysis_type="heat_intelligence",
            created_at="2026-08-28 11:00:00",
            updated_at="2026-08-28 11:00:00",
            location_label="Downtown Central",
            date="2026-08-28",
            time="14:00",
            observed_temperature=36.0,
            status="Completed",
        )
        add_analysis_record(r1)
        add_analysis_record(r2)

    render_dashboard_page()


class TestPhase17AppTest:
    """Simulate user interactions with Phase 17 Command Center UI."""

    def test_command_center_renders_phase17_sections_with_data(self):
        at = AppTest.from_function(_run_phase17_command_center, default_timeout=15)
        at.run()

        assert not at.exception
        # Verify markdown sections exist
        md_texts = " ".join([m.value for m in at.markdown])
        assert "Operational Posture & Executive Summary" in md_texts
        assert "What Changed Since Previous Observation?" in md_texts
        assert "Cross-Analysis Patterns Detected" in md_texts
        assert "Recommended Operator Workflow Actions" in md_texts

    def test_mark_as_reviewed_button_updates_review_marker(self):
        at = AppTest.from_function(_run_phase17_command_center, default_timeout=15)
        at.run()

        assert not at.exception

        # Find and click "Mark as Reviewed" button
        review_btn = None
        for b in at.button:
            if b.key == "_btn_mark_reviewed":
                review_btn = b
                break

        if review_btn:
            review_btn.click().run()
            assert not at.exception
            assert at.session_state["_user_last_seen_timestamp"] is not None
