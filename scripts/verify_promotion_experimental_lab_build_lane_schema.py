"""Workflow schema helpers for the experimental-lab build lane verifier.

ACT-K9B-HULK-PROMOTION-EXPERIMENTAL-LAB-BUILD-LANE01-CORRECTION02
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTAL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "promotion-experimental-lab-build.yml"
HARBOR_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "harbor-build-image.yml"


def load_workflow(path: Path) -> dict[str, object]:
    """Load a workflow YAML file and validate it is a mapping."""
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        raise ValueError(f"Workflow is not a mapping: {path}")
    return doc


def get_on(workflow: dict[str, object]) -> dict[str, object]:
    """Return the workflow's ``on`` mapping (handling YAML's True key)."""
    on_val: object = workflow.get("on")
    if on_val is None:
        for key in workflow.keys():
            if isinstance(key, bool):
                on_val = workflow[key]
                break
    if not isinstance(on_val, dict):
        return {}
    return on_val


def harbor_callers(
    experimental: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Return ``(job_id, job)`` for every job that calls harbor-build-image.yml."""
    jobs = experimental.get("jobs", {})
    if not isinstance(jobs, dict):
        return []
    callers: list[tuple[str, dict[str, object]]] = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if isinstance(uses, str) and uses.endswith("harbor-build-image.yml"):
            callers.append((job_id, job))
    return callers


def _workflow_call(harbor: dict[str, object]) -> dict[str, object]:
    on = get_on(harbor)
    workflow_call = on.get("workflow_call", {})
    if not isinstance(workflow_call, dict):
        return {}
    return workflow_call


def declared_harbor_outputs(harbor: dict[str, object]) -> set[str]:
    """Return the set of declared workflow_call.outputs keys."""
    outputs = _workflow_call(harbor).get("outputs", {})
    if not isinstance(outputs, dict):
        return set()
    return {key for key in outputs.keys()}


def declared_harbor_inputs(harbor: dict[str, object]) -> set[str]:
    """Return the set of declared workflow_call.inputs keys."""
    inputs = _workflow_call(harbor).get("inputs", {})
    if not isinstance(inputs, dict):
        return set()
    return {key for key in inputs.keys()}


def declared_harbor_secrets(harbor: dict[str, object]) -> set[str]:
    """Return the set of declared workflow_call.secrets keys."""
    secrets = _workflow_call(harbor).get("secrets", {})
    if not isinstance(secrets, dict):
        return set()
    return {key for key in secrets.keys()}