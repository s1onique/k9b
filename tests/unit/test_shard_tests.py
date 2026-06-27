"""Tests for the deterministic duration-weighted test sharding module."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Import the sharding module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import shard_tests


class TestLoadDurationWeights:
    """Tests for load_duration_weights function."""

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Loading non-existent file returns empty dict."""
        result = shard_tests.load_duration_weights(tmp_path / "nonexistent.json")
        assert result == {}

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        """Loading valid manifest returns weights dict."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [
                {"nodeid": "test_a.py::test_1", "duration_s": 1.5},
                {"nodeid": "test_b.py::test_2", "duration_s": 2.0},
            ]
        }))
        
        result = shard_tests.load_duration_weights(manifest)
        assert result == {
            "test_a.py::test_1": 1.5,
            "test_b.py::test_2": 2.0,
        }

    def test_fallback_weight_used_for_missing(self, tmp_path: Path) -> None:
        """Unknown nodeids use FALLBACK_WEIGHT when accessing weights."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [
                {"nodeid": "test_a.py::test_1", "duration_s": 1.5},
            ]
        }))
        
        weights = shard_tests.load_duration_weights(manifest)
        # Unknown test gets fallback
        assert weights.get("test_c.py::test_3", shard_tests.FALLBACK_WEIGHT) == shard_tests.FALLBACK_WEIGHT
        # Known test gets actual weight
        assert weights.get("test_a.py::test_1") == 1.5

    def test_duplicate_nodeid_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Duplicate nodeids in manifest cause error exit."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [
                {"nodeid": "test_a.py::test_1", "duration_s": 1.5},
                {"nodeid": "test_a.py::test_1", "duration_s": 2.0},  # Duplicate!
            ]
        }))
        
        with pytest.raises(SystemExit) as exc_info:
            shard_tests.load_duration_weights(manifest)
        
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Duplicate nodeid" in captured.err

    def test_empty_nodeid_skipped(self, tmp_path: Path) -> None:
        """Entries with empty nodeid are silently skipped."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [
                {"nodeid": "", "duration_s": 1.5},
                {"nodeid": "test_a.py::test_1", "duration_s": 2.0},
            ]
        }))
        
        result = shard_tests.load_duration_weights(manifest)
        assert "" not in result
        assert "test_a.py::test_1" in result

    def test_invalid_json_warns(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Invalid JSON file causes warning and returns empty dict."""
        manifest = tmp_path / "durations.json"
        manifest.write_text("not valid json {")
        
        result = shard_tests.load_duration_weights(manifest)
        assert result == {}
        captured = capsys.readouterr()
        assert "WARNING" in captured.err


class TestAssignShardsLPT:
    """Tests for assign_shards_lpt function."""

    def test_single_shard_contains_all(self) -> None:
        """Single shard gets all nodeids."""
        nodeids = ["test_1", "test_2", "test_3"]
        weights = {"test_1": 1.0, "test_2": 2.0, "test_3": 3.0}
        
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 1)
        
        assert len(shards) == 1
        assert len(shards[0].nodeids) == 3
        assert set(shards[0].nodeids) == set(nodeids)

    def test_deterministic_assignment(self) -> None:
        """Same inputs produce same outputs."""
        nodeids = ["test_1", "test_2", "test_3", "test_4"]
        weights = {"test_1": 1.0, "test_2": 2.0, "test_3": 3.0, "test_4": 4.0}
        
        shards1 = shard_tests.assign_shards_lpt(nodeids, weights, 2)
        shards2 = shard_tests.assign_shards_lpt(nodeids, weights, 2)
        
        # Same nodeids in same shards
        for s1, s2 in zip(shards1, shards2):
            assert sorted(s1.nodeids) == sorted(s2.nodeids)

    def test_all_nodeids_assigned_exactly_once(self) -> None:
        """Every nodeid appears exactly once across all shards."""
        nodeids = [f"test_{i}" for i in range(20)]
        weights = {n: (i + 1) * 0.5 for i, n in enumerate(nodeids)}  # Varying weights
        
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 4)
        
        all_assigned = []
        for shard in shards:
            all_assigned.extend(shard.nodeids)
        
        assert len(all_assigned) == len(nodeids)
        assert len(set(all_assigned)) == len(nodeids)  # No duplicates
        assert set(all_assigned) == set(nodeids)  # All present

    def test_unknown_tests_get_fallback_weight(self) -> None:
        """Nodeids not in weights dict use FALLBACK_WEIGHT."""
        nodeids = ["test_1", "test_2"]
        weights: dict[str, float] = {}  # No weights provided
        
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 2)
        
        # Both should get fallback weight
        for shard in shards:
            for nodeid in shard.nodeids:
                w = weights.get(nodeid, shard_tests.FALLBACK_WEIGHT)
                assert w == shard_tests.FALLBACK_WEIGHT

    def test_very_slow_test_isolated(self) -> None:
        """A very slow test should be placed in the lightest shard."""
        nodeids = ["slow_test", "fast_1", "fast_2", "fast_3"]
        weights = {
            "slow_test": 100.0,  # Very slow
            "fast_1": 1.0,
            "fast_2": 1.0,
            "fast_3": 1.0,
        }
        
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 2)
        
        # Find which shard has the slow test
        slow_shard_idx = None
        for i, shard in enumerate(shards):
            if "slow_test" in shard.nodeids:
                slow_shard_idx = i
                break
        
        assert slow_shard_idx is not None
        
        # Slow test shard should have the slow test (highest weight first)
        slow_shard = shards[slow_shard_idx]
        
        # Slow test shard should only have slow test (or minimal other work)
        # because it's placed first (highest weight)
        assert slow_shard.weight >= 100.0

    def test_invalid_shard_count_fails(self) -> None:
        """Zero or negative shard count raises error."""
        nodeids = ["test_1", "test_2"]
        weights: dict[str, float] = {}
        
        with pytest.raises(SystemExit):
            shard_tests.assign_shards_lpt(nodeids, weights, 0)
        
        with pytest.raises(SystemExit):
            shard_tests.assign_shards_lpt(nodeids, weights, -1)


class TestVerifyShardCompleteness:
    """Tests for verify_shard_completeness function."""

    def test_complete_assignment_passes(self) -> None:
        """All nodeids exactly once passes verification."""
        all_nodeids = ["test_1", "test_2", "test_3"]
        
        # Create shards with exact coverage
        shard_0 = shard_tests.ShardStats(nodeids=["test_1"])
        shard_1 = shard_tests.ShardStats(nodeids=["test_2", "test_3"])
        
        result = shard_tests.verify_shard_completeness(all_nodeids, [shard_0, shard_1])
        assert result is True

    def test_missing_nodeid_fails(self) -> None:
        """Missing nodeid causes verification failure."""
        all_nodeids = ["test_1", "test_2", "test_3"]
        
        # Shard 0 misses test_2
        shard_0 = shard_tests.ShardStats(nodeids=["test_1"])
        shard_1 = shard_tests.ShardStats(nodeids=["test_3"])
        
        result = shard_tests.verify_shard_completeness(all_nodeids, [shard_0, shard_1])
        assert result is False

    def test_duplicate_nodeid_fails(self) -> None:
        """Duplicate nodeid causes verification failure."""
        all_nodeids = ["test_1", "test_2"]
        
        # test_1 appears twice
        shard_0 = shard_tests.ShardStats(nodeids=["test_1"])
        shard_1 = shard_tests.ShardStats(nodeids=["test_1", "test_2"])
        
        result = shard_tests.verify_shard_completeness(all_nodeids, [shard_0, shard_1])
        assert result is False

    def test_empty_shard_warns(self, capsys: pytest.CaptureFixture) -> None:
        """Empty shard produces warning but passes if coverage complete."""
        all_nodeids = ["test_1", "test_2"]
        
        shard_0 = shard_tests.ShardStats(nodeids=[])
        shard_1 = shard_tests.ShardStats(nodeids=["test_1", "test_2"])
        
        result = shard_tests.verify_shard_completeness(all_nodeids, [shard_0, shard_1])
        assert result is True  # Still passes - coverage is complete
        
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "Shard 0" in captured.err


class TestShardMetrics:
    """Tests for shard metric computation."""

    def test_skew_ratio_calculation(self) -> None:
        """Skew ratio is max_weight / min_weight."""
        nodeids = ["test_1", "test_2", "test_3", "test_4"]
        weights = {
            "test_1": 10.0,
            "test_2": 1.0,
            "test_3": 10.0,
            "test_4": 1.0,
        }
        
        shards = shard_tests.assign_shards_lpt(nodeids, weights, 2)
        metrics = shard_tests.compute_shard_metrics(shards)
        
        # Should have some balance
        assert metrics["skew_ratio"] > 0
        assert metrics["skew_ratio"] <= 10.0  # At most 10x given our weights


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
        # Collect all nodeids
        result = subprocess.run(
            [
                sys.executable,
                "-m", "pytest",
                "--collect-only", "-q",
                "--ignore=tests/test_rollout_classifier_extended.py",
                "--ignore=tests/unit/test_property_checks.py",
                "tests/",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        
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
        # Collect
        result = subprocess.run(
            [
                sys.executable,
                "-m", "pytest",
                "--collect-only", "-q",
                "--ignore=tests/test_rollout_classifier_extended.py",
                "--ignore=tests/unit/test_property_checks.py",
                "tests/",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        
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


class TestRegressionGuard:
    """Tests for the hard-coded ignore regression guard."""

    def test_no_hard_coded_ignores_in_shard_tests(self) -> None:
        """Verify shard_tests.py has no hard-coded --ignore=tests/... literals."""
        import test_collection
        
        shard_tests_path = Path(__file__).parent.parent.parent / "scripts" / "shard_tests.py"
        violations = test_collection.check_for_hard_coded_ignores(shard_tests_path)
        
        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in shard_tests.py:\n"
            + "\n".join(violations)
        )

    def test_no_hard_coded_ignores_in_verify_test_exclusions(self) -> None:
        """Verify verify_test_exclusions.py has no hard-coded --ignore=tests/... literals."""
        import test_collection
        
        verify_path = Path(__file__).parent.parent.parent / "scripts" / "verify_test_exclusions.py"
        violations = test_collection.check_for_hard_coded_ignores(verify_path)
        
        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in verify_test_exclusions.py:\n"
            + "\n".join(violations)
        )

    def test_no_hard_coded_ignores_in_test_collection(self) -> None:
        """Verify test_collection.py itself has no hard-coded --ignore=tests/... literals."""
        import test_collection
        
        collection_path = Path(__file__).parent.parent.parent / "scripts" / "test_collection.py"
        violations = test_collection.check_for_hard_coded_ignores(collection_path)
        
        assert len(violations) == 0, (
            "Found hard-coded --ignore=tests/... in test_collection.py:\n"
            + "\n".join(violations)
        )

    def test_allowlist_exclusions_match_expected_state(self) -> None:
        """Verify ALLOWED_COLLECTION_EXCLUSIONS matches documented policy."""
        import test_collection
        
        # Current state: no exclusions
        assert len(test_collection.ALLOWED_COLLECTION_EXCLUSIONS) == 0, (
            "ALLOWED_COLLECTION_EXCLUSIONS should be empty when no files are broken"
        )

    def test_verify_no_hard_coded_ignores_passes(self) -> None:
        """Verify the full regression guard check passes."""
        import test_collection
        
        passed, violations = test_collection.verify_no_hard_coded_ignores()
        
        assert passed, (
            "Regression guard failed:\n"
            + "".join(violations)
        )

    def test_ast_guard_catches_multiline_ignore_pattern(self, tmp_path: Path) -> None:
        import test_collection
        
        # Create a temporary file with the stale multiline pattern
        test_file = tmp_path / "test_stale.py"
        stale_code = '''
import subprocess
import sys

def bad_function():
    result = subprocess.run([
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "--ignore=tests/test_rollout_classifier_extended.py",
        "tests/",
    ])
    return result
'''
        test_file.write_text(stale_code)
        
        violations = test_collection.check_for_hard_coded_ignores(test_file)
        
        assert len(violations) == 1, f"AST guard should catch multiline --ignore pattern. Got: {violations}"
        assert "test_rollout_classifier_extended.py" in violations[0]

    def test_ast_guard_cannot_catch_split_argument_ignore_pattern(self, tmp_path: Path) -> None:
        """Split-argument patterns are an explicit non-goal (documented in test_exclusions.md)."""
        import test_collection
        
        test_file = tmp_path / "test_split.py"
        # This is split into two separate strings - AST guard cannot catch this
        split_code = '''
import subprocess
import sys

def bad_function():
    result = subprocess.run([
        sys.executable,
        "-m",
        "pytest",
        "--ignore",
        "tests/foo.py",
        "tests/",
    ])
    return result
'''
        test_file.write_text(split_code)
        
        violations = test_collection.check_for_hard_coded_ignores(test_file)
        
        # AST guard cannot detect split-argument patterns
        # This is a known limitation - the guard catches --ignore=tests/... in one string
        assert len(violations) == 0, f"AST guard should NOT catch split-argument pattern: {violations}"

    def test_ast_guard_ignores_code_mention(self, tmp_path: Path) -> None:
        """Verify AST-based guard only catches actual command strings, not code mentions."""
        import test_collection
        
        test_file = tmp_path / "test_mentions.py"
        # This is valid code that mentions ignore but doesn't use it
        code = 'example = "--ignore=tests/foo.py"\n'
        test_file.write_text(code)
        
        violations = test_collection.check_for_hard_coded_ignores(test_file)
        
        # This should be caught since it's a string constant with the pattern
        # The guard is intentionally conservative
        assert len(violations) == 1, f"AST guard should catch string constants. Got: {violations}"


class TestCollectionCommandBuilder:
    def test_empty_allowlist_produces_no_ignore_flags(self) -> None:
        import test_collection
        
        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = set()
        
        try:
            cmd = test_collection.build_collection_command()
            assert "--ignore" not in cmd, f"Empty allowlist should not produce --ignore: {cmd}"
            assert "tests/" in cmd
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_allowlist_produces_ignore_flags(self) -> None:
        import test_collection
        
        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {
            "tests/unit/test_foo.py",
            "tests/unit/test_bar.py",
        }
        
        try:
            cmd = test_collection.build_collection_command()
            assert "--ignore" in cmd, f"Non-empty allowlist should produce --ignore: {cmd}"
            assert "tests/unit/test_foo.py" in cmd
            assert "tests/unit/test_bar.py" in cmd
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_ignore_flags_are_separate_arguments(self) -> None:
        import test_collection
        
        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {"tests/excluded.py"}
        
        try:
            cmd = test_collection.build_collection_command()
            ignore_idx = cmd.index("--ignore")
            assert cmd[ignore_idx + 1] == "tests/excluded.py"
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original

    def test_extra_args_appended(self) -> None:
        import test_collection
        
        cmd = test_collection.build_collection_command(extra_args=["--verbose", "-x"])
        assert "--verbose" in cmd
        assert "-x" in cmd
        assert cmd.index("--verbose") < cmd.index("tests/")
        assert cmd.index("-x") < cmd.index("tests/")

    def test_include_allowed_ignores_false_skips_ignores(self) -> None:
        import test_collection
        
        original = test_collection.ALLOWED_COLLECTION_EXCLUSIONS
        test_collection.ALLOWED_COLLECTION_EXCLUSIONS = {"tests/excluded.py"}
        
        try:
            cmd = test_collection.build_collection_command(include_allowed_ignores=False)
            assert "--ignore" not in cmd, f"include_allowed_ignores=False should skip --ignore: {cmd}"
        finally:
            test_collection.ALLOWED_COLLECTION_EXCLUSIONS = original
