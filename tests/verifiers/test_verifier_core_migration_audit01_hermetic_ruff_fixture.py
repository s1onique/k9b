"""CORRECTION25: Hermetic Ruff fixture verification tests.

This module verifies the hermetic_ruff_capability fixture correctly
patches and restores the resolver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.verifiers.verifier_core_migration_audit01_correction22_hermetic_ruff import (
    build_hermetic_capability,
    install_hermetic_ruff_resolver,
)


def test_hermetic_resolver_is_restored(
    tmp_path: Path,
) -> None:
    """Prove the fixture teardown restores the original resolver.

    This test uses MonkeyPatch.context() to patch and then automatically
    restore the resolver, proving that the fixture pattern works correctly.
    """
    import scripts.verifiers_audit.range_evidence_orchestrator as orchestrator

    # Capture the original resolver BEFORE patching
    original_resolver = orchestrator.resolve_ruff_identity

    capability = build_hermetic_capability(tmp_path / "ruff-capability")

    with pytest.MonkeyPatch.context() as patch:
        install_hermetic_ruff_resolver(monkeypatch=patch, capability=capability)

        # Verify the resolver was patched
        assert orchestrator.resolve_ruff_identity is not original_resolver

    # After the context exits, verify restoration
    assert orchestrator.resolve_ruff_identity is original_resolver


def test_hermetic_capability_provides_valid_identity(
    tmp_path: Path,
) -> None:
    """Prove the hermetic capability provides all required identity fields."""
    capability = build_hermetic_capability(tmp_path / "ruff-capability")
    identity = capability.get_identity()

    # Required fields
    assert "launcher_argv_prefix" in identity
    assert "launcher_path" in identity
    assert "launcher_sha256" in identity
    assert "tool_payload_path" in identity
    assert "tool_payload_sha256" in identity
    assert "ruff_version" in identity
    assert "ruff_invocation_mode" in identity
    assert "configuration_files" in identity
    assert "configuration_file_sha256" in identity

    # Verify values
    assert identity["ruff_invocation_mode"] == "hermetic_test_script"
    assert identity["tool_payload_path"] == str(capability.script_path)
    assert identity["tool_payload_sha256"] == capability.script_sha256
