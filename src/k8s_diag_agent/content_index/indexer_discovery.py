"""Content indexer source discovery.

This module handles discovery of source files from configured roots.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import logging
from pathlib import Path

from .indexer_contract import ContentIndexRoots, IndexerConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Source Discovery Patterns
# =============================================================================


# File patterns to index by path kind
INDEX_PATTERNS: dict[str, list[str]] = {
    "incident_store": [
        "**/k9b-incidents.json",
        "**/k9b-incident-detail.json",
        "**/incident-evidence-links.json",
    ],
    "artifact": [
        "**/review-packet*.json",
        "**/automatic-diagnosis-review*.json",
        "**/snapshot*.json",
    ],
    "lab": [
        "**/lab-result.json",
    ],
    "trace_capture": [
        "**/trace-summary.json",
    ],
    "perf_baseline": [
        "**/backend-api-baseline-summary.json",
    ],
}


def discover_sources(
    roots: ContentIndexRoots,
    config: IndexerConfig | None = None,
) -> list[tuple[Path, str, str]]:
    """Discover source files from roots.

    Args:
        roots: Content index roots.
        config: Indexer configuration.

    Returns:
        List of (absolute_path, relative_path, path_kind) tuples.
    """
    if config is None:
        config = IndexerConfig()

    discovered: list[tuple[Path, str, str]] = []
    active_roots = roots.get_active_roots()

    for path_kind, root_path in active_roots:
        if not root_path.exists():
            logger.warning(f"Root path does not exist: {root_path}")
            continue

        patterns = INDEX_PATTERNS.get(path_kind, [])

        for pattern in patterns:
            # Find matching files
            for match in root_path.rglob(pattern.replace("**/", "")):
                if not match.is_file():
                    continue

                # Check file size
                try:
                    size_mb = match.stat().st_size / (1024 * 1024)
                    if size_mb > config.max_file_size_mb:
                        logger.warning(
                            f"Skipping large file ({size_mb:.1f}MB): {match}"
                        )
                        continue
                except OSError:
                    continue

                # Compute relative path
                try:
                    relative_path = match.relative_to(root_path)
                except ValueError:
                    # File is outside root
                    continue

                discovered.append((match, str(relative_path), path_kind))

    return discovered


def make_content_id(path_kind: str, relative_path: str) -> str:
    """Create a content ID from path kind and relative path.

    Args:
        path_kind: Source path kind.
        relative_path: Relative path from root.

    Returns:
        Content ID string.
    """
    # Normalize path separators
    normalized = relative_path.replace("/", "-").replace("\\", "-")
    return f"{path_kind}:{normalized}"
