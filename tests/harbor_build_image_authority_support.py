"""
Support module for harbor-build-image workflow contract tests.

Provides shared utilities for:
- Workflow loading and caching
- workflow_call input/secret extraction
- Caller discovery
- Step lookup helpers
- Authority matrix model
"""

from pathlib import Path
from typing import Any

import yaml

# Workflow file paths
HARBOR_BUILD_IMAGE_WORKFLOW = Path(".github/workflows/harbor-build-image.yml")
HARBOR_WORKFLOW = Path(".github/workflows/harbor.yml")


# Cached workflow data
_workflow_cache: dict[str, dict[str, Any]] = {}


def load_workflow(path: Path) -> dict[str, Any]:
    """Load and cache a workflow YAML file."""
    key = str(path)
    if key not in _workflow_cache:
        with open(path) as f:
            _workflow_cache[key] = yaml.safe_load(f)
    return _workflow_cache[key]


def get_workflow_call_inputs(workflow: dict[str, Any]) -> dict[str, Any]:
    """Get inputs from workflow_call, handling YAML boolean parsing issues."""
    # Handle YAML parsing where "on" becomes True (boolean key)
    on_val: Any = workflow.get("on")
    if on_val is None:
        on_val = (workflow if isinstance(workflow.get(True), dict) else {}).get(True)  # type: ignore[call-overload]
    if on_val is None:
        on_val = {}
    if isinstance(on_val, dict):
        wc = on_val.get("workflow_call")
        if isinstance(wc, dict):
            inputs = wc.get("inputs")
            if isinstance(inputs, dict):
                return inputs
    return {}


def get_workflow_call_secrets(workflow: dict[str, Any]) -> dict[str, Any]:
    """Get secrets from workflow_call, handling YAML boolean parsing issues."""
    # Handle YAML parsing where "on" becomes True (boolean key)
    on_val: Any = workflow.get("on")
    if on_val is None:
        on_val = (workflow if isinstance(workflow.get(True), dict) else {}).get(True)  # type: ignore[call-overload]
    if on_val is None:
        on_val = {}
    if isinstance(on_val, dict):
        wc = on_val.get("workflow_call")
        if isinstance(wc, dict):
            secrets = wc.get("secrets")
            if isinstance(secrets, dict):
                return secrets
    return {}


def find_workflow_call_invocation_candidates(
    workflow: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Find all workflow_call invocations in jobs."""
    candidates = []
    jobs = workflow.get("jobs") or {}
    for job_name, job_config in jobs.items():
        if isinstance(job_config, dict) and "uses" in job_config:
            candidates.append((job_name, job_config))
    return candidates


def find_harbor_build_image_calls(
    workflow: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Find all harbor-build-image.yml workflow_call invocations."""
    candidates = []
    jobs = workflow.get("jobs") or {}
    for job_name, job_config in jobs.items():
        if isinstance(job_config, dict):
            uses = job_config.get("uses", "")
            if "harbor-build-image.yml" in uses:
                candidates.append((job_name, job_config))
    return candidates


def find_step_by_name(
    workflow: dict[str, Any],
    job_name: str,
    step_name: str,
) -> dict[str, Any] | None:
    """Find a step by name in a workflow job."""
    jobs = workflow.get("jobs") or {}
    job = jobs.get(job_name)
    if not isinstance(job, dict):
        return None
    steps = job.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("name") == step_name:
            return step
    return None


def find_all_steps_with_run(workflow: dict[str, Any], job_name: str) -> list[dict[str, Any]]:
    """Find all steps with run blocks in a workflow job."""
    steps_with_run: list[dict[str, Any]] = []
    jobs = workflow.get("jobs") or {}
    job = jobs.get(job_name)
    if not isinstance(job, dict):
        return steps_with_run
    steps = job.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and "run" in step:
            steps_with_run.append(step)
    return steps_with_run


# =============================================================================
# Authority matrix model
# =============================================================================


def calculate_authority(
    event_name: str,
    image_push_requested: bool,
    cache_write_requested: bool,
) -> dict[str, Any]:
    """
    Calculate the effective authority based on event and requested flags.

    This mirrors the logic in the authority preflight step.
    """
    if event_name == "pull_request":
        # PR is always read-only
        if image_push_requested or cache_write_requested:
            return {
                "allowed": False,
                "reason": "PR_WRITE_AUTHORITY_FORBIDDEN",
            }
        return {
            "allowed": True,
            "image_push": False,
            "cache_read": True,  # PR can read cache
            "cache_write": False,
            "login_required": False,
        }

    # Non-PR event
    login_required = image_push_requested or cache_write_requested

    return {
        "allowed": True,
        "image_push": image_push_requested,
        "cache_read": True,
        "cache_write": cache_write_requested,
        "login_required": login_required,
    }
