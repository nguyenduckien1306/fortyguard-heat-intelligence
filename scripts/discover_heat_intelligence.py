"""Phase 6B — One-shot Heat Intelligence live schema-discovery script.

This script uses the existing application architecture:
    HeatIntelligenceService → FortyGuardClient → FortyGuard API

It does NOT bypass FastAPI/client layers.
It does NOT print or log the API key.
It makes exactly ONE POST submission and polls the same activity.

Usage:
    python -m scripts.discover_heat_intelligence
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.client import FortyGuardClient
from backend.config import Settings, get_settings
from backend.models.heat_intelligence import HeatIntelligenceRequest
from backend.models.heatmap import DateTimeFilter, Feature, Geometry, PolygonAoi


def build_discovery_request() -> HeatIntelligenceRequest:
    """Build the single documented Heat Intelligence request.

    Uses the same proven Lower Manhattan AOI that succeeded in Phase 4.
    """
    return HeatIntelligenceRequest(
        polygon_aoi=PolygonAoi(
            type="FeatureCollection",
            features=[
                Feature(
                    type="Feature",
                    geometry=Geometry(
                        type="Polygon",
                        coordinates=[
                            [
                                [-74.0170, 40.7050],
                                [-74.0030, 40.7050],
                                [-74.0030, 40.7180],
                                [-74.0170, 40.7180],
                                [-74.0170, 40.7050],
                            ]
                        ],
                    ),
                )
            ],
        ),
        date_time=DateTimeFilter(
            start_date="2024-07-15",
            start_time="14:00",
            filter_type=1,
        ),
        granularity=100,
    )


def main() -> None:
    settings = get_settings()

    if not settings.fortyguard_api_configured:
        print("ERROR: FortyGuard API key is not configured in .env")
        sys.exit(1)

    print("=" * 60)
    print("PHASE 6B — Heat Intelligence Live Schema Discovery")
    print("=" * 60)
    print(f"Base URL: {settings.fortyguard_base_url}")
    print(f"API key configured: YES (value hidden)")
    print()

    request = build_discovery_request()
    submitted_payload = request.model_dump(mode="json")
    print("Submitted payload:")
    print(json.dumps(submitted_payload, indent=2))
    print()

    trace: dict = {
        "discovery_type": "heat_intelligence",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "submitted_payload": submitted_payload,
        "submission_http_status": None,
        "initial_response": None,
        "activity_id": None,
        "polling_history": [],
        "final_status": None,
        "final_response": None,
    }

    client = FortyGuardClient(settings=settings)

    # ── STEP 1: Exactly one POST submission ──
    print("Submitting POST /v1/heat-intelligence ...")
    t0 = time.monotonic()
    try:
        # We need the raw HTTP response for status code capture.
        # Use the client's internal _http_client directly for this one call
        # to capture HTTP status, then parse like the client does.
        import httpx

        raw_response = client._http_client.post(
            FortyGuardClient.HEAT_INTELLIGENCE_PATH,
            json=submitted_payload,
        )
        submission_elapsed = time.monotonic() - t0
        trace["submission_http_status"] = raw_response.status_code
        print(f"  HTTP status: {raw_response.status_code}")
        print(f"  Elapsed: {submission_elapsed:.2f}s")

        try:
            initial_body = raw_response.json()
        except Exception:
            initial_body = raw_response.text
        trace["initial_response"] = initial_body
        print(f"  Response body: {json.dumps(initial_body, indent=2) if isinstance(initial_body, dict) else initial_body}")

        if raw_response.status_code >= 400:
            print(f"\nSUBMISSION FAILED with HTTP {raw_response.status_code}")
            _save_trace(trace)
            return

        # Extract activity_id
        if isinstance(initial_body, dict):
            data_section = initial_body.get("data", {})
            if isinstance(data_section, dict):
                activity_id = data_section.get("activity_id")
            else:
                activity_id = None
        else:
            activity_id = None

        if not activity_id:
            print("\nERROR: No activity_id in submission response")
            _save_trace(trace)
            return

        trace["activity_id"] = activity_id
        print(f"\n  Activity ID: {activity_id}")

    except Exception as exc:
        submission_elapsed = time.monotonic() - t0
        print(f"  EXCEPTION during submission: {exc}")
        trace["submission_http_status"] = "EXCEPTION"
        trace["initial_response"] = str(exc)
        _save_trace(trace)
        return

    # ── STEP 2: Bounded polling ──
    print(f"\nPolling GET /v1/status/{activity_id} ...")
    MAX_ATTEMPTS = 60
    POLL_INTERVAL = 3.0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        poll_start = time.monotonic()
        try:
            status_response = client._http_client.get(
                f"/v1/status/{activity_id}"
            )
            poll_elapsed = time.monotonic() - poll_start
            try:
                status_body = status_response.json()
            except Exception:
                status_body = status_response.text

            poll_entry = {
                "attempt": attempt,
                "http_status": status_response.status_code,
                "elapsed_seconds": round(poll_elapsed, 3),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "response": status_body,
            }
            trace["polling_history"].append(poll_entry)

            # Extract status
            if isinstance(status_body, dict):
                data = status_body.get("data", {})
                if isinstance(data, dict):
                    current_status = data.get("status", "Unknown")
                else:
                    current_status = "Unknown"
            else:
                current_status = "Unknown"

            total_elapsed = time.monotonic() - t0
            print(f"  [{attempt}/{MAX_ATTEMPTS}] Status: {current_status} ({poll_elapsed:.2f}s, total {total_elapsed:.1f}s)")

            if current_status == "Completed":
                trace["final_status"] = "Completed"
                trace["final_response"] = status_body
                print(f"\n{'=' * 60}")
                print("TASK COMPLETED")
                print(f"{'=' * 60}")
                print(f"Total elapsed: {total_elapsed:.1f}s")
                print()

                # Extract and display result
                if isinstance(data, dict) and "result" in data:
                    result = data["result"]
                    print("Result keys:", list(result.keys()) if isinstance(result, dict) else type(result).__name__)
                    print()
                    print("Full result:")
                    print(json.dumps(result, indent=2, default=str)[:5000])
                    if isinstance(result, dict) and len(json.dumps(result)) > 5000:
                        print(f"\n... (truncated in console, full result saved to trace)")
                break

            elif current_status == "Failed":
                trace["final_status"] = "Failed"
                trace["final_response"] = status_body
                print(f"\nTASK FAILED")
                print(json.dumps(status_body, indent=2))
                break

            elif current_status == "Unknown":
                trace["final_status"] = "Unknown"
                trace["final_response"] = status_body
                print(f"\nUNKNOWN STATUS — stopping")
                break

            # Still Processing — wait and retry
            if attempt < MAX_ATTEMPTS:
                time.sleep(POLL_INTERVAL)

        except Exception as exc:
            poll_elapsed = time.monotonic() - poll_start
            poll_entry = {
                "attempt": attempt,
                "http_status": "EXCEPTION",
                "elapsed_seconds": round(poll_elapsed, 3),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "response": str(exc),
            }
            trace["polling_history"].append(poll_entry)
            print(f"  [{attempt}] EXCEPTION: {exc}")
            break
    else:
        # Exhausted all attempts
        trace["final_status"] = "Timeout"
        trace["final_response"] = trace["polling_history"][-1]["response"] if trace["polling_history"] else None
        total_elapsed = time.monotonic() - t0
        print(f"\nPOLLING TIMEOUT after {MAX_ATTEMPTS} attempts ({total_elapsed:.1f}s)")

    _save_trace(trace)
    client.close()


def _save_trace(trace: dict) -> None:
    """Save the execution trace to data/raw/."""
    activity_id = trace.get("activity_id") or "no_activity_id"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(activity_id))
    out_dir = PROJECT_ROOT / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"heat_intelligence_execution_{safe_id}.json"
    out_path = out_dir / filename

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, default=str)

    print(f"\nExecution trace saved: {out_path}")
    print(f"  File size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
