"""Small, test-only AST/source helpers for promotion architecture guards."""
from __future__ import annotations

import ast
from pathlib import Path


def repository_root(anchor: Path) -> Path:
    return anchor.resolve().parents[2]

def load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def parse_source(path: Path) -> ast.Module:
    return ast.parse(load_source(path), filename=str(path))

def find_functions(tree: ast.AST, name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]

def physical_lines(path: Path) -> int:
    return len(load_source(path).splitlines())
