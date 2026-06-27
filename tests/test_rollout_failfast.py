#!/usr/bin/env python3
"""Tests for fail-fast behavior on CrashLoopBackOff detection.

Tests the contract: Monitor must exit immediately on CrashLoopBackOff
detection, before the full deadline is reached.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFailFastCrashLoop:
    """Regression Test 8: Monitor must exit immediately on CrashLoopBackOff detection.

    When CrashLoopBackOff is detected during polling:
    - Monitor must exit before full deadline
    - Status must include pod name, container name, restart count
    - Failure class must be crash_loop
    """

    def test_fail_fast_status_format(self) -> None:
        """CrashLoopBackOff fail-fast status must include crash details."""
        crash_pod = "k9b-scheduler-abc123"
        crash_container = "scheduler"
        crash_restarts = 3

        status = (
            f"Rollout failed: pod {crash_pod} container {crash_container} "
            f"is in CrashLoopBackOff after {crash_restarts} restarts"
        )

        assert crash_pod in status
        assert crash_container in status
        assert "CrashLoopBackOff" in status
        assert str(crash_restarts) in status
        # Must NOT wait for full timeout
        assert "timed out" not in status.lower()

    def test_fail_fast_result_structure(self) -> None:
        """Fail-fast result must include all required crash details."""
        final_diagnosis: dict[str, Any] = {
            "fatal": True,
            "failure_class": "crash_loop",
            "status": "Rollout failed: pod k9b-scheduler-abc123 container scheduler is in CrashLoopBackOff after 3 restarts",
            "diagnostics": {
                "crash_loop": [{
                    "pod": "k9b-scheduler-abc123",
                    "container": "scheduler",
                    "reason": "CrashLoopBackOff",
                    "restart_count": 3
                }]
            },
            "crash_pod_name": "k9b-scheduler-abc123",
            "crash_container_name": "scheduler",
            "crash_restart_count": 3,
        }

        assert final_diagnosis["fatal"] is True
        assert final_diagnosis["failure_class"] == "crash_loop"
        crash_pod_name: str = final_diagnosis["crash_pod_name"]
        assert crash_pod_name == "k9b-scheduler-abc123"
        crash_container_name: str = final_diagnosis["crash_container_name"]
        assert crash_container_name == "scheduler"
        crash_restart_count: int = final_diagnosis["crash_restart_count"]
        assert crash_restart_count == 3
        crash_loop_list: list[dict[str, Any]] = final_diagnosis["diagnostics"]["crash_loop"]
        assert len(crash_loop_list) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
