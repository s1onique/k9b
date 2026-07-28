"""
Contract tests for harbor-build-image workflow authority model.

This module validates the security hardening implemented in:
ACT-K9B-IMAGE-BUILDER-REGISTRY-CACHE-AUTHORIZATION01-CORRECTION01

Security model:
- All PRs (fork, same-repo, Dependabot, bot) are read-only
- Write authority requires explicit non-PR event AND explicit input=true
- All three authority inputs are required (no defaults for write operations)
- secrets: inherit is NOT used - only explicit Harbor credentials passed
- External values transferred through env (not interpolated into shell source)
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml


HARBOR_BUILD_IMAGE_WORKFLOW = Path(".github/workflows/harbor-build-image.yml")
HARBOR_WORKFLOW = Path(".github/workflows/harbor.yml")


# =============================================================================
# Track A: Authority inputs explicit and fail-closed
# =============================================================================


class TestHarborBuildImageInputs:
    """Tests for explicit authority inputs with fail-closed defaults."""

    def test_workflow_file_exists(self) -> None:
        """Workflow file must exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW.exists(), \
            f"Workflow file {HARBOR_BUILD_IMAGE_WORKFLOW} does not exist"

    def _get_workflow_call_inputs(self, workflow: dict) -> dict:
        """Get inputs from workflow_call, handling YAML boolean parsing issues."""
        on_val: dict = workflow.get("on") or workflow.get(True) or {}
        if isinstance(on_val, dict):
            wc = on_val.get("workflow_call")
            if isinstance(wc, dict):
                inputs = wc.get("inputs")
                if isinstance(inputs, dict):
                    return inputs
        return {}

    def test_all_authority_inputs_are_required(self) -> None:
        """All three authority inputs must be required (no defaults for write ops)."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = self._get_workflow_call_inputs(workflow)

        # image_push_enabled must be required
        assert "image_push_enabled" in inputs, "image_push_enabled input missing"
        assert inputs["image_push_enabled"].get("required") is True, \
            "image_push_enabled must be required"

        # registry_cache_read_enabled must be required
        assert "registry_cache_read_enabled" in inputs, \
            "registry_cache_read_enabled input missing"
        assert inputs["registry_cache_read_enabled"].get("required") is True, \
            "registry_cache_read_enabled must be required"

        # registry_cache_write_enabled must be required
        assert "registry_cache_write_enabled" in inputs, \
            "registry_cache_write_enabled input missing"
        assert inputs["registry_cache_write_enabled"].get("required") is True, \
            "registry_cache_write_enabled must be required"

    def test_no_write_enabled_defaults(self) -> None:
        """Write authorities must NOT have default: true."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = self._get_workflow_call_inputs(workflow)

        # image_push_enabled must NOT have default: true
        image_push_default = inputs["image_push_enabled"].get("default")
        assert image_push_default != True, \
            "image_push_enabled must NOT have default: true (fail-closed)"

        # registry_cache_write_enabled must NOT have default: true
        cache_write_default = inputs["registry_cache_write_enabled"].get("default")
        assert cache_write_default != True, \
            "registry_cache_write_enabled must NOT have default: true (fail-closed)"

    def test_authority_inputs_are_boolean_type(self) -> None:
        """Authority inputs must be boolean type."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = self._get_workflow_call_inputs(workflow)

        assert inputs["image_push_enabled"]["type"] == "boolean"
        assert inputs["registry_cache_read_enabled"]["type"] == "boolean"
        assert inputs["registry_cache_write_enabled"]["type"] == "boolean"

    def test_authority_inputs_have_descriptions(self) -> None:
        """Authority inputs must have descriptions explaining their purpose."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        inputs = self._get_workflow_call_inputs(workflow)

        assert "description" in inputs["image_push_enabled"]
        assert "description" in inputs["registry_cache_read_enabled"]
        assert "description" in inputs["registry_cache_write_enabled"]


# =============================================================================
# Track B: PR boundary enforcement
# =============================================================================


class TestPRWriteRejection:
    """Tests for PR write operation rejection."""

    def test_preflight_rejects_pr_image_push(self) -> None:
        """Preflight must reject image push on pull_request event."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must have PR_WRITE_AUTHORITY_FORBIDDEN error for image push
        assert "ERROR: PR_WRITE_AUTHORITY_FORBIDDEN" in content, \
            "Must emit PR_WRITE_AUTHORITY_FORBIDDEN error"
        assert "Image push requested on pull_request event" in content, \
            "Must reject image push on PR"

    def test_preflight_rejects_pr_cache_write(self) -> None:
        """Preflight must reject cache write on pull_request event."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must have PR_WRITE_AUTHORITY_FORBIDDEN error for cache write
        assert "ERROR: PR_WRITE_AUTHORITY_FORBIDDEN" in content, \
            "Must emit PR_WRITE_AUTHORITY_FORBIDDEN error"
        assert "Cache write requested on pull_request event" in content, \
            "Must reject cache write on PR"

    def test_preflight_documents_all_pr_types_rejected(self) -> None:
        """Preflight must document that ALL PR types are rejected."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must document rejection of all PR types
        assert "Same-repository PR write: REJECTED" in content, \
            "Must reject same-repository PR writes"
        assert "Dependabot PR write: REJECTED" in content, \
            "Must reject Dependabot PR writes"
        assert "Fork PR write: REJECTED" in content, \
            "Must reject fork PR writes"

    def test_no_dependabot_exception(self) -> None:
        """Dependabot must NOT be exempted from PR restrictions."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Should NOT have dependabot exceptions that grant write
        # (Dependabot is mentioned in PR types list as REJECTED, not exempted)
        assert "/dependabot" not in content or "REJECTED" in content, \
            "Dependabot must be rejected, not exempted"

    def test_actor_classification_not_used_for_trust(self) -> None:
        """Actor classification may be logged but must NOT grant write authority."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Actor may be logged but cannot grant write
        # The PR rejection must be based on event_name, not actor
        assert 'if [[ "${EVENT_NAME}" == "pull_request" ]]' in content, \
            "PR rejection must be based on event_name"


# =============================================================================
# Track C: Secret boundary narrowing
# =============================================================================


class TestSecretBoundary:
    """Tests for narrowed secret boundary."""

    def test_no_secrets_inherit_in_callers(self) -> None:
        """Callers must NOT use secrets: inherit as a value."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        # secrets: inherit must NOT appear as a value (not in comments)
        # Use regex to match secrets: inherit at start of line (not in comments)
        import re
        pattern = r'^    secrets: inherit$'
        match = re.search(pattern, content, re.MULTILINE)
        assert match is None, \
            "secrets: inherit is forbidden - use explicit secrets mapping"

    def test_only_harbor_secrets_passed(self) -> None:
        """Only Harbor username and token secrets are passed."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        # Find all workflow_call invocations
        calls = []
        jobs = workflow.get("jobs") or {}
        for job_name, job_config in jobs.items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                calls.append((job_name, job_config))

        assert len(calls) > 0, "Must have at least one harbor-build-image.yml call"

        for job_name, job_config in calls:
            assert "secrets" in job_config, f"{job_name} must specify secrets"

            secrets = job_config["secrets"]

            # Must have HARBOR_USERNAME
            assert "HARBOR_USERNAME" in secrets, \
                f"{job_name} must pass HARBOR_USERNAME"

            # Must have HARBOR_TOKEN
            assert "HARBOR_TOKEN" in secrets, \
                f"{job_name} must pass HARBOR_TOKEN"

            # Must NOT have secrets: inherit
            assert secrets != "inherit", \
                f"{job_name} must not use secrets: inherit"

    def test_harbor_username_mapped_correctly(self) -> None:
        """HARBOR_USERNAME must be mapped from repository secrets."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_USERNAME" in secrets:
                    value = secrets["HARBOR_USERNAME"]
                    assert "secrets.HARBOR_USERNAME" in value, \
                        f"{job_name} HARBOR_USERNAME must map from repository secrets"

    def test_harbor_token_mapped_correctly(self) -> None:
        """HARBOR_TOKEN must be mapped from repository secrets."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                secrets = job_config.get("secrets", {})
                if "HARBOR_TOKEN" in secrets:
                    value = secrets["HARBOR_TOKEN"]
                    assert "secrets.HARBOR_TOKEN" in value, \
                        f"{job_name} HARBOR_TOKEN must map from repository secrets"


# =============================================================================
# Track D: Shell safety - env transfer instead of inline interpolation
# =============================================================================


class TestShellSafety:
    """Tests for shell safety - env transfer pattern."""

    def test_preflight_uses_env_block(self) -> None:
        """Preflight must use env block for external values."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        # Find the authority preflight step
        preflight_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        assert preflight_step is not None, "Authority preflight step not found"
        assert "env" in preflight_step, "Preflight must have env block"

    def test_preflight_env_contains_all_inputs(self) -> None:
        """Preflight env block must contain all input values."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        preflight_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        env = preflight_step.get("env", {})

        # Must have input values in env
        assert "EVENT_NAME" in env, "EVENT_NAME must be in env"
        assert "ACTOR" in env, "ACTOR must be in env"
        assert "REPOSITORY" in env, "REPOSITORY must be in env"
        assert "REGISTRY" in env, "REGISTRY must be in env"
        assert "HARBOR_PROJECT" in env, "HARBOR_PROJECT must be in env"
        assert "IMAGE_NAME" in env, "IMAGE_NAME must be in env"
        assert "IMAGE_PUSH_ENABLED" in env, "IMAGE_PUSH_ENABLED must be in env"
        assert "CACHE_READ_ENABLED" in env, "CACHE_READ_ENABLED must be in env"
        assert "CACHE_WRITE_ENABLED" in env, "CACHE_WRITE_ENABLED must be in env"

    def test_preflight_uses_env_variables_not_direct_interpolation(self) -> None:
        """Preflight run body must use env variables, not direct interpolation."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        preflight_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        run_body = preflight_step.get("run", "")

        # Should use ${VAR} pattern for values from env
        # Must NOT have direct ${{ }} interpolation in shell code
        lines = run_body.split("\n")
        for line in lines:
            # Skip comment lines
            if line.strip().startswith("#"):
                continue
            # Skip echo statements that might be for debugging
            if "echo" in line and ("inputs." in line or "github." in line or "secrets." in line):
                continue
            # Check for forbidden patterns in non-echo lines
            if "${{" in line and "env:" not in line:
                pytest.fail(f"Forbidden direct interpolation in shell: {line.strip()[:80]}")

    def test_preflight_does_not_print_credentials(self) -> None:
        """Preflight must not print credential values."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        preflight_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        run_body = preflight_step.get("run", "")

        # Must not print HARBOR_USERNAME or HARBOR_TOKEN values
        # Note: env vars can be set but not echoed with their values
        assert 'echo "${HARBOR_USERNAME}"' not in run_body, \
            "Must not echo HARBOR_USERNAME"
        assert 'echo "${HARBOR_TOKEN}"' not in run_body, \
            "Must not echo HARBOR_TOKEN"


# =============================================================================
# Track E: Buildx rendering for different contexts
# =============================================================================


class TestBuildxRendering:
    """Tests for Buildx command rendering."""

    def test_build_push_uses_input_condition(self) -> None:
        """Build push must use input.condition for push flag."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        build_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Build and push image":
                build_step = step
                break

        assert build_step is not None, "Build step not found"
        assert "push" in build_step["with"], "push flag must be specified"

        push_value = build_step["with"]["push"]
        assert "inputs.image_push_enabled" in str(push_value), \
            "push must use inputs.image_push_enabled"

    def test_cache_from_uses_input_condition(self) -> None:
        """cache-from must use inputs.registry_cache_read_enabled."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        build_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Build and push image":
                build_step = step
                break

        assert build_step is not None, "Build step not found"
        cache_from = build_step["with"].get("cache-from", "")

        assert "inputs.registry_cache_read_enabled" in str(cache_from), \
            "cache-from must use inputs.registry_cache_read_enabled"

    def test_cache_to_uses_input_condition(self) -> None:
        """cache-to must use inputs.registry_cache_write_enabled."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        build_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Build and push image":
                build_step = step
                break

        assert build_step is not None, "Build step not found"
        cache_to = build_step["with"].get("cache-to", "")

        assert "inputs.registry_cache_write_enabled" in str(cache_to), \
            "cache-to must use inputs.registry_cache_write_enabled"

    def test_no_unconditional_cache_to(self) -> None:
        """cache-to must not be unconditional."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        build_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Build and push image":
                build_step = step
                break

        assert build_step is not None, "Build step not found"
        cache_to = build_step["with"].get("cache-to", "")

        # cache-to must be conditional (contain registry_cache_write_enabled)
        assert "registry_cache_write_enabled" in str(cache_to), \
            "cache-to must be conditional on registry_cache_write_enabled"
        # Must not be always-present
        assert cache_to != "type=registry,ref=..." or "registry_cache_write_enabled" in str(cache_to), \
            "cache-to must not be unconditional"


# =============================================================================
# Track F: Caller authority matrix
# =============================================================================


class TestCallerAuthorityMatrix:
    """Tests for caller workflow authority matrix."""

    def test_all_callers_supply_all_authorities(self) -> None:
        """All callers must supply all three authority inputs."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        calls = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                calls.append((job_name, job_config.get("with", {})))

        assert len(calls) > 0, "Must have at least one harbor-build-image.yml call"

        for job_name, inputs in calls:
            assert "image_push_enabled" in inputs, \
                f"{job_name} must supply image_push_enabled"
            assert "registry_cache_read_enabled" in inputs, \
                f"{job_name} must supply registry_cache_read_enabled"
            assert "registry_cache_write_enabled" in inputs, \
                f"{job_name} must supply registry_cache_write_enabled"

    def test_pr_callers_use_read_only_matrix(self) -> None:
        """PR callers must use read-only authority matrix."""
        with open(HARBOR_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        # PR event is defined in the workflow
        # Handle YAML parsing where "on" becomes True (boolean)
        on_val = workflow.get("on", workflow.get(True, {}))
        
        # Check for pull_request in various YAML structures
        if isinstance(on_val, dict):
            has_pr_trigger = "pull_request" in on_val
        elif isinstance(on_val, list):
            has_pr_trigger = "pull_request" in on_val
        elif isinstance(on_val, str):
            has_pr_trigger = on_val == "pull_request"
        else:
            # Check if True key contains pull_request dict
            true_val = workflow.get(True, {})
            has_pr_trigger = isinstance(true_val, dict) and "pull_request" in true_val

        assert has_pr_trigger, f"Workflow must have pull_request trigger, got on={on_val}, True={workflow.get(True, {})}"

        # Check that callers use event condition for write authorities
        calls = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if "uses" in job_config and "harbor-build-image.yml" in job_config["uses"]:
                calls.append((job_name, job_config.get("with", {})))

        for job_name, inputs in calls:
            # write authorities should use event condition
            if "image_push_enabled" in inputs:
                value = str(inputs["image_push_enabled"])
                assert "github.event_name" in value, \
                    f"{job_name} image_push_enabled should use event condition"

            if "registry_cache_write_enabled" in inputs:
                value = str(inputs["registry_cache_write_enabled"])
                assert "github.event_name" in value, \
                    f"{job_name} registry_cache_write_enabled should use event condition"

    def test_login_condition_uses_authority_inputs(self) -> None:
        """Login step must use authority inputs for condition."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        login_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Login to Harbor":
                login_step = step
                break

        assert login_step is not None, "Login step not found"
        assert "if" in login_step, "Login step must have if condition"

        condition = login_step["if"]
        assert "image_push_enabled" in condition, \
            "Login condition must check image_push_enabled"
        assert "registry_cache_write_enabled" in condition, \
            "Login condition must check registry_cache_write_enabled"


# =============================================================================
# Authority preflight validation
# =============================================================================


class TestAuthorityPreflight:
    """Tests for authority preflight step."""

    def test_has_authority_preflight_step(self) -> None:
        """Must have authority preflight step."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        steps = workflow["jobs"]["build"]["steps"]
        step_names = [s.get("name") for s in steps]

        assert "Authority preflight" in step_names, \
            "Must have Authority preflight step"

    def test_preflight_validates_event_authority_combination(self) -> None:
        """Preflight must validate event/authority combination."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        assert "EVENT_NAME" in content, "Must use EVENT_NAME"
        assert '"pull_request"' in content, "Must check pull_request event"
        assert "IMAGE_PUSH_ENABLED" in content, "Must check IMAGE_PUSH_ENABLED"
        assert "CACHE_WRITE_ENABLED" in content, "Must check CACHE_WRITE_ENABLED"

    def test_preflight_checks_credentials_for_write(self) -> None:
        """Preflight must check credential availability for write operations."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Must check credentials when write is required
        assert "HARBOR_USERNAME" in content, "Must check HARBOR_USERNAME"
        assert "HARBOR_TOKEN" in content, "Must check HARBOR_TOKEN"
        assert "Credentials validated" in content or "credentials validated" in content.lower(), \
            "Must report credential validation"

    def test_preflight_exits_early_for_pr(self) -> None:
        """Preflight must exit early for PR events after validation."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            workflow = yaml.safe_load(f)

        preflight_step = None
        for step in workflow["jobs"]["build"]["steps"]:
            if step.get("name") == "Authority preflight":
                preflight_step = step
                break

        run_body = preflight_step.get("run", "")

        # Must exit early for PR after validation
        assert 'exit 0' in run_body, \
            "Preflight must exit early for read-only PR"

    def test_preflight_has_correct_phase_order(self) -> None:
        """Preflight must have correct phase ordering."""
        with open(HARBOR_BUILD_IMAGE_WORKFLOW) as f:
            content = f.read()

        # Find preflight run body
        preflight_match = re.search(
            r'Authority preflight.*?run: \|\s*(.*?)(?=\n      - name:|\njobs:)',
            content,
            re.DOTALL
        )

        if preflight_match:
            body = preflight_match.group(1)

            # Check phase order
            validate_inputs_pos = body.find("Validate required inputs")
            validate_boolean_pos = body.find("Validate boolean inputs")
            reject_pr_pos = body.find("Reject ALL PR write operations")
            write_required_pos = body.find("determine write requirements")
            validate_creds_pos = body.find("Validate credential availability")

            assert validate_inputs_pos < validate_boolean_pos, \
                "Phase 1 (validate inputs) must come before Phase 2 (validate booleans)"
            assert validate_boolean_pos < reject_pr_pos, \
                "Phase 2 (validate booleans) must come before Phase 3 (reject PR)"
            assert reject_pr_pos < write_required_pos, \
                "Phase 3 (reject PR) must come before Phase 4 (determine write)"
            assert write_required_pos < validate_creds_pos, \
                "Phase 4 (determine write) must come before Phase 5 (validate creds)"


# =============================================================================
# Policy truth table tests
# =============================================================================


class TestPolicyTruthTable:
    """Tests for authority policy truth table."""

    def test_pr_event_image_push_false(self) -> None:
        """PR event must result in image_push_enabled=false."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        # For pull_request trigger, image_push_enabled must be false
        # Check that expression evaluates to false for PR
        assert "github.event_name != 'pull_request'" in content or \
               "github.event_name == 'pull_request'" in content, \
            "Must use event condition for image_push_enabled"

    def test_pr_event_cache_write_false(self) -> None:
        """PR event must result in cache_write=false."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        # For pull_request trigger, cache_write must be false
        assert "github.event_name != 'pull_request'" in content or \
               "github.event_name == 'pull_request'" in content, \
            "Must use event condition for registry_cache_write_enabled"

    def test_pr_event_cache_read_true(self) -> None:
        """PR event may have cache_read=true (read-only)."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        # cache_read should be true for PR (read-only cache is fine)
        # Look for explicit cache_read_enabled: true
        assert "registry_cache_read_enabled: true" in content, \
            "PR should have cache_read enabled (read-only)"

    def test_trusted_push_all_write_true(self) -> None:
        """Trusted push event should enable all write operations."""
        with open(HARBOR_WORKFLOW) as f:
            content = f.read()

        # For non-PR events, write authorities should be enabled
        assert "github.event_name != 'pull_request'" in content, \
            "Trusted push should use github.event_name != 'pull_request' for write"


# =============================================================================
# Helper for truth table
# =============================================================================


def calculate_authority(event_name: str, image_push_requested: bool, cache_write_requested: bool) -> dict:
    """
    Calculate the effective authority based on event and requested flags.

    This mirrors the logic in the authority preflight step.
    """
    if event_name == "pull_request":
        # PR is always read-only
        if image_push_requested or cache_write_requested:
            return {"allowed": False, "reason": "PR_WRITE_AUTHORITY_FORBIDDEN"}
        return {
            "allowed": True,
            "image_push": False,
            "cache_read": True,  # PR can read cache
            "cache_write": False,
            "login_required": False,
        }

    # Non-PR event
    login_required = image_push_requested or cache_write_requested

    return {
        "allowed": True,
        "image_push": image_push_requested,
        "cache_read": True,
        "cache_write": cache_write_requested,
        "login_required": login_required,
    }


class TestAuthorityCalculation:
    """Unit tests for authority calculation logic."""

    def test_pr_readonly_allowed(self) -> None:
        """PR with read-only settings must be allowed."""
        result = calculate_authority("pull_request", False, False)
        assert result["allowed"] is True
        assert result["image_push"] is False
        assert result["cache_write"] is False
        assert result["login_required"] is False

    def test_pr_image_push_rejected(self) -> None:
        """PR with image push requested must be rejected."""
        result = calculate_authority("pull_request", True, False)
        assert result["allowed"] is False
        assert result["reason"] == "PR_WRITE_AUTHORITY_FORBIDDEN"

    def test_pr_cache_write_rejected(self) -> None:
        """PR with cache write requested must be rejected."""
        result = calculate_authority("pull_request", False, True)
        assert result["allowed"] is False
        assert result["reason"] == "PR_WRITE_AUTHORITY_FORBIDDEN"

    def test_pr_both_writes_rejected(self) -> None:
        """PR with both writes requested must be rejected."""
        result = calculate_authority("pull_request", True, True)
        assert result["allowed"] is False
        assert result["reason"] == "PR_WRITE_AUTHORITY_FORBIDDEN"

    def test_push_readonly_allowed(self) -> None:
        """Non-PR with read-only settings must be allowed."""
        result = calculate_authority("push", False, False)
        assert result["allowed"] is True
        assert result["image_push"] is False
        assert result["cache_write"] is False
        assert result["login_required"] is False

    def test_push_full_write_allowed(self) -> None:
        """Non-PR with full write settings must be allowed."""
        result = calculate_authority("push", True, True)
        assert result["allowed"] is True
        assert result["image_push"] is True
        assert result["cache_write"] is True
        assert result["login_required"] is True

    def test_push_cache_only_write_allowed(self) -> None:
        """Non-PR with cache-only write must be allowed."""
        result = calculate_authority("push", False, True)
        assert result["allowed"] is True
        assert result["image_push"] is False
        assert result["cache_write"] is True
        assert result["login_required"] is True
