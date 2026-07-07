"""Unit tests for Alertmanager service heuristic deduplication by backing pods.

Tests cover:
- Grouping sources by backing pod UIDs from EndpointSlices
- Fallback to endpoint-based grouping when EndpointSlices unavailable
- Mocking kubectl calls for controlled test scenarios

Note: Backing pod identity extraction tests are in test_alertmanager_backing_identity.py.
"""

from __future__ import annotations

from unittest.mock import patch

from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    BackingPodIdentity,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers import (
    DedupKey,
    _build_backing_pod_cache,
    _group_by_backing_pods,
    deduplicate_service_heuristic_sources,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceOrigin,
)


class TestBuildBackingPodCache:
    """Tests for _build_backing_pod_cache function."""

    def test_builds_cache_for_all_sources(self) -> None:
        """Should build cache entries for all unique namespace/name pairs."""
        sources = [
            AlertmanagerSource(
                source_id="service:monitoring/alertmanager-operated",
                endpoint="http://alertmanager-operated.monitoring:9093",
                namespace="monitoring",
                name="alertmanager-operated",
                origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            ),
            AlertmanagerSource(
                source_id="service:monitoring/kube-prometheus-stack-alertmanager",
                endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
                namespace="monitoring",
                name="kube-prometheus-stack-alertmanager",
                origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            ),
        ]
        
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0", "pod-uid-1"}),
            name_set=frozenset({"monitoring/alertmanager-0", "monitoring/alertmanager-1"}),
            service_names=("alertmanager-operated",),
        )
        
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity',
            return_value=mock_identity
        ) as mock_get_identity:
            cache = _build_backing_pod_cache(sources)
            
            # Should have 2 entries (one per unique namespace/name)
            assert len(cache) == 2
            assert "monitoring/alertmanager-operated" in cache
            assert "monitoring/kube-prometheus-stack-alertmanager" in cache
        
        # Should call _get_service_backing_identity for each unique namespace/name pair
        assert mock_get_identity.call_count == 2

    def test_deduplicates_cache_keys(self) -> None:
        """Should not query same namespace/name pair twice."""
        sources = [
            AlertmanagerSource(
                source_id="service:monitoring/svc-a",
                endpoint="http://svc-a.monitoring:9093",
                namespace="monitoring",
                name="svc-a",
                origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            ),
            AlertmanagerSource(
                source_id="service:monitoring/svc-b",
                endpoint="http://svc-b.monitoring:9093",
                namespace="monitoring",
                name="svc-a",  # Same name as above
                origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            ),
        ]
        
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            service_names=("svc-a",),
        )
        
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity',
            return_value=mock_identity
        ) as mock_get_identity:
            cache = _build_backing_pod_cache(sources)
            
            # Should only have 1 entry (same namespace/name)
            assert len(cache) == 1
            # Should only call _get_service_backing_identity once
            assert mock_get_identity.call_count == 1


class TestGroupByBackingPods:
    """Tests for _group_by_backing_pods function."""

    def test_groups_sources_by_same_pod_uids(self) -> None:
        """Should group sources that share the same backing pod UIDs."""
        source_a = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        pod_uids = frozenset({"pod-uid-0", "pod-uid-1"})
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=pod_uids,
            service_names=("alertmanager-operated",),
        )
        backing_pod_cache = {
            "monitoring/alertmanager-operated": mock_identity,
            "monitoring/kube-prometheus-stack-alertmanager": mock_identity,
        }
        
        groups = _group_by_backing_pods(sources, backing_pod_cache)
        
        # Should have 1 group with 2 sources (same backing pods)
        assert len(groups) == 1
        # Key is namespaced: ("pods", tuple of sorted UIDs)
        pod_key: DedupKey = ("pods", tuple(sorted(pod_uids)))
        assert pod_key in groups
        assert len(groups[pod_key][1]) == 2

    def test_separates_sources_with_different_pods(self) -> None:
        """Should separate sources with different backing pod UIDs."""
        source_a = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-a",
            endpoint="http://alertmanager-a.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-a",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-b",
            endpoint="http://alertmanager-b.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-b",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        backing_pod_cache = {
            "monitoring/alertmanager-a": BackingPodIdentity(
                kind="backing_pods",
                uid_set=frozenset({"pod-uid-a"}),
                service_names=("alertmanager-a",),
            ),
            "monitoring/alertmanager-b": BackingPodIdentity(
                kind="backing_pods",
                uid_set=frozenset({"pod-uid-b"}),
                service_names=("alertmanager-b",),
            ),
        }
        
        groups = _group_by_backing_pods(sources, backing_pod_cache)
        
        # Should have 2 groups (different backing pods)
        assert len(groups) == 2

    def test_fallback_to_endpoint_when_pod_info_unavailable(self) -> None:
        """Should fall back to endpoint-based grouping when pod info unavailable."""
        source_a = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-a",
            endpoint="http://alertmanager-a.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-a",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-b",
            endpoint="http://alertmanager-a.monitoring:9093",  # Same endpoint
            namespace="monitoring",
            name="alertmanager-b",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        backing_pod_cache = {
            "monitoring/alertmanager-a": None,  # Unavailable
            "monitoring/alertmanager-b": None,  # Unavailable
        }
        
        groups = _group_by_backing_pods(sources, backing_pod_cache)
        
        # Should have 1 group with 2 sources (same endpoint, pod info unavailable)
        assert len(groups) == 1
        # The key should be ("endpoint", "alertmanager-a.monitoring:9093")
        endpoint_key: DedupKey = ("endpoint", "alertmanager-a.monitoring:9093")
        assert endpoint_key in groups
        assert len(groups[endpoint_key][1]) == 2

    def test_fallback_keeps_different_endpoints_separate_when_pod_info_unavailable(self) -> None:
        """Regression test: Different endpoints should remain separate when pod info unavailable.
        
        This tests the fix for the fallback collision bug where all endpoint-fallback
        groups would incorrectly merge under the same key.
        """
        source_a = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-a",
            endpoint="http://alertmanager-a.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-a",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-b",
            endpoint="http://alertmanager-b.monitoring:9093",  # Different endpoint
            namespace="monitoring",
            name="alertmanager-b",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        backing_pod_cache = {
            "monitoring/alertmanager-a": None,  # Unavailable
            "monitoring/alertmanager-b": None,  # Unavailable
        }
        
        groups = _group_by_backing_pods(sources, backing_pod_cache)
        
        # Should have 2 separate groups (different endpoints)
        assert len(groups) == 2
        # Both should use endpoint-based keys
        key_a: DedupKey = ("endpoint", "alertmanager-a.monitoring:9093")
        key_b: DedupKey = ("endpoint", "alertmanager-b.monitoring:9093")
        assert key_a in groups
        assert key_b in groups
        assert len(groups[key_a][1]) == 1
        assert len(groups[key_b][1]) == 1


class TestDeduplicateServiceHeuristicSources:
    """Tests for deduplicate_service_heuristic_sources function."""

    def test_deduplicates_same_pods_different_service_names(self) -> None:
        """Regression test: Same backing pods but different service names should merge.
        
        This is the core bug scenario:
        - alertmanager-operated (headless, clusterIP: None)
        - kube-prometheus-stack-alertmanager (chart service)
        
        Both point to the same Alertmanager pod UIDs but have different DNS names.
        They should be deduplicated into one logical Alertmanager.
        """
        source_operated = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_chart = AlertmanagerSource(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_operated, source_chart]
        pod_uids = frozenset({"pod-uid-0", "pod-uid-1"})
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=pod_uids,
            service_names=("alertmanager-operated",),
        )
        
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity',
            return_value=mock_identity
        ):
            groups = deduplicate_service_heuristic_sources(sources)
        
        # Should result in 1 group (same backing pods)
        assert len(groups) == 1
        group = groups[0]
        
        # Should prefer chart service over -operated
        assert group.preferred.name == "kube-prometheus-stack-alertmanager"
        # -operated should be an alias
        assert len(group.aliases) == 1
        assert group.aliases[0].name == "alertmanager-operated"
        # Should track dedup metadata
        assert group.raw_candidate_count == 2

    def test_keeps_separate_when_different_pods(self) -> None:
        """Sources with different backing pods should remain separate."""
        source_a = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-a",
            endpoint="http://alertmanager-a.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-a",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-b",
            endpoint="http://alertmanager-b.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-b",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity'
        ) as mock_get_identity:
            mock_get_identity.side_effect = [
                BackingPodIdentity(
                    kind="backing_pods",
                    uid_set=frozenset({"pod-uid-a"}),
                    service_names=("alertmanager-a",),
                ),
                BackingPodIdentity(
                    kind="backing_pods",
                    uid_set=frozenset({"pod-uid-b"}),
                    service_names=("alertmanager-b",),
                ),
            ]
            
            groups = deduplicate_service_heuristic_sources(sources)
        
        # Should have 2 groups (different backing pods)
        assert len(groups) == 2

    def test_three_sources_two_groups(self) -> None:
        """Three sources where two share pods, one is separate."""
        # AM-A: operated + chart (same pods)
        source_a_operated = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_a_chart = AlertmanagerSource(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        # AM-B: standalone (different pods)
        source_b = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-backup",
            endpoint="http://alertmanager-backup.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-backup",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a_operated, source_a_chart, source_b]
        
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity'
        ) as mock_get_identity:
            mock_get_identity.side_effect = [
                BackingPodIdentity(
                    kind="backing_pods",
                    uid_set=frozenset({"pod-uid-0", "pod-uid-1"}),
                    service_names=("alertmanager-operated",),
                ),
                BackingPodIdentity(
                    kind="backing_pods",
                    uid_set=frozenset({"pod-uid-0", "pod-uid-1"}),  # Same UIDs
                    service_names=("kube-prometheus-stack-alertmanager",),
                ),
                BackingPodIdentity(
                    kind="backing_pods",
                    uid_set=frozenset({"pod-uid-2"}),  # Different UIDs
                    service_names=("alertmanager-backup",),
                ),
            ]
            
            groups = deduplicate_service_heuristic_sources(sources)
        
        # Should have 2 groups:
        # - Group 1: AM-A (2 sources merged)
        # - Group 2: AM-B (1 source)
        assert len(groups) == 2
        
        # Find the AM-A group
        am_a_groups = [g for g in groups if g.preferred.name == "kube-prometheus-stack-alertmanager"]
        assert len(am_a_groups) == 1
        assert len(am_a_groups[0].aliases) == 1  # Should have 1 alias
        assert am_a_groups[0].raw_candidate_count == 2
        
        # Find the AM-B group
        am_b_groups = [g for g in groups if g.preferred.name == "alertmanager-backup"]
        assert len(am_b_groups) == 1
        assert len(am_b_groups[0].aliases) == 0  # No aliases
        assert am_b_groups[0].raw_candidate_count == 1

    def test_fallback_when_kubectl_unavailable(self) -> None:
        """Should fall back to endpoint-based grouping when kubectl fails."""
        source_a = AlertmanagerSource(
            source_id="service:monitoring/svc-a",
            endpoint="http://svc-a.monitoring:9093",
            namespace="monitoring",
            name="svc-a",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        source_b = AlertmanagerSource(
            source_id="service:monitoring/svc-b",
            endpoint="http://svc-a.monitoring:9093",  # Same endpoint
            namespace="monitoring",
            name="svc-b",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        
        sources = [source_a, source_b]
        
        # kubectl fails -> returns None for both
        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_discovery_dedup_helpers._get_service_backing_identity',
            return_value=None
        ):
            groups = deduplicate_service_heuristic_sources(sources)
        
        # Should fall back to endpoint-based grouping
        # Result: 1 group with preferred=svc-a and 1 alias (svc-b)
        # Note: aliases are on the Group object, not on the preferred source itself
        assert len(groups) == 1
        assert groups[0].preferred.name == "svc-a"
        assert len(groups[0].aliases) == 1
        assert groups[0].aliases[0].name == "svc-b"
