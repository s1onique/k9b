"""Shared helpers for Docker Harbor cache regression tests.

This module contains pure helper functions for loading and parsing GitHub
workflow YAML files. It is intentionally NOT named test_*.py so pytest
will not collect it as a test module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# Paths to workflow files that use docker/build-push-action
HARBOR_BUILD_IMAGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "harbor-build-image.yml"
K9B_IMAGE_BUILDER_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "k9b-image-builder.yml"
OTEL_DEMO_LIVE_LAB_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "k9b-otel-demo-live-lab.yml"


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def find_build_push_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Find all docker/build-push-action steps in a workflow."""
    steps = []
    for job_name, job in workflow.get("jobs", {}).items():
        job_steps = job.get("steps", [])
        for step in job_steps:
            if step.get("uses", "").startswith("docker/build-push-action"):
                steps.append(step)
    return steps


def extract_build_section(content: str, job_name: str) -> str:
    """Extract a job section from workflow YAML content."""
    build_start = content.find(f"{job_name}:")
    if build_start == -1:
        return ""
    next_marker = content.find("\n  # ======", build_start)
    if next_marker == -1:
        next_marker = len(content)
    return content[build_start:next_marker]


# =============================================================================
# Semantic cache spec parser
# Supports both literal and conditional GitHub format() expressions
# =============================================================================


@dataclass(frozen=True, slots=True)
class RegistryCacheSpec:
    """Parsed representation of a BuildKit registry cache specification."""

    backend: str
    ref_template: str
    mode: str | None = None
    condition: str | None = None
    format_arguments: tuple[str, ...] = ()
    conditional_empty_fallback: bool = False


class CacheSpecParseError(ValueError):
    """Raised when a cache specification cannot be parsed."""

    pass


def _parse_literal_cache_spec(value: str) -> RegistryCacheSpec:
    """Parse a literal registry cache specification.

    Examples:
        type=registry,ref=registry/project/cache/image:buildcache
        type=registry,ref=registry/project/cache/image:buildcache,mode=max
    """
    value = value.strip()
    if not value:
        raise CacheSpecParseError("Empty cache specification")

    parts = value.split(",")
    backend: str | None = None
    ref_template: str | None = None
    mode: str | None = None

    for part in parts:
        part = part.strip()
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip()
        val = val.strip()

        if key == "type":
            backend = val
        elif key == "ref":
            ref_template = val
        elif key == "mode":
            mode = val

    if backend is None:
        raise CacheSpecParseError(f"Missing 'type' in: {value}")
    if ref_template is None:
        raise CacheSpecParseError(f"Missing 'ref' in: {value}")
    if not ref_template:
        raise CacheSpecParseError(f"Empty 'ref' in: {value}")

    return RegistryCacheSpec(
        backend=backend,
        ref_template=ref_template,
        mode=mode,
        conditional_empty_fallback=False,
    )


def _parse_conditional_format(value: str) -> RegistryCacheSpec:
    """Parse a conditional GitHub format() expression.

    Supports the bounded shape:
        ${{ condition && format('<spec>', arg0, ...) || '' }}

    Returns a RegistryCacheSpec with condition and format_arguments populated.
    """

    value = value.strip()

    # Check for GitHub expression wrapper
    if not (value.startswith("${{") and value.endswith("}}")):
        raise CacheSpecParseError(f"Not a GitHub expression: {value}")

    # Strip ${{ and }} to get the inner expression
    inner = value[3:-2].strip()

    # Parse: <condition> && format('<spec>', arg0, ...) || ''
    # Find the format(...) call using regex
    format_match = re.search(
        r"format\(\s*'([^']*)'\s*,\s*(.+)\)",
        inner,
        re.DOTALL,
    )
    if not format_match:
        raise CacheSpecParseError(f"No valid format() call in expression: {value}")

    template_str = format_match.group(1)
    args_str = format_match.group(2).strip()

    # Extract condition (everything before the first &&)
    and_match = re.match(r"(.+?)\s*&&", inner)
    if not and_match:
        raise CacheSpecParseError(f"No condition before format() in: {value}")

    condition = and_match.group(1).strip()

    # Parse format arguments - split by commas at depth 0
    format_arguments: list[str] = []
    paren_depth = 0
    current_arg = []

    for c in args_str:
        if c == "(":
            paren_depth += 1
            current_arg.append(c)
        elif c == ")":
            paren_depth -= 1
            current_arg.append(c)
        elif c == "," and paren_depth == 0:
            arg = "".join(current_arg).strip()
            if arg:
                format_arguments.append(arg)
            current_arg = []
        else:
            current_arg.append(c)

    # Don't forget the last argument
    arg = "".join(current_arg).strip()
    if arg:
        format_arguments.append(arg)

    # Parse the template string to extract backend, ref, mode
    spec_result = _parse_literal_cache_spec(template_str)

    # Check for || '' fallback (empty false branch)
    conditional_empty_fallback = "|| ''" in inner or '|| ""' in inner

    return RegistryCacheSpec(
        backend=spec_result.backend,
        ref_template=spec_result.ref_template,
        mode=spec_result.mode,
        condition=condition,
        format_arguments=tuple(format_arguments),
        conditional_empty_fallback=conditional_empty_fallback,
    )


def parse_registry_cache_spec(value: str) -> RegistryCacheSpec:
    """Parse a registry cache specification.

    Supports:
    1. Literal specifications:
       type=registry,ref=registry/project/cache/image:buildcache
       type=registry,ref=registry/project/cache/image:buildcache,mode=max

    2. Conditional GitHub format() expressions:
       ${{ condition && format('type=registry,ref=...', inputs.x, inputs.y) || '' }}

    Args:
        value: The cache-from or cache-to YAML value

    Returns:
        RegistryCacheSpec with parsed components

    Raises:
        CacheSpecParseError: If the value cannot be parsed

    Examples:
        >>> spec = parse_registry_cache_spec(
        ...     "type=registry,ref=harbor/k9b/cache/image:buildcache"
        ... )
        >>> spec.backend
        'registry'
        >>> spec.ref_template
        'harbor/k9b/cache/image:buildcache'
    """
    value = str(value).strip()

    if not value:
        raise CacheSpecParseError("Empty cache specification")

    if value.startswith("${{"):
        return _parse_conditional_format(value)
    else:
        return _parse_literal_cache_spec(value)
