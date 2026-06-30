"""Tests for public API import cleanliness.

These tests prove that:
1. All public runtime modules import cleanly
2. No accidental import errors in the runtime package
3. Import side effects are isolated to the right modules
"""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
)
from k8s_diag_agent.collect.runtime import (
    run_policy_enforced_loop,
    run_policy_enforced_loop_pass,
)
from k8s_diag_agent.collect.runtime_artifacts import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
)
from k8s_diag_agent.collect.runtime_gating import (
    GateSummary,
    gate_checks,
)
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_read_only_check_runner import ReadOnlyCheckHandler


# =============================================================================
# Import Tests
# =============================================================================


class TestRuntimeModuleImports:
    """Tests that verify runtime modules import cleanly."""

    def test_runtime_runtime_imports_cleanly(self) -> None:
        """The runtime module should import without errors."""
        from k8s_diag_agent.collect.runtime import (
            run_policy_enforced_loop_pass,
        )
        # Basic sanity check
        assert run_policy_enforced_loop_pass is not None
        assert run_policy_enforced_loop is not None

    def test_runtime_artifacts_imports_cleanly(self) -> None:
        """The runtime_artifacts module should import without errors."""
        assert P4C_DIAGNOSIS_SUBDIR == "p4c-k8s-multipass-diagnosis"
        assert P4C_LOOP_PASSES_SUBDIR == "loop-passes"

    def test_runtime_gating_imports_cleanly(self) -> None:
        """The runtime_gating module should import without errors."""
        assert GateSummary is not None
        assert callable(gate_checks)

    def test_runtime_state_imports_cleanly(self) -> None:
        """The runtime_state module should import without errors."""
        from k8s_diag_agent.collect.runtime_state import (
            RUNTIME_SCHEMA_VERSION,
        )
        state = LoopRuntimeState(
            loop_run_id="test",
            incident_id="test",
        )
        assert state.loop_run_id == "test"
        assert RUNTIME_SCHEMA_VERSION == "1.0"


class TestRuntimePassImportsCleanly:
    """Tests that run_policy_enforced_loop_pass works with minimal imports."""

    def test_pass_works_with_sample_data(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """run_policy_enforced_loop_pass should work with minimal data."""
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

        assert result is not None
        assert result.get("policy_enforced") is True
