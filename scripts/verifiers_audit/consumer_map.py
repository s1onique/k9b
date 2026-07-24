"""Real import-aware consumer map for every ``verifier_core`` symbol.

Performs ONE AST pass per file. For each file it:

1. Collects every import binding (direct, aliased, qualified).
2. Collects every local definition that shadows an import.
3. Walks every Name/Attribute reference in the file.
4. Resolves each reference via the binding map.

A reference counts as a real ``verifier_core`` consumer only when
the binding resolves to the live ``scripts.verifiers.verifier_core``
package and the resolved name appears in the core's ``__all__``.

Same-name local definitions, same-name imports from unrelated
packages, and string-only occurrences are explicitly rejected.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import ast
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass

from scripts.verifiers_audit.discovery import REPO_ROOT

CORE_PACKAGE = "scripts.verifiers.verifier_core"


@dataclass(frozen=True)
class Consumer:
    symbol: str
    module: str
    production_callers: tuple[str, ...]
    test_callers: tuple[str, ...]
    classification: str

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "module": self.module,
            "production_callers": list(self.production_callers),
            "test_callers": list(self.test_callers),
            "classification": self.classification,
        }


@dataclass(frozen=True)
class _ResolvedUse:
    """A single use of a verifier_core public symbol."""

    local_name: str  # the bound local name (or dotted attribute root)
    symbol: str  # the core public symbol actually used


def _is_core_path(path: str) -> bool:
    return path == CORE_PACKAGE or path.startswith(CORE_PACKAGE + "/")


def _is_test_path(path: str) -> bool:
    return path.startswith("tests/") or "/tests/" in path


def _local_definition_names(tree: ast.Module) -> set[str]:
    """Names defined in ``tree`` at module / class / function scope.

    These names shadow any import that might have brought them in.
    """
    out: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in tree.body:
        visit(stmt)
    return out


def _import_bindings(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    """Return ``local_name -> (module, symbol_name_or_None)``.

    Accepts:

    * ``from X import a``         -> ``a   -> (X, a)``
    * ``from X import a as b``    -> ``b   -> (X, a)``
    * ``import X``                -> ``X   -> (X, None)``
    * ``import X as Y``           -> ``Y   -> (X, None)``

    Star imports are skipped.  ``None`` marks a module reference:
    bare ``Y`` is not a symbol use; only ``Y.attr`` is.
    """
    bindings: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                bindings[local] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                # Module reference; the symbol slot is None.
                bindings[local] = (alias.name, None)
    return bindings


def _is_in_core_package(module: str) -> bool:
    """``True`` when ``module`` is the core package or any of
    its submodules."""
    return module == CORE_PACKAGE or module.startswith(
        CORE_PACKAGE + "."
    )


def _resolve_module(module: str, symbol: str | None) -> str | None:
    """Translate a binding (module, symbol) into the package path
    that actually exposes ``symbol``.

    * ``from scripts.verifiers.verifier_core import read_source``
      -> ``module="scripts.verifiers.verifier_core"``,
      ``symbol="read_source"`` -> resolves to
      ``scripts.verifiers.verifier_core``.
    * ``from scripts.verifiers import verifier_core`` ->
      ``module="scripts.verifiers"``, ``symbol="verifier_core"``
      -> the local name shadows the package name and resolves to
      ``scripts.verifiers.verifier_core``.  This is the only
      accepted re-export form.
    * ``import scripts.verifiers.verifier_core as core`` ->
      ``module="scripts.verifiers.verifier_core"``,
      ``symbol=None`` -> resolves to
      ``scripts.verifiers.verifier_core``.

    Returns ``None`` for any other binding shape (e.g. an
    unrelated package).
    """
    if _is_in_core_package(module):
        return module
    # Re-export: ``from parent import <core_package_basename>``
    if (
        symbol is not None
        and symbol == CORE_PACKAGE.rsplit(".", 1)[-1]
        and module + "." + symbol == CORE_PACKAGE
    ):
        return CORE_PACKAGE
    return None


def _classify_reference(
    node: ast.AST, bindings: dict[str, tuple[str, str | None]]
) -> _ResolvedUse | None:
    """Resolve a Name or Attribute to a verifier_core public symbol.

    Returns ``None`` for any reference that is NOT a real
    ``verifier_core`` consumer (local defs, unrelated imports,
    string literals, attribute chains through unrelated names,
    bare module references such as ``core`` without an attribute).
    """
    if isinstance(node, ast.Name):
        bound = bindings.get(node.id)
        if bound is None:
            return None
        module, symbol = bound
        effective = _resolve_module(module, symbol)
        if effective is None:
            return None
        # ``import X`` (without ``from``) creates a binding whose
        # symbol slot is None, and ``from parent import <core>``
        # also creates a binding whose effective module is the
        # core package but whose original symbol is the bare name
        # of that package (not a public symbol of the core).
        # In both cases a bare ``X`` reference is a module
        # reference, not a symbol use; only ``X.attr`` is.
        if (
            symbol is None
            or (symbol == CORE_PACKAGE.rsplit(".", 1)[-1]
                and module + "." + symbol == CORE_PACKAGE)
        ):
            return None
        return _ResolvedUse(local_name=node.id, symbol=symbol)
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        parts.append(cur.id)
        parts.reverse()
        bound = bindings.get(cur.id)
        if bound is None:
            return None
        module, symbol = bound
        effective = _resolve_module(module, symbol)
        if effective is None:
            return None
        # The attribute chain must be exactly "<root>.<symbol>" with
        # no intermediate parts.  ``verifier_core.foo`` is one level;
        # ``core.foo`` is one level.  Multi-level attribute chains
        # through ``verifier_core`` (e.g. ``verifier_core.sub.X``)
        # are out of scope: callers must import the submodule
        # explicitly via ``from ... import submodule`` first.
        if len(parts) != 2:
            return None
        return _ResolvedUse(local_name=cur.id, symbol=parts[1])
    return None


def _source_core_uses(source: str) -> set[str]:
    """Resolve a source string to the set of verifier_core symbols it uses.

    Exposed (no leading underscore on the name) so the audit tests
    can exercise the resolver without writing files into the repo.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    bindings = _import_bindings(tree)
    local_defs = _local_definition_names(tree)
    for shadowed in local_defs:
        bindings.pop(shadowed, None)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        resolved = _classify_reference(node, bindings)
        if resolved is not None:
            out.add(resolved.symbol)
    return out


def _file_core_uses(path: str) -> set[str] | None:
    """Return the set of verifier_core public symbols used in ``path``.

    Returns ``None`` when the file cannot be read.
    """
    full = REPO_ROOT / path
    try:
        source = full.read_text(encoding="utf-8")
    except OSError:
        return None
    return _source_core_uses(source)


def build_consumer_map(
    symbols: Iterable[str],
    symbol_modules: dict[str, str],
    included_paths: Iterable[str],
    test_paths: Iterable[str],
) -> list[Consumer]:
    symbol_set = set(symbols)
    prod_callers: dict[str, list[str]] = {s: [] for s in symbol_set}
    test_callers: dict[str, list[str]] = {s: [] for s in symbol_set}
    included = sorted(included_paths)
    tests = sorted(test_paths)
    for path in included:
        if _is_core_path(path):
            continue
        used = _file_core_uses(path)
        if used is None:
            continue
        for s in symbol_set & used:
            prod_callers[s].append(path)
    for path in tests:
        used = _file_core_uses(path)
        if used is None:
            continue
        for s in symbol_set & used:
            test_callers[s].append(path)
    consumers: list[Consumer] = []
    for s in symbol_set:
        prod = sorted(set(prod_callers[s]))
        test = sorted(set(test_callers[s]))
        if prod:
            cls = "PROVEN-REUSED"
        elif test:
            cls = "TEST-ONLY"
        else:
            cls = "UNUSED"
        consumers.append(
            Consumer(
                symbol=s,
                module=symbol_modules.get(s, ""),
                production_callers=tuple(prod),
                test_callers=tuple(test),
                classification=cls,
            )
        )
    consumers.sort(key=lambda c: (c.module, c.symbol))
    return consumers


def discover_test_paths() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "tests/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    out: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.endswith(".py"):
            out.append(line)
    out.sort()
    return out
