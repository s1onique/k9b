"""Policy gate: CI hermetic toolchain doctrine enforcement.

Verifies:
1. Doctrine doc exists and contains required terms
2. All workflow/action YAMLs have CI-HERMETIC-TOOLCACHE marker
3. No forbidden action patterns (setup/download actions)
4. YAML parse failures hard-fail

CI-HERMETIC-TOOLCACHE doctrine contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.github_actions_hermetic_policy_helpers import (
    HERMETIC_TOOLCACHE_MARKER,
    REQUIRED_DOCTRINE_TERMS,
    ROOT,
    collect_uses_in_yaml,
    file_contains_marker,
    find_yaml_files,
    is_action_forbidden,
    load_yaml_file,
)

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
        uses = collect_uses_in_yaml(data)
        violations = [u for u in uses if is_action_forbidden(u)]
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
        is_forbidden = is_action_forbidden(action)
        assert is_forbidden == violates, (
            f"Action '{action}' should {'violate' if violates else 'pass'}"
        )
