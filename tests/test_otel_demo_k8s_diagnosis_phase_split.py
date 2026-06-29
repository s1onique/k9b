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
