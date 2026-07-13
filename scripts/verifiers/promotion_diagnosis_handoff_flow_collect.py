"""Collection helpers for SEAM01 promotion-diagnosis handoff verifier.

This module handles:
- AST traversal to collect classes, functions, and imports
- Annotation-to-string conversion for type representation
- Class method detection for provenance tracking
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff_model import (
    ClassInfo,
    FunctionInfo,
    ImportInfo,
)


def annotation_to_str(annotation: ast.AST) -> str | None:
    """Convert an annotation AST node to a string representation."""
    if isinstance(annotation, ast.Name):
        return annotation.id
    elif isinstance(annotation, ast.Constant):
        return repr(annotation.value)
    elif isinstance(annotation, ast.Attribute):
        base = annotation_to_str(annotation.value)
        if base:
            return f"{base}.{annotation.attr}"
    elif isinstance(annotation, ast.Subscript):
        base = annotation_to_str(annotation.value)
        if base:
            if isinstance(annotation.slice, ast.Index):
                slice_val = annotation_to_str(annotation.slice.value)
            else:
                slice_val = annotation_to_str(annotation.slice)
            if slice_val:
                return f"{base}[{slice_val}]"
    elif isinstance(annotation, ast.BinOp):
        left = annotation_to_str(annotation.left)
        right = annotation_to_str(annotation.right)
        if left and right:
            if isinstance(annotation.op, ast.BitOr):
                return f"{left} | {right}"
    elif isinstance(annotation, ast.Constant) and annotation.value is None:
        return "None"
    return None


def _has_classmethod_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function has a @classmethod decorator."""
    for decorator in func_node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "classmethod":
            return True
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name) and decorator.func.id == "classmethod":
                return True
    return False


def collect_classes(tree: ast.AST) -> dict[str, ClassInfo]:
    """Collect all class definitions with their line ranges."""
    classes: dict[str, ClassInfo] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes[node.name] = ClassInfo(
                name=node.name,
                line_start=node.lineno or 0,
                line_end=node.end_lineno or 0,
            )
    return classes


def collect_functions(tree: ast.AST) -> list[FunctionInfo]:
    """Collect all function definitions with their parameter annotations and return types."""
    functions: list[FunctionInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params: dict[str, str | None] = {}
            is_classmethod = _has_classmethod_decorator(node)
            first_param = None
            if node.args.args:
                first_param = node.args.args[0].arg
            for arg in node.args.args:
                ann = None
                if arg.annotation:
                    ann = annotation_to_str(arg.annotation)
                params[arg.arg] = ann
            for arg in node.args.posonlyargs:
                ann = None
                if arg.annotation:
                    ann = annotation_to_str(arg.annotation)
                params[arg.arg] = ann
            for arg in node.args.kwonlyargs:
                ann = None
                if arg.annotation:
                    ann = annotation_to_str(arg.annotation)
                params[arg.arg] = ann
            if node.args.vararg and node.args.vararg.annotation:
                params[node.args.vararg.arg] = annotation_to_str(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation:
                params[node.args.kwarg.arg] = annotation_to_str(node.args.kwarg.annotation)
            return_annotation = None
            if node.returns:
                return_annotation = annotation_to_str(node.returns)
            functions.append(FunctionInfo(
                name=node.name,
                line_start=node.lineno or 0,
                line_end=node.end_lineno or 0,
                params=params,
                return_annotation=return_annotation,
                is_classmethod=is_classmethod,
                first_param=first_param,
            ))
    return functions


def collect_imports(tree: ast.AST) -> list[ImportInfo]:
    """Collect all import statements for identity verification."""
    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    name=alias.name,
                    alias=alias.asname,
                    line_start=node.lineno or 0,
                    line_end=node.end_lineno or 0,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or None
            for alias in node.names:
                imports.append(ImportInfo(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    line_start=node.lineno or 0,
                    line_end=node.end_lineno or 0,
                ))
    return imports
