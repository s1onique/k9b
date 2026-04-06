#!/usr/bin/env python3
"""Wrapper for kicking off the scheduled health loop with cadence flags."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_BIN = ROOT / ".venv" / "bin" / "python"
DEFAULT_CONFIG = Path("runs/health-config.local.json")
DEFAULT_LOG = ROOT / "runs" / "health" / "scheduler.log"


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return ivalue


def _ensure_python() -> Path:
    if not PYTHON_BIN.exists():
        raise RuntimeError(
            f"Python executable {PYTHON_BIN} not found; create or activate .venv before running."
        )
    return PYTHON_BIN


def _append_log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    DEFAULT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an automated health loop scheduler.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="health config file (default: runs/health-config.local.json)",
    )
    parser.add_argument(
        "--every-seconds",
        type=_positive_int,
        default=300,
        help="Interval between runs in seconds (default: 300).",
    )
    parser.add_argument(
        "--max-runs",
        type=_positive_int,
        help="Optional cap on the number of iterations.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single health iteration even when scheduling is configured.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Forward --quiet to the health loop so only summaries are printed.",
    )
    args = parser.parse_args(argv)

    python = _ensure_python()
    command = [
        str(python),
        "-m",
        "k8s_diag_agent.cli",
        "run-health-loop",
        "--config",
        str(args.config),
    ]
    if args.once:
        command.append("--once")
    if args.every_seconds:
        command.extend(["--every-seconds", str(args.every_seconds)])
    if args.max_runs is not None:
        command.extend(["--max-runs", str(args.max_runs)])
    if args.quiet:
        command.append("--quiet")

    _append_log("Starting scheduler with command: %s" % " ".join(command))
    result = subprocess.run(command, env=os.environ)
    status = "succeeded" if result.returncode == 0 else f"failed (code {result.returncode})"
    _append_log(f"Scheduler {status}")
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1)
