# FortyGuard Heat Intelligence — Heatmap Spatial Analysis

This document details the spatial heatmap analysis capabilities, input validation rules, deck.gl visualization pipeline, and derived spatial metrics.

---

## 1. What It Is & Why It Exists

Heatmap Analysis provides high-resolution spatial surface temperature modeling over user-defined polygon Areas of Interest (AOI). It allows environmental operators, urban planners, and municipal analysts to identify localized thermal hot spots, assess temperature distribution across neighborhoods, and understand microclimate variability.

---

## 2. Parameter Inputs & Pre-Flight Validation

The pre-flight validation core (`frontend/utils/validation.py`) strictly verifies all inputs before any submission request is generated:

| Parameter | Validation Rules | Error Behavior |
|---|---|---|
| **Area of Interest (AOI)** | Complete 2D GeoJSON polygon ($\ge 4$ coordinate pairs). Ring must close (first coordinate == last coordinate). Latitude $\in [-90, 90]$, Longitude $\in [-180, 180]$. | Red inline alert: "Polygon ring must be closed" or "Invalid coordinate range". Submit blocked. |
| **Observation Date** | Valid calendar date formatted as `YYYY-MM-DD`. | Inline error message; submit blocked. |
| **Observation Time** | Valid 24-hour time formatted as `HH:MM`. | Inline error message; submit blocked. |
| **Spatial Granularity** | Integer $10\text{m} \le g \le 1000\text{m}$ (default: 100m). | Clamped to bounds; validation alert. |
| **Location Label** | Optional string identifier (e.g., `Financial District`). | Sanitized to prevent injection. |

---

## 3. Visualization Pipeline & Deck.gl Integration

Once FortyGuard completes processing the spatial analysis task, the backend delivers a GeoJSON feature collection where each polygon tile feature contains temperature attributes.

### Dynamic Thermal Color Modes
The visualization component (`frontend/components/heatmap_result.py`) provides interactive color mapping:
- **Average Temperature Mode**: Colors tiles by mean tile temperature ($\bar{T}$).
- **Minimum Temperature Mode**: Colors tiles by minimum observed temperature ($T_{\min}$).
- **Maximum Temperature Mode**: Colors tiles by peak observed temperature ($T_{\max}$).

### Multi-Metric Interactive Tooltips
Hovering over any tile in the deck.gl layer reveals:
- Tile ID & Geographic Centroid (Latitude, Longitude)
- Average, Minimum, and Maximum Temperature ($^\circ\text{C}$)
- Spatial Spread ($\Delta T = T_{\max} - T_{\min}$)
- Data Quality Confidence Indicator

---

## 4. Derived Spatial Analytics

The Heatmap Result Adapter computes the following summary statistics:
- **Mean AOI Temperature ($\bar{T}$)**: Average across all valid tiles.
- **Thermal Extremes ($T_{\min}, T_{\max}$)**: Coolest and hottest recorded tile temperatures.
- **Thermal Spread ($\Delta T$)**: Total spatial variability across the polygon.
- **Hot-Area Proportion ($P_{\text{hot}}$)**: Percentage of AOI tiles exceeding the reference alert threshold ($35.0^\circ\text{C}$).
- **Temperature Distribution**: 5-point summary and histogram visualization.

---

## 5. Result Storage & Ingestion

Completed heatmap analyses are structurally validated and ingested into session history as immutable `AnalysisRecord` objects. They immediately become available in:
- The **Analysis Workspace** for search, filtering, tagging, and pinning.
- The **Decision Intelligence** engine for pairwise comparison against predecessor analyses.
- The **Operational Command Center** for automated signal detection and alert evaluation.
