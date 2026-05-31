"""Review metadata extraction and status helpers for runs-list.

This module contains the review metadata extraction functions using ijson streaming
and review status derivation logic.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

# Use the original logger name for compatibility
import logging
from pathlib import Path

import ijson

logger = logging.getLogger("k8s_diag_agent.ui.api")


def _extract_review_metadata_streaming(review_path: Path) -> dict[str, object] | None:
    """Extract only the required fields from review artifact using ijson streaming.

    This is a fast-path for extracting run_id, timestamp, run_label, and cluster_count
    without loading the entire JSON file into memory.

    Returns:
        Dictionary with extracted fields, or None if extraction fails.
    """
    try:
        with open(review_path, "rb") as f:
            # Use ijson to stream-parse only the fields we need
            parser = ijson.kvitems(f, "")
            extracted: dict[str, object] = {}
            for key, value in parser:
                if key in ("run_id", "timestamp", "run_label", "cluster_count"):
                    extracted[key] = value
                # Early exit once we have all required fields
                if len(extracted) >= 4:
                    break

            # Validate we got the required fields
            if "run_id" not in extracted or "timestamp" not in extracted:
                return None
            if not isinstance(extracted["run_id"], str):
                return None
            if not isinstance(extracted["timestamp"], str):
                return None

            return extracted
    except (OSError, UnicodeDecodeError, ValueError, ijson.common.IncompleteJSONError) as exc:
        # Note: catches ijson.common.IncompleteJSONError (malformed/incomplete JSON during streaming)
        logger.warning(
            "Failed to stream-parse review artifact: artifact=%s, error=%s",
            review_path.name,
            str(exc),
            exc_info=True,
        )
        return None


def _derive_review_status(execution_count: int, reviewed_count: int) -> str:
    """Derive review status from execution and reviewed counts.

    Returns one of:
    - "no-executions": run has no executed next checks
    - "unreviewed": has executions but none reviewed
    - "partially-reviewed": some executions reviewed, some not
    - "fully-reviewed": all executions reviewed
    """
    if execution_count == 0:
        return "no-executions"
    if reviewed_count == 0:
        return "unreviewed"
    if reviewed_count < execution_count:
        return "partially-reviewed"
    return "fully-reviewed"
