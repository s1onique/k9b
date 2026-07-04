"""Tests for update_python_test_durations.py timing manifest aggregation script."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import _duration_utils as updater


class TestClassnameToNodeid:
    """Tests for JUnit classname to pytest nodeid conversion."""

    def test_handles_dotted_classname_with_class(self) -> None:
        """Dotted classname with class converts correctly."""
        result = updater.classname_to_nodeid("tests.unit.test_foo.TestClass", "test_method")
        assert result == "tests/unit/test_foo.py::TestClass::test_method"

    def test_handles_dotted_classname_without_class(self) -> None:
        """Dotted classname without class converts correctly."""
        result = updater.classname_to_nodeid("tests.test_foo", "test_method")
        assert result == "tests/test_foo.py::test_method"

    def test_handles_path_format_classname(self) -> None:
        """Path-format classname with full nodeid avoids duplicate names."""
        # When classname already contains full nodeid, don't duplicate
        result = updater.classname_to_nodeid("tests/unit/test_foo.py::test_bar", "test_bar")
        assert result == "tests/unit/test_foo.py::test_bar"

    def test_handles_path_format_classname_no_match(self) -> None:
        """Path-format classname without matching name appends name."""
        result = updater.classname_to_nodeid("tests/unit/test_foo.py::SomeClass", "test_bar")
        assert result == "tests/unit/test_foo.py::SomeClass::test_bar"

    def test_handles_empty_classname(self) -> None:
        """Empty classname returns just the name."""
        result = updater.classname_to_nodeid("", "test_method")
        assert result == "test_method"


class TestFindJunitXmlFiles:
    """Tests for JUnit XML file discovery."""

    def test_finds_xml_file(self, tmp_path: Path) -> None:
        """Single XML file is returned."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<testsuite/>")

        result = updater.find_junit_xml_files([xml_file])
        assert result == [xml_file]

    def test_finds_xml_in_directory(self, tmp_path: Path) -> None:
        """XML files in directory are discovered recursively."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        xml1 = tmp_path / "file1.xml"
        xml2 = subdir / "file2.xml"
        xml1.write_text("<testsuite/>")
        xml2.write_text("<testsuite/>")

        result = updater.find_junit_xml_files([tmp_path])
        assert sorted(result) == [xml1, xml2]

    def test_skips_non_xml_files(self, tmp_path: Path) -> None:
        """Non-XML files in directory are skipped."""
        xml_file = tmp_path / "test.xml"
        txt_file = tmp_path / "readme.txt"
        xml_file.write_text("<testsuite/>")
        txt_file.write_text("not xml")

        result = updater.find_junit_xml_files([tmp_path])
        assert result == [xml_file]

    def test_returns_sorted_results(self, tmp_path: Path) -> None:
        """Results are returned in sorted order for determinism."""
        xml_c = tmp_path / "c.xml"
        xml_a = tmp_path / "a.xml"
        xml_b = tmp_path / "b.xml"
        xml_c.write_text("<testsuite/>")
        xml_a.write_text("<testsuite/>")
        xml_b.write_text("<testsuite/>")

        result = updater.find_junit_xml_files([tmp_path])
        assert result == [xml_a, xml_b, xml_c]


class TestParseJunitXml:
    """Tests for JUnit XML parsing."""

    def test_parses_basic_testcase(self, tmp_path: Path) -> None:
        """Basic testcase with classname and time is parsed correctly."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" failures="0" skipped="0" errors="0" time="1.5">
    <testcase classname="tests/unit/test_foo.py::test_bar" name="test_bar" time="0.5"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert len(result) == 1
        # classname already contains full nodeid, so name is not duplicated
        assert result[0] == ("tests/unit/test_foo.py::test_bar", 0.5)

    def test_parses_multiple_testcases(self, tmp_path: Path) -> None:
        """Multiple testcases are all parsed."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3">
    <testcase classname="tests/test_a.py" name="test_one" time="0.1"/>
    <testcase classname="tests/test_b.py" name="test_two" time="0.2"/>
    <testcase classname="tests/test_c.py::ClassName" name="test_three" time="0.3"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert len(result) == 3
        nodeids = [r[0] for r in result]
        assert "tests/test_a.py::test_one" in nodeids
        assert "tests/test_b.py::test_two" in nodeids
        assert "tests/test_c.py::ClassName::test_three" in nodeids

    def test_handles_missing_time_attribute(self, tmp_path: Path) -> None:
        """Testcase without time attribute gets 0.0 duration."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_foo.py" name="test_no_time"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert len(result) == 1
        assert result[0][0] == "tests/test_foo.py::test_no_time"
        assert result[0][1] == 0.0

    def test_handles_invalid_time_value(self, tmp_path: Path) -> None:
        """Invalid time value causes warning and test is skipped."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_foo.py" name="test_bad_time" time="not-a-number"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert result == []

    def test_handles_empty_name_with_classname(self, tmp_path: Path) -> None:
        """Testcase with empty name but with classname is included."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_foo.py" name="" time="0.5"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert len(result) == 1
        assert result[0][0] == "tests/test_foo.py::"
        assert result[0][1] == 0.5

    def test_handles_namespaced_xml(self, tmp_path: Path) -> None:
        """XML with namespace declarations is parsed correctly."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuite xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <testcase classname="tests/test_foo.py" name="test_namespaced" time="0.3"/>
</testsuite>"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        result = updater.parse_junit_xml(xml_file)
        assert len(result) == 1
        assert result[0][1] == 0.3

    def test_raises_parse_error_for_malformed_xml(self, tmp_path: Path) -> None:
        """Malformed XML raises ParseError."""
        xml_file = tmp_path / "bad.xml"
        xml_file.write_text("<testsuite><unclosed>")

        with pytest.raises(ET.ParseError):
            updater.parse_junit_xml(xml_file)


class TestAggregateDurations:
    """Tests for duration aggregation."""

    def test_max_aggregation(self) -> None:
        """Max aggregation picks the highest duration for duplicates."""
        durations = [
            ("tests/test_foo.py::test_bar", 0.5),
            ("tests/test_foo.py::test_bar", 0.8),
            ("tests/test_foo.py::test_baz", 0.3),
        ]

        result = updater.aggregate_durations(durations, "max")
        assert len(result) == 2

        by_nodeid = {r["nodeid"]: r["duration_s"] for r in result}
        assert by_nodeid["tests/test_foo.py::test_bar"] == 0.8
        assert by_nodeid["tests/test_foo.py::test_baz"] == 0.3

    def test_avg_aggregation(self) -> None:
        """Avg aggregation computes mean duration for duplicates."""
        durations = [
            ("tests/test_foo.py::test_bar", 0.5),
            ("tests/test_foo.py::test_bar", 0.7),
            ("tests/test_foo.py::test_bar", 0.9),
        ]

        result = updater.aggregate_durations(durations, "avg")
        assert len(result) == 1
        assert result[0]["nodeid"] == "tests/test_foo.py::test_bar"
        assert result[0]["duration_s"] == pytest.approx(0.7)

    def test_output_sorted_by_nodeid(self) -> None:
        """Output is sorted by nodeid for determinism."""
        durations = [
            ("tests/test_z.py::test_z", 0.3),
            ("tests/test_a.py::test_a", 0.1),
            ("tests/test_m.py::test_m", 0.2),
        ]

        result = updater.aggregate_durations(durations)
        nodeids = [r["nodeid"] for r in result]
        assert nodeids == sorted(nodeids)

    def test_empty_input_returns_empty(self) -> None:
        """Empty input produces empty output."""
        result = updater.aggregate_durations([])
        assert result == []


class TestBootstrapManifestDetection:
    """Tests for bootstrap placeholder detection."""

    def test_detects_bootstrap_manifest(self, tmp_path: Path) -> None:
        """Bootstrap placeholder manifests are detected."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "version": 1,
            "description": "Bootstrap duration manifest",
            "durations": [],
        }))

        assert updater.is_bootstrap_manifest(manifest) is True

    def test_detects_bootstrap_in_note(self, tmp_path: Path) -> None:
        """Bootstrap placeholder in 'note' field is detected."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "version": 1,
            "description": "Real data",
            "note": "Bootstrap duration manifest placeholder",
            "durations": [],
        }))

        assert updater.is_bootstrap_manifest(manifest) is True

    def test_real_manifest_not_flagged(self, tmp_path: Path) -> None:
        """Manifests with actual durations are not flagged."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "version": 1,
            "description": "Real test data",
            "durations": [{"nodeid": "tests/test_foo.py::test_bar", "duration_s": 0.5}],
        }))

        assert updater.is_bootstrap_manifest(manifest) is False

    def test_nonexistent_file_returns_false(self) -> None:
        """Non-existent file returns False."""
        assert updater.is_bootstrap_manifest(Path("/nonexistent.json")) is False

    def test_invalid_json_returns_false(self, tmp_path: Path) -> None:
        """Invalid JSON returns False."""
        manifest = tmp_path / "bad.json"
        manifest.write_text("not json {")

        assert updater.is_bootstrap_manifest(manifest) is False


class TestComputeShardBalance:
    """Tests for shard balance computation."""

    def test_balances_simple_workload(self) -> None:
        """Equal weights are balanced evenly."""
        durations = {"test_1": 1.0, "test_2": 1.0, "test_3": 1.0, "test_4": 1.0}
        metrics = updater.compute_shard_balance(durations, 2)
        assert metrics["num_shards"] == 2
        assert metrics["total_tests"] == 4
        assert metrics["shard_weights"] == [2.0, 2.0]
        assert metrics["skew_ratio"] == 1.0

    def test_places_heavy_tests_first(self) -> None:
        """Heavy tests are placed to minimize skew."""
        durations = {"slow": 10.0, "fast_1": 1.0, "fast_2": 1.0}
        metrics = updater.compute_shard_balance(durations, 2)
        weights = metrics["shard_weights"]
        assert max(weights) == 10.0
        assert min(weights) == 2.0

    def test_handles_empty_durations(self) -> None:
        """Empty durations dict is handled gracefully."""
        metrics = updater.compute_shard_balance({}, 2)
        assert metrics["total_tests"] == 0
        assert metrics["skew_ratio"] == float("inf")

    def test_skew_ratio_calculation(self) -> None:
        """Skew ratio is correctly computed."""
        durations = {"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0}
        metrics = updater.compute_shard_balance(durations, 2)
        assert metrics["skew_ratio"] == 1.0


class TestLoadExistingDurations:
    """Tests for loading existing manifests."""

    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        """Valid manifest is loaded correctly."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [{"nodeid": "test_a", "duration_s": 1.5}, {"nodeid": "test_b", "duration_s": 2.0}]
        }))
        result = updater.load_existing_durations(manifest)
        assert result == {"test_a": 1.5, "test_b": 2.0}

    def test_handles_missing_file(self) -> None:
        """Missing file returns empty dict."""
        result = updater.load_existing_durations(Path("/missing.json"))
        assert result == {}

    def test_skips_entries_without_required_fields(self, tmp_path: Path) -> None:
        """Entries missing nodeid or duration_s are skipped."""
        manifest = tmp_path / "durations.json"
        manifest.write_text(json.dumps({
            "durations": [
                {"nodeid": "test_a", "duration_s": 1.5},
                {"nodeid": "test_b"},
                {"duration_s": 2.0},
            ]
        }))
        result = updater.load_existing_durations(manifest)
        assert result == {"test_a": 1.5}


class TestCheckBalanceThreshold:
    """Tests for balance threshold checking."""

    def test_passes_within_threshold(self) -> None:
        """Balance check passes when skew is within threshold."""
        metrics = {"skew_ratio": 1.5}
        passes, message = updater.check_balance_threshold(metrics, 2.0)
        assert passes is True
        assert "OK" in message

    def test_fails_outside_threshold(self) -> None:
        """Balance check fails when skew exceeds threshold."""
        metrics = {"skew_ratio": 3.0}
        passes, message = updater.check_balance_threshold(metrics, 2.0)
        assert passes is False
        assert "Poor" in message


class TestIntegration:
    """Integration tests for end-to-end scenarios."""

    def test_full_update_workflow(self, tmp_path: Path) -> None:
        """Full workflow: parse XML, aggregate, write manifest."""
        import update_python_test_durations as updater_main
        xml_file = tmp_path / "junit" / "test.xml"
        xml_file.parent.mkdir()
        xml_file.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_a.py" name="test_one" time="0.5"/>
    <testcase classname="tests/test_b.py" name="test_two" time="1.5"/>
</testsuite>""")
        output_file = tmp_path / "durations.json"
        xml_files = updater.find_junit_xml_files([xml_file.parent])
        all_durations = [d for xml_f in xml_files for d in updater.parse_junit_xml(xml_f)]
        aggregated = updater.aggregate_durations(all_durations, "max")
        updater_main.write_manifest(output_file, xml_files, aggregated)
        with open(output_file) as f:
            data = json.load(f)
        assert data["test_count"] == 2
        assert len(data["durations"]) == 2

    def test_duplicate_aggregation_from_multiple_shards(self, tmp_path: Path) -> None:
        """Duplicates from multiple shard files are aggregated correctly."""
        shard1 = tmp_path / "shard1.xml"
        shard2 = tmp_path / "shard2.xml"
        shard1.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_shared.py" name="test_common" time="0.5"/>
    <testcase classname="tests/test_a.py" name="test_a" time="1.0"/>
</testsuite>""")
        shard2.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite>
    <testcase classname="tests/test_shared.py" name="test_common" time="0.7"/>
    <testcase classname="tests/test_b.py" name="test_b" time="2.0"/>
</testsuite>""")
        all_durations = [d for xml_file in [shard1, shard2] for d in updater.parse_junit_xml(xml_file)]
        aggregated = updater.aggregate_durations(all_durations, "max")
        assert len(aggregated) == 3
        test_common = next((r for r in aggregated if r["nodeid"] == "tests/test_shared.py::test_common"), None)
        assert test_common is not None
        assert test_common["duration_s"] == 0.7

    def test_compatibility_with_shard_tests_reader(self, tmp_path: Path) -> None:
        """Output is compatible with shard_tests.py duration reader."""
        manifest_file = tmp_path / "durations.json"
        manifest_file.write_text(json.dumps({
            "version": 1,
            "description": "Test manifest",
            "durations": [
                {"nodeid": "tests/test_a.py::test_foo", "duration_s": 1.5},
                {"nodeid": "tests/test_b.py::test_bar", "duration_s": 2.0},
            ]
        }))
        durations = updater.load_existing_durations(manifest_file)
        assert "tests/test_a.py::test_foo" in durations
        assert durations["tests/test_a.py::test_foo"] == 1.5
