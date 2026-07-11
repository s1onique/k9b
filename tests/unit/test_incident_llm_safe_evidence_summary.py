"""Unit tests for LLM-safe evidence boundary - RedactedEvidenceSummary and projections.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.

Tests for:
- RedactedEvidenceSummary serialization
- evidence_artifact_to_llm_safe_summary projection
- Prompt/case-file builder uses safe types
- No raw storage_ref in serialized LLM case-file evidence block
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_evidence import (
    ArtifactId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRole,
    ReviewPacketStorageRef,
    evidence_artifact_to_llm_safe_summary,
    make_llm_safe_artifact_ref,
    make_safe_evidence_excerpt,
    make_safe_relative_artifact_path,
)
from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    RedactedEvidenceSummary,
)


def _make_llm_safe(text: str) -> str:
    """Helper to produce an LLMSafeEvidenceText via the projection pipeline."""
    from k8s_diag_agent.collect.incident_evidence_redaction import (
        RawEvidenceText,
        project_raw_evidence_text_for_llm,
    )

    return str(project_raw_evidence_text_for_llm(RawEvidenceText(text), max_chars=500))


class TestMakeSafeEvidenceExcerpt:
    """Tests for make_safe_evidence_excerpt validation."""

    def test_accepts_valid_excerpt(self) -> None:
        """Accepts valid excerpt."""
        excerpt = make_safe_evidence_excerpt("Container restarted 5 times in the last hour", max_chars=100)
        assert excerpt == "Container restarted 5 times in the last hour"
        assert isinstance(excerpt, str)

    def test_rejects_empty_excerpt(self) -> None:
        """Rejects empty excerpt."""
        with pytest.raises(ValueError, match="cannot be empty"):
            make_safe_evidence_excerpt("", max_chars=100)


class TestRedactedEvidenceSummary:
    """Tests for RedactedEvidenceSummary dataclass."""

    def test_creates_summary_with_all_fields(self) -> None:
        """Creates summary with all fields."""
        artifact_id = ArtifactId("art-123")
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-123/evidence.json")
        summary_text = _make_llm_safe("Pod is in CrashLoopBackOff")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.LOG_EXCERPT,
            role=EvidenceRole.PRIMARY,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        assert summary.artifact_id == artifact_id
        assert summary.kind == EvidenceKind.LOG_EXCERPT
        assert summary.role == EvidenceRole.PRIMARY
        assert summary.safe_ref == safe_ref
        assert summary.summary == summary_text

    def test_creates_summary_without_safe_ref(self) -> None:
        """Creates summary without safe_ref (optional)."""
        artifact_id = ArtifactId("art-456")
        summary_text = _make_llm_safe("Event: BackOff restarting")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.LOG_EXCERPT,
            role=EvidenceRole.SUPPORTING,
            summary=summary_text,
        )

        assert summary.safe_ref is None

    def test_serializes_artifact_id_as_string(self) -> None:
        """Serializes artifact_id as string in to_dict."""
        artifact_id = ArtifactId("art-789")
        summary_text = _make_llm_safe("Deployment scaled")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            role=EvidenceRole.PRIMARY,
            summary=summary_text,
        )

        result = summary.to_dict()
        assert result["artifact_id"] == "art-789"
        assert isinstance(result["artifact_id"], str)

    def test_serializes_safe_ref_as_string(self) -> None:
        """Serializes safe_ref as string in to_dict."""
        artifact_id = ArtifactId("art-abc")
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-abc/summary.json")
        summary_text = _make_llm_safe("Test summary")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.RUN_SUMMARY,
            role=EvidenceRole.PRIMARY,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        result = summary.to_dict()
        assert result["safe_ref"] == "incidents/inc-abc/summary.json"
        assert isinstance(result["safe_ref"], str)

    def test_serializes_safe_ref_as_none_when_absent(self) -> None:
        """Serializes safe_ref as None when absent."""
        artifact_id = ArtifactId("art-xyz")
        summary_text = _make_llm_safe("Another summary")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.RUN_SUMMARY,
            role=EvidenceRole.SUPPORTING,
            summary=summary_text,
        )

        result = summary.to_dict()
        assert result["safe_ref"] is None

    def test_is_frozen(self) -> None:
        """Is immutable (frozen dataclass)."""
        artifact_id = ArtifactId("art-frozen")
        summary_text = _make_llm_safe("Immutable summary")

        summary = RedactedEvidenceSummary(
            artifact_id=artifact_id,
            kind=EvidenceKind.LOG_EXCERPT,
            role=EvidenceRole.PRIMARY,
            summary=summary_text,
        )

        with pytest.raises(AttributeError):
            summary.artifact_id = ArtifactId("art-modified")


class TestEvidenceArtifactToLLMSafeSummary:
    """Tests for evidence_artifact_to_llm_safe_summary projection function."""

    def test_accepts_llm_safe_artifact_ref(self) -> None:
        """Accepts LLMSafeArtifactRef as safe_ref."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-001"),
            kind=EvidenceKind.LOG_EXCERPT,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-001/log.json"),
        )
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-001/log.json")
        summary_text = _make_llm_safe("Pod restarted 3 times")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        assert isinstance(result, RedactedEvidenceSummary)
        assert result.artifact_id == artifact.artifact_id
        assert result.kind == EvidenceKind.LOG_EXCERPT
        assert result.safe_ref == safe_ref
        assert result.summary == summary_text

    def test_accepts_review_packet_storage_ref(self) -> None:
        """Accepts ReviewPacketStorageRef as safe_ref."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-002"),
            kind=EvidenceKind.REVIEW_PACKET,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-002/review.md"),
        )
        safe_ref = ReviewPacketStorageRef("incidents/inc-002/review.md")
        summary_text = _make_llm_safe("Review packet generated")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        assert isinstance(result, RedactedEvidenceSummary)
        assert result.safe_ref == safe_ref

    def test_accepts_none_safe_ref(self) -> None:
        """Accepts None as safe_ref."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-003"),
            kind=EvidenceKind.SNAPSHOT_BUNDLE,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-003/snapshot.json"),
        )
        summary_text = _make_llm_safe("Snapshot collected")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=None,
            summary=summary_text,
        )

        assert isinstance(result, RedactedEvidenceSummary)
        assert result.safe_ref is None

    def test_uses_properly_typed_llm_safe_artifact_ref(self) -> None:
        """Properly typed LLMSafeArtifactRef is accepted."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-004"),
            kind=EvidenceKind.LOG_EXCERPT,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-004/log.json"),
        )
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-004/log.json")
        summary_text = _make_llm_safe("Properly typed safe ref")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )
        assert isinstance(result, RedactedEvidenceSummary)
        assert result.safe_ref == safe_ref

    def test_accepts_properly_redacted_text(self) -> None:
        """Accepts properly typed RedactedEvidenceText."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-005"),
            kind=EvidenceKind.LOG_EXCERPT,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-005/log.json"),
        )
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-005/log.json")

        summary_text = _make_llm_safe("Properly typed redacted text")
        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )
        assert isinstance(result, RedactedEvidenceSummary)

    def test_rejects_non_evidence_artifact(self) -> None:
        """Rejects non-EvidenceArtifact objects."""
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-006/log.json")
        summary_text = _make_llm_safe("Summary text")

        with pytest.raises(TypeError, match="requires EvidenceArtifact"):
            evidence_artifact_to_llm_safe_summary(
                artifact="not an EvidenceArtifact",
                safe_ref=safe_ref,
                summary=summary_text,
            )

    def test_uses_supporting_role_by_default(self) -> None:
        """Uses SUPPORTING role by default for projected evidence."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-007"),
            kind=EvidenceKind.METRIC_WINDOW,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-007/metrics.json"),
        )
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-007/metrics.json")
        summary_text = _make_llm_safe("Metric anomaly detected")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        assert result.role == EvidenceRole.SUPPORTING


class TestNoRawStorageRefInSerializedEvidence:
    """Tests that serialized evidence blocks don't contain raw storage_ref."""

    def test_redacted_evidence_summary_no_raw_storage_ref(self) -> None:
        """RedactedEvidenceSummary.to_dict() doesn't expose raw storage_ref."""
        artifact = EvidenceArtifact(
            artifact_id=ArtifactId("art-008"),
            kind=EvidenceKind.LOG_EXCERPT,
            storage_ref=make_safe_relative_artifact_path("incidents/inc-008/log.json"),
        )
        safe_ref = make_llm_safe_artifact_ref("incidents/inc-008/log.json")
        summary_text = _make_llm_safe("Safe summary")

        result = evidence_artifact_to_llm_safe_summary(
            artifact=artifact,
            safe_ref=safe_ref,
            summary=summary_text,
        )

        serialized = result.to_dict()

        assert "safe_ref" in serialized
        assert "storage_ref" not in serialized
        assert "/var/lib" not in str(serialized.values())
        assert "/tmp/" not in str(serialized.values())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
