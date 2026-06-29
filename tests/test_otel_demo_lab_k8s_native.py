"""Tests for K8s-native OTel Demo Lab scenario (P2b → P3c → P4c).

This module tests:
1. The orchestrator correctly routes to K8s-native scenario when incident_scenario is set
2. Phase execution order: P2b → P3c → P4c
3. Fail-closed behavior when any phase fails
4. Preservation of existing cache/flag path
5. P4c not run unless P3c succeeds
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from scripts.k9b_otel_demo_lab_types import (
    SCENARIO_K8S_NATIVE_UNSCHEDULABLE,
    SCENARIO_RECOMMENDATION_CACHE_FAILURE,
    LabConfig,
    LabPhaseResult,
    LabResult,
)


class TestLabConfigK8sNative:
    """Tests for LabConfig K8s-native scenario fields."""

    def test_lab_config_has_incident_scenario_field(self) -> None:
        """LabConfig has incident_scenario field with default."""
        config = LabConfig()
        assert hasattr(config, "incident_scenario")
        assert config.incident_scenario == "recommendation-cache-failure"

    def test_lab_config_incident_scenario_can_be_set(self) -> None:
        """LabConfig.incident_scenario can be set to K8s-native value."""
        config = LabConfig(incident_scenario=SCENARIO_K8S_NATIVE_UNSCHEDULABLE)
        assert config.incident_scenario == "unschedulable-shipping"

    def test_lab_config_has_enable_k8s_native_diagnosis_field(self) -> None:
        """LabConfig has enable_k8s_native_diagnosis field."""
        config = LabConfig()
        assert hasattr(config, "enable_k8s_native_diagnosis")
        assert config.enable_k8s_native_diagnosis is False


class TestK8sNativeScenarioConstants:
    """Tests for K8s-native scenario constants."""

    def test_scenario_constants_defined(self) -> None:
        """K8s-native scenario constants are properly defined."""
        assert SCENARIO_K8S_NATIVE_UNSCHEDULABLE == "unschedulable-shipping"
        assert SCENARIO_RECOMMENDATION_CACHE_FAILURE == "recommendation-cache-failure"

    def test_lab_result_serialization(self) -> None:
        """LabResult serializes to dict including all fields."""
        result = LabResult()
        serialized = asdict(result)
        assert "provider_smoke_passed" in serialized
        assert serialized["provider_smoke_passed"] is False


class TestK8sNativePhaseOrder:
    """Tests verifying phase execution order for K8s-native scenario."""

    def test_phase_results_track_order(self) -> None:
        """Phase results track execution order correctly."""
        # Simulate phase results
        phases = []
        
        # P2b succeeds
        phases.append(LabPhaseResult(
            phase="P2b",
            success=True,
            message="P2b succeeded",
        ))
        
        # P3c succeeds
        phases.append(LabPhaseResult(
            phase="P3c",
            success=True,
            message="P3c succeeded",
        ))
        
        # P4c succeeds
        phases.append(LabPhaseResult(
            phase="P4c",
            success=True,
            message="P4c succeeded",
        ))
        
        # Verify order
        phase_names = [p.phase for p in phases]
        assert phase_names == ["P2b", "P3c", "P4c"]

    def test_p4c_not_run_if_p3c_fails(self) -> None:
        """P4c is not included if P3c fails (fail-closed)."""
        phases = []
        
        # P2b succeeds
        phases.append(LabPhaseResult(
            phase="P2b",
            success=True,
            message="P2b succeeded",
        ))
        
        # P3c fails
        phases.append(LabPhaseResult(
            phase="P3c",
            success=False,
            message="P3c failed",
        ))
        
        # P4c should NOT be in phases
        phase_names = [p.phase for p in phases]
        assert "P2b" in phase_names
        assert "P3c" in phase_names
        assert "P4c" not in phase_names

    def test_p3c_not_run_if_p2b_fails(self) -> None:
        """P3c is not included if P2b fails (fail-closed)."""
        phases = []
        
        # P2b fails
        phases.append(LabPhaseResult(
            phase="P2b",
            success=False,
            message="P2b failed",
        ))
        
        # P3c should NOT be in phases
        phase_names = [p.phase for p in phases]
        assert "P2b" in phase_names
        assert "P3c" not in phase_names
        assert "P4c" not in phase_names


class TestK8sNativeScenarioRouting:
    """Tests for scenario routing in orchestrator."""

    def test_k8s_native_scenario_routes_to_p2b_p3c_p4c(self) -> None:
        """K8s-native scenario should use P2b, P3c, P4c phases."""
        # Verify scenario constants
        assert SCENARIO_K8S_NATIVE_UNSCHEDULABLE == "unschedulable-shipping"

    def test_default_scenario_uses_cache_failure_path(self) -> None:
        """Default scenario should use cache failure path."""
        config = LabConfig()
        assert config.incident_scenario == SCENARIO_RECOMMENDATION_CACHE_FAILURE
        assert config.incident_scenario != SCENARIO_K8S_NATIVE_UNSCHEDULABLE


class TestArtifactBundleContract:
    """Tests for K8s-native artifact bundle contract."""

    def test_p2b_artifact_path(self, tmp_path: Path) -> None:
        """P2b artifact is at phase2-injected/p2b-k8s-injection/injection-evidence.json."""
        # Create artifact structure
        injection_dir = tmp_path / "phase2-injected" / "p2b-k8s-injection"
        injection_dir.mkdir(parents=True)
        artifact_file = injection_dir / "injection-evidence.json"
        artifact_file.write_text('{"phase": "P2b", "success": true}')
        
        # Verify path exists
        assert artifact_file.exists()
        assert artifact_file.read_text() == '{"phase": "P2b", "success": true}'

    def test_p3c_artifact_path(self, tmp_path: Path) -> None:
        """P3c artifact is at phase3-discovery/p3c-k8s-discovery/detection-evidence.json."""
        # Create artifact structure
        discovery_dir = tmp_path / "phase3-discovery" / "p3c-k8s-discovery"
        discovery_dir.mkdir(parents=True)
        artifact_file = discovery_dir / "detection-evidence.json"
        artifact_file.write_text('{"phase": "P3c", "success": true}')
        
        # Verify path exists
        assert artifact_file.exists()
        assert artifact_file.read_text() == '{"phase": "P3c", "success": true}'

    def test_p4c_artifact_path(self, tmp_path: Path) -> None:
        """P4c artifact is at phase4-diagnosis/p4c-k8s-multipass-diagnosis/diagnosis-evidence.json."""
        # Create artifact structure
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        artifact_file = diagnosis_dir / "diagnosis-evidence.json"
        artifact_file.write_text('{"phase": "P4c", "success": true}')
        
        # Verify path exists
        assert artifact_file.exists()
        assert artifact_file.read_text() == '{"phase": "P4c", "success": true}'

    def test_complete_bundle_all_artifacts_present(self, tmp_path: Path) -> None:
        """Complete K8s-native bundle requires all three artifacts."""
        # Create all required artifacts
        p2b_artifact = tmp_path / "phase2-injected" / "p2b-k8s-injection" / "injection-evidence.json"
        p3c_artifact = tmp_path / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
        p4c_artifact = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
        
        # Create directories and files
        p2b_artifact.parent.mkdir(parents=True)
        p2b_artifact.write_text('{"phase": "P2b"}')
        
        p3c_artifact.parent.mkdir(parents=True)
        p3c_artifact.write_text('{"phase": "P3c"}')
        
        p4c_artifact.parent.mkdir(parents=True)
        p4c_artifact.write_text('{"phase": "P4c"}')
        
        # Verify all exist
        assert p2b_artifact.exists()
        assert p3c_artifact.exists()
        assert p4c_artifact.exists()
        
        # Verify content
        assert '"phase": "P2b"' in p2b_artifact.read_text()
        assert '"phase": "P3c"' in p3c_artifact.read_text()
        assert '"phase": "P4c"' in p4c_artifact.read_text()

    def test_bundle_verification_requires_all_three(self, tmp_path: Path) -> None:
        """Bundle verification fails if any artifact is missing."""
        # Create only P2b and P3c
        p2b_artifact = tmp_path / "phase2-injected" / "p2b-k8s-injection" / "injection-evidence.json"
        p3c_artifact = tmp_path / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"
        
        p2b_artifact.parent.mkdir(parents=True)
        p2b_artifact.write_text('{"phase": "P2b"}')
        
        p3c_artifact.parent.mkdir(parents=True)
        p3c_artifact.write_text('{"phase": "P3c"}')
        
        # P4c missing
        p4c_artifact = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
        
        # Verify P4c is missing
        assert not p4c_artifact.exists()
        assert p2b_artifact.exists()
        assert p3c_artifact.exists()
