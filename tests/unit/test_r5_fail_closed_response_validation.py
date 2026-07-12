"""R5 fail-closed response validation tests.

R5 (item 1) hardens the consistency verifier so it:

* accepts ``opened_incidents`` and ``updated_incidents`` as required
  parameters and rejects count / record / ID disagreements;
* raises the typed ``PromotionConsistencyContractError`` for the
  exact legacy-backend regression (nonzero counts, empty IDs, empty
  records);
* rejects missing canonical IDs on opened/updated records;
* requires the per-aggregate canonical ID arrays to agree with the
  per-record canonical IDs.

The tests below pin every failure shape the contract forbids, plus a
couple of happy-path calls so the regression coverage is complete.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R5
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_identity_hardening import (
    INCIDENT_ACCESS_MODE_BACKEND,
    LOOKUP_ERROR_KIND_NOT_FOUND,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    BackendEndpointIdentity,
    LookupOutcome,
    PromotionConsistencyContractError,
    PromotionRecord,
    backend_endpoint_identity_from_url,
    verify_promotion_consistency,
)


def _endpoint() -> BackendEndpointIdentity:
    return backend_endpoint_identity_from_url("https://k9b-backend:8080")


class FailClosedResponseValidationTests(unittest.TestCase):
    """R5 (item 1) fail-closed contract."""

    def test_legacy_backend_regression_nonzero_counts_empty_records(self) -> None:
        """Legacy regression: nonzero counts, empty IDs, empty records -> typed error."""
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                [],
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=2,
                updated_incidents=1,
                opened_incident_ids=(),
                updated_incident_ids=(),
            )
        self.assertEqual(ctx.exception.opened_incidents, 2)
        self.assertEqual(ctx.exception.updated_incidents, 1)
        self.assertEqual(ctx.exception.promotion_record_count, 0)
        self.assertIn(
            "Legacy-backend regression",
            str(ctx.exception),
        )

    def test_count_disagreement_with_records(self) -> None:
        """opened_incidents aggregate disagrees with per-record count -> error."""
        records = [
            PromotionRecord("c-1", "inc-1", PROMOTION_OUTCOME_OPENED),
        ]
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                records,
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=2,  # disagrees with the single record
                updated_incidents=0,
                opened_incident_ids=("inc-1",),
                updated_incident_ids=(),
            )
        self.assertEqual(ctx.exception.opened_incidents, 2)
        self.assertEqual(ctx.exception.promotion_record_count, 1)


    def test_equal_cardinality_different_ids_rejected(self) -> None:
        """Equal cardinality but different IDs MUST be rejected.

        R6 multiset identity contract: opened_incident_ids must equal
        the multiset of canonical IDs on opened records in record
        order. Two records with IDs ``inc-1`` and ``inc-2`` paired
        with an opened_incident_ids tuple ``(inc-1, inc-3)`` has the
        same length but different identities, so the response is
        rejected as a typed contract failure.
        """
        records = [
            PromotionRecord("c-1", "inc-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("c-2", "inc-2", PROMOTION_OUTCOME_OPENED),
        ]
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                records,
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=2,
                updated_incidents=0,
                opened_incident_ids=("inc-1", "inc-3"),
                updated_incident_ids=(),
            )
        # The ordered-sequence-with-multiplicity check fires after
        # cardinality matches; we assert that the response was
        # rejected with the ordered-sequence message.
        self.assertIn(
            "ordered sequence",
            str(ctx.exception),
        )

    def test_repeated_valid_canonical_id_accepted(self) -> None:
        """Many->one collapse (repeated canonical ID) MUST be accepted.

        R6 multiset identity contract: ``opened_incident_ids`` is the
        multiset of canonical IDs on opened records. Multiple records
        mapping to the same canonical incident (many->one collapse)
        keep the response valid because the multiset equality holds.
        """
        records = [
            PromotionRecord("c-1", "inc-shared", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("c-2", "inc-shared", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("c-3", "inc-other", PROMOTION_OUTCOME_OPENED),
        ]
        result = verify_promotion_consistency(
            records,
            lookups=[],
            backend_endpoint=_endpoint(),
            opened_incidents=3,
            updated_incidents=0,
            opened_incident_ids=("inc-shared", "inc-shared", "inc-other"),
            updated_incident_ids=(),
        )
        # Many->one collapse is valid; no consistency error from the
        # response contract validator (the lookups list is empty, so
        # the lookup-phase check has nothing to assert).
        self.assertIsNone(result)

    def test_incorrect_multiplicity_rejected(self) -> None:
        """Incorrect multiplicity MUST be rejected.

        R6 multiset identity contract: the per-aggregate array's
        multiplicity must equal the per-record multiset. Records
        ``[inc-x x2]`` paired with ``(inc-x,)`` (single occurrence)
        is rejected because the multiplicity is off by one. The exact
        failure message is gated by the order of checks: the
        cardinality check fires first when distinct-record count
        disagrees with distinct-array count, and the multiset check
        fires when records and array agree in distinct count but
        disagree in record-order or multiplicity. We accept either
        wording as long as the response is rejected.
        """
        records = [
            PromotionRecord("c-1", "inc-x", PROMOTION_OUTCOME_UPDATED),
            PromotionRecord("c-2", "inc-x", PROMOTION_OUTCOME_UPDATED),
        ]
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                records,
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=0,
                updated_incidents=2,
                opened_incident_ids=(),
                updated_incident_ids=("inc-x",),
            )
        message = str(ctx.exception)
        self.assertTrue(
            "ordered sequence" in message or "ordered-sequence" in message,
            msg=(
                "incorrect multiplicity MUST raise a typed contract "
                f"error mentioning the ordered sequence contract; "
                f"got: {message!r}"
            ),
        )


    def test_missing_canonical_id_on_opened_record(self) -> None:
        """Opened/updated record missing canonical_incident_id -> typed error."""
        records = [
            PromotionRecord("c-1", None, PROMOTION_OUTCOME_OPENED),
        ]
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                records,
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=1,
                updated_incidents=0,
                opened_incident_ids=("inc-1",),
                updated_incident_ids=(),
            )
        self.assertEqual(len(ctx.exception.missing_canonical_ids), 1)

    def test_canonical_id_array_disagrees_with_records(self) -> None:
        """opened_incident_ids disagrees with per-record set -> typed error."""
        records = [
            PromotionRecord("c-1", "inc-1", PROMOTION_OUTCOME_OPENED),
        ]
        with self.assertRaises(PromotionConsistencyContractError) as ctx:
            verify_promotion_consistency(
                records,
                lookups=[],
                backend_endpoint=_endpoint(),
                opened_incidents=1,
                updated_incidents=0,
                opened_incident_ids=("inc-1", "inc-2"),
                updated_incident_ids=(),
            )
        # The ID array has 2 elements; the record set has 1 -- count
        # mismatch.
        self.assertEqual(ctx.exception.opened_id_count, 2)

    def test_happy_path_consistent_records(self) -> None:
        """Consistent records and counts produce no error (or a non-contract one)."""
        records = [
            PromotionRecord("c-1", "inc-1", PROMOTION_OUTCOME_OPENED),
            PromotionRecord("c-2", "inc-2", PROMOTION_OUTCOME_UPDATED),
        ]
        lookups = [
            LookupOutcome("inc-1", found=True),
            LookupOutcome("inc-2", found=True),
        ]
        result = verify_promotion_consistency(
            records,
            lookups=lookups,
            backend_endpoint=_endpoint(),
            opened_incidents=1,
            updated_incidents=1,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=("inc-2",),
        )
        # All records were found; no consistency error.
        self.assertIsNone(result)

    def test_consistency_error_still_raised_for_not_found_lookup(self) -> None:
        """A definitive not-found lookup still raises ``IncidentStoreConsistencyError``."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            IncidentStoreConsistencyError,
        )

        records = [
            PromotionRecord("c-1", "inc-1", PROMOTION_OUTCOME_OPENED),
        ]
        lookups = [LookupOutcome("inc-1", found=False, error_kind=LOOKUP_ERROR_KIND_NOT_FOUND)]
        result = verify_promotion_consistency(
            records,
            lookups=lookups,
            backend_endpoint=_endpoint(),
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=(),
        )
        self.assertIsInstance(result, IncidentStoreConsistencyError)
        # The contract validator does NOT raise for this shape; the
        # IncidentStoreConsistencyError is the only error returned.
        self.assertEqual(result.canonical_incident_ids, ("inc-1",))
        self.assertEqual(result.incident_access_mode, INCIDENT_ACCESS_MODE_BACKEND)

if __name__ == "__main__":
    unittest.main()
