"""Diagnostic execution evidence builder for incident reports.

This module projects diagnostic command execution artifacts as compact evidence
in incident reports without exposing raw stdout/stderr. It reuses the shared
execution artifact index utilities for consistent artifact discovery.

Design constraints:
- Use compact digest-style evidence, not raw command output
- Keep evidence boring, deterministic, and schema-friendly
- Do not infer root cause from execution output
- Failed/truncated executions are still evidence and must be represented honestly
- Provenance: artifact path and/or artifact ID, execution status, candidate info,
  usefulness class, truncation flags, and compact diagnostic signals

Language constraints:
- "Diagnostic command executed" / "Execution returned useful signal"
- "Execution failed" / "Execution output was truncated" / "Execution produced no useful signal"
- NOT "Root cause proven" / "Incident resolved" / "Cluster is healthy"
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .api_payloads import ArtifactLink, DiagnosticExecutionEvidencePayload

# Pattern for extracting run_id from execution artifact filenames
_EXECUTION_MARKER_PATTERN = re.compile(r"^(.+?)(-next-check-execution(?:-\d+)?)\.json$")


def _extract_run_id_from_filename(filename: str) -> str | None:
    """Extract run_id from an execution artifact filename."""
    match = _EXECUTION_MARKER_PATTERN.match(filename)
    if match:
        return match.group(1)
    return None


def _extract_signal_markers_from_output(output: str | None) -> list[str]:
    """Extract diagnostic signal markers from output text.

    Args:
        output: Combined output text to scan

    Returns:
        List of detected marker names (deduplicated, order-stable)
    """
    if not output:
        return []

    markers: list[str] = []
    seen: set[str] = set()

    # Signal markers to extract from K8s diagnostic output
    signal_markers = [
        ("CrashLoopBackOff", "CrashLoopBackOff"),
        ("ImagePullBackOff", "ImagePullBackOff"),
        ("ErrImagePull", "ErrImagePull"),
        ("Evicted", "Evicted"),
        ("OOMKilled", "OOMKilled"),
        ("Terminating", "Terminating"),
        ("FailedScheduling", "FailedScheduling"),
        ("ReadinessProbeFailed", "ReadinessProbeFailed"),
        ("LivenessProbeFailed", "LivenessProbeFailed"),
        ("StartupProbeFailed", "StartupProbeFailed"),
        ("forbidden", "Forbidden"),
        ("unauthorized", "Unauthorized"),
        ("permission denied", "PermissionDenied"),
        ("not found", "NotFound"),
        ("doesn't exist", "NotFound"),
        ("no such host", "DNSError"),
        ("connection refused", "ConnectionRefused"),
        ("TLS|certificate|ssl", "TLSCertError"),
        ("timeout|timed out", "Timeout"),
        ("insufficient|quota", "ResourceQuota"),
        ("memory limit|cpu limit", "ResourceLimit"),
    ]

    for pattern_str, marker_name in signal_markers:
        if marker_name in seen:
            continue
        if re.search(pattern_str, output, re.IGNORECASE):
            markers.append(marker_name)
            seen.add(marker_name)

    return markers


def _scan_execution_artifacts_for_incident_report(
    external_analysis_dir: Path,
    run_id: str,
) -> list[dict[str, Any]]:
    """Scan external-analysis directory for execution artifacts matching this run.

    Returns list of parsed execution artifact records suitable for incident report evidence.

    This function uses the same discovery logic as _scan_execution_artifacts_for_worklist
    to ensure consistency. It reads artifacts with purpose=next-check-execution and
    extracts compact evidence fields without raw output.
    """
    results: list[dict[str, Any]] = []

    if not external_analysis_dir.is_dir():
        return results

    # Find all execution artifact files for this run
    all_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))

    for artifact_file in sorted(all_files):
        try:
            raw = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue

            # Verify purpose
            purpose = raw.get("purpose")
            if purpose != "next-check-execution":
                continue

            # Extract run_id: use artifact field as primary, filename as fallback
            artifact_run_id = raw.get("run_id")
            if isinstance(artifact_run_id, str) and artifact_run_id:
                file_run_id = artifact_run_id
            else:
                file_run_id = _extract_run_id_from_filename(artifact_file.name)

            if not file_run_id or file_run_id != run_id:
                continue

            # Extract execution data from payload
            exec_payload = raw.get("payload", {})
            if not isinstance(exec_payload, dict):
                continue

            # Extract fields for evidence
            status = raw.get("status", "unknown")
            if not isinstance(status, str):
                status = "unknown"

            # Extract candidate info
            candidate_id = exec_payload.get("candidateId") or exec_payload.get("candidate_id")
            candidate_description = exec_payload.get("description")
            if not candidate_description:
                # Try to derive from command
                command = exec_payload.get("command") or exec_payload.get("commandText")
                if command and isinstance(command, str):
                    candidate_description = command[:200] if len(command) > 200 else command

            # Extract target cluster
            target_cluster = (
                exec_payload.get("clusterLabel")
                or exec_payload.get("cluster_label")
                or exec_payload.get("targetCluster")
            )

            # Extract usefulness class
            usefulness_class = exec_payload.get("usefulnessClass") or exec_payload.get("usefulness_class")

            # Extract truncation flags (handle snake_case from artifact schema)
            # Use explicit is not None check since False is a valid value (not truncated)
            stdout_truncated = raw.get("stdout_truncated")
            if stdout_truncated is None:
                stdout_truncated = raw.get("stdoutTruncated")
            stderr_truncated = raw.get("stderr_truncated")
            if stderr_truncated is None:
                stderr_truncated = raw.get("stderrTruncated")

            # Extract compact signals from raw_output (no raw output in evidence)
            raw_output = raw.get("raw_output")
            signals = _extract_signal_markers_from_output(raw_output)[:10]  # Limit to 10 signals

            # Extract artifact ID from artifact_path
            artifact_id = raw.get("artifact_id")

            # Compute artifact path relative to external_analysis_dir
            try:
                artifact_path = str(artifact_file.relative_to(external_analysis_dir.parent))
            except ValueError:
                artifact_path = str(artifact_file)

            results.append({
                "artifact_path": artifact_path,
                "artifact_id": artifact_id,
                "status": status,
                "candidate_id": str(candidate_id) if candidate_id else None,
                "candidate_description": candidate_description,
                "target_cluster": str(target_cluster) if target_cluster else None,
                "usefulness_class": usefulness_class,
                "signals": signals,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            })

        except (OSError, json.JSONDecodeError):
            continue

    return results


def _build_diagnostic_execution_evidence(
    external_analysis_dir: Path | None,
    run_id: str,
) -> list[DiagnosticExecutionEvidencePayload]:
    """Build diagnostic execution evidence from execution artifacts.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to filter by

    Returns:
        List of DiagnosticExecutionEvidencePayload for each execution artifact found
    """
    if external_analysis_dir is None:
        return []

    records = _scan_execution_artifacts_for_incident_report(external_analysis_dir, run_id)

    evidence: list[DiagnosticExecutionEvidencePayload] = []
    for record in records:
        artifact_path = record.get("artifact_path")
        source_refs: list[ArtifactLink] = []
        if artifact_path:
            source_refs.append({"label": "Next-Check Execution", "path": artifact_path})

        evidence.append({
            "artifactPath": record.get("artifact_path"),
            "artifactId": record.get("artifact_id"),
            "status": record.get("status", "unknown"),
            "candidateId": record.get("candidate_id"),
            "candidateDescription": record.get("candidate_description"),
            "targetCluster": record.get("target_cluster"),
            "usefulnessClass": record.get("usefulness_class"),
            "signals": record.get("signals", []),
            "stdoutTruncated": record.get("stdout_truncated"),
            "stderrTruncated": record.get("stderr_truncated"),
            "sourceArtifactRefs": source_refs,
        })

    return evidence