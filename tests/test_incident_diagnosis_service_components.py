"""Tests for individual components of the incident diagnosis service.

These tests verify the behavior of specific components like
NoOpDiagnosisProvider and TempFileArtifactWriter.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_service import (
    NoOpDiagnosisProvider,
    TempFileArtifactWriter,
)


def test_noop_provider_fails_closed() -> None:
    """NoOpDiagnosisProvider raises RuntimeError on complete."""
    provider = NoOpDiagnosisProvider()
    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")
    assert "No diagnosis provider configured" in str(exc_info.value)


def test_temp_file_artifact_writer() -> None:
    """TempFileArtifactWriter writes files correctly."""
    writer = TempFileArtifactWriter()
    output_dir = Path(tempfile.mkdtemp())

    result = writer.write_diagnosis_artifact(
        output_dir=output_dir,
        incident_id="test-001",
        diagnosis={"test": "data"},
        now=datetime.now(UTC),
    )

    assert result["written"] is True
    assert "artifact_path" in result
    assert Path(result["artifact_path"]).exists()
