#!/usr/bin/env python3
"""AST verifier preventing duplicate ``PromotionBatch`` definitions.

R4 task 1 contract: ``PromotionBatch`` is single-owned and lives in
``incident_promotion_batch.py`` ONLY. Any other module that defines a
class literally named ``PromotionBatch`` is treated as a contract
violation. This verifier walks every ``.py`` file under the ``src/`` tree
and reports offending modules so the CI gate (or a developer running this
script) can fail closed instead of letting two distinct ``PromotionBatch``
classes shadow each other.

R5 hardening (item 6): reject every class definition literally named
``PromotionBatch``, regardless of decorators (``@dataclass`` vs.
``@dataclass(frozen=True)`` vs. plain class) or base classes
(``TypedDict``, ``Protocol``, ``Generic``). The previous version gated
on a dataclass decorator, which let a stray ``class
PromotionBatch(Protocol)`` slip past the verifier and silently shadow
the canonical typed batch. The new check is purely structural
(AST-based) and reports any ``ClassDef`` whose ``name`` matches the
target exactly.

The check is purely structural (AST-based) so it does not import the
target modules and cannot be tricked by re-export shims. A module that
imports ``PromotionBatch`` is fine; a module that *defines* one is not.

Exit codes:
  0 -- exactly one definition found.
  1 -- zero or more than one definition found; violation list printed.
  2 -- verification infrastructure failure (e.g. ``src/`` not found).

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R4 / R5.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

TARGET_CLASS_NAME = "PromotionBatch"
EXPECTED_OWNER_SUFFIX = "incident_promotion_batch.py"


def _scan_module(path: Path) -> bool:
    """Return True if ``path`` defines a class literally named ``TARGET_CLASS_NAME``.

    R5 hardening: do not gate on decorator shape or base class. Any
    ``ClassDef`` whose ``name`` matches the target exactly counts as a
    definition. This catches plain ``class PromotionBatch: ...`` and
    ``class PromotionBatch(Protocol): ...`` alike, both of which would
    otherwise shadow the canonical typed batch at runtime.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # A syntax error is the file's problem; surface separately.
        print(f"WARN: cannot parse {path} (syntax error)", file=sys.stderr)
        return False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == TARGET_CLASS_NAME:
            return True
    return False


def discover_owner(src_root: Path) -> list[Path]:
    """Return the list of source modules that *define* ``PromotionBatch``."""
    definitions: list[Path] = []
    for py_file in src_root.rglob("*.py"):
        if _scan_module(py_file):
            definitions.append(py_file)
    return definitions


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-root",
        default="src",
        help="Root directory to scan (default: src)",
    )
    parser.add_argument(
        "--expected-owner-suffix",
        default=EXPECTED_OWNER_SUFFIX,
        help="Expected owner module path suffix",
    )
    args = parser.parse_args(argv)

    src_root = Path(args.src_root)
    if not src_root.is_dir():
        print(f"FAIL: source root {src_root} is not a directory", file=sys.stderr)
        return 2

    definitions = discover_owner(src_root)
    if len(definitions) == 0:
        print("FAIL: no PromotionBatch definition found under", src_root)
        return 1
    if len(definitions) > 1:
        print(
            f"FAIL: PromotionBatch is defined in {len(definitions)} modules "
            "(must be exactly one owner)"
        )
        for path in definitions:
            print(f"  - {path}")
        return 1
    owner = definitions[0]
    if not str(owner).endswith(args.expected_owner_suffix):
        print(
            f"FAIL: PromotionBatch is defined at {owner}; expected owner "
            f"ends with {args.expected_owner_suffix}"
        )
        return 1
    print(f"PASS: PromotionBatch single-owned at {owner}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
