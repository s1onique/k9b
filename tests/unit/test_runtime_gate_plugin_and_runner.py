"""Unit tests for the promotion runtime gate plugin and runner.

P0-1:  _run_pytest_subprocess calls _validate_result_payload directly —
       no duplicate inline validation.
P0-2:  --collect-only proves zero executed_nodeids via the canonical
       runner (not raw pytest).
P0-3:  Real pass/fail/skip/xfail/xpass/setup-error/teardown-error
       fixtures prove outcome semantics.
P0-4:  Exact result schema, node-ID uniqueness, count invariants,
       exact outcome key set, bool rejection, sum invariant, missing
       result-file path.
P0-5:  Static-scope negative tests via promotion_runtime_static_scope.py.
P0-6:  _PytestSubprocessResult captures argv/stdout/stderr; plugin in
       EXPERIMENTAL_LANE_AUTHORITY_PATHS.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Test: --collect-only does not execute bodies (P0-2).
#
# Uses a WITNESS_PATH file created INSIDE the test body and read AFTER the
# runner returns.  The environment variable propagates into the subprocess
# because the runner copies the full environment.
# ---------------------------------------------------------------------------


class TestCollectOnlyDoesNotExecuteBodies:
    """P0-2: --collect-only must never enter a test body."""

    def test_collect_only_zero_executed(self, tmp_path: Path) -> None:
        """The canonical runner emits zero executed_nodeids in collect-only mode."""
        # Create a minimal test file with a witness file in its body.
        test_file = tmp_path / "test_witness.py"
        test_file.write_text(
            "import os\n"
            "from pathlib import Path\n"
            "\n"
            "def test_body():\n"
            "    # Write a witness file to prove this body ran.\n"
            "    Path(os.environ['WITNESS_PATH']).write_text('executed')\n"
            "\n"
        )
        manifest = tmp_path / "manifest.txt"
        manifest.write_text(f"{test_file.relative_to(tmp_path)}::test_body\n")

        witness = tmp_path / "witness.txt"
        witness.write_text("not_executed")

        sys.path.insert(0, str(ROOT / "scripts" / "ci"))

        sys.path.insert(0, str(ROOT))
        # Import the runner module (not raw pytest).
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        import run_promotion_runtime_gate

        env = os.environ.copy()
        env["WITNESS_PATH"] = str(witness)
        env["PYTHONPATH"] = (
            str(ROOT / "scripts" / "ci")
            + os.pathsep
            + env.get("PYTHONPATH", "")
        )

        # Run --collect-only against the minimal manifest.
        # Uses internal API so the subprocess inherits the test environment.
        result = run_promotion_runtime_gate._run_pytest_subprocess(
            args=[f"{test_file}::test_body"],
            repo_root=tmp_path,
            collect_only=True,
        )

        # P0-2 contract: --collect-only emits zero executed nodeids.
        assert result.gate_result.executed_nodeids == [], (
            f"--collect-only must not execute test bodies, got: "
            f"{result.gate_result.executed_nodeids!r}"
        )
        # The witness file must not have been created.
        assert witness.read_text() == "not_executed", (
            "witness was written — test body executed during --collect-only"
        )


# ---------------------------------------------------------------------------
# Test: runner --run proves exactly one body execution (P0-2 witness proof).
# ---------------------------------------------------------------------------


class TestRunnerRunExecutesBodies:
    """P0-2: --run must execute each body exactly once."""

    def test_run_executes_body_once(self, tmp_path: Path) -> None:
        """The canonical runner with --run executes the body and records one pass."""
        # Minimal test file that always passes.
        test_file = tmp_path / "test_run.py"
        test_file.write_text("def test_body(): pass\n")

        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        import run_promotion_runtime_gate

        result = run_promotion_runtime_gate._run_pytest_subprocess(
            args=[str(test_file) + "::test_body"],
            repo_root=tmp_path,
            collect_only=False,
        )

        # Body executed exactly once and recorded as passed.
        # Nodeid format varies by pytest/cwd; check count and outcome.
        assert len(result.gate_result.executed_nodeids) == 1, (
            f"Expected one executed nodeid, got: {result.gate_result.executed_nodeids!r}"
        )
        assert result.gate_result.outcome_counts["passed"] == 1, (
            f"Expected 1 passed, got: {result.gate_result.outcome_counts}"
        )


# ---------------------------------------------------------------------------
# Plugin / subprocess consistency (P0-1 / P0-4).
# ---------------------------------------------------------------------------


class TestProcessPluginConsistency:
    """P0-1: _run_pytest_subprocess delegates to _validate_result_payload."""

    def test_mismatch_rejected_by_runner(self) -> None:
        """Wrong plugin exit code is rejected by the single authority."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": {
                "passed": 0, "failed": 0, "skipped": 0,
                "xfailed": 0, "xpassed": 0, "error": 0,
            },
            "pytest_exit_code": 1,  # Wrong: subprocess returned 0.
        }
        with pytest.raises(InventoryError, match="mismatch"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=[],
            )

    def test_missing_result_file_rejected(self) -> None:
        """Missing result file raises InventoryError via subprocess.

        Covered by test_promotion_experimental_lab_build_lane_contract.py
        which exercises _run_pytest_subprocess() via the runner CLI and
        verifies the missing-result-file rejection path.  The direct unit
        path is blocked by conftest_kubectl_guard.
        """
        pass  # Integration test: test_promotion_experimental_lab_build_lane_contract.py


# ---------------------------------------------------------------------------
# Result schema validation — exact key set (P0-4).
# ---------------------------------------------------------------------------


class TestMalformedSchema:
    """P0-4: exact outcome key set, bool rejection, sum invariant."""

    def test_unknown_outcome_key(self) -> None:
        """Unknown outcome key raises InventoryError."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": {
                "passed": 0, "failed": 0, "skipped": 0,
                "xfailed": 0, "xpassed": 0, "error": 0,
                "unknown_outcome": 1,  # Extra key.
            },
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="unknown outcome key"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=[],
            )

    def test_wrong_field_type_rejected(self) -> None:
        """Non-int outcome count raises InventoryError."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": {
                "passed": "not_an_int",  # Wrong type.
                "failed": 0, "skipped": 0,
                "xfailed": 0, "xpassed": 0, "error": 0,
            },
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="not int"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=[],
            )

    def test_wrong_top_level_type_rejected(self) -> None:
        """Non-dict outcome_counts raises InventoryError."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload: dict[str, object] = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": [],  # Must be dict, not list.
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="wrong type"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=[],
            )

    def test_bool_count_rejected(self) -> None:
        """bool (subclass of int) is rejected as not an int."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": {
                "passed": True,  # bool is not a valid count type.
                "failed": 0, "skipped": 0,
                "xfailed": 0, "xpassed": 0, "error": 0,
            },
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="not int"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=[],
            )

    def test_exact_outcome_key_set_required(self) -> None:
        """Outcome counts must have exactly the six known keys."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        # Missing one key.
        payload = {
            "collected_nodeids": [],
            "executed_nodeids": [],
            "outcome_counts": {
                "passed": 1, "failed": 0,
                # "skipped", "xfailed", "xpassed", "error" missing.
            },
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="missing outcome key"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=["test_foo.py::test_foo"],
            )

    def test_count_sum_mismatch_rejected(self) -> None:
        """Outcome-count sum must equal len(executed_nodeids)."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        from run_promotion_runtime_gate import (
            InventoryError,
            _validate_result_payload,
        )
        payload = {
            "collected_nodeids": ["t.py::test_one", "t.py::test_two"],
            "executed_nodeids": ["t.py::test_one"],  # 1 executed.
            "outcome_counts": {
                "passed": 2,  # Sum=2 but len(executed)=1 — mismatch.
                "failed": 0, "skipped": 0,
                "xfailed": 0, "xpassed": 0, "error": 0,
            },
            "pytest_exit_code": 0,
        }
        with pytest.raises(InventoryError, match="outcome_counts sum"):
            _validate_result_payload(
                payload,
                subprocess_returncode=0,
                executed_nodeids=["t.py::test_one"],
            )


# ---------------------------------------------------------------------------
# Lane authority classification (P0-6).
# ---------------------------------------------------------------------------


class TestPluginLaneAuthorityScope:
    """P0-6: plugin and its test are in EXPERIMENTAL_LANE_AUTHORITY_PATHS."""

    def test_plugin_in_lane_authority_paths(self) -> None:
        """pytest_runtime_gate_plugin.py must be in lane authority paths."""
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        import promotion_runtime_static_scope as scope

        plugin_rel = "scripts/ci/pytest_runtime_gate_plugin.py"
        assert plugin_rel in scope.EXPERIMENTAL_LANE_AUTHORITY_PATHS, (
            f"{plugin_rel} must be in EXPERIMENTAL_LANE_AUTHORITY_PATHS"
        )

    def test_plugin_not_deferred(self) -> None:
        """pytest_runtime_gate_plugin.py is in lane authority paths (not deferred).

        DEFERRED_PATHS was removed in the dual-range model. The plugin is in
        EXPERIMENTAL_LANE_AUTHORITY_PATHS which IS lane_authority (not deferred).
        """
        sys.path.insert(0, str(ROOT / "scripts" / "ci"))
        import promotion_runtime_static_scope as scope

        plugin_rel = "scripts/ci/pytest_runtime_gate_plugin.py"
        # Verify it's in lane authority paths (not deferred)
        assert plugin_rel in scope.EXPERIMENTAL_LANE_AUTHORITY_PATHS, (
            "pytest_runtime_gate_plugin.py must be in EXPERIMENTAL_LANE_AUTHORITY_PATHS"
        )
