"""HTTP and source-semantics self-tests for the backend-outcome verifier."""

from __future__ import annotations

import pytest

from tests.unit.automatic_diagnosis_backend_detail_outcomes_verifier_support import (
    _format_violations,
    assert_violation,
    check_dispatch_source,
    check_lookup_source,
    lookup_source,
)


def dispatch_source(
    *,
    source_expression: str | None = "BackendIncidentLookupSource.LOCAL_STORE",
    include_http_status: bool = False,
) -> str:
    lines = [
        "def dispatch_backend_incident(incident_id):",
        "    return BackendIncidentNotFound(",
        "        requested_incident_id=incident_id,",
    ]
    if source_expression is not None:
        lines.append(f"        source={source_expression},")
    if include_http_status:
        lines.append("        http_status=404,")
    lines.append("    )")
    return "\n".join(lines)


class TestBackendSourceSemantics:
    def test_exact_backend_404_branch_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(monkeypatch, lookup_source())
        assert not violations, _format_violations(violations)

    def test_backend_not_found_requires_backend_api_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(source_expression=None),
        )
        assert_violation(violations, "source=BackendIncidentLookupSource.BACKEND_API")

    def test_backend_not_found_rejects_local_store_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(
                source_expression="BackendIncidentLookupSource.LOCAL_STORE"
            ),
        )
        assert_violation(violations, "source=BackendIncidentLookupSource.BACKEND_API")

    def test_backend_not_found_requires_explicit_404_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(include_http_status=False),
        )
        assert_violation(violations, "http_status=404", "explicitly")


class TestExact404Branch:
    @pytest.mark.parametrize(
        "predicate",
        [
            "response.http_status != 404",
            "response.http_status in {400, 404}",
            "404 <= response.http_status",
            "response.http_status",
            "response.http_status == 400",
            "response.http_status >= 404",
            "response.http_status in (404,)",
            "response.http_status == 404 or response.http_status == 410",
        ],
        ids=[
            "not-equal",
            "set-membership",
            "lower-bound",
            "truthiness",
            "wrong-equality",
            "greater-or-equal",
            "tuple-membership",
            "compound-or",
        ],
    )
    def test_non_exact_404_predicate_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        predicate: str,
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(predicate=predicate),
        )
        assert_violation(violations, "EXACTLY", "response.http_status == 404")

    def test_reversed_exact_404_equality_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_lookup_source(
            monkeypatch,
            lookup_source(predicate="404 == response.http_status"),
        )
        assert not violations, _format_violations(violations)


class TestLocalSourceSemantics:
    def test_local_dispatch_rejects_synthetic_http_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_dispatch_source(
            monkeypatch,
            dispatch_source(include_http_status=True),
        )
        assert_violation(violations, "local-mode", "must not synthesise", "404")

    def test_local_dispatch_without_http_status_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_dispatch_source(monkeypatch, dispatch_source())
        assert not violations, _format_violations(violations)

    def test_local_dispatch_requires_explicit_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        violations = check_dispatch_source(
            monkeypatch,
            dispatch_source(source_expression=None),
        )
        assert_violation(violations, "explicit", "source")
