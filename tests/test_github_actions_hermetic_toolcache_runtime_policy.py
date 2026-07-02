"""Policy gate: Python wiring and toolcache runtime contracts.

Verifies:
1. Python wiring in k9b-live-lab-toolchain includes required paths
2. No ${runner.tool_cache} in shell scripts
3. Wire scripts export PATH before proof commands
4. No manual RUNNER_TOOL_CACHE/Python probing outside wire_toolcache_python.sh
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.github_actions_hermetic_policy_helpers import (
    HERMETIC_TOOLCACHE_MARKER,
    ROOT,
    collect_runs_in_yaml,
    file_contains_marker,
    find_yaml_files,
    load_yaml_file,
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
# Runtime hazard regressions
# ---------------------------------------------------------------------


class TestRuntimeHazardRegression:
    """Regression tests for known runtime hazards in shell wiring."""

    def test_no_runner_tool_cache_in_shell_scripts(self) -> None:
        """Checked-in shell scripts must not use '${runner.tool_cache}' (GitHub expression, not Bash var)."""
        # Forbidden: ${runner.tool_cache} is a GitHub expression, not a Bash variable.
        # Scripts must use RUNNER_TOOL_CACHE env var or AGENT_TOOLSDIRECTORY fallback.
        ci_scripts_dir = ROOT / "scripts" / "ci"
        if not ci_scripts_dir.exists():
            pytest.skip("scripts/ci/ directory not found")

        forbidden_pattern = "${runner.tool_cache}"
        violations: list[tuple[Path, str]] = []

        for shell_file in ci_scripts_dir.glob("*.sh"):
            content = shell_file.read_text(encoding="utf-8")
            if forbidden_pattern in content:
                # Find line numbers for diagnostics
                lines_with_violation = [
                    f"  line {i+1}: {line.rstrip()}"
                    for i, line in enumerate(content.splitlines())
                    if forbidden_pattern in line
                ]
                violations.append((shell_file, "\n".join(lines_with_violation)))

        assert not violations, (
            "Checked-in shell scripts must not use '${runner.tool_cache}' "
            "(GitHub expression, not Bash variable). "
            "Use RUNNER_TOOL_CACHE env var or AGENT_TOOLSDIRECTORY fallback.\n"
            + "\n".join(
                f"{path.relative_to(ROOT)}:\n{violation}"
                for path, violation in violations
            )
        )

    def test_wire_scripts_export_path_before_proof(self) -> None:
        """Wire scripts must export PATH before running verification commands."""
        ci_scripts_dir = ROOT / "scripts" / "ci"
        if not ci_scripts_dir.exists():
            pytest.skip("scripts/ci/ directory not found")

        # For each wire script, check that 'export PATH=' appears before
        # any proof command (invoking the tool with --version, -VV, etc.)
        violations: list[tuple[Path, str]] = []

        for shell_file in ci_scripts_dir.glob("*.sh"):
            content = shell_file.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Find position of first "export PATH=" (not LD_LIBRARY_PATH, not in comments)
            export_path_line = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("export PATH=") and "LD_LIBRARY_PATH" not in stripped:
                    export_path_line = i
                    break

            # Find position of first proof command invocation
            proof_line = None
            proof_patterns = [
                '"${PYTHON_BIN}" -',   # Python invocation with flag
                '"${GO_BIN}/go" ve',   # Go version invocation
                '"${NODE_BIN}" --',     # Node invocation with flag
                '"${HELM_PATH}" ve',   # Helm version invocation
                '"${KUBECTL_PATH}" ve', # kubectl version invocation
                "npm --version",        # npm (no path variable)
            ]
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue
                # Skip variable assignments (e.g., PYTHON_BIN="${...}")
                if "=" in stripped and not stripped.startswith("export "):
                    continue
                # Skip echo statements and command -v checks
                if stripped.startswith("echo ") or "command -v" in stripped:
                    continue
                # Look for proof command invocations
                for pattern in proof_patterns:
                    if pattern in stripped:
                        proof_line = i
                        break
                if proof_line is not None:
                    break

            if proof_line is not None and (export_path_line is None or export_path_line > proof_line):
                violations.append((
                    shell_file,
                    f"  export PATH at line {export_path_line + 1 if export_path_line else 'NOT FOUND'}, "
                    f"proof command at line {proof_line + 1}"
                ))

        assert not violations, (
            "Wire scripts must export PATH before running proof commands.\n"
            + "\n".join(
                f"{path.relative_to(ROOT)}: {v}"
                for path, v in violations
            )
        )


# ---------------------------------------------------------------------
# No manual toolcache probing
# ---------------------------------------------------------------------


class TestNoManualToolcacheProbing:
    """Regression tests to ensure Python toolcache probing is centralized."""

    @pytest.mark.parametrize(
        "yaml_path",
        [p for p in find_yaml_files() if p.suffix in (".yml", ".yaml") and "/workflows/" in str(p)],
        ids=lambda p: str(p.relative_to(ROOT)),
    )
    def test_no_manual_python_toolcache_probing(self, yaml_path: Path) -> None:
        """Fail on manual RUNNER_TOOL_CACHE/Python path probing unless using shared script.

        Workflows must use scripts/ci/wire_toolcache_python.sh instead of manually
        checking for Python at specific paths in RUNNER_TOOL_CACHE. This prevents
        drift when Python patch versions change.
        """
        data = load_yaml_file(yaml_path)
        run_blocks = collect_runs_in_yaml(data)

        violations: list[str] = []
        for block in run_blocks:
            # Check for manual RUNNER_TOOL_CACHE/Python probing
            has_manual_probe = "RUNNER_TOOL_CACHE" in block and "/Python/" in block
            uses_shared_script = "wire_toolcache_python.sh" in block
            if has_manual_probe and not uses_shared_script:
                violations.append(block[:100])

        assert not violations, (
            f"{yaml_path.relative_to(ROOT)}: manual RUNNER_TOOL_CACHE/Python probing "
            f"found. Use scripts/ci/wire_toolcache_python.sh instead.\n"
            + "\n".join(violations)
        )
