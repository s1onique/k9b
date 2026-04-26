"""Tests for Alertmanager durable learning boundary.

This module tests:
1. Feedback signal classification (durable vs run-scoped vs forbidden)
2. Pattern aggregation from review artifacts
3. Proposal candidate generation from stable patterns
4. Boundary enforcement (no silent cross-run changes, no sparse promotion)
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.external_analysis.alertmanager_durable_learning import (
    _DURABLE_SIGNALS,
    _FORBIDDEN_DURABLE_SIGNALS,
    _MIN_INSTANCES_PER_RUN,
    _MIN_RUNS_FOR_PROPOSAL,
    DurableFeedbackPattern,
    _extract_feedback_from_artifact,
    _is_review_artifact,
    aggregate_feedback_patterns,
    generate_proposal_candidates,
    scan_and_propose,
    write_proposal_candidates,
)


def _write_review_artifact(
    dir: Path,
    run_id: str,
    cluster_label: str,
    relevance: str,
    provenance: dict,
    timestamp: str | None = None,
    instance_suffix: str = "",
) -> Path:
    """Write a mock review artifact and return its path."""
    uuid = f"test-{hash((run_id, relevance, str(provenance), instance_suffix))}"[:8]
    filename = f"{run_id}-next-check-execution-alertmanager-review-{uuid}.json"
    path = dir / filename

    artifact = {
        "purpose": "next-check-execution-alertmanager-review",
        "run_id": run_id,
        "cluster_label": cluster_label,
        "alertmanager_relevance": relevance,
        "alertmanager_provenance": provenance,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "source_artifact": f"external-analysis/{run_id}-next-check-execution-0.json",
    }

    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


class TestFeedbackSignalClassification:
    """Tests for feedback signal trustworthiness classification."""

    def test_durable_signals_defined(self) -> None:
        """Test that durable signals are correctly defined."""
        assert "not_relevant" in _DURABLE_SIGNALS
        assert "noisy" in _DURABLE_SIGNALS
        assert len(_DURABLE_SIGNALS) == 2

    def test_forbidden_signals_defined(self) -> None:
        """Test that forbidden signals are correctly defined."""
        assert "relevant" in _FORBIDDEN_DURABLE_SIGNALS
        assert "unsure" in _FORBIDDEN_DURABLE_SIGNALS
        assert len(_FORBIDDEN_DURABLE_SIGNALS) == 2

    def test_no_overlap_between_durable_and_forbidden(self) -> None:
        """Test that durable and forbidden signals are mutually exclusive."""
        assert _DURABLE_SIGNALS.isdisjoint(_FORBIDDEN_DURABLE_SIGNALS)


class TestReviewArtifactParsing:
    """Tests for review artifact identification and parsing."""

    def test_review_artifact_identification(self) -> None:
        """Test identification of review artifacts by filename pattern."""
        assert _is_review_artifact(
            Path("run-abc-next-check-execution-alertmanager-review-1234abcd.json")
        )
        assert not _is_review_artifact(
            Path("run-abc-next-check-execution-0.json")
        )
        assert not _is_review_artifact(
            Path("run-abc-next-check-execution-usefulness-review-1234abcd.json")
        )

    def test_feedback_extraction_from_artifact(self) -> None:
        """Test feedback extraction from parsed artifact."""
        artifact = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_provenance": {
                "matchedDimensions": ["namespace"],
                "matchedValues": {"namespace": ["monitoring"]},
            },
        }
        result = _extract_feedback_from_artifact(artifact)
        assert result is not None
        assert result == ("namespace", "monitoring", "not_relevant")

    def test_forbidden_signals_not_extracted(self) -> None:
        """Test that forbidden signals return None."""
        for signal in _FORBIDDEN_DURABLE_SIGNALS:
            artifact = {
                "alertmanager_relevance": signal,
                "alertmanager_provenance": {
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            }
            result = _extract_feedback_from_artifact(artifact)
            assert result is None, f"Signal {signal} should not be extracted"

    def test_missing_provenance_not_extracted(self) -> None:
        """Test that artifacts without provenance are not extracted."""
        artifact = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_provenance": None,
        }
        result = _extract_feedback_from_artifact(artifact)
        assert result is None

    def test_empty_matched_dims_not_extracted(self) -> None:
        """Test that artifacts with empty matched dimensions are not extracted."""
        artifact = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_provenance": {
                "matchedDimensions": [],
                "matchedValues": {},
            },
        }
        result = _extract_feedback_from_artifact(artifact)
        assert result is None


class TestPatternAggregation:
    """Tests for feedback pattern aggregation."""

    def test_empty_directory_returns_no_patterns(self, tmp_path: Path) -> None:
        """Test that empty directory returns no patterns."""
        patterns = aggregate_feedback_patterns(tmp_path)
        assert len(patterns) == 0

    def test_single_run_single_instance_not_aggregated(self, tmp_path: Path) -> None:
        """Test that single run with single instance doesn't form a pattern."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        _write_review_artifact(
            external_analysis,
            run_id="run-1",
            cluster_label="cluster-a",
            relevance="not_relevant",
            provenance={
                "matchedDimensions": ["namespace"],
                "matchedValues": {"namespace": ["monitoring"]},
            },
        )

        patterns = aggregate_feedback_patterns(tmp_path)
        # Single instance doesn't meet threshold
        assert len(patterns) == 0

    def test_multiple_runs_aggregated_into_pattern(self, tmp_path: Path) -> None:
        """Test that multiple runs form an aggregated pattern."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        # Write artifacts from 3 different runs
        for i in range(3):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-{i+1}",
                cluster_label="cluster-a",
                relevance="not_relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        patterns = aggregate_feedback_patterns(tmp_path)
        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.dimension == "namespace"
        assert pattern.values == frozenset(["monitoring"])
        assert pattern.signal == "not_relevant"
        assert pattern.run_count == 3
        assert pattern.total_instances == 3

    def test_cluster_filtering(self, tmp_path: Path) -> None:
        """Test that cluster filter works correctly."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        # Write artifacts from 2 different clusters - 2 instances each to meet threshold
        for i in range(2):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-a-{i}",
                cluster_label="cluster-a",
                relevance="not_relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )
        for i in range(2):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-b-{i}",
                cluster_label="cluster-b",
                relevance="not_relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        # Filter by cluster-a only
        patterns = aggregate_feedback_patterns(tmp_path, cluster_filter="cluster-a")
        assert len(patterns) == 1
        assert "cluster-a" in patterns[0].cluster_labels
        assert "cluster-b" not in patterns[0].cluster_labels

    def test_different_signals_separated(self, tmp_path: Path) -> None:
        """Test that different signals are tracked separately."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        # Write 2 instances for not_relevant to meet threshold
        for i in range(2):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-nr-{i}",
                cluster_label="cluster-a",
                relevance="not_relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )
        # Write 2 instances for noisy to meet threshold
        for i in range(2):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-noisy-{i}",
                cluster_label="cluster-a",
                relevance="noisy",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        patterns = aggregate_feedback_patterns(tmp_path)
        assert len(patterns) == 2
        signals = {p.signal for p in patterns}
        assert signals == {"not_relevant", "noisy"}


class TestProposalThreshold:
    """Tests for proposal threshold enforcement."""

    def test_meets_proposal_threshold_requires_min_runs(self) -> None:
        """Test that proposal threshold requires minimum runs."""
        pattern_barely = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="not_relevant",
            run_count=_MIN_RUNS_FOR_PROPOSAL,  # Exactly 3
            total_instances=_MIN_RUNS_FOR_PROPOSAL * _MIN_INSTANCES_PER_RUN,  # 6
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )
        assert pattern_barely.meets_proposal_threshold

        pattern_insufficient = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="not_relevant",
            run_count=_MIN_RUNS_FOR_PROPOSAL - 1,  # 2
            total_instances=4,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )
        assert not pattern_insufficient.meets_proposal_threshold

    def test_is_actionable_requires_durable_signal(self) -> None:
        """Test that actionable requires durable signal."""
        pattern = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="relevant",  # Forbidden signal
            run_count=5,
            total_instances=10,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )
        assert not pattern.is_actionable


class TestProposalCandidateGeneration:
    """Tests for proposal candidate generation."""

    def test_proposal_generated_from_actionable_pattern(self) -> None:
        """Test that proposals are generated from actionable patterns."""
        pattern = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="noisy",
            run_count=5,
            total_instances=12,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(["cluster-a"]),
        )

        candidates = generate_proposal_candidates((pattern,), "cluster-a")
        assert len(candidates) == 1
        assert candidates[0].cluster_label == "cluster-a"
        assert candidates[0].proposal_type == "alertmanager_dimension_suppression"
        assert "suppress_dimension" in candidates[0]._build_promotion_payload()["action"]

    def test_no_proposal_from_non_actionable_pattern(self) -> None:
        """Test that proposals are not generated from non-actionable patterns."""
        pattern = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="relevant",  # Forbidden
            run_count=5,
            total_instances=12,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )

        candidates = generate_proposal_candidates((pattern,), "cluster-a")
        assert len(candidates) == 0

    def test_proposal_id_unique(self) -> None:
        """Test that proposal IDs are unique."""
        pattern_a = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="noisy",
            run_count=5,
            total_instances=12,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )
        pattern_b = DurableFeedbackPattern(
            dimension="cluster",
            values=frozenset(["minikube"]),
            signal="noisy",
            run_count=5,
            total_instances=12,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )

        candidates = generate_proposal_candidates((pattern_a, pattern_b), "cluster-a")
        ids = {c.proposal_id for c in candidates}
        assert len(ids) == len(candidates), "Proposal IDs should be unique"


class TestProposalArtifactWriting:
    """Tests for proposal artifact persistence."""

    def test_proposal_artifacts_written(self, tmp_path: Path) -> None:
        """Test that proposal artifacts are written correctly."""
        pattern = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring"]),
            signal="noisy",
            run_count=5,
            total_instances=12,
            source_artifacts=("artifact1.json",),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(["cluster-a"]),
        )

        candidates = generate_proposal_candidates((pattern,), "cluster-a")
        paths = write_proposal_candidates(tmp_path, candidates)

        assert len(paths) == 1
        assert paths[0].exists()
        assert "alertmanager-durable-proposals" in str(paths[0])

        # Verify artifact content
        written = json.loads(paths[0].read_text())
        assert written["proposal_type"] == "alertmanager_dimension_suppression"
        assert written["pattern"]["dimension"] == "namespace"


class TestScanAndPropose:
    """Tests for the main entry point."""

    def test_scan_with_insufficient_data(self, tmp_path: Path) -> None:
        """Test scan with insufficient feedback returns no candidates."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        # Write only 2 runs (below threshold)
        for i in range(2):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-{i+1}",
                cluster_label="cluster-a",
                relevance="not_relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        candidates = scan_and_propose(tmp_path, write_artifacts=False)
        assert len(candidates) == 0

    def test_scan_with_sufficient_data(self, tmp_path: Path) -> None:
        """Test scan with sufficient feedback generates candidates."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        # Write 3 runs with 2+ instances per run
        for run_i in range(3):
            for inst_i in range(2):
                _write_review_artifact(
                    external_analysis,
                    run_id=f"run-{run_i}",
                    cluster_label="cluster-a",
                    relevance="noisy",
                    provenance={
                        "matchedDimensions": ["namespace"],
                        "matchedValues": {"namespace": ["monitoring"]},
                    },
                    instance_suffix=f"{run_i}-{inst_i}",
                )

        candidates = scan_and_propose(tmp_path, write_artifacts=False)
        assert len(candidates) == 1
        assert candidates[0].pattern.signal == "noisy"


class TestBoundaryEnforcement:
    """Tests that verify the boundary enforcement."""

    def test_no_proposal_from_relevant_signal(self, tmp_path: Path) -> None:
        """Test that 'relevant' signal never generates proposals."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        for i in range(5):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-{i+1}",
                cluster_label="cluster-a",
                relevance="relevant",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        patterns = aggregate_feedback_patterns(tmp_path)
        # 'relevant' signals should not be extracted
        assert len(patterns) == 0

    def test_no_proposal_from_unsure_signal(self, tmp_path: Path) -> None:
        """Test that 'unsure' signal never generates proposals."""
        external_analysis = tmp_path / "external-analysis"
        external_analysis.mkdir()

        for i in range(5):
            _write_review_artifact(
                external_analysis,
                run_id=f"run-{i+1}",
                cluster_label="cluster-a",
                relevance="unsure",
                provenance={
                    "matchedDimensions": ["namespace"],
                    "matchedValues": {"namespace": ["monitoring"]},
                },
            )

        patterns = aggregate_feedback_patterns(tmp_path)
        # 'unsure' signals should not be extracted
        assert len(patterns) == 0

    def test_proposal_rationale_text_generated(self) -> None:
        """Test that proposal rationale is human-readable."""
        pattern_noisy = DurableFeedbackPattern(
            dimension="namespace",
            values=frozenset(["monitoring", "prometheus"]),
            signal="noisy",
            run_count=4,
            total_instances=8,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )

        rationale = pattern_noisy.proposal_rationale
        assert "namespace" in rationale
        assert "monitoring" in rationale
        assert "noisy" in rationale
        assert "4 runs" in rationale

        pattern_not_relevant = DurableFeedbackPattern(
            dimension="cluster",
            values=frozenset(["minikube"]),
            signal="not_relevant",
            run_count=3,
            total_instances=6,
            source_artifacts=(),
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            cluster_labels=frozenset(),
        )

        rationale = pattern_not_relevant.proposal_rationale
        assert "stop-tracking" in rationale
        assert "minikube" in rationale

    def test_single_dimension_extraction_only(self) -> None:
        """Test that only the first matched dimension is extracted.
        
        This documents the current limitation: artifacts with multiple matched
        dimensions contribute only the first extracted signal. This is a known
        limitation of the current implementation - not a bug, but documented behavior.
        """
        from k8s_diag_agent.external_analysis.alertmanager_durable_learning import (
            _extract_feedback_from_artifact,
        )
        
        # Artifact with two matched dimensions
        artifact = {
            "alertmanager_relevance": "not_relevant",
            "alertmanager_provenance": {
                "matchedDimensions": ["namespace", "cluster"],
                "matchedValues": {
                    "namespace": ["monitoring", "default"],
                    "cluster": ["minikube", "prod"],
                },
            },
        }
        
        result = _extract_feedback_from_artifact(artifact)
        assert result is not None
        
        # Only first dimension/value extracted
        assert result[0] == "namespace"
        assert result[1] == "monitoring"
        assert result[2] == "not_relevant"
        
        # Second dimension not returned (known limitation)
        # If multi-dimension extraction is needed, the implementation would need to
        # return a list of tuples instead of a single tuple.
