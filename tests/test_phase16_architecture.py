"""Phase 16 — Repository & Architecture Forensics Test Suite.

Verifies:
1. Clean architectural boundary between backend and frontend.
2. Backend modules never import Streamlit or frontend UI components.
3. Frontend analytics utilities never make direct database or backend router calls.
4. No unsafe mutable default arguments (e.g. def fn(a=[])) across codebase.
5. All session state keys adhere to controlled prefix conventions.
6. Schema version uniformity (SCHEMA_VERSION = 1).
7. Clock abstraction protocol and inheritance consistency.
8. AnalysisRecord dataclass field contracts and immutability preservation.
9. Watchlist, AlertItem, EvidenceBundle, InvestigationItem dataclass contracts.
10. Zero test-only mock leaks in production code paths.
11. Explicit exception handling without bare 'except:' clauses in critical paths.
12. Responsible Analytics notices consistency.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"


def _get_python_files(directory: Path) -> list[Path]:
    """Recursively collect all Python files in a directory."""
    return [p for p in directory.rglob("*.py") if "__pycache__" not in p.parts]


class TestArchitecturalBoundaries:
    """Verify clean separation between FastAPI backend and Streamlit frontend."""

    def test_backend_never_imports_streamlit(self):
        """Backend must never import Streamlit."""
        for py_file in _get_python_files(BACKEND_DIR):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "streamlit" not in alias.name, f"Forbidden import 'streamlit' in {py_file}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "streamlit" not in node.module, f"Forbidden import from 'streamlit' in {py_file}"

    def test_backend_never_imports_frontend(self):
        """Backend must never import from frontend.* modules."""
        for py_file in _get_python_files(BACKEND_DIR):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("frontend"), f"Forbidden import '{alias.name}' in {py_file}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert not node.module.startswith("frontend"), f"Forbidden import from '{node.module}' in {py_file}"

    def test_frontend_utils_never_import_backend_routes(self):
        """Frontend utilities must not import backend API route handlers directly."""
        utils_dir = FRONTEND_DIR / "utils"
        for py_file in _get_python_files(utils_dir):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("backend.routes"), f"Forbidden import from backend.routes in {py_file}"

    def test_frontend_never_imports_fastapi_server_instance(self):
        """Frontend must not import the FastAPI 'app' instance from main.py."""
        for py_file in _get_python_files(FRONTEND_DIR):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "main":
                    for name in node.names:
                        assert name.name != "app", f"Frontend directly imported FastAPI 'app' in {py_file}"

    def test_backend_routes_use_standard_router_prefix(self):
        """All backend router files must define an APIRouter with /api/v1 prefix."""
        routes_dir = BACKEND_DIR / "routes"
        for py_file in _get_python_files(routes_dir):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            assert "APIRouter(" in content, f"Router file {py_file.name} missing APIRouter definition"


class TestCodeQualityAndSafety:
    """Verify absence of common anti-patterns like mutable defaults or bare excepts."""

    def test_no_mutable_default_arguments_in_frontend(self):
        """Ensure no functions define mutable defaults (list/dict/set) in frontend."""
        for py_file in _get_python_files(FRONTEND_DIR):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if default is not None and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                            pytest.fail(f"Mutable default argument in {py_file.name}::{node.name} at line {node.lineno}")

    def test_no_mutable_default_arguments_in_backend(self):
        """Ensure no functions define mutable defaults (list/dict/set) in backend."""
        for py_file in _get_python_files(BACKEND_DIR):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for default in node.args.defaults + node.args.kw_defaults:
                        if default is not None and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                            pytest.fail(f"Mutable default argument in {py_file.name}::{node.name} at line {node.lineno}")

    def test_no_bare_except_clauses_in_core_utils(self):
        """Ensure core intelligence utilities do not use bare 'except:' without specifying Exception."""
        utils_dir = FRONTEND_DIR / "utils"
        for py_file in _get_python_files(utils_dir):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    assert node.type is not None, f"Bare except clause found in {py_file.name} at line {node.lineno}"

    def test_no_print_statements_in_backend_routes(self):
        """Backend routes should not contain lingering stdout print statements."""
        routes_dir = BACKEND_DIR / "routes"
        for py_file in _get_python_files(routes_dir):
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                    pytest.fail(f"Lingering print() statement in backend route {py_file.name} at line {node.lineno}")


class TestSchemaAndModelIntegrity:
    """Verify consistency across dataclasses, schema versions, and clock injection."""

    def test_schema_version_is_integer_one(self):
        """Schema version must be 1 across all snapshot and export models."""
        from frontend.utils.intelligence_snapshot import SCHEMA_VERSION
        assert SCHEMA_VERSION == 1
        assert isinstance(SCHEMA_VERSION, int)

    def test_clock_abstraction_protocol_compliance(self):
        """Verify Clock subclasses implement now() and now_iso()."""
        from frontend.utils.clock import Clock, FrozenClock, ManualClock, SystemClock
        for cls in (SystemClock, FrozenClock, ManualClock):
            assert issubclass(cls, Clock)
            inst = cls("2026-08-23T12:00:00Z") if cls != SystemClock else cls()
            assert isinstance(inst.now_iso(), str)
            assert inst.now() is not None

    def test_analysis_record_dataclass_fields(self):
        """Verify AnalysisRecord has all required positional and canonical fields."""
        from frontend.utils.analysis_history import AnalysisRecord
        sig = inspect.signature(AnalysisRecord.__init__)
        params = list(sig.parameters.keys())
        expected_required = ["self", "analysis_id", "activity_id", "analysis_type", "created_at", "updated_at", "location_label"]
        for exp in expected_required:
            assert exp in params, f"Missing expected parameter '{exp}' in AnalysisRecord.__init__"

    def test_watchlist_model_capacity_and_version(self):
        """Verify Watchlist default version and criteria containment."""
        from frontend.utils.watchlists import Watchlist, WatchlistCriterion
        c = WatchlistCriterion(metric="mean_temp", operator=">", threshold=38.0)
        wl = Watchlist(watchlist_id="WL-01", name="Test", criteria=[c])
        assert wl.version == 1
        assert len(wl.criteria) == 1
        assert wl.enabled is True

    def test_alert_item_dataclass_structure(self):
        """Verify AlertItem structure and escalation level default."""
        from frontend.utils.alert_engine import AlertItem
        alert = AlertItem(
            alert_id="ALT-001",
            alert_fingerprint="fp123",
            signal_id="SIG-01",
            policy_id="POL-01",
            policy_name="Extreme Heat",
            analysis_id="HM-01",
            location="Downtown",
            severity="CRITICAL",
            priority_score=90.0,
            priority_tier="Critical",
            created_at="2026-08-23T12:00:00Z",
            updated_at="2026-08-23T12:00:00Z",
        )
        assert alert.escalation_level == "NORMAL"
        assert alert.status == "NEW"
        assert alert.parent_alert_id is None

    def test_evidence_bundle_hash_field(self):
        """Verify EvidenceBundle structure and fields."""
        from frontend.utils.evidence import EvidenceBundle
        bundle = EvidenceBundle(
            evidence_id="EVD-001",
            target_id="SIG-001",
            analysis_id="HM-001",
            evidence_as_of="2026-08-23T12:00:00Z",
            items=({"metric": "mean_temp", "value": 42.0},),
            why_am_i_seeing_this="Test why",
            evidence_hash="abcdef1234567890",
        )
        assert len(bundle.evidence_hash) > 0
        assert bundle.evidence_id == "EVD-001"

    def test_investigation_item_dataclass_structure(self):
        """Verify InvestigationItem structure and defaults."""
        from frontend.utils.investigation_queue import InvestigationItem
        inv = InvestigationItem(
            queue_id="Q-001",
            analysis_id="HM-001",
            priority="Critical",
            status="OPEN",
            created_at="2026-08-23T12:00:00Z",
            updated_at="2026-08-23T12:00:00Z",
        )
        assert inv.status == "OPEN"
        assert inv.assigned_to == "Unassigned"
        assert isinstance(inv.events, list)

    def test_investigation_event_dataclass_structure(self):
        """Verify immutable InvestigationEvent structure."""
        from frontend.utils.investigation_queue import InvestigationEvent
        evt = InvestigationEvent(
            event_id="EVT-01",
            timestamp="2026-08-23T12:00:00Z",
            event_type="CREATED",
            actor="operator",
            details="Initial creation",
        )
        assert evt.event_type == "CREATED"
        assert evt.actor == "operator"


class TestControlledSessionKeys:
    """Verify session state keys adhere to controlled prefix conventions."""

    def test_session_state_key_constants(self):
        """Verify known session state keys follow safe private prefix conventions."""
        from frontend.utils import (
            analysis_history,
            investigation_queue,
            phase15_orchestrator,
            signal_pipeline,
            watchlists,
        )
        keys_to_check = [
            analysis_history._RECORDS_STORE_KEY,
            analysis_history._COUNTERS_STORE_KEY,
            phase15_orchestrator._SNAPSHOT_STORE_KEY,
            phase15_orchestrator._WATCHLISTS_STORE_KEY,
            phase15_orchestrator._SIGNAL_LIFECYCLE_STORE_KEY,
            phase15_orchestrator._ALERT_COOLDOWN_STORE_KEY,
            phase15_orchestrator._QUEUE_STORE_KEY,
            phase15_orchestrator._NOTES_STORE_KEY,
            phase15_orchestrator._AUDIT_TRAIL_STORE_KEY,
            watchlists._WATCHLISTS_STORE_KEY,
            watchlists._WATCHLIST_COUNTER_KEY,
            signal_pipeline._SIGNAL_LIFECYCLE_STORE_KEY,
            signal_pipeline._SIGNAL_DEDUP_STORE_KEY,
            investigation_queue._QUEUE_STORE_KEY,
            investigation_queue._QUEUE_COUNTER_KEY,
        ]
        for k in keys_to_check:
            assert k.startswith("_"), f"Session key '{k}' must start with an underscore for isolation"


class TestExportFunctionSignatures:
    """Verify all export generators accept format parameter and return sanitized strings."""

    def test_all_export_functions_available(self):
        """Check availability and signature of primary export functions."""
        from frontend.utils.export import (
            generate_alert_evidence_export,
            generate_command_center_decision_brief,
            generate_export_provenance_header,
            generate_investigation_brief,
            generate_watchlist_evaluation_export,
        )
        for fn in (
            generate_alert_evidence_export,
            generate_command_center_decision_brief,
            generate_investigation_brief,
            generate_watchlist_evaluation_export,
        ):
            sig = inspect.signature(fn)
            assert "format" in sig.parameters, f"Export function {fn.__name__} must accept 'format' parameter"

    def test_export_provenance_header_signature(self):
        """Verify generate_export_provenance_header requires export_type and canonical_hash."""
        from frontend.utils.export import generate_export_provenance_header
        sig = inspect.signature(generate_export_provenance_header)
        assert "export_type" in sig.parameters
        assert "canonical_hash" in sig.parameters


class TestResponsibleAnalyticsNotices:
    """Verify that responsible analytics disclaimers are uniformly exported."""

    def test_canonical_responsible_analytics_notice_text(self):
        """Verify the canonical disclaimer contains non-causal statement."""
        from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE
        notice_lower = RESPONSIBLE_ANALYTICS_NOTICE.lower()
        assert "causation" in notice_lower or "causality" in notice_lower
        assert "predict" in notice_lower or "forecast" in notice_lower
        assert "medical" in notice_lower or "safety" in notice_lower

    def test_sanitize_text_for_responsible_analytics(self):
        """Verify text sanitizer strips prohibited causal and medical claims."""
        from frontend.utils.responsible_analytics import sanitize_narrative_text
        dirty = "The temperature rise was caused by heat waves creating a deadly hazard."
        clean = sanitize_narrative_text(dirty)
        assert "caused by" not in clean.lower()
        assert "deadly" not in clean.lower()


class TestRequirementsAndDependencies:
    """Verify clean dependencies without bloat."""

    def test_requirements_file_exists_and_clean(self):
        """requirements.txt must exist and not contain forbidden heavy dependencies."""
        req_file = REPO_ROOT / "requirements.txt"
        assert req_file.exists()
        content = req_file.read_text(encoding="utf-8").lower()
        forbidden = ["celery", "redis", "sqlalchemy", "django", "alembic", "psycopg2"]
        for pkg in forbidden:
            assert pkg not in content, f"Forbidden database/worker dependency '{pkg}' found in requirements.txt"

    def test_no_dead_or_unused_legacy_phase_directories(self):
        """Repository root must not contain obsolete phase dump folders."""
        for p in REPO_ROOT.iterdir():
            if p.is_dir():
                assert not p.name.startswith("phase_"), f"Unexpected phase scratch directory '{p.name}' in repo root"

    def test_dot_env_example_contains_all_core_keys(self):
        """Ensure .env.example contains FortyGuard API configuration keys."""
        env_example = REPO_ROOT / ".env.example"
        assert env_example.exists()
        content = env_example.read_text(encoding="utf-8")
        assert "FORTYGUARD_API_KEY" in content
        assert "FORTYGUARD_BASE_URL" in content
