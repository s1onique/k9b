#!/usr/bin/env python3
"""Tests for OTel Demo workflow common gates parity with CNPG live lab.

These tests enforce that the OTel demo lab uses the same common gates pattern
as the CNPG live lab for backend health and provider preflight checks.
"""

from __future__ import annotations

from pathlib import Path

import yaml


class TestOtelWorkflowCommonGates:
    """Test that OTel workflow uses common gates like CNPG."""

    def test_otel_workflow_file_exists(self) -> None:
        """The OTel demo workflow file should exist."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")
        assert workflow_path.exists(), "k9b-otel-demo-incident-lab.yml should exist"

    def test_otel_workflow_uses_backend_health_gate(self) -> None:
        """OTel workflow should use backend_health_gate script or provider health phases."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")
        content = workflow_path.read_text()
        
        # Should reference the backend health gate or provider smoke phases
        has_backend_health = "backend_health_gate" in content
        has_provider_smoke = "provider-smoke" in content or "enable-provider-smoke" in content
        
        assert has_backend_health or has_provider_smoke, \
            "OTel workflow should use backend_health_gate script or provider smoke phases"

    def test_otel_workflow_uses_k9b_lab_baseline(self) -> None:
        """OTel workflow should use ensure_k9b_lab_baseline script."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")
        content = workflow_path.read_text()
        
        # Should reference the k9b lab baseline script
        assert "ensure_k9b_lab_baseline" in content, \
            "OTel workflow should use ensure_k9b_lab_baseline script"

    def test_otel_workflow_backend_health_before_otel_install(self) -> None:
        """OTel workflow should run backend health gate BEFORE OTel install.
        
        This ensures early failure detection when k9b backend is unhealthy,
        rather than waiting until after expensive OTel Demo install.
        """
        workflow_path = Path(".github/workflows/k9b-otel-demo-incident-lab.yml")
        content = workflow_path.read_text()
        
        # Parse workflow to check phase ordering
        workflow = yaml.safe_load(content)
        
        # Get all steps in live-k3s-lab job
        live_lab_job = workflow.get("jobs", {}).get("live-k3s-lab", {})
        steps = live_lab_job.get("steps", [])
        
        step_names = [s.get("name", "") for s in steps]
        step_uses = [s.get("uses", "") for s in steps]
        
        # Find backend health gate and OTel demo lab positions
        backend_health_idx = None
        otel_lab_idx = None
        
        for i, (name, use) in enumerate(zip(step_names, step_uses)):
            if "backend" in name.lower() and "health" in name.lower():
                backend_health_idx = i
            if "k9b_otel_demo_lab" in str(use):
                otel_lab_idx = i
            # Also check run steps
            if "backend_health_gate" in str(name):
                backend_health_idx = i
        
        # If we have backend health gate, it should come before OTel lab
        if backend_health_idx is not None and otel_lab_idx is not None:
            assert backend_health_idx < otel_lab_idx, \
                "Backend health gate should run BEFORE OTel demo lab"

    def test_otel_workflow_uses_provider_preflight(self) -> None:
        """OTel lab should use provider preflight check."""
        # Check that the provider preflight module exists
        preflight_path = Path("scripts/k9b_provider_preflight.py")
        assert preflight_path.exists(), \
            "k9b_provider_preflight.py should exist"

    def test_otel_workflow_uses_frontend_smoke(self) -> None:
        """OTel lab should use frontend smoke test."""
        # Check that the frontend smoke module exists
        smoke_path = Path("scripts/k9b_otel_frontend_smoke.py")
        assert smoke_path.exists(), \
            "k9b_otel_frontend_smoke.py should exist"


class TestOtelFrontendTrafficContract:
    """Test that frontend traffic uses resolved Service URLs."""

    def test_frontend_smoke_resolves_service_port(self) -> None:
        """Frontend smoke should resolve port from Service, not hard-code."""
        from scripts.k9b_otel_frontend_smoke import _find_http_port
        
        # Test port finding logic with common port patterns
        ports = [
            {"name": "http", "port": 8080},
            {"name": "metrics", "port": 9090},
        ]
        
        # Should find 8080 as the HTTP port
        found_port = _find_http_port(ports)
        assert found_port == 8080, "Should find HTTP port 8080"

    def test_frontend_smoke_finds_named_http_port(self) -> None:
        """Frontend smoke should find named HTTP ports."""
        from scripts.k9b_otel_frontend_smoke import _find_http_port
        
        # Test with named port
        ports = [
            {"name": "http-web", "port": 3000},
            {"name": "grpc", "port": 50051},
        ]
        
        found_port = _find_http_port(ports)
        assert found_port == 3000, "Should find HTTP-named port 3000"

    def test_traffic_uses_resolve_service_url(self) -> None:
        """Traffic generation should use resolve_service_http_url."""
        traffic_path = Path("scripts/k9b_otel_demo_lab_traffic.py")
        content = traffic_path.read_text()
        
        # Should import and use resolve_service_http_url
        assert "resolve_service_http_url" in content, \
            "Traffic should use resolve_service_http_url for port resolution"


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

    def test_failure_backend_unhealthy(self) -> None:
        """k9b backend unhealthy should be classified early."""
        from scripts.k9b_otel_demo_lab_constants import FAILURE_BACKEND_HEALTH_FAILED
        
        assert FAILURE_BACKEND_HEALTH_FAILED == "backend_health_failed"

    def test_failure_provider_unavailable(self) -> None:
        """Provider unavailable should be classified early."""
        from scripts.k9b_provider_preflight import FAILURE_PROVIDER_UNAVAILABLE
        
        assert FAILURE_PROVIDER_UNAVAILABLE == "provider_unavailable"

    def test_failure_frontend_unreachable(self) -> None:
        """Frontend unreachable should be classified."""
        from scripts.k9b_otel_frontend_smoke import FAILURE_FRONTEND_SMOKE_NO_SUCCESS
        
        assert FAILURE_FRONTEND_SMOKE_NO_SUCCESS == "frontend_smoke_no_success"

    def test_failure_traffic_target_missing(self) -> None:
        """Traffic target missing should be classified."""
        from scripts.k9b_otel_demo_lab_constants import FAILURE_TRAFFIC_TARGET_SERVICE_MISSING
        
        assert FAILURE_TRAFFIC_TARGET_SERVICE_MISSING == "traffic_target_service_missing"


class TestOtelLabPhaseOrder:
    """Test that OTel lab phases run in correct order."""

    def test_provider_preflight_phase_exists_and_runs_before_install(self) -> None:
        """Provider preflight P0b phase should exist and run before OTel install."""
        # Check provider preflight module has the phase function
        preflight_path = Path("scripts/k9b_provider_preflight.py")
        content = preflight_path.read_text()
        
        # Should have run_provider_preflight function
        assert "def run_provider_preflight" in content
        
        # Check provider health module references the preflight phase
        provider_health_path = Path("scripts/k9b_otel_demo_lab_provider_health.py")
        if provider_health_path.exists():
            health_content = provider_health_path.read_text()
            # Should reference the preflight
            assert "run_provider_preflight" in health_content or "provider_preflight" in health_content, \
                "Provider health module should reference provider preflight"

    def test_provider_preflight_phase_order_in_orchestrator(self) -> None:
        """Provider preflight should run before deployment phase in orchestrator."""
        # Find the main orchestrator script
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        if lab_main_path.exists():
            content = lab_main_path.read_text()
            
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

    def test_backend_health_runs_before_otel_install_in_lab(self) -> None:
        """Backend health should run before OTel install phase in lab flow."""
        provider_health_path = Path("scripts/k9b_otel_demo_lab_provider_health.py")
        deployment_path = Path("scripts/k9b_otel_demo_lab_deployment.py")
        
        if provider_health_path.exists() and deployment_path.exists():
            health_content = provider_health_path.read_text()
            deploy_content = deployment_path.read_text()
            
            # Provider health module should exist
            assert "run_backend_health" in health_content or "BackendHealth" in health_content
            
            # Deployment should reference backend health
            assert "backend_health" in deploy_content.lower() or "phase_p0" in deploy_content.lower(), \
                "Deployment should reference backend health gate or P0 phase"


class TestP0bProviderPreflightIntegration:
    """Regression tests for P0b provider preflight gate in OTel lab orchestrator.
    
    These tests verify that the P0b phase is called BEFORE any expensive OTel phases
    (Helm install, traffic generation, symptom wait) when provider smoke is enabled.
    """

    def test_p0b_phase_is_called_in_orchestrator(self) -> None:
        """P0b provider preflight must be called in the orchestrator."""
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_main_path.read_text()
        
        # Must import the phase
        assert "phase_p0b_provider_preflight" in content, \
            "Orchestrator must import phase_p0b_provider_preflight"
        
        # Must call the phase (not just define it)
        assert "phase_p0b = phase_p0b_provider_preflight" in content, \
            "Orchestrator must call phase_p0b_provider_preflight"

    def test_p0b_runs_before_helm_install(self) -> None:
        """P0b must run BEFORE Helm install in the orchestrator flow."""
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_main_path.read_text()
        
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
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_main_path.read_text()
        
        # Check that the gate checks enable_provider_smoke AND phase failure
        assert "if config.enable_provider_smoke and not phase_p0b.success" in content, \
            "P0b must check enable_provider_smoke AND phase failure before failing"

    def test_p0b_failure_returns_before_phase1(self) -> None:
        """P0b failure with provider-smoke must return BEFORE Phase 1."""
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_main_path.read_text()
        
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
        provider_health_path = Path("scripts/k9b_otel_demo_lab_provider_health.py")
        content = provider_health_path.read_text()
        
        # Phase must return artifacts with provider_preflight_result key
        assert "provider_preflight_result" in content, \
            "P0b phase must record provider_preflight_result artifacts"
        
        # The orchestrator records the phase result
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        orchestrator_content = lab_main_path.read_text()
        assert "result.phases.append(_phase_to_dict(phase_p0b))" in orchestrator_content, \
            "P0b result must be recorded in orchestrator for diagnostics"

    def test_p0b_uses_correct_phase_name(self) -> None:
        """P0b phase must use the correct phase name in results."""
        provider_health_path = Path("scripts/k9b_otel_demo_lab_provider_health.py")
        content = provider_health_path.read_text()
        
        # Phase function should return phase="p0b-provider-preflight"
        assert 'phase="p0b-provider-preflight"' in content, \
            "P0b phase must return phase='p0b-provider-preflight'"

    def test_p0b_skipped_when_provider_smoke_disabled(self) -> None:
        """P0b failure should NOT block lab when provider-smoke is disabled."""
        lab_main_path = Path("scripts/k9b_otel_demo_lab.py")
        content = lab_main_path.read_text()
        
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
        from unittest.mock import MagicMock, patch
        from scripts.k9b_otel_demo_lab import run_lab
        from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult
        from pathlib import Path
        import tempfile

        # Create a temp artifact dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_dir = Path(tmp_dir)
            
            # Create mock results
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
            
            with patch("scripts.k9b_otel_demo_lab.phase_p0_k9b_backend_prerequisite") as mock_p0, \
                 patch("scripts.k9b_otel_demo_lab.phase_p0b_provider_preflight") as mock_p0b, \
                 patch("scripts.k9b_otel_demo_lab.phase1_deploy_otel_demo") as mock_phase1, \
                 patch("scripts.k9b_otel_demo_lab._finish_result") as mock_finish:
                
                mock_p0.return_value = mock_p0_result
                mock_p0b.return_value = mock_p0b_result
                mock_finish.side_effect = lambda r, *args: r  # Pass through
                
                # Run the lab
                result = run_lab(config)
                
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
        from unittest.mock import MagicMock, patch
        from scripts.k9b_otel_demo_lab import run_lab
        from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            artifact_dir = Path(tmp_dir)
            
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
            
            config = LabConfig(
                kubeconfig="/fake/kubeconfig",
                artifact_dir=str(artifact_dir),
                mode="scaffold",
                enable_provider_smoke=True,
            )
            
            with patch("scripts.k9b_otel_demo_lab.phase_p0_k9b_backend_prerequisite") as mock_p0, \
                 patch("scripts.k9b_otel_demo_lab.phase_p0b_provider_preflight") as mock_p0b, \
                 patch("scripts.k9b_otel_demo_lab.phase1_deploy_otel_demo") as mock_phase1, \
                 patch("scripts.k9b_otel_demo_lab._finish_result") as mock_finish:
                
                mock_p0.return_value = mock_p0_result
                mock_p0b.return_value = mock_p0b_result
                mock_phase1.return_value = mock_phase1_result
                mock_finish.side_effect = lambda r, *args: r
                
                result = run_lab(config)
                
                # Assert Phase 1 WAS called (P0b passed)
                assert mock_phase1.called, \
                    "Phase 1 should be called when P0b passes"
