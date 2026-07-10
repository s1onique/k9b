"""Common utilities for the incident lifecycle boundary verifier."""

from __future__ import annotations

from pathlib import Path

# Default paths for verification
DOMAIN_MODULE = Path("src/k8s_diag_agent/domain/incident_lifecycle.py")
DOMAIN_ADAPTER_MODULE = Path("src/k8s_diag_agent/collect/incident_lifecycle_domain_adapter.py")
TRANSITIONS_MODULE = Path("src/k8s_diag_agent/collect/incident_lifecycle_transitions.py")
EVIDENCE_MODULE = Path("src/k8s_diag_agent/collect/incident_evidence.py")
EVIDENCE_LLM_SAFE_MODULE = Path("src/k8s_diag_agent/collect/incident_evidence_llm_safe.py")
REPO_ROOT = Path("src")


def iter_python_files(root: Path) -> list[Path]:
    """Iterate over all Python files in a directory, excluding virtual envs."""
    return [
        path
        for path in root.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    ]


def format_error(filepath: str, lineno: int, message: str) -> str:
    """Format an error message with file path and line number."""
    return f"{filepath}:{lineno}: {message}"


def read_source_file(filepath: str) -> tuple[str, list[str]]:
    """Read a source file and return (content, error_list).

    Returns an empty error list on success, or a single error message on failure.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        return source, []
    except OSError as e:
        return "", [f"Cannot read {filepath}: {e}"]
