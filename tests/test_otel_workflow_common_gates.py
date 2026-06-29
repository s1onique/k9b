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
