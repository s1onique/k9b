"""Helper utilities for k9b-live-lab-toolchain action tests.

This module contains non-test helper functions and path constants extracted
from the main test file to keep line counts below the LLM-friendly gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__test__ = False


# Path to the toolchain action file
TOOLCHAIN_ACTION_FILE = Path(__file__).parent.parent.parent / ".github/actions/k9b-live-lab-toolchain/action.yml"

# Path to the OTel live lab workflow
OTEL_LIVE_LAB_WORKFLOW = Path(__file__).parent.parent.parent / ".github/workflows/k9b-otel-demo-live-lab.yml"

# Path to the CNPG incident lab live workflow
CNPG_LIVE_LAB_WORKFLOW = Path(__file__).parent.parent.parent / ".github/workflows/k9b-cnpg-incident-lab-live.yml"

# Path to the requirements file
REQUIREMENTS_LIVE_LAB = Path(__file__).parent.parent.parent / "requirements-live-lab.txt"


def _load_action_yaml(path: Path) -> dict[str, Any]:
    """Load YAML from action file."""
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def _get_step_ids(action: dict) -> list[str]:
    """Extract step IDs from action steps."""
    return [
        step.get("id", "")
        for step in action.get("runs", {}).get("steps", [])
        if step.get("id")
    ]


def _get_step_by_id(action: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    """Get step by its id."""
    for step in action.get("runs", {}).get("steps", []):
        if step.get("id") == step_id:
            return step  # type: ignore[no-any-return]
    return None


def _get_step_names(action: dict) -> list[str]:
    """Extract step names from action steps."""
    return [
        step.get("name", "")
        for step in action.get("runs", {}).get("steps", [])
    ]
