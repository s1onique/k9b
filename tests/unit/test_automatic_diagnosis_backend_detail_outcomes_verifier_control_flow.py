"""Exception and truthiness mutation self-tests for the backend-outcome verifier."""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.unit.automatic_diagnosis_backend_detail_outcomes_verifier_support import (
    assert_no_violation,
    assert_violation,
    check_touched_seam_source,
)


def broad_exception_return_none_source() -> str:
    return textwrap.dedent(
        """
        def fetch_incident(incident_id):
            try:
                raise ValueError("boom")
            except Exception:
                return None
        """
    ).strip()


def broad_exception_not_found_source() -> str:
    return textwrap.dedent(
        """
        def fetch_incident(incident_id):
            try:
                raise ValueError("boom")
            except Exception:
                return BackendIncidentNotFound(
                    requested_incident_id=incident_id,
                    http_status=404,
                )
        """
    ).strip()


def falsy_incident_reason_source() -> str:
    return textwrap.dedent(
        """
        def lookup(incident_id):
            incident = None
            if not incident:
                reason = "incident_not_found"
            return reason
        """
    ).strip()


def falsy_payload_not_found_source() -> str:
    return textwrap.dedent(
        """
        def lookup(incident_id, payload):
            if not payload:
                return BackendIncidentNotFound(
                    requested_incident_id=incident_id,
                    http_status=404,
                )
        """
    ).strip()


@pytest.fixture
def probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], list[str]]:
    def run(source: str) -> list[str]:
        return check_touched_seam_source(tmp_path, monkeypatch, source)

    return run


class TestForbiddenPatternsDetected:
    def test_broad_exception_return_none_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(broad_exception_return_none_source())
        assert_violation(violations, "bare", "return None")

    def test_broad_exception_returning_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(broad_exception_not_found_source())
        assert_violation(violations, "BackendIncidentNotFound", "forbidden")

    def test_truthiness_check_then_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(falsy_incident_reason_source())
        assert_violation(violations, "forbidden truthiness")

    def test_empty_payload_returning_not_found_is_detected(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        violations = probe(falsy_payload_not_found_source())
        assert_violation(violations, "truthiness", "BackendIncidentNotFound")


def test_ast_round_trip_on_synthetic_snippet() -> None:
    snippets = (
        broad_exception_return_none_source(),
        broad_exception_not_found_source(),
        falsy_incident_reason_source(),
        falsy_payload_not_found_source(),
    )
    for snippet in snippets:
        ast.parse(snippet)


class TestStructurallyValidAlternatives:
    def test_narrow_exception_return_none_is_not_flagged_as_broad(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        source = textwrap.dedent(
            """
            def fetch_incident(incident_id):
                try:
                    raise ValueError("boom")
                except ValueError:
                    return None
            """
        ).strip()
        assert_no_violation(probe(source), "except Exception: return None")

    def test_broad_exception_returning_lookup_failed_is_not_collapsed(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        source = textwrap.dedent(
            """
            def fetch_incident(incident_id):
                try:
                    raise ValueError("boom")
                except Exception:
                    return BackendIncidentLookupFailed(
                        requested_incident_id=incident_id,
                    )
            """
        ).strip()
        violations = probe(source)
        assert_no_violation(violations, "broad handlers must NOT collapse")

    def test_explicit_incident_none_check_is_not_truthiness(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        source = textwrap.dedent(
            """
            def lookup(incident):
                if incident is None:
                    return "incident_not_found"
                return "found"
            """
        ).strip()
        assert_no_violation(probe(source), "forbidden truthiness")

    def test_explicit_payload_none_check_is_not_truthiness(
        self, probe: Callable[[str], list[str]]
    ) -> None:
        source = textwrap.dedent(
            """
            def lookup(incident_id, payload):
                if payload is None:
                    return BackendIncidentLookupFailed(
                        requested_incident_id=incident_id,
                    )
                return payload
            """
        ).strip()
        assert_no_violation(probe(source), "forbidden truthiness")
