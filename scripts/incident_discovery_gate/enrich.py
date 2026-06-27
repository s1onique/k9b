"""LLM enrichment classification for incident discovery gate.

Provides Phase 2d/2e classification logic for provider activation and LLM enrichment.
"""

from __future__ import annotations

from typing import Any

# Failure class constants (imported from constants.py)
# FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT
# FAILURE_LLM_ENRICHMENT_DISABLED
# FAILURE_LLM_PROVIDER_NOT_CONFIGURED
# FAILURE_LLM_PROVIDER_SECRET_MISSING
# FAILURE_LLM_PROVIDER_ENV_MISSING
# FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE
# FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED
# FAILURE_LLM_PROVIDER_REQUEST_FAILED
# FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED


def classify_enrichment_status(
    incident_exists: bool,
    provider_enabled: bool,
    provider_configured: bool,
    provider_secret_refs_present: list[str],
    provider_env_vars_present: list[str],
    provider_invocation_count: int,
    incident_enriched: bool,
) -> str:
    """Classify LLM enrichment status based on observed state.

    Args:
        incident_exists: Whether an incident was found
        provider_enabled: Whether LLM enrichment is enabled in config
        provider_configured: Whether provider credentials are configured
        provider_secret_refs_present: List of required Secret ref names that exist
        provider_env_vars_present: List of required env var names that are set
        provider_invocation_count: Number of provider calls observed
        incident_enriched: Whether the incident shows enrichment/review state

    Returns:
        Failure class constant or empty string if enrichment is working
    """
    # Import constants here to avoid circular imports
    from .constants import (
        FAILURE_LLM_ENRICHMENT_DISABLED,
        FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT,
        FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED,
        FAILURE_LLM_PROVIDER_ENV_MISSING,
        FAILURE_LLM_PROVIDER_NOT_CONFIGURED,
        FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED,
        FAILURE_LLM_PROVIDER_SECRET_MISSING,
    )

    # No incident -> no enrichment expected
    if not incident_exists:
        return FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT

    # Enrichment is disabled
    if not provider_enabled:
        return FAILURE_LLM_ENRICHMENT_DISABLED

    # Provider not configured at all
    if not provider_configured:
        return FAILURE_LLM_PROVIDER_NOT_CONFIGURED

    # Check for missing Secrets (required Secret refs not present)
    if provider_secret_refs_present is not None and len(provider_secret_refs_present) == 0:
        # If we expected Secret refs but none exist
        return FAILURE_LLM_PROVIDER_SECRET_MISSING

    # Check for missing env vars
    if provider_env_vars_present is not None and len(provider_env_vars_present) == 0:
        return FAILURE_LLM_PROVIDER_ENV_MISSING

    # Provider configured but never invoked
    if provider_invocation_count == 0:
        # Check if there's a policy gate that might have prevented it
        return FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED

    # Provider invoked but incident not enriched (result not persisted)
    if not incident_enriched:
        return FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED

    # Enrichment appears to be working
    return ""


def extract_enrichment_status_from_incident(incident_data: dict[str, Any] | None) -> bool:
    """Extract whether an incident has been enriched/triaged.

    Args:
        incident_data: Incident data from API

    Returns:
        True if incident shows enrichment/review state
    """
    if not incident_data:
        return False

    # Check for common enrichment/review indicators
    # These fields may vary based on API contract
    enriched_indicators = [
        "enriched",
        "triage_status",
        "review_status",
        "llm_enriched",
        "analysis_complete",
        "diagnostic_summary",
        "triage_summary",
        "enrichment_timestamp",
        "llm_response",
    ]

    for indicator in enriched_indicators:
        if indicator in incident_data and incident_data[indicator]:
            return True

    # Check for nested enrichment state
    if "metadata" in incident_data:
        metadata = incident_data["metadata"]
        for indicator in enriched_indicators:
            if indicator in metadata and metadata[indicator]:
                return True

    return False


def get_provider_config_from_backend(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
) -> dict[str, Any]:
    """Extract provider configuration from backend pod environment.

    This simulates checking backend pod for provider config.
    In real implementation, this would use kubectl exec or pod logs.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name

    Returns:
        Dict with provider configuration status
    """
    import subprocess

    result = {
        "provider_enabled": False,
        "provider_configured": False,
        "provider_name": "",
        "provider_model": "",
        "provider_endpoint": "",
        "secret_refs_present": [],
        "env_vars_present": [],
        "raw_env_summary": "",
    }

    try:
        # Get backend pod name
        pod_cmd = [
            "kubectl", "get", "pods",
            "-n", namespace,
            "-l", f"app={backend_deployment}",
            "-o", "jsonpath={.items[0].metadata.name}",
        ]
        pod_result = subprocess.run(
            pod_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={"KUBECONFIG": kubeconfig},
        )
        if pod_result.returncode != 0:
            return result
        pod_name = pod_result.stdout.strip()
        if not pod_name:
            return result

        # Get pod env vars summary (names only, no values)
        env_cmd = [
            "kubectl", "exec", pod_name, "-n", namespace,
            "--", "env", "-0",
        ]
        env_result = subprocess.run(
            env_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={"KUBECONFIG": kubeconfig},
        )
        if env_result.returncode == 0:
            # Parse null-separated env vars
            env_vars = []
            for line in env_result.stdout.split("\x00"):
                if "=" in line:
                    key = line.split("=", 1)[0]
                    env_vars.append(key)
            result["raw_env_summary"] = f"{len(env_vars)} env vars set"

            # Check for LLM-related env vars
            llm_related = [
                "LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_ENDPOINT",
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_KEY",
                "PROVIDER_NAME", "PROVIDER_MODEL", "PROVIDER_API_KEY",
            ]
            result["env_vars_present"] = [v for v in env_vars if v in llm_related]

            # Check if provider is enabled
            for var in env_vars:
                if var in ["LLM_PROVIDER", "PROVIDER_NAME", "OPENAI_API_KEY",
                           "ANTHROPIC_API_KEY", "AZURE_OPENAI_KEY"]:
                    result["provider_configured"] = True
                    result["provider_enabled"] = True
                    break

            # Extract provider name
            for var in ["LLM_PROVIDER", "PROVIDER_NAME"]:
                if var in env_vars:
                    result["provider_name"] = f"${{{var}}}"
                    break

            # Extract model
            for var in ["LLM_MODEL", "PROVIDER_MODEL"]:
                if var in env_vars:
                    result["provider_model"] = f"${{{var}}}"
                    break

            # Extract endpoint
            for var in ["LLM_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "PROVIDER_ENDPOINT"]:
                if var in env_vars:
                    result["provider_endpoint"] = f"${{{var}}}"
                    break

        # Check for Secret refs in pod spec
        secret_cmd = [
            "kubectl", "get", "pod", pod_name, "-n", namespace,
            "-o", "jsonpath={.spec.containers[0].envFrom[*].secretRef.name}",
        ]
        secret_result = subprocess.run(
            secret_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={"KUBECONFIG": kubeconfig},
        )
        if secret_result.returncode == 0 and secret_result.stdout.strip():
            result["secret_refs_present"] = secret_result.stdout.strip().split()

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return result


def check_incident_enriched(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    backend_port: int,
    incident_id: str,
) -> tuple[bool, dict[str, Any]]:
    """Check if an incident has been enriched.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        backend_port: Backend port
        incident_id: Incident ID to check

    Returns:
        Tuple of (is_enriched, incident_data)
    """
    import json
    import subprocess

    try:
        # Get backend pod name
        pod_cmd = [
            "kubectl", "get", "pods",
            "-n", namespace,
            "-l", f"app={backend_deployment}",
            "-o", "jsonpath={.items[0].metadata.name}",
        ]
        pod_result = subprocess.run(
            pod_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={"KUBECONFIG": kubeconfig},
        )
        if pod_result.returncode != 0:
            return False, {}
        pod_name = pod_result.stdout.strip()
        if not pod_name:
            return False, {}

        # Call incident detail API
        api_cmd = [
            "kubectl", "exec", pod_name, "-n", namespace, "-c", backend_container,
            "--", "curl", "-s", f"http://localhost:{backend_port}/api/incidents/{incident_id}",
        ]
        api_result = subprocess.run(
            api_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env={"KUBECONFIG": kubeconfig},
        )
        if api_result.returncode != 0:
            return False, {}

        try:
            incident_data = json.loads(api_result.stdout)
        except json.JSONDecodeError:
            return False, {}

        is_enriched = extract_enrichment_status_from_incident(incident_data)
        return is_enriched, incident_data

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, {}
