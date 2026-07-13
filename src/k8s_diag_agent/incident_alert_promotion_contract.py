"""Typed contract for current-run alert-signal incident promotion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .domain.identifiers import AlertSignalId, HealthRunId
from .domain.incident_lifecycle import IncidentId

MAX_PROMOTION_SIGNAL_IDS = 200
MAX_PROMOTION_FAILURES = 20
MAX_ID_LENGTH = 160
MAX_SOURCE_IDENTITY_LENGTH = 512
MAX_FAILURE_DETAIL_LENGTH = 256

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")


class PromotionScopeError(ValueError):
    """Raised before mutation when an explicit promotion scope is invalid."""


@dataclass(frozen=True, slots=True)
class PromoteAlertSignalsRequest:
    """Exact alert-signal workset produced by one health-run ingestion."""

    run_id: HealthRunId
    source_identity: str
    signal_ids: tuple[AlertSignalId, ...]

    def __post_init__(self) -> None:
        if not _is_safe_id(str(self.run_id)):
            raise PromotionScopeError("runId is malformed")
        if not self.source_identity or len(self.source_identity) > MAX_SOURCE_IDENTITY_LENGTH:
            raise PromotionScopeError("sourceIdentity is required and must be bounded")
        if len(self.signal_ids) > MAX_PROMOTION_SIGNAL_IDS:
            raise PromotionScopeError(
                f"signalIds exceeds maximum of {MAX_PROMOTION_SIGNAL_IDS}"
            )
        values = [str(signal_id) for signal_id in self.signal_ids]
        if any(not _is_safe_id(value) for value in values):
            raise PromotionScopeError("signalIds contains a malformed identifier")
        if len(set(values)) != len(values):
            raise PromotionScopeError("signalIds must not contain duplicates")

    def to_wire_dict(self) -> dict[str, object]:
        return {
            "runId": str(self.run_id),
            "sourceIdentity": self.source_identity,
            "signalIds": [str(signal_id) for signal_id in self.signal_ids],
        }


@dataclass(frozen=True, slots=True)
class IncidentPromotionFailure:
    """Bounded per-signal failure returned after partial promotion success."""

    signal_id: AlertSignalId
    reason_code: str
    detail: str | None = None

    def to_wire_dict(self) -> dict[str, str]:
        payload = {
            "signalId": str(self.signal_id),
            "reasonCode": self.reason_code[:MAX_ID_LENGTH],
        }
        if self.detail:
            payload["detail"] = self.detail[:MAX_FAILURE_DETAIL_LENGTH]
        return payload


@dataclass(frozen=True, slots=True)
class IncidentPromotionResult:
    """Canonical categorized result for one explicit current-run signal workset."""

    run_id: HealthRunId
    source_identity: str
    scanned_signal_ids: tuple[AlertSignalId, ...] = field(default_factory=tuple)
    opened_incident_ids: tuple[IncidentId, ...] = field(default_factory=tuple)
    materially_changed_incident_ids: tuple[IncidentId, ...] = field(
        default_factory=tuple
    )
    observation_refreshed_incident_ids: tuple[IncidentId, ...] = field(
        default_factory=tuple
    )
    unchanged_incident_ids: tuple[IncidentId, ...] = field(default_factory=tuple)
    skipped_signal_ids: tuple[AlertSignalId, ...] = field(default_factory=tuple)
    failures: tuple[IncidentPromotionFailure, ...] = field(default_factory=tuple)

    @property
    def actionable_incident_ids(self) -> tuple[IncidentId, ...]:
        """Stable first-occurrence union of opened and material changes only."""
        return _stable_unique((*self.opened_incident_ids, *self.materially_changed_incident_ids))

    @property
    def scanned_signal_count(self) -> int:
        return len(self.scanned_signal_ids)

    @property
    def opened_incident_count(self) -> int:
        return len(self.opened_incident_ids)

    @property
    def materially_changed_incident_count(self) -> int:
        return len(self.materially_changed_incident_ids)

    @property
    def observation_refreshed_incident_count(self) -> int:
        return len(self.observation_refreshed_incident_ids)

    @property
    def unchanged_incident_count(self) -> int:
        return len(self.unchanged_incident_ids)

    def to_wire_dict(self) -> dict[str, object]:
        return {
            "runId": str(self.run_id),
            "sourceIdentity": self.source_identity,
            "scannedSignalIds": _strings(self.scanned_signal_ids),
            "openedIncidentIds": _strings(self.opened_incident_ids),
            "materiallyChangedIncidentIds": _strings(
                self.materially_changed_incident_ids
            ),
            "observationRefreshedIncidentIds": _strings(
                self.observation_refreshed_incident_ids
            ),
            "unchangedIncidentIds": _strings(self.unchanged_incident_ids),
            "skippedSignalIds": _strings(self.skipped_signal_ids),
            "failures": [failure.to_wire_dict() for failure in self.failures],
            "actionableIncidentIds": _strings(self.actionable_incident_ids),
        }

    @classmethod
    def empty(cls, request: PromoteAlertSignalsRequest) -> IncidentPromotionResult:
        return cls(run_id=request.run_id, source_identity=request.source_identity)

    @classmethod
    def from_wire_dict(
        cls,
        payload: Mapping[str, object],
    ) -> IncidentPromotionResult:
        """Parse the canonical camelCase wire payload into a typed result.

        This parser is the authoritative translator for the
        ``/api/internal/incidents/promote-alert-signals`` response. It
        accepts the exact wire keys returned by the backend handler and
        fails closed on unknown keys or wrong types so a malformed
        payload cannot produce a synthetic failed promotion.

        R3 invariants:

        * Every wire ID list (``scannedSignalIds``, ``skippedSignalIds``,
          every per-category incident ID list, and ``actionableIncidentIds``)
          MUST be parsed through the same strict parser that enforces
          ``list[str]``, deduplicates within the list, and rejects empty
          / non-string entries. ``failures[].signalId`` is also strictly
          validated.
        * All four result categories (``opened``, materially-changed,
          observation-refreshed, unchanged``) MUST be pairwise disjoint;
          every pair is rejected with a ``PromotionScopeError``.
        * ``actionableIncidentIds`` is cross-validated against the
          computed opened+materially-changed union when the field is
          present in the payload (explicit membership test, not the
          previous double-negative opaque condition).
        """
        if not isinstance(payload, Mapping):
            raise PromotionScopeError(
                "promotion response must be a JSON object"
            )
        allowed = {
            "runId",
            "sourceIdentity",
            "scannedSignalIds",
            "openedIncidentIds",
            "materiallyChangedIncidentIds",
            "observationRefreshedIncidentIds",
            "unchangedIncidentIds",
            "skippedSignalIds",
            "failures",
            "actionableIncidentIds",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise PromotionScopeError(
                f"promotion response contains unsupported fields: "
                f"{sorted(unknown)}"
            )
        for required in ("runId", "sourceIdentity"):
            if required not in payload:
                raise PromotionScopeError(
                    f"promotion response missing required field {required}"
                )

        def _parse_id_list(
            key: str, type_: type
        ) -> tuple[object, ...]:
            """Parse a wire field as a list of unique, safe identifiers.

            Rejects:

            * non-list values,
            * non-string entries,
            * entries that violate ``_is_safe_id`` (empty, oversized,
              whitespace-only, or non-bounded characters),
            * duplicate IDs,
            * missing entries default to an empty list.
            """
            raw_value = payload.get(key, [])
            if raw_value is None:
                raw_value = []
            if not isinstance(raw_value, list) or any(
                not isinstance(item, str) for item in raw_value
            ):
                raise PromotionScopeError(
                    f"promotion response field {key} must be an array of strings"
                )
            ids: list[object] = []
            seen_ids: set[str] = set()
            for item in raw_value:
                if not _is_safe_id(item):
                    raise PromotionScopeError(
                        f"promotion response field {key} contains malformed "
                        f"identifier {item!r}"
                    )
                if item in seen_ids:
                    raise PromotionScopeError(
                        f"promotion response field {key} contains duplicate ID {item!r}"
                    )
                seen_ids.add(item)
                ids.append(type_(item))
            return tuple(ids)

        def _parse_signal_id_list(key: str) -> tuple[AlertSignalId, ...]:
            return _parse_id_list(key, AlertSignalId)  # type: ignore[return-value]

        def _parse_incident_id_list(key: str) -> tuple[IncidentId, ...]:
            return _parse_id_list(key, IncidentId)  # type: ignore[return-value]

        run_id = payload["runId"]
        source_identity = payload["sourceIdentity"]
        if not isinstance(run_id, str) or not isinstance(source_identity, str):
            raise PromotionScopeError(
                "promotion response runId and sourceIdentity must be strings"
            )
        # Bounded safe-ID validation: reject empty, oversized, or
        # non-bounded runId / sourceIdentity so a malformed wire payload
        # cannot produce a synthetic failed promotion.
        if not _is_safe_id(run_id):
            raise PromotionScopeError(
                "promotion response runId is malformed"
            )
        if not source_identity or len(source_identity) > MAX_SOURCE_IDENTITY_LENGTH:
            raise PromotionScopeError(
                "promotion response sourceIdentity is required and must be bounded"
            )

        failures_payload = payload.get("failures", [])
        if failures_payload is None:
            failures_payload = []
        if not isinstance(failures_payload, list):
            raise PromotionScopeError(
                "promotion response failures must be an array"
            )
        failures: list[IncidentPromotionFailure] = []
        seen_failure_signal_ids: set[str] = set()
        for raw in failures_payload:
            if not isinstance(raw, Mapping):
                raise PromotionScopeError(
                    "promotion response failure entry must be an object"
                )
            allowed_failure = {"signalId", "reasonCode", "detail"}
            unknown_failure = set(raw) - allowed_failure
            if unknown_failure:
                raise PromotionScopeError(
                    f"promotion response failure contains unsupported fields: "
                    f"{sorted(unknown_failure)}"
                )
            signal_id_raw = raw.get("signalId")
            reason_code_raw = raw.get("reasonCode")
            detail_raw = raw.get("detail")
            if not isinstance(signal_id_raw, str):
                raise PromotionScopeError(
                    "promotion response failure.signalId must be a string"
                )
            # R3.3: bounded safe-ID validation on every failure entry
            # so a malformed wire payload (e.g. ``"\n"`` or an oversized
            # value) cannot slip into a typed ``IncidentPromotionFailure``.
            if not _is_safe_id(signal_id_raw):
                raise PromotionScopeError(
                    "promotion response failure.signalId is malformed"
                )
            if not isinstance(reason_code_raw, str):
                raise PromotionScopeError(
                    "promotion response failure.reasonCode must be a string"
                )
            if detail_raw is not None and not isinstance(detail_raw, str):
                raise PromotionScopeError(
                    "promotion response failure.detail must be a string"
                )
            if signal_id_raw in seen_failure_signal_ids:
                raise PromotionScopeError(
                    "promotion response failures contains duplicate "
                    f"signalId {signal_id_raw!r}"
                )
            seen_failure_signal_ids.add(signal_id_raw)
            failures.append(
                IncidentPromotionFailure(
                    signal_id=AlertSignalId(signal_id_raw),
                    reason_code=reason_code_raw,
                    detail=detail_raw,
                )
            )

        scanned_signal_ids = _parse_signal_id_list("scannedSignalIds")
        skipped_signal_ids = _parse_signal_id_list("skippedSignalIds")
        opened_incident_ids = _parse_incident_id_list("openedIncidentIds")
        materially_changed_incident_ids = _parse_incident_id_list(
            "materiallyChangedIncidentIds"
        )
        observation_refreshed_incident_ids = _parse_incident_id_list(
            "observationRefreshedIncidentIds"
        )
        unchanged_incident_ids = _parse_incident_id_list("unchangedIncidentIds")

        # R3: strict pairwise-disjointness over all four incident
        # categories. An incident cannot appear in more than one
        # category at the same time; every overlap is rejected with a
        # ``PromotionScopeError``.
        _enforce_pairwise_disjoint(
            opened_incident_ids=opened_incident_ids,
            materially_changed_incident_ids=materially_changed_incident_ids,
            observation_refreshed_incident_ids=observation_refreshed_incident_ids,
            unchanged_incident_ids=unchanged_incident_ids,
        )

        result = cls(
            run_id=HealthRunId(run_id),
            source_identity=source_identity,
            scanned_signal_ids=scanned_signal_ids,
            opened_incident_ids=opened_incident_ids,
            materially_changed_incident_ids=materially_changed_incident_ids,
            observation_refreshed_incident_ids=observation_refreshed_incident_ids,
            unchanged_incident_ids=unchanged_incident_ids,
            skipped_signal_ids=skipped_signal_ids,
            failures=tuple(failures),
        )
        # R3: explicit membership test for ``actionableIncidentIds``.
        # When the field is present we MUST cross-validate it against the
        # computed opened+materially-changed union; the previous
        # double-negative condition was obscure and could mask
        # contradictory payloads. The field is allowed to be absent;
        # when absent we trust the recomputed projection.
        if "actionableIncidentIds" in payload:
            wire_actionable = _parse_incident_id_list("actionableIncidentIds")
            if wire_actionable != result.actionable_incident_ids:
                raise PromotionScopeError(
                    "actionableIncidentIds does not match opened/material changes"
                )
        return result


def parse_promote_alert_signals_request(data: object) -> PromoteAlertSignalsRequest:
    """Strictly parse the internal API wire request or fail closed."""
    if not isinstance(data, dict):
        raise PromotionScopeError("request body must be a JSON object")
    allowed = {"runId", "sourceIdentity", "signalIds"}
    unknown = set(data) - allowed
    if unknown:
        raise PromotionScopeError("request contains unsupported fields")
    for required in allowed:
        if required not in data:
            raise PromotionScopeError(f"{required} is required")
    run_id = data["runId"]
    source_identity = data["sourceIdentity"]
    signal_ids = data["signalIds"]
    if not isinstance(run_id, str) or not isinstance(source_identity, str):
        raise PromotionScopeError("runId and sourceIdentity must be strings")
    if not isinstance(signal_ids, list) or any(
        not isinstance(value, str) for value in signal_ids
    ):
        raise PromotionScopeError("signalIds must be an array of strings")
    return PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )


def _is_safe_id(value: str) -> bool:
    return bool(value) and len(value) <= MAX_ID_LENGTH and _SAFE_ID.fullmatch(value) is not None


def _enforce_pairwise_disjoint(
    *,
    opened_incident_ids: tuple[IncidentId, ...],
    materially_changed_incident_ids: tuple[IncidentId, ...],
    observation_refreshed_incident_ids: tuple[IncidentId, ...],
    unchanged_incident_ids: tuple[IncidentId, ...],
) -> None:
    """Reject any incident ID that appears in more than one category.

    The four incident categories MUST be pairwise disjoint: an incident
    cannot be simultaneously ``opened`` and ``unchanged`` at the same
    time. Every pairwise intersection is rejected with a typed
    :class:`PromotionScopeError` carrying the offending category pair
    so the parser fails closed on internally inconsistent wire payloads.
    """
    opened_set = set(opened_incident_ids)
    materially_set = set(materially_changed_incident_ids)
    observation_set = set(observation_refreshed_incident_ids)
    unchanged_set = set(unchanged_incident_ids)
    pairs = (
        ("opened", "materially_changed", opened_set & materially_set),
        ("opened", "observation_refreshed", opened_set & observation_set),
        ("opened", "unchanged", opened_set & unchanged_set),
        ("materially_changed", "observation_refreshed", materially_set & observation_set),
        ("materially_changed", "unchanged", materially_set & unchanged_set),
        ("observation_refreshed", "unchanged", observation_set & unchanged_set),
    )
    for left, right, overlap in pairs:
        if overlap:
            raise PromotionScopeError(
                "promotion response has overlapping "
                f"{left} and {right} incident IDs: "
                f"{sorted(str(value) for value in overlap)}"
            )


def _stable_unique(values: tuple[IncidentId, ...]) -> tuple[IncidentId, ...]:
    seen: set[str] = set()
    result: list[IncidentId] = []
    for value in values:
        key = str(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _strings(values: tuple[object, ...]) -> list[str]:
    return [str(value) for value in values]


__all__ = [
    "IncidentPromotionFailure",
    "IncidentPromotionResult",
    "MAX_PROMOTION_SIGNAL_IDS",
    "PromoteAlertSignalsRequest",
    "PromotionScopeError",
    "parse_promote_alert_signals_request",
]
