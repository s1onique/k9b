"""Regression test for P4c namespace isolation bug.

Bug: The P4c runner was passing the incident namespace (e.g., otel-demo) to
get_automatic_loop_enabled_with_reason(), which caused the gate to look for
k9b-scheduler deployment in the wrong namespace.

Fix: The runner now uses get_default_k9b_namespace() to always check the
scheduler deployment in the k9b namespace, regardless of incident namespace.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_gate import (
    LoopEnabledCheckResult,
)


class TestP4cNamespaceIsolation:
    """Test that P4c runner uses k9b namespace for scheduler gate, not incident namespace."""

    def test_run_diagnosis_loop_uses_k9b_namespace_for_scheduler_gate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression: P4c runner should check scheduler in k9b namespace, not incident namespace.

        The incident might be in otel-demo, but the k9b-scheduler runs in k9b.
        The gate should be called with namespace="k9b", NOT namespace="otel-demo".
        """
        # Track the namespace passed to the gate
        captured_namespaces: list[str] = []

        def fake_gate(
            *,
            kubeconfig,
            namespace,
            allow_env_fallback,
        ) -> tuple[bool, LoopEnabledCheckResult]:
            captured_namespaces.append(namespace)
            # Return enabled so we don't hit the failure path
            return True, LoopEnabledCheckResult(
                enabled=True,
                source="deployment",
                reason="env_var_from_deployment",
            )

        # Patch the gate at the module where it's used (not where it's defined)
        # The runner imports and calls it from incident_diagnosis_auto_loop_config
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_automatic_loop_enabled_with_reason",
            fake_gate,
        )
        monkeypatch.setenv("K9B_NAMESPACE", "k9b")

        # Mock collect_automatic_diagnosis_evidence to avoid real execution
        mock_result = Mock()
        mock_result.eligible = True
        mock_result.run_id = "run-123"
        mock_result.checks_run = []
        mock_result.review_packet_name = None

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop.collect_automatic_diagnosis_evidence",
            lambda *args, **kwargs: mock_result,
        )

        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import run_diagnosis_loop

        with TemporaryDirectory() as tmpdir:
            incident_id = "test-incident-123"
            analysis_dir = Path(tmpdir) / incident_id
            analysis_dir.mkdir(parents=True)

            run_diagnosis_loop(
                incident_id=incident_id,
                external_analysis_dir=analysis_dir,
                kubeconfig="/tmp/kubeconfig",
                namespace="otel-demo",  # Incident namespace
                allow_simulation=False,
            )

        # The critical assertion: namespace should be k9b, not otel-demo
        assert len(captured_namespaces) >= 1, "Gate should have been called at least once"
        gate_namespace = captured_namespaces[0]
        assert gate_namespace == "k9b", (
            f"Gate should be called with namespace='k9b' (scheduler namespace), "
            f"not {gate_namespace!r} (incident namespace). "
            f"This is the namespace isolation bug!"
        )

    def test_result_includes_scheduler_namespace_checked(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify result dict includes which namespace was checked for scheduler."""
        def fake_gate(
            *,
            kubeconfig,
            namespace,
            allow_env_fallback,
        ) -> tuple[bool, LoopEnabledCheckResult]:
            return False, LoopEnabledCheckResult(
                enabled=False,
                source="error",
                reason="automatic_loop_env_read_failed",
                error_message="NotFound: deployment.apps 'k9b-scheduler' not found",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_config.get_automatic_loop_enabled_with_reason",
            fake_gate,
        )
        monkeypatch.setenv("K9B_NAMESPACE", "k9b")

        from pathlib import Path
        from tempfile import TemporaryDirectory

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import run_diagnosis_loop

        with TemporaryDirectory() as tmpdir:
            incident_id = "test-incident-456"
            analysis_dir = Path(tmpdir) / incident_id
            analysis_dir.mkdir(parents=True)

            result = run_diagnosis_loop(
                incident_id=incident_id,
                external_analysis_dir=analysis_dir,
                kubeconfig="/tmp/kubeconfig",
                namespace="otel-demo",
                allow_simulation=False,
            )

        # Result should have the scheduler namespace recorded
        assert "scheduler_namespace_checked" in result
        assert result["scheduler_namespace_checked"] == "k9b"


class TestSchedulerDeploymentNamespace:
    """Verify scheduler deployment is always looked up in k9b namespace."""

    def test_scheduler_always_in_k9b_namespace_not_incident_namespace(self) -> None:
        """Critical: k9b-scheduler deployment is ONLY in k9b namespace.

        Kubernetes namespaces scope names - k9b-scheduler in k9b and k9b-scheduler
        in otel-demo are DIFFERENT deployments.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
            get_default_k9b_namespace,
        )

        # The default k9b namespace should be used for ALL scheduler lookups
        k9b_ns = get_default_k9b_namespace()
        assert k9b_ns == "k9b", (
            f"Default k9b namespace should be 'k9b', got {k9b_ns!r}"
        )

        # When running for an incident in otel-demo namespace:
        incident_namespace = "otel-demo"
        scheduler_namespace = get_default_k9b_namespace()

        # These should NEVER be the same for scheduler lookups
        assert scheduler_namespace != incident_namespace, (
            "Scheduler namespace (k9b) and incident namespace (otel-demo) "
            "should be different. The bug was using incident namespace for scheduler lookup."
        )
