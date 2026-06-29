"""Shared helpers for k9b baseline installer."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .k9b_lab_common_helpers import write_text_artifact


def run_kubectl_collector(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    kubectl_collectors: list[tuple[str, list[str]]],
) -> None:
    """Run kubectl commands and write output as artifacts.

    On non-zero exit code, also writes stderr and exit code as sibling artifacts.
    """
    for filename, cmd in kubectl_collectors:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace] + cmd,
            capture_output=True, text=True, timeout=15,
        )
        write_text_artifact(artifact_dir, filename, result.stdout or "(empty)")
        if result.returncode != 0:
            write_text_artifact(artifact_dir, f"{filename}.exit-code.txt", str(result.returncode))
            if result.stderr:
                write_text_artifact(artifact_dir, f"{filename}.stderr.log", result.stderr)
