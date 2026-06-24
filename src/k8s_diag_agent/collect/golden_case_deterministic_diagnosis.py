"""Deterministic diagnosis provider for golden cases.

This module provides the DeterministicDiagnosisProvider class that produces
safe, bounded diagnosis output for known golden case scenarios.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from .golden_case_evidence_provider import GoldenCaseEvidenceProvider
from .golden_case_providers_constants import _FORBIDDEN_PRIMARY_CAUSE_PATTERNS

if TYPE_CHECKING:
    from .incident_llm_diagnosis import IncidentDiagnosisLLM

__all__ = ["DeterministicDiagnosisProvider", "build_deterministic_diagnosis"]


class DeterministicDiagnosisProvider:
    """Deterministic diagnosis provider for known golden cases.

    This provider returns controlled, predictable diagnosis output for
    known case scenarios without requiring LLM access.

    Design constraints:
    - Returns deterministic output for the same case_id
    - Enforces safety checks on output
    - Does NOT bake regex diagnosis directly as production behavior
    - Used for wiring verification, not general diagnosis
    """

    def __init__(
        self,
        manifest: dict[str, object],
        expected: dict[str, object],
        evidence_provider: GoldenCaseEvidenceProvider,
    ) -> None:
        """Initialize with golden-case metadata.

        Args:
            manifest: Golden-case manifest.json
            expected: Golden-case expected.json
            evidence_provider: Provider for evidence content
        """
        self.manifest = manifest
        self.expected = expected
        self.evidence_provider = evidence_provider
        self._findings = evidence_provider.extract_findings()

    def diagnose(self) -> dict[str, object]:
        """Generate deterministic diagnosis for the golden case.

        Returns:
            Diagnosis report matching the production schema
        """
        case_id = self.manifest.get("case_id", "unknown")

        # Build diagnosis based on findings
        findings = self._findings

        # Sanitized placeholders derived from golden-case metadata
        sanitized_namespace = "<LAB_NAMESPACE>"
        sanitized_pod_name = "<APP_NAME>"

        if (
            findings["pod_running"]
            and findings["pod_not_ready"]
            and findings["readiness_probe_failure_evidence"]
        ):
            # Correct diagnosis for readiness probe failure case
            category = "readiness_probe_failure"
            root_cause = "readiness probe failure"
            confidence = "high"
            description = (
                f"Pod {sanitized_namespace}-{sanitized_pod_name} is Running but NotReady. "
                "The readiness probe consistently fails (exit code 1), "
                "preventing the pod from being marked as Ready. "
                "The probe command /bin/false always returns non-zero exit code."
            )
        else:
            # Fallback for other cases
            category = "unknown"
            root_cause = "insufficient evidence"
            confidence = "low"
            description = "Unable to determine root cause from available evidence."

        # Check for forbidden conclusions in description
        forbidden_observed: list[str] = []
        for pattern in _FORBIDDEN_PRIMARY_CAUSE_PATTERNS:
            if pattern.search(description):
                forbidden_observed.append(pattern.pattern)

        # Build evidence refs from expected evidence files
        evidence_refs: list[str] = []
        expected_files = self.manifest.get("expected_evidence_files", [])
        if isinstance(expected_files, list):
            for ref in expected_files:
                if self.evidence_provider.has_evidence(ref):
                    evidence_refs.append(ref)

        # Build next checks (read-only only) using sanitized placeholders
        next_checks = [
            {
                "description": "Describe the failing pod to see detailed probe status",
                "owner": "platform-engineer",
                "method": f"kubectl describe pod {sanitized_namespace}-{sanitized_pod_name} -n {sanitized_namespace}",
                "evidence_needed": ["probe status", "container state"],
            },
            {
                "description": "Check pod YAML for readiness probe configuration",
                "owner": "platform-engineer",
                "method": f"kubectl get pod {sanitized_namespace}-{sanitized_pod_name} -n {sanitized_namespace} -o yaml",
                "evidence_needed": ["readinessProbe spec", "probe command"],
            },
        ]

        # Verify mutation patterns in description
        mutation_proposals_observed: list[str] = []
        mutation_patterns = [
            re.compile(r"kubectl\s+apply", re.IGNORECASE),
            re.compile(r"kubectl\s+delete", re.IGNORECASE),
            re.compile(r"helm\s+upgrade", re.IGNORECASE),
            re.compile(r"kubectl\s+edit", re.IGNORECASE),
        ]
        for pattern in mutation_patterns:
            if pattern.search(description):
                mutation_proposals_observed.append(pattern.pattern)

        return {
            "case_id": case_id,
            "category": category,
            "root_cause": root_cause,
            "confidence": confidence,
            "description": description,
            "evidence_refs": evidence_refs,
            "read_only": True,
            "allowed_actions": [],
            "forbidden_actions_observed": forbidden_observed,
            "mutation_proposals_observed": mutation_proposals_observed,
            "diagnosis_engine": "deterministic-golden-case-provider",
            "next_checks": next_checks,
        }


def build_deterministic_diagnosis(
    manifest: dict[str, object],
    expected: dict[str, object],
    evidence_provider: GoldenCaseEvidenceProvider,
    *,
    llm: IncidentDiagnosisLLM | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build a diagnosis using the deterministic provider.

    This function creates a diagnosis that matches the production schema
    using deterministic golden-case data. It can optionally use an LLM
    provider if one is injected, but defaults to deterministic output.

    Args:
        manifest: Golden-case manifest.json
        expected: Golden-case expected.json
        evidence_provider: Provider for evidence content
        llm: Optional LLM provider (not used in this deterministic implementation)
        now: Optional datetime for timestamp

    Returns:
        Diagnosis report matching the production schema
    """
    provider = DeterministicDiagnosisProvider(manifest, expected, evidence_provider)
    return provider.diagnose()
