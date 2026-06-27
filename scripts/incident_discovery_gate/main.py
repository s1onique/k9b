"""Main orchestration for incident discovery gate.

Provides the main run function that orchestrates fixture preflight,
candidate detection, incident polling, and LLM enrichment checks (Phase 2a-2e).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .classify import (
    classify_api_contract_issue,
    classify_api_response_shape,
    classify_candidate_detection,
    classify_fixture_failure,
    extract_incident_id_from_response,
)
from .collect import (
    call_backend_incidents_api,
    collect_backend_logs,
    collect_scheduler_logs,
    get_namespace_events,
    get_pod_status,
    list_pods_in_namespace,
)
from .constants import (
    FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED,
    FAILURE_INCIDENT_DISCOVERY_TIMEOUT,
    FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY,
    FAILURE_INCIDENT_FIXTURE_MISSING,
)
from .enrich import (
    check_incident_enriched,
    classify_enrichment_status,
    get_provider_config_from_backend,
)
from .render import format_polling_history, write_all_artifacts
from .types import IncidentDiscoveryResult


def run_incident_discovery(
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    backend_port: int,
    fixture_name: str,
    artifact_dir: Path,
    max_retries: int = 12,
    retry_interval: int = 10,
    expect_llm_enrichment: bool = False,
) -> IncidentDiscoveryResult:
    """Run incident discovery gate with bounded polling and classification.

    Args:
        kubeconfig: Path to kubeconfig file
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        backend_port: Backend port
        fixture_name: Name of the incident fixture pod
        artifact_dir: Directory for artifacts
        max_retries: Maximum number of polling attempts
        retry_interval: Seconds between retries
        expect_llm_enrichment: Whether LLM enrichment is expected (enables Phase 2d/2e checks)

    Returns:
        IncidentDiscoveryResult with classification and diagnostics
    """
    result = IncidentDiscoveryResult()
    result.fixture_name = fixture_name
    result.fixture_namespace = namespace
    result.diagnostics["timestamp"] = datetime.now(UTC).isoformat()

    start_time = time.time()

    # Use artifact_dir as-is (workflow passes full path: ./lab-artifacts/live/provider-smoke/incident-discovery)
    discovery_dir = artifact_dir
    discovery_dir.mkdir(parents=True, exist_ok=True)

    # Track polling history
    poll_results: list[dict[str, Any]] = []

    # ===================================================================
    # Phase 2a: Fixture Preflight
    # ===================================================================
    print("Phase 2a: Verifying incident fixture...", flush=True)

    pod_status = get_pod_status(kubeconfig, namespace, fixture_name)
    result.fixture_exists = pod_status.get("found", False)
    result.fixture_phase = pod_status.get("phase", "")
    result.fixture_conditions = pod_status.get("conditions", [])
    result.fixture_container_states = pod_status.get("container_statuses", [])

    # Check container readiness
    container_statuses = pod_status.get("container_statuses", [])
    all_ready = all(cs.get("ready", False) for cs in container_statuses)
    result.fixture_is_healthy = all_ready

    result.diagnostics["fixture"] = {
        "name": fixture_name,
        "namespace": namespace,
        "found": result.fixture_exists,
        "phase": result.fixture_phase,
        "all_ready": all_ready,
    }

    # Classify fixture status
    fixture_failure = classify_fixture_failure(pod_status, fixture_name, namespace)

    if fixture_failure:
        result.passed = False
        result.failure_class = fixture_failure
        result.total_elapsed_seconds = time.time() - start_time

        # Collect events for diagnostics
        events = get_namespace_events(kubeconfig, namespace)
        result.diagnostics["events_count"] = len(events)

        # Write artifacts and exit
        backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Fixture '{fixture_name}' check: {fixture_failure}", flush=True)

        return result

    print(f"  Fixture '{fixture_name}' exists and is failing as expected", flush=True)

    # ===================================================================
    # Phase 2b: Candidate Detection
    # ===================================================================
    print("Phase 2b: Verifying candidate detection...", flush=True)

    events = get_namespace_events(kubeconfig, namespace)
    result.diagnostics["events_count"] = len(events)

    candidate_detected, candidate_type = classify_candidate_detection(pod_status, events)
    result.candidate_detected = candidate_detected
    result.candidate_type = candidate_type

    result.diagnostics["candidate"] = {
        "detected": candidate_detected,
        "type": candidate_type,
    }

    if not candidate_detected:
        result.passed = False
        result.failure_class = FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED
        result.total_elapsed_seconds = time.time() - start_time

        # Collect additional context
        all_pods = list_pods_in_namespace(kubeconfig, namespace)
        result.diagnostics["all_pods"] = all_pods

        backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  No candidate detected for fixture '{fixture_name}'", flush=True)

        return result

    print(f"  Candidate detected: {candidate_type}", flush=True)

    # ===================================================================
    # Phase 2c: Incident Polling with Classification
    # ===================================================================
    print(f"Phase 2c: Polling backend API (max {max_retries} attempts)...", flush=True)

    for poll_num in range(1, max_retries + 1):
        # Call backend API
        response_body, http_status = call_backend_incidents_api(
            kubeconfig, namespace, backend_deployment, backend_container, backend_port
        )

        total_elapsed = time.time() - start_time

        # Track responses
        result.poll_count = poll_num
        result.http_status_codes_seen.append(str(http_status))
        result.last_api_response = response_body

        # Classify response shape
        response_shape = classify_api_response_shape(response_body)
        result.api_response_shapes_seen.append(response_shape)

        poll_results.append({
            "poll_num": poll_num,
            "elapsed_seconds": total_elapsed,
            "http_status": http_status,
            "response_shape": response_shape,
            "incident_id": "",
        })

        # Check for API contract issues
        contract_failure = classify_api_contract_issue(response_body, http_status)
        if contract_failure:
            result.passed = False
            result.failure_class = contract_failure
            result.total_elapsed_seconds = total_elapsed

            backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
            scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
            write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

            print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
            print(f"  API response shape: {response_shape}", flush=True)
            return result

        # Extract incident ID
        incident_id = extract_incident_id_from_response(response_body)

        if incident_id:
            result.passed = True
            result.incident_found = True
            result.incident_id = incident_id
            result.total_elapsed_seconds = total_elapsed

            poll_results[-1]["incident_id"] = incident_id

            print(f"  Incident found: {incident_id} (poll {poll_num}/{max_retries}, {total_elapsed:.1f}s)", flush=True)

            # Write success artifacts
            result.diagnostics["poll_results"] = poll_results
            backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
            scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
            write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

            # Phase 2d/2e: Check LLM enrichment if expected
            if expect_llm_enrichment:
                result = _check_llm_enrichment(
                    result, kubeconfig, namespace, backend_deployment,
                    backend_container, backend_port, incident_id, discovery_dir
                )

            return result

        # No incident yet
        print(f"  No incident found... (poll {poll_num}/{max_retries}, {total_elapsed:.1f}s)", flush=True)

        if poll_num < max_retries:
            time.sleep(retry_interval)

    # ===================================================================
    # Timeout: All polls exhausted
    # ===================================================================
    result.passed = False
    result.total_elapsed_seconds = time.time() - start_time

    # Classify the timeout based on what we observed
    if result.candidate_detected:
        # Candidate detected but not promoted
        result.failure_class = FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED
    elif not result.fixture_exists:
        result.failure_class = FAILURE_INCIDENT_FIXTURE_MISSING
    elif result.fixture_is_healthy:
        result.failure_class = FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY
    else:
        result.failure_class = FAILURE_INCIDENT_DISCOVERY_TIMEOUT

    result.diagnostics["poll_results"] = poll_results

    # Collect final diagnostics
    all_pods = list_pods_in_namespace(kubeconfig, namespace)
    result.diagnostics["all_pods"] = all_pods

    backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
    scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
    write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

    print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
    print(f"  No incident after {max_retries} polls ({result.total_elapsed_seconds:.1f}s total)", flush=True)
    print(f"  Candidate detected: {result.candidate_detected}", flush=True)
    print("  Polling history:", flush=True)
    print(format_polling_history(poll_results), flush=True)

    return result


def _check_llm_enrichment(
    result: IncidentDiscoveryResult,
    kubeconfig: str,
    namespace: str,
    backend_deployment: str,
    backend_container: str,
    backend_port: int,
    incident_id: str,
    discovery_dir: Path,
) -> IncidentDiscoveryResult:
    """Phase 2d/2e: Check LLM enrichment status.

    Args:
        result: Current result object
        kubeconfig: Path to kubeconfig
        namespace: Kubernetes namespace
        backend_deployment: Backend deployment name
        backend_container: Backend container name
        backend_port: Backend port
        incident_id: Found incident ID
        discovery_dir: Artifact directory

    Returns:
        Updated result with enrichment classification
    """

    print("Phase 2d: Checking provider configuration...", flush=True)

    # Get provider configuration from backend
    provider_config = get_provider_config_from_backend(kubeconfig, namespace, backend_deployment)

    result.provider_enabled = provider_config.get("provider_enabled", False)
    result.provider_configured = provider_config.get("provider_configured", False)
    result.provider_name = provider_config.get("provider_name", "")
    result.provider_model = provider_config.get("provider_model", "")
    result.provider_endpoint = provider_config.get("provider_endpoint", "")
    result.provider_secret_refs = provider_config.get("secret_refs_present", [])
    result.provider_env_vars = provider_config.get("env_vars_present", [])

    # Store provider config in diagnostics
    result.diagnostics["provider_config"] = {
        "enabled": result.provider_enabled,
        "configured": result.provider_configured,
        "name": result.provider_name,
        "model": result.provider_model,
        "endpoint": result.provider_endpoint,
        "secret_refs": result.provider_secret_refs,
        "env_vars": result.provider_env_vars,
        "env_summary": provider_config.get("raw_env_summary", ""),
    }

    print("Phase 2e: Checking incident enrichment status...", flush=True)

    # Check if incident has been enriched
    incident_enriched, incident_data = check_incident_enriched(
        kubeconfig, namespace, backend_deployment, backend_container,
        backend_port, incident_id
    )

    result.enrichment_status = "completed" if incident_enriched else "not_triggered"

    if incident_data:
        result.diagnostics["incident_detail"] = incident_data

    # Provider invocation count would come from backend logs/metrics
    # For now, assume 0 unless we find evidence
    result.provider_invocation_count = 0

    # Look for provider invocation evidence in logs
    backend_logs = collect_backend_logs(kubeconfig, namespace, backend_deployment, backend_container)
    if backend_logs:
        # Check for common LLM provider call patterns in logs
        llm_indicators = [
            "openai", "anthropic", "azure", "llm", "provider",
            "triage", "enrich", "analysis"
        ]
        for indicator in llm_indicators:
            if indicator.lower() in backend_logs.lower():
                result.provider_invocation_count = 1
                break

    result.provider_invocation_expected = result.provider_enabled and result.provider_configured

    # Classify enrichment status
    enrichment_failure = classify_enrichment_status(
        incident_exists=result.incident_found,
        provider_enabled=result.provider_enabled,
        provider_configured=result.provider_configured,
        provider_secret_refs_present=result.provider_secret_refs,
        provider_env_vars_present=result.provider_env_vars,
        provider_invocation_count=result.provider_invocation_count,
        incident_enriched=incident_enriched,
    )

    if enrichment_failure:
        result.passed = False
        result.failure_class = enrichment_failure
        result.enrichment_status = "failed"

        print(f"LLM ENRICHMENT GATE FAILED: {enrichment_failure}", flush=True)

        # Write updated artifacts
        scheduler_logs = collect_scheduler_logs(kubeconfig, namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)
    else:
        print(f"LLM enrichment status: {result.enrichment_status}", flush=True)
        if result.provider_invocation_expected:
            print(f"  Provider invocation count: {result.provider_invocation_count}", flush=True)

    return result
