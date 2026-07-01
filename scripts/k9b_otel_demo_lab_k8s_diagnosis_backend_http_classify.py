"""Backend HTTP failure classification for OTel demo lab.

This module extracts failure classification logic from
k9b_otel_demo_lab_k8s_diagnosis_backend_http.py.

Classification rules:
- curl_rc=52, http_code=0 -> backend empty reply / handler crashed
- curl_rc!=0 with DNS/connect failure -> transport_error
- HTTP non-2xx -> http_error
- HTTP 2xx with invalid JSON -> invalid_json
- HTTP 2xx with skipped=True, eligible=False -> loop_not_eligible (budget_exhausted)
"""

from __future__ import annotations

from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
    FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
)
from scripts.lab_common.provider_curl_helpers import CurlResult


def classify_backend_fetch_failure(
    curl_result: CurlResult,
) -> tuple[str, str]:
    """Classify a backend incident fetch failure.

    Args:
        curl_result: The curl result from fetch_backend_incident_detail_result

    Returns:
        Tuple of (error_class, error_detail)
    """
    # Case: curl was not executed (curl_rc=None due to exec timeout)
    if curl_result.curl_rc is None:
        return (
            FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            f"Transport error: curl not executed, exec timeout or exception. stderr={curl_result.stderr[:100]!r}",
        )

    # Case: Transport error (http_code=0 or nonzero curl_rc)
    if curl_result.http_code == 0 or curl_result.curl_rc != 0:
        # Classify specific curl_rc values for better diagnostics
        if curl_result.curl_rc == 6:
            error_detail = f"Transport error: backend DNS resolution failure (curl_rc=6), http_code={curl_result.http_code}"
        elif curl_result.curl_rc == 7:
            error_detail = f"Transport error: backend endpoint/connect failure (curl_rc=7), http_code={curl_result.http_code}"
        elif curl_result.curl_rc == 28:
            error_detail = f"Transport error: backend timeout (curl_rc=28), http_code={curl_result.http_code}"
        else:
            error_detail = f"Transport error: curl_rc={curl_result.curl_rc}, http_code={curl_result.http_code}"

        return (FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR, error_detail)

    # Case: HTTP 404 not found
    if curl_result.http_code == 404:
        return (
            FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            "Incident not found: HTTP 404",
        )

    # Case: Other non-2xx HTTP errors
    if curl_result.http_code < 200 or curl_result.http_code >= 300:
        return (
            FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
            f"HTTP error: {curl_result.http_code}",
        )

    # Case: Success (should not reach here for failures)
    return (
        FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
        "Unknown fetch failure state",
    )


def classify_targeted_invocation_failure(
    curl_result: CurlResult,
    response_data: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Classify a targeted invocation failure with precise reason.

    This function provides precise failure classification for P4c failures:
    - curl_rc=52 with http_code=0 indicates backend empty reply / handler crashed
    - budget_exhausted responses are classified as loop_not_eligible
    - Other transport failures are classified as transport_error

    Args:
        curl_result: The curl result from invoke_targeted_automatic_diagnosis_loop
        response_data: Parsed JSON response if available

    Returns:
        Tuple of (error_class, error_detail)
    """
    # Case A: curl_rc=52, http_code=0 -> backend empty reply / handler crashed
    # curl_rc=52 means "Empty reply from server" - the backend handler crashed
    # or returned no data at all
    if curl_result.curl_rc == 52 and curl_result.http_code == 0:
        return (
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
            (
                "Backend handler crashed or returned empty reply (curl_rc=52, http_code=0). "
                f"stderr: {curl_result.stderr[:200]!r}. "
                "Check backend logs for exception during one-pass handling."
            ),
        )

    # Case B: Transport failures
    if curl_result.curl_rc is not None and curl_result.curl_rc != 0:
        if curl_result.curl_rc == 6:
            return (
                FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
                f"Transport error: backend DNS resolution failure (curl_rc=6), http_code={curl_result.http_code}",
            )
        elif curl_result.curl_rc == 7:
            return (
                FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
                f"Transport error: backend endpoint/connect failure (curl_rc=7), http_code={curl_result.http_code}",
            )
        elif curl_result.curl_rc == 28:
            return (
                FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
                f"Transport error: backend timeout (curl_rc=28), http_code={curl_result.http_code}",
            )
        else:
            return (
                FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
                f"Transport error: curl_rc={curl_result.curl_rc}, http_code={curl_result.http_code}",
            )

    # Case C: HTTP non-2xx
    if curl_result.http_code < 200 or curl_result.http_code >= 300:
        return (
            FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            f"HTTP {curl_result.http_code} error from backend",
        )

    # Case D: HTTP 2xx but invalid JSON
    if response_data is None:
        # JSON parse already failed if we got here
        return (
            FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            "HTTP 200 but invalid JSON response",
        )

    # Case E: Check for structured skip/not eligible (budget_exhausted)
    # These are expected runtime states, not errors
    if isinstance(response_data, dict):
        skipped = response_data.get("skipped", False)
        eligible = response_data.get("eligible", True)
        eligibility_reason = response_data.get("eligibility_reason", "")

        if skipped and not eligible:
            # This is a structured "not eligible" response, not an error
            # Classify as loop_not_eligible for clear semantics
            return (
                FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
                (
                    f"Loop not eligible: eligibility_reason={eligibility_reason!r}. "
                    f"skipped={skipped}, eligible={eligible}. "
                    f"skip_reason: {response_data.get('skip_reason', 'N/A')!r}"
                ),
            )

    # Case F: Unknown error
    return (
        FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
        f"Unknown invocation error: curl_rc={curl_result.curl_rc}, http_code={curl_result.http_code}",
    )


__all__ = [
    "classify_backend_fetch_failure",
    "classify_targeted_invocation_failure",
]
