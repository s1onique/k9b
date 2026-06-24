"""Dependency injection provider for incident one-pass diagnosis service.

This module provides a registry for injectable dependencies used by the
HTTP API route handler. Tests can override these to inject fake providers,
handlers, and artifact writers without modifying the handler code.

Production default: All providers return None, causing fail-closed behavior
if no LLM provider is configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_diagnosis_service import ArtifactWriter, DiagnosisProvider
    from .incident_read_only_check_runner import ReadOnlyCheckHandler

# Global provider registry
_diagnosis_provider: DiagnosisProvider | None = None
_fake_handlers: dict[str, ReadOnlyCheckHandler] | None = None
_artifact_writer: ArtifactWriter | None = None
_golden_case_mode: bool = False
_golden_case_manifest: dict[str, Any] | None = None
_golden_case_case_dir: Path | None = None
_golden_case_evidence_provider: Any = None


def get_diagnosis_provider() -> DiagnosisProvider | None:
    """Get the current diagnosis provider."""
    return _diagnosis_provider


def set_diagnosis_provider(provider: DiagnosisProvider | None) -> None:
    """Set a custom diagnosis provider (for testing)."""
    global _diagnosis_provider
    _diagnosis_provider = provider


def get_fake_handlers() -> dict[str, ReadOnlyCheckHandler] | None:
    """Get the current fake handlers."""
    return _fake_handlers


def set_fake_handlers(handlers: dict[str, ReadOnlyCheckHandler] | None) -> None:
    """Set custom fake handlers (for testing)."""
    global _fake_handlers
    _fake_handlers = handlers


def get_artifact_writer() -> ArtifactWriter | None:
    """Get the current artifact writer."""
    return _artifact_writer


def set_artifact_writer(writer: ArtifactWriter | None) -> None:
    """Set a custom artifact writer (for testing)."""
    global _artifact_writer
    _artifact_writer = writer


def is_golden_case_mode() -> bool:
    """Get whether golden-case mode is enabled."""
    return _golden_case_mode


def get_golden_case_manifest() -> dict[str, Any] | None:
    """Get the golden-case manifest (if in golden-case mode)."""
    return _golden_case_manifest


def get_golden_case_case_dir() -> Path | None:
    """Get the golden-case case directory (if in golden-case mode)."""
    return _golden_case_case_dir


def get_golden_case_evidence_provider() -> Any:
    """Get the golden-case evidence provider (if in golden-case mode)."""
    return _golden_case_evidence_provider


def set_golden_case_context(
    enabled: bool,
    manifest: dict[str, Any] | None = None,
    case_dir: Path | None = None,
    evidence_provider: Any = None,
) -> None:
    """Set golden-case context for ACT-local verification.

    Args:
        enabled: Whether golden-case mode is enabled
        manifest: Golden-case manifest dict
        case_dir: Path to golden-case fixture directory
        evidence_provider: Golden-case evidence provider instance
    """
    global _golden_case_mode, _golden_case_manifest, _golden_case_case_dir, _golden_case_evidence_provider
    _golden_case_mode = enabled
    _golden_case_manifest = manifest
    _golden_case_case_dir = case_dir
    _golden_case_evidence_provider = evidence_provider


def reset_providers() -> None:
    """Reset all providers to default (None)."""
    global _diagnosis_provider, _fake_handlers, _artifact_writer
    global _golden_case_mode, _golden_case_manifest, _golden_case_case_dir, _golden_case_evidence_provider
    _diagnosis_provider = None
    _fake_handlers = None
    _artifact_writer = None
    _golden_case_mode = False
    _golden_case_manifest = None
    _golden_case_case_dir = None
    _golden_case_evidence_provider = None


__all__ = [
    "get_diagnosis_provider",
    "set_diagnosis_provider",
    "get_fake_handlers",
    "set_fake_handlers",
    "get_artifact_writer",
    "set_artifact_writer",
    "is_golden_case_mode",
    "get_golden_case_manifest",
    "get_golden_case_case_dir",
    "get_golden_case_evidence_provider",
    "set_golden_case_context",
    "reset_providers",
]
