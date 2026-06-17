"""Shared fixtures for incident suggested checks tests.

This module provides test builders for SAFE-linked candidates,
plan payloads, and other helpers used across suggested-check test files.
"""

from __future__ import annotations


def make_linked_candidate(
    incident_id: str,
    candidate_id: str = "c1",
    description: str = "Check pod logs",
    title: str | None = None,
    rationale: str | None = None,
    risk_level: str | None = None,
) -> dict:
    """Create a safely linked candidate dict."""
    candidate = {
        "linkage_status": "linked",
        "incident_id": incident_id,
        "candidateId": candidate_id,
        "description": description,
    }
    if title:
        candidate["title"] = title
    if rationale:
        candidate["rationale"] = rationale
    if risk_level:
        candidate["riskLevel"] = risk_level
    return candidate


def make_partial_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
    namespace: str = "default",
    object_kind: str = "Pod",
    object_name: str = "my-pod",
) -> dict:
    """Create a partial candidate (no incident_id, has entity fields)."""
    return {
        "linkage_status": "partial",
        "candidateId": candidate_id,
        "description": description,
        "namespace": namespace,
        "objectKind": object_kind,
        "objectName": object_name,
    }


def make_unlinked_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
) -> dict:
    """Create an unlinked candidate."""
    return {
        "linkage_status": "unlinked",
        "candidateId": candidate_id,
        "description": description,
    }


def make_old_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
) -> dict:
    """Create a legacy candidate without linkage fields."""
    return {
        "candidateId": candidate_id,
        "description": description,
        "suggestedCommandFamily": "kubectl-logs",
    }


def make_plan_payload(
    candidates: list[dict],
    run_id: str = "run-123",
    linkage_status: str | None = None,
    linkage_reason: str | None = None,
) -> dict:
    """Create a plan payload dict."""
    plan = {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": candidates,
    }
    if linkage_status:
        plan["linkage_status"] = linkage_status
    if linkage_reason:
        plan["linkage_reason"] = linkage_reason
    return plan


# Shared test constants
DEFAULT_INCIDENT_ID = "default-pod-my-pod-crash-loop"
