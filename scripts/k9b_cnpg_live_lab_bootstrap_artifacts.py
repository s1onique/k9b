#!/usr/bin/env python3
"""Failure artifact collection functions for CNPG Live Lab.

This module contains functions for collecting failure artifacts during
bootstrap failures.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from .k9b_cnpg_live_lab_helpers import (
    log,
    write_json_atomically,
)


def collect_failure_artifacts(
    kubeconfig: str | None,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
    image_tag: str = "unknown",
) -> None:
    """Collect failure artifacts."""
    log("Collecting failure artifacts...")
    diagnosis.heading(2, "Failure Artifacts")

    if not namespace or not kubeconfig:
        diagnosis.text("No namespace or kubeconfig provided for artifact collection")
        diagnosis.save()
        return

    # Collect kubectl artifacts
    kubectl_artifacts = [
        ("namespace-events.txt", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ("pods.txt", ["get", "pods", "-n", namespace, "-o", "wide"]),
        ("services.txt", ["get", "svc", "-n", namespace]),
        ("pvc.txt", ["get", "pvc", "-n", namespace]),
    ]

    for filename, cmd in kubectl_artifacts:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig] + cmd,
            capture_output=True,
            text=True,
        )
        (artifact_dir / filename).write_text(result.stdout or result.stderr or "(empty)")
        diagnosis.bullet(f"{diagnosis.inline_code(filename)}")

    # CNPG CRDs
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "crd", "clusters.postgresql.cnpg.io"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "get", "clusters", "-n", namespace, "-o", "yaml"],
            capture_output=True,
            text=True,
        )
        (artifact_dir / "cnpg.txt").write_text(result.stdout or result.stderr or "(empty)")
        diagnosis.bullet(f"{diagnosis.inline_code('cnpg.txt')}")

    # Generate summary.json with proper JSON
    summary = {
        "failure_class": preflight.failure_class or "unknown",
        "failure_stage": preflight.failure_stage or "unknown",
        "active_identity": preflight.active_identity or "unknown",
        "namespace": namespace,
        "release": "k9b",
        "image_tag": image_tag,
        "next_suggested_action": "Review lab-diagnosis.md for root cause and required fix",
    }
    write_json_atomically(artifact_dir / "summary.json", summary)
    diagnosis.bullet(f"{diagnosis.inline_code('summary.json')}")

    # Next steps
    diagnosis.heading(2, "Next Steps")
    diagnosis.text("1. Review the diagnosis file for root cause analysis")
    diagnosis.text("2. Check the summary file for failure classification")
    diagnosis.text("3. Address the identified issue and re-run the workflow")
    diagnosis.save()
