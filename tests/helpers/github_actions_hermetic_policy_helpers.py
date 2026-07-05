"""Shared helpers for GitHub Actions hermetic policy tests.

This module contains constants, YAML loading utilities, and helper functions
used across the hermetic policy test modules.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

__test__ = False

ROOT = Path(__file__).parent.parent.parent
HERMETIC_TOOLCACHE_MARKER = "CI-HERMETIC-TOOLCACHE"

# Simple prefix-based forbidden patterns (LLM-friendly)
FORBIDDEN_ACTION_PREFIXES = (
    "actions/setup-",
    "azure/setup-",
    "docker/setup-",
    "helm/",
    "azure/setup-helm",
    "docker/login-",
)

# Prefix-based allowlist for tool installers that use version pinning and caching,
# and for repo-local actions. These are KNOWN EXCEPTIONS, not preferred patterns.
#
# Tool installers (actions/setup-go) differ from forbidden setup-* actions
# (setup-python, setup-node) because they use built-in Go module caching
# and install pinned tool versions once per job.
_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # Repo-local actions
    "./",
    # Tool installer action - installs pinned Go tool with built-in caching.
    "actions/setup-go",
)

# Exact-match allowlist for unversioned actions
_ALLOWLIST_EXACT: frozenset[str] = frozenset({
    "actions/checkout",
    "actions/cache",
    "actions/download-artifact",
    "actions/upload-artifact",
    "actions/github-script",
    "github/script",
})


def _is_allowlisted(action: str) -> bool:
    """Check if an action is allowlisted (exact or prefix match)."""
    if action in _ALLOWLIST_EXACT:
        return True
    for prefix in _ALLOWLIST_PREFIXES:
        if action == prefix or action.startswith(prefix):
            return True
    return False


REQUIRED_DOCTRINE_TERMS = [
    "CI-HERMETIC-TOOLCACHE",
    "shell-first",
    "toolcache-first",
    "RUNNER_TOOL_CACHE",
    "AGENT_TOOLSDIRECTORY",
    "fail fast",
    "libpython",
    "LD_LIBRARY_PATH",
    "python3 -VV",
    "sys.executable",
]


def find_yaml_files(pattern: str = "**/*.yml") -> Iterator[Path]:
    """Find YAML files in .github/ directory."""
    github_dir = ROOT / ".github"
    if not github_dir.exists():
        pytest.skip(".github/ directory not found")
    yield from github_dir.glob(pattern)


def load_yaml_file(path: Path) -> dict:
    """Load YAML file; hard fail on parse error for workflow policy gates."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"{path} did not parse to a YAML mapping"
    return data


def collect_uses_in_yaml(data: dict) -> list[str]:
    """Recursively collect all 'uses' values from a YAML dict."""
    uses = []
    if isinstance(data, dict):
        if "uses" in data and isinstance(data["uses"], str):
            uses.append(data["uses"])
        for v in data.values():
            uses.extend(collect_uses_in_yaml(v))
    elif isinstance(data, list):
        for item in data:
            uses.extend(collect_uses_in_yaml(item))
    return uses


def collect_runs_in_yaml(data: dict) -> list[str]:
    """Recursively collect all 'run' block contents from a YAML dict."""
    run_blocks: list[str] = []
    def _collect(d: dict | list) -> None:
        if isinstance(d, dict):
            if "run" in d and isinstance(d["run"], str):
                run_blocks.append(d["run"])
            for v in d.values():
                _collect(v)
        elif isinstance(d, list):
            for item in d:
                _collect(item)
    _collect(data)
    return run_blocks


def file_contains_marker(path: Path, marker: str) -> bool:
    """Check if file contains the given marker string."""
    try:
        with open(path, encoding="utf-8") as f:
            return marker in f.read()
    except OSError:
        return False


def is_action_forbidden(action: str) -> bool:
    """Check if an action is forbidden (not allowlisted and matches forbidden prefix)."""
    if _is_allowlisted(action):
        return False
    return any(action.startswith(p) for p in FORBIDDEN_ACTION_PREFIXES)
