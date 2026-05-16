"""Regression test: operator-facing payloads must not expose raw "in-cluster".

This test proves that realistic operator UI payloads (cluster list, cluster detail,
worklist, notifications, LLM activity) with raw internal markers are rendered with
the canonical presentation label "cluster-local" instead.

This is NOT testing artifact inspector views (those intentionally show raw data).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from k8s_diag_agent.security.kubectl_context import (
    CLUSTER_LOCAL_PRESENTATION_LABEL,
    sanitize_kubectl_display_command,
    sanitize_operator_text,
)
from k8s_diag_agent.ui.api_incident_report import (
    _sanitize_target_cluster,
    _sanitize_target_context,
)


# =============================================================================
# Realistic Operator Payload Fixtures
# =============================================================================


def make_cluster_row_with_in_cluster() -> dict[str, object]:
    """Simulate a cluster list row with raw in-cluster internal marker."""
    return {
        "label": "in-cluster",
        "context": "in-cluster",
        "healthRating": "DEGRADED",
        "clusterRole": "control-plane",
        "warnings": 3,
        "nonRunningPods": 2,
    }


def make_queue_item_with_in_cluster() -> dict[str, object]:
    """Simulate a next-check queue item with raw in-cluster markers."""
    return {
        "candidateId": "check-001",
        "candidateIndex": 0,
        "description": "kubectl get pods --context in-cluster",
        "targetCluster": "in-cluster",
        "targetContext": "in-cluster",
        "commandPreview": "kubectl get pods -n monitoring --context in-cluster",
        "priorityLabel": "high",
        "executionState": "unexecuted",
        "sourceReason": "Detected issues in in-cluster namespace",
    }


def make_llm_activity_summary_with_in_cluster() -> dict[str, object]:
    """Simulate an LLM activity summary with raw in-cluster references."""
    return {
        "runId": "run-001",
        "runLabel": "Morning Health Check",
        "clusterLabel": "in-cluster",
        "toolName": "llamacpp",
        "status": "success",
        "summary": "Analyzed in-cluster health: found degraded pods in in-cluster namespace",
        "promptTokens": 1500,
        "completionTokens": 200,
    }


def make_notification_with_in_cluster() -> dict[str, object]:
    """Simulate a notification with raw in-cluster cluster label."""
    return {
        "kind": "warning",
        "summary": "Pod crash in in-cluster namespace",
        "clusterLabel": "in-cluster",
        "context": "in-cluster",
        "details": [
            ("cluster", "in-cluster"),
            ("namespace", "default"),
            ("reason", "in-cluster pod restart detected"),
        ],
    }


def make_deterministic_evidence_with_in_cluster() -> dict[str, object]:
    """Simulate deterministic next-check evidence with raw in-cluster."""
    return {
        "label": "in-cluster",
        "context": "in-cluster",
        "topProblem": "Pod CrashLoopBackOff in in-cluster",
        "deterministicNextCheckCount": 3,
        "deterministicNextCheckSummaries": [
            {
                "description": "Review pod status for in-cluster namespace",
                "method": "kubectl get pods",
                "evidence_needed": ["pod status", "events"],
                "urgency": "high",
                "workstream": "incident",
                "isPrimaryTriage": True,
                "why_now": "in-cluster pod needs immediate attention",
            },
        ],
    }


def make_drilldown_summary_with_in_cluster() -> dict[str, object]:
    """Simulate a drilldown summary with raw in-cluster references."""
    return {
        "label": "in-cluster",
        "context": "in-cluster",
        "triggerReasons": ["Pod CrashLoopBackOff in in-cluster namespace"],
        "warningEvents": 5,
        "nonRunningPods": 3,
        "summary": "in-cluster is degraded due to pod failures in in-cluster namespace",
    }


# =============================================================================
# Regression Tests for Operator-Facing Payloads
# =============================================================================


class TestOperatorPayloadRegression(unittest.TestCase):
    """Regression tests proving operator-facing payloads use 'cluster-local'."""

    def test_cluster_row_label_sanitized(self) -> None:
        """Cluster list row with raw in-cluster label renders as cluster-local."""
        row = make_cluster_row_with_in_cluster()
        # Simulate rendering logic from cluster list API
        rendered_label = _sanitize_target_cluster(row["label"], row["context"])
        # Must show cluster-local, not in-cluster
        self.assertEqual(rendered_label, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered_label)

    def test_cluster_row_context_sanitized(self) -> None:
        """Cluster list row with raw in-cluster context renders as cluster-local."""
        row = make_cluster_row_with_in_cluster()
        rendered_context = _sanitize_target_context(row["context"])
        self.assertEqual(rendered_context, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered_context)

    def test_queue_item_target_cluster_sanitized(self) -> None:
        """Queue item targetCluster with raw in-cluster renders as cluster-local."""
        item = make_queue_item_with_in_cluster()
        rendered = _sanitize_target_cluster(item["targetCluster"], item["targetContext"])
        self.assertEqual(rendered, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered)

    def test_queue_item_target_context_sanitized(self) -> None:
        """Queue item targetContext with raw in-cluster renders as cluster-local."""
        item = make_queue_item_with_in_cluster()
        rendered = _sanitize_target_context(item["targetContext"])
        self.assertEqual(rendered, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered)

    def test_queue_item_description_command_sanitized(self) -> None:
        """Queue item description with kubectl --context in-cluster is sanitized."""
        item = make_queue_item_with_in_cluster()
        rendered = sanitize_kubectl_display_command(item["description"])
        # Command should have context removed entirely (not replaced with cluster-local)
        self.assertNotIn("--context", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_queue_item_command_preview_sanitized(self) -> None:
        """Queue item commandPreview with kubectl --context in-cluster is sanitized."""
        item = make_queue_item_with_in_cluster()
        rendered = sanitize_kubectl_display_command(item["commandPreview"])
        self.assertNotIn("--context", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_queue_item_source_reason_prose_sanitized(self) -> None:
        """Queue item sourceReason prose with in-cluster is sanitized."""
        item = make_queue_item_with_in_cluster()
        rendered = sanitize_operator_text(item["sourceReason"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_llm_activity_summary_sanitized(self) -> None:
        """LLM activity summary with in-cluster references is sanitized."""
        summary = make_llm_activity_summary_with_in_cluster()
        # Simulate rendering cluster label
        rendered_label = _sanitize_target_cluster(summary["clusterLabel"])
        self.assertEqual(rendered_label, CLUSTER_LOCAL_PRESENTATION_LABEL)
        # Simulate rendering prose
        rendered_prose = sanitize_operator_text(summary["summary"])
        self.assertIn("cluster-local", rendered_prose)
        self.assertNotIn("in-cluster", rendered_prose)

    def test_notification_cluster_label_sanitized(self) -> None:
        """Notification clusterLabel with raw in-cluster is sanitized."""
        notif = make_notification_with_in_cluster()
        rendered = _sanitize_target_cluster(notif["clusterLabel"], notif["context"])
        self.assertEqual(rendered, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered)

    def test_notification_summary_prose_sanitized(self) -> None:
        """Notification summary prose with in-cluster is sanitized."""
        notif = make_notification_with_in_cluster()
        rendered = sanitize_operator_text(notif["summary"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_deterministic_evidence_label_sanitized(self) -> None:
        """Deterministic evidence label with raw in-cluster is sanitized."""
        evidence = make_deterministic_evidence_with_in_cluster()
        rendered = _sanitize_target_cluster(evidence["label"], evidence["context"])
        self.assertEqual(rendered, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered)

    def test_deterministic_evidence_top_problem_sanitized(self) -> None:
        """Deterministic evidence topProblem prose with in-cluster is sanitized."""
        evidence = make_deterministic_evidence_with_in_cluster()
        rendered = sanitize_operator_text(evidence["topProblem"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_deterministic_next_check_description_sanitized(self) -> None:
        """Deterministic next check description prose with in-cluster is sanitized."""
        evidence = make_deterministic_evidence_with_in_cluster()
        check = evidence["deterministicNextCheckSummaries"][0]
        rendered = sanitize_operator_text(check["description"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_deterministic_why_now_sanitized(self) -> None:
        """Deterministic why_now prose with in-cluster is sanitized."""
        evidence = make_deterministic_evidence_with_in_cluster()
        check = evidence["deterministicNextCheckSummaries"][0]
        rendered = sanitize_operator_text(check["why_now"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_drilldown_summary_label_sanitized(self) -> None:
        """Drilldown summary label with raw in-cluster is sanitized."""
        drilldown = make_drilldown_summary_with_in_cluster()
        rendered = _sanitize_target_cluster(drilldown["label"], drilldown["context"])
        self.assertEqual(rendered, CLUSTER_LOCAL_PRESENTATION_LABEL)
        self.assertNotIn("in-cluster", rendered)

    def test_drilldown_summary_prose_sanitized(self) -> None:
        """Drilldown summary prose with in-cluster is sanitized."""
        drilldown = make_drilldown_summary_with_in_cluster()
        rendered = sanitize_operator_text(drilldown["summary"])
        self.assertIn("cluster-local", rendered)
        self.assertNotIn("in-cluster", rendered)

    def test_drilldown_trigger_reasons_sanitized(self) -> None:
        """Drilldown trigger reasons with in-cluster are sanitized."""
        drilldown = make_drilldown_summary_with_in_cluster()
        for reason in drilldown["triggerReasons"]:
            rendered = sanitize_operator_text(reason)
            self.assertIn("cluster-local", rendered)
            self.assertNotIn("in-cluster", rendered)

    def test_full_worklist_payload_contains_no_raw_in_cluster(self) -> None:
        """Full worklist payload with mixed in-cluster data contains zero raw markers."""
        # Build raw input data
        raw_queue_items = [
            make_queue_item_with_in_cluster(),
            {
                **make_queue_item_with_in_cluster(),
                "candidateId": "check-002",
                "description": "kubectl describe pod -n in-cluster",
                "targetCluster": "prod-cluster",  # Real cluster - should be preserved
                "targetContext": "prod-cluster",
            },
        ]
        raw_llm_summaries = [
            make_llm_activity_summary_with_in_cluster(),
            {
                **make_llm_activity_summary_with_in_cluster(),
                "clusterLabel": "prod-cluster",  # Real cluster - should be preserved
                "summary": "Analyzed prod-cluster health: healthy",
            },
        ]
        raw_clusters = [make_cluster_row_with_in_cluster()]
        raw_notifications = [make_notification_with_in_cluster()]

        # Simulate building a sanitized payload (as the API would)
        sanitized_payload: dict[str, object] = {
            "queueItems": [],
            "llmSummaries": [],
            "clusters": [],
            "notifications": [],
        }

        # Sanitize queue items
        for item in raw_queue_items:
            sanitized_item = {
                "candidateId": item["candidateId"],
                "description": sanitize_kubectl_display_command(item["description"]) or item["description"],
                "targetCluster": _sanitize_target_cluster(item["targetCluster"], item["targetContext"]),
                "targetContext": _sanitize_target_context(item["targetContext"]),
                "commandPreview": sanitize_kubectl_display_command(item["commandPreview"]) or item["commandPreview"],
                "sourceReason": sanitize_operator_text(item["sourceReason"]) or item["sourceReason"],
            }
            sanitized_payload["queueItems"].append(sanitized_item)  # type: ignore[arg-type]

        # Sanitize LLM summaries
        for summary in raw_llm_summaries:
            sanitized_summary = {
                "clusterLabel": _sanitize_target_cluster(summary["clusterLabel"]),
                "summary": sanitize_operator_text(summary["summary"]) or summary["summary"],
            }
            sanitized_payload["llmSummaries"].append(sanitized_summary)  # type: ignore[arg-type]

        # Sanitize clusters
        for cluster in raw_clusters:
            sanitized_cluster = {
                "label": _sanitize_target_cluster(cluster["label"], cluster["context"]),
                "context": _sanitize_target_context(cluster["context"]),
            }
            sanitized_payload["clusters"].append(sanitized_cluster)  # type: ignore[arg-type]

        # Sanitize notifications
        for notif in raw_notifications:
            sanitized_notif = {
                "clusterLabel": _sanitize_target_cluster(notif["clusterLabel"], notif["context"]),
                "summary": sanitize_operator_text(notif["summary"]) or notif["summary"],
            }
            sanitized_payload["notifications"].append(sanitized_notif)  # type: ignore[arg-type]

        # Convert to string for comprehensive leak check
        payload_str = str(sanitized_payload)

        # Check that raw internal markers are NOT present in sanitized output
        self.assertNotIn("in-cluster", payload_str)
        self.assertNotIn("in_cluster", payload_str)

        # Check that canonical presentation label IS present
        self.assertIn(CLUSTER_LOCAL_PRESENTATION_LABEL, payload_str)

        # Check that real cluster names are preserved
        self.assertIn("prod-cluster", payload_str)

    def test_command_context_removal_not_replacement(self) -> None:
        """kubectl commands intentionally have context removed, not replaced."""
        # Commands use different sanitization: context is removed entirely
        # because there's no real cluster context to show
        cmd1 = "kubectl get pods --context in-cluster"
        cmd2 = "kubectl logs -n in-cluster pod-x --context=in-cluster"

        rendered1 = sanitize_kubectl_display_command(cmd1)
        rendered2 = sanitize_kubectl_display_command(cmd2)

        # Context should be removed entirely, not replaced
        self.assertNotIn("--context", rendered1)
        self.assertNotIn("--context", rendered2)
        self.assertNotIn("in-cluster", rendered1)
        self.assertNotIn("in-cluster", rendered2)

        # But the command itself should still be meaningful
        self.assertIn("kubectl get pods", rendered1)
        self.assertIn("kubectl logs", rendered2)


if __name__ == "__main__":
    unittest.main()
