import unittest
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
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
        eligible, reason, *_ = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, baseline
        )
        self.assertTrue(eligible)
        self.assertEqual(reason, "policy compatible")

    def test_role_mismatch_blocks_suspicious_intent(self) -> None:
        baseline = self._baseline()
        primary = self._record("alpha", "alpha", "prod", "primary")
        secondary = self._record("beta", "beta", "prod", "canary")
        eligible, reason, *_ = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, baseline
        )
        self.assertFalse(eligible)
        self.assertIn("peer roles differ", reason)

    def test_missing_class_blocks_comparison(self) -> None:
        baseline = self._baseline()
        primary = self._record("alpha", "alpha", None, "primary")
        secondary = self._record("beta", "beta", "prod", "primary")
        eligible, reason, *_ = _policy_eligible_pair(
            primary, secondary, ComparisonIntent.SUSPICIOUS_DRIFT, baseline
        )
        self.assertFalse(eligible)
        self.assertIn("cluster class metadata missing", reason)
