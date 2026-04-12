import json
import subprocess
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis import llamacpp_adapter as llamacpp_module
from k8s_diag_agent.external_analysis.adapter import (
    ExternalAnalysisRequest,
    build_external_analysis_adapters,
)
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    UsefulnessClass,
    write_external_analysis_artifact,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisSettings,
    parse_external_analysis_settings,
)
from k8s_diag_agent.external_analysis.k8sgpt_adapter import K8sGptAdapter
from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter
from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
from k8s_diag_agent.external_analysis.review_schema import (
    ReviewEnrichmentPayload,
    ReviewEnrichmentPayloadError,
)
from k8s_diag_agent.llm.llamacpp_provider import LlamaCppProvider


def test_artifact_roundtrip_and_file_io(tmp_path: Path) -> None:
    artifact = ExternalAnalysisArtifact(
        tool_name="testtool",
        run_id="run-123",
        cluster_label="cluster-x",
        source_artifact="source.json",
        summary="summary text",
        findings=("f1", "f2"),
        suggested_next_checks=("c1",),
        status=ExternalAnalysisStatus.SUCCESS,
        raw_output="raw output",
    )
    data = artifact.to_dict()
    loaded = ExternalAnalysisArtifact.from_dict(data)
    assert loaded == artifact

    path = tmp_path / "sub" / "ext.json"
    written = write_external_analysis_artifact(path, artifact)
    assert written == path
    read = json.loads(path.read_text(encoding="utf-8"))
    reloaded = ExternalAnalysisArtifact.from_dict(read)
    assert reloaded == artifact


def test_parse_settings_defaults_and_full() -> None:
    defaults = parse_external_analysis_settings(None)
    assert isinstance(defaults, ExternalAnalysisSettings)
    assert defaults.policy.manual is True
    assert defaults.adapters == ()

    raw = {
        "policy": {"manual": False, "degraded_health": True, "suspicious_comparison": True},
        "adapters": [
            {"name": "k8sgpt", "enabled": True, "command": ["foo", "bar"]}
        ],
    }
    settings = parse_external_analysis_settings(raw)
    assert settings.policy.manual is False
    assert settings.policy.degraded_health is True
    assert settings.policy.suspicious_comparison is True
    assert len(settings.adapters) == 1
    cfg = settings.adapters[0]
    assert cfg.name == "k8sgpt"
    assert cfg.enabled is True
    assert cfg.command == ("foo", "bar")


def test_build_adapters_and_skip(monkeypatch: Any) -> None:
    # disabled adapter yields no adapters
    cfgs = [ExternalAnalysisAdapterConfig(name="k8sgpt", enabled=False, command=None)]
    adapters = build_external_analysis_adapters(cfgs)
    assert adapters == {}

    # empty command yields adapter but skip status
    cfgs = [ExternalAnalysisAdapterConfig(name="k8sgpt", enabled=True, command=())]
    adapters = build_external_analysis_adapters(cfgs)
    assert "k8sgpt" in adapters
    adapter = adapters["k8sgpt"]
    req = ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=None)
    artifact = adapter.run(req)
    assert artifact.status == ExternalAnalysisStatus.SKIPPED

    cfgs = [ExternalAnalysisAdapterConfig(name="llamacpp", enabled=True, command=())]
    adapters = build_external_analysis_adapters(cfgs)
    assert "llamacpp" in adapters
    llama_adapter = adapters["llamacpp"]
    artifact = llama_adapter.run(req)
    assert artifact.status == ExternalAnalysisStatus.SKIPPED


def test_k8sgpt_adapter_success(monkeypatch: Any) -> None:
    adapter = K8sGptAdapter(command=("echo", "line1\nline2"))
    class FakeResult:
        def __init__(self) -> None:
            self.stdout = "line1\nline2"
            self.stderr = ""
            self.returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    req = ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact="sa.json")
    art = adapter.run(req)
    assert art.status == ExternalAnalysisStatus.SUCCESS
    assert art.summary == "line1"
    assert art.provider == "k8sgpt"
    assert isinstance(art.duration_ms, int)


def _fake_assessment_payload() -> dict[str, Any]:
    return {
        "observed_signals": [],
        "findings": [
            {
                "description": "finding-1",
                "supporting_signals": [],
                "layer": "workflow",
            }
        ],
        "hypotheses": [],
        "next_evidence_to_collect": [
            {
                "description": "check one",
                "owner": "platform-engineer",
                "method": "kubectl",
                "evidence_needed": ["kubectl get pods"],
            }
        ],
        "recommended_action": {
            "type": "observation",
            "description": "Take action now",
            "references": [],
            "safety_level": "low-risk",
        },
        "safety_level": "low-risk",
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_review_enrichment_payload_validation() -> None:
    payload = {
        "summary": "Focus on latency",
        "triageOrder": ["cluster-z", "cluster-a"],
        "topConcerns": ["ingress", "storage"],
        "evidenceGaps": ["CDN metrics"],
        "nextChecks": ["inspect ingress logs"],
        "focusNotes": ["prioritize cluster-z"],
    }
    parsed = ReviewEnrichmentPayload.from_dict(payload)
    assert parsed.summary == "Focus on latency"
    assert parsed.triage_order == ("cluster-z", "cluster-a")
    assert parsed.top_concerns == ("ingress", "storage")
    assert parsed.focus_notes == ("prioritize cluster-z",)


def test_review_enrichment_payload_invalid_entry() -> None:
    invalid_payload = {"triageOrder": [""]}
    failed = False
    try:
        ReviewEnrichmentPayload.from_dict(invalid_payload)
    except ReviewEnrichmentPayloadError:
        failed = True
    assert failed

def _configure_http_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://example")
    monkeypatch.setenv("LLAMA_CPP_MODEL", "test-model")


def test_llamacpp_adapter_http_success(monkeypatch: Any, tmp_path: Path) -> None:
    _configure_http_env(monkeypatch)
    # Use bounded review-enrichment payload (not assessment-shaped)
    fake_review_enrichment = {
        "summary": "Review insight",
        "triageOrder": ["cluster-a"],
        "topConcerns": ["latency", "storage"],
        "evidenceGaps": ["pod metrics"],
        "nextChecks": ["check ingress", "check storage"],
        "focusNotes": ["prioritize cluster-a"],
    }

    def fake_assess(
        self: LlamaCppProvider,
        prompt: str,
        payload: Any,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
    ) -> dict[str, Any]:
        # Verify system instructions include review enrichment guidance
        assert system_instructions is not None
        assert "summary" in system_instructions.lower() or "triageorder" in system_instructions.lower()
        # Verify validate_schema is False for review enrichment
        assert validate_schema is False
        return fake_review_enrichment
    monkeypatch.setattr(LlamaCppProvider, "assess", fake_assess)
    adapter = LlamaCppAdapter()
    review_path = tmp_path / "runs" / "health" / "reviews" / "r-review.json"
    _write_json(review_path, {"run_id": "r", "selected_drilldowns": []})
    req = ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=str(review_path))
    artifact = adapter.run(req)
    assert artifact.status == ExternalAnalysisStatus.SUCCESS
    assert artifact.summary == "Review insight"
    # Verify bounded fields are extracted correctly
    assert artifact.findings == ("latency", "storage")
    assert artifact.suggested_next_checks == ("check ingress", "check storage")
    assert artifact.payload == fake_review_enrichment
    assert artifact.provider == "llamacpp"


def test_llamacpp_adapter_http_failure(monkeypatch: Any, tmp_path: Path) -> None:
    _configure_http_env(monkeypatch)
    def fake_assess(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")
    monkeypatch.setattr(LlamaCppProvider, "assess", fake_assess)
    adapter = LlamaCppAdapter()
    review_path = tmp_path / "runs" / "health" / "reviews" / "r-review.json"
    _write_json(review_path, {"run_id": "r", "selected_drilldowns": []})
    artifact = adapter.run(
        ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=str(review_path))
    )
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.error_summary == "boom"


def test_llamacpp_adapter_http_invalid_response(monkeypatch: Any, tmp_path: Path) -> None:
    _configure_http_env(monkeypatch)

    def fake_assess(
        self: LlamaCppProvider,
        prompt: str,
        payload: Any,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
    ) -> dict[str, Any]:
        raise ValueError("schema")
    monkeypatch.setattr(LlamaCppProvider, "assess", fake_assess)
    adapter = LlamaCppAdapter()
    review_path = tmp_path / "runs" / "health" / "reviews" / "r-review.json"
    _write_json(review_path, {"run_id": "r", "selected_drilldowns": []})
    artifact = adapter.run(
        ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=str(review_path))
    )
    assert artifact.status == ExternalAnalysisStatus.SKIPPED
    assert artifact.skip_reason == "schema"


def test_llamacpp_adapter_http_review_payload(monkeypatch: Any, tmp_path: Path) -> None:
    _configure_http_env(monkeypatch)
    fake_payload = {
        "summary": "Review insight",
        "triageOrder": ["cluster-a"],
        "topConcerns": ["latency"],
        "evidenceGaps": ["pod metrics"],
        "nextChecks": ["check ingress"],
        "focusNotes": ["prioritize cluster-a"],
    }

    def fake_assess(
        self: LlamaCppProvider,
        prompt: str,
        payload: Any,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
    ) -> dict[str, Any]:
        assert validate_schema is False
        return fake_payload

    monkeypatch.setattr(LlamaCppProvider, "assess", fake_assess)
    adapter = LlamaCppAdapter()
    review_path = tmp_path / "runs" / "health" / "reviews" / "r-review.json"
    _write_json(review_path, {"run_id": "r", "selected_drilldowns": []})
    artifact = adapter.run(
        ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=str(review_path))
    )
    assert artifact.status == ExternalAnalysisStatus.SUCCESS
    assert artifact.provider == "llamacpp"
    assert artifact.summary == "Review insight"
    assert artifact.findings == ("latency",)
    assert artifact.suggested_next_checks == ("check ingress",)


def test_llamacpp_adapter_http_review_payload_invalid(monkeypatch: Any, tmp_path: Path) -> None:
    _configure_http_env(monkeypatch)

    def fake_assess(
        self: LlamaCppProvider,
        prompt: str,
        payload: Any,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
    ) -> dict[str, Any]:
        return {"triageOrder": [""], "topConcerns": ["latency"], "nextChecks": ["check ingress"], "focusNotes": []}

    monkeypatch.setattr(LlamaCppProvider, "assess", fake_assess)
    adapter = LlamaCppAdapter()
    review_path = tmp_path / "runs" / "health" / "reviews" / "r-review.json"
    _write_json(review_path, {"run_id": "r", "selected_drilldowns": []})
    artifact = adapter.run(
        ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=str(review_path))
    )
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.error_summary is not None
    assert "triageOrder" in artifact.error_summary


def test_llamacpp_adapter_command_precedence(monkeypatch: Any) -> None:
    _configure_http_env(monkeypatch)
    adapter = LlamaCppAdapter(command=("echo", "analysis"))
    captured: list[Sequence[str]] = []
    def fake_run(command: Sequence[str]) -> str:
        captured.append(command)
        return "ok"
    monkeypatch.setattr(llamacpp_module, "_run_subprocess", fake_run)
    artifact = adapter.run(ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=None))
    assert artifact.status == ExternalAnalysisStatus.SUCCESS
    assert captured


def test_llamacpp_adapter_missing_config_skip(monkeypatch: Any) -> None:
    monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
    monkeypatch.delenv("LLAMA_CPP_MODEL", raising=False)
    adapter = LlamaCppAdapter(command=())
    artifact = adapter.run(ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=None))
    assert artifact.status == ExternalAnalysisStatus.SKIPPED


def test_review_enrichment_input_review_only(tmp_path: Path) -> None:
    run_id = "run-review-only"
    review_path = tmp_path / "runs" / "health" / "reviews" / f"{run_id}-review.json"
    review = {
        "run_id": run_id,
        "selected_drilldowns": [
            {"label": "cluster-a", "context": "cluster-a"},
            {"label": "cluster-b", "context": "cluster-b"},
        ],
    }
    _write_json(review_path, review)
    context = build_review_enrichment_input(review_path, run_id)
    assert context.review["run_id"] == run_id
    assert len(context.selections) == 2
    assert context.missing_drilldowns == ("cluster-a", "cluster-b")
    assert context.missing_assessments == ("cluster-a", "cluster-b")
    assert context.missing_snapshots == ()
    assert all(selection.drilldown is None for selection in context.selections)


def test_review_enrichment_input_with_optional_contexts(tmp_path: Path) -> None:
    run_id = "run-review-context"
    root = tmp_path / "runs" / "health"
    review_path = root / "reviews" / f"{run_id}-review.json"
    review = {
        "run_id": run_id,
        "selected_drilldowns": [
            {"label": "cluster-a", "context": "cluster-a"},
            {"label": "cluster-b", "context": "cluster-b"},
        ],
    }
    _write_json(review_path, review)
    drilldown_path = root / "drilldowns" / f"{run_id}-cluster-a-drilldown.json"
    drilldown_data = {"context": "cluster-a", "trigger_reasons": ["foo"]}
    _write_json(drilldown_path, drilldown_data)
    snapshot_path = root / "snapshots" / f"{run_id}-cluster-a-1.json"
    snapshot_data = {"metadata": {"cluster_id": "cluster-a"}}
    _write_json(snapshot_path, snapshot_data)
    assessment_path = root / "assessments" / f"{run_id}-cluster-a-assessment.json"
    assessment_data = {"snapshot_path": str(snapshot_path)}
    _write_json(assessment_path, assessment_data)
    context = build_review_enrichment_input(review_path, run_id)
    selection = context.selections[0]
    assert selection.label == "cluster-a"
    assert selection.drilldown == drilldown_data
    assert selection.assessment == assessment_data
    assert selection.snapshot == snapshot_data
    assert context.missing_drilldowns == ("cluster-b",)
    assert context.missing_assessments == ("cluster-b",)
    assert context.missing_snapshots == ()


def test_review_enrichment_input_missing_snapshot(tmp_path: Path) -> None:
    run_id = "run-review-missing-snapshot"
    root = tmp_path / "runs" / "health"
    review_path = root / "reviews" / f"{run_id}-review.json"
    review = {
        "run_id": run_id,
        "selected_drilldowns": [{"label": "cluster-a", "context": "cluster-a"}],
    }
    _write_json(review_path, review)
    drilldown_path = root / "drilldowns" / f"{run_id}-cluster-a-drilldown.json"
    _write_json(drilldown_path, {"context": "cluster-a"})
    assessment_path = root / "assessments" / f"{run_id}-cluster-a-assessment.json"
    missing_snapshot_path = root / "snapshots" / f"{run_id}-cluster-a-missing.json"
    assessment_data = {"snapshot_path": str(missing_snapshot_path)}
    _write_json(assessment_path, assessment_data)
    context = build_review_enrichment_input(review_path, run_id)
    assert context.missing_snapshots == ("cluster-a",)
    assert context.selections[0].snapshot is None
def test_k8sgpt_adapter_failure(monkeypatch: Any) -> None:
    def fake_run(cmd: Any, capture_output: Any, text: Any, check: Any) -> None:
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd, stderr="errord")

    adapter = K8sGptAdapter(command=("badcmd",))
    monkeypatch.setattr(subprocess, "run", fake_run)
    req = ExternalAnalysisRequest(run_id="r", cluster_label="c", source_artifact=None)
    art = adapter.run(req)
    assert art.status == ExternalAnalysisStatus.FAILED
    raw_output = art.raw_output or ""
    assert "exited 2" in raw_output or "Command not found" in raw_output
    assert art.provider == "k8sgpt"
    assert isinstance(art.duration_ms, int)


def test_external_analysis_adapter_persists_artifact(tmp_path: Path, monkeypatch: Any) -> None:
    class FakeResult:
        def __init__(self) -> None:
            self.stdout = "insight line"
            self.stderr = ""
            self.returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    adapter = K8sGptAdapter(command=("echo", "analysis"))
    req = ExternalAnalysisRequest(run_id="run-1", cluster_label="cluster-a", source_artifact="assessments/cluster-a.json")
    artifact = adapter.run(req)
    output_path = tmp_path / "analysis.json"
    artifact_with_path = replace(artifact, artifact_path=str(output_path))
    written = write_external_analysis_artifact(output_path, artifact_with_path)
    assert written == output_path
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["tool_name"] == "k8sgpt"
    assert persisted["artifact_path"] == str(output_path)


# --- UsefulnessClass contract tests ---

def test_usefulness_class_enum_values() -> None:
    """Verify only the 4 approved usefulness classes exist."""
    expected = {"useful", "partial", "noisy", "empty"}
    actual = {cls.value for cls in UsefulnessClass}
    assert actual == expected, f"UsefulnessClass has unexpected values: {actual - expected} or missing: {expected - actual}"


def test_usefulness_class_roundtrip_useful() -> None:
    """Test roundtrip for useful."""
    artifact = ExternalAnalysisArtifact(
        tool_name="test",
        run_id="r",
        cluster_label="c",
        usefulness_class=UsefulnessClass.USEFUL,
        usefulness_summary="Found relevant output",
    )
    data = artifact.to_dict()
    loaded = ExternalAnalysisArtifact.from_dict(data)
    assert loaded.usefulness_class == UsefulnessClass.USEFUL
    assert loaded.usefulness_summary == "Found relevant output"


def test_usefulness_class_roundtrip_partial() -> None:
    """Test roundtrip for partial."""
    artifact = ExternalAnalysisArtifact(
        tool_name="test",
        run_id="r",
        cluster_label="c",
        usefulness_class=UsefulnessClass.PARTIAL,
        usefulness_summary="Output was truncated",
    )
    data = artifact.to_dict()
    loaded = ExternalAnalysisArtifact.from_dict(data)
    assert loaded.usefulness_class == UsefulnessClass.PARTIAL


def test_usefulness_class_roundtrip_noisy() -> None:
    """Test roundtrip for noisy."""
    artifact = ExternalAnalysisArtifact(
        tool_name="test",
        run_id="r",
        cluster_label="c",
        usefulness_class=UsefulnessClass.NOISY,
        usefulness_summary="Found warnings in output",
    )
    data = artifact.to_dict()
    loaded = ExternalAnalysisArtifact.from_dict(data)
    assert loaded.usefulness_class == UsefulnessClass.NOISY


def test_usefulness_class_roundtrip_empty() -> None:
    """Test roundtrip for empty."""
    artifact = ExternalAnalysisArtifact(
        tool_name="test",
        run_id="r",
        cluster_label="c",
        usefulness_class=UsefulnessClass.EMPTY,
    )
    data = artifact.to_dict()
    loaded = ExternalAnalysisArtifact.from_dict(data)
    assert loaded.usefulness_class == UsefulnessClass.EMPTY


def test_usefulness_class_unknown_value_becomes_none() -> None:
    """Test that unknown usefulness values (e.g., from old artifacts) become None."""
    # Simulate an old artifact with "redundant" which is no longer valid
    old_artifact_data = {
        "tool_name": "test",
        "run_id": "r",
        "cluster_label": "c",
        "usefulness_class": "redundant",
    }
    loaded = ExternalAnalysisArtifact.from_dict(old_artifact_data)
    # Unknown value should be treated as unset (None)
    assert loaded.usefulness_class is None


def test_usefulness_class_not_in_enum_raises() -> None:
    """Verify that constructing UsefulnessClass with invalid value raises ValueError."""
    import pytest
    with pytest.raises(ValueError):
        UsefulnessClass("redundant")
    with pytest.raises(ValueError):
        UsefulnessClass("unknown")
