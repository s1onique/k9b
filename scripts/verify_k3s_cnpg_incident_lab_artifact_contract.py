"""Contracts for verify_k3s_cnpg_incident_lab_artifact.

This module contains types, constants, and data structures used
across the verification pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Import from sanitizer for shared constants
from sanitize_live_lab_artifacts_contract import (
    Finding,
    FindingKind,
)

# ============================================================================
# VERIFICATION CONTEXT
# ============================================================================

@dataclass
class VerificationContext:
    """Context for artifact verification."""
    artifact_dir: Path
    verbose: bool = False
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_finding(self, kind: str, message: str, file: str, context: str | None = None) -> None:
        """Add a finding with deduplication."""
        finding = Finding(kind=kind, message=message, file=file, context=context)
        # Deduplicate
        for existing in self.findings:
            if (existing.kind == finding.kind and
                existing.message == finding.message and
                existing.file == finding.file and
                existing.context == finding.context):
                return
        self.findings.append(finding)

    def add_error(self, message: str) -> None:
        """Add a verification error."""
        self.errors.append(message)

    def add_fatal(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add a fatal finding (actual secret detected)."""
        self.add_finding(FindingKind.FATAL, message, file, context)

    def add_warning(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add a warning finding (sensitive metadata retained)."""
        self.add_finding(FindingKind.WARNING, message, file, context)

    def add_info(self, message: str, file: str = "", context: str | None = None) -> None:
        """Add an info finding (benign Kubernetes reference)."""
        self.add_finding(FindingKind.INFO, message, file, context)


# ============================================================================
# SAFE KUBERNETES VOCABULARY
# ============================================================================

# Safe Kubernetes field patterns that should NOT trigger fatal findings
# These are Kubernetes vocabulary, not actual secrets
SAFE_K8S_PATTERNS: list[re.Pattern[str]] = [
    # Secret references
    re.compile(r"(?i)secretName\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)secretRef\s*[:=]\s*\{"),
    re.compile(r"(?i)secretNames\s*[:=]\s*\["),
    # Service account references
    re.compile(r"(?i)serviceAccountName\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)serviceAccount\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)serviceAccountToken\s*[:=]"),
    # Auto-mount flags
    re.compile(r"(?i)automountServiceAccountToken\s*[:=]\s*(true|false)"),
    # CNPG specific
    re.compile(r"(?i)clientCASecret\s*[:=]\s*[\w-]+"),
    re.compile(r"(?i)caSecret\s*[:=]\s*[\w-]+"),
    # RBAC
    re.compile(r"(?i)roleRef\s*[:=]"),
    re.compile(r"(?i)subjects\s*[:=]"),
    # Auth mode
    re.compile(r"(?i)auth\s*[:=]\s*[\w]+"),
    re.compile(r"(?i)authMode\s*[:=]"),
    re.compile(r"(?i)inCluster\s*[:=]"),
    re.compile(r"(?i)incluster\s*[:=]"),
    # Kubeconfig paths (not content)
    re.compile(r"(?i)kubeconfigPath\s*[:=]"),
    re.compile(r"(?i)kubeconfig\s*[:=]\s*[\/\w.-]+"),
    # RBAC resources
    re.compile(r"(?i)resources\s*[:=]\s*\[\s*[\"']secrets[\"']"),
    re.compile(r"(?i)kind\s*[:=]\s*[\"']?(Secret|ClusterRole|ClusterRoleBinding|Role|RoleBinding)[\"']?", re.IGNORECASE),
    # CNPG fields
    re.compile(r"(?i)secretTemplate\s*[:=]"),
    re.compile(r"(?i)namespace\s*[:=]\s*[\w-]+"),
]

# Known benign patterns in kubectl output
BENIGN_K8S_PATTERNS: list[re.Pattern[str]] = [
    # kubectl describe output commonly mentions secrets
    re.compile(r"This\s+pod\s+has\s+the\s+following\s+secret\s+credentials:", re.IGNORECASE),
    re.compile(r"secrets\s+referenced\s+by\s+\w+\s+:", re.IGNORECASE),
    # CNPG cluster status fields
    re.compile(r"(?i)secretName\s*[:=]\s*[\w-]+"),
    # Pod volume projections
    re.compile(r"(?i)projected\s*serviceAccountToken"),
]


# ============================================================================
# REQUIRED ARTIFACT STRUCTURE
# ============================================================================

# Required artifact structure.
REQUIRED_ARTIFACTS = {
    "lab-result.json": {"required": True, "type": "file"},
}

REQUIRED_BASELINE = {
    "nodes.txt": {"required": True, "type": "file"},
    "pods.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
    "k9b-status.json": {"required": True, "type": "file"},
}

REQUIRED_INCIDENT = {
    "injected-change.yaml": {"required": True, "type": "file"},
    "pods.txt": {"required": True, "type": "file"},
    "events.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
}

REQUIRED_INCIDENT_K9B = {
    "k9b-incidents.json": {"required": True, "type": "file"},
    "k9b-incident-detail.json": {"required": False, "type": "file"},
}

REQUIRED_FINAL = {
    "pods.txt": {"required": True, "type": "file"},
    "events.txt": {"required": True, "type": "file"},
    "cnpg-clusters.json": {"required": True, "type": "file"},
}

REQUIRED_LOGS = {
    "lab-runner.log": {"required": True, "type": "file"},
}
