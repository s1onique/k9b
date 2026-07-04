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


# Module-scoped fixture for collected nodeids (computed once per test session)
_collected_nodeids: CollectedNodeids | None = None


def _get_collected_nodeids() -> CollectedNodeids:
    """Get cached collection results or collect fresh."""
    global _collected_nodeids
    if _collected_nodeids is None:
        import test_collection
        result = test_collection.collect_test_nodeids()
        _collected_nodeids = CollectedNodeids(
            nodeids=list(result.nodeids),
            returncode=result.returncode,
        )
    return _collected_nodeids


class TestCLIParsing:
    """Tests for CLI argument parsing via main()."""

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

    def test_collect_only_outputs_nodeids(self) -> None:
        """--collect-only outputs nodeids without sharding (CLI smoke test)."""
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

        assert result.returncode == 0
        # Should output some nodeids
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) > 0

    def test_metrics_json_output(self) -> None:
        """--metrics outputs valid JSON (CLI smoke test)."""
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

        assert result.returncode == 0

        # Should be valid JSON
        data = json.loads(result.stdout)
        assert "num_shards" in data
        assert data["num_shards"] == 4


class TestIntegration:
    """Integration tests for the full sharding workflow.

    Uses cached collection results to avoid repeated pytest --collect-only calls.
    """

    def test_four_shard_completeness(self) -> None:
        """4-shard assignment covers all nodeids exactly once."""
        collected = _get_collected_nodeids()
        assert len(collected.nodeids) > 0, "Should collect some nodeids"

        all_nodeids = collected.nodeids

        # Assign to 4 shards
        shards = shard_tests.assign_shards_lpt(all_nodeids, {}, 4)

        # Verify completeness
        success = shard_tests.verify_shard_completeness(all_nodeids, shards)
        assert success is True

        # Verify all shards have some work
        for shard in shards:
            assert len(shard.nodeids) > 0

    def test_shard_union_matches_collection(self) -> None:
        """Union of all shards equals collected nodeids."""
        collected = _get_collected_nodeids()
        all_nodeids = set(collected.nodeids)

        # Shard into 4
        shards = shard_tests.assign_shards_lpt(list(all_nodeids), {}, 4)

        # Collect union
        union = set()
        for shard in shards:
            union.update(shard.nodeids)

        assert union == all_nodeids

    def test_no_duplicate_nodeids_across_shards(self) -> None:
        """No nodeid appears in more than one shard."""
        collected = _get_collected_nodeids()
        all_nodeids = collected.nodeids

        # Shard into 4
        shards = shard_tests.assign_shards_lpt(all_nodeids, {}, 4)

        # Check for duplicates
        seen: dict[str, int] = {}
        for shard in shards:
            for nodeid in shard.nodeids:
                seen[nodeid] = seen.get(nodeid, 0) + 1

        duplicates = {nid: count for nid, count in seen.items() if count > 1}
        assert len(duplicates) == 0, f"Found duplicate nodeids: {duplicates}"

    def test_metrics_reflect_shard_distribution(self) -> None:
        """Metrics JSON correctly reflects shard weights and counts."""
        collected = _get_collected_nodeids()
        all_nodeids = collected.nodeids

        # Assign to 4 shards
        shards = shard_tests.assign_shards_lpt(all_nodeids, {}, 4)

        # Compute metrics directly
        metrics = shard_tests.compute_shard_metrics(shards)

        assert metrics["num_shards"] == 4
        assert metrics["total_tests"] == len(all_nodeids)
        assert len(metrics["shard_weights"]) == 4
        assert len(metrics["shard_counts"]) == 4

        # Sum of shard counts should equal total
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
