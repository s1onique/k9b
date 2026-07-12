"""Tests for the incident identity hardening module.

ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1 hardening
"""

from __future__ import annotations

import json

from k8s_diag_agent.collect.incident_identity_hardening import (
    DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC,
    DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC,
    DEFAULT_MAX_PROMOTION_RECORDS_IN_DIAGNOSTIC,
    DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC,
    INCIDENT_ACCESS_MODE_BACKEND,
    INCIDENT_ACCESS_MODE_LOCAL,
    LOOKUP_ERROR_KIND_AUTHENTICATION,
    LOOKUP_ERROR_KIND_BACKEND_FAILURE,
    LOOKUP_ERROR_KIND_NOT_FOUND,
    LOOKUP_ERROR_KIND_TRANSPORT,
    LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD,
    PROMOTION_MODE_BACKEND_API,
    PROMOTION_MODE_LOCAL,
    PROMOTION_OUTCOME_NOOP,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
    PROMOTION_OUTCOME_UPDATED,
    BackendEndpointIdentity,
    IncidentStoreConsistencyError,
    LookupOutcome,
    PromotionRecord,
    backend_endpoint_identity_from_url,
    build_promotion_records_from_pairs,
    select_canonical_ids_from_promotion,
    verify_promotion_consistency,
)
from k8s_diag_agent.ui.server_incident_internal_models import PromotionResponse


class TestPromotionRecord:
    """Tests for PromotionRecord dataclass."""

    def test_to_dict_round_trip(self) -> None:
        record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="incident-1",
            promotion_outcome=PROMOTION_OUTCOME_OPENED,
        )
        payload = record.to_dict()
        assert payload == {
            "source_candidate_id": "cand-1",
            "canonical_incident_id": "incident-1",
            "promotion_outcome": "opened",
        }

    def test_to_dict_with_none_canonical(self) -> None:
        record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id=None,
            promotion_outcome=PROMOTION_OUTCOME_NOOP,
        )
        payload = record.to_dict()
        assert payload["canonical_incident_id"] is None


class TestBackendEndpointIdentity:
    """Tests for BackendEndpointIdentity and helpers.

    R1 contract: URL sanitisation MUST drop userinfo, path, query string,
    and fragment. Only the scheme, hostname, and port survive. No
    credentials or query tokens can leak into structured logs.
    """

    def test_to_dict_no_credentials(self) -> None:
        identity = backend_endpoint_identity_from_url(
            "https://user:pass@k9b-backend:8080/path?token=secret#frag",
        )
        payload = identity.to_dict()
        assert payload["scheme"] == "https"
        assert payload["host"] == "k9b-backend"
        assert payload["port"] == 8080
        assert "@" not in payload["host"]
        assert payload["base_url"] == "https://k9b-backend:8080"
        assert identity.base_url == "https://k9b-backend:8080"
        allowed_keys = {
            "scheme",
            "host",
            "port",
            "internal_api_path_prefix",
            "backend_reachable",
            "base_url",
        }
        assert set(payload) <= allowed_keys
        serialized = json.dumps(payload)
        for forbidden in (
            "Bearer ",
            "Authorization",
            "user:pass",
            "userinfo",
            "password",
            "/path",
            "token=secret",
            "#frag",
        ):
            assert forbidden not in serialized, forbidden

    def test_credential_bearing_url_is_sanitized(self) -> None:
        identity = backend_endpoint_identity_from_url(
            "https://backend?token=ABCDEFGHIJKLMNOP&api_key=xyz",
        )
        serialized = json.dumps(identity.to_dict())
        for forbidden in ("ABCDEFGHIJKLMNOP", "api_key", "xyz", "token=", "Bearer "):
            assert forbidden not in serialized
        assert identity.base_url == "https://backend"

    def test_userinfo_url_strips_credentials(self) -> None:
        identity = backend_endpoint_identity_from_url(
            "https://admin:hunter2@k9b-backend:9090/secret",
        )
        serialized = json.dumps(identity.to_dict())
        assert "admin" not in serialized
        assert "hunter2" not in serialized
        assert "@" not in identity.to_dict()["host"]
        assert identity.base_url == "https://k9b-backend:9090"

    def test_to_dict_none_url(self) -> None:
        identity = backend_endpoint_identity_from_url(None)
        assert identity.base_url == ""
        assert identity.to_dict()["backend_reachable"] is None
        assert identity.to_dict()["scheme"] == ""
        assert identity.to_dict()["host"] == ""
        assert identity.to_dict()["port"] is None

    def test_unparseable_url_returns_empty_safely(self) -> None:
        identity = backend_endpoint_identity_from_url("not a url at all!!!")
        assert identity.base_url == ""
        assert identity.scheme == ""
        assert identity.host == ""
        assert identity.port is None


class TestBuildPromotionRecordsFromPairs:
    def test_constructs_records(self) -> None:
        pairs = [
            ("cand-a", "incident-a", "opened"),
            ("cand-b", None, "skipped_duplicate"),
        ]
        records = build_promotion_records_from_pairs(pairs)
        assert [r.source_candidate_id for r in records] == ["cand-a", "cand-b"]
        assert records[0].canonical_incident_id == "incident-a"
        assert records[1].canonical_incident_id is None


class TestSelectCanonicalIdsFromPromotion:
    def test_collects_unique_opened_or_updated_only_by_default(self) -> None:
        records = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-2", "incident-2", PROMOTION_OUTCOME_UPDATED),
            PromotionRecord("cand-3", "incident-3", PROMOTION_OUTCOME_SKIPPED_DUPLICATE),
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-4", None, PROMOTION_OUTCOME_NOOP),
        ]
        assert select_canonical_ids_from_promotion(records) == [
            "incident-1",
            "incident-2",
        ]

    def test_include_skipped_when_requested(self) -> None:
        records = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-3", "incident-3", PROMOTION_OUTCOME_SKIPPED_DUPLICATE),
        ]
        ids = select_canonical_ids_from_promotion(records, include_skipped=True)
        assert ids == ["incident-1", "incident-3"]

    def test_dedupes_duplicates(self) -> None:
        records = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-2", "incident-1", PROMOTION_OUTCOME_OPENED),
        ]
        ids = select_canonical_ids_from_promotion(records)
        assert ids == ["incident-1"]


class TestLookupOutcomeAuthoritative:
    def test_authoritative_answer_only_when_not_found_kind(self) -> None:
        not_found = LookupOutcome("incident-1", found=False)
        not_found_authoritative = LookupOutcome("incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_NOT_FOUND)
        transport = LookupOutcome(
            "incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_TRANSPORT
        )
        auth = LookupOutcome(
            "incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_AUTHENTICATION
        )
        backend = LookupOutcome(
            "incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_BACKEND_FAILURE
        )
        payload = LookupOutcome(
            "incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD
        )
        # The default LookupOutcome uses NOT_FOUND; we want to make
        # sure the verifier treats only NOT_FOUND as authoritative.
        assert not_found.is_authoritative_answer() is True
        assert not_found_authoritative.is_authoritative_answer() is True
        assert transport.is_authoritative_answer() is False
        assert auth.is_authoritative_answer() is False
        assert backend.is_authoritative_answer() is False
        assert payload.is_authoritative_answer() is False


class TestVerifyPromotionConsistency:
    def _endpoint(self) -> BackendEndpointIdentity:
        return backend_endpoint_identity_from_url("https://k9b-backend:8080")

    @staticmethod
    def _open_update_counts(
        promotions: list[PromotionRecord],
    ) -> tuple[int, int, list[str], list[str]]:
        """Derive (opened_incidents, updated_incidents, opened_ids, updated_ids).

        R5 helper for tests that exercise the verifier contract: the
        helper counts outcomes and aggregates per-aggregate canonical ID
        arrays in deterministic first-seen order so the assertions can
        compare against the exact value the orchestrator would pass.
        """
        opened_ids = [
            record.canonical_incident_id
            for record in promotions
            if record.promotion_outcome == PROMOTION_OUTCOME_OPENED
            and record.canonical_incident_id is not None
        ]
        updated_ids = [
            record.canonical_incident_id
            for record in promotions
            if record.promotion_outcome == PROMOTION_OUTCOME_UPDATED
            and record.canonical_incident_id is not None
        ]
        return (
            len(opened_ids),
            len(updated_ids),
            list(dict.fromkeys(opened_ids)),
            list(dict.fromkeys(updated_ids)),
        )

    def test_returns_none_when_consistent(self) -> None:
        promotions = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("cand-2", "incident-2", PROMOTION_OUTCOME_UPDATED),
        ]
        lookups = [
            LookupOutcome("incident-1", found=True),
            LookupOutcome("incident-2", found=True),
        ]
        opened, updated, opened_ids, updated_ids = self._open_update_counts(
            promotions
        )
        result = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=self._endpoint(),
            opened_incidents=opened,
            updated_incidents=updated,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
        )
        assert result is None

    def test_returns_error_when_lookup_missing(self) -> None:
        promotions = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
        ]
        lookups = [LookupOutcome("incident-1", found=False)]
        opened, updated, opened_ids, updated_ids = self._open_update_counts(
            promotions
        )
        result = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=self._endpoint(),
            opened_incidents=opened,
            updated_incidents=updated,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
        )
        assert isinstance(result, IncidentStoreConsistencyError)
        payload = result.to_dict()
        assert payload["error_kind"] == "incident_store_consistency_error"
        assert payload["canonical_incident_ids"] == ["incident-1"]
        assert payload["promotion_outcomes"] == ["opened"]
        assert payload["source_candidate_ids"] == ["cand-1"]
        assert payload["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND
        assert payload["lookup_outcomes"][0]["found"] is False
        assert payload["backend_endpoint"]["base_url"] == "https://k9b-backend:8080"

    def test_returns_none_when_lookup_is_inconclusive(self) -> None:
        # A transport failure during the authoritative lookup is NOT a
        # consistency error. The verifier reports a reachability
        # problem separately but does not raise ``not_found`` for
        # transport errors.
        promotions = [
            PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
        ]
        lookups = [
            LookupOutcome(
                "incident-1", found=False, error_kind=LOOKUP_ERROR_KIND_TRANSPORT
            )
        ]
        opened, updated, opened_ids, updated_ids = self._open_update_counts(
            promotions
        )
        result = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=self._endpoint(),
            opened_incidents=opened,
            updated_incidents=updated,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
        )
        assert result is None

    def test_skipped_outcomes_are_ignored(self) -> None:
        promotions = [
            PromotionRecord("cand-1", None, PROMOTION_OUTCOME_SKIPPED_DUPLICATE),
        ]
        opened, updated, opened_ids, updated_ids = self._open_update_counts(
            promotions
        )
        result = verify_promotion_consistency(
            promotions,
            lookups=[],
            backend_endpoint=self._endpoint(),
            opened_incidents=opened,
            updated_incidents=updated,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
        )
        assert result is None

    def test_returns_none_for_empty_promotions(self) -> None:
        result = verify_promotion_consistency(
            [],
            lookups=[LookupOutcome("incident-1", found=False)],
            backend_endpoint=self._endpoint(),
        )
        assert result is None

    def test_diagnostics_are_bounded(self) -> None:
        """Truncated records and ``*_omitted`` counters are present."""
        # Build 200 promotion records, all opening different canonical IDs.
        promotions = [
            PromotionRecord(
                source_candidate_id=f"cand-{i:04d}",
                canonical_incident_id=f"incident-{i:04d}",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            )
            for i in range(200)
        ]
        lookups = [
            LookupOutcome(f"incident-{i:04d}", found=False)
            for i in range(200)
        ]
        opened, updated, opened_ids, updated_ids = self._open_update_counts(
            promotions
        )
        result = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=self._endpoint(),
            opened_incidents=opened,
            updated_incidents=updated,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
        )
        assert isinstance(result, IncidentStoreConsistencyError)
        payload = result.to_dict()
        assert len(payload["canonical_incident_ids"]) == DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC
        assert len(payload["source_candidate_ids"]) == DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC
        assert len(payload["lookup_outcomes"]) == DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC
        # Omitted counters must report the rest.
        assert payload["canonical_incident_ids_omitted"] == (
            200 - DEFAULT_MAX_CANONICAL_IDS_IN_DIAGNOSTIC
        )
        assert payload["source_candidate_ids_omitted"] == (
            200 - DEFAULT_MAX_SOURCE_CANDIDATE_IDS_IN_DIAGNOSTIC
        )
        assert payload["lookup_outcomes_omitted"] == (
            200 - DEFAULT_MAX_LOOKUP_OUTCOMES_IN_DIAGNOSTIC
        )
        # Promotion outcomes mirror the canonical-ID truncation, not the
        # promotion_records list, so we cap at the smaller of the two.
        assert len(payload["promotion_outcomes"]) <= DEFAULT_MAX_PROMOTION_RECORDS_IN_DIAGNOSTIC


class TestPromotionResponseCanonicalPropagation:
    def test_promotion_response_carries_canonical_ids(self) -> None:
        response = PromotionResponse(
            ok=True,
            scanned=2,
            firing=2,
            opened_incidents=1,
            updated_incidents=1,
            skipped_duplicates=0,
            errors=0,
            opened_incident_ids=["incident-a"],
            updated_incident_ids=["incident-b"],
            promotion_records=[
                {
                    "source_candidate_id": "cand-a",
                    "canonical_incident_id": "incident-a",
                    "promotion_outcome": "opened",
                },
                {
                    "source_candidate_id": "cand-b",
                    "canonical_incident_id": "incident-b",
                    "promotion_outcome": "updated",
                },
            ],
            unique_candidate_count=2,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode="backend",
        )
        payload = response.to_dict()
        assert payload["opened_incident_ids"] == ["incident-a"]
        assert payload["updated_incident_ids"] == ["incident-b"]
        assert payload["promotion_records"][0]["canonical_incident_id"] == "incident-a"
        assert payload["incident_access_mode"] == "backend"

    def test_promotion_response_from_promotion_result(self) -> None:
        result = type(
            "PromotionLike",
            (),
            {
                "scanned_signal_count": 3,
                "firing_signal_count": 3,
                "opened_incident_count": 1,
                "updated_incident_count": 1,
                "skipped_duplicate_count": 1,
            },
        )()
        response = PromotionResponse.from_promotion_result(
            result,
            opened_ids=["incident-a"],
            updated_ids=["incident-b"],
            promotion_records=[
                {
                    "source_candidate_id": "cand-a",
                    "canonical_incident_id": "incident-a",
                    "promotion_outcome": "opened",
                },
                {
                    "source_candidate_id": "cand-b",
                    "canonical_incident_id": "incident-b",
                    "promotion_outcome": "updated",
                },
            ],
            unique_candidate_count=3,
            promotion_scan_scope="internal_api_alert_signals",
        )
        assert response.scanned == 3
        assert response.opened_incidents == 1
        assert response.updated_incident_ids == ["incident-b"]
        assert response.unique_candidate_count == 3


class TestAccessModeConstants:
    def test_constants(self) -> None:
        assert INCIDENT_ACCESS_MODE_BACKEND == "backend"
        assert INCIDENT_ACCESS_MODE_LOCAL == "local"
        assert PROMOTION_MODE_LOCAL == "local"
        assert PROMOTION_MODE_BACKEND_API == "backend-api"

    def test_lookup_error_kind_constants(self) -> None:
        assert LOOKUP_ERROR_KIND_NOT_FOUND == "not_found"
        assert LOOKUP_ERROR_KIND_TRANSPORT == "transport_error"
        assert LOOKUP_ERROR_KIND_AUTHENTICATION == "authentication_error"
        assert LOOKUP_ERROR_KIND_BACKEND_FAILURE == "backend_failure"
        assert LOOKUP_ERROR_KIND_UNEXPECTED_PAYLOAD == "unexpected_payload"


class TestBackendEndpointIdentityR3IPv6Rendering:
    """R3: IPv6 hostnames MUST be re-bracketed when rendering ``base_url``.

    ``urlparse(...).hostname`` strips the surrounding brackets from
    IPv6 literals, so ``BackendEndpointIdentity.host`` ends up as a
    colon-bearing hostname like ``::1`` or ``fe80::1``. The
    ``base_url`` property MUST re-bracket those values before rendering
    so the URL stays parseable.

    R3 acceptance proof covers:
    * valid IPv6 with and without port,
    * IPv6 literals that are already bracketed (no double-bracket),
    * malformed brackets that should not raise,
    * non-numeric / out-of-range ports,
    * credentials, query strings, and fragments must still be sanitised.
    """

    def test_ipv6_with_port_is_bracketed(self) -> None:
        identity = backend_endpoint_identity_from_url("http://[::1]:8080")
        assert identity.scheme == "http"
        # ``urlparse`` strips the brackets; we re-add them.
        assert identity.host == "::1"
        assert identity.port == 8080
        assert identity.base_url == "http://[::1]:8080"

    def test_ipv6_without_port_is_bracketed(self) -> None:
        identity = backend_endpoint_identity_from_url("http://[::1]")
        assert identity.scheme == "http"
        assert identity.host == "::1"
        assert identity.port is None
        # The port-less render MUST still bracket the IPv6 host so
        # callers do not parse ``http://::1`` as scheme ``http``,
        # host ``:``, port ``1``.
        assert identity.base_url == "http://[::1]"

    def test_ipv6_full_form_is_bracketed(self) -> None:
        identity = backend_endpoint_identity_from_url("https://[2001:db8::1]:8443/path?token=secret")
        assert identity.scheme == "https"
        assert identity.host == "2001:db8::1"
        assert identity.port == 8443
        assert identity.base_url == "https://[2001:db8::1]:8443"
        # Credentials and path are still dropped.
        assert "@" not in identity.base_url
        assert "token" not in identity.base_url

    def test_malformed_brackets_do_not_raise(self) -> None:
        # An unclosed bracket must not raise; we should still get a
        # parseable ``base_url`` or an empty identity.
        identity = backend_endpoint_identity_from_url("http://[unclosed")
        assert isinstance(identity.scheme, str)
        assert isinstance(identity.host, str)

    def test_ipv6_with_credentials_drops_userinfo(self) -> None:
        identity = backend_endpoint_identity_from_url("http://user:pass@[::1]:8080/path")
        assert identity.host == "::1"
        assert identity.port == 8080
        # ``user:pass@`` MUST NOT survive into ``base_url``.
        assert "user" not in identity.base_url
        assert "pass" not in identity.base_url
        assert "@" not in identity.base_url
        assert identity.base_url == "http://[::1]:8080"

    def test_nonnumeric_port_does_not_crash_rendering(self) -> None:
        identity = backend_endpoint_identity_from_url("http://[::1]:abc")
        # ``parsed.port`` raises ``ValueError`` on non-numeric input; we
        # drop the port to ``None`` rather than crash.
        assert identity.host == "::1"
        assert identity.port is None
        assert identity.base_url == "http://[::1]"


class TestBackendEndpointIdentityR2Hardening:
    """R2 hardening: invalid ports and IPv6 formatting must not crash.

    ``urlparse(...).port`` and ``.hostname`` can raise ``ValueError``
    for malformed inputs (out-of-range ports, IPv6 literals with
    zones, etc.). The sanitiser must catch the exception and continue
    returning a useful diagnostic; it must never let the structured
    log call crash the caller.
    """

    def test_invalid_port_string_returns_none_port(self) -> None:
        identity = backend_endpoint_identity_from_url("http://backend:abc")
        assert identity.scheme == "http"
        assert identity.host == "backend"
        # Non-integer port MUST NOT crash; it should drop to ``None``.
        assert identity.port is None
        assert identity.base_url == "http://backend"

    def test_out_of_range_port_returns_none_port(self) -> None:
        identity = backend_endpoint_identity_from_url("http://backend:99999999")
        assert identity.scheme == "http"
        assert identity.host == "backend"
        # Out-of-range port MUST NOT crash; it should drop to ``None``.
        assert identity.port is None

    def test_ipv6_literal_with_zone_id_does_not_crash(self) -> None:
        # IPv6 zone identifiers (``%25eth0`` URL-escaped zone) make
        # ``parsed.hostname`` raise ``ValueError`` on older Python
        # releases. The sanitiser MUST catch the exception and keep
        # the rest of the diagnostic useful.
        identity = backend_endpoint_identity_from_url(
            "http://[fe80::1%25eth0]:8080/path",
        )
        assert identity.scheme == "http"
        # The hostname recovery is best-effort. We accept either an
        # empty string (when ``hostname`` raised) or the bracketed
        # literal; in either case the call must not raise.
        assert isinstance(identity.host, str)
        # The port should still be parsed when the URL is otherwise
        # well-formed.
        assert identity.port == 8080

    def test_ipv6_literal_without_zone_id(self) -> None:
        identity = backend_endpoint_identity_from_url("http://[::1]:8080")
        assert identity.scheme == "http"
        # ``parsed.hostname`` strips the IPv6 brackets; we accept
        # either ``::1`` or an empty string here, but the call MUST NOT
        # raise and the port must be reported.
        assert identity.port == 8080

    def test_malformed_url_returns_empty_identity(self) -> None:
        identity = backend_endpoint_identity_from_url("not a url at all")
        # We expect either an empty identity or a best-effort parse,
        # but the call MUST NOT raise ``ValueError`` regardless.
        assert isinstance(identity.scheme, str)
        assert isinstance(identity.host, str)
        assert identity.port is None or isinstance(identity.port, int)

    def test_none_url_returns_empty_identity(self) -> None:
        identity = backend_endpoint_identity_from_url(None)
        assert identity.scheme == ""
        assert identity.host == ""
        assert identity.port is None
        assert identity.base_url == ""
