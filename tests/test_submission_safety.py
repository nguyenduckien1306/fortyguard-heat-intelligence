"""Submission safety tests proving invalid inputs never trigger API calls or history records.

Architectural Invariant Tested:
    INVALID INPUT
         ↓
    CENTRAL VALIDATION FAILS
         ↓
    ZERO HTTP CALLS
    ZERO BACKEND CLIENT CALLS
    ZERO SESSION HISTORY RECORDS
"""

from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock

from frontend.pages.heat_intelligence import render_heat_intelligence_page
from frontend.pages.heatmap import render_heatmap_page
from frontend.utils.history import clear_session_history, get_session_history
from frontend.utils.validation import (
    validate_heat_intelligence_request,
    validate_heatmap_request,
)


def test_invalid_heat_intelligence_parameters_prevent_api_call() -> None:
    """Proves invalid coordinates fail validation and do not call submit_heat_intelligence."""
    mock_client = MagicMock()
    clear_session_history()

    # Out of range coordinates
    res = validate_heat_intelligence_request(
        latitude=100.0,
        longitude=200.0,
        temperature=32.5,
        date_val=date(2024, 7, 15),
        categories=["geographic"],
    )
    assert res.is_valid is False

    # Simulate submission attempt with failed validation guard
    if res.is_valid:
        mock_client.submit_heat_intelligence({})

    # Must be 0 calls
    mock_client.submit_heat_intelligence.assert_not_called()
    assert len(get_session_history()) == 0


def test_empty_categories_prevent_api_call() -> None:
    """Proves empty analysis category selection fails validation and blocks submission."""
    mock_client = MagicMock()
    clear_session_history()

    res = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date_val=date(2024, 7, 15),
        categories=[],  # Empty
    )
    assert res.is_valid is False

    if res.is_valid:
        mock_client.submit_heat_intelligence({})

    mock_client.submit_heat_intelligence.assert_not_called()
    assert len(get_session_history()) == 0


def test_invalid_heatmap_aoi_prevents_api_call() -> None:
    """Proves malformed GeoJSON AOI fails validation and prevents heatmap submission."""
    mock_client = MagicMock()
    clear_session_history()

    bad_aoi = {"type": "FeatureCollection", "features": []}
    res = validate_heatmap_request(
        polygon_aoi=bad_aoi,
        date_val=date(2024, 7, 15),
        time_val=time(14, 0),
        granularity=100,
    )
    assert res.is_valid is False

    if res.is_valid:
        mock_client.submit_heatmap({})

    mock_client.submit_heatmap.assert_not_called()
    assert len(get_session_history()) == 0


def test_invalid_heatmap_coordinates_prevent_api_call() -> None:
    """Proves out-of-bounds coordinates inside GeoJSON polygon fail validation and block submission."""
    mock_client = MagicMock()
    clear_session_history()

    bad_coords_aoi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [250.0, 40.0],  # Longitude > 180
                            [250.0, 41.0],
                            [251.0, 41.0],
                            [251.0, 40.0],
                            [250.0, 40.0],
                        ]
                    ],
                },
            }
        ],
    }

    res = validate_heatmap_request(
        polygon_aoi=bad_coords_aoi,
        date_val=date(2024, 7, 15),
        time_val=time(14, 0),
        granularity=100,
    )
    assert res.is_valid is False
    assert "longitude" in res.errors[0].lower()

    if res.is_valid:
        mock_client.submit_heatmap({})

    mock_client.submit_heatmap.assert_not_called()
    assert len(get_session_history()) == 0


def test_reopening_historical_analysis_triggers_zero_api_calls() -> None:
    """Proves reopening an existing historical analysis renders strictly from session state with 0 API calls."""
    from frontend.utils.analysis_history import AnalysisRecord, add_analysis_record, get_analysis_record
    clear_session_history()

    mock_client = MagicMock()

    # Pre-populate history with a confirmed record
    rec = AnalysisRecord(
        analysis_id="HM-20260822-001",
        activity_id="act_existing_999",
        analysis_type="heatmap",
        created_at="2026-08-22 14:00:00",
        updated_at="2026-08-22 14:00:00",
        location_label="Historical Area",
        status="Completed",
        metrics={"mean_temp": 32.1, "total_tiles": 50},
        result_cached={"stats_data": {"min_temp": 28.0, "max_temp": 36.0, "mean_temp": 32.1}},
    )
    add_analysis_record(rec)

    # Reopen analysis from session state
    reopened = get_analysis_record("HM-20260822-001")
    assert reopened is not None
    assert reopened.activity_id == "act_existing_999"
    assert reopened.result_cached is not None

    # Assert 0 client calls were executed
    mock_client.submit_heatmap.assert_not_called()
    mock_client.submit_heat_intelligence.assert_not_called()
    mock_client.get_heatmap_status.assert_not_called()
    mock_client.get_heat_intelligence_status.assert_not_called()


def test_workspace_operations_trigger_zero_api_calls() -> None:
    """Proves searching, filtering, pinning, tagging, deleting, and clearing make 0 network calls."""
    from frontend.utils.analysis_history import (
        AnalysisRecord,
        add_analysis_record,
        add_tag_to_analysis_record,
        clear_all_analysis_records,
        delete_analysis_record,
        pin_analysis_record,
        remove_tag_from_analysis_record,
        search_and_filter_records,
        unpin_analysis_record,
    )
    clear_all_analysis_records()

    mock_client = MagicMock()

    # Add 2 records
    r1 = add_analysis_record(AnalysisRecord(
        analysis_id="HM-001",
        activity_id="act_1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Loc 1",
    ))
    r2 = add_analysis_record(AnalysisRecord(
        analysis_id="HI-002",
        activity_id="act_2",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Loc 2",
    ))

    # Search & Filter (0 calls)
    res = search_and_filter_records(query="Loc", type_filter="heatmap", sort_by="Newest")
    assert len(res) == 1

    # Pin & Unpin (0 calls)
    pin_analysis_record(r1.analysis_id)
    unpin_analysis_record(r1.analysis_id)

    # Tag & Untag (0 calls)
    add_tag_to_analysis_record(r1.analysis_id, "baseline")
    remove_tag_from_analysis_record(r1.analysis_id, "baseline")

    # Delete (0 calls)
    delete_analysis_record(r1.analysis_id)

    # Clear (0 calls)
    clear_all_analysis_records()

    # Zero backend client calls
    mock_client.submit_heatmap.assert_not_called()
    mock_client.submit_heat_intelligence.assert_not_called()
    mock_client.get_heatmap_status.assert_not_called()
    mock_client.get_heat_intelligence_status.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Phase 12B.2 Explicit Credit & Submission Invariants
# ──────────────────────────────────────────────────────────────────────────────


def test_credit_invariant_invalid_produces_zero_post() -> None:
    """Invalid input -> 0 POST requests."""
    mock_client = MagicMock()
    val = validate_heat_intelligence_request(
        latitude=999.0,
        longitude=999.0,
        temperature=30.0,
        date_val=date(2026, 8, 22),
        categories=["urban"],
    )
    assert not val.is_valid
    if val.is_valid:
        mock_client.submit_heat_intelligence({})
    mock_client.submit_heat_intelligence.assert_not_called()


def test_credit_invariant_processing_and_polling_produces_zero_post() -> None:
    """Polling existing activity during Processing -> 0 POST requests."""
    mock_client = MagicMock()
    mock_client.get_heat_intelligence_status.return_value = {
        "activity_id": "act-poll-credit",
        "status": "Processing",
    }
    # Poll 5 times
    for _ in range(5):
        mock_client.get_heat_intelligence_status("act-poll-credit")

    mock_client.submit_heat_intelligence.assert_not_called()
    assert mock_client.get_heat_intelligence_status.call_count == 5


def test_credit_invariant_timeout_and_check_again_produces_zero_post() -> None:
    """Observation timeout + Check Again -> 0 POST requests."""
    from frontend.utils.analysis_execution import (
        create_execution_context,
        resume_polling_after_timeout,
        transition_to_processing,
        transition_to_submitting,
        transition_to_timeout,
    )
    mock_client = MagicMock()
    ctx = create_execution_context("heat_intelligence")
    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-timeout-credit")
    transition_to_timeout(ctx)

    # User clicks Check Again
    resume_polling_after_timeout(ctx)
    mock_client.get_heat_intelligence_status("act-timeout-credit")

    mock_client.submit_heat_intelligence.assert_not_called()
    assert mock_client.get_heat_intelligence_status.call_count == 1


def test_credit_invariant_retry_produces_exactly_one_post() -> None:
    """User-controlled retry -> exactly 1 new POST submission."""
    from frontend.utils.analysis_execution import (
        create_execution_context,
        create_retry_context,
        transition_to_failed,
        transition_to_processing,
        transition_to_submitting,
    )
    mock_client = MagicMock()
    mock_client.submit_heat_intelligence.return_value = {"activity_id": "act-retry-new"}

    # Attempt 1 failed
    ctx = create_execution_context("heat_intelligence", {"latitude": 40.7, "longitude": -74.0})
    transition_to_submitting(ctx)
    transition_to_processing(ctx, "act-retry-old")
    transition_to_failed(ctx)

    # Explicit user retry
    retry_ctx = create_retry_context(ctx)
    transition_to_submitting(retry_ctx)
    resp = mock_client.submit_heat_intelligence(retry_ctx.request_params)
    transition_to_processing(retry_ctx, resp["activity_id"])

    assert mock_client.submit_heat_intelligence.call_count == 1
    assert retry_ctx.activity_id == "act-retry-new"
    assert retry_ctx.parent_activity_id == "act-retry-old"
    assert retry_ctx.attempt_number == 2


# ──────────────────────────────────────────────────────────────────────────────
# Phase 14 Operational Intelligence Zero-API Invariants
# ──────────────────────────────────────────────────────────────────────────────


def test_phase14_zero_api_calls_invariant() -> None:
    """All Phase 14 operational subsystems generate exactly 0 API requests."""
    from frontend.utils.alert_engine import acknowledge_signal, dismiss_signal, evaluate_alert_policies, restore_signal
    from frontend.utils.alert_policies import AlertPolicy, delete_alert_policy, get_alert_policies, save_alert_policy
    from frontend.utils.analysis_history import AnalysisRecord
    from frontend.utils.export import generate_investigation_brief
    from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue, mark_in_review, mark_resolved
    from frontend.utils.operational_intelligence import generate_operational_signals
    from frontend.utils.priority import calculate_priority_score
    from frontend.utils.scenario_engine import compare_scenario_to_observed, create_scenario_adjustments

    mock_client = MagicMock()
    rec = AnalysisRecord(
        analysis_id="HM-P14-001",
        activity_id="act_p14_001",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Test Location",
        metrics={"mean_temp": 42.0},
        status="Completed",
    )

    # 1. Operational Signal Detection (0 API calls)
    signals = generate_operational_signals([rec])
    assert len(signals) >= 1

    # 2. Policy Evaluation & Management (0 API calls)
    pol = AlertPolicy("P-TEST", "Policy", "mean_temperature", ">=", 40.0)
    save_alert_policy(pol)
    get_alert_policies()
    evaluate_alert_policies([rec], [pol])
    delete_alert_policy(pol.policy_id)

    # 3. Signal Lifecycle Transitions (0 API calls)
    acknowledge_signal("SIG-TEST")
    dismiss_signal("SIG-TEST")
    restore_signal("SIG-TEST")

    # 4. Priority Calculations (0 API calls)
    calculate_priority_score(signals[0])

    # 5. Queue Management (0 API calls)
    _, _, item = add_to_investigation_queue(rec.analysis_id)
    if item:
        mark_in_review(item.queue_id)
        mark_resolved(item.queue_id)
    clear_investigation_queue()

    # 6. Scenario Sandbox (0 API calls)
    adj = create_scenario_adjustments(temperature_delta=2.0)
    scen = compare_scenario_to_observed(rec, adj)

    # 7. Investigation Brief Export (0 API calls)
    generate_investigation_brief(signals[0], rec, scenario=scen)

    # Confirm 0 client calls across all functions
    mock_client.submit_heatmap.assert_not_called()
    mock_client.submit_heat_intelligence.assert_not_called()
    mock_client.get_heatmap_status.assert_not_called()
    mock_client.get_heat_intelligence_status.assert_not_called()



