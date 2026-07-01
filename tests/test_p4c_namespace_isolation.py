"""Regression test: P4c must use k9b namespace for backend-targeted diagnosis.

Bug: P4c was passing config.namespace (otel-demo) to run_diagnosis_loop,
but the backend runs in k9b namespace. kubectl exec against deploy/k9b-backend
must use -n k9b to find the deployment.

This test ensures the phase uses DEFAULT_K9B_NAMESPACE for backend calls,
not the incident namespace (otel-demo).

See: https://github.com/s1onique/k9b/issues/[issue] for context.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_phase_uses_k9b_namespace_for_backend_diagnosis() -> None:
    """Phase passes k9b namespace to run_diagnosis_loop, not incident namespace."""
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
        DIAGNOSIS_SOURCE_REAL,
    )
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
        phase_p4c_verify_k8s_mult_pass_diagnosis,
    )
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_config import (
        DEFAULT_K9B_NAMESPACE,
    )
    from scripts.k9b_otel_demo_lab_types import LabConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)

        # Create P3c evidence
        p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
        p3c_dir.mkdir(parents=True)
        p3c_evidence = {
            "discovery_success": True,
            "validation_success": True,
            "incident_id": "inc-123",
            "candidate_class": "pending_pod",
        }
        (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

        # Track the namespace passed to run_diagnosis_loop
        captured_namespace: list[str] = []

        def mock_run_diagnosis_loop(**kwargs: object) -> dict[str, object]:
            captured_namespace.append(str(kwargs.get("namespace", "")))
            return {
                "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
                "simulation_used": False,
                "automatic_loop_enabled": True,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/path/pass1.json", "/path/pass2.json"],
                "provider_invocation_attempted": True,
                "review_packet_found": True,
                "diagnosis_loop_module": "k8s_diag_agent.collect.incident_diagnosis_auto_loop",
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
                "requested_checks": [],
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing. No node in the cluster has "
                    "this label, so the shipping pod cannot be scheduled."
                ),
                "artifact_path": "/path",
                "review_packet_path": "/path/review.json",
            }

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
            side_effect=mock_run_diagnosis_loop,
        ):
            # config.namespace is otel-demo (incident namespace)
            config = LabConfig(
                kubeconfig="/tmp/kubeconfig",
                artifact_dir=str(artifact_dir),
                namespace="otel-demo",  # Incident is in otel-demo namespace
            )
            phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

        # The phase should have called run_diagnosis_loop with k9b namespace,
        # NOT otel-demo namespace (the incident namespace)
        assert len(captured_namespace) == 1, "run_diagnosis_loop should be called once"
        assert captured_namespace[0] == DEFAULT_K9B_NAMESPACE, (
            f"Expected namespace={DEFAULT_K9B_NAMESPACE} (k9b backend namespace), "
            f"but got namespace={captured_namespace[0]!r}. "
            f"The backend runs in k9b namespace; kubectl exec must use -n k9b."
        )
        assert captured_namespace[0] != "otel-demo", (
            "Bug: run_diagnosis_loop was called with otel-demo (incident namespace) "
            "instead of k9b (backend namespace). "
            "kubectl exec against deploy/k9b-backend must use -n k9b to find the deployment."
        )
