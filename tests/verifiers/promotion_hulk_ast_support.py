"""Canonical AST/source helpers for promotion verifier guards."""

from __future__ import annotations

import ast
from pathlib import Path


def repository_root(anchor: Path) -> Path:
    return anchor.resolve().parents[2]


def load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_source(path: Path) -> ast.Module:
    return ast.parse(load_source(path), filename=str(path))


def find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def find_functions(tree: ast.AST, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]


def calls_in_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    return [node for node in ast.walk(func) if isinstance(node, ast.Call)]


def call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def imports_from(tree: ast.Module) -> list[ast.ImportFrom]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]


def module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def function_bodies(text: str) -> dict[str, list[ast.stmt]]:
    return {node.name: list(node.body) for node in ast.walk(ast.parse(text)) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def assignment_targets(stmt: ast.stmt) -> list[str]:
    targets: list[str] = []
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            targets.append(ast.unparse(target))
    elif isinstance(stmt, ast.AugAssign):
        targets.append(ast.unparse(stmt.target))
    return targets


BATCH_MUTATION_FIELDS = (
    "total_scanned",
    "total_firing",
    "total_opened_incidents",
    "total_updated_incidents",
    "total_skipped_duplicates",
    "total_unique_candidate_count",
    "total_errors",
    "last_promotion_mode",
    "last_incident_access_mode",
    "last_source_kind",
    "last_promotion_scan_scope",
)


def statements_contain_mutation(body: list[ast.stmt], fields: tuple[str, ...] = BATCH_MUTATION_FIELDS) -> bool:
    for stmt in body:
        if any(target == field or target.endswith(f".{field}") for target in assignment_targets(stmt) for field in fields):
            return True
    return False


def physical_lines(path: Path) -> int:
    return len(load_source(path).splitlines())


def scoped_dispatch_result_to_accumulator_handoff_used(tree: ast.Module) -> bool:
    """Return whether the typed accumulator-handoff adapter is referenced."""
    return any((isinstance(node, ast.Name) and node.id == "scoped_dispatch_result_to_accumulator_handoff") or (isinstance(node, ast.Attribute) and node.attr == "scoped_dispatch_result_to_accumulator_handoff") for node in ast.walk(tree))
