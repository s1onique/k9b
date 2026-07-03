"""APF regression test for provider health envelope contract.

APF guard: known successful curl wrapper metadata is accepted transport envelope metadata,
not provider-health JSON contamination. Do not flip this boundary without changing
the contract table and doctrine doc.

This test explicitly documents the oscillation boundary and ensures the contract is
enforced. It uses the shared contract matrix from tests/contracts/provider_health_envelope_cases.py.
"""

from __future__ import annotations

import pytest

from tests.contracts.provider_health_envelope_cases import (
    ACCEPTED_CASES,
    REJECTED_CASES,
    EnvelopeTestCase,
)


class TestProviderHealthEnvelopeApfContract:
    """APF regression tests for provider health envelope contract.

    These tests guard against doctrine oscillation where the curl-envelope boundary
    keeps flipping between "curl metadata is accepted" and "curl metadata is contamination".
    """

    @pytest.mark.parametrize("case", ACCEPTED_CASES, ids=lambda c: c.description)
    def test_accepted_cases_pass_wire_format(self, case: EnvelopeTestCase) -> None:
        """Accepted cases must pass wire-format validation (no contamination error)."""
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        failure_class, _, _ = _classify_provider_health_body(case.body)

        assert failure_class is None, (
            f"Case '{case.description}' should pass wire-format validation.\n"
            f"  Body: {case.body!r}\n"
            f"  Expected: wire-format pass\n"
            f"  Got: {failure_class}\n"
            f"  Notes: {case.notes}"
        )

    @pytest.mark.parametrize("case", REJECTED_CASES, ids=lambda c: c.description)
    def test_rejected_cases_fail_wire_format(
        self, case: EnvelopeTestCase
    ) -> None:
        """Rejected cases must fail wire-format validation with correct classification."""
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        failure_class, _, _ = _classify_provider_health_body(case.body)

        if case.expected_result == "contamination":
            assert failure_class == "provider_health_output_contaminated", (
                f"Case '{case.description}' should fail as contamination.\n"
                f"  Body: {case.body!r}\n"
                f"  Expected: provider_health_output_contaminated\n"
                f"  Got: {failure_class}\n"
                f"  Notes: {case.notes}"
            )
        elif case.expected_result == "invalid_json":
            assert failure_class == "provider_health_invalid_json", (
                f"Case '{case.description}' should fail as invalid_json.\n"
                f"  Body: {case.body!r}\n"
                f"  Expected: provider_health_invalid_json\n"
                f"  Got: {failure_class}\n"
                f"  Notes: {case.notes}"
            )
        elif case.expected_result == "empty":
            assert failure_class == "provider_health_empty_body", (
                f"Case '{case.description}' should fail as empty.\n"
                f"  Body: {case.body!r}\n"
                f"  Expected: provider_health_empty_body\n"
                f"  Got: {failure_class}\n"
                f"  Notes: {case.notes}"
            )

    def test_known_curl_envelope_accepted_contract(self) -> None:
        """Explicit contract test: CURL_EXIT=0 + HTTP_CODE=200 is accepted envelope.

        This is the canonical case that was oscillating in CI. Known successful
        curl wrapper metadata is transport envelope, not JSON contamination.
        """
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200'
        failure_class, payload, _ = _classify_provider_health_body(body)

        assert failure_class is None, (
            "Known successful curl envelope (CURL_EXIT=0, HTTP_CODE=200) must be ACCEPTED.\n"
            f"  Body: {body!r}\n"
            f"  Got failure_class: {failure_class}"
        )
        assert payload is not None, "Payload should be extracted from JSON body"
        assert isinstance(payload, dict), "Payload should be parsed JSON"
        assert payload.get("healthy") is True

    def test_stderr_block_with_noise_accepted_contract(self) -> None:
        """Explicit contract test: STDERR_BLOCK with debug noise is accepted envelope.

        Live-lab output may include debug noise from the curl wrapper inside the
        STDERR_BLOCK envelope. This is still valid transport metadata.
        """
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = (
            '{"healthy": true}\n'
            'STDERR_BLOCK\n'
            'debug noise from curl wrapper\n'
            'CURL_EXIT=0\n'
            'HTTP_CODE=200\n'
        )
        failure_class, payload, _ = _classify_provider_health_body(body)

        assert failure_class is None, (
            "STDERR_BLOCK with debug noise must be ACCEPTED.\n"
            f"  Body: {body!r}\n"
            f"  Got failure_class: {failure_class}"
        )
        assert payload is not None
        assert isinstance(payload, dict)

    def test_failed_curl_not_accepted(self) -> None:
        """Explicit contract test: CURL_EXIT=1 is NOT accepted envelope.

        Failed curl (non-zero exit) is transport failure, not valid envelope.
        """
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = '{"healthy": true}\nCURL_EXIT=1\nHTTP_CODE=200'
        failure_class, _, _ = _classify_provider_health_body(body)

        assert failure_class == "provider_health_output_contaminated", (
            "Failed curl (CURL_EXIT=1) must be REJECTED as contamination.\n"
            f"  Body: {body!r}\n"
            f"  Got: {failure_class}"
        )

    def test_failed_http_not_accepted(self) -> None:
        """Explicit contract test: HTTP_CODE=500 is NOT accepted envelope.

        Failed HTTP (non-200 code) is not valid envelope.
        """
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=500'
        failure_class, _, _ = _classify_provider_health_body(body)

        assert failure_class == "provider_health_output_contaminated", (
            "Failed HTTP (HTTP_CODE=500) must be REJECTED as contamination.\n"
            f"  Body: {body!r}\n"
            f"  Got: {failure_class}"
        )

    def test_concatenated_json_still_invalid(self) -> None:
        """Explicit contract test: second JSON document is invalid, not contamination.

        Concatenated JSON documents are invalid JSON, not valid output with contamination.
        """
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = '{"first": true}{"second": true}'
        failure_class, _, _ = _classify_provider_health_body(body)

        assert failure_class == "provider_health_invalid_json", (
            "Concatenated JSON documents must be REJECTED as invalid_json.\n"
            f"  Body: {body!r}\n"
            f"  Got: {failure_class}"
        )


class TestContractMatrixCompleteness:
    """Verify the contract matrix covers the critical oscillation boundary cases."""

    def test_all_accepted_cases_start_with_valid_json(self) -> None:
        """All accepted cases must have valid JSON at the appropriate position.

        Some cases intentionally have non-JSON prefix (STDOUT_BLOCK) - these are
        handled by the raw-output classifier. This test checks cases where the
        body should start with valid JSON (possibly with whitespace).
        """
        import json

        for case in ACCEPTED_CASES:
            stripped = case.body.lstrip()
            
            # Skip cases where the body intentionally doesn't start with JSON
            # (e.g., STDOUT_BLOCK prefix - these are tested by the raw-output classifier)
            if stripped.startswith("STDOUT_BLOCK"):
                continue

            decoder = json.JSONDecoder()
            try:
                parsed, _ = decoder.raw_decode(stripped)
                assert isinstance(parsed, (dict, list)), (
                    f"Case '{case.description}' must have JSON body after whitespace.\n"
                    f"  Body: {case.body!r}"
                )
            except json.JSONDecodeError:
                pytest.fail(
                    f"Accepted case '{case.description}' must have valid JSON.\n"
                    f"  Body: {case.body!r}"
                )

    def test_known_envelope_patterns_are_accepted(self) -> None:
        """All known successful curl envelope patterns must be in ACCEPTED_CASES."""
        from tests.contracts.provider_health_envelope_cases import ACCEPTED_CASES

        accepted_bodies = {case.body for case in ACCEPTED_CASES}

        # These patterns MUST be accepted
        required_patterns = [
            '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200',
            '{"healthy": true}\nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200',
        ]

        for pattern in required_patterns:
            assert pattern in accepted_bodies, (
                f"Known envelope pattern must be in ACCEPTED_CASES.\n"
                f"  Pattern: {pattern!r}"
            )

    def test_known_rejected_patterns_are_rejected(self) -> None:
        """All known failed curl envelope patterns must be in REJECTED_CASES."""
        from tests.contracts.provider_health_envelope_cases import REJECTED_CASES

        rejected_bodies = {case.body for case in REJECTED_CASES}

        # These patterns MUST be rejected as contamination
        required_patterns = [
            '{"healthy": true}\nCURL_EXIT=1\nHTTP_CODE=200',
            '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=500',
            '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200\nextra',
        ]

        for pattern in required_patterns:
            assert pattern in rejected_bodies, (
                f"Known rejected pattern must be in REJECTED_CASES.\n"
                f"  Pattern: {pattern!r}"
            )
