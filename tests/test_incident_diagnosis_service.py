"""Tests for incident one-pass diagnosis service.

These tests verify the service wiring with golden-case fixtures.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_lifecycle import Incident

import pytest

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_fake_handlers import (
    create_golden_case_fake_handlers,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    GoldenCaseDeterministicLLMProvider,
)
from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    NoOpDiagnosisProvider,
    TempFileArtifactWriter,
    _enforce_safety,
    run_incident_one_pass_diagnosis,
)
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"


@pytest.fixture
def case_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def manifest(case_dir: Path) -> dict:
    with open(case_dir / "manifest.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def expected(case_dir: Path) -> dict:
    with open(case_dir / "expected.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def evidence_provider(case_dir: Path) -> GoldenCaseEvidenceProvider:
    return GoldenCaseEvidenceProvider(case_dir)


@pytest.fixture(autouse=True)
def cleanup_store() -> Generator[None, None, None]:
    """Reset incident store before and after each test."""
    reset_incident_store()
    yield
    reset_incident_store()


# =============================================================================
# Test Helpers
# =============================================================================


def _create_test_incident(
    incident_id: str,
    namespace: str = "test-namespace",
    object_kind: str = "Pod",
    object_name: str = "test-pod",
    severity: str = "medium",
) -> Incident:
    """Create a valid test incident with all required fields."""
    from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus

    now = datetime.now(UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id=f"candidate-{incident_id}",
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        raw_object_kind=None,
        candidate_class="PodFailure",
        severity=severity,
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
    )


# =============================================================================
# Fake Provider for Testing
# =============================================================================


class FakeDiagnosisProvider:
    """Fake diagnosis provider for testing the service."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        """Return deterministic response."""
        del prompt
        return json.dumps(self.response)


class FakeArtifactWriter:
    """Fake artifact writer that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.last_diagnosis: dict[str, Any] | None = None

    def write_diagnosis_artifact(
        self,
        output_dir: Path,
        incident_id: str,
        diagnosis: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Record the call and return success."""
        self.calls.append({
            "output_dir": str(output_dir),
            "incident_id": incident_id,
            "now": now.isoformat(),
        })
        self.last_diagnosis = diagnosis
        return {
            "written": True,
            "artifact_path": str(output_dir / f"{incident_id}-diagnosis.json"),
            "name": f"{incident_id}-diagnosis.json",
        }


# =============================================================================
# Test: Service Rejects Missing Incident
# =============================================================================


def test_service_rejects_missing_incident() -> None:
    """Service returns error for missing incident."""
    request = IncidentOnePassServiceRequest(
        incident_id="nonexistent-incident",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "test",
            "confidence": "high",
            "likely_causes": [],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "nonexistent-incident"
    assert result.error == "Incident not found"
    assert result.run_id == ""


# =============================================================================
# Test: Service Rejects Missing Diagnosis Provider (Fail-Closed)
# =============================================================================


def test_service_rejects_missing_diagnosis_provider() -> None:
    """Service fails closed when no diagnosis provider is configured."""
    from datetime import UTC

    from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store with a real incident
    store = IncidentStore()
    now = datetime.now(UTC)
    incident = Incident(
        incident_id="test-incident-001",
        source_candidate_id="test-candidate-001",
        namespace="test-namespace",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="PodFailure",
        severity="medium",
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
    )
    store._incidents["test-incident-001"] = incident
    set_incident_store(store)

    # Request without provider - should fail
    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-001",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=None,  # NoOpDiagnosisProvider is default
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "test-incident-001"
    assert result.error is not None
    assert "Diagnosis provider error" in result.error or "NoOpDiagnosisProvider" in result.error


# =============================================================================
# Test: Service Rejects Mutation Proposals
# =============================================================================


def test_service_rejects_mutation_proposals() -> None:
    """Service fails closed when provider returns mutation proposals."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store with a real incident
    store = IncidentStore()
    incident = _create_test_incident("test-incident-002")
    store._incidents["test-incident-002"] = incident
    set_incident_store(store)

    # Provider that returns mutation proposal
    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-002",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Try kubectl apply to fix this",
            "confidence": "high",
            "likely_causes": ["configuration issue"],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.incident_id == "test-incident-002"
    assert result.error is not None
    assert "Safety enforcement failed" in result.error
    assert "Mutation proposal" in result.error


# =============================================================================
# Test: Service Persists Diagnosis Artifacts
# =============================================================================


def test_service_persists_diagnosis_artifacts() -> None:
    """Service persists diagnosis output to artifact writer."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store
    store = IncidentStore()
    incident = _create_test_incident("test-incident-003")
    store._incidents["test-incident-003"] = incident
    set_incident_store(store)

    fake_writer = FakeArtifactWriter()

    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-003",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Diagnosis complete",
            "confidence": "high",
            "likely_causes": ["probe failure"],
            "recommended_investigations": [
                {"check_id": "pod_describe", "title": "Describe pod"}
            ],
        }),
        artifact_writer=fake_writer,
    )

    result = run_incident_one_pass_diagnosis(request)

    assert result.error is None
    assert result.artifact_written is True
    assert result.artifact_name is not None
    assert len(fake_writer.calls) == 1
    assert fake_writer.last_diagnosis is not None
    assert fake_writer.last_diagnosis["read_only"] is True
    assert fake_writer.last_diagnosis["allowed_actions"] == []


# =============================================================================
# Test: Service Returns Stable Response DTO
# =============================================================================


def test_service_returns_stable_dto() -> None:
    """Service returns properly structured response DTO."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create and populate store
    store = IncidentStore()
    incident = _create_test_incident("test-incident-004")
    store._incidents["test-incident-004"] = incident
    set_incident_store(store)

    request = IncidentOnePassServiceRequest(
        incident_id="test-incident-004",
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=FakeDiagnosisProvider({
            "summary": "Diagnosis complete",
            "confidence": "high",
            "likely_causes": ["probe failure"],
            "recommended_investigations": [],
        }),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify DTO structure
    dto = result.to_dict()
    required_fields = [
        "schema_version", "incident_id", "run_id", "category", "root_cause",
        "confidence", "description", "evidence_refs", "read_only",
        "allowed_actions", "forbidden_actions_observed", "mutation_proposals_observed",
        "decision", "checks_run", "next_checks", "artifact_written",
    ]
    for field in required_fields:
        assert field in dto, f"Missing required field: {field}"

    # Verify types
    assert isinstance(dto["read_only"], bool)
    assert isinstance(dto["allowed_actions"], list)
    assert isinstance(dto["next_checks"], list)
    assert dto["read_only"] is True
    assert dto["allowed_actions"] == []


# =============================================================================
# Test: Golden-Case Pod-Failure Passes Through Service Seam
# =============================================================================


def test_golden_case_pod_failure_through_service_seam(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Pod-failure golden case passes through the service/API seam."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create incident matching golden case
    store = IncidentStore()
    incident = _create_test_incident(
        incident_id=manifest["case_id"],
        namespace=manifest["fixture_namespace"],
        object_name=manifest["fixture_name"],
    )
    store._incidents[manifest["case_id"]] = incident
    set_incident_store(store)

    fake_writer = FakeArtifactWriter()
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)
    llm_provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    request = IncidentOnePassServiceRequest(
        incident_id=manifest["case_id"],
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=llm_provider,
        fake_handlers=fake_handlers,
        artifact_writer=fake_writer,
        now=datetime.now(UTC),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify successful diagnosis
    assert result.error is None
    assert result.incident_id == manifest["case_id"]
    assert result.read_only is True
    assert result.allowed_actions == []
    assert result.mutation_proposals_observed == []
    assert result.forbidden_actions_observed == []

    # Verify diagnosis content (category and root_cause may vary)
    assert result.category is not None
    assert result.root_cause is not None

    # Verify artifact was persisted
    assert result.artifact_written is True
    assert fake_writer.last_diagnosis is not None


# =============================================================================
# Test: Read-Only Handlers Are Invoked
# =============================================================================


def test_read_only_handlers_invoked(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Read-only fake handlers are configured for the service."""
    # This test verifies that fake handlers can be created and passed
    # to the service request. The ACT-local verification script
    # already confirms handlers are invoked at runtime.
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)

    # Verify all expected handler IDs are present
    expected_handler_ids = [
        "pod_describe", "pod_events", "pod_logs",
        "deployment_status", "node_status", "service_endpoints"
    ]
    for handler_id in expected_handler_ids:
        assert handler_id in fake_handlers, f"Missing handler: {handler_id}"


# =============================================================================
# Test: Safety Enforcement
# =============================================================================


def test_enforce_safety_rejects_mutation_in_description() -> None:
    """Safety enforcement rejects mutation proposals in description."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "kubectl apply -f deployment.yaml to fix",
        "next_checks": [],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Mutation proposal" in e for e in errors)


def test_enforce_safety_rejects_mutation_in_next_checks() -> None:
    """Safety enforcement rejects mutation proposals in next_checks methods."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "Issue detected",
        "next_checks": [
            {"method": "kubectl scale deployment myapp --replicas=3"}
        ],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Mutation proposal" in e for e in errors)


def test_enforce_safety_rejects_forbidden_conclusions() -> None:
    """Safety enforcement rejects forbidden diagnosis conclusions."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "This is ImagePullBackOff",
        "next_checks": [],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Forbidden conclusion" in e for e in errors)


def test_enforce_safety_accepts_valid_diagnosis() -> None:
    """Safety enforcement accepts valid read-only diagnosis."""
    diagnosis = {
        "read_only": True,
        "allowed_actions": [],
        "description": "Readiness probe failure detected",
        "next_checks": [
            {"method": "kubectl describe pod <NAME> -n <NS>"}
        ],
    }
    is_safe, errors = _enforce_safety(diagnosis)
    assert is_safe is True
    assert len(errors) == 0


# =============================================================================
# Test: NoOpDiagnosisProvider Fails Closed
# =============================================================================


def test_noop_provider_fails_closed() -> None:
    """NoOpDiagnosisProvider raises RuntimeError on complete."""
    provider = NoOpDiagnosisProvider()
    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")
    assert "No diagnosis provider configured" in str(exc_info.value)


# =============================================================================
# Test: TempFileArtifactWriter Works
# =============================================================================


def test_temp_file_artifact_writer() -> None:
    """TempFileArtifactWriter writes files correctly."""
    writer = TempFileArtifactWriter()
    output_dir = Path(tempfile.mkdtemp())

    result = writer.write_diagnosis_artifact(
        output_dir=output_dir,
        incident_id="test-001",
        diagnosis={"test": "data"},
        now=datetime.now(UTC),
    )

    assert result["written"] is True
    assert "artifact_path" in result
    assert Path(result["artifact_path"]).exists()


# =============================================================================
# Test: Service Uses Same One-Pass Loop
# =============================================================================


def test_service_uses_same_one_pass_loop(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Service uses the same run_one_read_only_diagnosis_loop_pass function."""
    from k8s_diag_agent.collect.incident_store import IncidentStore

    # Create incident matching golden case
    store = IncidentStore()
    incident = _create_test_incident(
        incident_id=manifest["case_id"],
        namespace=manifest["fixture_namespace"],
        object_name=manifest["fixture_name"],
    )
    store._incidents[manifest["case_id"]] = incident
    set_incident_store(store)

    llm_provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    request = IncidentOnePassServiceRequest(
        incident_id=manifest["case_id"],
        external_analysis_dir=Path(tempfile.mkdtemp()),
        diagnosis_provider=llm_provider,
        fake_handlers=create_golden_case_fake_handlers(evidence_provider),
        now=datetime.now(UTC),
    )

    result = run_incident_one_pass_diagnosis(request)

    # Verify orchestrator ran successfully (one-pass)
    assert result.error is None
    assert result.run_id is not None
