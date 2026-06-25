"""Classification and normalization for backend health gate."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import Any

from .allowlists import (
    ALLOWED_DEPENDENCY_KEYS,
    ALLOWED_FAILURE_CLASSES,
    ALLOWED_REASON_CODES,
    _normalize_reason_code,
)
from .constants import (
    FAILURE_DEP_BACKEND_CRASHED,
    FAILURE_DEP_BACKEND_PENDING,
    FAILURE_DEP_PROVIDER_INIT_FAILED,
    FAILURE_DEP_PVC_MOUNT_ERROR,
    FAILURE_DEP_SCHEDULER_UNAVAILABLE,
    FAILURE_DEP_SCHEDULER_UNHEALTHY,
    FAILURE_DEP_UNKNOWN,
)
from .k8s_diagnostics import _sanitize_message_snippet


def _classify_dependency_failure(
    backend_diags: dict[str, Any],
    scheduler_diags: dict[str, Any],
    provider_status: dict[str, bool],
) -> tuple[str, list[dict[str, Any]]]:
    """Classify which internal dependency caused the backend health 500 failure.
    
    This function analyzes the collected diagnostics to determine which internal
    dependency (scheduler, PVC, backend restart, provider) caused the failure.
    
    Returns:
        Tuple of (primary_failure_class, list of dependency status dicts)
        The dependency list contains safe, sanitized info about each dependency.
    """
    dependencies: list[dict[str, Any]] = []
    primary_failure = FAILURE_DEP_UNKNOWN
    
    # Check backend pod states
    backend_pods = [(k, v) for k, v in backend_diags.items() if k.startswith("pod_")]
    for pod_key, pod_info in backend_pods:
        phase = pod_info.get("phase", "Unknown")
        restarts = pod_info.get("restart_count", 0)
        containers = pod_info.get("containers", [])
        
        # Check container states for specific failure patterns
        for cs in containers:
            cs_name = cs.get("name", "unknown")
            cs_state = cs.get("state", "unknown")
            cs_reason = cs.get("reason", "")
            # Prefer already-sanitized message_snippet from diagnostic collectors
            # Fall back to raw message if not present (e.g., direct API calls)
            # Defense-in-depth: sanitize again in case of unexpected input
            cs_message = _sanitize_message_snippet(cs.get("message_snippet", cs.get("message", "")))
            
            dep_entry: dict[str, Any] = {
                "dependency_name": f"backend_container:{cs_name}",
                "status": "unknown",
                "phase": phase,
                "failure_class": FAILURE_DEP_UNKNOWN,
                "reason_code": "unknown",
                "message_snippet": cs_message,  # Already sanitized by diagnostic collectors
            }
            
            if cs_state == "waiting":
                # Container is waiting - check reason
                if cs_reason in ("CrashLoopBackOff", "Error"):
                    dep_entry["status"] = "failing"
                    dep_entry["failure_class"] = FAILURE_DEP_BACKEND_CRASHED
                    dep_entry["reason_code"] = _normalize_reason_code(cs_reason, "container")
                    primary_failure = FAILURE_DEP_BACKEND_CRASHED
                elif cs_reason == "ContainerCreating":
                    dep_entry["status"] = "pending"
                    dep_entry["failure_class"] = FAILURE_DEP_BACKEND_PENDING
                    dep_entry["reason_code"] = "container_creating"
                    if "pvc" in cs_message.lower() or "mount" in cs_message.lower():
                        dep_entry["failure_class"] = FAILURE_DEP_PVC_MOUNT_ERROR
                        dep_entry["reason_code"] = "pvc_mount_pending"
                        primary_failure = FAILURE_DEP_PVC_MOUNT_ERROR
                    else:
                        primary_failure = FAILURE_DEP_BACKEND_PENDING
                else:
                    dep_entry["status"] = "waiting"
                    dep_entry["reason_code"] = _normalize_reason_code(cs_reason, "container")
                    primary_failure = FAILURE_DEP_BACKEND_PENDING
            elif cs_state == "running":
                dep_entry["status"] = "running"
                dep_entry["failure_class"] = ""
                dep_entry["reason_code"] = "container_running"
            elif cs_state == "terminated":
                dep_entry["status"] = "terminated"
                dep_entry["failure_class"] = FAILURE_DEP_BACKEND_CRASHED
                dep_entry["reason_code"] = "container_state_terminated"
                primary_failure = FAILURE_DEP_BACKEND_CRASHED
            else:
                dep_entry["status"] = cs_state
                dep_entry["reason_code"] = _normalize_reason_code(cs_reason, "container")
            
            dependencies.append(dep_entry)
        
        # Check for high restart count indicating instability
        if restarts > 3 and phase == "Running":
            # High restarts but currently running - might be intermittent
            pass  # Don't override more specific failure
    
    # Check scheduler pod states
    scheduler_pods = [(k, v) for k, v in scheduler_diags.items() if k.startswith("pod_")]
    scheduler_found = False
    for pod_key, pod_info in scheduler_pods:
        scheduler_found = True
        phase = pod_info.get("phase", "Unknown")
        restarts = pod_info.get("restart_count", 0)
        containers = pod_info.get("containers", [])
        
        for cs in containers:
            cs_name = cs.get("name", "unknown")
            cs_state = cs.get("state", "unknown")
            cs_reason = cs.get("reason", "")
            
            scheduler_entry: dict[str, Any] = {
                "dependency_name": f"scheduler_container:{cs_name}",
                "status": "unknown",
                "phase": phase,
                "failure_class": "",
                "reason_code": "scheduler_checked",
                "message_snippet": "",
            }
            
            if cs_state == "waiting":
                scheduler_entry["status"] = "failing"
                scheduler_entry["failure_class"] = FAILURE_DEP_SCHEDULER_UNHEALTHY
                scheduler_entry["reason_code"] = _normalize_reason_code(cs_reason, "scheduler")
                if primary_failure == FAILURE_DEP_UNKNOWN:
                    primary_failure = FAILURE_DEP_SCHEDULER_UNHEALTHY
            elif cs_state == "terminated":
                scheduler_entry["status"] = "terminated"
                scheduler_entry["failure_class"] = FAILURE_DEP_SCHEDULER_UNAVAILABLE
                scheduler_entry["reason_code"] = "scheduler_terminated"
                if primary_failure == FAILURE_DEP_UNKNOWN:
                    primary_failure = FAILURE_DEP_SCHEDULER_UNAVAILABLE
            elif phase != "Running":
                scheduler_entry["status"] = "not_running"
                scheduler_entry["failure_class"] = FAILURE_DEP_SCHEDULER_UNAVAILABLE
                scheduler_entry["reason_code"] = "scheduler_phase_pending" if "pending" in phase.lower() else "scheduler_phase_failed"
                if primary_failure == FAILURE_DEP_UNKNOWN:
                    primary_failure = FAILURE_DEP_SCHEDULER_UNAVAILABLE
            else:
                scheduler_entry["status"] = "healthy"
                scheduler_entry["reason_code"] = "scheduler_healthy"
            
            dependencies.append(scheduler_entry)
    
    if not scheduler_found:
        # No scheduler pods found - might be a lab configuration issue
        dependencies.append({
            "dependency_name": "scheduler",
            "status": "not_found",
            "phase": "N/A",
            "failure_class": FAILURE_DEP_SCHEDULER_UNAVAILABLE,
            "reason_code": "scheduler_pods_not_found",
            "message_snippet": "",
        })
        if primary_failure == FAILURE_DEP_UNKNOWN:
            primary_failure = FAILURE_DEP_SCHEDULER_UNAVAILABLE
    
    # Check provider config status
    provider_dep: dict[str, Any] = {
        "dependency_name": "diagnosis_provider",
        "status": "unknown",
        "phase": "N/A",
        "failure_class": "",
        "reason_code": "provider_config_checked",
        "message_snippet": "",
        "config": {
            "enabled": provider_status.get("diagnosis_provider_enabled", False),
            "api_key_present": provider_status.get("api_key_present", False),
            "secret_ref_present": provider_status.get("diagnosis_provider_secret_ref_present", False),
            "base_url_present": provider_status.get("base_url_present", False),
            "model_present": provider_status.get("model_present", False),
        },
    }
    
    # Provider is configured if enabled AND has at least one accepted secret ref
    has_diagnosis_secret = provider_status.get("diagnosis_provider_secret_ref_present", False)
    has_small_secret = provider_status.get("small_provider_secret_ref_present", False)
    has_any_secret = has_diagnosis_secret or has_small_secret
    
    if provider_status.get("diagnosis_provider_enabled") and not has_any_secret:
        # Provider enabled but no accepted secret ref - might cause init failures
        provider_dep["status"] = "misconfigured"
        provider_dep["failure_class"] = FAILURE_DEP_PROVIDER_INIT_FAILED
        provider_dep["reason_code"] = "provider_enabled_no_secret"
        if primary_failure == FAILURE_DEP_UNKNOWN:
            primary_failure = FAILURE_DEP_PROVIDER_INIT_FAILED
    elif provider_status.get("diagnosis_provider_enabled"):
        provider_dep["status"] = "configured"
        provider_dep["reason_code"] = "provider_configured"
    else:
        provider_dep["status"] = "disabled"
        provider_dep["reason_code"] = "provider_disabled"
    
    dependencies.append(provider_dep)
    
    return primary_failure, dependencies


def _collect_health_dependencies(
    backend_diags: dict[str, Any],
    scheduler_diags: dict[str, Any],
    provider_status: dict[str, bool],
) -> dict[str, Any]:
    """Collect and classify health dependencies for self-diagnosis.
    
    This produces a bounded, sanitized artifact explaining which internal
    health dependency failed, without exposing raw logs or secrets.
    
    Returns:
        dict with dependency status and failure classification
    """
    primary_failure, dependencies = _classify_dependency_failure(
        backend_diags, scheduler_diags, provider_status
    )
    
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "primary_failure_class": primary_failure,
        "dependency_count": len(dependencies),
        "dependencies": dependencies,
        "summary": {
            "backend_pods_checked": len([d for d in dependencies if d["dependency_name"].startswith("backend_container")]),
            "scheduler_pods_checked": len([d for d in dependencies if d["dependency_name"].startswith("scheduler")]),
            "provider_config_checked": any(d["dependency_name"] == "diagnosis_provider" for d in dependencies),
            "failures_detected": len([d for d in dependencies if d.get("failure_class")]),
        },
    }


def _get_provider_config_status(
    kubeconfig: str,
    namespace: str,
) -> dict[str, bool]:
    """Get sanitized provider config status (booleans only, no secrets).
    
    Detection rules:
    - diagnosis_provider_secret_ref_present: K9B_DIAGNOSIS_API_KEY via secretKeyRef
    - small_provider_secret_ref_present: K9B_EXTERNAL_ANALYSIS_API_KEY via secretKeyRef
    - diagnosis_provider_enabled: diagnosis provider config detected (via any indicator)
    - base_url_present: any BASE_URL env var detected
    - model_present: any MODEL env var detected
    """
    status: dict[str, bool] = {
        "diagnosis_provider_enabled": False,
        "diagnosis_provider_secret_ref_present": False,
        "small_provider_secret_ref_present": False,
        "base_url_present": False,
        "model_present": False,
        "api_key_present": False,
    }
    
    # Get deployment JSON for comprehensive inspection
    cmd = [
        "kubectl", "--kubeconfig", kubeconfig,
        "get", "deployment", "-n", namespace,
        "-o", "json",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return status
        
        deploy_data = json.loads(result.stdout)
        
        for item in deploy_data.get("items", []):
            for container in item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
                # Check env vars for presence indicators
                env_names = [e.get("name", "") for e in container.get("env", [])]
                for env_name in env_names:
                    # Diagnosis provider enabled indicator
                    if "DIAGNOSIS_PROVIDER_ENABLED" in env_name.upper():
                        status["diagnosis_provider_enabled"] = True
                    if "K9B_DIAGNOSIS" in env_name.upper():
                        status["diagnosis_provider_enabled"] = True
                    # Base URL presence
                    if "BASE_URL" in env_name.upper() or "EXTERNAL_ANALYSIS_BASE_URL" in env_name.upper():
                        status["base_url_present"] = True
                    # Model presence
                    if "MODEL" in env_name.upper() or "EXTERNAL_ANALYSIS_MODEL" in env_name.upper():
                        status["model_present"] = True
                
                # Check secretKeyRef for PROOF-BASED detection
                for env in container.get("env", []):
                    env_name = env.get("name", "")
                    env_src = env.get("valueFrom", {})
                    
                    if "secretKeyRef" in env_src:
                        secret_name = env_src.get("secretKeyRef", {}).get("name", "")
                        _ = env_src.get("secretKeyRef", {}).get("key", "")  # key read but not used
                        
                        # Proof-based detection:
                        # K9B_DIAGNOSIS_API_KEY + secretKeyRef -> diagnosis_provider_secret_ref_present
                        if env_name == "K9B_DIAGNOSIS_API_KEY":
                            status["diagnosis_provider_secret_ref_present"] = True
                            status["diagnosis_provider_enabled"] = True
                            status["api_key_present"] = True
                        
                        # K9B_EXTERNAL_ANALYSIS_API_KEY + secretKeyRef -> small_provider_secret_ref_present
                        if env_name == "K9B_EXTERNAL_ANALYSIS_API_KEY":
                            status["small_provider_secret_ref_present"] = True
                            status["api_key_present"] = True
                        
                        # Any other API key via secretKeyRef
                        if "API_KEY" in env_name.upper() or env_name.endswith("_KEY"):
                            status["api_key_present"] = True
                        
                        # Diagnosis secret name (regardless of key)
                        if "diagnosis" in secret_name.lower() or "k9b-diagnosis" in secret_name.lower():
                            # But only set enabled if it's actually used for diagnosis
                            if env_name.startswith("K9B_DIAGNOSIS"):
                                status["diagnosis_provider_enabled"] = True
                
                # Also check envFrom for secretRef (alternative pattern)
                for env_from in container.get("envFrom", []):
                    secret_ref = env_from.get("secretRef", {})
                    secret_name = secret_ref.get("name", "")
                    if "diagnosis" in secret_name.lower() or "k9b-diagnosis" in secret_name.lower():
                        status["diagnosis_provider_enabled"] = True
    except Exception:
        pass
    
    return status


def _normalize_backend_health_details(
    data: dict | None,
    backend_health_failed: bool,
) -> tuple[dict[str, Any], bool]:
    """Normalize backend /api/health/details response for safe artifact inclusion.
    
    This function validates and sanitizes the backend health details response
    to ensure only allowlisted fields and values make it into the artifact.
    
    Args:
        data: Raw response from /api/health/details (may be None)
        backend_health_failed: Whether /api/health itself failed (HTTP 500)
        
    Returns:
        Tuple of (normalized_dict, is_conclusive)
        - normalized_dict: Sanitized/normalized health details
        - is_conclusive: True if backend details provide clear diagnosis
    """
    if data is None:
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "backend_endpoint",
            "backend_details_error": "no_response",
            "primary_failure_class": "",
            "dependency_count": 0,
            "dependencies": [],
            "summary": {},
            "backend_healthy": None,
            "is_conclusive": False,
        }, False
    
    # Check if backend details are inconclusive
    is_conclusive = True
    inconclusive_reasons: list[str] = []
    
    primary_failure = data.get("primary_failure_class", "")
    backend_healthy = data.get("healthy", None)
    dependencies = data.get("dependencies", [])
    
    # If backend health check failed but details say healthy, that's suspicious
    if backend_health_failed and backend_healthy is True:
        is_conclusive = False
        inconclusive_reasons.append("health_check_failed_but_details_healthy")
    
    # If backend health check failed but no primary failure class, inconclusive
    if backend_health_failed and not primary_failure:
        is_conclusive = False
        inconclusive_reasons.append("no_primary_failure_class")
    
    # If no dependencies reported, inconclusive
    if not dependencies:
        is_conclusive = False
        inconclusive_reasons.append("no_dependencies")
    
    # Normalize dependencies - allowlist keys and values
    normalized_deps: list[dict[str, Any]] = []
    for dep in dependencies[:10]:  # Cap at 10 dependencies
        if not isinstance(dep, dict):
            continue
        
        normalized_dep: dict[str, Any] = {}
        
        # Only include allowlisted keys
        for key in ALLOWED_DEPENDENCY_KEYS:
            value = dep.get(key)
            if value is None:
                continue
            
            # Type check
            if not isinstance(value, str):
                value = str(value)[:200]  # Truncate non-strings
            
            # Value validation
            if key == "failure_class":
                if value not in ALLOWED_FAILURE_CLASSES:
                    value = ""  # Unknown failure class -> empty
            elif key == "reason_code":
                if value not in ALLOWED_REASON_CODES:
                    value = "unknown"  # Unknown reason code -> unknown
            elif key == "message_snippet":
                # Sanitize message_snippet from backend endpoint (defense-in-depth)
                value = _sanitize_message_snippet(value, max_len=100)
            elif key in ("dependency_name", "status"):
                # Cap string lengths
                value = value[:100]
            
            normalized_dep[key] = value
        
        if normalized_dep:
            normalized_deps.append(normalized_dep)
    
    # Build normalized result
    normalized: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "backend_endpoint",
        "primary_failure_class": primary_failure if primary_failure in ALLOWED_FAILURE_CLASSES else "",
        "dependency_count": len(normalized_deps),
        "dependencies": normalized_deps,
        "summary": {
            "dependencies_checked": len(normalized_deps),
            "failures_detected": len([d for d in normalized_deps if d.get("failure_class")]),
        },
        "backend_healthy": backend_healthy,
        "is_conclusive": is_conclusive,
        "inconclusive_reasons": inconclusive_reasons if not is_conclusive else [],
    }
    
    return normalized, is_conclusive
