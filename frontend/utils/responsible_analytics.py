"""Centralized Responsible Analytics Enforcement Engine.

Enforces strict compliance with FortyGuard Responsible Analytics rules across all derived outputs.

Strict Invariants:
1. Rejects causal assertions ("caused by", "due to").
2. Rejects predictive certainty and forecasts ("forecast", "prediction", "will happen").
3. Rejects medical/public health classifications ("hazardous", "fatal", "deadly", "health risk").
4. Raises ResponsibleAnalyticsViolation when unapproved content is detected.
"""

from __future__ import annotations

import re
from typing import Sequence

RESPONSIBLE_ANALYTICS_NOTICE: str = (
    "Responsible Analytics Notice: All observations and derived metrics describe confirmed historical "
    "data points. They do not establish causation, predict future conditions, or make medical "
    "or scientific safety classifications."
)

FORBIDDEN_TERMS: tuple[str, ...] = (
    "caused by",
    "because of",
    "due to",
    "resulting from",
    "attributable to",
    "will cause",
    "forecast",
    "prediction",
    "will happen",
    "guaranteed",
    "projected outcome",
    "future certainty",
    "health risk",
    "fatal",
    "dangerous",
    "hazardous",
    "deadly",
    "casualty",
    "heatstroke",
    "diagnosis",
    "mortality",
    "emergency condition",
)


class ResponsibleAnalyticsViolation(Exception):
    """Raised when generated or exported text violates Responsible Analytics standards."""

    def __init__(self, message: str, forbidden_terms_found: list[str]) -> None:
        super().__init__(message)
        self.forbidden_terms_found = forbidden_terms_found


def check_prohibited_terms(text: str) -> list[str]:
    """Scan text for any prohibited causal, predictive, or medical terminology."""
    if not text:
        return []

    text_lower = text.lower()
    found: list[str] = []

    for term in FORBIDDEN_TERMS:
        # Use regex word boundary matching for single words, direct substring for multi-word phrases
        if " " in term:
            if term in text_lower:
                found.append(term)
        else:
            pattern = rf"\b{re.escape(term)}\b"
            if re.search(pattern, text_lower):
                found.append(term)

    return sorted(list(set(found)))


def is_text_compliant(text: str) -> bool:
    """Return True if text satisfies Responsible Analytics standards."""
    return len(check_prohibited_terms(text)) == 0


def validate_analytical_text(text: str, context_label: str = "Analytical Content") -> None:
    """Validate text against Responsible Analytics rules, raising ResponsibleAnalyticsViolation if violated."""
    violations = check_prohibited_terms(text)
    if violations:
        terms_str = ", ".join(f"'{t}'" for t in violations)
        raise ResponsibleAnalyticsViolation(
            f"Responsible Analytics Violation in {context_label}: prohibited terms detected ({terms_str}). "
            f"Outputs must remain strictly descriptive without causal, predictive, or medical claims.",
            forbidden_terms_found=violations,
        )


def sanitize_narrative_text(text: str) -> str:
    """Replace common accidental prohibited phrases with compliant descriptive terms."""
    if not text:
        return ""

    replacements: list[tuple[str, str]] = [
        ("caused by", "associated with observed"),
        ("because of", "alongside observed"),
        ("due to", "in the presence of"),
        ("will cause", "is associated with"),
        ("forecast", "analytical observation"),
        ("prediction", "scenario calculation"),
        ("hazardous", "elevated thermal"),
        ("dangerous", "elevated"),
        ("fatal", "extreme"),
        ("deadly", "extreme"),
        ("health risk", "thermal deviation"),
    ]

    cleaned = text
    for forbidden, replacement in replacements:
        pattern = re.compile(re.escape(forbidden), re.IGNORECASE)
        cleaned = pattern.sub(replacement, cleaned)

    return cleaned


def get_responsible_analytics_disclaimer() -> str:
    """Return standard centralized Responsible Analytics disclaimer."""
    return RESPONSIBLE_ANALYTICS_NOTICE
