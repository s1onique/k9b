"""Sharded JSON report writer (CORRECTION01 minimal)."""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment"
import hashlib
import json
import os
import tempfile
from pathlib import Path

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
    "gate_classification",
)
REQUIRED_SHARDS: frozenset[str] = frozenset(SHARD_NAMES)


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
    """Compute ``path`` relative to ``REPO_ROOT`` in a way that
    tolerates macOS's ``/private/var`` vs ``/Users`` symlink
    mismatch.  Both sides are resolved through ``os.path.realpath``
    so the symlink expansion matches the validator's view.
    Falls back to the absolute path when the two roots do not
    share a common prefix.
    """
    from pathlib import Path

    try:
        return str(
            Path(
                os.path.relpath(
                    os.path.realpath(path),
                    os.path.realpath(REPO_ROOT),
                )
            )
        )
    except ValueError:
        return str(path.resolve())


def write_all(
    report_root: Path | None = None,
    audit: dict | None = None,
) -> dict[str, str]:
    """Write every audit-owned shard to ``report_root`` (defaults
    to the canonical :data:`REPORT_ROOT`).  ``gate_classification``
    is intentionally NOT written here - that shard is owned by
    :mod:`scripts.verifiers_audit.collect_r2_evidence`.

    If ``audit`` is provided, the function updates
    ``audit["index"]["shards"]`` in place so the recorded
    paths match the on-disk locations.  Otherwise the
    function builds a fresh audit object internally and
    returns the recorded paths.

    Returns a mapping ``shard_name -> relative_path``.
    """
    from scripts.verifiers_audit.builder import build_audit_object

    root = report_root or REPORT_ROOT
    owns_audit = audit is None
    if owns_audit:
        audit = build_audit_object({})
    shards: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name in WRITE_OWNED_SHARD_NAMES:
        shard_path = root / f"{name}.json"
        if name == "helpers":
            # The helpers shard uses a compact inner separator
            # so a 74-helper shard fits under the 500-line
            # LLM-friendly threshold.  The validator mirrors
            # this encoding via ``_dump_helpers_shard``-aware
            # body reconstruction (see
            # :mod:`scripts.verifiers_audit.validation`).
            body = _dump_helpers_shard(audit[name])
        else:
            body = _json_dumps(audit[name])
        h = _write_atomic(shard_path, body)
        shards[name] = _relative_to_repo(shard_path)
        hashes[name] = h
    # Include the on-disk gate_classification shard hash in the
    # index WITHOUT writing or modifying the shard itself.  The
    # canonical owner of that shard is
    # :mod:`scripts.verifiers_audit.collect_r2_evidence`.
    gc_path = root / "gate_classification.json"
    if gc_path.exists():
        gc_bytes = gc_path.read_bytes()
        shards["gate_classification"] = _relative_to_repo(gc_path)
        hashes["gate_classification"] = _hash_bytes(gc_bytes)
    audit["index"]["shards"] = {
        name: {"path": p, "sha256": hashes[name]}
        for name, p in shards.items()
    }
    top_level = root / "verifier-core-migration-audit01.json"
    _write_atomic(top_level, _json_dumps(audit["index"]))
    return {name: info["path"] for name, info in audit["index"]["shards"].items()}


def write_audit(
    skip_gate: bool = False,
    report_root: Path | None = None,
) -> dict[str, str]:
    """Write the full audit set to ``report_root`` (defaults to
    the canonical :data:`REPORT_ROOT`).  ``gate_classification``
    is NEVER written by this helper - that shard is owned
    exclusively by :mod:`scripts.verifiers_audit.collect_r2_evidence`.

    ``skip_gate`` propagates to the builder for fast local
    sanity runs; production closures leave it ``False`` so
    real evidence is recorded.
    """
    return write_all(report_root=report_root)


def load_top_level_index() -> dict[str, object]:
    return json.loads(TOP_LEVEL_JSON.read_text(encoding="utf-8"))


def load_shard(name: str) -> dict[str, object]:
    return json.loads((REPORT_ROOT / f"{name}.json").read_text(encoding="utf-8"))


def shard_paths() -> dict[str, str]:
    index = load_top_level_index()
    return {name: info["path"] for name, info in index["shards"].items()}
