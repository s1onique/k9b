"""Shared test cases for provider health envelope contract.

APF guard: known successful curl wrapper metadata is accepted transport envelope metadata,
not provider-health JSON contamination. Do not flip this boundary without changing
the contract table and doctrine doc.

This module provides an executable contract matrix for provider-health envelope behavior.
It defines the canonical cases for wire-format validation of provider preflight responses.

Wire-format layers:
1. Transport envelope extraction: Known successful curl metadata is accepted as transport.
2. JSON body classification: Valid JSON body passes to semantic evaluation.
3. Semantic provider-health evaluation: Only proceeds after wire-format passes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class EnvelopeTestCase:
    """A single test case for provider health envelope validation.

    Attributes:
        description: Human-readable description of the test case
        body: Raw body string to test
        expected_result: 'pass' if wire-format passes, 'contamination', 'invalid_json', or 'empty'
        notes: Additional context about why this case has this expected result
    """

    description: str
    body: str
    expected_result: Literal["pass", "contamination", "invalid_json", "empty"]
    notes: str = ""


# =============================================================================
# ACCEPTED cases: wire-format passes, semantic evaluation proceeds
# =============================================================================

ACCEPTED_CASES: list[EnvelopeTestCase] = [
    EnvelopeTestCase(
        description="Clean JSON only",
        body='{"healthy": true}',
        expected_result="pass",
        notes="Exactly one clean JSON document - no prefix/suffix",
    ),
    EnvelopeTestCase(
        description="Leading whitespace + clean JSON",
        body='  \n{"healthy": true}\n  ',
        expected_result="pass",
        notes="Leading whitespace before JSON is allowed",
    ),
    EnvelopeTestCase(
        description="JSON + CURL_EXIT=0 + HTTP_CODE=200",
        body='{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200',
        expected_result="pass",
        notes="Known successful curl envelope is ACCEPTED as transport metadata",
    ),
    EnvelopeTestCase(
        description="JSON + STDERR_BLOCK + CURL_EXIT=0 + HTTP_CODE=200",
        body='{"healthy": true}\nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200',
        expected_result="pass",
        notes="Known successful curl envelope with STDERR_BLOCK is ACCEPTED",
    ),
    EnvelopeTestCase(
        description="JSON + STDERR_BLOCK + debug noise + CURL_EXIT=0 + HTTP_CODE=200",
        body='{"healthy": true}\nSTDERR_BLOCK\ndebug noise from curl wrapper\nCURL_EXIT=0\nHTTP_CODE=200',
        expected_result="pass",
        notes="Arbitrary stderr/debug lines inside known envelope are accepted",
    ),
    EnvelopeTestCase(
        description="Leading whitespace + JSON + curl envelope",
        body='\n  {"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200\n',
        expected_result="pass",
        notes="Leading whitespace + known curl envelope is accepted",
    ),
]

# =============================================================================
# REJECTED cases: wire-format fails with specific classification
# =============================================================================

REJECTED_CASES: list[EnvelopeTestCase] = [
    EnvelopeTestCase(
        description="Unknown non-whitespace suffix",
        body='{"healthy": true}\nUNKNOWN_METADATA=value',
        expected_result="contamination",
        notes="Unknown suffix after JSON is contamination",
    ),
    EnvelopeTestCase(
        description="Second JSON document (concatenated)",
        body='{"first": true}{"second": true}',
        expected_result="invalid_json",
        notes="Adjacent/concatenated JSON documents are invalid, not contamination",
    ),
    EnvelopeTestCase(
        description="Unknown prefix before JSON",
        body='DEBUG\n{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200',
        expected_result="contamination",
        notes="Only STDOUT_BLOCK/whitespace may appear before JSON",
    ),
    EnvelopeTestCase(
        description="Non-whitespace prefix before JSON",
        body='INFO starting log\n{"healthy": true}',
        expected_result="contamination",
        notes="Non-whitespace prefix before JSON is contamination",
    ),
    EnvelopeTestCase(
        description="Malformed curl envelope - wrong order",
        body='{"healthy": true}\nHTTP_CODE=200\nCURL_EXIT=0',
        expected_result="contamination",
        notes="Curl metadata in wrong order is not a valid envelope",
    ),
    EnvelopeTestCase(
        description="CURL_EXIT=1 (failed curl)",
        body='{"healthy": true}\nCURL_EXIT=1\nHTTP_CODE=200',
        expected_result="contamination",
        notes="Failed curl (non-zero exit) is not accepted envelope",
    ),
    EnvelopeTestCase(
        description="HTTP_CODE=500 (failed HTTP)",
        body='{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=500',
        expected_result="contamination",
        notes="Failed HTTP (non-200 code) is not accepted envelope",
    ),
    EnvelopeTestCase(
        description="Curl envelope with extra data after",
        body='{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200\nextra',
        expected_result="contamination",
        notes="Known envelope followed by unknown data is contamination",
    ),
    EnvelopeTestCase(
        description="STDERR_BLOCK envelope with wrong order",
        body='{"healthy": true}\nSTDERR_BLOCK\nHTTP_CODE=200\nCURL_EXIT=0',
        expected_result="contamination",
        notes="STDERR_BLOCK envelope with wrong metadata order is invalid",
    ),
    EnvelopeTestCase(
        description="Empty body",
        body='',
        expected_result="empty",
        notes="Empty/whitespace-only body fails as empty",
    ),
    EnvelopeTestCase(
        description="Whitespace-only body",
        body='   \n\t  ',
        expected_result="empty",
        notes="Whitespace-only body fails as empty",
    ),
]


def run_envelope_cases(
    classify_fn: Callable[[str], tuple[str | None, object | None, str]],
) -> list[tuple[EnvelopeTestCase, bool, str]]:
    """Run envelope test cases against a classifier function.

    Args:
        classify_fn: Function that takes a body string and returns
            (failure_class, payload, detail_message)

    Returns:
        List of (case, passed, message) tuples
    """
    results: list[tuple[EnvelopeTestCase, bool, str]] = []

    for case in ACCEPTED_CASES + REJECTED_CASES:
        failure_class, _, _ = classify_fn(case.body)

        if case.expected_result == "pass":
            passed = failure_class is None
            msg = f"Expected pass, got {failure_class}" if not passed else "OK"
        elif case.expected_result == "contamination":
            passed = failure_class == "provider_health_output_contaminated"
            msg = f"Expected contamination, got {failure_class}" if not passed else "OK"
        elif case.expected_result == "invalid_json":
            passed = failure_class == "provider_health_invalid_json"
            msg = f"Expected invalid_json, got {failure_class}" if not passed else "OK"
        elif case.expected_result == "empty":
            passed = failure_class == "provider_health_empty_body"
            msg = f"Expected empty, got {failure_class}" if not passed else "OK"
        else:
            passed = False
            msg = f"Unknown expected_result: {case.expected_result}"

        results.append((case, passed, msg))

    return results
