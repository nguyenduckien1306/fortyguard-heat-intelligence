# FortyGuard Heat Intelligence — Testing Strategy & Test Suites

This document provides a comprehensive overview of the testing methodologies, test suite organization, coverage standards, and execution commands for FortyGuard Heat Intelligence.

---

## 1. Testing Philosophy & Standards

The platform enforces strict automated test verification across multiple layers:
1. **Zero Flakiness**: All tests run deterministically using dependency injection and `FrozenClock` fixtures.
2. **Zero Network Leakage**: Invariant tests enforce 0 unexpected HTTP requests across all local intelligence operations.
3. **Immutability Verification**: Tests verify that completed `AnalysisRecord` instances and session state cannot be mutated by analytical engines.
4. **Failure Injection**: Hostile input tests (NaN, Inf, malformed polygons, HTTP 500s, dropped sockets) ensure graceful error handling.

---

## 2. Test Suite Organization

The test directory (`tests/`) contains **90 test files** covering **1,528 test cases** organized across distinct test tiers:

```
tests/
 ├── Foundation & Configuration
 │    ├── test_config.py
 │    └── test_health.py
 ├── Input Validation & Safety Boundaries
 │    ├── test_validation.py
 │    ├── test_polygon_builder.py
 │    ├── test_ui_validation_apptest.py
 │    └── test_submission_safety.py
 ├── Provider Client & Backend Services
 │    ├── test_api_client.py
 │    ├── test_heatmap_client.py
 │    ├── test_heat_intelligence_client.py
 │    ├── test_heatmap_service.py
 │    └── test_heat_intelligence_service.py
 ├── Execution State Machine & Polling
 │    ├── test_analysis_execution.py
 │    ├── test_polling_safety.py
 │    ├── test_execution_console_apptest.py
 │    └── test_status_pipeline_diagnostics.py
 ├── Session History & Analysis Workspace
 │    ├── test_analysis_history.py
 │    ├── test_analysis_tags.py
 │    ├── test_analysis_workspace.py
 │    └── test_workspace_apptest.py
 ├── Decision Intelligence & Comparisons
 │    ├── test_decision_intelligence.py
 │    ├── test_heatmap_comparison.py
 │    ├── test_insights.py
 │    └── test_comparison_export.py
 ├── Operational Intelligence & Signals
 │    ├── test_operational_intelligence.py
 │    ├── test_signal_pipeline.py
 │    ├── test_priority.py
 │    └── test_investigation_queue.py
 ├── Watchlists & Automated Alerts
 │    ├── test_watchlists.py
 │    ├── test_watchlist_engine.py
 │    ├── test_alert_policies.py
 │    ├── test_alert_engine.py
 │    └── test_alert_grouping.py
 ├── Cross-Analysis Intelligence & Decision Workflows
 │    ├── test_operational_summary.py
 │    ├── test_pattern_detection.py
 │    ├── test_latest_change.py
 │    ├── test_location_intelligence.py
 │    ├── test_attention_score.py
 │    ├── test_review_delta.py
 │    └── test_operator_actions.py
 ├── Security, Observability & Invariants
 │    ├── test_security_audit.py
 │    ├── test_pdf_hardening.py
 │    └── test_responsible_analytics.py
 └── Failure Injection & Resilience
      ├── test_provider_failure_diagnostics.py
      └── test_errors_ux.py
```

---

## 3. Key Invariant Test Suites

### Zero-Network Local Intelligence Invariant

Verified in automated invariant test suites:
- Patches all HTTP libraries (`httpx.Client.request`, `requests.request`, `urllib`).
- Executes full multi-analysis pipelines (signal generation, watchlist evaluations, priority scoring, queue actions, scenario adjustments, decision brief exports).
- Asserts `mock_requests.call_count == 0` and `mock_httpx.call_count == 0`.

### Strict Secret & URL Redaction Invariant

Verified in automated security audit suites:
- Injects mock API keys and signed S3 URLs into raw payloads.
- Runs recursive redaction across all export and inspection targets.
- Asserts zero instances of original secret strings in output files.

---

## 4. Running the Tests

### Full Test Suite Execution

Run all 1,528 tests in quiet mode:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Targeted Suite Execution

```powershell
# Run validation and safety tests
.venv\Scripts\python.exe -m pytest tests/test_validation.py tests/test_submission_safety.py -v

# Run operational intelligence & alert engine tests
.venv\Scripts\python.exe -m pytest tests/test_operational_intelligence.py tests/test_alert_engine.py -v

# Run Streamlit AppTest UI verification
.venv\Scripts\python.exe -m pytest tests/test_command_center_apptest.py tests/test_execution_console_apptest.py -v

# Run security and privacy audit tests
.venv\Scripts\python.exe -m pytest tests/test_security_audit.py tests/test_responsible_analytics.py -v
```
