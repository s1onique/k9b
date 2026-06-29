# Copyright (c) 2025 Artem Chistyakov
# SPDX-License-Identifier: MIT

"""Tests for scripts.lab_common.provider_status module.

These tests verify that the canonical provider status parser correctly handles
both legacy flattened format and new dependencies[] response format from
/api/health/details.

This module is the single source of truth for provider status parsing used by
both CNPG and OTel labs.
"""

from __future__ import annotations


class TestProviderStatusParsing:
    """Test provider status parsing from /api/health/details responses."""

    def test_parse_dependency_only_health_details(self) -> None:
        """Should derive provider status from dependencies[] when top-level fields are absent."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        # Exact payload shape observed in live lab where provider is available
        # but top-level flattened fields are null/missing
        health_details = {
            "healthy": True,
            "primary_failure_class": "",
            "dependencies": [
                {
                    "dependency_name": "health_loop_runtime",
                    "status": "healthy",
                    "failure_class": "",
                    "reason_code": "runtime_healthy",
                    "message_snippet": "",
                },
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                    "failure_class": "",
                    "reason_code": "provider_available",
                    "message_snippet": "",
                },
            ],
        }

        status = parse_provider_status_from_health_details(health_details)

        # Assert provider is correctly identified as available
        assert status.provider_enabled is True, \
            "provider_enabled should be True when dependency status is 'available'"
        assert status.provider_configured is True, \
            "provider_configured should be True when dependency status is 'available'"
        assert status.provider_status == "available", \
            "provider_status should be 'available' from dependency"
        assert status.provider_phase == "models_list_ok", \
            "provider_phase should be 'models_list_ok' from dependency"
        assert status.reason_code == "provider_available"
        assert status.healthy is True

    def test_parse_legacy_flattened_format(self) -> None:
        """Should use flattened fields when present."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        health_details = {
            "healthy": True,
            "primary_failure_class": "",
            "provider_enabled": True,
            "provider_configured": True,
            "provider_status": "configured",
            "phase": "ready",
        }

        status = parse_provider_status_from_health_details(health_details)

        assert status.provider_enabled is True
        assert status.provider_configured is True
        assert status.provider_status == "configured"
        assert status.provider_phase == "ready"

    def test_parse_flatttened_takes_precedence_over_dependency(self) -> None:
        """Flattened fields should take precedence over dependency values."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        # Both formats present - flattened should take precedence
        health_details = {
            "healthy": True,
            "provider_enabled": False,  # Explicitly disabled
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",  # But dependency says available
                    "phase": "models_list_ok",
                },
            ],
        }

        status = parse_provider_status_from_health_details(health_details)

        # Flattened value should be used, not derived
        assert status.provider_enabled is False, \
            "Flattened provider_enabled=False should take precedence over dependency status"

    def test_derives_status_from_available(self) -> None:
        """Should derive enabled=True when dependency status is 'available'."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        health_details = {
            "healthy": True,
            "primary_failure_class": "",
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                },
            ],
        }

        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is True

    def test_derives_status_from_configured(self) -> None:
        """Should derive enabled=True when dependency status is 'configured'."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        health_details = {
            "healthy": True,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "configured",
                    "phase": "ready",
                },
            ],
        }

        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is True

    def test_derives_status_from_healthy(self) -> None:
        """Should derive enabled=True when dependency status is 'healthy'."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details

        health_details = {
            "healthy": True,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "healthy",
                    "phase": "models_list_ok",
                },
            ],
        }

        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is True

    def test_handles_missing_dependencies(self) -> None:
        """Should handle health details with no dependencies list."""
        from scripts.lab_common.provider_status import _find_dependency_by_name

        health_details = {"healthy": True, "primary_failure_class": ""}

        provider_dep = _find_dependency_by_name(health_details, "diagnosis_provider")

        # Should return empty dict when dependencies is missing
        assert provider_dep == {}, \
            "_find_dependency_by_name should return {} when dependencies is missing"

    def test_handles_non_list_dependencies(self) -> None:
        """Should handle non-list dependencies gracefully."""
        from scripts.lab_common.provider_status import _find_dependency_by_name

        # dependencies is a dict instead of list (invalid but defensive)
        health_details = {
            "healthy": True,
            "dependencies": {"diagnosis_provider": {"status": "available"}},
        }

        provider_dep = _find_dependency_by_name(health_details, "diagnosis_provider")

        # Should return empty dict, not crash
        assert provider_dep == {}


class TestProviderStatusResult:
    """Test ProviderStatus dataclass."""

    def test_to_dict(self) -> None:
        """Should convert to dictionary for JSON serialization."""
        from scripts.lab_common.provider_status import ProviderStatus

        status = ProviderStatus(
            provider_enabled=True,
            provider_configured=True,
            provider_status="available",
            provider_phase="models_list_ok",
            reason_code="provider_available",
        )

        result = status.to_dict()

        assert result["provider_enabled"] is True
        assert result["provider_configured"] is True
        assert result["provider_status"] == "available"
        assert result["provider_phase"] == "models_list_ok"
        assert result["reason_code"] == "provider_available"


class TestIsProviderHealthy:
    """Test is_provider_healthy helper function."""

    def test_healthy_provider(self) -> None:
        """Should return True for healthy provider."""
        from scripts.lab_common.provider_status import ProviderStatus, is_provider_healthy

        status = ProviderStatus(
            provider_enabled=True,
            provider_configured=True,
            provider_status="available",
        )

        assert is_provider_healthy(status) is True

    def test_disabled_provider(self) -> None:
        """Should return False for disabled provider."""
        from scripts.lab_common.provider_status import ProviderStatus, is_provider_healthy

        status = ProviderStatus(
            provider_enabled=False,
            provider_configured=False,
            provider_status="unavailable",
        )

        assert is_provider_healthy(status) is False

    def test_unconfigured_provider(self) -> None:
        """Should return False for unconfigured provider."""
        from scripts.lab_common.provider_status import ProviderStatus, is_provider_healthy

        status = ProviderStatus(
            provider_enabled=True,
            provider_configured=False,
            provider_status="configured",
        )

        assert is_provider_healthy(status) is False
