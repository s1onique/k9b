"""Tests for scoped verification modes.

Tests verify_all.sh scoped verification modes:
- --python-only flag
- --frontend-only flag
- Profile-based scoping

JSON Plan Contract (--print-plan --json output):
    {
        "profile": str,       # "fast" | "full"
        "scope": str,         # "all" | "python" | "frontend" | "helm"
        "is_full_gate": bool,
        "is_full_lane": bool,
        "metadata": {...},
        "lanes": {
            "python": [step, ...],
            "frontend": [step, ...],
            "helm": [step, ...]
        },
        "skipped": [{"id": str, "reason": str}, ...],
        "step_count": int,
        "skipped_count": int
    }
    where step = {"id": str, "lane": str, "command": str, "description": str}
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestScopedVerificationModes(unittest.TestCase):
    """Test verify_all.sh scoped verification modes (--python-only, --frontend-only)."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_scoped_")
        os.makedirs(self._tmp_dir, exist_ok=True)
        # Clean up any existing lock
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            import shutil
            shutil.rmtree(lock_dir, ignore_errors=True)

    def tearDown(self) -> None:
        """Clean up temp directory and lock."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_python_only_flag_accepted(self) -> None:
        """verify_all.sh --python-only should be accepted without error."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        # Should accept the flag
        self.assertNotIn("unrecognized", result.stderr.lower())

    def test_frontend_only_flag_accepted(self) -> None:
        """verify_all.sh --frontend-only should be accepted without error."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--frontend-only", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        # Should accept the flag
        self.assertNotIn("unrecognized", result.stderr.lower())

    def test_python_only_runs_python_checks(self) -> None:
        """
        verify_all.sh --python-only should resolve to Python lane only.
        
        Uses --print-plan to avoid executing verification in the unit-test shard.
        """
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--profile", "fast", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        
        self.assertEqual(
            result.returncode, 0,
            f"Plan resolution should succeed. stderr: {result.stderr[:500]}"
        )
        
        plan = json.loads(result.stdout)
        
        # Should have Python steps
        python_steps = plan.get("lanes", {}).get("python", [])
        self.assertTrue(
            len(python_steps) > 0,
            f"Python lane should have steps. Plan: {json.dumps(plan, indent=2)[:500]}"
        )
        
        # Should NOT have frontend or helm steps
        frontend_steps = plan.get("lanes", {}).get("frontend", [])
        helm_steps = plan.get("lanes", {}).get("helm", [])
        self.assertEqual(len(frontend_steps), 0, "Frontend lane should be empty")
        self.assertEqual(len(helm_steps), 0, "Helm lane should be empty")

    def test_frontend_only_runs_frontend_checks(self) -> None:
        """
        verify_all.sh --frontend-only should resolve to Frontend lane only.
        
        Uses --print-plan to avoid executing verification in the unit-test shard.
        """
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--frontend-only", "--profile", "fast", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        
        self.assertEqual(
            result.returncode, 0,
            f"Plan resolution should succeed. stderr: {result.stderr[:500]}"
        )
        
        plan = json.loads(result.stdout)
        
        # Should have Frontend steps
        frontend_steps = plan.get("lanes", {}).get("frontend", [])
        self.assertTrue(
            len(frontend_steps) > 0,
            f"Frontend lane should have steps. Plan: {json.dumps(plan, indent=2)[:500]}"
        )
        
        # Should NOT have python or helm steps
        python_steps = plan.get("lanes", {}).get("python", [])
        helm_steps = plan.get("lanes", {}).get("helm", [])
        self.assertEqual(len(python_steps), 0, "Python lane should be empty")
        self.assertEqual(len(helm_steps), 0, "Helm lane should be empty")

    def test_default_runs_all_checks(self) -> None:
        """
        verify_all.sh without scope flags should include all lanes.
        
        Uses --print-plan to avoid executing verification in the unit-test shard.
        Proves that no scope filter was applied (scope == 'all').
        """
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--profile", "fast", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        
        self.assertEqual(
            result.returncode, 0,
            f"Plan resolution should succeed. stderr: {result.stderr[:500]}"
        )
        
        plan = json.loads(result.stdout)
        
        # Key assertion: no scope filter was applied
        self.assertEqual(
            plan.get("scope"), "all",
            f"No scope filter should be applied by default. Got: {plan.get('scope')}"
        )
        
        # Profile should be fast (the default when not specified)
        self.assertEqual(plan.get("profile"), "fast", "Profile should be fast")
        
        # Should have steps in at least one lane (profile may skip some)
        lanes = plan.get("lanes", {})
        has_any_steps = any(len(steps) > 0 for steps in lanes.values())
        self.assertTrue(
            has_any_steps,
            f"Should have steps in at least one lane. Plan: {json.dumps(plan, indent=2)[:500]}"
        )

    def test_scope_flags_combine_with_profile(self) -> None:
        """
        Scope flags should combine with --profile correctly.
        
        This test uses --print-plan to avoid executing the full verification,
        which would cause a timeout regression in the unit-test shard.
        The test proves that --python-only + --profile <x> resolves to
        Python-scoped steps without running nested pytest.
        
        Note: Scoped runs (--python-only, --frontend-only, --helm-only) normalize
        the profile to 'full' due to legacy behavior in resolve_profile_and_scope().
        This is documented so the contract is explicit.
        """
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        
        # Use --print-plan --json to get the resolved plan without execution
        # This is the contract test approach: verify resolution, not execution
        # Note: --python-only + --profile act-local was the original failing combination
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--profile", "act-local", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,  # Plan resolution is fast, 10s is generous
            env=env,
            cwd=self.REPO_ROOT,
        )
        
        # Should complete without error
        self.assertEqual(
            result.returncode, 0,
            f"Plan resolution should succeed. stderr: {result.stderr[:500]}"
        )
        
        # Parse JSON plan
        try:
            plan = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"Output should be valid JSON: {e}. Output: {result.stdout[:500]}")
        
        # Verify scope is 'python' (--python-only sets scope to 'python')
        self.assertEqual(
            plan.get("scope"), "python",
            f"Scope should be 'python', got: {plan.get('scope')}"
        )
        
        # Scoped runs normalize profile to 'full' (legacy behavior)
        # This is documented behavior: resolve_profile_and_scope() sets profile='full'
        # when scope != 'all' to ensure full lane execution
        self.assertEqual(
            plan.get("profile"), "full",
            f"Scoped runs normalize profile to 'full'. Got: {plan.get('profile')}"
        )
        
        # Verify only Python lane has steps (no frontend/helm steps)
        python_steps = plan.get("lanes", {}).get("python", [])
        frontend_steps = plan.get("lanes", {}).get("frontend", [])
        helm_steps = plan.get("lanes", {}).get("helm", [])
        
        self.assertTrue(
            len(python_steps) > 0,
            f"Python lane should have steps. Plan: {json.dumps(plan, indent=2)[:1000]}"
        )
        self.assertEqual(
            len(frontend_steps), 0,
            f"Frontend lane should have no steps when --python-only is set. Got: {len(frontend_steps)}"
        )
        self.assertEqual(
            len(helm_steps), 0,
            f"Helm lane should have no steps when --python-only is set. Got: {len(helm_steps)}"
        )
        
        # Verify all Python steps are actually in the python lane
        for step in python_steps:
            self.assertEqual(
                step.get("lane"), "python",
                f"All Python lane steps should have lane='python'. Step: {step}"
            )



if __name__ == "__main__":
    unittest.main()
