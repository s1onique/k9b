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
# Regression tests: runtime hazards
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
            # Proof commands are when we actually invoke the tool with version flags:
            # - "${PYTHON_BIN}" -VV or "${PYTHON_BIN}" -c "import sys"
            # - "${GO_BIN}/go" version
            # - "${NODE_BIN}" --version
            # - npm --version
            # - "${HELM_PATH}" version
            # - "${KUBECTL_PATH}" version --client
            proof_line = None
            # Only match lines where the tool is ACTUALLY INVOKED (after the tool path)
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
# End of policy gate
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

        # Collect all 'run' blocks from the workflow
        run_blocks: list[str] = []
        def collect_runs(d: dict | list) -> None:
            if isinstance(d, dict):
                if "run" in d and isinstance(d["run"], str):
                    run_blocks.append(d["run"])
                for v in d.values():
                    collect_runs(v)
            elif isinstance(d, list):
                for item in d:
                    collect_runs(item)

        collect_runs(data)

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
        run_blocks: list[str] = []
        def collect_runs(d: dict | list) -> None:
            if isinstance(d, dict):
                if "run" in d and isinstance(d["run"], str):
                    run_blocks.append(d["run"])
                for v in d.values():
                    collect_runs(v)
            elif isinstance(d, list):
                for item in d:
                    collect_runs(item)
        collect_runs(data)

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
        run_blocks: list[str] = []
        def collect_runs(d: dict | list) -> None:
            if isinstance(d, dict):
                if "run" in d and isinstance(d["run"], str):
                    run_blocks.append(d["run"])
                for v in d.values():
                    collect_runs(v)
            elif isinstance(d, list):
                for item in d:
                    collect_runs(item)
        collect_runs(data)

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
        run_blocks: list[str] = []
        def collect_runs(d: dict | list) -> None:
            if isinstance(d, dict):
                if "run" in d and isinstance(d["run"], str):
                    run_blocks.append(d["run"])
                for v in d.values():
                    collect_runs(v)
            elif isinstance(d, list):
                for item in d:
                    collect_runs(item)
        collect_runs(data)

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
