"""Type definitions for incident diagnosis service.

Extracts request/response types from incident_diagnosis_service.py
to keep that module under the 500-line limit.

Module organization:
- Protocol definitions for provider/writer injection
- Request/response dataclasses for API seam
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .incident_read_only_check_runner import ReadOnlyCheckHandler


__all__ = [
    "DiagnosisProvider",
    "ArtifactWriter",
    "TempFileArtifactWriter",
    "IncidentOnePassServiceRequest",
    "IncidentDiagnosisServiceResult",
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
# Request/Response Types
# =============================================================================


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
        import json
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
        from .diagnosis_provider_proof import NoOpDiagnosisProvider
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
    # Provider proof fields for live-lab smoke testing
    # Set to True when a real (non-NoOp) provider was invoked
    provider_configured: bool = False
    provider_invocation_attempted: bool = False

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
            # Provider proof fields for live-lab smoke testing
            "provider_configured": self.provider_configured,
            "provider_invocation_attempted": self.provider_invocation_attempted,
        }
        if self.artifact_name is not None:
            result["artifact_name"] = self.artifact_name
        if self.error is not None:
            result["error"] = self.error
        if self.handler_invocations:
            result["handler_invocations"] = self.handler_invocations
        return result
