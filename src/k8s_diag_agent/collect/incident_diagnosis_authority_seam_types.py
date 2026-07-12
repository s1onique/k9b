"""Shared types for the automatic-diagnosis authority seam.

This module exists to break the circular import between the seam
(:mod:`incident_diagnosis_authority_seam`), the local-mode writer
(:mod:`incident_diagnosis_authority_seam_local`), and the backend-mode
writer (:mod:`incident_diagnosis_authority_seam_backend`).

It owns the closed vocabulary (:class:`LifecycleTransition`,
:class:`LifecycleDispatchMode`), the bounded typed write outcomes
(:class:`LifecycleWriteApplied` / :class:`LifecycleWriteRejected` /
:class:`LifecycleWriteFailed` / :class:`LifecycleWriteSkipped`), the
:class:`LifecycleWriteOutcome` union, and the wire-schema version
constant.

Callers MUST import the public types from the seam module
(:mod:`incident_diagnosis_authority_seam`), which re-exports them. The
sibling dispatch modules import directly from this types module to
avoid a circular import cycle.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, TypeAlias

# Lifecycle-transition request/response schema version. The backend
# internal endpoint and the scheduler client MUST agree on this value.
# A request carrying an unsupported schema version is rejected by the
# backend handler with HTTP 400 (unsupported request schema), which the
# response translator maps to ``LifecycleWriteRejected``. This 400
# contract is canonical across server behavior, client translation,
# documentation, and tests.
LIFECYCLE_SCHEMA_VERSION: Final[int] = 1


class LifecycleTransition(StrEnum):
    """Closed vocabulary of automatic-diagnosis lifecycle transitions.

    The backend internal lifecycle endpoint, the scheduler-side client,
    and the aggregate store delegate ALL route through this enum so the
    transition string is never authored as a free literal at any call
    site.
    """

    STARTED = "started"
    FAILED = "failed"
    COMPLETED = "completed"


class LifecycleDispatchMode(StrEnum):
    """The active dispatch mode for lifecycle writes.

    Mirrors the incident-detail dispatch mode so a single configuration
    resolution drives both reads and writes.
    """

    LOCAL = "local"
    BACKEND = "backend"


@dataclass(frozen=True, slots=True)
class LifecycleWriteApplied:
    """The authority applied the requested lifecycle transition.

    For backend mode ``idempotent_replay`` is set when the backend
    recognised a previously-applied identical transition and did not
    duplicate any side effects. ``http_status`` is set to the observed
    response status for backend mode and is ``None`` for local mode.
    """
    transition: LifecycleTransition
    incident_id: str
    applied: Literal[True] = True
    idempotent_replay: bool = False
    http_status: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class LifecycleWriteRejected:
    """The authority rejected the transition with a bounded reason.

    A ``LifecycleWriteRejected`` is the typed equivalent of HTTP 4xx
    responses that are NOT ``404`` (which is mapped to
    ``LifecycleWriteFailed``). The scheduler MUST surface this without
    silent fallback to local storage.
    """
    transition: LifecycleTransition
    incident_id: str
    reason_code: str
    applied: Literal[False] = False
    http_status: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class LifecycleWriteFailed:
    """The lifecycle write failed for a non-business reason.

    Covers transport errors, 5xx responses, 404 (incident not found in
    the backend store), and authentication failures. The scheduler MUST
    NOT silently fall back to local storage when this outcome is
    returned; the operator must observe the failure.
    """
    transition: LifecycleTransition
    incident_id: str
    reason_code: str
    applied: Literal[False] = False
    http_status: int | None = None
    detail: str | None = None
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class LifecycleWriteSkipped:
    """The lifecycle write was deliberately skipped (e.g. local mode has no
    authoritative backend store, or the resolver refused to dispatch).

    This is the ONLY outcome that does not imply a transport or backend
    failure. It is used to make ``Authority-aware dispatch refused to
    operate in this mode`` explicit so the scheduler can decide whether
    the missing write is acceptable.
    """
    transition: LifecycleTransition
    incident_id: str
    reason: str
    applied: Literal[False] = False


LifecycleWriteOutcome: TypeAlias = (
    LifecycleWriteApplied
    | LifecycleWriteRejected
    | LifecycleWriteFailed
    | LifecycleWriteSkipped
)
