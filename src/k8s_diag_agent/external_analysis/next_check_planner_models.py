"""Models, enums, and constants for next-check planner.

Extracted from next_check_planner.py to reduce file size and improve modularity.
"""

from __future__ import annotations

import re as re_module
from enum import StrEnum

# These are kubectl verbs that are genuinely mutating and should require approval.
# Important: Order matters for the regex-based detection to avoid false positives.
# - "describe" is NOT mutating (read-only operation, used for inspection)
# - "label" and "annotate" are mutating but must be matched as whole words
MUTATION_KEYWORDS = (
    # Core mutating kubectl verbs (word-boundary matched)
    r"\bapply\b",
    r"\bdelete\b",
    r"\bscale\b",
    r"\bpatch\b",
    r"\breplace\b",
    r"\bcreate\b",
    r"\bedit\b",
    r"\blabel\b",
    r"\bannotate\b",
    # rollout is mutating when followed by certain subcommands
    r"\brollout\b",
    # cordon, uncordon, drain are mutating node operations
    r"\bcordon\b",
    r"\buncordon\b",
    r"\bdrain\b",
    # exec into pod is potentially mutating
    r"\bexec\b",
    # set commands that modify resources
    r"\bset\s+",  # e.g., kubectl set image, kubectl set env
    # port-forward is not strictly mutating but can be security-sensitive
    # upgrade is a cluster operation
    r"\bupgrade\b",
)


class CommandFamily(StrEnum):
    KUBECTL_GET = "kubectl-get"
    KUBECTL_DESCRIBE = "kubectl-describe"
    KUBECTL_LOGS = "kubectl-logs"
    KUBECTL_GET_CRD = "kubectl-get-crd"
    KUBECTL_TOP = "kubectl-top"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostEstimate(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NormalizationReason(StrEnum):
    SELECTION_LABEL = "selection_label"
    SELECTION_CONTEXT = "selection_context"
    SELECTION_DEFAULT = "selection_default"
    SUMMARY_FALLBACK = "summary_fallback"
    UNKNOWN = "unknown"


class SafetyReason(StrEnum):
    KNOWN_COMMAND = "known_command"
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE_EVIDENCE = "duplicate_evidence"


class ApprovalReason(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    GENERIC = "requires_operator_approval"


class DuplicateReason(StrEnum):
    EXACT_MATCH = "exact_match"
    OVERLAP = "overlap"


class BlockingReason(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    MUTATION_DETECTED = "mutation_detected"
    DUPLICATE = "duplicate"
    REQUIRES_APPROVAL = "requires_approval"
    COMMAND_NOT_ALLOWED = "command_not_allowed"
    MISSING_DESCRIPTION = "missing_description"
    MISSING_CONTEXT = "missing_context"


# Re-export for backward compatibility
__all__ = [
    # Enums
    "CommandFamily",
    "RiskLevel",
    "CostEstimate",
    "NormalizationReason",
    "SafetyReason",
    "ApprovalReason",
    "DuplicateReason",
    "BlockingReason",
    # Constants
    "MUTATION_KEYWORDS",
    # Functions
    "detect_command_family",
    "detect_expected_signal",
    "_mentions_mutation",
    "_risk_from_family",
    "_confidence_level",
    "_cost_from_risk",
    "_normalize_text",
]


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def detect_command_family(text: str) -> CommandFamily:
    normalized = text.lower()
    if "kubectl logs" in normalized or "logs" in normalized and "kubectl" in normalized:
        return CommandFamily.KUBECTL_LOGS
    if "kubectl describe" in normalized or "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    if "kubectl top" in normalized:
        return CommandFamily.KUBECTL_TOP
    if "kubectl get" in normalized:
        if "crd" in normalized:
            return CommandFamily.KUBECTL_GET_CRD
        return CommandFamily.KUBECTL_GET
    if "describe" in normalized:
        return CommandFamily.KUBECTL_DESCRIBE
    return CommandFamily.UNKNOWN


def detect_expected_signal(text: str) -> str | None:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ("logs", "log file", "pod logs")):
        return "logs"
    if any(keyword in normalized for keyword in ("event", "events", "warning")):
        return "events"
    if any(keyword in normalized for keyword in ("metric", "latency", "cpu", "memory", "iops")):
        return "metrics"
    if any(keyword in normalized for keyword in ("rollout", "deployment", "replica", "cronjob")):
        return "rollout"
    if any(keyword in normalized for keyword in ("storage", "pvc", "volume")):
        return "storage"
    return None


def _mentions_mutation(text: str) -> bool:
    normalized = text.lower()
    # Use word-boundary aware regex matching to avoid false positives
    # e.g., "describe" should NOT match "set" (it's not a mutation)
    return any(re_module.search(pattern, normalized) for pattern in MUTATION_KEYWORDS)


def _risk_from_family(family: CommandFamily) -> RiskLevel:
    if family in (CommandFamily.KUBECTL_LOGS, CommandFamily.KUBECTL_DESCRIBE, CommandFamily.KUBECTL_TOP):
        return RiskLevel.LOW
    if family in (CommandFamily.KUBECTL_GET, CommandFamily.KUBECTL_GET_CRD):
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _confidence_level(safe: bool, family: CommandFamily) -> str:
    if safe and family != CommandFamily.UNKNOWN:
        return "high"
    if family == CommandFamily.UNKNOWN:
        return "low"
    return "medium"


def _cost_from_risk(risk: RiskLevel) -> CostEstimate:
    if risk == RiskLevel.LOW:
        return CostEstimate.LOW
    if risk == RiskLevel.MEDIUM:
        return CostEstimate.MEDIUM
    return CostEstimate.HIGH
