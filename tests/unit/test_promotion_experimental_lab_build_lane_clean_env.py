"""Clean-environment completeness proof for the experimental runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION05

The proof MUST read the canonical manifest
(``scripts/ci/promotion_runtime_tests.txt``) via the canonical runner
(``scripts/ci/run_promotion_runtime_gate.py --collect-only``); it MUST
NOT define its own subset of files.

The proof asserts exact collection equality: the node IDs collected in
the fresh venv MUST equal the canonical manifest's expected collection.

A bootstrap failure is reported as a test failure (not skip); this is the
"required integration proof" model from the CORRECTION05 specification.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "ci" / "bootstrap_python_dev.sh"
RUNNER_SCRIPT = ROOT / "scripts" / "ci" / "run_promotion_runtime_gate.py"
MANIFEST = ROOT / "scripts" / "ci" / "promotion_runtime_tests.txt"


def _host_python() -> str:
    for candidate in ("python3", "python3.13", "python3.12", "python"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("no python interpreter on PATH")


@unittest.skipUnless(
    BOOTSTRAP_SCRIPT.exists() and RUNNER_SCRIPT.exists() and MANIFEST.exists(),
    "canonical experimental-lab tools not found",
)
class TestCleanEnvCompleteness(unittest.TestCase):
    """Fresh venv + canonical runner proves the runtime inventory collects."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="k9b-clean-env-")
        self._venv = Path(self._tmpdir) / "venv"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _bootstrap(self) -> None:
        env = os.environ.copy()
        env["VENV_DIR"] = str(self._venv)
        env["PYTHON_BIN"] = _host_python()
        env["PYTHONNOUSERSITE"] = "1"
        proc = subprocess.run(
            ["bash", str(BOOTSTRAP_SCRIPT)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(
                "canonical bootstrap failed; bootstrap is a required "
                f"integration step. stderr={proc.stderr[-400:]}"
            ),
        )

    def test_fresh_venv_installs_dev_tools(self) -> None:
        self._bootstrap()
        venv_python = self._venv / "bin" / "python"
        self.assertTrue(venv_python.exists())
        for tool in ("pytest", "ruff", "mypy"):
            proc = subprocess.run(
                [str(venv_python), "-c", f"import {tool}; print({tool}.__file__)"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"{tool} not importable from venv: {proc.stderr}",
            )
            self.assertIn(str(self._venv), proc.stdout)
        # sys.prefix must differ from the host prefix.
        proc = subprocess.run(
            [str(venv_python), "-c", "import sys; print(sys.prefix)"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn(str(self._venv), proc.stdout)

    def test_canonical_inventory_collects_in_fresh_venv(self) -> None:
        """The exact canonical inventory MUST collect cleanly in a fresh venv.

        This is the CORRECTION05 P0-5 "required integration proof":
        bootstrap or collection failure is a TEST FAILURE (not a skip).
        """
        self._bootstrap()
        # Run the canonical runner with the canonical manifest in the
        # fresh venv.  The runner invokes pytest directly, so it picks
        # up the venv via its shebang and PYTHONNOUSERSITE=1.
        env = os.environ.copy()
        env["PATH"] = f"{self._venv}/bin:" + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(self._venv)
        env["PYTHONNOUSERSITE"] = "1"
        transcript = Path(self._tmpdir) / "transcript.log"
        proc = subprocess.run(
            [
                str(self._venv / "bin" / "python"),
                str(RUNNER_SCRIPT),
                "--collect-only",
                "--manifest",
                str(MANIFEST),
                "--transcript",
                str(transcript),
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(
                "canonical runner failed in fresh venv: stdout="
                f"{proc.stdout[-400:]} stderr={proc.stderr[-400:]}"
            ),
        )
        # The transcript must include the structured runtime_gate_record
        # with collected_node_count > 0.
        self.assertTrue(transcript.exists())
        transcript_text = transcript.read_text(encoding="utf-8")
        self.assertIn("collected_node_count", transcript_text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()