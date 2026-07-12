"""Unit tests for the authority run-summary accounting.

Covers the ACT-required per-run counters
(``backend_lookup_outcomes`` / ``eligibility_outcomes`` /
``lifecycle_write_outcomes`` / ``backend_found_then_incident_not_found``)
derived from per-incident result mappings.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01 (R1)
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_diagnosis_authority_run_summary import (
    AuthorityRunSummary,
    summarize_incident_results,
)


def test_backend_not_found_is_counted() -> None:
    results = [
        {
            "eligible": False,
            "eligibility_reason": "not_found",
            "skipped": True,
            "skip_reason": "incident_not_found",
        }
    ]
    summary = summarize_incident_results(results)
    assert summary.backend_lookup_outcomes == {"not_found": 1}
    assert summary.backend_found_then_incident_not_found == 0


def test_backend_lookup_failed_is_counted() -> None:
    results = [
        {
            "eligible": False,
            "eligibility_reason": "backend_incident_invalid_payload",
            "error": "synthetic",
        }
    ]
    summary = summarize_incident_results(results)
    assert summary.backend_lookup_outcomes == {"lookup_failed": 1}
    assert summary.backend_found_then_incident_not_found == 0


def test_eligible_processed_incident_is_applied() -> None:
    results = [
        {
            "eligible": True,
            "eligibility_reason": "active_incident_with_suggested_checks",
            "skipped": False,
            "error": None,
        }
    ]
    summary = summarize_incident_results(results)
    assert summary.backend_lookup_outcomes == {"found": 1}
    assert summary.eligibility_outcomes == {"eligible": 1}
    assert summary.lifecycle_write_outcomes == {"applied": 1}


def test_ineligible_incident_reason_is_keyed() -> None:
    results = [
        {
            "eligible": False,
            "eligibility_reason": "budget_exhausted",
            "skipped": True,
            "skip_reason": "not_eligible: budget_exhausted",
        }
    ]
    summary = summarize_incident_results(results)
    assert summary.eligibility_outcomes == {"budget_exhausted": 1}
    # A budget-exhausted incident is a backend-found incident (it was
    # resolved) but was not processed → lifecycle not applicable.
    assert summary.backend_lookup_outcomes == {"found": 1}
    assert summary.lifecycle_write_outcomes == {"not_applicable": 1}
    assert summary.backend_found_then_incident_not_found == 0


def test_lifecycle_start_and_completion_failures_are_distinguished() -> None:
    results = [
        {
            "eligible": True,
            "eligibility_reason": "active_incident_with_suggested_checks",
            "error": "diagnosis_lifecycle_start_failed: backend_url_not_configured",
        },
        {
            "eligible": True,
            "eligibility_reason": "active_incident_with_suggested_checks",
            "error": "diagnosis_lifecycle_completion_failed: backend_error",
        },
        {
            "eligible": True,
            "eligibility_reason": "active_incident_with_suggested_checks",
            "error": "Failed to build case file: KeyError; "
            "lifecycle_recording_error=backend_error; http_status=500",
        },
    ]
    summary = summarize_incident_results(results)
    assert summary.lifecycle_write_outcomes == {
        "start_failed": 1,
        "completion_failed": 1,
        "recording_failed": 1,
    }


def test_split_authority_regression_is_flagged() -> None:
    # The legacy defect: backend-found incident collapsed to
    # incident_not_found (eligibility_reason == "incident_not_found").
    results = [
        {
            "eligible": False,
            "eligibility_reason": "incident_not_found",
            "skipped": True,
            "skip_reason": "not_eligible: incident_not_found",
        }
    ]
    summary = summarize_incident_results(results)
    assert summary.backend_lookup_outcomes == {"found": 1}
    assert summary.backend_found_then_incident_not_found == 1


def test_to_dict_shape_has_required_fields() -> None:
    summary = AuthorityRunSummary()
    payload = summary.to_dict()
    assert set(payload.keys()) == {
        "backend_lookup_outcomes",
        "eligibility_outcomes",
        "lifecycle_write_outcomes",
        "backend_found_then_incident_not_found",
    }
    assert payload["backend_found_then_incident_not_found"] == 0


def test_mixed_run_aggregates_counts() -> None:
    results = [
        {"eligible": True, "eligibility_reason": "active", "error": None},
        {"eligible": True, "eligibility_reason": "active", "error": None},
        {
            "eligible": False,
            "eligibility_reason": "not_found",
            "skipped": True,
            "skip_reason": "incident_not_found",
        },
        {
            "eligible": False,
            "eligibility_reason": "backend_incident_unsupported_schema",
        },
    ]
    summary = summarize_incident_results(results)
    assert summary.backend_lookup_outcomes == {
        "found": 2,
        "not_found": 1,
        "lookup_failed": 1,
    }
    assert summary.eligibility_outcomes["eligible"] == 2
    assert summary.backend_found_then_incident_not_found == 0
