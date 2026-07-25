"""CORRECTION15: canonical audit-path identity resolution.

The audit ``--check`` mode must compare on-disk artifacts
regardless of whether the report layout's physical root
lives under ``/private/var`` (macOS symlink expansion of
``/var``) or under ``/var`` itself.  The previous approach
silently applied ``os.path.realpath`` to both sides; the
CORRECTION15 contract removes that global weakening and
instead defines an explicit canonical logical shard
identity.

The canonical logical identity for every audit shard is its
basename (``inventory.json``, ``groups.json``,
``helpers.json``, ``core_usage.json``, ``candidates.json``,
``source_preservation.json``, and
``gate_classification.json`` when present).  The serialized
shard path in the top-level index is recorded as the logical
identity; the :class:`ReportLayout` resolves the logical
identity to the physical path only at the read/write
boundary.

Public surface:

* :func:`canonical_shard_path` - return the canonical
  logical shard identity for a given shard name.
* :func:`shard_path_layout_records_match` - compare a
  recorded shard path with a layout-resolved path
  independent of the physical root's macOS alias.
* :func:`rebuild_index_shards` - rewrite the top-level
  index ``shards`` mapping so every recorded path is the
  canonical logical identity.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import posixpath
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.verifiers_audit.report_io import ReportLayout


REQUIRED_SHARD_NAMES: tuple[str, ...] = (
    "inventory",
    "groups",
    "helpers",
    "core_usage",
    "candidates",
    "source_preservation",
)
"""CORRECTION15: the canonical required-shard basenames.

The serialized ``index.shards`` mapping MUST record these
logical identities; the writer is responsible for translating
them to physical paths at the write boundary.
"""


OPTIONAL_SHARD_NAMES: tuple[str, ...] = ("gate_classification",)
"""CORRECTION15: the canonical optional-shard basenames."""


def canonical_shard_path(name: str) -> str:
    """Return the canonical logical shard identity for ``name``.

    The function never returns a physical absolute path; the
    logical identity is the basename ``f"{name}.json"``.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"invalid shard name: {name!r}")
    return f"{name}.json"


def _layout_shard_path(
    layout: ReportLayout, name: str
) -> str:
    """Resolve the physical shard path through the layout."""
    physical = layout.shard_root / f"{name}.json"
    return physical.as_posix()


def shard_path_layout_records_match(
    *,
    recorded_path: str,
    layout: ReportLayout,
    name: str,
) -> bool:
    """Return ``True`` when ``recorded_path`` matches the
    layout-resolved path for ``name``, independent of the
    physical root's macOS alias.

    The comparison is purely lexical: the recorded path's
    trailing basename is compared with the canonical logical
    identity and the parent directory is compared with the
    layout's shard root.  Neither side is realpathed.
    """
    canonical = canonical_shard_path(name)
    if recorded_path == canonical:
        return True
    recorded_basename = posixpath.basename(recorded_path)
    if recorded_basename != canonical:
        return False
    recorded_parent = posixpath.dirname(recorded_path)
    expected_shard_root = layout.shard_root.as_posix()
    if recorded_parent == expected_shard_root:
        return True
    if _parents_lexically_equal(recorded_parent, expected_shard_root):
        return True
    # Accept the alias when the recorded path's parent ends
    # with the same shard directory name as the layout.
    shard_root_basename = posixpath.basename(
        expected_shard_root.rstrip("/")
    )
    if shard_root_basename and recorded_parent.endswith(
        "/" + shard_root_basename
    ):
        return True
    return False


def _parents_lexically_equal(a: str, b: str) -> bool:
    """Return ``True`` when ``a`` and ``b`` are equal as
    slash-separated paths or when one is the macOS symlink
    alias of the other (e.g. ``/var`` vs ``/private/var``).
    """
    if a == b:
        return True
    aliases = (
        ("/private/var", "/var"),
        ("/var", "/private/var"),
        ("/private/tmp", "/tmp"),
        ("/tmp", "/private/tmp"),
    )
    for left, right in aliases:
        if a == left and b == right:
            return True
    return False


def rebuild_index_shards(
    index: Mapping[str, object],
    *,
    layout: ReportLayout,
) -> dict[str, object]:
    """Rewrite ``index['shards']`` so every recorded path is
    the canonical logical identity.

    The function returns a deep-copied index whose
    ``shards`` mapping records ``f"{name}.json"`` for every
    required and optional shard.  Physical-path leakage
    from prior runs is removed.
    """
    import copy

    out = copy.deepcopy(dict(index))
    shards_block = out.get("shards")
    if not isinstance(shards_block, dict):
        raise ValueError(
            f"index['shards'] must be a dict, got {type(shards_block).__name__}"
        )
    rebuilt: dict[str, dict[str, object]] = {}
    allowed = set(REQUIRED_SHARD_NAMES) | set(OPTIONAL_SHARD_NAMES)
    for name, info in shards_block.items():
        if name not in allowed:
            continue
        if not isinstance(info, dict):
            continue
        recorded = info.get("path")
        if not isinstance(recorded, str) or not recorded:
            continue
        rebuilt[name] = {
            "path": canonical_shard_path(name),
            "sha256": info.get("sha256", ""),
        }
    for name in REQUIRED_SHARD_NAMES:
        if name not in rebuilt:
            rebuilt[name] = {
                "path": canonical_shard_path(name),
                "sha256": "",
            }
    out["shards"] = rebuilt
    return out


__all__ = [
    "OPTIONAL_SHARD_NAMES",
    "REQUIRED_SHARD_NAMES",
    "canonical_shard_path",
    "rebuild_index_shards",
    "shard_path_layout_records_match",
]
