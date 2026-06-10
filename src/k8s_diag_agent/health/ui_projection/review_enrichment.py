"""Review enrichment serialization and status building.

Extracted from health/ui.py to provide a focused module for review enrichment concerns.

This module handles:
- Review enrichment artifact serialization
- Review enrichment policy serialization
- Review enrichment status building
- Adapter registration checks
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from ...external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from ...external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from ...security import sanitize_execution_output
from ...security.deanonymization import deanonymize_review_enrichment, deanonymize_text, safe_alias_mapping
from ..ui_shared import _relative_path

logger = logging.getLogger(__name__)


def _serialize_review_enrichment_policy(policy: ReviewEnrichmentPolicy) -> dict[str, object]:
    """Serialize review enrichment policy to a dict for UI consumption."""
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
    }


def _serialize_review_enrichment(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    fallback: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object] | None:
    """Serialize review enrichment artifact to a dict for UI consumption.

    This function extracts relevant fields from the review enrichment artifact
    and applies de-anonymization to prevent alias leakage.
    """
    artifact = _find_review_enrichment_artifact(artifacts, run_id)
    if not artifact and fallback:
        fallback_entries: list[ExternalAnalysisArtifact] = []
        for raw in fallback:
            if not isinstance(raw, Mapping):
                continue
            try:
                candidate = ExternalAnalysisArtifact.from_dict(raw)
            except (ValueError, KeyError, TypeError):
                continue
            if candidate.run_id != run_id:
                continue
            if candidate.purpose != ExternalAnalysisPurpose.REVIEW_ENRICHMENT:
                continue
            fallback_entries.append(candidate)
        if fallback_entries:
            artifact = sorted(fallback_entries, key=lambda item: item.timestamp, reverse=True)[0]
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}

    # Merge interpretation field (which carries alertmanagerEvidenceReferences) into payload
    # This ensures the bounded evidence references are threaded through to the UI
    if artifact.interpretation and isinstance(artifact.interpretation, Mapping):
        for key, value in artifact.interpretation.items():
            if key not in payload:
                payload[key] = value

    # Apply de-anonymization to review enrichment payload before UI serialization
    # This prevents provider aliases (cluster-a, namespace-f, etc.) from leaking to
    # operator-facing UI fields in ui-index.json
    alias_mapping = safe_alias_mapping(getattr(artifact, "alias_mapping", None))
    if alias_mapping:
        payload = deanonymize_review_enrichment(payload, alias_mapping)

    def _list_from(*keys: str) -> list[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [str(item) for item in value]
            if value is not None:
                return [str(value)]
        return []

    # Extract alertmanager evidence references from merged payload
    alertmanager_refs = payload.get("alertmanagerEvidenceReferences") or payload.get("alertmanager_evidence_references")

    # Sanitize error_summary to prevent credential/exception leakage in operator-facing UI
    sanitized_error_summary, _ = sanitize_execution_output(
        artifact.error_summary,
        artifact.raw_output,
    )
    result: dict[str, object] = {
        "status": artifact.status.value,
        "provider": artifact.provider,
        "timestamp": artifact.timestamp.isoformat(),
        "summary": deanonymize_text(artifact.summary, alias_mapping) if alias_mapping else artifact.summary,
        "triageOrder": _list_from("triageOrder", "triage_order"),
        "topConcerns": _list_from("topConcerns", "top_concerns"),
        "evidenceGaps": _list_from("evidenceGaps", "evidence_gaps"),
        "nextChecks": _list_from("nextChecks", "next_checks"),
        "focusNotes": _list_from("focusNotes", "focus_notes", "caveats", "proposal_caveats"),
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
        "errorSummary": sanitized_error_summary,
        "skipReason": artifact.skip_reason,
    }
    if alertmanager_refs is not None:
        result["alertmanagerEvidenceReferences"] = alertmanager_refs
    return result


def _find_review_enrichment_artifact(artifacts: Sequence[ExternalAnalysisArtifact], run_id: str) -> ExternalAnalysisArtifact | None:
    """Find the most recent review enrichment artifact for a given run_id."""
    from ...external_analysis.utils import artifact_matches_run

    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if artifact.purpose == ExternalAnalysisPurpose.REVIEW_ENRICHMENT and artifact_matches_run(artifact, run_id):
            return artifact
    return None


def _build_review_enrichment_status(
    settings: ExternalAnalysisSettings | None,
    adapters: Iterable[str] | None,
    has_artifact: bool,
    run_config: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Build the review enrichment status dict for UI display.

    This function determines the current state of review enrichment based on:
    - Policy configuration (enabled/disabled)
    - Provider availability
    - Artifact existence for current run
    """
    policy = (settings or ExternalAnalysisSettings()).review_enrichment
    provider_raw = policy.provider or ""
    provider = provider_raw.strip()
    provider_name = provider or None
    if has_artifact:
        return None
    adapter_available = _adapter_registered(provider, adapters) if provider else None
    status = "unknown"
    reason: str | None = None
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        value = run_config.get("provider")
        run_provider_raw = str(value).strip() if value else ""
        run_provider = run_provider_raw or None
    if not policy.enabled:
        status = "policy-disabled"
        reason = "Review enrichment is disabled in the current configuration."
    elif not provider:
        status = "provider-missing"
        reason = "No provider is configured for review enrichment."
    elif adapter_available is False:
        status = "adapter-unavailable"
        reason = f"Adapter '{provider}' is not registered for review enrichment."
    elif not run_config or "enabled" not in run_config or "provider" not in run_config:
        status = "unknown"
        reason = reason or "Review enrichment metadata is incomplete for this run."
    elif run_enabled is False or not run_provider:
        status = "awaiting-next-run"
        if run_provider:
            reason = f"Review enrichment is enabled now, but the latest run was produced before '{run_provider}' was active."
        else:
            reason = "Review enrichment is enabled now, but the latest run predates this setting."
    else:
        status = "not-attempted"
        if run_provider:
            reason = f"Review enrichment was enabled for '{run_provider}' in this run, but no artifact was recorded."
        else:
            reason = "Review enrichment was enabled for this run, but no artifact was recorded."
    return {
        "status": status,
        "reason": reason,
        "provider": provider_name,
        "policyEnabled": policy.enabled,
        "providerConfigured": bool(provider),
        "adapterAvailable": adapter_available,
        "runEnabled": run_enabled,
        "runProvider": run_provider,
    }


def _adapter_registered(provider: str, adapters: Iterable[str] | None) -> bool | None:
    """Check if a provider adapter is registered."""
    if not adapters:
        return None
    normalized = provider.lower()
    for adapter in adapters:
        if adapter and adapter.lower() == normalized:
            return True
    return False
