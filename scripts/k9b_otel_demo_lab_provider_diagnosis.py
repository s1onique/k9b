#!/usr/bin/env python3
"""Provider smoke diagnosis phases (P2, P3, P4).

These phases handle incident discovery, one-pass diagnosis, and persisted diagnosis verification.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

from .k9b_lab_common_helpers import log
from .k9b_otel_demo_lab_constants import (
    FAILURE_PROVIDER_SMOKE_NOT_CONFIGURED,
    FAILURE_PROVIDER_SMOKE_NOT_INVOKED,
    K9B_BACKEND_CONTAINER,
    K9B_BACKEND_DEPLOYMENT,
    K9B_BACKEND_PORT,
    K9B_NAMESPACE,
    OTEL_INCIDENT_FIXTURE,
    PHASE_INCIDENT_DISCOVERY,
    PHASE_PERSISTED_DIAGNOSIS,
    PHASE_PROVIDER_SMOKE,
)
from .k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def phase_p2_incident_discovery_provider(
    config: LabConfig, artifact_dir: Path
) -> tuple[LabPhaseResult, str | None]:
    """Phase P2: Incident Discovery (k9b API-backed).
    
    After OTel failure injection, polls the backend API for incidents.
    This is fail-closed when enable_provider_smoke=true.
    
    Args:
        config: Lab configuration containing kubeconfig and namespace
        artifact_dir: Directory for phase artifacts
    
    Returns:
        Tuple of (phase_result, incident_id or None)
    """
    from .incident_discovery_gate import run_incident_discovery

    start = time.time()
    phase_dir = artifact_dir / PHASE_INCIDENT_DISCOVERY
    phase_dir.mkdir(parents=True, exist_ok=True)

    # Backend namespace (where k9b backend runs)
    backend_namespace = K9B_NAMESPACE
    
    # Workload namespace (where OTel demo incidents are injected)
    # This is where we should look for the failing fixture
    incident_namespace = config.namespace  # OTEL_DEMO_NAMESPACE from config
    
    log("=== Phase P2: Incident Discovery (k9b API) ===")
    log(f"Polling k9b backend for incidents:")
    log(f"  backend_namespace={backend_namespace}")
    log(f"  incident_namespace={incident_namespace}")
    log(f"  expected_fixture={OTEL_INCIDENT_FIXTURE}")

    # The OTel demo scenario uses "recommendation" with feature flag failure (chart 0.40.9 naming)
    fixture_name = OTEL_INCIDENT_FIXTURE

    try:
        result = run_incident_discovery(
            kubeconfig=config.kubeconfig,
            backend_namespace=backend_namespace,
            incident_namespace=incident_namespace,
            backend_deployment=K9B_BACKEND_DEPLOYMENT,
            backend_container=K9B_BACKEND_CONTAINER,
            backend_port=K9B_BACKEND_PORT,
            fixture_name=fixture_name,
            artifact_dir=phase_dir,
            max_retries=12,
            retry_interval=10,
            expect_llm_enrichment=False,
        )

        result_data = result.to_dict()
        result_path = phase_dir / "incident-discovery-result.json"
        result_path.write_text(json.dumps(result_data, indent=2))

        duration = time.time() - start
        incident_id = result.incident_id

        if result.passed and incident_id:
            log(f"Incident discovery PASSED: incident_id={incident_id}")

            incident_id_path = phase_dir / "incident-id.txt"
            incident_id_path.write_text(incident_id)

            return LabPhaseResult(
                phase="p2-incident-discovery",
                success=True,
                message=f"Incident discovered: {incident_id}",
                artifacts={
                    "discovery_result": str(result_path),
                    "incident_id": incident_id,
                },
                duration_seconds=duration,
            ), incident_id
        else:
            log(f"Incident discovery FAILED: {result.failure_class}")
            return LabPhaseResult(
                phase="p2-incident-discovery",
                success=False,
                message=f"Incident discovery failed: {result.failure_class}",
                artifacts={"discovery_result": str(result_path)},
                duration_seconds=duration,
            ), None

    except Exception as e:
        duration = time.time() - start
        log(f"Incident discovery error: {e}")
        return LabPhaseResult(
            phase="p2-incident-discovery",
            success=False,
            message=f"Incident discovery error: {e}",
            artifacts={},
            duration_seconds=duration,
        ), None


def phase_p3_provider_smoke(
    config: LabConfig, artifact_dir: Path, incident_id: str
) -> LabPhaseResult:
    """Phase P3: One-Pass Diagnosis Provider Smoke.
    
    Calls POST /api/incidents/{id}/one-pass-diagnosis against the k9b backend.
    Verifies provider_configured=true and provider_invocation_attempted=true.
    Uses verify_diagnosis_provider_artifacts.py for artifact safety.
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_PROVIDER_SMOKE
    phase_dir.mkdir(parents=True, exist_ok=True)

    log("=== Phase P3: One-Pass Diagnosis Provider Smoke ===")
    log(f"Calling one-pass diagnosis for incident: {incident_id}")

    url = f"http://localhost:{K9B_BACKEND_PORT}/api/incidents/{incident_id}/one-pass-diagnosis"

    # Use temp dir for raw response (not uploaded to artifacts)
    raw_tmp = Path(tempfile.mkdtemp(prefix="provider-smoke-raw-"))

    try:
        curl_cmd = [
            "kubectl", "--kubeconfig", config.kubeconfig, "exec", "-n", K9B_NAMESPACE,
            f"deploy/{K9B_BACKEND_DEPLOYMENT}", "-c", K9B_BACKEND_CONTAINER, "--",
            "curl", "-sS", "-X", "POST",
            url,
            "-H", "Content-Type: application/json",
            "-d", "{}",
            "-w", "\n%{http_code}",
            "--max-time", "180",
        ]

        result = subprocess.run(
            curl_cmd, capture_output=True, text=True, timeout=200
        )

        output_lines = result.stdout.strip().split("\n")
        if not output_lines:
            return _fail_provider_smoke(phase_dir, raw_tmp, start, "empty_response", "No output from curl")

        http_status = output_lines[-1]
        response_body = "\n".join(output_lines[:-1]) if len(output_lines) > 1 else ""

        # Save raw response to temp (not uploaded)
        (raw_tmp / "diagnosis-response.json").write_text(response_body)
        (raw_tmp / "http-status.txt").write_text(http_status)

        try:
            response_json = json.loads(response_body)
        except json.JSONDecodeError:
            return _fail_provider_smoke(phase_dir, raw_tmp, start, "invalid_json", f"Invalid JSON response: HTTP {http_status}")

        if http_status != "200":
            return _fail_provider_smoke(phase_dir, raw_tmp, start, f"http_error_{http_status}", f"HTTP {http_status} from API")

        provider_configured = response_json.get("provider_configured", False)
        provider_invoked = response_json.get("provider_invocation_attempted", False)

        # Use the actual provider artifact verifier for safety
        from .verify_diagnosis_provider_artifacts import verify_provider_artifacts
        sanitized_data, artifact_error = verify_provider_artifacts(
            incident_id=incident_id,
            raw_response=response_json,
            phase_dir=phase_dir,
        )

        duration = time.time() - start

        if artifact_error:
            return _fail_provider_smoke(phase_dir, raw_tmp, start, "artifact_verification_failed", artifact_error)

        if not provider_configured:
            return _fail_provider_smoke(phase_dir, raw_tmp, start, FAILURE_PROVIDER_SMOKE_NOT_CONFIGURED, "provider_configured=false")

        if not provider_invoked:
            return _fail_provider_smoke(phase_dir, raw_tmp, start, FAILURE_PROVIDER_SMOKE_NOT_INVOKED, "provider_invocation_attempted=false")

        log(f"Provider smoke PASSED: configured={provider_configured}, invoked={provider_invoked}")

        rmtree(raw_tmp, ignore_errors=True)

        return LabPhaseResult(
            phase="p3-provider-smoke",
            success=True,
            message=f"Provider smoke passed: configured={provider_configured}, invoked={provider_invoked}",
            artifacts={"provider_smoke_result": str(phase_dir / "provider-smoke-result.json")},
            duration_seconds=duration,
        )

    except subprocess.TimeoutExpired:
        return _fail_provider_smoke(phase_dir, raw_tmp, start, "timeout", "One-pass diagnosis timed out after 180s")
    except Exception as e:
        return _fail_provider_smoke(phase_dir, raw_tmp, start, "error", str(e))


def _fail_provider_smoke(
    phase_dir: Path, raw_tmp: Path, start: float, failure_class: str, message: str
) -> LabPhaseResult:
    """Helper to handle provider smoke failures."""
    duration = time.time() - start

    failure_data = {
        "failure_class": failure_class,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    failure_path = phase_dir / "provider-smoke-failed.json"
    failure_path.write_text(json.dumps(failure_data, indent=2))

    rmtree(raw_tmp, ignore_errors=True)

    return LabPhaseResult(
        phase="p3-provider-smoke",
        success=False,
        message=f"Provider smoke failed: {message}",
        artifacts={"failure": str(failure_path)},
        duration_seconds=duration,
    )


def phase_p4_persisted_diagnosis(
    config: LabConfig, artifact_dir: Path, incident_id: str
) -> LabPhaseResult:
    """Phase P4: Persisted Diagnosis Contract Verification.
    
    Fetches incident via GET /api/incidents/{id} and verifies persisted diagnosis state.
    Uses check_persisted_diagnosis_contract.py and verify_diagnosis_provider_artifacts.py.
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_PERSISTED_DIAGNOSIS
    phase_dir.mkdir(parents=True, exist_ok=True)

    log("=== Phase P4: Persisted Diagnosis Contract Verification ===")
    log(f"Fetching incident: {incident_id}")

    url = f"http://localhost:{K9B_BACKEND_PORT}/api/incidents/{incident_id}"

    # Use temp dir for raw response
    raw_tmp = Path(tempfile.mkdtemp(prefix="persisted-diagnosis-raw-"))

    try:
        curl_cmd = [
            "kubectl", "--kubeconfig", config.kubeconfig, "exec", "-n", K9B_NAMESPACE,
            f"deploy/{K9B_BACKEND_DEPLOYMENT}", "-c", K9B_BACKEND_CONTAINER, "--",
            "curl", "-sS", "-X", "GET",
            url,
            "-w", "\n%{http_code}",
            "--max-time", "60",
        ]

        result = subprocess.run(
            curl_cmd, capture_output=True, text=True, timeout=70
        )

        output_lines = result.stdout.strip().split("\n")
        if not output_lines:
            return _fail_persisted_diagnosis(phase_dir, raw_tmp, start, "empty_response", "No output from curl")

        http_status = output_lines[-1]
        response_body = "\n".join(output_lines[:-1]) if len(output_lines) > 1 else ""

        (raw_tmp / "incident-response.json").write_text(response_body)
        (raw_tmp / "http-status.txt").write_text(http_status)

        try:
            incident_json = json.loads(response_body)
        except json.JSONDecodeError:
            return _fail_persisted_diagnosis(phase_dir, raw_tmp, start, "invalid_json", f"Invalid JSON response: HTTP {http_status}")

        if http_status != "200":
            return _fail_persisted_diagnosis(phase_dir, raw_tmp, start, f"http_error_{http_status}", f"HTTP {http_status} from API")

        # Use check_persisted_diagnosis_contract.py functions
        from .check_persisted_diagnosis_contract import (
            check_diagnosis_persisted,
            check_for_secrets,
            check_provider_status,
        )

        diagnosis_persisted, diag_failure, diag_findings = check_diagnosis_persisted(incident_json)
        provider_ok, prov_failure, prov_findings = check_provider_status(incident_json, require_provider_invoked=True)
        incident_content = json.dumps(incident_json)
        secret_findings = check_for_secrets(incident_content)

        # Use verify_diagnosis_provider_artifacts for artifact safety
        from .verify_diagnosis_provider_artifacts import verify_provider_artifacts
        _, artifact_error = verify_provider_artifacts(
            incident_id=incident_id,
            raw_response=incident_json,
            phase_dir=phase_dir,
        )

        duration = time.time() - start

        passed = diagnosis_persisted and provider_ok and not secret_findings and not artifact_error

        sanitized_data = {
            "incident_id": incident_id,
            "http_status": http_status,
            "diagnosis_persisted": diagnosis_persisted,
            "provider_ok": provider_ok,
            "secrets_found": len(secret_findings) > 0,
            "artifact_safety": "passed" if not artifact_error else f"failed: {artifact_error}",
            "timestamp": datetime.now(UTC).isoformat(),
            "findings": diag_findings + prov_findings,
        }
        sanitized_path = phase_dir / "persisted-diagnosis-result.json"
        sanitized_path.write_text(json.dumps(sanitized_data, indent=2))

        summary_lines = [
            f"Persisted Diagnosis Contract Gate Result: {'PASSED' if passed else 'FAILED'}",
            f"Incident ID: {incident_id}",
            f"Incident fetch: HTTP {http_status}",
            f"Diagnosis persisted: {diagnosis_persisted}",
            f"Provider configured/invoked: {provider_ok}",
            f"Secrets found: {len(secret_findings) > 0}",
        ]
        if not passed:
            if diag_failure:
                summary_lines.append(f"Failure: {diag_failure}")
            if prov_failure:
                summary_lines.append(f"Failure: {prov_failure}")
            if artifact_error:
                summary_lines.append(f"Artifact safety: {artifact_error}")
            if secret_findings:
                summary_lines.append(f"Secrets: {secret_findings}")

        summary_path = phase_dir / "bounded-summary.txt"
        summary_path.write_text("\n".join(summary_lines))

        rmtree(raw_tmp, ignore_errors=True)

        if passed:
            log("Persisted diagnosis contract PASSED")
            return LabPhaseResult(
                phase="p4-persisted-diagnosis",
                success=True,
                message="Persisted diagnosis contract verified",
                artifacts={"persisted_diagnosis_result": str(sanitized_path)},
                duration_seconds=duration,
            )
        else:
            failure_reason = diag_failure or prov_failure or (artifact_error and "artifact_verification_failed") or "contract_verification_failed"
            log(f"Persisted diagnosis contract FAILED: {failure_reason}")
            return LabPhaseResult(
                phase="p4-persisted-diagnosis",
                success=False,
                message=f"Persisted diagnosis contract failed: {failure_reason}",
                artifacts={"persisted_diagnosis_result": str(sanitized_path)},
                duration_seconds=duration,
            )

    except subprocess.TimeoutExpired:
        return _fail_persisted_diagnosis(phase_dir, raw_tmp, start, "timeout", "Incident fetch timed out after 60s")
    except Exception as e:
        return _fail_persisted_diagnosis(phase_dir, raw_tmp, start, "error", str(e))


def _fail_persisted_diagnosis(
    phase_dir: Path, raw_tmp: Path, start: float, failure_class: str, message: str
) -> LabPhaseResult:
    """Helper to handle persisted diagnosis failures."""
    duration = time.time() - start

    failure_data = {
        "failure_class": failure_class,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    failure_path = phase_dir / "persisted-diagnosis-failed.json"
    failure_path.write_text(json.dumps(failure_data, indent=2))

    summary_lines = [
        "Persisted Diagnosis Contract Gate Result: FAILED",
        f"Failure class: {failure_class}",
        f"Message: {message}",
    ]
    summary_path = phase_dir / "bounded-summary.txt"
    summary_path.write_text("\n".join(summary_lines))

    rmtree(raw_tmp, ignore_errors=True)

    return LabPhaseResult(
        phase="p4-persisted-diagnosis",
        success=False,
        message=f"Persisted diagnosis failed: {message}",
        artifacts={"failure": str(failure_path)},
        duration_seconds=duration,
    )
