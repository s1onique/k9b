#!/usr/bin/env python3
"""Telemetry collection for OTel Demo Lab live mode.

Collects telemetry evidence from:
- Kubernetes resources (pods, events, services)
- Prometheus metrics (if available)
- Jaeger traces (if available)
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import (
    kubectl_describe,
    kubectl_events,
    kubectl_json,
    kubectl_logs,
    log,
    write_json_artifact,
    write_text_artifact,
)
from .k9b_otel_demo_lab_constants import OTEL_DEMO_NAMESPACE

# Sanitizer: redacts sensitive values from K8s artifacts
try:
    from .lab_common.artifact_sanitizer import sanitize_artifact
except ImportError:
    def sanitize_artifact(data: Any, max_depth: int = 20) -> Any:
        return data


class TelemetryAvailability:
    """Telemetry availability status."""
    
    KUBERNETES = "kubernetes"
    PROMETHEUS = "prometheus"
    JAEGER = "jaeger"


@dataclass
class TelemetryResult:
    """Result of telemetry collection."""
    
    available: dict[str, bool]
    artifacts: dict[str, Path]
    recommendationservice_metrics: dict[str, Any]
    recommendationservice_events: list[dict[str, Any]]
    recommendationservice_logs: str
    recommendationservice_describe: str
    error: str | None = None


def collect_telemetry(
    kubeconfig: str,
    artifact_dir: Path,
    namespace: str = OTEL_DEMO_NAMESPACE,
) -> TelemetryResult:
    """Collect telemetry evidence from the cluster.
    
    Args:
        kubeconfig: Path to kubeconfig
        artifact_dir: Directory to write artifacts
        namespace: OTel Demo namespace
        
    Returns:
        TelemetryResult with collected evidence
    """
    
    log("Collecting telemetry evidence...")
    
    telemetry_dir = artifact_dir / "phase2-injected" / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    
    available: dict[str, bool] = {}
    artifacts: dict[str, Path] = {}
    recommendationservice_metrics: dict[str, Any] = {}
    recommendationservice_events: list[dict[str, Any]] = []
    recommendationservice_logs = ""
    recommendationservice_describe = ""
    error: str | None = None
    
    # 1. Kubernetes evidence (always available)
    available[TelemetryAvailability.KUBERNETES] = True
    k8s_artifacts = _collect_kubernetes_evidence(kubeconfig, namespace, telemetry_dir)
    artifacts.update(k8s_artifacts)
    
    # Extract recommendationservice-specific events
    recommendationservice_events = _extract_recommendationservice_events(kubeconfig, namespace)
    if recommendationservice_events:
        events_path = write_json_artifact(telemetry_dir, "recommendationservice-events.json", 
                                         {"events": recommendationservice_events})
        artifacts["recommendationservice_events"] = events_path
    
    # 2. Prometheus metrics (if available)
    prom_available, prom_metrics = _collect_prometheus_metrics(kubeconfig, namespace)
    available[TelemetryAvailability.PROMETHEUS] = prom_available
    if prom_available and prom_metrics:
        metrics_path = write_json_artifact(telemetry_dir, "prometheus-metrics.json", prom_metrics)
        artifacts["prometheus_metrics"] = metrics_path
        recommendationservice_metrics = prom_metrics
    
    # 3. Jaeger traces (if available)
    jaeger_available, jaeger_traces = _collect_jaeger_traces(kubeconfig, namespace)
    available[TelemetryAvailability.JAEGER] = jaeger_available
    if jaeger_available and jaeger_traces:
        traces_path = write_json_artifact(telemetry_dir, "jaeger-traces.json", jaeger_traces)
        artifacts["jaeger_traces"] = traces_path
    
    # 4. Collect recommendationservice logs
    rec_logs, rec_describe = _collect_recommendationservice_details(kubeconfig, namespace)
    recommendationservice_logs = rec_logs
    recommendationservice_describe = rec_describe
    
    if rec_logs:
        logs_path = write_text_artifact(telemetry_dir, "recommendationservice-logs.txt", rec_logs)
        artifacts["recommendationservice_logs"] = logs_path
    
    if rec_describe:
        desc_path = write_text_artifact(telemetry_dir, "recommendationservice-describe.txt", rec_describe)
        artifacts["recommendationservice_describe"] = desc_path
    
    log(f"Telemetry collection complete: available={available}")
    
    return TelemetryResult(
        available=available,
        artifacts=artifacts,
        recommendationservice_metrics=recommendationservice_metrics,
        recommendationservice_events=recommendationservice_events,
        recommendationservice_logs=recommendationservice_logs,
        recommendationservice_describe=recommendationservice_describe,
        error=error,
    )


def _collect_kubernetes_evidence(
    kubeconfig: str,
    namespace: str,
    telemetry_dir: Path,
) -> dict[str, Path]:
    """Collect Kubernetes resource evidence."""
    artifacts: dict[str, Path] = {}
    
    # Pods
    pods_result = kubectl_json(kubeconfig, "pods", namespace)
    if pods_result.success and pods_result.data:
        # Sanitize pods to redact sensitive values (passwords, tokens, kubeconfig refs)
        sanitized_pods = sanitize_artifact(pods_result.data)
        pods_path = write_json_artifact(telemetry_dir, "pods.json", sanitized_pods)
        artifacts["pods"] = pods_path
    
    # Deployments
    deploy_result = kubectl_json(kubeconfig, "deployments", namespace)
    if deploy_result.success and deploy_result.data:
        # Sanitize deployments to redact sensitive values (passwords, tokens, kubeconfig refs)
        sanitized_deployments = sanitize_artifact(deploy_result.data)
        deploy_path = write_json_artifact(telemetry_dir, "deployments.json", sanitized_deployments)
        artifacts["deployments"] = deploy_path
    
    # Services
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    if svc_result.success and svc_result.data:
        svc_path = write_json_artifact(telemetry_dir, "services.json", svc_result.data)
        artifacts["services"] = svc_path
    
    # Endpoints
    ep_result = kubectl_json(kubeconfig, "endpoints", namespace)
    if ep_result.success and ep_result.data:
        ep_path = write_json_artifact(telemetry_dir, "endpoints.json", ep_result.data)
        artifacts["endpoints"] = ep_path
    
    # Events
    events_result = kubectl_events(kubeconfig, namespace)
    if events_result.success:
        events_path = write_text_artifact(telemetry_dir, "events.txt", events_result.stdout)
        artifacts["events"] = events_path
    
    # ConfigMaps (flag state)
    cm_result = kubectl_json(kubeconfig, "configmaps", namespace)
    if cm_result.success and cm_result.data:
        flag_cms = {
            cm.get("metadata", {}).get("name", ""): cm
            for cm in cm_result.data.get("items", [])
            if "flag" in cm.get("metadata", {}).get("name", "").lower()
        }
        if flag_cms:
            cms_path = write_json_artifact(telemetry_dir, "feature-flag-configmaps.json", {"configmaps": flag_cms})
            artifacts["feature_flag_configmaps"] = cms_path
    
    return artifacts


def _extract_recommendationservice_events(
    kubeconfig: str,
    namespace: str,
) -> list[dict[str, Any]]:
    """Extract recommendationservice-related events."""
    events_result = kubectl_events(kubeconfig, namespace)
    if not events_result.success:
        return []
    
    events = []
    for line in events_result.stdout.split("\n"):
        if "recommendation" in line.lower():
            events.append({"raw": line})
    
    return events


def _collect_prometheus_metrics(
    kubeconfig: str,
    namespace: str,
) -> tuple[bool, dict[str, Any]]:
    """Collect Prometheus metrics if available."""
    # Try to find Prometheus service
    prom_svc = _find_service(kubeconfig, namespace, "prometheus")
    if not prom_svc:
        return False, {}
    
    # Try to query Prometheus API
    prom_url = f"http://{prom_svc}.{namespace}.svc:9090/api/v1/query"
    
    queries = [
        ("recommendationservice_memory", 'container_memory_working_set_bytes{pod=~"recommendationservice.*"}'),
        ("recommendationservice_cpu", 'rate(container_cpu_usage_seconds_total{pod=~"recommendationservice.*"}[5m])'),
        ("recommendationservice_errors", 'rate(http_requests_total{service="recommendationservice",status=~"5.."}[5m])'),
    ]
    
    metrics: dict[str, Any] = {}
    for name, query in queries:
        result = subprocess.run(
            ["curl", "-s", f"{prom_url}?query={query}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            try:
                metrics[name] = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass
    
    return bool(metrics), metrics


def _collect_jaeger_traces(
    kubeconfig: str,
    namespace: str,
) -> tuple[bool, dict[str, Any]]:
    """Collect Jaeger traces if available."""
    # Try to find Jaeger service
    jaeger_svc = _find_service(kubeconfig, namespace, "jaeger")
    if not jaeger_svc:
        return False, {}
    
    # Try to query Jaeger API
    jaeger_url = f"http://{jaeger_svc}.{namespace}.svc:16686/api/traces?service=recommendationservice&limit=10"
    
    result = subprocess.run(
        ["curl", "-s", jaeger_url],
        capture_output=True, text=True, timeout=10
    )
    
    if result.returncode == 0:
        try:
            return True, json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    
    return False, {}


def _collect_recommendationservice_details(
    kubeconfig: str,
    namespace: str,
) -> tuple[str, str]:
    """Collect recommendationservice pod logs and describe output."""
    # Find recommendationservice pod
    pods_result = kubectl_json(kubeconfig, "pods", namespace)
    rec_pod = None
    
    if pods_result.success and pods_result.data:
        for pod in pods_result.data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "recommendation" in pod_name.lower():
                rec_pod = pod_name
                break
    
    if not rec_pod:
        return "", ""
    
    # Get logs
    logs_result = kubectl_logs(kubeconfig, rec_pod, namespace)
    logs = logs_result.stdout if logs_result.success else ""
    
    # Get describe
    desc_result = kubectl_describe(kubeconfig, "pod", rec_pod, namespace)
    describe = desc_result.stdout if desc_result.success else ""
    
    return logs, describe


def _find_service(kubeconfig: str, namespace: str, name: str) -> str | None:
    """Find a service by name pattern."""
    svc_result = kubectl_json(kubeconfig, "services", namespace)
    if svc_result.success and svc_result.data:
        for svc in svc_result.data.get("items", []):
            svc_name: str = svc.get("metadata", {}).get("name", "") or ""
            if name in svc_name.lower():
                return svc_name
    return None
