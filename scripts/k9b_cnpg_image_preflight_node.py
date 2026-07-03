"""Node-side image pullability preflight using diagnostic pods."""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_kubectl(kubeconfig: str, namespace: str, args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """Run kubectl command and return (returncode, stdout, stderr)."""
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "kubectl timeout"
    except FileNotFoundError:
        return -1, "", "kubectl not found"
    except Exception as e:
        return -1, "", str(e)


def create_diagnostic_pod(kubeconfig: str, namespace: str, image_ref: str, component: str) -> tuple[str | None, str]:
    """Create short-lived diagnostic pod to test image pullability."""
    pod_name = f"img-preflight-{component}-{int(time.time())}"
    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {"app": "image-preflight", "component": component},
        },
        "spec": {
            "restartPolicy": "Never",
            "activeDeadlineSeconds": 120,
            "containers": [{
                "name": "test",
                "image": image_ref,
                "command": ["sh", "-c", "exit 0"],
                "imagePullPolicy": "Always",
                "resources": {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "100m", "memory": "64Mi"}},
            }],
        },
    }
    manifest_path = Path(f"/tmp/preflight-pod-{component}.json")
    manifest_path.write_text(json.dumps(pod_manifest))
    rc, stdout, stderr = run_kubectl(kubeconfig, namespace, ["apply", "-f", str(manifest_path)])
    manifest_path.unlink(missing_ok=True)
    if rc != 0:
        return None, f"Failed to create pod: {stderr}"
    return pod_name, ""


def delete_pod(kubeconfig: str, namespace: str, pod_name: str) -> None:
    """Delete diagnostic pod."""
    run_kubectl(kubeconfig, namespace, ["delete", "pod", pod_name, "--wait=false"])


def get_pod_status(kubeconfig: str, namespace: str, pod_name: str) -> dict[str, Any]:
    """Get pod status JSON including container states."""
    rc, stdout, _ = run_kubectl(kubeconfig, namespace, ["get", "pod", pod_name, "-o", "json"])
    if rc == 0:
        return json.loads(stdout)  # type: ignore[no-any-return]
    return {}


def get_pod_events(kubeconfig: str, namespace: str) -> dict[str, Any]:
    """Get namespace events JSON."""
    rc, stdout, _ = run_kubectl(kubeconfig, namespace, ["get", "events", "--sort-by=.lastTimestamp", "-o", "json"])
    if rc == 0:
        return json.loads(stdout)  # type: ignore[no-any-return]
    return {"items": []}


def get_pod_describe(kubeconfig: str, namespace: str, pod_name: str) -> str:
    """Get kubectl describe output for pod."""
    rc, stdout, _ = run_kubectl(kubeconfig, namespace, ["describe", "pod", pod_name])
    return stdout if rc == 0 else ""


def classify_pull_failure(events_json: dict, pod_name: str, describe_output: str) -> tuple[str, str]:
    """Classify pull failure from events scoped to specific pod.

    Returns (failure_class, message).
    """
    from k9b_cnpg_image_preflight_types import (
        FAIL_NODE_IMAGE_MISSING,
        FAIL_NODE_NETWORK,
        FAIL_NODE_PULL_BACKOFF,
        FAIL_NODE_TLS,
        FAIL_NODE_UNAUTHORIZED,
    )

    # Check events for our specific pod
    for event in events_json.get("items", []):
        involved = event.get("involvedObject", {})
        if involved.get("name") != pod_name or involved.get("kind") != "Pod":
            continue
        reason = event.get("reason", "")
        message = event.get("message", "") or ""
        if reason in ("ImagePullBackOff", "ErrImagePull"):
            msg_lower = message.lower()
            if "manifest unknown" in msg_lower or "not found" in msg_lower:
                return FAIL_NODE_IMAGE_MISSING, message
            if "unauthorized" in msg_lower or "authentication" in msg_lower or "forbidden" in msg_lower or "denied" in msg_lower:
                return FAIL_NODE_UNAUTHORIZED, message
            if "certificate" in msg_lower or "tls" in msg_lower or "ssl" in msg_lower:
                return FAIL_NODE_TLS, message
            if "dial tcp" in msg_lower or "network" in msg_lower or "connect" in msg_lower or "dns" in msg_lower or "no such host" in msg_lower:
                return FAIL_NODE_NETWORK, message
            return FAIL_NODE_PULL_BACKOFF, message

    # Check describe output for waiting containers
    output_lower = describe_output.lower()
    if "imagepullbackoff" in output_lower or "errimagepull" in output_lower:
        for line in describe_output.split("\n"):
            line_lower = line.lower()
            if "imagepullbackoff" in line_lower or "errimagepull" in line_lower:
                if ":" in line:
                    message = line.split(":", 1)[1].strip()
                    msg_lower = message.lower()
                    if "manifest unknown" in msg_lower or "not found" in msg_lower:
                        return FAIL_NODE_IMAGE_MISSING, message
                    if "unauthorized" in msg_lower or "forbidden" in msg_lower or "denied" in msg_lower:
                        return FAIL_NODE_UNAUTHORIZED, message
                    if "certificate" in msg_lower or "tls" in msg_lower:
                        return FAIL_NODE_TLS, message
                    if "network" in msg_lower or "connect" in msg_lower:
                        return FAIL_NODE_NETWORK, message
                    return FAIL_NODE_PULL_BACKOFF, message
        return FAIL_NODE_PULL_BACKOFF, "ImagePullBackOff detected"

    return "", ""


def check_container_waiting_reason(pod_status: dict) -> tuple[str, str]:
    """Check containerStatuses for waiting reason.

    Returns (reason, message) for the first waiting container.
    """
    from k9b_cnpg_image_preflight_types import (
        FAIL_NODE_IMAGE_MISSING,
        FAIL_NODE_NETWORK,
        FAIL_NODE_PULL_BACKOFF,
        FAIL_NODE_TLS,
        FAIL_NODE_UNAUTHORIZED,
    )

    for cs in pod_status.get("status", {}).get("containerStatuses", []):
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        if waiting:
            reason = waiting.get("reason", "")
            message = waiting.get("message", "") or ""
            if reason in ("ImagePullBackOff", "ErrImagePull"):
                msg_lower = message.lower()
                if "manifest unknown" in msg_lower or "not found" in msg_lower:
                    return reason, FAIL_NODE_IMAGE_MISSING
                if "unauthorized" in msg_lower or "forbidden" in msg_lower or "denied" in msg_lower:
                    return reason, FAIL_NODE_UNAUTHORIZED
                if "certificate" in msg_lower or "tls" in msg_lower:
                    return reason, FAIL_NODE_TLS
                if "network" in msg_lower or "connect" in msg_lower or "dns" in msg_lower:
                    return reason, FAIL_NODE_NETWORK
                return reason, FAIL_NODE_PULL_BACKOFF
    return "", ""


def check_node_pullability(
    kubeconfig: str,
    namespace: str,
    image_ref: str,
    component: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Test image pullability on cluster nodes.

    Creates diagnostic pod, polls for container waiting reason, fails fast on pull failure.
    Returns dict with keys matching NodePullResult.
    """
    from k9b_cnpg_image_preflight_types import (
        FAIL_NODE_IMAGE_MISSING,
        FAIL_NODE_NETWORK,
        FAIL_NODE_PULL_BACKOFF,
        FAIL_NODE_TLS,
        FAIL_NODE_UNAUTHORIZED,
        FAIL_NODE_UNKNOWN,
        NodePullResult,
    )

    timestamp = datetime.now(UTC).isoformat()
    pod_name: str | None = None
    pod_phase = ""
    container_reason = ""
    container_message = ""
    describe_output = ""
    events_json: dict[str, Any] = {"items": []}

    pod_name, create_error = create_diagnostic_pod(kubeconfig, namespace, image_ref, component)
    if not pod_name:
        return NodePullResult(  # type: ignore[no-any-return]
            component=component,
            image_ref=image_ref,
            pod_name="",
            success=False,
            failure_class=FAIL_NODE_UNKNOWN,
            events_summary=f"Failed to create pod: {create_error}",
            timestamp=timestamp,
        ).to_dict()

    try:
        start_time = time.time()
        poll_interval = 3
        max_wait = 60

        while time.time() - start_time < max_wait:
            pod_status = get_pod_status(kubeconfig, namespace, pod_name)
            pod_phase = pod_status.get("status", {}).get("phase", "")

            # Check container waiting reason FIRST (fast-fail on pull errors)
            reason, failure_class = check_container_waiting_reason(pod_status)
            if reason:
                container_reason = reason
                container_message = pod_status.get("status", {}).get("containerStatuses", [{}])[0].get("state", {}).get("waiting", {}).get("message", "")
                events_json = get_pod_events(kubeconfig, namespace)
                describe_output = get_pod_describe(kubeconfig, namespace, pod_name)
                # Classify based on waiting reason
                if failure_class == FAIL_NODE_IMAGE_MISSING:
                    pass  # Already set
                elif failure_class == FAIL_NODE_UNAUTHORIZED:
                    pass
                elif failure_class == FAIL_NODE_TLS:
                    pass
                elif failure_class == FAIL_NODE_NETWORK:
                    pass
                else:
                    failure_class = FAIL_NODE_PULL_BACKOFF

                return NodePullResult(  # type: ignore[no-any-return]
                    component=component,
                    image_ref=image_ref,
                    pod_name=pod_name,
                    success=False,
                    failure_class=failure_class,
                    pod_phase=pod_phase,
                    container_waiting_reason=container_reason,
                    container_waiting_message=container_message,
                    events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
                    describe_output=describe_output[:2000],
                    timestamp=timestamp,
                ).to_dict()

            # Pod succeeded - pull works
            if pod_phase == "Succeeded":
                events_json = get_pod_events(kubeconfig, namespace)
                return NodePullResult(  # type: ignore[no-any-return]
                    component=component,
                    image_ref=image_ref,
                    pod_name=pod_name,
                    success=True,
                    pod_phase=pod_phase,
                    events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
                    timestamp=timestamp,
                ).to_dict()

            # Pod failed - parse events
            if pod_phase in ("Failed", "Error"):
                events_json = get_pod_events(kubeconfig, namespace)
                describe_output = get_pod_describe(kubeconfig, namespace, pod_name)
                fc, msg = classify_pull_failure(events_json, pod_name, describe_output)
                if fc:
                    container_reason = "ErrImagePull" if "imagepull" not in container_reason.lower() else container_reason
                    return NodePullResult(  # type: ignore[no-any-return]
                        component=component,
                        image_ref=image_ref,
                        pod_name=pod_name,
                        success=False,
                        failure_class=fc,
                        pod_phase=pod_phase,
                        container_waiting_reason=container_reason,
                        container_waiting_message=msg,
                        events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
                        describe_output=describe_output[:2000],
                        timestamp=timestamp,
                    ).to_dict()
                return NodePullResult(  # type: ignore[no-any-return]
                    component=component,
                    image_ref=image_ref,
                    pod_name=pod_name,
                    success=False,
                    failure_class=FAIL_NODE_UNKNOWN,
                    pod_phase=pod_phase,
                    events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
                    describe_output=describe_output[:2000],
                    timestamp=timestamp,
                ).to_dict()

            time.sleep(poll_interval)

        # Timeout - check final state
        events_json = get_pod_events(kubeconfig, namespace)
        describe_output = get_pod_describe(kubeconfig, namespace, pod_name)
        fc, msg = classify_pull_failure(events_json, pod_name, describe_output)
        if fc:
            return NodePullResult(  # type: ignore[no-any-return]
                component=component,
                image_ref=image_ref,
                pod_name=pod_name,
                success=False,
                failure_class=fc,
                pod_phase=pod_phase or "Timeout",
                events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
                describe_output=describe_output[:2000],
                timestamp=timestamp,
            ).to_dict()

        return NodePullResult(  # type: ignore[no-any-return]
            component=component,
            image_ref=image_ref,
            pod_name=pod_name,
            success=False,
            failure_class=FAIL_NODE_UNKNOWN,
            pod_phase=pod_phase or "Timeout",
            events_summary=json.dumps([e for e in events_json.get("items", []) if e.get("involvedObject", {}).get("name") == pod_name][-5:]),
            describe_output=describe_output[:2000],
            timestamp=timestamp,
        ).to_dict()

    finally:
        delete_pod(kubeconfig, namespace, pod_name)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Test node-side image pullability")
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--component", required=True)
    args = parser.parse_args(sys.argv[1:])

    result = check_node_pullability(args.kubeconfig, args.namespace, args.image, args.component, Path("/tmp"))
    print(json.dumps(result, indent=2))
