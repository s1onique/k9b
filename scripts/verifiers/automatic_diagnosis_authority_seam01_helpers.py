"""AST and file helpers for the ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
verifier.

This module owns:

* File-collection primitives (``_read``, ``_parse``, ``_iter_python_files``)
  used by the verifier to discover source files under ``src/``.
* Pure AST helpers (``_function_defs``, ``_called_names``,
  ``_call_keyword``, ``_match_case_type``) that translate a parsed
  :class:`ast.Module` into the minimal structures the individual checks
  need.
* Forbidden-pattern detectors that operate on any AST tree and are
  reusable across multiple checks
  (``_contains_truthiness_to_not_found``, ``_has_empty_except_pass``).

The verifier entry point
(:mod:`scripts.verifiers.automatic_diagnosis_authority_seam01`)
re-exports every public helper so the self-tests can access them via
the verifier module attribute. The per-file-size check is split between
this helpers module and the per-check checks module to keep both files
within the LLM-friendly 500-line limit.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

# Repo-rooted paths reused by both this helpers module and the checks
# module. They are duplicated here (not imported from the verifier
# entry point) so the helpers module is self-contained and the cyclic
# import graph stays acyclic.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SRC_ROOT: Path = REPO_ROOT / "src" / "k8s_diag_agent"

PROCESSOR_PATH: Path = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_evidence_processor.py"
)
EVALUATOR_PATH: Path = (
    SRC_ROOT / "collect" / "incident_diagnosis_auto_loop_config.py"
)
SEAM_PATH: Path = (
    SRC_ROOT / "collect" / "incident_diagnosis_authority_seam.py"
)
# Backward-compat alias for self-tests and existing call sites.
ELIGIBILITY_PATH: Path = EVALUATOR_PATH


def read_text(path: Path) -> str | None:
    """Read a UTF-8 text file, returning ``None`` on OS errors."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def parse_path(path: Path) -> ast.Module | None:
    """Read and parse a Python file; return ``None`` on any error."""
    source = read_text(path)
    if source is None:
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def iter_python_files() -> Iterable[Path]:
    """Yield every non-``__init__`` Python file under ``src/``."""
    for path in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        yield path


def function_defs(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Return a name→FunctionDef map for top-level function definitions."""
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = node
    return out


def called_names(node: ast.Call) -> list[str]:
    """Return the dotted-name call identifier list for a Call node.

    For ``a.b.c()`` we return ``["a", "b", "c"]``. For bare ``foo()``
    we return ``["foo"]``. Side-effect-only calls return an empty
    list so we never false-positive on attribute references used as
    function arguments.
    """
    func = node.func
    parts: list[str] = []
    cur: ast.AST = func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return parts
    return []


def call_keyword(call: ast.Call, keyword: str) -> ast.AST | None:
    """Return the AST node passed as ``keyword=...`` to a call, or ``None``."""
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def match_case_type() -> type | None:
    """Return the AST node type for ``match ... case`` patterns.

    Python 3.10–3.13 expose :class:`ast.MatchCase`; Python 3.14
    renamed the class to the lowercase :func:`ast.match_case` form.
    """
    return getattr(ast, "MatchCase", None) or getattr(ast, "match_case", None)


def contains_truthiness_to_not_found(tree: ast.AST) -> bool:
    """Return True if any ``if not X: ... reason="incident_not_found"`` appears.

    The forbidden pattern collapses HTTP 200 + valid JSON into
    ``incident_not_found`` via a truthiness check; the verifier must
    reject it.
    """

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found: bool = False

        def visit_If(self, node: ast.If) -> None:  # noqa: D401
            if self.found:
                return
            if not isinstance(node.test, ast.UnaryOp) or not isinstance(
                node.test.op, ast.Not
            ):
                self.generic_visit(node)
                return
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if (
                        isinstance(sub, ast.Assign)
                        and isinstance(sub.value, ast.Constant)
                        and sub.value.value == "incident_not_found"
                    ):
                        self.found = True
                        return
                    if (
                        isinstance(sub, ast.AnnAssign)
                        and isinstance(sub.value, ast.Constant)
                        and sub.value.value == "incident_not_found"
                    ):
                        self.found = True
                        return
                    # Constructor keyword-argument form, e.g.
                    # ``AutoLoopIncidentResult(eligibility_reason="incident_not_found")``.
                    if isinstance(sub, ast.Call):
                        for kw in sub.keywords:
                            if (
                                isinstance(kw.value, ast.Constant)
                                and kw.value.value == "incident_not_found"
                            ):
                                self.found = True
                                return
            self.generic_visit(node)

    v = _Visitor()
    v.visit(tree)
    return v.found


def has_empty_except_pass(tree: ast.AST) -> bool:
    """Return True if any ``except ...: pass`` (with no body) appears."""

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found: bool = False

        def visit_Try(self, node: ast.Try) -> None:  # noqa: D401

            if not self.found:
                for handler in node.handlers:
                    if (
                        len(handler.body) == 1
                        and isinstance(handler.body[0], ast.Pass)
                    ):
                        self.found = True
                        break
            self.generic_visit(node)

    v = _Visitor()
    v.visit(tree)
    return v.found
