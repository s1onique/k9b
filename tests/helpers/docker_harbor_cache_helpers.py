"""Shared helpers for Docker Harbor cache regression tests.

This module contains pure helper functions for loading and parsing GitHub
workflow YAML files. It is intentionally NOT named test_*.py so pytest
will not collect it as a test module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# Paths to workflow files that use docker/build-push-action
HARBOR_BUILD_IMAGE_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "harbor-build-image.yml"
)
K9B_IMAGE_BUILDER_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "k9b-image-builder.yml"
)
OTEL_DEMO_LIVE_LAB_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "k9b-otel-demo-live-lab.yml"
)


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def find_build_push_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Find all docker/build-push-action steps in a workflow."""
    steps = []
    for job_name, job in workflow.get("jobs", {}).items():
        job_steps = job.get("steps", [])
        for step in job_steps:
            if step.get("uses", "").startswith("docker/build-push-action"):
                steps.append(step)
    return steps


def extract_build_section(content: str, job_name: str) -> str:
    """Extract a job section from workflow YAML content."""
    build_start = content.find(f"{job_name}:")
    if build_start == -1:
        return ""
    next_marker = content.find("\n  # ======", build_start)
    if next_marker == -1:
        next_marker = len(content)
    return content[build_start:next_marker]
