"""Regression tests for top-level JSON array handling in the sanitizer.

These tests verify that the sanitizer can handle JSON files whose root
is an array (list), not just a mapping (dict). Previously, the sanitizer
assumed all JSON roots were dicts and called .items() on them, causing
AttributeError when processing array roots.

This file is intentionally kept under 500 lines to comply with llm-friendly checks.
"""

import json
import subprocess
import sys
from pathlib import Path

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"


class TestSanitizerTopLevelJSONArrays:
    """Regression tests for top-level JSON array handling.

    These tests verify that the sanitizer can handle JSON files whose root
    is an array (list), not just a mapping (dict). Previously, the sanitizer
    assumed all JSON roots were dicts and called .items() on them, causing
    AttributeError when processing array roots.
    """

    def test_sanitizer_handles_top_level_json_array_of_dicts(self, tmp_path: Path) -> None:
        """Top-level JSON array of incident-like dicts should sanitize successfully."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create k9b-incidents.json with top-level array (the original failing case)
        (input_dir / "k9b-incidents.json").write_text(json.dumps([
            {"id": "inc-1", "title": "Pod NotReady", "status": "open", "cluster": "prod"},
            {"id": "inc-2", "title": "PVC Pending", "status": "closed", "cluster": "dev"},
        ]))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        output = json.loads((output_dir / "k9b-incidents.json").read_text())
        assert isinstance(output, list)
        assert len(output) == 2
        assert output[0]["id"] == "inc-1"
        assert output[0]["title"] == "Pod NotReady"
        assert output[1]["id"] == "inc-2"

    def test_sanitizer_handles_symptom_snapshots_array(self, tmp_path: Path) -> None:
        """Top-level JSON array of symptom snapshots should sanitize successfully."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create pod-failure-symptom-snapshots.json with top-level array (the original failing case)
        (input_dir / "pod-failure-symptom-snapshots.json").write_text(json.dumps([
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "event": "PodNotReady",
                "namespace": "default",
                "pod": "test-pod-abc123",
            },
            {
                "timestamp": "2026-01-01T00:01:00Z",
                "event": "ContainerRestart",
                "namespace": "default",
                "pod": "test-pod-abc123",
            },
        ]))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        output = json.loads((output_dir / "pod-failure-symptom-snapshots.json").read_text())
        assert isinstance(output, list)
        assert len(output) == 2
        assert output[0]["event"] == "PodNotReady"
        assert output[1]["event"] == "ContainerRestart"

    def test_sanitizer_redacts_secret_inside_top_level_json_array(self, tmp_path: Path) -> None:
        """Secrets inside a top-level JSON array should be detected and redacted as FATAL."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # Create snapshots.json with top-level array containing a JWT token
        # Note: JWT pattern in _FATAL_PATTERNS matches "eyJ...eyJ..." format
        (input_dir / "snapshots.json").write_text(json.dumps([
            {"event": "safe"},
            {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"},
        ]))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        # Should fail due to fatal finding (JWT pattern detected)
        assert result.returncode == 1, f"Sanitizer should have failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert "FATAL" in result.stdout or "credential pattern" in result.stdout.lower()

        # Output should contain redacted value
        output = (output_dir / "snapshots.json").read_text()
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in output, "JWT token leaked into output!"
        assert "<REDACTED>" in output, "Token should be redacted"

    def test_sanitizer_handles_nested_array_in_object(self, tmp_path: Path) -> None:
        """Objects containing arrays (e.g., incident arrays) should sanitize correctly."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        # JSON with dict root containing arrays (existing behavior should still work)
        (input_dir / "cluster-status.json").write_text(json.dumps({
            "cluster": "prod",
            "incidents": [
                {"id": "inc-1", "title": "Pod crash"},
                {"id": "inc-2", "title": "Network timeout"},
            ],
            "resolved": [
                {"id": "inc-3", "title": "Earlier issue"},
            ],
        }))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        output = json.loads((output_dir / "cluster-status.json").read_text())
        assert output["cluster"] == "prod"
        assert len(output["incidents"]) == 2
        assert output["incidents"][0]["id"] == "inc-1"
        assert len(output["resolved"]) == 1

    def test_sanitizer_handles_mixed_array_contents(self, tmp_path: Path) -> None:
        """Arrays with mixed content (dicts, strings, numbers) should sanitize correctly."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "mixed.json").write_text(json.dumps([
            "plain string",
            12345,
            {"key": "value"},
            {"nested": {"deep": "data"}},
        ]))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        output = json.loads((output_dir / "mixed.json").read_text())
        assert output[0] == "plain string"
        assert output[1] == 12345
        assert output[2] == {"key": "value"}
        assert output[3] == {"nested": {"deep": "data"}}

    def test_sanitizer_handles_empty_array(self, tmp_path: Path) -> None:
        """Empty JSON arrays should not crash the sanitizer."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        (input_dir / "empty.json").write_text(json.dumps([]))

        result = subprocess.run(
            [sys.executable, str(SANITIZER_SCRIPT), "--input", str(input_dir), "--output", str(output_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Sanitizer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        output = json.loads((output_dir / "empty.json").read_text())
        assert output == []
