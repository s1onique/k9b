"""Tests for safety enforcement in incident diagnosis service.

These tests verify that the service properly enforces safety policies,
rejecting diagnoses that contain mutation proposals or forbidden conclusions.
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_diagnosis_service import _enforce_safety


def test_enforce_safety_rejects_mutation_in_description() -> None:
    """Safety enforcement rejects mutation proposals in description."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "kubectl apply -f deployment.yaml to fix",
        "next_checks": [],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Mutation proposal" in e for e in errors)


def test_enforce_safety_rejects_mutation_in_next_checks() -> None:
    """Safety enforcement rejects mutation proposals in next_checks methods."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "Issue detected",
        "next_checks": [
            {"method": "kubectl scale deployment myapp --replicas=3"}
        ],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Mutation proposal" in e for e in errors)


def test_enforce_safety_rejects_forbidden_conclusions() -> None:
    """Safety enforcement rejects forbidden diagnosis conclusions."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "This is ImagePullBackOff",
        "next_checks": [],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Forbidden conclusion" in e for e in errors)


def test_enforce_safety_accepts_valid_diagnosis() -> None:
    """Safety enforcement accepts valid read-only diagnosis."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "Readiness probe failure detected",
        "next_checks": [
            {"method": "kubectl describe pod <NAME> -n <NS>"}
        ],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is True
    assert len(errors) == 0
