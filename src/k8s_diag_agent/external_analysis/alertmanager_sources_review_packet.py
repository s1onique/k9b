"""Alertmanager sources review packet - downloadable evidence for the "2 AlertManagers" problem.

This module provides the review packet model that explains WHY K9B discovered 2 Alertmanager
sources and whether they are genuinely distinct or service aliases pointing to the same backend.

Schema version: k9b.alertmanager_sources.review_packet.v1

Design rationale:
- This is evidence, not a diagnosis. It provides structured context for the operator to
  understand the "2 AlertManagers" state without K9B making heuristic dedupe decisions.
- By default, K9B does NOT dump raw config data. The Alertmanager v2 status response
  includes config data, so K9B records a hash plus selected redacted metadata unless
  an explicit unsafe/debug flag is enabled.
- Packet is designed for download via UI button, enabling offline analysis and audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..identity.artifact import new_artifact_id

# Schema version for the review packet format
SCHEMA_VERSION = "k9b.alertmanager_sources.review_packet.v1"

# Redaction policy constants
REDACTION_ALERTMANAGER_CONFIG = "sha256_only"
REDACTION_ANNOTATIONS = "secret_like_values_redacted"
REDACTION_TOKENS = "redacted"


@dataclass(frozen=True)
class RuntimeIdentity:
    """Runtime identity from Alertmanager /api/v2/status probe.
    
    Captures evidence about the actual running Alertmanager instance without
    storing sensitive configuration data.
    """
    probe_attempted: bool = False
    ready: bool = False
    healthy: bool = False
    alertmanager_version: str | None = None
    cluster_status: str | None = None
    cluster_peer_count: int = 0
    config_sha256: str | None = None
    # Supporting evidence: counts/hashes only, not raw payloads
    receiver_count: int | None = None
    silence_count: int | None = None
    alert_group_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_attempted": self.probe_attempted,
            "ready": self.ready,
            "healthy": self.healthy,
            "alertmanager_version": self.alertmanager_version,
            "cluster_status": self.cluster_status,
            "cluster_peer_count": self.cluster_peer_count,
            "config_sha256": self.config_sha256,
            "receiver_count": self.receiver_count,
            "silence_count": self.silence_count,
            "alert_group_count": self.alert_group_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeIdentity:
        return cls(
            probe_attempted=bool(data.get("probe_attempted", False)),
            ready=bool(data.get("ready", False)),
            healthy=bool(data.get("healthy", False)),
            alertmanager_version=data.get("alertmanager_version"),
            cluster_status=data.get("cluster_status"),
            cluster_peer_count=int(data.get("cluster_peer_count", 0)),
            config_sha256=data.get("config_sha256"),
            receiver_count=data.get("receiver_count"),
            silence_count=data.get("silence_count"),
            alert_group_count=data.get("alert_group_count"),
        )


@dataclass(frozen=True)
class KubernetesIdentity:
    """Kubernetes-level identity for the Alertmanager source.
    
    Captures Service, EndpointSlice, Pod, and owner reference information
    for deduplication analysis.
    """
    service_uid: str | None = None
    service_type: str | None = None  # ClusterIP, Headless, etc.
    labels: dict[str, str] = field(default_factory=dict)
    annotations_redacted: dict[str, str] = field(default_factory=dict)  # Secret-like values redacted
    selector: dict[str, str] = field(default_factory=dict)
    ports: list[dict[str, Any]] = field(default_factory=list)
    owner_references: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_uid": self.service_uid,
            "service_type": self.service_type,
            "labels": dict(self.labels),
            "annotations_redacted": dict(self.annotations_redacted),
            "selector": dict(self.selector),
            "ports": list(self.ports),
            "owner_references": list(self.owner_references),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KubernetesIdentity:
        return cls(
            service_uid=data.get("service_uid"),
            service_type=data.get("service_type"),
            labels=dict(data.get("labels", {})),
            annotations_redacted=dict(data.get("annotations_redacted", {})),
            selector=dict(data.get("selector", {})),
            ports=list(data.get("ports", [])),
            owner_references=list(data.get("owner_references", [])),
        )


@dataclass(frozen=True)
class EndpointIdentity:
    """Endpoint-level identity for the Alertmanager source.
    
    Captures which pods the service endpoints resolve to.
    """
    endpoint_slices: list[str] = field(default_factory=list)  # EndpointSlice names
    target_pod_uids: list[str] = field(default_factory=list)  # Pod UIDs - stable identity
    target_pod_names: list[str] = field(default_factory=list)  # Pod namespace/name pairs
    target_owner_refs: list[dict[str, Any]] = field(default_factory=list)  # Pod -> StatefulSet -> CRD chain

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_slices": list(self.endpoint_slices),
            "target_pod_uids": list(self.target_pod_uids),
            "target_pod_names": list(self.target_pod_names),
            "target_owner_refs": list(self.target_owner_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndpointIdentity:
        return cls(
            endpoint_slices=list(data.get("endpoint_slices", [])),
            target_pod_uids=list(data.get("target_pod_uids", [])),
            target_pod_names=list(data.get("target_pod_names", [])),
            target_owner_refs=list(data.get("target_owner_refs", [])),
        )


@dataclass(frozen=True)
class SourceEntry:
    """A single Alertmanager source entry in the review packet.
    
    Captures all identity information needed to understand why this source
    was discovered and whether it is distinct from other sources.
    """
    source_id: str
    state: str  # AlertmanagerSourceState value
    origin: str  # AlertmanagerSourceOrigin value
    provenance: str  # How it was discovered
    namespace: str | None
    service_name: str | None
    endpoint_url: str
    cluster: str | None
    kubernetes_identity: KubernetesIdentity
    endpoint_identity: EndpointIdentity
    runtime_identity: RuntimeIdentity

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "state": self.state,
            "origin": self.origin,
            "provenance": self.provenance,
            "namespace": self.namespace,
            "service_name": self.service_name,
            "endpoint_url": self.endpoint_url,
            "cluster": self.cluster,
            "kubernetes_identity": self.kubernetes_identity.to_dict(),
            "endpoint_identity": self.endpoint_identity.to_dict(),
            "runtime_identity": self.runtime_identity.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceEntry:
        return cls(
            source_id=str(data["source_id"]),
            state=str(data["state"]),
            origin=str(data["origin"]),
            provenance=str(data["provenance"]),
            namespace=data.get("namespace"),
            service_name=data.get("service_name"),
            endpoint_url=str(data["endpoint_url"]),
            cluster=data.get("cluster"),
            kubernetes_identity=KubernetesIdentity.from_dict(data.get("kubernetes_identity", {})),
            endpoint_identity=EndpointIdentity.from_dict(data.get("endpoint_identity", {})),
            runtime_identity=RuntimeIdentity.from_dict(data.get("runtime_identity", {})),
        )


@dataclass(frozen=True)
class DuplicateAnalysis:
    """Analysis of why sources are potentially duplicates.
    
    Explains the reasoning behind grouping sources as aliases and
    what action is recommended.
    """
    group_id: str
    source_ids: tuple[str, ...]
    same_target_pods: bool
    same_alertmanager_cluster: bool
    same_config_hash: bool
    recommended_action: str  # "collapse_as_aliases", "keep_separate", "requires_manual_review"
    reason: str  # Human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "source_ids": list(self.source_ids),
            "same_target_pods": self.same_target_pods,
            "same_alertmanager_cluster": self.same_alertmanager_cluster,
            "same_config_hash": self.same_config_hash,
            "recommended_action": self.recommended_action,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DuplicateAnalysis:
        return cls(
            group_id=str(data["group_id"]),
            source_ids=tuple(data.get("source_ids", [])),
            same_target_pods=bool(data.get("same_target_pods", False)),
            same_alertmanager_cluster=bool(data.get("same_alertmanager_cluster", False)),
            same_config_hash=bool(data.get("same_config_hash", False)),
            recommended_action=str(data.get("recommended_action", "requires_manual_review")),
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True)
class Redactions:
    """Redaction policy applied to the review packet."""
    alertmanager_config: str = REDACTION_ALERTMANAGER_CONFIG
    annotations: str = REDACTION_ANNOTATIONS
    tokens: str = REDACTION_TOKENS

    def to_dict(self) -> dict[str, Any]:
        return {
            "alertmanager_config": self.alertmanager_config,
            "annotations": self.annotations,
            "tokens": self.tokens,
        }


@dataclass(frozen=True)
class Summary:
    """Summary counts for the review packet."""
    total: int = 0
    tracked: int = 0
    manual: int = 0
    degraded: int = 0
    missing: int = 0
    duplicate_groups: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "tracked": self.tracked,
            "manual": self.manual,
            "degraded": self.degraded,
            "missing": self.missing,
            "duplicate_groups": self.duplicate_groups,
        }


@dataclass(frozen=True)
class AlertmanagerSourcesReviewPacket:
    """Review packet for the Alertmanager sources discovery results.
    
    This packet provides structured evidence to help operators understand
    the "2 AlertManagers" state without K9B making heuristic dedupe decisions.
    
    Design principles:
    1. Evidence-first: Shows raw discovery data, not conclusions
    2. Identity-aware: Captures pod UIDs, config hashes, cluster status
    3. Explanation-ready: Includes duplicate analysis with recommendations
    4. Redaction-safe: Does not dump raw config by default
    """
    schema_version: str = SCHEMA_VERSION
    artifact_id: str = field(default_factory=new_artifact_id)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: str = "in-cluster"  # vs "external" for manually configured sources
    summary: Summary = field(default_factory=Summary)
    sources: tuple[SourceEntry, ...] = field(default_factory=tuple)
    duplicate_analysis: tuple[DuplicateAnalysis, ...] = field(default_factory=tuple)
    redactions: Redactions = field(default_factory=Redactions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "generated_at": self.generated_at.isoformat(),
            "context": self.context,
            "summary": self.summary.to_dict(),
            "sources": [s.to_dict() for s in self.sources],
            "duplicate_analysis": [d.to_dict() for d in self.duplicate_analysis],
            "redactions": self.redactions.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourcesReviewPacket:
        summary = Summary(**data.get("summary", {})) if isinstance(data.get("summary"), dict) else Summary()
        sources = tuple(SourceEntry.from_dict(s) for s in data.get("sources", []) if isinstance(s, dict))
        duplicate_analysis = tuple(
            DuplicateAnalysis.from_dict(d) for d in data.get("duplicate_analysis", []) if isinstance(d, dict)
        )
        redactions = Redactions(**data.get("redactions", {})) if isinstance(data.get("redactions"), dict) else Redactions()
        
        generated_at = data.get("generated_at")
        if isinstance(generated_at, str):
            try:
                if generated_at.endswith("Z"):
                    generated_at = f"{generated_at[:-1]}+00:00"
                generated_at = datetime.fromisoformat(generated_at)
            except ValueError:
                generated_at = datetime.now(UTC)
        elif generated_at is None:
            generated_at = datetime.now(UTC)
        
        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            artifact_id=str(data.get("artifact_id", "")),
            generated_at=generated_at,
            context=str(data.get("context", "in-cluster")),
            summary=summary,
            sources=sources,
            duplicate_analysis=duplicate_analysis,
            redactions=redactions,
        )


__all__ = [
    "SCHEMA_VERSION",
    "REDACTION_ALERTMANAGER_CONFIG",
    "REDACTION_ANNOTATIONS",
    "REDACTION_TOKENS",
    "RuntimeIdentity",
    "KubernetesIdentity",
    "EndpointIdentity",
    "SourceEntry",
    "DuplicateAnalysis",
    "Redactions",
    "Summary",
    "AlertmanagerSourcesReviewPacket",
]
