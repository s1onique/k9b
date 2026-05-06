"""Adapter interface and registry for external analysis tools."""

from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ..security.subprocess_helpers import (
    sanitize_subprocess_error,
)
from .artifact import ExternalAnalysisArtifact
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings


class ExternalAnalysisExecutionError(RuntimeError):
    """Base exception for external analysis adapter failures."""
    pass


# Subprocess timeout for external tool execution (120s)
EXTERNAL_ANALYSIS_TIMEOUT_SECONDS = 120

# Allowed command families for external analysis adapters (REM-S3)
# These are the only permitted command binaries that may be configured
# and executed as external analysis tools.
_ALLOWED_COMMAND_FAMILIES = frozenset((
    # k8sGPT - Kubernetes diagnostics tool
    "k8sgpt",
    # llama.cpp family - Local LLM inference
    "llamacpp",
    "llama-cli",
    "llama.cpp",
))

# Blocked command families - shell interpreters, scripting languages,
# and network tools that should never be executed as external analysis commands.
_BLOCKED_COMMAND_FAMILIES = frozenset((
    # Shell interpreters
    "sh", "bash", "zsh", "fish", "dash", "ash", "ksh", "csh", "tcsh",
    # Scripting language interpreters
    "python", "python3", "python2", "perl", "ruby", "node", "php", "lua",
    # Network tools
    "curl", "wget", "nc", "netcat", "socat", "ncat", "openssl",
    # Container/remote execution
    "docker", "podman", "kubectl", "helm",
    # Remote access
    "ssh", "scp", "rsync", "ftp",
))

# Shell metacharacters that must not appear in command[0]
# These patterns indicate potential shell injection or misuse.
_SHELL_METACHAR_PATTERN = re.compile(r"[;|&$`<>\n\r]")


def _validate_command_for_execution(command: Sequence[str]) -> None:
    """Validate a command before execution.

    Args:
        command: The command argv to validate.

    Raises:
        ExternalAnalysisExecutionError: If the command is invalid or disallowed.
    """
    # Non-empty check
    if not command:
        raise ExternalAnalysisExecutionError(
            "Cannot execute empty command"
        )

    # Must be a list/tuple of strings (not a string)
    if not isinstance(command, (list, tuple)):
        raise ExternalAnalysisExecutionError(
            "Command must be a list of strings"
        )

    # First element is the command name
    cmd0 = command[0]
    if not isinstance(cmd0, str):
        raise ExternalAnalysisExecutionError(
            "Command name must be a string"
        )

    # Check for shell metacharacters in command[0]
    if _SHELL_METACHAR_PATTERN.search(cmd0):
        raise ExternalAnalysisExecutionError(
            "Command contains unsupported characters"
        )

    # Extract the base command name (strip path components)
    cmd_base = cmd0.split("/")[-1].lower()

    # Check against blocked families
    if cmd_base in _BLOCKED_COMMAND_FAMILIES:
        raise ExternalAnalysisExecutionError(
            f"Command '{cmd_base}' is not allowed for external analysis"
        )

    # Check against allowed families (if the set is not empty)
    # Note: Empty _ALLOWED_COMMAND_FAMILIES means "allow all" - not the case here
    if cmd_base not in _ALLOWED_COMMAND_FAMILIES:
        raise ExternalAnalysisExecutionError(
            f"Command '{cmd_base}' is not a recognized external analysis tool"
        )


class TimeoutError(Exception):
    """Raised when a request times out."""
    pass


class AuthError(Exception):
    """Raised when authentication fails (401/403)."""
    pass


class InvalidResponseError(Exception):
    """Raised when the response is malformed or invalid."""
    pass


class UpstreamError(Exception):
    """Raised when upstream service returns an error (5xx) or is unreachable."""
    pass


@dataclass(frozen=True)
class ExternalAnalysisRequest:
    run_id: str
    cluster_label: str
    source_artifact: str | None
    metadata: Mapping[str, object] | None = None


class ExternalAnalysisAdapter(ABC):
    name: str

    def __init__(self, command: Sequence[str] | None = None) -> None:
        self._command = tuple(command) if command else None

    @abstractmethod
    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        ...


AdapterBuilder = Callable[[ExternalAnalysisAdapterConfig, ExternalAnalysisSettings], ExternalAnalysisAdapter | None]
_ADAPTER_BUILDERS: dict[str, AdapterBuilder] = {}


def register_external_analysis_adapter(name: str) -> Callable[[AdapterBuilder], AdapterBuilder]:
    def decorator(builder: AdapterBuilder) -> AdapterBuilder:
        _ADAPTER_BUILDERS[name.lower()] = builder
        return builder

    return decorator


def build_external_analysis_adapters(
    configs: Sequence[ExternalAnalysisAdapterConfig],
    settings: ExternalAnalysisSettings | None = None,
) -> dict[str, ExternalAnalysisAdapter]:
    if settings is None:
        settings = ExternalAnalysisSettings()
    adapters: dict[str, ExternalAnalysisAdapter] = {}
    for entry in configs:
        if not entry.enabled:
            continue
        builder = _ADAPTER_BUILDERS.get(entry.name.lower())
        if not builder:
            continue
        adapter = builder(entry, settings)
        if adapter:
            adapters[adapter.name] = adapter
    return adapters


def _run_subprocess(command: Sequence[str]) -> str:
    # Validate command before execution (REM-S3)
    _validate_command_for_execution(command)
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=True,
            timeout=EXTERNAL_ANALYSIS_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        # Include only safe truncated command summary (first element only)
        # Do not leak full command args which may contain sensitive data
        cmd_summary = command[0] if command else "unknown"
        raise ExternalAnalysisExecutionError(
            f"Command {cmd_summary} timed out after "
            f"{EXTERNAL_ANALYSIS_TIMEOUT_SECONDS}s. External tool may be unresponsive.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        # Use sanitize_subprocess_error for safe error message construction
        stderr = exc.stderr if exc.stderr else exc.stdout
        cmd_summary = command[0] if command else "unknown"
        message = sanitize_subprocess_error(
            f"Command {cmd_summary} exited {exc.returncode}",
            stderr,
            max_length=1000,
        )
        raise ExternalAnalysisExecutionError(message)
    except FileNotFoundError as exc:
        raise ExternalAnalysisExecutionError(f"Command not found: {exc}")
