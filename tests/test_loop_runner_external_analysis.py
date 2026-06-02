"""Tests for loop_runner_external_analysis helper.

Tests behavior-preservation for the external analysis seam extracted from
HealthLoopRunner._run_external_analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisAdapter, ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import ExternalAnalysisPolicy
from k8s_diag_agent.health.loop import HealthSnapshotRecord, HealthTarget
from k8s_diag_agent.health.loop_runner_external_analysis import run_external_analysis_for_records
from k8s_diag_agent.health.loop_types import ManualExternalAnalysisRequest


@dataclass(frozen=True)
class MockAssessment:
    artifact_path: str


def _create_mock_record(label: str, assessment_artifact_path: str | None = None) -> HealthSnapshotRecord:
    """Create a mock HealthSnapshotRecord with minimal required fields."""
    target = HealthTarget(
        context=label,
        label=label,
        monitor_health=True,
        watched_helm_releases=(),
        watched_crd_families=(),
    )
    # Create mock snapshot
    snapshot = MagicMock()
    snapshot.context = label
    # Create mock assessment
    assessment: MagicMock | None = None
    if assessment_artifact_path:
        assessment = MagicMock()
        assessment.artifact_path = assessment_artifact_path
    # Create mock baseline_policy
    baseline_policy = MagicMock()
    # Create mock path
    path = Path(f"/tmp/{label}")
    
    # Use MagicMock for all required fields
    record = MagicMock(spec=HealthSnapshotRecord)
    record.target = target
    record.snapshot = snapshot
    record.path = path
    record.baseline_policy = baseline_policy
    record.assessment = assessment
    record.pattern_reasons = ()
    record.pattern_metadata = {}
    record.image_pull_secret_insight = None
    
    # Make refs() work
    def mock_refs() -> tuple[str, str]:
        return (label, label)
    record.refs = mock_refs
    
    return record


class MockAdapter(ExternalAnalysisAdapter):
    name = "mock-adapter"

    def __init__(
        self,
        status: ExternalAnalysisStatus = ExternalAnalysisStatus.SUCCESS,
        summary: str = "mock result",
    ) -> None:
        super().__init__(command=None)
        self._status = status
        self._summary = summary
        self.calls: list[ExternalAnalysisRequest] = []

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        self.calls.append(request)
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            run_label="test",
            source_artifact=request.source_artifact,
            summary=self._summary,
            findings=(),
            suggested_next_checks=(),
            status=self._status,
            timestamp=datetime.now(UTC),
        )


class TestRunExternalAnalysisForRecords:
    """Test run_external_analysis_for_records preserves behavior."""

    def setup_method(self) -> None:
        self.tmp_dir = Path("tests/tmp-external-analysis")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.directories = {
            "external_analysis": self.tmp_dir / "external-analysis",
            "notifications": self.tmp_dir / "notifications",
        }
        self.directories["external_analysis"].mkdir(parents=True, exist_ok=True)
        self.directories["notifications"].mkdir(parents=True, exist_ok=True)

        # Create mock records
        self.records = [
            _create_mock_record("cluster-a", "assessments/cluster-a.json"),
            _create_mock_record("cluster-b"),  # No assessment, uses path
        ]

        # Create mock requests using ManualExternalAnalysisRequest
        self.requests = (
            ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),
            ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-b"),
        )

        # Log events and notifications for verification
        self.logged_events: list[tuple[str, str, str, dict[str, Any]]] = []
        self.notification_paths: list[Path] = []

        def mock_log(component: str, severity: str, message: str, **metadata: Any) -> None:
            self.logged_events.append((component, severity, message, metadata))

        def mock_notification(directory: Path, artifact: Any) -> Path:
            path = directory / f"{artifact.kind}-{artifact.artifact_id or 'legacy'}.json"
            self.notification_paths.append(path)
            return path

        self.log_fn = mock_log
        self.record_notification_fn = mock_notification

    def teardown_method(self) -> None:
        import shutil

        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def test_returns_empty_when_no_adapters(self) -> None:
        """No adapters available returns empty list."""
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=self.requests,
            external_analysis_policy=policy,
            analysis_adapters={},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert result == []

    def test_returns_empty_when_no_requests(self) -> None:
        """No manual requests returns empty list."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert result == []

    def test_returns_empty_when_manual_disabled(self) -> None:
        """Manual policy disabled logs and returns empty."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=False)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=self.requests,
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert result == []
        # Verify manual-disabled log was emitted
        manual_disabled_logs = [
            e for e in self.logged_events
            if e[2] == "Manual external analysis ignored" and e[3].get("event") == "manual-disabled"
        ]
        assert len(manual_disabled_logs) == 1

    def test_adapter_unavailable_logs_warning(self) -> None:
        """Adapter not found for request logs warning."""
        # Provide a different adapter so early-return is skipped, then request
        # an adapter that doesn't exist to trigger the warning.
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="missing-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"other-adapter": adapter},  # Different adapter name
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert result == []
        adapter_unavailable_logs = [
            e for e in self.logged_events
            if "adapter unavailable" in e[2].lower()
        ]
        assert len(adapter_unavailable_logs) == 1

    def test_target_missing_logs_warning(self) -> None:
        """Request target not in records logs warning."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="missing-cluster"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert result == []
        target_missing_logs = [
            e for e in self.logged_events
            if "target missing" in e[2].lower()
        ]
        assert len(target_missing_logs) == 1

    def test_successful_analysis_writes_artifact_and_notification(self) -> None:
        """Successful adapter run writes artifact and creates notification."""
        adapter = MockAdapter(status=ExternalAnalysisStatus.SUCCESS, summary="analysis result")
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 1
        assert result[0].status == ExternalAnalysisStatus.SUCCESS
        assert result[0].cluster_label == "cluster-a"
        # Verify adapter was called with correct request
        assert len(adapter.calls) == 1
        assert adapter.calls[0].run_id == "run-1"
        assert adapter.calls[0].cluster_label == "cluster-a"
        # Verify artifact was written
        assert len(list(self.directories["external_analysis"].glob("*.json"))) == 1
        # Verify notification was created
        assert len(self.notification_paths) == 1

    def test_artifact_path_format_preserved(self) -> None:
        """Artifact path follows expected format: {run_id}-{cluster_label}-{adapter_name}.json"""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        run_id = "test-run-123"
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id=run_id,
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 1
        expected_path = f"{run_id}-cluster-a-mock-adapter.json"
        written_files = list(self.directories["external_analysis"].glob("*.json"))
        assert len(written_files) == 1
        assert written_files[0].name == expected_path

    def test_uses_assessment_artifact_path_when_available(self) -> None:
        """Source artifact uses assessment path when available, not record.path."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(adapter.calls) == 1
        # cluster-a has an assessment with artifact_path
        assert adapter.calls[0].source_artifact == "assessments/cluster-a.json"

    def test_uses_record_path_when_no_assessment(self) -> None:
        """Source artifact uses record.path when no assessment is available."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-b"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(adapter.calls) == 1
        # cluster-b has no assessment, so uses record.path
        assert adapter.calls[0].source_artifact == str(self.records[1].path)

    def test_failed_analysis_status_logged_as_error(self) -> None:
        """Failed analysis logs with ERROR severity."""
        adapter = MockAdapter(status=ExternalAnalysisStatus.FAILED, summary="failed analysis")
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 1
        assert result[0].status == ExternalAnalysisStatus.FAILED
        # Verify ERROR log was emitted
        error_logs = [e for e in self.logged_events if e[1] == "ERROR"]
        assert len(error_logs) == 1

    def test_skipped_analysis_status_logged_as_warning(self) -> None:
        """Skipped analysis logs with WARNING severity."""
        adapter = MockAdapter(status=ExternalAnalysisStatus.SKIPPED, summary="skipped analysis")
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=(ManualExternalAnalysisRequest(tool="mock-adapter", target="cluster-a"),),
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 1
        assert result[0].status == ExternalAnalysisStatus.SKIPPED
        # Verify WARNING log was emitted
        warning_logs = [e for e in self.logged_events if e[1] == "WARNING"]
        assert len(warning_logs) == 1

    def test_multiple_requests_processed_in_order(self) -> None:
        """All requests are processed in order."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=self.requests,  # cluster-a then cluster-b
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 2
        assert result[0].cluster_label == "cluster-a"
        assert result[1].cluster_label == "cluster-b"
        # Verify adapter was called for both
        assert len(adapter.calls) == 2
        assert adapter.calls[0].cluster_label == "cluster-a"
        assert adapter.calls[1].cluster_label == "cluster-b"

    def test_notification_created_for_each_artifact(self) -> None:
        """Each analysis artifact creates a notification."""
        adapter = MockAdapter()
        policy = ExternalAnalysisPolicy(manual=True)
        result = run_external_analysis_for_records(
            records=self.records,
            manual_requests=self.requests,
            external_analysis_policy=policy,
            analysis_adapters={"mock-adapter": adapter},
            run_id="run-1",
            run_label="test",
            record_notification_fn=self.record_notification_fn,
            log_event_fn=self.log_fn,
            directories=self.directories,
        )
        assert len(result) == 2
        assert len(self.notification_paths) == 2
