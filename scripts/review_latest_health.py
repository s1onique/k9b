#!/usr/bin/env python3
"""Daily operator review flow that surfaces the most actionable health drilldown."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

DEFAULT_HEALTH_DIR = Path("runs/health")
DEFAULT_HEALTH_CONFIG = Path("runs/health-config.local.json")
HEALTH_CONFIG_FALLBACK = Path("runs/health-config.local.example.json")


def _root_path() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_src_path_in_sys_path() -> None:
    root = _root_path()
    src_path = root / "src"
    src_str = str(src_path)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


if TYPE_CHECKING:
    _ensure_src_path_in_sys_path()
    from k8s_diag_agent.health.review import LatestRunSelection
    from k8s_diag_agent.llm.assessor_schema import AssessorAssessment


def _missing_assess_drilldown_artifact(*args: object, **kwargs: object) -> None:
    raise RuntimeError("LLM assessor helper not loaded; import failed or path not configured.")


assess_drilldown_artifact: Callable[..., AssessorAssessment]
assess_drilldown_artifact = _missing_assess_drilldown_artifact


def _ensure_assess_drilldown_artifact() -> Callable[..., AssessorAssessment]:
    global assess_drilldown_artifact
    if assess_drilldown_artifact is _missing_assess_drilldown_artifact:
        from k8s_diag_agent.health.drilldown_assessor import assess_drilldown_artifact as real_assess

        assess_drilldown_artifact = real_assess
    return assess_drilldown_artifact


def _missing_review_helper(*args: object, **kwargs: object) -> object:
    raise RuntimeError("Review helpers not loaded; import failure or missing path.")


assessment_path_for_drilldown: Callable[..., Path] = _missing_review_helper  # type: ignore[assignment]
load_assessment: Callable[..., AssessorAssessment | None] = _missing_review_helper  # type: ignore[assignment]
select_latest_run: Callable[..., LatestRunSelection] = _missing_review_helper  # type: ignore[assignment]


def _ensure_review_helpers() -> None:
    global assessment_path_for_drilldown, load_assessment, select_latest_run
    if assessment_path_for_drilldown is _missing_review_helper:
        review_module = importlib.import_module("k8s_diag_agent.health.review")
        assessment_path_for_drilldown = review_module.assessment_path_for_drilldown
        load_assessment = review_module.load_assessment
        select_latest_run = review_module.select_latest_run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the operator review workflow.")
    parser.add_argument(
        "--health-dir",
        type=Path,
        default=DEFAULT_HEALTH_DIR,
        help="Base directory where health run artifacts live (default: runs/health).",
    )
    parser.add_argument(
        "--health-config",
        type=Path,
        default=DEFAULT_HEALTH_CONFIG,
        help="Health config file used when --run-health is supplied.",
    )
    parser.add_argument(
        "--run-health",
        action="store_true",
        help="Run run-health-loop --once before reviewing the latest artifacts.",
    )
    return parser


def _python_executable() -> Path:
    python_binary = _root_path() / ".venv" / "bin" / "python"
    if not python_binary.exists():
        raise RuntimeError(
            f"Python executable {python_binary} not found; activate or create .venv before running."
        )
    return python_binary


def _resolve_health_config(path: Path) -> Path:
    if path.exists():
        return path
    if path == DEFAULT_HEALTH_CONFIG and HEALTH_CONFIG_FALLBACK.exists():
        raise RuntimeError(
            f"Local config {path} is missing; copy {HEALTH_CONFIG_FALLBACK} → {path} before running."
        )
    raise RuntimeError(f"Health config {path} not found; pass a valid --health-config.")


def _run_health_loop_once(
    config_path: Path, python_bin: Path | None = None, env: Mapping[str, str] | None = None
) -> int:
    python = python_bin or _python_executable()
    executable_env = dict(env) if env is not None else os.environ
    result = subprocess.run(
        [
            str(python),
            "-m",
            "k8s_diag_agent.cli",
            "run-health-loop",
            "--config",
            str(config_path),
            "--once",
        ],
        env=executable_env,
    )
    return result.returncode


def _has_llama_config(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(source.get("LLAMA_CPP_BASE_URL") and source.get("LLAMA_CPP_MODEL"))


def _print_summary(
    selection: LatestRunSelection,
    assessment: AssessorAssessment | None,
    assessment_path: Path,
) -> None:
    artifact = selection.candidates[0].artifact
    print(f"Latest run: {selection.run_id} @ {selection.run_timestamp.isoformat()}")
    print(f"Selected cluster: {artifact.cluster_id}")
    reasons = ", ".join(artifact.trigger_reasons) or "none"
    print(f"Trigger reasons: {reasons}")

    if assessment and assessment.findings:
        print("Top findings:")
        for index, finding in enumerate(assessment.findings[:3], start=1):
            layer = finding.layer or "unspecified"
            print(f"  {index}. {finding.description} (layer: {layer})")
    else:
        print("Top findings: none")

    if assessment and assessment.hypotheses:
        hypothesis = assessment.hypotheses[0]
        print(
            f"Top hypothesis: {hypothesis.description} (confidence: {hypothesis.confidence.value}, layer: {hypothesis.probable_layer})"
        )
    else:
        print("Top hypothesis: unavailable")

    if assessment and assessment.next_evidence_to_collect:
        print("Next low-risk checks:")
        for check in assessment.next_evidence_to_collect[:3]:
            evidence = ", ".join(check.evidence_needed) or "none"
            print(
                f"  - {check.description} (method: {check.method}, owner: {check.owner}, evidence: {evidence})"
            )
    else:
        print("Next low-risk checks: none")

    print(f"Drilldown artifact: {selection.candidates[0].path}")
    print(f"Assessment artifact: {assessment_path}")


def run_operator_review(
    health_dir: Path,
    run_health: bool,
    health_config: Path,
    python_bin: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    env_source = os.environ if env is None else env
    _ensure_src_path_in_sys_path()
    _ensure_review_helpers()
    if run_health:
        try:
            config_path = _resolve_health_config(health_config)
        except RuntimeError as exc:
            print(f"Unable to resolve health config: {exc}", file=sys.stderr)
            return 1
        exit_code = _run_health_loop_once(config_path, python_bin=python_bin, env=env_source)
        if exit_code != 0:
            return exit_code

    drilldown_dir = health_dir / "drilldowns"
    try:
        latest = select_latest_run(drilldown_dir)
    except RuntimeError as exc:
        print(f"No drilldowns found: {exc}", file=sys.stderr)
        return 1

    candidate = latest.candidates[0]
    assessments_dir = health_dir / "assessments"
    assessment_path = assessment_path_for_drilldown(candidate.path, assessments_dir)
    assessment = load_assessment(assessment_path)

    if _has_llama_config(env_source):
        print("LLAMA_CPP config detected; running LLM drilldown assessment.")
        try:
            assessor = _ensure_assess_drilldown_artifact()
            assessment = assessor(candidate.artifact, provider_name="llamacpp")
        except Exception as exc:
            print(f"LLM assessment failed: {exc}", file=sys.stderr)
        else:
            assessments_dir.mkdir(parents=True, exist_ok=True)
            assessment_path.write_text(
                json.dumps(assessment.to_dict(), indent=2), encoding="utf-8"
            )
            print(f"Updated assessment artifact: {assessment_path}")
    else:
        print("LLAMA_CPP env vars not set; skipping automated assessment.")

    _print_summary(latest, assessment, assessment_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_operator_review(
        health_dir=args.health_dir,
        run_health=args.run_health,
        health_config=args.health_config,
        env=os.environ,
    )


if __name__ == "__main__":
    raise SystemExit(main())
