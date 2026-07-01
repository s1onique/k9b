#!/usr/bin/env python3
"""
Profile model definitions - step registry and profile definitions.

This module contains the canonical step definitions and profile composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepCategory(Enum):
    """Step execution category."""
    POLICY = "policy"
    SMOKE = "smoke"
    FULL_SUITE = "full_suite"
    BUILD = "build"
    DOCS = "docs"


# =============================================================================
# Step Registry
# =============================================================================

# Canonical step definitions
STEPS: dict[str, dict] = {
    "ruff-lint": {
        "command": "ruff check src tests",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Ruff linting",
        "is_expensive": False,
    },
    "mypy": {
        "command": ".venv/bin/python -m mypy src/k8s_diag_agent",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Mypy type checking on main package",
        "is_expensive": False,
    },
    "mypy-tests": {
        "command": ".venv/bin/python -m mypy tests/__init__.py tests/path_helper.py tests/test_*.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Mypy type checking on tests",
        "is_expensive": False,
    },
    "llm-friendly": {
        "command": "python scripts/check_llm_friendly_files.py --quiet",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "File size check for LLM-friendliness",
        "is_expensive": False,
    },
    "package-import-hygiene": {
        "command": "python scripts/verify_package_import_hygiene.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Prevent src.k8s_diag_agent import anti-pattern",
        "is_expensive": False,
    },
    "no-new-llm-allowlist": {
        "command": "python scripts/verify_no_new_llm_allowlist.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "No new LLM allowlist entries policy",
        "is_expensive": False,
    },
    "shell-containment": {
        "command": "python scripts/verify_shell_containment.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Shell containment policy enforcement",
        "is_expensive": False,
    },
    "doctrine": {
        "command": "bash scripts/verify_factory_doctrine.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Factory doctrine verification",
        "is_expensive": False,
    },
    "dockerhub-base-images": {
        "command": "bash scripts/verify_dockerhub_base_images.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Dockerfile base image verification",
        "is_expensive": False,
    },
    "docker-workflow-hygiene": {
        "command": "bash scripts/verify_docker_workflow_hygiene.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Docker workflow registry hygiene",
        "is_expensive": False,
    },
    "helm-workflow-hygiene": {
        "command": "bash scripts/verify_helm_workflow_hygiene.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Helm version pin hygiene verification",
        "is_expensive": False,
    },
    "docker-build-locality": {
        "command": "bash scripts/verify_docker_build_locality.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Docker build locality hygiene",
        "is_expensive": False,
    },
    "structured-output": {
        "command": "bash scripts/verify_health_loop_structured_output.sh",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Health loop structured output hygiene",
        "is_expensive": False,
    },
    "agent-pipeline": {
        "command": "python scripts/verify_agentic_pipeline.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Agentic pipeline doctrine verification",
        "is_expensive": False,
    },
    "llm-evidence-boundaries": {
        "command": "python scripts/verify_llm_evidence_boundaries.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "LLM evidence boundaries verification",
        "is_expensive": False,
    },
    "llm-semantic-injection": {
        "command": "python scripts/verify_llm_semantic_injection_detection.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Semantic injection detection verification",
        "is_expensive": False,
    },
    "ci-gate-drift": {
        "command": "python scripts/verify_ci_gate_drift.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "CI workflow gate mapping drift check",
        "is_expensive": False,
    },
    "incident-report-quality": {
        "command": "python scripts/verify_incident_report_quality.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Incident report quality invariants",
        "is_expensive": False,
    },
    "artifact-immutability": {
        "command": "python scripts/verify_artifact_immutability.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Artifact immutability enforcement",
        "is_expensive": False,
    },
    "production-readiness-disclaimer": {
        "command": "python scripts/verify_production_readiness_disclaimer.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Production readiness disclaimers",
        "is_expensive": False,
    },
    "discovery-logging-hygiene": {
        "command": "python scripts/verify_discovery_logging_hygiene.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Discovery strategy logging hygiene",
        "is_expensive": False,
    },
    "next-check-sanitization": {
        "command": "python scripts/verify_next_check_sanitization_hygiene.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Next-check sanitization hygiene",
        "is_expensive": False,
    },
    "operator-projection-hygiene": {
        "command": "python scripts/verify_operator_projection_hygiene.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Operator projection sanitization hygiene",
        "is_expensive": False,
    },
    "pvc-rollout-policy": {
        "command": "python scripts/verify_pvc_rollout_policy.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "PVC rollout policy verification",
        "is_expensive": False,
    },
    "shared-pvc-colocation": {
        "command": "python scripts/verify_shared_pvc_colocation.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "Shared PVC colocation policy",
        "is_expensive": False,
    },
    "no-force-push-policy": {
        "command": "python scripts/verify_no_force_push_policy.py",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "No-force-push policy verification",
        "is_expensive": False,
    },
    "openapi-contract": {
        "command": ".venv/bin/python -m pytest tests/test_openapi_contract.py -v",
        "lane": "python",
        "category": StepCategory.POLICY,
        "description": "OpenAPI contract completeness gate",
        "is_expensive": False,
    },
    "unit-tests": {
        "command": "bash scripts/run_unit_tests.sh",
        "lane": "python",
        "category": StepCategory.FULL_SUITE,
        "description": "Full Python unit test suite",
        "is_expensive": True,
    },
    "docs-inventory": {
        "command": "python scripts/verify_docs_inventory.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs inventory integrity",
        "is_expensive": False,
    },
    "docs-claims-registry": {
        "command": "python scripts/verify_docs_claims_registry.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs claims registry integrity",
        "is_expensive": False,
    },
    "docs-claim-traceability": {
        "command": "python scripts/verify_docs_claim_traceability.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs claim traceability matrix",
        "is_expensive": False,
    },
    "docs-claim-candidates": {
        "command": "python scripts/scan_docs_claim_candidates.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs claim candidate scanning",
        "is_expensive": False,
    },
    "docs-claim-candidate-coverage": {
        "command": "python scripts/verify_docs_claim_candidate_coverage.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs claim candidate coverage verification",
        "is_expensive": False,
    },
    "docs-claim-candidate-dispositions": {
        "command": "python scripts/verify_docs_claim_candidate_dispositions.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Docs claim candidate dispositions verification",
        "is_expensive": False,
    },
    "docs-claim-disposition-csv-integrity": {
        "command": "python scripts/verify_docs_claim_disposition_csv_integrity.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Disposition shard CSV integrity verification",
        "is_expensive": False,
    },
    "docs-claim-disposition-semantic-diff-self-test": {
        "command": "python scripts/diff_docs_claim_dispositions.py --self-test",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Disposition semantic diff self-test",
        "is_expensive": False,
    },
    "docs-claim-candidate-backlog-report-self-test": {
        "command": "python scripts/run_backlog_report.py --self-test",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Claim candidate backlog report self-test",
        "is_expensive": False,
    },
    "data-model-docs": {
        "command": "python scripts/verify_data_model_docs.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Data model documentation hygiene",
        "is_expensive": False,
    },
    "llm-security-requirements": {
        "command": "python scripts/verify_llm_security_requirements.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "LLM security requirements register integrity",
        "is_expensive": False,
    },
    "security-claim-traceability": {
        "command": "python scripts/verify_security_claim_traceability.py",
        "lane": "python",
        "category": StepCategory.DOCS,
        "description": "Security claim traceability verification",
        "is_expensive": False,
    },
    "npm-ci": {
        "command": "npm ci",
        "lane": "frontend",
        "category": StepCategory.BUILD,
        "description": "Install frontend dependencies",
        "is_expensive": True,
    },
    "npm-test-ui": {
        "command": "bash scripts/run_frontend_ui_tests.sh",
        "lane": "frontend",
        "category": StepCategory.SMOKE,
        "description": "Frontend UI tests (smoke)",
        "is_expensive": True,
    },
    "npm-build": {
        "command": "npm run build",
        "lane": "frontend",
        "category": StepCategory.BUILD,
        "description": "Frontend production build",
        "is_expensive": True,
    },
    "helm-chart": {
        "command": "bash scripts/verify_helm_chart.sh",
        "lane": "helm",
        "category": StepCategory.POLICY,
        "description": "Helm chart verification",
        "is_expensive": False,
    },
    "helm-oci-login": {
        "command": "bash scripts/verify_helm_oci_login.sh",
        "lane": "helm",
        "category": StepCategory.POLICY,
        "description": "Helm OCI dual-login workaround verification",
        "is_expensive": False,
    },
}


# =============================================================================
# Profile Definitions
# =============================================================================

# Fast profile: excludes expensive steps
FAST_EXCLUDES: set[str] = {
    "unit-tests",
    "npm-ci",
    "npm-test-ui",
    "npm-build",
    "docs-claim-traceability",
    "docs-claim-candidates",
    "data-model-docs",
    "docs-claim-candidate-coverage",
    "docs-claim-candidate-dispositions",
    "docs-claim-disposition-csv-integrity",
    "docs-claim-disposition-semantic-diff-self-test",
    "docs-claim-candidate-backlog-report-self-test",
}

# Lane scopes map to full lane execution
LANE_SCOPES: set[str] = {"python", "frontend", "helm"}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class StepPlan:
    """A verification step plan."""
    profile: str
    scope: str
    steps: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    is_full_lane: bool = False


@dataclass
class ProfileMetadata:
    """Profile metadata for display."""
    name: str
    description: str
    target_time_seconds: int
    ideal_time_seconds: int
    escalation_command: str
    is_full_gate: bool


def get_skipped_reasons() -> dict[str, str]:
    """Get human-readable reasons for skipped steps."""
    return {
        "unit-tests": "Python full test suite",
        "npm-ci": "Frontend dependency install",
        "npm-test-ui": "Frontend UI test suite",
        "npm-build": "Frontend production build",
        "docs-claim-traceability": "Heavy docs traceability scan",
        "docs-claim-candidates": "Heavy docs claim scanning",
        "data-model-docs": "Data model documentation verification",
        "docs-claim-candidate-coverage": "Claim candidate coverage verification",
        "docs-claim-candidate-dispositions": "Claim candidate disposition verification",
        "docs-claim-disposition-csv-integrity": "Disposition CSV integrity check",
        "docs-claim-disposition-semantic-diff-self-test": "Disposition semantic diff self-test",
        "docs-claim-candidate-backlog-report-self-test": "Claim backlog report self-test",
    }
