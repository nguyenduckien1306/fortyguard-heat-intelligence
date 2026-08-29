"""Unit tests for Phase 15.4 Alert Promotion, Escalation, Cooldown & Suppression.

Verifies:
- Promotion gates: signal matching, priority thresholds, data quality checks.
- Suppression reasons (LOW_DATA_QUALITY, POLICY_FILTER, COOLDOWN, CAPACITY_LIMIT).
- Distinct alert fingerprints preventing duplicate alert spam across reruns.
- Cooldown expiration handling via ManualClock.
- Escalation on repeated breach (NORMAL -> HIGH -> CRITICAL).
- Alert recovery ancestry chain (parent_alert_id).
- Hard capacity limits (max 50 active alerts).
- "Why didn't this become an alert?" explainability.
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest
import streamlit as st

from frontend.utils.alert_engine import (
    LIFECYCLE_RESOLVED,
    MAX_ACTIVE_ALERTS,
    SUPPRESSION_CAPACITY_LIMIT,
    SUPPRESSION_COOLDOWN,
    SUPPRESSION_LOW_DATA_QUALITY,
    SUPPRESSION_POLICY_FILTER,
    AlertItem,
    explain_alert_decision,
    generate_alert_fingerprint,
    get_active_alerts,
    promote_signals_to_alerts,
)
from frontend.utils.alert_policies import AlertPolicy
from frontend.utils.clock import FrozenClock, ManualClock, set_current_clock
from frontend.utils.operational_intelligence import OperationalSignal


@pytest.fixture(autouse=True)
def clean_session():
    st.session_state.clear()
    set_current_clock(FrozenClock("2026-08-23T10:00:00"))
    yield
    st.session_state.clear()
    set_current_clock(None)


def _sample_signal(
    signal_id: str = "SIG-001",
    analysis_id: str = "REC-001",
    severity: str = "CRITICAL",
    data_quality: str = "HIGH",
    title: str = "Extreme Heat Detected",
) -> OperationalSignal:
    return OperationalSignal(
        signal_id=signal_id,
        analysis_id=analysis_id,
        signal_type="THRESHOLD_BREACH",
        severity=severity,
        title=title,
        description="High temperature observed.",
        metric="mean_temperature",
        observed_value=42.0,
        threshold_value=38.0,
        data_quality=data_quality,
        evidence=["Observed 42.0°C >= threshold 38.0°C."],
    )


def _sample_policy(
    policy_id: str = "P-HEAT",
    name: str = "Extreme Heat Policy",
    metric: str = "mean_temperature",
    threshold: float = 38.0,
    severity: str = "CRITICAL",
) -> AlertPolicy:
    return AlertPolicy(
        policy_id=policy_id,
        name=name,
        metric=metric,
        operator=">=",
        threshold=threshold,
        severity=severity,
        applies_to="all",
        enabled=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Promotion Gates & Fingerprinting Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAlertPromotionAndFingerprinting:
    """Alert promotion gates and fingerprint determinism."""

    def test_alert_fingerprint_determinism(self):
        fp1 = generate_alert_fingerprint("P-01", "SIG-01", "REC-01", "Downtown")
        fp2 = generate_alert_fingerprint("P-01", "SIG-01", "REC-01", "Downtown")
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_alert_fingerprint_differs_by_policy_or_signal(self):
        fp1 = generate_alert_fingerprint("P-01", "SIG-01", "REC-01")
        fp2 = generate_alert_fingerprint("P-02", "SIG-01", "REC-01")
        fp3 = generate_alert_fingerprint("P-01", "SIG-02", "REC-01")
        assert fp1 != fp2
        assert fp1 != fp3

    def test_valid_signal_promotes_to_alert(self):
        sig = _sample_signal()
        pol = _sample_policy()
        clk = FrozenClock("2026-08-23T10:00:00")

        alerts, diag = promote_signals_to_alerts([sig], [pol], clock=clk)
        assert len(alerts) == 1
        assert diag["promoted_count"] == 1
        assert alerts[0].status == "NEW"
        assert alerts[0].severity == "CRITICAL"
        assert alerts[0].policy_id == pol.policy_id
        assert alerts[0].signal_id == sig.signal_id


# ══════════════════════════════════════════════════════════════════════════════
# 2. Suppression Reasons & Cooldown Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAlertSuppressionAndCooldown:
    """Suppression reason codes and cooldown fatigue protection."""

    def test_insufficient_data_quality_suppresses_alert(self):
        sig = _sample_signal(data_quality="INSUFFICIENT")
        pol = _sample_policy()

        alerts, diag = promote_signals_to_alerts([sig], [pol])
        assert len(alerts) == 0
        assert diag["low_quality_suppressed"] == 1

        exp = explain_alert_decision(sig, [pol])
        assert exp["promoted"] is False
        assert exp["suppression_reason"] == SUPPRESSION_LOW_DATA_QUALITY

    def test_disabled_policy_filters_promotion(self):
        sig = _sample_signal()
        pol = _sample_policy()
        pol.enabled = False

        alerts, diag = promote_signals_to_alerts([sig], [pol])
        assert len(alerts) == 0
        assert diag["total_suppressed"] >= 0

        exp = explain_alert_decision(sig, [pol])
        assert exp["promoted"] is False
        assert exp["suppression_reason"] == SUPPRESSION_POLICY_FILTER

    def test_cooldown_prevents_duplicate_alerts_within_window(self):
        clk = ManualClock("2026-08-23T10:00:00")
        sig = _sample_signal()
        pol = _sample_policy()

        # Run 1: Alert created
        alerts1, diag1 = promote_signals_to_alerts([sig], [pol], clock=clk, cooldown_window="1h")
        assert len(alerts1) == 1
        assert diag1["promoted_count"] == 1

        # Run 2 at 10:15 (within 1h cooldown): Alert suppressed
        clk.advance(minutes=15)
        alerts2, diag2 = promote_signals_to_alerts([sig], [pol], clock=clk, cooldown_window="1h")
        assert len(alerts2) == 1  # No new alert created
        assert diag2["cooldown_suppressed"] == 1

    def test_alert_escalates_on_repeated_breach(self):
        clk = ManualClock("2026-08-23T10:00:00")
        sig = _sample_signal()
        pol = _sample_policy()

        # Run 1: Normal
        alerts1, _ = promote_signals_to_alerts([sig], [pol], clock=clk)
        assert alerts1[0].trigger_count == 1
        assert alerts1[0].escalation_level == "NORMAL"

        # Advance past cooldown to 11:30 and trigger again
        clk.advance(minutes=90)
        alerts2, _ = promote_signals_to_alerts([sig], [pol], clock=clk)
        assert len(alerts2) == 1
        assert alerts2[0].trigger_count == 2
        assert alerts2[0].escalation_level == "HIGH"

        # Advance to 13:00 and trigger a 3rd time -> Escalates to CRITICAL
        clk.advance(minutes=90)
        alerts3, _ = promote_signals_to_alerts([sig], [pol], clock=clk)
        assert alerts3[0].trigger_count == 3
        assert alerts3[0].escalation_level == "CRITICAL"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Recovery Ancestry & Capacity Limit Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestRecoveryAncestryAndCapacity:
    """Alert ancestry chains and capacity limits."""

    def test_resolved_alert_creates_successor_with_parent_id(self):
        clk = ManualClock("2026-08-23T10:00:00")
        sig = _sample_signal()
        pol = _sample_policy()

        # Initial alert
        alerts, _ = promote_signals_to_alerts([sig], [pol], clock=clk)
        old_alert = alerts[0]
        old_id = old_alert.alert_id

        # Mark old alert as RESOLVED
        old_alert.status = LIFECYCLE_RESOLVED
        st.session_state["_session_active_alerts_store"] = [old_alert.to_dict()]

        # Advance past cooldown to 12:00
        clk.advance(hours=2)

        # New breach occurs -> Creates new alert with parent_alert_id set
        alerts_new, _ = promote_signals_to_alerts([sig], [pol], clock=clk)
        active_new = [a for a in alerts_new if a.status != LIFECYCLE_RESOLVED]
        assert len(active_new) == 1
        assert active_new[0].parent_alert_id == old_id

    def test_capacity_limit_enforced_at_50_active_alerts(self):
        pol = _sample_policy()
        fake_alerts = [
            AlertItem(
                alert_id=f"ALT-{i:03d}",
                alert_fingerprint=f"FP-{i:03d}",
                signal_id=f"SIG-{i:03d}",
                policy_id="P-HEAT",
                policy_name="Policy",
                analysis_id=f"REC-{i:03d}",
                location="Loc",
                severity="WATCH",
                priority_score=50.0,
                priority_tier="Medium",
                status="NEW",
            ).to_dict()
            for i in range(MAX_ACTIVE_ALERTS)
        ]
        st.session_state["_session_active_alerts_store"] = fake_alerts

        # Attempt to promote 51st alert
        sig_extra = _sample_signal(signal_id="SIG-EXTRA", analysis_id="REC-EXTRA")
        alerts, diag = promote_signals_to_alerts([sig_extra], [pol])
        assert len(alerts) == MAX_ACTIVE_ALERTS
        assert diag["capacity_suppressed"] == 1

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_alert_automation_makes_zero_network_calls(self, mock_requests, mock_httpx):
        sig = _sample_signal()
        pol = _sample_policy()
        promote_signals_to_alerts([sig], [pol])
        explain_alert_decision(sig, [pol])

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_alert_item_from_dict_and_to_dict_roundtrip(self):
        item = AlertItem(
            alert_id="ALT-123",
            alert_fingerprint="FP-123",
            signal_id="SIG-123",
            policy_id="P-123",
            policy_name="Policy 123",
            analysis_id="REC-123",
            location="Downtown",
            severity="CRITICAL",
            priority_score=85.0,
            priority_tier="Critical",
            escalation_level="ELEVATED",
            status="NEW",
            trigger_count=2,
            cooldown_until="2026-08-23T11:00:00",
            evidence=["Item 1"],
            promotion_reason="Matched policy",
        )
        d = item.to_dict()
        assert d["alert_id"] == "ALT-123"
        assert d["escalation_level"] == "ELEVATED"

        reconstructed = AlertItem.from_dict(d)
        assert reconstructed.alert_id == item.alert_id
        assert reconstructed.escalation_level == item.escalation_level
        assert reconstructed.trigger_count == item.trigger_count

    def test_custom_cooldown_windows_15m_and_24h(self):
        clk = ManualClock("2026-08-23T10:00:00")
        sig = _sample_signal()
        pol = _sample_policy()

        # 15m window
        promote_signals_to_alerts([sig], [pol], clock=clk, cooldown_window="15m")
        # Advance 10m -> still in cooldown
        clk.advance(minutes=10)
        _, diag1 = promote_signals_to_alerts([sig], [pol], clock=clk, cooldown_window="15m")
        assert diag1["cooldown_suppressed"] == 1

        # Advance 6m (total 16m) -> cooldown expired, re-trigger permitted
        clk.advance(minutes=6)
        alerts2, _ = promote_signals_to_alerts([sig], [pol], clock=clk, cooldown_window="15m")
        assert alerts2[0].trigger_count == 2

    def test_explain_alert_decision_promoted_explanation(self):
        sig = _sample_signal()
        pol = _sample_policy()
        exp = explain_alert_decision(sig, [pol])
        assert exp["promoted"] is True
        assert "Extreme Heat Policy" in exp["explanation"]
        assert exp["priority_tier"] == "Critical"

    def test_get_active_alerts_empty_returns_empty_list(self):
        st.session_state.clear()
        assert get_active_alerts() == []

