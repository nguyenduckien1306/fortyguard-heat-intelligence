# FortyGuard Heat Intelligence — Hackathon Demo Guide & Pitch Script

This guide outlines a 3–5 minute high-impact demonstration flow for presenting FortyGuard Heat Intelligence to hackathon judges, evaluators, and stakeholders.

> 🌐 **Live Application URL**: [fortyguard-heat-intelligence.streamlit.app](https://fortyguard-heat-intelligence.streamlit.app/)

---

## 1. Demo Narrative Overview

| Timestamp | Demo Segment | Core Message & Action |
|---|---|---|
| **0:00 – 0:30** | **The Problem** | Raw thermal data is overwhelming. Operators need actionable signals, not just maps. |
| **0:30 – 1:00** | **Execute Analysis** | Run a Heatmap or Heat Intelligence point analysis; show clean execution console. |
| **1:00 – 1:30** | **Signals & Priority** | Navigate to Command Center; show auto-detected signals and explainable priority score. |
| **1:30 – 2:00** | **Investigation & Evidence** | Add signal to Investigation Queue; inspect cryptographic Evidence Bundle. |
| **2:00 – 2:30** | **Decision Intelligence** | Compare two analyses side-by-side; show change detection and thermal delta metrics. |
| **2:30 – 3:00** | **Scenario Sandbox** | Run a hypothetical what-if adjustment (e.g., +2°C temp change) without altering history. |
| **3:00 – 3:30** | **Export Decision Brief** | Download a sanitized, provenance-tracked Decision Case Brief in TXT or JSON. |
| **3:30 – 4:00** | **Architecture Proof** | Highlight zero-network local intelligence, backend secret isolation, and 1,500+ tests. |

---

## 2. Step-by-Step Demonstration Script

### Step 1: Setting the Stage (0:00 – 0:30)

> *"Urban heat is one of the most critical environmental challenges facing modern cities. While APIs like FortyGuard provide powerful thermal modeling, raw temperature arrays don't tell city managers what changed, what requires immediate attention, or what evidence justifies an operational response. FortyGuard Heat Intelligence bridges this gap by turning raw thermal data into proactive operational decision intelligence."*

---

### Step 2: Running an Analysis (0:30 – 1:00)

1. Navigate to **Heatmap Analysis** in the sidebar.
2. Select an example Area of Interest (AOI) polygon (e.g., `Financial District`).
3. Point out the pre-flight validation check (`✓ Request Parameters Ready`).
4. Click **`[ Run Heatmap Analysis ]`**.
5. Show the **Execution Console** tracking elapsed time and bounded status polling.
6. When completed, show the interactive deck.gl thermal map with color-mode switching (`Average`, `Minimum`, `Maximum`).

---

### Step 3: Operational Command Center & Signals (1:00 – 1:30)

1. Switch to the **Dashboard** page.
2. Show the **Executive Summary** and the **Active Signals** section.
3. Click on a `CRITICAL` or `ELEVATED` signal card.
4. Expand the **Why this priority?** breakdown:
   - Base severity points
   - Exceedance magnitude points
   - Observation recency
   - Persistence trajectory

---

### Step 4: Investigation Queue & Evidence Audit (1:30 – 2:00)

1. Click **`[ Add to Queue ]`** on the signal card.
2. Navigate to the **Investigation Queue** tab.
3. Highlight the structured case item: status (`OPEN` $\to$ `IN_REVIEW`), priority, notes.
4. Open the **Evidence & Audit Trail**: show observed temperature vs. threshold, timestamps, and the SHA-256 integrity hash.

---

### Step 5: Decision Intelligence & Comparative Analytics (2:00 – 2:30)

1. Go to the **Analysis Workspace** tab.
2. Select two completed analyses for the same region across different dates or times.
3. Show the **Comparison Delta Grid**:
   - $\Delta$ Mean Temperature
   - $\Delta$ Spatial Spread
   - $\Delta$ Above-Threshold Proportion
4. Highlight the non-causal descriptive insights generated automatically.

---

### Step 6: Scenario Sandbox (Hypothetical What-If) (2:30 – 3:00)

1. Open the **Scenario Sandbox** tab.
2. Adjust the sliders (e.g., **Temperature Adjustment Δ +2.0°C**, **Policy Threshold -1.0°C**).
3. Show the real-time **Observed vs. Scenario State** delta comparison.
4. Point out the **Hypothetical What-If** banner and invariant guarantee: *historical observations are never mutated and zero API credits are consumed*.

---

### Step 7: Export & Decision Case Brief (3:00 – 3:30)

1. In the **Investigation Queue** or **Diagnostics** tab, click **`[ Download Decision Brief (TXT) ]`**.
2. Open the brief to show the complete, structured report containing executive summary, evidence hashes, comparative deltas, and responsible analytics disclaimers.

---

### Step 8: Architectural & Security Differentiators (3:30 – 4:00)

> *"Under the hood, FortyGuard Heat Intelligence is built with strict enterprise engineering discipline:
> - **Zero-Network Local Intelligence**: Once an analysis is completed, all comparisons, signals, alerts, scenarios, and exports operate 100% locally with zero external API calls.
> - **Strict Security Isolation**: The frontend has zero access to provider credentials or signed storage links.
> - **Production-Grade Reliability**: Backed by a verified suite of over 1,500 tests covering unit logic, failure injection, security audits, and invariants."*

---

## 3. Recommended Backup Demo Points

- If external provider latency is high, use existing session history records to demonstrate the Command Center, Decision Intelligence, and Scenario Sandbox immediately.
- Point to `docs/ARCHITECTURE.md` and `docs/SECURITY.md` for deep technical dive questions.
