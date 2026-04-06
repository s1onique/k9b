import json
import shutil
import unittest
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    WarningEventSummary,
    extract_cluster_snapshots,
)
from k8s_diag_agent.compare.two_cluster import ClusterComparison, compare_snapshots
from k8s_diag_agent.health.baseline import (
    BaselineDriftCategory,
    BaselinePolicy,
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
from k8s_diag_agent.health.image_pull_secret import (
    BROKEN_IMAGE_PULL_SECRET_REASON,
    ExternalSecretStatus,
    ImagePullSecretInsight,
    ImagePullSecretInspector,
    TargetSecretStatus,
)
from k8s_diag_agent.health.loop import (
    BaselineRegistry,
    ComparisonIntent,
    ComparisonPeer,
    HealthAssessmentResult,
    HealthHistoryEntry,
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
        self.pattern_snapshots = self._load_pattern_snapshots()

    def tearDown(self) -> None:
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    class _StubDrilldownCollector(DrilldownCollector):
        def __init__(self) -> None:
            super().__init__(command_runner=lambda command: "{}")
            self.calls: list[tuple[str, tuple[str, ...]]] = []

        def collect(
            self,
            context: str,
            namespaces: Sequence[str],
            image_pull_secret_insight: ImagePullSecretInsight | None = None,
            pattern_reasons: Sequence[str] | None = None,
            pattern_metadata: Mapping[str, Sequence[str]] | None = None,
        ) -> DrilldownEvidence:
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
                image_pull_secret_insights=(),
            )

    class _StubImagePullSecretInspector(ImagePullSecretInspector):
        def __init__(self, insight: ImagePullSecretInsight | None = None):
            super().__init__(command_runner=lambda command: "{}")
            self.insight = insight
            self.calls: list[tuple[str, tuple[str, ...], tuple[WarningEventSummary, ...]]] = []

        def inspect(
            self,
            context: str,
            namespaces: Iterable[str],
            warning_events: Iterable[WarningEventSummary],
        ) -> ImagePullSecretInsight | None:
            self.calls.append((context, tuple(namespaces), tuple(warning_events)))
            return self.insight

    def _read_comparison_decision(self) -> Mapping[str, Any]:
        decision_dir = self.tmp_dir / "health"
        files = list(decision_dir.glob("*-comparison-decisions.json"))
        self.assertEqual(len(files), 1, "Expected exactly one comparison decision artifact")
        raw = json.loads(files[0].read_text(encoding="utf-8"))
        decisions = cast(list[Mapping[str, Any]], raw)
        self.assertEqual(len(decisions), 1, "Expected a single comparison decision entry")
        return decisions[0]

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
        payload: dict[str, object] = {
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

    def _make_image_pull_secret_insight(self) -> ImagePullSecretInsight:
        external_secret = ExternalSecretStatus(
            namespace="default",
            name="glcr-secret-external",
            target_secret="glcr-secret",
            secret_store_ref={"name": "glcr-store", "kind": "SecretStore", "namespace": "default"},
            status_reason="UpdateFailed",
            status_message="Secret does not exist",
            ready=False,
        )
        return ImagePullSecretInsight(
            namespace="default",
            secret_name="glcr-secret",
            deployments=({"namespace": "default", "name": "app-deployment"},),
            external_secrets=(external_secret,),
            secret_store_refs=({"name": "glcr-store", "kind": "SecretStore", "namespace": "default"},),
            target_secret_status=TargetSecretStatus.missing("default", "glcr-secret", "secret not found"),
            events=(
                WarningEventSummary(
                    namespace="default",
                    reason="FailedToRetrieveImagePullSecret",
                    message='Failed to retrieve image pull secret "glcr-secret".',
                    count=1,
                    last_seen="2026-01-01T00:00:00Z",
                ),
            ),
        )

    def _load_pattern_snapshots(self) -> dict[str, ClusterSnapshot]:
        path = Path("tests/fixtures/snapshots/deterministic-patterns.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        snapshots = extract_cluster_snapshots(raw)
        return {snapshot.metadata.cluster_id: snapshot for snapshot in snapshots}

    def _pattern_assessment(self, cluster_id: str) -> HealthAssessmentResult:
        snapshot = self.pattern_snapshots[cluster_id]
        target = HealthTarget(
            context=cluster_id,
            label=cluster_id,
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        return build_health_assessment(snapshot, target, None, BaselinePolicy.empty())

    def _baseline_policy(
        self,
        ignored: Sequence[BaselineDriftCategory] | None = None,
        release_versions: Sequence[str] | None = None,
        expected: Sequence[BaselineDriftCategory] | None = None,
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
            expected_drift_categories=set(expected or []),
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

    def test_baseline_example_includes_expected_drift(self) -> None:
        baseline_path = Path("runs/health-baseline.example.json")
        baseline = BaselinePolicy.load_from_file(baseline_path)
        self.assertTrue(baseline.expected_drift_categories)
        self.assertIn(
            BaselineDriftCategory.WATCHED_HELM_RELEASE,
            baseline.expected_drift_categories,
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
            baseline_policy=BaselinePolicy.empty(),
            assessment=build_health_assessment(primary_snapshot, primary_target, None, BaselinePolicy.empty()),
        )
        secondary_record = HealthSnapshotRecord(
            target=secondary_target,
            snapshot=secondary_snapshot,
            path=Path("/tmp"),
            baseline_policy=BaselinePolicy.empty(),
            assessment=build_health_assessment(secondary_snapshot, secondary_target, None, BaselinePolicy.empty()),
        )
        baseline = self._baseline_policy(ignored=[BaselineDriftCategory.WATCHED_HELM_RELEASE])
        policy = TriggerPolicy(True, True, True, True, True, True)
        registry = BaselineRegistry([baseline])
        details = determine_pair_trigger_reasons(
            primary_record,
            secondary_record,
            policy,
            {},
            set(),
            baseline,
            registry,
            ComparisonIntent.SUSPICIOUS_DRIFT.label(),
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
            baseline_policy=BaselinePolicy.empty(),
            assessment=build_health_assessment(primary_snapshot, primary_target, None, BaselinePolicy.empty()),
        )
        secondary_record = HealthSnapshotRecord(
            target=secondary_target,
            snapshot=secondary_snapshot,
            path=Path("/tmp"),
            baseline_policy=BaselinePolicy.empty(),
            assessment=build_health_assessment(secondary_snapshot, secondary_target, None, BaselinePolicy.empty()),
        )
        policy = TriggerPolicy(True, True, True, True, True, True)
        registry = BaselineRegistry([BaselinePolicy.empty()])
        details = determine_pair_trigger_reasons(
            primary_record,
            secondary_record,
            policy,
            {},
            set(),
            BaselinePolicy.empty(),
            registry,
            ComparisonIntent.SUSPICIOUS_DRIFT.label(),
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
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                    "baseline_cohort": "fleet-production",
                }
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

    def test_config_requires_target_metadata(self) -> None:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = self.tmp_dir / "health-baseline.json"
        baseline_path.write_text(
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
        config_path = self.tmp_dir / "health-config.json"
        payload = {
            "run_label": "health",
            "targets": [
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                }
            ],
            "peer_mappings": [],
            "manual_pairs": [],
            "baseline_policy_path": baseline_path.name,
        }
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "baseline_cohort/platform_generation"):
            HealthRunConfig.load(config_path)

    def test_no_comparison_when_no_trigger_fires(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
            "cluster-beta": self._make_snapshot("beta"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        comparison_called: list[bool] = []

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
            peers=(
                ComparisonPeer(
                    primary="cluster-alpha",
                    secondary="cluster-beta",
                    intent=ComparisonIntent.SUSPICIOUS_DRIFT,
                ),
            ),
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

    def test_all_targets_produce_assessments(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
            "cluster-beta": self._make_snapshot("beta"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        targets = (
            HealthTarget(
                context="cluster-alpha",
                label="cluster-alpha",
                monitor_health=True,
                watched_helm_releases=(),
                watched_crd_families=(),
                cluster_class="prod",
                cluster_role="primary",
                baseline_cohort="fleet-production",
            ),
            HealthTarget(
                context="cluster-beta",
                label="cluster-beta",
                monitor_health=True,
                watched_helm_releases=(),
                watched_crd_families=(),
                cluster_class="prod",
                cluster_role="primary",
                baseline_cohort="fleet-production",
            ),
        )
        config = HealthRunConfig(
            run_label="coverage",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=targets,
            peers=(),
            trigger_policy=TriggerPolicy(False, False, False, False, False, False),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=self._StubDrilldownCollector(),
        )
        assessments, triggers, _ = runner.execute()
        self.assertEqual(len(assessments), len(targets))
        self.assertCountEqual([artifact.label for artifact in assessments], ["cluster-alpha", "cluster-beta"])
        self.assertEqual(triggers, [])

    def test_suspicious_pair_with_matching_baseline_cohorts_is_policy_eligible(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
            "cluster-beta": self._make_snapshot("beta"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target_alpha = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet-production",
        )
        target_beta = HealthTarget(
            context="cluster-beta",
            label="cluster-beta",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet-production",
        )
        config = HealthRunConfig(
            run_label="cohort-eligible",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target_alpha, target_beta),
            peers=(
                ComparisonPeer(
                    primary="cluster-alpha",
                    secondary="cluster-beta",
                    intent=ComparisonIntent.SUSPICIOUS_DRIFT,
                ),
            ),
            trigger_policy=TriggerPolicy(False, False, False, False, False, False),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=self._StubDrilldownCollector(),
        )
        runner.execute()
        decision = self._read_comparison_decision()
        self.assertTrue(decision["policy_eligible"])
        self.assertFalse(decision["triggered"])
        self.assertEqual(decision.get("primary_cohort"), "fleet-production")
        self.assertEqual(decision.get("secondary_cohort"), "fleet-production")
        self.assertIn("policy compatible but no triggers fired", decision["reason"])

    def test_suspicious_pair_ineligible_when_cohort_mismatch(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
            "cluster-beta": self._make_snapshot("beta"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target_alpha = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet-production",
        )
        target_beta = HealthTarget(
            context="cluster-beta",
            label="cluster-beta",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet-dr",
        )
        config = HealthRunConfig(
            run_label="cohort-mismatch",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target_alpha, target_beta),
            peers=(
                ComparisonPeer(
                    primary="cluster-alpha",
                    secondary="cluster-beta",
                    intent=ComparisonIntent.SUSPICIOUS_DRIFT,
                ),
            ),
            trigger_policy=TriggerPolicy(False, False, False, False, False, False),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=self._StubDrilldownCollector(),
        )
        runner.execute()
        decision = self._read_comparison_decision()
        self.assertFalse(decision["policy_eligible"])
        self.assertFalse(decision["triggered"])
        self.assertIn("baseline cohorts differ", decision["reason"])
        self.assertEqual(decision.get("primary_cohort"), "fleet-production")
        self.assertEqual(decision.get("secondary_cohort"), "fleet-dr")

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

    def test_drilldown_reasons_include_image_pull_secret_supply_chain(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-alpha",
            health_signals={
                "pod_counts": {
                    "non_running": 1,
                    "crash_loop_backoff": 0,
                    "pending": 0,
                    "image_pull_backoff": 1,
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
        stub_inspector = self._StubImagePullSecretInspector(self._make_image_pull_secret_insight())
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=stub_collector,
            image_pull_secret_inspector=stub_inspector,
        )
        _, _, drilldowns = runner.execute()
        self.assertTrue(drilldowns)
        self.assertIn(BROKEN_IMAGE_PULL_SECRET_REASON, drilldowns[0].trigger_reasons)

    def test_drilldown_collects_pattern_details_for_probe(self) -> None:
        snapshot = self.pattern_snapshots["pattern-probe"]
        snapshots = {"pattern-probe": snapshot}

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target = HealthTarget(
            context="pattern-probe",
            label="pattern-probe",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="pattern",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(True, True, True, True, True, True),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        collector_stub = DrilldownCollector(command_runner=lambda command: "{}")
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=collector_stub,
        )
        _, _, drilldowns = runner.execute()
        self.assertTrue(drilldowns)
        self.assertIn("probe_failure", drilldowns[0].trigger_reasons)
        self.assertIn("probe_failure", drilldowns[0].pattern_details)

    def test_build_health_assessment_crashloop_backoff_degrades(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-crashloop",
            health_signals={
                "pod_counts": {
                    "non_running": 1,
                    "pending": 0,
                    "crash_loop_backoff": 1,
                    "image_pull_backoff": 0,
                    "completed_job_pods": 0,
                },
                "job_failures": 0,
                "warning_events": (),
            },
        )
        target = HealthTarget(
            context="cluster-crashloop",
            label="cluster-crashloop",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
        self.assertEqual(result.rating, HealthRating.DEGRADED)
        self.assertTrue(
            any(
                "CrashLoopBackOff" in finding.description
                for finding in result.assessment.findings
            )
        )

    def test_build_health_assessment_image_pull_backoff_degrades(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-imageerr",
            health_signals={
                "pod_counts": {
                    "non_running": 1,
                    "pending": 0,
                    "crash_loop_backoff": 0,
                    "image_pull_backoff": 1,
                    "completed_job_pods": 0,
                },
                "job_failures": 0,
                "warning_events": (),
            },
        )
        target = HealthTarget(
            context="cluster-imageerr",
            label="cluster-imageerr",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        result = build_health_assessment(snapshot, target, None, BaselinePolicy.empty())
        self.assertEqual(result.rating, HealthRating.DEGRADED)
        self.assertTrue(
            any(
                "ImagePullBackOff" in finding.description
                for finding in result.assessment.findings
            )
        )

    def test_build_health_assessment_records_secret_supply_chain(self) -> None:
        snapshot = self._make_snapshot(
            "cluster-imageerr",
            health_signals={
                "pod_counts": {
                    "non_running": 1,
                    "pending": 0,
                    "crash_loop_backoff": 0,
                    "image_pull_backoff": 1,
                    "completed_job_pods": 0,
                },
                "job_failures": 0,
                "warning_events": (),
            },
        )
        target = HealthTarget(
            context="cluster-imageerr",
            label="cluster-imageerr",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        insight = self._make_image_pull_secret_insight()
        result = build_health_assessment(
            snapshot,
            target,
            None,
            BaselinePolicy.empty(),
            image_pull_secret_insight=insight,
        )
        descriptions = [finding.description for finding in result.assessment.findings]
        self.assertTrue(
            any("ExternalSecret glcr-secret-external" in desc for desc in descriptions)
        )
        self.assertIn(
            "Image pull secret glcr-secret", result.assessment.hypotheses[0].description
        )

    def test_deterministic_patterns_emit_findings_and_checks(self) -> None:
        expectations = [
            {
                "cluster_id": "pattern-probe",
                "reason": "probe_failure",
                "finding_fragment": "Readiness/liveness probe",
                "next_check_fragment": "Inspect pods in",
            },
            {
                "cluster_id": "pattern-scheduling",
                "reason": "failed_scheduling",
                "finding_fragment": "Pods remain Pending",
                "next_check_fragment": "Describe Pending pods",
            },
            {
                "cluster_id": "pattern-metrics",
                "reason": "missing_metrics",
                "finding_fragment": "HPA resource metrics",
                "next_check_fragment": "Collect HPA and metrics-server",
            },
            {
                "cluster_id": "pattern-pvc",
                "reason": "pvc_pending",
                "finding_fragment": "PersistentVolumeClaims in",
                "next_check_fragment": "Describe PVCs and related storageclasses",
            },
            {
                "cluster_id": "pattern-ingress",
                "reason": "ingress_timeout",
                "finding_fragment": "Ingress/backend timeouts",
                "next_check_fragment": "Inspect ingress endpoints",
            },
        ]
        for spec in expectations:
            with self.subTest(reason=spec["reason"]):
                result = self._pattern_assessment(spec["cluster_id"])
                self.assertIn(spec["reason"], result.pattern_reasons)
                descriptions = [finding.description for finding in result.assessment.findings]
                self.assertTrue(
                    any(spec["finding_fragment"] in desc for desc in descriptions)
                )
                check_descriptions = [check.description for check in result.assessment.next_evidence_to_collect]
                self.assertTrue(
                    any(spec["next_check_fragment"] in desc for desc in check_descriptions)
                )


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

    def test_health_assessment_artifact_contains_metadata(self) -> None:
        snapshot = self._make_snapshot("cluster-artifact")
        snapshots = {"cluster-artifact": snapshot}

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        target = HealthTarget(
            context="cluster-artifact",
            label="cluster-artifact",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="artifact",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(True, True, True, True, True, True),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )
        runner = HealthLoopRunner(
            config,
            available_contexts=snapshots.keys(),
            snapshot_collector=collector,
            comparison_fn=compare_snapshots,
            quiet=True,
            manual_drilldown_contexts=(),
            drilldown_collector=self._StubDrilldownCollector(),
        )
        assessments, _, _ = runner.execute()
        self.assertEqual(len(assessments), 1)
        artifact_dir = self.tmp_dir / "health" / "assessments"
        files = list(artifact_dir.glob("*.json"))
        self.assertTrue(files)
        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data.get("run_label"), config.run_label)
        self.assertEqual(data.get("cluster_id"), "cluster-artifact")
        assessment_data = data.get("assessment") or {}
        self.assertGreater(len(assessment_data.get("findings", [])), 0)
        self.assertGreater(len(assessment_data.get("hypotheses", [])), 0)
        self.assertTrue(assessment_data.get("recommended_action"))

    def test_config_allows_empty_peer_mappings_for_health_only(self) -> None:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = self.tmp_dir / "health-baseline.json"
        baseline_path.write_text(
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
        config_path = self.tmp_dir / "health-config.json"
        payload = {
            "run_label": "health-only",
            "targets": [
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                    "baseline_cohort": "fleet-production",
                }
            ],
            "peer_mappings": [],
            "manual_pairs": [],
            "baseline_policy_path": baseline_path.name,
        }
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        config = HealthRunConfig.load(config_path)
        self.assertEqual(config.peers, ())
        self.assertEqual(config.manual_pairs, ())

    def test_health_only_mode_skips_peer_comparison(self) -> None:
        snapshots = {
            "cluster-alpha": self._make_snapshot("alpha"),
        }

        def collector(context: str) -> ClusterSnapshot:
            return snapshots[context]

        comparison_called: list[bool] = []

        def compare_stub(a: ClusterSnapshot, b: ClusterSnapshot) -> ClusterComparison:
            comparison_called.append(True)
            return compare_snapshots(a, b)

        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
        )
        config = HealthRunConfig(
            run_label="health-only",
            output_dir=self.tmp_dir,
            collector_version="0.1",
            targets=(target,),
            peers=(),
            trigger_policy=TriggerPolicy(True, True, True, True, True, True),
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
        _, triggers, _ = runner.execute()
        self.assertFalse(comparison_called)
        self.assertEqual(triggers, [])
        self.assertIn("No peer mappings configured; running health-only mode.", runner._collection_messages)

    def test_manual_pairs_reference_unknown_cluster_fails(self) -> None:
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = self.tmp_dir / "health-baseline.json"
        baseline_path.write_text(
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
        config_path = self.tmp_dir / "health-config.json"
        payload = {
            "run_label": "health",
            "targets": [
                {
                    "context": "cluster-alpha",
                    "label": "cluster-alpha",
                    "cluster_class": "prod",
                    "cluster_role": "primary",
                    "baseline_cohort": "fleet-production",
                }
            ],
            "peer_mappings": [
                {"source": "cluster-alpha", "peers": ["cluster-alpha"]}
            ],
            "manual_pairs": [
                {"primary": "cluster-alpha", "secondary": "cluster-missing"}
            ],
            "baseline_policy_path": baseline_path.name,
        }
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Manual pair references unknown cluster"):
            HealthRunConfig.load(config_path)

    def test_drilldown_artifact_serialization(self) -> None:
        timestamp = datetime(2026, 1, 2, tzinfo=UTC)
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
