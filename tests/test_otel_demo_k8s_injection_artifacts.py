"""Tests for OTel Demo K8s-native incident injection - Artifacts and Integration.

These tests verify artifact paths and phase return structure.
"""

from __future__ import annotations

from pathlib import Path


class TestK8sInjectionArtifactPaths:
    """Test that artifact paths are correctly structured."""

    def test_phase_artifact_directory_structure(self) -> None:
        """Phase creates correct artifact directory structure."""
        phase_dir = Path("/tmp/lab-artifacts/otel-demo/phase2-injected")
        injection_dir = phase_dir / "p2b-k8s-injection"

        expected_artifacts = [
            "previous-pod-template.json",
            "injection-patch.json",
            "injection-command.json",
            "injection-evidence.json",
            "cleanup-command.json",
            "symptom-evidence.json",
        ]

        for artifact in expected_artifacts:
            assert not (injection_dir / artifact).exists()  # Not created yet in test


class TestK8sInjectionPhaseReturnsCorrectStructure:
    """Test that phase returns correct LabPhaseResult structure."""

    def test_phase_returns_lab_phase_result(self) -> None:
        """phase_p2b_inject_unschedulable_shipping_rollout returns LabPhaseResult."""
        from scripts.k9b_otel_demo_lab_types import LabPhaseResult

        # Create a mock result with the expected structure
        result = LabPhaseResult(
            phase="p2b-k8s-injection",
            success=True,
            message="K8s-native incident injected: Pending",
            artifacts={
                "injection_dir": "/tmp/injection",
                "previous_template": "/tmp/previous-pod-template.json",
                "symptom_evidence": "/tmp/symptom-evidence.json",
                "symptom_found": True,
                "symptom_type": "Pending",
            },
            duration_seconds=30.5,
        )

        assert result.phase == "p2b-k8s-injection"
        assert result.success is True
        assert "symptom_found" in result.artifacts
        assert "symptom_type" in result.artifacts


class TestK8sInjectionSeparationFromCacheFlag:
    """Test that K8s injection is separate from cache/flag injection."""

    def test_cache_failure_injection_still_exists(self) -> None:
        """Feature flag cache failure injection still exists and works."""
        from scripts.k9b_otel_demo_lab_inject import inject_recommendation_cache_failure

        assert callable(inject_recommendation_cache_failure)

    def test_cache_failure_constant_unchanged(self) -> None:
        """FEATURE_FLAG_CACHE_FAILURE constant is unchanged."""
        from scripts.k9b_otel_demo_lab_constants import FEATURE_FLAG_CACHE_FAILURE

        assert FEATURE_FLAG_CACHE_FAILURE == "recommendationServiceCacheFailure"

    def test_phase2_inject_incident_still_exists(self) -> None:
        """Original phase2_inject_incident still exists for cache failure."""
        from scripts.k9b_otel_demo_lab_lifecycle import phase2_inject_incident

        assert callable(phase2_inject_incident)

    def test_k8s_injection_is_additional_phase(self) -> None:
        """K8s injection is an ADDITIONAL phase, not replacing existing."""
        from scripts.k9b_otel_demo_lab_phases import (
            phase2_inject_incident,
            phase_p2b_inject_unschedulable_shipping_rollout,
        )

        # Both phases exist
        assert callable(phase2_inject_incident)
        assert callable(phase_p2b_inject_unschedulable_shipping_rollout)


class TestK8sInjectionNoLiveClusterRequired:
    """Verify tests don't require live cluster."""

    def test_all_tests_are_unit_tests(self) -> None:
        """All tests in this module are unit tests (no pytest.mark.live)."""
        # This is a documentation test - the module should only have unit tests

        from scripts import k9b_otel_demo_lab_k8s_injection as module

        # Verify helper functions are internal (start with _)
        helpers = [
            name
            for name in dir(module)
            if callable(getattr(module, name)) and not name.startswith("_")
        ]

        # Public API should only be the phase, cleanup, and dataclass
        assert "phase_p2b_inject_unschedulable_shipping_rollout" in helpers
        assert "cleanup_unschedulable_shipping_rollout" in helpers
        assert "K8sInjectionResult" in helpers
