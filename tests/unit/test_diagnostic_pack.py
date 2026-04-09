import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import cast

from scripts.build_diagnostic_pack import create_diagnostic_pack
from tests.fixtures.ui_index_sample import sample_ui_index


class DiagnosticPackBuilderTests(unittest.TestCase):
    def test_build_diagnostic_pack_includes_expected_artifacts(self) -> None:
        run_id = "run-1"
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
            # write artifacts per category
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "triggers" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "comparisons" / f"{run_id}-cluster-a-vs-cluster-b-comparison.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "reviews" / f"{run_id}-review.json").write_text(
                json.dumps({"rating": "ok"}), encoding="utf-8"
            )
            (health_dir / "external-analysis" / f"{run_id}-review-enrichment.json").write_text(
                "{}", encoding="utf-8"
            )
            (health_dir / "external-analysis" / f"{run_id}-next-check-plan.json").write_text(
                "{}", encoding="utf-8"
            )
            packs_dir = Path(tmpdir) / "packs"
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
            self.assertTrue(pack_path.exists())
            with zipfile.ZipFile(pack_path, "r") as archive:
                names = set(archive.namelist())
                self.assertIn("ui-index.json", names)
                self.assertIn("summary.md", names)
                self.assertIn("analyst_prompt.md", names)
                self.assertIn("manifest.json", names)
                self.assertIn("assessments/run-1-cluster-a.json", names)
                self.assertIn("drilldowns/run-1-cluster-a.json", names)
                self.assertIn("triggers/run-1-cluster-a.json", names)
                self.assertIn("comparisons/run-1-cluster-a-vs-cluster-b-comparison.json", names)
                self.assertIn("reviews/run-1-review.json", names)
                self.assertIn("external-analysis/run-1-review-enrichment.json", names)
                self.assertIn("external-analysis/run-1-next-check-plan.json", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest.get("run_id"), run_id)
                self.assertGreaterEqual(manifest.get("file_count"), 1)
                summary = archive.read("summary.md").decode("utf-8")
                self.assertIn("Degraded clusters", summary)
