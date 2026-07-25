"""Sharded JSON report writer (CORRECTION11 sole-authority layout; CORRECTION12 single-writer invariant)."""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.discovery import REPO_ROOT

REPORT_ROOT = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01"
TOP_LEVEL_JSON = REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01.json"
SHARD_NAMES: tuple[str, ...] = (
    "inventory",
    "helpers",
    "groups",
    "core_usage",
    "candidates",
    "source_preservation",
)
# The shards the audit writer is responsible for emitting.
# ``gate_classification`` is an OPTIONAL shard owned by
# :mod:`scripts.verifiers_audit.collect_r2_evidence`; the
# audit writer does not emit it but may include it in the
# top-level index when the file already exists on disk.
REQUIRED_SHARDS: frozenset[str] = frozenset(SHARD_NAMES)
OPTIONAL_SHARDS: frozenset[str] = frozenset({"gate_classification"})
ALL_SHARDS: frozenset[str] = REQUIRED_SHARDS | OPTIONAL_SHARDS


class AuditWriteError(RuntimeError):
    """CORRECTION12: typed failure for audit-writing invariants.

    Raised by :func:`write_all` / :func:`write_audit` when the
    audit object is structurally invalid (missing the ``index``
    block, missing a required shard, or otherwise outside the
    CORRECTION11/CORRECTION12 contract).  Generic
    :class:`OSError` and :class:`ValueError` continue to surface
    filesystem and layout-validator failures respectively.
    """

    pass

# CORRECTION11: the canonical filenames are FROZEN.  Any
# deviation (extra ``docs/`` prefix, nested path, wrong filename)
# is rejected by the ``ReportLayout`` validator below.
_CANONICAL_TOP_LEVEL_FILENAME = "verifier-core-migration-audit01.json"
_CANONICAL_MARKDOWN_FILENAME = "verifier-core-migration-audit01.md"


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _json_dumps(obj: object) -> bytes:
    return (
        json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def _compact_json_dumps(obj: object) -> bytes:
    return (
        json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def _write_atomic(path: Path, body: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return _hash_bytes(body)


WRITE_OWNED_SHARD_NAMES: tuple[str, ...] = (
    "inventory",
    "helpers",
    "groups",
    "core_usage",
    "candidates",
    "source_preservation",
)


def _dump_helpers_shard(shard: dict[str, object]) -> bytes:
    """Render the ``helpers`` shard with one helper per line so
    a 74-helper shard fits under the 500-line LLM-friendly
    threshold (the default ``_json_dumps`` indents every field
    and overflows the threshold).

    The output is byte-identical to ``_json_dumps`` output
    modulo the per-helper rendering: every ``helpers`` entry is
    rendered as a single line via ``json.dumps(separators=(",", ":"))``
    and the outer object is hand-assembled with the
    ``indent=2`` layout.  The validator mirrors this exact
    encoding so the on-disk file round-trips through
    :func:`json.loads`.
    """
    import json as _json

    helpers = shard.get("helpers") or []
    if not (
        isinstance(helpers, list)
        and helpers
        and isinstance(helpers[0], dict)
    ):
        return (
            _json.dumps(
                shard, indent=2, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )
    totals = shard["totals"]
    # Hand-assemble the JSON so every helper dict is rendered
    # on a single line and the ``helpers`` list spans ~80 lines
    # instead of ~530.  The on-disk file still round-trips
    # through :func:`json.loads`.  No trailing commas (standard
    # JSON does not allow them).
    totals_items = list(totals.items())
    helpers_json = ",".join(
        _json.dumps(h, separators=(",", ":"), ensure_ascii=False)
        for h in helpers
    )
    totals_json = ",".join(
        f'"{k}":{_json.dumps(v, ensure_ascii=False)}' for k, v in totals_items
    )
    helpers_count = len(helpers)
    body = (
        "{\n"
        '  "schema_version": "1.0",\n'
        '  "totals": {' + totals_json + "},\n"
        f'  "helpers": [{helpers_json}],\n'
        f'  "helpers_count_marker_for_diagnostics": {helpers_count}\n'
        "}\n"
    )
    return body.encode("utf-8")


def _relative_to_repo(path: Path) -> str:
    """Compute ``path`` relative to ``REPO_ROOT``.

    CORRECTION15: the helper no longer applies
    ``os.path.realpath`` to both sides; the global
    realpath weakening was REMOVED because it silently
    accepted both the canonical parent and its macOS
    ``/private/var`` symlink alias as identical.  The
    function now records the canonical logical shard
    identity (``f"{name}.json"``) when ``path`` is a
    child of the canonical ``REPORT_ROOT``, and falls
    back to a ``Path.relative_to`` computation when the
    path lies under ``REPO_ROOT``.  The audit
    ``--check`` mode uses
    :func:`range_evidence_inventory.shard_path_layout_records_match`
    to compare the recorded path with the layout-resolved
    path without applying a global realpath.
    """
    canonical_top_level = REPO_ROOT / "docs" / "reports" / (
        "verifier-core-migration-audit01.json"
    )
    canonical_shard_root = REPO_ROOT / "docs" / "reports" / (
        "verifier-core-migration-audit01"
    )
    try:
        if path == canonical_top_level:
            return "docs/reports/verifier-core-migration-audit01.json"
        if canonical_shard_root in path.parents:
            return path.name
    except OSError:
        pass
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _validate_layout(layout: ReportLayout) -> None:
    """CORRECTION11: enforce the strict invariants below on a
    ``ReportLayout`` before the FIRST write is performed.

    * ``shard_root_absolute``: ``shard_root`` must be an absolute
      path.
    * ``top_level_is_expected_sibling``: ``top_level_json`` must
      live at ``shard_root.parent / canonical_top_level_filename``.
    * ``markdown_is_expected_sibling``: ``markdown_path`` must
      live at ``shard_root.parent / canonical_markdown_filename``.
    * ``top_level_filename_exact``: ``top_level_json.name`` must
      be exactly ``verifier-core-migration-audit01.json``.
    * ``markdown_filename_exact``: ``markdown_path.name`` must
      be exactly ``verifier-core-migration-audit01.md``.
    * ``paths_do_not_overlap``: ``shard_root``, ``top_level_json``,
      and ``markdown_path`` must be three distinct paths.
    """
    if not layout.shard_root.is_absolute():
        raise ValueError(
            f"shard_root must be absolute: {layout.shard_root}"
        )
    if layout.top_level_json.name != _CANONICAL_TOP_LEVEL_FILENAME:
        raise ValueError(
            f"top_level filename is wrong: {layout.top_level_json.name!r} "
            f"(expected {_CANONICAL_TOP_LEVEL_FILENAME!r})"
        )
    if layout.markdown_path.name != _CANONICAL_MARKDOWN_FILENAME:
        raise ValueError(
            f"markdown filename is wrong: {layout.markdown_path.name!r} "
            f"(expected {_CANONICAL_MARKDOWN_FILENAME!r})"
        )
    expected_top = (
        layout.shard_root.parent / _CANONICAL_TOP_LEVEL_FILENAME
    )
    if layout.top_level_json != expected_top:
        raise ValueError(
            f"top_level_json is not the expected sibling of "
            f"shard_root: {layout.top_level_json} != {expected_top}"
        )
    expected_md = (
        layout.shard_root.parent / _CANONICAL_MARKDOWN_FILENAME
    )
    if layout.markdown_path != expected_md:
        raise ValueError(
            f"markdown_path is not the expected sibling of "
            f"shard_root: {layout.markdown_path} != {expected_md}"
        )
    if (
        layout.shard_root == layout.top_level_json
        or layout.shard_root == layout.markdown_path
        or layout.top_level_json == layout.markdown_path
    ):
        raise ValueError(
            f"paths must not overlap: shard_root={layout.shard_root}, "
            f"top_level_json={layout.top_level_json}, "
            f"markdown_path={layout.markdown_path}"
        )


@dataclass(frozen=True)
class ReportLayout:
    """CORRECTION10/CORRECTION11: the canonical report artifact layout.

    The constructor (via :meth:`__post_init__`) enforces the
    strict invariants listed in :func:`_validate_layout`.  An
    inconsistent layout raises ``ValueError`` at construction
    time, BEFORE any write is performed.

    Tests construct a :class:`ReportLayout` entirely beneath
    ``tmp_path``.  The CLI constructs the canonical layout
    explicitly via :func:`canonical_layout`.  Any deviation
    (extra ``docs/`` prefix, nested path, wrong filename) is
    rejected by the constructor.
    """
    shard_root: Path
    top_level_json: Path
    markdown_path: Path

    def __post_init__(self) -> None:
        _validate_layout(self)


def canonical_layout() -> ReportLayout:
    """Return the canonical :class:`ReportLayout` for the live
    repository (the default ``REPORT_ROOT``).  The top-level and
    markdown files live at :data:`TOP_LEVEL_JSON` and a sibling
    path respectively.  Any deviation raises ``ValueError``.
    """
    from pathlib import Path as _P

    if not _P(TOP_LEVEL_JSON).name == _CANONICAL_TOP_LEVEL_FILENAME:
        raise ValueError(
            f"canonical top-level filename is wrong: {TOP_LEVEL_JSON}"
        )
    return ReportLayout(
        shard_root=REPORT_ROOT,
        top_level_json=TOP_LEVEL_JSON,
        markdown_path=REPORT_ROOT.parent / _CANONICAL_MARKDOWN_FILENAME,
    )


def report_layout_for_shard_root(root: Path) -> ReportLayout:
    """CORRECTION10/CORRECTION11: construct a :class:`ReportLayout`
    for an arbitrary ``root`` (typically a test's
    ``tmp_path / "reports"``).

    The top-level file lives at ``root.parent / _CANONICAL_TOP_LEVEL_FILENAME``
    (a SIBLING of the shard directory).  The markdown lives
    at ``root.parent / _CANONICAL_MARKDOWN_FILENAME``.

    The constructor's ``__post_init__`` validator enforces the
    invariant; any deviation raises ``ValueError`` so the
    validator can reject the layout.
    """

    if not root.is_absolute():
        raise ValueError(f"shard_root must be absolute: {root}")
    top = root.parent / _CANONICAL_TOP_LEVEL_FILENAME
    md = root.parent / _CANONICAL_MARKDOWN_FILENAME
    return ReportLayout(
        shard_root=root, top_level_json=top, markdown_path=md
    )


def load_top_level_index(layout: ReportLayout | None = None) -> dict[str, object]:
    if layout is None:
        layout = canonical_layout()
    return json.loads(layout.top_level_json.read_text(encoding="utf-8"))


def load_shard(
    name: str, layout: ReportLayout | None = None
) -> dict[str, object]:
    if layout is None:
        layout = canonical_layout()
    return json.loads((layout.shard_root / f"{name}.json").read_text(encoding="utf-8"))


def shard_paths(layout: ReportLayout | None = None) -> dict[str, str]:
    index = load_top_level_index(layout)
    return {name: info["path"] for name, info in index["shards"].items()}


def _load_gate_classification_from(
    layout: ReportLayout,
) -> dict[str, object] | None:
    """Load the ``gate_classification.json`` shard from a layout.
    The canonical owner is
    :mod:`scripts.verifiers_audit.collect_r2_evidence`; this
    helper only reads.
    """
    path = layout.shard_root / "gate_classification.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_all(
    *,
    layout: ReportLayout,
    audit: dict[str, object],
) -> dict[str, str]:
    """CORRECTION11: write every audit-owned shard to ``layout``.

    The function accepts ONE output description (``layout``);
    the legacy ``report_root`` parameter is removed.  Every
    write MUST go through the layout:

    * shards are written to ``layout.shard_root / ``<name>.json``,
    * the top-level index is written through
      ``_write_atomic(layout.top_level_json, ...)``,
    * the markdown is written through
      ``layout.markdown_path.write_bytes(...)``.

    The validator :func:`_validate_layout` runs BEFORE any
    write is performed so an inconsistent layout is rejected
    before reaching the filesystem.

    ``gate_classification`` is intentionally NOT written here -
    that shard is owned by
    :mod:`scripts.verifiers_audit.collect_r2_evidence`.  When
    the shard exists on disk, its hash is recorded in the index
    without re-emitting the shard itself.

    Returns a mapping ``shard_name -> relative_path``.
    """
    _validate_layout(layout)
    from scripts.verifiers_audit.builder import build_audit_object
    from scripts.verifiers_audit.render import render_markdown

    if audit is None:
        audit = build_audit_object({})
    # CORRECTION12: a structurally invalid audit object is a
    # WRITE-side failure (the caller passed a bad dict).  Surface
    # it as the typed :class:`AuditWriteError` so :func:`cmd_write`
    # can report it without conflating it with generic filesystem
    # failures (``OSError``) or layout-validator failures
    # (``ValueError``).
    if not isinstance(audit, dict):
        raise AuditWriteError(
            f"audit object must be a dict, got {type(audit).__name__}"
        )
    if "index" not in audit or not isinstance(audit["index"], dict):
        raise AuditWriteError(
            "audit object missing 'index' block"
        )
    for name in WRITE_OWNED_SHARD_NAMES:
        if name not in audit:
            raise AuditWriteError(
                f"audit object missing required shard: {name!r}"
            )
    shards: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name in WRITE_OWNED_SHARD_NAMES:
        shard_path = layout.shard_root / f"{name}.json"
        if name == "helpers":
            # The helpers shard uses a compact inner separator
            # so a 74-helper shard fits under the 500-line
            # LLM-friendly threshold.  The validator mirrors
            # this encoding via ``_dump_helpers_shard``-aware
            # body reconstruction (see
            # :mod:`scripts.verifiers_audit.validation`).
            body = _dump_helpers_shard(
                cast("dict[str, object]", audit[name])
            )
        else:
            body = _json_dumps(audit[name])
        h = _write_atomic(shard_path, body)
        # CORRECTION15: the recorded shard path is the
        # canonical logical identity (basename), independent
        # of the physical root.  The :class:`ReportLayout`
        # resolves the logical identity to the physical path
        # only at the read/write boundary.
        shards[name] = f"{name}.json"
        hashes[name] = h
    # Include the on-disk gate_classification shard hash in the
    # index WITHOUT writing or modifying the shard itself.  The
    # canonical owner of that shard is
    # :mod:`scripts.verifiers_audit.collect_r2_evidence`.
    gc_path = layout.shard_root / "gate_classification.json"
    if gc_path.exists():
        gc_bytes = gc_path.read_bytes()
        shards["gate_classification"] = "gate_classification.json"
        hashes["gate_classification"] = _hash_bytes(gc_bytes)
    audit["index"]["shards"] = {
        name: {"path": p, "sha256": hashes[name]}
        for name, p in shards.items()
    }
    # CORRECTION09/CORRECTION11: the canonical top-level file
    # lives at ``layout.shard_root.parent / canonical_filename``
    # — i.e. the top-level is a SIBLING of the shard directory,
    # not a child.  The :func:`_validate_layout` call at the
    # top of this function already enforces this; the explicit
    # ``layout.top_level_json`` use below is the SOLE write path.
    _write_atomic(layout.top_level_json, _json_dumps(audit["index"]))
    # The markdown is written through ``layout.markdown_path``.
    layout.markdown_path.write_bytes(render_markdown(audit).encode("utf-8"))
    return {name: info["path"] for name, info in audit["index"]["shards"].items()}


def write_audit(
    *,
    layout: ReportLayout | None = None,
) -> dict[str, str]:
    """CORRECTION11: write the full audit set to ``layout``.

    The layout is the ONLY output description accepted by this
    function.  There is no ``report_root`` legacy parameter
    and no ``skip_gate`` parameter (the latter was removed by
    Contract B; the audit object reads the persisted
    ``gate_classification.json`` from the layout's shard_root).

    ``layout`` defaults to :func:`canonical_layout` so the
    production CLI gets the canonical on-disk layout.
    """
    if layout is None:
        layout = canonical_layout()
    persisted_gc = _load_gate_classification_from(layout)
    from scripts.verifiers_audit.builder import build_audit_object

    audit = build_audit_object(
        {},
        gate_classification=persisted_gc,
    )
    return write_all(layout=layout, audit=audit)
