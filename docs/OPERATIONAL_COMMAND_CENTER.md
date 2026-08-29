# FortyGuard Heat Intelligence — Operational Command Center

This document details the multi-tab Operational Command Center dashboard, executive summary posture metrics, operator review deltas, and sandbox exploration.

---

## 1. What It Is & Why It Exists

The Operational Command Center (`frontend/pages/dashboard.py`) is the central nerve center of the FortyGuard Heat Intelligence platform. It aggregates completed session records, evaluates active watchlists and alert policies, prioritizes operational signals, manages the investigation workflow, and provides hypothetical scenario modeling—all operating 100% locally with zero external network consumption.

---

## 2. Command Center Tab Architecture

The Command Center provides 8 specialized analytical workspaces:

| Tab Name | Component / Engine | Operational Purpose |
|---|---|---|
| **Command Center (Home)** | `operational_summary.py`, `latest_change.py` | Executive posture summary, latest change deltas, top alerts by attention score, priority signals strip |
| **Watchlists** | `watchlist_dashboard.py` | Geographic and categorical monitoring rules, active matches, hysteresis controls |
| **Signal Center** | `signal_center.py` | Raw detected signals across threshold exceedance, temperature delta, spread, and data quality |
| **Alert Center** | `alert_center.py` | Promoted alert items, lifecycle state management (`NEW`, `ACKNOWLEDGED`, `RESOLVED`) |
| **Investigation Queue** | `investigation_queue.py` | Prioritized operator backlog, case assignments, notes, and investigation brief exports |
| **Analysis Workspace** | `analysis_history.py`, `comparison.py` | Session analysis cards, search, filtering, tagging, pinning, and Decision Intelligence |
| **Scenario Sandbox** | `scenario_engine.py` | Hypothetical what-if parameter delta modeling (never mutates history records) |
| **Intelligence Diagnostics** | `observability.py`, intelligence snapshot engine | Cryptographic SHA-256 snapshot hashes, zero-network verification counters, audit logs |

---

## 3. Executive Posture Summary & Review Delta

### Executive Operational Narrative
The executive posture engine (`frontend/utils/operational_summary.py`) synthesizes active signals, watchlist matches, priority distributions, and data quality ratings into a single, cohesive situational briefing:
> *"Operational Posture: Elevated thermal monitoring across 3 locations. 2 active critical threshold alerts require investigation. Overall data quality is HIGH."*

### Review Delta ("What Changed Since I Last Looked?")
The review delta tracker (`frontend/utils/review_delta.py`) records the timestamp when an operator clicks **Mark as Reviewed**. On subsequent visits, it highlights only new events that occurred since that review:
- Newly completed analyses
- Newly triggered alert policies
- Escalated signal severities
- Newly resolved investigation cases

---

## 4. Scenario Sandbox (Hypothetical What-If)

The Scenario Sandbox (`frontend/utils/scenario_engine.py`) allows operators to test policy thresholds and simulate environmental adjustments:
- **Sliders**: Temperature Adjustment ($\Delta T = -5.0^\circ\text{C}$ to $+5.0^\circ\text{C}$), Policy Threshold ($\Delta \text{Th} = -5.0^\circ\text{C}$ to $+5.0^\circ\text{C}$), Spatial Spread ($\Delta \text{Sp}$), and Hot-Area Proportion ($\Delta P$).
- **Visual Callout**: Clearly styled with a **Hypothetical What-If** banner.
- **Safety Invariant**: Historical `AnalysisRecord` data is strictly immutable; adjustments exist solely in temporary sandbox view state.
