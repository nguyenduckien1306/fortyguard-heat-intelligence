# FortyGuard Heat Intelligence — Watchlists & Monitoring Rules

This document details the Watchlist Engine, criteria configuration, anti-flapping hysteresis, and temporal evaluation modes.

---

## 1. What It Is & Why It Exists

Watchlists (`frontend/utils/watchlists.py`, `frontend/utils/watchlist_engine.py`) enable operators to define ongoing monitoring rules for critical geographic locations or facility types. Instead of manually inspecting every completed analysis, the system evaluates all new records against active watchlists to automatically flag conditions of concern.

---

## 2. Watchlist Configuration Parameters

| Parameter | Type | Description |
|---|---|---|
| `name` | String | Unique identifier for the watchlist rule (e.g., `Downtown Critical Care Zone`). |
| `location_pattern` | String | Exact string or partial substring match on record `location_label`. |
| `metric` | Enum | Target metric: `mean_temp`, `max_temp`, `temp_spread`, `above_threshold_proportion`. |
| `operator` | Enum | Comparison operator: `>` (greater than), `>=` (greater than or equal to). |
| `trigger_threshold`| Float | Value required to activate the watchlist match. |
| `clear_threshold`  | Float | Value required to deactivate the match (hysteresis buffer). |
| `severity` | Enum | Alert severity level assigned upon match: `WATCH`, `ELEVATED`, `CRITICAL`. |
| `temporal_mode` | Enum | Comparison timeframe: `CURRENT`, `PREVIOUS`, `FIRST`, `ROLLING`. |

---

## 3. Anti-Flapping Hysteresis

When surface temperatures fluctuate near a trigger threshold, traditional alerting systems flap between active and inactive states. 

The Watchlist Engine incorporates dual-threshold hysteresis:
- **Activation**: Triggers when metric $\ge T_{\text{trigger}}$ (e.g., $38.0^\circ\text{C}$).
- **Deactivation**: Remains active until metric drops below $T_{\text{clear}}$ (e.g., $36.5^\circ\text{C}$).
- **Result**: Eliminates noisy, intermittent alerts during minor thermal oscillations.

---

## 4. Temporal Modes

- **`CURRENT`**: Evaluates the absolute observed value in the latest record.
- **`PREVIOUS`**: Evaluates the delta ($\Delta = \text{Latest} - \text{Preceding}$) for the same location.
- **`FIRST`**: Evaluates the cumulative change compared to the earliest session baseline record.
- **`ROLLING`**: Evaluates the delta against the moving average of the last $N$ records.
