#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_command(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> CommandResult:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except Exception as exc:  # noqa: BLE001
        return CommandResult(
            argv=argv,
            returncode=999,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
        )


def find_python_venv() -> str | None:
    candidate = Path(".venv/bin/python")
    return str(candidate) if candidate.exists() else None


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


def tail_directory(path: Path, limit: int = 15) -> list[dict[str, Any]]:
    if not path.exists():
        return [{"_error": f"missing directory: {path}"}]

    entries: list[dict[str, Any]] = []
    for item in sorted(path.iterdir(), key=lambda p: p.name)[-limit:]:
        stat = item.stat()
        entries.append(
            {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size_bytes": stat.st_size,
                "mtime_epoch": stat.st_mtime,
            }
        )
    return entries


def discover_compose_command(explicit: str | None) -> list[str] | None:
    if explicit:
        return explicit.split()

    docker = shutil.which("docker")
    if docker:
        probe = run_command([docker, "compose", "version"], timeout=15)
        if probe.ok:
            return [docker, "compose"]

    podman = shutil.which("podman")
    if podman:
        probe = run_command([podman, "compose", "version"], timeout=15)
        if probe.ok:
            return [podman, "compose"]

    return None


def count_matching_files(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob(pattern))


def list_matching_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern))


def extract_review_run_ids(review_files: list[Path]) -> list[str]:
    ids: list[str] = []
    for path in review_files:
        name = path.name
        if name.endswith("-review.json"):
            ids.append(name.removesuffix("-review.json"))
    return sorted(set(ids))


def extract_execution_run_ids(execution_files: list[Path]) -> list[str]:
    ids: list[str] = []
    suffix = ".json"
    marker = "-next-check-execution-"
    for path in execution_files:
        name = path.name
        if marker not in name or not name.endswith(suffix):
            continue
        prefix, _index = name[: -len(suffix)].rsplit(marker, 1)
        ids.append(prefix)
    return sorted(set(ids))


def sample_json(path: Path | None, line_limit: int = 160) -> Any:
    if path is None or not path.exists():
        return None
    loaded = load_json_file(path)
    try:
        pretty = json.dumps(loaded, indent=2, sort_keys=True)
        lines = pretty.splitlines()
        if len(lines) <= line_limit:
            return loaded
        return {
            "_truncated": True,
            "_line_limit": line_limit,
            "preview": "\n".join(lines[:line_limit]),
        }
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"}


def fetch_json_via_curl(base_url: str, path: str, timeout: int = 30) -> dict[str, Any]:
    curl = shutil.which("curl")
    url = f"{base_url.rstrip('/')}{path}"
    if not curl:
        return {
            "url": url,
            "error": "curl not found",
        }

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = run_command(
            [curl, "-sS", "-o", tmp_path, "-w", "%{http_code}", url],
            timeout=timeout,
        )
        payload_text = Path(tmp_path).read_text() if Path(tmp_path).exists() else ""
        parsed: Any
        try:
            parsed = json.loads(payload_text) if payload_text else None
        except Exception:
            parsed = None

        return {
            "url": url,
            "http_code": result.stdout.strip(),
            "command": asdict(result),
            "body": parsed if parsed is not None else payload_text,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def grep_interesting_run_fields(payload: Any) -> dict[str, Any]:
    matches: dict[str, Any] = {}

    interesting = {
        "executionState",
        "outcomeStatus",
        "latestArtifactPath",
        "queueStatus",
        "reviewStatus",
        "executionCount",
        "reviewedCount",
        "triaged",
    }

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_path = f"{path}.{key}" if path else key
                if key in interesting:
                    matches[next_path] = value
                walk(value, next_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "")
    return matches


def maybe_rebuild_ui_index(runs_dir: str) -> dict[str, Any]:
    python_bin = find_python_venv()
    if not python_bin:
        return {"skipped": True, "reason": "missing .venv/bin/python"}
    result = run_command(
        [python_bin, "scripts/update_ui_index.py", "--runs-dir", runs_dir],
        timeout=120,
    )
    return asdict(result)


def maybe_rebuild_diagnostic_pack(runs_dir: str) -> dict[str, Any]:
    python_bin = find_python_venv()
    if not python_bin:
        return {"skipped": True, "reason": "missing .venv/bin/python"}
    result = run_command(
        [python_bin, "scripts/build_diagnostic_pack.py", "--runs-dir", runs_dir],
        timeout=180,
    )
    return asdict(result)


def backend_container_snapshot(compose_cmd: list[str]) -> dict[str, Any]:
    shell_script = r"""
set -e
python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path("/app/runs/health")
reviews = base / "reviews"
external = base / "external-analysis"

def count(pattern_dir, pattern):
    if not pattern_dir.exists():
        return 0
    return sum(1 for _ in pattern_dir.glob(pattern))

def tail(pattern_dir, limit=10):
    if not pattern_dir.exists():
        return [{"_error": f"missing directory: {pattern_dir}"}]
    items = sorted(pattern_dir.iterdir(), key=lambda p: p.name)[-limit:]
    out = []
    for item in items:
        stat = item.stat()
        out.append({
            "name": item.name,
            "path": str(item),
            "is_dir": item.is_dir(),
            "size_bytes": stat.st_size,
            "mtime_epoch": stat.st_mtime,
        })
    return out

print(json.dumps({
    "env": {
        "HEALTH_RUNS_DIR": os.getenv("HEALTH_RUNS_DIR"),
        "HEALTH_UI_RUNS_DIR": os.getenv("HEALTH_UI_RUNS_DIR"),
        "PWD": os.getcwd(),
    },
    "counts": {
        "reviews": count(reviews, "*-review.json"),
        "executions": count(external, "*-next-check-execution-*.json"),
    },
    "tails": {
        "reviews": tail(reviews),
        "external_analysis": tail(external),
    },
}, indent=2, sort_keys=True))
PY
"""
    result = run_command([*compose_cmd, "exec", "-T", "backend", "sh", "-lc", shell_script], timeout=90)
    parsed: Any
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except Exception:
        parsed = None
    return {
        "command": asdict(result),
        "parsed": parsed,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    runs_dir = Path(args.runs_dir)
    reviews_dir = runs_dir / "reviews"
    external_dir = runs_dir / "external-analysis"

    review_files = list_matching_files(reviews_dir, "*-review.json")
    execution_files = list_matching_files(external_dir, "*-next-check-execution-*.json")

    report: dict[str, Any] = {
        "meta": {
            "cwd": str(Path.cwd()),
            "runs_dir": str(runs_dir),
            "backend_url": args.backend_url,
            "rebuild_ui_index": args.rebuild_ui_index,
            "rebuild_diagnostic_pack": args.rebuild_diagnostic_pack,
            "python": sys.executable,
        },
        "host_artifacts": {
            "counts": {
                "review_artifacts": len(review_files),
                "execution_artifacts": len(execution_files),
            },
            "run_ids": {
                "review_run_ids": extract_review_run_ids(review_files),
                "execution_run_ids": extract_execution_run_ids(execution_files),
            },
            "directory_tails": {
                "reviews": tail_directory(reviews_dir),
                "external_analysis": tail_directory(external_dir),
            },
            "latest_samples": {
                "latest_review_path": str(review_files[-1]) if review_files else None,
                "latest_execution_path": str(execution_files[-1]) if execution_files else None,
                "latest_review_json": sample_json(review_files[-1] if review_files else None, 120),
                "latest_execution_json": sample_json(execution_files[-1] if execution_files else None, 160),
            },
        },
    }

    if args.rebuild_ui_index:
        report["ui_index_rebuild"] = maybe_rebuild_ui_index(str(runs_dir))

    if args.rebuild_diagnostic_pack:
        report["diagnostic_pack_rebuild"] = maybe_rebuild_diagnostic_pack(str(runs_dir))

    api_runs = fetch_json_via_curl(args.backend_url, "/api/runs")
    api_run = fetch_json_via_curl(args.backend_url, "/api/run")

    report["backend_api"] = {
        "api_runs": api_runs,
        "api_run": api_run,
        "api_run_interesting_fields": grep_interesting_run_fields(api_run.get("body")),
    }

    compose_cmd = discover_compose_command(args.compose_cmd)
    report["container_visibility"] = {
        "compose_command": compose_cmd,
        "backend_snapshot": backend_container_snapshot(compose_cmd) if compose_cmd else None,
    }

    report["quick_interpretation_guide"] = [
        "If review_artifacts is 0, Recent runs showing zero counts is expected.",
        "If execution artifacts exist but /api/run still reports unexecuted queue items, backend queue reconciliation is broken.",
        "If host artifact counts differ from backend container counts, the backend is reading a different runs directory or bind mount view.",
        "If /api/runs is empty while review artifacts exist on disk, backend run discovery is broken.",
    ]

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect k9b run/debug state and emit a single JSON report to stdout."
    )
    parser.add_argument(
        "--runs-dir",
        default=os.environ.get("RUNS_DIR", "runs/health"),
        help="Health runs directory (default: runs/health or $RUNS_DIR).",
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8080"),
        help="Backend base URL (default: http://127.0.0.1:8080 or $BACKEND_URL).",
    )
    parser.add_argument(
        "--compose-cmd",
        default=os.environ.get("COMPOSE_CMD"),
        help='Explicit compose command, e.g. "docker compose" or "podman compose".',
    )
    parser.add_argument(
        "--rebuild-ui-index",
        action="store_true",
        help="Run scripts/update_ui_index.py before API checks.",
    )
    parser.add_argument(
        "--rebuild-diagnostic-pack",
        action="store_true",
        help="Run scripts/build_diagnostic_pack.py before API checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
