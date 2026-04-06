import unittest
from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    CRDRecord,
    HelmReleaseRecord,
)
from k8s_diag_agent.compare.two_cluster import compare_snapshots
from k8s_diag_agent.feedback.models import (
    AssessmentArtifact,
    FailureMode,
    ProposedImprovement,
    RunArtifact,
    SnapshotPairArtifact,
    ValidationResult,
)
from k8s_diag_agent.feedback.runner import _serialize_run_artifact
from k8s_diag_agent.models import ConfidenceLevel


def _text_dict_strategy() -> st.SearchStrategy[dict[str, str]]:
    return st.dictionaries(st.text(min_size=1), st.text(min_size=1), max_size=3)


@st.composite
def _metadata_strategy(draw: st.DrawFn) -> ClusterSnapshotMetadata:
    labels = draw(st.dictionaries(st.text(min_size=1), st.text(min_size=1), max_size=2))
    return ClusterSnapshotMetadata(
        cluster_id=draw(st.text(min_size=1)),
        captured_at=draw(st.datetimes(timezones=st.just(UTC))),
        control_plane_version=draw(st.text(min_size=1)),
        node_count=draw(st.integers(min_value=0, max_value=10)),
        pod_count=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=50))),
        region=draw(st.one_of(st.none(), st.text(min_size=1))),
        labels=labels,
    )


@st.composite
def _helm_releases_strategy(draw: st.DrawFn) -> dict[str, HelmReleaseRecord]:
    releases: dict[str, HelmReleaseRecord] = {}
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        name = draw(st.text(min_size=1))
        namespace = draw(st.text(min_size=1))
        chart_version = draw(st.text(min_size=1))
        chart = f"{name}-{draw(st.text(min_size=1))}"
        release = HelmReleaseRecord(
            name=name,
            namespace=namespace,
            chart=chart,
            chart_version=chart_version,
            app_version=draw(st.one_of(st.none(), st.text(min_size=1))),
        )
        releases[release.key] = release
    return releases


@st.composite
def _crd_strategy(draw: st.DrawFn) -> dict[str, CRDRecord]:
    crds: dict[str, CRDRecord] = {}
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        name = draw(st.text(min_size=1))
        served = tuple(draw(st.lists(st.text(min_size=1), min_size=1, max_size=3)))
        storage = draw(st.one_of(st.none(), st.text(min_size=1)))
        record = CRDRecord(name=name, served_versions=served, storage_version=storage)
        crds[record.name] = record
    return crds


@st.composite
def _collection_status_strategy(draw: st.DrawFn) -> CollectionStatus:
    missing = tuple(draw(st.lists(st.text(min_size=1), max_size=3)))
    return CollectionStatus(
        helm_error=draw(st.one_of(st.none(), st.text(min_size=1))),
        missing_evidence=missing,
    )


@st.composite
def _workloads_strategy(draw: st.DrawFn) -> dict[str, object]:
    return draw(st.dictionaries(st.text(min_size=1), st.one_of(st.text(), st.integers(), st.booleans()), max_size=3))


@st.composite
def _metrics_strategy(draw: st.DrawFn) -> dict[str, float]:
    return draw(
        st.dictionaries(
            st.text(min_size=1),
            st.floats(allow_nan=False, allow_infinity=False),
            max_size=4,
        )
    )


@st.composite
def _snapshot_strategy(draw: st.DrawFn) -> ClusterSnapshot:
    return ClusterSnapshot(
        metadata=draw(_metadata_strategy()),
        workloads=draw(_workloads_strategy()),
        metrics=draw(_metrics_strategy()),
        helm_releases=draw(_helm_releases_strategy()),
        crds=draw(_crd_strategy()),
        collection_status=draw(_collection_status_strategy()),
    )


@st.composite
def _snapshot_pair_strategy(draw: st.DrawFn) -> SnapshotPairArtifact:
    return SnapshotPairArtifact(
        primary_snapshot_id=draw(st.text(min_size=1)),
        primary_snapshot_path=draw(st.text(min_size=1)),
        comparison_summary=draw(st.dictionaries(st.text(min_size=1), st.integers(min_value=0, max_value=5), max_size=3)),
        secondary_snapshot_id=draw(st.one_of(st.none(), st.text(min_size=1))),
        secondary_snapshot_path=draw(st.one_of(st.none(), st.text(min_size=1))),
        status=draw(st.text(min_size=1)),
        missing_evidence=draw(st.lists(st.text(min_size=1), max_size=3)),
    )


@st.composite
def _assessment_strategy(draw: st.DrawFn) -> AssessmentArtifact:
    return AssessmentArtifact(
        assessment_id=draw(st.text(min_size=1)),
        schema_version=draw(st.text(min_size=1)),
        assessment=draw(_text_dict_strategy()),
        overall_confidence=draw(st.one_of(st.none(), st.sampled_from([level.value for level in ConfidenceLevel]))),
    )


@st.composite
def _validation_result_strategy(draw: st.DrawFn) -> ValidationResult:
    failure = draw(st.one_of(st.none(), st.sampled_from(list(FailureMode))))
    return ValidationResult(
        name=draw(st.text(min_size=1)),
        passed=draw(st.booleans()),
        errors=draw(st.lists(st.text(min_size=1), max_size=3)),
        checked_at=draw(st.datetimes(timezones=st.just(UTC))),
        failure_mode=failure,
    )


@st.composite
def _improvement_strategy(draw: st.DrawFn) -> ProposedImprovement:
    return ProposedImprovement(
        id=draw(st.text(min_size=1)),
        description=draw(st.text(min_size=1)),
        target=draw(st.text(min_size=1)),
        owner=draw(st.one_of(st.none(), st.text(min_size=1))),
        confidence=draw(st.one_of(st.none(), st.sampled_from(list(ConfidenceLevel)))),
        rationale=draw(st.one_of(st.none(), st.text(min_size=1))),
        related_failure_modes=draw(st.lists(st.sampled_from(list(FailureMode)), max_size=2)),
    )


@st.composite
def _run_artifact_strategy(draw: st.DrawFn) -> RunArtifact:
    return RunArtifact(
        run_id=draw(st.text(min_size=1)),
        timestamp=draw(st.datetimes(timezones=st.just(UTC))),
        context_name=draw(st.one_of(st.none(), st.text(min_size=1))),
        comparison_intent=draw(st.one_of(st.none(), st.text(min_size=1))),
        comparison_notes=draw(st.one_of(st.none(), st.text(min_size=1))),
        expected_drift_categories=tuple(draw(st.lists(st.text(min_size=1), max_size=3))),
        unexpected_drift_categories=tuple(draw(st.lists(st.text(min_size=1), max_size=3))),
        collector_version=draw(st.text(min_size=1)),
        collection_status=draw(st.text(min_size=1)),
        snapshot_pair=draw(_snapshot_pair_strategy()),
        comparison_summary=draw(st.dictionaries(st.text(min_size=1), st.integers(min_value=0, max_value=5), max_size=3)),
        missing_evidence=draw(st.lists(st.text(min_size=1), max_size=3)),
        assessment=draw(st.one_of(st.none(), _assessment_strategy())),
        validation_results=draw(st.lists(_validation_result_strategy(), max_size=3)),
        failure_modes=draw(st.lists(st.sampled_from(list(FailureMode)), max_size=3)),
        proposed_improvements=draw(st.lists(_improvement_strategy(), max_size=2)),
        notes=draw(st.one_of(st.none(), st.text(min_size=1))),
    )


class SnapshotPropertyTests(unittest.TestCase):
    @settings(max_examples=25, deadline=None)
    @given(snapshot=_snapshot_strategy())
    def test_roundtrip_serialization_preserves_snapshot(self, snapshot: ClusterSnapshot) -> None:
        restored = ClusterSnapshot.from_dict(snapshot.to_dict())
        self.assertEqual(restored, snapshot)


class FeedbackArtifactPropertyTests(unittest.TestCase):
    @settings(max_examples=25, deadline=None)
    @given(artifact=_run_artifact_strategy())
    def test_feedback_serialization_keeps_nested_metadata(self, artifact: RunArtifact) -> None:
        serialized = _serialize_run_artifact(artifact)
        self.assertEqual(serialized["run_id"], artifact.run_id)
        self.assertEqual(serialized.get("comparison_intent"), artifact.comparison_intent)
        self.assertEqual(serialized.get("comparison_notes"), artifact.comparison_notes)
        self.assertEqual(
            serialized.get("expected_drift_categories"), artifact.expected_drift_categories
        )
        self.assertEqual(
            serialized.get("unexpected_drift_categories"), artifact.unexpected_drift_categories
        )
        self.assertEqual(serialized["timestamp"], artifact.timestamp.isoformat())
        self.assertEqual(
            serialized["snapshot_pair"]["primary_snapshot_id"], artifact.snapshot_pair.primary_snapshot_id
        )
        self.assertEqual(len(serialized["validation_results"]), len(artifact.validation_results))
        for expected, actual in zip(artifact.validation_results, serialized["validation_results"]):
            self.assertEqual(actual["checked_at"], expected.checked_at.isoformat())
            if expected.failure_mode is not None:
                self.assertEqual(actual["failure_mode"], expected.failure_mode.value)


class ComparisonPropertyTests(unittest.TestCase):
    BASE_METADATA = ClusterSnapshotMetadata(
        cluster_id="base",
        captured_at=datetime(2025, 1, 1, tzinfo=UTC),
        control_plane_version="v1.25",
        node_count=1,
    )

    @settings(max_examples=25, deadline=None)
    @given(
        primary_metrics=_metrics_strategy(),
        secondary_metrics=_metrics_strategy(),
        primary_helm=_helm_releases_strategy(),
        secondary_helm=_helm_releases_strategy(),
        primary_crds=_crd_strategy(),
        secondary_crds=_crd_strategy(),
    )
    def test_comparison_only_reports_actual_differences(
        self,
        primary_metrics: dict[str, float],
        secondary_metrics: dict[str, float],
        primary_helm: dict[str, HelmReleaseRecord],
        secondary_helm: dict[str, HelmReleaseRecord],
        primary_crds: dict[str, CRDRecord],
        secondary_crds: dict[str, CRDRecord],
    ) -> None:
        primary = ClusterSnapshot(
            metadata=self.BASE_METADATA,
            metrics=primary_metrics,
            helm_releases=primary_helm,
            crds=primary_crds,
        )
        secondary = ClusterSnapshot(
            metadata=self.BASE_METADATA,
            metrics=secondary_metrics,
            helm_releases=secondary_helm,
            crds=secondary_crds,
        )
        comparison = compare_snapshots(primary, secondary)
        metric_diffs = comparison.differences.get("metrics", {})
        union_metrics = set(primary_metrics) | set(secondary_metrics)
        for key in metric_diffs:
            self.assertIn(key, union_metrics)
            self.assertNotEqual(primary_metrics.get(key), secondary_metrics.get(key))
        for key in union_metrics:
            if primary_metrics.get(key) != secondary_metrics.get(key):
                self.assertIn(key, metric_diffs)
        helm_diff = comparison.differences.get("helm_releases", {})
        helm_union = set(primary_helm) | set(secondary_helm)
        self.assertLessEqual(set(helm_diff), helm_union)
        for key in helm_diff:
            self.assertNotEqual(primary_helm.get(key), secondary_helm.get(key))
        crd_diff = comparison.differences.get("crds", {})
        crd_union = set(primary_crds) | set(secondary_crds)
        self.assertLessEqual(set(crd_diff), crd_union)
        for key in crd_diff:
            self.assertNotEqual(primary_crds.get(key), secondary_crds.get(key))
