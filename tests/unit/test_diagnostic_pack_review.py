import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from scripts.diagnostic_pack_review import (
    create_diagnostic_pack_review,
    extract_diagnostic_pack,
    load_manifest,
    load_summary,
)
from tests.fixtures.ui_index_sample import sample_ui_index


def _payload(result: Any) -> dict[str, object]:
    return cast(dict[str, object], result.artifact.payload or {})


def _build_sample_pack(tmp_path: Path, index_modifier: Callable[[dict[str, object]], None] | None = None) -> Path:
    runs_dir = tmp_path / "runs" / "health"
    runs_dir.mkdir(parents=True)
    manifest = {"run_id": "run-1", "run_label": "health-run"}
    (runs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (runs_dir / "summary.md").write_text("Sample summary", encoding="utf-8")
    index = sample_ui_index()
    if index_modifier:
        index_modifier(index)
    (runs_dir / "ui-index.json").write_text(json.dumps(index), encoding="utf-8")
    pack_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(pack_path, "w") as archive:
        for path in runs_dir.rglob("*"):
            archive.write(path, path.relative_to(tmp_path))
    return pack_path


def test_extract_and_load_pack(tmp_path: Path) -> None:
    pack = _build_sample_pack(tmp_path)
    dest = tmp_path / "work"
    extracted = extract_diagnostic_pack(pack, dest)
    assert (extracted / "manifest.json").exists()
    assert (extracted / "summary.md").exists()
    manifest = load_manifest(extracted)
    assert manifest["run_id"] == "run-1"
    summary = load_summary(extracted)
    assert summary == "Sample summary"


def test_create_diagnostic_pack_review(tmp_path: Path) -> None:
    pack = _build_sample_pack(tmp_path)
    result = create_diagnostic_pack_review(pack, temporarily_extract_to=tmp_path / "work")
    assert result.artifact.purpose.value == "diagnostic-pack-review"
    payload = _payload(result)
    assert payload["confidence"] == "medium"
    assert (tmp_path / "work" / "runs" / "health" / "external-analysis").exists()


def test_review_payload_captures_expected_defaults(tmp_path: Path) -> None:
    pack = _build_sample_pack(tmp_path)
    result = create_diagnostic_pack_review(pack, temporarily_extract_to=tmp_path / "work")
    payload = _payload(result)
    assert payload["summary"] == "Sample summary"
    assert isinstance(payload["generic_checks"], list)
    assert payload["generic_checks"]
    assert payload["ranking_issues"]
    assert payload["recommended_next_actions"] == ["Collect kubelet logs for control-plane pods"]
    assert isinstance(payload["missing_checks"], list)
    assert payload["drift_misprioritized"] is False
    assert payload["major_disagreements"] == []


def test_review_payload_handles_missing_optional_sections(tmp_path: Path) -> None:
    def _strip_optional(index: dict[str, object]) -> None:
        run = index.get("run") or {}
        run.pop("next_check_plan", None)
        index.pop("next_check_plan", None)
        run.pop("next_check_queue_explanation", None)
        index.pop("next_check_queue_explanation", None)
        run.pop("deterministic_next_checks", None)
        index.pop("deterministic_next_checks", None)

    pack = _build_sample_pack(tmp_path, index_modifier=_strip_optional)
    result = create_diagnostic_pack_review(pack, temporarily_extract_to=tmp_path / "work")
    payload = _payload(result)
    assert payload["generic_checks"] == []
    assert payload["ranking_issues"] == []
    assert payload["recommended_next_actions"] == []
    assert payload["missing_checks"] == []
    assert payload["major_disagreements"] == []
    assert payload["drift_misprioritized"] is False