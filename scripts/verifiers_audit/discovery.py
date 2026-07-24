"""AST-driven helper discovery.

This module parses every included verifier file with :mod:`ast` and
extracts every top-level and nested function or method definition.
Each discovered helper carries:

* :attr:`HelperRecord.path` — repository-relative path
* :attr:`HelperRecord.qualname` — ``module.helper`` or
  ``module.Class.helper``
* :attr:`HelperRecord.line` — start line
* :attr:`HelperRecord.end_line` — end line
* :attr:`HelperRecord.kind` — ``function`` / ``method`` /
  ``async_function`` / ``async_method``
* :attr:`HelperRecord.returns` — return annotation text (or
  ``None``)
* :attr:`HelperRecord.args_count` — number of positional
  parameters
* :attr:`HelperRecord.is_public` — name does not start with ``_``

The discovery layer is purely mechanical; classification as
``structural`` vs ``non-structural`` happens in
:mod:`scripts.verifiers_audit.groups` after the helpers are
cross-referenced against the verifier_core public surface.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import ast
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class HelperRecord:
    """One top-level or nested function/method AST node."""

    path: str
    qualname: str
    line: int
    end_line: int
    kind: str  # function / method / async_function / async_method
    returns: str | None
    args_count: int
    is_public: bool
    decorators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _kind(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool) -> str:
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_method" if is_method else "async_function"
    return "method" if is_method else "function"


def _annotation_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


def _collect_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out: list[str] = []
    for d in node.decorator_list:
        try:
            out.append(ast.unparse(d))
        except Exception:  # pragma: no cover - defensive
            out.append("<unknown>")
    return out


def _walk_for_helpers(
    tree: ast.Module, path: str
) -> Iterable[HelperRecord]:
    """Yield helper records for every function/method in ``tree``."""

    def visit(node: ast.AST, parent_qual: str) -> Iterable[HelperRecord]:
        if isinstance(node, ast.ClassDef):
            qual = (
                f"{parent_qual}.{node.name}" if parent_qual else node.name
            )
            # Methods live inside ClassDef body.
            for stmt in node.body:
                yield from visit(stmt, qual)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_method = bool(parent_qual)
            qual = f"{parent_qual}.{node.name}" if parent_qual else node.name
            yield HelperRecord(
                path=path,
                qualname=qual,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                kind=_kind(node, is_method),
                returns=_annotation_text(node.returns),
                args_count=len(node.args.args) + len(node.args.kwonlyargs),
                is_public=not node.name.startswith("_"),
                decorators=_collect_decorators(node),
            )
            # Nested functions/methods (closure helpers, private
            # classmethods, etc.) are also helpers — the AST yields
            # them through the recursive visit.
            for stmt in node.body:
                yield from visit(stmt, qual)
            return
        # Recurse into container nodes so we find nested defs.
        for child in ast.iter_child_nodes(node):
            yield from visit(child, parent_qual)

    for stmt in tree.body:
        yield from visit(stmt, "")


def discover_helpers_for_file(path: str) -> list[HelperRecord]:
    """Parse ``path`` and return its AST-discovered helpers."""
    full = REPO_ROOT / path
    try:
        source = full.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(full))
    except SyntaxError:
        return []
    records = list(_walk_for_helpers(tree, path))
    records.sort(key=lambda r: (r.path, r.line, r.qualname))
    return records


def discover_helpers(paths: Iterable[str]) -> list[HelperRecord]:
    """Discover helpers across every included verifier path."""
    out: list[HelperRecord] = []
    for p in paths:
        out.extend(discover_helpers_for_file(p))
    out.sort(key=lambda r: (r.path, r.line, r.qualname))
    return out


def count_lines(path: str) -> int:
    """Return the physical line count of ``path`` (0 if unreadable)."""
    full = REPO_ROOT / path
    try:
        text = full.read_text(encoding="utf-8")
    except OSError:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def core_public_symbols() -> list[str]:
    """Read the live ``verifier_core.__all__`` tuple."""
    init_path = REPO_ROOT / "scripts/verifiers/verifier_core/__init__.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__all__":
                    if isinstance(node.value, ast.Tuple):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant)
                            and isinstance(elt.value, str)
                        ]
    return []


def core_symbol_modules() -> dict[str, str]:
    """Return a ``{symbol_name: module_path}`` map by scanning each
    ``verifier_core`` submodule's ``__all__`` (or the import block of
    ``__init__.py`` when present).
    """
    mapping: dict[str, str] = {}
    init_path = REPO_ROOT / "scripts/verifiers/verifier_core/__init__.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod_short = node.module.split(".")[-1]
            for alias in node.names:
                if alias.name in {"__all__"}:
                    continue
                mapping[alias.asname or alias.name] = (
                    f"scripts/verifiers/verifier_core/{mod_short}.py"
                )
    # Fallback: scan each submodule's __all__ for any names not yet
    # mapped.
    for mod in (
        "codes",
        "diagnostics",
        "lookups",
        "directness",
        "detectors",
    ):
        sub = REPO_ROOT / "scripts/verifiers/verifier_core" / f"{mod}.py"
        try:
            text = sub.read_text(encoding="utf-8")
        except OSError:
            continue
        sub_tree = ast.parse(text)
        for node in sub_tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if (
                        isinstance(tgt, ast.Name)
                        and tgt.id == "__all__"
                        and isinstance(node.value, ast.Tuple)
                    ):
                        for elt in node.value.elts:
                            if (
                                isinstance(elt, ast.Constant)
                                and isinstance(elt.value, str)
                            ):
                                mapping.setdefault(
                                    elt.value,
                                    f"scripts/verifiers/verifier_core/{mod}.py",
                                )
    return mapping
