"""Incident one-pass diagnosis service.

This module provides a shared service function that wires the real incident
diagnosis API/service path to the production one-pass read-only diagnosis loop.

The service:
1. Loads the incident from the incident store
2. Builds the production case file
3. Runs one pass of the read-only diagnosis loop orchestrator
4. Persists diagnosis output/artifacts
5. Returns a stable API/service DTO

Design constraints:
- Fully offline (no kubectl, helm, docker, registry, GitHub API)
- Read-only (no cluster mutation)
- Provider injected (tests inject fake, production uses real)
- Fail-closed on missing providers/handlers
- Uses golden-case safety patterns for consistency

Module organization:
- Service function with full provider injection
- Types (Protocol, Request/Response dataclasses) moved to incident_diagnosis_types.py
- Safety enforcement in diagnosis_safety_enforcer.py
- Provider proof fields in diagnosis_provider_proof.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from .diagnosis_provider_proof import get_provider_proof_fields
from .diagnosis_safety_enforcer import enforce_diagnosis_safety
from .golden_case_one_pass_enforcement import (
    FakeHandlerExecutionError,
    enforce_fake_handlers,
)
from .incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)
from .incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from .incident_diagnosis_types import (
    IncidentDiagnosisServiceResult,
    IncidentOnePassServiceRequest,
)
from .incident_llm_diagnosis import (
    build_incident_diagnosis,
)

if TYPE_CHECKING:
    pass


__all__ = [
    # Types (re-exported for backwards compatibility)
    "IncidentDiagnosisServiceResult",
    "IncidentOnePassServiceRequest",
    # Classes (re-exported for backwards compatibility - moved to incident_diagnosis_types.py)
    "ArtifactWriter",
    "DiagnosisProvider",
    "NoOpDiagnosisProvider",
    "TempFileArtifactWriter",
    # Functions (re-exported for backwards compatibility - moved to diagnosis_safety_enforcer.py)
    "_enforce_safety",
    # Main service function
    "run_incident_one_pass_diagnosis",
]


# Re-export for backwards compatibility (moved to incident_diagnosis_types.py)
from .diagnosis_provider_proof import NoOpDiagnosisProvider

# Re-export for backwards compatibility (moved to diagnosis_safety_enforcer.py)
from .diagnosis_safety_enforcer import enforce_diagnosis_safety as _enforce_safety
from .incident_diagnosis_types import (
    ArtifactWriter,
    DiagnosisProvider,
    TempFileArtifactWriter,
)

# =============================================================================
# Service Function
# =============================================================================


def run_incident_one_pass_diagnosis(
    request: IncidentOnePassServiceRequest,
) -> IncidentDiagnosisServiceResult:
    """Run one-pass read-only diagnosis for an incident.

    This function wires the real incident diagnosis API/service path to the
    production one-pass read-only diagnosis loop.

    The function:
    1. Loads the incident from the incident store
    2. Builds the production case file
    3. Runs one pass of the read-only diagnosis loop orchestrator
    4. Persists diagnosis output/artifacts
    5. Returns a stable API/service DTO

    Args:
        request: Service request with all dependencies injected

    Returns:
        IncidentDiagnosisServiceResult with diagnosis outcome
    """
    from .incident_store_provider import get_incident_store

    resolved_now = request.now if request.now is not None else datetime.now(UTC)
    incident_id = request.incident_id

    # Step 1: Load incident from store
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            error="Incident not found",
        )

    # Step 2: Build case file
    if request.golden_case_mode and request.golden_case_manifest:
        # Use golden-case case file builder for ACT-local proof path
        from .golden_case_one_pass_diagnosis_loop import build_golden_case_case_file

        case_dir = request.golden_case_case_dir
        evidence_provider = request.golden_case_evidence_provider
        if case_dir is None or evidence_provider is None:
            return IncidentDiagnosisServiceResult(
                incident_id=incident_id,
                error="golden_case_case_dir and golden_case_evidence_provider are required for golden_case_mode",
            )

        case_file = build_golden_case_case_file(
            case_dir=case_dir,
            manifest=request.golden_case_manifest,
            evidence_provider=evidence_provider,
            now=resolved_now,
        )
    else:
        # Use production case file builder
        from .incident_case_file import build_incident_case_file

        raw_case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=request.external_analysis_dir,
            now=resolved_now,
        )
        if raw_case_file is not None:
            # Convert dict[str, object] to dict[str, Any] for downstream compatibility
            case_file = cast(dict[str, Any], dict(raw_case_file))
        else:
            case_file = None

    if case_file is None:
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            error="Failed to build case file",
        )

    # Step 3: Build diagnosis report via LLM provider
    # This may fail closed if no provider is configured
    try:
        diagnosis_report = build_incident_diagnosis(
            case_file=case_file,
            llm=request.diagnosis_provider,  # type: ignore[arg-type]
            now=resolved_now,
        )
    except RuntimeError as exc:
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            error=f"Diagnosis provider error: {exc}",
        )

    # Step 4: Generate run IDs and emit started event
    # NOTE: run_id must use "auto-" prefix so find_latest_review_packet() can locate
    # the packet (it searches for "auto-{incident_id}-*" pattern)
    run_id = f"auto-{incident_id}-{resolved_now.strftime('%Y%m%d%H%M%S')}"
    collector_run_id = f"auto-{resolved_now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    # Emit diagnosis_loop_started event BEFORE orchestrator runs
    # This ensures Phase 4 sees loop_status != "not_run" even if subsequent steps fail
    store.mark_diagnosis_loop_started(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
    )

    # Step 5: Run one-pass orchestrator
    # Import LiveCommandGuard for golden-case mode
    handler_invocations: list[dict[str, Any]] = []
    orchestrator_result: dict[str, Any] = {}
    runner_result: dict[str, Any] = {}

    try:
        if request.use_live_command_guard:
            from .golden_case_one_pass_diagnosis_loop import LiveCommandGuard

            guard = LiveCommandGuard()
            with guard:
                orchestrator_result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=incident_id,
                    external_analysis_dir=request.external_analysis_dir,
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=run_id,
                    now=resolved_now,
                    fake_handlers=request.fake_handlers,
                )
        else:
            orchestrator_result = run_one_read_only_diagnosis_loop_pass(
                incident_id=incident_id,
                external_analysis_dir=request.external_analysis_dir,
                case_file=case_file,
                diagnosis_report=diagnosis_report,
                run_id=run_id,
                now=resolved_now,
                fake_handlers=request.fake_handlers,
            )

        # Extract ALL handler invocations from runner_result.results
        # Note: The runner puts golden_case_handler inside evidence dict
        # We must include ALL results (including unsafe/unknown) so enforcement
        # can reject false flags and unknown check IDs.
        runner_result_raw = orchestrator_result.get("runner_result")
        if isinstance(runner_result_raw, dict):
            runner_result = runner_result_raw
        results = runner_result.get("results", []) if isinstance(runner_result.get("results"), list) else []
        for result_item in results:
            if isinstance(result_item, dict):
                # Extract flags with explicit defaults (False for safety)
                evidence = result_item.get("evidence", {})
                golden_case_handler = bool(evidence.get("golden_case_handler")) if isinstance(evidence, dict) else False
                no_kubernetes_call = bool(evidence.get("no_kubernetes_call")) if isinstance(evidence, dict) else False
                # Append ALL results - enforcement will reject unsafe ones
                handler_invocations.append({
                    "check_id": result_item.get("check_id", ""),
                    "golden_case_handler": golden_case_handler,
                    "no_kubernetes_call": no_kubernetes_call,
                })

    except Exception as exc:
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            run_id=run_id,
            error=f"Orchestrator error: {exc}",
        )

    # Step 5: Extract diagnosis from report
    # Note: LLM provider returns PascalCase keys (Confidence, Summary, etc.)
    # We need to handle both PascalCase and camelCase for compatibility
    diagnosis = diagnosis_report.get("diagnosis", {})
    if not isinstance(diagnosis, dict):
        diagnosis = {"Summary": str(diagnosis), "Confidence": "unknown"}

    # Helper to get value with fallback between PascalCase and camelCase
    def get_diag(key: str, default: Any = None) -> Any:
        return diagnosis.get(key) or diagnosis.get(key.lower()) or diagnosis.get(key.capitalize()) or default

    # Step 6: Extract category from golden-case case file or manifest
    category = ""
    if request.golden_case_mode and request.golden_case_manifest:
        # For golden-case mode, extract category from the golden_case_source
        golden_case_source = case_file.get("golden_case_source", {})
        category = golden_case_source.get("category", "")
        if not category:
            category = request.golden_case_manifest.get("category", "")
    else:
        # For production mode, use candidate_class or empty
        category = getattr(incident, "candidate_class", "")

    # Step 7: Extract evidence refs from case file
    evidence_refs: list[str] = []
    evidence_links = case_file.get("evidence_links", [])
    if isinstance(evidence_links, list):
        evidence_refs = [str(ref) if isinstance(ref, str) else ref.get("path", "") for ref in evidence_links[:20]]

    # Step 8: Build next_checks from recommendations
    # Pass through check_id so orchestrator can match fake handlers
    next_checks: list[dict[str, Any]] = []
    recommended_raw: Any = get_diag("RecommendedInvestigations") or get_diag("recommended_investigations") or []
    recommended: list[Any] = recommended_raw if isinstance(recommended_raw, list) else []
    if isinstance(recommended, list):
        for item in recommended[:10]:
            if isinstance(item, dict):
                next_checks.append({
                    "check_id": item.get("check_id", ""),
                    "description": item.get("title", item.get("description", "")),
                    "owner": item.get("owner", "platform-engineer"),
                    "method": item.get("method", "kubectl describe pod <NAMESPACE>/<POD_NAME> -n <NAMESPACE>"),
                    "evidence_needed": item.get("evidence_needed", ["probe status", "container state"]),
                    "priority": item.get("priority", 5),
                    "risk_level": item.get("risk_level", "low"),
                    "read_only": item.get("read_only", True),
                    "source": item.get("source", "llm-review"),
                })

    # Step 9: Extract check counts
    runner_result_from_orchestrator = orchestrator_result.get("runner_result")
    checks_run = 0
    if runner_result_from_orchestrator and isinstance(runner_result_from_orchestrator, dict):
        checks_run = runner_result_from_orchestrator.get("checks_run", 0)

    # Step 10: Build root_cause from diagnosis
    root_cause = get_diag("RootCause") or diagnosis.get("root_cause", "")
    if not root_cause:
        likely_causes = get_diag("LikelyCauses") or get_diag("likely_causes") or []
        if isinstance(likely_causes, list) and likely_causes:
            root_cause = likely_causes[0] if isinstance(likely_causes[0], str) else str(likely_causes[0])
        else:
            root_cause = "unknown"

    # Extract other fields using helper
    confidence = get_diag("Confidence") or get_diag("confidence") or "unknown"
    summary = get_diag("Summary") or get_diag("summary") or ""

    # Step 11: Build diagnosis for artifact persistence
    service_diagnosis: dict[str, Any] = {
        "case_id": incident_id,
        "category": category,
        "root_cause": root_cause,
        "confidence": confidence,
        "description": summary,
        "evidence_refs": evidence_refs,
        "read_only": True,
        "allowed_actions": [],
        "forbidden_actions_observed": [],
        "mutation_proposals_observed": [],
        "decision": orchestrator_result.get("decision", ""),
        "checks_run": checks_run,
        "next_checks": next_checks,
    }

    # Step 12: Enforce safety using golden-case patterns
    is_safe, safety_errors = enforce_diagnosis_safety(service_diagnosis)
    if not is_safe:
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            run_id=run_id,
            error=f"Safety enforcement failed: {'; '.join(safety_errors)}",
        )

    # Step 13: Enforce fake-handler execution in golden-case mode
    # Fail closed: golden_case_mode requires fake_handlers for ACT-local proof path
    if request.golden_case_mode and request.enforce_fake_handlers:
        if not request.fake_handlers:
            return IncidentDiagnosisServiceResult(
                incident_id=incident_id,
                run_id=run_id,
                error="Fake-handler enforcement failed: golden_case_mode=True requires fake_handlers to be set. Missing fake handlers are not acceptable for the ACT-local proof path.",
            )
        try:
            enforce_fake_handlers(
                loop_result=orchestrator_result,
                runner_result_dict=runner_result if isinstance(runner_result, dict) else {},
                read_only_checks_sidecar={"handler_invocations": handler_invocations},
                fake_handlers=request.fake_handlers,
                enforce=True,
                allow_zero_checks=False,  # Require checks_run > 0 for ACT-local proof
            )
        except FakeHandlerExecutionError as exc:
            return IncidentDiagnosisServiceResult(
                incident_id=incident_id,
                run_id=run_id,
                error=f"Fake-handler enforcement failed: {exc}",
            )

    # Step 14: Persist review packet and emit completed event
    # This must happen BEFORE returning so Phase 4 sees persisted state
    review_packet_written = False
    review_packet_name: str | None = None

    # Compute provider proof fields early for error returns
    provider_configured, provider_invoked = get_provider_proof_fields(request.diagnosis_provider)

    # Get provider name for persistence
    provider_name: str | None = getattr(request.diagnosis_provider, "model_name", None)
    if provider_name is None:
        provider_name = getattr(request.diagnosis_provider, "name", None)

    try:
        # Write review packet for operator/ChatGPT review
        # This makes automatic_diagnosis_review.available=true in Phase 4
        review_packet_meta = write_diagnosis_review_packet(
            external_analysis_dir=request.external_analysis_dir,
            incident_id=incident_id,
            collector_run_id=collector_run_id,
            run_id=run_id,
            decision=str(orchestrator_result.get("decision", "")),
            checks_requested=0,  # Not available from orchestrator result
            checks_run=checks_run,
            checks_skipped=0,  # Not available from orchestrator result
            checks_rejected=0,  # Not available from orchestrator result
            eligible=True,
            eligibility_reason="service-initiated one-pass diagnosis",
            now=resolved_now,
            case_file=case_file,
            orchestrator_result=orchestrator_result,
            provider_configured=provider_configured,
            provider_invocation_attempted=provider_invoked,
            provider_name=provider_name,
        )
        if review_packet_meta.get("written"):
            review_packet_written = True
            review_packet_name = str(review_packet_meta.get("name")) if review_packet_meta.get("name") else None
    except Exception as exc:
        # Contract-critical: If review packet write fails, Phase 4 will fail.
        # Return error to avoid silent partial state.
        return IncidentDiagnosisServiceResult(
            incident_id=incident_id,
            run_id=run_id,
            error=f"Failed to persist diagnosis review packet: {exc}",
            provider_configured=provider_configured,
            provider_invocation_attempted=provider_invoked,
        )

    # Emit diagnosis_loop_completed event AFTER review packet write succeeds
    # This makes automatic_diagnosis_loop_summary.status="completed" in Phase 4
    # Only emit if review packet was written to avoid partial state
    if review_packet_written:
        store.mark_diagnosis_loop_completed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            review_packet_name=review_packet_name,
            checks_requested=0,
            checks_run=checks_run,
            checks_rejected=0,
        )

    # Step 15: Persist diagnosis artifact (legacy artifact, non-blocking)
    artifact_written = False
    artifact_name: str | None = None

    try:
        writer = request.artifact_writer
        if writer is not None:
            artifact_result = writer.write_diagnosis_artifact(
                output_dir=request.external_analysis_dir,
                incident_id=incident_id,
                diagnosis=service_diagnosis,
                now=resolved_now,
            )
            artifact_written = artifact_result.get("written", False)
            artifact_name = artifact_result.get("name")
    except Exception:
        # Artifact write failure is non-fatal
        pass

    return IncidentDiagnosisServiceResult(
        schema_version="1.0", incident_id=incident_id, run_id=run_id, category=category,
        root_cause=root_cause, confidence=confidence, description=summary,
        evidence_refs=evidence_refs, read_only=True, allowed_actions=[],
        forbidden_actions_observed=[], mutation_proposals_observed=[],
        decision=str(orchestrator_result.get("decision", "")), checks_run=checks_run,
        next_checks=next_checks, artifact_written=artifact_written,
        artifact_name=artifact_name, handler_invocations=handler_invocations,
        provider_configured=provider_configured, provider_invocation_attempted=provider_invoked,
    )
