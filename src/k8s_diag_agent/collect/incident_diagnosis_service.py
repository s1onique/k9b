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
- Request/response types for API seam
- Safety enforcement for mutation proposals and forbidden conclusions
- Fake-handler enforcement to ensure handlers are exercised
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from .golden_case_one_pass_enforcement import (
    FakeHandlerExecutionError,
    enforce_fake_handlers,
)
from .golden_case_one_pass_patterns import (
    _FORBIDDEN_CONCLUSION_PATTERNS,
    _MUTATION_PATTERNS,
)
from .incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)
from .incident_llm_diagnosis import (
    build_incident_diagnosis,
)
from .incident_read_only_check_runner import ReadOnlyCheckHandler

if TYPE_CHECKING:
    from .incident_case_file import build_incident_case_file


__all__ = [
    "DiagnosisProvider",
    "ArtifactWriter",
    "IncidentDiagnosisServiceResult",
    "IncidentOnePassServiceRequest",
    "run_incident_one_pass_diagnosis",
]


# =============================================================================
# Provider Protocols
# =============================================================================


class DiagnosisProvider(Protocol):
    """Protocol for LLM diagnosis provider injection.

    Tests inject a fake provider with this same interface.
    Production uses a real LLM provider (if configured).
    """

    def complete(self, prompt: str) -> str:
        """Generate completion for the given prompt.

        Args:
            prompt: The diagnosis prompt to complete.

        Returns:
            Raw model output as string.
        """
        ...


class ArtifactWriter(Protocol):
    """Protocol for diagnosis artifact writer injection.

    Tests inject a fake writer or use tempfile.
    Production uses the real artifact writer.
    """

    def write_diagnosis_artifact(
        self,
        output_dir: Path,
        incident_id: str,
        diagnosis: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Write diagnosis artifact and return metadata.

        Args:
            output_dir: Directory for output files
            incident_id: The incident ID
            diagnosis: The diagnosis result
            now: Current timestamp

        Returns:
            Dict with 'written' (bool) and optionally 'artifact_path' or 'error'
        """
        ...


# =============================================================================
# Fake/Default Providers
# =============================================================================


class NoOpDiagnosisProvider:
    """No-op diagnosis provider that fails closed.

    Used when no real LLM provider is configured.
    """

    def complete(self, prompt: str) -> str:
        """Fail closed - no diagnosis provider configured."""
        raise RuntimeError(
            "No diagnosis provider configured. "
            "Cannot run production diagnosis without LLM provider. "
            "Use a fake diagnosis provider for testing."
        )


class TempFileArtifactWriter:
    """Default artifact writer using temp files."""

    def write_diagnosis_artifact(
        self,
        output_dir: Path,
        incident_id: str,
        diagnosis: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Write diagnosis artifact to temp file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        diagnosis_path = output_dir / f"{incident_id}-diagnosis.json"
        try:
            with open(diagnosis_path, "w", encoding="utf-8") as f:
                json.dump(diagnosis, f, indent=2)
            return {
                "written": True,
                "artifact_path": str(diagnosis_path),
                "name": diagnosis_path.name,
            }
        except OSError as e:
            return {
                "written": False,
                "error": str(e),
            }


# =============================================================================
# Request/Response Types
# =============================================================================


@dataclass
class IncidentOnePassServiceRequest:
    """Request shape for incident one-pass diagnosis service.

    This is the internal service-level request, distinct from the HTTP API
    request in api_incident_diagnosis_loop.py.
    """

    incident_id: str
    external_analysis_dir: Path
    diagnosis_provider: DiagnosisProvider | None = None
    fake_handlers: dict[str, ReadOnlyCheckHandler] | None = None
    artifact_writer: ArtifactWriter | None = None
    now: datetime | None = None
    # Golden-case specific options
    golden_case_mode: bool = False
    golden_case_manifest: dict[str, Any] | None = None  # Required for golden_case_mode
    golden_case_case_dir: Path | None = None  # Required for golden_case_mode
    golden_case_evidence_provider: Any = None  # Required for golden_case_mode
    enforce_fake_handlers: bool = True
    use_live_command_guard: bool = True

    def __post_init__(self) -> None:
        # Default to no-op provider (fail-closed)
        if self.diagnosis_provider is None:
            self.diagnosis_provider = NoOpDiagnosisProvider()
        # Default to temp file writer
        if self.artifact_writer is None:
            self.artifact_writer = TempFileArtifactWriter()


@dataclass
class IncidentDiagnosisServiceResult:
    """Response shape for incident one-pass diagnosis service.

    This is the internal service-level response, distinct from the HTTP API
    response in api_incident_diagnosis_loop.py.
    """

    schema_version: str = "1.0"
    incident_id: str = ""
    run_id: str = ""
    category: str = ""
    root_cause: str = ""
    confidence: str = "unknown"
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    read_only: bool = True
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions_observed: list[str] = field(default_factory=list)
    mutation_proposals_observed: list[str] = field(default_factory=list)
    decision: str = ""
    checks_run: int = 0
    next_checks: list[dict[str, Any]] = field(default_factory=list)
    artifact_written: bool = False
    artifact_name: str | None = None
    error: str | None = None
    # Golden-case specific fields
    handler_invocations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "category": self.category,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "description": self.description,
            "evidence_refs": self.evidence_refs,
            "read_only": self.read_only,
            "allowed_actions": self.allowed_actions,
            "forbidden_actions_observed": self.forbidden_actions_observed,
            "mutation_proposals_observed": self.mutation_proposals_observed,
            "decision": self.decision,
            "checks_run": self.checks_run,
            "next_checks": self.next_checks,
            "artifact_written": self.artifact_written,
        }
        if self.artifact_name is not None:
            result["artifact_name"] = self.artifact_name
        if self.error is not None:
            result["error"] = self.error
        if self.handler_invocations:
            result["handler_invocations"] = self.handler_invocations
        return result


# =============================================================================
# Safety Enforcement (using golden-case patterns)
# =============================================================================


def _enforce_safety(diagnosis: dict[str, Any]) -> tuple[bool, list[str]]:
    """Enforce safety constraints on diagnosis output using golden-case patterns.

    Uses comprehensive forbidden conclusion patterns from golden_case_one_pass_patterns.py:
    - ImagePullBackOff, ErrImagePull (image pull failures)
    - PVC, PersistentVolumeClaim (storage failures)
    - FailedScheduling (scheduling failures)
    - registry auth failures
    - cnpg-operator failures

    Also checks for mutation proposals (kubectl apply, helm install, etc.)

    Args:
        diagnosis: The diagnosis result to validate

    Returns:
        Tuple of (is_safe, list of error messages)
    """
    errors: list[str] = []
    root_cause = str(diagnosis.get("root_cause", ""))
    description = str(diagnosis.get("description", ""))

    # Check forbidden conclusions in root cause
    for pattern_str, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.search(root_cause):
            errors.append(f"Forbidden conclusion in root_cause: '{label}'")
        if pattern.search(description):
            errors.append(f"Forbidden conclusion in description: '{label}'")

    # Check mutation proposals in description
    for pattern_str in _MUTATION_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.search(description):
            errors.append(f"Mutation proposal in description: '{pattern_str}'")

    # Check mutation proposals in next_checks methods
    next_checks = diagnosis.get("next_checks", [])
    if isinstance(next_checks, list):
        for i, check in enumerate(next_checks):
            if isinstance(check, dict):
                method = check.get("method", "")
                if method:
                    for pattern_str in _MUTATION_PATTERNS:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        if pattern.search(method):
                            errors.append(f"Mutation proposal in next_check[{i}].method: '{pattern_str}'")

    # Check read_only flag
    if not diagnosis.get("read_only", False):
        errors.append("Diagnosis must have read_only=True")

    # Check allowed_actions is empty
    if diagnosis.get("allowed_actions") != []:
        errors.append("Diagnosis must have allowed_actions=[]")

    return len(errors) == 0, errors


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

        case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=request.external_analysis_dir,
            now=resolved_now,
        )

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

    # Step 4: Run one-pass orchestrator
    run_id = f"service-{incident_id}-{resolved_now.strftime('%Y%m%d-%H%M%S')}"

    # Import LiveCommandGuard for golden-case mode
    handler_invocations: list[dict[str, Any]] = []
    orchestrator_result: dict[str, Any] = {}

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
        runner_result: dict[str, Any] = runner_result_raw if isinstance(runner_result_raw, dict) else {}
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
    runner_result = orchestrator_result.get("runner_result")
    checks_run = 0
    if runner_result and isinstance(runner_result, dict):
        checks_run = runner_result.get("checks_run", 0)

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
    is_safe, safety_errors = _enforce_safety(service_diagnosis)
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

    # Step 14: Persist diagnosis artifact
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

    decision_val = orchestrator_result.get("decision", "")
    return IncidentDiagnosisServiceResult(
        schema_version="1.0",
        incident_id=incident_id,
        run_id=run_id,
        category=category,
        root_cause=root_cause,
        confidence=confidence,
        description=summary,
        evidence_refs=evidence_refs,
        read_only=True,
        allowed_actions=[],
        forbidden_actions_observed=[],
        mutation_proposals_observed=[],
        decision=str(decision_val),
        checks_run=checks_run,
        next_checks=next_checks,
        artifact_written=artifact_written,
        artifact_name=artifact_name,
        handler_invocations=handler_invocations,
    )
