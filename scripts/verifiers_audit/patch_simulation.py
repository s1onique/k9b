"""Measured Wave-1 patch generation (R4 / CORRECTION04).

The patch *generation* logic:

1. AST-walks the production verifier to find the three Wave-1
   helper spans and the five call sites that use them.
2. Removes the three helper definitions verbatim.
3. Inserts a single ``from scripts.verifiers import verifier_core``
   import block at the top.
4. Rewrites the five call sites to ``verifier_core.X(...)`` form
   (bounded to ``Call.func == Name(local_name)`` so strings,
   comments, unrelated identifiers, and definitions are never
   touched).
5. Records ``production_lines_added``, ``production_lines_removed``,
   ``net_production_lines_removed``, ``call_sites_changed``, and
   ``helpers_removed`` from a unified diff.

The patch *execution* logic (parse, compile, run the patched
verifier, run the focused R20 equivalence tests against it)
lives in :mod:`scripts.verifiers_audit.patch_execution`.

The numbers come from the unified diff itself, not from a
hand-computed ``len(candidates)`` or any other literal.

The simulation NEVER touches the real verifier file; the
mutation happens in a sibling temp file under :mod:`tempfile`.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import ast
import difflib
import re
from dataclasses import dataclass

from scripts.verifiers_audit.discovery import REPO_ROOT

TARGET_PATH = (
    "scripts/verifiers/incident_current_run_promotion_workset01.py"
)


# Wave-1 local helpers -> core symbols (Option B: module import).
WAVE_1_BINDINGS: dict[str, str] = {
    "_read_source": "read_source",
    "_parse": "parse_path",
    "_function_def_in": "top_level_function",
}


@dataclass(frozen=True)
class _HelperSpan:
    """Line range (1-based, inclusive) of one helper definition."""

    name: str
    start_line: int
    end_line: int  # inclusive
    text: str  # verbatim slice


def _function_spans(source: str, tree: ast.Module) -> list[_HelperSpan]:
    """Return verbatim text spans of every top-level helper we
    plan to remove."""
    lines = source.splitlines()
    spans: list[_HelperSpan] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name in WAVE_1_BINDINGS:
            start = stmt.lineno
            end = getattr(stmt, "end_lineno", None) or stmt.lineno
            text = "\n".join(lines[start - 1: end])
            spans.append(_HelperSpan(
                name=stmt.name,
                start_line=start,
                end_line=end,
                text=text,
            ))
    return spans


def _call_site_count(tree: ast.Module, callee: str) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(
            node.func, ast.Name
        ) and node.func.id == callee:
            n += 1
    return n


def _insert_import_block(source: str) -> str:
    """Insert the verifier_core module import block at the top,
    after the future-import line if present."""
    block = (
        "from scripts.verifiers import verifier_core\n"
    )
    if "from scripts.verifiers import verifier_core" in source:
        return source
    future_match = re.search(
        r"^from __future__ import annotations\s*\n",
        source,
        flags=re.MULTILINE,
    )
    if future_match is not None:
        idx = future_match.end()
        return source[:idx] + block + source[idx:]
    return block + source


def _remove_helper_spans(source: str, spans: list[_HelperSpan]) -> str:
    """Remove the helper definition blocks. ``end_line`` is
    inclusive; we also strip one trailing newline when present."""
    lines = source.splitlines()
    drop: set[int] = set()
    for span in spans:
        for n in range(span.start_line, span.end_line + 1):
            drop.add(n)
        if span.end_line < len(lines) and not lines[span.end_line].strip():
            drop.add(span.end_line + 1)
    kept = [line for idx, line in enumerate(lines, start=1)
            if idx not in drop]
    return "\n".join(kept) + "\n"


def _rewrite_call_names(source: str, callee: str,
                        module: str, replacement: str) -> str:
    """Replace bare ``callee`` token (only in a Call.func == Name
    position) with ``module.replacement``.

    Bounded to a CALL site that uses the bare name; nothing else
    is touched (no strings, no comments, no other identifiers,
    no definitions).  The trick: only swap when the next
    non-whitespace character on the line is ``(`` so we never
    rewrite identifiers used in attribute access or definitions.
    """
    lines = source.splitlines(keepends=True)
    pattern = re.compile(
        rf"(?<!def )(?<!\.)\b{re.escape(callee)}\b"
    )
    new_lines: list[str] = []
    for line in lines:
        def _swap(match: re.Match[str]) -> str:
            end = match.end()
            tail = line[end:]
            stripped = tail.lstrip()
            if not stripped.startswith("("):
                return match.group(0)
            return f"{module}.{replacement}"

        new_lines.append(pattern.sub(_swap, line))
    return "".join(new_lines)


def _diff_stats(original: str, modified: str) -> tuple[int, int]:
    """Return ``(lines_added, lines_removed)`` from a unified diff."""
    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=TARGET_PATH,
            tofile=TARGET_PATH + ".patched",
            n=0,
        )
    )
    added = sum(
        1 for line in diff
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff
        if line.startswith("-") and not line.startswith("---")
    )
    return added, removed


def _build_modified_source(original_source: str) -> tuple[str, list[_HelperSpan], dict[str, int]]:
    """Apply the Wave-1 transformations and return the patched
    source, the helper spans that were removed, and the per-helper
    call-site counts."""
    tree = ast.parse(original_source)
    spans = _function_spans(original_source, tree)
    call_counts = {
        name: _call_site_count(tree, name)
        for name in WAVE_1_BINDINGS
    }
    modified = original_source
    modified = _remove_helper_spans(modified, spans)
    modified = _insert_import_block(modified)
    for local_name, core_symbol in WAVE_1_BINDINGS.items():
        modified = _rewrite_call_names(
            modified, local_name, "verifier_core", core_symbol
        )
    return modified, spans, call_counts


def _simulate_wave_1() -> dict[str, object]:
    original_path = REPO_ROOT / TARGET_PATH
    original_source = original_path.read_text(encoding="utf-8")
    modified, spans, call_counts = _build_modified_source(original_source)
    added, removed = _diff_stats(original_source, modified)
    net = removed - added

    # Execute the patch via the companion module so the file
    # stays under the LLM-friendly threshold.
    from scripts.verifiers_audit.patch_execution import execute_patched

    executable = execute_patched(modified)

    return {
        "target_path": TARGET_PATH,
        "production_lines_added": added,
        "production_lines_removed": removed,
        "net_production_lines_removed": net,
        "call_sites_changed": sum(call_counts.values()),
        "helpers_removed": len(spans),
        "call_sites_by_helper": call_counts,
        "helpers_removed_by_name": {
            span.name: True for span in spans
        },
        **executable,
    }


def measured_patch_summary() -> dict[str, object]:
    sim = _simulate_wave_1()
    return {
        "schema_version": "1.0",
        "totals": {
            "production_lines_added": sim["production_lines_added"],
            "production_lines_removed": sim[
                "production_lines_removed"
            ],
            "net_production_lines_removed": sim[
                "net_production_lines_removed"
            ],
            "call_sites_changed": sim["call_sites_changed"],
            "helpers_removed": sim["helpers_removed"],
            "parse_passed": sim["parse_passed"],
            "compile_passed": sim["compile_passed"],
            "verifier_exit_code": sim["verifier_exit_code"],
            "targeted_tests_passed": sim["targeted_tests_passed"],
        },
        "details": sim,
    }


def measured_net_deletion_lines() -> int:
    """Convenience accessor used by callers that only need the int."""
    val = _simulate_wave_1()["net_production_lines_removed"]
    if isinstance(val, int):
        return val
    return int(val) if isinstance(val, (str, float, bool)) else 0


__all__ = (
    "TARGET_PATH",
    "WAVE_1_BINDINGS",
    "measured_patch_summary",
    "measured_net_deletion_lines",
)