"""Tests for P4c outcome normalization helpers.

These tests verify that normalize_p4c_outcome_for_dict handles shape mismatches
at evidence boundary crossings, preventing runtime errors like:
    'str' object has no attribute 'keys'

See: https://github.com/s1onique/k9b/issues/... (P4c boundary shape mismatch)
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contract_types import (
    normalize_p4c_outcome_for_dict,
    normalize_review_artifact_ref,
)


class TestNormalizeP4cOutcomeForDict:
    """Tests for normalize_p4c_outcome_for_dict function."""

    def test_preserves_review_artifact_path_strings(self) -> None:
        """Verify list[str] review_artifact_paths are preserved as list[str].

        This is the primary APF-style regression for the boundary shape mismatch
        where review_artifact_paths could arrive as list[str] but downstream
        code expected list[dict] and called .keys() on strings.
        """
        outcome = normalize_p4c_outcome_for_dict(
            {
                "success": True,
                "review_artifact_paths": [
                    "auto-pass1-diagnosis-review-packet.json",
                    "auto-pass2-diagnosis-review-packet.json",
                ],
                "pass_run_ids": ("pass-1", "pass-2"),
                "failure_reasons": (),
            }
        )

        assert outcome["review_artifact_paths"] == [
            "auto-pass1-diagnosis-review-packet.json",
            "auto-pass2-diagnosis-review-packet.json",
        ]
        assert outcome["pass_run_ids"] == ["pass-1", "pass-2"]
        assert outcome["failure_reasons"] == []

    def test_normalizes_tuple_to_list(self) -> None:
        """Verify tuple fields are normalized to list for JSON serialization."""
        outcome = normalize_p4c_outcome_for_dict(
            {
                "success": True,
                "pass_run_ids": ("run-1", "run-2", "run-3"),
                "review_artifact_paths": ("artifact1.json",),
                "failure_reasons": ("reason1", "reason2"),
            }
        )

        assert outcome["pass_run_ids"] == ["run-1", "run-2", "run-3"]
        assert outcome["review_artifact_paths"] == ["artifact1.json"]
        assert outcome["failure_reasons"] == ["reason1", "reason2"]

    def test_flattens_nested_lists(self) -> None:
        """Verify nested lists are flattened to single-level list of strings."""
        outcome = normalize_p4c_outcome_for_dict(
            {
                "success": True,
                "review_artifact_paths": [
                    ["nested1.json", "nested2.json"],
                    ["nested3.json"],
                ],
            }
        )

        assert outcome["review_artifact_paths"] == [
            "nested1.json",
            "nested2.json",
            "nested3.json",
        ]

    def test_handles_empty_review_artifact_paths(self) -> None:
        """Verify empty/None review_artifact_paths returns empty list."""
        outcome = normalize_p4c_outcome_for_dict(
            {
                "success": False,
                "review_artifact_paths": [],
            }
        )
        assert outcome["review_artifact_paths"] == []

    def test_handles_string_input_gracefully(self) -> None:
        """Verify string input (unexpected type) returns empty dict."""
        outcome = normalize_p4c_outcome_for_dict("unexpected-string")
        assert outcome == {}

    def test_handles_none_input(self) -> None:
        """Verify None input returns empty dict."""
        outcome = normalize_p4c_outcome_for_dict(None)
        assert outcome == {}


class TestNormalizeReviewArtifactRef:
    """Tests for normalize_review_artifact_ref function."""

    def test_string_to_path_dict(self) -> None:
        """Verify string input is wrapped in dict with 'path' key."""
        result = normalize_review_artifact_ref("path/to/artifact.json")
        assert result == {"path": "path/to/artifact.json"}

    def test_dict_passed_through(self) -> None:
        """Verify dict input is returned as-is."""
        input_dict = {"path": "artifact.json", "extra": "field"}
        result = normalize_review_artifact_ref(input_dict)
        assert result == input_dict

    def test_none_returns_empty_dict(self) -> None:
        """Verify None returns empty dict."""
        result = normalize_review_artifact_ref(None)
        assert result == {}

    def test_raises_on_unsupported_type(self) -> None:
        """Verify unsupported types raise TypeError."""
        import pytest

        with pytest.raises(TypeError, match="unsupported review artifact ref type"):
            normalize_review_artifact_ref(123)
