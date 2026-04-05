"""Fail if private contexts or runtime config paths leak into tracked files."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Sequence, Set


RUNTIME_CONFIG_PATHS = (
    Path("runs/run-config.local.json"),
    Path("runs/run-config.json"),
    Path("runs/health-config.local.json"),
    Path("snapshots/targets.local.json"),
)

SNAPSHOT_DIRECTORIES = (
    Path("runs/snapshots"),
    Path("snapshots"),
)

ALLOWED_SNAPSHOT_FILES = {
    Path("snapshots/targets.local.example.json").as_posix(),
}


def _normalize_name(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _extract_targets(raw: dict[str, object]) -> Set[str]:
    contexts: Set[str] = set()
    for entry in raw.get("targets", []):
        if not isinstance(entry, dict):
            continue
        context = _normalize_name(entry.get("context"))
        label = _normalize_name(entry.get("label"))
        if context:
            contexts.add(context)
        if label:
            contexts.add(label)
    return contexts


def _extract_pairs(raw: dict[str, object]) -> Set[str]:
    contexts: Set[str] = set()
    for entry in raw.get("pairs", []):
        if not isinstance(entry, dict):
            continue
        primary = _normalize_name(entry.get("primary"))
        secondary = _normalize_name(entry.get("secondary"))
        if primary:
            contexts.add(primary)
        if secondary:
            contexts.add(secondary)
    return contexts


def _gather_private_contexts() -> Set[str]:
    result: Set[str] = set()
    for path in RUNTIME_CONFIG_PATHS:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            result.update(_extract_targets(raw))
            result.update(_extract_pairs(raw))
    result.update(_gather_snapshot_contexts())
    return result


def _gather_snapshot_contexts() -> Set[str]:
    contexts: Set[str] = set()
    for directory in SNAPSHOT_DIRECTORIES:
        if not directory.exists():
            continue
        for entry in directory.glob("*.json"):
            normalized = entry.as_posix()
            if normalized in ALLOWED_SNAPSHOT_FILES:
                continue
            try:
                payload = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict):
                metadata = payload.get("metadata") or {}
                context = _normalize_name(metadata.get("cluster_id"))
                if context:
                    contexts.add(context)
    return contexts


def _is_snapshot_path(raw_path: str) -> bool:
    normalized = Path(raw_path).as_posix()
    if normalized in ALLOWED_SNAPSHOT_FILES:
        return False
    for directory in SNAPSHOT_DIRECTORIES:
        prefix = directory.as_posix()
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        if normalized.startswith(prefix):
            return True
    return False


def _check_files(files: Iterable[str], banned_contexts: Set[str]) -> list[str]:
    problems: list[str] = []
    banned_paths = {str(path) for path in RUNTIME_CONFIG_PATHS}
    for raw_path in files:
        normalized = Path(raw_path).as_posix()
        if normalized in banned_paths:
            problems.append(f"runtime config path staged: {normalized}")
            continue
        if _is_snapshot_path(normalized):
            problems.append(f"runtime snapshot path staged: {normalized}")
            continue
        if not banned_contexts:
            continue
        try:
            text = Path(raw_path).read_text(encoding="utf-8")
        except OSError:
            continue
        for context in banned_contexts:
            if context in text:
                problems.append(f"{normalized}: contains private context '{context}'")
    return problems


def main(args: Sequence[str] | None = None) -> int:
    files = list(args or sys.argv[1:])
    if not files:
        return 0
    banned_contexts = _gather_private_contexts()
    problems = _check_files(files, banned_contexts)
    if problems:
        print("Private context check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
