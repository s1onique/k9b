#!/usr/bin/env python3
"""Pod-failure symptom verifier with state-aware polling.

Polls the injected pod until:
- success: phase=Running AND Ready=False AND readiness probe failure evidence
- fatal: ImagePullBackOff / ErrImagePull / CreateContainerConfigError / FailedScheduling
- timeout: still Pending/ContainerCreating/Pulling after deadline

Emits structured classes:
- pod_failure_symptom_observed: Success - readiness failure symptom confirmed
- pod_failure_symptom_pending: Non-fatal intermediate state (keep polling)
- pod_failure_symptom_image_pull_backoff: Fatal - image pull failure
- pod_failure_symptom_scheduling_failed: Fatal - scheduling failure
- pod_failure_symptom_timeout: Timeout - pod stuck in intermediate state

Usage:
    python scripts/verify_pod_failure_symptom.py \
        --kubeconfig <path> \
        --namespace <name> \
        --pod-name <name> \
        --deadline <seconds> \
        --poll-interval <seconds> \
        [--artifact-dir <path>]

Exit codes:
    0 - Symptom observed (pod running with readiness failure)
    1 - Fatal failure or timeout
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


def write_snapshots(artifact_dir: Path | None, snapshots: list[dict]) -> None:
    """Write poll snapshots to artifact directory."""
    if artifact_dir:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / "pod-failure-symptom-snapshots.json"
        path.write_text(json.dumps(snapshots, indent=2) + "\n")

# Symptom classes
# =============================================================================

class SymptomClass(StrEnum):
    """Structured symptom classification for pod-failure verifier.
    
    Uses StrEnum for type-safe string enum values.
    """
    
    OBSERVED = "pod_failure_symptom_observed"
    PENDING = "pod_failure_symptom_pending"
    IMAGE_PULL_BACKOFF = "pod_failure_symptom_image_pull_backoff"
    SCHEDULING_FAILED = "pod_failure_symptom_scheduling_failed"
    TIMEOUT = "pod_failure_symptom_timeout"
    CREATE_CONTAINER_CONFIG_ERROR = "pod_failure_symptom_create_container_config_error"


# =============================================================================
# Result data structure
# =============================================================================

@dataclass
class SymptomVerificationResult:
    """Result of pod-failure symptom verification."""
    symptom_class: SymptomClass
    fatal: bool
    pod_phase: str
    pod_ready: str  # "True", "False", or "Unknown"
    container_state: str  # "Running", "Waiting", "Terminated", or "Unknown"
    container_waiting_reason: str
    latest_event: str
    readiness_probe_failure_evidence: bool
    failure_reason: str
    elapsed_seconds: float
    poll_count: int
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["symptom_class"] = self.symptom_class.value
        return d


# =============================================================================
# Kubernetes helpers
# =============================================================================

