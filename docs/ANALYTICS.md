# FortyGuard Heat Intelligence — Analytical Stack & Intelligence Engine

This document details the deterministic analytical methodologies, signal detection pipelines, priority scoring algorithms, alert lifecycle management, and evidence bundling mechanisms implemented across FortyGuard Heat Intelligence.

---

## 1. The Operational Intelligence Stack

The platform transforms raw provider observations into structured decision intelligence through a deterministic, 8-stage pipeline:

```
1. Completed AnalysisRecord (Raw GeoJSON tiles or Point Observation)
   │
   ▼
2. Metric Derivation & Data Quality Assessment
   │
   ▼
3. Watchlist Evaluation & Multi-Condition Matching
   │
   ▼
4. Operational Signal Detection (Threshold, Delta, Persistence, Spatial)
   │
   ▼
5. Deterministic Priority Scoring (0–100 Mathematical Model)
   │
   ▼
6. Alert Promotion, Hysteresis & Cooldown Suppression
   │
   ▼
7. Attention Score Ranking (Operator Urgency)
   │
   ▼
8. Evidence Bundling & Decision Case Brief Export
```

---

## 2. Metric Derivation & Structural Data Quality

When a spatial heatmap analysis completes, raw GeoJSON tile geometries and temperature values are ingested. The system computes descriptive metrics:

### Metric Formulations

- **Mean Temperature ($\bar{T}$)**: Arithmetic average of all valid tile temperature values.
- **Spread ($\Delta T$)**: $T_{\max} - T_{\min}$.
- **Above-Threshold Proportion ($P_{\text{hot}}$)**: 
  $$P_{\text{hot}} = \frac{\text{Count of tiles with } T \ge T_{\text{threshold}}}{\text{Total valid tiles}} \times 100$$
- **Spatial Variability Classification**:
  - `Very Low`: $\Delta T < 3.0^\circ\text{C}$
  - `Low`: $3.0^\circ\text{C} \le \Delta T < 6.0^\circ\text{C}$
  - `Moderate`: $6.0^\circ\text{C} \le \Delta T < 10.0^\circ\text{C}$
  - `High`: $\Delta T \ge 10.0^\circ\text{C}$

### Structural Data Quality Scoring

Data quality is evaluated purely on structural completeness:
- **`HIGH`**: $\ge 95\%$ valid tiles, no missing coordinate attributes.
- **`MEDIUM`**: $80\% \le \text{valid tiles} < 95\%$.
- **`LOW`**: $50\% \le \text{valid tiles} < 80\%$.
- **`INSUFFICIENT`**: $< 50\%$ valid tiles or corrupted payload structures.

---

## 3. Watchlist Engine & Hysteresis

Watchlists (`frontend/utils/watchlists.py`, `frontend/utils/watchlist_engine.py`) allow operators to define geographic or categorical monitoring rules:

- **Location Matching**: Exact or case-insensitive partial substring match on location labels.
- **Condition Thresholds**: Mean temperature exceedance, max temperature exceedance, high spread, or high hot-area proportion.
- **Hysteresis & Cooldown Protection**: Prevents alert flapping when temperature fluctuates around a threshold. An alert requires a predefined buffer margin ($\Delta = 0.5^\circ\text{C}$) to clear.

---

## 4. Operational Signal Detection

Signals (`frontend/utils/operational_intelligence.py`) represent discrete, observable phenomena derived from confirmed records:

| Signal Type | Condition Trigger | Default Severity |
|---|---|---|
| `threshold_exceedance` | Observed metric exceeds configured alert threshold | `CRITICAL` or `ELEVATED` |
| `temperature_increase` | Metric increased by $\ge 2.0^\circ\text{C}$ compared to baseline | `ELEVATED` |
| `high_spatial_spread` | Spatial variability $\Delta T \ge 10.0^\circ\text{C}$ across AOI | `ELEVATED` |
| `high_hot_area_proportion` | $> 50\%$ of AOI tiles exceed reference threshold | `CRITICAL` |
| `data_quality_alert` | Record data quality flagged as `LOW` or `INSUFFICIENT` | `WATCH` |
| `persistent_elevation` | Consecutive analyses in same location remain elevated | `CRITICAL` |

---

## 5. Explainable Priority Scoring Model

Priority scores ($0.0 \le S \le 100.0$) are calculated using a transparent mathematical formula (`frontend/utils/priority.py`):

$$S = \min\left(100.0, \, \max\left(0.0, \, \left(B_{\text{sev}} + P_{\text{mag}} + P_{\text{rec}} + P_{\text{per}}\right) \times M_{\text{dq}}\right)\right)$$

### Component Breakdown

1. **Severity Base Points ($B_{\text{sev}}$)**:
   - `CRITICAL`: 40.0 pts
   - `ELEVATED`: 30.0 pts
   - `WATCH`: 20.0 pts
   - `INFO`: 10.0 pts
2. **Magnitude Points ($P_{\text{mag}}$, 0 to 30 pts)**:
   - Normalized difference between observed value and threshold:
     $$P_{\text{mag}} = \min\left(30.0, \, \frac{|T_{\text{obs}} - T_{\text{threshold}}|}{5.0^\circ\text{C}} \times 30.0\right)$$
3. **Recency Points ($P_{\text{rec}}$, 0 to 15 pts)**:
   - $\le 24\text{ hours}$: 15.0 pts
   - $\le 7\text{ days}$: 10.0 pts
   - $\le 30\text{ days}$: 5.0 pts
   - $> 30\text{ days}$: 2.0 pts
4. **Persistence Points ($P_{\text{per}}$, 0 to 15 pts)**:
   - Known persistent or increasing thermal trajectory: 10.0 to 15.0 pts.
5. **Data Quality Multiplier ($M_{\text{dq}}$)**:
   - `HIGH`: $1.00$
   - `MEDIUM`: $0.85$
   - `LOW`: $0.70$
   - `INSUFFICIENT`: $0.40$

### Priority Classification

- **Critical**: $S \ge 75.0$
- **High**: $50.0 \le S < 75.0$
- **Medium**: $30.0 \le S < 50.0$
- **Low**: $S < 30.0$

---

## 6. Operator Attention Score Ranking

The Operator Attention Score (`frontend/utils/attention_score.py`) ranks active items by immediate operator urgency. It factors in:
- Base priority score
- Observation recency (exponential decay)
- Investigation state (unassigned items score higher than in-review items)
- Cross-analysis recurrence (recurring conditions receive an attention boost)

---

## 7. Evidence Bundles & Provenance

Every promoted alert and investigation item generates a cryptographically anchored Evidence Bundle (`frontend/utils/evidence_bundle.py`):
- **Observed Values vs. Threshold**: Exact measured temperatures and thresholds.
- **Audit Trail**: Source `analysis_id`, `activity_id`, timestamps, and location coordinates.
- **Integrity Hash**: SHA-256 hash of the normalized signal parameters.
- **Sanitized Context**: Linked historical predecessor analyses with comparative deltas.

---

## 8. Responsible Analytics Principles

All narrative summaries, insights, and decision briefs adhere to the project's strict Responsible Analytics standard (`frontend/utils/responsible_analytics.py`):

> **Non-Causal Guarantee**: The platform generates descriptive analytical observations from confirmed sensor and satellite modeling data. It does not assert causality, human health risks, clinical diagnoses, or predictive microclimate guarantees.
