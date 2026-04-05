import json
import shutil
import unittest
from pathlib import Path
from typing import Dict, List

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.compare.two_cluster import ClusterComparison, compare_snapshots
from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.loop import (
    ComparisonPeer,
    HealthLoopRunner,
    HealthRating,
    HealthRunConfig,
    HealthSnapshotRecord,
    HealthTarget,
    TriggerPolicy,
    build_health_assessment,
    determine_pair_trigger_reasons,
)


class HealthLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path("tests/tmp-health")
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def tearDown(self) -> None:
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def _make_snapshot(
        self,
        cluster_id: str,
        control_plane_version: str = "v1.24.0",
        node_count: int = 3,
        pod_count: int = 5,
        helm_releases: list[dict[str, object]] | None = None,
        crds: list[dict[str, object]] | None = None,
        status: dict[str, object] | None = None,
    ) -> ClusterSnapshot:
        payload: Dict[str, object] = {
            "metadata": {
                "cluster_id": cluster_id,
                "captured_at": "2026-01-01T00:00:00Z",
                "control_plane_version": control_plane_version,
                "node_count": node_count,
                "pod_count": pod_count,
            }
        }
        if helm_releases is not None:
            payload["helm_releases"] = helm_releases
        if crds is not None:
            payload["crds"] = crds
        if status is not None:
            payload["status"] = status
        return ClusterSnapshot.from_dict(payload)

    def test_build_health_assessment_healthy_snapshot(self) -> None:
        snapshot = self._make_snapshot("cluster-healthy")
        target = HealthTarget(
            context="cluster-healthy",
            label="cluster-healthy",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None)
        self.assertEqual(result.rating, HealthRating.HEALTHY)
        self.assertGreater(len(result.assessment.observed_signals), 0)
        self.assertEqual(result.missing_evidence, ())

    def test_build_health_assessment_with_helm_error_and_missing_evidence(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-error",
            status={"helm_error": "timeout", "missing_evidence": ["events"]},
        )
        target = HealthTarget(
            context="cluster-error",
            label="cluster-error",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None)
        self.assertEqual(result.rating, HealthRating.DEGRADED)
        descriptions = [signal.description for signal in result.assessment.observed_signals]
        self.assertTrue(any("Missing evidence" in desc for desc in descriptions))
        self.assertTrue(any("Helm collection" in desc for desc in descriptions))

    def test_trigger_detects_watched_helm_release_drift(self) -> None:
        primary_snapshot = self._make_snapshot(
            "alpha",
            helm_releases=[
                {
                    "name": "observability",
                    "namespace": "kube-system",
                    "chart": "observability-1.0.0",
                    "chart_version": "1.0.0",
                }
            ],
        )
        secondary_snapshot = self._make_snapshot(
            "beta",
            helm_releases=[
                {
                    "name": "observability",
                    "namespace": "kube-system",
                    "chart": "observability-1.1.0",
                    "chart_version": "1.1.0",
                }
            ],
        )
        primary_target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=("kube-system/observability",),
            watched_crd_families=(),
        )
        secondary_target = HealthTarget(
            context="cluster-beta",
            label="cluster-beta",
            monitor_health=True,
            watched_helm_releases=("kube-system/observability",),
            watched_crd_families=(),
        )
        primary_record = HealthSnapshotRecord(
            target=primary_target,
            snapshot=primary_snapshot,
            path=Path("/tmp"),
            assessment=build_health_assessment(primary_snapshot, primary_target, None),
        )
        secondary_record = HealthSnapshotRecord(
            target=secondary_target,
            snapshot=secondary_snapshot,
            path=Path("/tmp"),
            assessment=build_health_assessment(secondary_snapshot, secondary_target, None),
        )
        policy = TriggerPolicy(True, True, True, True, True, True)
        reasons = determine_pair_trigger_reasons(primary_record, secondary_record, policy, {}, set())
        self.assertTrue(any("watched Helm release" in reason for reason in reasons))

    def test_load_deprecated_run_id_maps_to_run_label(self) -> None:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.tmp_dir / "health-config.json"
        payload = {
            "run_id": "legacy-run",
            "targets": [
                {"context": "cluster-alpha", "label": "cluster-alpha"},
            ],
            "peer_mappings": [
                {"source": "cluster-alpha", "peers": ["cluster-alpha"]},
            ],
        }
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        config = HealthRunConfig.load(config_path)
        self.assertEqual(config.run_label, "legacy-run")

    def test_no_comparison_when_no_trigger_fires(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
            "cluster-beta": self._make_snapshot("beta"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        comparison_called: List[bool] = []

        def compare_stub(a: ClusterSnapshot, b: ClusterSnapshot) -> ClusterComparison:
            comparison_called.append(True)
            return compare_snapshots(a, b)

        target_alpha = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        target_beta = HealthTarget(
            context="cluster-beta",
            label="cluster-beta",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="test-health",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target_alpha, target_beta),
            peers=(ComparisonPeer(source="cluster-alpha", peers=("cluster-beta",)),),
            trigger_policy=TriggerPolicy(False, False, False, False, False, False),
            manual_pairs=(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_stub,
            quiet=True,
        )
        _, triggers = runner.execute()
        self.assertFalse(comparison_called)
        self.assertEqual(triggers, [])
