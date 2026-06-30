"""Utility functions for diagnosis loop runtime.

This module provides pure utility functions used by the runtime envelope.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# =============================================================================
# Constants
# =============================================================================

# Strict regex for allowed run_id characters
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


# =============================================================================
# Safety Validation
# =============================================================================


def is_safe_run_id(run_id: str | None) -> bool:
    """Validate that a run_id is safe for path construction."""
    if not run_id:
        return False
    if _SAFE_RUN_ID_RE.fullmatch(run_id) is None:
        return False
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        return False
    return True


def compute_fingerprint(check: Mapping[str, object]) -> str:
    """Compute a fingerprint for a check to detect duplicates.

    Uses normalized check_id and parameters to create a stable hash.
    """
    check_id = str(check.get("check_id", ""))
    params = check.get("parameters", {})

    # Normalize: sort params keys for stable hashing
    if isinstance(params, dict):
        normalized_params = json.dumps(params, sort_keys=True)
    else:
        normalized_params = str(params)

    content = f"{check_id}:{normalized_params}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_case_file_hash(case_file: Mapping[str, object]) -> str:
    """Compute a hash of the case file for pass artifact."""
    signals = case_file.get("signals")
    events = case_file.get("events")
    key_fields = {
        "incident_id": case_file.get("incident", {}).get("incident_id", ""),
        "namespace": case_file.get("incident", {}).get("namespace", ""),
        "object_kind": case_file.get("incident", {}).get("object_kind", ""),
        "object_name": case_file.get("incident", {}).get("object_name", ""),
        "severity": case_file.get("incident", {}).get("severity", ""),
        "signals_count": len(signals) if isinstance(signals, (list, tuple)) else 0,
        "events_count": len(events) if isinstance(events, (list, tuple)) else 0,
    }
    content = json.dumps(key_fields, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def extract_evidence_hashes(runner_result: Any) -> list[str]:
    """Extract evidence hashes from runner result.

    Returns fingerprints of checks that produced new evidence.
    """
    if not runner_result:
        return []

    hashes: list[str] = []
    results = runner_result.get("results", [])

    if not isinstance(results, list):
        return []

    for result in results:
        if not isinstance(result, dict):
            continue

        # A check produces evidence if it completed successfully
        status = result.get("status", "")
        if status == "completed":
            check_id = str(result.get("check_id", ""))
            params = result.get("parameters", {})
            fp = hashlib.sha256(f"{check_id}:{json.dumps(params, sort_keys=True)}".encode()).hexdigest()[:16]
            hashes.append(fp)

    return hashes
