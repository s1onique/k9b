"""Gate verification checks for CI gate drift verifier."""

from __future__ import annotations

import re


def check_shard_matrix_in_job(job_content: str) -> dict:
    """Check if a job has a shard matrix configuration."""
    result = {
        "has_shard_matrix": False,
        "shard_indices": [],
        "shard_total": None,
    }

    matrix_pattern = re.compile(r"^\s*matrix:\s*$", re.MULTILINE)
    if matrix_pattern.search(job_content):
        result["has_shard_matrix"] = True

        shard_index_pattern = re.compile(r"shard_index:\s*\[(.*?)\]", re.MULTILINE)
        match = shard_index_pattern.search(job_content)
        if match:
            indices_str = match.group(1)
            result["shard_indices"] = [
                int(x.strip()) for x in indices_str.split(",") if x.strip()
            ]

        shard_total_pattern = re.compile(r"shard_total:\s*\[?(\d+)\]?", re.MULTILINE)
        match = shard_total_pattern.search(job_content)
        if match:
            result["shard_total"] = int(match.group(1))

    return result


def check_shard_union_verification(jobs: dict[str, dict]) -> dict:
    """Check if shard union verification job exists and is properly configured."""
    result = {
        "has_shard_union_job": False,
        "depends_on_shards": False,
        "verify_shards_command": None,
    }

    for job_name, job_data in jobs.items():
        if "shard-union" in job_name.lower() or "shard_union" in job_name.lower():
            result["has_shard_union_job"] = True

            if job_data["has_needs"]:
                result["depends_on_shards"] = True

            for cmd in job_data["commands"]:
                if "--verify-shards" in cmd or "verify-shards" in cmd:
                    result["verify_shards_command"] = cmd
                    break

    return result


def verify_gate_mapping(
    gate_id: str,
    gate_config: dict,
    workflow_jobs: dict[str, dict],
    all_workflow_jobs: dict[str, dict],
    workflow_path: str | None = None,
) -> tuple[bool, str, list[str]]:
    """Verify a single gate mapping.

    Args:
        gate_id: The gate identifier
        gate_config: Gate configuration from manifest
        workflow_jobs: Jobs in the current workflow
        all_workflow_jobs: All jobs across all workflows
        workflow_path: Optional workflow path to look up per-workflow ci_equivalent

    Returns (passed, message, errors)
    """
    errors = []
    fragments = gate_config.get("required_command_fragments", [])

    # Get ci_equivalent jobs - could be per-workflow or fallback to list
    ci_equivs = gate_config.get("ci_equivalent", [])
    if isinstance(ci_equivs, dict) and workflow_path:
        ci_equivs = ci_equivs.get(workflow_path, [])

    found_jobs = []
    for ci_job in ci_equivs:
        if ci_job in workflow_jobs:
            found_jobs.append(ci_job)

    if not found_jobs:
        errors.append(f"Required gate '{gate_id}' has no matching CI job in workflow")
        return False, f"FAIL: No CI job found for '{gate_id}'", errors

    if gate_config.get("shard_required"):
        shard_job_found = False
        for job_name, job_data in workflow_jobs.items():
            raw_content = job_data.get("raw_content", "")
            shard_info = check_shard_matrix_in_job(raw_content)
            if shard_info["has_shard_matrix"]:
                shard_job_found = True
                if len(shard_info["shard_indices"]) < 2:
                    errors.append(f"Gate '{gate_id}' shard matrix has fewer than 2 shards")

        if not shard_job_found:
            errors.append(f"Gate '{gate_id}' requires shard matrix but none found")

    if gate_config.get("shard_union_required"):
        shard_union = check_shard_union_verification(all_workflow_jobs)
        if not shard_union["has_shard_union_job"]:
            errors.append(f"Gate '{gate_id}' requires shard union verifier but none found")
        elif not shard_union["depends_on_shards"]:
            errors.append(f"Gate '{gate_id}' shard union verifier does not depend on shard jobs")

    for fragment in fragments:
        found_in_any_job = False
        for job_name, job_data in workflow_jobs.items():
            for cmd in job_data.get("commands", []):
                if fragment in cmd:
                    found_in_any_job = True
                    break

        if not found_in_any_job:
            errors.append(f"Gate '{gate_id}' command fragment '{fragment}' not found in CI")

    if errors:
        return False, f"FAIL: {errors[0]}", errors

    return True, f"PASS: {gate_id} -> {', '.join(found_jobs)}", []


def check_allowlist_entry(entry: dict, manifest: dict) -> tuple[bool, str, list[str]]:
    """Check if an allowlist entry is valid."""
    errors = []
    gate_id = entry.get("gate", "")
    workflow = entry.get("workflow", "")
    reason = entry.get("reason", "")

    if not reason or len(reason.strip()) < 10:
        errors.append(f"Allowlist entry for '{gate_id}' has insufficient reason")
        return False, f"FAIL: Insufficient reason for '{gate_id}'", errors

    if gate_id not in manifest.get("required_gates", {}):
        errors.append(f"Allowlist entry '{gate_id}' references unknown gate")
        return False, f"FAIL: Unknown gate '{gate_id}' in allowlist", errors

    # Verify workflow is in workflows_to_check
    workflows_to_check = manifest.get("workflows_to_check", [])
    if workflow not in workflows_to_check:
        errors.append(f"Allowlist entry '{gate_id}' references workflow not in workflows_to_check")
        return False, f"FAIL: Workflow '{workflow}' not in workflows_to_check", errors

    return True, f"OK: Allowlist entry for '{gate_id}'", []
