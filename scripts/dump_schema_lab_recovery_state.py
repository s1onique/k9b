#!/usr/bin/env python3
"""Dump k9b schema-lab recovery state.

Purpose
-------
This script is a read-only evidence collector for the CNPG live-lab recovery
thread.

It exists because the recovery path exposed two classes of process risk:

1. Deleted-file state can be misreported by higher-level digest/review tools.
   In particular, an old oversized test file may be deleted in the index while
   still appearing confusingly in a generated digest.

2. LLM-friendly allowlists can become accidental escape hatches.
   A local line-count verifier can pass if an oversized file is added to an
   allowlist, so we need explicit evidence that no allowlist/ignore file grew.

The script prints a structured, timestamped report and exits non-zero if the
important recovery invariants are violated.

What this script does NOT do
----------------------------
It does not stage files. It does not commit files. It does not edit repo files.
It does not delete files. It does not run kubectl. It does not print kubeconfig,
tokens, certs, base64 secrets, or cluster data.

Typical usage
-------------
    python3 scripts/dump_schema_lab_recovery_state.py --skip-verifiers
    python3 scripts/dump_schema_lab_recovery_state.py --output /tmp/k9b-schema-recovery-report.txt
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dump_schema_lab_lib import (
    CommandResult,
    diff_has_added_non_header_lines,
    git_output,
    run_command,
    safe_relative,
)

# Files that historically matter for this recovery.
OLD_MONOLITHIC_TEST = Path("tests/test_schema_evidence_extraction.py")
SPLIT_TEST_GLOB = "test_schema_evidence*.py"

# The current policy is that these are legacy debt registers, not active
# escape hatches. This script therefore treats additions to them as a hard
# recovery failure.
ALLOWLIST_FILES = [
    Path("scripts/llm_friendly_allowlist.py"),
    Path(".llm-friendly-ignore"),
]

# These keys are illegal when rendered directly under a Kubernetes container.
ILLEGAL_CONTAINER_TOP_LEVEL_KEYS = {
    "allowPrivilegeEscalation",
    "readOnlyRootFilesystem",
    "capabilities",
    "limits",
    "requests",
}


@dataclass
class Report:
    """Accumulates human-readable report text and validation failures."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def section(self, title: str) -> None:
        self.lines.extend(["", "=" * 80, title, "=" * 80])

    def subsection(self, title: str) -> None:
        self.lines.extend(["", "-" * 80, title, "-" * 80])

    def text(self, value: str = "") -> None:
        self.lines.append(value)

    def command(self, result: CommandResult) -> None:
        self.lines.append(f"$ {result.command_text}")
        self.lines.append(f"[exit {result.returncode}]")
        if result.stdout:
            self.lines.append("--- stdout ---")
            self.lines.append(result.stdout.rstrip())
        if result.stderr:
            self.lines.append("--- stderr ---")
            self.lines.append(result.stderr.rstrip())
        if not result.stdout and not result.stderr:
            self.lines.append("(no output)")
        self.lines.append("")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self.lines.append(f"FAIL: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.lines.append(f"WARN: {message}")

    def pass_(self, message: str) -> None:
        self.lines.append(f"PASS: {message}")

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def require_git_root(report: Report) -> Path | None:
    """Resolve the Git root and fail closed if it cannot be found."""

    result = run_command(["git", "rev-parse", "--show-toplevel"])
    report.command(result)
    if result.returncode != 0:
        report.fail("cannot resolve git root")
        return None
    root = Path(result.stdout.strip())
    if not root.exists():
        report.fail(f"git root path does not exist: {root}")
        return None
    return root


def collect_git_state(root: Path, report: Report) -> dict[str, str]:
    """Dump raw Git state."""
    report.section("RAW GIT STATE")
    outputs: dict[str, str] = {}
    for label, args in [
        ("status_porcelain_v2", ["status", "--porcelain=v2"]),
        ("status_short", ["status", "--short"]),
        ("diff_cached_name_status", ["diff", "--cached", "--name-status"]),
        ("diff_cached_stat", ["diff", "--cached", "--stat"]),
        ("diff_cached_deleted", ["diff", "--cached", "--diff-filter=D", "--name-only"]),
        ("ls_files_untracked", ["ls-files", "--others", "--exclude-standard"]),
    ]:
        report.subsection(label)
        result = git_output(root, args)
        report.command(result)
        outputs[label] = result.stdout
    return outputs


def list_schema_test_files(root: Path, report: Report) -> list[Path]:
    """Report schema evidence test split state and line counts."""
    report.section("SCHEMA EVIDENCE TEST SPLIT STATE")
    tests_dir = root / "tests"
    files = sorted(tests_dir.glob(SPLIT_TEST_GLOB))

    report.text("Filesystem test files:")
    if files:
        for path in files:
            report.text(f"- {safe_relative(path, root)}")
    else:
        report.text("(none)")

    report.subsection("git ls-files --stage for schema evidence tests")
    report.command(git_output(root, ["ls-files", "--stage", "tests/test_schema_evidence*.py"]))

    report.subsection("line counts")
    for path in files:
        try:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
        except UnicodeDecodeError:
            report.fail(f"cannot decode test file as UTF-8: {safe_relative(path, root)}")
            continue
        report.text(f"{line_count:5d} {safe_relative(path, root)}")
        if line_count > 500:
            report.fail(f"schema evidence test exceeds 500 lines: {safe_relative(path, root)}")

    old_path = root / OLD_MONOLITHIC_TEST
    report.subsection("old monolithic test file")
    report.text(f"path: {OLD_MONOLITHIC_TEST}")
    report.text(f"exists_in_worktree: {old_path.exists()}")
    if old_path.exists():
        report.fail(f"old monolithic test still exists: {OLD_MONOLITHIC_TEST}")
    else:
        report.pass_(f"old monolithic test absent: {OLD_MONOLITHIC_TEST}")

    required = {
        "test_schema_evidence_json.py",
        "test_schema_evidence_patterns.py",
        "test_schema_evidence_resource_mapping.py",
        "test_schema_evidence_summary.py",
        "test_schema_evidence_workflow.py",
    }
    missing = sorted(required - {p.name for p in files})
    if missing:
        report.fail(f"missing split tests: {', '.join(missing)}")
    else:
        report.pass_("all expected split tests exist")
    return files


def check_allowlist_growth(root: Path, report: Report) -> None:
    """Prove that LLM-friendly allowlist/ignore files did not grow."""
    report.section("LLM-FRIENDLY ALLOWLIST / IGNORE STATE")
    for path in ALLOWLIST_FILES:
        report.text(f"{path}: exists={(root / path).exists()}")
    paths = [str(p) for p in ALLOWLIST_FILES]
    unstaged = git_output(root, ["diff", "--", *paths])
    staged = git_output(root, ["diff", "--cached", "--", *paths])
    added_u = diff_has_added_non_header_lines(unstaged.stdout)
    added_s = diff_has_added_non_header_lines(staged.stdout)
    if added_u:
        report.fail("unstaged allowlist additions detected")
    if added_s:
        report.fail("staged allowlist additions detected")
    if not added_u and not added_s:
        report.pass_("no allowlist/ignore additions detected")


def run_helm_render(root: Path, report: Report, output_path: Path) -> bool:
    """Render the chart using the same value path as the live workflow."""
    report.section("HELM RENDER")
    args = [
        "helm", "template", "k9b", "./charts/k9b",
        "--namespace", os.environ.get("LAB_NAMESPACE", "k9b-live-lab"),
        "--values", "./charts/k9b/values-live-lab.yaml",
        "--set", "image.backend.repository=harbor-pve1.spbnix.local/k9b/k9b-backend",
        "--set", "image.backend.tag=test",
        "--set", "backend.auth.enabled=false",
        "--set", "kubernetes.auth.mode=inCluster",
    ]
    result = run_command(args, cwd=root)
    report.command(result)
    if result.returncode != 0:
        report.fail("helm template failed")
        return False
    output_path.write_text(result.stdout, encoding="utf-8")
    report.pass_(f"helm template rendered to {output_path}")
    return True


def analyze_rendered_containers(rendered_path: Path, report: Report) -> None:
    """Validate container resource/securityContext placement."""
    report.section("RENDERED CONTAINER STRUCTURE")
    try:
        import yaml
    except Exception as exc:
        report.fail(f"cannot import PyYAML: {exc}")
        return
    try:
        docs = list(yaml.safe_load_all(rendered_path.read_text(encoding="utf-8")))
    except Exception as exc:
        report.fail(f"failed to parse YAML: {exc}")
        return
    normalized = [d for d in docs if isinstance(d, dict)]
    report.pass_(f"parsed {len(normalized)} Kubernetes YAML documents")

    inspected = 0
    for doc in normalized:
        kind = doc.get("kind")
        metadata = doc.get("metadata") or {}
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "")
        containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if not isinstance(containers, list):
            continue
        for container in containers:
            if not isinstance(container, dict):
                continue
            inspected += 1
            cname = container.get("name", "")
            identity = f"{kind}/{name} container={cname}"
            if namespace:
                identity += f" namespace={namespace}"
            report.subsection(identity)
            illegal = sorted(ILLEGAL_CONTAINER_TOP_LEVEL_KEYS.intersection(container.keys()))
            report.text(f"top_level_illegal_keys: {json.dumps(illegal)}")
            report.text(f"securityContext: {json.dumps(container.get('securityContext'), sort_keys=True)}")
            report.text(f"resources: {json.dumps(container.get('resources'), sort_keys=True)}")
            if illegal:
                report.fail(f"illegal top-level keys in {identity}: {', '.join(illegal)}")
            else:
                report.pass_("no illegal top-level container keys")
            sc = container.get("securityContext")
            res = container.get("resources")
            if isinstance(sc, dict):
                for key in ["allowPrivilegeEscalation", "readOnlyRootFilesystem", "capabilities"]:
                    if key in sc:
                        report.pass_(f"securityContext.{key} nested correctly")
            if isinstance(res, dict):
                for key in ["limits", "requests"]:
                    if key in res:
                        report.pass_(f"resources.{key} nested correctly")

    if inspected == 0:
        report.fail("no workload containers found")
    else:
        report.pass_(f"inspected {inspected} rendered containers")


def run_verifiers(root: Path, report: Report) -> None:
    """Run fresh verification commands and capture final output."""
    report.section("FRESH VERIFIER OUTPUT")
    schema_tests = sorted((root / "tests").glob("test_schema_evidence_*.py"))
    schema_args = [safe_relative(p, root) for p in schema_tests]
    if not schema_args:
        report.fail("no split schema evidence test files found")
        return
    for args in [
        ["pytest", *schema_args],
        ["ruff", "check", "scripts/k9b_cnpg_live_lab_bootstrap.py", *schema_args],
        ["mypy", "scripts/k9b_cnpg_live_lab_bootstrap.py"],
        ["./scripts/verify_all.sh", "--act-local"],
    ]:
        result = run_command(args, cwd=root, timeout_seconds=900)
        report.command(result)
        if result.returncode != 0:
            report.fail(f"verifier failed: {' '.join(args)}")
        else:
            report.pass_(f"verifier passed: {' '.join(args)}")


def summarize_recovery(root: Path, report: Report, outputs: dict[str, str]) -> None:
    """Add final high-signal recovery summary."""
    report.section("RECOVERY SUMMARY")
    cached_del = set(filter(None, outputs.get("diff_cached_deleted", "").splitlines()))
    untracked = set(filter(None, outputs.get("ls_files_untracked", "").splitlines()))
    old = str(OLD_MONOLITHIC_TEST)
    report.text(f"old_monolithic_in_cached_deletions: {old in cached_del}")
    report.text(f"old_monolithic_in_untracked: {old in untracked}")
    report.text(f"old_monolithic_exists: {(root / OLD_MONOLITHIC_TEST).exists()}")
    if (root / OLD_MONOLITHIC_TEST).exists():
        report.fail("old monolithic test still exists on disk")
    if report.failures:
        report.text("")
        report.text("FINAL_STATUS: FAIL")
        for failure in report.failures:
            report.text(f"- {failure}")
    else:
        report.text("")
        report.text("FINAL_STATUS: PASS")


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Dump k9b schema lab recovery state.")
    parser.add_argument("--skip-verifiers", action="store_true", help="Skip pytest/ruff/mypy/ACT-local")
    parser.add_argument("--output", default="", help="Optional path to write a copy of the full report")
    parser.add_argument("--render-output", default="/tmp/k9b-schema-lab-rendered.yaml")
    args = parser.parse_args(argv)

    report = Report()
    now = dt.datetime.now(dt.UTC).isoformat()
    report.section("K9B SCHEMA LAB RECOVERY STATE DUMP")
    report.text(f"generated_at: {now}")

    root = require_git_root(report)
    if root is None:
        print(report.render(), end="")
        return 2

    outputs = collect_git_state(root, report)
    list_schema_test_files(root, report)
    check_allowlist_growth(root, report)

    rendered_path = Path(args.render_output)
    if run_helm_render(root, report, rendered_path):
        analyze_rendered_containers(rendered_path, report)

    if args.skip_verifiers:
        report.warn("verifiers skipped by --skip-verifiers")
    else:
        run_verifiers(root, report)

    summarize_recovery(root, report, outputs)
    print(report.render(), end="")

    if args.output:
        Path(args.output).write_text(report.render(), encoding="utf-8")
        print(f"\nReport written to: {args.output}")

    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
