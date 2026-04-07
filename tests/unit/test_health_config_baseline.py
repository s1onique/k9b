import json
import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.health.loop import HealthRunConfig


class HealthConfigBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_baseline(self, relative: str) -> Path:
        path = self.tmpdir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "control_plane_version_range": {},
                    "watched_releases": [],
                    "required_crd_families": [],
                    "ignored_drift": [],
                    "peer_roles": {},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_cohort_and_target_baseline_paths_resolve(self) -> None:
        default_baseline = self._write_baseline("health-baseline.json")
        cohort_a = self._write_baseline("baseline-a.json")
        cohort_b = self._write_baseline("special/baseline-b.json")
        config_path = self.tmpdir / "health-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "run_label": "cohorted",
                    "output_dir": "runs",
                    "targets": [
                        {
                            "context": "alpha",
                            "label": "alpha",
                            "cluster_class": "prod",
                            "cluster_role": "primary",
                            "baseline_cohort": "cohort-a",
                        },
                        {
                            "context": "beta",
                            "label": "beta",
                            "cluster_class": "prod",
                            "cluster_role": "primary",
                            "baseline_cohort": "cohort-b",
                            "baseline_policy_path": "special/baseline-b.json",
                        },
                        {
                            "context": "gamma",
                            "label": "gamma",
                            "cluster_class": "prod",
                            "cluster_role": "secondary",
                            "baseline_cohort": "cohort-a",
                        },
                    ],
                    "peer_mappings": [
                        {
                            "primary": "alpha",
                            "peers": ["beta"],
                            "intent": "expected-drift",
                        }
                    ],
                    "manual_pairs": [],
                    "baseline_policy_path": "health-baseline.json",
                    "baseline_policies": [
                        {"cohort": "cohort-a", "path": "baseline-a.json"},
                        {"cohort": "cohort-b", "path": "special/baseline-b.json"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        config = HealthRunConfig.load(config_path)
        self.assertEqual(config.baseline_policy_path, default_baseline)
        alpha_policy, alpha_path = config.target_baselines["alpha"]
        beta_policy, beta_path = config.target_baselines["beta"]
        gamma_policy, gamma_path = config.target_baselines["gamma"]
        self.assertEqual(alpha_path, cohort_a)
        self.assertEqual(beta_path, cohort_b)
        self.assertEqual(gamma_path, cohort_a)
        self.assertIs(alpha_policy, config.cohort_baselines["cohort-a"][0])
        self.assertIs(beta_policy, config.cohort_baselines["cohort-b"][0])
        self.assertIs(gamma_policy, config.cohort_baselines["cohort-a"][0])

    def test_example_health_config_documents_review_enrichment(self) -> None:
        root = Path(__file__).resolve().parents[2]
        example_path = root / "runs" / "health-config.local.example.json"
        content = json.loads(example_path.read_text(encoding="utf-8"))
        external_analysis = content.get("external_analysis") or {}
        self.assertIn("adapters", external_analysis)
        adapters = external_analysis["adapters"]
        self.assertIsInstance(adapters, list)
        self.assertGreater(len(adapters), 0)
        auto_drilldown = external_analysis.get("auto_drilldown") or {}
        self.assertIn("enabled", auto_drilldown)
        self.assertIn("provider", auto_drilldown)
        review_enrichment = external_analysis.get("review_enrichment") or {}
        self.assertIn("enabled", review_enrichment)
        self.assertIn("provider", review_enrichment)
