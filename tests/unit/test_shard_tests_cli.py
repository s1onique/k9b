"""Tests for CLI argument parsing, subprocess behavior, and integration workflows."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Import the sharding module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import shard_tests


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
        """--collect-only outputs nodeids without sharding."""
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
        """--metrics outputs valid JSON."""
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
    """Integration tests for the full sharding workflow."""

    def test_four_shard_completeness(self) -> None:
        """4-shard assignment covers all nodeids exactly once."""
        import test_collection

        # Collect all nodeids using the shared collection helper
        # (tests/ is appended automatically by build_collection_command)
        cmd = test_collection.build_collection_command(include_allowed_ignores=False)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)

        assert result.returncode == 0

        all_nodeids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("tests/") and "::" in line:
                all_nodeids.append(line)

        assert len(all_nodeids) > 0

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
        import test_collection

        # Collect using the shared collection helper
        # (tests/ is appended automatically by build_collection_command)
        cmd = test_collection.build_collection_command(include_allowed_ignores=False)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)

        all_nodeids = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("tests/") and "::" in line:
                all_nodeids.add(line)

        # Shard into 4
        shards = shard_tests.assign_shards_lpt(list(all_nodeids), {}, 4)

        # Collect union
        union = set()
        for shard in shards:
            union.update(shard.nodeids)

        assert union == all_nodeids
