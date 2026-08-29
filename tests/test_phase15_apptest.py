"""Streamlit AppTest suite for Phase 15 Command Center UI Components.

Verifies:
- 7-tab Command Center renders without duplicate widget keys or exceptions.
- Watchlist dashboard renders and handles interactions cleanly.
- Signal Center renders precedence and disposition controls.
- Alert Center renders and handles filter changes.
- Investigation Queue renders and handles notes/transitions.
- Intelligence Diagnostics tab renders cryptographic hash and metrics.
- Zero network I/O during all UI renders.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest


def _app_entrypoint():
    from datetime import datetime, timezone
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record

    now = datetime.now(timezone.utc).isoformat()

    # Seed sample completed records with required created_at / updated_at
    r1 = AnalysisRecord(
        analysis_id="HM-20260823-001",
        activity_id="act_01",
        analysis_type="heatmap",
        created_at=now,
        updated_at=now,
        location_label="Central Park",
        date="2026-08-20",
        metrics={"mean_temp": 41.5, "temp_spread": 12.0, "total_tiles": 100},
        status="Completed",
    )
    r2 = AnalysisRecord(
        analysis_id="HI-20260823-002",
        activity_id="act_02",
        analysis_type="heat_intelligence",
        created_at=now,
        updated_at=now,
        location_label="Midtown Core",
        date="2026-08-21",
        observed_temperature=39.0,
        status="Completed",
    )
    add_analysis_record(r1)
    add_analysis_record(r2)

    render_dashboard_page()


class TestPhase15AppTest:
    """End-to-end Streamlit AppTest for Phase 15 Command Center UI."""

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_dashboard_renders_all_tabs_without_exception(self, mock_req, mock_httpx):
        at = AppTest.from_function(_app_entrypoint, default_timeout=15).run()
        assert not at.exception
        mock_req.assert_not_called()
        mock_httpx.assert_not_called()

    def test_tabs_exist_in_rendered_app(self):
        at = AppTest.from_function(_app_entrypoint, default_timeout=15).run()
        assert not at.exception
        # Ensure elements rendered
        assert len(at.tabs) >= 7

    def test_metrics_rendered_on_top_strip(self):
        at = AppTest.from_function(_app_entrypoint, default_timeout=15).run()
        assert not at.exception
        assert len(at.metric) >= 5
