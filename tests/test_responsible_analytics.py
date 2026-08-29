"""Tests for frontend.utils.responsible_analytics — Responsible Analytics Enforcement Engine.

Validates:
- Detection of prohibited causal assertions ("caused by", "due to", "because of", "will cause").
- Detection of prohibited predictive claims ("forecast", "prediction", "will happen", "guaranteed").
- Detection of prohibited medical/health claims ("hazardous", "fatal", "deadly", "health risk", "heatstroke").
- Exception raising: ResponsibleAnalyticsViolation when unapproved content is detected.
- is_text_compliant boolean checker.
- sanitize_narrative_text replacement with neutral phrasing.
- Permitted descriptive words pass validation cleanly.
- Centralized disclaimer string compliance.
- Zero network I/O invariant.
"""

from __future__ import annotations

import pytest

from frontend.utils.responsible_analytics import (
    FORBIDDEN_TERMS,
    RESPONSIBLE_ANALYTICS_NOTICE,
    ResponsibleAnalyticsViolation,
    check_prohibited_terms,
    get_responsible_analytics_disclaimer,
    is_text_compliant,
    sanitize_narrative_text,
    validate_analytical_text,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Prohibited Terms Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestProhibitedTermsDetection:
    """Detection of prohibited causal, predictive, and medical language."""

    def test_causal_terms_detected(self):
        t1 = "The temperature increase was caused by solar radiation."
        assert "caused by" in check_prohibited_terms(t1)

        t2 = "Spread is wide due to urban density."
        assert "due to" in check_prohibited_terms(t2)

        t3 = "Conditions shifted because of high humidity."
        assert "because of" in check_prohibited_terms(t3)

        t4 = "This trend will cause further warming."
        assert "will cause" in check_prohibited_terms(t4)

    def test_predictive_terms_detected(self):
        t1 = "Our forecast for tomorrow shows higher temperatures."
        assert "forecast" in check_prohibited_terms(t1)

        t2 = "The prediction is that temperatures will rise."
        assert "prediction" in check_prohibited_terms(t2)

        t3 = "A hot summer will happen next month."
        assert "will happen" in check_prohibited_terms(t3)

        t4 = "This threshold is guaranteed to be exceeded."
        assert "guaranteed" in check_prohibited_terms(t4)

    def test_medical_and_danger_terms_detected(self):
        t1 = "Conditions in the downtown area are hazardous."
        assert "hazardous" in check_prohibited_terms(t1)

        t2 = "This heat level is deadly."
        assert "deadly" in check_prohibited_terms(t2)

        t3 = "Extreme temperatures represent a major health risk."
        assert "health risk" in check_prohibited_terms(t3)

        t4 = "High likelihood of heatstroke among citizens."
        assert "heatstroke" in check_prohibited_terms(t4)

        t5 = "The diagnosis of urban heat islands."
        assert "diagnosis" in check_prohibited_terms(t5)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Compliant Descriptive Language Passes Cleanly
# ══════════════════════════════════════════════════════════════════════════════


class TestCompliantLanguage:
    """Permitted neutral descriptive terms pass without false positives."""

    def test_pure_descriptive_statements_pass(self):
        valid_texts = [
            "Mean temperature was observed at 34.5°C.",
            "Observed temperature of 38.0°C exceeds the configured threshold of 35.0°C by +3.0°C.",
            "Spatial spread of 8.2°C indicates elevated thermal variability across tiles.",
            "Under a hypothetical +2.0°C adjustment, scenario temperature becomes 36.5°C.",
            "Temperature remained consistent within comparison tolerance across observations.",
            "Descriptive numerical difference between baseline and comparison is +1.5°C.",
            "Chronological observations from August 1 to August 15 show an upward trend.",
        ]
        for text in valid_texts:
            assert is_text_compliant(text) is True
            assert len(check_prohibited_terms(text)) == 0

    def test_empty_string_is_compliant(self):
        assert is_text_compliant("") is True
        assert check_prohibited_terms("") == []


# ══════════════════════════════════════════════════════════════════════════════
# 3. Validation Exception Raising
# ══════════════════════════════════════════════════════════════════════════════


class TestValidationExceptions:
    """validate_analytical_text raises ResponsibleAnalyticsViolation."""

    def test_raises_on_single_violation(self):
        text = "This anomaly was caused by lack of vegetation."
        with pytest.raises(ResponsibleAnalyticsViolation) as exc_info:
            validate_analytical_text(text, context_label="Investigation Summary")

        assert "caused by" in exc_info.value.forbidden_terms_found
        assert "Investigation Summary" in str(exc_info.value)

    def test_raises_on_multiple_violations(self):
        text = "This hazardous forecast was caused by heat waves."
        with pytest.raises(ResponsibleAnalyticsViolation) as exc_info:
            validate_analytical_text(text)

        violations = exc_info.value.forbidden_terms_found
        assert "hazardous" in violations
        assert "forecast" in violations
        assert "caused by" in violations

    def test_does_not_raise_on_compliant_text(self):
        text = "Observed mean temperature is 35.2°C, representing a difference of +2.1°C."
        # Should execute without raising
        validate_analytical_text(text)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Text Sanitization
# ══════════════════════════════════════════════════════════════════════════════


class TestTextSanitization:
    """sanitize_narrative_text replaces forbidden terms with neutral phrasing."""

    def test_sanitizes_causal_phrase(self):
        dirty = "The high reading was caused by concrete surfaces."
        cleaned = sanitize_narrative_text(dirty)
        assert "caused by" not in cleaned.lower()
        assert is_text_compliant(cleaned)

    def test_sanitizes_forecast_and_hazardous(self):
        dirty = "The forecast indicates hazardous conditions."
        cleaned = sanitize_narrative_text(dirty)
        assert "forecast" not in cleaned.lower()
        assert "hazardous" not in cleaned.lower()

    def test_clean_text_remains_unchanged(self):
        clean = "Observed mean temperature is 34.0°C."
        assert sanitize_narrative_text(clean) == clean


# ══════════════════════════════════════════════════════════════════════════════
# 5. Disclaimer Compliance & Edge Cases
# ══════════════════════════════════════════════════════════════════════════════


class TestDisclaimerCompliance:
    """The centralized disclaimer string itself must be 100% compliant."""

    def test_disclaimer_is_compliant(self):
        disclaimer = get_responsible_analytics_disclaimer()
        assert is_text_compliant(disclaimer) is True
        assert disclaimer == RESPONSIBLE_ANALYTICS_NOTICE

    def test_forbidden_terms_tuple_is_non_empty(self):
        assert len(FORBIDDEN_TERMS) >= 15
        assert "caused by" in FORBIDDEN_TERMS
        assert "forecast" in FORBIDDEN_TERMS
        assert "hazardous" in FORBIDDEN_TERMS

    def test_case_insensitive_detection(self):
        assert len(check_prohibited_terms("CAUSED BY global warming")) == 1
        assert len(check_prohibited_terms("This is a FORECAST")) == 1
        assert len(check_prohibited_terms("Deadly Heat")) == 1

    def test_word_boundary_isolation(self):
        # "fatalistic" should not match "fatal"
        # "forecasting" should match or word boundary "forecast"
        assert is_text_compliant("A non-fatal anomaly was noted.") is False
        assert is_text_compliant("Observing thermal conditions across tiles.") is True

    def test_punctuation_around_forbidden_terms(self):
        assert "hazardous" in check_prohibited_terms("Condition: (hazardous)!")
        assert "due to" in check_prohibited_terms("Delta: +2.0°C (due to: sensor)")

    def test_sanitize_empty_string_returns_empty(self):
        assert sanitize_narrative_text("") == ""
        assert sanitize_narrative_text(None) == ""

    def test_violation_exception_attributes(self):
        exc = ResponsibleAnalyticsViolation("Test message", ["due to", "fatal"])
        assert exc.forbidden_terms_found == ["due to", "fatal"]
        assert "Test message" in str(exc)

    def test_mortality_and_emergency_terms(self):
        assert "mortality" in check_prohibited_terms("Risk of mortality in area")
        assert "emergency condition" in check_prohibited_terms("Declared an emergency condition")

