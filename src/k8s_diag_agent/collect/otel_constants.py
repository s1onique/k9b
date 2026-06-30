"""OTel constants for diagnosis loop instrumentation.

This module contains all constant definitions:
- Span names (k9b namespace)
- Attribute keys (k9b namespace)
- Event names (k9b namespace)

These are stable identifiers that should not change across versions.
"""

from __future__ import annotations

# =============================================================================
# Span Names (k9b namespace)
# =============================================================================

SPAN_LOOP_RUN = "k9b.diagnosis_loop.run"
SPAN_LOOP_PASS = "k9b.diagnosis_loop.pass"
SPAN_LOOP_BUDGET = "k9b.diagnosis_loop.budget"
SPAN_LOOP_PLAN = "k9b.diagnosis_loop.plan"
SPAN_LOOP_GATE = "k9b.diagnosis_loop.gate"
SPAN_LOOP_EXECUTE = "k9b.diagnosis_loop.execute"
SPAN_LOOP_ARTIFACT = "k9b.diagnosis_loop.artifact"
SPAN_LOOP_STOP = "k9b.diagnosis_loop.stop"

# =============================================================================
# Attribute Keys (k9b namespace)
# =============================================================================

# Loop attributes
ATTR_INCIDENT_ID = "k9b.incident.id"
ATTR_LOOP_RUN_ID = "k9b.loop.run_id"
ATTR_LOOP_PASS_INDEX = "k9b.loop.pass_index"
ATTR_LOOP_SCHEMA_VERSION = "k9b.loop.schema_version"
ATTR_LOOP_POLICY_SCHEMA_VERSION = "k9b.loop.policy.schema_version"
ATTR_LOOP_MAX_PASSES = "k9b.loop.max_passes"
ATTR_LOOP_MAX_CHECKS_PER_PASS = "k9b.loop.max_checks_per_pass"
ATTR_LOOP_MAX_TOTAL_CHECKS = "k9b.loop.max_total_checks"
ATTR_LOOP_BUDGET_EXCEEDED = "k9b.loop.budget_exceeded"
ATTR_LOOP_STOP_REASON = "k9b.loop.stop_reason"
ATTR_LOOP_DECISION = "k9b.loop.decision"
ATTR_LOOP_RUNNER_KIND = "k9b.loop.runner_kind"

# Gate attributes
ATTR_CHECKS_PROPOSED = "k9b.loop.checks.proposed"
ATTR_CHECKS_ACCEPTED = "k9b.loop.checks.accepted"
ATTR_CHECKS_REJECTED = "k9b.loop.checks.rejected"
ATTR_CHECKS_REJECTED_MUTATING = "k9b.loop.checks.rejected_mutating"
ATTR_CHECKS_REJECTED_SENSITIVE = "k9b.loop.checks.rejected_sensitive"
ATTR_CHECKS_REJECTED_DUPLICATE = "k9b.loop.checks.rejected_duplicate"
ATTR_CHECKS_REJECTED_BUDGET = "k9b.loop.checks.rejected_budget"

# Execution/artifact attributes
ATTR_EVIDENCE_NEW_COUNT = "k9b.loop.evidence.new_count"
ATTR_ARTIFACT_PATH = "k9b.loop.artifact.path"
ATTR_ARTIFACT_SCHEMA_VALID = "k9b.loop.artifact.schema_valid"
ATTR_ARTIFACT_SCHEMA_MISSING_COUNT = "k9b.loop.artifact.schema_missing_count"

# =============================================================================
# Event Names (k9b namespace)
# =============================================================================

EVENT_BUDGET_EXCEEDED = "k9b.diagnosis_loop.budget_exceeded"
EVENT_CHECK_REJECTED = "k9b.diagnosis_loop.check_rejected"
EVENT_CHECKS_EXECUTED = "k9b.diagnosis_loop.checks_executed"
EVENT_ARTIFACT_WRITTEN = "k9b.diagnosis_loop.artifact_written"
EVENT_LOOP_STOP = "k9b.diagnosis_loop.stop"


__all__ = [
    # Span names
    "SPAN_LOOP_RUN",
    "SPAN_LOOP_PASS",
    "SPAN_LOOP_BUDGET",
    "SPAN_LOOP_PLAN",
    "SPAN_LOOP_GATE",
    "SPAN_LOOP_EXECUTE",
    "SPAN_LOOP_ARTIFACT",
    "SPAN_LOOP_STOP",
    # Attribute keys
    "ATTR_INCIDENT_ID",
    "ATTR_LOOP_RUN_ID",
    "ATTR_LOOP_PASS_INDEX",
    "ATTR_LOOP_SCHEMA_VERSION",
    "ATTR_LOOP_POLICY_SCHEMA_VERSION",
    "ATTR_LOOP_MAX_PASSES",
    "ATTR_LOOP_MAX_CHECKS_PER_PASS",
    "ATTR_LOOP_MAX_TOTAL_CHECKS",
    "ATTR_LOOP_BUDGET_EXCEEDED",
    "ATTR_LOOP_STOP_REASON",
    "ATTR_LOOP_DECISION",
    "ATTR_LOOP_RUNNER_KIND",
    "ATTR_CHECKS_PROPOSED",
    "ATTR_CHECKS_ACCEPTED",
    "ATTR_CHECKS_REJECTED",
    "ATTR_CHECKS_REJECTED_MUTATING",
    "ATTR_CHECKS_REJECTED_SENSITIVE",
    "ATTR_CHECKS_REJECTED_DUPLICATE",
    "ATTR_CHECKS_REJECTED_BUDGET",
    "ATTR_EVIDENCE_NEW_COUNT",
    "ATTR_ARTIFACT_PATH",
    "ATTR_ARTIFACT_SCHEMA_VALID",
    "ATTR_ARTIFACT_SCHEMA_MISSING_COUNT",
    # Event names
    "EVENT_BUDGET_EXCEEDED",
    "EVENT_CHECK_REJECTED",
    "EVENT_CHECKS_EXECUTED",
    "EVENT_ARTIFACT_WRITTEN",
    "EVENT_LOOP_STOP",
]
