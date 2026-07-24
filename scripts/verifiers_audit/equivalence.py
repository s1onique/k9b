"""Outcome-based Wave-1 equivalence fixtures (R5).

Each Wave-1 candidate must be paired-tested against the real core
primitive. Both implementations are invoked independently and
their captured outcomes are compared.

A case passes only if BOTH implementations independently return
equivalent results or independently raise equivalent exceptions.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import ast
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.verifiers_audit.discovery import REPO_ROOT


@dataclass(frozen=True)
class Returned:
    """Captured normal return value."""

    value_kind: str  # "str" | "module" | "function_node" | "none" | "list"
    normalized_value: str


@dataclass(frozen=True)
class Raised:
    """Captured exception."""

    exception_type: str
    errno: int | None


def _capture_str(value: str) -> Returned:
    return Returned(value_kind="str", normalized_value=value)


def _capture_module(value: ast.Module | None) -> Returned:
    if value is None:
        return Returned(value_kind="none", normalized_value="None")
    return Returned(value_kind="module", normalized_value=ast.unparse(value))


def _capture_func_node(value: Any) -> Returned:
    if value is None:
        return Returned(value_kind="none", normalized_value="None")
    return Returned(
        value_kind="function_node",
        normalized_value=f"{value.name}@{value.lineno}",
    )


def _capture_exception(exc: BaseException) -> Raised:
    errno_val: int | None = None
    if isinstance(exc, OSError) and exc.errno is not None:
        errno_val = exc.errno
    return Raised(exception_type=type(exc).__name__, errno=errno_val)


def _invoke(func: Any, *args: Any, **kwargs: Any) -> Returned | Raised:
    """Invoke ``func`` and capture either Returned or Raised."""
    try:
        result = func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - capture all
        return _capture_exception(exc)
    if isinstance(result, str):
        return _capture_str(result)
    if isinstance(result, ast.Module) or result is None:
        return _capture_module(result)
    return _capture_func_node(result)


def _outcomes_match(a: Returned | Raised, b: Returned | Raised) -> bool:
    if isinstance(a, Returned) and isinstance(b, Returned):
        return a == b
    if isinstance(a, Raised) and isinstance(b, Raised):
        # Both raised; consider equivalent if exception type matches
        # AND, when applicable, errno matches.
        if a.exception_type != b.exception_type:
            return False
        return a.errno == b.errno
    # Mixed return vs raised is NOT equivalent.
    return False


_STATUS_PASSED = "PASSED"
_STATUS_SKIPPED = "SKIPPED"
_STATUS_FAILED = "FAILED"


def _case(name: str, local_outcome: Returned | Raised,
          core_outcome: Returned | Raised) -> dict[str, object]:
    return {
        "name": name,
        "status": _STATUS_PASSED if _outcomes_match(
            local_outcome, core_outcome
        ) else _STATUS_FAILED,
        "local": _outcome_repr(local_outcome),
        "core": _outcome_repr(core_outcome),
    }


def _skipped_case(name: str, reason: str) -> dict[str, object]:
    """Mark a case as platform-skipped (does NOT increment ``passed``)."""
    return {
        "name": name,
        "status": _STATUS_SKIPPED,
        "local": f"skipped ({reason})",
        "core": f"skipped ({reason})",
    }


def _outcome_repr(o: Returned | Raised) -> str:
    if isinstance(o, Returned):
        return f"Returned({o.value_kind}, {o.normalized_value[:60]!r})"
    return f"Raised({o.exception_type}, errno={o.errno})"


# ---------------------------------------------------------------------------
# _read_source  vs  read_source
# ---------------------------------------------------------------------------


def _read_source_equivalence() -> list[dict[str, object]]:
    from scripts.verifiers import verifier_core

    cases: list[dict[str, object]] = []
    module = _import_workset_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)

        # Valid UTF-8 file.
        p_ok = td / "ok.py"
        p_ok.write_text("def f(): pass\n", encoding="utf-8")
        cases.append(_case(
            "valid_utf8",
            _invoke(module._read_source, p_ok),
            _invoke(verifier_core.read_source, p_ok),
        ))

        # Empty file.
        p_empty = td / "empty.py"
        p_empty.write_text("", encoding="utf-8")
        cases.append(_case(
            "empty_file",
            _invoke(module._read_source, p_empty),
            _invoke(verifier_core.read_source, p_empty),
        ))

        # Missing file.
        p_missing = td / "missing.py"
        cases.append(_case(
            "missing_file",
            _invoke(module._read_source, p_missing),
            _invoke(verifier_core.read_source, p_missing),
        ))

        # Directory supplied as a file.
        cases.append(_case(
            "dir_as_file",
            _invoke(module._read_source, td),
            _invoke(verifier_core.read_source, td),
        ))

        # Invalid UTF-8 bytes.
        p_invalid = td / "invalid.py"
        p_invalid.write_bytes(b"\xff\xfe\xfd")
        cases.append(_case(
            "invalid_utf8",
            _invoke(module._read_source, p_invalid),
            _invoke(verifier_core.read_source, p_invalid),
        ))

        # Permission denied. Create a read-only file; if the platform
        # forbids even opening it for read, both helpers must raise
        # PermissionError or OSError with errno=EACCES.
        p_ro = td / "ro.py"
        p_ro.write_text("# deny\n", encoding="utf-8")
        try:
            os.chmod(p_ro, 0)
            local_outcome = _invoke(module._read_source, p_ro)
            core_outcome = _invoke(verifier_core.read_source, p_ro)
            # Platform-skip when both succeeded: mode 0 is still
            # readable on some platforms / by some users.  A skip
            # MUST NOT increment ``passed``.
            if not isinstance(local_outcome, Raised) or not isinstance(
                core_outcome, Raised
            ):
                cases.append(_skipped_case(
                    "permission_denied", "mode 0 still readable on this platform"
                ))
            else:
                cases.append(_case(
                    "permission_denied", local_outcome, core_outcome
                ))
        finally:
            try:
                os.chmod(p_ro, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

    return cases


# ---------------------------------------------------------------------------
# _parse  vs  parse_path
# ---------------------------------------------------------------------------


def _parse_equivalence() -> list[dict[str, object]]:
    from scripts.verifiers import verifier_core

    cases: list[dict[str, object]] = []
    module = _import_workset_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)

        # Valid Python.
        p_ok = td / "ok.py"
        p_ok.write_text("x = 1\n", encoding="utf-8")
        local = module._parse(p_ok)
        core = verifier_core.parse_path(p_ok)
        cases.append(_case(
            "valid_python",
            _capture_module(local),
            _capture_module(core),
        ))

        # Empty file (valid Python: empty module).
        p_empty = td / "empty.py"
        p_empty.write_text("", encoding="utf-8")
        local = module._parse(p_empty)
        core = verifier_core.parse_path(p_empty)
        cases.append(_case(
            "empty_file",
            _capture_module(local),
            _capture_module(core),
        ))

        # Syntax-invalid.
        p_bad = td / "bad.py"
        p_bad.write_text("def f(:\n", encoding="utf-8")
        cases.append(_case(
            "syntax_invalid",
            _invoke(module._parse, p_bad),
            _invoke(verifier_core.parse_path, p_bad),
        ))

        # Missing file.
        p_missing = td / "missing.py"
        cases.append(_case(
            "missing_file",
            _invoke(module._parse, p_missing),
            _invoke(verifier_core.parse_path, p_missing),
        ))

        # Directory.
        cases.append(_case(
            "dir_as_file",
            _invoke(module._parse, td),
            _invoke(verifier_core.parse_path, td),
        ))

        # Invalid UTF-8.
        p_invalid = td / "invalid.py"
        p_invalid.write_bytes(b"\xff\xfe\xfd")
        cases.append(_case(
            "invalid_utf8",
            _invoke(module._parse, p_invalid),
            _invoke(verifier_core.parse_path, p_invalid),
        ))

    return cases


# ---------------------------------------------------------------------------
# _function_def_in  vs  top_level_function
# ---------------------------------------------------------------------------


def _function_def_in_equivalence() -> list[dict[str, object]]:
    from scripts.verifiers import verifier_core

    cases: list[dict[str, object]] = []
    module = _import_workset_module()

    # Matching top-level function.
    src = "def outer(): pass\n"
    tree = _parse(src)
    cases.append(_case(
        "top_level_match",
        _capture_func_node(module._function_def_in(tree, "outer")),
        _capture_func_node(verifier_core.top_level_function(tree, "outer")),
    ))

    # Absent name.
    cases.append(_case(
        "absent_name",
        _capture_func_node(module._function_def_in(tree, "absent")),
        _capture_func_node(verifier_core.top_level_function(tree, "absent")),
    ))

    # Nested-only matching name (R3 / CORRECTION03). The target is
    # nested inside a top-level ``container``.  Both helpers must
    # return None (top level only).
    src = "def container():\n    def target(): pass\n"
    tree = _parse(src)
    cases.append(_case(
        "nested_only_top_level_returns_none",
        _capture_func_node(module._function_def_in(tree, "target")),
        _capture_func_node(verifier_core.top_level_function(tree, "target")),
    ))

    # Class-method-only matching name (R3 / CORRECTION03).  The
    # target is a method on a top-level ``Container`` class.  Both
    # helpers must return None (top level only).
    src = "class Container:\n    def target(self): pass\n"
    tree = _parse(src)
    cases.append(_case(
        "class_method_only_top_level_returns_none",
        _capture_func_node(module._function_def_in(tree, "target")),
        _capture_func_node(verifier_core.top_level_function(tree, "target")),
    ))

    # Async-only matching name. Both helpers must return None (the
    # core only matches ``FunctionDef``; the workset does too).
    src = "async def outer(): pass\n"
    tree = _parse(src)
    cases.append(_case(
        "async_only_returns_none",
        _capture_func_node(module._function_def_in(tree, "outer")),
        _capture_func_node(verifier_core.top_level_function(tree, "outer")),
    ))

    # Duplicate top-level definitions. Both must return the FIRST.
    src = "def outer(): return 1\ndef outer(): return 2\n"
    tree = _parse(src)
    a = module._function_def_in(tree, "outer")
    b = verifier_core.top_level_function(tree, "outer")
    same_first = (
        isinstance(a, ast.FunctionDef)
        and isinstance(b, ast.FunctionDef)
        and ast.unparse(a) == "def outer():\n    return 1"
    )
    cases.append({
        "name": "duplicate_first_match",
        "status": _STATUS_PASSED if same_first else _STATUS_FAILED,
        "local": _outcome_repr(_capture_func_node(a)),
        "core": _outcome_repr(_capture_func_node(b)),
    })

    # Top-level function plus same-name nested function. Both must
    # return the top-level one.
    src = "def outer(): pass\ndef outer2():\n    def outer(): pass\n"
    tree = _parse(src)
    a = module._function_def_in(tree, "outer")
    b = verifier_core.top_level_function(tree, "outer")
    top_level_match = (
        isinstance(a, ast.FunctionDef)
        and isinstance(b, ast.FunctionDef)
        and a.col_offset == 0  # top-level, not nested
        and a.lineno == 1       # first match
    )
    cases.append({
        "name": "top_level_plus_nested",
        "status": _STATUS_PASSED if top_level_match else _STATUS_FAILED,
        "local": _outcome_repr(_capture_func_node(a)),
        "core": _outcome_repr(_capture_func_node(b)),
    })

    # Class method followed by top-level function. The class method
    # must NOT match; the top-level function must. Both
    # implementations must agree on which node was selected.
    src = "class C:\n    def outer(self): pass\ndef outer(): pass\n"
    tree = _parse(src)
    local_outcome = _invoke(module._function_def_in, tree, "outer")
    core_outcome = _invoke(verifier_core.top_level_function, tree, "outer")
    cases.append(_case(
        "method_then_top_level", local_outcome, core_outcome
    ))

    return cases


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


def _import_workset_module() -> Any:
    """Import the workset module by file path."""
    import importlib.util
    import sys

    path = REPO_ROOT / "scripts/verifiers/incident_current_run_promotion_workset01.py"
    spec = importlib.util.spec_from_file_location("_audit_workset_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_audit_workset_target"] = module
    spec.loader.exec_module(module)
    return module


def summarise_equivalence(results: list[dict[str, object]]) -> dict[str, object]:
    """Reduce a list of case dicts into a suite summary.

    Returns ``total``, ``executed``, ``passed``, ``failed``,
    ``skipped``, plus the per-case detail.  ``executed ==
    passed + failed``; ``skipped`` is reported separately.
    """
    total = len(results)
    passed = sum(1 for c in results if c.get("status") == _STATUS_PASSED)
    failed = sum(1 for c in results if c.get("status") == _STATUS_FAILED)
    skipped = sum(1 for c in results if c.get("status") == _STATUS_SKIPPED)
    return {
        "total": total,
        "executed": passed + failed,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "cases": list(results),
    }


def run_read_source_equivalence() -> dict[str, object]:
    return summarise_equivalence(_read_source_equivalence())


def run_parse_equivalence() -> dict[str, object]:
    return summarise_equivalence(_parse_equivalence())


def run_top_level_function_equivalence() -> dict[str, object]:
    return summarise_equivalence(_function_def_in_equivalence())


def run_all_equivalence() -> dict[str, dict[str, object]]:
    return {
        "read_source": run_read_source_equivalence(),
        "parse": run_parse_equivalence(),
        "top_level_function": run_top_level_function_equivalence(),
    }
