"""Tests for backward compatibility of the public API.

These tests prove that:
1. Legacy import paths still work
2. Compatibility aliases are maintained
3. Existing consumers are not broken
"""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from k8s_diag_agent.collect.runtime import (
    run_policy_enforced_loop,
    run_policy_enforced_loop_pass,
)
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_read_only_check_runner import ReadOnlyCheckHandler


# =============================================================================
# Legacy Import Path Tests
# =============================================================================


class TestLegacyImportPaths:
    """Tests that legacy import paths still work."""

    def test_import_from_runtime_runtime(self) -> None:
        """Importing from runtime should work (backward compatibility)."""
        from k8s_diag_agent.collect.runtime import (
            run_policy_enforced_loop,
            run_policy_enforced_loop_pass,
        )
        assert callable(run_policy_enforced_loop_pass)
        assert callable(run_policy_enforced_loop)

    def test_import_loop_runtime_state_from_runtime(self) -> None:
        """Importing LoopRuntimeState from runtime should work."""
        from k8s_diag_agent.collect.runtime import LoopRuntimeState
        assert isinstance(LoopRuntimeState, type)

    def test_import_gate_summary_from_runtime(self) -> None:
        """Importing GateSummary from runtime should work."""
        from k8s_diag_agent.collect.runtime import GateSummary
        assert isinstance(GateSummary, type)

    def test_import_runtime_schema_version_from_runtime(self) -> None:
        """Importing RUNTIME_SCHEMA_VERSION from runtime should work."""
        from k8s_diag_agent.collect.runtime import RUNTIME_SCHEMA_VERSION
        assert isinstance(RUNTIME_SCHEMA_VERSION, str)
        assert RUNTIME_SCHEMA_VERSION == "1.0"


class TestCompatibilityAliases:
    """Tests for compatibility aliases."""

    def test_loop_runtime_state_can_be_imported_from_contract(self) -> None:
        """LoopRuntimeState should be importable from contract module."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_runtime_contract import (
            LoopRuntimeState,
        )
        assert isinstance(LoopRuntimeState, type)

    def test_runtime_schema_version_can_be_imported_from_contract(self) -> None:
        """RUNTIME_SCHEMA_VERSION should be importable from contract module."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_runtime_contract import (
            RUNTIME_SCHEMA_VERSION,
        )
        assert isinstance(RUNTIME_SCHEMA_VERSION, str)

    def test_diagnosis_loop_policy_can_be_imported_from_contract(self) -> None:
        """DiagnosisLoopPolicy should be importable from contract module."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_runtime_contract import (
            DiagnosisLoopPolicy,
        )
        assert isinstance(DiagnosisLoopPolicy, type)


# =============================================================================
# Cross-Module Compatibility
# =============================================================================


class TestCrossModuleCompatibility:
    """Tests that cross-module imports work correctly."""

    def test_runtime_artifacts_imports_work_from_runtime_runtime(self) -> None:
        """Importing from runtime_artifacts via runtime should work."""
        from k8s_diag_agent.collect.runtime import (
            P4C_DIAGNOSIS_SUBDIR,
            P4C_LOOP_PASSES_SUBDIR,
            build_policy_enforced_pass_artifact,
        )
        assert callable(build_policy_enforced_pass_artifact)
        assert P4C_DIAGNOSIS_SUBDIR == "p4c-k8s-multipass-diagnosis"
        assert P4C_LOOP_PASSES_SUBDIR == "loop-passes"

    def test_runtime_gating_imports_work_from_runtime_runtime(self) -> None:
        """Importing gate_checks via runtime should work."""
        from k8s_diag_agent.collect.runtime import gate_checks
        assert callable(gate_checks)

    def test_runtime_state_imports_work_from_runtime_runtime(self) -> None:
        """Importing LoopRuntimeState via runtime should work."""
        from k8s_diag_agent.collect.runtime import LoopRuntimeState
        assert isinstance(LoopRuntimeState, type)


# =============================================================================
# Runtime Behavior Compatibility
# =============================================================================


class TestRuntimeBehaviorCompatibility:
    """Tests that runtime behavior is preserved."""

    def test_loop_pass_returns_policy_enforced_true(
        self,
        sample_policy,
        sample_case_file,
    ) -> None:
        """run_policy_enforced_loop_pass should return policy_enforced=True."""
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }

        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )

        assert result.get("policy_enforced") is True

    def test_loop_pass_returns_gate_summary(
        self,
        sample_policy,
        sample_case_file,
    ) -> None:
        """run_policy_enforced_loop_pass should return gate_summary."""
        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }

        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop_pass(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=sample_policy,
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )

        assert "gate_summary" in result
        gate_summary = result["gate_summary"]
        assert "proposed" in gate_summary
        assert "accepted" in gate_summary
        assert "rejected_mutating" in gate_summary

    def test_loop_returns_pass_artifacts(
        self,
        sample_case_file,
    ) -> None:
        """run_policy_enforced_loop should return pass_artifacts."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            DiagnosisLoopPolicy,
        )

        diagnosis_report = {
            "diagnosis": {
                "recommended_investigations": [
                    {"check_id": "check_1", "title": "Check 1"},
                ]
            }
        }

        fake_handlers: dict[str, Any] = {
            "check_1": lambda c, now=None: {"check_id": "check_1", "status": "completed"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_policy_enforced_loop(
                incident_id="test-incident",
                external_analysis_dir=Path(tmp_dir),
                case_file=sample_case_file,
                diagnosis_report=diagnosis_report,
                run_id="test-run",
                policy=DiagnosisLoopPolicy(max_passes=2),
                now=datetime.now(UTC),
                fake_handlers=cast("dict[str, ReadOnlyCheckHandler]", fake_handlers),
            )

        assert "pass_artifacts" in result
        assert isinstance(result["pass_artifacts"], list)

    def test_runtime_state_to_dict_works(self) -> None:
        """LoopRuntimeState.to_dict() should work."""
        state = LoopRuntimeState(
            loop_run_id="test-loop",
            incident_id="test-incident",
            pass_index=1,
            started_at="2024-01-01T00:00:00+00:00",
        )

        d = state.to_dict()
        assert isinstance(d, dict)
        assert d["loop_run_id"] == "test-loop"
        assert d["incident_id"] == "test-incident"

    def test_runtime_state_from_dict_works(self) -> None:
        """LoopRuntimeState.from_dict() should work."""
        data = {
            "loop_run_id": "test-loop",
            "incident_id": "test-incident",
            "pass_index": 1,
            "started_at": "2024-01-01T00:00:00+00:00",
            "seen_check_fingerprints": [],
            "total_checks_executed": 0,
            "total_checks_proposed": 0,
            "total_checks_rejected": 0,
            "total_mutating_executed": 0,
            "total_sensitive_executed": 0,
            "total_model_calls": 0,
            "evidence_hashes_seen": [],
            "last_case_file_hash": "",
            "schema_version": "1.0",
        }

        state = LoopRuntimeState.from_dict(data)
        assert state.loop_run_id == "test-loop"
        assert state.incident_id == "test-incident"
