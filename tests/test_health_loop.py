import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from tests.path_helper import ensure_src_in_path

ensure_src_in_path()

from k8s_diag_agent.compare.two_cluster import ClusterComparison, compare_snapshots
from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot, WarningEventSummary
from k8s_diag_agent.health.baseline import (
    BaselinePolicy,
    BaselineDriftCategory,
    ControlPlaneExpectation,
    CRDPolicy,
    ReleasePolicy,
)
from k8s_diag_agent.health.drilldown import (
    DrilldownArtifact,
    DrilldownCollector,
    DrilldownEvidence,
    DrilldownPod,
    DrilldownRolloutStatus,
)
from k8s_diag_agent.health.loop import (
    ComparisonPeer,
    HealthLoopRunner,
    HealthHistoryEntry,
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

    class _StubDrilldownCollector(DrilldownCollector):
        def __init__(self) -> None:
            super().__init__(command_runner=lambda command: "{}")
            self.calls: List[tuple[str, Tuple[str, ...]]] = []

        def collect(self, context: str, namespaces: Sequence[str]) -> DrilldownEvidence:
            self.calls.append((context, tuple(namespaces)))
            return DrilldownEvidence(
                warning_events=(),
                non_running_pods=(),
                pod_descriptions={},
                rollouts=(),
                affected_namespaces=tuple(namespaces or ("default",)),
                affected_workloads=(),
                summary={"placeholder": True},
                collection_timestamps={
                    "warning_events": "2026-01-01T00:00:00Z",
                    "pods": "2026-01-01T00:00:00Z",
                    "rollouts": "2026-01-01T00:00:00Z",
                },
            )

    def _make_snapshot(
        self,
        cluster_id: str,
        control_plane_version: str = "v1.24.0",
        node_count: int = 3,
        pod_count: int = 5,
        helm_releases: list[dict[str, object]] | None = None,
        crds: list[dict[str, object]] | None = None,
        status: dict[str, object] | None = None,
        health_signals: dict[str, object] | None = None,
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
        if health_signals is not None:
            payload["health_signals"] = health_signals
        return ClusterSnapshot.from_dict(payload)

    def _baseline_policy(
        self,
        ignored: Sequence[BaselineDriftCategory] | None = None,
        release_versions: Sequence[str] | None = None,
    ) -> BaselinePolicy:
        cp = ControlPlaneExpectation(
            min_version="v1.24.0",
            max_version="v1.25.0",
            why="Control plane must stay within the supported range.",
            next_check="Inspect kube-apiserver pods for version mismatches.",
        )
        release_policy = ReleasePolicy(
            release_key="kube-system/observability",
            allowed_versions=tuple(release_versions or ("1.1.0",)),
            why="The observability stack must run the curated chart.",
            next_check="Compare the Helm chart version to the platform manifest.",
        )
        crd_policy = CRDPolicy(
            family="monitoring.example.com",
            why="Monitoring controllers rely on this CRD family.",
            next_check="Ensure the CRD is present and served.",
        )
        return BaselinePolicy(
            control_plane_expectation=cp,
            release_policies={release_policy.release_key: release_policy},
            required_crds={crd_policy.family: crd_policy},
            ignored_drift_categories=set(ignored or []),
            peer_roles={"cluster-alpha": "primary", "cluster-beta": "canary"},
        )

    def test_build_health_assessment_healthy_snapshot(self) -> None:
        snapshot = self._make_snapshot("cluster-healthy")
        target = HealthTarget(
            context="cluster-healthy",
            label="cluster-healthy",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
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
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
        self.assertEqual(result.rating, HealthRating.DEGRADED)
        descriptions = [signal.description for signal in result.assessment.observed_signals]
        self.assertTrue(any("Missing evidence" in desc for desc in descriptions))
        self.assertTrue(any("Helm collection" in desc for desc in descriptions))

    def test_build_health_assessment_reports_history_changes(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-change",
            control_plane_version="v1.25.0",
            node_count=4,
            pod_count=7,
            helm_releases=[
                {
                    "name": "observability",
                    "namespace": "kube-system",
                    "chart": "observability",
                    "chart_version": "1.1.0",
                }
            ],
            crds=[
                {
                    "name": "monitoring.example.com",
                    "spec": {"versions": [{"name": "v2", "served": True, "storage": True}]},
                }
            ],
            status={"missing_evidence": ["events"]},
        )
        target = HealthTarget(
            context="cluster-change",
            label="cluster-change",
            monitor_health=True,
            watched_helm_releases=("kube-system/observability",),
            watched_crd_families=("monitoring.example.com",),
        )
        previous = HealthHistoryEntry(
            cluster_id="cluster-change",
            node_count=3,
            pod_count=5,
            control_plane_version="v1.24.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=("logs",),
            watched_helm_releases={"kube-system/observability": "1.0.0"},
            watched_crd_families={"monitoring.example.com": "v1"},
        )
        result = build_health_assessment(snapshot, target, previous, BaselinePolicy.empty())
        descriptions = [
            finding.description for finding in result.assessment.findings
        ]
        self.assertTrue(any("Control plane version changed" in desc for desc in descriptions))
        self.assertTrue(any("Node count changed" in desc for desc in descriptions))
        self.assertTrue(any("Pod count changed" in desc for desc in descriptions))
        self.assertTrue(
            any("Watched Helm release kube-system/observability" in desc for desc in descriptions)
        )
        self.assertTrue(
            any("Watched CRD monitoring.example.com" in desc for desc in descriptions)
        )
        self.assertTrue(
            any("New missing telemetry since last run" in desc for desc in descriptions)
        )

    def test_baseline_control_plane_drift_annotates_reason(self) -> None:
        snapshot = self._make_snapshot("cluster-a", control_plane_version="v1.26.0")
        target = HealthTarget(
            context="cluster-a",
            label="cluster-a",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        baseline = self._baseline_policy()
        result = build_health_assessment(snapshot, target, None, baseline)
        self.assertTrue(
            any(
                "Baseline policy violation" in hypothesis.description
                for hypothesis in result.assessment.hypotheses
            )
        )
        self.assertTrue(
            any("baseline expectation" in finding.description for finding in result.assessment.findings)
        )

    def test_baseline_required_crd_missing(self) -> None:
        snapshot = self._make_snapshot("cluster-b", crds=[])
        target = HealthTarget(
            context="cluster-b",
            label="cluster-b",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=("monitoring.example.com",),
        )
        baseline = self._baseline_policy()
        result = build_health_assessment(snapshot, target, None, baseline)
        self.assertTrue(
            any(
                "CRD family monitoring.example.com" in finding.description
                for finding in result.assessment.findings
            )
        )

    def test_baseline_release_out_of_policy(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-c",
            helm_releases=[
                {
                    "name": "observability",
                    "namespace": "kube-system",
                    "chart": "observability",
                    "chart_version": "1.2.0",
                }
            ],
        )
        target = HealthTarget(
            context="cluster-c",
            label="cluster-c",
            monitor_health=True,
            watched_helm_releases=("kube-system/observability",),
            watched_crd_families=(),
        )
        baseline = self._baseline_policy()
        result = build_health_assessment(snapshot, target, None, baseline)
        self.assertTrue(
            any(
                "baseline requires" in finding.description
                for finding in result.assessment.findings
                if "Watched Helm release" in finding.description
            )
        )

    def test_no_trigger_when_baseline_allows_release_drift(self) -> None:
        primary_snapshot = self._make_snapshot(
            "alpha",
            helm_releases=[
                {
                    "name": "observability",
                    "namespace": "kube-system",
                    "chart": "observability",
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
                    "chart": "observability",
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
            assessment=build_health_assessment(primary_snapshot, primary_target, None, BaselinePolicy.empty()),
        )
        secondary_record = HealthSnapshotRecord(
            target=secondary_target,
            snapshot=secondary_snapshot,
            path=Path("/tmp"),
            assessment=build_health_assessment(secondary_snapshot, secondary_target, None, BaselinePolicy.empty()),
        )
        baseline = self._baseline_policy(ignored=[BaselineDriftCategory.WATCHED_HELM_RELEASE])
        policy = TriggerPolicy(True, True, True, True, True, True)
        details = determine_pair_trigger_reasons(
            primary_record,
            secondary_record,
            policy,
            {},
            set(),
            baseline,
        )
        self.assertFalse(
            any(detail.type == BaselineDriftCategory.WATCHED_HELM_RELEASE.value for detail in details)
        )

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
            assessment=build_health_assessment(primary_snapshot, primary_target, None, BaselinePolicy.empty()),
        )
        secondary_record = HealthSnapshotRecord(
            target=secondary_target,
            snapshot=secondary_snapshot,
            path=Path("/tmp"),
            assessment=build_health_assessment(secondary_snapshot, secondary_target, None, BaselinePolicy.empty()),
        )
        policy = TriggerPolicy(True, True, True, True, True, True)
        details = determine_pair_trigger_reasons(
            primary_record,
            secondary_record,
            policy,
            {},
            set(),
            BaselinePolicy.empty(),
        )
        self.assertTrue(
            any(detail.type == BaselineDriftCategory.WATCHED_HELM_RELEASE.value for detail in details)
        )

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
        baseline_path = self.tmp_dir / "health-baseline.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "control_plane_version_range": {
                        "min_version": "v1.24.0",
                        "max_version": "v1.25.0",
                        "why": "test",
                        "next_check": "test",
                    },
                    "watched_releases": [],
                    "required_crd_families": [],
                    "ignored_drift": [],
                    "peer_roles": {},
                }
            ),
            encoding="utf-8",
        )
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
            baseline_policy=BaselinePolicy.empty(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_stub,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=self._StubDrilldownCollector(),
        )
        _, triggers, drilldowns = runner.execute()
        self.assertFalse(comparison_called)
        self.assertEqual(triggers, [])
        self.assertEqual(drilldowns, [])

    def test_drilldown_trigger_created_on_crashloop(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-alpha",
            health_signals={
                "pod_counts": {
                    "non_running": 2,
                    "crash_loop_backoff": 1,
                    "pending": 1,
                    "image_pull_backoff": 0,
                },
                "job_failures": 0,
                "warning_events": (),
            },
        )
        snapshots = {"cluster-alpha": snapshot}

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="test",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(True, True, True, True, True, True),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        stub_collector = self._StubDrilldownCollector()
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=stub_collector,
        )
        _, _, drilldowns = runner.execute()
        self.assertEqual(len(drilldowns), 1)
        self.assertIn("CrashLoopBackOff", drilldowns[0].trigger_reasons)

    def test_drilldown_not_created_when_healthy(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-alpha",
            health_signals={
                "pod_counts": {
                    "non_running": 0,
                    "crash_loop_backoff": 0,
                    "pending": 0,
                    "image_pull_backoff": 0,
                },
                "job_failures": 0,
                "warning_events": (),
            },
        )
        snapshots = {"cluster-alpha": snapshot}

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="test",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(True, True, True, True, True, True),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        stub_collector = self._StubDrilldownCollector()
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=stub_collector,
        )
        _, _, drilldowns = runner.execute()
        self.assertEqual(drilldowns, [])

    def test_drilldown_artifact_serialization(self) -> None:
        timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
        warning = WarningEventSummary(
            namespace="default",
            reason="TestReason",
            message="message",
            count=1,
            last_seen="2026-01-01T00:00:00Z",
        )
        pod = DrilldownPod(
            namespace="default",
            name="pod-1",
            phase="CrashLoopBackOff",
            reason="CrashLoopBackOff",
        )
        rollout = DrilldownRolloutStatus(
            kind="Deployment",
            namespace="default",
            name="deploy-1",
            desired_replicas=3,
            available_replicas=2,
            unavailable_replicas=1,
            updated_replicas=2,
            generation=1,
            observed_generation=1,
            conditions=("Available=True",),
        )
        artifact = DrilldownArtifact(
            run_label="run",
            run_id="id",
            timestamp=timestamp,
            snapshot_timestamp=timestamp,
            context="cluster",
            label="cluster",
            cluster_id="cluster-1",
            trigger_reasons=("CrashLoopBackOff",),
            missing_evidence=("logs",),
            evidence_summary={"events": 2},
            affected_namespaces=("default",),
            affected_workloads=({"kind": "Pod", "namespace": "default", "name": "pod-1"},),
            warning_events=(warning,),
            non_running_pods=(pod,),
            pod_descriptions={"default/pod-1": "desc"},
            rollout_status=(rollout,),
            collection_timestamps={
                "warning_events": "2026-01-02T00:00:00Z",
                "pods": "2026-01-02T00:00:00Z",
                "rollouts": "2026-01-02T00:00:00Z",
            },
        )
        round_trip = DrilldownArtifact.from_dict(artifact.to_dict())
        self.assertEqual(round_trip.run_label, artifact.run_label)
        self.assertEqual(round_trip.trigger_reasons, artifact.trigger_reasons)
        self.assertEqual(round_trip.missing_evidence, artifact.missing_evidence)
        self.assertEqual(round_trip.warning_events[0].reason, warning.reason)
        self.assertEqual(round_trip.non_running_pods[0].name, pod.name)
        self.assertEqual(round_trip.rollout_status[0].name, rollout.name)
