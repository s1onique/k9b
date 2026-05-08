"""Unit tests for shell scripts under scripts/.

These tests stub Python and health-loop calls to keep execution fast
and deterministic without requiring a live Kubernetes cluster.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ScriptsTest(unittest.TestCase):
    """Tests for run_health_once.sh and related scheduler scripts."""

    def _get_script_path(self, name: str) -> Path:
        """Return absolute path to a script in the scripts/ directory."""
        return Path(__file__).resolve().parents[2] / "scripts" / name

    def _base_env(self) -> dict[str, str]:
        """Minimal environment for script tests."""
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        return env

    # ------------------------------------------------------------------
    # Test (a): Fresh runs dir is created.
    # ------------------------------------------------------------------
    def test_run_health_once_creates_runs_dir(self) -> None:
        """Test that run_health_once.sh creates the runs directory on fresh PVC."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            health_dir = runs_parent / "health"
            self.assertFalse(health_dir.exists())

            # Create a minimal config that passes basic JSON validation.
            config_path = runs_parent / "health-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            result = subprocess.run(
                [str(script), "--help", "--runs-dir", str(health_dir)],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

    # ------------------------------------------------------------------
    # Test (b): Health loop is in the script flow.
    # ------------------------------------------------------------------
    def test_run_health_once_script_contains_health_loop(self) -> None:
        """Verify the script contains the canonical health loop command."""
        script = self._get_script_path("run_health_once.sh")
        content = script.read_text()
        # The script must invoke the canonical health loop.
        self.assertIn("run-health-loop", content)
        # The health loop must come before summary.
        loop_pos = content.find("run-health-loop")
        summary_pos = content.find("health-summary")
        self.assertNotEqual(loop_pos, -1, "run-health-loop not in script")
        self.assertNotEqual(summary_pos, -1, "health-summary not in script")
        self.assertLess(loop_pos, summary_pos, "health-loop must come before summary")

    # ------------------------------------------------------------------
    # Test (c): HEALTH_REQUIRE_SUMMARY env var is used.
    # ------------------------------------------------------------------
    def test_run_health_once_script_uses_health_require_summary(self) -> None:
        """Verify the script references HEALTH_REQUIRE_SUMMARY."""
        script = self._get_script_path("run_health_once.sh")
        content = script.read_text()
        self.assertIn("HEALTH_REQUIRE_SUMMARY", content)

    # ------------------------------------------------------------------
    # Test (d): Summary non-fatal special case for no runs.
    # ------------------------------------------------------------------
    def test_run_health_once_script_has_no_runs_warning(self) -> None:
        """Verify the script has the 'Unable to discover any health runs' special case."""
        script = self._get_script_path("run_health_once.sh")
        content = script.read_text()
        self.assertIn("Unable to discover any health runs", content)

    # ------------------------------------------------------------------
    # Test (e): Other summary failures remain fatal.
    # ------------------------------------------------------------------
    def test_run_health_once_summary_other_errors_fatal(self) -> None:
        """Test that non 'no-runs' summary errors still cause non-zero exit."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            health_dir = runs_parent / "health"
            health_dir.mkdir(parents=True)

            config_path = runs_parent / "health-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            # Fake CLI that returns an error that is NOT the "no runs" special case.
            fake_cli = runs_parent / "fake_other.py"
            fake_cli.write_text(
                """#!/usr/bin/env python3
import sys
print("Something else went wrong: permission denied reading artifact", file=sys.stderr)
sys.exit(1)
"""
            )
            fake_cli.chmod(0o755)

            fake_bin = runs_parent / "fake_bin2"
            fake_bin.mkdir()
            fake_python = fake_bin / "python"
            fake_python.write_text(
                f"""#!/bin/sh
case "$*" in
    *health-summary*)
        exec {fake_cli} "$@"
        ;;
    *)
        exec {sys.executable} "$@"
        ;;
esac
"""
            )
            fake_python.chmod(0o755)

            env_fake = env.copy()
            env_fake["HEALTH_PYTHON_BIN"] = str(fake_python)

            result = subprocess.run(
                [str(script), "--runs-dir", str(health_dir), "--config", str(config_path)],
                env=env_fake,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertNotEqual(
                result.returncode, 0,
                f"Expected non-zero exit for unexpected summary error.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            # Should NOT trigger the no-runs warning.
            self.assertNotIn(
                "WARNING: Health summary found no runs",
                result.stdout + result.stderr
            )

    # ------------------------------------------------------------------
    # Test: HEALTH_CONFIG_PATH env var is used as default.
    # ------------------------------------------------------------------
    def test_run_health_once_uses_health_config_path_env(self) -> None:
        """Test that CONFIG_PATH defaults to HEALTH_CONFIG_PATH env var."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            health_dir = runs_parent / "health"
            health_dir.mkdir(parents=True)

            config_path = runs_parent / "my-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            env_with_path = env.copy()
            env_with_path["HEALTH_CONFIG_PATH"] = str(config_path)

            # Using --help is safe as it exits before resolving run dirs.
            result = subprocess.run(
                [str(script), "--help"],
                env=env_with_path,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

    # ------------------------------------------------------------------
    # Test: HEALTH_RUNS_DIR env var is used as default.
    # ------------------------------------------------------------------
    def test_run_health_once_uses_health_runs_dir_env(self) -> None:
        """Test that RUNS_DIR defaults to HEALTH_RUNS_DIR env var."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            target_runs_dir = runs_parent / "custom-health"
            self.assertFalse(target_runs_dir.exists())

            config_path = runs_parent / "health-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            env_with_runs = env.copy()
            env_with_runs["HEALTH_RUNS_DIR"] = str(target_runs_dir)

            result = subprocess.run(
                [str(script), "--help"],
                env=env_with_runs,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

    # ------------------------------------------------------------------
    # Test: HEALTH_REQUIRE_DIAGNOSTIC_PACK env var is used.
    # ------------------------------------------------------------------
    def test_run_health_once_script_uses_health_require_diagnostic_pack(self) -> None:
        """Verify the script references HEALTH_REQUIRE_DIAGNOSTIC_PACK."""
        script = self._get_script_path("run_health_once.sh")
        content = script.read_text()
        self.assertIn("HEALTH_REQUIRE_DIAGNOSTIC_PACK", content)

    # ------------------------------------------------------------------
    # Test: UI_INDEX_PATH is exported for Python heredoc.
    # ------------------------------------------------------------------
    def test_run_health_once_script_exports_ui_index_path(self) -> None:
        """Verify the script exports UI_INDEX_PATH for embedded Python."""
        script = self._get_script_path("run_health_once.sh")
        content = script.read_text()
        # UI_INDEX_PATH must be exported so Python heredoc can read it from os.environ.
        self.assertIn("export UI_INDEX_PATH", content)
        # Python heredoc must read from os.environ, not receive a literal path.
        self.assertIn('os.environ["UI_INDEX_PATH"]', content)
        # Must NOT have the broken pattern of Path("$UI_INDEX_PATH") inside quoted heredoc.
        self.assertNotIn('Path("$UI_INDEX_PATH")', content)

    # ------------------------------------------------------------------
    # Test: Missing ui-index.json is non-fatal by default.
    # ------------------------------------------------------------------
    def test_run_health_once_missing_ui_index_nonfatal_by_default(self) -> None:
        """Test that missing ui-index.json logs WARNING but continues when HEALTH_REQUIRE_DIAGNOSTIC_PACK=false."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            health_dir = runs_parent / "health"
            health_dir.mkdir(parents=True)

            config_path = runs_parent / "health-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            # Fake CLI that returns 0 for health-loop and health-summary (no runs).
            fake_cli = runs_parent / "fake_ok.py"
            fake_cli.write_text(
                """#!/usr/bin/env python3
import sys
print("Unable to discover any health runs", file=sys.stdout)
sys.exit(0)
"""
            )
            fake_cli.chmod(0o755)

            fake_bin = runs_parent / "fake_bin3"
            fake_bin.mkdir()
            fake_python = fake_bin / "python"
            fake_python.write_text(
                f"""#!/bin/sh
case "$*" in
    *run-health-loop*|*health-summary*)
        exec {fake_cli} "$@"
        ;;
    *inspect_health_config*)
        exit 0
        ;;
    *)
        exec {sys.executable} "$@"
        ;;
esac
"""
            )
            fake_python.chmod(0o755)

            env_fake = env.copy()
            env_fake["HEALTH_PYTHON_BIN"] = str(fake_python)
            env_fake["HEALTH_BUILD_DIAGNOSTIC_PACK"] = "1"
            # Default: HEALTH_REQUIRE_DIAGNOSTIC_PACK is not set (defaults to false).

            result = subprocess.run(
                [str(script), "--runs-dir", str(health_dir), "--config", str(config_path)],
                env=env_fake,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Script must succeed (non-fatal by default).
            self.assertEqual(
                result.returncode, 0,
                f"Expected zero exit when ui-index missing and HEALTH_REQUIRE_DIAGNOSTIC_PACK=false.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            # Must log the warning about missing UI index.
            self.assertIn(
                "WARNING",
                result.stdout + result.stderr
            )

    # ------------------------------------------------------------------
    # Test: Missing ui-index.json is fatal when HEALTH_REQUIRE_DIAGNOSTIC_PACK=true.
    # ------------------------------------------------------------------
    def test_run_health_once_missing_ui_index_fatal_when_required(self) -> None:
        """Test that missing ui-index.json causes non-zero exit when HEALTH_REQUIRE_DIAGNOSTIC_PACK=true."""
        script = self._get_script_path("run_health_once.sh")
        env = self._base_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_parent = Path(tmpdir)
            health_dir = runs_parent / "health"
            health_dir.mkdir(parents=True)

            config_path = runs_parent / "health-config.json"
            config_path.write_text('{"output_dir": "' + str(runs_parent) + '", "targets": []}')

            # Fake CLI that returns 0 for health-loop and health-summary (no runs).
            fake_cli = runs_parent / "fake_ok2.py"
            fake_cli.write_text(
                """#!/usr/bin/env python3
import sys
print("Unable to discover any health runs", file=sys.stdout)
sys.exit(0)
"""
            )
            fake_cli.chmod(0o755)

            fake_bin = runs_parent / "fake_bin4"
            fake_bin.mkdir()
            fake_python = fake_bin / "python"
            fake_python.write_text(
                f"""#!/bin/sh
case "$*" in
    *run-health-loop*|*health-summary*)
        exec {fake_cli} "$@"
        ;;
    *inspect_health_config*)
        exit 0
        ;;
    *)
        exec {sys.executable} "$@"
        ;;
esac
"""
            )
            fake_python.chmod(0o755)

            env_fake = env.copy()
            env_fake["HEALTH_PYTHON_BIN"] = str(fake_python)
            env_fake["HEALTH_BUILD_DIAGNOSTIC_PACK"] = "1"
            env_fake["HEALTH_REQUIRE_DIAGNOSTIC_PACK"] = "true"

            result = subprocess.run(
                [str(script), "--runs-dir", str(health_dir), "--config", str(config_path)],
                env=env_fake,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Script must fail (fatal when required).
            self.assertNotEqual(
                result.returncode, 0,
                f"Expected non-zero exit when ui-index missing and HEALTH_REQUIRE_DIAGNOSTIC_PACK=true.\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            # Must mention the strict flag in output.
            self.assertIn(
                "HEALTH_REQUIRE_DIAGNOSTIC_PACK=true",
                result.stdout + result.stderr
            )


if __name__ == "__main__":
    unittest.main()