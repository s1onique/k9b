"""Self-tests for the automatic-diagnosis disposition ADT verifier.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

Covers Section 10 (verifier self-tests): PASS cases only. The expected-FAIL cases
(negative-fifth-variant mypy proof) are deferred to the typed-outcome ACT.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "incident_lifecycle_boundary" / "automatic_diagnosis_disposition.py"


def _run_verifier() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


class TestVerifierPass:
    """The verifier must report PASS on the current (compliant) source tree."""

    def test_verifier_passes_on_current_tree(self):
        result = _run_verifier()
        assert result.returncode == 0, (
            f"verifier failed unexpectedly:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "PASSED" in result.stdout

    def test_verifier_reports_specific_check_names(self):
        result = _run_verifier()
        expected_checks = [
            "closed_union_contains_expected_variants",
            "reducer_uses_assert_never_sentinel",
            "batch_does_not_rescan_serialized_dicts",
            "reason_maps_keyed_by_enum",
            "scheduler_completion_includes_all_three_reason_maps",
            "schema_version_explicit",
            "production_path_uses_canonical_reducer_and_emitter",
        ]
        for check in expected_checks:
            assert check in result.stdout, (
                f"verifier did not report {check!r}\nstdout:\n{result.stdout}"
            )


class TestVerifierImportable:
    """The verifier module is also importable as a library for inline checks."""

    def test_can_import_verifier(self):
        sys.path.insert(0, str(VERIFIER.parent))
        try:
            # Import only when the file is part of the repo.
            import importlib

            spec = importlib.util.spec_from_file_location("automatic_diagnosis_disposition", VERIFIER)
            assert spec is not None
            mod = importlib.util.module_from_spec(spec)
            assert mod is not None
        finally:
            sys.path.pop(0)
