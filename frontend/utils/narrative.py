"""Pure Evidence-Backed Analytical Narrative Engine.

Rules & Invariants:
1. Every statement references confirmed numeric observations and calculated deltas.
2. Strictly neutral language — NEVER makes causal assertions ('caused by', 'due to').
3. NEVER makes medical, public health, or human risk classifications ('hazardous', 'fatal').
4. Always includes transparent disclosures of missing data limitations and analytical disclaimers.
"""

from __future__ import annotations

from typing import Any, Mapping

from frontend.utils.decision_intelligence import RESPONSIBLE_ANALYTICS_DISCLAIMER


def generate_comparison_narrative(comparison_result: Mapping[str, Any]) -> dict[str, Any]:
    """Generate a structured, evidence-backed narrative from comparison results."""
    increased = comparison_result.get("increased", [])
    decreased = comparison_result.get("decreased", [])
    unchanged = comparison_result.get("unchanged", [])
    missing = comparison_result.get("missing", [])

    b_id = comparison_result.get("baseline_id", "Baseline")
    c_id = comparison_result.get("comparison_id", "Comparison")
    b_date = comparison_result.get("baseline_date", "")
    c_date = comparison_result.get("comparison_date", "")

    # ── Section 1: What Changed? ──
    changed_statements: list[str] = []

    for m in increased:
        label = m.label if hasattr(m, "label") else m.get("label")
        b_val = m.baseline_value if hasattr(m, "baseline_value") else m.get("baseline_value")
        c_val = m.comparison_value if hasattr(m, "comparison_value") else m.get("comparison_value")
        delta = m.delta if hasattr(m, "delta") else m.get("delta")
        unit = m.unit if hasattr(m, "unit") else m.get("unit", "")
        pct = m.percent_change if hasattr(m, "percent_change") else m.get("percent_change")

        pct_str = f" (+{pct:.1f}%)" if pct is not None else ""
        unit_str = f" {unit}" if unit else ""
        delta_str = f"+{delta:.2f}" if delta is not None and delta > 0 else f"{delta:.2f}"
        changed_statements.append(
            f"{label} increased from {b_val:.2f}{unit_str} to {c_val:.2f}{unit_str}, representing a difference of {delta_str}{unit_str}{pct_str}."
        )

    for m in decreased:
        label = m.label if hasattr(m, "label") else m.get("label")
        b_val = m.baseline_value if hasattr(m, "baseline_value") else m.get("baseline_value")
        c_val = m.comparison_value if hasattr(m, "comparison_value") else m.get("comparison_value")
        delta = m.delta if hasattr(m, "delta") else m.get("delta")
        unit = m.unit if hasattr(m, "unit") else m.get("unit", "")
        pct = m.percent_change if hasattr(m, "percent_change") else m.get("percent_change")

        pct_str = f" ({pct:.1f}%)" if pct is not None else ""
        unit_str = f" {unit}" if unit else ""
        changed_statements.append(
            f"{label} decreased from {b_val:.2f}{unit_str} to {c_val:.2f}{unit_str}, representing a difference of {delta:.2f}{unit_str}{pct_str}."
        )

    if not changed_statements:
        what_changed = "No measurable changes were detected beyond the configured tolerance thresholds for available metrics."
    else:
        what_changed = " ".join(changed_statements)

    # ── Section 2: What Stayed Similar? ──
    similar_statements: list[str] = []
    for m in unchanged:
        label = m.label if hasattr(m, "label") else m.get("label")
        b_val = m.baseline_value if hasattr(m, "baseline_value") else m.get("baseline_value")
        c_val = m.comparison_value if hasattr(m, "comparison_value") else m.get("comparison_value")
        unit = m.unit if hasattr(m, "unit") else m.get("unit", "")
        unit_str = f" {unit}" if unit else ""
        similar_statements.append(
            f"{label} remained within comparison tolerance (Baseline: {b_val:.2f}{unit_str}, Comparison: {c_val:.2f}{unit_str})."
        )

    if not similar_statements:
        what_stayed_similar = "All evaluated metrics exhibited measurable changes beyond the baseline comparison tolerance."
    else:
        what_stayed_similar = " ".join(similar_statements)

    # ── Section 3: Data Limitations ──
    missing_statements: list[str] = []
    for m in missing:
        label = m.label if hasattr(m, "label") else m.get("label")
        missing_statements.append(
            f"{label} could not be compared because one or both analysis records lacked this specific metric."
        )

    if not missing_statements:
        data_limitations = "All candidate comparative metrics were present and successfully evaluated in both analyses."
    else:
        data_limitations = " ".join(missing_statements)

    headline = str(comparison_result.get("headline") or "Comparative Analysis")

    return {
        "headline": headline,
        "what_changed": what_changed,
        "what_stayed_similar": what_stayed_similar,
        "data_limitations": data_limitations,
        "disclaimer": RESPONSIBLE_ANALYTICS_DISCLAIMER,
        "baseline_summary": f"Baseline: {b_id} ({b_date})",
        "comparison_summary": f"Comparison: {c_id} ({c_date})",
    }
