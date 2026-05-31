"""Ownership and routing derivation for unknown/missing-evidence items.

This module provides derivable ownership hints for unknowns so operators
can understand who should collect the missing signal and where to send follow-up.

Key principles:
- Ownership is derived-only (stateless) from available evidence signals.
- No invented certainty: ambiguous cases remain honestly "unknown".
- Ownership hints are concise and operator-readable.
- Existing clues are reused: method/command family, workstream, probable_layer,
  evidence_needed labels, owner fields, cluster-vs-fleet scope.
"""

from __future__ import annotations

from typing import Literal

# =============================================================================
# Evidence Owner Taxonomy
# =============================================================================


# Canonical evidence owner categories
# These represent the team or component most likely responsible for collecting
# the missing evidence signal.
EvidenceOwner = Literal[
    "platform",      # kubelet, node, control-plane, cluster API, cluster infrastructure
    "application",  # pod logs, application config, resource limits, container behavior
    "networking",   # service mesh, DNS, ingress, CNI, traffic policy
    "storage",       # PVC, volume, storage class, disk-pressure
    "security",      # policy, identity, cert, admission-control
    "observability", # metrics, logs, tracing, monitoring tooling
    "unknown",       # insufficient signal to infer ownership
]


# Mapping from Layer enum to preferred ownership category
_LAYER_TO_OWNER: dict[str, EvidenceOwner] = {
    "workload": "application",
    "node": "platform",
    "storage": "storage",
    "network": "networking",
    "observability": "observability",
    "rollout": "application",
}


# Method/command patterns mapped to ownership categories
# These keywords in method or evidence_needed suggest specific ownership
_METHOD_PATTERNS: dict[EvidenceOwner, tuple[str, ...]] = {
    "platform": (
        "kubelet",
        "node",
        "kube-apiserver",
        "kube-controller",
        "etcd",
        "scheduler",
        "control-plane",
        "control plane",
        "cgroup",
        "kernel",
        "systemd",
        "container runtime",
    ),
    "application": (
        "pod",
        "container",
        "deployment",
        "statefulset",
        "daemonset",
        "job",
        "cronjob",
        "application",
        "app config",
        "resource limit",
        "startup probe",
        "liveness probe",
        "readiness probe",
        "env",
        "configmap",
        "secret",
        "rollout",
        "image",
    ),
    "networking": (
        "service",
        "ingress",
        "endpoint",
        "dns",
        "coredns",
        "corefile",
        "networkpolicy",
        "cncf",
        "cilium",
        "calico",
        "flannel",
        "service mesh",
        "istio",
        "linkerd",
        "envoy",
        "lb",
        "load balancer",
        "nodeport",
        "clusterip",
    ),
    "storage": (
        "pvc",
        "pv",
        "storageclass",
        "storage class",
        "volume",
        "disk",
        "ceph",
        " EBS",
        "GCEPersistentDisk",
        "nfs",
        "mount",
        "emptydir",
        "hostpath",
    ),
    "security": (
        "rbac",
        "policy",
        "psp",
        "psyc",
        "networkpolicy",
        "certificate",
        "cert",
        "identity",
        "serviceaccount",
        "service account",
        "token",
        "imagepullsecret",
        "image pull secret",
        "securitycontext",
        "security context",
        "admission",
        "auth can-i",
    ),
    "observability": (
        "metrics",
        "metric",
        "prometheus",
        "grafana",
        "alertmanager",
        "fluentd",
        "fluent-bit",
        "tracing",
        "jaeger",
        "opentelemetry",
        "monitoring",
        "dashboard",
    ),
}


# Routing hint templates per ownership category
_ROUTING_HINTS: dict[EvidenceOwner, str] = {
    "platform": "Contact platform engineering or cluster operations team",
    "application": "Contact the application team or workload owner",
    "networking": "Contact the networking or platform team responsible for CNI/service mesh",
    "storage": "Contact the storage or platform team responsible for volumes",
    "security": "Contact the security or platform team responsible for RBAC/identity",
    "observability": "Check if observability tooling (metrics/logs) is properly deployed",
    "unknown": "Insufficient signal to determine evidence ownership",
}


# =============================================================================
# Derivation Logic
# =============================================================================


def _matches_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    """Check if text contains any of the patterns (case-insensitive)."""
    text_lower = text.lower()
    return any(pattern.lower() in text_lower for pattern in patterns)


def _derive_evidence_owner_from_method_and_evidence(
    method: str | None,
    evidence_needed: tuple[str, ...] | None,
) -> EvidenceOwner:
    """Derive evidence owner from method and evidence_needed patterns."""
    if not method and not evidence_needed:
        return "unknown"

    # Check method patterns first (highest priority)
    if method:
        for owner, patterns in _METHOD_PATTERNS.items():
            if _matches_pattern(method, patterns):
                return owner

    # Check evidence_needed patterns
    if evidence_needed:
        combined_evidence = " ".join(evidence_needed)
        for owner, patterns in _METHOD_PATTERNS.items():
            if _matches_pattern(combined_evidence, patterns):
                return owner

    return "unknown"


def _derive_evidence_owner_from_layer(probable_layer: str | None) -> EvidenceOwner:
    """Derive evidence owner from probable layer of origin."""
    if not probable_layer:
        return "unknown"
    return _LAYER_TO_OWNER.get(probable_layer.lower(), "unknown")


def _derive_evidence_owner_from_owner_field(owner: str | None) -> EvidenceOwner:
    """Derive evidence owner from existing owner field."""
    if not owner:
        return "unknown"

    owner_lower = owner.lower()

    # Map known owner values to evidence owners
    if owner_lower in ("platform", "platform-engineer", "cluster-ops", "clusterops"):
        return "platform"
    if owner_lower in ("app", "application", "app-team", "workload", "developer"):
        return "application"
    if owner_lower in ("network", "networking", "networking-team", "cni"):
        return "networking"
    if owner_lower in ("storage", "storage-team", "volumes"):
        return "storage"
    if owner_lower in ("security", "security-team", "rbac", "identity"):
        return "security"
    if owner_lower in ("observability", "monitoring", "sre", "ops"):
        return "observability"

    return "unknown"


def _derive_evidence_owner_from_workstream(workstream: str | None) -> EvidenceOwner | None:
    """Derive evidence owner hints from workstream context."""
    if not workstream:
        return None

    workstream_lower = workstream.lower()
    if "drift" in workstream_lower:
        return "platform"  # Fleet-wide drift typically owned by platform
    if "incident" in workstream_lower:
        return "application"  # Incident workstream often targets app-level evidence
    if "network" in workstream_lower:
        return "networking"
    if "storage" in workstream_lower:
        return "storage"
    if "security" in workstream_lower:
        return "security"

    return None


def derive_evidence_ownership(
    method: str | None,
    evidence_needed: tuple[str, ...] | None,
    probable_layer: str | None,
    owner: str | None,
    workstream: str | None,
    is_cross_cluster: bool = False,
) -> tuple[EvidenceOwner, str | None, float]:
    """Derive ownership hints for an unknown/missing-evidence item.

    This function combines multiple signals to produce the most likely ownership
    category, a concise routing hint, and a confidence score.

    Derivation priority:
    1. Existing owner field (highest confidence)
    2. Method/evidence_needed patterns (high confidence)
    3. Probable layer (medium confidence)
    4. Workstream context (low confidence)
    5. Cross-cluster scope (platform hint)

    Args:
        method: The diagnostic method or command family
        evidence_needed: Labels/commands describing the needed evidence
        probable_layer: Probable layer of origin from hypothesis
        owner: Existing owner field from deterministic next check
        workstream: Workstream context (incident | drift | network | etc)
        is_cross_cluster: Whether this spans multiple clusters

    Returns:
        Tuple of (evidence_owner, routing_hint, confidence_score)
        - evidence_owner: Most likely ownership category
        - routing_hint: Concise operator-readable routing instruction
        - confidence_score: 0.0-1.0 indicating derivation confidence
    """
    confidence_sources: list[tuple[EvidenceOwner, float]] = []

    # 1. Check existing owner field (highest confidence signal)
    if owner:
        owner_hint = _derive_evidence_owner_from_owner_field(owner)
        if owner_hint != "unknown":
            confidence_sources.append((owner_hint, 0.9))

    # 2. Check method and evidence_needed patterns
    method_hint = _derive_evidence_owner_from_method_and_evidence(method, evidence_needed)
    if method_hint != "unknown":
        confidence_sources.append((method_hint, 0.75))

    # 3. Check probable layer
    layer_hint = _derive_evidence_owner_from_layer(probable_layer)
    if layer_hint != "unknown":
        confidence_sources.append((layer_hint, 0.6))

    # 4. Check workstream context
    workstream_hint = _derive_evidence_owner_from_workstream(workstream)
    if workstream_hint:
        confidence_sources.append((workstream_hint, 0.4))

    # 5. Cross-cluster/fleet scope -> platform ownership
    if is_cross_cluster:
        confidence_sources.append(("platform", 0.5))

    # Determine final ownership: prefer the highest-confidence signal
    if not confidence_sources:
        return "unknown", _ROUTING_HINTS["unknown"], 0.0

    # Sort by confidence and pick the winner
    confidence_sources.sort(key=lambda x: x[1], reverse=True)
    best_owner, best_confidence = confidence_sources[0]

    # Get routing hint for the owner
    routing_hint = _ROUTING_HINTS.get(best_owner, _ROUTING_HINTS["unknown"])

    return best_owner, routing_hint, best_confidence


def format_ownership_fields(
    evidence_owner: EvidenceOwner,
    routing_hint: str | None,
    confidence_score: float,
) -> dict[str, object]:
    """Format ownership fields for inclusion in IncidentReportUnknownPayload.

    Args:
        evidence_owner: The derived ownership category
        routing_hint: The routing instruction for operators
        confidence_score: Confidence score 0.0-1.0

    Returns:
        Dict with formatted ownership fields, suitable for merging into payload
    """
    # Determine ownership confidence level
    if confidence_score >= 0.8:
        ownership_confidence = "high"
    elif confidence_score >= 0.6:
        ownership_confidence = "medium"
    elif confidence_score >= 0.4:
        ownership_confidence = "low"
    else:
        ownership_confidence = "unknown"

    fields: dict[str, object] = {
        "evidenceOwner": evidence_owner,
    }

    if routing_hint and evidence_owner != "unknown":
        fields["routingHint"] = routing_hint

    if confidence_score > 0:
        fields["ownershipConfidence"] = ownership_confidence

    return fields
