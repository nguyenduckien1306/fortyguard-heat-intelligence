# FortyGuard Heat Intelligence — Decision Intelligence & Comparative Analytics

This document details the Decision Intelligence engine, pairwise analysis comparisons, sequential change detection, and cross-analysis pattern recognition.

---

## 1. What It Is & Why It Exists

Decision Intelligence moves beyond isolated analysis runs to provide comparative, longitudinal, and multi-record operational insights. It automatically evaluates differences across time, baseline benchmarks, and geographic areas to help operators understand environmental trends, identify anomalies, and justify intervention strategies.

---

## 2. Core Decision Intelligence Capabilities

### 1. Pairwise Analysis Comparison
Operators can select any two completed analyses (`Baseline Analysis A` and `Comparison Analysis B`) from session history. The engine (`frontend/utils/comparison.py`) computes:
- **Mean Temperature Delta**: $\Delta \bar{T} = \bar{T}_B - \bar{T}_A$ ($^\circ\text{C}$).
- **Spatial Spread Delta**: $\Delta (\Delta T) = \Delta T_B - \Delta T_A$ ($^\circ\text{C}$).
- **Hot-Area Proportion Delta**: $\Delta P_{\text{hot}} = P_{\text{hot}, B} - P_{\text{hot}, A}$ ($\%$).
- **Descriptive Trajectory**: Neutral plain-language interpretation (e.g., *"Warmer in B by +2.40°C with 15.0% higher above-threshold coverage"*).

### 2. Change Since Last Observation
The sequential change engine (`frontend/utils/latest_change.py`) automatically evaluates the delta between the most recent observation and its chronological predecessor for the same location:
- **Newly Triggered Conditions**: Flags metrics that crossed critical thresholds between consecutive runs.
- **Data Quality Transitions**: Tracks confidence rating shifts (`HIGH` $\to$ `MEDIUM` $\to$ `LOW`).
- **Metric Shifts**: Formats significant variations into an executive delta panel.

### 3. Cross-Analysis Pattern Detection
The pattern detector (`frontend/utils/pattern_detection.py`) continuously scans completed session history records to discover:
- **Repeated Exceedance**: Locations exceeding critical thresholds across $\ge 2$ consecutive observations.
- **Thermal Acceleration**: Sustained positive temperature gradients over time.
- **Concentrated Alerts**: Clusters of signals in specific geographic zones.
- **Data Quality Degradation**: Locations with consistently dropping sensor tile completeness.

---

## 3. Responsible Analytics Enforcement

All comparative insights and narratives pass through the Responsible Analytics validator (`frontend/utils/responsible_analytics.py`):
- Outputs describe **what changed mathematically**, never asserting unverified root causes (e.g., *"traffic emissions caused this spike"*).
- Every comparison card displays the standard non-causal disclaimer notice.
