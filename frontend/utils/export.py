"""Local analysis summary export utilities.

Generates structured JSON, formatted text, and analytical brief export summaries
of application-derived and request metadata. Strictly scrubs all internal
credentials, headers, and signed S3 URLs through recursive deep sanitization.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from frontend.utils.operational_intelligence import (
    _determine_record_data_quality,
    _extract_metric_val,
    _safe_float,
)


# ──────────────────────────────────────────────────────────────────────────────
# Recursive deep sanitization
# ──────────────────────────────────────────────────────────────────────────────

# Keys whose values should be redacted. Normalized (lowercase, dashes converted to underscores).
_REDACT_EXACT_KEYS: frozenset[str] = frozenset({
    "api_key",
    "apikey",
    "authorization",
    "download_link",
    "signed_url",
    "secret",
    "secret_key",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "session_token",
})

# Key substrings that indicate credential-like fields (normalized with underscores).
_REDACT_SUBSTRING_PATTERNS: tuple[str, ...] = (
    "api_key",
    "secret",
    "password",
    "download_link",
    "signed_url",
)

_REDACT_VALUE = "[REDACTED]"
_REDACT_URL_VALUE = "[REDACTED_SECURE_SIGNED_URL]"


def _should_redact_key(key: str) -> bool:
    """Determine if a dictionary key represents a credential-like field.

    Uses normalized matching (lowercase, dashes to underscores) against
    known exact keys and substring patterns.
    """
    normalized_key = key.lower().replace("-", "_").strip()

    # Exact match
    if normalized_key in _REDACT_EXACT_KEYS:
        return True

    # Substring match for credential patterns
    for pattern in _REDACT_SUBSTRING_PATTERNS:
        if pattern in normalized_key:
            return True

    return False


def _deep_sanitize(obj: Any) -> Any:
    """Recursively sanitize a data structure, redacting credential-like values.

    Walks nested dicts and lists. Redacts values whose keys match known
    credential patterns. Does NOT modify the original object.
    """
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if _should_redact_key(str(k)):
                # Determine redaction label based on value type
                if isinstance(v, str) and ("s3" in v.lower() or "http" in v.lower()):
                    result[k] = _REDACT_URL_VALUE
                else:
                    result[k] = _REDACT_VALUE
            elif isinstance(v, str) and (
                "X-Amz-Signature=" in v
                or "X-Amz-Credential=" in v
                or "Signature=" in v
                or "token=" in v.lower()
            ):
                result[k] = _REDACT_URL_VALUE
            else:
                result[k] = _deep_sanitize(v)
        return result
    elif isinstance(obj, list):
        return [_deep_sanitize(item) for item in obj]
    elif isinstance(obj, str):
        if "X-Amz-Signature=" in obj or "X-Amz-Credential=" in obj or "Signature=" in obj:
            return _REDACT_URL_VALUE
        return obj
    else:
        return obj


# ──────────────────────────────────────────────────────────────────────────────
# Export dict generation
# ──────────────────────────────────────────────────────────────────────────────


def generate_analysis_export_dict(
    analysis_entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a clean, sanitized dictionary of the analysis metadata and derived metrics."""
    clean: dict[str, Any] = {
        "analysis_type": analysis_entry.get("analysis_type", "Unknown"),
        "activity_id": analysis_entry.get("activity_id", "N/A"),
        "status": analysis_entry.get("status", "Unknown"),
        "label": analysis_entry.get("label", "N/A"),
        "created_at": analysis_entry.get("created_at", "N/A"),
        "updated_at": analysis_entry.get("updated_at", "N/A"),
    }

    if "request_params" in analysis_entry and isinstance(analysis_entry["request_params"], Mapping):
        clean["request_parameters"] = _deep_sanitize(dict(analysis_entry["request_params"]))

    if "metrics_summary" in analysis_entry and isinstance(analysis_entry["metrics_summary"], Mapping):
        clean["derived_metrics"] = _deep_sanitize(dict(analysis_entry["metrics_summary"]))

    clean["export_note"] = "Generated locally by FortyGuard Heat Intelligence platform."
    return clean


def generate_analysis_export_json(
    analysis_entry: Mapping[str, Any],
) -> str:
    """Serialize the sanitized analysis summary as formatted JSON."""
    data = generate_analysis_export_dict(analysis_entry)
    return json.dumps(data, indent=2)


def generate_analysis_export_text(
    analysis_entry: Mapping[str, Any],
) -> str:
    """Generate a clean, human-readable plain text analysis summary."""
    data = generate_analysis_export_dict(analysis_entry)
    lines: list[str] = [
        "=" * 50,
        "FORTYGUARD HEAT INTELLIGENCE — ANALYSIS SUMMARY",
        "=" * 50,
        f"Analysis Type : {data['analysis_type']}",
        f"Activity ID   : {data['activity_id']}",
        f"Status        : {data['status']}",
        f"Label         : {data['label']}",
        f"Created At    : {data['created_at']}",
        "-" * 50,
    ]

    req = data.get("request_parameters")
    if req:
        lines.append("REQUEST PARAMETERS:")
        for k, v in req.items():
            lines.append(f"  • {k}: {v}")
        lines.append("-" * 50)

    metrics = data.get("derived_metrics")
    if metrics:
        lines.append("DERIVED METRICS:")
        for k, v in metrics.items():
            lines.append(f"  • {k}: {v}")
        lines.append("-" * 50)

    lines.append(data.get("export_note", ""))
    lines.append("=" * 50)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Analytical brief export
# ──────────────────────────────────────────────────────────────────────────────


def generate_analytical_brief(
    analysis_entry: Mapping[str, Any],
    insights: Sequence[Any] | None = None,
    comparison: Mapping[str, Any] | None = None,
) -> str:
    """Generate an analytical brief text export including derived insights.

    Args:
        analysis_entry: Session history entry dict.
        insights: List of Insight objects (from insights.py).
        comparison: Optional comparison result dict.

    Returns:
        A formatted text brief, fully scrubbed of credentials.
    """
    data = generate_analysis_export_dict(analysis_entry)
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD HEAT INTELLIGENCE — ANALYTICAL BRIEF",
        "=" * 60,
        "",
        f"Analysis Type : {data['analysis_type']}",
        f"Activity ID   : {data['activity_id']}",
        f"Status        : {data['status']}",
        f"Label         : {data['label']}",
        f"Created At    : {data['created_at']}",
        "",
        "-" * 60,
    ]

    # Request parameters
    req = data.get("request_parameters")
    if req:
        lines.append("")
        lines.append("REQUEST PARAMETERS:")
        for k, v in req.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("-" * 60)

    # Derived metrics
    metrics = data.get("derived_metrics")
    if metrics:
        lines.append("")
        lines.append("DERIVED METRICS:")
        for k, v in metrics.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("-" * 60)

    # Analytical insights
    if insights:
        lines.append("")
        lines.append("ANALYTICAL INSIGHTS:")
        lines.append("(Descriptive calculations derived from API data;")
        lines.append(" not additional FortyGuard classifications.)")
        lines.append("")
        for ins in insights:
            sev = getattr(ins, "severity", None)
            sev_str = sev.value if sev else "INFO"
            title = getattr(ins, "title", "Insight")
            summary = getattr(ins, "summary", "")
            evidence = getattr(ins, "evidence", "")
            line = f"  [{sev_str}] {title}: {summary}"
            if evidence:
                line += f"\n         Evidence: {evidence}"
            lines.append(line)
        lines.append("")
        lines.append("-" * 60)

    # Comparison information
    if comparison and comparison.get("is_valid"):
        lines.append("")
        lines.append("COMPARISON ANALYSIS:")
        lines.append(f"  Baseline (A): {comparison.get('analysis_a_label', 'A')}")
        lines.append(f"  Comparison (B): {comparison.get('analysis_b_label', 'B')}")
        lines.append("")
        for m in comparison.get("compared_metrics", []):
            interp = m.get("interpretation", "")
            lines.append(f"  {m.get('label', '')}: {m.get('diff_formatted', '')} — {interp}")
        lines.append("")
        lines.append("-" * 60)

    lines.append("")
    lines.append("NOTE: This analytical brief was generated locally by the")
    lines.append("FortyGuard Heat Intelligence platform. All insights are")
    lines.append("deterministic derivations from confirmed API data.")
    lines.append("=" * 60)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Raw result sanitization for developer inspection
# ──────────────────────────────────────────────────────────────────────────────


def sanitize_raw_result_for_inspection(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Sanitize raw provider payload for developer inspection.

    Recursively walks the structure and redacts any credential-like keys
    so that signed URLs, API keys, and tokens never reach the UI text.
    """
    if not result:
        return {}

    return _deep_sanitize(dict(result))


# ──────────────────────────────────────────────────────────────────────────────
# Phase 13 Comparison Export Utilities
# ──────────────────────────────────────────────────────────────────────────────


def generate_comparison_json(
    comparison_data: Mapping[str, Any],
    narrative: Mapping[str, Any] | None = None,
) -> str:
    """Generate a clean, sanitized JSON export string for a comparison result."""
    clean_comp = _deep_sanitize(dict(comparison_data))

    # Normalize metrics if ComparisonMetric instances
    raw_metrics = clean_comp.get("metrics") or []
    normalized_metrics = []
    for m in raw_metrics:
        if hasattr(m, "to_dict"):
            normalized_metrics.append(m.to_dict())
        elif isinstance(m, dict):
            normalized_metrics.append(m)
    clean_comp["metrics"] = normalized_metrics

    # Remove non-serializable objects
    clean_comp.pop("available_metrics", None)
    clean_comp.pop("increased", None)
    clean_comp.pop("decreased", None)
    clean_comp.pop("unchanged", None)
    clean_comp.pop("missing", None)

    export_dict: dict[str, Any] = {
        "export_type": "FORTYGUARD_COMPARATIVE_ANALYSIS",
        "comparison": clean_comp,
    }
    if narrative:
        export_dict["narrative"] = _deep_sanitize(dict(narrative))

    return json.dumps(export_dict, indent=2)


def generate_comparison_txt(
    comparison_data: Mapping[str, Any],
    narrative: Mapping[str, Any] | None = None,
) -> str:
    """Generate a formatted plain text comparison export."""
    clean_comp = _deep_sanitize(dict(comparison_data))
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD HEAT INTELLIGENCE — COMPARATIVE ANALYSIS EXPORT",
        "=" * 60,
        f"Headline: {clean_comp.get('headline', 'N/A')}",
        "",
        f"Baseline Analysis   : {clean_comp.get('baseline_id', 'N/A')} ({clean_comp.get('baseline_location', 'N/A')} - {clean_comp.get('baseline_date', 'N/A')})",
        f"Comparison Analysis : {clean_comp.get('comparison_id', 'N/A')} ({clean_comp.get('comparison_location', 'N/A')} - {clean_comp.get('comparison_date', 'N/A')})",
        "",
        "-" * 60,
        "METRIC COMPARISONS:",
        "-" * 60,
    ]

    metrics = clean_comp.get("metrics") or []
    for m in metrics:
        label = m.label if hasattr(m, "label") else m.get("label", "Metric")
        unit = m.unit if hasattr(m, "unit") else m.get("unit", "")
        b_val = m.baseline_value if hasattr(m, "baseline_value") else m.get("baseline_value")
        c_val = m.comparison_value if hasattr(m, "comparison_value") else m.get("comparison_value")
        delta = m.delta if hasattr(m, "delta") else m.get("delta")
        interp = m.interpretation if hasattr(m, "interpretation") else m.get("interpretation", "")
        avail = m.available if hasattr(m, "available") else m.get("available", True)

        if not avail:
            lines.append(f"  {label}: [Insufficient Data / Metric Missing]")
        else:
            delta_str = f"+{delta:.2f}" if delta is not None and delta > 0 else (f"{delta:.2f}" if delta is not None else "N/A")
            unit_str = f" {unit}" if unit else ""
            lines.append(f"  {label}: Baseline={b_val}{unit_str} | Comparison={c_val}{unit_str} | Δ={delta_str}{unit_str}")
            lines.append(f"    Observation: {interp}")

    if narrative:
        clean_narrative = _deep_sanitize(dict(narrative))
        lines.append("")
        lines.append("-" * 60)
        lines.append("EVIDENCE-BACKED NARRATIVE:")
        lines.append("-" * 60)
        lines.append(f"What Changed:\n  {clean_narrative.get('what_changed', '')}")
        lines.append(f"\nWhat Stayed Similar:\n  {clean_narrative.get('what_stayed_similar', '')}")
        lines.append(f"\nData Limitations:\n  {clean_narrative.get('data_limitations', '')}")

    lines.append("")
    lines.append("-" * 60)
    lines.append("RESPONSIBLE ANALYTICS:")
    lines.append(clean_comp.get("disclaimer", "Descriptive calculations derived from confirmed analysis records."))
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_comparison_brief(
    comparison_data: Mapping[str, Any],
    narrative: Mapping[str, Any] | None = None,
) -> str:
    """Generate a formal Analytical Comparison Brief."""
    clean_comp = _deep_sanitize(dict(comparison_data))
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD ANALYTICAL COMPARISON BRIEF",
        "=" * 60,
        "",
        "BASELINE",
        "---------",
        f"Analysis ID : {clean_comp.get('baseline_id', 'N/A')}",
        f"Location    : {clean_comp.get('baseline_location', 'N/A')}",
        f"Date        : {clean_comp.get('baseline_date', 'N/A')}",
        "",
        "COMPARISON",
        "----------",
        f"Analysis ID : {clean_comp.get('comparison_id', 'N/A')}",
        f"Location    : {clean_comp.get('comparison_location', 'N/A')}",
        f"Date        : {clean_comp.get('comparison_date', 'N/A')}",
        "",
        "OBSERVED CHANGES",
        "----------------",
    ]

    if narrative:
        clean_narrative = _deep_sanitize(dict(narrative))
        lines.append(f"{clean_narrative.get('what_changed', 'None observed.')}")
        lines.append("")
        lines.append("CONSISTENT METRICS")
        lines.append("------------------")
        lines.append(f"{clean_narrative.get('what_stayed_similar', 'None.')}")
        lines.append("")
        lines.append("DATA LIMITATIONS")
        lines.append("----------------")
        lines.append(f"{clean_narrative.get('data_limitations', 'None.')}")
    else:
        lines.append(f"{clean_comp.get('headline', '')}")

    lines.append("")
    lines.append("METRIC DETAILS")
    lines.append("--------------")
    metrics = clean_comp.get("metrics") or []
    for m in metrics:
        label = m.label if hasattr(m, "label") else m.get("label", "Metric")
        ev = m.evidence if hasattr(m, "evidence") else m.get("evidence", "")
        lines.append(f"* {label}: {ev}")

    lines.append("")
    lines.append("RESPONSIBLE ANALYTICS DISCLAIMER")
    lines.append("--------------------------------")
    lines.append(clean_comp.get("disclaimer", "Descriptive calculations only."))
    lines.append("=" * 60)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 14 Investigation Brief Export
# ──────────────────────────────────────────────────────────────────────────────


def generate_investigation_brief(
    signal: Any,
    record: Any,
    historical_context: Sequence[Any] | None = None,
    scenario: Any | None = None,
    format: str = "brief",
) -> str:
    """Generate a sanitized formal Investigation Brief.

    Args:
        signal: OperationalSignal, InvestigationItem, AlertItem, or dict.
        record: AnalysisRecord instance or dict.
        historical_context: Optional list of related records or timeline events.
        scenario: Optional ScenarioComparison instance or dict.
        format: 'brief' (Markdown/Text), 'json', or 'txt'.

    Returns:
        Recursively sanitized investigation brief string.
    """
    sig_dict = _deep_sanitize(signal.to_dict() if hasattr(signal, "to_dict") else dict(signal))
    rec_dict = _deep_sanitize(record.to_dict() if hasattr(record, "to_dict") else (dict(record) if record else {}))
    scen_dict = _deep_sanitize(scenario.to_dict() if hasattr(scenario, "to_dict") else (dict(scenario) if scenario else {}))

    # Check for embedded source_signal or evidence_bundle
    src_sig = sig_dict.get("source_signal") if isinstance(sig_dict.get("source_signal"), Mapping) else {}
    ev_bundle = sig_dict.get("evidence_bundle") if isinstance(sig_dict.get("evidence_bundle"), Mapping) else {}
    ev_items = ev_bundle.get("items", []) if isinstance(ev_bundle.get("items"), Sequence) else []

    # 1. Resolve Metric
    metric = sig_dict.get("metric") or src_sig.get("metric")
    if not metric:
        for itm in ev_items:
            if isinstance(itm, Mapping) and itm.get("metric"):
                metric = itm["metric"]
                break
    if not metric and rec_dict:
        if rec_dict.get("observed_temperature") is not None and not (isinstance(rec_dict.get("metrics"), Mapping) and rec_dict["metrics"].get("mean_temp")):
            metric = "observed_temperature"
        elif isinstance(rec_dict.get("metrics"), Mapping) and rec_dict["metrics"].get("mean_temp") is not None:
            metric = "mean_temperature"
        else:
            metric = "Not available"
    if not metric:
        metric = "Not available"

    # 2. Resolve Observed Value
    observed_val = sig_dict.get("observed_value")
    if observed_val is None and src_sig:
        observed_val = src_sig.get("observed_value")
    if observed_val is None:
        for itm in ev_items:
            if isinstance(itm, Mapping) and itm.get("observed_value") is not None:
                observed_val = itm["observed_value"]
                break
    if observed_val is None and rec_dict:
        observed_val = _extract_metric_val(rec_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])

    # 3. Resolve Threshold Value
    threshold_val = sig_dict.get("threshold_value")
    if threshold_val is None and src_sig:
        threshold_val = src_sig.get("threshold_value")
    if threshold_val is None:
        for itm in ev_items:
            if isinstance(itm, Mapping) and itm.get("threshold_value") is not None:
                threshold_val = itm["threshold_value"]
                break

    # 4. Resolve Data Quality
    data_quality_val = sig_dict.get("data_quality") or src_sig.get("data_quality") or ev_bundle.get("data_quality")
    if not data_quality_val and rec_dict:
        data_quality_val = _determine_record_data_quality(rec_dict)
    if not data_quality_val:
        data_quality_val = "Not available"

    # 5. Resolve Delta & Percent Delta
    delta_val = sig_dict.get("delta")
    if delta_val is None and src_sig:
        delta_val = src_sig.get("delta")
    percent_delta_val = sig_dict.get("percent_delta")
    if percent_delta_val is None and src_sig:
        percent_delta_val = src_sig.get("percent_delta")

    # 6. Resolve Watchlist ID and Criterion Key
    watchlist_id = sig_dict.get("watchlist_id") or src_sig.get("watchlist_id")
    criterion_key = sig_dict.get("criterion_key") or src_sig.get("criterion_key")

    # Update sig_dict with resolved canonical values for consistent JSON export
    sig_dict["metric"] = metric if metric != "Not available" else sig_dict.get("metric")
    sig_dict["observed_value"] = observed_val
    sig_dict["threshold_value"] = threshold_val
    sig_dict["data_quality"] = str(data_quality_val).upper() if data_quality_val != "Not available" else "Not available"
    if delta_val is not None:
        sig_dict["delta"] = delta_val
    if percent_delta_val is not None:
        sig_dict["percent_delta"] = percent_delta_val
    if watchlist_id:
        sig_dict["watchlist_id"] = watchlist_id
    if criterion_key:
        sig_dict["criterion_key"] = criterion_key

    hist_summary: list[dict[str, Any]] = []
    if historical_context:
        for h in historical_context:
            h_dict = _deep_sanitize(h.to_dict() if hasattr(h, "to_dict") else dict(h))
            hist_summary.append({
                "analysis_id": h_dict.get("analysis_id"),
                "date": h_dict.get("date"),
                "mean_temperature": h_dict.get("mean_temperature") or (h_dict.get("metrics", {}).get("mean_temp") if isinstance(h_dict.get("metrics"), dict) else None) or h_dict.get("observed_temperature"),
            })

    if format.lower() == "json":
        export_payload = {
            "export_type": "FORTYGUARD_OPERATIONAL_INVESTIGATION_BRIEF",
            "signal": sig_dict,
            "record": rec_dict,
            "historical_context": hist_summary,
            "scenario": scen_dict,
            "disclaimer": "Descriptive calculations derived from confirmed analysis records without causal assertions.",
        }
        return json.dumps(export_payload, indent=2)

    # Text / Brief formatting
    obs_display = f"{observed_val}" if observed_val is not None else "Not available"
    th_display = f"{threshold_val}" if threshold_val is not None else "Not available"
    dq_display = str(data_quality_val).upper() if data_quality_val != "Not available" else "Not available"

    rec_loc = rec_dict.get("location_label", "Analysis Area") if rec_dict else "Analysis Area"
    desc_val = sig_dict.get("description") or (f"Priority investigation item for {rec_loc}." if rec_dict else "N/A")

    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD OPERATIONAL INVESTIGATION BRIEF",
        "=" * 60,
        "",
        "OPERATIONAL SIGNAL",
        "------------------",
        f"Signal ID   : {sig_dict.get('signal_id') or sig_dict.get('queue_id') or 'N/A'}",
        f"Severity    : {sig_dict.get('severity') or sig_dict.get('priority', 'N/A')}",
        f"Signal Type : {sig_dict.get('signal_type', 'N/A')}",
        f"Title       : {sig_dict.get('title') or sig_dict.get('reason', 'N/A')}",
        f"Description : {desc_val}",
        "",
        "OBSERVED EVIDENCE",
        "-----------------",
        f"Analysis ID : {rec_dict.get('analysis_id', sig_dict.get('analysis_id', 'N/A'))}",
        f"Location    : {rec_dict.get('location_label', sig_dict.get('location', 'N/A'))}",
        f"Date/Time   : {rec_dict.get('date', 'N/A')} {rec_dict.get('time', '')}".strip(),
        f"Metric      : {metric}",
        f"Observed    : {obs_display}",
        f"Threshold   : {th_display}",
        f"Data Quality: {dq_display}",
    ]
    if watchlist_id:
        lines.append(f"Watchlist ID: {watchlist_id}")
    if criterion_key:
        lines.append(f"Criterion   : {criterion_key}")
    if delta_val is not None:
        lines.append(f"Delta       : {delta_val}")
    if percent_delta_val is not None:
        lines.append(f"Percent Δ   : {percent_delta_val}%")
    lines.append("")

    evidence_items = sig_dict.get("evidence") or ev_items
    if evidence_items:
        lines.append("Evidence Items:")
        for ev in evidence_items:
            if isinstance(ev, str):
                lines.append(f"  * {ev}")
            elif isinstance(ev, Mapping):
                ev_txt = ev.get("evidence_text") or f"{ev.get('metric')}: observed {ev.get('observed_value')} vs threshold {ev.get('threshold_value')}"
                lines.append(f"  * {ev_txt}")
        lines.append("")

    if hist_summary:
        lines.append("HISTORICAL CONTEXT")
        lines.append("------------------")
        for h in hist_summary:
            lines.append(f"  * {h.get('date')} [{h.get('analysis_id')}]: Mean Temp = {h.get('mean_temperature') or 'N/A'}")
        lines.append("")

    if scen_dict:
        lines.append("SCENARIO WHAT-IF EXPLORATION")
        lines.append("----------------------------")
        lines.append(f"Narrative: {scen_dict.get('narrative_summary', 'N/A')}")
        lines.append(f"Scenario Value: {scen_dict.get('scenario_mean_temp', 'N/A')}")
        lines.append("")

    lines.append("RESPONSIBLE ANALYTICS NOTICE")
    lines.append("----------------------------")
    lines.append("This analysis describes observed data and derived comparisons.")
    lines.append("It does not establish causation or predict future conditions.")
    lines.append("=" * 60)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 15 Export Functions with Provenance Headers
# ──────────────────────────────────────────────────────────────────────────────

import hashlib
from frontend.utils.clock import Clock, get_current_clock


def generate_export_provenance_header(
    export_type: str,
    canonical_hash: str | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Construct canonical provenance metadata header for Phase 15 exports."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    hash_val = canonical_hash or hashlib.sha256(f"{export_type}:{now_iso}".encode("utf-8")).hexdigest()

    return {
        "export_type": export_type,
        "schema_version": 1,
        "system_source": "FortyGuard Heat Intelligence Decision Engine",
        "generated_at": now_iso,
        "canonical_hash": hash_val,
        "responsible_analytics_notice": "Descriptive calculations derived exclusively from completed session analysis records. Contains zero causal, predictive, or medical classifications.",
    }


def generate_alert_evidence_export(
    alert: Any,
    evidence_bundle: Any | None = None,
    format: str = "json",
    clock: Clock | None = None,
) -> str:
    """Export an Alert and its associated EvidenceBundle with provenance."""
    clk = clock or get_current_clock()
    alert_raw = alert.to_dict() if hasattr(alert, "to_dict") else dict(alert)
    alert_clean = _deep_sanitize(alert_raw)

    ev_clean: dict[str, Any] = {}
    if evidence_bundle:
        ev_raw = evidence_bundle.to_dict() if hasattr(evidence_bundle, "to_dict") else dict(evidence_bundle)
        ev_clean = _deep_sanitize(ev_raw)

    header = generate_export_provenance_header(
        export_type="ALERT_EVIDENCE_REPORT",
        canonical_hash=ev_clean.get("evidence_hash"),
        clock=clk,
    )

    if format.lower() == "json":
        payload = {
            "provenance": header,
            "alert": alert_clean,
            "evidence_bundle": ev_clean,
        }
        return json.dumps(payload, indent=2)

    # Brief / TXT format
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD ALERT EVIDENCE REPORT",
        "=" * 60,
        f"Export Generated At : {header['generated_at']}",
        f"Canonical Hash      : {header['canonical_hash']}",
        "",
        "ALERT DETAILS",
        "-------------",
        f"Alert ID         : {alert_clean.get('alert_id', 'N/A')}",
        f"Policy           : {alert_clean.get('policy_name', 'N/A')}",
        f"Severity         : {alert_clean.get('severity', 'N/A')}",
        f"Priority Score   : {alert_clean.get('priority_score', 'N/A')} ({alert_clean.get('priority_tier', 'N/A')})",
        f"Escalation Level : {alert_clean.get('escalation_level', 'NORMAL')}",
        f"Trigger Count    : {alert_clean.get('trigger_count', 1)}",
        f"Analysis ID      : {alert_clean.get('analysis_id', 'N/A')}",
        f"Location         : {alert_clean.get('location', 'N/A')}",
        "",
    ]

    if ev_clean:
        lines.append("EVIDENCE BUNDLE")
        lines.append("---------------")
        lines.append(f"Evidence ID : {ev_clean.get('evidence_id', 'N/A')}")
        lines.append(f"Data Quality: {ev_clean.get('data_quality', 'HIGH')}")
        lines.append("")
        lines.append("Why am I seeing this?")
        lines.append(ev_clean.get("why_am_i_seeing_this", "Threshold condition met."))
        lines.append("")

    lines.append("RESPONSIBLE ANALYTICS NOTICE")
    lines.append("----------------------------")
    lines.append(header["responsible_analytics_notice"])
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_watchlist_evaluation_export(
    evaluations: Sequence[Any],
    format: str = "json",
    clock: Clock | None = None,
) -> str:
    """Export Watchlist evaluation results with full criteria breakdown."""
    clk = clock or get_current_clock()
    clean_evals: list[dict[str, Any]] = []
    for ev in evaluations:
        raw_e = ev.to_dict() if hasattr(ev, "to_dict") else dict(ev)
        clean_evals.append(_deep_sanitize(raw_e))

    header = generate_export_provenance_header(
        export_type="WATCHLIST_EVALUATION_REPORT",
        clock=clk,
    )

    if format.lower() == "json":
        payload = {
            "provenance": header,
            "total_evaluated": len(clean_evals),
            "matched_count": sum(1 for e in clean_evals if e.get("matched")),
            "evaluations": clean_evals,
        }
        return json.dumps(payload, indent=2)

    # Text / Brief format
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD WATCHLIST EVALUATION REPORT",
        "=" * 60,
        f"Generated At    : {header['generated_at']}",
        f"Evaluations Run : {len(clean_evals)}",
        f"Matches Found   : {sum(1 for e in clean_evals if e.get('matched'))}",
        "",
    ]

    for idx, e in enumerate(clean_evals, start=1):
        lines.append(f"[{idx}] Watchlist: {e.get('watchlist_name')} (v{e.get('watchlist_version', 1)})")
        lines.append(f"    Status   : {'MATCHED' if e.get('matched') else 'NO MATCH'}")
        lines.append(f"    Quality  : {e.get('data_quality', 'HIGH')}")
        if e.get("matched_criteria"):
            lines.append(f"    Matched  : {', '.join(e['matched_criteria'])}")
        if e.get("evidence_list"):
            for ev_item in e["evidence_list"]:
                lines.append(f"      * {ev_item}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def generate_command_center_decision_brief(
    snapshot: Any,
    format: str = "brief",
    clock: Clock | None = None,
) -> str:
    """Export complete executive Decision Brief from an IntelligenceSnapshot."""
    clk = clock or get_current_clock()
    snap_dict = snapshot.to_dict() if hasattr(snapshot, "to_dict") else dict(snapshot)
    clean_snap = _deep_sanitize(snap_dict)

    header = generate_export_provenance_header(
        export_type="COMMAND_CENTER_DECISION_BRIEF",
        canonical_hash=clean_snap.get("canonical_hash"),
        clock=clk,
    )

    if format.lower() == "json":
        payload = {
            "provenance": header,
            "snapshot": clean_snap,
        }
        return json.dumps(payload, indent=2)

    # Executive Brief format
    p_summary = clean_snap.get("priority_summary", {})
    dq_summary = clean_snap.get("data_quality_summary", {})

    lines: list[str] = [
        "=" * 65,
        "FORTYGUARD HEAT INTELLIGENCE — COMMAND CENTER DECISION BRIEF",
        "=" * 65,
        f"Snapshot ID     : {clean_snap.get('snapshot_id', 'N/A')}",
        f"Generated At    : {clean_snap.get('generated_at', header['generated_at'])}",
        f"Canonical Hash  : {clean_snap.get('canonical_hash', header['canonical_hash'])}",
        "",
        "OPERATIONAL METRICS SUMMARY",
        "---------------------------",
        f"Total Analyses Evaluated  : {len(clean_snap.get('record_ids', []))}",
        f"Active Signals Detected   : {len(clean_snap.get('signals', []))}",
        f"Promoted Active Alerts    : {len(clean_snap.get('alerts', []))}",
        f"Investigation Queue Items : {len(clean_snap.get('queue_items', []))}",
        "",
        "PRIORITY BREAKDOWN",
        "------------------",
        f"Critical : {p_summary.get('critical', 0)}",
        f"High     : {p_summary.get('high', 0)}",
        f"Medium   : {p_summary.get('medium', 0)}",
        f"Low      : {p_summary.get('low', 0)}",
        "",
        "DATA QUALITY AUDIT",
        "------------------",
        f"High Quality Analyses   : {dq_summary.get('high', 0)}",
        f"Medium Quality Analyses : {dq_summary.get('medium', 0)}",
        f"Low Quality Analyses    : {dq_summary.get('low', 0)}",
        f"Insufficient Analyses   : {dq_summary.get('insufficient', 0)}",
        "",
        "RESPONSIBLE ANALYTICS GOVERNANCE",
        "--------------------------------",
        header["responsible_analytics_notice"],
        "=" * 65,
    ]

    return "\n".join(lines)


def generate_operational_decision_case_brief(
    investigation_item: Any | None = None,
    source_record: Any | None = None,
    source_signal: Any | None = None,
    source_alert: Any | None = None,
    related_analyses: Sequence[Any] | None = None,
    related_signals: Sequence[Any] | None = None,
    related_alerts: Sequence[Any] | None = None,
    latest_change_summary: Any | None = None,
    evidence_bundle: Any | None = None,
    format: str = "text",
    clock: Clock | None = None,
) -> str:
    """Construct a consolidated Phase 17 Operational Decision Case Brief with full provenance."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    # 1. Sanitize all inputs
    if isinstance(investigation_item, tuple):
        # Unpack (ok, err, item) from add_to_investigation_queue
        investigation_item = investigation_item[2] if len(investigation_item) > 2 else investigation_item[0]

    inv_dict = _deep_sanitize(investigation_item.to_dict() if hasattr(investigation_item, "to_dict") else dict(investigation_item or {}))
    rec_dict = _deep_sanitize(source_record.to_dict() if hasattr(source_record, "to_dict") else dict(source_record or {}))
    sig_dict = _deep_sanitize(source_signal.to_dict() if hasattr(source_signal, "to_dict") else dict(source_signal or {}))
    alert_dict = _deep_sanitize(source_alert.to_dict() if hasattr(source_alert, "to_dict") else dict(source_alert or {}))
    ev_dict = _deep_sanitize(evidence_bundle.to_dict() if hasattr(evidence_bundle, "to_dict") else dict(evidence_bundle or {}))
    change_dict = _deep_sanitize(latest_change_summary.to_dict() if hasattr(latest_change_summary, "to_dict") else dict(latest_change_summary or {}))

    case_id = inv_dict.get("queue_id") or inv_dict.get("item_id") or alert_dict.get("alert_id") or sig_dict.get("signal_id") or "CASE-001"
    analysis_id = rec_dict.get("analysis_id") or sig_dict.get("analysis_id") or alert_dict.get("analysis_id") or "N/A"
    signal_id = sig_dict.get("signal_id") or "N/A"
    alert_id = alert_dict.get("alert_id") or "N/A"
    watchlist_id = sig_dict.get("watchlist_id") or alert_dict.get("watchlist_id") or "N/A"
    location = rec_dict.get("location_label") or sig_dict.get("location") or alert_dict.get("location_label") or "Analysis Area"

    # Status
    inv_status = inv_dict.get("status", "OPEN").upper()
    alert_status = alert_dict.get("status", "ACTIVE").upper()

    # Provenance header
    prov_header = generate_export_provenance_header(
        export_type="FORTYGUARD_OPERATIONAL_DECISION_CASE_BRIEF",
        canonical_hash=ev_dict.get("evidence_hash"),
        clock=clk,
    )

    if format.lower() == "json":
        payload = {
            "provenance": prov_header,
            "case_id": case_id,
            "source": {
                "analysis_id": analysis_id,
                "signal_id": signal_id,
                "alert_id": alert_id,
                "watchlist_id": watchlist_id,
                "location": location,
            },
            "status": {
                "investigation_status": inv_status,
                "alert_status": alert_status,
            },
            "investigation": inv_dict,
            "record": rec_dict,
            "signal": sig_dict,
            "alert": alert_dict,
            "evidence_bundle": ev_dict,
            "latest_change": change_dict,
            "related_analyses": [_deep_sanitize(r.to_dict() if hasattr(r, "to_dict") else dict(r)) for r in (related_analyses or [])],
            "related_signals": [_deep_sanitize(s.to_dict() if hasattr(s, "to_dict") else dict(s)) for s in (related_signals or [])],
            "related_alerts": [_deep_sanitize(a.to_dict() if hasattr(a, "to_dict") else dict(a)) for a in (related_alerts or [])],
            "disclaimer": "Descriptive calculations derived from confirmed session analysis records without causal assertions.",
        }
        return json.dumps(payload, indent=2)

    # Text / Markdown formatting
    lines: list[str] = [
        "=" * 60,
        "FORTYGUARD OPERATIONAL DECISION BRIEF",
        "=" * 60,
        "",
        f"Case                 : {case_id}",
        f"Source Analysis      : {analysis_id}",
        f"Source Signal        : {signal_id}",
        f"Source Alert         : {alert_id}",
        f"Watchlist ID         : {watchlist_id}",
        f"Location             : {location}",
        f"Status               : Investigation: {inv_status} | Alert: {alert_status}",
        "",
        "Executive Summary",
        "-----------------",
        f"Operational case {case_id} for {location} (Analysis: {analysis_id}).",
        f"Trigger severity: {sig_dict.get('severity', alert_dict.get('severity', 'WATCH'))}. Current state: {inv_status}.",
        "",
        "What Changed?",
        "-------------",
    ]

    if change_dict and change_dict.get("changed_metrics"):
        for cm in change_dict["changed_metrics"]:
            lines.append(f"  * {cm.get('metric_name')}: {cm.get('baseline_value')} -> {cm.get('latest_value')} ({cm.get('direction', 'changed')}, delta: {cm.get('difference')})")
    elif change_dict and change_dict.get("is_first_analysis"):
        lines.append("  * First observation for this location — no baseline comparison.")
    else:
        lines.append("  * No significant metric deltas detected against previous session observation.")
    lines.append("")

    lines.extend([
        "Why It Was Flagged",
        "------------------",
        f"  * Reason: {sig_dict.get('title') or sig_dict.get('reason') or alert_dict.get('title') or 'Operational threshold or watchlist criterion matched.'}",
    ])
    if sig_dict.get("description"):
        lines.append(f"  * Details: {sig_dict.get('description')}")
    lines.append("")

    # Evidence
    obs_v = inv_dict.get("observed_value") or ev_dict.get("observed_value") or sig_dict.get("observed_value") or rec_dict.get("observed_temperature") or (rec_dict.get("metrics", {}).get("mean_temp") if isinstance(rec_dict.get("metrics"), dict) else None)
    th_v = inv_dict.get("threshold_value") or ev_dict.get("threshold_value") or sig_dict.get("threshold_value") or "Not available"
    dq_v = inv_dict.get("data_quality") or ev_dict.get("data_quality") or sig_dict.get("data_quality") or rec_dict.get("data_quality") or "HIGH"

    lines.extend([
        "Evidence",
        "--------",
        f"  * Observed Value   : {obs_v if obs_v is not None else 'Not available'}",
        f"  * Threshold Value  : {th_v}",
        f"  * Metric Evaluated : {sig_dict.get('metric', 'observed_temperature')}",
        f"  * Data Quality     : {str(dq_v).upper()}",
    ])
    if ev_dict.get("evidence_hash"):
        lines.append(f"  * Evidence SHA-256 : {ev_dict.get('evidence_hash')}")
    lines.append("")

    # Related Historical Analyses
    lines.extend([
        "Related Historical Analyses",
        "----------------------------",
    ])
    rel_recs = list(related_analyses or [])
    if rel_recs:
        for r in rel_recs:
            rd = _deep_sanitize(r.to_dict() if hasattr(r, "to_dict") else dict(r))
            lines.append(f"  * Analysis {rd.get('analysis_id')}: Date {rd.get('date', 'N/A')}, Observed/Mean Temp: {rd.get('observed_temperature') or (rd.get('metrics', {}).get('mean_temp') if isinstance(rd.get('metrics'), dict) else 'N/A')}")
    else:
        lines.append("  * Zero related prior analyses recorded in session history.")
    lines.append("")

    # Related Signals
    lines.extend([
        "Related Signals",
        "---------------",
    ])
    rel_sigs = list(related_signals or [])
    if rel_sigs:
        for s in rel_sigs:
            sd = _deep_sanitize(s.to_dict() if hasattr(s, "to_dict") else dict(s))
            lines.append(f"  * Signal {sd.get('signal_id')}: [{sd.get('severity')}] {sd.get('title', sd.get('signal_type', 'N/A'))}")
    else:
        lines.append("  * Zero concurrent related signals in session.")
    lines.append("")

    # Related Alerts
    lines.extend([
        "Related Alerts",
        "--------------",
    ])
    rel_als = list(related_alerts or [])
    if rel_als:
        for a in rel_als:
            ad = _deep_sanitize(a.to_dict() if hasattr(a, "to_dict") else dict(a))
            lines.append(f"  * Alert {ad.get('alert_id')}: [{ad.get('severity')}] {ad.get('title', 'N/A')} (Status: {ad.get('status')})")
    else:
        lines.append("  * Zero related alerts.")
    lines.append("")

    # Investigation Status & Notes
    lines.extend([
        "Investigation Status",
        "--------------------",
        f"  * Current State    : {inv_status}",
        f"  * Queue Assigned   : {inv_dict.get('assigned_to', 'Unassigned')}",
    ])
    notes = inv_dict.get("notes", [])
    if notes:
        lines.append("  * Investigation Notes:")
        for n in notes:
            lines.append(f"    - {n}")
    lines.append("")

    # Data Quality & Limitations
    lines.extend([
        "Data Quality",
        "------------",
        f"  * Classification   : {str(dq_v).upper()}",
        f"  * Limitations      : Observational sensor data collected within active session.",
        "",
        "Limitations",
        "-----------",
        "  * Analysis reflects historical point observations.",
        "  * No predictive certainty or medical classifications.",
        "",
        "Responsible Analytics Notice",
        "----------------------------",
        prov_header["responsible_analytics_notice"],
        "",
        "Provenance",
        "----------",
        f"  * System Source    : {prov_header['system_source']}",
        f"  * Generated At     : {prov_header['generated_at']}",
        f"  * Canonical Hash   : {prov_header['canonical_hash']}",
        f"  * Local Network    : Zero external HTTP requests made.",
        "=" * 60,
    ])

    return "\n".join(lines)


generate_command_center_decision_brief = generate_command_center_decision_brief
