"""Tests for Docker build locality verifier.

These tests verify:
1. Stale requirements.docker.txt is detected
2. Failure output shows only relevant remediation items
3. Already-passing checks are not repeated as failed remediation items
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestDockerBuildLocalityVerifier(unittest.TestCase):
    """Test docker build locality verifier behavior."""

    REPO_ROOT = Path(__file__).parent.parent
    SCRIPT_DIR = REPO_ROOT / "scripts"
    VERIFY_SCRIPT = SCRIPT_DIR / "verify_docker_build_locality.sh"
    SYNC_SCRIPT = SCRIPT_DIR / "sync-docker-requirements.sh"
    REQUIREMENTS_FILE = REPO_ROOT / "requirements.docker.txt"
    PYPROJECT = REPO_ROOT / "pyproject.toml"

    def setUp(self) -> None:
        """Set up test fixtures."""
        if not self.VERIFY_SCRIPT.exists():
            self.skipTest("verify_docker_build_locality.sh not found")
        os.chmod(self.VERIFY_SCRIPT, 0o755)

    def test_verifier_passes_when_requirements_fresh(self) -> None:
        """Verifier should pass when requirements.docker.txt matches pyproject.toml.
        
        Note: Uses --check mode to verify freshness without modifying repo state.
        """
        # Verify requirements are fresh using --check (no modification)
        check_result = subprocess.run(
            [str(self.SYNC_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=self.REPO_ROOT,
        )
        
        if check_result.returncode != 0:
            self.skipTest("requirements.docker.txt is stale - run sync-docker-requirements.sh first")

        result = subprocess.run(
            [str(self.VERIFY_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0, f"Verifier failed: {result.stderr}")
        self.assertIn("RESULT: PASSED", result.stdout)
        self.assertIn("requirements.docker.txt is fresh", result.stdout)

    def test_verifier_fails_when_requirements_stale(self) -> None:
        """Verifier should fail when requirements.docker.txt is out of sync."""
        # Save original requirements
        original_content = self.REQUIREMENTS_FILE.read_text()

        try:
            # Make requirements stale by removing a dependency
            stale_content = original_content.replace("pyyaml>=6.0\n", "")
            self.REQUIREMENTS_FILE.write_text(stale_content)

            result = subprocess.run(
                [str(self.VERIFY_SCRIPT)],
                capture_output=True,
                text=True,
                cwd=self.REPO_ROOT,
            )

            # Should fail
            self.assertNotEqual(result.returncode, 0, "Verifier should fail when requirements are stale")

            # Should show the specific failure
            self.assertIn("requirements.docker.txt is stale", result.stdout)
            self.assertIn("RESULT: FAILED", result.stdout)

            # Should suggest the fix command
            self.assertIn("sync-docker-requirements.sh", result.stdout)

            # Should NOT show irrelevant remediation items
            # The stale-requirements issue should not trigger QEMU/Buildx cache suggestions
            self.assertNotIn("[QEMU]", result.stdout)
            self.assertNotIn("[Buildx]", result.stdout)
            self.assertNotIn("[Cache]", result.stdout)

            # Should show the SSOT-specific fix
            self.assertIn("[SSOT] requirements.docker.txt is stale", result.stdout)

        finally:
            # Restore original requirements
            self.REQUIREMENTS_FILE.write_text(original_content)

    def test_verifier_shows_targeted_failure_for_stale_requirements(self) -> None:
        """When only SSOT is stale, failure output should show only SSOT fix."""
        original_content = self.REQUIREMENTS_FILE.read_text()

        try:
            # Make requirements stale
            stale_content = original_content.replace("pyyaml>=6.0\n", "")
            self.REQUIREMENTS_FILE.write_text(stale_content)

            result = subprocess.run(
                [str(self.VERIFY_SCRIPT)],
                capture_output=True,
                text=True,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr

            # Should fail
            self.assertNotEqual(result.returncode, 0)

            # Should clearly identify the problem
            self.assertIn("FAIL: requirements.docker.txt is stale", output)

            # Should show only SSOT remediation (not all 5 generic items)
            # Count how many [category] lines appear in the failure section
            failure_section = output.split("Please fix:")[-1] if "Please fix:" in output else output
            ssot_fix_count = failure_section.count("[SSOT]")
            qemu_fix_count = failure_section.count("[QEMU]")
            buildx_fix_count = failure_section.count("[Buildx]")
            cache_fix_count = failure_section.count("[Cache]")

            self.assertEqual(ssot_fix_count, 1, "Should show exactly one SSOT fix")
            self.assertEqual(qemu_fix_count, 0, "Should not show QEMU fix (already passing)")
            self.assertEqual(buildx_fix_count, 0, "Should not show Buildx fix (already passing)")
            self.assertEqual(cache_fix_count, 0, "Should not show Cache fix (already passing)")

        finally:
            self.REQUIREMENTS_FILE.write_text(original_content)

    def test_sync_script_check_mode(self) -> None:
        """sync-docker-requirements.sh --check should detect stale requirements."""
        original_content = self.REQUIREMENTS_FILE.read_text()

        try:
            # Make requirements stale
            stale_content = original_content.replace("pyyaml>=6.0\n", "")
            self.REQUIREMENTS_FILE.write_text(stale_content)

            result = subprocess.run(
                [str(self.SYNC_SCRIPT), "--check"],
                capture_output=True,
                text=True,
                cwd=self.REPO_ROOT,
            )

            # Should fail
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stale", result.stdout.lower())

        finally:
            self.REQUIREMENTS_FILE.write_text(original_content)

    def test_sync_script_regenerates_correctly(self) -> None:
        """sync-docker-requirements.sh should regenerate requirements from pyproject.toml."""
        result = subprocess.run(
            [str(self.SYNC_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0)

        # Verify check mode passes after regeneration
        check_result = subprocess.run(
            [str(self.SYNC_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(check_result.returncode, 0)
        self.assertIn("fresh", check_result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
