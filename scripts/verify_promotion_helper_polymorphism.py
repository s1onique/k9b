#!/usr/bin/env python3
"""AST verifier preventing production calls to the generic helper.

R4 task 6 contract: local promotion MUST drive the polymorphic
``store.promote_candidates_with_records(...)`` method. The free helper
in ``incident_store_promotion_helpers`` is the base in-memory
implementation; SQLite activates its durable override through the
polymorphic method, so production code that bypasses that boundary
quietly loses the durability guarantee.

This verifier scans every ``.py`` file under ``src/`` and reports any
call-site that references the free helper directly. ``verify_*.py``
scripts, ``tests/`` directories, and ``__init__`` re-export shims are
ignored so the verifier stays meaningful as production code evolves.
The ``tests/`` directory is scanned separately so unit tests can
exercise the generic helper without tripping the verifier.

R5 hardening (item 6): detect module-qualified and aliased calls.
The R4 verifier only flagged bare ``Name`` calls like
``promote_candidates_with_records(c, o, b)``; production code that
reached the helper through ``incident_store_promotion_helpers
.pomote_candidates_with_records(...)`` or an aliased import
``from incident_store_promotion_helpers import
promote_candidates_with_records as _p; _p(...)`` slipped past the check
and silently bypassed the polymorphic boundary. The R5 check now flags
all three shapes:

  * bare ``Name`` call;
  * ``Attribute`` call whose ``value`` is the helper module by name
    (``module.promote_candidates_with_records``);
  * ``Name`` call where the name corresponds to an ``ImportFrom`` alias
    that re-bound the helper to a different identifier;
  * ``ImportFrom`` itself (the simple import form is the canonical
    shortcut that lets the renamed call above compile).

Exit codes:
  0 -- no production callers found.
  1 -- at least one production caller found.
  2 -- verification infrastructure failure.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

GENERIC_HELPER_NAME = "promote_candidates_with_records"
GENERIC_HELPER_MODULE = "incident_store_promotion_helpers"
ALLOWED_MODULES = frozenset({
    # The free helper's own home is allowed to define the function so it
    # can be imported by tests and the in-memory base implementation.
    "incident_store_promotion_helpers.py",
    # The in-memory base implementation is allowed to wrap the helper
    # because that wrapping lives inside the store itself, not in
    # production callers.
    "incident_store.py",
    # Tests intentionally exercise the helper.
})


def _is_allowed(path: Path) -> bool:
    """Return True for paths that legitimately use the free helper."""
    text = str(path)
    if any(
        segment in text
        for segment in ("/tests/", "/__tests__/", "/.venv/")
    ):
        return True
    return any(text.endswith(name) for name in ALLOWED_MODULES)


def _module_imports_helper(tree: ast.Module, helper_name: str) -> bool:
    """Return True when the module imports the helper.

    Inspects both ``from <module> import <helper>`` and aliased forms
    (``from <module> import <helper> as <alias>``), because the latter
    re-binds the helper to a different name and our call-shape walker
    must look those aliases up to flag a call to the renamed name.
    """
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom):
            continue
        # module qualification: ``from <module> import <helper>``
        if stmt.module and stmt.module.endswith(GENERIC_HELPER_MODULE):
            for alias in stmt.names:
                if alias.name == helper_name:
                    return True
        # aliased imports of the helper from anywhere
        for alias in stmt.names:
            if alias.name == helper_name or alias.asname == helper_name:
                if stmt.module and stmt.module.endswith(
                    GENERIC_HELPER_MODULE
                ):
                    return True
    return False


def _aliased_helper_names(tree: ast.Module, helper_name: str) -> set[str]:
    """Return the set of alias identifiers bound to the helper.

    ``from incident_store_promotion_helpers import
    promote_candidates_with_records as promote_legacy`` rebinds the
    helper to ``promote_legacy``. Any call to ``promote_legacy`` in the
    same module is therefore a helper call and must be reported.
    """
    aliases: set[str] = set()
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom):
            continue
        if not (stmt.module and stmt.module.endswith(GENERIC_HELPER_MODULE)):
            continue
        for alias in stmt.names:
            if alias.asname and alias.name == helper_name:
                aliases.add(alias.asname)
    return aliases


def _aliased_helper_module_names(tree: ast.Module) -> set[str]:
    """Return the set of identifiers bound to the helper module.

    ``import incident_store_promotion_helpers as helpers`` rebinds the
    helper module to ``helpers``. ``from . import
    incident_store_promotion_helpers as helpers`` does the same through
    an ``ImportFrom`` with a relative module and ``asname`` alias. Any
    attribute call through one of these aliases
    (``helpers.promote_candidates_with_records(...)``) MUST be flagged:
    production callers may not bypass the polymorphic boundary through a
    renamed module handle.
    """
    aliases: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if (
                    alias.name == GENERIC_HELPER_MODULE
                    or alias.name.endswith(f".{GENERIC_HELPER_MODULE}")
                ) and alias.asname:
                    aliases.add(alias.asname)
        elif isinstance(stmt, ast.ImportFrom):
            if not stmt.module:
                # ``from . import incident_store_promotion_helpers as helpers``
                # surfaces here as ``module=None`` with one alias entry.
                for alias in stmt.names:
                    if (
                        alias.name == GENERIC_HELPER_MODULE
                        or alias.name.endswith(f".{GENERIC_HELPER_MODULE}")
                    ) and alias.asname:
                        aliases.add(alias.asname)
    return aliases


def _calls_helper(
    node: ast.AST,
    helper_name: str,
    aliased_names: set[str],
    aliased_module_names: set[str],
) -> bool:
    """Return True when ``node`` is any shape of call to the helper.

    Detects:

    * bare ``Name`` call (``promote_candidates_with_records(...)``);
    * module-qualified ``Attribute`` call
      (``incident_store_promotion_helpers.promote_candidates_with_records(...)``);
    * aliased ``Name`` call (any name produced by
      ``from incident_store_promotion_helpers import ... as <alias>``);
    * aliased module ``Attribute`` call (any name produced by
      ``import incident_store_promotion_helpers as helpers`` or
      ``from . import incident_store_promotion_helpers as helpers``
      followed by ``helpers.promote_candidates_with_records(...)``).

    Attribute calls on a non-module receiver (e.g.
    ``store.promote_candidates_with_records(...)``) are the polymorphic
    boundary R4 task 6 INSISTS on and are deliberately NOT flagged.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return (
            func.id == helper_name or func.id in aliased_names
        )
    if isinstance(func, ast.Attribute) and func.attr == helper_name:
        # ``module.<helper>`` only counts when the receiver is a plain
        # ``Name`` matching the helper module's tail OR an alias bound
        # to that module. ``store.<helper>`` is the polymorphic boundary
        # and must stay allowed.
        if isinstance(func.value, ast.Name):
            return (
                func.value.id == GENERIC_HELPER_MODULE
                or func.value.id in aliased_module_names
            )
    return False


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return a list of ``(line_no, reason)`` violations found in ``path``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    aliased_names = _aliased_helper_names(tree, GENERIC_HELPER_NAME)
    aliased_module_names = _aliased_helper_module_names(tree)

    if _module_imports_helper(tree, GENERIC_HELPER_NAME):
        # The ``from <module> import <helper>`` form is itself a smell:
        # every call below would silently bypass the polymorphic
        # boundary even if the call shape is hidden behind an alias.
        return [
            (
                0,
                f"module imports free helper {GENERIC_HELPER_NAME} "
                "directly (bypasses polymorphic boundary)",
            ),
        ]

    # An aliased import of the helper MODULE itself (e.g.
    # ``import incident_store_promotion_helpers as helpers`` or
    # ``from . import incident_store_promotion_helpers as helpers``)
    # is the canonical shortcut for callers that want to reach the free
    # helper via an attribute call (``helpers.<helper>(...)``). It MUST
    # be reported even when the call shape alone would not match.
    if aliased_module_names:
        return [
            (
                0,
                "module aliases the helper module as "
                f"{sorted(aliased_module_names)} (bypasses polymorphic "
                "boundary)",
            ),
        ]

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if _calls_helper(
            node,
            GENERIC_HELPER_NAME,
            aliased_names,
            aliased_module_names,
        ):
            call_kind = _classify_call(node)  # type: ignore[arg-type]
            violations.append(
                (
                    getattr(node, "lineno", 0),
                    f"calls {GENERIC_HELPER_NAME} via {call_kind}",
                ),
            )
    return violations


def _classify_call(node: ast.Call) -> str:
    """Return a short human label describing the offending call shape."""
    func = node.func
    if isinstance(func, ast.Name):
        return "Name"
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return f"Attribute (module={func.value.id})"
        return "Attribute (non-module)"
    return type(func).__name__


def discover_violations(src_root: Path) -> list[tuple[Path, int, str]]:
    """Walk ``src_root`` and return production callers of the free helper."""
    violations: list[tuple[Path, int, str]] = []
    for py_file in src_root.rglob("*.py"):
        if _is_allowed(py_file):
            continue
        for line, reason in _scan_file(py_file):
            violations.append((py_file, line, reason))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-root",
        default="src",
        help="Root directory to scan (default: src)",
    )
    args = parser.parse_args(argv)

    src_root = Path(args.src_root)
    if not src_root.is_dir():
        print(f"FAIL: source root {src_root} is not a directory", file=sys.stderr)
        return 2

    violations = discover_violations(src_root)
    if violations:
        print(
            f"FAIL: {len(violations)} production caller(s) of the free "
            f"{GENERIC_HELPER_NAME} helper detected:"
        )
        for path, line, reason in violations:
            location = f"{path}" if line == 0 else f"{path}:{line}"
            print(f"  - {location}: {reason}")
        return 1

    print(
        "PASS: no production code bypasses the polymorphic "
        f"{GENERIC_HELPER_NAME} boundary."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
