"""Unit tests for Phase 15.1 Watchlists Data Model & Session Store.

Verifies:
- WatchlistCriterion validation (supported metrics, operators, finite thresholds, hysteresis).
- Watchlist validation (name length, comparison modes, window size, duplicate criteria rejection).
- Session-local CRUD (get, save, toggle, delete, version increments).
- Deep-copy duplication preserving source immutability.
- Hard capacity limit enforcement (max 20 watchlists).
- Default presets and reset.
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.clock import FrozenClock, set_current_clock
from frontend.utils.watchlists import (
    MAX_WATCHLISTS,
    Watchlist,
    WatchlistCriterion,
    delete_watchlist,
    duplicate_watchlist,
    get_default_watchlists,
    get_watchlist,
    get_watchlists,
    reset_default_watchlists,
    save_watchlist,
    toggle_watchlist,
    validate_watchlist,
    validate_watchlist_criterion,
)


@pytest.fixture(autouse=True)
def clean_session():
    st.session_state.clear()
    set_current_clock(FrozenClock("2026-08-23T10:00:00"))
    yield
    st.session_state.clear()
    set_current_clock(None)


# ══════════════════════════════════════════════════════════════════════════════
# 1. WatchlistCriterion Validation Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestWatchlistCriterionValidation:
    """Validation of individual WatchlistCriterion objects."""

    def test_valid_criterion_passes(self):
        c = WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0)
        ok, err = validate_watchlist_criterion(c)
        assert ok is True
        assert err is None

    def test_all_supported_metrics_pass(self):
        metrics = [
            "mean_temperature",
            "temperature_change",
            "temperature_change_percent",
            "temperature_spread",
            "above_threshold_proportion",
            "analysis_count",
        ]
        for m in metrics:
            c = WatchlistCriterion(metric=m, operator=">", threshold=10.0)
            ok, err = validate_watchlist_criterion(c)
            assert ok is True, f"Failed for metric {m}: {err}"

    def test_invalid_metric_fails(self):
        c = WatchlistCriterion(metric="unsupported_custom_metric", operator=">", threshold=10.0)
        ok, err = validate_watchlist_criterion(c)
        assert ok is False
        assert "Invalid criterion metric" in err

    def test_all_supported_operators_pass(self):
        for op in (">", ">=", "<", "<=", "==", "!="):
            c = WatchlistCriterion(metric="mean_temperature", operator=op, threshold=30.0)
            ok, _ = validate_watchlist_criterion(c)
            assert ok is True

    def test_invalid_operator_fails(self):
        c = WatchlistCriterion(metric="mean_temperature", operator="~=", threshold=30.0)
        ok, err = validate_watchlist_criterion(c)
        assert ok is False
        assert "Invalid operator" in err

    def test_non_finite_threshold_fails(self):
        for bad_th in (float("nan"), float("inf"), float("-inf")):
            c = WatchlistCriterion(metric="mean_temperature", operator=">", threshold=bad_th)
            ok, err = validate_watchlist_criterion(c)
            assert ok is False
            assert "finite number" in err

    def test_valid_hysteresis_positive_operator(self):
        # Trigger (38.0) > Clear (36.0) is valid for >=
        c = WatchlistCriterion(
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
            trigger_threshold=38.0,
            clear_threshold=36.0,
        )
        ok, err = validate_watchlist_criterion(c)
        assert ok is True

    def test_invalid_hysteresis_positive_operator_fails(self):
        # Trigger <= Clear is invalid for >=
        c = WatchlistCriterion(
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
            trigger_threshold=35.0,
            clear_threshold=37.0,
        )
        ok, err = validate_watchlist_criterion(c)
        assert ok is False
        assert "strictly greater" in err

    def test_valid_hysteresis_negative_operator(self):
        # Trigger (20.0) < Clear (22.0) is valid for <=
        c = WatchlistCriterion(
            metric="mean_temperature",
            operator="<=",
            threshold=20.0,
            trigger_threshold=20.0,
            clear_threshold=22.0,
        )
        ok, err = validate_watchlist_criterion(c)
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════════
# 2. Watchlist Model & Validation Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestWatchlistValidation:
    """Validation of Watchlist configuration objects."""

    def _sample_valid_watchlist(self) -> Watchlist:
        return Watchlist(
            watchlist_id="WL-TEST-1",
            name="Downtown Watch",
            description="Monitoring downtown thermal levels.",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=37.0)],
            location_scope="all",
            comparison_mode="PREVIOUS",
            window_size=5,
            enabled=True,
        )

    def test_valid_watchlist_passes(self):
        wl = self._sample_valid_watchlist()
        ok, err = validate_watchlist(wl)
        assert ok is True
        assert err is None

    def test_empty_name_fails(self):
        wl = self._sample_valid_watchlist()
        wl.name = "   "
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "name cannot be empty" in err

    def test_name_exceeding_max_length_fails(self):
        wl = self._sample_valid_watchlist()
        wl.name = "A" * 61
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "exceeds maximum allowed length" in err

    def test_invalid_comparison_mode_fails(self):
        wl = self._sample_valid_watchlist()
        wl.comparison_mode = "INVALID_MODE"
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "Invalid comparison mode" in err

    def test_invalid_window_size_fails(self):
        wl = self._sample_valid_watchlist()
        wl.window_size = 0
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "Window size must be an integer" in err

    def test_empty_criteria_fails(self):
        wl = self._sample_valid_watchlist()
        wl.criteria = []
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "at least one criterion" in err

    def test_duplicate_identical_criteria_fails(self):
        wl = self._sample_valid_watchlist()
        c = WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=37.0)
        wl.criteria = [c, c]
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "Duplicate identical criterion" in err


# ══════════════════════════════════════════════════════════════════════════════
# 3. Session CRUD & Versioning Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestWatchlistSessionCRUD:
    """CRUD operations on session state watchlists."""

    def test_get_default_watchlists_initialization(self):
        wls = get_watchlists()
        assert len(wls) == 3
        ids = {w.watchlist_id for w in wls}
        assert "WL-001" in ids
        assert "WL-002" in ids
        assert "WL-003" in ids

    def test_save_new_watchlist(self):
        wl = Watchlist(
            watchlist_id="",
            name="New Zone Watch",
            criteria=[WatchlistCriterion(metric="temperature_spread", operator=">", threshold=12.0)],
        )
        ok, err, saved = save_watchlist(wl)
        assert ok is True
        assert saved is not None
        assert saved.watchlist_id.startswith("WL-")
        assert saved.version == 1

        fetched = get_watchlist(saved.watchlist_id)
        assert fetched is not None
        assert fetched.name == "New Zone Watch"

    def test_update_existing_watchlist_increments_version(self):
        wls = get_watchlists()
        target = wls[0]
        initial_version = target.version

        target.name = "Renamed Extreme Watch"
        ok, err, updated = save_watchlist(target)
        assert ok is True
        assert updated.version == initial_version + 1

        refetched = get_watchlist(target.watchlist_id)
        assert refetched.name == "Renamed Extreme Watch"
        assert refetched.version == initial_version + 1

    def test_toggle_watchlist_enabled(self):
        wls = get_watchlists()
        target = wls[0]
        assert target.enabled is True

        # Disable
        ok = toggle_watchlist(target.watchlist_id)
        assert ok is True
        assert get_watchlist(target.watchlist_id).enabled is False

        # Re-enable
        ok = toggle_watchlist(target.watchlist_id)
        assert ok is True
        assert get_watchlist(target.watchlist_id).enabled is True

    def test_delete_watchlist(self):
        wls = get_watchlists()
        target_id = wls[0].watchlist_id

        assert delete_watchlist(target_id) is True
        assert get_watchlist(target_id) is None
        assert len(get_watchlists()) == len(wls) - 1

    def test_duplicate_watchlist_creates_deep_copy(self):
        wls = get_watchlists()
        source = wls[0]

        ok, err, copy_wl = duplicate_watchlist(source.watchlist_id, new_name="Custom Copy")
        assert ok is True
        assert copy_wl is not None
        assert copy_wl.watchlist_id != source.watchlist_id
        assert copy_wl.name == "Custom Copy"
        assert len(copy_wl.criteria) == len(source.criteria)

        # Mutating copy criteria does NOT affect source
        copy_wl.name = "Changed Name"
        assert get_watchlist(source.watchlist_id).name == source.name

    def test_capacity_limit_enforced_at_20(self):
        reset_default_watchlists()

        # Add up to 20 watchlists
        for i in range(4, MAX_WATCHLISTS + 1):
            wl = Watchlist(
                watchlist_id=f"WL-{i:03d}",
                name=f"Watchlist {i}",
                criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0 + i)],
            )
            ok, err, _ = save_watchlist(wl)
            assert ok is True, f"Failed adding watchlist {i}: {err}"

        assert len(get_watchlists()) == MAX_WATCHLISTS

        # Attempt adding the 21st watchlist must fail cleanly
        wl_extra = Watchlist(
            watchlist_id="WL-OVERFLOW",
            name="Overflow Watchlist",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=50.0)],
        )
        ok, err, saved = save_watchlist(wl_extra)
        assert ok is False
        assert "Maximum watchlist capacity (20) reached" in err
        assert saved is None

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_watchlist_operations_make_zero_network_calls(self, mock_requests, mock_httpx):
        wls = get_watchlists()
        toggle_watchlist(wls[0].watchlist_id)
        duplicate_watchlist(wls[0].watchlist_id)
        delete_watchlist(wls[0].watchlist_id)
        reset_default_watchlists()

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_watchlist_criterion_from_dict_defaults(self):
        c = WatchlistCriterion.from_dict({})
        assert c.metric == "mean_temperature"
        assert c.operator == ">"
        assert c.threshold == 0.0
        assert c.trigger_threshold is None
        assert c.clear_threshold is None
        assert c.version == 1

    def test_watchlist_from_dict_defaults(self):
        wl = Watchlist.from_dict({})
        assert wl.name == "Untitled Watchlist"
        assert wl.criteria == []
        assert wl.comparison_mode == "PREVIOUS"
        assert wl.window_size == 5
        assert wl.enabled is True
        assert wl.version == 1

    def test_max_criteria_per_watchlist_enforced(self):
        criteria = [
            WatchlistCriterion(metric="mean_temperature", operator=">", threshold=float(i))
            for i in range(11)
        ]
        wl = Watchlist(
            watchlist_id="WL-MAX-CRIT",
            name="Too Many Criteria",
            criteria=criteria,
        )
        ok, err = validate_watchlist(wl)
        assert ok is False
        assert "exceeds maximum allowed criteria limit" in err

    def test_duplicate_watchlist_not_found_returns_error(self):
        ok, err, duplicated = duplicate_watchlist("NON_EXISTENT_WL")
        assert ok is False
        assert "not found" in err
        assert duplicated is None

    def test_delete_non_existent_watchlist_returns_false(self):
        assert delete_watchlist("NON_EXISTENT_WL") is False
        assert delete_watchlist("") is False

    def test_get_watchlist_empty_id_returns_none(self):
        assert get_watchlist("") is None

    def test_toggle_non_existent_watchlist_returns_false(self):
        assert toggle_watchlist("NON_EXISTENT_WL") is False

    def test_hysteresis_equal_thresholds_fails_for_positive_operator(self):
        c = WatchlistCriterion(
            metric="mean_temperature",
            operator=">",
            threshold=35.0,
            trigger_threshold=35.0,
            clear_threshold=35.0,
        )
        ok, err = validate_watchlist_criterion(c)
        assert ok is False
        assert "strictly greater" in err

    def test_hysteresis_equal_thresholds_fails_for_negative_operator(self):
        c = WatchlistCriterion(
            metric="mean_temperature",
            operator="<",
            threshold=25.0,
            trigger_threshold=25.0,
            clear_threshold=25.0,
        )
        ok, err = validate_watchlist_criterion(c)
        assert ok is False
        assert "strictly less" in err

    def test_comparison_mode_case_insensitivity(self):
        wl = Watchlist(
            watchlist_id="WL-CASE",
            name="Case Mode Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=30.0)],
            comparison_mode="rolling",
        )
        ok, err = validate_watchlist(wl)
        assert ok is True

    def test_window_size_boundaries(self):
        # Window size 1 (valid)
        wl1 = Watchlist(
            watchlist_id="WL-W1",
            name="W1",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
            window_size=1,
        )
        assert validate_watchlist(wl1)[0] is True

        # Window size 50 (valid)
        wl50 = Watchlist(
            watchlist_id="WL-W50",
            name="W50",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
            window_size=50,
        )
        assert validate_watchlist(wl50)[0] is True

        # Window size 51 (invalid)
        wl51 = Watchlist(
            watchlist_id="WL-W51",
            name="W51",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
            window_size=51,
        )
        assert validate_watchlist(wl51)[0] is False

