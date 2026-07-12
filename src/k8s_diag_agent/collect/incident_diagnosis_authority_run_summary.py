"""Authority run-summary accounting for the automatic-diagnosis loop.

This module derives the ACT-required per-run counters from the
per-incident results the batch loop already produces:

* ``backend_lookup_outcomes`` — how each incident's authority lookup
  resolved (``found`` / ``not_found`` / ``lookup_failed``).
* ``eligibility_outcomes`` — the eligibility decision keyed by reason
  (``eligible`` when the incident was eligible, otherwise the bounded
  ineligibility reason).
* ``lifecycle_write_outcomes`` — how the lifecycle write resolved
  (``applied`` / ``start_failed`` / ``completion_failed`` /
  ``recording_failed`` / ``not_applicable``).
* ``backend_found_then_incident_not_found`` — the split-authority
  regression counter: a backend-found incident that nonetheless
  produced an ``incident_not_found`` disposition. Post-fix this must
  stay ``0``; a non-zero value is a direct signal that the closed
  defect has reappeared.

The accounting is a pure fold over result mappings so it is fully
deterministic and testable without a running loop.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AuthorityRunSummary",
    "summarize_incident_results",
]


def _incr(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


@dataclass(slots=True)
class AuthorityRunSummary:
    """Bounded per-run accounting for the authority seam."""

    backend_lookup_outcomes: dict[str, int] = field(default_factory=dict)
    eligibility_outcomes: dict[str, int] = field(default_factory=dict)
    lifecycle_write_outcomes: dict[str, int] = field(default_factory=dict)
    backend_found_then_incident_not_found: int = 0

    def record(self, result: Mapping[str, Any]) -> None:
        """Fold a single per-incident result into the running counters."""
        eligibility_reason = str(result.get("eligibility_reason") or "")
        skip_reason = str(result.get("skip_reason") or "")
        error = str(result.get("error") or "")
        eligible = bool(result.get("eligible"))
        skipped = bool(result.get("skipped"))

        lookup = _classify_backend_lookup(eligibility_reason, skip_reason)
        _incr(self.backend_lookup_outcomes, lookup)

        _incr(
            self.eligibility_outcomes,
            "eligible" if eligible else (eligibility_reason or "unknown"),
        )

        _incr(
            self.lifecycle_write_outcomes,
            _classify_lifecycle_write(error, eligible=eligible, skipped=skipped),
        )

        # Split-authority regression: a backend-found incident must
        # never collapse to ``incident_not_found``.
        if lookup == "found" and (
            eligibility_reason == "incident_not_found"
            or "incident_not_found" in skip_reason
        ):
            self.backend_found_then_incident_not_found += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_lookup_outcomes": dict(self.backend_lookup_outcomes),
            "eligibility_outcomes": dict(self.eligibility_outcomes),
            "lifecycle_write_outcomes": dict(self.lifecycle_write_outcomes),
            "backend_found_then_incident_not_found": (
                self.backend_found_then_incident_not_found
            ),
        }


def _classify_backend_lookup(eligibility_reason: str, skip_reason: str) -> str:
    """Classify the authority lookup outcome for a per-incident result."""
    if eligibility_reason == "not_found" and "incident_not_found" in skip_reason:
        return "not_found"
    if eligibility_reason.startswith("backend_incident_"):
        return "lookup_failed"
    return "found"


def _classify_lifecycle_write(
    error: str,
    *,
    eligible: bool,
    skipped: bool,
) -> str:
    """Classify the lifecycle-write outcome from the result's error field."""
    if "diagnosis_lifecycle_start_failed" in error:
        return "start_failed"
    if "diagnosis_lifecycle_completion_failed" in error:
        return "completion_failed"
    if "lifecycle_recording_error" in error:
        return "recording_failed"
    if eligible and not skipped and not error:
        return "applied"
    return "not_applicable"


def summarize_incident_results(
    results: Iterable[Mapping[str, Any]],
) -> AuthorityRunSummary:
    """Fold per-incident result mappings into an :class:`AuthorityRunSummary`."""
    summary = AuthorityRunSummary()
    for result in results:
        summary.record(result)
    return summary
