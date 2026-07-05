"""Tests for CLI argument parsing, subprocess behavior, and integration workflows.

Optimization: Use module-scoped collected nodeids fixture to avoid repeated
pytest --collect-only subprocess calls. Keep CLI smoke tests for real wiring.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# Import the sharding module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import shard_tests


class CollectedNodeids(NamedTuple):
    """Cached collection result for use across tests."""
    nodeids: list[str]
    returncode: int


class CLICollectResult(NamedTuple):
    """Cached CLI --collect-only result for use across tests."""
    stdout: str
    returncode: int


class CLIMetricsResult(NamedTuple):
    """Cached CLI --metrics result for use across tests."""
    stdout: str
    returncode: int


class CLIAllShardsMetricsResult(NamedTuple):
    """Cached CLI --metrics result with --total 4 for use across tests."""
    stdout: str
    returncode: int


# Module-scoped fixtures (computed once per test session)
_collected_nodeids: CollectedNodeids | None = None
_cli_collect_result: CLICollectResult | None = None
_cli_metrics_result: CLIMetricsResult | None = None
_cli_all_shards_metrics_result: CLIAllShardsMetricsResult | None = None


def _get_collected_nodeids() -> CollectedNodeids:
    """Get cached collection results or collect fresh (once per session)."""
    global _collected_nodeids
    if _collected_nodeids is None:
        import test_collection
        result = test_collection.collect_test_nodeids()
        _collected_nodeids = CollectedNodeids(
            nodeids=list(result.nodeids),
            returncode=result.returncode,
        )
    return _collected_nodeids


def _get_cli_collect_result() -> CLICollectResult:
    """Get cached CLI --collect-only result or run fresh (once per session)."""
    global _cli_collect_result
    if _cli_collect_result is None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"),
                "--total", "2",
                "--collect-only",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        _cli_collect_result = CLICollectResult(
            stdout=result.stdout,
            returncode=result.returncode,
        )
    return _cli_collect_result


def _get_cli_metrics_result() -> CLIMetricsResult:
    """Get cached CLI --metrics (4 shards) result or run fresh (once per session)."""
    global _cli_metrics_result
    if _cli_metrics_result is None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"),
                "--total", "4",
                "--metrics",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        _cli_metrics_result = CLIMetricsResult(
            stdout=result.stdout,
            returncode=result.returncode,
        )
    return _cli_metrics_result


class TestCLIParsing:
    """Tests for CLI argument parsing and end-to-end CLI behavior.

    Preserves CLI subprocess smoke tests for wiring verification.
    Algorithm correctness is tested via direct function calls (faster, deterministic).
    """

    def test_invalid_shard_index_rejected(self) -> None:
        """Shard index outside valid range exits with error."""
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"),
                "--total", "4",
                "--shard", "5",  # Invalid: 5 >= 4
                "--collect-only",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "invalid" in result.stderr.lower()

    def test_negative_shard_index_rejected(self) -> None:
        """Negative shard index exits with error."""
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"),
                "--total", "4",
                "--shard", "-1",
                "--collect-only",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1

    def test_cli_smoke_end_to_end(self) -> None:
        """End-to-end CLI smoke: --collect-only and --metrics wiring.

        Verifies both CLI entry points produce correct output using cached
        subprocess results to avoid repeated CLI invocation overhead.
        """
        collect_result = _get_cli_collect_result()
        assert collect_result.returncode == 0
        lines = [line for line in collect_result.stdout.strip().split("\n") if line]
        assert len(lines) > 0

        metrics_result = _get_cli_metrics_result()
        assert metrics_result.returncode == 0
        data = json.loads(metrics_result.stdout)
        assert data["num_shards"] == 4
        assert "total_tests" in data
        assert "shard_counts" in data
        assert "shard_weights" in data


class TestIntegration:
    """Integration tests for the full sharding workflow.

    Uses cached collection results to avoid repeated pytest --collect-only calls.
    """

    def test_four_shard_properties(self) -> None:
        """Verify all shard correctness properties in one pass.

        Combines completeness, union, duplicate, and metrics checks into one
        algorithm test. This avoids repeated collection calls across multiple
        test methods while preserving all meaningful assertions.
        """
        collected = _get_collected_nodeids()
        assert len(collected.nodeids) > 0, "Should collect some nodeids"

        all_nodeids = collected.nodeids
        all_nodeids_set = set(all_nodeids)

        # Assign to 4 shards (one computation shared by all assertions)
        shards = shard_tests.assign_shards_lpt(all_nodeids, {}, 4)

        # Property 1: completeness - all nodeids assigned exactly once
        success = shard_tests.verify_shard_completeness(all_nodeids, shards)
        assert success is True
        for shard in shards:
            assert len(shard.nodeids) > 0

        # Property 2: union of shards equals collected nodeids
        union = set()
        for shard in shards:
            union.update(shard.nodeids)
        assert union == all_nodeids_set

        # Property 3: no duplicate nodeids across shards
        seen: dict[str, int] = {}
        for shard in shards:
            for nodeid in shard.nodeids:
                seen[nodeid] = seen.get(nodeid, 0) + 1
        duplicates = {nid: count for nid, count in seen.items() if count > 1}
        assert len(duplicates) == 0, f"Found duplicate nodeids: {duplicates}"

        # Property 4: metrics reflect shard distribution
        metrics = shard_tests.compute_shard_metrics(shards)
        assert metrics["num_shards"] == 4
        assert metrics["total_tests"] == len(all_nodeids)
        assert len(metrics["shard_weights"]) == 4
        assert len(metrics["shard_counts"]) == 4
        assert sum(metrics["shard_counts"]) == len(all_nodeids)

    def test_missing_duration_file_falls_back_to_round_robin(self, tmp_path: Path) -> None:
        """Missing duration file should use fallback weights, not fail."""
        # Use a non-existent duration file
        missing_durations = tmp_path / "nonexistent.json"

        # Call load_duration_weights directly
        weights = shard_tests.load_duration_weights(missing_durations)

        # Should return empty dict (use fallback weight of 1.0)
        assert weights == {}

        # Sharding should still work with empty weights
        nodeids = [
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
            "tests/test_c.py::test_three",
        ]
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 2)

        # Should have 2 shards with some nodeids each
        assert len(shards) == 2
        total_assigned = sum(len(s.nodeids) for s in shards)
        assert total_assigned == 3
