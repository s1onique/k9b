"""Budget status helpers for local mode."""

from __future__ import annotations

import logging
from pathlib import Path

from scripts._k9b_budget_backend_scripts import _BACKEND_STATUS_SCRIPT

_logger = logging.getLogger(__name__)

DIAGNOSIS_REVIEW_PACKET_SUFFIX = "-diagnosis-review-packet.json"
LOOP_PASS_SUFFIX = "-diagnosis-loop-pass.json"

BUDGET_RESETTABLE_SUFFIXES = (
    "-diagnosis-review-packet.json",
    "-diagnosis-loop-pass.json",
    "-read-only-check-result.json",
    "-next-check-budget.json",
)


def _matches_artifact(name: str, incident_id: str) -> bool:
    """Check if filename matches budget-affecting artifact (suffix-aware)."""
    if not name.startswith(f"auto-{incident_id}-"):
        return False
    return name.endswith(BUDGET_RESETTABLE_SUFFIXES)


def get_budget_status_local(
    runs_dir: Path,
    incident_id: str,
) -> dict:
    """Get diagnosis loop budget status (local mode)."""
    health_root = runs_dir if runs_dir.name == "health" else runs_dir / "health"
    external_dir = health_root / "external-analysis"

    if not external_dir.exists():
        return {
            "incident_id": incident_id,
            "budget_clean": True,
            "review_packet_count": 0,
            "loop_pass_count": 0,
            "other_auto_count": 0,
            "total_auto_artifact_count": 0,
            "budget_exhausted": False,
        }

    review_packets: list[str] = []
    loop_passes: list[str] = []
    other_auto: list[str] = []

    try:
        for path in external_dir.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if not _matches_artifact(name, incident_id):
                continue

            relative = str(path.relative_to(external_dir))
            if name.endswith(DIAGNOSIS_REVIEW_PACKET_SUFFIX):
                review_packets.append(relative)
            elif name.endswith(LOOP_PASS_SUFFIX):
                loop_passes.append(relative)
            else:
                other_auto.append(relative)
    except OSError:
        pass

    total = len(review_packets) + len(loop_passes) + len(other_auto)

    return {
        "incident_id": incident_id,
        "budget_clean": total == 0,
        "review_packet_count": len(review_packets),
        "loop_pass_count": len(loop_passes),
        "other_auto_count": len(other_auto),
        "total_auto_artifact_count": total,
        "budget_exhausted": total > 0,
        "review_packets": review_packets,
        "loop_passes": loop_passes,
        "other_auto": other_auto,
    }


# Import for backend status
import json
import subprocess


def get_budget_status_in_backend(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    deployment: str = "k9b-backend",
    container: str = "backend",
    backend_runs_dir: str = "/app/runs",
) -> dict:
    """Get diagnosis loop budget status in backend container (k8s mode)."""
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "exec",
        "-n", namespace,
        f"deploy/{deployment}",
        "-c", container,
        "--",
        "python", "-c", _BACKEND_STATUS_SCRIPT,
        incident_id,
        backend_runs_dir,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {
            "incident_id": incident_id,
            "error": "timeout",
            "budget_clean": False,
            "review_packet_count": 0,
            "loop_pass_count": 0,
            "other_auto_count": 0,
            "total_auto_artifact_count": 0,
            "budget_exhausted": False,
        }

    if result.returncode != 0:
        return {
            "incident_id": incident_id,
            "error": f"kubectl_exec_failed:{result.stderr[:500]}",
            "budget_clean": False,
            "review_packet_count": 0,
            "loop_pass_count": 0,
            "other_auto_count": 0,
            "total_auto_artifact_count": 0,
            "budget_exhausted": False,
        }

    try:
        data = json.loads(result.stdout.strip())
        if not data.get("exists", False):
            return {
                "incident_id": incident_id,
                "budget_clean": True,
                "review_packet_count": 0,
                "loop_pass_count": 0,
                "other_auto_count": 0,
                "total_auto_artifact_count": 0,
                "budget_exhausted": False,
            }

        review = data.get("review_packet_count", 0)
        loop = data.get("loop_pass_count", 0)
        other = data.get("other_auto_count", 0)
        total = review + loop + other

        return {
            "incident_id": incident_id,
            "budget_clean": total == 0,
            "review_packet_count": review,
            "loop_pass_count": loop,
            "other_auto_count": other,
            "total_auto_artifact_count": total,
            "budget_exhausted": total > 0,
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "incident_id": incident_id,
            "error": f"parse_error: {result.stdout[:200]}",
            "budget_clean": False,
            "review_packet_count": 0,
            "loop_pass_count": 0,
            "other_auto_count": 0,
            "total_auto_artifact_count": 0,
            "budget_exhausted": False,
        }
