#!/usr/bin/env python3
"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 semantic verifier.

This stable entry module owns repository/path orchestration, violation
aggregation, and the CLI contract. Focused AST rule implementations live in
``current_run_promotion_seam01_checks`` and are re-exported here under the
historical underscored names for the existing verifier self-tests.

Exit codes:

* 0 -- no violations
* 1 -- violations
* 2 -- verification infrastructure failure
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import current_run_promotion_seam01_checks as _checks

Violation = _checks.Violation
VerifierInfrastructureError = _checks.VerifierInfrastructureError
_verify_file = _checks._verify_file

if TYPE_CHECKING:
    from current_run_promotion_seam01_checks import Violation as _ViolationType
else:
    _ViolationType = _checks.Violation

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC_ROOT = REPO_ROOT / "src" / "k8s_diag_agent"

# Modules where production seam correctness MUST hold.
SEAM_MODULE_SUBSTRINGS: tuple[str, ...] = (
    "loop_alertmanager_snapshot_signals",
    "loop_automatic_diagnosis",
    "loop_runner_execute",
    "loop_runner",
    "promotion_diagnosis_handoff",
    "incident_alert_signal_snapshot_adapter",
    "incident_alert_promotion",
    "incident_alert_promotion_scoped",
    "incident_alert_promotion_contract",
    "incident_alert_signal",
    "incident_alert_signal_store",
    "signal_persistence_outcomes",
    "current_run_promotion_workset",
    "promotion_outcomes",
    "diagnosis_selection",
    "store_scan_policy",
    "incident_promotion_batch",
    "incident_promotion_accumulator",
    "incident_promotion_backend",
    "incident_promotion_dispatch",
)

__all__ = [
    "Violation",
    "VerifierInfrastructureError",
    "SEAM_MODULE_SUBSTRINGS",
    "DEFAULT_SRC_ROOT",
    "verify_seam",
    "main",
    "_collect_python_files",
    "_is_seam_module",
]


def _collect_python_files(src_root: Path) -> list[Path]:
    if not src_root.exists():
        raise VerifierInfrastructureError(
            f"Source root {src_root} does not exist"
        )
    return sorted(src_root.rglob("*.py"))


def _is_seam_module(path: Path) -> bool:
    name = path.name
    if name.endswith(".py") and name.startswith("test_"):
        return False
    return any(substring in name for substring in SEAM_MODULE_SUBSTRINGS)


def verify_seam(src_root: Path) -> tuple[int, list[str]]:
    """Run focused checks over seam files in deterministic path order."""
    files: list[Path] = _collect_python_files(src_root)
    seam_files = [path for path in files if _is_seam_module(path)]
    violations: list[_ViolationType] = []
    for path in seam_files:
        violations.extend(_verify_file(path))
    if violations:
        return 1, [violation.render() for violation in violations]
    return 0, []


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 verifier.",
    )
    parser.add_argument(
        "--src-root",
        default=str(DEFAULT_SRC_ROOT),
        help="Source root to scan",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv if argv is not None else sys.argv[1:])
        src_root = Path(args.src_root)
        exit_code, rendered = verify_seam(src_root)
    except VerifierInfrastructureError as exc:
        print(f"verifier infrastructure error: {exc}", file=sys.stderr)
        return 2
    if exit_code == 0:
        print("OK: current-run promotion seam verifier found no violations")
        return 0
    for line in rendered:
        print(line)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
