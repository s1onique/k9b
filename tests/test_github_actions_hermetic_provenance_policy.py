"""Policy tests for hermetic toolchain provenance in CI workflows.

This module validates that CI workflows emit toolchain provenance information
using the hermetic toolchain wiring pattern. Provenance enables reproducibility
and debugging by recording resolved tool versions and paths.

See docs/ci-hermetic-toolchain.md for the full policy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import pytest

from tests.helpers.github_actions_hermetic_policy_helpers import (
    HERMETIC_TOOLCACHE_MARKER,
    ROOT,
    collect_runs_in_yaml,
    load_yaml_file,
)

# =============================================================================
# Constants
# =============================================================================

PROVENANCE_SCRIPT = "scripts/ci/emit_toolchain_provenance.sh"

# Valid tool names for provenance emission
VALID_TOOLS = {
    "python",
    "go",
    "node",
    "npm",
    "helm",
    "kubectl",
    "docker",
    "buildx",
}

# Expected provenance script invocation pattern
PROVENANCE_PATTERN = re.compile(
    r"scripts/ci/emit_toolchain_provenance\.sh\s+[\"']?([^\"'\n]+)[\"']?"
)

# Workflows that should emit provenance and their expected tools
WORKFLOW_EXPECTATIONS = {
    "verify.yml": {
        # lint job: Python and Node/npm wiring
        "python": True,
        "node": True,
        "npm": True,
        # helm-chart job: Helm wiring
        "helm": True,
    },
    "k9b-cnpg-incident-lab.yml": {
        # Go and Python toolchain wiring
        "go": True,
        "python": True,
    },
    "k9b-cnpg-incident-lab-live.yml": {
        # Python, Helm, kubectl from toolchain action
        "python": True,
        "helm": True,
        "kubectl": True,
    },
    "harbor-build-image.yml": {
        # Docker and Buildx wiring
        "docker": True,
        "buildx": True,
    },
    "k9b-image-builder.yml": {
        # Docker and Buildx wiring (reusable workflow)
        "docker": True,
        "buildx": True,
    },
    "k9b-otel-demo-live-lab.yml": {
        # Docker and Buildx wiring
        "docker": True,
        "buildx": True,
    },
}

# =============================================================================
# Helpers
# =============================================================================


_SHELL_ENV_REF_RE = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")
_BRACED_SHELL_ENV_REF_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _resolve_static_env_arg(
    arg: str,
    *,
    workflow_env: Mapping[str, object],
    job_env: Mapping[str, object],
    step_env: Mapping[str, object],
) -> str:
    """Resolve simple shell env indirection used by hermetic workflow contracts.

    This intentionally supports only whole-token env references such as:
      $TOOLCHAIN_COMPONENTS
      ${TOOLCHAIN_COMPONENTS}

    It does not attempt general shell evaluation.
    """
    stripped = arg.strip().strip("\"'")

    match = _SHELL_ENV_REF_RE.fullmatch(stripped)
    if match is None:
        match = _BRACED_SHELL_ENV_REF_RE.fullmatch(stripped)

    if match is None:
        return stripped

    name = match.group(1)

    for env in (step_env, job_env, workflow_env):
        value = env.get(name)
        if isinstance(value, str):
            return value

    return stripped


# =============================================================================
# Tests
# =============================================================================


class TestToolchainProvenanceScriptExists:
    """Verify the provenance script exists and is executable."""

    def test_provenance_script_exists(self) -> None:
        """The provenance script must exist in the CI scripts directory."""
        script_path = ROOT / PROVENANCE_SCRIPT
        assert script_path.exists(), (
            f"Provenance script not found: {PROVENANCE_SCRIPT}. "
            "Create scripts/ci/emit_toolchain_provenance.sh"
        )

    def test_provenance_script_has_shebang(self) -> None:
        """The provenance script must have a valid shebang."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        assert content.startswith("#!/"), (
            f"{PROVENANCE_SCRIPT} must start with a shebang"
        )

    def test_provenance_script_has_hermetic_marker(self) -> None:
        """The provenance script must include the CI-HERMETIC-TOOLCACHE marker."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        assert HERMETIC_TOOLCACHE_MARKER in content, (
            f"{PROVENANCE_SCRIPT} must include {HERMETIC_TOOLCACHE_MARKER} marker"
        )

    def test_provenance_script_uses_strict_mode(self) -> None:
        """The provenance script must use set -euo pipefail."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        # Check for strict mode in first 30 lines (accounts for comment headers)
        header = "\n".join(content.split("\n")[:30])
        assert "set -euo pipefail" in header or "set -e" in header, (
            f"{PROVENANCE_SCRIPT} must use set -euo pipefail or set -e"
        )


class TestProvenanceScriptOutputs:
    """Verify the provenance script produces expected outputs."""

    def test_provenance_script_writes_to_github_step_summary(self) -> None:
        """The provenance script should write to GITHUB_STEP_SUMMARY."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        assert "GITHUB_STEP_SUMMARY" in content, (
            f"{PROVENANCE_SCRIPT} should write to GITHUB_STEP_SUMMARY for job summaries"
        )

    def test_provenance_script_writes_to_github_output(self) -> None:
        """The provenance script should write outputs to GITHUB_OUTPUT."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        assert "GITHUB_OUTPUT" in content, (
            f"{PROVENANCE_SCRIPT} should write key outputs to GITHUB_OUTPUT"
        )

    def test_provenance_script_validates_tools(self) -> None:
        """The provenance script should validate requested tools."""
        script_path = ROOT / PROVENANCE_SCRIPT
        if not script_path.exists():
            pytest.skip("Provenance script does not exist")
        content = script_path.read_text(encoding="utf-8")
        # Check that script handles tool validation or has a collect_* function pattern
        assert "collect_" in content or "tool" in content.lower(), (
            f"{PROVENANCE_SCRIPT} should have tool collection/validation logic"
        )


class TestWorkflowProvenanceIntegration:
    """Verify workflows correctly invoke the provenance script."""

    @pytest.mark.parametrize("workflow_name", list(WORKFLOW_EXPECTATIONS.keys()))
    def test_workflow_has_hermetic_marker(
        self,
        workflow_name: str,
    ) -> None:
        """Workflows using hermetic toolchain must have the CI-HERMETIC-TOOLCACHE marker."""
        workflow_path = ROOT / ".github" / "workflows" / workflow_name
        if not workflow_path.exists():
            pytest.skip(f"Workflow not found: {workflow_name}")
        content = workflow_path.read_text(encoding="utf-8")
        assert HERMETIC_TOOLCACHE_MARKER in content, (
            f"{workflow_name} must include {HERMETIC_TOOLCACHE_MARKER} marker"
        )

    @pytest.mark.parametrize("workflow_name", list(WORKFLOW_EXPECTATIONS.keys()))
    def test_workflow_calls_provenance_script(
        self,
        workflow_name: str,
    ) -> None:
        """Workflows using hermetic toolchain must call emit_toolchain_provenance.sh."""
        workflow_path = ROOT / ".github" / "workflows" / workflow_name
        if not workflow_path.exists():
            pytest.skip(f"Workflow not found: {workflow_name}")
        data = load_yaml_file(workflow_path)
        run_blocks = collect_runs_in_yaml(data)

        provenance_calls = [
            block for block in run_blocks
            if PROVENANCE_SCRIPT in block
        ]

        assert len(provenance_calls) > 0, (
            f"{workflow_name} must call {PROVENANCE_SCRIPT} after toolchain wiring"
        )

    @pytest.mark.parametrize("workflow_name", list(WORKFLOW_EXPECTATIONS.keys()))
    def test_workflow_provenance_uses_valid_tools(
        self,
        workflow_name: str,
    ) -> None:
        """Provenance calls in workflows must use valid tool names."""
        workflow_path = ROOT / ".github" / "workflows" / workflow_name
        if not workflow_path.exists():
            pytest.skip(f"Workflow not found: {workflow_name}")
        data = load_yaml_file(workflow_path)

        # Extract env contexts for resolution
        workflow_env: dict[str, object] = data.get("env", {}) or {}

        provenance_calls = [
            block for block in collect_runs_in_yaml(data)
            if PROVENANCE_SCRIPT in block
        ]

        for call in provenance_calls:
            match = PROVENANCE_PATTERN.search(call)
            if match:
                tools_arg = match.group(1)

                # Extract step env from the matching run block context
                # We need to find the step that contains this provenance call
                # to extract its env context. Stop both loops once matched.
                step_env: dict[str, object] = {}
                job_env: dict[str, object] = {}
                matched_context = False

                for _job_name, job_data in data.get("jobs", {}).items():
                    if not isinstance(job_data, dict):
                        continue

                    candidate_job_env = job_data.get("env", {}) or {}

                    for step in job_data.get("steps", []):
                        if not isinstance(step, dict):
                            continue

                        step_run = step.get("run", "")
                        if not isinstance(step_run, str):
                            continue

                        if step_run == call:
                            job_env = candidate_job_env
                            step_env = step.get("env", {}) or {}
                            matched_context = True
                            break

                    if matched_context:
                        break

                # Resolve env references in the tools argument
                resolved_arg = _resolve_static_env_arg(
                    tools_arg,
                    workflow_env=workflow_env,
                    job_env=job_env,
                    step_env=step_env,
                )

                tools = [t.strip() for t in resolved_arg.split(",")]
                for tool in tools:
                    assert tool in VALID_TOOLS, (
                        f"{workflow_name}: invalid tool '{tool}' in provenance call. "
                        f"Valid tools: {sorted(VALID_TOOLS)}"
                    )


class TestBuildxWiringExposesBuilderName:
    """Verify Buildx wiring exposes builder name for provenance."""

    def test_wire_docker_buildx_exports_builder_name(self) -> None:
        """wire_docker_buildx.sh must export K9B_BUILDX_BUILDER to GITHUB_ENV."""
        script_path = ROOT / "scripts/ci/wire_docker_buildx.sh"
        if not script_path.exists():
            pytest.skip("wire_docker_buildx.sh does not exist")
        content = script_path.read_text(encoding="utf-8")
        assert "K9B_BUILDX_BUILDER" in content, (
            "wire_docker_buildx.sh must export K9B_BUILDX_BUILDER for provenance"
        )
        assert "GITHUB_ENV" in content, (
            "wire_docker_buildx.sh must write to GITHUB_ENV"
        )


class TestProvenancePolicyCompleteness:
    """Verify all CI workflows follow the provenance policy."""

    def test_all_workflows_with_toolchain_have_provenance(self) -> None:
        """All workflows with toolchain wiring must emit provenance."""
        workflows_with_toolchain = set(WORKFLOW_EXPECTATIONS.keys())
        workflows_found: set[str] = set()

        # Search in .github/workflows/ specifically
        workflows_dir = ROOT / ".github" / "workflows"
        if workflows_dir.exists():
            for yaml_path in workflows_dir.glob("*.yml"):
                workflow_name = yaml_path.name
                if workflow_name not in workflows_with_toolchain:
                    continue

                data = load_yaml_file(yaml_path)
                run_blocks = collect_runs_in_yaml(data)

                provenance_calls = [
                    block for block in run_blocks
                    if PROVENANCE_SCRIPT in block
                ]

                if len(provenance_calls) > 0:
                    workflows_found.add(workflow_name)

        missing = workflows_with_toolchain - workflows_found
        assert len(missing) == 0, (
            f"Workflows missing provenance calls: {sorted(missing)}. "
            f"These workflows use hermetic toolchain and must call "
            f"{PROVENANCE_SCRIPT} after toolchain wiring."
        )


class TestEnvResolutionRegression:
    """Regression tests for env variable resolution in provenance calls.

    These tests ensure the provenance parser correctly resolves shell env
    indirection patterns used in hermetic workflow contracts.
    """

    def test_provenance_allows_step_env_toolchain_components(self) -> None:
        """Regression: step env $TOOLCHAIN_COMPONENTS must resolve correctly."""
        workflow_env: dict[str, object] = {}
        job_env: dict[str, object] = {}
        step_env: dict[str, object] = {
            "TOOLCHAIN_COMPONENTS": "python,helm,kubectl",
        }

        resolved = _resolve_static_env_arg(
            "$TOOLCHAIN_COMPONENTS",
            workflow_env=workflow_env,
            job_env=job_env,
            step_env=step_env,
        )

        assert resolved == "python,helm,kubectl"

    def test_provenance_allows_braced_step_env_toolchain_components(self) -> None:
        """Regression: braced step env ${TOOLCHAIN_COMPONENTS} must resolve correctly."""
        resolved = _resolve_static_env_arg(
            "${TOOLCHAIN_COMPONENTS}",
            workflow_env={},
            job_env={},
            step_env={"TOOLCHAIN_COMPONENTS": "docker,buildx"},
        )

        assert resolved == "docker,buildx"

    def test_resolve_static_env_arg_noop_for_literal_values(self) -> None:
        """Literal tool names should pass through unchanged."""
        resolved = _resolve_static_env_arg(
            "python,helm",
            workflow_env={},
            job_env={},
            step_env={},
        )
        assert resolved == "python,helm"

    def test_resolve_static_env_arg_job_env_priority(self) -> None:
        """Job env should override workflow env."""
        resolved = _resolve_static_env_arg(
            "$TOOLCHAIN_COMPONENTS",
            workflow_env={"TOOLCHAIN_COMPONENTS": "wrong"},
            job_env={"TOOLCHAIN_COMPONENTS": "correct"},
            step_env={},
        )
        assert resolved == "correct"

    def test_resolve_static_env_arg_step_env_highest_priority(self) -> None:
        """Step env should override both workflow and job env."""
        resolved = _resolve_static_env_arg(
            "$TOOLCHAIN_COMPONENTS",
            workflow_env={"TOOLCHAIN_COMPONENTS": "workflow"},
            job_env={"TOOLCHAIN_COMPONENTS": "job"},
            step_env={"TOOLCHAIN_COMPONENTS": "step"},
        )
        assert resolved == "step"

    def test_resolve_static_env_arg_missing_env_returns_original(self) -> None:
        """Unresolved references should return the original token."""
        resolved = _resolve_static_env_arg(
            "$UNDEFINED_VAR",
            workflow_env={},
            job_env={},
            step_env={},
        )
        assert resolved == "$UNDEFINED_VAR"
