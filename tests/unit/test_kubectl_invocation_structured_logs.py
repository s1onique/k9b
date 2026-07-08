"""Runtime-seam tests for kubectl_invocation structured logging.

This module proves that log_kubectl_invocation() emits JSONL-only output,
enforcing the runtime contract for scheduler monitoring and UI warning counts.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import TextIO

from k8s_diag_agent.security.kubectl_invocation import KubectlInvocation, log_kubectl_invocation


class TestLogKubectlInvocationStructuredLogs:
    """Runtime-seam tests for log_kubectl_invocation.

    Uses explicit writer capture to avoid pytest capsys interference.
    """

    def _call_with_capture(
        self,
        invocation: KubectlInvocation,
        level: str,
        message: str,
        writer: TextIO,
    ) -> None:
        """Helper to call log_kubectl_invocation with explicit writer."""
        import k8s_diag_agent.structured_logging as sl_module

        # Save original state
        original_writer = sl_module.DEFAULT_LOG_STREAM
        original_func = sl_module.emit_structured_log

        try:
            sl_module.DEFAULT_LOG_STREAM = writer

            def patched_emit(
                component: str,
                message: str,
                run_label: str,
                *,
                severity: str = "INFO",
                run_id: str | None = None,
                log_path: Path | None = None,
                writer: TextIO | None = None,
                metadata: dict[str, object] | None = None,
                **extra_metadata: dict[str, object],
            ) -> dict[str, object]:
                result: dict[str, object] = original_func(
                    component=component,
                    message=message,
                    run_label=run_label,
                    severity=severity,
                    run_id=run_id,
                    log_path=log_path,
                    writer=writer,
                    metadata=metadata,
                    **extra_metadata,
                )
                return result

            sl_module.emit_structured_log = patched_emit
            log_kubectl_invocation(invocation, level, message)
        finally:
            sl_module.DEFAULT_LOG_STREAM = original_writer
            sl_module.emit_structured_log = original_func

    def test_log_kubectl_invocation_emits_only_structured_log(self) -> None:
        """Prove log_kubectl_invocation emits JSONL only (no unstructured logs)."""
        invocation = KubectlInvocation.from_command(
            ["kubectl", "version", "--output", "json"],
            timeout_seconds=60,
            run_id="run-1",
        )
        invocation.failed = True
        invocation.returncode = 1
        invocation.error_message = "connection refused"

        writer = StringIO()
        self._call_with_capture(
            invocation,
            "ERROR",
            "kubectl failed with exit code 1",
            writer,
        )

        output = writer.getvalue()
        lines = [line for line in output.splitlines() if line.strip()]

        # Should emit exactly one log line (JSONL)
        assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}: {lines}"

        # The line must be valid JSON
        payload = json.loads(lines[0])

        # Must have required fields for runtime contract
        assert "timestamp" in payload, "missing timestamp field"
        assert "component" in payload, "missing component field"
        assert payload["component"] == "kubectl-invocation"
        assert "severity" in payload, "missing severity field"
        assert payload["severity"] == "ERROR"
        assert "message" in payload, "missing message field"
        assert payload["message"] == "kubectl failed with exit code 1"

        # Should not have unstructured text (the old bug pattern)
        line_text = lines[0]
        assert not line_text.startswith("kubectl failed with exit code"), \
            "Unstructured log line detected - raw text instead of JSON"
        assert not line_text.startswith("argv="), \
            "Unstructured log line detected - argv prefix instead of JSON"

    def test_log_kubectl_invocation_debug_flag_disabled(self) -> None:
        """Prove no unstructured logs when K9B_DEBUG_UNSTRUCTURED_LOGS is not set."""
        invocation = KubectlInvocation.from_command(
            ["kubectl", "get", "pods", "-n", "default"],
            timeout_seconds=30,
            run_id="run-debug-test",
        )

        writer = StringIO()
        self._call_with_capture(
            invocation,
            "INFO",
            "kubectl completed successfully",
            writer,
        )

        output = writer.getvalue()
        lines = [line for line in output.splitlines() if line.strip()]

        # Should emit exactly one JSONL line (debug flag is off by default)
        assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}: {lines}"

        # Must be valid JSON
        payload = json.loads(lines[0])
        assert payload["component"] == "kubectl-invocation"
        assert payload["severity"] == "INFO"

    def test_log_kubectl_invocation_all_severities(self) -> None:
        """Prove all valid severities emit JSONL only."""
        valid_severities = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for severity in valid_severities:
            invocation = KubectlInvocation.from_command(
                ["kubectl", "version"],
                timeout_seconds=10,
            )

            writer = StringIO()
            self._call_with_capture(
                invocation,
                severity,
                f"test {severity} message",
                writer,
            )

            output = writer.getvalue()
            lines = [line for line in output.splitlines() if line.strip()]

            assert len(lines) == 1, f"Severity {severity}: expected 1 line, got {len(lines)}"
            payload = json.loads(lines[0])
            assert payload["severity"] == severity, f"Severity {severity} mismatch"
            assert payload["component"] == "kubectl-invocation"

    def test_log_kubectl_invocation_no_duplicate_emission(self) -> None:
        """Prove no duplicate log lines (one event = one JSONL record)."""
        invocation = KubectlInvocation.from_command(
            ["kubectl", "top", "pods"],
            timeout_seconds=30,
            run_id="run-dup-test",
        )
        invocation.failed = True
        invocation.returncode = 2
        invocation.stderr_bytes = 256

        writer = StringIO()
        self._call_with_capture(
            invocation,
            "WARNING",
            "kubectl top pods failed",
            writer,
        )

        output = writer.getvalue()
        lines = [line for line in output.splitlines() if line.strip()]

        # Exactly one log record per event
        assert len(lines) == 1, \
            f"Duplicate emission detected: expected 1 line, got {len(lines)}: {lines}"

        # Must be parseable as JSON
        payload = json.loads(lines[0])
        assert payload["event"] == "kubectl_invocation"
        assert payload["failed"] is True

    def test_log_kubectl_invocation_output_shape_contract(self) -> None:
        """Prove kubectl_invocation logs expose expected runtime fields from to_log_dict.

        This test explicitly verifies the output shape contract - fields from
        KubectlInvocation.to_log_dict() must appear in the JSON payload under
        the metadata merge path (not kwargs expansion).

        The metadata= parameter path was chosen over **kwargs expansion to avoid
        mypy arg-type errors with complex types like list[str] in argv.
        """
        invocation = KubectlInvocation.from_command(
            ["kubectl", "get", "pods", "-n", "monitoring", "-o", "json"],
            timeout_seconds=30,
            run_id="run-shape-test",
        )
        invocation.failed = False
        invocation.returncode = 0
        invocation.elapsed_seconds = 1.5
        invocation.stdout_bytes = 4096
        invocation.stderr_bytes = 0

        writer = StringIO()
        self._call_with_capture(
            invocation,
            "INFO",
            "kubectl completed successfully",
            writer,
        )

        output = writer.getvalue()
        lines = [line for line in output.splitlines() if line.strip()]
        assert len(lines) == 1, f"Expected 1 JSONL line, got {len(lines)}"

        payload = json.loads(lines[0])

        # Top-level fields from emit_structured_log contract
        assert "timestamp" in payload
        assert "component" in payload
        assert payload["component"] == "kubectl-invocation"
        assert "message" in payload
        assert "severity" in payload
        assert payload["severity"] == "INFO"
        assert "run_label" in payload

        # Fields from to_log_dict() via metadata= parameter
        assert payload["event"] == "kubectl_invocation"
        assert payload["failed"] is False
        assert payload["returncode"] == 0
        assert payload["elapsed_seconds"] == 1.5
        assert payload["stdout_bytes"] == 4096
        assert payload["stderr_bytes"] == 0
        assert payload["namespace"] == "monitoring"
        assert payload["output_format"] == "json"
        assert payload["run_id"] == "run-shape-test"
        assert "argv" in payload
        assert payload["argv"] == ["kubectl", "get", "pods", "-n", "monitoring", "-o", "json"]
