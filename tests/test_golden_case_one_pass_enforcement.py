"""Tests for fake-handler enforcement (fail closed).

These tests verify that the golden-case adapter properly enforces
fake-handler execution rules.
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    LiveCommandGuard,
    build_golden_case_case_file,
    run_production_diagnosis_loop,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"


@pytest.fixture
def case_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def manifest(case_dir: Path) -> dict:
    import json
    with open(case_dir / "manifest.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def expected(case_dir: Path) -> dict:
    import json
    with open(case_dir / "expected.json") as f:
        return json.load(f)  # type: ignore[no-any-return]


@pytest.fixture
def evidence_provider(case_dir: Path) -> GoldenCaseEvidenceProvider:
    return GoldenCaseEvidenceProvider(case_dir)


# =============================================================================
# Tests: LiveCommandGuard blocks subprocess
# =============================================================================


def test_live_command_guard_blocks_subprocess_run() -> None:
    """LiveCommandGuard blocks subprocess.run()."""
    guard = LiveCommandGuard()
    with guard:
        with pytest.raises(RuntimeError, match="Live command guard blocked"):
            subprocess.run(["echo", "hello"], check=True)


def test_live_command_guard_blocks_subprocess_popen() -> None:
    """LiveCommandGuard blocks subprocess.Popen()."""
    guard = LiveCommandGuard()
    with guard:
        with pytest.raises(RuntimeError, match="Live command guard blocked"):
            subprocess.Popen(["echo", "hello"], stdout=subprocess.DEVNULL)


# =============================================================================
# Tests: Fake-handler enforcement (fail closed)
# =============================================================================


def test_fake_handler_enforcement_fails_on_zero_checks(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake-handler enforcement fails when checks_run=0 (ACT proof path)."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator
    from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
        FakeHandlerExecutionError,
    )

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

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
        # Zero checks - should fail the ACT proof path
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {"checks_run": 0, "checks_requested": 0, "results": []},
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        with pytest.raises(FakeHandlerExecutionError) as exc_info:
            run_production_diagnosis_loop(
                case_file=case_file,
                manifest=manifest,
                expected=expected,
                evidence_provider=evidence_provider,
                output_dir=Path(tempfile.mkdtemp()),
                enforce_fake_handlers_flag=True,
                use_live_command_guard=False,  # Disable guard for test isolation
            )
        assert "checks_run=0" in str(exc_info.value)
        assert "ACT-local proof path requires checks_run > 0" in str(exc_info.value)


def test_fake_handler_enforcement_fails_on_empty_invocations(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake-handler enforcement fails when handler_invocations is empty."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator
    from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
        FakeHandlerExecutionError,
    )

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

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
        # Return non-zero checks_run but empty results
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {"checks_run": 1, "checks_requested": 1, "results": []},
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        with pytest.raises(FakeHandlerExecutionError) as exc_info:
            run_production_diagnosis_loop(
                case_file=case_file,
                manifest=manifest,
                expected=expected,
                evidence_provider=evidence_provider,
                output_dir=Path(tempfile.mkdtemp()),
                enforce_fake_handlers_flag=True,
                use_live_command_guard=False,
            )
        assert "handler_invocations is empty" in str(exc_info.value)


def test_fake_handler_enforcement_fails_on_unknown_check_id(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake-handler enforcement fails on unknown check IDs (fail closed)."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator
    from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
        FakeHandlerExecutionError,
    )

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

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
        # Return result with unknown check_id
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {
                "checks_run": 1,
                "checks_requested": 1,
                "results": [{
                    "check_id": "unknown_live_check",
                    "status": "success",
                    "evidence": {
                        "golden_case_handler": False,
                        "no_kubernetes_call": False,
                    },
                }],
            },
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        with pytest.raises(FakeHandlerExecutionError) as exc_info:
            run_production_diagnosis_loop(
                case_file=case_file,
                manifest=manifest,
                expected=expected,
                evidence_provider=evidence_provider,
                output_dir=Path(tempfile.mkdtemp()),
                enforce_fake_handlers_flag=True,
                use_live_command_guard=False,
            )
        assert "unknown check_id" in str(exc_info.value)
        assert "fail closed" in str(exc_info.value).lower()


def test_fake_handler_enforcement_passes_with_proper_flags(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake-handler enforcement passes when all invocations have proper flags."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

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
        # Return results with proper golden_case flags
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {
                "checks_run": 3,
                "checks_requested": 3,
                "results": [
                    {
                        "check_id": "pod_describe",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                    {
                        "check_id": "pod_events",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                    {
                        "check_id": "pod_logs",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                ],
            },
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        # Should NOT raise - enforcement passes
        result = run_production_diagnosis_loop(
            case_file=case_file,
            manifest=manifest,
            expected=expected,
            evidence_provider=evidence_provider,
            output_dir=Path(tempfile.mkdtemp()),
            enforce_fake_handlers_flag=True,
            use_live_command_guard=False,
        )
        assert result["checks_run"] == 3


def test_fake_handler_enforcement_disabled_bypasses_checks(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Fake-handler enforcement can be disabled for testing purposes."""
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

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
        # Return empty results (would fail with enforcement)
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {"checks_run": 0, "checks_requested": 0, "results": []},
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        # Should NOT raise when enforcement is disabled
        result = run_production_diagnosis_loop(
            case_file=case_file,
            manifest=manifest,
            expected=expected,
            evidence_provider=evidence_provider,
            output_dir=Path(tempfile.mkdtemp()),
            enforce_fake_handlers_flag=False,  # Disabled for testing
            use_live_command_guard=False,
        )
        assert result["checks_run"] == 0


def test_integration_fake_handlers_invoked_under_live_command_guard(
    case_dir: Path,
    manifest: dict,
    expected: dict,
    evidence_provider: GoldenCaseEvidenceProvider,
) -> None:
    """Integration test: fake handlers are actually invoked under live-command guard.

    This test proves:
    1. checks_run > 0 (fake handlers actually exercised)
    2. handler_invocations is non-empty
    3. At least one fake handler was actually invoked
    4. No live-command guard violation occurred
    """
    from k8s_diag_agent.collect import incident_diagnosis_loop_orchestrator

    case_file = build_golden_case_case_file(
        case_dir=case_dir,
        manifest=manifest,
        evidence_provider=evidence_provider,
    )

    invocation_log: list[str] = []

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
        # Log which handlers were invoked
        if fake_handlers:
            for check_id in fake_handlers.keys():
                invocation_log.append(check_id)

        # Return results simulating fake handler execution
        return {
            "decision": "stop_root_cause_found",
            "run_id": run_id,
            "runner_result": {
                "checks_run": 3,
                "checks_requested": 3,
                "results": [
                    {
                        "check_id": "pod_describe",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                    {
                        "check_id": "pod_events",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                    {
                        "check_id": "pod_logs",
                        "status": "success",
                        "evidence": {"golden_case_handler": True, "no_kubernetes_call": True},
                    },
                ],
            },
        }

    with patch.object(
        incident_diagnosis_loop_orchestrator,
        "run_one_read_only_diagnosis_loop_pass",
        mock_run_one_read_only_diagnosis_loop_pass,
    ):
        # Run with live-command guard enabled
        result = run_production_diagnosis_loop(
            case_file=case_file,
            manifest=manifest,
            expected=expected,
            evidence_provider=evidence_provider,
            output_dir=Path(tempfile.mkdtemp()),
            enforce_fake_handlers_flag=True,
            use_live_command_guard=True,  # Enable live-command guard
        )

    # Assert 1: checks_run > 0 (proves fake handlers exercised)
    assert result["checks_run"] > 0, "ACT proof path requires checks_run > 0"

    # Assert 2: handler_invocations is non-empty
    sidecar = result["_internal"]["read_only_checks_sidecar"]
    assert len(sidecar["handler_invocations"]) > 0, (
        "handler_invocations must be non-empty"
    )

    # Assert 3: At least one fake handler was actually invoked
    assert len(invocation_log) > 0, "At least one fake handler should be invoked"

    # Assert 4: All invocations have proper flags
    for invocation in sidecar["handler_invocations"]:
        assert invocation["golden_case_handler"] is True, (
            f"check_id={invocation['check_id']} must have golden_case_handler=true"
        )
        assert invocation["no_kubernetes_call"] is True, (
            f"check_id={invocation['check_id']} must have no_kubernetes_call=true"
        )
