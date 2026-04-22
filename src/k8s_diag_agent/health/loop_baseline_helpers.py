"""Baseline policy helpers for the health loop.

Extracts baseline/cohort/policy helper functions from loop.py into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the policy resolution logic that:
1. Normalizes drift category lists
2. Loads baseline policies with caching
3. Parses cohort baselines from config
4. Resolves target baseline paths
5. Determines policy for a target

These are pure helpers with no runner logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .baseline import (
    BaselinePolicy,
    _str_or_none,
    resolve_baseline_policy_path,
)


def _normalize_category_list(value: Any | None) -> tuple[str, ...]:
    """Normalize a drift category value into a sorted tuple of canonical strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = _str_or_none(value)
        return (normalized,) if normalized else ()
    if isinstance(value, Sequence):
        categories: list[str] = []
        for item in value:
            normalized = _str_or_none(item)
            if normalized:
                categories.append(normalized)
        return tuple(dict.fromkeys(categories))
    return ()


def _load_baseline_policy_from_path(
    path: Path, cache: dict[Path, BaselinePolicy]
) -> BaselinePolicy:
    """Load a baseline policy from disk, using the provided cache for deduplication."""
    if path in cache:
        return cache[path]
    policy = BaselinePolicy.load_from_file(path)
    cache[path] = policy
    return policy


def _parse_cohort_baselines(
    raw: Any | None,
    directory: Path,
    cache: dict[Path, BaselinePolicy],
) -> dict[str, tuple[BaselinePolicy, Path]]:
    """Parse cohort baselines from config structure into resolved policy map."""
    cohort_map: dict[str, tuple[BaselinePolicy, Path]] = {}
    if not raw:
        return cohort_map
    entries: list[tuple[str, str]] = []
    if isinstance(raw, Mapping):
        for cohort, value in raw.items():
            cohort_name = _str_or_none(cohort if isinstance(cohort, str) else str(cohort))
            path_value = _str_or_none(value if isinstance(value, str) else str(value))
            if cohort_name and path_value:
                entries.append((cohort_name, path_value))
    elif isinstance(raw, Sequence):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            cohort_name = _str_or_none(item.get("cohort")) or _str_or_none(item.get("name"))
            path_value = _str_or_none(item.get("path")) or _str_or_none(item.get("baseline_policy_path"))
            if cohort_name and path_value:
                entries.append((cohort_name, path_value))
    for cohort_name, path_value in entries:
        resolved = resolve_baseline_policy_path(directory, path_value)
        policy = _load_baseline_policy_from_path(resolved, cache)
        cohort_map[cohort_name] = (policy, resolved)
    return cohort_map


def _resolve_target_baseline_path(
    directory: Path,
    explicit: str | None,
    cohort: str | None,
    cohort_map: dict[str, tuple[BaselinePolicy, Path]],
    default_path: Path | None,
) -> Path | None:
    """Resolve the baseline path for a target, preferring explicit > cohort > default."""
    if explicit:
        return resolve_baseline_policy_path(directory, explicit)
    if cohort and cohort in cohort_map:
        return cohort_map[cohort][1]
    return default_path


def _policy_for_target(
    baseline_path_str: str | None,
    cohort: str | None,
    default_policy: BaselinePolicy,
    default_path: Path | None,
    cohort_map: dict[str, tuple[BaselinePolicy, Path]],
    cache: dict[Path, BaselinePolicy],
) -> tuple[BaselinePolicy, Path | None]:
    """Determine the effective policy and path for a target."""
    if baseline_path_str:
        resolved_path = Path(baseline_path_str)
        policy = _load_baseline_policy_from_path(resolved_path, cache)
        return policy, resolved_path
    if cohort and cohort in cohort_map:
        return cohort_map[cohort]
    return default_policy, default_path
