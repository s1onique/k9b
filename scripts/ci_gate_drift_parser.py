"""Workflow and verify_all.sh parsing for CI gate drift verifier."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add scripts to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))


def parse_verify_all_gate_ids(repo_root: Path) -> set[str]:
    """Parse gate IDs from verification source of truth.

    The canonical source of truth for gate IDs is now verify_profile_model.py STEPS dict.
    We also check verify_all.sh for any gates that might be defined there.

    Returns a set of gate IDs found in the verification system.
    """
    gate_ids: set[str] = set()

    # Primary source: verify_profile_model.py STEPS dict
    profile_model_path = repo_root / "scripts" / "verify_profile_model.py"
    if profile_model_path.exists():
        try:
            # Import STEPS from verify_profile_model
            # We need to be careful about imports, so we'll parse the file directly
            with open(profile_model_path, encoding="utf-8") as f:
                content = f.read()

            # Extract step IDs from STEPS dict definitions
            # Pattern: "gate-id": { ... }
            step_pattern = re.compile(r'^\s+"([^"]+)":\s*\{', re.MULTILINE)
            for match in step_pattern.finditer(content):
                gate_id = match.group(1)
                # Skip internal keys that look like metadata
                if not gate_id.startswith("_"):
                    gate_ids.add(gate_id)
        except Exception:
            pass  # Fall back to verify_all.sh parsing

    # Secondary source: verify_all.sh (legacy, for any gates defined there)
    verify_all_path = repo_root / "scripts" / "verify_all.sh"
    if verify_all_path.exists():
        try:
            with open(verify_all_path, encoding="utf-8") as f:
                content = f.read()

            # Pattern to match _run_and_record calls across all lanes:
            # _run_and_record "python" "gate-id" "message" ...
            pattern = re.compile(r'_run_and_record\s+"[^"]+"\s+"([^"]+)"', re.MULTILINE)
            for match in pattern.finditer(content):
                gate_ids.add(match.group(1))
        except Exception:
            pass

    return gate_ids


def compare_gate_ids(
    verify_all_gates: set[str],
    manifest_gates: set[str],
    explicit_extras: set[str],
) -> tuple[list[str], list[str]]:
    """Compare gate IDs between verify_all.sh and manifest.

    Args:
        verify_all_gates: Gate IDs found in verify_all.sh
        manifest_gates: Gate IDs defined in manifest
        explicit_extras: Gate IDs that are explicitly allowed as extras

    Returns:
        (missing_in_manifest, extra_in_manifest) - lists of gate IDs
    """
    # Gates in verify_all.sh but not in manifest (missing mapping)
    missing_in_manifest = verify_all_gates - manifest_gates - explicit_extras

    # Gates in manifest but not in verify_all.sh (extra mapping)
    extra_in_manifest = manifest_gates - verify_all_gates

    return sorted(missing_in_manifest), sorted(extra_in_manifest)


def extract_jobs_from_workflow(workflow_content: str) -> dict[str, dict]:
    """Extract job definitions from workflow YAML content.

    Returns dict mapping job name -> {commands: list[str], has_needs: bool, raw_content: str}
    """
    jobs = {}

    # Find all job definitions
    # Match patterns like: "  job-name:" but NOT trigger events
    job_pattern = re.compile(r"^\s{2}(\w[\w-]*):\s*$", re.MULTILINE)

    # Known trigger event names to exclude (these appear under "on:" section)
    trigger_events = {
        "pull_request", "push", "schedule", "workflow_dispatch",
        "workflow_call", "repository_dispatch", "release", "issues",
        "pull_request_target", "fork", "page_build", "public",
    }

    lines = workflow_content.split("\n")
    current_job = None
    current_job_content = []
    in_jobs_section = False

    for line in lines:
        # Track when we enter the jobs: section
        if re.match(r"^\s*jobs:\s*$", line):
            in_jobs_section = True

        # Check if this line starts a new job
        job_match = job_pattern.match(line)
        if job_match:
            job_name = job_match.group(1)

            # Skip if not in jobs section or if it's a trigger event
            if not in_jobs_section or job_name in trigger_events:
                continue

            # Save previous job if exists
            if current_job:
                raw_content = "\n".join(current_job_content)
                job_data = _parse_job_content(raw_content)
                job_data["raw_content"] = raw_content
                jobs[current_job] = job_data

            current_job = job_name
            current_job_content = [line]
        elif current_job:
            current_job_content.append(line)

    # Don't forget the last job
    if current_job:
        raw_content = "\n".join(current_job_content)
        job_data = _parse_job_content(raw_content)
        job_data["raw_content"] = raw_content
        jobs[current_job] = job_data

    return jobs


def _parse_job_content(content: str) -> dict:
    """Parse job content to extract commands and dependencies."""
    commands = []
    has_needs = False

    # Extract needs: dependencies
    needs_match = re.search(r"^\s*needs:\s*\[?(.*?)\]?\s*$", content, re.MULTILINE)
    if needs_match:
        has_needs = True

    # Extract run: commands - handle both single-line and multi-line (|) blocks
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for single-line run: command (run: some command without | or >)
        run_match = re.match(r"^\s*run:\s*(?![|>])(\S.+?)\s*$", line)
        if run_match:
            commands.append(run_match.group(1).strip())
            i += 1
            continue

        # Check for multi-line run: block (run: |, run: |-, run: |+, run: >, etc.)
        multi_run_match = re.match(r"^(\s*)run:\s*([|>][-+]?)?\s*$", line)
        if multi_run_match:
            run_indent = len(multi_run_match.group(1))
            block_lines = []
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if not next_line:
                    block_lines.append("")
                    i += 1
                    continue
                stripped = next_line.lstrip()
                leading_spaces = len(next_line) - len(stripped)
                # Block ends when indentation is <= run_indent
                if leading_spaces <= run_indent:
                    break
                if stripped:
                    block_lines.append(stripped)
                i += 1
            if block_lines:
                commands.append("\n".join(block_lines))
            continue

        i += 1

    # Extract uses: actions
    uses_pattern = re.compile(r"^\s*uses:\s*(.+)$", re.MULTILINE)
    for match in uses_pattern.finditer(content):
        commands.append(f"uses: {match.group(1).strip()}")

    return {"commands": commands, "has_needs": has_needs}
