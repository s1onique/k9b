import unittest
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    BaselineRegistry,
    ComparisonIntent,
    HealthSnapshotRecord,
    HealthTarget,
    _policy_eligible_pair,
)


class ComparisonPolicyTest(unittest.TestCase):
    @staticmethod
    def _make_snapshot(cluster_id: str) -> ClusterSnapshot:
        return ClusterSnapshot.from_dict(
            {
                "metadata": {
                    "cluster_id": cluster_id,
                    "captured_at": "2026-01-01T00:00:00Z",
                    "control_plane_version": "v1.25.0",
                    "node_count": 3,
                }
            }
        )

    @staticmethod
    def _record(
        cluster_id: str,
        label: str,
        cluster_class: str | None,
        cluster_role: str | None,
        baseline_cohort: str | None = "cohort-default",
    ) -> HealthSnapshotRecord:
        snapshot = ComparisonPolicyTest._make_snapshot(cluster_id)
        target = HealthTarget(
            context=cluster_id,
            label=label,
            monitor_health=False,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class=cluster_class,
            cluster_role=cluster_role,
            baseline_cohort=baseline_cohort,
        )
        return HealthSnapshotRecord(target=target, snapshot=snapshot, path=Path(f"{cluster_id}.json"))

    @staticmethod
    def _baseline(role_map: dict[str, str] | None = None) -> BaselinePolicy:
        return BaselinePolicy(
            control_plane_expectation=None,
            release_policies={},
            required_crds={},
            ignored_drift_categories=set(),
            expected_drift_categories=set(),
            peer_roles={ref: role for ref, role in (role_map or {}).items()},
        )

    def test_same_role_pair_is_eligible(self) -> None:
        baseline = self._baseline({"alpha": "primary", "beta": "primary"})
        primary = self._record("alpha", "alpha", "prod", "primary")
        secondary = self._record("beta", "beta", "prod", "primary")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, registry
        )
        self.assertTrue(eligible)
        self.assertEqual(reason, "policy compatible")
        self.assertEqual(primary_cohort, secondary_cohort)
        self.assertEqual(primary_cohort, "cohort-default")

    def test_role_mismatch_blocks_suspicious_intent(self) -> None:
        baseline = self._baseline()
        primary = self._record("alpha", "alpha", "prod", "primary")
        secondary = self._record("beta", "beta", "prod", "canary")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, registry
        )
        self.assertFalse(eligible)
        self.assertIn("peer roles differ", reason)

    def test_missing_class_blocks_comparison(self) -> None:
        baseline = self._baseline()
        primary = self._record("alpha", "alpha", None, "primary")
        secondary = self._record("beta", "beta", "prod", "primary")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, registry
        )
        self.assertFalse(eligible)
        self.assertIn("cluster class metadata missing", reason)

    def test_baseline_cohort_mismatch_blocks_suspicious_intent(self) -> None:
        baseline = self._baseline({"alpha": "primary", "beta": "primary"})
        primary = self._record("alpha", "alpha", "prod", "primary", "cohort-1")
        secondary = self._record("beta", "beta", "prod", "primary", "cohort-2")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, registry
        )
        self.assertFalse(eligible)
        self.assertIn("baseline cohorts differ", reason)
        self.assertEqual(primary_cohort, "cohort-1")
        self.assertEqual(secondary_cohort, "cohort-2")

    def test_baseline_cohort_missing_blocks_suspicious_intent(self) -> None:
        baseline = self._baseline({"alpha": "primary", "beta": "primary"})
        primary = self._record("alpha", "alpha", "prod", "primary", None)
        secondary = self._record("beta", "beta", "prod", "primary", "cohort-1")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, registry
        )
        self.assertFalse(eligible)
        self.assertIn("baseline cohort metadata missing", reason)
        self.assertIsNone(primary_cohort)
        self.assertEqual(secondary_cohort, "cohort-1")

    def test_expected_drift_ignores_cohort_mismatch(self) -> None:
        baseline = self._baseline({"alpha": "primary", "beta": "primary"})
        primary = self._record("alpha", "alpha", "prod", "primary", "cohort-a")
        secondary = self._record("beta", "beta", "prod", "primary", "cohort-b")
        registry = BaselineRegistry([baseline])
        eligible, reason, *_rest, primary_cohort, secondary_cohort = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.EXPECTED_DRIFT, registry
        )
        self.assertTrue(eligible)
        self.assertEqual(reason, "policy compatible")
