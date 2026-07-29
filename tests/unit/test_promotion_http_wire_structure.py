"""Structural tests for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

Covers required-field validation, strict-bool, non-negative-int,
closed-vocabulary membership, and per-record validation.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.promotion_http_wire_decode import (
    _REQUIRED_WIRE_FIELDS,
    PromotionHttpWireResult,
    PromotionWireRecord,
)
from k8s_diag_agent.collect.promotion_http_wire_types import (
    PromotionHttpWireValidationError,
    PromotionWireIncidentAccessMode,
    PromotionWireRecordOutcome,
    PromotionWireScanScope,
)


def _valid_payload() -> dict[str, Any]:
    """Build a minimal valid 1-record success payload."""
    return {
        "ok": True,
        "scanned": 1,
        "firing": 1,
        "opened_incidents": 1,
        "updated_incidents": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "error_messages": [],
        "opened_incident_ids": ["canonical-inc-001"],
        "updated_incident_ids": [],
        "canonical_incident_ids": ["canonical-inc-001"],
        "promotion_records": [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ],
        "unique_candidate_count": 1,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


class TestRequiredFields:
    @pytest.mark.parametrize("missing_field", _REQUIRED_WIRE_FIELDS)
    def test_missing_required_field_raises(self, missing_field: str) -> None:
        payload = _valid_payload()
        payload.pop(missing_field)
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "missing required field" in str(exc_info.value)

    def test_missing_multiple_fields_reported_together(self) -> None:
        payload = _valid_payload()
        payload.pop("ok")
        payload.pop("scanned")
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "ok" in str(exc_info.value)
        assert "scanned" in str(exc_info.value)


class TestTopLevelType:
    def test_non_mapping_payload_raises(self) -> None:
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(["not", "a", "mapping"])

    def test_string_payload_raises(self) -> None:
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload("not a mapping")


class TestStrictBoolValidation:
    @pytest.mark.parametrize(
        "value", ["true", 1, 0, "", "false", None, [True], {"ok": True}]
    )
    def test_ok_must_be_strict_bool(self, value: Any) -> None:
        payload = _valid_payload()
        payload["ok"] = value
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert "ok" in str(exc_info.value)


class TestNonNegativeIntValidation:
    @pytest.mark.parametrize("field_name", ["scanned", "firing", "errors", "unique_candidate_count"])
    @pytest.mark.parametrize("value", [-1, "1", 1.5, None, [1]])
    def test_field_must_be_non_negative_int(
        self, field_name: str, value: Any
    ) -> None:
        payload = _valid_payload()
        payload[field_name] = value
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult.from_payload(payload)
        assert field_name in str(exc_info.value)

    def test_bool_as_integer_rejected(self) -> None:
        payload = _valid_payload()
        payload["scanned"] = True
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestCollectionTypeValidation:
    @pytest.mark.parametrize(
        "field_name",
        [
            "opened_incident_ids",
            "updated_incident_ids",
            "canonical_incident_ids",
            "promotion_records",
            "error_messages",
        ],
    )
    def test_field_must_be_list_or_tuple(self, field_name: str) -> None:
        payload = _valid_payload()
        payload[field_name] = "not a list"
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestStringIDValidation:
    @pytest.mark.parametrize(
        "field_name",
        ["opened_incident_ids", "updated_incident_ids", "canonical_incident_ids"],
    )
    def test_non_string_id_raises(self, field_name: str) -> None:
        payload = _valid_payload()
        payload[field_name] = [123]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    @pytest.mark.parametrize(
        "field_name",
        ["opened_incident_ids", "updated_incident_ids", "canonical_incident_ids"],
    )
    def test_empty_string_id_raises(self, field_name: str) -> None:
        payload = _valid_payload()
        payload[field_name] = [""]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestErrorMessagesValidation:
    def test_non_string_error_message_raises(self) -> None:
        payload = _valid_payload()
        payload["ok"] = False
        payload["errors"] = 1
        payload["error_messages"] = [123]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_empty_error_message_raises(self) -> None:
        payload = _valid_payload()
        payload["ok"] = False
        payload["errors"] = 1
        payload["error_messages"] = [""]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestScopeAndAccessMode:
    def test_invalid_scope_raises(self) -> None:
        payload = _valid_payload()
        payload["promotion_scan_scope"] = "other-scope"
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_invalid_access_mode_raises(self) -> None:
        payload = _valid_payload()
        payload["incident_access_mode"] = "remote"
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)


class TestRecordValidation:
    def test_unknown_record_outcome_raises(self) -> None:
        payload = _valid_payload()
        payload["promotion_records"] = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "unknown_value",
            }
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_record_missing_source_id_raises(self) -> None:
        payload = _valid_payload()
        payload["promotion_records"] = [
            {
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_record_empty_source_id_raises(self) -> None:
        payload = _valid_payload()
        payload["promotion_records"] = [
            {
                "source_candidate_id": "",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": "opened",
            }
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_record_missing_canonical_id_raises(self) -> None:
        payload = _valid_payload()
        payload["promotion_records"] = [
            {
                "source_candidate_id": "sig-001",
                "promotion_outcome": "opened",
            }
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    def test_direct_construction_with_invalid_record_raises(self) -> None:
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionWireRecord(
                source_candidate_id="",
                canonical_incident_id="x",
                promotion_outcome=PromotionWireRecordOutcome.OPENED,
            )


class TestClosedEnumReachability:
    def test_record_outcome_enum_is_closed(self) -> None:
        assert {member.value for member in PromotionWireRecordOutcome} == {
            "opened",
            "updated",
            "observation_refreshed",
            "unchanged",
        }

    def test_scope_enum_is_closed(self) -> None:
        assert {member.value for member in PromotionWireScanScope} == {
            "internal_api_alert_signals:scoped",
        }

    def test_access_mode_enum_is_closed(self) -> None:
        assert {member.value for member in PromotionWireIncidentAccessMode} == {
            "backend",
            "local",
        }


class TestDirectConstructionParity:
    """Direct dataclass construction must enforce the same
    entry-parity invariants as :meth:`from_payload`.

    The dataclass-generated ``__init__`` invokes ``__post_init__``,
    so every invariant that ``from_payload`` validates must also
    fire for callers using the constructor directly.
    """

    def _kwargs(
        self,
        *,
        opened_incident_ids: Any = ("canonical-inc-001",),
        updated_incident_ids: Any = (),
        canonical_incident_ids: Any = ("canonical-inc-001",),
        promotion_records: Any = (
            PromotionWireRecord(
                source_candidate_id="sig-001",
                canonical_incident_id="canonical-inc-001",
                promotion_outcome=PromotionWireRecordOutcome.OPENED,
            ),
        ),
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "scanned": 1,
            "firing": 1,
            "opened_incidents": 1,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": (),
            "opened_incident_ids": opened_incident_ids,
            "updated_incident_ids": updated_incident_ids,
            "canonical_incident_ids": canonical_incident_ids,
            "promotion_records": promotion_records,
            "unique_candidate_count": 1,
            "promotion_scan_scope": PromotionWireScanScope.INTERNAL_API_ALERT_SIGNALS_SCOPED,
            "incident_access_mode": PromotionWireIncidentAccessMode.BACKEND,
        }

    @pytest.mark.parametrize(
        "field_name",
        ["opened_incident_ids", "updated_incident_ids", "canonical_incident_ids"],
    )
    def test_non_tuple_collection_raises(self, field_name: str) -> None:
        kwargs = self._kwargs()
        kwargs[field_name] = ["canonical-inc-001"]
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult(**kwargs)
        assert field_name in str(exc_info.value)

    @pytest.mark.parametrize(
        "field_name",
        ["opened_incident_ids", "updated_incident_ids", "canonical_incident_ids"],
    )
    def test_non_string_entry_raises(self, field_name: str) -> None:
        kwargs = self._kwargs()
        kwargs[field_name] = (123,)
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult(**kwargs)
        assert field_name in str(exc_info.value)

    @pytest.mark.parametrize(
        "field_name",
        ["opened_incident_ids", "updated_incident_ids", "canonical_incident_ids"],
    )
    def test_empty_string_entry_raises(self, field_name: str) -> None:
        kwargs = self._kwargs()
        kwargs[field_name] = ("",)
        with pytest.raises(PromotionHttpWireValidationError) as exc_info:
            PromotionHttpWireResult(**kwargs)
        assert field_name in str(exc_info.value)

    def test_error_messages_non_tuple_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["error_messages"] = ["non-empty"]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_error_messages_non_string_entry_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["error_messages"] = (123,)
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_error_messages_empty_string_entry_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["error_messages"] = ("",)
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_promotion_records_not_tuple_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["promotion_records"] = [
            PromotionWireRecord(
                source_candidate_id="sig-001",
                canonical_incident_id="canonical-inc-001",
                promotion_outcome=PromotionWireRecordOutcome.OPENED,
            ),
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_promotion_records_contains_non_record_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["promotion_records"] = ({"not": "a record"},)
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_promotion_scan_scope_not_enum_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["promotion_scan_scope"] = "internal_api_alert_signals:scoped"
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)

    def test_incident_access_mode_not_enum_raises(self) -> None:
        kwargs = self._kwargs()
        kwargs["incident_access_mode"] = "backend"
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult(**kwargs)


class TestMalformedEnumBoundary:
    """Every malformed wire value MUST converge on
    :class:`PromotionHttpWireValidationError`.

    Both ``TypeError`` (non-string arguments to ``StrEnum``) and
    ``ValueError`` (unknown string literal) are captured so no
    raw enum exception leaks to the client.
    """

    @pytest.mark.parametrize(
        "malformed_value", [[], {}, [1, 2], {"a": 1}, 0, 1, 1.5, None, True]
    )
    def test_promotion_outcome_malformed_value_raises_validation_error(
        self, malformed_value: Any
    ) -> None:
        payload = _valid_payload()
        payload["promotion_records"] = [
            {
                "source_candidate_id": "sig-001",
                "canonical_incident_id": "canonical-inc-001",
                "promotion_outcome": malformed_value,
            }
        ]
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    @pytest.mark.parametrize(
        "malformed_value", [[], {}, 1, 1.5, None, True, False]
    )
    def test_promotion_scan_scope_malformed_value_raises_validation_error(
        self, malformed_value: Any
    ) -> None:
        payload = _valid_payload()
        payload["promotion_scan_scope"] = malformed_value
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)

    @pytest.mark.parametrize(
        "malformed_value", [[], {}, 1, 1.5, None, True, False]
    )
    def test_incident_access_mode_malformed_value_raises_validation_error(
        self, malformed_value: Any
    ) -> None:
        payload = _valid_payload()
        payload["incident_access_mode"] = malformed_value
        with pytest.raises(PromotionHttpWireValidationError):
            PromotionHttpWireResult.from_payload(payload)
