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


def write_all() -> dict[str, str]:
    from scripts.verifiers_audit.builder import build_audit_object

    audit = build_audit_object({})
    shards: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name in SHARD_NAMES:
        shard_path = REPORT_ROOT / f"{name}.json"
        body = _json_dumps(audit[name])
        h = _write_atomic(shard_path, body)
        shards[name] = str(shard_path.relative_to(REPO_ROOT))
        hashes[name] = h
    audit["index"]["shards"] = {
        name: {"path": p, "sha256": hashes[name]}
        for name, p in shards.items()
    }
    _write_atomic(TOP_LEVEL_JSON, _json_dumps(audit["index"]))
    return {name: info["path"] for name, info in audit["index"]["shards"].items()}


def write_audit(
    skip_gate: bool = False,
) -> dict[str, str]:
    """Write the full audit set; ``skip_gate`` propagates to the
    builder.  This helper is exposed for production report
    generation that must run the canonical gate."""
    from scripts.verifiers_audit.builder import build_audit_object

    audit = build_audit_object({}, skip_gate=skip_gate)
    shards: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name in SHARD_NAMES:
        shard_path = REPORT_ROOT / f"{name}.json"
        body = _json_dumps(audit[name])
        h = _write_atomic(shard_path, body)
        shards[name] = str(shard_path.relative_to(REPO_ROOT))
        hashes[name] = h
    audit["index"]["shards"] = {
        name: {"path": p, "sha256": hashes[name]}
        for name, p in shards.items()
    }
    _write_atomic(TOP_LEVEL_JSON, _json_dumps(audit["index"]))
    return {name: info["path"] for name, info in audit["index"]["shards"].items()}


def load_top_level_index() -> dict[str, object]:
    return json.loads(TOP_LEVEL_JSON.read_text(encoding="utf-8"))


def load_shard(name: str) -> dict[str, object]:
    return json.loads((REPORT_ROOT / f"{name}.json").read_text(encoding="utf-8"))


def shard_paths() -> dict[str, str]:
    index = load_top_level_index()
    return {name: info["path"] for name, info in index["shards"].items()}
