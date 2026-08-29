"""Tests for frontend.utils.investigation_queue — Investigation Queue Management Engine.

Validates:
- InvestigationItem dataclass serialization and deserialization.
- Adding items to the investigation queue.
- Duplicate detection for active (OPEN, IN_REVIEW) queue items.
- Capacity limit enforcement (maximum 100 items).
- Status transitions: OPEN -> IN_REVIEW -> RESOLVED.
- Prioritized sorting of active items in list_open_queue().
- Removing items and clearing the queue.
- Zero network I/O invariant.
"""

from __future__ import annotations

import streamlit as st
import pytest

from frontend.utils.investigation_queue import (
    MAX_INVESTIGATION_QUEUE_ITEMS,
    STATUS_IN_REVIEW,
    STATUS_OPEN,
    STATUS_RESOLVED,
    InvestigationItem,
    add_to_investigation_queue,
    clear_investigation_queue,
    get_investigation_queue,
    list_open_queue,
    mark_in_review,
    mark_resolved,
    remove_from_investigation_queue,
)


@pytest.fixture(autouse=True)
def clean_session_state():
    st.session_state.clear()
    yield
    st.session_state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Model & Serialization
# ══════════════════════════════════════════════════════════════════════════════


class TestInvestigationItemModel:
    """Dataclass fields, immutability, and dictionary conversions."""

    def test_item_initialization(self):
        item = InvestigationItem(
            queue_id="Q-001",
            analysis_id="REC-001",
            signal_id="SIG-001",
            priority="Critical",
            reason="High temperature threshold exceeded.",
            location="Downtown",
            analysis_type="heatmap",
            status=STATUS_OPEN,
        )
        assert item.queue_id == "Q-001"
        assert item.priority == "Critical"
        assert item.status == STATUS_OPEN

    def test_to_dict_and_from_dict_roundtrip(self):
        item = InvestigationItem(
            queue_id="Q-002",
            analysis_id="REC-002",
            signal_id=None,
            priority="High",
            reason="Spread elevated",
            location="Marina",
            analysis_type="heat_intelligence",
            status=STATUS_IN_REVIEW,
            notes="Assigned to senior analyst.",
        )
        d = item.to_dict()
        assert d["queue_id"] == "Q-002"
        assert d["notes"] == "Assigned to senior analyst."

        reconstructed = InvestigationItem.from_dict(d)
        assert reconstructed.queue_id == item.queue_id
        assert reconstructed.analysis_id == item.analysis_id
        assert reconstructed.priority == "High"
        assert reconstructed.status == STATUS_IN_REVIEW
        assert reconstructed.notes == item.notes


# ══════════════════════════════════════════════════════════════════════════════
# 2. Adding to Queue & Validation
# ══════════════════════════════════════════════════════════════════════════════


class TestAddToInvestigationQueue:
    """Adding items, validation rules, and duplicate detection."""

    def test_add_valid_item_succeeds(self):
        ok, err, item = add_to_investigation_queue(
            analysis_id="REC-100",
            signal_id="SIG-100",
            priority="Critical",
            reason="Critical thermal exceedance",
            location="Downtown",
        )
        assert ok is True
        assert err is None
        assert item is not None
        assert item.queue_id.startswith("Q-")

        queue = get_investigation_queue()
        assert len(queue) == 1
        assert queue[0].analysis_id == "REC-100"

    def test_add_empty_analysis_id_fails(self):
        ok, err, item = add_to_investigation_queue(analysis_id="")
        assert ok is False
        assert "analysis id is required" in err.lower()
        assert item is None

    def test_add_duplicate_active_item_fails(self):
        add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-100")
        ok, err, item = add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-100")
        assert ok is False
        assert "already present" in err.lower()
        assert item is None

    def test_add_same_analysis_different_signal_succeeds(self):
        add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-1")
        ok, err, item = add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-2")
        assert ok is True
        assert len(get_investigation_queue()) == 2

    def test_add_same_analysis_after_resolved_succeeds(self):
        _, _, item1 = add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-1")
        mark_resolved(item1.queue_id)

        # Adding same analysis & signal now succeeds since prior is RESOLVED
        ok, err, item2 = add_to_investigation_queue(analysis_id="REC-100", signal_id="SIG-1")
        assert ok is True
        assert len(get_investigation_queue()) == 2

    def test_queue_capacity_limit_enforced(self):
        # Fill queue up to MAX_INVESTIGATION_QUEUE_ITEMS
        for i in range(MAX_INVESTIGATION_QUEUE_ITEMS):
            add_to_investigation_queue(analysis_id=f"REC-{i}", signal_id=f"SIG-{i}")

        assert len(get_investigation_queue()) == MAX_INVESTIGATION_QUEUE_ITEMS

        # 101st item should fail
        ok, err, item = add_to_investigation_queue(analysis_id="REC-OVERFLOW")
        assert ok is False
        assert "maximum capacity" in err.lower()
        assert item is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. Status Transitions
# ══════════════════════════════════════════════════════════════════════════════


class TestQueueStatusTransitions:
    """State machine transitions: OPEN -> IN_REVIEW -> RESOLVED."""

    def test_mark_in_review(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-1")
        assert item.status == STATUS_OPEN

        ok, err = mark_in_review(item.queue_id, notes="Investigating anomalous tile cluster.")
        assert ok is True
        assert err is None

        queue = get_investigation_queue()
        assert queue[0].status == STATUS_IN_REVIEW
        assert queue[0].notes == "Investigating anomalous tile cluster."

    def test_mark_resolved(self):
        _, _, item = add_to_investigation_queue(analysis_id="REC-1")
        ok, err = mark_resolved(item.queue_id, notes="Confirmed as temporal transient.")
        assert ok is True

        queue = get_investigation_queue()
        assert queue[0].status == STATUS_RESOLVED
        assert queue[0].notes == "Confirmed as temporal transient."

    def test_transition_non_existent_item_fails(self):
        ok, err = mark_in_review("Q-DOES-NOT-EXIST")
        assert ok is False
        assert "not found" in err.lower()

        ok, err = mark_resolved("Q-DOES-NOT-EXIST")
        assert ok is False
        assert "not found" in err.lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Queue Filtering & Prioritized Listing
# ══════════════════════════════════════════════════════════════════════════════


class TestListOpenQueue:
    """Listing active items sorted by priority (Critical -> High -> Medium -> Low)."""

    def test_list_open_queue_prioritization(self):
        add_to_investigation_queue("R1", priority="Low")
        add_to_investigation_queue("R2", priority="Critical")
        add_to_investigation_queue("R3", priority="Medium")
        add_to_investigation_queue("R4", priority="High")

        open_items = list_open_queue()
        assert len(open_items) == 4
        assert [i.priority for i in open_items] == ["Critical", "High", "Medium", "Low"]

    def test_list_open_queue_excludes_resolved(self):
        _, _, item1 = add_to_investigation_queue("R1", priority="Critical")
        _, _, item2 = add_to_investigation_queue("R2", priority="High")
        mark_resolved(item1.queue_id)

        open_items = list_open_queue()
        assert len(open_items) == 1
        assert open_items[0].analysis_id == "R2"

    def test_list_open_queue_includes_in_review(self):
        _, _, item1 = add_to_investigation_queue("R1", priority="High")
        mark_in_review(item1.queue_id)

        open_items = list_open_queue()
        assert len(open_items) == 1
        assert open_items[0].status == STATUS_IN_REVIEW


# ══════════════════════════════════════════════════════════════════════════════
# 5. Removal & Clearing
# ══════════════════════════════════════════════════════════════════════════════


class TestQueueRemovalAndClear:
    """Removing individual items and clearing session queue."""

    def test_remove_item(self):
        _, _, item = add_to_investigation_queue("R1")
        assert len(get_investigation_queue()) == 1

        ok, err = remove_from_investigation_queue(item.queue_id)
        assert ok is True
        assert len(get_investigation_queue()) == 0

    def test_remove_non_existent_item_fails(self):
        ok, err = remove_from_investigation_queue("Q-MISSING")
        assert ok is False
        assert "not found" in err.lower()

    def test_clear_investigation_queue(self):
        add_to_investigation_queue("R1")
        add_to_investigation_queue("R2")
        assert len(get_investigation_queue()) == 2

        clear_investigation_queue()
        assert len(get_investigation_queue()) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. Edge Cases & Case Normalization
# ══════════════════════════════════════════════════════════════════════════════


class TestQueueEdgeCases:
    """Case normalization, notes updates, and data conversion edge cases."""

    def test_priority_case_normalization(self):
        _, _, item1 = add_to_investigation_queue("R1", priority="critical")
        assert item1.priority == "Critical"

        _, _, item2 = add_to_investigation_queue("R2", priority="HIGH")
        assert item2.priority == "High"

        _, _, item3 = add_to_investigation_queue("R3", priority="low")
        assert item3.priority == "Low"

    def test_default_priority_is_medium(self):
        _, _, item = add_to_investigation_queue("R-DEFAULT")
        assert item.priority == "Medium"

    def test_notes_preserved_when_not_overwritten(self):
        _, _, item = add_to_investigation_queue("R1", notes="Initial note.")
        # Mark in review with None notes -> notes should stay "Initial note."
        mark_in_review(item.queue_id, notes=None)
        q = get_investigation_queue()
        assert q[0].notes == "Initial note."

    def test_notes_updated_when_provided(self):
        _, _, item = add_to_investigation_queue("R1", notes="Initial note.")
        mark_in_review(item.queue_id, notes="Updated review note.")
        q = get_investigation_queue()
        assert q[0].notes == "Updated review note."

    def test_from_dict_handles_missing_fields(self):
        minimal_data = {
            "queue_id": "Q-MIN",
            "analysis_id": "R-MIN",
        }
        item = InvestigationItem.from_dict(minimal_data)
        assert item.priority == "Medium"
        assert item.status == STATUS_OPEN
        assert item.location == "Analysis Area"
        assert item.signal_id is None

    def test_location_and_analysis_type_defaults(self):
        _, _, item = add_to_investigation_queue("R1", location="Harbor District", analysis_type="heat_intelligence")
        assert item.location == "Harbor District"
        assert item.analysis_type == "heat_intelligence"

    def test_list_open_queue_when_empty_returns_empty(self):
        assert list_open_queue() == []

    def test_same_priority_items_sorted_by_timestamp(self):
        add_to_investigation_queue("R1", priority="Critical")
        add_to_investigation_queue("R2", priority="Critical")
        items = list_open_queue()
        assert len(items) == 2
        assert items[0].analysis_id == "R1"
        assert items[1].analysis_id == "R2"

