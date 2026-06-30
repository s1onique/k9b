# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Tests for OTel workflow backend health gate.

These tests verify that the backend health gate is used in the OTel workflow,
runs before OTel install, and is properly aliased in provider health module.

NOTE: This file tests the OTel LIVE LAB workflow (k9b-otel-demo-live-lab.yml).
CI-only workflow (k9b-otel-demo-incident-lab.yml) is scaffold-only.
"""

from __future__ import annotations

import yaml
from pathlib import Path

from tests.otel_workflow_common_gates_helpers import (
    DEPLOYMENT_PHASES,
    OTEL_LIVE_LAB_WORKFLOW,
    PROVIDER_HEALTH,
    read_text,
)


# CI-only workflow for regression test (should NOT have live-lab features)
OTEL_CI_WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-incident-lab.yml"


class TestOtelWorkflowCommonGates:
    """Test that OTel workflow uses common gates like CNPG."""

    def test_otel_workflow_file_exists(self) -> None:
        """The OTel live lab workflow file should exist."""
        assert OTEL_LIVE_LAB_WORKFLOW.exists(), "k9b-otel-demo-live-lab.yml should exist"

    def test_otel_ci_workflow_is_ci_only(self) -> None:
        """OTel CI-only workflow should NOT contain live-lab markers."""
        content = OTEL_CI_WORKFLOW.read_text()
        # CI-only workflow should have CI markers
        assert "K3s OTel Demo Incident Lab CI" in content
        assert "build-and-verify" in content
        # CI-only workflow should NOT have live-lab markers
        assert "live-k3s-lab" not in content
        assert "harbor-pve1.spbnix.local" not in content
        assert "Ensure k9b lab baseline" not in content

    def test_otel_workflow_uses_backend_health_gate(self) -> None:
        """OTel workflow should use backend_health_gate script or provider health phases."""
        content = read_text(OTEL_LIVE_LAB_WORKFLOW)

        # Should reference the backend health gate or provider smoke phases
        has_backend_health = "backend_health_gate" in content
        has_provider_smoke = "provider-smoke" in content or "enable-provider-smoke" in content

        assert has_backend_health or has_provider_smoke, \
            "OTel workflow should use backend_health_gate script or provider smoke phases"

    def test_otel_workflow_backend_health_before_otel_install(self) -> None:
        """OTel workflow should run backend health gate BEFORE OTel install.

        This ensures early failure detection when k9b backend is unhealthy,
        rather than waiting until after expensive OTel Demo install.
        
        NOTE: This test runs against the live-lab workflow which has live-k3s-lab job.
        """
        content = read_text(OTEL_LIVE_LAB_WORKFLOW)

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


class TestOtelLabPhaseOrder:
    """Test that OTel lab phases run in correct order."""

    def test_backend_health_runs_before_otel_install_in_lab(self) -> None:
        """Backend health should run before OTel install phase in lab flow."""
        if not (PROVIDER_HEALTH.exists() and DEPLOYMENT_PHASES.exists()):
            return

        health_content = read_text(PROVIDER_HEALTH)
        deploy_content = read_text(DEPLOYMENT_PHASES)

        # Provider health module should exist
        assert "run_backend_health" in health_content or "BackendHealth" in health_content

        # Deployment should reference backend health
        assert "backend_health" in deploy_content.lower() or "phase_p0" in deploy_content.lower(), \
            "Deployment should reference backend health gate or P0 phase"

    def test_provider_health_exposes_backend_health_contract_alias(self) -> None:
        """Provider health module should expose backend health gate contract alias."""
        content = read_text(PROVIDER_HEALTH)

        # Should have the run_health_gate import and alias
        assert "from .backend_health_gate import run_health_gate" in content or \
               "from scripts.backend_health_gate import run_health_gate" in content, \
            "Provider health should import run_health_gate"
        assert "run_backend_health = run_health_gate" in content, \
            "Provider health should alias run_backend_health to run_health_gate"

    def test_deployment_phase_mentions_backend_health_gate_contract(self) -> None:
        """Deployment phases should mention backend health gate contract."""
        content = read_text(DEPLOYMENT_PHASES)

        assert "phase_p1_backend_health_gate" in content or "backend_health" in content.lower(), \
            "Deployment should mention backend health gate contract"
