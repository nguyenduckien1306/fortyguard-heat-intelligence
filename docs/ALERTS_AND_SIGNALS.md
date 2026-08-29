# FortyGuard Heat Intelligence — Operational Signals & Alert Automation

This document details the Signal Pipeline, Priority Scoring algorithm, Alert Policies, promotion rules, and fatigue protection cooldowns.

---

## 1. What It Is & Why It Exists

The Signals and Alerts architecture bridges raw data and operational action. When an analysis completes, the Signal Engine detects notable observational events. These signals are scored for priority and evaluated against alert policies to promote high-severity events into formal alert items with fatigue protection.

---

## 2. Signal Types & Precedence Hierarchy

Signals (`frontend/utils/operational_intelligence.py`) are ranked by operational precedence:

```
[Highest Precedence]
 1. WATCHLIST_MATCH     — Explicit operator-defined monitoring rule triggered
 2. THRESHOLD_BREACH    — Severe thermal exceedance above standard policy
 3. RAPID_CHANGE        — Sudden temperature jump (ΔT ≥ +3.0°C)
 4. SIGNIFICANT_CHANGE  — Moderate delta (ΔT ≥ +2.0°C)
 5. REPEATED_HEAT       — Persistent elevated thermal observations
 6. DATA_ANOMALY        — Low or degraded sensor data quality
[Lowest Precedence]
```

---

## 3. Explainable Priority Scoring (0–100 Model)

Priority scores are calculated via a pure, transparent mathematical formula (`frontend/utils/priority.py`):

$$\text{Priority Score} = \min\left(100.0, \, \max\left(0.0, \, \left(\text{Base}_{\text{sev}} + \text{Pts}_{\text{mag}} + \text{Pts}_{\text{rec}} + \text{Pts}_{\text{per}}\right) \times \text{Mult}_{\text{dq}}\right)\right)$$

### Scoring Weights

| Component | Range | Basis of Calculation |
|---|---|---|
| **Severity Base** | $10.0 - 40.0$ pts | `CRITICAL` (40), `ELEVATED` (30), `WATCH` (20), `INFO` (10) |
| **Magnitude Points** | $0.0 - 30.0$ pts | Absolute exceedance normalized over $5.0^\circ\text{C}$ range |
| **Recency Points** | $2.0 - 15.0$ pts | Observation age: $\le 24\text{h}$ (15), $\le 7\text{d}$ (10), $\le 30\text{d}$ (5), $>30\text{d}$ (2) |
| **Persistence Points** | $0.0 - 15.0$ pts | Trajectory persistence indicators |
| **Data Quality Multiplier** | $0.40 - 1.00$ | `HIGH` (1.00), `MEDIUM` (0.85), `LOW` (0.70), `INSUFFICIENT` (0.40) |

---

## 4. Alert Lifecycle & Fatigue Protection

Alerts (`frontend/utils/alert_engine.py`) transition through an audit-ready lifecycle:

```
NEW ──► ACKNOWLEDGED ──► INVESTIGATING ──► RESOLVED / DISMISSED
```

### Fatigue Protection (Cooldown Windows)
- Configurable cooldown windows: **15 min**, **1 hour**, **6 hours**, **24 hours**.
- If a matching signal occurs while an alert is active in its cooldown window, the engine increments the alert's occurrence counter rather than generating duplicate alert records.
- Signals from analyses with `INSUFFICIENT` data quality are automatically suppressed to prevent false alarms.
