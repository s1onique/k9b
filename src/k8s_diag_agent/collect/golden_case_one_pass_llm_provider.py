"""Deterministic LLM provider for golden-case diagnosis loop.

This module provides a deterministic LLM provider that returns fixed
diagnoses based on golden-case evidence findings.
"""

from __future__ import annotations

import json
from typing import Any

from .golden_case_evidence_provider import GoldenCaseEvidenceProvider


class GoldenCaseDeterministicLLMProvider:
    """Deterministic LLM provider for golden cases."""

    def __init__(
        self,
        manifest: dict[str, Any],
        expected: dict[str, Any],
        evidence_provider: GoldenCaseEvidenceProvider,
    ) -> None:
        self.manifest = manifest
        self.expected = expected
        self.evidence_provider = evidence_provider
        self._findings = evidence_provider.extract_findings()

    def complete(self, prompt: str) -> str:
        """Generate deterministic completion for the given prompt."""
        del prompt
        findings = self._findings
        sanitized_namespace = "<LAB_NAMESPACE>"
        sanitized_pod_name = self.manifest.get("fixture_name", "<APP_NAME>")

        if (
            findings["pod_running"]
            and findings["pod_not_ready"]
            and findings["readiness_probe_failure_evidence"]
        ):
            summary = (
                f"Pod {sanitized_namespace}/{sanitized_pod_name} is Running but NotReady. "
                "The readiness probe consistently fails (exit code 1), "
                "preventing the pod from being marked as Ready."
            )
            likely_causes = ["readiness probe failure", "application health check misconfiguration"]
            supporting_evidence = [
                "Pod is Running phase with 0/1 ready containers",
                "Readiness probe command /bin/false always fails",
                "Warning event: Unhealthy readiness probe",
            ]
            # Return structured proposals with check_ids that match fake handlers
            # The orchestrator uses these check_ids to find matching fake handlers
            recommended_investigations = [
                {
                    "check_id": "pod_describe",
                    "title": "Get detailed pod status including probe configuration",
                    "rationale": "Describe the pod to see probe configuration and status",
                    "priority": 1,
                    "risk_level": "low",
                    "read_only": True,
                    "source": "llm-review",
                },
                {
                    "check_id": "pod_events",
                    "title": "Check for readiness probe failure events",
                    "rationale": "List events to find readiness probe failure messages",
                    "priority": 2,
                    "risk_level": "low",
                    "read_only": True,
                    "source": "llm-review",
                },
                {
                    "check_id": "pod_logs",
                    "title": "Verify application behavior",
                    "rationale": "Check pod logs for any errors",
                    "priority": 3,
                    "risk_level": "low",
                    "read_only": True,
                    "source": "llm-review",
                },
            ]
            uncertainties = ["Exact probe failure timing", "Application startup time requirements"]
            # Return medium confidence so the planner decides to run checks.
            # This proves the ACT requirement that fake handlers are exercised.
            # High confidence would cause early stop without running checks.
            confidence = "medium"
        else:
            summary = "Unable to determine root cause from available evidence."
            likely_causes = []
            supporting_evidence = []
            recommended_investigations = []
            uncertainties = ["Insufficient evidence for diagnosis"]
            confidence = "unknown"

        return json.dumps({
            "summary": summary,
            "likely_causes": likely_causes,
            "supporting_evidence": supporting_evidence,
            "recommended_investigations": recommended_investigations,
            "uncertainties": uncertainties,
            "confidence": confidence,
        })
