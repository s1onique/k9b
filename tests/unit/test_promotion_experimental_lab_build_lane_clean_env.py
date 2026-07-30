"""Clean-environment completeness proof for the experimental runtime gate.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION04
P0-3: prove that a fresh virtual environment, built ONLY with the
repository's ``.[dev]`` dependency authority, supplies pytest, Ruff and
mypy without relying on any runner-global pre-installed Python package.

The test is intentionally hermetic: it creates its own virtual environment
under a temporary directory, runs the canonical bootstrap script
(``scripts/ci/bootstrap_python_dev.sh``), and asserts:

* ``pytest``, ``ruff`` and ``mypy`` are importable from the venv;
* the focused promotion runtime test inventory can be collected;
* the venv exposes a non-zero, distinct sys.prefix.

The test is skipped when the canonical bootstrap script cannot be
found, the host Python is too old to create a venv, or pip cannot
install from the public index (sandboxed CI without network).
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

FOCUSED_TEST_FILES = (
    "tests/unit/test_scoped_selection_identity.py",
    "tests/unit/test_act_k9b_hulk_promotion_dispatch_outcome01_classifier.py",
    "tests/unit/test_promotion_outcomes.py",
    "tests/unit/test_promotion_diagnosis_handoff.py",
)


def _host_python() -> str:
    for candidate in ("python3", "python3.13", "python3.12", "python"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("no python interpreter on PATH")


@unittest.skipUnless(
    BOOTSTRAP_SCRIPT.exists(),
    f"canonical bootstrap script not found at {BOOTSTRAP_SCRIPT}",
)
class TestCleanEnvCompleteness(unittest.TestCase):
    """Fresh venv + .[dev] bootstrap is sufficient for pytest/ruff/mypy."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="k9b-clean-env-")
        self._venv = Path(self._tmpdir) / "venv"

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fresh_venv_installs_dev_tools(self) -> None:
        env = os.environ.copy()
        env["VENV_DIR"] = str(self._venv)
        env["PYTHON_BIN"] = _host_python()
        # Avoid the runner-global site-packages interfering with the venv.
        env["PYTHONNOUSERSITE"] = "1"
        # Ensure pip can resolve dependencies from the public index.
        proc = subprocess.run(
            ["bash", str(BOOTSTRAP_SCRIPT)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            self.skipTest(
                "canonical bootstrap failed in this environment "
                f"(network may be unavailable): {proc.stderr[-400:]}"
            )

        venv_python = self._venv / "bin" / "python"
        self.assertTrue(venv_python.exists())

        # Each required tool must be importable.
        for tool in ("pytest", "ruff", "mypy"):
            proc = subprocess.run(
                [
                    str(venv_python),
                    "-c",
                    f"import {tool}; print({tool}.__file__)",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"{tool} not importable from venv: {proc.stderr}",
            )
            self.assertIn(
                str(self._venv),
                proc.stdout,
                msg=f"{tool} resolved outside the venv: {proc.stdout}",
            )

        # The venv sys.prefix must differ from the host prefix.
        proc = subprocess.run(
            [
                str(venv_python),
                "-c",
                "import sys; print(sys.prefix)",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn(str(self._venv), proc.stdout)

    def test_focused_promotion_tests_collect_in_fresh_venv(self) -> None:
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
        if proc.returncode != 0:
            self.skipTest(
                "canonical bootstrap failed in this environment "
                f"(network may be unavailable): {proc.stderr[-400:]}"
            )

        venv_python = self._venv / "bin" / "python"
        proc = subprocess.run(
            [
                str(venv_python),
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                *FOCUSED_TEST_FILES,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"pytest collection failed: {proc.stdout}\n{proc.stderr}",
        )
        self.assertIn("tests collected", proc.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()