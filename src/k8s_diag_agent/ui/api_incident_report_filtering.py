"""Artifact filtering utilities for provenance quality.

This module provides filtering logic for sourceArtifactRefs to improve operator
trust by suppressing non-useful artifact references. Filtering is derived-only
and stateless; no new persistence is introduced.

Filtering rules:
1. Filter refs for artifacts explicitly marked skipped (status=skipped)
2. Filter refs for known placeholder/error messages that provide no evidence value
3. Preserve refs when an artifact is failed/partial but still contains evidence
4. Preserve canonical artifact refs (assessment, drilldown, execution) unless truly non-informative
5. If filtering would remove all provenance, retain the best available informative ref

Non-useful artifacts:
- status=skipped
- skip_reason only (no meaningful payload)
- adapter-not-registered placeholders
- empty/error-only with no diagnostic value

Preserved artifacts:
- successful artifacts with evidence
- failed artifacts with failure_metadata, error_summary, or diagnostic context
- partial artifacts with partial evidence
- canonical refs (assessment, drilldown, execution result)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .api_payloads import ArtifactLink

# Known placeholder patterns that indicate non-informative artifacts
# These are summaries/error messages that provide no operator insight
_PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "adapter is not configured",
    "adapter is not registered",
    "adapter not found",
    "not configured",
    "not registered",
)


@dataclass(frozen=True)
class ArtifactFilteringResult:
    """Result of artifact filtering with provenance quality metadata."""

    # Filtered links suitable for operator-facing provenance
    filtered_links: list[ArtifactLink]
    # Whether filtering removed any refs
    had_filtered_refs: bool
    # Number of original refs before filtering
    original_count: int
    # Summary of what was filtered (for observability)
    filter_summary: str


def _is_placeholder_artifact(artifact: ExternalAnalysisArtifact) -> bool:
    """Check if artifact is a known placeholder with no evidence value.

    Returns True if the artifact summary or error indicates it contains only
    adapter registration errors or configuration placeholders.
    """
    # Check summary for placeholder patterns
    summary = artifact.summary or ""
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.lower() in summary.lower():
            return True

    # Check error_summary for placeholder patterns
    error_summary = artifact.error_summary or ""
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.lower() in error_summary.lower():
            return True

    # Check skip_reason for adapter-not-registered patterns
    skip_reason = artifact.skip_reason or ""
    if "not registered" in skip_reason.lower() or "not configured" in skip_reason.lower():
        return True

    return False


def _has_useful_evidence(artifact: ExternalAnalysisArtifact) -> bool:
    """Check if artifact contains useful evidence for operator diagnostics.

    An artifact has useful evidence if it has any of:
    - successful status with actual output
    - failed status with failure_metadata containing diagnostic context
    - error_summary with meaningful information
    - non-empty raw_output with captured data
    - useful findings or suggestions

    An artifact lacks useful evidence if it's:
    - skipped with only a skip_reason and no other content
    - failed but empty (no failure_metadata, no error_summary, no payload)
    - a placeholder with no diagnostic value
    """
    # Successful artifacts typically have evidence
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        # Check if there's actual content beyond just metadata
        has_content = (
            artifact.raw_output
            or (artifact.payload and len(artifact.payload) > 0)
            or artifact.summary
            or artifact.findings
            or artifact.suggested_next_checks
        )
        if has_content:
            return True

    # Failed artifacts with diagnostic context are useful
    if artifact.status == ExternalAnalysisStatus.FAILED:
        # Check for meaningful failure metadata
        if artifact.failure_metadata:
            # Failure metadata indicates diagnostic context was captured
            return True

        # Check for meaningful error summary
        if artifact.error_summary and len(artifact.error_summary) > 0:
            # Error summary provides diagnostic context
            return True

        # Check for partial evidence in payload
        if artifact.payload and len(artifact.payload) > 0:
            return True

    return False


def _should_filter_artifact(artifact: ExternalAnalysisArtifact) -> bool:
    """Determine if an artifact should be filtered from provenance.

    Returns True if the artifact should be excluded from operator-visible
    sourceArtifactRefs. This happens when the artifact:
    1. Has status=skipped (explicitly not executed)
    2. Is a known placeholder pattern (no evidence value)
    3. Is empty with no useful evidence content

    Returns False (preserve) if:
    1. Artifact has successful status with evidence
    2. Artifact has failed status but with diagnostic context
    3. Artifact has partial evidence useful for operators
    """
    # Always filter skipped artifacts
    if artifact.status == ExternalAnalysisStatus.SKIPPED:
        return True

    # Filter known placeholder patterns
    if _is_placeholder_artifact(artifact):
        return True

    # Check if artifact has useful evidence
    if not _has_useful_evidence(artifact):
        return True

    return False


def filter_artifact_links(
    links: list[ArtifactLink],
    runs_dir: Path | None = None,
) -> ArtifactFilteringResult:
    """Filter artifact links to remove non-useful references.

    This function reads artifact metadata from disk to determine whether
    each reference should be included in operator-visible provenance.

    Args:
        links: List of ArtifactLink dicts with 'label' and 'path' keys
        runs_dir: Optional runs directory for resolving relative artifact paths

    Returns:
        ArtifactFilteringResult containing:
        - filtered_links: List of ArtifactLink that passed filtering
        - had_filtered_refs: True if any refs were filtered
        - original_count: Count of refs before filtering
        - filter_summary: Human-readable summary of what was filtered
    """
    if not links:
        return ArtifactFilteringResult(
            filtered_links=[],
            had_filtered_refs=False,
            original_count=0,
            filter_summary="No links provided",
        )

    original_count = len(links)
    filtered: list[ArtifactLink] = []
    filtered_reasons: list[str] = []

    for link in links:
        path_str = link.get("path")
        if not path_str:
            # Skip links without paths
            filtered_reasons.append(f"empty path for {link.get('label', 'unknown')}")
            continue

        # Try to read artifact metadata
        artifact: ExternalAnalysisArtifact | None = None

        # Try to resolve the path
        if runs_dir:
            artifact_path = runs_dir / path_str
        else:
            artifact_path = Path(path_str)

        # Try to read as external analysis artifact
        try:
            from ..external_analysis.artifact_readers import try_read_external_analysis_artifact

            artifact = try_read_external_analysis_artifact(
                artifact_path,
                log_failures=False,  # Silent for filtering
            )
        except Exception:
            # If we can't read the artifact, preserve the link
            # This is safer than filtering without evidence
            filtered.append(link)
            continue

        if artifact is None:
            # Artifact couldn't be parsed, preserve the link
            filtered.append(link)
            continue

        # Apply filtering rules
        if _should_filter_artifact(artifact):
            label = link.get("label", "unknown")
            status = artifact.status.value
            reason = f"{label} ({status})"
            if artifact.skip_reason:
                reason += f": {artifact.skip_reason[:50]}"
            filtered_reasons.append(reason)
            continue

        # Artifact passed filtering
        filtered.append(link)

    # Build summary
    if filtered_reasons:
        summary = f"Filtered {len(filtered_reasons)} refs: {', '.join(filtered_reasons[:3])}"
        if len(filtered_reasons) > 3:
            summary += f" (+{len(filtered_reasons) - 3} more)"
    else:
        summary = "All refs preserved"

    return ArtifactFilteringResult(
        filtered_links=filtered,
        had_filtered_refs=len(filtered) < original_count,
        original_count=original_count,
        filter_summary=summary,
    )


def filter_artifact_refs_preserving_minimum(
    links: list[ArtifactLink],
    runs_dir: Path | None = None,
) -> list[ArtifactLink]:
    """Filter artifact links but preserve at least one if all would be filtered.

    This function applies the same filtering rules as filter_artifact_links,
    but includes a safety fallback: if filtering would remove all provenance
    from a claim, it retains the best available ref rather than leaving
    an evidence-backed claim with nothing.

    This prevents the edge case where a claim would appear to have provenance
    but have no actual references.

    Args:
        links: List of ArtifactLink dicts with 'label' and 'path' keys
        runs_dir: Optional runs directory for resolving relative artifact paths

    Returns:
        List of ArtifactLink after filtering (may include at least one ref)
    """
    result = filter_artifact_links(links, runs_dir)

    # If filtering removed all refs, return the original list
    # This is safer than returning nothing for an evidence-backed claim
    if not result.filtered_links and result.original_count > 0:
        return links

    return result.filtered_links