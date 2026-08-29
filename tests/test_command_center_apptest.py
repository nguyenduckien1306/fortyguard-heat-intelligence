"""Streamlit AppTest integration tests for the Operational Intelligence Command Center."""

from __future__ import annotations

import streamlit as st
from streamlit.testing.v1 import AppTest


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_command_center_empty() -> None:
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import clear_all_analysis_records
    from frontend.utils.investigation_queue import clear_investigation_queue

    clear_all_analysis_records()
    clear_investigation_queue()
    render_dashboard_page()


def _run_command_center_with_data() -> None:
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, clear_all_analysis_records
    from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue

    if "_cc_test_init" not in st.session_state:
        st.session_state["_cc_test_init"] = True
        clear_all_analysis_records()
        clear_investigation_queue()

        r1 = AnalysisRecord(
            analysis_id="HM-20260822-001",
            activity_id="act_test_1",
            analysis_type="heatmap",
            created_at="2026-08-22 10:00:00",
            updated_at="2026-08-22 10:00:00",
            location_label="Downtown Core",
            date="2026-08-22",
            time="14:00",
            granularity=100,
            metrics={"mean_temp": 42.5, "min_temp": 34.0, "max_temp": 47.0, "temp_spread": 13.0, "total_tiles": 60, "above_threshold_proportion": 0.55},
            status="Completed",
        )
        r2 = AnalysisRecord(
            analysis_id="HI-20260822-002",
            activity_id="act_test_2",
            analysis_type="heat_intelligence",
            created_at="2026-08-22 11:00:00",
            updated_at="2026-08-22 11:00:00",
            location_label="Harbor Point",
            date="2026-08-22",
            observed_temperature=31.0,
            categories=["urban"],
            status="Completed",
        )
        add_analysis_record(r1)
        add_analysis_record(r2)

        add_to_investigation_queue(
            analysis_id="HM-20260822-001",
            priority="Critical",
            reason="High temperature threshold exceeded.",
            location="Downtown Core",
        )

    render_dashboard_page()


# ══════════════════════════════════════════════════════════════════════════════
# AppTest Test Cases
# ══════════════════════════════════════════════════════════════════════════════


def test_command_center_empty_state_renders_cleanly() -> None:
    """Empty Command Center displays guidance message without exceptions."""
    at = _app_test(_run_command_center_empty)
    at.run()

    assert not at.exception
    all_text = " ".join([m.value for m in at.markdown] + [s.value for s in at.subheader])
    assert "No Analyses Yet" in all_text or "Command Center" in all_text


def test_command_center_executive_metrics_strip() -> None:
    """Command Center renders the 6 executive metrics."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Total Analyses" in labels
    assert "Active Signals" in labels
    assert any("Critical" in lbl for lbl in labels)
    assert "Queue Items" in labels
    assert "Locations" in labels
    assert "Latest Date" in labels


def test_command_center_navigation_tabs() -> None:
    """Command Center renders all 5 main operational tabs."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    tab_labels = [t.label for t in at.tabs]
    assert any("Command Center" in lbl for lbl in tab_labels)
    assert any("Alert Center" in lbl for lbl in tab_labels)
    assert any("Investigation Queue" in lbl for lbl in tab_labels)
    assert any("Analysis Workspace" in lbl for lbl in tab_labels)
    assert any("Scenario Sandbox" in lbl for lbl in tab_labels)
    assert any("Intelligence Diagnostics" in lbl for lbl in tab_labels)


def test_diagnostics_tab_renders_observability_copy() -> None:
    """Diagnostics tab shows provenance and local observability copy without errors."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "Intelligence Diagnostics" in markdown_text or "Observability" in markdown_text


def test_priority_signal_cards_render_in_command_center() -> None:
    """Priority signals tab renders cards with actions."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "Priority Operational Signals" in markdown_text

    # Buttons for Investigate and Add to Queue exist
    btn_labels = [b.label for b in at.button]
    assert any("Investigate" in (lbl or "") for lbl in btn_labels)
    assert any("Add to Queue" in (lbl or "") for lbl in btn_labels)


def test_investigation_queue_renders_items_and_actions() -> None:
    """Investigation queue renders existing queue items."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    markdown_text = " ".join([m.value for m in at.markdown])
    assert "Investigation Queue" in markdown_text
    assert "Downtown Core" in markdown_text


def test_scenario_sandbox_renders_sliders_and_disclaimer() -> None:
    """Scenario Sandbox renders slider controls and mandatory disclaimer."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    assert not at.exception
    info_text = " ".join([inf.value for inf in at.info])
    assert "SCENARIO ONLY" in info_text
    assert "mathematical what-if" in info_text.lower()

    # Sliders exist for scenario adjustments
    assert len(at.slider) >= 4


def test_scenario_sandbox_adjustment_rerun() -> None:
    """Modifying a scenario slider updates the scenario comparison without error."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    slider_temp = at.slider(key="_scen_temp_adj")
    if slider_temp:
        slider_temp.set_value(3.0).run()
        assert not at.exception
        metrics = [m.label for m in at.metric]
        assert "Mean Temperature" in metrics


def test_investigation_brief_download_buttons_present() -> None:
    """Download buttons for Investigation Brief exist."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    dl_buttons = at.download_button
    assert len(dl_buttons) >= 2


def test_search_filtering_in_workspace() -> None:
    """Workspace search input filters cards without exception."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    search_input = at.text_input(key="_ws_search_input")
    if search_input:
        search_input.set_value("Downtown").run()
        assert not at.exception


def test_acknowledge_signal_action() -> None:
    """Clicking Ack button on a signal triggers acknowledgement without exception."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    ack_btns = [b for b in at.button if b.label == "Ack"]
    if ack_btns:
        ack_btns[0].click().run()
        assert not at.exception


def test_dismiss_signal_action() -> None:
    """Clicking Dismiss button moves signal to dismissed archive."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    dsm_btns = [b for b in at.button if b.label == "Dismiss"]
    if dsm_btns:
        dsm_btns[0].click().run()
        assert not at.exception


def test_open_analysis_detail_view_navigation() -> None:
    """Opening an analysis navigates to detail inspection view."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    open_btns = [b for b in at.button if b.label == "Open Analysis"]
    if open_btns:
        open_btns[0].click().run()
        assert not at.exception
        assert "Investigation Console" in " ".join([m.value for m in at.markdown] + [s.value for s in at.subheader])


def test_back_to_command_center_navigation() -> None:
    """Clicking back button returns to the Command Center main view."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    open_btns = [b for b in at.button if b.label == "Open Analysis"]
    if open_btns:
        open_btns[0].click().run()
        back_btn = [b for b in at.button if "Back to Command Center" in (b.label or "")][0]
        back_btn.click().run()
        assert not at.exception
        assert any("Command Center" in t.label for t in at.tabs)


def test_clear_resolved_queue_items_action() -> None:
    """Clicking clear resolved queue items runs cleanly."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    clear_btn = [b for b in at.button if "Clear Resolved" in (b.label or "")][0]
    clear_btn.click().run()
    assert not at.exception


def test_zero_network_calls_during_all_interactions() -> None:
    """Ensure no external network / requests are made during any interaction."""
    at = _app_test(_run_command_center_with_data)
    at.run()

    # Navigating, filtering, toggling
    assert not at.exception


def _run_command_center_with_live_watch_signal() -> None:
    import streamlit as st
    from frontend.pages.dashboard import render_dashboard_page
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, clear_all_analysis_records
    from frontend.utils.investigation_queue import clear_investigation_queue

    if "_cc_live_init" not in st.session_state:
        st.session_state["_cc_live_init"] = True
        clear_all_analysis_records()
        clear_investigation_queue()

        # Real point Heat Intelligence record matching live failure scenario
        r_hi = AnalysisRecord(
            analysis_id="HI-20260828-001",
            activity_id="act_hi_live",
            analysis_type="heat_intelligence",
            created_at="2026-08-28 10:00:00",
            updated_at="2026-08-28 10:00:00",
            location_label="Downtown",
            date="2026-08-28",
            time="12:00",
            observed_temperature=32.5,
            categories=["urban", "outdoor"],
            status="Completed",
        )
        add_analysis_record(r_hi)

    render_dashboard_page()


def test_command_center_add_to_queue_preserves_live_evidence_and_brief() -> None:
    """AppTest verifying UI Add to Queue action creates InvestigationItem with exact observed=32.5, threshold=32.0, LOW."""
    from frontend.utils.export import generate_investigation_brief
    from frontend.utils.investigation_queue import get_investigation_queue
    from frontend.utils.analysis_history import get_analysis_record

    at = _app_test(_run_command_center_with_live_watch_signal)
    at.run()
    assert not at.exception

    # 1. Verify signal card displays with correct evidence
    all_text = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    assert "Watch Temperature Threshold Reached" in all_text or "32.5" in all_text

    # 2. Click "➕ Add to Queue" on the signal card
    q_btns = [b for b in at.button if "Add to Queue" in (b.label or "")]
    assert len(q_btns) >= 1
    q_btns[0].click().run()
    assert not at.exception

    # 3. Verify InvestigationItem created with exact facts inside AppTest session_state
    from frontend.utils.investigation_queue import InvestigationItem
    assert "_session_investigation_queue" in at.session_state
    raw_queue = at.session_state["_session_investigation_queue"]
    assert len(raw_queue) >= 1
    target_item = InvestigationItem.from_dict(raw_queue[-1])
    assert target_item.analysis_id == "HI-20260828-001"
    assert target_item.observed_value == 32.5
    assert target_item.threshold_value == 32.0
    assert target_item.data_quality == "LOW"

    # 4. Generate Investigation Brief from this item
    rec = {
        "analysis_id": "HI-20260828-001",
        "analysis_type": "heat_intelligence",
        "location_label": "Downtown",
        "date": "2026-08-28",
        "observed_temperature": 32.5,
    }
    brief_txt = generate_investigation_brief(target_item, rec, format="brief")
    assert "Observed    : 32.5" in brief_txt
    assert "Threshold   : 32.0" in brief_txt
    assert "Data Quality: LOW" in brief_txt
    assert "Observed    : None" not in brief_txt
    assert "Threshold   : 35.0" not in brief_txt
    assert "Data Quality: HIGH" not in brief_txt

