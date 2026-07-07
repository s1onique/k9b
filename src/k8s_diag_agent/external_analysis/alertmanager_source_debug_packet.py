"""Alertmanager source debug packet - per-row probe and discovery evidence.

This module provides the debug packet model for a single Alertmanager source row,
enabling operators to:
- Probe now: Re-run runtime probes (/-/healthy, /-/ready, /api/v2/status)
- Download JSON: Get the full debug packet as downloadable JSON
- Why discovered?: Understand why this source was found

Schema version: k9b.alertmanager_source.debug_packet.v1

Alertmanager explicitly exposes:
- /-/healthy - health check endpoint
- /-/ready - readiness endpoint  
- /api/v2/status - instance and cluster status (includes config hash)

See: https://prometheus.io/docs/alerting/latest/management_api/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..identity.artifact import new_artifact_id

# Schema version for the debug packet format
SCHEMA_VERSION = "k9b.alertmanager_source.debug_packet.v1"


@dataclass(frozen=True)
class HttpProbeResult:
    """Result of an HTTP probe to an Alertmanager endpoint."""
    url: str
    status_code: int | None = None
    latency_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HttpProbeResult:
        return cls(
            url=str(data.get("url", "")),
            status_code=data.get("status_code"),
            latency_ms=data.get("latency_ms"),
            error=data.get("error"),
        )


@dataclass(frozen=True)
class HttpProbeResults:
    """Results from all HTTP probes to Alertmanager endpoints."""
    healthy: HttpProbeResult | None = None
    ready: HttpProbeResult | None = None
    status: HttpProbeResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy.to_dict() if self.healthy else None,
            "ready": self.ready.to_dict() if self.ready else None,
            "status": self.status.to_dict() if self.status else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HttpProbeResults:
        return cls(
            healthy=HttpProbeResult.from_dict(data["healthy"]) if data.get("healthy") else None,
            ready=HttpProbeResult.from_dict(data["ready"]) if data.get("ready") else None,
            status=HttpProbeResult.from_dict(data["status"]) if data.get("status") else None,
        )


@dataclass(frozen=True)
class KubernetesProbeData:
    """Results from Kubernetes API probes for the source."""
    service: dict[str, Any] = field(default_factory=dict)
    endpoints: dict[str, Any] = field(default_factory=dict)
    endpoint_slices: list[dict[str, Any]] = field(default_factory=list)
    pods: list[dict[str, Any]] = field(default_factory=list)
    alertmanager_cr_matches: list[dict[str, Any]] = field(default_factory=list)
    statefulset_matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": dict(self.service),
            "endpoints": dict(self.endpoints),
            "endpoint_slices": list(self.endpoint_slices),
            "pods": list(self.pods),
            "alertmanager_cr_matches": list(self.alertmanager_cr_matches),
            "statefulset_matches": list(self.statefulset_matches),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KubernetesProbeData:
        return cls(
            service=dict(data.get("service", {})),
            endpoints=dict(data.get("endpoints", {})),
            endpoint_slices=list(data.get("endpoint_slices", [])),
            pods=list(data.get("pods", [])),
            alertmanager_cr_matches=list(data.get("alertmanager_cr_matches", [])),
            statefulset_matches=list(data.get("statefulset_matches", [])),
        )


@dataclass(frozen=True)
class DiscoveryReason:
    """Explains why this source was discovered."""
    matched_heuristic: str | None = None  # "service_name_or_label", "crd_name", etc.
    matched_fields: list[str] = field(default_factory=list)  # e.g., ["service.metadata.name", "service.labels.app.kubernetes.io/name"]
    confidence: str = "unknown"  # "high", "medium", "low", "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_heuristic": self.matched_heuristic,
            "matched_fields": list(self.matched_fields),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryReason:
        return cls(
            matched_heuristic=data.get("matched_heuristic"),
            matched_fields=list(data.get("matched_fields", [])),
            confidence=str(data.get("confidence", "unknown")),
        )


@dataclass(frozen=True)
class AlertmanagerSourceDebugPacket:
    """Debug packet for a single Alertmanager source.
    
    This packet provides comprehensive debug information for a single source row:
    - Discovery reason: Why was this source discovered?
    - Kubernetes probe: What K8s objects were found?
    - HTTP probe: What did /-/healthy, /-/ready, /api/v2/status return?
    - Errors: Any errors encountered during probing?
    
    Designed for:
    - "Probe now" button: Re-run all probes
    - "Download JSON" button: Get full debug packet
    - "Why discovered?" tooltip: Understand discovery mechanism
    """
    # Fields without defaults must come first
    source_id: str
    discovery_reason: DiscoveryReason
    kubernetes_probe: KubernetesProbeData
    http_probe: HttpProbeResults
    # Fields with defaults follow
    schema_version: str = SCHEMA_VERSION
    artifact_id: str = field(default_factory=new_artifact_id)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "generated_at": self.generated_at.isoformat(),
            "source_id": self.source_id,
            "discovery_reason": self.discovery_reason.to_dict(),
            "kubernetes_probe": self.kubernetes_probe.to_dict(),
            "http_probe": self.http_probe.to_dict(),
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourceDebugPacket:
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
            source_id=str(data["source_id"]),
            discovery_reason=DiscoveryReason.from_dict(data.get("discovery_reason", {})),
            kubernetes_probe=KubernetesProbeData.from_dict(data.get("kubernetes_probe", {})),
            http_probe=HttpProbeResults.from_dict(data.get("http_probe", {})),
            errors=list(data.get("errors", [])),
        )


__all__ = [
    "SCHEMA_VERSION",
    "HttpProbeResult",
    "HttpProbeResults",
    "KubernetesProbeData",
    "DiscoveryReason",
    "AlertmanagerSourceDebugPacket",
]
