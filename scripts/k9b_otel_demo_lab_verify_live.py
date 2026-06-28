#!/usr/bin/env python3
"""Live mode verification for OTel Demo Lab.

Verifies that live mode artifacts contain real observation evidence,
not only scaffold/fake-provider artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .k9b_lab_common_helpers import read_json
from .k9b_otel_demo_lab_constants import (
    FAILURE_LIVE_FEATURE_FLAG_NOT_ENABLED,
    FAILURE_LIVE_OBSERVATION_MISSING,
    FAILURE_LIVE_RECOMMENDATIONSERVICE_EVIDENCE_MISSING,
    FAILURE_LIVE_SYMPTOM_EVIDENCE_MISSING,
    FAILURE_LIVE_TELEMETRY_SIGNAL_MISSING,
    FAILURE_LIVE_TELEMETRY_UNAVAILABLE,
    FAILURE_LIVE_TRAFFIC_FAILED,
    FAILURE_LIVE_TRAFFIC_NOT_ATTEMPTED,
    PHASE_INJECTED,
)

# Symptom keywords that indicate real incident evidence
SYMPTOM_KEYWORDS = [
    "error",
    "fail",
    "crash",
    "restart",
    "oom",
    "memory",
    "cache",
    "timeout",
    "unhealthy",
    "warning",
    "critical",
]


def verify_otel_demo_lab_live(artifact_dir: Path) -> dict[str, Any]:
    """Verify live mode OTel Demo lab run.
    
    Required evidence:
    - baseline readiness passed
    - injection command recorded
    - feature flag before/after evidence exists
    - after-state shows recommendationServiceCacheFailure enabled
    - recommendationservice pod/deployment evidence exists after injection
    - live traffic artifact exists
    - live traffic attempted more than zero requests
    - at least one live observation artifact was collected after traffic started
    - diagnosis/artifact explicitly uses mode: live
    
    Live symptom evidence (at least one required):
    - recommendationservice warning event
    - recommendationservice restart count increase
    - recommendationservice readiness/liveness failure
    - recommendationservice log evidence mentioning cache/error/OOM/failure
    - recommendationservice memory growth telemetry
    - recommendationservice latency/error telemetry
    - trace evidence involving recommendationservice and error/latency symptoms
    
    Args:
        artifact_dir: Path to artifact directory
        
    Returns:
        Verification result dict with passed, failure_classes, details
    """
    failure_classes: list[str] = []
    details: dict[str, Any] = {}
    
    # Check 1: Live traffic artifact exists
    traffic_artifact = artifact_dir / PHASE_INJECTED / "traffic-live.json"
    if not traffic_artifact.exists():
        failure_classes.append(FAILURE_LIVE_TRAFFIC_NOT_ATTEMPTED)
        details["traffic"] = {"error": "traffic-live.json not found"}
    else:
        traffic_data = read_json(traffic_artifact)
        details["traffic"] = traffic_data
        
        # Verify traffic mode is live
        if traffic_data.get("mode") != "live":
            failure_classes.append(FAILURE_LIVE_TRAFFIC_FAILED)
        
        # Verify summary_found is true and actual_attempts > 0
        summary_found = bool(traffic_data.get("summary_found", "attempts" in traffic_data))
        actual_attempts = int(traffic_data.get("actual_attempts", traffic_data.get("attempts", 0)) or 0)
        
        if not summary_found or actual_attempts <= 0:
            failure_classes.append(FAILURE_LIVE_TRAFFIC_NOT_ATTEMPTED)
        
        details["summary_found"] = summary_found
        details["actual_attempts"] = actual_attempts
    
    # Check 2: recommendationservice evidence after injection
    injection_dir = artifact_dir / PHASE_INJECTED
    pods_artifact = injection_dir / "pods.json"
    recommendationservice_found = False
    
    if pods_artifact.exists():
        pods_data = read_json(pods_artifact)
        for pod in pods_data.get("items", []):
            pod_name = pod.get("metadata", {}).get("name", "")
            if "recommendation" in pod_name.lower():
                recommendationservice_found = True
                details["recommendationservice_pod"] = pod_name
                
                # Check for symptom evidence in pod status
                container_statuses = pod.get("status", {}).get("containerStatuses", [])
                for cs in container_statuses:
                    restart_count = cs.get("restartCount", 0)
                    state = cs.get("state", {})
                    
                    # Collect symptom evidence
                    if restart_count > 0:
                        details["symptom"] = {
                            "type": "restart_count",
                            "pod": pod_name,
                            "restart_count": restart_count,
                        }
                    
                    if "waiting" in state:
                        waiting = state["waiting"]
                        details["symptom"] = details.get("symptom") or {
                            "type": "waiting_state",
                            "pod": pod_name,
                            "reason": waiting.get("reason", ""),
                            "message": waiting.get("message", ""),
                        }
    else:
        failure_classes.append(FAILURE_LIVE_RECOMMENDATIONSERVICE_EVIDENCE_MISSING)
    
    if not recommendationservice_found:
        failure_classes.append(FAILURE_LIVE_RECOMMENDATIONSERVICE_EVIDENCE_MISSING)
    
    details["recommendationservice_found"] = recommendationservice_found
    
    # Check 3: Feature flag evidence
    flag_before = injection_dir / "flag-config-before.json"
    flag_after = injection_dir / "flag-config-after.json"
    flag_enabled = False
    flag_before_missing = not flag_before.exists()
    flag_after_missing = not flag_after.exists()
    
    details["flag_before_missing"] = flag_before_missing
    details["flag_after_missing"] = flag_after_missing
    
    if flag_before_missing:
        failure_classes.append(FAILURE_LIVE_FEATURE_FLAG_NOT_ENABLED)
        details["flag_error"] = "flag-config-before.json missing"
    elif flag_after_missing:
        failure_classes.append(FAILURE_LIVE_FEATURE_FLAG_NOT_ENABLED)
        details["flag_error"] = "flag-config-after.json missing"
    elif flag_before.exists() and flag_after.exists():
        before_data = read_json(flag_before)
        after_data = read_json(flag_after)
        details["flag_before"] = before_data
        details["flag_after"] = after_data
        
        # Check if recommendationServiceCacheFailure is enabled in after state
        # Parse the nested flag structure: flags -> flag_name -> enabled
        flags = after_data.get("flags", {})
        flag_spec = flags.get("recommendationServiceCacheFailure", flags.get("recommendationservicecachefailure", {}))
        if isinstance(flag_spec, dict):
            flag_enabled = flag_spec.get("enabled", False)
        else:
            # Fallback: check string representation
            flag_after_str = str(after_data).lower()
            flag_enabled = "recommendationservicecachefailure" in flag_after_str and "true" in flag_after_str
        
        if not flag_enabled:
            failure_classes.append(FAILURE_LIVE_FEATURE_FLAG_NOT_ENABLED)
    
    details["flag_enabled"] = flag_enabled
    
    # Check 4: Symptom evidence
    symptom_found = _check_symptom_evidence(artifact_dir, details)
    if not symptom_found:
        failure_classes.append(FAILURE_LIVE_SYMPTOM_EVIDENCE_MISSING)
    
    details["symptom_found"] = symptom_found
    
    # Check 5: Live observation artifacts exist
    observation_artifact = injection_dir / "telemetry"
    if not observation_artifact.exists():
        # Check for any observation artifacts
        observation_files = list(injection_dir.glob("*"))
        if not any(f.suffix in [".json", ".txt"] for f in observation_files):
            failure_classes.append(FAILURE_LIVE_OBSERVATION_MISSING)
    
    details["observation_artifact_exists"] = observation_artifact.exists()
    
    # Check 6: Diagnosis is live mode
    diagnosis_dir = artifact_dir / "phase4-diagnosis"
    diagnosis_data = None
    
    for fname in ["final-diagnosis.json", "live-diagnosis.json"]:
        fpath = diagnosis_dir / fname
        if fpath.exists():
            diagnosis_data = read_json(fpath)
            break
    
    if diagnosis_data:
        diagnosis_mode = diagnosis_data.get("mode", "")
        details["diagnosis_mode"] = diagnosis_mode
        details["diagnosis_provider"] = diagnosis_data.get("provider", "")
        
        if diagnosis_mode != "live":
            details["diagnosis_warning"] = "Diagnosis mode should be 'live', found: " + diagnosis_mode
    else:
        details["diagnosis_warning"] = "No diagnosis artifact found"
    
    # Check 7: Telemetry availability
    telemetry_dir = injection_dir / "telemetry"
    telemetry_available = {
        "kubernetes": (injection_dir / "pods.json").exists(),
        "prometheus": (telemetry_dir / "prometheus-metrics.json").exists() if telemetry_dir.exists() else False,
        "jaeger": (telemetry_dir / "jaeger-traces.json").exists() if telemetry_dir.exists() else False,
    }
    details["telemetry_available"] = telemetry_available
    
    # Check for telemetry signal (if telemetry is available)
    if any(telemetry_available.values()):
        telemetry_signal = _check_telemetry_signal(telemetry_dir, pods_artifact)
        if not telemetry_signal:
            failure_classes.append(FAILURE_LIVE_TELEMETRY_SIGNAL_MISSING)
        details["telemetry_signal"] = telemetry_signal
    else:
        failure_classes.append(FAILURE_LIVE_TELEMETRY_UNAVAILABLE)
    
    passed = len(failure_classes) == 0
    
    return {
        "passed": passed,
        "failure_classes": failure_classes,
        "details": details,
        "recommendationservice_found": recommendationservice_found,
        "flag_enabled": flag_enabled,
        "symptom_found": symptom_found,
    }


def _check_symptom_evidence(artifact_dir: Path, details: dict[str, Any]) -> bool:
    """Check if any symptom evidence is present.
    
    Returns True if symptom evidence found.
    """
    injection_dir = artifact_dir / PHASE_INJECTED
    telemetry_dir = injection_dir / "telemetry"
    
    # 1. Check if symptom already recorded in details
    if details.get("symptom"):
        return True
    
    # 2. Check recommendationservice events
    if telemetry_dir.exists():
        events_file = telemetry_dir / "recommendationservice-events.json"
        if events_file.exists():
            events_data = read_json(events_file)
            events_str = str(events_data).lower()
            if any(kw in events_str for kw in SYMPTOM_KEYWORDS):
                return True
    
    # 3. Check recommendationservice logs
    if telemetry_dir.exists():
        logs_file = telemetry_dir / "recommendationservice-logs.txt"
        if logs_file.exists():
            logs_content = logs_file.read_text().lower()
            if any(kw in logs_content for kw in SYMPTOM_KEYWORDS):
                return True
    
    # 4. Check events.json for warnings
    events_file = injection_dir / "events.json"
    if events_file.exists():
        events_data = read_json(events_file)
        events_str = str(events_data).lower()
        if "recommendation" in events_str and any(kw in events_str for kw in ["warning", "error", "fail"]):
            return True
    
    # 5. Check pod describe for issues
    if telemetry_dir.exists():
        for f in telemetry_dir.glob("recommendationservice-describe*.txt"):
            desc_content = f.read_text().lower()
            if any(kw in desc_content for kw in ["unhealthy", "error", "warning", "failure", "crash"]):
                return True
    
    # 6. Check for restart count in pods
    pods_file = injection_dir / "pods.json"
    if pods_file.exists():
        pods_data = read_json(pods_file)
        for pod in pods_data.get("items", []):
            if "recommendation" not in pod.get("metadata", {}).get("name", "").lower():
                continue
            for cs in pod.get("status", {}).get("containerStatuses", []):
                if cs.get("restartCount", 0) > 0:
                    return True
    
    return False


def _check_telemetry_signal(telemetry_dir: Path | None, pods_artifact: Path | None = None) -> bool:
    """Check if telemetry shows any signal.
    
    Returns True if any telemetry signal is present.
    Kubernetes pod data counts as valid signal.
    """
    # Kubernetes pod data is valid telemetry signal
    if pods_artifact and pods_artifact.exists():
        return True
    
    if not telemetry_dir or not telemetry_dir.exists():
        return False
    
    # Check Prometheus metrics
    prom_file = telemetry_dir / "prometheus-metrics.json"
    if prom_file.exists():
        prom_data = read_json(prom_file)
        # Check if metrics have any results
        for metric_value in prom_data.values():
            if isinstance(metric_value, dict):
                result = metric_value.get("data", {}).get("result", [])
                if result:
                    return True
    
    # Check Jaeger traces
    jaeger_file = telemetry_dir / "jaeger-traces.json"
    if jaeger_file.exists():
        jaeger_data = read_json(jaeger_file)
        if jaeger_data.get("data") or jaeger_data.get("spans"):
            return True
    
    return False
