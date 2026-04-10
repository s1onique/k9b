import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import cast
from unittest.mock import patch

from scripts.build_diagnostic_pack import (
    REVIEW_BUNDLE_SCHEMA,
    REVIEW_INPUT_SCHEMA,
    create_diagnostic_pack,
)
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
            assessment_payload = {
                "cluster_label": "cluster-a",
                "assessment": {
                    "health_rating": "degraded",
                    "findings": [{"description": "pod pressure"}],
                    "hypotheses": [{"description": "control plane drift"}],
                    "next_checks": [{"description": "capture pod logs"}],
                    "recommended_action": {"description": "investigate workloads"},
                },
            }
            (health_dir / "assessments" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(assessment_payload), encoding="utf-8"
            )
            drilldown_payload = {
                "cluster_label": "cluster-a",
                "trigger_reasons": ["CrashLoopBackOff"],
                "warning_events": [{"reason": "CrashLoopBackOff"}],
                "non_running_pods": [{"name": "pod"}],
                "affected_namespaces": ["default"],
                "pattern_details": {"pattern": "failure"},
                "summary": {"severity": "high"},
            }
            (health_dir / "drilldowns" / f"{run_id}-cluster-a.json").write_text(
                json.dumps(drilldown_payload), encoding="utf-8"
            )
            (health_dir / "triggers" / f"{run_id}-cluster-a.json").write_text(
                "{}", encoding="utf-8"
            )
            comparison_payload = {
                "summary": "comparison summary",
                "top_drifts": ["control plane version drift"],
                "primary_cluster_label": "cluster-a",
                "secondary_cluster_label": "cluster-b",
            }
            (health_dir / "comparisons" / f"{run_id}-cluster-a-vs-cluster-b-comparison.json").write_text(
                json.dumps(comparison_payload), encoding="utf-8"
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
            external_diagnostic = {
                "cluster_label": "cluster-a",
                "suggested_next_checks": ["external check"],
                "findings": ["external finding"],
                "summary": "external summary",
                "purpose": "auto-drilldown",
            }
            (health_dir / "external-analysis" / f"{run_id}-cluster-a-diag.json").write_text(
                json.dumps(external_diagnostic), encoding="utf-8"
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
                self.assertIn("digest.md", names)
                self.assertIn("review_bundle.json", names)
                self.assertIn("review_input_14b.json", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest.get("run_id"), run_id)
                self.assertGreaterEqual(manifest.get("file_count"), 1)
                file_paths = [entry.get("path") for entry in manifest.get("files", [])]
                self.assertIn("digest.md", file_paths)
                self.assertIn("review_bundle.json", file_paths)
                summary = archive.read("summary.md").decode("utf-8")
                self.assertIn("Degraded clusters", summary)
                digest = archive.read("digest.md").decode("utf-8")
                self.assertIn("Diagnostic pack digest", digest)
                self.assertIn("## Run identity", digest)
                self.assertIn("## Artifact map", digest)
                bundle = json.loads(archive.read("review_bundle.json"))
                self.assertEqual(bundle.get("schema_version"), REVIEW_BUNDLE_SCHEMA)
                self.assertEqual(bundle.get("run", {}).get("run_id"), run_id)
                self.assertEqual(bundle.get("review", {}).get("path"), f"reviews/{run_id}-review.json")
                self.assertEqual(bundle.get("review", {}).get("content", {}).get("rating"), "ok")
                self.assertIsInstance(bundle.get("assessments"), list)
                self.assertEqual(bundle.get("assessments", [])[0].get("cluster_label"), "cluster-a")
                self.assertIn(
                    "assessments/run-1-cluster-a.json",
                    bundle.get("artifact_manifest", {}).get("included_paths", []),
                )
                self.assertIn("external-analysis/run-1-review-enrichment.json",
                    bundle.get("artifact_manifest", {}).get("included_paths", []))
                self.assertNotIn("ui_index", bundle)
                run_entry = bundle.get("run", {})
                self.assertNotIn("historical_llm_stats", run_entry)
                self.assertNotIn("llm_activity", run_entry)
                for section in ("assessments", "drilldowns", "triggers", "comparisons", "external_analysis"):
                    self.assertIsInstance(bundle.get(section), list)
                manifest = json.loads(archive.read("manifest.json"))
                file_paths = [entry.get("path") for entry in manifest.get("files", [])]
                self.assertEqual(
                    set(bundle.get("artifact_manifest", {}).get("included_paths", [])),
                    set(filter(None, file_paths)),
                )
                review_input = json.loads(archive.read("review_input_14b.json"))
                self.assertEqual(review_input.get("schema_version"), REVIEW_INPUT_SCHEMA)
                self.assertEqual(review_input.get("run", {}).get("run_id"), run_id)
                self.assertEqual(review_input.get("source_review_bundle_path"), "review_bundle.json")
                self.assertEqual(
                    review_input.get("artifact_manifest", {}).get("review_input_14b_path"),
                    "review_input_14b.json",
                )
                self.assertIn("review_bundle.json", review_input.get("artifact_manifest", {}).get("included_paths", []))
                cluster_summary = review_input.get("cluster_summaries", [])[0]
                self.assertEqual(cluster_summary.get("cluster_label"), "cluster-a")
                self.assertTrue(cluster_summary.get("top_findings"))
                self.assertTrue(cluster_summary.get("top_hypotheses"))
                self.assertTrue(cluster_summary.get("top_next_checks"))
                self.assertIsNotNone(cluster_summary.get("drilldown_summary"))
                self.assertTrue(cluster_summary.get("artifact_paths", {}).get("external_analysis"))
                self.assertIsInstance(review_input.get("fleet_summary"), dict)
                review_summary = review_input.get("review_summary", {})
                selected = review_summary.get("selected_drilldowns", [])
                if selected:
                    self.assertIsNotNone(selected[0].get("cluster_label"))
                    self.assertEqual(selected[0].get("cluster_label"), "cluster-a")
                comparison_detail = review_input.get("comparison_summary", [])[0]
                self.assertIsNotNone(comparison_detail.get("summary", {}).get("primary_cluster"))
                self.assertIsNotNone(comparison_detail.get("summary", {}).get("secondary_cluster"))
                self.assertTrue(comparison_detail.get("top_drifts"))
                top_drifts = comparison_detail.get("top_drifts") or []
                self.assertTrue(any("control plane version drift" in drift for drift in top_drifts))
                self.assertNotIn("pod_descriptions", json.dumps(review_input))
                self.assertNotIn("warning_events", json.dumps(review_input))
                artifact_paths = cluster_summary.get("artifact_paths", {})
                self.assertIsNotNone(artifact_paths.get("drilldown"))
                self.assertTrue(
                    "external-analysis/run-1-cluster-a-diag.json"
                    in artifact_paths.get("external_analysis", []),
                )

    def test_structured_log_events_emit_when_building_pack(self) -> None:
        run_id = "run-logging"
        run_label = "health-run"
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "scripts.build_diagnostic_pack.emit_structured_log"
        ) as emit_mock:
            runs_dir = Path(tmpdir) / "runs"
            health_dir = runs_dir / "health"
            (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
            (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
            (health_dir / "triggers").mkdir(parents=True, exist_ok=True)
            (health_dir / "comparisons").mkdir(parents=True, exist_ok=True)
            (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
            (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)
            index_data = sample_ui_index()
            run_payload = cast(dict[str, object], index_data["run"])
            run_payload["run_id"] = run_id
            run_payload["run_label"] = run_label
            (health_dir / "ui-index.json").write_text(
                json.dumps(index_data), encoding="utf-8"
            )
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
            emit_mock.return_value = {}
            pack_path = create_diagnostic_pack(run_id, runs_dir, output_dir=packs_dir)
            self.assertTrue(pack_path.exists())
            self.assertGreaterEqual(emit_mock.call_count, 9)
            start_call = emit_mock.call_args_list[0]
            self.assertEqual(start_call.kwargs["event"], "diagnostic-pack-start")
            self.assertEqual(start_call.kwargs["run_id"], run_id)
            summary_calls = [
                call
                for call in emit_mock.call_args_list
                if call.kwargs["event"] == "diagnostic-pack-collection-summary"
            ]
            self.assertEqual(len(summary_calls), 7)
            counts = {
                call.kwargs["metadata"]["artifact_kind"]: call.kwargs["metadata"]["artifact_count"]
                for call in summary_calls
            }
            self.assertEqual(counts.get("external_analysis"), 2)
            ready_call = emit_mock.call_args_list[-1]
            self.assertEqual(ready_call.kwargs["event"], "diagnostic-pack-ready")
