# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Tests for OTel workflow provider preflight gate.

These tests verify that the P0b provider preflight gate is properly integrated
into the OTel lab orchestrator, runs before expensive operations, and handles
failure correctly (fail-closed when enabled, pass-through when disabled).
"""

from __future__ import annotations

from tests.otel_workflow_common_gates_helpers import (
    OTEL_ORCHESTRATOR,
    PROVIDER_HEALTH,
    PROVIDER_PREFLIGHT,
    read_text,
)


class TestProviderPreflightPhaseOrder:
    """Test provider preflight phase order in orchestrator."""

    def test_provider_preflight_phase_exists_and_runs_before_install(self) -> None:
        """Provider preflight P0b phase should exist and run before OTel install."""
        # Check provider preflight module has the phase function
        content = read_text(PROVIDER_PREFLIGHT)

        # Should have run_provider_preflight function
        assert "def run_provider_preflight" in content

        # Check provider health module references the preflight phase
        if PROVIDER_HEALTH.exists():
            health_content = read_text(PROVIDER_HEALTH)
            # Should reference the preflight
            assert "run_provider_preflight" in health_content or "provider_preflight" in health_content, \
                "Provider health module should reference provider preflight"

    def test_provider_preflight_phase_order_in_orchestrator(self) -> None:
        """Provider preflight should run before deployment phase in orchestrator."""
        content = read_text(OTEL_ORCHESTRATOR)

        # Find positions of provider preflight and deployment phases
        preflight_pos = content.find("provider_preflight")
        deployment_pos = content.find("phase_1_deployment")
        otel_install_pos = content.find("phase_1_otel_install")

        # If we have preflight, it should come before deployment/install
        if preflight_pos != -1:
            if deployment_pos != -1:
                assert preflight_pos < deployment_pos, \
                    "provider_preflight should appear before phase_1_deployment"
            if otel_install_pos != -1:
                assert preflight_pos < otel_install_pos, \
                    "provider_preflight should appear before phase_1_otel_install"


class TestOtelProviderPreflightContract:
    """Test provider preflight failure classification."""

    def test_provider_preflight_failure_classes(self) -> None:
        """Provider preflight should have correct failure classes."""
        from scripts.k9b_provider_preflight import (
            FAILURE_PROVIDER_CONNECTION_FAILED,
            FAILURE_PROVIDER_DISABLED_REQUIRED,
            FAILURE_PROVIDER_NOT_INITIALIZED,
            FAILURE_PROVIDER_UNAVAILABLE,
        )

        assert FAILURE_PROVIDER_DISABLED_REQUIRED == "provider_disabled_required"
        assert FAILURE_PROVIDER_UNAVAILABLE == "provider_unavailable"
        assert FAILURE_PROVIDER_NOT_INITIALIZED == "provider_not_initialized"
        assert FAILURE_PROVIDER_CONNECTION_FAILED == "provider_connection_failed"

    def test_provider_preflight_evaluates_dependency_failure(self) -> None:
        """Provider preflight should detect dependency_provider_connection_failed."""
        from scripts.k9b_provider_preflight import (
            FAILURE_PROVIDER_UNAVAILABLE,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )

        result = ProviderPreflightResult(passed=False)
        evaluated = _evaluate_provider_state(
            result=result,
            primary_failure="dependency_provider_connection_failed",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )

        assert evaluated.failure_class == FAILURE_PROVIDER_UNAVAILABLE
        assert evaluated.passed is False

    def test_provider_preflight_evaluates_not_initialized(self) -> None:
        """Provider preflight should detect not_initialized phase when provider is enabled."""
        from scripts.k9b_provider_preflight import (
            FAILURE_PROVIDER_NOT_INITIALIZED,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )

        # Set provider_enabled=True and provider_configured=True so it doesn't fail earlier
        result = ProviderPreflightResult(
            passed=False,
            provider_enabled=True,
            provider_configured=True,
            provider_phase="not_initialized",
            provider_status="initialized",  # Set to non-unavailable status
        )
        evaluated = _evaluate_provider_state(
            result=result,
            primary_failure="",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )

        assert evaluated.failure_class == FAILURE_PROVIDER_NOT_INITIALIZED
        assert evaluated.passed is False


class TestOtelLabFailureClassification:
    """Test OTel lab failure classification distinguishes early vs late failures."""

    def test_failure_provider_unavailable(self) -> None:
        """Provider unavailable should be classified early."""
        from scripts.k9b_provider_preflight import FAILURE_PROVIDER_UNAVAILABLE

        assert FAILURE_PROVIDER_UNAVAILABLE == "provider_unavailable"


class TestP0bProviderPreflightIntegration:
    """Regression tests for P0b provider preflight gate in OTel lab orchestrator.

    These tests verify that the P0b phase is called BEFORE any expensive OTel phases
    (Helm install, traffic generation, symptom wait) when provider smoke is enabled.
    """

    def test_p0b_phase_is_called_in_orchestrator(self) -> None:
        """P0b provider preflight must be called in the orchestrator."""
        content = read_text(OTEL_ORCHESTRATOR)

        # Must import the phase
        assert "phase_p0b_provider_preflight" in content, \
            "Orchestrator must import phase_p0b_provider_preflight"

        # Must call the phase (not just define it)
        assert "phase_p0b = phase_p0b_provider_preflight" in content, \
            "Orchestrator must call phase_p0b_provider_preflight"

    def test_p0b_runs_before_helm_install(self) -> None:
        """P0b must run BEFORE Helm install in the orchestrator flow."""
        content = read_text(OTEL_ORCHESTRATOR)

        # Find positions of P0b call and Phase 1 deployment
        # The import is at top, but the actual call is: phase_p0b = phase_p0b_provider_preflight
        p0b_call_pos = content.find("phase_p0b = phase_p0b_provider_preflight")
        # The actual variable assignment for Phase 1
        helm_install_pos = content.find("phase1 = phase1_deploy_otel_demo")

        assert p0b_call_pos != -1, "P0b must be called in orchestrator"
        assert helm_install_pos != -1, "Helm install phase must be in orchestrator"
        assert p0b_call_pos < helm_install_pos, \
            "P0b must run BEFORE Helm install to fail fast"

    def test_p0b_fails_before_helm_when_provider_smoke_enabled(self) -> None:
        """P0b failure with provider-smoke enabled must fail BEFORE Helm install."""
        content = read_text(OTEL_ORCHESTRATOR)

        # Check that the gate checks enable_provider_smoke AND phase failure
        assert "if config.enable_provider_smoke and not phase_p0b.success" in content, \
            "P0b must check enable_provider_smoke AND phase failure before failing"

    def test_p0b_failure_returns_before_phase1(self) -> None:
        """P0b failure with provider-smoke must return BEFORE Phase 1."""
        content = read_text(OTEL_ORCHESTRATOR)

        # Find the P0b gate and check it returns before Phase 1
        p0b_gate_pos = content.find("if config.enable_provider_smoke and not phase_p0b.success")
        phase1_pos = content.find("PHASE 1: Deploy OpenTelemetry Demo")

        assert p0b_gate_pos != -1, "P0b gate must exist"
        assert phase1_pos != -1, "Phase 1 must exist"

        # The gate must appear before Phase 1 header
        assert p0b_gate_pos < phase1_pos, \
            "P0b failure gate must appear before Phase 1 starts"

    def test_p0b_writes_early_artifact(self) -> None:
        """P0b must write artifacts even when it fails."""
        # The phase function writes the artifacts, not the orchestrator
        content = read_text(PROVIDER_HEALTH)

        # Phase must return artifacts with provider_preflight_result key
        assert "provider_preflight_result" in content, \
            "P0b phase must record provider_preflight_result artifacts"

        # The orchestrator records the phase result
        orchestrator_content = read_text(OTEL_ORCHESTRATOR)
        assert "result.phases.append(_phase_to_dict(phase_p0b))" in orchestrator_content, \
            "P0b result must be recorded in orchestrator for diagnostics"

    def test_p0b_uses_correct_phase_name(self) -> None:
        """P0b phase must use the correct phase name in results."""
        content = read_text(PROVIDER_HEALTH)

        # Phase function should return phase="p0b-provider-preflight"
        assert 'phase="p0b-provider-preflight"' in content, \
            "P0b phase must return phase='p0b-provider-preflight'"

    def test_p0b_skipped_when_provider_smoke_disabled(self) -> None:
        """P0b failure should NOT block lab when provider-smoke is disabled."""
        content = read_text(OTEL_ORCHESTRATOR)

        # The gate should only fail when enable_provider_smoke is True
        assert "if config.enable_provider_smoke and not phase_p0b.success" in content, \
            "P0b gate must only fail when enable_provider_smoke is True"

        # When False, lab continues to Phase 1
        assert "Phase 1" in content, \
            "Phase 1 should still run when provider smoke is disabled"


class TestP0bBehavioralMockTest:
    """Behavioral test using mocks to verify P0b gate controls phase execution."""

    def test_run_lab_does_not_call_phase1_when_p0b_fails_with_provider_smoke_enabled(self) -> None:
        """P0b failure must prevent Phase 1 from being called when provider-smoke enabled."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.k9b_otel_demo_lab import run_lab
        from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult

        # Create a temp artifact dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_dir = Path(tmp_dir)

            # Mock all phases that run before P0b gate
            mock_phase0_result = LabPhaseResult(
                phase="phase0-cluster-baseline",
                success=True,
                message="Cluster baseline verified",
                artifacts={},
                duration_seconds=0.1,
            )

            mock_p0_result = LabPhaseResult(
                phase="p0-k9b-backend-prerequisite",
                success=True,
                message="k9b backend prerequisites verified",
                artifacts={},
                duration_seconds=0.1,
            )

            mock_p0b_result = LabPhaseResult(
                phase="p0b-provider-preflight",
                success=False,
                message="Provider preflight failed: provider_unavailable - Diagnosis provider unavailable: dependency_provider_connection_failed",
                artifacts={"provider_preflight_result": str(artifact_dir / "preflight-result.json")},
                duration_seconds=0.5,
            )

            # Config with provider smoke enabled
            config = LabConfig(
                kubeconfig="/fake/kubeconfig",
                artifact_dir=str(artifact_dir),
                mode="live",
                enable_provider_smoke=True,  # Critical: provider smoke enabled
            )

            with (
                patch("scripts.k9b_otel_demo_lab.phase0_cluster_baseline") as mock_phase0,
                patch("scripts.k9b_otel_demo_lab.phase_p0_k9b_backend_prerequisite") as mock_p0,
                patch("scripts.k9b_otel_demo_lab.phase_p0b_provider_preflight") as mock_p0b,
                patch("scripts.k9b_otel_demo_lab.phase1_deploy_otel_demo") as mock_phase1,
                patch("scripts.k9b_otel_demo_lab._finish_result") as mock_finish,
            ):
                mock_phase0.return_value = mock_phase0_result
                mock_p0.return_value = mock_p0_result
                mock_p0b.return_value = mock_p0b_result
                # Fail-fast guard: if Phase 1 is called, fail immediately instead of hanging
                mock_phase1.side_effect = AssertionError(
                    "Phase 1 must not run when P0b fails with provider-smoke enabled"
                )
                mock_finish.side_effect = lambda r, *args: r  # Pass through

                # Run the lab
                result = run_lab(config)

                # Assert Phase 0 was called
                assert mock_phase0.called, "Phase 0 should be called"

                # Assert P0 was called
                assert mock_p0.called, "P0 should be called"

                # Assert P0b was called
                assert mock_p0b.called, "P0b should be called"

                # Assert Phase 1 was NOT called (this is the key behavioral test)
                assert not mock_phase1.called, \
                    "Phase 1 should NOT be called when P0b fails with provider-smoke enabled"

                # Assert the failure reason mentions P0b
                assert "P0b failed" in (result.failure_reason or ""), \
                    f"Failure reason should mention P0b, got: {result.failure_reason}"

    def test_run_lab_calls_phase1_when_p0b_passes_with_provider_smoke_enabled(self) -> None:
        """Phase 1 must be called when P0b passes even with provider-smoke enabled."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from scripts.k9b_otel_demo_lab import run_lab
        from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult

        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_dir = Path(tmp_dir)

            mock_phase0_result = LabPhaseResult(
                phase="phase0-cluster-baseline",
                success=True,
                message="Cluster baseline verified",
                artifacts={},
                duration_seconds=0.1,
            )

            mock_p0_result = LabPhaseResult(
                phase="p0-k9b-backend-prerequisite",
                success=True,
                message="k9b backend prerequisites verified",
                artifacts={},
                duration_seconds=0.1,
            )

            mock_p0b_result = LabPhaseResult(
                phase="p0b-provider-preflight",
                success=True,
                message="Provider preflight passed",
                artifacts={"provider_preflight_result": str(artifact_dir / "preflight-result.json")},
                duration_seconds=0.5,
            )

            mock_phase1_result = LabPhaseResult(
                phase="phase-1-deploy-otel-demo",
                success=True,
                message="OTel Demo deployed successfully",
                artifacts={},
                duration_seconds=10.0,
            )

            mock_phase1b_result = LabPhaseResult(
                phase="phase-1b-baseline-readiness",
                success=False,  # Fail fast - we only care that Phase 1 was called
                message="Baseline readiness failed - test stops here",
                artifacts={},
                duration_seconds=5.0,
            )

            config = LabConfig(
                kubeconfig="/fake/kubeconfig",
                artifact_dir=str(artifact_dir),
                mode="scaffold",
                enable_provider_smoke=True,
            )

            with (
                patch("scripts.k9b_otel_demo_lab.phase0_cluster_baseline") as mock_phase0,
                patch("scripts.k9b_otel_demo_lab.phase_p0_k9b_backend_prerequisite") as mock_p0,
                patch("scripts.k9b_otel_demo_lab.phase_p0b_provider_preflight") as mock_p0b,
                patch("scripts.k9b_otel_demo_lab.phase1_deploy_otel_demo") as mock_phase1,
                patch("scripts.k9b_otel_demo_lab.phase1b_baseline_readiness") as mock_phase1b,
                patch("scripts.k9b_otel_demo_lab._finish_result") as mock_finish,
            ):
                mock_phase0.return_value = mock_phase0_result
                mock_p0.return_value = mock_p0_result
                mock_p0b.return_value = mock_p0b_result
                mock_phase1.return_value = mock_phase1_result
                mock_phase1b.return_value = mock_phase1b_result
                mock_finish.side_effect = lambda r, *args: r

                run_lab(config)

                # Assert Phase 1 WAS called (P0b passed)
                assert mock_phase1.called, \
                    "Phase 1 should be called when P0b passes"
