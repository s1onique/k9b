"""Policy gate: CI hermetic toolchain doctrine enforcement.

Verifies:
1. Doctrine doc exists and contains required terms
2. All workflow/action YAMLs have CI-HERMETIC-TOOLCACHE marker
3. No forbidden action patterns (setup/download actions)
4. Python wiring in k9b-live-lab-toolchain includes LD_LIBRARY_PATH

CI-HERMETIC-TOOLCACHE doctrine contract.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
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

# Prefix-based allowlist - these are KNOWN EXCEPTIONS, not preferred patterns
_ALLOWLIST_PREFIXES = (
    # Repo-local actions
    "./",
)

# Exact-match allowlist for unversioned actions
_ALLOWLIST_EXACT = {
    "actions/checkout",
    "actions/cache",
    "actions/download-artifact",
    "actions/upload-artifact",
    "actions/github-script",
    "github/script",
}


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


def load_yaml_file(path: Path) -> dict | None:
    """Load YAML file safely."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]
    except (yaml.YAMLError, OSError):
        return None


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


def file_contains_marker(path: Path, marker: str) -> bool:
    """Check if file contains the given marker string."""
    try:
        with open(path, encoding="utf-8") as f:
            return marker in f.read()
    except OSError:
        return False


# ---------------------------------------------------------------------
# Doctrine existence and content
# ---------------------------------------------------------------------


class TestDoctrineExists:
    def test_doctrine_file_exists(self) -> None:
        """docs/ci-hermetic-toolchain.md must exist."""
        path = ROOT / "docs" / "ci-hermetic-toolchain.md"
        assert path.exists(), f"Doctrine file not found: {path}"

    def test_doctrine_contains_required_terms(self) -> None:
        """Doctrine must contain all required terms."""
        path = ROOT / "docs" / "ci-hermetic-toolchain.md"
        if not path.exists():
            pytest.skip("Doctrine file not found")
        content = path.read_text(encoding="utf-8")
        missing = [t for t in REQUIRED_DOCTRINE_TERMS if t not in content]
        assert not missing, f"Doctrine missing terms: {missing}"


# ---------------------------------------------------------------------
# Marker presence in workflow/action YAMLs
# ---------------------------------------------------------------------


class TestWorkflowsAndActionsHaveMarker:
    """Every .github workflow/action YAML must carry CI-HERMETIC-TOOLCACHE."""

    @pytest.mark.parametrize(
        "yaml_path",
        list(find_yaml_files()),
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_has_marker(self, yaml_path: Path) -> None:
        """Each YAML file must contain the CI-HERMETIC-TOOLCACHE comment block."""
        assert file_contains_marker(yaml_path, HERMETIC_TOOLCACHE_MARKER), (
            f"{yaml_path.relative_to(ROOT)} missing "
            f"'{HERMETIC_TOOLCACHE_MARKER}' marker"
        )


# ---------------------------------------------------------------------
# Forbidden action patterns
# ---------------------------------------------------------------------


class TestForbiddenActions:
    """Workflows must not use forbidden setup/download action families."""

    @pytest.mark.parametrize(
        "yaml_path",
        [p for p in find_yaml_files() if p.suffix in (".yml", ".yaml")],
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_forbidden_actions(self, yaml_path: Path) -> None:
        """Fail on forbidden action patterns unless allowlisted."""
        data = load_yaml_file(yaml_path)
        if data is None:
            pytest.skip(f"Could not parse {yaml_path}")
        uses = collect_uses_in_yaml(data)
        violations = []
        for u in uses:
            if _is_allowlisted(u):
                continue
            for prefix in FORBIDDEN_ACTION_PREFIXES:
                if u.startswith(prefix):
                    violations.append(u)
                    break
        assert not violations, (
            f"{yaml_path.relative_to(ROOT)} uses forbidden actions: {violations}"
        )

    @pytest.mark.parametrize(
        "action,violates",
        [
            # Known-bad examples that MUST be flagged
            ("actions/setup-python@v6", True),
            ("actions/setup-node@v5", True),
            ("actions/setup-go@v5", True),
            ("azure/setup-helm@v4", True),
            ("docker/setup-buildx-action@v3", True),
            ("docker/login-action@v4", True),
            ("helm/toolkit-actions@v1", True),
            # Known-good examples that MUST pass
            ("actions/checkout@v4", False),
            ("actions/cache@v4", False),
            ("docker/build-push-action@v5", False),
            ("./my-local-action", False),
        ],
    )
    def test_known_bad_examples(self, action: str, violates: bool) -> None:
        """Prove that known-bad examples fail and known-good examples pass."""
        is_forbidden = not _is_allowlisted(action) and any(
            action.startswith(p) for p in FORBIDDEN_ACTION_PREFIXES
        )
        assert is_forbidden == violates, (
            f"Action '{action}' should {'violate' if violates else 'pass'}"
        )


# ---------------------------------------------------------------------
# Python wiring in k9b-live-lab-toolchain
# ---------------------------------------------------------------------


class TestToolchainActionPythonWiring:
    """k9b-live-lab-toolchain action.yml must prove Python executable startup."""

    def test_toolchain_action_exists(self) -> None:
        """k9b-live-lab-toolchain action.yml must exist."""
        path = ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
        assert path.exists(), f"Toolchain action not found: {path}"

    def test_action_has_hermetic_marker(self) -> None:
        """Toolchain action.yml must have CI-HERMETIC-TOOLCACHE marker."""
        path = ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
        assert file_contains_marker(path, HERMETIC_TOOLCACHE_MARKER), (
            f"{path} missing '{HERMETIC_TOOLCACHE_MARKER}' marker"
        )

    def test_python_wiring_includes_ld_library_path(self) -> None:
        """Python wiring must include LD_LIBRARY_PATH for shared library linking."""
        path = ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
        if not path.exists():
            pytest.skip("Toolchain action not found")
        content = path.read_text(encoding="utf-8")
        assert "LD_LIBRARY_PATH" in content, (
            "k9b-live-lab-toolchain must include LD_LIBRARY_PATH "
            "to load libpython shared libraries"
        )

    def test_python_wiring_includes_version_check(self) -> None:
        """Python wiring must include 'python3 -VV' to prove executable startup."""
        path = ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
        if not path.exists():
            pytest.skip("Toolchain action not found")
        content = path.read_text(encoding="utf-8")
        assert "python3 -VV" in content or "python -VV" in content, (
            "k9b-live-lab-toolchain must run 'python3 -VV' "
            "to prove executable startup"
        )

    def test_python_wiring_includes_sys_executable(self) -> None:
        """Python wiring must include sys.executable to prove executable path."""
        path = ROOT / ".github" / "actions" / "k9b-live-lab-toolchain" / "action.yml"
        if not path.exists():
            pytest.skip("Toolchain action not found")
        content = path.read_text(encoding="utf-8")
        assert "sys.executable" in content, (
            "k9b-live-lab-toolchain must check sys.executable "
            "to verify executable path"
        )


# ---------------------------------------------------------------------
# End of policy gate
# ---------------------------------------------------------------------
