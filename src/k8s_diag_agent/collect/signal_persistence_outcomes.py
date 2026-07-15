"""Closed union of per-signal persistence outcomes.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 domain model.

The previous contract represented per-signal persistence results as the
``AlertSignalAdapterResult`` counters ``signals_written`` and
``signals_skipped_duplicates``, with ``signals_failed`` as a separate
counter. Authority decisions were reconstructed from those counters at
orchestration boundaries, which let a successful identity-match
observation be silently collapsed into ``signals_skipped_duplicates``
and removed from the current-run promotion workset.

This module replaces that counter-based authority with a closed union
of typed per-signal outcomes. The orchestrator decides
promotion-workset membership by inspecting the outcome variants, never
by reading free-form integers.

Outcomes:

* :class:`SignalInserted` -- the artifact was newly written.
* :class:`SignalIdentityMatched` -- an artifact with the same immutable
  identity already existed; the observation still belongs to the
  current run.
* :class:`SignalIdentityConflict` -- an existing artifact shares the
  storage key but its canonical identity differs. The current-run
  workset MUST NOT admit conflicting duplicates.
* :class:`SignalPersistenceFailed` -- the persistence call raised or
  returned an unusable result. The current-run workset MUST NOT admit
  failed observations.

Counts are projections: ``inserted_count``,
``identity_matched_count``, ``identity_conflict_count`` and
``persistence_failure_count`` are derived from the outcome sequence
and not independently maintained.

Free-form detail is attached only as a diagnostic artifact. It MUST
NOT drive authority decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class SignalIdentityConflictCode(StrEnum):
    """Bounded reason codes for identity-conflicting duplicates.

    Identity conflicts are distinct from persistence failures: the
    storage call succeeded but produced an artifact whose canonical
    identity disagrees with the current observation. The conflict code
    is the only authoritative policy input; ``detail`` carries optional
    diagnostic context that MUST NOT branch authority.
    """

    DIFFERENT_FINGERPRINT = "different_fingerprint"
    """The existing artifact's external fingerprint differs."""

    DIFFERENT_SOURCE_IDENTITY = "different_source_identity"
    """The existing artifact belongs to a different source instance."""

    DIFFERENT_ALERTNAME = "different_alertname"
    """The alertname changed; storage key collided but signal changed."""

    DIFFERENT_LABELS = "different_labels"
    """Stable label set changed; storage key collided but signal changed."""

    DIFFERENT_IDENTITY_HASH = "different_identity_hash"
    """Identity hash changed under same storage key (schema validation)."""


class SignalPersistenceFailureCode(StrEnum):
    """Bounded reason codes for persistence failures.

    Free-form exception messages are not enumerated here; callers may
    attach a bounded diagnostic detail but authority decisions MUST
    only branch on this enum.
    """

    IO_ERROR = "io_error"
    """Filesystem or artifact write failed."""

    SCHEMA_ERROR = "schema_error"
    """Persisted artifact could not be parsed or validated."""

    CONTRACT_VIOLATION = "contract_violation"
    """Persistence contract was violated (e.g. missing identity)."""

    TRANSPORT_ERROR = "transport_error"
    """Cross-process transport failed."""

    UNKNOWN_ERROR = "unknown_error"
    """Catch-all for unexpected exceptions. Use sparingly."""


@dataclass(frozen=True, slots=True)
class SignalInserted:
    """Outcome: a new alert-signal artifact was successfully written."""

    signal_id: str
    """Canonical identity of the newly written artifact."""


@dataclass(frozen=True, slots=True)
class SignalIdentityMatched:
    """Outcome: an artifact with the same canonical identity exists.

    The duplicate observation belongs to the current-run promotion
    workset because the artifact identity is the same immutable key
    the backend uses to scope membership.
    """

    signal_id: str
    """Canonical identity that was already present on disk."""


@dataclass(frozen=True, slots=True)
class SignalIdentityConflict:
    """Outcome: existing artifact has a conflicting canonical identity.

    The storage key collided (same filename) but the canonical
    immutable identity differs. The current-run workset MUST NOT admit
    this observation.
    """

    signal_id: str
    """Canonical identity the caller attempted to persist."""

    existing_artifact_identity: str | None
    """Identity of the previously stored artifact, when known."""

    reason: SignalIdentityConflictCode
    """Closed reason code for the conflict."""

    detail: str | None = None
    """Optional bounded diagnostic detail. Never drives authority."""


@dataclass(frozen=True, slots=True)
class SignalPersistenceFailed:
    """Outcome: persistence call failed and the observation is unusable.

    The current-run workset MUST NOT admit this outcome. The candidate
    signal id may be ``None`` when the failure occurred before a
    canonical identity was assigned.
    """

    candidate_signal_id: str | None
    """Signal id that was being persisted, when known."""

    reason: SignalPersistenceFailureCode
    """Closed reason code for the failure."""

    detail: str | None = None
    """Optional bounded diagnostic detail. Never drives authority."""


# Closed union -- exhaustively matched where used.
SignalPersistenceOutcome = (
    SignalInserted
    | SignalIdentityMatched
    | SignalIdentityConflict
    | SignalPersistenceFailed
)


def is_promotable(outcome: SignalPersistenceOutcome) -> bool:
    """Return True when the outcome admits the signal into the workset.

    The current-run promotion workset is exactly:

        SignalInserted ∪ SignalIdentityMatched

    Conflicts and failures are excluded.
    """
    return isinstance(outcome, (SignalInserted, SignalIdentityMatched))


@dataclass(frozen=True, slots=True)
class SignalPersistenceSummary:
    """Projection of a sequence of signal persistence outcomes.

    Counts are derived from the outcomes; they are not separately
    maintained authority. The sequence itself is preserved verbatim.
    """

    outcomes: tuple[SignalPersistenceOutcome, ...]

    @property
    def inserted_count(self) -> int:
        """Count of :class:`SignalInserted` outcomes."""
        return sum(1 for item in self.outcomes if isinstance(item, SignalInserted))

    @property
    def identity_matched_count(self) -> int:
        """Count of :class:`SignalIdentityMatched` outcomes."""
        return sum(
            1 for item in self.outcomes if isinstance(item, SignalIdentityMatched)
        )

    @property
    def identity_conflict_count(self) -> int:
        """Count of :class:`SignalIdentityConflict` outcomes."""
        return sum(
            1 for item in self.outcomes if isinstance(item, SignalIdentityConflict)
        )

    @property
    def persistence_failure_count(self) -> int:
        """Count of :class:`SignalPersistenceFailed` outcomes."""
        return sum(
            1 for item in self.outcomes if isinstance(item, SignalPersistenceFailed)
        )

    @property
    def promotable_count(self) -> int:
        """Count of observations that belong to the current-run workset.

        Equivalent to ``inserted_count + identity_matched_count``.
        """
        return self.inserted_count + self.identity_matched_count

    @property
    def has_conflicts(self) -> bool:
        """True if any observation produced an identity conflict."""
        return self.identity_conflict_count > 0

    @property
    def has_failures(self) -> bool:
        """True if any observation produced a persistence failure."""
        return self.persistence_failure_count > 0


__all__ = [
    "SignalIdentityConflictCode",
    "SignalIdentityConflict",
    "SignalIdentityMatched",
    "SignalInserted",
    "SignalPersistenceFailed",
    "SignalPersistenceFailureCode",
    "SignalPersistenceOutcome",
    "SignalPersistenceSummary",
    "is_promotable",
]
