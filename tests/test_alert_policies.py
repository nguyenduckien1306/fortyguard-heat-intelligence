"""Tests for frontend.utils.alert_policies — User Configurable Alert Policy System.

Validates:
- AlertPolicy dataclass serialization and deserialization.
- Policy validation rules (metric, operator, severity, name length, thresholds).
- Threshold range constraints per metric.
- Duplicate equivalent policy rejection.
- Capacity limit enforcement (max 20 policies).
- Session state policy management: get, save, delete, toggle, reset defaults.
- Zero network I/O invariant.
"""

from __future__ import annotations

import streamlit as st
import pytest

from frontend.utils.alert_policies import (
    MAX_ALERT_POLICIES,
    MAX_POLICY_NAME_LENGTH,
    SUPPORTED_METRICS,
    SUPPORTED_OPERATORS,
    SUPPORTED_SEVERITIES,
    AlertPolicy,
    are_policies_equivalent,
    delete_alert_policy,
    get_alert_policies,
    get_default_alert_policies,
    reset_default_alert_policies,
    save_alert_policy,
    toggle_alert_policy,
    validate_alert_policy,
)


@pytest.fixture(autouse=True)
def clean_session_state():
    """Ensure session state is cleared before and after each test."""
    st.session_state.clear()
    yield
    st.session_state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Model & Validation Basics
# ══════════════════════════════════════════════════════════════════════════════


class TestAlertPolicyValidation:
    """Validation rules for alert policy creation."""

    def test_valid_policy_passes(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Downtown High Heat",
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
            severity="CRITICAL",
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is True
        assert err is None

    def test_empty_name_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="   ",
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "name cannot be empty" in err.lower()

    def test_name_exceeding_max_length_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="A" * (MAX_POLICY_NAME_LENGTH + 1),
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "exceeds maximum allowed length" in err

    def test_invalid_metric_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="unsupported_humidity",
            operator=">=",
            threshold=38.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "invalid metric" in err.lower()

    def test_invalid_operator_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="mean_temperature",
            operator="!=",
            threshold=38.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "invalid operator" in err.lower()

    def test_invalid_severity_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="mean_temperature",
            operator=">=",
            threshold=38.0,
            severity="FATAL",  # invalid non-standard severity
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "invalid severity" in err.lower()

    def test_nan_threshold_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="mean_temperature",
            operator=">=",
            threshold=float("nan"),
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "finite" in err.lower()

    def test_inf_threshold_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="mean_temperature",
            operator=">=",
            threshold=float("inf"),
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "finite" in err.lower()

    def test_extreme_temperature_threshold_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="mean_temperature",
            operator=">=",
            threshold=150.0,  # exceeds 100°C limit
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "-100°c and 100°c" in err.lower()

    def test_negative_tile_count_threshold_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="tile_count",
            operator="<=",
            threshold=-5.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "negative" in err.lower()

    def test_negative_spread_threshold_fails(self):
        pol = AlertPolicy(
            policy_id="POL-1",
            name="Test",
            metric="temperature_spread",
            operator=">=",
            threshold=-1.0,
        )
        is_valid, err = validate_alert_policy(pol)
        assert is_valid is False
        assert "non-negative" in err.lower()

    def test_proportion_range_validation(self):
        pol_valid = AlertPolicy(
            policy_id="P1",
            name="Valid Prop",
            metric="above_threshold_proportion",
            operator=">=",
            threshold=50.0,
        )
        assert validate_alert_policy(pol_valid)[0] is True

        pol_invalid = AlertPolicy(
            policy_id="P2",
            name="Invalid Prop",
            metric="above_threshold_proportion",
            operator=">=",
            threshold=150.0,
        )
        assert validate_alert_policy(pol_invalid)[0] is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. Policy Equivalence Testing
# ══════════════════════════════════════════════════════════════════════════════


class TestPolicyEquivalence:
    """Duplicate condition detection."""

    def test_exact_equivalent_policies(self):
        p1 = AlertPolicy("P1", "Name 1", "mean_temperature", ">=", 40.0, "CRITICAL", "all")
        p2 = AlertPolicy("P2", "Name 2", "mean_temperature", ">=", 40.0, "CRITICAL", "all")
        assert are_policies_equivalent(p1, p2) is True

    def test_different_threshold_not_equivalent(self):
        p1 = AlertPolicy("P1", "Name 1", "mean_temperature", ">=", 40.0, "CRITICAL", "all")
        p2 = AlertPolicy("P2", "Name 2", "mean_temperature", ">=", 35.0, "CRITICAL", "all")
        assert are_policies_equivalent(p1, p2) is False

    def test_different_operator_not_equivalent(self):
        p1 = AlertPolicy("P1", "Name 1", "mean_temperature", ">=", 40.0, "CRITICAL", "all")
        p2 = AlertPolicy("P2", "Name 2", "mean_temperature", ">", 40.0, "CRITICAL", "all")
        assert are_policies_equivalent(p1, p2) is False

    def test_different_scope_not_equivalent(self):
        p1 = AlertPolicy("P1", "Name 1", "mean_temperature", ">=", 40.0, "CRITICAL", "all")
        p2 = AlertPolicy("P2", "Name 2", "mean_temperature", ">=", 40.0, "CRITICAL", "Downtown")
        assert are_policies_equivalent(p1, p2) is False


# ══════════════════════════════════════════════════════════════════════════════
# 3. Session State Policy Management (CRUD)
# ══════════════════════════════════════════════════════════════════════════════


class TestSessionPolicyStore:
    """Session-local storage management for policies."""

    def test_get_initial_policies_returns_defaults(self):
        policies = get_alert_policies()
        assert len(policies) == len(get_default_alert_policies())
        assert any(p.policy_id == "POL-CRIT-HEAT" for p in policies)

    def test_save_new_valid_policy(self):
        pol = AlertPolicy(
            policy_id="POL-CUSTOM-1",
            name="Custom Cool Area Watch",
            metric="minimum_temperature",
            operator="<=",
            threshold=15.0,
            severity="WATCH",
        )
        ok, err = save_alert_policy(pol)
        assert ok is True
        assert err is None

        saved = get_alert_policies()
        assert any(p.policy_id == "POL-CUSTOM-1" for p in saved)

    def test_update_existing_policy(self):
        pol = AlertPolicy(
            policy_id="POL-CRIT-HEAT",
            name="Updated Critical Temperature Alert",
            metric="mean_temperature",
            operator=">=",
            threshold=42.0,
            severity="CRITICAL",
        )
        ok, err = save_alert_policy(pol)
        assert ok is True

        saved = get_alert_policies()
        updated = next(p for p in saved if p.policy_id == "POL-CRIT-HEAT")
        assert updated.threshold == 42.0
        assert updated.name == "Updated Critical Temperature Alert"

    def test_save_duplicate_equivalent_policy_rejected(self):
        # Create a policy with same condition as default critical heat
        dup = AlertPolicy(
            policy_id="POL-DUP",
            name="Another Critical Heat Rule",
            metric="mean_temperature",
            operator=">=",
            threshold=40.0,
            severity="CRITICAL",
            applies_to="all",
        )
        ok, err = save_alert_policy(dup)
        assert ok is False
        assert "equivalent policy already exists" in err.lower()

    def test_capacity_limit_enforced(self):
        # Fill store up to MAX_ALERT_POLICIES
        for i in range(MAX_ALERT_POLICIES):
            pol = AlertPolicy(
                policy_id=f"POL-FILL-{i}",
                name=f"Policy {i}",
                metric="mean_temperature",
                operator=">=",
                threshold=float(i + 1),
                severity="INFO",
                applies_to=f"Zone {i}",
            )
            save_alert_policy(pol)

        # 21st policy should fail
        overflow_pol = AlertPolicy(
            policy_id="POL-OVERFLOW",
            name="Overflow Policy",
            metric="mean_temperature",
            operator=">=",
            threshold=99.0,
            severity="INFO",
            applies_to="Zone Overflow",
        )
        ok, err = save_alert_policy(overflow_pol)
        assert ok is False
        assert "maximum policy limit" in err.lower()

    def test_delete_policy(self):
        ok, err = delete_alert_policy("POL-CRIT-HEAT")
        assert ok is True
        assert err is None

        saved = get_alert_policies()
        assert not any(p.policy_id == "POL-CRIT-HEAT" for p in saved)

    def test_delete_non_existent_policy_fails(self):
        ok, err = delete_alert_policy("POL-DOES-NOT-EXIST")
        assert ok is False
        assert "not found" in err.lower()

    def test_toggle_policy_enabled(self):
        # Disable policy
        ok, _ = toggle_alert_policy("POL-CRIT-HEAT", enabled=False)
        assert ok is True
        pol = next(p for p in get_alert_policies() if p.policy_id == "POL-CRIT-HEAT")
        assert pol.enabled is False

        # Toggle back to true
        ok, _ = toggle_alert_policy("POL-CRIT-HEAT")
        assert ok is True
        pol = next(p for p in get_alert_policies() if p.policy_id == "POL-CRIT-HEAT")
        assert pol.enabled is True

    def test_toggle_non_existent_policy_fails(self):
        ok, err = toggle_alert_policy("POL-UNKNOWN")
        assert ok is False
        assert "not found" in err.lower()

    def test_reset_default_policies(self):
        # Delete everything
        for p in get_alert_policies():
            delete_alert_policy(p.policy_id)
        assert len(get_alert_policies()) == 0

        # Reset
        reset_default_alert_policies()
        assert len(get_alert_policies()) == len(get_default_alert_policies())

    def test_from_dict_and_to_dict(self):
        d = {
            "policy_id": "P-TEST",
            "name": "Test Name",
            "metric": "tile_count",
            "operator": "<=",
            "threshold": 10.0,
            "severity": "ELEVATED",
            "applies_to": "all",
            "enabled": True,
        }
        pol = AlertPolicy.from_dict(d)
        assert pol.metric == "tile_count"
        assert pol.threshold == 10.0
        assert pol.to_dict()["policy_id"] == "P-TEST"

    def test_auto_generated_policy_id_when_empty(self):
        pol = AlertPolicy(
            policy_id="",
            name="No ID Policy",
            metric="tile_count",
            operator=">=",
            threshold=10.0,
        )
        ok, _ = save_alert_policy(pol)
        assert ok is True
        saved = get_alert_policies()
        no_id_pols = [p for p in saved if p.name == "No ID Policy"]
        assert len(no_id_pols) == 1
        assert no_id_pols[0].policy_id.startswith("POL-")

    def test_case_insensitivity_in_from_dict(self):
        d = {
            "name": "Case Test",
            "metric": "MEAN_TEMPERATURE",
            "severity": "critical",
            "operator": ">=",
            "threshold": "39.5",
        }
        pol = AlertPolicy.from_dict(d)
        assert pol.metric == "mean_temperature"
        assert pol.severity == "CRITICAL"
        assert pol.threshold == 39.5

    def test_null_threshold_fails_validation(self):
        d = {
            "name": "Null Thresh",
            "metric": "mean_temperature",
            "operator": ">=",
            "threshold": None,
        }
        is_valid, err = validate_alert_policy(d)
        assert is_valid is False
        assert "cannot be none" in err.lower()

    def test_supported_operators_and_metrics_constants(self):
        assert ">" in SUPPORTED_OPERATORS
        assert "<=" in SUPPORTED_OPERATORS
        assert "==" in SUPPORTED_OPERATORS
        assert "mean_temperature" in SUPPORTED_METRICS
        assert "tile_count" in SUPPORTED_METRICS
        assert "CRITICAL" in SUPPORTED_SEVERITIES

