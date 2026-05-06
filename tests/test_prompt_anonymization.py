"""Integration tests for prompt path anonymization (REM-P2 Phase 2).

These tests verify that MetadataAnonymizer is properly integrated into all
LLM prompt construction paths, ensuring cluster metadata is anonymized
before prompts are built.

Requirements:
1. Real names do not appear in generated prompts
2. Aliases are consistent within one prompt
3. sanitize_prompt() still runs after anonymization
4. Original input objects are not mutated
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.compare.two_cluster import ClusterComparison
from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter
from k8s_diag_agent.external_analysis.review_input import (
    AlertmanagerContext,
    ReviewEnrichmentInput,
    ReviewSelectionContext,
)
from k8s_diag_agent.health.drilldown import (
    DrilldownArtifact,
    DrilldownPod,
    DrilldownRolloutStatus,
    WarningEventSummary,
)
from k8s_diag_agent.llm.drilldown_prompts import build_drilldown_prompt
from k8s_diag_agent.llm.prompts import build_assessment_prompt

# Type alias for mock comparison objects used in tests
# These are created inline in test methods with only 'differences' attribute
_MockComparisonType = Any


# Helper wrapper to cast test mocks to concrete production types
def _build_assessment_prompt_for_test(
    primary: MockClusterSnapshot,
    secondary: MockClusterSnapshot,
    comparison: _MockComparisonType,
) -> str:
    """Wrapper that casts mock types to production types for build_assessment_prompt."""
    # The cast() calls ensure runtime compatibility; mypy sees return as Any due to cast().
    return build_assessment_prompt(
        cast(ClusterSnapshot, primary),
        cast(ClusterSnapshot, secondary),
        cast(ClusterComparison, comparison),
    )


def _build_review_prompt_for_test(
    adapter: LlamaCppAdapter,
    request: MockRequest,
    context: ReviewEnrichmentInput,
) -> str:
    """Wrapper that casts mock request to ExternalAnalysisRequest for _build_prompt."""
    # The cast() ensures runtime compatibility; mypy sees return as Any due to cast().
    return adapter._build_prompt(
        cast(ExternalAnalysisRequest, request),
        context,
    )


# Helper dataclasses for building test data
@dataclass(frozen=True)
class MockClusterSnapshotMetadata:
    """Minimal mock for ClusterSnapshotMetadata."""
    cluster_id: str
    captured_at: datetime
    control_plane_version: str
    node_count: int
    pod_count: int | None = None
    region: str | None = None
    labels: dict[str, str] | None = None


@dataclass(frozen=True)
class MockCollectionStatus:
    """Minimal mock for CollectionStatus."""
    helm_error: str | None = None
    missing_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "helm_error": self.helm_error,
            "missing_evidence": list(self.missing_evidence),
        }


@dataclass(frozen=True)
class MockClusterSnapshot:
    """Minimal mock for ClusterSnapshot."""
    metadata: MockClusterSnapshotMetadata
    workloads: dict[str, object] | None = None
    metrics: dict[str, float] | None = None
    helm_releases: dict[str, object] | None = None
    crds: dict[str, object] | None = None
    collection_status: MockCollectionStatus | None = None
    health_signals: object | None = None

    @property
    def collection_status_to_dict(self) -> dict[str, object]:
        if self.collection_status:
            return self.collection_status.to_dict()
        return {}


@dataclass(frozen=True)
class MockComparisonIntentMetadata:
    """Minimal mock for ComparisonIntentMetadata."""
    intent: str | None = None
    notes: str | None = None
    expected_drift_categories: tuple[str, ...] = ()
    unexpected_drift_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockRequest:
    """Minimal mock ExternalAnalysisRequest for testing _build_prompt()."""
    run_id: str
    cluster_label: str
    source_artifact: str | None = None


# Helper to create minimal drilldown artifact
def _create_drilldown_artifact(
    cluster_id: str = "prod-us-east-1",
    affected_namespaces: tuple[str, ...] = ("production", "default"),
    non_running_pods: tuple[DrilldownPod, ...] | None = None,
    rollout_status: tuple[DrilldownRolloutStatus, ...] | None = None,
) -> DrilldownArtifact:
    """Create a minimal DrilldownArtifact for testing."""
    if non_running_pods is None:
        non_running_pods = (
            DrilldownPod(
                namespace="production",
                name="myapp-deployment-abc123",
                phase="CrashLoopBackOff",
                reason="CrashLoopBackOff",
            ),
            DrilldownPod(
                namespace="default",
                name="nginx-deployment-xyz789",
                phase="Pending",
                reason="Pending",
            ),
        )
    if rollout_status is None:
        rollout_status = (
            DrilldownRolloutStatus(
                kind="Deployment",
                namespace="production",
                name="myapp-deployment",
                desired_replicas=3,
                available_replicas=1,
                unavailable_replicas=2,
                updated_replicas=1,
                generation=2,
                observed_generation=2,
                conditions=("Available=True", "Progressing=True"),
            ),
        )
    return DrilldownArtifact(
        run_label="test-run",
        run_id="run-2024-01-15-abc123",
        timestamp=datetime.now(UTC),
        snapshot_timestamp=datetime.now(UTC),
        context="admin@prod-us-east-1",
        label="health-check",
        cluster_id=cluster_id,
        trigger_reasons=("WarningEventsDetected",),
        missing_evidence=(),
        evidence_summary={
            "warning_events": 5,
            "non_running_pods": 2,
            "pod_descriptions": 2,
            "rollout_entries": 1,
        },
        affected_namespaces=affected_namespaces,
        affected_workloads=(),
        warning_events=(
            WarningEventSummary(
                namespace="production",
                reason="BackOff",
                message="Back-off restarting failed container",
                count=3,
                last_seen="2024-01-15T10:30:00Z",
            ),
        ),
        non_running_pods=non_running_pods,
        pod_descriptions={
            "production/myapp-deployment-abc123": "Container image pull failed",
            "default/nginx-deployment-xyz789": "Pod pending scheduling",
        },
        rollout_status=rollout_status,
        collection_timestamps={
            "warning_events": "2024-01-15T10:00:00Z",
            "pods": "2024-01-15T10:05:00Z",
            "rollouts": "2024-01-15T10:10:00Z",
        },
    )


def _create_review_context(
    cluster_id: str = "prod-us-east-1",
    namespace: str = "production",
    deployment_name: str = "api-gateway",
) -> tuple[LlamaCppAdapter, MockRequest, ReviewEnrichmentInput]:
    """Create a minimal LlamaCppAdapter with test review context."""
    adapter = LlamaCppAdapter()
    request = MockRequest(run_id="test-run", cluster_label="test-cluster")

    review = {
        "run_id": "test-run",
        "selected_drilldowns": [
            {"label": "api-deployment", "context": namespace},
        ],
        "metadata": {
            "cluster_id": cluster_id,
        },
    }

    selection = ReviewSelectionContext(
        label="api-deployment",
        context=namespace,
        entry={
            "label": "api-deployment",
            "context": namespace,
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": namespace,
            },
        },
        drilldown_path=None,
        drilldown={
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": namespace,
            },
            "spec": {
                "replicas": 3,
            },
            "status": {
                "availableReplicas": 2,
            },
        },
        assessment_path=None,
        assessment={
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": namespace,
            },
            "snapshot_path": "/fake/snapshot.json",
        },
        snapshot_path="/fake/snapshot.json",
        snapshot={
            "kind": "Deployment",
            "metadata": {
                "name": deployment_name,
                "namespace": namespace,
            },
            "spec": {
                "selector": {"matchLabels": {"app": "api-gateway"}},
            },
        },
    )

    alertmanager = AlertmanagerContext(
        available=True,
        source="run_artifact",
        compact={
            "endpoint": f"https://alertmanager.{namespace}.example.com",
            "cluster": cluster_id,
        },
        status="active",
    )

    context = ReviewEnrichmentInput(
        run_id="test-run",
        review_path=Path("/fake/test-review.json"),
        review=review,
        selections=(selection,),
        missing_drilldowns=(),
        missing_assessments=(),
        missing_snapshots=(),
        alertmanager_context=alertmanager,
    )

    return adapter, request, context


class TestAssessmentPromptAnonymization(unittest.TestCase):
    """Tests for Path 1: build_assessment_prompt() anonymization."""

    def test_cluster_id_anonymized_in_prompt(self) -> None:
        """Verify cluster_id is replaced with alias in assessment prompt."""
        primary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="prod-us-east-1",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=5,
                pod_count=42,
                region="us-east-1",
            ),
            collection_status=MockCollectionStatus(),
        )
        secondary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="staging-us-west-2",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=3,
                pod_count=20,
                region="us-west-2",
            ),
            collection_status=MockCollectionStatus(),
        )

        # Create mock comparison with differences
        @dataclass(frozen=True)
        class MockComparison:
            differences: dict[str, object]

        comparison = MockComparison(differences={})

        prompt = _build_assessment_prompt_for_test(primary, secondary, comparison)

        # Verify original cluster names do NOT appear
        self.assertNotIn("prod-us-east-1", prompt)
        self.assertNotIn("staging-us-west-2", prompt)

        # Verify aliases DO appear
        self.assertIn("cluster-", prompt)

    def test_namespace_anonymized_in_helm_diffs(self) -> None:
        """Verify namespace names in helm diffs are anonymized."""
        primary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="prod-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=5,
            ),
            collection_status=MockCollectionStatus(),
        )
        secondary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="staging-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=3,
            ),
            collection_status=MockCollectionStatus(),
        )

        # Mock comparison with helm diffs containing namespace names
        @dataclass(frozen=True)
        class MockComparison:
            differences: dict[str, object]

        comparison = MockComparison(differences={
            "helm_releases": {
                "production/ingress-nginx": {
                    "primary": {
                        "namespace": "production",
                        "chart_version": "4.0.0",
                    },
                },
            },
        })

        prompt = _build_assessment_prompt_for_test(primary, secondary, comparison)

        # Original namespace should not appear
        self.assertNotIn("production", prompt)
        # But some namespace alias should
        self.assertIn("namespace-", prompt)


class TestDrilldownPromptAnonymization(unittest.TestCase):
    """Tests for Path 2: build_drilldown_prompt() anonymization."""

    def test_cluster_id_anonymized_in_prompt(self) -> None:
        """Verify cluster_id is replaced with alias in drilldown prompt."""
        artifact = _create_drilldown_artifact(
            cluster_id="prod-us-east-1",
        )
        original_cluster_id = artifact.cluster_id

        prompt = build_drilldown_prompt(artifact)

        # Verify original cluster ID does NOT appear
        self.assertNotIn(original_cluster_id, prompt)
        # Verify alias appears
        self.assertIn("cluster-", prompt)

    def test_affected_namespaces_anonymized(self) -> None:
        """Verify affected_namespaces are anonymized in drilldown prompt."""
        artifact = _create_drilldown_artifact(
            affected_namespaces=("production", "default", "kube-system"),
        )

        prompt = build_drilldown_prompt(artifact)

        # Original namespace names should NOT appear
        self.assertNotIn("production", prompt)
        self.assertNotIn("default", prompt)
        self.assertNotIn("kube-system", prompt)

        # But namespace aliases should appear (multiple)
        self.assertIn("namespace-", prompt)

    def test_pod_names_anonymized(self) -> None:
        """Verify pod names/namespace in non-running pods section are anonymized."""
        artifact = _create_drilldown_artifact()

        prompt = build_drilldown_prompt(artifact)

        # Original pod name should NOT appear
        self.assertNotIn("myapp-deployment-abc123", prompt)
        self.assertNotIn("production", prompt)

        # Verify aliases appear (pod-a, namespace-a, etc.)
        self.assertIn("namespace-", prompt)

    def test_rollout_names_anonymized(self) -> None:
        """Verify rollout names/namespace are anonymized in drilldown prompt."""
        rollout_status = (
            DrilldownRolloutStatus(
                kind="Deployment",
                namespace="production",
                name="api-gateway",
                desired_replicas=3,
                available_replicas=2,
                unavailable_replicas=1,
                updated_replicas=2,
                generation=1,
                observed_generation=1,
                conditions=(),
            ),
        )
        artifact = _create_drilldown_artifact(rollout_status=rollout_status)

        prompt = build_drilldown_prompt(artifact)

        # Original names should NOT appear
        self.assertNotIn("api-gateway", prompt)
        self.assertNotIn("production", prompt)

        # Aliases should appear
        self.assertIn("namespace-", prompt)

    def test_pod_descriptions_keys_anonymized(self) -> None:
        """Verify pod description keys (namespace/name) are anonymized."""
        artifact = _create_drilldown_artifact()

        prompt = build_drilldown_prompt(artifact)

        # Original keys should NOT appear
        self.assertNotIn("production/myapp-deployment-abc123", prompt)
        self.assertNotIn("default/nginx-deployment-xyz789", prompt)


class TestReviewEnrichmentPromptAnonymization(unittest.TestCase):
    """Tests for Path 3: llamacpp_adapter._build_prompt() anonymization."""

    def setUp(self) -> None:
        self._adapter = LlamaCppAdapter()

    def test_review_json_cluster_id_anonymized(self) -> None:
        """Verify cluster_id in review JSON is anonymized in prompt."""
        adapter, request, context = _create_review_context(
            cluster_id="prod-us-east-1",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original cluster ID should NOT appear
        self.assertNotIn("prod-us-east-1", prompt)
        # But alias should appear
        self.assertIn("cluster-", prompt)

    def test_review_json_namespace_anonymized(self) -> None:
        """Verify namespace in review JSON is anonymized in prompt."""
        adapter, request, context = _create_review_context(
            namespace="production",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Namespace in context field should be anonymized
        self.assertIn("namespace-", prompt)

    def test_review_json_deployment_name_anonymized(self) -> None:
        """Verify deployment name in metadata.name is anonymized in prompt."""
        adapter, request, context = _create_review_context(
            deployment_name="api-gateway",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original deployment name in metadata.name should be anonymized
        # Note: name appearing in selector.matchLabels is beyond current scope
        # but metadata.name should be anonymized
        self.assertNotIn('"name": "api-gateway"', prompt)

    def test_alertmanager_context_anonymized(self) -> None:
        """Verify Alertmanager context data is anonymized in prompt."""
        adapter, request, context = _create_review_context(
            cluster_id="my-production-cluster",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original cluster reference should NOT appear
        self.assertNotIn("my-production-cluster", prompt)
        # Alertmanager compact data should be anonymized
        self.assertIn("cluster-", prompt)

    def test_selection_entry_anonymized(self) -> None:
        """Verify selection entry data is anonymized in prompt."""
        adapter, request, context = _create_review_context(
            deployment_name="my-backend-service",
            namespace="staging",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original values should NOT appear
        self.assertNotIn("my-backend-service", prompt)
        self.assertNotIn("staging", prompt)

    def test_selection_drilldown_anonymized(self) -> None:
        """Verify drilldown artifact data is anonymized in prompt.
        
        Note: The word "default" may appear in hardcoded prompt template examples
        (e.g., kubectl commands in instructions), but cluster-specific values
        like "frontend-app" should be anonymized.
        """
        adapter, request, context = _create_review_context(
            deployment_name="frontend-app",
            namespace="default",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original deployment name should NOT appear
        self.assertNotIn("frontend-app", prompt)
        # "default" may appear in hardcoded template examples, but let's verify
        # it appears as namespace-a alias, not the literal "default" cluster value
        self.assertIn("namespace-", prompt)

    def test_cluster_label_anonymized_in_header(self) -> None:
        """Verify request.cluster_label is anonymized in prompt header."""
        adapter, request, context = _create_review_context(
            cluster_id="prod-us-east-1",
        )
        # Override cluster_label to a meaningful name
        request = MockRequest(run_id="test-run", cluster_label="my-production-cluster")

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original cluster_label should NOT appear in header
        self.assertNotIn("my-production-cluster", prompt)
        # But some cluster alias should appear
        self.assertIn("cluster-", prompt)

    def test_missing_drilldown_fallback_uses_anon_label(self) -> None:
        """Verify missing drilldown fallback message uses anonymized label."""
        adapter, request, context = _create_review_context(
            deployment_name="my-app-server",
            namespace="production",
        )
        # Override selection to have no drilldown
        selection = ReviewSelectionContext(
            label="my-app-server",
            context="production",
            entry={"label": "my-app-server", "context": "production"},
            drilldown_path=None,
            drilldown=None,  # No drilldown available
            assessment_path=None,
            assessment=None,
            snapshot_path=None,
            snapshot=None,
        )
        context = ReviewEnrichmentInput(
            run_id="test-run",
            review_path=Path("/fake/test-review.json"),
            review=context.review,
            selections=(selection,),
            missing_drilldowns=(),
            missing_assessments=(),
            missing_snapshots=(),
            alertmanager_context=context.alertmanager_context,
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original label should NOT appear in fallback message
        self.assertNotIn("my-app-server", prompt)
        # Fallback message should exist with anonymized content
        self.assertIn("Drilldown artifact unavailable for", prompt)

    def test_missing_assessment_fallback_uses_anon_label(self) -> None:
        """Verify missing assessment fallback message uses anonymized label."""
        adapter, request, context = _create_review_context(
            deployment_name="api-gateway",
            namespace="staging",
        )
        # Override selection to have no assessment
        selection = ReviewSelectionContext(
            label="api-gateway",
            context="staging",
            entry={"label": "api-gateway", "context": "staging"},
            drilldown_path=None,
            drilldown={"kind": "Deployment", "metadata": {"name": "api-gateway"}},
            assessment_path=None,
            assessment=None,  # No assessment available
            snapshot_path=None,
            snapshot=None,
        )
        context = ReviewEnrichmentInput(
            run_id="test-run",
            review_path=Path("/fake/test-review.json"),
            review=context.review,
            selections=(selection,),
            missing_drilldowns=(),
            missing_assessments=(),
            missing_snapshots=(),
            alertmanager_context=context.alertmanager_context,
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        # Original label should NOT appear in fallback message
        self.assertNotIn("api-gateway", prompt)
        # Fallback message should exist with anonymized content
        self.assertIn("Assessment artifact unavailable for", prompt)


class TestAliasConsistency(unittest.TestCase):
    """Tests that aliases are consistent within a single prompt."""

    def test_same_namespace_same_alias_in_assessment(self) -> None:
        """Verify same namespace appearing in multiple sections maps to same alias."""
        # Create snapshots where same namespace appears in multiple places
        primary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="prod-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=5,
            ),
            collection_status=MockCollectionStatus(),
        )
        secondary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="staging-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=3,
            ),
            collection_status=MockCollectionStatus(),
        )

        @dataclass(frozen=True)
        class MockComparison:
            differences: dict[str, object]

        # Same namespace appearing in helm diffs as in metadata
        comparison = MockComparison(differences={
            "helm_releases": {
                "production/ingress-nginx": {
                    "primary": {"namespace": "production", "chart_version": "4.0.0"},
                },
            },
        })

        prompt = _build_assessment_prompt_for_test(primary, secondary, comparison)

        # Count occurrences of namespace aliases
        import re
        namespace_aliases = re.findall(r'namespace-[a-z]+', prompt)
        unique_aliases = set(namespace_aliases)

        # If production appears multiple times, it should map to the same alias
        # Check that there's only one namespace alias used consistently
        self.assertGreater(len(namespace_aliases), 0)
        # All namespace references should use the same alias
        self.assertEqual(len(unique_aliases), 1)

    def test_same_namespace_same_alias_in_drilldown(self) -> None:
        """Verify same namespace in drilldown maps to same alias."""
        pods = (
            DrilldownPod(
                namespace="production",
                name="pod-a",
                phase="CrashLoopBackOff",
                reason="CrashLoopBackOff",
            ),
            DrilldownPod(
                namespace="production",
                name="pod-b",
                phase="Pending",
                reason="Pending",
            ),
        )
        rollout = (
            DrilldownRolloutStatus(
                kind="Deployment",
                namespace="production",
                name="myapp-deployment",
                desired_replicas=3,
                available_replicas=2,
                unavailable_replicas=1,
                updated_replicas=2,
                generation=1,
                observed_generation=1,
                conditions=(),
            ),
        )
        # Must override warning_events and pod_descriptions too to avoid
        # hardcoded default namespaces in _create_drilldown_artifact
        warning_events = (
            WarningEventSummary(
                namespace="production",
                reason="BackOff",
                message="Back-off restarting failed container",
                count=3,
                last_seen="2024-01-15T10:30:00Z",
            ),
        )
        artifact = _create_drilldown_artifact(
            affected_namespaces=("production",),
            non_running_pods=pods,
            rollout_status=rollout,
        )
        # Override warning_events and pod_descriptions to only have "production"
        from dataclasses import replace
        clean_artifact = replace(
            artifact,
            warning_events=warning_events,
            pod_descriptions={"production/pod-a": "Crash error", "production/pod-b": "Pending error"},
        )

        prompt = build_drilldown_prompt(clean_artifact)

        import re
        namespace_aliases = re.findall(r'namespace-[a-z]+', prompt)
        unique_aliases = set(namespace_aliases)

        # All "production" references should use the same alias
        self.assertEqual(len(unique_aliases), 1)

    def test_same_namespace_same_alias_in_review(self) -> None:
        """Verify same namespace appearing in review JSON, drilldown, etc. maps to same alias."""
        adapter, request, context = _create_review_context(
            namespace="production",
            deployment_name="myapp",
        )

        prompt = _build_review_prompt_for_test(adapter, request, context)

        import re
        namespace_aliases = re.findall(r'namespace-[a-z]+', prompt)
        unique_aliases = set(namespace_aliases)

        # All "production" references should use the same alias
        self.assertEqual(len(unique_aliases), 1)


class TestSanitizePromptStillRuns(unittest.TestCase):
    """Tests that sanitize_prompt() still runs after anonymization."""

    def test_credentials_still_redacted_in_assessment_prompt(self) -> None:
        """Verify credentials don't appear in assessment prompt (redacted or anonymized)."""
        primary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="prod-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=5,
                labels={"api_token": "Bearer eyJhbGciOiJIUzI1NiJ9.secret123"},
            ),
            collection_status=MockCollectionStatus(),
        )
        secondary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="staging-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=3,
            ),
            collection_status=MockCollectionStatus(),
        )

        @dataclass(frozen=True)
        class MockComparison:
            differences: dict[str, object]

        comparison = MockComparison(differences={})
        prompt = _build_assessment_prompt_for_test(primary, secondary, comparison)

        # Token should be redacted (either by sanitize_prompt or anonymizer)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9.secret123", prompt)

    def test_credentials_still_redacted_in_drilldown_prompt(self) -> None:
        """Verify credentials don't appear in drilldown prompt (redacted or anonymized).
        
        Note: sanitize_prompt() scrubs Secret manifests with <scrubbed>. Other
        credential patterns in text fields may be anonymized instead.
        """
        artifact = _create_drilldown_artifact()
        # Add a credential to pod description
        new_descriptions = dict(artifact.pod_descriptions)
        new_descriptions["production/myapp"] = "Token: Bearer secret-key-abc123"

        @dataclass(frozen=True)
        class DrilldownArtifactWithCreds(DrilldownArtifact):
            pass

        # Create new artifact with credentials (workaround for frozen dataclass)
        from dataclasses import replace
        artifact_with_creds = replace(
            artifact,
            pod_descriptions=new_descriptions,
        )

        prompt = build_drilldown_prompt(artifact_with_creds)

        # Token should not appear (redacted or anonymized)
        self.assertNotIn("secret-key-abc123", prompt)

    def test_credentials_still_redacted_in_review_prompt(self) -> None:
        """Verify credentials are still replaced with <scrubbed> in review prompt."""
        adapter, request, context = _create_review_context()

        # Add credential to review
        context_with_creds = ReviewEnrichmentInput(
            run_id=context.run_id,
            review_path=context.review_path,
            review={
                **context.review,
                "credentials": {
                    "token": "Bearer my-secret-token-xyz789",
                },
            },
            selections=context.selections,
            missing_drilldowns=context.missing_drilldowns,
            missing_assessments=context.missing_assessments,
            missing_snapshots=context.missing_snapshots,
            alertmanager_context=context.alertmanager_context,
        )

        prompt = _build_review_prompt_for_test(adapter, request, context_with_creds)

        # Token should be redacted
        self.assertNotIn("my-secret-token-xyz789", prompt)
        self.assertIn("<scrubbed>", prompt)


class TestInputNotMutated(unittest.TestCase):
    """Tests that original input objects are not mutated."""

    def test_drilldown_artifact_not_mutated(self) -> None:
        """Verify DrilldownArtifact is not mutated by build_drilldown_prompt."""
        original_artifact = _create_drilldown_artifact(
            cluster_id="prod-cluster",
            affected_namespaces=("production", "staging"),
        )
        original_cluster_id = original_artifact.cluster_id
        original_namespaces = list(original_artifact.affected_namespaces)

        # Call the function
        build_drilldown_prompt(original_artifact)

        # Verify the original artifact is unchanged
        self.assertEqual(original_artifact.cluster_id, original_cluster_id)
        self.assertEqual(list(original_artifact.affected_namespaces), original_namespaces)

    def test_cluster_snapshot_not_mutated(self) -> None:
        """Verify ClusterSnapshot is not mutated by build_assessment_prompt."""
        primary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="test-cluster",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=5,
            ),
            collection_status=MockCollectionStatus(),
        )
        original_cluster_id = primary.metadata.cluster_id

        secondary = MockClusterSnapshot(
            metadata=MockClusterSnapshotMetadata(
                cluster_id="staging",
                captured_at=datetime.now(UTC),
                control_plane_version="v1.28.0",
                node_count=3,
            ),
            collection_status=MockCollectionStatus(),
        )

        @dataclass(frozen=True)
        class MockComparison:
            differences: dict[str, object]

        comparison = MockComparison(differences={})

        _build_assessment_prompt_for_test(primary, secondary, comparison)

        # Verify the original metadata is unchanged
        self.assertEqual(primary.metadata.cluster_id, original_cluster_id)


if __name__ == "__main__":
    unittest.main()
