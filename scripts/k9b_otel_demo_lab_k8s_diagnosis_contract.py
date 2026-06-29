#!/usr/bin/env python3
"""Contract definitions for K8s multi-pass diagnosis phase.

This module contains the evidence schema and factory functions for
the P4c diagnosis phase. It defines the structure of diagnosis evidence
without any execution logic.
"""

from __future__ import annotations

import time
from typing import Any

from scripts.k9b_otel_demo_lab_constants import SHIPPING_DEPLOYMENT
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    DIAGNOSIS_SOURCE_REAL,
    MIN_REQUIRED_PASSES,
    PHASE_NAME,
)


def create_initial_evidence(
    target_namespace: str,
) -> dict[str, Any]:
    """Create initial evidence dict with full schema.

    This initializes all fields with safe defaults, including
    metadata fields required by the verifier.

    Args:
        target_namespace: Target K8s namespace

    Returns:
        Initialized evidence dict
    """
    return {
        # Identification
        "phase": PHASE_NAME,
        "scenario": "unschedulable-shipping-rollout",
        "target_deployment": SHIPPING_DEPLOYMENT,
        "target_namespace": target_namespace,
        "timestamp": time.time(),
        # Diagnosis source metadata (required by verifier)
        "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
        "simulation_used": False,
        "automatic_loop_enabled": False,
        "real_loop_invoked": False,
        "real_pass_artifacts_found": False,
        "pass_artifact_paths": [],
        "provider_invocation_attempted": False,
        "review_packet_found": False,
        "diagnosis_loop_module": None,
        # Loop status
        "loop_status": None,
        # Pass tracking
        "pass_count": 0,
        "pass_run_ids": [],
        "min_required_passes": MIN_REQUIRED_PASSES,
        # Safety contract
        "read_only": True,
        "read_only_violations": [],
        "allowed_actions": [],
        "requested_checks": [],
        "executed_checks": [],
        # Diagnosis output
        "diagnosis_started": None,
        "diagnosis_completed": None,
        "loop_status_detail": None,
        "root_cause_summary": "",
        "root_cause_matches": {},
        # Root-cause term checks
        "mentions_shipping": False,
        "mentions_node_selector": False,
        "mentions_selector_key": False,
        "mentions_selector_value": False,
        "mentions_no_matching_node": False,
        # Validation state
        "validation_success": False,
        "failure_reason": None,
        # Paths
        "detection_evidence_path": None,
        "raw_diagnosis_artifact_path": None,
        "review_packet_path": None,
    }


# Schema field names for reference
DIAGNOSIS_EVIDENCE_FIELDS = [
    "phase",
    "scenario",
    "incident_id",
    "candidate_class",
    "target_namespace",
    "target_deployment",
    "diagnosis_started",
    "diagnosis_completed",
    "loop_status",
    "pass_count",
    "pass_run_ids",
    "read_only",
    "allowed_actions",
    "requested_checks",
    "executed_checks",
    "root_cause_summary",
    "root_cause_matches",
    "mentions_shipping",
    "mentions_node_selector",
    "mentions_selector_key",
    "mentions_selector_value",
    "mentions_no_matching_node",
    "failure_reason",
    "raw_diagnosis_artifact_path",
    "review_packet_path",
]
