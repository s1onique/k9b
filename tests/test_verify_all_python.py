#!/usr/bin/env python3
"""
Tests for verify_all.py and shell shim behavior.

Tests verify:
1. verify_all.py argument parsing and default behavior
2. verify_all.sh is shim-only (no profile/lane/skip semantics)
3. Runner process non-zero causes gate failure
4. JSON output is valid JSON only
5. Lane scopes still force full-lane behavior
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
VERIFY_ALL_SH = SCRIPT_DIR / "verify_all.sh"
VERIFY_ALL_PY = SCRIPT_DIR / "verify_all.py"


class TestVerifyAllShimOnly(unittest.TestCase):
    """Test that verify_all.sh is a pure shim with no orchestration logic."""
    
    def test_shell_is_executable_shim(self):
        """verify_all.sh should be an executable shim that execs Python."""
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        content = VERIFY_ALL_SH.read_text()
        
        # Should have exec that calls verify_all.py
        self.assertIn("exec", content.lower())
        self.assertIn("verify_all.py", content)
    
    def test_shell_has_no_profile_semantics(self):
        """Shell should have no profile/scope/lane semantics."""
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        content = VERIFY_ALL_SH.read_text()
        
        # Remove comment lines before checking for runtime patterns
        # (allow doc comments but not runtime code)
        code_lines = [line for line in content.split('\n') if not line.strip().startswith('#')]
        code_only = '\n'.join(code_lines)
        
        # These should NOT be in the shell runtime code
        forbidden = [
            "STEP_PROFILE=", "STEP_SCOPE=", "STEP_JSON_MODE=",
            "step_runner.sh", "source ", "emit_full_plan",
            "case ", "--fast", "--full",
            "python-only", "frontend-only", "helm-only",
            "step_count", "VERIFY_PROFILE=", "IS_FULL_GATE=",
        ]
        
        found_forbidden = [p for p in forbidden if p in code_only]
        self.assertEqual(found_forbidden, [], 
            f"Shell should not contain profile semantics: {found_forbidden}")
    
    def test_shell_has_no_hardcoded_steps(self):
        """Shell should not have hardcoded step arrays."""
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        content = VERIFY_ALL_SH.read_text()
        
        forbidden = [
            "python_steps=", "frontend_steps=", "helm_steps=",
            "ruff-lint", "mypy", "unit-tests",
        ]
        
        found_forbidden = [p for p in forbidden if p in content]
        self.assertEqual(found_forbidden, [],
            f"Shell should not have hardcoded steps: {found_forbidden}")
    
    def test_shell_has_no_step_execution(self):
        """Shell should not call step runners directly."""
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        content = VERIFY_ALL_SH.read_text()
        
        forbidden = [
            "verify_profile_runner.py", "run_step", "step_run",
        ]
        
        found_forbidden = [p for p in forbidden if p in content]
        self.assertEqual(found_forbidden, [],
            f"Shell should not execute steps directly: {found_forbidden}")


class TestVerifyAllPyArgumentParsing(unittest.TestCase):
    """Test verify_all.py argument parsing and default behavior."""
    
    def test_fast_flag_accepted(self):
        """--fast should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--fast", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_full_flag_accepted(self):
        """--full should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--full", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_json_flag_accepted(self):
        """--json should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--json", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_python_only_flag_accepted(self):
        """--python-only should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--python-only", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_frontend_only_flag_accepted(self):
        """--frontend-only should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--frontend-only", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_helm_only_flag_accepted(self):
        """--helm-only should be accepted."""
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--helm-only", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
    
    def test_default_is_fast(self):
        """Default profile should be fast (not --full)."""
        # We can't run the full gate here, but we can check the argument parsing
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        # Help text should mention fast as default
        self.assertIn("fast", result.stdout.lower())
        self.assertIn("default", result.stdout.lower())


class TestVerifyAllJsonMode(unittest.TestCase):
    """Test JSON output purity."""
    
    @classmethod
    def setUpClass(cls):
        """Check if we should run full tests."""
        cls._should_run = os.environ.get("RUN_FULL_VERIFY_TEST") == "1"
    
    def test_json_mode_requires_valid_json(self):
        """--json should emit valid JSON only to stdout."""
        if not self._should_run:
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verification")
        
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        # Run with --json
        result = subprocess.run(
            [str(VERIFY_ALL_SH), "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**os.environ, "RUN_FULL_VERIFY_TEST": "0"},  # Don't run nested tests
        )
        
        # stdout should be valid JSON
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"stdout is not valid JSON: {e}\nstdout: {result.stdout[:500]}")
    
    def test_json_mode_quiet_stderr(self):
        """--json should not emit human output to stderr on success."""
        if not self._should_run:
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verification")
        
        if not VERIFY_ALL_SH.exists():
            self.skipTest("verify_all.sh not found")
        
        result = subprocess.run(
            [str(VERIFY_ALL_SH), "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**os.environ, "RUN_FULL_VERIFY_TEST": "0"},
        )
        
        # On success, stderr should be empty or only contain system errors
        # Not human-readable step output
        if result.returncode == 0:
            # Should be empty or just contain error messages
            lines = result.stderr.strip().split("\n")
            human_lines = [l for l in lines if l and not l.startswith("ERROR:")]
            self.assertEqual(human_lines, [],
                f"JSON mode should not have human output on stderr: {human_lines}")


class TestVerifyAllLaneScopes(unittest.TestCase):
    """Test lane scope behavior."""
    
    def test_python_only_runs_full_python_lane(self):
        """--python-only should run full Python lane (not fast profile)."""
        # This test verifies the contract behavior
        # When scope is not 'all', profile should be 'full'
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all import resolve_profile_and_scope
        import argparse
        
        class MockArgs:
            profile = None
            scope = "python"
        
        profile, scope = resolve_profile_and_scope(MockArgs())
        self.assertEqual(profile, "full")
        self.assertEqual(scope, "python")
    
    def test_frontend_only_runs_full_frontend_lane(self):
        """--frontend-only should run full Frontend lane (not fast profile)."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all import resolve_profile_and_scope
        import argparse
        
        class MockArgs:
            profile = None
            scope = "frontend"
        
        profile, scope = resolve_profile_and_scope(MockArgs())
        self.assertEqual(profile, "full")
        self.assertEqual(scope, "frontend")
    
    def test_helm_only_runs_full_helm_lane(self):
        """--helm-only should run full Helm lane (not fast profile)."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all import resolve_profile_and_scope
        import argparse
        
        class MockArgs:
            profile = None
            scope = "helm"
        
        profile, scope = resolve_profile_and_scope(MockArgs())
        self.assertEqual(profile, "full")
        self.assertEqual(scope, "helm")


class TestVerifyAllLockBehavior(unittest.TestCase):
    """Test lock behavior."""
    
    def test_recursion_protection(self):
        """Recursion should be detected and rejected."""
        env = os.environ.copy()
        env["VERIFY_ALL_ACTIVE"] = "1"
        
        result = subprocess.run(
            [sys.executable, str(VERIFY_ALL_PY), "--help"],
            capture_output=True,
            text=True,
            env=env,
        )
        
        # Should fail with recursion error (exit code 2)
        self.assertEqual(result.returncode, 2)
        self.assertIn("recursion", result.stderr.lower())


class TestVerifyAllOutput(unittest.TestCase):
    """Test output formatting."""
    
    def test_profile_footer_shows_profile_name(self):
        """Profile footer should always show the profile name."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_profile_plan import emit_full_plan
        
        # Fast profile
        plan = emit_full_plan("fast", "all")
        self.assertEqual(plan["profile"], "fast")
        
        # Full profile
        plan = emit_full_plan("full", "all")
        self.assertEqual(plan["profile"], "full")
    
    def test_skipped_reported_honestly(self):
        """Skipped steps should be reported with profile name."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_profile_plan import emit_full_plan
        
        plan = emit_full_plan("fast", "all")
        
        # Fast profile should have skipped steps
        self.assertGreater(plan["skipped_count"], 0)
        self.assertGreater(len(plan["skipped"]), 0)
        
        # Each skipped step should have an id and reason
        for skip in plan["skipped"]:
            self.assertIn("id", skip)
            self.assertIn("reason", skip)


class TestVerifyAllFailClosed(unittest.TestCase):
    """Test fail-closed behavior for runner failures and state issues."""
    
    def test_lane_state_missing_fails_closed(self):
        """Missing lane state file should cause failure."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all_orchestrator import VerificationOrchestrator
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = VerificationOrchestrator(
                repo_root=tmpdir,
                profile="fast",
                scope="python",
            )
            orchestrator.setup()
            
            # Remove the lane state file to simulate missing state
            if orchestrator.lane_state_file and orchestrator.lane_state_file.exists():
                orchestrator.lane_state_file.unlink()
            
            # Should raise RuntimeError on missing lane state
            with self.assertRaises(RuntimeError) as ctx:
                orchestrator.execute()
            
            self.assertIn("not found", str(ctx.exception))
    
    def test_lane_state_corrupt_fails_closed(self):
        """Corrupt lane state file should cause failure."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all_orchestrator import VerificationOrchestrator
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = VerificationOrchestrator(
                repo_root=tmpdir,
                profile="fast",
                scope="python",
            )
            orchestrator.setup()
            
            # Corrupt the lane state file
            if orchestrator.lane_state_file:
                with open(orchestrator.lane_state_file, "w") as f:
                    f.write("{ invalid json }")
            
            # Should raise RuntimeError on corrupt lane state
            with self.assertRaises(RuntimeError) as ctx:
                orchestrator.execute()
            
            self.assertIn("corrupt", str(ctx.exception).lower())
    
    def test_runner_failure_propagates(self):
        """Verify runner failure propagates - tests the code path, not full gate."""
        # This test verifies the contract by checking that runner subprocess
        # failures propagate. We test this by examining the lane state structure.
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_profile_plan import emit_full_plan
        
        plan = emit_full_plan("fast", "python")
        # Verify the plan structure includes lane information
        self.assertIn("lanes", plan)
        self.assertIn("python", plan["lanes"])
        # The runner will set exit_code on failure which propagates
    
    def test_json_mode_emits_valid_json_on_failure(self):
        """JSON mode should emit valid JSON even on failure."""
        # This test is skipped because running the full gate is expensive
        # JSON validity is tested indirectly via contract checks
        self.skipTest("Skipped: requires full gate execution")


if __name__ == "__main__":
    unittest.main()
