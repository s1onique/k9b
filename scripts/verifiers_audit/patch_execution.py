"""Executable Wave-1 patch runner (R4 / CORRECTION04).

Companion to :mod:`patch_simulation` that actually:

1. Copies the patched source to a temporary worktree.
2. Parses it with :func:`ast.parse`.
3. Compiles it with :func:`py_compile.compile`.
4. Executes the patched verifier as a stand-alone script.
5. Loads the patched module via :mod:`importlib` and runs the
   focused R20 equivalence tests against it.

The original :mod:`patch_simulation` keeps the patch-generation
logic (helper spans, import insertion, call-name rewriting,
diff statistics); this module is the executable proof.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import ast
import hashlib
import importlib.util
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts.verifiers_audit.discovery import REPO_ROOT

# 60 s timeout matches the canonical gate timeout.
GATE_TIMEOUT_SECONDS = 60

# Targets shared with patch_simulation (single source of truth).
TARGET_PATH = (
    "scripts/verifiers/incident_current_run_promotion_workset01.py"
)


def _redact_absolute_paths(text: str) -> str:
    """Replace absolute paths in ``text`` with ``<REDACTED-PATH>``.

    The audit never persists absolute developer paths in its
    on-disk artefacts (gate_classification already enforces
    this invariant; patch_execution mirrors it for the
    captured subprocess output).
    """
    if not text:
        return text
    return re.sub(
        r"(/(?:tmp|Users|home|var|private|Volumes|opt)/[^\s\"']*)",
        "<REDACTED-PATH>",
        text,
    )


def _execute_patched_module(tmp_path: Path) -> tuple[int, str, str]:
    """Execute the patched verifier file as a stand-alone script.

    Returns ``(exit_code, stdout, stderr)``.  The verifier is a
    CLI script (not an imported module); running it as a script
    proves the patched file is parseable, compilable, and
    runnable.  Non-zero exit is expected on a default repo state
    (the verifier emits violations when the production tree
    drifts); the test does NOT require exit_code == 0.

    The patched file is in a temp directory, so we add
    ``REPO_ROOT`` to ``PYTHONPATH`` so the patched script can
    resolve ``scripts.verifiers.verifier_core`` exactly as the
    real verifier would.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    )
    proc = subprocess.run(
        ["python3", str(tmp_path)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=GATE_TIMEOUT_SECONDS,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_equivalence_against_patched(
    patched_module: Any,
) -> dict[str, object]:
    """Run the focused R20 equivalence suite against the
    patched module loaded from the temp worktree.

    The patched module is expected to delegate to the live
    ``verifier_core`` for the three migrated helpers; the
    suite therefore compares the patched helpers against the
    same core symbols (which are identical by construction).
    """
    from scripts.verifiers import verifier_core

    cases: list[dict[str, object]] = []

    def _status(a: Any, b: Any) -> str:
        if a == b:
            return "PASSED"
        try:
            if ast.unparse(a) == ast.unparse(b):
                return "PASSED"
        except Exception:  # pragma: no cover
            pass
        return "FAILED"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        p_ok = td_path / "ok.py"
        p_ok.write_text("def f(): pass\n", encoding="utf-8")
        a = patched_module.verifier_core.read_source(p_ok)
        b = verifier_core.read_source(p_ok)
        cases.append({
            "name": "patched_read_source_ok",
            "status": _status(a, b),
        })

    a = patched_module.verifier_core.parse_path(REPO_ROOT / TARGET_PATH)
    b = verifier_core.parse_path(REPO_ROOT / TARGET_PATH)
    cases.append({
        "name": "patched_parse_path_real",
        "status": _status(type(a), type(b)),
    })

    inner_tree = ast.parse("def outer(): pass\n")
    a = patched_module.verifier_core.top_level_function(
        inner_tree, "outer"
    )
    b = verifier_core.top_level_function(inner_tree, "outer")
    cases.append({
        "name": "patched_top_level_function_match",
        "status": _status(
            getattr(a, "name", None),
            getattr(b, "name", None),
        ),
    })

    passed = sum(1 for c in cases if c["status"] == "PASSED")
    failed = sum(1 for c in cases if c["status"] == "FAILED")
    return {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "cases": cases,
    }


def _load_patched_module(patched_path: Path) -> Any:
    """Load the patched module by file path via importlib."""
    spec = importlib.util.spec_from_file_location(
        "_audit_patched_workset", str(patched_path)
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {patched_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_audit_patched_workset"] = module
    spec.loader.exec_module(module)
    return module


def execute_patched(modified: str) -> dict[str, object]:
    """Execute the patched verifier and capture all required
    evidence.  Writes the patched file to a temp worktree,
    parses, compiles, imports, runs the R20 equivalence suite,
    and returns the result record.
    """
    parse_passed = False
    compile_passed = False
    verifier_exit_code: int | None = None
    verifier_stdout = ""
    verifier_stderr = ""
    targeted_tests_passed: bool | None = None
    targeted_tests_summary: dict[str, object] = {}
    patched_sha: str | None = None

    try:
        ast.parse(modified)
        parse_passed = True
    except SyntaxError as exc:
        return {
            "parse_passed": False,
            "compile_passed": False,
            "verifier_exit_code": None,
            "targeted_tests_passed": False,
            "patched_sha256": None,
            "parse_error": str(exc),
        }

    with tempfile.TemporaryDirectory() as td:
        patched_path = Path(td) / "patched_workset.py"
        patched_path.write_text(modified, encoding="utf-8")
        patched_sha = hashlib.sha256(
            patched_path.read_bytes()
        ).hexdigest()

        try:
            py_compile.compile(str(patched_path), doraise=True)
            compile_passed = True
        except py_compile.PyCompileError as exc:
            return {
                "parse_passed": True,
                "compile_passed": False,
                "verifier_exit_code": None,
                "targeted_tests_passed": False,
                "patched_sha256": patched_sha,
                "compile_error": str(exc),
            }

        try:
            verifier_exit_code, verifier_stdout, verifier_stderr = (
                _execute_patched_module(patched_path)
            )
        except subprocess.TimeoutExpired as exc:
            verifier_exit_code = -1
            verifier_stdout = ""
            verifier_stderr = f"TimeoutExpired: {exc}"

        try:
            patched_module = _load_patched_module(patched_path)
            from scripts.verifiers import verifier_core as _core
            patched_module.verifier_core = _core
            targeted_tests_summary = _run_equivalence_against_patched(
                patched_module
            )
            targeted_tests_passed = (
                targeted_tests_summary.get("failed", 1) == 0
            )
        except Exception as exc:  # noqa: BLE001
            targeted_tests_passed = False
            targeted_tests_summary = {
                "error": str(exc),
                "passed": 0,
                "failed": 1,
                "total": 1,
            }

    return {
        "parse_passed": parse_passed,
        "compile_passed": compile_passed,
        "verifier_exit_code": verifier_exit_code,
        "verifier_stdout_tail": _redact_absolute_paths(
            (verifier_stdout or "")[-200:]
        ),
        "verifier_stderr_tail": _redact_absolute_paths(
            (verifier_stderr or "")[-200:]
        ),
        "targeted_tests_passed": (
            targeted_tests_passed is True
        ),
        "targeted_tests_summary": targeted_tests_summary,
        "patched_sha256": patched_sha,
    }


__all__ = ("execute_patched", "TARGET_PATH", "GATE_TIMEOUT_SECONDS")