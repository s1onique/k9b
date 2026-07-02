"""Policy gate: Docker and Buildx/QEMU wiring security.

Verifies:
1. No inline Docker login with direct ${{ secrets.* }} interpolation
2. No inline Buildx setup commands outside wire_docker_buildx.sh
3. No inline QEMU/binfmt setup outside wire_qemu_binfmt.sh
4. Wire scripts exist and have required properties
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.github_actions_hermetic_policy_helpers import (
    ROOT,
    collect_runs_in_yaml,
    find_yaml_files,
    load_yaml_file,
)

# ---------------------------------------------------------------------
# Docker login security
# ---------------------------------------------------------------------


class TestDockerLoginSecurity:
    """Regression tests for Docker login security hygiene."""

    @pytest.mark.parametrize(
        "yaml_path",
        [p for p in find_yaml_files() if p.suffix in (".yml", ".yaml")],
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_inline_docker_login_with_secrets(self, yaml_path: Path) -> None:
        """Fail on inline 'docker login' with direct ${{ secrets.* }} interpolation.

        Workflows must use scripts/ci/docker_login.sh instead of piping secrets
        to 'docker login' inline. This prevents secrets from appearing in shell
        history or CI logs.
        """
        data = load_yaml_file(yaml_path)
        run_blocks = collect_runs_in_yaml(data)

        violations: list[str] = []
        for block in run_blocks:
            # Check for 'docker login' followed by '${{ secrets.' in same run block
            if "docker login" in block and "${{ secrets." in block:
                # Extract the relevant lines for diagnostics
                lines = [line for line in block.splitlines() if "secrets" in line or "docker login" in line]
                violations.append(f"Lines: {', '.join(line.strip() for line in lines[:3])}")

        assert not violations, (
            f"{yaml_path.relative_to(ROOT)}: inline 'docker login' with "
            f"${{ secrets.* }} interpolation found. Use scripts/ci/docker_login.sh instead.\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------
# Buildx and QEMU/binfmt wiring
# ---------------------------------------------------------------------


class TestQemuBinfmtAndBuildxWiring:
    """Regression tests to ensure QEMU/binfmt and Buildx wiring is centralized."""

    @pytest.mark.parametrize(
        "yaml_path",
        [p for p in find_yaml_files() if p.suffix in (".yml", ".yaml") and "/workflows/" in str(p)],
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_inline_buildx_commands(self, yaml_path: Path) -> None:
        """Fail on inline 'docker buildx create/use/inspect --bootstrap' unless using wire script.

        Workflows must use scripts/ci/wire_docker_buildx.sh instead of inline buildx commands.
        This prevents drift and ensures consistent builder configuration.
        """
        data = load_yaml_file(yaml_path)
        run_blocks = collect_runs_in_yaml(data)

        violations: list[str] = []
        for block in run_blocks:
            # Check for inline buildx commands
            has_inline_buildx = any(cmd in block for cmd in [
                "docker buildx create",
                "docker buildx use",
                "docker buildx inspect --bootstrap",
            ])
            uses_wire_script = "wire_docker_buildx.sh" in block
            if has_inline_buildx and not uses_wire_script:
                # Extract relevant lines for diagnostics
                lines = [line.strip() for line in block.splitlines() if any(
                    cmd in line for cmd in ["docker buildx", "buildx create", "buildx use", "buildx inspect"]
                )]
                violations.append(f"Lines: {', '.join(lines[:2])}")

        assert not violations, (
            f"{yaml_path.relative_to(ROOT)}: inline 'docker buildx' commands found. "
            f"Use scripts/ci/wire_docker_buildx.sh instead.\n"
            + "\n".join(violations)
        )

    @pytest.mark.parametrize(
        "yaml_path",
        [p for p in find_yaml_files() if p.suffix in (".yml", ".yaml") and "/workflows/" in str(p)],
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_inline_qemu_binfmt_setup(self, yaml_path: Path) -> None:
        """Fail on inline QEMU/binfmt setup unless using wire script.

        Workflows must use scripts/ci/wire_qemu_binfmt.sh instead of inline binfmt setup.
        This prevents drift and ensures consistent QEMU configuration.
        """
        data = load_yaml_file(yaml_path)
        run_blocks = collect_runs_in_yaml(data)

        violations: list[str] = []
        for block in run_blocks:
            # Check for inline binfmt setup
            has_inline_binfmt = any(pattern in block for pattern in [
                "tonistiigi/binfmt",
                "--install aarch64",
                "/proc/sys/fs/binfmt_misc/qemu-aarch64",
                "binfmt_misc/qemu-aarch64",
            ])
            uses_wire_script = "wire_qemu_binfmt.sh" in block
            if has_inline_binfmt and not uses_wire_script:
                # Extract relevant lines for diagnostics
                lines = [line.strip() for line in block.splitlines() if any(
                    pattern in line for pattern in ["binfmt", "qemu", "aarch64", "tonistiigi"]
                )]
                violations.append(f"Lines: {', '.join(lines[:2])}")

        assert not violations, (
            f"{yaml_path.relative_to(ROOT)}: inline QEMU/binfmt setup found. "
            f"Use scripts/ci/wire_qemu_binfmt.sh instead.\n"
            + "\n".join(violations)
        )

    def test_wire_scripts_exist_and_have_required_properties(self) -> None:
        """Verify wire scripts exist and have required properties."""
        ci_scripts_dir = ROOT / "scripts" / "ci"
        if not ci_scripts_dir.exists():
            pytest.skip("scripts/ci/ directory not found")

        required_scripts: dict[str, dict[str, str | bool | list[str]]] = {
            "wire_qemu_binfmt.sh": {
                "marker": "CI-HERMETIC-TOOLCACHE",
                "has_set_euo_pipefail": True,
                "forbidden_actions": ["docker/setup-qemu-action"],
                "uses_harbor_cache": True,
            },
            "wire_docker_buildx.sh": {
                "marker": "CI-HERMETIC-TOOLCACHE",
                "has_set_euo_pipefail": True,
                "forbidden_actions": ["docker/setup-buildx-action"],
                "uses_harbor_cache": True,
            },
        }

        violations: list[str] = []
        for script_name, requirements in required_scripts.items():
            script_path = ci_scripts_dir / script_name
            if not script_path.exists():
                violations.append(f"{script_name}: does not exist")
                continue

            content = script_path.read_text(encoding="utf-8")
            marker = str(requirements["marker"])
            has_set_euo_pipefail = bool(requirements["has_set_euo_pipefail"])
            forbidden_actions = requirements["forbidden_actions"]
            assert isinstance(forbidden_actions, list)
            uses_harbor_cache = bool(requirements["uses_harbor_cache"])

            # Check for CI-HERMETIC-TOOLCACHE marker
            if marker not in content:
                violations.append(f"{script_name}: missing '{marker}' marker")

            # Check for set -euo pipefail
            if has_set_euo_pipefail:
                if "set -euo pipefail" not in content:
                    violations.append(f"{script_name}: missing 'set -euo pipefail'")

            # Check for forbidden actions
            for forbidden in forbidden_actions:
                if forbidden in content:
                    violations.append(f"{script_name}: contains forbidden action '{forbidden}'")

            # Check for Harbor proxy-cache usage (no direct Docker Hub pulls)
            if uses_harbor_cache:
                # Should use Harbor proxy-cache images
                if "harbor-pve1.spbnix.local" not in content:
                    violations.append(f"{script_name}: should use Harbor proxy-cache images")
                # Should NOT pull directly from Docker Hub (except in comments)
                lines_without_comments = [
                    line for line in content.splitlines()
                    if not line.strip().startswith("#") and "tonistiigi/binfmt" in line
                ]
                if lines_without_comments and "dockerhub-cache" not in "".join(lines_without_comments):
                    violations.append(f"{script_name}: appears to pull directly from Docker Hub (should use Harbor proxy-cache)")

        assert not violations, (
            "Wire script validation failed:\n" + "\n".join(violations)
        )
