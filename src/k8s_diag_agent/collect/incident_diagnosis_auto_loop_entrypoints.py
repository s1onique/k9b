"""Single-incident entrypoints for automatic diagnosis loop.

This module provides the public convenience API for single-incident
automatic diagnosis evidence collection.

The main entrypoint `collect_automatic_diagnosis_evidence()` was extracted
from `incident_diagnosis_auto_loop.py` to keep that module under the
LLM-friendly size limit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from .incident_diagnosis_auto_loop_evidence_collection import run_automatic_diagnosis_loop_evidence_collection
from .incident_diagnosis_auto_loop_models import AutoLoopIncidentResult

if TYPE_CHECKING:
    pass


__all__ = [
    "collect_automatic_diagnosis_evidence",
    "_positive_int",
]


def _positive_int(value: object, default: int) -> int:
    """Coerce a JSON-decoded value to a positive integer.

    JSON allows booleans (true/false), numbers (int/float), strings, null,
    arrays, and objects. This function handles the edge cases that json.loads()
    produces but that may not be semantically valid for budget fields.

    Args:
        value: The JSON-decoded value to coerce
        default: Default value if coercion fails

    Returns:
        Positive integer, or default if invalid
    """
    if isinstance(value, bool):
        # JSON booleans are distinct from integers
        return default
    if not isinstance(value, int):
        # Floats, strings, None, lists, dicts are not valid budget values
        return default
    # Valid integer - ensure positive
    return value if value > 0 else default


def collect_automatic_diagnosis_evidence(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
) -> AutoLoopIncidentResult:
    """Collect automatic diagnosis evidence for a single incident.

    Convenience wrapper for single-incident collection.
    Respects the K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED setting.

    Args:
        incident_id: The incident ID to collect evidence for
        external_analysis_dir: Path to external-analysis directory
        config: Optional custom configuration. If None, uses defaults.
            For lab scenarios requiring multiple passes (e.g., P4c with min_required_passes=2),
            pass a config with max_passes_per_incident >= min_required_passes.

    Returns:
        AutoLoopIncidentResult with processing outcome
    """
    from .incident_diagnosis_auto_loop import is_automatic_diagnosis_loop_enabled

    if not is_automatic_diagnosis_loop_enabled():
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason="automatic_collector_disabled",
            skipped=True,
            skip_reason="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED is not set to true",
        )

    result = run_automatic_diagnosis_loop_evidence_collection(
        external_analysis_dir=external_analysis_dir,
        config=config,
        incident_ids=[incident_id],
    )

    if result.incident_results:
        return AutoLoopIncidentResult(
            **result.incident_results[0]
        )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=False,
        eligibility_reason="no_incidents_processed",
        skipped=True,
        skip_reason="No incidents were processed",
    )
