"""Pod failure symptom verifier entry point."""
from pathlib import Path

from verify_pod_failure_impl import verify_pod_failure_symptom


def main() -> int:
    """CLI entry point."""
    import argparse

    from verify_pod_failure_impl import SymptomClass

    parser = argparse.ArgumentParser(description="Verify pod failure symptom")
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--pod-name", required=True)
    parser.add_argument("--deadline", type=int, required=True)
    parser.add_argument("--poll-interval", type=int, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)

    args = parser.parse_args()

    result = verify_pod_failure_symptom(
        kubeconfig=args.kubeconfig,
        namespace=args.namespace,
        pod_name=args.pod_name,
        deadline=args.deadline,
        poll_interval=args.poll_interval,
        artifact_dir=args.artifact_dir,
    )

    # Write result JSON
    result_path = args.artifact_dir / "pod-failure-symptom-result.json"
    import json
    result_dict = {
        "symptom_class": result.symptom_class.value if hasattr(result.symptom_class, "value") else str(result.symptom_class),
        "fatal": result.fatal,
        "pod_phase": result.pod_phase,
        "pod_ready": result.pod_ready,
        "container_state": result.container_state,
        "container_waiting_reason": result.container_waiting_reason,
        "latest_event": result.latest_event,
        "readiness_probe_failure_evidence": result.readiness_probe_failure_evidence,
        "failure_reason": result.failure_reason,
        "elapsed_seconds": result.elapsed_seconds,
        "poll_count": result.poll_count,
    }
    result_path.write_text(json.dumps(result_dict, indent=2))

    if result.symptom_class == SymptomClass.OBSERVED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
