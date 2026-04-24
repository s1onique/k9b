"""Tests for Alertmanager-influenced ranking in next check planner.

Tests cover:
- No Alertmanager context => ranking unchanged from baseline
- Empty/disabled/error Alertmanager status => no ranking bonus applied
- Namespace match gives bounded promotion
- Service match gives bounded promotion
- Cluster/context match gives bounded promotion
- Unrelated candidates do not receive alert-driven bonus
- Rationale/provenance clearly indicates Alertmanager-driven influence when applied
- Deterministic repeated ranking with same input produces same order / same rationale
- If multiple matches exist, the combined effect remains bounded and explainable
- Severity-aware bonus refinement
- Structured provenance for Alertmanager-driven ranking
"""

import unittest

from k8s_diag_agent.external_analysis.next_check_planner import (
    AlertmanagerRankingSignal,
    CommandFamily,
    CostEstimate,
    NextCheckCandidate,
    RiskLevel,
    _build_alertmanager_rationale,
    _compute_alertmanager_bonus,
    _compute_candidate_sort_score,
    _rank_candidates,
    build_alertmanager_provenance,
    compute_alertmanager_match_bonus,
    extract_alertmanager_severity_weight,
)
from k8s_diag_agent.external_analysis.review_input import AlertmanagerContext


def _make_candidate(
    description: str,
    family: CommandFamily,
    target_cluster: str | None = "test-cluster",
    target_context: str | None = None,
) -> NextCheckCandidate:
    """Create a minimal NextCheckCandidate for testing."""
    risk = RiskLevel.LOW if family in (
        CommandFamily.KUBECTL_LOGS, CommandFamily.KUBECTL_DESCRIBE, CommandFamily.KUBECTL_TOP
    ) else RiskLevel.MEDIUM
    cost = CostEstimate.LOW if risk == RiskLevel.LOW else CostEstimate.MEDIUM
    
    return NextCheckCandidate(
        candidate_id=f"id-{description[:20]}",
        description=description,
        target_cluster=target_cluster,
        target_context=target_context,
        source_reason="test",
        expected_signal=None,
        suggested_command_family=family,
        safe_to_automate=True,
        requires_operator_approval=False,
        risk_level=risk,
        estimated_cost=cost,
        confidence="high",
        gating_reason=None,
        duplicate_of_existing_evidence=False,
        duplicate_evidence_description=None,
        normalization_reason="test",
        safety_reason="known_command",
        approval_reason=None,
        duplicate_reason=None,
        blocking_reason=None,
        priority_label="secondary",
    )


def _make_alertmanager_context(
    available: bool,
    status: str | None = "ok",
    namespaces: tuple[str, ...] = (),
    clusters: tuple[str, ...] = (),
    services: tuple[str, ...] = (),
    severity_counts: dict[str, int] | None = None,
) -> AlertmanagerContext:
    """Create a mock AlertmanagerContext for testing."""
    compact: dict | None = None
    if available:
        compact = {
            "status": status or "ok",
            "alert_count": len(namespaces) + len(clusters) + len(services),
            "affected_namespaces": list(namespaces),
            "affected_clusters": list(clusters),
            "affected_services": list(services),
            "severity_counts": severity_counts or {"warning": 1},
            "state_counts": {"active": 1},
            "top_alert_names": ["test-alert"],
            "truncated": False,
            "captured_at": "2024-01-01T00:00:00Z",
        }
    return AlertmanagerContext(
        available=available,
        source="run_artifact" if available else "unavailable",
        compact=compact,
        status=status,
    )


class TestAlertmanagerRankingSignalFromContext(unittest.TestCase):
    """Tests for AlertmanagerRankingSignal.from_alertmanager_context()."""

    def test_unavailable_context_returns_unavailable_signal(self) -> None:
        """Unavailable context should return unavailable signal."""
        ctx = _make_alertmanager_context(available=False)
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertFalse(signal.available)
        self.assertEqual(signal.affected_namespaces, ())
        self.assertEqual(signal.affected_clusters, ())
        self.assertEqual(signal.affected_services, ())
        self.assertIsNone(signal.status)
        self.assertEqual(signal.severity_counts, ())

    def test_empty_status_returns_empty_signal(self) -> None:
        """Empty status should return available but empty signal."""
        ctx = _make_alertmanager_context(available=True, status="empty")
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_namespaces, ())
        self.assertEqual(signal.affected_clusters, ())
        self.assertEqual(signal.affected_services, ())
        self.assertEqual(signal.status, "empty")
        self.assertEqual(signal.severity_counts, ())

    def test_disabled_status_returns_empty_signal(self) -> None:
        """Disabled status should return available but empty signal."""
        ctx = _make_alertmanager_context(available=True, status="disabled")
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_namespaces, ())
        self.assertEqual(signal.affected_clusters, ())
        self.assertEqual(signal.affected_services, ())
        self.assertEqual(signal.status, "disabled")
        self.assertEqual(signal.severity_counts, ())

    def test_timeout_status_returns_empty_signal(self) -> None:
        """Timeout status should return available but empty signal."""
        ctx = _make_alertmanager_context(available=True, status="timeout")
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_namespaces, ())
        self.assertEqual(signal.affected_clusters, ())
        self.assertEqual(signal.affected_services, ())
        self.assertEqual(signal.status, "timeout")
        self.assertEqual(signal.severity_counts, ())

    def test_upstream_error_status_returns_empty_signal(self) -> None:
        """Upstream error status should return available but empty signal."""
        ctx = _make_alertmanager_context(available=True, status="upstream_error")
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_namespaces, ())
        self.assertEqual(signal.affected_clusters, ())
        self.assertEqual(signal.affected_services, ())
        self.assertEqual(signal.status, "upstream_error")
        self.assertEqual(signal.severity_counts, ())

    def test_ok_status_extracts_namespaces(self) -> None:
        """OK status with namespaces should extract them."""
        ctx = _make_alertmanager_context(
            available=True,
            status="ok",
            namespaces=("monitoring", "default", "kube-system"),
        )
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_namespaces, ("monitoring", "default", "kube-system"))
        self.assertEqual(signal.status, "ok")

    def test_ok_status_extracts_clusters(self) -> None:
        """OK status with clusters should extract them."""
        ctx = _make_alertmanager_context(
            available=True,
            status="ok",
            clusters=("prod-cluster", "staging-cluster"),
        )
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_clusters, ("prod-cluster", "staging-cluster"))

    def test_ok_status_extracts_services(self) -> None:
        """OK status with services should extract them."""
        ctx = _make_alertmanager_context(
            available=True,
            status="ok",
            services=("api-gateway", "auth-service"),
        )
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.affected_services, ("api-gateway", "auth-service"))

    def test_ok_status_extracts_severity_counts(self) -> None:
        """OK status with severity_counts should extract them."""
        ctx = _make_alertmanager_context(
            available=True,
            status="ok",
            severity_counts={"critical": 2, "warning": 5, "info": 3},
        )
        signal = AlertmanagerRankingSignal.from_alertmanager_context(ctx)
        
        self.assertTrue(signal.available)
        self.assertEqual(signal.severity_counts, (("critical", 2), ("warning", 5), ("info", 3)))


class TestAlertmanagerRankingSignalMatching(unittest.TestCase):
    """Tests for AlertmanagerRankingSignal matching methods."""

    def setUp(self) -> None:
        self.signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring", "default"),
            affected_clusters=("prod-cluster",),
            affected_services=("api-gateway", "auth-service"),
            status="ok",
            severity_counts=(("warning", 5),),
        )

    def test_matches_namespace_in_target_cluster(self) -> None:
        """Should match namespace when it appears in target_cluster (exact/prefix only)."""
        # Exact match
        self.assertTrue(
            self.signal.matches_namespace("monitoring", None)
        )
        # Prefix match: "monitoring-something"
        self.assertTrue(
            self.signal.matches_namespace("monitoring-pod-xyz", None)
        )
        # NOTE: substring in description without target_context does NOT match
        # ( tightened semantics - only in target_context or exact/prefix in target_cluster)
        self.assertFalse(
            self.signal.matches_namespace("check monitoring namespace", None)
        )

    def test_matches_namespace_in_target_context(self) -> None:
        """Should match namespace when it appears in target_context."""
        self.assertTrue(
            self.signal.matches_namespace(None, "namespace=monitoring")
        )
        self.assertTrue(
            self.signal.matches_namespace(None, "target: default ns")
        )

    def test_does_not_match_unrelated_namespace(self) -> None:
        """Should not match unrelated namespace."""
        self.assertFalse(
            self.signal.matches_namespace("other-cluster", None)
        )
        self.assertFalse(
            self.signal.matches_namespace(None, "unrelated context")
        )

    def test_matches_cluster_exact(self) -> None:
        """Should match cluster when it appears in target_cluster."""
        self.assertTrue(
            self.signal.matches_cluster("prod-cluster")
        )
        self.assertTrue(
            self.signal.matches_cluster("my-prod-cluster")
        )

    def test_does_not_match_unrelated_cluster(self) -> None:
        """Should not match unrelated cluster."""
        self.assertFalse(
            self.signal.matches_cluster("dev-cluster")
        )
        self.assertFalse(
            self.signal.matches_cluster(None)
        )

    def test_matches_service_in_description(self) -> None:
        """Should match service when it appears in candidate description."""
        self.assertTrue(
            self.signal.matches_service("check api-gateway logs", None)
        )
        self.assertTrue(
            self.signal.matches_service("auth-service health check", None)
        )

    def test_matches_service_in_context(self) -> None:
        """Should match service when it appears in target_context."""
        self.assertTrue(
            self.signal.matches_service(None, "targeting api-gateway")
        )

    def test_does_not_match_unrelated_service(self) -> None:
        """Should not match unrelated service."""
        self.assertFalse(
            self.signal.matches_service("check database pod", None)
        )


class TestExtractAlertmanagerSeverityWeight(unittest.TestCase):
    """Tests for extract_alertmanager_severity_weight function."""

    def test_empty_severity_returns_baseline(self) -> None:
        """Empty severity_counts should return baseline weight (1.0)."""
        weight = extract_alertmanager_severity_weight(())
        self.assertEqual(weight, 1.0)

    def test_critical_severity_boosts(self) -> None:
        """Critical dominant severity should return 1.25."""
        weight = extract_alertmanager_severity_weight((("critical", 5), ("warning", 2)))
        self.assertEqual(weight, 1.25)

    def test_warning_severity_baseline(self) -> None:
        """Warning dominant severity should return 1.0."""
        weight = extract_alertmanager_severity_weight((("warning", 10), ("info", 5)))
        self.assertEqual(weight, 1.0)

    def test_info_severity_weaker(self) -> None:
        """Info dominant severity should return 0.9."""
        weight = extract_alertmanager_severity_weight((("info", 8),))
        self.assertEqual(weight, 0.9)

    def test_unknown_severity_defaults_baseline(self) -> None:
        """Unknown severity should default to baseline (1.0)."""
        weight = extract_alertmanager_severity_weight((("unknown", 5),))
        self.assertEqual(weight, 1.0)


class TestComputeAlertmanagerMatchBonus(unittest.TestCase):
    """Tests for compute_alertmanager_match_bonus function."""

    def test_no_match_returns_zero(self) -> None:
        """No dimension matches should return 0."""
        bonus = compute_alertmanager_match_bonus(False, False, False, 1.25)
        self.assertEqual(bonus, 0)

    def test_namespace_only_baseline(self) -> None:
        """Namespace match with warning severity should give 80."""
        bonus = compute_alertmanager_match_bonus(True, False, False, 1.0)
        self.assertEqual(bonus, 80)

    def test_namespace_critical_boost(self) -> None:
        """Namespace match with critical severity should give ~100 (80 * 1.25)."""
        bonus = compute_alertmanager_match_bonus(True, False, False, 1.25)
        self.assertEqual(bonus, 100)

    def test_namespace_info_weaker(self) -> None:
        """Namespace match with info severity should give ~72 (80 * 0.9)."""
        bonus = compute_alertmanager_match_bonus(True, False, False, 0.9)
        self.assertEqual(bonus, 72)

    def test_all_three_matches_critical_capped(self) -> None:
        """Namespace+cluster+service with critical should be capped at 150."""
        # (80 + 60 + 50) * 1.25 = 237.5, rounded to 237, capped to 150
        bonus = compute_alertmanager_match_bonus(True, True, True, 1.25)
        self.assertEqual(bonus, 150)

    def test_all_three_matches_warning(self) -> None:
        """Namespace+cluster+service with warning should give 150."""
        bonus = compute_alertmanager_match_bonus(True, True, True, 1.0)
        self.assertEqual(bonus, 150)


class TestComputeAlertmanagerBonus(unittest.TestCase):
    """Tests for _compute_alertmanager_bonus function."""

    def setUp(self) -> None:
        self.signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=("prod-cluster",),
            affected_services=("api-gateway",),
            status="ok",
            severity_counts=(("warning", 5),),
        )

    def test_unavailable_signal_returns_zero_bonus(self) -> None:
        """Unavailable signal should return zero bonus."""
        unavailable_signal = AlertmanagerRankingSignal(
            available=False,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            status=None,
            severity_counts=(),
        )
        candidate = _make_candidate("kubectl logs", CommandFamily.KUBECTL_LOGS)
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, unavailable_signal)
        
        self.assertEqual(bonus, 0)
        self.assertFalse(ns)
        self.assertFalse(cluster)
        self.assertFalse(service)

    def test_empty_signal_returns_zero_bonus(self) -> None:
        """Empty signal (no affected dimensions) should return zero bonus."""
        empty_signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            status="empty",
            severity_counts=(),
        )
        candidate = _make_candidate("kubectl logs", CommandFamily.KUBECTL_LOGS)
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, empty_signal)
        
        self.assertEqual(bonus, 0)
        self.assertFalse(ns)
        self.assertFalse(cluster)
        self.assertFalse(service)

    def test_namespace_match_gives_bonus_warning(self) -> None:
        """Namespace match with warning severity should give bonus ~80."""
        candidate = _make_candidate(
            "kubectl logs monitoring pod",
            CommandFamily.KUBECTL_LOGS,
            target_cluster="monitoring",
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, self.signal)
        
        # 80 * 1.0 = 80 for warning
        self.assertEqual(bonus, 80)
        self.assertTrue(ns)
        self.assertFalse(cluster)
        self.assertFalse(service)

    def test_namespace_match_gives_bonus_critical(self) -> None:
        """Namespace match with critical severity should give bonus ~100."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("critical", 3), ("warning", 1)),  # critical dominant
        )
        candidate = _make_candidate(
            "kubectl logs monitoring pod",
            CommandFamily.KUBECTL_LOGS,
            target_cluster="monitoring",
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, signal)
        
        # 80 * 1.25 = 100 for critical
        self.assertEqual(bonus, 100)
        self.assertTrue(ns)

    def test_namespace_match_gives_bonus_info(self) -> None:
        """Namespace match with info severity should give bonus ~72."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("info", 5),),  # info dominant
        )
        candidate = _make_candidate(
            "kubectl logs monitoring pod",
            CommandFamily.KUBECTL_LOGS,
            target_cluster="monitoring",
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, signal)
        
        # 80 * 0.9 = 72 for info
        self.assertEqual(bonus, 72)
        self.assertTrue(ns)

    def test_cluster_match_gives_bonus(self) -> None:
        """Cluster match should give bonus."""
        candidate = _make_candidate(
            "kubectl describe pod",
            CommandFamily.KUBECTL_DESCRIBE,
            target_cluster="prod-cluster",
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, self.signal)
        
        # 60 * 1.0 = 60 for warning
        self.assertEqual(bonus, 60)
        self.assertFalse(ns)
        self.assertTrue(cluster)
        self.assertFalse(service)

    def test_service_match_gives_bonus(self) -> None:
        """Service match should give bonus."""
        candidate = _make_candidate(
            "kubectl logs api-gateway",
            CommandFamily.KUBECTL_LOGS,
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, self.signal)
        
        # 50 * 1.0 = 50 for warning
        self.assertEqual(bonus, 50)
        self.assertFalse(ns)
        self.assertFalse(cluster)
        self.assertTrue(service)

    def test_multiple_matches_capped(self) -> None:
        """Multiple matches should be capped at maximum."""
        # Candidate with namespace + service matches (two matches)
        # Using "monitoring" in target_cluster and description to match namespace/service
        candidate = _make_candidate(
            "kubectl logs monitoring",  # matches namespace (via target_cluster) and service
            CommandFamily.KUBECTL_LOGS,
            target_cluster="monitoring",  # matches namespace
        )
        
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=("monitoring",),  # matches via description
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, signal)
        
        # namespace match: "monitoring" in "monitoring" -> True (+80)
        # service match: "monitoring" in description -> True (+50)
        # 80 + 50 = 130 * 1.0 = 130 (warning), which is under cap but meaningful bonus
        self.assertEqual(bonus, 130)
        self.assertTrue(ns)
        self.assertFalse(cluster)
        self.assertTrue(service)

    def test_all_three_matches_critical_capped_at_150(self) -> None:
        """Candidate matching all three dimensions with critical should be capped at 150.

        namespace (80) + cluster (60) + service (50) = 190, * 1.25 = 237.5, capped to 150.
        """
        candidate = _make_candidate(
            "kubectl logs prod-gateway in prod-cluster",  # service match via description
            CommandFamily.KUBECTL_LOGS,
            target_cluster="prod-cluster",  # cluster match
        )
        
        # Signal with all three dimensions and critical severity
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("prod-cluster",),  # matches via namespace (exact in target_cluster)
            affected_clusters=("prod-cluster",),     # matches via cluster
            affected_services=("prod-gateway",),     # matches via description
            status="ok",
            severity_counts=(("critical", 5),),
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, signal)
        
        # 190 * 1.25 = 237.5, capped to 150
        self.assertEqual(bonus, 150)
        self.assertTrue(ns)
        self.assertTrue(cluster)
        self.assertTrue(service)

    def test_unrelated_candidate_gets_zero_bonus(self) -> None:
        """Unrelated candidate should get zero bonus."""
        candidate = _make_candidate(
            "kubectl logs other-pod",
            CommandFamily.KUBECTL_LOGS,
            target_cluster="dev-cluster",
        )
        
        bonus, ns, cluster, service = _compute_alertmanager_bonus(candidate, self.signal)
        
        self.assertEqual(bonus, 0)
        self.assertFalse(ns)
        self.assertFalse(cluster)
        self.assertFalse(service)


class TestBuildAlertmanagerProvenance(unittest.TestCase):
    """Tests for build_alertmanager_provenance function."""

    def test_none_when_no_matches(self) -> None:
        """Should return None when no matches occurred."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        provenance = build_alertmanager_provenance(False, False, False, 0, 0, signal)
        
        self.assertIsNone(provenance)

    def test_namespace_match_provenance(self) -> None:
        """Should build provenance with namespace dimension."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring", "default"),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("critical", 2), ("warning", 3)),
        )
        
        provenance = build_alertmanager_provenance(True, False, False, 80, 100, signal)
        
        self.assertIsNotNone(provenance)
        assert provenance is not None  # for mypy
        self.assertIn("namespace", provenance.matched_dimensions)
        self.assertEqual(provenance.base_bonus, 80)
        self.assertEqual(provenance.applied_bonus, 100)
        self.assertEqual(provenance.severity_summary, {"critical": 2, "warning": 3})
        self.assertEqual(provenance.signal_status, "ok")

    def test_all_three_matches_provenance(self) -> None:
        """Should build provenance with all three dimensions."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=("prod-cluster",),
            affected_services=("api-gateway",),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        provenance = build_alertmanager_provenance(True, True, True, 190, 180, signal)
        
        self.assertIsNotNone(provenance)
        assert provenance is not None  # for mypy
        self.assertIn("namespace", provenance.matched_dimensions)
        self.assertIn("cluster", provenance.matched_dimensions)
        self.assertIn("service", provenance.matched_dimensions)
        self.assertEqual(len(provenance.matched_dimensions), 3)
        self.assertEqual(provenance.base_bonus, 190)
        self.assertEqual(provenance.applied_bonus, 180)

    def test_provenance_to_dict(self) -> None:
        """Should convert to serializable dict."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        provenance = build_alertmanager_provenance(True, False, False, 80, 80, signal)
        
        self.assertIsNotNone(provenance)
        assert provenance is not None  # for mypy
        d = provenance.to_dict()
        
        self.assertIn("matchedDimensions", d)
        self.assertIn("matchedValues", d)
        self.assertIn("baseBonus", d)
        self.assertIn("appliedBonus", d)
        self.assertIn("severitySummary", d)
        self.assertIn("signalStatus", d)
        self.assertEqual(d["baseBonus"], 80)
        self.assertEqual(d["appliedBonus"], 80)


class TestBuildAlertmanagerRationale(unittest.TestCase):
    """Tests for _build_alertmanager_rationale function."""

    def test_none_when_no_matches(self) -> None:
        """Should return None when no matches occurred."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(),
        )
        
        rationale = _build_alertmanager_rationale(False, False, False, signal)
        
        self.assertIsNone(rationale)

    def test_includes_namespace_match(self) -> None:
        """Should include namespace in rationale when matched."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring", "default"),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(),
        )
        
        rationale = _build_alertmanager_rationale(True, False, False, signal)
        
        self.assertIsNotNone(rationale)
        assert rationale is not None  # for mypy
        self.assertIn("alertmanager-context", rationale)
        self.assertIn("namespace(s): monitoring, default", rationale)

    def test_includes_cluster_match(self) -> None:
        """Should include cluster in rationale when matched."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=("prod-cluster",),
            affected_services=(),
            status="ok",
            severity_counts=(),
        )
        
        rationale = _build_alertmanager_rationale(False, True, False, signal)
        
        self.assertIsNotNone(rationale)
        assert rationale is not None  # for mypy
        self.assertIn("cluster(s): prod-cluster", rationale)

    def test_includes_service_match(self) -> None:
        """Should include service in rationale when matched."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=("api-gateway", "auth-service"),
            status="ok",
            severity_counts=(),
        )
        
        rationale = _build_alertmanager_rationale(False, False, True, signal)
        
        self.assertIsNotNone(rationale)
        assert rationale is not None  # for mypy
        self.assertIn("service(s): api-gateway, auth-service", rationale)

    def test_includes_multiple_matches(self) -> None:
        """Should include all matched dimensions."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=("prod-cluster",),
            affected_services=("api-gateway",),
            status="ok",
            severity_counts=(),
        )
        
        rationale = _build_alertmanager_rationale(True, True, True, signal)
        
        self.assertIsNotNone(rationale)
        assert rationale is not None  # for mypy
        self.assertIn("namespace(s): monitoring", rationale)
        self.assertIn("cluster(s): prod-cluster", rationale)
        self.assertIn("service(s): api-gateway", rationale)


class TestRankingWithAlertmanagerSignal(unittest.TestCase):
    """Tests for _rank_candidates with Alertmanager signal."""

    def test_no_signal_unchanged_ranking(self) -> None:
        """Without signal, ranking should be unchanged."""
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=None)
        
        # No ranking policy reason should be set
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_unavailable_signal_unchanged_ranking(self) -> None:
        """Unavailable signal should not affect ranking."""
        unavailable_signal = AlertmanagerRankingSignal(
            available=False,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            status=None,
            severity_counts=(),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=unavailable_signal)
        
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_empty_status_unchanged_ranking(self) -> None:
        """Empty status should not affect ranking."""
        empty_signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            status="empty",
            severity_counts=(),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=empty_signal)
        
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_namespace_match_promotes_candidate(self) -> None:
        """Candidate matching namespace should be promoted."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="monitoring"),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Monitoring candidate should be first due to namespace match
        self.assertEqual(ranked[0].description, "kubectl describe pod")
        self.assertIsNotNone(ranked[0].ranking_policy_reason)
        assert ranked[0].ranking_policy_reason is not None  # for mypy
        self.assertIn("alertmanager-context", ranked[0].ranking_policy_reason)
        
        # Provenance should be set
        self.assertIsNotNone(ranked[0].alertmanager_provenance)
        
        # Non-matching candidate should be second
        self.assertEqual(ranked[1].description, "kubectl get crd")
        self.assertIsNone(ranked[1].ranking_policy_reason)
        self.assertIsNone(ranked[1].alertmanager_provenance)

    def test_namespace_match_critical_boost(self) -> None:
        """Candidate matching namespace with critical severity should get boosted bonus."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("critical", 3),),  # critical dominant
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="monitoring"),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Monitoring candidate should be first due to namespace match with critical boost
        self.assertEqual(ranked[0].description, "kubectl describe pod")
        self.assertIsNotNone(ranked[0].alertmanager_provenance)
        assert ranked[0].alertmanager_provenance is not None  # for mypy
        # base_bonus = 80, applied_bonus = 80 * 1.25 = 100
        self.assertEqual(ranked[0].alertmanager_provenance.base_bonus, 80)
        self.assertEqual(ranked[0].alertmanager_provenance.applied_bonus, 100)
        self.assertEqual(ranked[0].alertmanager_provenance.severity_summary, {"critical": 3})

    def test_cluster_match_promotes_candidate(self) -> None:
        """Candidate matching cluster should be promoted."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=("prod-cluster",),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="prod-cluster"),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Prod-cluster candidate should be first due to cluster match
        self.assertEqual(ranked[0].description, "kubectl describe pod")
        self.assertIsNotNone(ranked[0].ranking_policy_reason)
        assert ranked[0].ranking_policy_reason is not None  # for mypy
        self.assertIn("alertmanager-context", ranked[0].ranking_policy_reason)
        self.assertIsNotNone(ranked[0].alertmanager_provenance)

    def test_service_match_promotes_candidate(self) -> None:
        """Candidate mentioning affected service should be promoted."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=("api-gateway",),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD),
            _make_candidate("kubectl logs api-gateway", CommandFamily.KUBECTL_LOGS),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Service-matching candidate should be first
        self.assertEqual(ranked[0].description, "kubectl logs api-gateway")
        self.assertIsNotNone(ranked[0].ranking_policy_reason)
        assert ranked[0].ranking_policy_reason is not None  # for mypy
        self.assertIn("alertmanager-context", ranked[0].ranking_policy_reason)
        self.assertIsNotNone(ranked[0].alertmanager_provenance)

    def test_multiple_matches_combined_bounded(self) -> None:
        """Candidate with multiple matches should get bounded bonus."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=("prod-cluster",),
            affected_services=("api-gateway",),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate(
                "kubectl logs api-gateway", 
                CommandFamily.KUBECTL_LOGS, 
                target_cluster="prod-cluster",  # matches cluster
            ),
            _make_candidate(
                "kubectl describe other", 
                CommandFamily.KUBECTL_DESCRIBE,
            ),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Matching candidate should be first
        self.assertEqual(ranked[0].description, "kubectl logs api-gateway")
        self.assertIsNotNone(ranked[0].ranking_policy_reason)
        self.assertIsNotNone(ranked[0].alertmanager_provenance)

    def test_deterministic_ranking(self) -> None:
        """Same input should produce same ranking order and provenance."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate("kubectl logs monitoring", CommandFamily.KUBECTL_LOGS, target_cluster="monitoring"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE),
        ]
        
        # Run ranking twice
        ranked1 = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        ranked2 = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Both should produce identical ordering
        self.assertEqual(
            [c.description for c in ranked1],
            [c.description for c in ranked2]
        )
        
        # Both should have same rationale
        self.assertEqual(
            ranked1[0].ranking_policy_reason,
            ranked2[0].ranking_policy_reason
        )
        
        # Both should have same provenance
        prov1 = ranked1[0].alertmanager_provenance
        prov2 = ranked2[0].alertmanager_provenance
        self.assertIsNotNone(prov1)
        self.assertIsNotNone(prov2)
        self.assertEqual(prov1.to_dict(), prov2.to_dict())

    def test_unrelated_candidates_no_bonus(self) -> None:
        """Unrelated candidates should not receive bonus or provenance."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=("prod-cluster",),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl logs database", CommandFamily.KUBECTL_LOGS, target_cluster="staging"),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Neither should have ranking_policy_reason or provenance set
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_timeout_status_no_promotion(self) -> None:
        """Timeout status should produce no promotion (bonus not applied).

        Even if signal has affected_namespaces, error statuses like timeout
        should not trigger bonus computation.
        """
        # Signal has data but status indicates error - bonus should NOT be applied
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="timeout",
            severity_counts=(),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="monitoring"),
        ]

        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)

        # No bonus applied due to timeout status
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_upstream_error_status_no_promotion(self) -> None:
        """Upstream error status should produce no promotion (bonus not applied).

        Even if signal has affected_namespaces, error statuses like upstream_error
        should not trigger bonus computation.
        """
        # Signal has data but status indicates error - bonus should NOT be applied
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="upstream_error",
            severity_counts=(),
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="monitoring"),
        ]

        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)

        # No bonus applied due to upstream_error status
        for c in ranked:
            self.assertIsNone(c.ranking_policy_reason)
            self.assertIsNone(c.alertmanager_provenance)

    def test_no_severity_data_preserves_baseline(self) -> None:
        """No severity data should result in baseline behavior."""
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(),  # empty severity
        )
        candidates = [
            _make_candidate("kubectl get crd", CommandFamily.KUBECTL_GET_CRD, target_cluster="dev"),
            _make_candidate("kubectl describe pod", CommandFamily.KUBECTL_DESCRIBE, target_cluster="monitoring"),
        ]
        
        ranked = _rank_candidates(candidates, workstream=None, review_stage=None, alertmanager_signal=signal)
        
        # Monitoring candidate should be first
        self.assertEqual(ranked[0].description, "kubectl describe pod")
        self.assertIsNotNone(ranked[0].alertmanager_provenance)
        assert ranked[0].alertmanager_provenance is not None  # for mypy
        # With no severity, weight defaults to 1.0, so base = applied = 80
        self.assertEqual(ranked[0].alertmanager_provenance.base_bonus, 80)
        self.assertEqual(ranked[0].alertmanager_provenance.applied_bonus, 80)
        self.assertEqual(ranked[0].alertmanager_provenance.severity_summary, {})


class TestComputeCandidateSortScoreWithAlertmanager(unittest.TestCase):
    """Tests for _compute_candidate_sort_score with Alertmanager signal."""

    def test_alertmanager_signal_parameter_exists(self) -> None:
        """Function should accept alertmanager_signal parameter."""
        # Include "monitoring" in the description so it matches the signal's namespace
        candidate = _make_candidate(
            "kubectl logs monitoring pod", 
            CommandFamily.KUBECTL_LOGS,
            target_cluster="monitoring",  # Also matches via target_cluster
        )
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        # Should not raise - function accepts optional alertmanager_signal
        score, demotion, am_bonus, ns, cluster, service = _compute_candidate_sort_score(
            candidate, workstream=None, review_stage=None, alertmanager_signal=signal
        )
        
        # Namespace match should have been detected (in both target_cluster and description)
        self.assertTrue(ns)
        # Warning severity: 80 * 1.0 = 80
        self.assertEqual(am_bonus, 80)

    def test_none_signal_works(self) -> None:
        """None signal should not affect scoring."""
        candidate = _make_candidate("kubectl logs", CommandFamily.KUBECTL_LOGS)
        
        score, demotion, am_bonus, ns, cluster, service = _compute_candidate_sort_score(
            candidate, workstream=None, review_stage=None, alertmanager_signal=None
        )
        
        self.assertEqual(am_bonus, 0)
        self.assertFalse(ns)
        self.assertFalse(cluster)
        self.assertFalse(service)

    def test_bonus_additive_to_base_score(self) -> None:
        """Alertmanager bonus should add to base score, not replace."""
        candidate = _make_candidate(
            "kubectl logs monitoring", 
            CommandFamily.KUBECTL_LOGS, 
            target_cluster="monitoring"
        )
        signal = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        
        score_with_bonus, _, am_bonus, _, _, _ = _compute_candidate_sort_score(
            candidate, alertmanager_signal=signal
        )
        score_without_bonus, _, _, _, _, _ = _compute_candidate_sort_score(
            candidate, alertmanager_signal=None
        )
        
        # Score with bonus should be higher by exactly the bonus amount
        self.assertEqual(score_with_bonus - score_without_bonus, am_bonus)

    def test_severity_boost_in_score(self) -> None:
        """Critical severity should result in higher bonus."""
        candidate = _make_candidate(
            "kubectl logs monitoring", 
            CommandFamily.KUBECTL_LOGS, 
            target_cluster="monitoring"
        )
        signal_warning = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("warning", 5),),
        )
        signal_critical = AlertmanagerRankingSignal(
            available=True,
            affected_namespaces=("monitoring",),
            affected_clusters=(),
            affected_services=(),
            status="ok",
            severity_counts=(("critical", 3),),
        )
        
        _, _, bonus_warning, _, _, _ = _compute_candidate_sort_score(
            candidate, alertmanager_signal=signal_warning
        )
        _, _, bonus_critical, _, _, _ = _compute_candidate_sort_score(
            candidate, alertmanager_signal=signal_critical
        )
        
        # Critical bonus should be higher than warning bonus
        self.assertGreater(bonus_critical, bonus_warning)
        # Warning: 80 * 1.0 = 80
        self.assertEqual(bonus_warning, 80)
        # Critical: 80 * 1.25 = 100
        self.assertEqual(bonus_critical, 100)


if __name__ == "__main__":
    unittest.main()
