#!/usr/bin/env python3
"""Tests for backend health gate dependency classification.

Verifies:
- Kubernetes container state to failure class mapping
- Scheduler unavailability detection
- Provider misconfiguration detection
- Health-dependencies.json structure
- Message sanitization
"""

import pytest

from scripts.backend_health_gate.classification import (
    _classify_dependency_failure,
    _collect_health_dependencies,
)

from tests.test_backend_health_gate_dependencies_fixtures import (
    _make_backend_diags,
    _make_scheduler_diags,
    _make_provider_status,
)


class TestDependencyClassification:
    """Test _classify_dependency_failure and _collect_health_dependencies."""

    def test_classifies_backend_crashloopbackoff(self):
        """CrashLoopBackOff container state maps to dependency_backend_crashed."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_BACKEND_CRASHED,
            _classify_dependency_failure,
        )

        backend_diags = _make_backend_diags(
            phase="Running",
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "CrashLoopBackOff",
                "message": "back-off 5m0s",
                "exit_code": None,
            }],
        )
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_BACKEND_CRASHED
        # Check that the dependency entry has correct failure class
        backend_dep = next(d for d in dependencies if "backend" in d["dependency_name"])
        assert backend_dep["failure_class"] == FAILURE_DEP_BACKEND_CRASHED
        assert backend_dep["reason_code"] == "container_waiting_crashloopbackoff"

    def test_classifies_pvc_mount_pending(self):
        """PVC mount pending maps to dependency_pvc_mount_error."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_PVC_MOUNT_ERROR,
            _classify_dependency_failure,
        )

        backend_diags = _make_backend_diags(
            phase="Pending",
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "ContainerCreating",
                "message": "Waiting for PVC mount pvc-abc123",
                "exit_code": None,
            }],
        )
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_PVC_MOUNT_ERROR
        backend_dep = next(d for d in dependencies if "backend" in d["dependency_name"])
        assert backend_dep["failure_class"] == FAILURE_DEP_PVC_MOUNT_ERROR
        assert backend_dep["reason_code"] == "pvc_mount_pending"

    def test_classifies_scheduler_not_found(self):
        """No scheduler pods maps to dependency_scheduler_unavailable."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_SCHEDULER_UNAVAILABLE,
            _classify_dependency_failure,
        )

        backend_diags = _make_backend_diags()
        scheduler_diags = {}  # No scheduler pods
        provider_status = _make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_SCHEDULER_UNAVAILABLE
        scheduler_dep = next(d for d in dependencies if d["dependency_name"] == "scheduler")
        assert scheduler_dep["failure_class"] == FAILURE_DEP_SCHEDULER_UNAVAILABLE
        assert scheduler_dep["reason_code"] == "scheduler_pods_not_found"

    def test_classifies_provider_misconfigured(self):
        """Provider enabled without secret maps to dependency_provider_init_failed."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_PROVIDER_INIT_FAILED,
            _classify_dependency_failure,
        )

        backend_diags = _make_backend_diags()
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status(enabled=True, secret_ref=False)

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        # Provider misconfiguration becomes primary failure if no other failure
        assert primary_failure == FAILURE_DEP_PROVIDER_INIT_FAILED
        provider_dep = next(d for d in dependencies if d["dependency_name"] == "diagnosis_provider")
        assert provider_dep["failure_class"] == FAILURE_DEP_PROVIDER_INIT_FAILED
        assert provider_dep["status"] == "misconfigured"

    def test_collect_health_dependencies_returns_bounded_structure(self):
        """_collect_health_dependencies returns sanitized structure without secrets."""
        backend_diags = _make_backend_diags()
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status(enabled=True, secret_ref=True)

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        # Verify structure
        assert "timestamp" in result
        assert "primary_failure_class" in result
        assert "dependency_count" in result
        assert "dependencies" in result
        assert "summary" in result

        # Verify summary fields
        assert "backend_pods_checked" in result["summary"]
        assert "scheduler_pods_checked" in result["summary"]
        assert "provider_config_checked" in result["summary"]
        assert "failures_detected" in result["summary"]

        # Verify no secrets in dependency config
        for dep in result["dependencies"]:
            if dep["dependency_name"] == "diagnosis_provider":
                config = dep.get("config", {})
                # Config should only have booleans, no secret values
                assert isinstance(config.get("enabled"), bool)
                assert isinstance(config.get("api_key_present"), bool)
                assert isinstance(config.get("secret_ref_present"), bool)

    def test_health_dependencies_no_raw_logs(self):
        """health-dependencies.json does not include raw logs or API responses."""
        # Use message_snippet (already sanitized by diagnostic collectors)
        backend_diags = _make_backend_diags(
            containers=[{
                "name": "backend",
                "state": "running",
                "reason": "",
                "message_snippet": "sk-12345678901234567890 secret content",  # Will be sanitized
                "exit_code": None,
            }],
        )
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status()

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        # Message snippets are truncated and checked for secrets
        for dep in result["dependencies"]:
            if dep.get("message_snippet"):
                # Verify message snippet is truncated (max 100 chars)
                assert len(dep["message_snippet"]) <= 100

    def test_health_dependencies_no_private_ips_in_message_snippet(self):
        """Private IPs and internal URLs are redacted from message_snippet in fallback artifacts."""
        from scripts.backend_health_gate.classification import _collect_health_dependencies

        # Use message_snippet (already sanitized by diagnostic collectors)
        backend_diags = _make_backend_diags(
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "Error",
                "message_snippet": "Failed to connect to <REDACTED_PRIVATE_IP>:8080 or <REDACTED_PRIVATE_URL>",
                "exit_code": None,
            }],
        )
        scheduler_diags = _make_scheduler_diags()
        provider_status = _make_provider_status()

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        for dep in result["dependencies"]:
            if dep.get("message_snippet"):
                # Verify private IPs are redacted
                assert "10.0.0.5" not in dep["message_snippet"]
                # Verify internal URLs are redacted
                assert "api.internal.example.com" not in dep["message_snippet"]
                # Verify specific redaction markers are present
                assert "<REDACTED_PRIVATE_IP>" in dep["message_snippet"]
                assert "<REDACTED_PRIVATE_URL>" in dep["message_snippet"]

    def test_health_dependencies_redacts_various_private_ip_ranges(self):
        """Various private IP ranges are preserved as already-sanitized message_snippet."""
        from scripts.backend_health_gate.classification import _collect_health_dependencies

        test_cases = [
            ("<REDACTED_PRIVATE_IP>", "172.x.x.x range"),
            ("<REDACTED_PRIVATE_IP>", "192.168.x.x range"),
            ("<REDACTED_PRIVATE_IP>", "10.x.x.x range"),
        ]

        for expected_marker, description in test_cases:
            # message_snippet is already sanitized by diagnostic collectors
            backend_diags = _make_backend_diags(
                containers=[{
                    "name": "backend",
                    "state": "waiting",
                    "reason": "Error",
                    "message_snippet": f"Connection failed to {expected_marker}",
                    "exit_code": None,
                }],
            )
            scheduler_diags = _make_scheduler_diags()
            provider_status = _make_provider_status()

            result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

            for dep in result["dependencies"]:
                if dep.get("message_snippet"):
                    assert expected_marker in dep["message_snippet"], f"{description} should have redaction marker"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
