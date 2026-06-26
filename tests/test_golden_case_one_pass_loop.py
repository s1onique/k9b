"""Tests for golden-case one-pass diagnosis loop adapter.

These tests verify the production loop wiring with golden-case fixtures.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    GoldenCaseDeterministicLLMProvider,
    build_golden_case_case_file,
    enforce_safety,
    run_production_diagnosis_loop,
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


def test_build_golden_case_case_file_structure(
    case_dir: Path,
    manifest: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Golden-case bundle converts into production case-file shape."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

    assert "schema_version" in case_file
    assert "incident" in case_file
    assert "signals" in case_file
    assert "events" in case_file
    assert "evidence_links" in case_file
    assert case_file["read_only"] is True
    assert case_file["allowed_actions"] == []
    assert "mutate_cluster" in case_file["disallowed_actions"]

    incident = case_file["incident"]
    assert incident["incident_id"] == manifest["case_id"]
    assert incident["object_kind"] == "Pod"
    assert incident["object_name"] == manifest["fixture_name"]
    assert incident["namespace"] == manifest["fixture_namespace"]

    assert "golden_case_source" in case_file
    assert case_file["golden_case_source"]["case_id"] == manifest["case_id"]


def test_build_golden_case_case_file_bounds_events(
    case_dir: Path,
    manifest: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Case-file events are bounded."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )
    assert len(case_file["events"]) <= 50


def test_fake_handlers_provided_to_orchestrator(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake handlers are passed into the orchestrator."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator
    from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
        run_production_diagnosis_loop,
    )

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

    captured_handlers: dict = {}

    def mock_run_one_read_only_diagnosis_loop_pass(
        incident_id: str,
        external_analysis_dir: Path,
        case_file: dict,
        diagnosis_report: dict,
        run_id: str,
        prior_loop_state: dict | None = None,
        now: datetime | None = None,
        fake_handlers: dict | None = None,
    ) -> dict:
        captured_handlers["handlers"] = fake_handlers
        # Return actual fake handler results with proper flags
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {
                "checks_run": 1,
                "checks_requested": 1,
                "results": [{
                    "check_id": "pod_describe",
                    "status": "success",
                    "evidence": {
                        "golden_case_handler": True,
                        "no_kubernetes_call": True,
                        "observations": [],
                    },
                }],
            },
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        run_production_diagnosis_loop(
            case_file=case_file,
            manifest=manifest,
            expected=expected,
            evidence_provider=evidence_provider,
            output_dir=Path(tempfile.mkdtemp()),
            enforce_fake_handlers_flag=True,
        )

    assert "handlers" in captured_handlers
    assert captured_handlers["handlers"] is not None
    expected_handler_ids = ["pod_describe", "pod_events", "pod_logs", "deployment_status", "node_status", "service_endpoints"]
    assert all(h in captured_handlers["handlers"] for h in expected_handler_ids)


def test_production_loop_returns_handler_invocation_evidence(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Production loop returns evidence of handler invocations."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

    result = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=Path(tempfile.mkdtemp()),
    )

    assert "_internal" in result
    assert "read_only_checks_sidecar" in result["_internal"]
    sidecar = result["_internal"]["read_only_checks_sidecar"]
    assert "handler_invocations" in sidecar
    assert "checks_run" in sidecar
    assert "safety_metadata" in sidecar


def test_no_live_command_runner_imported() -> None:
    """Verify no live command runner is imported."""
    import k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop as module
    module_dict = dir(module)
    forbidden_imports = ["kubernetes", "subprocess", "kubectl", "helm", "docker"]
    for forbidden in forbidden_imports:
        assert forbidden not in module_dict, f"Module should not import {forbidden}"


def test_enforce_safety_rejects_mutation_proposals() -> None:
    """Safety enforcement rejects mutation proposals."""
    diagnosis = {
        "root_cause": "readiness probe failure",
        "description": "Try kubectl apply to fix this",
        "read_only": True,
        "forbidden_actions_observed": [],
        "mutation_proposals_observed": [],
        "next_checks": [],
    }
    is_safe, errors = enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Mutation proposal" in e for e in errors)


def test_enforce_safety_rejects_forbidden_conclusions() -> None:
    """Safety enforcement rejects forbidden conclusions."""
    diagnosis = {
        "root_cause": "ImagePullBackOff",
        "description": "Image pull failure",
        "read_only": True,
        "forbidden_actions_observed": [],
        "mutation_proposals_observed": [],
        "next_checks": [],
    }
    is_safe, errors = enforce_safety(diagnosis)
    assert is_safe is False
    assert any("Forbidden conclusion" in e for e in errors)


def test_enforce_safety_accepts_correct_diagnosis(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Safety enforcement accepts correct golden-case diagnosis."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )
    result = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=Path(tempfile.mkdtemp()),
    )
    is_safe, errors = enforce_safety(result)
    assert is_safe is True, f"Safety errors: {errors}"


def test_deterministic_llm_provider_returns_correct_diagnosis(
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Deterministic provider returns correct readiness probe failure diagnosis.
    
    Note: Returns 'medium' confidence intentionally to allow planner to run checks.
    This proves the ACT requirement that fake handlers are exercised.
    High confidence would cause early stop without running checks.
    """
    provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )
    result = provider.complete("test prompt")
    parsed = json.loads(result)
    assert parsed["confidence"] == "medium"
    assert "readiness probe" in parsed["summary"].lower()


def test_diagnosis_output_contract(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Diagnosis output matches required contract."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )
    result = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=Path(tempfile.mkdtemp()),
    )

    required_fields = [
        "case_id", "category", "root_cause", "confidence", "description",
        "evidence_refs", "read_only", "allowed_actions", "forbidden_actions_observed",
        "mutation_proposals_observed", "diagnosis_engine", "next_checks",
    ]
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    assert result["category"] == "readiness_probe_failure"
    assert "readiness probe" in result["root_cause"].lower()
    assert result["read_only"] is True
    assert result["allowed_actions"] == []
    assert result["forbidden_actions_observed"] == []
    assert result["mutation_proposals_observed"] == []


def test_diagnosis_output_includes_evidence_refs(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Diagnosis output includes all expected evidence refs."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )
    result = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=Path(tempfile.mkdtemp()),
    )
    expected_files = manifest["expected_evidence_files"]
    assert result["evidence_refs"] == expected_files


def test_diagnosis_output_next_checks_are_read_only(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Next checks use only read-only kubectl commands."""
    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )
    result = run_production_diagnosis_loop(
        case_file=case_file,
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
        output_dir=Path(tempfile.mkdtemp()),
    )
    allowed_prefixes = ["kubectl get", "kubectl describe", "kubectl logs", "kubectl top"]
    for check in result.get("next_checks", []):
        method = check.get("method", "")
        assert any(method.startswith(prefix) for prefix in allowed_prefixes), f"Non-read-only method: {method}"
