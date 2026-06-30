"""Tests for public API boundaries.

These tests prove that:
1. Forbidden/internal APIs are not exposed in public imports
2. Private implementation details remain internal
3. Boundary contracts are respected
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# =============================================================================
# Private Name Tests
# =============================================================================


class TestPrivateNamesNotExported:
    """Tests that private names are not in public exports."""

    def test_runtime_all_does_not_contain_private_names(self) -> None:
        """__all__ should not contain private (underscore-prefixed) names."""
        from k8s_diag_agent.collect.runtime import __all__
        for name in __all__:
            assert not name.startswith("_"), f"Private name {name!r} found in __all__"

    def test_runtime_artifacts_all_does_not_contain_private_names(self) -> None:
        """__all__ should not contain private names."""
        from k8s_diag_agent.collect.runtime_artifacts import __all__
        for name in __all__:
            assert not name.startswith("_"), f"Private name {name!r} found in __all__"

    def test_runtime_gating_all_does_not_contain_private_names(self) -> None:
        """__all__ should not contain private names."""
        from k8s_diag_agent.collect.runtime_gating import __all__
        for name in __all__:
            assert not name.startswith("_"), f"Private name {name!r} found in __all__"

    def test_runtime_state_all_does_not_contain_private_names(self) -> None:
        """__all__ should not contain private names."""
        from k8s_diag_agent.collect.runtime_state import __all__
        for name in __all__:
            assert not name.startswith("_"), f"Private name {name!r} found in __all__"


class TestInternalModulesNotExported:
    """Tests that internal modules are not re-exported in public API."""

    def test_runtime_runtime_all_contains_only_public_names(self) -> None:
        """runtime should only export intended public names."""
        from k8s_diag_agent.collect.runtime import __all__

        # Expected public names (defined for documentation, actual check validates no private names)
        for name in __all__:
            # Should be a public name (no underscore prefix)
            assert not name.startswith("_"), f"Private name {name!r} in __all__"


class TestModuleBoundaryContracts:
    """Tests for module boundary contracts."""

    def test_runtime_does_not_export_internal_gating_details(self) -> None:
        """runtime should not export internal gating implementation details."""
        from k8s_diag_agent.collect.runtime import __all__

        # These should NOT be in runtime's __all__
        internal_names = [
            "_check_is_mutating",
            "_check_is_sensitive",
            "_compute_fingerprint",
        ]

        for name in internal_names:
            assert name not in __all__, f"Internal name {name!r} should not be in runtime __all__"

    def test_runtime_state_exports_only_state_class(self) -> None:
        """runtime_state should only export state-related names."""
        from k8s_diag_agent.collect.runtime_state import __all__

        assert "LoopRuntimeState" in __all__
        # RUNTIME_SCHEMA_VERSION is also allowed as it's a constant
        allowed_extras = {"RUNTIME_SCHEMA_VERSION"}
        for name in __all__:
            if name not in allowed_extras:
                assert name == "LoopRuntimeState", f"Unexpected export: {name!r}"


# =============================================================================
# Type Safety Tests
# =============================================================================


class TestTypeContracts:
    """Tests for type-level contracts."""

    def test_loop_runtime_state_has_required_fields(self) -> None:
        """LoopRuntimeState should have all required fields."""
        from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

        state = LoopRuntimeState(
            loop_run_id="test-loop",
            incident_id="test-incident",
            pass_index=1,
            started_at="2024-01-01T00:00:00+00:00",
        )

        assert state.loop_run_id == "test-loop"
        assert state.incident_id == "test-incident"
        assert state.pass_index == 1
        assert state.started_at == "2024-01-01T00:00:00+00:00"

    def test_gate_summary_has_required_fields(self) -> None:
        """GateSummary should have all required fields."""
        from k8s_diag_agent.collect.runtime_gating import GateSummary

        summary = GateSummary(
            proposed=5,
            accepted=3,
            rejected_mutating=1,
            rejected_sensitive=0,
            rejected_duplicate=1,
            accepted_checks=[],
            rejected_checks=[],
            accepted_fingerprints=[],
            rejected_fingerprints=[],
        )

        assert summary.proposed == 5
        assert summary.accepted == 3
        assert summary.rejected_mutating == 1
        assert summary.rejected_sensitive == 0
        assert summary.rejected_duplicate == 1

    def test_runtime_schema_version_format(self) -> None:
        """RUNTIME_SCHEMA_VERSION should follow semver format."""
        from k8s_diag_agent.collect.runtime_state import RUNTIME_SCHEMA_VERSION

        # Should match X.Y format
        assert re.match(r"^\d+\.\d+$", RUNTIME_SCHEMA_VERSION), (
            f"Invalid schema version format: {RUNTIME_SCHEMA_VERSION!r}"
        )
