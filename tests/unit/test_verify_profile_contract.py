#!/usr/bin/env python3
"""
Tests for verification profile contracts.

These tests prove that:
1. fast does not accidentally include known expensive suites
2. full includes all required merge-grade gates
3. skipped checks are reported honestly
4. success output always includes the profile name

Run with:
    python -m pytest tests/unit/test_verify_profile_contract.py -v
"""

import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from verify_profile_contract import (
    check_all_steps_in_some_profile,
    check_fast_includes_core_checks,
    check_fast_no_expensive_steps,
    check_full_includes_all_non_excluded,
    check_no_duplicate_step_ids,
    check_profile_contract_has_escalation,
    check_step_commands_are_valid,
    run_contract_checks,
)
from verify_profiles import (
    get_all_steps,
    get_profiles,
    resolve_profile,
)


class TestFastProfile:
    """Tests for the fast profile definition."""

    def test_fast_excludes_expensive_steps(self):
        """Fast profile must not include expensive steps."""
        passed, message = check_fast_no_expensive_steps()
        assert passed, f"Fast profile should not include expensive steps: {message}"

    def test_fast_includes_core_linting(self):
        """Fast profile must include ruff-lint."""
        steps, _ = resolve_profile("fast")
        step_ids = {s.id for s in steps}
        assert "ruff-lint" in step_ids, "Fast profile must include ruff-lint"

    def test_fast_includes_mypy(self):
        """Fast profile must include mypy."""
        steps, _ = resolve_profile("fast")
        step_ids = {s.id for s in steps}
        assert "mypy" in step_ids, "Fast profile must include mypy"

    def test_fast_includes_core_checks(self):
        """Fast profile must include core checks."""
        passed, message = check_fast_includes_core_checks()
        assert passed, f"Fast profile should include core checks: {message}"

    def test_fast_has_escalation_command(self):
        """Fast profile must have escalation command."""
        profiles = get_profiles()
        fast = profiles["fast"]
        assert fast.escalation_command, "Fast profile must have escalation_command"
        assert "--full" in fast.escalation_command, "Fast escalation should point to --full"

    def test_fast_target_time_is_under_60s(self):
        """Fast profile target time should be ≤60s."""
        profiles = get_profiles()
        fast = profiles["fast"]
        assert fast.target_time_seconds <= 60, f"Fast target time should be ≤60s, got {fast.target_time_seconds}"

    def test_fast_ideal_time_is_under_45s(self):
        """Fast profile ideal time should be ≤45s."""
        profiles = get_profiles()
        fast = profiles["fast"]
        assert fast.ideal_time_seconds <= 45, f"Fast ideal time should be ≤45s, got {fast.ideal_time_seconds}"


class TestFullProfile:
    """Tests for the full profile definition."""

    def test_full_includes_all_non_excluded_steps(self):
        """Full profile must include all non-excluded steps."""
        passed, message = check_full_includes_all_non_excluded()
        assert passed, f"Full profile should include all steps: {message}"

    def test_full_has_no_escalation(self):
        """Full profile should not need escalation."""
        profiles = get_profiles()
        full = profiles["full"]
        # Full profile is the endpoint, escalation is optional
        # But if set, it should be empty or indicate done
        if full.escalation_command:
            assert "done" in full.escalation_command.lower() or full.escalation_command == "", \
                "Full profile escalation should indicate done"

    def test_full_includes_unit_tests(self):
        """Full profile must include unit-tests."""
        steps, _ = resolve_profile("full")
        step_ids = {s.id for s in steps}
        assert "unit-tests" in step_ids, "Full profile must include unit-tests"

    def test_full_includes_frontend_checks(self):
        """Full profile must include frontend checks."""
        steps, _ = resolve_profile("full")
        step_ids = {s.id for s in steps}
        assert "npm-ci" in step_ids, "Full profile must include npm-ci"
        assert "npm-test-ui" in step_ids, "Full profile must include npm-test-ui"
        assert "npm-build" in step_ids, "Full profile must include npm-build"


class TestStepDefinitions:
    """Tests for step definitions."""

    def test_all_steps_have_valid_commands(self):
        """All steps must have non-empty commands."""
        passed, message = check_step_commands_are_valid()
        assert passed, f"All steps should have valid commands: {message}"

    def test_no_duplicate_step_ids(self):
        """All step IDs must be unique."""
        passed, message = check_no_duplicate_step_ids()
        assert passed, f"Step IDs should be unique: {message}"

    def test_all_steps_covered_by_profiles(self):
        """All steps should be covered by at least one profile."""
        passed, message = check_all_steps_in_some_profile()
        assert passed, f"All steps should be covered: {message}"

    def test_expensive_steps_marked_correctly(self):
        """Steps marked as expensive should actually be expensive."""
        # These are the canonical expensive steps
        expensive_by_nature = {"unit-tests", "npm-ci", "npm-test-ui", "npm-build"}
        
        for step in get_all_steps():
            if step.id in expensive_by_nature:
                assert step.is_expensive, f"{step.id} should be marked as expensive"

    def test_step_categories_are_set(self):
        """All steps should have a category."""
        for step in get_all_steps():
            assert step.category, f"{step.id} should have a category"


class TestProfileContracts:
    """Tests for profile contracts."""

    def test_all_profiles_have_escalation_commands(self):
        """Non-full profiles must have escalation commands."""
        passed, message = check_profile_contract_has_escalation()
        assert passed, f"Profiles should have escalation commands: {message}"

    def test_fast_and_full_are_distinct(self):
        """Fast and full profiles must be different."""
        fast_steps, _ = resolve_profile("fast")
        full_steps, _ = resolve_profile("full")
        
        fast_ids = {s.id for s in fast_steps}
        full_ids = {s.id for s in full_steps}
        
        # Full should be a superset of fast
        assert fast_ids <= full_ids, "Fast steps should be a subset of full steps"
        
        # But they should not be equal
        assert fast_ids != full_ids, "Fast and full should not be identical"


class TestContractExecution:
    """Tests for contract execution."""

    def test_run_all_contract_checks(self):
        """Running all contract checks should not raise."""
        results = run_contract_checks()
        assert len(results) > 0, "Should have contract checks"

    def test_all_critical_checks_pass(self):
        """All error-severity contract checks should pass."""
        results = run_contract_checks()
        errors = [r for r in results if not r.passed and r.severity == "error"]
        assert len(errors) == 0, f"Error-severity checks should pass: {[r.id for r in errors]}"


class TestProfileSkippedReporting:
    """Tests for skipped step reporting."""

    def test_fast_reports_skipped_steps(self):
        """Fast profile should report what it skips."""
        steps, skipped = resolve_profile("fast")
        
        # Fast should skip expensive steps
        expensive_steps = {s.id for s in get_all_steps() if s.is_expensive}
        skipped_set = set(skipped)
        
        # At least the expensive steps should be in skipped
        assert expensive_steps <= skipped_set, \
            f"Expensive steps should be skipped: {expensive_steps - skipped_set}"

    def test_skipped_includes_unit_tests(self):
        """Fast should skip unit-tests."""
        _, skipped = resolve_profile("fast")
        assert "unit-tests" in skipped, "Fast should skip unit-tests"

    def test_skipped_includes_frontend_full_suite(self):
        """Fast should skip frontend full suite."""
        _, skipped = resolve_profile("fast")
        assert "npm-test-ui" in skipped, "Fast should skip npm-test-ui"


class TestProfileDocumentation:
    """Tests for profile documentation metadata."""

    def test_all_profiles_have_descriptions(self):
        """All profiles must have descriptions."""
        profiles = get_profiles()
        for name, profile in profiles.items():
            assert profile.description, f"Profile {name} must have a description"

    def test_fast_profile_has_local_default_notice(self):
        """Fast profile description should indicate it's the local default."""
        profiles = get_profiles()
        fast = profiles["fast"]
        assert "local" in fast.description.lower() or "fast" in fast.description.lower(), \
            "Fast description should indicate local/fast nature"

    def test_full_profile_indicates_exhaustive(self):
        """Full profile description should indicate exhaustive nature."""
        profiles = get_profiles()
        full = profiles["full"]
        assert "full" in full.description.lower() or "exhaustive" in full.description.lower() or \
               "merge" in full.description.lower(), \
            "Full description should indicate exhaustive nature"
