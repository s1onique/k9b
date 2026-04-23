"""Tests for shared artifact write helpers."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.identity.artifact import write_append_only_json_artifact


class TestWriteAppendOnlyJsonArtifact(unittest.TestCase):
    """Tests for write_append_only_json_artifact function."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_creates_parent_directories(self) -> None:
        """Test that write_append_only_json_artifact creates parent directories."""
        nested_path = self.tmpdir / "nested" / "deep" / "path" / "artifact.json"
        data = {"key": "value"}

        result = write_append_only_json_artifact(nested_path, data)

        self.assertTrue(result.exists())
        self.assertTrue(nested_path.parent.exists())

    def test_write_produces_valid_json(self) -> None:
        """Test that written file contains valid JSON."""
        path = self.tmpdir / "artifact.json"
        data = {"key": "value", "nested": {"inner": 42}}

        write_append_only_json_artifact(path, data)

        content = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(content["key"], "value")
        self.assertEqual(content["nested"]["inner"], 42)

    def test_write_with_indent(self) -> None:
        """Test that JSON is written with indent=2 formatting."""
        path = self.tmpdir / "artifact.json"
        data = {"key": "value"}

        write_append_only_json_artifact(path, data)

        content = path.read_text(encoding="utf-8")
        # Check that the file contains newlines and indentation
        self.assertIn("\n", content)

    def test_write_rejects_overwrite(self) -> None:
        """Test that attempting to write to an existing path raises FileExistsError."""
        path = self.tmpdir / "artifact.json"
        # Pre-create the file
        path.write_text("existing content", encoding="utf-8")
        data = {"key": "value"}

        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(path, data)

        self.assertIn("immutability contract violated", str(ctx.exception))

    def test_write_reject_overwrite_includes_context(self) -> None:
        """Test that FileExistsError includes context message when provided."""
        path = self.tmpdir / "artifact.json"
        # Pre-create the file
        path.write_text("existing content", encoding="utf-8")
        data = {"key": "value"}
        context = "run_id=test-run, cluster=prod"

        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(path, data, context=context)

        error_msg = str(ctx.exception)
        self.assertIn("immutability contract violated", error_msg)
        self.assertIn("run_id=test-run", error_msg)
        self.assertIn("cluster=prod", error_msg)

    def test_write_reject_overwrite_without_context(self) -> None:
        """Test that FileExistsError includes path without context."""
        path = self.tmpdir / "artifact.json"
        path.write_text("existing content", encoding="utf-8")
        data = {"key": "value"}

        with self.assertRaises(FileExistsError) as ctx:
            write_append_only_json_artifact(path, data)

        error_msg = str(ctx.exception)
        self.assertIn("immutability contract violated", error_msg)
        self.assertIn(str(path), error_msg)

    def test_write_with_mapping_subclass(self) -> None:
        """Test that the helper accepts Mapping subclasses (like to_dict results)."""
        path = self.tmpdir / "artifact.json"
        data = {"key": "value"}

        write_append_only_json_artifact(path, data)

        self.assertTrue(path.exists())

    def test_roundtrip_preserves_data(self) -> None:
        """Test that data survives write -> read roundtrip."""
        path = self.tmpdir / "artifact.json"
        original = {
            "tool_name": "test-tool",
            "run_id": "run-123",
            "status": "success",
            "nested": {"key": ["list", "items"]},
        }

        write_append_only_json_artifact(path, original)
        restored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(restored, original)


if __name__ == "__main__":
    unittest.main()
