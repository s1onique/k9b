#!/usr/bin/env python3
"""Regression tests for rollout monitor contract fix (ACT 2026-06-27).

This module aggregates tests from split modules for backward compatibility
and targeted test runs.

Tests cover:
1. Manifest derivation - expected Deployment names from rendered Helm manifest
2. Classifier precedence - crash_loop over transient VolumeBinding
3. Crash artifact collection - current and previous logs
4. CLI integration - manifest-derived deployment names
5. Fail-fast behavior - CrashLoopBackOff detection
6. Split-brain deployment name drift - no stale "Deployment k9b" messages
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Test module paths (relative to this file's location)
TEST_MODULES = [
    "tests.test_rollout_manifest_derivation",
    "tests.test_rollout_classifier_crash",
    "tests.test_rollout_integration",
    "tests.test_rollout_failfast",
]


class TestRolloutMonitorRegressionAggregator:
    """Aggregator that runs all split rollout monitor regression tests.

    This class exists to satisfy pytest's test discovery so that running:
        pytest tests/test_rollout_monitor_regression_act_2026_06_27.py -v
    will actually collect and run meaningful tests (not 0 tests).
    """

    def test_all_split_modules_exist(self) -> None:
        """Verify all split test modules exist and are importable."""
        for module_name in TEST_MODULES:
            relative_path = module_name.replace("tests.", "").replace(".", "/") + ".py"
            module_path = Path(__file__).parent / relative_path
            assert module_path.exists(), f"Test module not found: {module_path}"

    def test_split_modules_run_all_tests(self) -> None:
        """Run all split test modules and verify they pass.
        
        This is the real regression gate - proving not just collection but
        actual execution and passing tests.
        """
        # Run pytest on all split modules together
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "-v", "-p", "no:cacheprovider",
                "tests/test_rollout_manifest_derivation.py",
                "tests/test_rollout_classifier_crash.py",
                "tests/test_rollout_integration.py",
                "tests/test_rollout_failfast.py",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        # Exit code 0 means all tests passed
        assert result.returncode == 0, (
            f"Split module tests failed:\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
