"""Handoff serializers for automatic diagnosis review packets.

This module provides serialization functions for the automatic diagnosis
review handoff API payload. The handoff provides a bounded, sanitized
markdown summary suitable for human/ChatGPT review.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only for this module)
- NO raw packet contents beyond bounded summary fields
- NO absolute paths
- NO secrets, tokens, or kubeconfig
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..observability import trace_automatic_diagnosis_review_load
from .api_payloads_incident_reads import (
    AutomaticDiagnosisReviewHandoffPayload,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "build_automatic_diagnosis_review_handoff_payload",
    "MAX_HANDOFF_CONTENT_LENGTH",
]


# =============================================================================
# Constants for field bounds (safety)
# =============================================================================

MAX_HANDOFF_CONTENT_LENGTH = 16 * 1024  # 16 KiB
MAX_ARTIFACT_NAME_LENGTH = 240
MAX_RUN_ID_LENGTH = 160
MAX_COLLECTOR_RUN_ID_LENGTH = 160
MAX_DECISION_LENGTH = 120
MAX_ELIGIBILITY_REASON_LENGTH = 160
MAX_GENERATED_AT_LENGTH = 80
MAX_CONTENT_SHA256_LENGTH = 64


# =============================================================================
# Forbidden patterns for safety validation
# =============================================================================

# These are specific patterns that would indicate data leakage.
# Avoid overly broad terms like "authorization" or "token" alone,
# which appear in legitimate review instructions.

_FORBIDDEN_CONTENT_PATTERNS: list[tuple[str, str]] = [
    # Raw data fields (exact matches for field names)
    ("raw_case_file", "raw case file"),
    ("runner_result", "runner result"),
    ("selected_checks", "selected checks"),
    # Paths and locations
    ("artifact_path", "artifact path"),
    ("absolute_path", "absolute path"),
    # Credentials (specific forms)
    ("bearer ", "bearer token"),
    ("auth_token", "auth token"),
    ("authorization: ", "authorization header"),
    ("x-api-key", "api key header"),
    # Secrets
    ("kubeconfig", "kubeconfig"),
    (":secret", "secret value"),
    ("password=", "password value"),
    ("api_key", "api key value"),
    # Action terms in unsafe contexts
    ("kubectl apply", "kubectl apply"),
    ("kubectl delete", "kubectl delete"),
    ("kubectl patch", "kubectl patch"),
    ("kubectl scale", "kubectl scale"),
    ("kubectl exec", "kubectl exec"),
    ("helm install", "helm install"),
    ("helm upgrade", "helm upgrade"),
    ("remediate", "remediate action"),
    ("rollout restart", "rollout restart"),
]


# =============================================================================
# Serializer Functions
# =============================================================================


def _bound(value: str | None, max_length: int) -> str | None:
    """Bound a string value to a maximum length."""
    if value is None:
        return None
    return value[:max_length]


def _validate_handoff_content(content: str) -> bool:
    """Validate that handoff content doesn't contain forbidden patterns.

    This is a safety check to ensure the sanitized content doesn't
    accidentally include forbidden patterns that would indicate data leakage.

    Args:
        content: The handoff content to validate

    Returns:
        True if content is safe, False if forbidden patterns are present
    """
    content_lower = content.lower()
    for pattern, _ in _FORBIDDEN_CONTENT_PATTERNS:
        if pattern in content_lower:
            return False
    return True


def build_automatic_diagnosis_review_handoff_payload(
    external_analysis_dir: Path | None,
    incident_id: str,
) -> AutomaticDiagnosisReviewHandoffPayload:
    """Build AutomaticDiagnosisReviewHandoffPayload from latest review packet.

    This function loads and transforms the latest automatic diagnosis loop
    review packet into a bounded, sanitized markdown handoff suitable for
    human/ChatGPT review.

    The handoff content is intentionally compact and review-oriented.
    It includes only safe summary fields and explicit review guidance.

    Args:
        external_analysis_dir: Path to external-analysis directory, or None
        incident_id: The incident ID to search for

    Returns:
        AutomaticDiagnosisReviewHandoffPayload with available=True and handoff fields,
        or available=False with unavailable_reason when no packet exists
        or packet is malformed.

    Safety constraints enforced:
    - artifact_name is filename only (no path)
    - All string fields are bounded to safe maximum lengths
    - content is bounded to 16 KiB max
    - content is validated for forbidden terms
    - content includes explicit read-only/review-required/no-remediation language
    - read_only is always True
    - review_required_before_any_action is always True
    - no_remediation_attempted is always True

    Hard constraints:
    - NO remediation actions
    - NO raw packet contents beyond bounded summary fields
    - NO absolute paths
    - NO secrets, tokens, or kubeconfig
    """
    def _build_payload() -> AutomaticDiagnosisReviewHandoffPayload:
        if external_analysis_dir is None:
            return {
                "available": False,
                "unavailable_reason": "no_review_packet",
            }

        # Import here to avoid circular dependencies and keep this module read-only
        try:
            from ..collect.incident_diagnosis_review_packet import (
                load_review_packet_for_handoff,
            )
            from ..collect.incident_diagnosis_review_packet_exceptions import (
                AutomaticDiagnosisReviewPacketUnavailable,
            )
        except ImportError:
            return {
                "available": False,
                "unavailable_reason": "malformed_review_packet",
            }

        try:
            packet_data = load_review_packet_for_handoff(external_analysis_dir, incident_id)
        except AutomaticDiagnosisReviewPacketUnavailable:
            # Packet exists but couldn't be loaded (I/O error, malformed JSON)
            return {
                "available": False,
                "unavailable_reason": "malformed_review_packet",
            }

        if packet_data is None:
            return {
                "available": False,
                "unavailable_reason": "no_review_packet",
            }

        # Extract safe summary fields from packet
        run_id = packet_data.get("run_id")
        collector_run_id = packet_data.get("collector_run_id")
        generated_at = packet_data.get("generated_at")
        decision = packet_data.get("decision")
        checks_requested = packet_data.get("checks_requested", 0)
        checks_run = packet_data.get("checks_run", 0)
        checks_rejected = packet_data.get("checks_rejected", 0)
        eligible = packet_data.get("eligible")
        eligibility_reason = packet_data.get("eligibility_reason")

        # Build artifact name from run_id (filename only)
        artifact_name = f"{run_id}-diagnosis-review-packet.json" if run_id else None

        # Build handoff content (markdown)
        content_parts: list[str] = []

        content_parts.append("# Automatic diagnosis review packet")
        content_parts.append("")
        content_parts.append(f"Incident: {incident_id}")
        content_parts.append(f"Generated: {generated_at or 'unknown'}")
        content_parts.append(f"Run ID: {run_id or 'unknown'}")

        # Artifact name (filename only)
        if artifact_name:
            content_parts.append(f"Artifact: {artifact_name}")

        content_parts.append("")
        content_parts.append("## Safety")
        content_parts.append("")
        content_parts.append("This is read-only evidence.")
        content_parts.append("Review is required before any action.")
        content_parts.append("No remediation was attempted.")
        content_parts.append("")
        content_parts.append("## Decision")
        content_parts.append("")
        content_parts.append(decision or "no decision recorded")

        content_parts.append("")
        content_parts.append("## Check counts")
        content_parts.append("")
        content_parts.append(f"Requested: {checks_requested}")
        content_parts.append(f"Run: {checks_run}")
        content_parts.append(f"Rejected: {checks_rejected}")

        content_parts.append("")
        content_parts.append("## Eligibility")
        content_parts.append("")
        content_parts.append(f"Eligible: {'true' if eligible else 'false'}")
        content_parts.append(f"Reason: {eligibility_reason or 'unknown'}")

        content_parts.append("")
        content_parts.append("## Review instructions")
        content_parts.append("")
        content_parts.append("Use this packet to review diagnosis evidence only.")
        content_parts.append("Do not infer authorization to mutate the cluster.")
        content_parts.append("Do not recommend unsafe actions without explicit operator review.")

        content = "\n".join(content_parts)

        # Bound content to maximum length
        if len(content) > MAX_HANDOFF_CONTENT_LENGTH:
            content = content[:MAX_HANDOFF_CONTENT_LENGTH]

        # Validate content for forbidden terms
        if not _validate_handoff_content(content):
            # Content contains forbidden terms - this shouldn't happen but handle safely
            return {
                "available": False,
                "unavailable_reason": "malformed_review_packet",
            }

        # Compute content SHA256 (first 16 chars for brevity)
        import hashlib
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

        return {
            "available": True,
            "incident_id": incident_id,
            "artifact_type": "diagnosis-loop-review-packet",
            "artifact_name": _bound(artifact_name, MAX_ARTIFACT_NAME_LENGTH),
            "run_id": _bound(run_id, MAX_RUN_ID_LENGTH),
            "collector_run_id": _bound(collector_run_id, MAX_COLLECTOR_RUN_ID_LENGTH),
            "generated_at": _bound(generated_at, MAX_GENERATED_AT_LENGTH),
            "format": "markdown",
            "content": content,
            "content_sha256": content_sha256,
            "read_only": True,
            "review_required_before_any_action": True,
            "no_remediation_attempted": True,
        }

    return trace_automatic_diagnosis_review_load(  # type: ignore[no-any-return]
        _build_payload,
        attributes={"k9b.artifact_kind": "review_packet"},
    )
