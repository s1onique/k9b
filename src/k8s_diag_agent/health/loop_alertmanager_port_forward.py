"""Alertmanager port-forward process helpers for health loop runs."""

from __future__ import annotations

import subprocess
from collections.abc import Callable


def start_alertmanager_port_forward(
    namespace: str,
    service_name: str,
    context: str | None,
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
    choose_free_local_port: Callable[[], int],
    wait_for_port_ready: Callable[[str, int, float, float], bool],
) -> tuple[subprocess.Popen[str], int]:
    """Start kubectl port-forward to an Alertmanager service.

    Chooses a free local port and waits for it to become ready before returning.

    Args:
        namespace: Kubernetes namespace for the Alertmanager service.
        service_name: Name of the Kubernetes service to port-forward to.
        context: Kubernetes context to use (None for default context).
        run_id: Run identifier for logging.
        run_label: Run label for logging.
        log_event: Callback for structured logging (component, severity, message, **metadata).
        choose_free_local_port: Callable to select a free local TCP port.
        wait_for_port_ready: Callable to poll until a port accepts connections.

    Returns:
        Tuple of (subprocess handle, local port number).

    Raises:
        RuntimeError: If port-forward cannot be started or the port
            does not become ready within the timeout.
    """
    from ..security.subprocess_helpers import _log_subprocess_failure

    # Choose a free local port before starting kubectl
    local_port = choose_free_local_port()

    # Build the kubectl command with the chosen port
    cmd = [
        "kubectl", "port-forward",
        "-n", namespace,
        f"svc/{service_name}",
        f"{local_port}:9093",  # Forward to Alertmanager's default port
    ]
    if context:
        cmd.extend(["--context", context])

    log_event(
        "alertmanager-snapshot",
        "INFO",
        "Starting Alertmanager port-forward",
        event="alertmanager-portforward-start",
        run_id=run_id,
        run_label=run_label,
        namespace=namespace,
        service_name=service_name,
        cluster_context=context,
        local_port=local_port,
    )

    try:
        # Start the port-forward process with text mode for type compatibility
        # Capture stderr for diagnostics (stdout discarded as it's kubectl port-forward noise)
        port_forward_process: subprocess.Popen[str] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for the port to become ready (with retries)
        if not wait_for_port_ready("127.0.0.1", local_port, 5.0, 0.1):
            # Port did not become ready - capture stderr for diagnostics before cleanup
            # Avoid communicate-before-kill hang: kill first if still running, then collect stderr
            stderr_output = ""
            if port_forward_process.poll() is None:
                port_forward_process.kill()
                try:
                    _, stderr_output = port_forward_process.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    port_forward_process.kill()
                    _, stderr_output = port_forward_process.communicate()
            else:
                try:
                    _, stderr_output = port_forward_process.communicate(timeout=0.1)
                except subprocess.TimeoutExpired:
                    stderr_output = ""

            # Log subprocess failure with safe metadata
            _log_subprocess_failure(
                operation="port_forward",
                command_args=cmd,
                return_code=port_forward_process.returncode,
                stderr=stderr_output,
                run_id=run_id,
                cluster_label=run_label,
            )

            log_event(
                "alertmanager-snapshot",
                "ERROR",
                "Alertmanager port-forward failed to become ready",
                event="alertmanager-portforward-failed",
                run_id=run_id,
                run_label=run_label,
                namespace=namespace,
                service_name=service_name,
                local_port=local_port,
                reason="port-not-ready",
            )
            raise RuntimeError(
                f"kubectl port-forward for {namespace}/{service_name} "
                f"did not become ready on port {local_port}"
            )

        # Check if process is still running
        if port_forward_process.poll() is not None:
            log_event(
                "alertmanager-snapshot",
                "ERROR",
                "Alertmanager port-forward failed to start",
                event="alertmanager-portforward-failed",
                run_id=run_id,
                run_label=run_label,
                namespace=namespace,
                service_name=service_name,
                exit_code=port_forward_process.returncode,
                reason="process-exited",
            )
            raise RuntimeError(
                f"kubectl port-forward exited unexpectedly with code "
                f"{port_forward_process.returncode}"
            )

        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager port-forward ready",
            event="alertmanager-portforward-ready",
            run_id=run_id,
            run_label=run_label,
            namespace=namespace,
            service_name=service_name,
            local_port=local_port,
        )

        return port_forward_process, local_port

    except FileNotFoundError:
        log_event(
            "alertmanager-snapshot",
            "ERROR",
            "kubectl not found - cannot establish port-forward",
            event="alertmanager-portforward-failed",
            run_id=run_id,
            run_label=run_label,
            namespace=namespace,
            service_name=service_name,
            reason="kubectl-not-found",
        )
        raise RuntimeError("kubectl not found in PATH - cannot port-forward to Alertmanager")
    except OSError as exc:
        log_event(
            "alertmanager-snapshot",
            "ERROR",
            "Failed to start port-forward subprocess",
            event="alertmanager-portforward-failed",
            run_id=run_id,
            run_label=run_label,
            namespace=namespace,
            service_name=service_name,
            severity_reason=str(exc),
            reason="subprocess-error",
        )
        raise RuntimeError(f"Failed to start kubectl port-forward: {exc}")


def stop_alertmanager_port_forward(
    process: subprocess.Popen[str],
    local_port: int | None,
    run_id: str,
    run_label: str,
    log_event: Callable[..., None],
) -> None:
    """Stop the port-forward process and log the event.

    Args:
        process: The subprocess.Popen handle from start_alertmanager_port_forward.
        local_port: The local port number that was forwarded (for logging).
        run_id: Run identifier for logging.
        run_label: Run label for logging.
        log_event: Callback for structured logging (component, severity, message, **metadata).
    """
    try:
        if process.poll() is None:
            # Process is still running, terminate it gracefully
            process.terminate()
            try:
                # Wait briefly for graceful termination
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop gracefully
                process.kill()
                process.wait()

        log_event(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager port-forward stopped",
            event="alertmanager-portforward-stopped",
            run_id=run_id,
            run_label=run_label,
            local_port=local_port,
        )
    # REVIEWED: port-forward cleanup subprocess boundary.
    # Must never propagate exceptions during cleanup -- process termination/kill are best-effort
    # and may raise OSError (broken pipe), subprocess.SubprocessError, or TimeoutError.
    # These are all expected during cleanup and must not crash the health loop.
    # Logged as warning, run continues. No credential exposure.
    except Exception as exc:
        log_event(
            "alertmanager-snapshot",
            "WARNING",
            "Error during port-forward cleanup",
            event="alertmanager-portforward-stopped",
            run_id=run_id,
            run_label=run_label,
            local_port=local_port,
            severity_reason=str(exc),
            reason="cleanup-error",
        )