"""Serializer verifier return-path regression fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.incident_lifecycle_boundary.redaction_serialization import (
    check_serializer_explicit_conversion,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "fixture.py"
    path.write_text(content, encoding="utf-8")
    return path


def _module(body: str) -> str:
    return f"from dataclasses import dataclass\n@dataclass\nclass RedactedEvidenceSummary:\n    artifact_id: str\n    summary: str\n{body}"


def test_two_valid_literal_dict_returns_pass(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _module("    def to_dict(self, include_id: bool):\n        if include_id:\n            return {'artifact_id': self.artifact_id, 'summary': str(self.summary)}\n        return {'summary': str(self.summary)}\n"),
    )
    assert check_serializer_explicit_conversion(str(path)) == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "    def to_dict(self, include_summary: bool):\n        if include_summary:\n            return {'artifact_id': self.artifact_id, 'summary': str(self.summary)}\n        return {'artifact_id': self.artifact_id}\n",
            "Missing summary",
        ),
        (
            "    def to_dict(self, include_summary: bool):\n        if include_summary:\n            return {'artifact_id': self.artifact_id, 'summary': str(self.summary)}\n        return {'artifact_id': self.artifact_id, 'summary': self.summary}\n",
            "str(self.summary)",
        ),
        (
            "    def to_dict(self):\n        payload = {'summary': str(self.summary)}\n        return payload\n",
            "literal dict",
        ),
        (
            "    def to_dict(self):\n        payload = {'summary': str(self.summary)}\n",
            "No return",
        ),
    ],
)
def test_invalid_serializer_return_paths_fail(
    tmp_path: Path,
    body: str,
    expected: str,
) -> None:
    path = _write(tmp_path, _module(body))
    errors = check_serializer_explicit_conversion(str(path))
    assert errors
    assert any(expected in error for error in errors), errors
