"""Regression tests for K8s diagnosis phase module split.

These tests verify:
1. Module sizes are within LLM-friendly limits
2. Public imports are preserved for backward compatibility
3. The facade correctly delegates to sibling modules
"""

from __future__ import annotations

from pathlib import Path

MAX_LINES = 500  # LLM-friendly gate threshold
FACADE_MAX_LINES = 300  # Stricter limit for the main facade


class TestModuleSizes:
    """Test that split modules are within size limits."""

    def test_facade_is_within_llm_friendly_limit(self) -> None:
        """Facade should be under 500 lines to pass LLM-friendly gate."""
        path = Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_phase.py")
        assert path.exists(), f"Facade not found: {path}"
        line_count = len(path.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Facade has {line_count} lines, limit is {MAX_LINES}"

    def test_contract_module_is_llm_friendly(self) -> None:
        """Contract module should be under size limit."""
        path = Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_contract.py")
        assert path.exists(), f"Contract module not found: {path}"
        line_count = len(path.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Contract has {line_count} lines, limit is {MAX_LINES}"

    def test_runner_module_is_llm_friendly(self) -> None:
        """Runner module should be under size limit."""
        path = Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_runner.py")
        assert path.exists(), f"Runner module not found: {path}"
        line_count = len(path.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Runner has {line_count} lines, limit is {MAX_LINES}"

    def test_artifacts_module_is_llm_friendly(self) -> None:
        """Artifacts module should be under size limit."""
        path = Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_artifacts.py")
        assert path.exists(), f"Artifacts module not found: {path}"
        line_count = len(path.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Artifacts has {line_count} lines, limit is {MAX_LINES}"

    def test_render_module_is_llm_friendly(self) -> None:
        """Render module should be under size limit."""
        path = Path("scripts/k9b_otel_demo_lab_k8s_diagnosis_render.py")
        assert path.exists(), f"Render module not found: {path}"
        line_count = len(path.read_text().splitlines())
        assert line_count <= MAX_LINES, f"Render has {line_count} lines, limit is {MAX_LINES}"


class TestPublicImports:
    """Test that public imports are preserved for backward compatibility."""

    def test_phase_function_importable(self) -> None:
        """Main phase function should be importable from facade."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        assert callable(phase_p4c_verify_k8s_mult_pass_diagnosis)

    def test_create_initial_evidence_re_exported(self) -> None:
        """create_initial_evidence should be re-exported from facade."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            create_initial_evidence,
        )
        assert callable(create_initial_evidence)

    def test_run_diagnosis_loop_re_exported(self) -> None:
        """run_diagnosis_loop should be re-exported from facade."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            run_diagnosis_loop,
        )
        assert callable(run_diagnosis_loop)

    def test_write_diagnosis_evidence_re_exported(self) -> None:
        """write_diagnosis_evidence should be re-exported from facade."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            write_diagnosis_evidence,
        )
        assert callable(write_diagnosis_evidence)

    def test_get_diagnosis_dir_re_exported(self) -> None:
        """get_diagnosis_dir should be re-exported from facade."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            get_diagnosis_dir,
        )
        assert callable(get_diagnosis_dir)

    def test_contract_module_has_create_initial_evidence(self) -> None:
        """Contract module should have create_initial_evidence function."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_contract import (
            create_initial_evidence,
        )
        assert callable(create_initial_evidence)

    def test_runner_module_has_run_diagnosis_loop(self) -> None:
        """Runner module should have run_diagnosis_loop function."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            run_diagnosis_loop,
        )
        assert callable(run_diagnosis_loop)

    def test_artifacts_module_has_write_diagnosis_evidence(self) -> None:
        """Artifacts module should have write_diagnosis_evidence function."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_artifacts import (
            write_diagnosis_evidence,
        )
        assert callable(write_diagnosis_evidence)


class TestFacadeIntegration:
    """Test that facade correctly integrates sibling modules."""

    def test_evidence_creation(self) -> None:
        """create_initial_evidence should produce valid evidence dict."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_contract import (
            create_initial_evidence,
        )

        evidence = create_initial_evidence("test-namespace")

        # Check required fields exist
        assert "phase" in evidence
        assert "pass_count" in evidence
        assert "root_cause_summary" in evidence
        assert evidence["target_namespace"] == "test-namespace"
        assert evidence["pass_count"] == 0

    def test_diagnosis_dir_creation(self) -> None:
        """get_diagnosis_dir should create proper directory path."""
        import tempfile

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_artifacts import (
            get_diagnosis_dir,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            diagnosis_dir = get_diagnosis_dir(artifact_dir)

            assert diagnosis_dir.name == "p4c-k8s-multipass-diagnosis"
            assert diagnosis_dir.parent.name == "phase4-diagnosis"


class TestMergeDiagnosisResultTerminalFlags:
    """Regression tests for terminal no-checks flag merging.

    These tests ensure the bridge between runner phases and compute_p4c_outcome
    cannot regress by losing critical terminal decision metadata.
    """

    def test_merge_diagnosis_result_preserves_terminal_no_checks_flags(self) -> None:
        """Merge must preserve terminal_no_checks flags for compute_p4c_outcome.

        This is the exact bridge that was broken: runner set these flags but
        _merge_diagnosis_result() never copied them to evidence.
        """
        from typing import Any

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            _merge_diagnosis_result,
        )

        evidence: dict[str, Any] = {}
        result: dict[str, Any] = {
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": True,
            "premature_terminal_no_checks": True,
        }

        _merge_diagnosis_result(evidence, result)

        assert evidence["terminal_no_checks_accepted"] is True
        assert evidence["terminal_decision_reached"] is True
        assert evidence["premature_terminal_no_checks"] is True

    def test_p4c_phase_normalizes_premature_terminal_before_root_cause_failures(self) -> None:
        """Premature terminal must be normalized, not fall through to multipass.

        Given result has premature_terminal_no_checks=True and pass_count=1
        When merged and normalized under lab-strict min_required_passes=2
        Then mode is premature_terminal_no_checks, not multipass
        """
        from typing import Any

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            _merge_diagnosis_result,
        )

        # Simulate runner output with premature terminal
        evidence: dict[str, Any] = {}
        result: dict[str, Any] = {
            "status": "completed",
            "pass_count": 1,
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": True,
            "premature_terminal_no_checks": True,
            "real_pass_artifacts_found": True,
            "root_cause_summary": "Pod failed scheduling",
        }

        _merge_diagnosis_result(evidence, result)

        # Normalize with lab-strict settings
        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=True,
        )

        assert outcome.mode == "premature_terminal_no_checks"
        assert outcome.success is False
        assert outcome.root_cause_evidence_reason == (
            "premature_terminal_no_checks_before_required_passes"
        )
