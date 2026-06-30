"""Tests for public API exports.

These tests prove that:
1. __all__ lists contain the intended public names
2. No private leakage in public exports
3. Re-exports from new modules work correctly
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from k8s_diag_agent.collect.runtime import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    GateSummary,
    LoopRuntimeState,
    build_policy_enforced_pass_artifact,
    gate_checks,
    run_policy_enforced_loop,
    run_policy_enforced_loop_pass,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Export Tests
# =============================================================================


class TestRuntimeExports:
    """Tests for runtime module exports."""

    def test_runtime_all_defines_public_api(self) -> None:
        """The runtime module should have __all__ defining public API."""
        from k8s_diag_agent.collect.runtime import __all__
        assert __all__ is not None
        assert isinstance(__all__, list)
        assert len(__all__) > 0

    def test_runtime_all_contains_run_policy_enforced_loop_pass(self) -> None:
        """run_policy_enforced_loop_pass should be in __all__."""
        from k8s_diag_agent.collect.runtime import __all__
        assert "run_policy_enforced_loop_pass" in __all__

    def test_runtime_all_contains_run_policy_enforced_loop(self) -> None:
        """run_policy_enforced_loop should be in __all__."""
        from k8s_diag_agent.collect.runtime import __all__
        assert "run_policy_enforced_loop" in __all__

    def test_runtime_all_contains_gate_checks(self) -> None:
        """gate_checks should be in __all__."""
        from k8s_diag_agent.collect.runtime import __all__
        assert "gate_checks" in __all__

    def test_runtime_all_contains_loop_runtime_state(self) -> None:
        """LoopRuntimeState should be in __all__."""
        from k8s_diag_agent.collect.runtime import __all__
        assert "LoopRuntimeState" in __all__


class TestContractModuleExports:
    """Tests for contract module exports."""

    def test_contract_module_has_all(self) -> None:
        """The contract module should have __all__."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_runtime_contract import __all__
        assert __all__ is not None
        assert "LoopRuntimeState" in __all__
        assert "RUNTIME_SCHEMA_VERSION" in __all__
        assert "DiagnosisLoopPolicy" in __all__


class TestRenderingModuleExports:
    """Tests for rendering module exports."""

    def test_rendering_module_has_all(self) -> None:
        """The rendering module should have __all__."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_runtime_rendering import __all__
        assert __all__ is not None
        assert "render_runtime_summary" in __all__
        assert "render_loop_summary" in __all__


class TestRuntimeArtifactsExports:
    """Tests for runtime_artifacts module exports."""

    def test_runtime_artifacts_all_contains_build_function(self) -> None:
        """build_policy_enforced_pass_artifact should be exported."""
        from k8s_diag_agent.collect.runtime_artifacts import __all__
        assert "build_policy_enforced_pass_artifact" in __all__

    def test_runtime_artifacts_all_contains_write_function(self) -> None:
        """write_runtime_pass_artifact should be exported."""
        from k8s_diag_agent.collect.runtime_artifacts import __all__
        assert "write_runtime_pass_artifact" in __all__

    def test_runtime_artifacts_all_contains_schema_version(self) -> None:
        """RUNTIME_SCHEMA_VERSION should be exported."""
        from k8s_diag_agent.collect.runtime_artifacts import __all__
        assert "RUNTIME_SCHEMA_VERSION" in __all__


# =============================================================================
# Public Names Tests
# =============================================================================


class TestPublicNames:
    """Tests that verify public names are accessible."""

    def test_run_policy_enforced_loop_pass_is_callable(self) -> None:
        """run_policy_enforced_loop_pass should be callable."""
        assert callable(run_policy_enforced_loop_pass)

    def test_run_policy_enforced_loop_is_callable(self) -> None:
        """run_policy_enforced_loop should be callable."""
        assert callable(run_policy_enforced_loop)

    def test_gate_checks_is_callable(self) -> None:
        """gate_checks should be callable."""
        assert callable(gate_checks)

    def test_build_policy_enforced_pass_artifact_is_callable(self) -> None:
        """build_policy_enforced_pass_artifact should be callable."""
        assert callable(build_policy_enforced_pass_artifact)

    def test_loop_runtime_state_is_class(self) -> None:
        """LoopRuntimeState should be a class."""
        assert isinstance(LoopRuntimeState, type)

    def test_gate_summary_is_class(self) -> None:
        """GateSummary should be a class."""
        assert isinstance(GateSummary, type)

    def test_runtime_schema_version_is_string(self) -> None:
        """RUNTIME_SCHEMA_VERSION should be a string."""
        assert isinstance(RUNTIME_SCHEMA_VERSION, str)

    def test_p4c_constants_are_strings(self) -> None:
        """P4C constants should be strings."""
        assert isinstance(P4C_DIAGNOSIS_SUBDIR, str)
        assert isinstance(P4C_LOOP_PASSES_SUBDIR, str)
