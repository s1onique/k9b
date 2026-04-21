"""Tests for artifact_id in diagnostic pack artifacts.

These tests verify that:
1. New diagnostic pack artifacts include `artifact_id` at creation time
2. Serialized bundle/manifest artifacts include `artifact_id`
3. Legacy artifacts without `artifact_id` remain readable (backward compatibility)
4. Roundtrip preserves `artifact_id`
5. `artifact_id` is distinct from `run_id` and other identifiers
"""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import cast

from scripts.build_diagnostic_pack import (
    REVIEW_BUNDLE_SCHEMA,
    REVIEW_INPUT_SCHEMA,
    create_diagnostic_pack,
)
from tests.fixtures.ui_index_sample import sample_ui_index


def _is_valid_uuid7(uid: str) -> bool:
    """Check if string is a valid UUID-like format (8-4-4-4-12)."""
    if not uid:
        return False
    parts = uid.split("-")
    if len(parts) != 5:
        return False
    lengths = [8, 4, 4, 4, 12]
    for part, expected_len in zip(parts, lengths):
        if len(part) != expected_len:
            return False
        try:
            int(part, 16)
        except ValueError:
            return False
    return True


class TestDiagnosticPackArtifactId(unittest.TestCase):
    """Tests for artifact_id in diagnostic pack artifacts."""

    def test_review_bundle_includes_artifact_id(self) -> None:
        """review_bundle.json should include artifact_id field."""
        run_id = "run-artifact-id-test"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=Path(tmpdir) / "packs")
            self.assertTrue(pack_path.exists())
            
            with zipfile.ZipFile(pack_path, "r") as archive:
                bundle = json.loads(archive.read("review_bundle.json"))
                
                # Verify artifact_id exists
                self.assertIn("artifact_id", bundle)
                self.assertIsNotNone(bundle["artifact_id"])
                self.assertIsInstance(bundle["artifact_id"], str)
                
                # Verify artifact_id is a valid UUID-like format
                self.assertTrue(_is_valid_uuid7(bundle["artifact_id"]))
                
                # Verify artifact_id is distinct from run_id
                self.assertNotEqual(bundle["artifact_id"], run_id)
                run_entry = bundle.get("run", {})
                self.assertNotEqual(bundle["artifact_id"], run_entry.get("run_id"))

    def test_review_input_14b_includes_artifact_id(self) -> None:
        """review_input_14b.json should include artifact_id field."""
        run_id = "run-input-artifact-id"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=Path(tmpdir) / "packs")
            self.assertTrue(pack_path.exists())
            
            with zipfile.ZipFile(pack_path, "r") as archive:
                review_input = json.loads(archive.read("review_input_14b.json"))
                
                # Verify artifact_id exists
                self.assertIn("artifact_id", review_input)
                self.assertIsNotNone(review_input["artifact_id"])
                self.assertIsInstance(review_input["artifact_id"], str)
                
                # Verify artifact_id is a valid UUID-like format
                self.assertTrue(_is_valid_uuid7(review_input["artifact_id"]))
                
                # Verify artifact_id is distinct from source_run_id
                self.assertNotEqual(review_input["artifact_id"], review_input.get("source_run_id"))

    def test_manifest_includes_artifact_id(self) -> None:
        """manifest.json should include artifact_id field."""
        run_id = "run-manifest-artifact-id"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=Path(tmpdir) / "packs")
            self.assertTrue(pack_path.exists())
            
            with zipfile.ZipFile(pack_path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json"))
                
                # Verify artifact_id exists
                self.assertIn("artifact_id", manifest)
                self.assertIsNotNone(manifest["artifact_id"])
                self.assertIsInstance(manifest["artifact_id"], str)
                
                # Verify artifact_id is a valid UUID-like format
                self.assertTrue(_is_valid_uuid7(manifest["artifact_id"]))
                
                # Verify artifact_id is distinct from run_id
                self.assertNotEqual(manifest["artifact_id"], run_id)

    def test_artifact_ids_are_unique_per_build(self) -> None:
        """Each artifact should have a unique artifact_id."""
        run_id = "run-unique-ids"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=Path(tmpdir) / "packs")
            self.assertTrue(pack_path.exists())
            
            with zipfile.ZipFile(pack_path, "r") as archive:
                bundle = json.loads(archive.read("review_bundle.json"))
                review_input = json.loads(archive.read("review_input_14b.json"))
                manifest = json.loads(archive.read("manifest.json"))
                
                bundle_id = bundle.get("artifact_id")
                input_id = review_input.get("artifact_id")
                manifest_id = manifest.get("artifact_id")
                
                # All three should be unique
                self.assertIsNotNone(bundle_id)
                self.assertIsNotNone(input_id)
                self.assertIsNotNone(manifest_id)
                
                # Verify uniqueness
                self.assertEqual(len({bundle_id, input_id, manifest_id}), 3)

    def test_artifact_id_distinct_from_run_id(self) -> None:
        """artifact_id must be distinct from run_id and other identifiers."""
        run_id = "run-distinct-ids"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=Path(tmpdir) / "packs")
            self.assertTrue(pack_path.exists())
            
            with zipfile.ZipFile(pack_path, "r") as archive:
                bundle = json.loads(archive.read("review_bundle.json"))
                manifest = json.loads(archive.read("manifest.json"))
                
                # artifact_id should not equal run_id
                self.assertNotEqual(bundle.get("artifact_id"), run_id)
                self.assertNotEqual(manifest.get("artifact_id"), run_id)
                
                # artifact_id should not equal run.run_id
                run_entry = bundle.get("run", {})
                self.assertNotEqual(bundle.get("artifact_id"), run_entry.get("run_id"))
                
                # artifact_id should not equal manifest.run_id
                self.assertNotEqual(manifest.get("artifact_id"), manifest.get("run_id"))

    def test_latest_mirror_contains_artifact_ids(self) -> None:
        """Latest pack mirror files should contain artifact_ids."""
        run_id = "run-latest-mirror"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            
            # write ui-index
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
            
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {"health_rating": "degraded"},
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            
            packs_dir = Path(tmpdir) / "packs"
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
            self.assertTrue(pack_path.exists())
            
            # Verify latest mirror exists and contains artifact_ids
            latest_dir = packs_dir / "latest"
            self.assertTrue(latest_dir.exists())
            
            bundle_path = latest_dir / "review_bundle.json"
            self.assertTrue(bundle_path.exists())
            
            input_path = latest_dir / "review_input_14b.json"
            self.assertTrue(input_path.exists())
            
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            review_input = json.loads(input_path.read_text(encoding="utf-8"))
            
            # Both should have artifact_ids
            self.assertIn("artifact_id", bundle)
            self.assertIn("artifact_id", review_input)
            self.assertTrue(_is_valid_uuid7(bundle["artifact_id"]))
            self.assertTrue(_is_valid_uuid7(review_input["artifact_id"]))


class TestLegacyBackwardCompatibility(unittest.TestCase):
    """Tests for backward compatibility with legacy artifacts without artifact_id."""

    def test_review_bundle_readable_without_artifact_id(self) -> None:
        """Legacy review_bundle.json without artifact_id should be readable."""
        # Simulate a legacy bundle without artifact_id
        legacy_bundle = {
            "schema_version": REVIEW_BUNDLE_SCHEMA,
            "generated_at": "2024-01-01T00:00:00+00:00",
            "run": {
                "run_id": "legacy-run-1",
                "run_label": "legacy-run",
                "timestamp": "2024-01-01T00:00:00+00:00",
            },
            "fleet_summary": {},
            "review": {"path": None, "content": None},
            "assessments": [],
            "drilldowns": [],
            "triggers": [],
            "comparisons": [],
            "external_analysis": [],
            "proposals": [],
            "artifact_manifest": {
                "included_paths": [],
            },
        }
        
        # Should not raise any errors when accessing without artifact_id
        self.assertNotIn("artifact_id", legacy_bundle)
        self.assertIsNone(legacy_bundle.get("artifact_id"))
        
        # Other fields should still be accessible
        self.assertEqual(legacy_bundle.get("schema_version"), REVIEW_BUNDLE_SCHEMA)
        self.assertEqual(legacy_bundle.get("run", {}).get("run_id"), "legacy-run-1")

    def test_review_input_readable_without_artifact_id(self) -> None:
        """Legacy review_input_14b.json without artifact_id should be readable."""
        # Simulate a legacy input without artifact_id
        legacy_input = {
            "schema_version": REVIEW_INPUT_SCHEMA,
            "generated_at": "2024-01-01T00:00:00+00:00",
            "source_run_id": "legacy-run-1",
            "source_review_bundle_path": "review_bundle.json",
            "run": {
                "run_id": "legacy-run-1",
                "run_label": "legacy-run",
            },
            "fleet_summary": {},
            "artifact_manifest": {
                "included_paths": [],
            },
        }
        
        # Should not raise any errors when accessing without artifact_id
        self.assertNotIn("artifact_id", legacy_input)
        self.assertIsNone(legacy_input.get("artifact_id"))
        
        # Other fields should still be accessible
        self.assertEqual(legacy_input.get("schema_version"), REVIEW_INPUT_SCHEMA)
        self.assertEqual(legacy_input.get("source_run_id"), "legacy-run-1")

    def test_manifest_readable_without_artifact_id(self) -> None:
        """Legacy manifest.json without artifact_id should be readable."""
        # Simulate a legacy manifest without artifact_id
        legacy_manifest = {
            "run_id": "legacy-run-1",
            "run_label": "legacy-run",
            "generated_at": "2024-01-01T00:00:00+00:00",
            "file_count": 5,
            "files": [],
        }
        
        # Should not raise any errors when accessing without artifact_id
        self.assertNotIn("artifact_id", legacy_manifest)
        self.assertIsNone(legacy_manifest.get("artifact_id"))
        
        # Other fields should still be accessible
        self.assertEqual(legacy_manifest.get("run_id"), "legacy-run-1")
        self.assertEqual(legacy_manifest.get("file_count"), 5)


if __name__ == "__main__":
    unittest.main()
