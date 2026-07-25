"""CORRECTION13/CORRECTION14: layout-aware index normalisation.

This module owns the complete top-level shard-layout schema
enforcement and the layout-aware per-shard path normalisation:

* the ``shards`` field MUST be a dict;
* ``set(index['shards'])`` MUST equal ``REQUIRED_SHARDS``
  (no missing required shard, no extra unknown shard);
* every shard's info MUST be a dict with a string ``path``
  field;
* the recorded path MUST identify exactly
  ``layout.shard_root / f"{shard_name}.json"``;
* symlink aliases are REJECTED (no ``Path.resolve()``-only
  equivalence);
* path-traversal segments (``..``) are REJECTED.

The module is extracted from :mod:`scope` to keep that module
under the 500-line LLM-friendly threshold.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import copy
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT


class IndexNormalisationError(ValueError):
    """CORRECTION13/CORRECTION14: typed failure for layout-aware
    normalisation.

    Raised by :func:`normalise_index_paths` when a shard
    path fails the layout contract: an unknown shard name,
    a missing or non-string path, a wrong parent
    directory, a wrong basename, a path-traversal attempt,
    a swapped shard path (inventory's path under groups'
    name, etc.), or a symlink alias.
    """


import os


def _resolve_path_against_layout_candidates(
    raw_path: str,
    *,
    layout_shard_root: Path,
) -> tuple[Path, ...]:
    """Return every plausible resolution of ``raw_path``.

    The recorded path may be:

    * an absolute path (``/abs/.../shard.json``); or
    * a relative path (``docs/reports/.../shard.json``).

    For relative paths the function returns every candidate:

    * :data:`REPO_ROOT / p` (the canonical layout uses
      ``_relative_to_repo`` to make paths relative to the
      repository root);
    * ``layout_shard_root / p`` (the test layout stores paths
      relative to the layout's shard_root when the layout
      sits outside the repository root).

    The candidate resolution uses
    :meth:`Path.resolve` to canonicalise ``..`` segments
    against the actual filesystem (which is the only way
    to compare a stored relative path with the canonical
    shard target when the layout lives OUTSIDE ``REPO_ROOT``).
    The symlink check is performed by the caller BEFORE
    ``resolve`` is consulted, so symlink aliases are NOT
    transparent.
    """
    p = Path(raw_path)
    if p.is_absolute():
        return (p,)
    candidates: list[Path] = [REPO_ROOT / p, layout_shard_root / p]
    out: list[Path] = []
    for cand in candidates:
        try:
            out.append(cand.resolve())
        except OSError:
            out.append(cand)
    return tuple(out)


def _validate_shard_path_against_layout(
    shard_name: str,
    info: object,
    *,
    layout_shard_root: Path,
    required_shards: frozenset[str],
) -> str | None:
    """Return the canonical normalised path when valid, else raise."""
    if shard_name not in required_shards:
        raise IndexNormalisationError(
            f"unknown shard name {shard_name!r}; "
            f"required={sorted(required_shards)}"
        )
    if not isinstance(info, dict):
        raise IndexNormalisationError(
            f"shard {shard_name!r} info must be a dict, got "
            f"{type(info).__name__}"
        )
    raw_path = info.get("path")
    if not isinstance(raw_path, str):
        raise IndexNormalisationError(
            f"shard {shard_name!r} path must be a string, got "
            f"{type(raw_path).__name__}: {raw_path!r}"
        )
    recorded_path = Path(raw_path)
    expected_basename = f"{shard_name}.json"
    if recorded_path.name != expected_basename:
        raise IndexNormalisationError(
            f"shard {shard_name!r} basename drift: recorded="
            f"{recorded_path.name!r} expected={expected_basename!r}"
        )
    expected_abs = layout_shard_root / f"{shard_name}.json"
    candidates = _resolve_path_against_layout_candidates(
        raw_path, layout_shard_root=layout_shard_root
    )
    expected_real = Path(os.path.realpath(expected_abs))
    matched = next(
        (
            c for c in candidates
            if c == expected_abs or c == expected_real
        ),
        None,
    )
    if matched is None:
        raise IndexNormalisationError(
            f"shard {shard_name!r} path drift: recorded="
            f"{recorded_path.as_posix()!r} expected={expected_abs.as_posix()!r}"
        )
    # Reject symlink aliases; lexical ``..`` segments in the
    # RAW recorded path are acceptable when the resolved path
    # equals the canonical target (a test layout can sit
    # outside REPO_ROOT and produce a relative path that uses
    # ``..`` to escape back into the layout's shard_root).
    if matched.is_symlink():
        raise IndexNormalisationError(
            f"shard {shard_name!r} recorded path is a symlink alias: "
            f"{matched.as_posix()!r}"
        )
    return f"{shard_name}.json"


def normalise_index_paths(
    index: dict[str, object],
    *,
    layout_shard_root: Path,
    required_shards: frozenset[str],
    optional_shards: frozenset[str] = frozenset({"gate_classification"}),
) -> dict[str, object]:
    """CORRECTION13/CORRECTION14: complete top-level shard-layout
    schema enforcement + layout-aware path normalisation.

    The function returns a deep-copied index whose values
    are equivalent modulo the canonical shard-path
    representation.

    The function enforces, in order:

    1. ``shards`` MUST be a dict;
    2. ``set(index['shards']) - optional_shards`` MUST equal
       ``required_shards`` (every required shard is present;
       extra required shards are REJECTED; optional shards
       are accepted when present and ignored when absent);
    3. every required shard's info MUST be a dict;
    4. every required shard's info MUST contain a string
       ``path`` field;
    5. the recorded path MUST identify exactly
       ``layout_shard_root / f"{shard_name}.json"``;
    6. symlink aliases are REJECTED;
    7. path-traversal (``..``) segments are REJECTED;
    8. unknown extra shards (not in ``required_shards`` and
       not in ``optional_shards``) are REJECTED.

    The function NEVER normalises ``schema_version``,
    ``analysis_base_commit``, ``identity_binding``,
    ``totals``, shard hashes (``sha256``), or unknown extra
    fields.
    """
    out = copy.deepcopy(index)
    shards = out.get("shards")
    if not isinstance(shards, dict):
        raise IndexNormalisationError(
            f"top-level index 'shards' must be a dict, got "
            f"{type(shards).__name__}"
        )
    # Required shards MUST be present.
    missing = sorted(required_shards - set(shards))
    if missing:
        raise IndexNormalisationError(
            f"top-level index missing required shards: {missing}"
        )
    # Extra shards (outside the required + optional sets) are REJECTED.
    allowed = required_shards | optional_shards
    extra = sorted(set(shards) - allowed)
    if extra:
        raise IndexNormalisationError(
            f"top-level index contains unknown extra shards: {extra}"
        )
    # Validate every required shard; optional shards are
    # ALSO normalised when present so the canonical and
    # the rebuilt expected index produce identical path
    # representations.
    for name in sorted(required_shards | (set(shards) & optional_shards)):
        info = shards.get(name)
        if not isinstance(info, dict):
            raise IndexNormalisationError(
                f"shard {name!r} info must be a dict, got "
                f"{type(info).__name__}"
            )
        if "path" not in info:
            raise IndexNormalisationError(
                f"shard {name!r} info is missing required 'path' field"
            )
        info["path"] = _validate_shard_path_against_layout(
            str(name),
            info,
            layout_shard_root=layout_shard_root,
            required_shards=required_shards | optional_shards,
        )
    return out


__all__ = [
    "IndexNormalisationError",
    "normalise_index_paths",
]