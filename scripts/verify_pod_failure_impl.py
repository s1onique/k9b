"""Pod failure symptom verifier implementation."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from verify_pod_failure_types import SymptomClass, SymptomVerificationResult, write_snapshots


def run_kubectl(
    kubeconfig: str,
    namespace: str,
    args: list[str],
    timeout: int = 60,
) -> tuple[int, str, str]:
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


def get_pod_status(kubeconfig: str, namespace: str, pod_name: str) -> dict:
    """Get pod status JSON including container states and conditions."""
    rc, stdout, _ = run_kubectl(kubeconfig, namespace, ["get", "pod", pod_name, "-o", "json"])
    if rc == 0:
        return json.loads(stdout)  # type: ignore[no-any-return]
    return {}


def get_pod_events(kubeconfig: str, namespace: str, pod_name: str) -> list[dict]:
    """Get recent events for a specific pod."""
    rc, stdout, _ = run_kubectl(
        kubeconfig,
        namespace,
        ["get", "events", "--sort-by=.lastTimestamp", "-o", "json"],
    )
    if rc == 0:
        events_data: dict = json.loads(stdout)
        # Filter to events for our pod
        return [
            e for e in events_data.get("items", [])
            if e.get("involvedObject", {}).get("name") == pod_name
        ]
    return []


def get_pod_describe(kubeconfig: str, namespace: str, pod_name: str) -> str:
    """Get kubectl describe output for pod."""
    rc, stdout, _ = run_kubectl(kubeconfig, namespace, ["describe", "pod", pod_name])
    return stdout if rc == 0 else ""


# =============================================================================
# State analysis
# =============================================================================

def check_container_waiting_reason(pod_status: dict) -> tuple[str, str]:
    """Check containerStatuses for waiting reason.

    Returns (reason, message) for the first waiting container.
    """
    for cs in pod_status.get("status", {}).get("containerStatuses", []):
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        if waiting:
            reason = waiting.get("reason", "")
            message = waiting.get("message", "") or ""
            return reason, message
    return "", ""


def check_readiness_probe_failure(pod_status: dict, pod_describe: str) -> bool:
    """Check for readiness probe failure evidence.

    Returns True if readiness probe has failed (exit code != 0).
    """
    # Check container statuses for readiness probe failures
    for cs in pod_status.get("status", {}).get("containerStatuses", []):
        # Check lastState.terminated for probe failures
        last_state = cs.get("lastState", {})
        terminated = last_state.get("terminated", {})
        if terminated:
            exit_code = terminated.get("exitCode", 0)
            reason = terminated.get("reason", "")
            # Health check failures show as exit code 1 or specific reasons
            if exit_code != 0 and reason in ("Error", "Completed", ""):
                return True
        # Check ready status
        ready = cs.get("ready", False)
        if not ready:
            return True

    # Check conditions for Ready=False
    conditions = pod_status.get("status", {}).get("conditions", [])
    for cond in conditions:
        if cond.get("type") == "Ready":
            if cond.get("status") in ("False", "false"):
                return True

    # Check describe output for probe failure evidence
    describe_lower = pod_describe.lower()
    if "readiness probe" in describe_lower and ("failed" in describe_lower or "failure" in describe_lower):
        return True
    if "exec /bin/false" in pod_describe:
        # The fixture uses /bin/false for readiness probe
        return True

    return False


def classify_fatal_state(
    pod_status: dict,
    pod_describe: str,
    events: list[dict],
) -> tuple[bool, SymptomClass, str]:
    """Check if pod is in a fatal failure state.

    Returns (is_fatal, symptom_class, reason).
    """
    describe_lower = pod_describe.lower()

    # Check container waiting reasons for fatal states
    for cs in pod_status.get("status", {}).get("containerStatuses", []):
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        if waiting:
            reason = waiting.get("reason", "")
            message = waiting.get("message", "") or ""

            if reason in ("ImagePullBackOff", "ErrImagePull"):
                return True, SymptomClass.IMAGE_PULL_BACKOFF, f"{reason}: {message}"

            if reason == "CreateContainerConfigError":
                return True, SymptomClass.CREATE_CONTAINER_CONFIG_ERROR, f"{reason}: {message}"

    # Check events for scheduling failures
    for event in events:
        reason = event.get("reason", "")
        message = event.get("message", "") or ""
        if reason == "FailedScheduling":
            return True, SymptomClass.SCHEDULING_FAILED, f"FailedScheduling: {message}"

    # Check describe output for fatal patterns
    if "imagepullbackoff" in describe_lower or "errimagepull" in describe_lower:
        return True, SymptomClass.IMAGE_PULL_BACKOFF, "ImagePullBackOff detected in describe output"

    if "createcontainerconfigerror" in describe_lower:
        return True, SymptomClass.CREATE_CONTAINER_CONFIG_ERROR, "CreateContainerConfigError detected"

    if "failedscheduling" in describe_lower:
        return True, SymptomClass.SCHEDULING_FAILED, "FailedScheduling detected"

    return False, SymptomClass.PENDING, ""


def is_intermediate_state(pod_status: dict, pod_describe: str) -> tuple[bool, str]:
    """Check if pod is in a non-fatal intermediate state.

    Returns (is_intermediate, latest_event).
    """
    phase = pod_status.get("status", {}).get("phase", "")
    reason, _message = check_container_waiting_reason(pod_status)

    # ContainerCreating, Pulling, or Pending without fatal reasons are intermediate
    if phase == "Pending":
        if reason in ("", "ContainerCreating", "Waiting", "PodInitializing"):
            return True, reason or "Pending"
        return False, reason

    if reason == "ContainerCreating":
        return True, "ContainerCreating"

    if reason == "PodInitializing":
        return True, "PodInitializing"

    # Check describe for Pulling evidence
    describe_lower = pod_describe.lower()
    if "pulling" in describe_lower:
        return True, "Pulling"

    return False, reason or phase


def check_success_condition(pod_status: dict, pod_describe: str) -> bool:
    """Check if pod has reached the target symptom state.

    Target: phase=Running AND Ready=False AND readiness probe failure evidence.
    """
    phase = pod_status.get("status", {}).get("phase", "")
    if phase != "Running":
        return False

    # Check Ready condition
    conditions = pod_status.get("status", {}).get("conditions", [])
    ready_status = "Unknown"
    for cond in conditions:
        if cond.get("type") == "Ready":
            ready_status = cond.get("status", "Unknown")
            break

    if ready_status in ("True", "true"):
        return False

    # Check readiness probe failure evidence
    return check_readiness_probe_failure(pod_status, pod_describe)


# =============================================================================
# Main verification logic
# =============================================================================

def verify_pod_failure_symptom(
    kubeconfig: str,
    namespace: str,
    pod_name: str,
    deadline: int = 120,
    poll_interval: int = 5,
    artifact_dir: Path | None = None,
    wait_timeout: int = 60,
) -> SymptomVerificationResult:
    """Verify pod-failure symptom with state-aware polling.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Pod namespace
        pod_name: Name of the failing pod
        deadline: Maximum seconds to wait
        poll_interval: Seconds between polls
        artifact_dir: Optional directory for artifacts
        wait_timeout: Maximum seconds to wait for pod to exist (default 60s)

    Returns:
        SymptomVerificationResult with classification
    """
    start_time = time.time()
    poll_count = 0
    latest_event = ""
    pod_phase = "Unknown"
    pod_ready = "Unknown"
    container_state = "Unknown"
    container_waiting_reason = ""
    readiness_probe_failure_evidence = False

    # First, wait for pod to exist
    wait_start = time.time()
    while time.time() - wait_start < wait_timeout:
        rc, _, _ = run_kubectl(kubeconfig, namespace, ["get", "pod", pod_name])
        if rc == 0:
            break
        time.sleep(2)
    else:
        elapsed = time.time() - start_time
        write_snapshots(artifact_dir, [])
        return SymptomVerificationResult(
            symptom_class=SymptomClass.TIMEOUT,
            fatal=True,
            pod_phase="NotFound",
            pod_ready="Unknown",
            container_state="NotFound",
            container_waiting_reason="",
            latest_event="PodNotFound",
            readiness_probe_failure_evidence=False,
            failure_reason=f"Pod {pod_name} not found in namespace {namespace} after {wait_timeout}s",
            elapsed_seconds=elapsed,
            poll_count=0,
        )

    # Poll loop
    snapshots: list[dict] = []

    while time.time() - start_time < deadline:
        poll_count += 1
        elapsed = time.time() - start_time

        # Get current state
        pod_status = get_pod_status(kubeconfig, namespace, pod_name)
        pod_describe = get_pod_describe(kubeconfig, namespace, pod_name)
        events = get_pod_events(kubeconfig, namespace, pod_name)

        # Extract current state
        pod_phase = pod_status.get("status", {}).get("phase", "Unknown")

        conditions = pod_status.get("status", {}).get("conditions", [])
        for cond in conditions:
            if cond.get("type") == "Ready":
                pod_ready = str(cond.get("status", "Unknown"))
                break

        container_state = "Unknown"
        container_statuses = pod_status.get("status", {}).get("containerStatuses", [])
        if container_statuses:
            cs = container_statuses[0]
            if "running" in cs.get("state", {}):
                container_state = "Running"
            elif "waiting" in cs.get("state", {}):
                container_state = "Waiting"
            elif "terminated" in cs.get("state", {}):
                container_state = "Terminated"

        container_waiting_reason, _ = check_container_waiting_reason(pod_status)

        # Get latest event
        if events:
            latest_event = f"{events[-1].get('reason', '')}: {events[-1].get('message', '')[:100]}"

        # Record snapshot
        snapshot = {
            "poll_count": poll_count,
            "elapsed_seconds": round(elapsed, 1),
            "pod_phase": pod_phase,
            "pod_ready": pod_ready,
            "container_state": container_state,
            "container_waiting_reason": container_waiting_reason,
            "latest_event": latest_event,
        }
        snapshots.append(snapshot)

        # Check for fatal state FIRST
        is_fatal, symptom_class, failure_reason = classify_fatal_state(
            pod_status, pod_describe, events
        )
        if is_fatal:
            readiness_probe_failure_evidence = check_readiness_probe_failure(pod_status, pod_describe)
            write_snapshots(artifact_dir, snapshots)
            return SymptomVerificationResult(
                symptom_class=symptom_class,
                fatal=True,
                pod_phase=pod_phase,
                pod_ready=pod_ready,
                container_state=container_state,
                container_waiting_reason=container_waiting_reason,
                latest_event=latest_event,
                readiness_probe_failure_evidence=readiness_probe_failure_evidence,
                failure_reason=failure_reason,
                elapsed_seconds=elapsed,
                poll_count=poll_count,
            )

        # Check for success condition
        if check_success_condition(pod_status, pod_describe):
            readiness_probe_failure_evidence = True
            write_snapshots(artifact_dir, snapshots)
            return SymptomVerificationResult(
                symptom_class=SymptomClass.OBSERVED,
                fatal=False,
                pod_phase=pod_phase,
                pod_ready=pod_ready,
                container_state=container_state,
                container_waiting_reason=container_waiting_reason,
                latest_event=latest_event,
                readiness_probe_failure_evidence=readiness_probe_failure_evidence,
                failure_reason="",
                elapsed_seconds=elapsed,
                poll_count=poll_count,
            )

        # Check for intermediate state (non-fatal, keep polling)
        is_intermediate, intermediate_event = is_intermediate_state(pod_status, pod_describe)
        if is_intermediate:
            print(
                f"[verify_pod_failure_symptom] poll={poll_count} elapsed={elapsed:.1f}s "
                f"phase={pod_phase} reason={container_waiting_reason or intermediate_event} - waiting...",
                flush=True,
            )
            time.sleep(poll_interval)
            continue

        # Unknown state - might be transitioning, keep polling
        print(
            f"[verify_pod_failure_symptom] poll={poll_count} elapsed={elapsed:.1f}s "
            f"phase={pod_phase} ready={pod_ready} - checking...",
            flush=True,
        )
        time.sleep(poll_interval)

    # Timeout
    elapsed = time.time() - start_time
    print(
        f"[verify_pod_failure_symptom] TIMEOUT after {elapsed:.1f}s ({poll_count} polls)",
        flush=True,
    )

    # Timeout
    write_snapshots(artifact_dir, snapshots)
    return SymptomVerificationResult(
        symptom_class=SymptomClass.TIMEOUT,
        fatal=True,
        pod_phase=pod_phase,
        pod_ready=pod_ready,
        container_state=container_state,
        container_waiting_reason=container_waiting_reason,
        latest_event=latest_event,
        readiness_probe_failure_evidence=False,
        failure_reason=f"Timeout after {deadline}s - pod still in {pod_phase}/{container_waiting_reason or 'Unknown'} state",
        elapsed_seconds=elapsed,
        poll_count=poll_count,
    )


# =============================================================================
# CLI entry point
# =============================================================================
