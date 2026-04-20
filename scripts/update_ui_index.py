"""Update the UI index after a diagnostic pack is built."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

DIAGNOSTIC_PACK_PATTERN = re.compile(r"diagnostic-pack-[^-]+-(\d{8}T\d{6}Z)\.zip")


def _extract_timestamp(name: str) -> datetime | None:
    match = DIAGNOSTIC_PACK_PATTERN.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _latest_pack(packs_dir: Path, run_id: str) -> Path | None:
    if not packs_dir.is_dir():
        return None
    candidates = [entry for entry in packs_dir.glob(f"diagnostic-pack-{run_id}-*.zip") if entry.is_file()]
    latest: tuple[Path, datetime | None] | None = None
    for candidate in candidates:
        ts = _extract_timestamp(candidate.name)
        if ts is None:
            try:
                ts = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
            except OSError:
                ts = None
        if latest is None or (ts is not None and (latest[1] is None or ts > latest[1])):
            latest = (candidate, ts)
    return latest[0] if latest else None


def update_index(runs_dir: Path, run_id: str) -> bool:
    ui_index_path = runs_dir / "health" / "ui-index.json"
    packs_dir = runs_dir / "health" / "diagnostic-packs"
    if not ui_index_path.is_file():
        return False
    pack_path = _latest_pack(packs_dir, run_id)
    if not pack_path:
        return False
    timestamp = _extract_timestamp(pack_path.name)
    if timestamp is None:
        try:
            timestamp = datetime.fromtimestamp(pack_path.stat().st_mtime, UTC)
        except OSError:
            timestamp = None
    data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    run_entry = data.setdefault("run", {})
    run_label = run_entry.get("run_label") or ""
    run_entry["diagnostic_pack"] = {
        "path": str(pack_path.relative_to(runs_dir / "health")).replace("\\", "/"),
        "timestamp": timestamp.isoformat() if timestamp else None,
        "label": run_label.strip() or None,
    }
    ui_index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the UI index with diagnostic pack metadata.")
    parser.add_argument("--runs-dir", required=True, help="Base runs directory containing health artifacts.")
    parser.add_argument("--run-id", required=True, help="Run ID used to name the diagnostic pack.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_dir = Path(args.runs_dir)
    if not update_index(runs_dir, args.run_id):
        raise SystemExit(1)


if __name__ == "__main__":
    main()