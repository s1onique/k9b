#!/usr/bin/env python3
"""ACT-local smoke test for small-provider runtime invocation."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


from k8s_diag_agent.external_analysis import (
    build_external_analysis_adapters,
    parse_external_analysis_settings,
)
from k8s_diag_agent.external_analysis.config import ExternalAnalysisAdapterConfig
from k8s_diag_agent.external_analysis.fake_small_provider import (
    get_fake_provider_state,
    reset_fake_provider_state,
)
from k8s_diag_agent.health.loop_runner_review_enrichment import run_review_enrichment


def _null_logger(*args: object, **kwargs: object) -> None:
    pass


def run_smoke_test(output_dir: Path | None = None) -> dict[str, object]:
    reset_fake_provider_state()
    
    test_env = {
        "K9B_EXTERNAL_ANALYSIS_BASE_URL": "https://fake-llm.example.com/v1",
        "K9B_EXTERNAL_ANALYSIS_MODEL": "test-model",
        "K9B_EXTERNAL_ANALYSIS_API_KEY": "sk-test-fake-key-1234567890abcdef",
    }
    
    old_environ = dict(os.environ)
    os.environ.update(test_env)
    
    try:
        settings = parse_external_analysis_settings({
            "review_enrichment": {"enabled": True, "provider": "fake_small_provider"}
        })
        
        # Build fake adapter through the registry seam like production does
        adapter_config = ExternalAnalysisAdapterConfig(
            name="fake_small_provider",
            enabled=True,
            command=None,
        )
        
        # Build through the production factory (takes Sequence[ExternalAnalysisAdapterConfig])
        adapters = build_external_analysis_adapters([adapter_config], settings)
        
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            review_path = tmp_path / "review.json"
            review_data = {
                "run_id": "test-run-001",
                "clusters": ["cluster-a", "cluster-b"],
                "assessments": [{"cluster": "cluster-a", "summary": "Test assessment"}],
                "drilldowns": [],
                "proposals": [],
            }
            review_path.write_text(json.dumps(review_data))
            
            artifact = run_review_enrichment(
                review_path=review_path,
                directories={"external_analysis": tmp_path},
                review_enrichment_policy=settings.review_enrichment,
                analysis_adapters=adapters,
                run_id="test-run-001",
                run_label="test-cluster",
                log_event_fn=_null_logger,
            )
    finally:
        os.environ.clear()
        os.environ.update(old_environ)
    
    state = get_fake_provider_state()
    
    failures = []
    if not state.configured:
        failures.append("small_provider_configured=False")
    if not state.base_url_present:
        failures.append("base_url_present=False")
    if not state.model_present:
        failures.append("model_present=False")
    if not state.api_key_present:
        failures.append("api_key_present=False")
    if len(state.invocations) == 0:
        failures.append("small_provider_invocation_attempted=False")
    if state.kubernetes_fallback_attempted:
        failures.append("kubernetes_fallback_attempted=True")
    
    proof = {
        "test_name": "small_provider_runtime_invocation",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "small_provider_configured": state.configured,
        "small_provider_invocation_attempted": len(state.invocations) > 0,
        "no_kubernetes_fallback": not state.kubernetes_fallback_attempted,
        "invocation_count": len(state.invocations),
        "base_url_present": state.base_url_present,
        "model_present": state.model_present,
        "api_key_present": state.api_key_present,
        "artifact_status": artifact.status.value if artifact else None,
        "artifact_summary": artifact.summary if artifact else None,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "status.json", "w") as f:
            json.dump(proof, f, indent=2)
        if artifact and artifact.raw_output:
            with open(output_dir / "provider-output.json", "w") as f:
                f.write(artifact.raw_output)
    
    return proof


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args()
    
    output_dir = args.output or (REPO_ROOT / "provider-smoke" / "small-provider")
    proof = run_smoke_test(output_dir)
    
    print(f"Status: {proof['status']}")
    print(f"small_provider_configured: {proof['small_provider_configured']}")
    print(f"small_provider_invocation_attempted: {proof['small_provider_invocation_attempted']}")
    print(f"no_kubernetes_fallback: {proof['no_kubernetes_fallback']}")
    
    if proof["failures"]:
        print("FAILURES:", proof["failures"])
    
    return 0 if proof["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
