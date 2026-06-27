"""Rendering module for scheduler health gate.

This module handles output formatting for human-readable and JSON output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .contracts import SchedulerHealthResult

# Maximum lines to include from logs in bounded summary
MAX_LOG_LINES = 20

# =============================================================================
# Console output rendering
# =============================================================================


def render_console_output(result: SchedulerHealthResult) -> None:
    """Print human-readable status to stdout."""
    if result.passed:
        print("SCHEDULER HEALTH GATE PASSED", flush=True)
    else:
        print(f"SCHEDULER HEALTH GATE FAILED: {result.failure_class}", flush=True)
        print(f"  Reason: {result.failure_reason}", flush=True)
        print(f"  Details: {result.failure_details}", flush=True)


def render_deployment_status(
    ready_replicas: int,
    spec_replicas: int,
    available_replicas: int,
) -> None:
    """Print deployment status to stdout."""
    print("Scheduler deployment status:", flush=True)
    print(f"  Ready replicas: {ready_replicas}/{spec_replicas}", flush=True)
    print(f"  Available replicas: {available_replicas}/{spec_replicas}", flush=True)


def render_partial_readiness_warning(ready_replicas: int, spec_replicas: int) -> None:
    """Print partial readiness warning."""
    print(f"WARNING: Scheduler has partial readiness ({ready_replicas}/{spec_replicas})", flush=True)


# =============================================================================
# Artifact writing
# =============================================================================


def write_result_artifact(
    scheduler_dir: Path,
    result: SchedulerHealthResult,
) -> Path:
    """Write main result JSON artifact.
    
    Returns:
        Path to the written result file.
    """
    result_path = scheduler_dir / "scheduler-health-result.json"
    result_path.write_text(json.dumps(result.to_dict(), indent=2))
    print(f"Result artifact: {result_path}", flush=True)
    return result_path


def _bound_log_content(log_content: str | None, max_lines: int = MAX_LOG_LINES) -> str:
    """Bound log content to at most max_lines, preserving head and tail.
    
    Shows startup context at the head and crash/error context at the tail,
    with a marker line indicating how many lines were omitted.
    """
    if not log_content:
        return "(no log content)"

    lines = log_content.strip().split("\n")
    if len(lines) <= max_lines:
        return log_content.strip()

    # Reserve 1 line for the ellipsis marker, split remainder between head and tail
    retained = max_lines - 1
    omitted_count = len(lines) - retained
    marker = f"... [{omitted_count} more lines] ..."
    head_count = retained // 2
    tail_count = retained - head_count

    return "\n".join([
        *lines[:head_count],
        marker,
        *lines[-tail_count:],
    ])


def _format_crash_evidence(crash: dict, logs: dict[str, str]) -> list[str]:
    """Format crash loop evidence with termination details and log excerpts."""
    pod_name = crash.get("pod", "")
    container = crash.get("container", "")
    reason = crash.get("reason", "")
    restart_count = crash.get("restart_count", 0)
    message = crash.get("message", "")
    
    lines = [
        f"  - {pod_name}/{container}: {reason} (restarts={restart_count})",
    ]
    
    # Include termination details if available
    last_exit_code = crash.get("last_exit_code")
    last_exit_reason = crash.get("last_exit_reason")
    last_exit_message = crash.get("last_exit_message")
    exit_code = crash.get("exit_code")
    exit_reason = crash.get("exit_reason")
    exit_message = crash.get("exit_message")
    
    if last_exit_code is not None:
        term_reason = last_exit_reason or "Unknown"
        lines.append(f"    Previous termination: exit={last_exit_code} reason={term_reason}")
        if last_exit_message:
            lines.append(f"    Last exit message: {last_exit_message[:200]}")
    elif exit_code is not None:
        term_reason = exit_reason or "Unknown"
        lines.append(f"    Termination: exit={exit_code} reason={term_reason}")
        if exit_message:
            lines.append(f"    Exit message: {exit_message[:200]}")
    
    if message:
        lines.append(f"    Waiting message: {message[:200]}")
    
    # Include bounded log excerpts
    if logs:
        current_log = logs.get(pod_name, "")
        prev_log = logs.get(f"{pod_name}.previous", "")
        
        if current_log:
            lines.append(f"    Current log excerpt (max {MAX_LOG_LINES} lines):")
            for line in _bound_log_content(current_log, MAX_LOG_LINES).split("\n"):
                lines.append(f"      {line[:200]}")
        
        if prev_log:
            lines.append(f"    Previous log excerpt (max {MAX_LOG_LINES} lines):")
            for line in _bound_log_content(prev_log, MAX_LOG_LINES).split("\n"):
                lines.append(f"      {line[:200]}")
    
    return lines


def write_bounded_summary(
    scheduler_dir: Path,
    result: SchedulerHealthResult,
) -> Path:
    """Write bounded summary text artifact with crash loop evidence.
    
    Returns:
        Path to the written summary file.
    """
    summary_lines: list[str] = [
        f"Scheduler Health Gate Result: {'PASSED' if result.passed else 'FAILED'}",
        f"Failure class: {result.failure_class}",
        f"Failure reason: {result.failure_reason}",
        f"Failure details: {result.failure_details}",
        "",
        f"Deployment: {result.deployment_name}",
        f"Found: {result.deployment_found}",
        f"Pod count: {result.pod_count}",
        f"Ready replicas: {result.ready_replicas}",
        f"Available replicas: {result.available_replicas}",
        "",
        f"Crash loop pods: {len(result.crash_loop_pods)}",
    ]
    
    # Include detailed evidence for crash loop pods
    for crash in result.crash_loop_pods:
        summary_lines.extend(_format_crash_evidence(crash, result.scheduler_logs))
    
    summary_lines.extend([
        "",
        f"Waiting pods: {len(result.waiting_pods)}",
    ])
    
    for waiting in result.waiting_pods:
        summary_lines.append(
            f"  - {waiting['pod']}/{waiting['container']}: "
            f"{waiting['reason']}"
        )
    
    summary_lines.extend([
        "",
        f"Namespace events (scheduler-related): {len(result.namespace_events)}",
    ])
    
    summary_path = scheduler_dir / "bounded-summary.txt"
    summary_path.write_text("\n".join(summary_lines))
    print(f"Summary artifact: {summary_path}", flush=True)
    return summary_path


def write_pods_json(
    scheduler_dir: Path,
    scheduler_pods_json: str,
) -> Path | None:
    """Write raw pods JSON artifact for debugging.
    
    Returns:
        Path to the written pods file, or None if empty.
    """
    if not scheduler_pods_json:
        return None
    
    pods_path = scheduler_dir / "scheduler-pods.json"
    pods_path.write_text(scheduler_pods_json)
    print(f"Pods artifact: {pods_path}", flush=True)
    return pods_path


def write_logs(
    scheduler_dir: Path,
    logs: dict[str, str],
) -> Path:
    """Write logs to artifact directory.
    
    Returns:
        Path to the logs directory.
    """
    logs_dir = scheduler_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for pod_name, log_content in logs.items():
        (logs_dir / f"{pod_name}.log").write_text(log_content)
    print(f"Logs artifact: {logs_dir}/", flush=True)
    return logs_dir


def write_debug_logs(logs: dict[str, str]) -> Path:
    """Write extra debug copy to RUNNER_TEMP or /tmp.
    
    Returns:
        Path to the debug logs directory.
    """
    runner_temp = os.environ.get("RUNNER_TEMP", "/tmp")
    debug_dir = Path(runner_temp) / "k9b-scheduler-health-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for pod_name, log_content in logs.items():
        (debug_dir / f"{pod_name}.log").write_text(log_content)
    print(f"Debug logs: {debug_dir}/", flush=True)
    return debug_dir


def write_all_artifacts(
    scheduler_dir: Path,
    result: SchedulerHealthResult,
    logs: dict[str, str],
) -> None:
    """Write all result artifacts.
    
    Args:
        scheduler_dir: Directory for scheduler artifacts
        result: Scheduler health result
        logs: Collected scheduler logs
    """
    write_result_artifact(scheduler_dir, result)
    write_bounded_summary(scheduler_dir, result)
    write_pods_json(scheduler_dir, result.scheduler_pods_json)
    write_logs(scheduler_dir, logs)
    write_debug_logs(logs)
