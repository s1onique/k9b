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
    call_backend_snapshot_api,
    collect_backend_logs,
    collect_scheduler_logs,
    get_backend_pod_info,
    get_namespace_events,
    get_pod_status,
    list_pods_in_namespace,
)
from .constants import (
    FAILURE_BACKEND_POD_NOT_FOUND,
    FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED,
    FAILURE_INCIDENT_DISCOVERY_TIMEOUT,
    FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY,
    FAILURE_INCIDENT_FIXTURE_MISSING,
    FAILURE_INCIDENT_PROMOTED_NOT_LISTED,
    FAILURE_SNAPSHOT_COMPLETED_NO_CANDIDATES,
    FAILURE_SNAPSHOT_NOT_TRIGGERED,
    FAILURE_WRONG_BACKEND_PROCESS,
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
    backend_namespace: str,
    incident_namespace: str,
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
        backend_namespace: Kubernetes namespace where k9b backend runs (for API calls)
        incident_namespace: Kubernetes namespace where incident fixture exists (for snapshot/discovery)
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
    result.fixture_namespace = incident_namespace
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

    pod_status = get_pod_status(kubeconfig, incident_namespace, fixture_name)
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
        "namespace": incident_namespace,
        "found": result.fixture_exists,
        "phase": result.fixture_phase,
        "all_ready": all_ready,
    }

    # Classify fixture status
    fixture_failure = classify_fixture_failure(pod_status, fixture_name, incident_namespace)

    if fixture_failure:
        result.passed = False
        result.failure_class = fixture_failure
        result.total_elapsed_seconds = time.time() - start_time

        # Collect events for diagnostics
        events = get_namespace_events(kubeconfig, incident_namespace)
        result.diagnostics["events_count"] = len(events)

        # Write artifacts and exit (logs from backend namespace)
        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Fixture '{fixture_name}' check: {fixture_failure}", flush=True)

        return result

    print(f"  Fixture '{fixture_name}' exists and is failing as expected", flush=True)

    # ===================================================================
    # Phase 2b: Candidate Detection
    # ===================================================================
    print("Phase 2b: Verifying candidate detection...", flush=True)

    events = get_namespace_events(kubeconfig, incident_namespace)
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

        # Collect additional context from incident namespace
        all_pods = list_pods_in_namespace(kubeconfig, incident_namespace)
        result.diagnostics["all_pods"] = all_pods

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  No candidate detected for fixture '{fixture_name}'", flush=True)

        return result

    print(f"  Candidate detected: {candidate_type}", flush=True)

    # ===================================================================
    # Phase 2c: Trigger Snapshot Capture and Poll for Incidents
    # ===================================================================
    print("Phase 2c: Triggering backend snapshot capture...", flush=True)

    # Step 1: Select a single backend pod for identity consistency
    # Since IncidentStore is process-local, all API calls must go to the same pod
    snapshot_pod_info = get_backend_pod_info(kubeconfig, backend_namespace, backend_deployment)
    result.diagnostics["snapshot_pod_info"] = snapshot_pod_info

    if not snapshot_pod_info.get("found"):
        result.passed = False
        result.failure_class = FAILURE_BACKEND_POD_NOT_FOUND
        result.total_elapsed_seconds = time.time() - start_time
        result.diagnostics["snapshot_error"] = "Could not find backend pod"

        # Include attempted selectors in diagnostics for debugging
        attempted = snapshot_pod_info.get("attempted_selectors", [])
        if attempted:
            result.diagnostics["attempted_selectors"] = attempted
            result.diagnostics["namespace_diagnostics"] = snapshot_pod_info.get("diagnostics", {})

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print("  Could not find backend pod for snapshot capture", flush=True)
        # Print attempted selectors for debugging
        for attempt in attempted:
            source = attempt.get("source", "unknown")
            selector = attempt.get("selector", "unknown")
            print(f"    Tried {source} selector: {selector}", flush=True)
        return result

    snapshot_pod_name = snapshot_pod_info.get("pod_name", "")
    print(f"  Using backend pod: {snapshot_pod_name}", flush=True)
    if snapshot_pod_info.get("total_running_pods", 0) > 1:
        print(f"  WARNING: Multiple backend replicas detected ({snapshot_pod_info.get('total_running_pods')}). Using oldest pod for consistency.", flush=True)

    # Step 2: Trigger snapshot capture
    # Use backend_namespace for exec location, incident_namespace for snapshot target
    snapshot_response, snapshot_http_status, snapshot_actual_pod = call_backend_snapshot_api(
        kubeconfig=kubeconfig,
        namespace=backend_namespace,
        backend_deployment=backend_deployment,
        backend_container=backend_container,
        backend_port=backend_port,
        snapshot_namespace=incident_namespace,
        backend_pod_name=snapshot_pod_name,
    )

    # Verify the snapshot was actually called on the expected pod
    if snapshot_actual_pod != snapshot_pod_name:
        result.passed = False
        result.failure_class = FAILURE_WRONG_BACKEND_PROCESS
        result.total_elapsed_seconds = time.time() - start_time
        result.diagnostics["wrong_backend_process_detected"] = True
        result.diagnostics["expected_pod"] = snapshot_pod_name
        result.diagnostics["actual_pod"] = snapshot_actual_pod

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print("  Snapshot API called on unexpected pod", flush=True)
        print(f"  Expected: {snapshot_pod_name}, Actual: {snapshot_actual_pod}", flush=True)
        return result

    result.diagnostics["snapshot_request"] = {
        "backend_namespace": backend_namespace,
        "incident_namespace": incident_namespace,
        "pod_name": snapshot_pod_name,
        "http_status": snapshot_http_status,
    }
    result.diagnostics["snapshot_response"] = snapshot_response

    # Step 3: Parse snapshot response
    if snapshot_http_status != 200:
        result.passed = False
        result.failure_class = FAILURE_SNAPSHOT_NOT_TRIGGERED
        result.total_elapsed_seconds = time.time() - start_time
        result.diagnostics["snapshot_error"] = f"HTTP {snapshot_http_status}"

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Snapshot API returned HTTP {snapshot_http_status}", flush=True)
        return result

    if snapshot_response.get("error"):
        result.passed = False
        result.failure_class = FAILURE_SNAPSHOT_NOT_TRIGGERED
        result.total_elapsed_seconds = time.time() - start_time
        result.diagnostics["snapshot_error"] = snapshot_response.get("error", "Unknown error")

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Snapshot error: {snapshot_response.get('error')}", flush=True)
        return result

    # Extract snapshot metadata
    bundle_id = snapshot_response.get("bundle_id", "")
    summary = snapshot_response.get("summary", {})
    candidates_count = summary.get("candidates_count", 0)
    incidents_promoted_count = summary.get("incidents_promoted_count", 0)
    promoted_incidents = snapshot_response.get("promoted_incidents", [])

    print(f"  Snapshot captured: bundle_id={bundle_id}", flush=True)
    print(f"  Candidates found: {candidates_count}", flush=True)
    print(f"  Incidents promoted: {incidents_promoted_count}", flush=True)

    result.diagnostics["snapshot_bundle_id"] = bundle_id
    result.diagnostics["snapshot_candidates_count"] = candidates_count
    result.diagnostics["snapshot_incidents_promoted_count"] = incidents_promoted_count

    # Step 4: Check if snapshot generated candidates
    if candidates_count == 0:
        result.passed = False
        result.failure_class = FAILURE_SNAPSHOT_COMPLETED_NO_CANDIDATES
        result.total_elapsed_seconds = time.time() - start_time

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print("  Snapshot completed but generated zero candidates", flush=True)
        return result

    # Step 5: Check if candidates were promoted
    if incidents_promoted_count == 0 and not promoted_incidents:
        result.passed = False
        result.failure_class = FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED
        result.total_elapsed_seconds = time.time() - start_time

        backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

        print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
        print("  Snapshot generated candidates but none were promoted to incident store", flush=True)
        return result

    # Step 6: Poll incidents API using the SAME backend pod
    print(f"Phase 2c: Polling incidents API (max {max_retries} attempts)...", flush=True)

    # Track the pod used for incidents polling to verify consistency
    incidents_pod_name: str | None = None

    for poll_num in range(1, max_retries + 1):
        # Call incidents API targeting the SAME pod as snapshot (in backend_namespace)
        response_body, http_status = call_backend_incidents_api(
            kubeconfig, backend_namespace, backend_deployment, backend_container, backend_port,
            backend_pod_name=snapshot_pod_name,
        )
        # Track which pod was used for the first poll
        if poll_num == 1:
            incidents_pod_name = snapshot_pod_name

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
            "snapshot_pod": snapshot_pod_name,
            "incidents_pod": incidents_pod_name,
        })

        # Check for API contract issues
        contract_failure = classify_api_contract_issue(response_body, http_status)
        if contract_failure:
            result.passed = False
            result.failure_class = contract_failure
            result.total_elapsed_seconds = total_elapsed

            backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
            scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
            write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

            print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
            print(f"  API response shape: {response_shape}", flush=True)
            return result

        # Extract incident ID
        incident_id = extract_incident_id_from_response(response_body)

        if incident_id:
            # Phase 2c: Incident discovered successfully
            result.passed = True  # Overall gate passes unless enrichment fails
            result.incident_found = True
            result.incident_id = incident_id
            result.total_elapsed_seconds = total_elapsed
            result.discovery_status = "passed"  # Incident discovery PASSED

            poll_results[-1]["incident_id"] = incident_id

            print(f"  Incident found: {incident_id} (poll {poll_num}/{max_retries}, {total_elapsed:.1f}s)", flush=True)

            # Write initial success artifacts
            result.diagnostics["poll_results"] = poll_results
            backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
            scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
            write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

            # Phase 2d/2e: Check LLM enrichment if expected
            if expect_llm_enrichment:
                result = _check_llm_enrichment(
                    result, kubeconfig, backend_namespace, backend_deployment,
                    backend_container, backend_port, incident_id, discovery_dir
                )
                # If enrichment failed, overall passed is False but discovery_status remains passed
                if not result.passed:
                    result.discovery_status = "passed"  # Discovery still passed, only enrichment failed
            else:
                # Enrichment not expected, mark as skipped/disabled
                result.enrichment_gate_status = "skipped"
                result.enrichment_status = "skipped"

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

    # The snapshot promoted incidents but they don't appear in the list API
    # This could indicate a backend process identity mismatch
    if incidents_promoted_count > 0 or promoted_incidents:
        result.failure_class = FAILURE_INCIDENT_PROMOTED_NOT_LISTED
    elif candidates_count > 0:
        result.failure_class = FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED
    elif result.candidate_detected:
        result.failure_class = FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED
    elif not result.fixture_exists:
        result.failure_class = FAILURE_INCIDENT_FIXTURE_MISSING
    elif result.fixture_is_healthy:
        result.failure_class = FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY
    else:
        result.failure_class = FAILURE_INCIDENT_DISCOVERY_TIMEOUT

    result.diagnostics["poll_results"] = poll_results

    # Collect final diagnostics
    all_pods = list_pods_in_namespace(kubeconfig, incident_namespace)
    result.diagnostics["all_pods"] = all_pods

    backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
    scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
    write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)

    print(f"INCIDENT DISCOVERY GATE FAILED: {result.failure_class}", flush=True)
    print(f"  Snapshot triggered with {incidents_promoted_count} incidents promoted", flush=True)
    print(f"  But /api/incidents returned empty after {max_retries} polls", flush=True)
    print("  Polling history:", flush=True)
    print(format_polling_history(poll_results), flush=True)

    return result


def _check_llm_enrichment(
    result: IncidentDiscoveryResult,
    kubeconfig: str,
    backend_namespace: str,
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
        backend_namespace: Kubernetes namespace where k9b backend runs
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
    provider_config = get_provider_config_from_backend(kubeconfig, backend_namespace, backend_deployment)

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
        kubeconfig, backend_namespace, backend_deployment, backend_container,
        backend_port, incident_id
    )

    result.enrichment_status = "completed" if incident_enriched else "not_triggered"

    if incident_data:
        result.diagnostics["incident_detail"] = incident_data

    # Provider invocation count would come from backend logs/metrics
    # For now, assume 0 unless we find evidence
    result.provider_invocation_count = 0

    # Look for provider invocation evidence in logs
    backend_logs = collect_backend_logs(kubeconfig, backend_namespace, backend_deployment, backend_container)
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

        # Distinguish between "disabled" (expected but not enabled) vs "configured but not working"
        if enrichment_failure == "llm_enrichment_disabled":
            result.enrichment_gate_status = "disabled"
            print("LLM enrichment gate: DISABLED", flush=True)
            print(f"  Provider enabled: {result.provider_enabled}", flush=True)
            print(f"  Provider configured: {result.provider_configured}", flush=True)
        else:
            result.enrichment_gate_status = "failed"
            print(f"LLM ENRICHMENT GATE FAILED: {enrichment_failure}", flush=True)

        # Write updated artifacts
        scheduler_logs = collect_scheduler_logs(kubeconfig, backend_namespace)
        write_all_artifacts(discovery_dir, result, backend_logs, scheduler_logs)
    else:
        result.enrichment_gate_status = "passed"
        print(f"LLM enrichment status: {result.enrichment_status}", flush=True)
        if result.provider_invocation_expected:
            print(f"  Provider invocation count: {result.provider_invocation_count}", flush=True)

    return result
