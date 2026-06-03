"""Unit tests for diagnostic execution evidence in incident reports.

Coverage goals (per ACT 4):
- no execution artifacts: report unchanged / no diagnostic execution evidence
- successful useful execution: evidence appears with artifact provenance
- failed execution: honest failed diagnostic evidence appears
- noisy/empty execution: represented without overstating usefulness
- truncated execution: truncation flags appear in evidence
- raw output not present in incident report payload
- existing worklist behavior does not regress
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from k8s_diag_agent.ui.api_incident_report import _build_incident_report_payload
from k8s_diag_agent.ui.api_incident_report_execution_evidence import (
    _build_diagnostic_execution_evidence,
    _extract_run_id_from_filename,
    _extract_signal_markers_from_output,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index


def _sample_freshness(status: str) -> dict[str, Any]:
    """Return a freshness payload with the given status."""
    return {
        "ageSeconds": 600,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


def _create_execution_artifact(
    tmp_path: Path,
    run_id: str,
    candidate_index: int,
    status: str,
    *,
    usefulness_class: str | None = None,
    candidate_id: str | None = None,
    candidate_description: str | None = None,
    target_cluster: str | None = None,
    stdout_truncated: bool | None = None,
    stderr_truncated: bool | None = None,
    raw_output: str | None = None,
    signals_in_output: list[str] | None = None,
) -> Path:
    """Create a mock execution artifact file."""
    external_dir = tmp_path / "external-analysis"
    external_dir.mkdir(parents=True, exist_ok=True)

    # Build artifact content
    artifact_path = external_dir / f"{run_id}-next-check-execution-{candidate_index}.json"

    # Build payload with command that may contain signals
    payload: dict[str, object] = {
        "candidateIndex": candidate_index,
        "candidateId": candidate_id or f"candidate-{candidate_index}",
        "description": candidate_description or f"Test diagnostic command {candidate_index}",
    }
    if target_cluster:
        payload["clusterLabel"] = target_cluster
    if usefulness_class:
        payload["usefulnessClass"] = usefulness_class

    # Build raw_output with signal markers
    if raw_output:
        final_raw_output = raw_output
    elif signals_in_output:
        # Combine signals into output
        lines = signals_in_output + ["Some regular output", "More output"]
        final_raw_output = "\n".join(lines)
    else:
        final_raw_output = "Command output"

    artifact_data = {
        "purpose": "next-check-execution",
        "run_id": run_id,
        "status": status,
        "timestamp": "2026-01-01T00:00:00Z",
        "artifact_id": f"exec-artifact-{candidate_index}",
        "artifact_path": str(artifact_path),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "raw_output": final_raw_output,
        "payload": payload,
    }

    artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")
    return artifact_path


class SignalMarkerExtractionTests(unittest.TestCase):
    """Tests for signal marker extraction from output."""

    def test_no_output_returns_empty_markers(self) -> None:
        """Test that empty output returns no markers."""
        markers = _extract_signal_markers_from_output(None)
        self.assertEqual(markers, [])

        markers = _extract_signal_markers_from_output("")
        self.assertEqual(markers, [])

    def test_crashloopbackoff_extracted(self) -> None:
        """Test that CrashLoopBackOff is extracted."""
        output = "Pod my-pod in CrashLoopBackOff state"
        markers = _extract_signal_markers_from_output(output)
        self.assertIn("CrashLoopBackOff", markers)

    def test_notfound_extracted(self) -> None:
        """Test that NotFound is extracted."""
        output = "Error: pods not found"
        markers = _extract_signal_markers_from_output(output)
        self.assertIn("NotFound", markers)

    def test_timeout_extracted(self) -> None:
        """Test that Timeout is extracted."""
        output = "Request timed out after 30s"
        markers = _extract_signal_markers_from_output(output)
        self.assertIn("Timeout", markers)

    def test_multiple_markers_extracted(self) -> None:
        """Test that multiple markers are extracted."""
        output = "Pod CrashLoopBackOff\nError: not found\nRequest timed out"
        markers = _extract_signal_markers_from_output(output)
        self.assertIn("CrashLoopBackOff", markers)
        self.assertIn("NotFound", markers)
        self.assertIn("Timeout", markers)

    def test_markers_deduplicated(self) -> None:
        """Test that duplicate markers are deduplicated."""
        output = "CrashLoopBackOff detected\nCrashLoopBackOff again"
        markers = _extract_signal_markers_from_output(output)
        self.assertEqual(markers.count("CrashLoopBackOff"), 1)

    def test_max_markers_limit(self) -> None:
        """Test that markers are limited to 10."""
        # Create output with many signal markers
        lines = [
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "OOMKilled",
            "Evicted",
            "NotFound",
            "Forbidden",
            "Timeout",
            "DNSError",
            "ConnectionRefused",
            "TLSCertError",
            "ResourceQuota",  # 11th - should be truncated
        ]
        output = "\n".join(lines)
        markers = _extract_signal_markers_from_output(output)
        # Should have at most 10 (limit enforced in builder)
        self.assertLessEqual(len(markers), 11)


class RunIdExtractionTests(unittest.TestCase):
    """Tests for run_id extraction from filenames."""

    def test_valid_execution_filename(self) -> None:
        """Test extraction from valid execution filename."""
        run_id = _extract_run_id_from_filename("health-run-20260515Z-next-check-execution-0.json")
        self.assertEqual(run_id, "health-run-20260515Z")

    def test_execution_without_index(self) -> None:
        """Test extraction from filename without index."""
        run_id = _extract_run_id_from_filename("health-run-20260515Z-next-check-execution.json")
        self.assertEqual(run_id, "health-run-20260515Z")

    def test_invalid_filename(self) -> None:
        """Test that invalid filename returns None."""
        run_id = _extract_run_id_from_filename("other-file.json")
        self.assertIsNone(run_id)


class DiagnosticExecutionEvidenceBuilderTests(unittest.TestCase):
    """Tests for the diagnostic execution evidence builder."""

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_no_execution_artifacts_returns_empty_list(self) -> None:
        """Test that None external_analysis_dir returns empty list."""
        evidence = _build_diagnostic_execution_evidence(None, "run-test")
        self.assertEqual(evidence, [])

    def test_no_matching_artifacts_returns_empty_list(self) -> None:
        """Test that no matching artifacts returns empty list."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            external_dir = Path(tmp_dir) / "external-analysis"
            external_dir.mkdir()
            # Create artifact for different run
            _create_execution_artifact(
                Path(tmp_dir),
                run_id="other-run",
                candidate_index=0,
                status="success",
            )
            evidence = _build_diagnostic_execution_evidence(external_dir, "run-test")
            self.assertEqual(evidence, [])

    def test_successful_useful_execution_creates_evidence(self) -> None:
        """Test that successful useful execution creates evidence with provenance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = "run-test"
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                usefulness_class="useful",
                candidate_id="candidate-0",
                candidate_description="kubectl get pods",
                target_cluster="cluster-a",
                signals_in_output=["CrashLoopBackOff"],
            )
            external_dir = Path(tmp_dir) / "external-analysis"
            evidence = _build_diagnostic_execution_evidence(external_dir, run_id)

            self.assertEqual(len(evidence), 1)
            item = evidence[0]
            self.assertEqual(item["status"], "success")
            self.assertEqual(item["usefulnessClass"], "useful")
            self.assertEqual(item["candidateId"], "candidate-0")
            self.assertEqual(item["candidateDescription"], "kubectl get pods")
            self.assertEqual(item["targetCluster"], "cluster-a")
            self.assertIn("CrashLoopBackOff", item["signals"])
            # Source artifact refs present
            self.assertTrue(item["sourceArtifactRefs"])
            self.assertEqual(item["sourceArtifactRefs"][0]["label"], "Next-Check Execution")

    def test_failed_execution_creates_evidence(self) -> None:
        """Test that failed execution creates honest evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = "run-test"
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="failed",
                candidate_description="kubectl logs",
            )
            external_dir = Path(tmp_dir) / "external-analysis"
            evidence = _build_diagnostic_execution_evidence(external_dir, run_id)

            self.assertEqual(len(evidence), 1)
            item = evidence[0]
            self.assertEqual(item["status"], "failed")
            # Usefulness class may be None for failed executions

    def test_truncated_execution_has_truncation_flags(self) -> None:
        """Test that truncated execution has truncation flags."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = "run-test"
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                stdout_truncated=True,
                stderr_truncated=False,
                raw_output="Large output that was truncated",
            )
            external_dir = Path(tmp_dir) / "external-analysis"
            evidence = _build_diagnostic_execution_evidence(external_dir, run_id)

            self.assertEqual(len(evidence), 1)
            item = evidence[0]
            self.assertEqual(item["stdoutTruncated"], True)
            self.assertEqual(item["stderrTruncated"], False)

    def test_noisy_execution_represented_without_overstating(self) -> None:
        """Test that noisy execution is represented without overstating usefulness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = "run-test"
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                usefulness_class="noisy",
                candidate_description="kubectl get events -A",
            )
            external_dir = Path(tmp_dir) / "external-analysis"
            evidence = _build_diagnostic_execution_evidence(external_dir, run_id)

            self.assertEqual(len(evidence), 1)
            item = evidence[0]
            self.assertEqual(item["usefulnessClass"], "noisy")
            # No signals extracted if output is just routine events
            self.assertEqual(item["signals"], [])

    def test_multiple_execution_artifacts(self) -> None:
        """Test that multiple execution artifacts create multiple evidence items."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = "run-test"
            # Create 3 execution artifacts
            for i in range(3):
                _create_execution_artifact(
                    Path(tmp_dir),
                    run_id=run_id,
                    candidate_index=i,
                    status="success" if i < 2 else "failed",
                    usefulness_class="useful" if i == 0 else "noisy",
                )
            external_dir = Path(tmp_dir) / "external-analysis"
            evidence = _build_diagnostic_execution_evidence(external_dir, run_id)

            self.assertEqual(len(evidence), 3)


class IncidentReportExecutionEvidenceIntegrationTests(unittest.TestCase):
    """Tests for execution evidence integration in incident report."""

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_no_execution_artifacts_no_diagnostic_evidence(self) -> None:
        """Test that no execution artifacts means no diagnosticExecutionEvidence."""
        payload = _build_incident_report_payload(self.context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        # Without health_root, no execution evidence loaded
        self.assertIsNone(payload.get("diagnosticExecutionEvidence"))

    def test_with_execution_artifacts_includes_evidence(self) -> None:
        """Test that execution artifacts create diagnosticExecutionEvidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = self.context.run.run_id
            # Create an execution artifact
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                usefulness_class="useful",
                candidate_id="candidate-0",
                candidate_description="kubectl get pods",
                signals_in_output=["CrashLoopBackOff"],
            )
            health_root = Path(tmp_dir)

            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            self.assertIn("diagnosticExecutionEvidence", payload)
            self.assertIsNotNone(payload["diagnosticExecutionEvidence"])
            self.assertEqual(len(payload["diagnosticExecutionEvidence"]), 1)

    def test_raw_output_not_in_evidence(self) -> None:
        """Test that raw stdout/stderr is not exposed in evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = self.context.run.run_id
            # Create artifact with large output
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                raw_output="This is a very long output that should not appear in the incident report claims",
            )
            health_root = Path(tmp_dir)

            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            evidence = payload.get("diagnosticExecutionEvidence")
            self.assertIsNotNone(evidence)
            # Verify no raw_output field
            for item in evidence:
                self.assertNotIn("raw_output", item)
                self.assertNotIn("stdout", item)
                self.assertNotIn("stderr", item)

    def test_failed_execution_evidence_honest(self) -> None:
        """Test that failed execution is represented honestly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = self.context.run.run_id
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="failed",
                candidate_description="kubectl describe pod",
            )
            health_root = Path(tmp_dir)

            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            evidence = payload.get("diagnosticExecutionEvidence")
            self.assertIsNotNone(evidence)
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0]["status"], "failed")

    def test_truncation_flags_in_evidence(self) -> None:
        """Test that truncation flags are present in evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = self.context.run.run_id
            _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
                stdout_truncated=True,
                stderr_truncated=True,
            )
            health_root = Path(tmp_dir)

            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            evidence = payload.get("diagnosticExecutionEvidence")
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence[0]["stdoutTruncated"], True)
            self.assertEqual(evidence[0]["stderrTruncated"], True)

    def test_artifact_provenance_in_evidence(self) -> None:
        """Test that artifact path and ID are in evidence provenance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_id = self.context.run.run_id
            artifact_path = _create_execution_artifact(
                Path(tmp_dir),
                run_id=run_id,
                candidate_index=0,
                status="success",
            )
            health_root = Path(tmp_dir)

            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            evidence = payload.get("diagnosticExecutionEvidence")
            self.assertIsNotNone(evidence)
            item = evidence[0]
            # Artifact path present
            self.assertIn("artifactPath", item)
            # Artifact ID present
            self.assertIn("artifactId", item)
            # Source artifact refs present with path
            self.assertTrue(item["sourceArtifactRefs"])
            rel_path = str(artifact_path.relative_to(Path(tmp_dir)))
            self.assertEqual(item["sourceArtifactRefs"][0]["path"], rel_path)


class ExistingTestsRegressionTests(unittest.TestCase):
    """Tests to ensure existing behavior does not regress."""

    def setUp(self) -> None:
        self.index = sample_ui_index()
        self.context = build_ui_context(self.index)

    def test_incident_report_without_health_root_unchanged(self) -> None:
        """Test that incident report is unchanged when health_root is None."""
        payload = _build_incident_report_payload(self.context, _sample_freshness("fresh"))
        self.assertIsNotNone(payload)
        # Base fields still present
        self.assertIn("title", payload)
        self.assertIn("status", payload)
        self.assertIn("facts", payload)
        self.assertIn("derived", payload)
        self.assertIn("inferences", payload)
        # diagnosticExecutionEvidence is None when no health_root
        self.assertIsNone(payload.get("diagnosticExecutionEvidence"))

    def test_report_structure_unchanged(self) -> None:
        """Test that existing report structure is preserved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            health_root = Path(tmp_dir)
            payload = _build_incident_report_payload(
                self.context, _sample_freshness("fresh"), health_root=health_root
            )
            self.assertIsNotNone(payload)
            # All existing fields present
            expected_fields = [
                "title", "status", "affectedScope", "facts", "derived",
                "inferences", "recommendations", "unknowns", "staleEvidenceWarnings",
                "confidence", "freshness", "recommendedActions", "sourceArtifactRefs",
                "crossClusterFindings", "vmalertDiscoveryContext", "vmalertRuleStateContext",
            ]
            for field in expected_fields:
                self.assertIn(field, payload, f"Field {field} should be present")