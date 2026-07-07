"""Runtime probe for Alertmanager endpoints.

This module provides functions to probe Alertmanager instances via HTTP,
supporting both the discovery verification stage and the "Probe Now" UI feature.

Alertmanager exposes:
- /-/healthy - health check endpoint
- /-/ready - readiness endpoint
- /api/v2/status - instance and cluster status

See: https://prometheus.io/docs/alerting/latest/management_api/
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .alertmanager_source_debug_packet import (
    HttpProbeResult,
    HttpProbeResults,
)

# Default timeout for HTTP requests
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class RuntimeProbeResult:
    """Result of probing an Alertmanager instance.
    
    Captures the results of probing /-/healthy, /-/ready, and /api/v2/status.
    """
    endpoint: str
    healthy: HttpProbeResult
    ready: HttpProbeResult
    status: HttpProbeResult
    # Parsed status data (redacted)
    version: str | None = None
    cluster_status: str | None = None
    peer_count: int = 0
    config_sha256: str | None = None
    receiver_count: int | None = None
    silence_count: int | None = None
    alert_group_count: int | None = None
    probed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_healthy(self) -> bool:
        """Whether the Alertmanager is healthy and ready."""
        return self.healthy.status_code == 200 and self.ready.status_code == 200


def _compute_config_sha256(config_data: Any) -> str | None:
    """Compute SHA256 hash of Alertmanager config.
    
    The config is typically in config.original or config.resolved.
    We only hash the config data, not the full response.
    """
    try:
        config_json = json.dumps(config_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return None


def _probe_endpoint(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> HttpProbeResult:
    """Probe a single HTTP endpoint.
    
    Args:
        url: The URL to probe
        timeout: Request timeout in seconds
        
    Returns:
        HttpProbeResult with status code, latency, and any error
    """
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency_ms = (time.perf_counter() - start) * 1000
            return HttpProbeResult(
                url=url,
                status_code=response.status,
                latency_ms=round(latency_ms, 2),
                error=None,
            )
    except urllib.error.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return HttpProbeResult(
            url=url,
            status_code=exc.code,
            latency_ms=round(latency_ms, 2),
            error=f"HTTP {exc.code}: {exc.reason}",
        )
    except urllib.error.URLError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return HttpProbeResult(
            url=url,
            status_code=None,
            latency_ms=round(latency_ms, 2),
            error=f"Connection failed: {exc.reason}",
        )
    except TimeoutError:
        latency_ms = (time.perf_counter() - start) * 1000
        return HttpProbeResult(
            url=url,
            status_code=None,
            latency_ms=round(latency_ms, 2),
            error="Request timed out",
        )


def _parse_status_response(response_data: dict[str, Any]) -> dict[str, Any]:
    """Parse /api/v2/status response and extract redacted data.
    
    Returns:
        Dictionary with version, cluster_status, peer_count, config_sha256,
        and count fields only. Does NOT return raw config data.
    """
    result: dict[str, Any] = {}
    
    # Extract version info
    version_info = response_data.get("data", {}).get("versionInfo", {})
    result["version"] = version_info.get("version")
    
    # Extract cluster info
    cluster_info = response_data.get("data", {}).get("cluster", {})
    result["cluster_status"] = cluster_info.get("status")
    result["peer_count"] = len(cluster_info.get("peers", []))
    
    # Extract config hash (not raw config)
    config_info = response_data.get("data", {}).get("config", {})
    config_original = config_info.get("original")
    if config_original:
        result["config_sha256"] = _compute_config_sha256(config_original)
    
    # Extract count fields (not raw data)
    result["receiver_count"] = len(response_data.get("data", {}).get("receivers", []))
    
    return result


def probe_alertmanager(
    endpoint: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RuntimeProbeResult:
    """Probe an Alertmanager instance via HTTP.
    
    Probes /-/healthy, /-/ready, and /api/v2/status endpoints.
    
    Args:
        endpoint: Base URL of the Alertmanager instance (e.g., "http://alertmanager:9093")
        timeout: Request timeout in seconds
        
    Returns:
        RuntimeProbeResult with all probe results and parsed status data
    """
    endpoint = endpoint.rstrip("/")
    
    # Probe all endpoints in parallel-like manner (sequential but fast)
    healthy_result = _probe_endpoint(f"{endpoint}/-/healthy", timeout)
    ready_result = _probe_endpoint(f"{endpoint}/-/ready", timeout)
    status_result = _probe_endpoint(f"{endpoint}/api/v2/status", timeout)
    
    # Parse status response if successful
    version: str | None = None
    cluster_status: str | None = None
    peer_count: int = 0
    config_sha256: str | None = None
    receiver_count: int | None = None
    silence_count: int | None = None
    alert_group_count: int | None = None
    
    if status_result.status_code == 200 and status_result.error is None:
        try:
            # Get the raw response for parsing
            req = urllib.request.Request(f"{endpoint}/api/v2/status")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read())
                parsed = _parse_status_response(data)
                version = parsed.get("version")
                cluster_status = parsed.get("cluster_status")
                peer_count = parsed.get("peer_count", 0)
                config_sha256 = parsed.get("config_sha256")
                receiver_count = parsed.get("receiver_count")
                
                # Note: silence_count and alert_group_count would require additional API calls
                # to /api/v2/silences and /api/v2/alerts/groups respectively
                # For now, we don't make those calls to keep probes fast
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    
    return RuntimeProbeResult(
        endpoint=endpoint,
        healthy=healthy_result,
        ready=ready_result,
        status=status_result,
        version=version,
        cluster_status=cluster_status,
        peer_count=peer_count,
        config_sha256=config_sha256,
        receiver_count=receiver_count,
        silence_count=silence_count,
        alert_group_count=alert_group_count,
    )


def build_http_probe_results(probe_result: RuntimeProbeResult) -> HttpProbeResults:
    """Build HttpProbeResults from RuntimeProbeResult.
    
    This is a helper for building debug packets.
    """
    return HttpProbeResults(
        healthy=probe_result.healthy,
        ready=probe_result.ready,
        status=probe_result.status,
    )


def build_runtime_identity(probe_result: RuntimeProbeResult) -> dict[str, Any]:
    """Build RuntimeIdentity dict from RuntimeProbeResult.
    
    This is a helper for building review packets.
    """
    return {
        "probe_attempted": True,
        "healthy": probe_result.healthy.status_code == 200,  # Fixed: /-/healthy probe result
        "ready": probe_result.ready.status_code == 200,  # Fixed: /-/ready probe result
        "alertmanager_version": probe_result.version,
        "cluster_status": probe_result.cluster_status,
        "cluster_peer_count": probe_result.peer_count,
        "config_sha256": probe_result.config_sha256,
        "receiver_count": probe_result.receiver_count,
        "silence_count": probe_result.silence_count,
        "alert_group_count": probe_result.alert_group_count,
    }


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "RuntimeProbeResult",
    "probe_alertmanager",
    "build_http_probe_results",
    "build_runtime_identity",
]
