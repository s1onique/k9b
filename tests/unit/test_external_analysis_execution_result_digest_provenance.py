"""Tests for execution provenance attachment in candidate building."""

import unittest

from k8s_diag_agent.external_analysis.next_check_planner_candidate_execution import (
    build_execution_provenance,
    find_execution_result_for_candidate,
)
from k8s_diag_agent.external_analysis.result_digest import ExecutionResultDigest


class TestProvenanceAttachment(unittest.TestCase):
    """Tests for execution provenance attachment in candidate building."""

    def test_attaches_provenance_on_description_overlap(self) -> None:
        """Test that provenance is attached when description overlaps."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx-pod",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=(),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        result = find_execution_result_for_candidate(
            "kubectl describe pod nginx-pod --namespace=default",
            (digest,),
        )
        
        self.assertIsNotNone(result)
        provenance = build_execution_provenance(result)
        self.assertEqual(provenance["priorCandidateDescription"], "kubectl describe pod nginx-pod")

    def test_attaches_provenance_on_signal_overlap(self) -> None:
        """Test that provenance is attached when signal overlaps."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl logs nginx-pod",
            status="failed",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] CrashLoopBackOff",
            signals=("CrashLoopBackOff",),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        # Candidate mentions CrashLoopBackOff, which overlaps with digest signals
        result = find_execution_result_for_candidate(
            "kubectl describe pod nginx - look for CrashLoopBackOff",
            (digest,),
        )
        
        self.assertIsNotNone(result)
        provenance = build_execution_provenance(result)
        self.assertEqual(provenance["priorStatus"], "failed")

    def test_no_provenance_on_cluster_only_match(self) -> None:
        """Test that provenance is NOT attached on cluster-only match.
        
        This is the key test: same cluster, unrelated commands should NOT
        get execution provenance attached.
        """
        # First digest: kubectl describe pod nginx on prod-cluster
        digest1 = ExecutionResultDigest(
            artifact_path="/path/to/exec1.json",
            candidate_id="id1",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=(),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        # Second digest: kubectl describe deployment frontend on prod-cluster
        digest2 = ExecutionResultDigest(
            artifact_path="/path/to/exec2.json",
            candidate_id="id2",
            candidate_description="kubectl describe deployment frontend",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=(),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        # New candidate: kubectl get pods - completely unrelated description
        # Should NOT match either digest since there's no description or signal overlap
        result = find_execution_result_for_candidate(
            "kubectl get pods",
            (digest1, digest2),
        )
        
        self.assertIsNone(result)

    def test_no_provenance_when_empty_context(self) -> None:
        """Test that no provenance is attached when execution context is empty."""
        result = find_execution_result_for_candidate(
            "kubectl describe pod nginx",
            (),
        )
        
        self.assertIsNone(result)

    def test_provenance_preserves_all_fields(self) -> None:
        """Test that provenance dict contains all expected fields."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context="default",
            summary="[useful] Pod running normally",
            signals=("CrashLoopBackOff", "OOMKilled"),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        result = find_execution_result_for_candidate(
            "kubectl describe pod nginx-pod",
            (digest,),
        )
        
        provenance = build_execution_provenance(result)
        
        self.assertIn("priorArtifact", provenance)
        self.assertIn("priorCandidateId", provenance)
        self.assertIn("priorCandidateDescription", provenance)
        self.assertIn("priorStatus", provenance)
        self.assertIn("priorUsefulnessClass", provenance)
        self.assertIn("priorSummary", provenance)
        self.assertIn("priorSignals", provenance)

    def test_provenance_signals_are_list(self) -> None:
        """Test that provenance signals are converted to list."""
        digest = ExecutionResultDigest(
            artifact_path="/path/to/execution.json",
            candidate_id="abc123",
            candidate_description="kubectl describe pod nginx",
            status="success",
            usefulness_class="useful",
            target_cluster="prod-cluster",
            target_context=None,
            summary="[useful] OK",
            signals=("CrashLoopBackOff", "OOMKilled"),
            stdout_truncated=False,
            stderr_truncated=False,
        )
        
        result = find_execution_result_for_candidate(
            "kubectl describe pod nginx-pod",
            (digest,),
        )
        
        provenance = build_execution_provenance(result)
        
        self.assertIsInstance(provenance["priorSignals"], list)
        self.assertEqual(len(provenance["priorSignals"]), 2)


if __name__ == "__main__":
    unittest.main()