"""Unit tests for Phase 15.5 Investigation Workflow & Audit Trails.

Verifies:
- InvestigationItem lifecycle (OPEN -> IN_REVIEW -> RESOLVED -> DISMISSED).
- Immutable InvestigationEvent audit trail generation for all mutations.
- Structured analyst notes CRUD.
- Assignment workflow.
- Capacity limits (max 100 queue items).
- Synchronization with high-priority signals and alerts.
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.clock import FrozenClock, set_current_clock
from frontend.utils.investigation_queue import (
    MAX_INVESTIGATION_QUEUE_ITEMS,
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    STATUS_RESOLVED,
    InvestigationEvent,
    InvestigationItem,
    add_note_to_investigation,
    add_to_investigation_queue,
    assign_investigation,
    attach_evidence_bundle,
    clear_investigation_queue,
    get_investigation_item,
    get_investigation_queue,
    list_open_queue,
    mark_in_review,
    mark_resolved,
    remove_from_investigation_queue,
    sync_investigation_queue_with_signals_and_alerts,
)


@pytest.fixture(autouse=True)
def clean_session():
    st.session_state.clear()
    set_current_clock(FrozenClock("2026-08-23T10:00:00"))
    yield
    st.session_state.clear()
    set_current_clock(None)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Queue Item Lifecycle & Audit Trails
# ══════════════════════════════════════════════════════════════════════════════


class TestInvestigationLifecycleAndAuditTrails:
    """Queue creation, transitions, and immutable audit event trails."""

    def test_add_to_investigation_queue_creates_initial_event(self):
        ok, err, item = add_to_investigation_queue(
            analysis_id="REC-001",
            priority="Critical",
            reason="Mean temp > 40°C",
        )
        assert ok is True
        assert item is not None
        assert item.status == STATUS_OPEN
        assert len(item.events) == 1
        assert item.events[0].event_type == "CREATED"
        assert "Critical" in item.events[0].details

    def test_mark_in_review_records_audit_event(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-002", priority="High")
        ok, err = mark_in_review(item.queue_id, notes="Investigating anomaly", actor="Senior Analyst")
        assert ok is True

        updated = get_investigation_item(item.queue_id)
        assert updated.status == STATUS_IN_REVIEW
        assert len(updated.events) == 2
        assert updated.events[1].event_type == "STATUS_CHANGE"
        assert updated.events[1].actor == "Senior Analyst"

    def test_mark_resolved_records_audit_event(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-003", priority="Medium")
        mark_in_review(item.queue_id)
        ok, err = mark_resolved(item.queue_id, notes="False positive verified", actor="Lead Analyst")
        assert ok is True

        updated = get_investigation_item(item.queue_id)
        assert updated.status == STATUS_RESOLVED
        assert len(updated.events) == 3
        assert updated.events[2].event_type == "STATUS_CHANGE"
        assert "RESOLVED" in updated.events[2].details


# ══════════════════════════════════════════════════════════════════════════════
# 2. Structured Notes CRUD & Assignments
# ══════════════════════════════════════════════════════════════════════════════


class TestInvestigationNotesAndAssignments:
    """Structured notes CRUD and assignment workflows."""

    def test_add_structured_notes(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-NOTE-1")

        ok1, _ = add_note_to_investigation(item.queue_id, "First preliminary note.", author="Analyst A")
        ok2, _ = add_note_to_investigation(item.queue_id, "Second detailed note.", author="Analyst B")
        assert ok1 is True
        assert ok2 is True

        updated = get_investigation_item(item.queue_id)
        assert len(updated.notes_list) == 2
        assert updated.notes_list[0]["author"] == "Analyst A"
        assert updated.notes_list[1]["author"] == "Analyst B"
        assert len(updated.events) == 3  # CREATED + 2 NOTES

    def test_add_empty_note_fails(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-NOTE-2")
        ok, err = add_note_to_investigation(item.queue_id, "   ")
        assert ok is False
        assert "cannot be empty" in err

    def test_assign_investigation_workflow(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-ASSIGN")
        assert item.assigned_to == "Unassigned"

        ok, err = assign_investigation(item.queue_id, "Jane Doe", actor="Team Lead")
        assert ok is True

        updated = get_investigation_item(item.queue_id)
        assert updated.assigned_to == "Jane Doe"
        assert updated.events[-1].event_type == "ASSIGNED"
        assert updated.events[-1].actor == "Team Lead"

    def test_attach_evidence_bundle_to_item(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-EVD")
        fake_bundle = {
            "evidence_id": "EVD-ATTACH-01",
            "why_am_i_seeing_this": "Reason text",
            "items": [],
        }
        ok = attach_evidence_bundle(item.queue_id, fake_bundle)
        assert ok is True

        updated = get_investigation_item(item.queue_id)
        assert updated.evidence_bundle["evidence_id"] == "EVD-ATTACH-01"
        assert updated.events[-1].event_type == "EVIDENCE_REFRESHED"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Queue Synchronization & Capacity Limits
# ══════════════════════════════════════════════════════════════════════════════


class TestQueueSyncAndCapacityLimits:
    """Synchronization with high priority alerts and 100-item hard capacity."""

    def test_sync_with_critical_and_high_alerts(self):
        fake_alerts = [
            {"alert_id": "ALT-CRIT", "analysis_id": "REC-C", "priority_tier": "Critical", "promotion_reason": "Extreme Heat"},
            {"alert_id": "ALT-HIGH", "analysis_id": "REC-H", "priority_tier": "High", "promotion_reason": "Rapid Rise"},
            {"alert_id": "ALT-LOW", "analysis_id": "REC-L", "priority_tier": "Low", "promotion_reason": "Minor Temp"},
        ]
        items = sync_investigation_queue_with_signals_and_alerts(signals=[], alerts=fake_alerts)
        # Critical and High alerts added, Low alert ignored
        analysis_ids = {i.analysis_id for i in items}
        assert "REC-C" in analysis_ids
        assert "REC-H" in analysis_ids
        assert "REC-L" not in analysis_ids

    def test_duplicate_active_item_rejected(self):
        add_to_investigation_queue(analysis_id="REC-DUP", signal_id="SIG-1")
        ok, err, _ = add_to_investigation_queue(analysis_id="REC-DUP", signal_id="SIG-1")
        assert ok is False
        assert "already present in the active investigation queue" in err

    def test_capacity_limit_enforced_at_100_items(self):
        # Fill queue to 100 items
        for i in range(MAX_INVESTIGATION_QUEUE_ITEMS):
            add_to_investigation_queue(analysis_id=f"REC-CAP-{i:03d}")

        assert len(get_investigation_queue()) == MAX_INVESTIGATION_QUEUE_ITEMS

        # 101st item rejected
        ok, err, extra = add_to_investigation_queue(analysis_id="REC-CAP-101")
        assert ok is False
        assert "maximum capacity" in err
        assert extra is None

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_investigation_operations_make_zero_network_calls(self, mock_requests, mock_httpx):
        _, _, item = add_to_investigation_queue(analysis_id="REC-ZERO")
        mark_in_review(item.queue_id)
        add_note_to_investigation(item.queue_id, "Note")
        assign_investigation(item.queue_id, "Analyst")
        mark_resolved(item.queue_id)
        remove_from_investigation_queue(item.queue_id)
        clear_investigation_queue()

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_signal_evidence_preserved_in_investigation_item(self):
        """Verify that InvestigationItem preserves exact source signal metrics, thresholds, and data quality."""
        source_signal = {
            "signal_id": "SIG-TH-WATCH-HI-20260828-001",
            "analysis_id": "HI-20260828-001",
            "signal_type": "temperature_above_threshold",
            "severity": "WATCH",
            "title": "Watch Temperature Threshold Reached (Downtown)",
            "metric": "mean_temperature",
            "observed_value": 32.5,
            "threshold_value": 32.0,
            "data_quality": "LOW",
            "evidence": ["Observed value: 32.50°C", "Watch threshold: 32.00°C"],
        }
        ok, err, item = add_to_investigation_queue(
            analysis_id="HI-20260828-001",
            signal_id="SIG-TH-WATCH-HI-20260828-001",
            priority="Medium",
            reason="Watch Temperature Threshold Reached (Downtown)",
            source_signal=source_signal,
        )
        assert ok is True
        assert item is not None
        assert item.metric == "mean_temperature"
        assert item.observed_value == 32.5
        assert item.threshold_value == 32.0
        assert item.data_quality == "LOW"
        assert item.evidence_bundle is not None
        assert item.evidence_bundle["data_quality"] == "LOW"
        assert len(item.evidence_bundle["items"]) == 2
        assert item.evidence_bundle["items"][0]["observed_value"] == 32.5
        assert item.evidence_bundle["items"][0]["threshold_value"] == 32.0

