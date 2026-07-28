"""Shared helpers for Docker Harbor cache regression tests.

This module contains pure helper functions for loading and parsing GitHub
workflow YAML files. It is intentionally NOT named test_*.py so pytest
will not collect it as a test module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
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

    # Extract condition (everything before the first &&)
    and_match = re.match(r"(.+?)\s*&&\s*", inner)
    if not and_match:
        raise CacheSpecParseError(f"No condition before format() in: {value}")

    condition = and_match.group(1).strip()

    # Get the rest after condition &&
    after_condition = inner[and_match.end() :].strip()

    # Find the format(...) call - match format('template', args)
    # We need to match the template string and then parse args properly
    format_pattern = r"format\(\s*'([^']*)'\s*,"
    format_match = re.match(format_pattern, after_condition)
    if not format_match:
        raise CacheSpecParseError(f"No valid format() call in expression: {value}")

    template_str = format_match.group(1)
    args_start = after_condition[format_match.end() :]

    # Parse format arguments - split by commas at depth 0
    # We need to find the closing ) that matches the format(
    format_arguments: list[str] = []
    paren_depth = 1  # We've already passed the opening ( of format
    current_arg = []
    i = 0

    while i < len(args_start):
        c = args_start[i]
        if c == "(":
            paren_depth += 1
            current_arg.append(c)
        elif c == ")":
            paren_depth -= 1
            if paren_depth == 0:
                # End of format() call
                break
            current_arg.append(c)
        elif c == "," and paren_depth == 1:
            # Comma at depth 1 (not inside nested parens)
            arg = "".join(current_arg).strip()
            if arg:
                format_arguments.append(arg)
            current_arg = []
        else:
            current_arg.append(c)
        i += 1

    # Don't forget the last argument
    arg = "".join(current_arg).strip()
    if arg:
        format_arguments.append(arg)

    # Check for || '' fallback (empty false branch)
    after_format = args_start[i + 1 :].strip() if i < len(args_start) else ""
    conditional_empty_fallback = "|| ''" in after_format or '|| ""' in after_format

    # Parse the template string to extract backend, ref, mode
    spec_result = _parse_literal_cache_spec(template_str)

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


# =============================================================================
# Strict Harbor cache policy validator
# Validates parsed specs against Harbor policy requirements
# =============================================================================


class CacheDirection(Enum):
    """Direction of cache operation."""

    FROM = "from"
    TO = "to"


class CacheContractValidationError(ValueError):
    """Raised when a cache specification violates Harbor policy."""

    pass


def validate_harbor_registry_cache_contract(
    spec: RegistryCacheSpec,
    direction: CacheDirection,
) -> None:
    """Validate a parsed cache spec against Harbor policy requirements.

    For cache-from:
    - backend: registry
    - condition: inputs.registry_cache_read_enabled
    - ref_template: {0}/{1}/cache/{2}:buildcache
    - format_arguments: inputs.registry, inputs.harbor_project, inputs.image_name
    - mode: absent
    - conditional_empty_fallback: True

    For cache-to:
    - backend: registry
    - condition: inputs.registry_cache_write_enabled
    - ref_template: {0}/{1}/cache/{2}:buildcache
    - format_arguments: inputs.registry, inputs.harbor_project, inputs.image_name
    - mode: max
    - conditional_empty_fallback: True

    Raises:
        CacheContractValidationError: If any policy requirement is violated

    Examples:
        >>> spec = parse_registry_cache_spec(
        ...     "${{ inputs.registry_cache_read_enabled && "
        ...     "format('type=registry,ref={0}/{1}/cache/{2}:buildcache', "
        ...     "inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        ... )
        >>> validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)
        # No exception = valid
    """
    # Validate backend is registry
    if spec.backend != "registry":
        raise CacheContractValidationError(f"Cache {direction.value} must use backend=registry, got: {spec.backend}")

    # Validate conditional_empty_fallback
    if not spec.conditional_empty_fallback:
        raise CacheContractValidationError(f"Cache {direction.value} must have empty false branch (|| ''), got: nonempty or missing")

    # Direction-specific validation
    if direction == CacheDirection.FROM:
        _validate_cache_from_policy(spec)
    else:
        _validate_cache_to_policy(spec)


def _validate_cache_from_policy(spec: RegistryCacheSpec) -> None:
    """Validate cache-from policy requirements."""
    # Validate condition
    if spec.condition != "inputs.registry_cache_read_enabled":
        raise CacheContractValidationError(f"Cache-from condition must be 'inputs.registry_cache_read_enabled', got: {spec.condition}")

    # Validate ref_template ends with :buildcache
    if not spec.ref_template.endswith(":buildcache"):
        raise CacheContractValidationError(f"Cache-from ref_template must end with ':buildcache', got: {spec.ref_template}")

    # Validate format arguments
    expected_args = (
        "inputs.registry",
        "inputs.harbor_project",
        "inputs.image_name",
    )
    if spec.format_arguments != expected_args:
        raise CacheContractValidationError(f"Cache-from format_arguments must be {expected_args}, got: {spec.format_arguments}")

    # Validate no mode for cache-from
    if spec.mode is not None:
        raise CacheContractValidationError(f"Cache-from must not have mode, got: {spec.mode}")


def _validate_cache_to_policy(spec: RegistryCacheSpec) -> None:
    """Validate cache-to policy requirements."""
    # Validate condition
    if spec.condition != "inputs.registry_cache_write_enabled":
        raise CacheContractValidationError(f"Cache-to condition must be 'inputs.registry_cache_write_enabled', got: {spec.condition}")

    # Validate ref_template ends with :buildcache
    if not spec.ref_template.endswith(":buildcache"):
        raise CacheContractValidationError(f"Cache-to ref_template must end with ':buildcache', got: {spec.ref_template}")

    # Validate format arguments
    expected_args = (
        "inputs.registry",
        "inputs.harbor_project",
        "inputs.image_name",
    )
    if spec.format_arguments != expected_args:
        raise CacheContractValidationError(f"Cache-to format_arguments must be {expected_args}, got: {spec.format_arguments}")

    # Validate mode is max
    if spec.mode != "max":
        raise CacheContractValidationError(f"Cache-to mode must be 'max', got: {spec.mode}")
