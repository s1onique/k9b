"""LLM-safe review-boundary verifier.

Scans the LLM-boundary modules (case-file, review-packet, LLM diagnosis)
for unsafe-access patterns that would let raw artifact content cross
the LLM boundary: ``LocalArtifactPath``, ``ExternalStorageRef``,
``artifact.storage_ref`` direct access, and absolute ``artifact_path``
literals.
"""

from __future__ import annotations

from pathlib import Path

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    LLM_REVIEW_MODULES,
    UNSAFE_PATTERNS,
)


def check_llm_review_unsafe_access(repo_root: Path) -> list[str]:
    """Scan LLM/review modules for unsafe access patterns."""
    errors: list[str] = []

    for module_path in LLM_REVIEW_MODULES:
        full_path = repo_root / module_path
        if not full_path.exists():
            continue

        try:
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue

        for pattern, description in UNSAFE_PATTERNS:
            if pattern.search(source):
                for i, line in enumerate(source.splitlines(), 1):
                    if pattern.search(line):
                        errors.append(f"{module_path}:{i}: Detected unsafe pattern: {description}")

    return errors