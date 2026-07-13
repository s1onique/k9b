"""Shared fixtures for R5/SEAM01 verifier negative tests.

Provides reusable helpers for creating synthetic fixture trees and
running verifier scripts via subprocess.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_verifier(script_name: str):
    """Import ``scripts/<script_name>.py`` as a module."""
    script_path = REPO_ROOT / "scripts" / f"{script_name}.py"
    spec = importlib.util.spec_from_file_location(script_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load verifier: {script_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_name] = module
    spec.loader.exec_module(module)
    return module


class _FixtureTree:
    """Context manager for a temporary ``src/`` fixture root."""

    def __init__(self, relative_path: str, body: str):
        self._relative_path = relative_path
        self._body = textwrap.dedent(body)
        self._tmp: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        tmp_root = Path(tempfile.mkdtemp(prefix="k9b_r5_verifier_"))
        src_root = tmp_root / "src"
        src_root.mkdir(parents=True, exist_ok=True)
        # Always add an innocent sibling so rglob() has at least one
        # other ``.py`` file to consider
        (src_root / "__init__.py").write_text("", encoding="utf-8")
        violation_path = src_root / self._relative_path
        violation_path.parent.mkdir(parents=True, exist_ok=True)
        violation_path.write_text(self._body, encoding="utf-8")
        self._tmp = tmp_root
        return src_root

    def __exit__(self, *_exc: object) -> None:
        if self._tmp is None:
            return
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)


class _SubprocessMixin:
    """Run a verifier script via subprocess and capture the result."""

    @staticmethod
    def _run(script_name: str, src_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / f"{script_name}.py"),
                "--src-root",
                str(src_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
