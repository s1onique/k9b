"""Tests for ui/api.py batch eligibility security hardening.

These tests verify the security hardening for:
- _compute_batch_eligibility() glob pattern validation
- _compute_batch_eligibility_from_cache() validation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import (
    _compute_batch_eligibility,
    _compute_batch_eligibility_from_cache,
)


class TestComputeBatchEligibility:
    """Tests for _compute_batch_eligibility() security hardening."""

    def test_valid_run_id_computes_eligibility(self, tmp_path: Path) -> None:
        """Valid run_id should compute eligibility normally."""
        # Create external-analysis directory with plan and execution artifacts
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create a valid plan artifact
        plan_file = ea_dir / "run-test-next-check-plan-001.json"
        plan_file.write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Test command",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }),
            encoding="utf-8",
        )

        # Valid run_id should work
        executable, count = _compute_batch_eligibility("run-test", tmp_path)
        assert executable is True
        assert count == 1

    def test_traversal_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Traversal run_id should not search outside root and returns safe fallback."""
        # Create external-analysis directory with artifacts
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts that should NOT be found
        (ea_dir / "run-test-next-check-plan-001.json").write_text(
            json.dumps({"purpose": "next-check-planning", "payload": {"candidates": []}}),
            encoding="utf-8",
        )

        # Traversal run_id should return safe fallback, not raise
        executable, count = _compute_batch_eligibility("../etc", tmp_path)
        assert executable is False
        assert count == 0

    def test_glob_metachar_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Glob metacharacter in run_id should return safe fallback."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create artifacts
        (ea_dir / "run-test-next-check-plan-001.json").write_text(
            json.dumps({"purpose": "next-check-planning", "payload": {"candidates": []}}),
            encoding="utf-8",
        )

        # Glob metacharacter should be rejected and return safe fallback
        executable, count = _compute_batch_eligibility("run*", tmp_path)
        assert executable is False
        assert count == 0

    def test_prefix_collision_prevented(self, tmp_path: Path) -> None:
        """Verify run_id prefix collision is prevented.

        run_id="run-test" should NOT match "run-test-extra" artifacts.
        """
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create exact prefix artifact
        (ea_dir / "run-test-next-check-plan-001.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Exact prefix match",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }),
            encoding="utf-8",
        )
        # Create extended prefix artifact (should NOT match)
        (ea_dir / "run-test-extra-next-check-plan-001.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c2",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Extended prefix - should not match",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }),
            encoding="utf-8",
        )

        # Only exact prefix should match
        executable, count = _compute_batch_eligibility("run-test", tmp_path)
        assert executable is True
        assert count == 1  # Only c1 should be found

    def test_empty_run_id_returns_safe_fallback(self, tmp_path: Path) -> None:
        """Empty run_id should return safe fallback."""
        executable, count = _compute_batch_eligibility("", tmp_path)
        assert executable is False
        assert count == 0

    def test_execution_glob_also_hardened(self, tmp_path: Path) -> None:
        """Verify execution glob pattern is also hardened."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create plan artifact with candidates
        (ea_dir / "run-test-next-check-plan-001.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Test command",
                            "targetContext": "prod-cluster",
                        },
                        {
                            "candidateId": "c2",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Another test",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }),
            encoding="utf-8",
        )

        # Create execution artifact for index 0
        (ea_dir / "run-test-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "payload": {"candidateIndex": 0}
            }),
            encoding="utf-8",
        )

        # run-test should find 1 eligible (c1 executed, c2 not)
        executable, count = _compute_batch_eligibility("run-test", tmp_path)
        assert executable is True
        assert count == 1

        # Traversal should return empty (no execution glob search)
        executable, count = _compute_batch_eligibility("../evil", tmp_path)
        assert executable is False
        assert count == 0


class TestComputeBatchEligibilityFromCache:
    """Tests for _compute_batch_eligibility_from_cache() security hardening."""

    def test_valid_run_id_computes_eligibility(self) -> None:
        """Valid run_id should compute eligibility normally from cache."""
        plan_data = {
            "run-test": {
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Test command",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }
        }
        execution_indices = {"run-test": set()}  # type: ignore[var-annotated]

        executable, count = _compute_batch_eligibility_from_cache(
            "run-test", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is True
        assert count == 1

    def test_traversal_run_id_returns_safe_fallback(self) -> None:
        """Traversal run_id should return safe fallback."""
        plan_data: dict[str, dict[str, object]] = {
            "run-test": {
                "purpose": "next-check-planning",
                "payload": {"candidates": []}
            }
        }
        execution_indices: dict[str, set[int]] = {}

        # Traversal should return safe fallback, not raise
        executable, count = _compute_batch_eligibility_from_cache(
            "../etc", plan_data, execution_indices
        )
        assert executable is False
        assert count == 0

    def test_glob_metachar_run_id_returns_safe_fallback(self) -> None:
        """Glob metacharacter in run_id should return safe fallback."""
        plan_data: dict[str, dict[str, object]] = {
            "run-test": {
                "purpose": "next-check-planning",
                "payload": {"candidates": []}
            }
        }
        execution_indices: dict[str, set[int]] = {}

        # Glob metacharacter should be rejected
        executable, count = _compute_batch_eligibility_from_cache(
            "run*", plan_data, execution_indices
        )
        assert executable is False
        assert count == 0

    def test_execution_indices_uses_validated_run_id(self) -> None:
        """Verify execution_indices lookup uses validated_run_id."""
        plan_data = {
            "run-test": {
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Test command",
                            "targetContext": "prod-cluster",
                        },
                        {
                            "candidateId": "c2",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Another test",
                            "targetContext": "prod-cluster",
                        }
                    ]
                }
            }
        }
        # Pre-populate execution indices for run-test
        execution_indices = {"run-test": {0}}  # Index 0 already executed

        # run-test should find 1 eligible (c1 executed, c2 not)
        executable, count = _compute_batch_eligibility_from_cache(
            "run-test", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is True
        assert count == 1

        # Invalid run_id should return 0 (no dict lookup)
        executable, count = _compute_batch_eligibility_from_cache(
            "../evil", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is False
        assert count == 0

    def test_empty_run_id_returns_safe_fallback(self) -> None:
        """Empty run_id should return safe fallback."""
        plan_data: dict[str, dict[str, object]] = {}
        execution_indices: dict[str, set[int]] = {}

        executable, count = _compute_batch_eligibility_from_cache(
            "", plan_data, execution_indices
        )
        assert executable is False
        assert count == 0

    def test_missing_plan_data_returns_zero(self) -> None:
        """Missing plan data should return 0."""
        plan_data: dict[str, dict[str, object]] = {}
        execution_indices: dict[str, set[int]] = {}

        executable, count = _compute_batch_eligibility_from_cache(
            "run-test", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is False
        assert count == 0

    def test_validated_run_id_lookup_consistency(self) -> None:
        """Verify both plan_data and execution_indices use validated_run_id."""
        # Create a plan with candidates
        plan_data = {
            "run-123": {
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "candidateId": "c1",
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl",
                            "description": "Test",
                            "targetContext": "prod",
                        }
                    ]
                }
            }
        }
        # Execution indices for run-123
        execution_indices = {"run-123": set()}  # type: ignore[var-annotated]

        # Valid run_id should find both plan and indices
        executable, count = _compute_batch_eligibility_from_cache(
            "run-123", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is True
        assert count == 1

        # Invalid run_id should not find anything (no glob needed, but dict lookup)
        executable, count = _compute_batch_eligibility_from_cache(
            "run-456", cast(dict[str, dict[str, object]], plan_data), execution_indices
        )
        assert executable is False
        assert count == 0