"""Golden-case evidence provider.

This module provides the GoldenCaseEvidenceProvider class that reads evidence
files from a golden-case bundle.
"""

from __future__ import annotations

import re
from pathlib import Path

from .golden_case_providers_constants import _READINESS_PROBE_PATTERNS

__all__ = ["GoldenCaseEvidenceProvider"]


class GoldenCaseEvidenceProvider:
    """Provides evidence from a golden-case bundle.

    This class reads evidence files from a golden-case bundle and serves
    them to fake handlers when they need to return context-specific output.

    Design constraints:
    - Read-only from the bundle
    - No mutation
    - Deterministic based on bundle contents
    """

    def __init__(self, case_dir: Path) -> None:
        """Initialize with golden-case bundle directory.

        Args:
            case_dir: Path to the golden-case bundle directory
        """
        self.case_dir = case_dir
        self._evidence_cache: dict[str, str] = {}
        self._load_evidence()

    def _load_evidence(self) -> None:
        """Load all evidence files from the bundle."""
        for subdir in ["incident", "baseline", "recovery-or-final"]:
            subdir_path = self.case_dir / subdir
            if subdir_path.exists():
                for file_path in subdir_path.iterdir():
                    if file_path.is_file():
                        rel_key = f"{subdir}/{file_path.name}"
                        try:
                            self._evidence_cache[rel_key] = file_path.read_text(encoding="utf-8")
                        except Exception:
                            pass  # Skip unreadable files

    def get_evidence(self, relative_path: str) -> str | None:
        """Get evidence content by relative path.

        Args:
            relative_path: Relative path within the bundle (e.g., "incident/pods.txt")

        Returns:
            File content as string, or None if not found
        """
        return self._evidence_cache.get(relative_path)

    def get_all_evidence(self) -> dict[str, str]:
        """Get all loaded evidence as a dict.

        Returns:
            Dict mapping relative paths to content
        """
        return dict(self._evidence_cache)

    def has_evidence(self, relative_path: str) -> bool:
        """Check if evidence file exists in bundle.

        Args:
            relative_path: Relative path within the bundle

        Returns:
            True if evidence exists
        """
        return relative_path in self._evidence_cache

    def find_pattern_in_evidence(self, pattern: re.Pattern[str]) -> list[str]:
        """Search all evidence for a pattern.

        Args:
            pattern: Compiled regex pattern to search for

        Returns:
            List of matching file paths
        """
        matches: list[str] = []
        for rel_path, content in self._evidence_cache.items():
            if pattern.search(content):
                matches.append(rel_path)
        return matches

    def extract_findings(self) -> dict[str, bool]:
        """Extract key findings from evidence.

        Returns:
            Dict of finding names to boolean values
        """
        all_text = "\n".join(self._evidence_cache.values())

        findings: dict[str, bool] = {
            "pod_running": False,
            "pod_not_ready": False,
            "readiness_probe_failure_evidence": False,
            "unhealthy_events": False,
            "container_running": False,
            "container_ready": False,
        }

        # Check for Running pod with NotReady
        if re.search(r"cnpg-lab-failing-app.*Running", all_text):
            findings["pod_running"] = True

        if re.search(r"cnpg-lab-failing-app.*0/1", all_text):
            findings["pod_not_ready"] = True

        # Check for readiness probe failure evidence
        for pattern in _READINESS_PROBE_PATTERNS:
            if pattern.search(all_text):
                findings["readiness_probe_failure_evidence"] = True
                break

        # Check for Unhealthy events
        if re.search(r"Warning.*Unhealthy", all_text):
            findings["unhealthy_events"] = True

        # Check for container running
        if re.search(r"cnpg-lab-failing-app.*Running.*0/1", all_text):
            findings["container_running"] = True
            findings["container_ready"] = False

        return findings
