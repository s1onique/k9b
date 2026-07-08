"""Incident promotion dispatcher.

This module selects the appropriate promotion path (local vs backend-api) based on
configuration and provides a unified interface for scheduler incident promotion.

Hard constraints enforced:
- NO scheduler direct SQLite writes
- NO scheduler SQLiteIncidentStore instantiation
- NO remediation actions
- NO LLM calls from the promotion transport layer
- Internal promotion must use K9B_INTERNAL_API_TOKEN bearer auth

Configuration:
- K9B_INCIDENT_PROMOTION_MODE: local|backend-api|auto (default: auto)
- K9B_BACKEND_INTERNAL_URL: Backend service URL for backend-api mode
- K9B_INTERNAL_API_TOKEN: Token for internal API authentication
- K9B_INCIDENT_STORE_BACKEND: Backend type (memory|file|sqlite)
- K9B_PROCESS_ROLE: Process role (backend|scheduler)

Behavior:
- local: Use existing local get_incident_store() promotion path
- backend-api: Post to backend internal API (required for scheduler+sqlite)
- auto: Use backend-api if K9B_INCIDENT_STORE_BACKEND=sqlite or K9B_PROCESS_ROLE=scheduler
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .incident_candidates import (
    CandidateSignal,
    IncidentCandidate,
)

_logger = logging.getLogger(__name__)

# Environment variables
ENV_PROMOTION_MODE = "K9B_INCIDENT_PROMOTION_MODE"
ENV_BACKEND_URL = "K9B_BACKEND_INTERNAL_URL"
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Promotion modes
MODE_LOCAL: Literal["local"] = "local"
MODE_BACKEND_API: Literal["backend-api"] = "backend-api"
MODE_AUTO: Literal["auto"] = "auto"

# Process roles
ROLE_BACKEND = "backend"
ROLE_SCHEDULER = "scheduler"


@dataclass(frozen=True)
class IncidentPromotionDispatchConfig:
    """Configuration for incident promotion dispatcher."""

    mode: Literal["local", "backend-api", "auto"]
    backend_url: str | None
    internal_api_token: str | None
    store_backend: str
    process_role: str

    def resolved_mode(self) -> Literal["local", "backend-api"]:
        """Resolve auto mode to concrete mode."""
        if self.mode == MODE_LOCAL:
            return MODE_LOCAL
        if self.mode == MODE_BACKEND_API:
            return MODE_BACKEND_API
        # Auto mode
        if self.store_backend == "sqlite":
            return MODE_BACKEND_API
        if self.process_role == ROLE_SCHEDULER:
            return MODE_BACKEND_API
        return MODE_LOCAL

    def requires_backend_api(self) -> bool:
        """Check if backend API is required for promotion."""
        return self.resolved_mode() == MODE_BACKEND_API

    def can_use_local(self) -> bool:
        """Check if local promotion is allowed."""
        resolved = self.resolved_mode()
        if resolved == MODE_LOCAL:
            if self.process_role == ROLE_SCHEDULER and self.store_backend == "sqlite":
                return False
            return True
        return False

    def is_config_valid(self) -> tuple[bool, str | None]:
        """Validate configuration for the resolved mode."""
        if self.resolved_mode() == MODE_BACKEND_API:
            if not self.backend_url:
                return False, "missing_backend_url"
            if not self.internal_api_token:
                return False, "missing_internal_api_token"
        return True, None


@dataclass(frozen=True)
class IncidentPromotionResult:
    """Result of an incident promotion operation."""

    ok: bool = True
    scanned: int = 0
    firing: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: tuple[str, ...] = field(default_factory=tuple)
    # Track the mode used for correct event logging
    promotion_mode: Literal["local", "backend-api"] = "local"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for logging/response."""
        return {
            "ok": self.ok,
            "scanned": self.scanned,
            "firing": self.firing,
            "opened_incidents": self.opened_incidents,
            "updated_incidents": self.updated_incidents,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": self.errors,
            "error_messages": list(self.error_messages),
            "promotion_mode": self.promotion_mode,
        }


def _get_dispatch_config() -> IncidentPromotionDispatchConfig:
    """Get the current dispatch configuration from environment."""
    return IncidentPromotionDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, MODE_AUTO).lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )


def _result_from_dict(
    d: dict[str, Any], promotion_mode: Literal["local", "backend-api"] = "local"
) -> IncidentPromotionResult:
    """Convert promotion dict to IncidentPromotionResult."""
    return IncidentPromotionResult(
        ok=d.get("ok", False),
        scanned=d.get("scanned", 0),
        firing=d.get("firing", 0),
        opened_incidents=d.get("opened_incidents", 0),
        updated_incidents=d.get("updated_incidents", 0),
        skipped_duplicates=d.get("skipped_duplicates", 0),
        errors=d.get("errors", 0),
        error_messages=tuple(d.get("error_messages", [])),
        promotion_mode=promotion_mode,
    )


def promote_candidates(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote incident candidates via configured path.

    This is the main entry point for scheduler health-loop promotion.

    Args:
        candidates: List of candidates to promote
        observed_at: When candidates were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    if resolved == MODE_LOCAL:
        if not config.can_use_local():
            _logger.error(
                "Local promotion forbidden for scheduler+sqlite mode",
                extra={
                    "event": "incident-promotion-config-invalid",
                    "reason": "scheduler_sqlite_forbidden",
                    "process_role": config.process_role,
                    "store_backend": config.store_backend,
                },
            )
            return IncidentPromotionResult(
                ok=False,
                scanned=len(candidates),
                errors=1,
                error_messages=(
                    "Local promotion forbidden: scheduler cannot use SQLite store directly",
                ),
            )
        from .incident_promotion_local import promote_local

        return _result_from_dict(promote_local(candidates, observed_at, snapshot_bundle_id), MODE_LOCAL)

    # Backend API mode
    from .incident_promotion_backend import promote_via_backend_api

    return _result_from_dict(promote_via_backend_api(candidates, observed_at, snapshot_bundle_id), MODE_BACKEND_API)


def promote_alert_signals(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote alert signal candidates via configured path.

    This is the main entry point for Alertmanager alert signal promotion.

    Args:
        candidates: List of alert signal candidates to promote
        observed_at: When signals were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    _logger.info(
        "Alert signal promotion requested",
        extra={
            "event": "alert-signals-promotion-start"
            if resolved == MODE_LOCAL
            else "alert-signals-promotion-start-via-backend",
            "promotion_mode": resolved,
            "candidate_count": len(candidates),
            "snapshot_bundle_id": snapshot_bundle_id,
        },
    )

    if resolved == MODE_LOCAL:
        if not config.can_use_local():
            _logger.error(
                "Local promotion forbidden for scheduler+sqlite mode",
                extra={
                    "event": "incident-promotion-config-invalid",
                    "reason": "scheduler_sqlite_forbidden",
                    "process_role": config.process_role,
                    "store_backend": config.store_backend,
                },
            )
            return IncidentPromotionResult(
                ok=False,
                scanned=len(candidates),
                errors=1,
                error_messages=(
                    "Local promotion forbidden: scheduler cannot use SQLite store directly",
                ),
            )
        from .incident_promotion_local import promote_local

        result = _result_from_dict(promote_local(candidates, observed_at, snapshot_bundle_id), MODE_LOCAL)
        _logger.info(
            "Alert signals promoted",
            extra={
                "event": "alert-signals-promoted",
                "promotion_mode": MODE_LOCAL,
                "scanned": result.scanned,
                "firing": result.firing,
                "opened_incidents": result.opened_incidents,
                "updated_incidents": result.updated_incidents,
                "skipped_duplicates": result.skipped_duplicates,
                "errors": result.errors,
            },
        )
        return result

    # Backend API mode - use alert-signals specific endpoint
    from .incident_promotion_backend import promote_alert_signals_via_backend_api

    _logger.info(
        "Alert signal promotion via backend API",
        extra={
            "event": "alert-signals-promotion-via-backend",
            "promotion_mode": "backend-api",
            "backend_url": config.backend_url,
            "candidate_count": len(candidates),
        },
    )

    result = _result_from_dict(
        promote_alert_signals_via_backend_api(candidates, observed_at, snapshot_bundle_id),
        MODE_BACKEND_API,
    )
    _logger.info(
        "Alert signals promoted via backend",
        extra={
            "event": "alert-signals-promoted-via-backend",
            "promotion_mode": MODE_BACKEND_API,
            "backend_url": config.backend_url,
            "scanned": result.scanned,
            "firing": result.firing,
            "opened_incidents": result.opened_incidents,
            "updated_incidents": result.updated_incidents,
            "skipped_duplicates": result.skipped_duplicates,
            "errors": result.errors,
        },
    )
    return result


def log_promotion_config() -> None:
    """Log the current promotion configuration at startup."""
    config = _get_dispatch_config()
    resolved = config.resolved_mode()
    is_valid, error = config.is_config_valid()

    if is_valid:
        _logger.info(
            "Incident promotion configured",
            extra={
                "event": "incident-promotion-configured",
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )
    else:
        _logger.error(
            "Incident promotion configuration invalid",
            extra={
                "event": "incident-promotion-config-invalid",
                "reason": error,
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )


def scan_alert_signals_as_candidates(runs_dir: Path) -> list[IncidentCandidate]:
    """Scan persisted alert signals and convert to candidates for API promotion.

    Args:
        runs_dir: The runs directory containing alert signal artifacts

    Returns:
        List of IncidentCandidates ready for promotion
    """
    from ..incident_alert_classifier import classify_alert_signal
    from ..incident_alert_correlation import build_alert_incident_correlation_key
    from ..incident_alert_promotion import (
        _build_alert_message,
        _map_alert_class_to_candidate_class,
        _map_entity_kind_to_object_kind,
        _map_severity,
    )
    from ..incident_alert_signal_reader import scan_alert_signal_artifacts

    candidates: list[IncidentCandidate] = []
    seen_keys: set[str] = set()

    for artifact in scan_alert_signal_artifacts(runs_dir):
        try:
            if artifact.signal is None:
                continue
            signal = artifact.signal
            if signal.status.value != "firing":
                continue

            classification = classify_alert_signal(signal)
            correlation_key = build_alert_incident_correlation_key(signal, classification)
            if correlation_key in seen_keys:
                continue
            seen_keys.add(correlation_key)

            # Build candidate
            candidate_class = _map_alert_class_to_candidate_class(classification.class_)
            severity = _map_severity(signal.severity)
            object_kind = _map_entity_kind_to_object_kind(classification.entity_kind)

            candidates.append(
                IncidentCandidate(
                    candidate_id=correlation_key,
                    namespace=classification.namespace,
                    object_kind=object_kind,
                    object_name=classification.entity_name,
                    candidate_class=candidate_class,
                    severity=severity,
                    signals=(
                        CandidateSignal(
                            source="alert",
                            reason=signal.alertname,
                            message=_build_alert_message(signal),
                        ),
                    ),
                    evidence_needed=("alert_evidence",),
                )
            )
        except Exception:
            _logger.exception("Error scanning alert signal artifact %s", artifact.identity)

    return candidates


def promote_alert_signals_from_artifacts(
    runs_dir: Path,
    snapshot_bundle_id: str | None = None,
) -> IncidentPromotionResult:
    """Promote alert signals from persisted artifacts.

    Args:
        runs_dir: The runs directory containing alert signal artifacts
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        IncidentPromotionResult with promotion counts
    """
    from datetime import UTC

    candidates = scan_alert_signals_as_candidates(runs_dir)
    if not candidates:
        return IncidentPromotionResult(
            ok=True, scanned=0, firing=0, opened_incidents=0,
            updated_incidents=0, skipped_duplicates=0, errors=0,
        )
    return promote_alert_signals(
        candidates=candidates,
        observed_at=datetime.now(UTC),
        snapshot_bundle_id=snapshot_bundle_id,
    )


__all__ = [
    "IncidentPromotionDispatchConfig",
    "IncidentPromotionResult",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
    "promote_alert_signals",
    "promote_alert_signals_from_artifacts",
    "promote_candidates",
    "log_promotion_config",
    "scan_alert_signals_as_candidates",
]
