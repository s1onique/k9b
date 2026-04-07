import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.adapter import (
    ExternalAnalysisRequest,
    build_external_analysis_adapters,
)
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisSettings,
    parse_external_analysis_settings,
)
from k8s_diag_agent.external_analysis.k8sgpt_adapter import K8sGptAdapter


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
