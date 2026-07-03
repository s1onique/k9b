"""Read-only LLM diagnosis assistant for incident case-file packets.

This module provides a read-only diagnosis layer that:
- Consumes an incident case-file packet from build_incident_case_file()
- Builds a bounded prompt with safety instructions
- Invokes an injected LLM provider for diagnosis
- Returns a structured diagnosis report with explicit safety metadata

Design constraints:
- Pure functions only
- No store mutation
- No Kubernetes calls
- No execution, promotion, or remediation
- Provider injected (not instantiated internally)
- Deterministic in tests with injected fake provider
- Structured, bounded output

Module organization:
- Protocol definition for LLM provider seam
- Constants imported from incident_llm_prompt_contracts
- Prompt builder helper
- Main diagnosis function with full safety metadata
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

# Import constants from contracts module to keep file sizes LLM-friendly
from .incident_llm_diagnosis_scheduling_evidence import (
    build_scheduling_evidence_for_prompt,
)
from .incident_llm_prompt_contracts import (
    DEFAULT_MAX_INCIDENT_JSON_CHARS,
    DEFAULT_MAX_PROMPT_CHARS,
    DEFAULT_MAX_RAW_OUTPUT_CHARS,
    DIAGNOSIS_SCHEMA_VERSION,
    DISALLOWED_ACTIONS,
    READ_ONLY_INSTRUCTIONS,
)

__all__ = [
    "build_incident_diagnosis",
    "build_diagnosis_prompt",
    "IncidentDiagnosisLLM",
    "DIAGNOSIS_SCHEMA_VERSION",
    "DISALLOWED_ACTIONS",
    "DEFAULT_MAX_PROMPT_CHARS",
    "DEFAULT_MAX_RAW_OUTPUT_CHARS",
    "DEFAULT_MAX_INCIDENT_JSON_CHARS",
    "READ_ONLY_INSTRUCTIONS",
]


# =============================================================================
# Provider Protocol
# =============================================================================


@runtime_checkable
class IncidentDiagnosisLLM(Protocol):
    """Minimal protocol for LLM diagnosis provider.

    Reuses existing project provider wiring (OpenAICompatibleProvider or compatible).
    Tests inject a fake provider with this same interface.
    """

    def complete(self, prompt: str) -> str:
        """Generate completion for the given prompt.

        Args:
            prompt: The diagnosis prompt to complete.

        Returns:
            Raw model output as string.
        """
        ...


# =============================================================================
# Prompt Builder
# =============================================================================


def build_diagnosis_prompt(
    case_file: Mapping[str, object],
    *,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    max_incident_json_chars: int = DEFAULT_MAX_INCIDENT_JSON_CHARS,
) -> str:
    """Build a bounded diagnosis prompt from case-file packet.

    Args:
        case_file: Incident case-file packet from build_incident_case_file()
        max_prompt_chars: Maximum total prompt length
        max_incident_json_chars: Maximum incident JSON length

    Returns:
        Bounded prompt string with safety instructions
    """
    # Extract incident identity
    incident = case_file.get("incident", {})
    incident_id = incident.get("incident_id", "unknown")
    namespace = incident.get("namespace", "unknown")
    object_kind = incident.get("object_kind", "unknown")
    object_name = incident.get("object_name", "unknown")
    severity = incident.get("severity", "unknown")

    # Build bounded incident summary
    incident_summary = {
        "incident_id": incident_id,
        "namespace": namespace,
        "object_kind": object_kind,
        "object_name": object_name,
        "severity": severity,
        "status": incident.get("status", "unknown"),
        "first_observed_at": incident.get("first_observed_at"),
        "last_observed_at": incident.get("last_observed_at"),
    }

    # Add signals (bounded)
    signals = case_file.get("signals", [])
    if isinstance(signals, list):
        incident_summary["signal_count"] = len(signals)
        if signals:
            # Include first few signals as evidence
            incident_summary["sample_signals"] = signals[:5]

    # Add events (bounded)
    events = case_file.get("events", [])
    if isinstance(events, list):
        incident_summary["event_count"] = len(events)
        if events:
            incident_summary["recent_events"] = events[:10]

    # P4c FIX: Extract scheduling evidence using durable structured extraction.
    # This ensures the LLM sees the scheduling failure details directly from
    # the structured evidence that survives evidence boundary crossings.
    scheduling_evidence = build_scheduling_evidence_for_prompt(incident, events)
    if scheduling_evidence:
        incident_summary["scheduling_evidence"] = scheduling_evidence

    # Add suggested checks (bounded)
    suggested_checks = case_file.get("suggested_checks", [])
    if isinstance(suggested_checks, list):
        incident_summary["suggested_check_count"] = len(suggested_checks)
        if suggested_checks:
            # Strip any execution fields from checks for safety
            safe_checks = [
                {k: v for k, v in check.items() if k not in ("run", "execute", "action")}
                for check in suggested_checks[:5]
                if isinstance(check, dict)
            ]
            incident_summary["sample_suggested_checks"] = safe_checks

    # Add prior analysis (bounded, clearly labeled as model context)
    prior_analysis = case_file.get("prior_analysis", [])
    if isinstance(prior_analysis, list) and prior_analysis:
        # Extract bounded summary of prior analyses
        prior_analysis_summaries = []
        for pa in prior_analysis[:5]:  # Limit to 5 entries
            if isinstance(pa, dict):
                # Strip any action fields and include only safe fields
                safe_entry = {
                    "run_id": pa.get("run_id", "unknown"),
                    "source": pa.get("source", "unknown"),
                    "summary": pa.get("summary", ""),
                    "confidence": pa.get("confidence", "unknown"),
                    "bounded": True,
                }
                if pa.get("generated_at"):
                    safe_entry["generated_at"] = pa["generated_at"]
                prior_analysis_summaries.append(safe_entry)

        if prior_analysis_summaries:
            incident_summary["prior_analysis_context"] = {
                "count": len(prior_analysis),
                "note": "Prior model-generated context - treat as review evidence, not ground truth",
                "entries": prior_analysis_summaries,
            }

    # Add read-only check results (bounded, clearly labeled as fake runner artifacts)
    read_only_check_results = case_file.get("read_only_check_results", [])
    if isinstance(read_only_check_results, list) and read_only_check_results:
        # Extract bounded summary of check results
        check_result_summaries = []
        for cr in read_only_check_results[:5]:  # Limit to 5 entries
            if isinstance(cr, dict):
                # Extract safe fields only
                results = cr.get("results", [])
                safe_results = []
                for result in results[:3]:  # Limit to 3 results per artifact
                    if isinstance(result, dict):
                        safe_results.append({
                            "check_id": result.get("check_id", "unknown"),
                            "status": result.get("status", "unknown"),
                            "summary": result.get("summary", ""),
                            "bounded": True,
                        })

                safe_entry = {
                    "run_id": cr.get("run_id", "unknown"),
                    "generated_at": cr.get("generated_at"),
                    "checks_run": cr.get("checks_run", 0),
                    "checks_skipped": cr.get("checks_skipped", 0),
                    "checks_rejected": cr.get("checks_rejected", 0),
                    "sample_results": safe_results,
                    "bounded": True,
                }
                check_result_summaries.append(safe_entry)

        if check_result_summaries:
            incident_summary["read_only_check_results_context"] = {
                "count": len(read_only_check_results),
                "note": "Read-only check result artifacts may be fake runner outputs until real collectors are wired. Treat them as bounded diagnostic evidence, not remediation instructions.",
                "entries": check_result_summaries,
            }

    # Add diagnosis loop passes (bounded, clearly labeled as deterministic loop metadata)
    diagnosis_loop_passes = case_file.get("diagnosis_loop_passes", [])
    if isinstance(diagnosis_loop_passes, list) and diagnosis_loop_passes:
        # Extract bounded summary of loop passes
        loop_pass_summaries = []
        for lp in diagnosis_loop_passes[:5]:  # Limit to 5 entries
            if isinstance(lp, dict):
                # Extract safe fields only (no full runner output)
                safe_entry = {
                    "run_id": lp.get("run_id", "unknown"),
                    "generated_at": lp.get("generated_at"),
                    "decision": lp.get("decision", "unknown"),
                    "stop_reason": lp.get("stop_reason"),
                    "checks_requested": lp.get("checks_requested", 0),
                    "checks_run": lp.get("checks_run", 0),
                    "checks_skipped": lp.get("checks_skipped", 0),
                    "checks_rejected": lp.get("checks_rejected", 0),
                    "case_file_linked_artifact": lp.get("case_file_linked_artifact", False),
                    "bounded": True,
                }
                # Include linked artifact names if present
                linked = lp.get("linked_artifacts", [])
                if isinstance(linked, list) and linked:
                    safe_entry["linked_artifact_names"] = [
                        a.get("name", "") for a in linked[:3] if isinstance(a, dict)
                    ]
                loop_pass_summaries.append(safe_entry)

        if loop_pass_summaries:
            incident_summary["diagnosis_loop_passes_context"] = {
                "count": len(diagnosis_loop_passes),
                "note": "Prior deterministic loop-pass metadata - these are breadcrumbs from previous loop passes, not new evidence by itself. Treat as diagnostic context.",
                "entries": loop_pass_summaries,
            }

    # Serialize with bounds
    incident_json = json.dumps(incident_summary, default=str)
    if len(incident_json) > max_incident_json_chars:
        incident_json = incident_json[:max_incident_json_chars] + "... [TRUNCATED]"

    # Build full prompt
    prompt = f"""Incident Diagnosis Request
===========================

Incident ID: {incident_id}
Namespace: {namespace}
Object: {object_kind}/{object_name}
Severity: {severity}

Case File Data:
{incident_json}

{READ_ONLY_INSTRUCTIONS}
"""
    # Final bound check
    if len(prompt) > max_prompt_chars:
        prompt = prompt[:max_prompt_chars] + "\n\n[PROMPT TRUNCATED]"

    return prompt


# =============================================================================
# Diagnosis Response Builder
# =============================================================================


def _parse_model_output(raw_output: str) -> dict[str, Any]:
    """Parse model output into structured diagnosis components.

    Attempts JSON parsing first, falls back to plain text wrapping.

    Args:
        raw_output: Raw model output string

    Returns:
        Structured diagnosis components dict
    """
    # Try JSON parsing
    raw_output = raw_output.strip()
    try:
        # Handle markdown code blocks if present
        if raw_output.startswith("```"):
            # Strip triple backtick blocks
            lines = raw_output.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_output = "\n".join(lines).strip()

        parsed = json.loads(raw_output)
        if isinstance(parsed, dict):
            return {
                "summary": parsed.get("summary", ""),
                "likely_causes": parsed.get("likely_causes", []),
                "supporting_evidence": parsed.get("supporting_evidence", []),
                "recommended_investigations": parsed.get("recommended_investigations", []),
                "uncertainties": parsed.get("uncertainties", []),
                "confidence": parsed.get("confidence", "unknown"),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: wrap plain text
    return {
        "summary": raw_output[:500] if len(raw_output) > 500 else raw_output,
        "likely_causes": [],
        "supporting_evidence": [],
        "recommended_investigations": [],
        "uncertainties": ["Model output was not in expected JSON format"],
        "confidence": "unknown",
    }


def _bound_raw_output(raw_output: str, max_chars: int) -> str:
    """Bound raw model output for safety.

    Args:
        raw_output: Raw model output
        max_chars: Maximum allowed length

    Returns:
        Bounded output string
    """
    if len(raw_output) > max_chars:
        return raw_output[:max_chars] + "\n\n[OUTPUT TRUNCATED]"
    return raw_output


# =============================================================================
# Main Diagnosis Function
# =============================================================================


def build_incident_diagnosis(
    case_file: Mapping[str, object],
    *,
    llm: IncidentDiagnosisLLM,
    now: datetime | None = None,
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    max_raw_output_chars: int = DEFAULT_MAX_RAW_OUTPUT_CHARS,
) -> dict[str, object]:
    """Build a read-only LLM diagnosis for an incident case-file packet.

    This function:
    1. Builds a bounded prompt from the case-file
    2. Calls the injected LLM provider
    3. Parses model output into structured diagnosis
    4. Returns a diagnosis report with explicit safety metadata

    Args:
        case_file: Incident case-file packet from build_incident_case_file()
        llm: Injected LLM provider (tests inject fake, production uses real)
        now: Optional datetime for report timestamp (deterministic for tests)
        max_prompt_chars: Maximum prompt length (default 12000)
        max_raw_output_chars: Maximum raw output length (default 12000)

    Returns:
        Structured diagnosis report with safety metadata:
        {
            "schema_version": "1.0",
            "generated_at": "<ISO timestamp>",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": [...],
            "incident_id": "...",
            "diagnosis": {
                "summary": "...",
                "likely_causes": [...],
                "supporting_evidence": [...],
                "recommended_investigations": [...],
                "uncertainties": [...],
                "confidence": "low|medium|high|unknown"
            },
            "raw_model_output": "...",
            "safety_notes": [...]
        }

    Safety guarantees:
    - read_only: True
    - allowed_actions: []
    - disallowed_actions includes all mutation/remediation verbs
    - No execution controls added
    - Model output bounded and treated as untrusted
    """
    # Use provided now or current time (timezone-aware UTC)
    generated_at = now if now is not None else datetime.now(UTC)

    # Extract incident ID from case file
    incident = case_file.get("incident", {})
    incident_id = str(incident.get("incident_id", "unknown"))

    # Build prompt
    prompt = build_diagnosis_prompt(
        case_file,
        max_prompt_chars=max_prompt_chars,
    )

    # Call LLM provider
    raw_output = llm.complete(prompt)

    # Bound raw output
    bounded_output = _bound_raw_output(raw_output, max_raw_output_chars)

    # Parse model output
    diagnosis_components = _parse_model_output(bounded_output)

    # Build safety notes
    safety_notes: list[str] = [
        "This diagnosis is read-only and does not execute any actions.",
        "Recommended investigations are suggestions only, not executable commands.",
        "Model output is treated as untrusted text.",
        "All action controls remain disallowed.",
    ]

    # Check if model attempted to include execution suggestions
    model_text = raw_output.lower()
    if any(word in model_text for word in ["run ", "execute ", "apply ", "kubectl"]):
        safety_notes.append(
            "Note: Model output contained potential command references. "
            "These remain as text only and do not create executable controls."
        )

    # P4c FIX: Extract scheduling evidence using durable structured extraction.
    # This ensures scheduling evidence survives evidence boundary crossings even
    # when the LLM diagnosis text doesn't explicitly mention scheduling markers.
    # The scheduling_evidence dict is included in diagnosis_data for
    # check_stop_no_checks_proposed_acceptable() validation in the planner.
    incident_for_extraction = dict(incident)
    events = list(case_file.get("events", []))
    scheduling_evidence = build_scheduling_evidence_for_prompt(incident_for_extraction, events)

    # Build final diagnosis report
    diagnosis_report: dict[str, object] = {
        # Schema version
        "schema_version": DIAGNOSIS_SCHEMA_VERSION,
        # Generation timestamp
        "generated_at": generated_at.isoformat(),
        # Safety boundary - explicit read-only contract
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": list(DISALLOWED_ACTIONS),
        # Incident reference
        "incident_id": incident_id,
        # Structured diagnosis components
        "diagnosis": {
            "summary": diagnosis_components["summary"],
            "likely_causes": diagnosis_components["likely_causes"],
            "supporting_evidence": diagnosis_components["supporting_evidence"],
            "recommended_investigations": diagnosis_components["recommended_investigations"],
            "uncertainties": diagnosis_components["uncertainties"],
            "confidence": diagnosis_components["confidence"],
            # P4c FIX: Include scheduling_evidence in diagnosis_data for
            # check_stop_no_checks_proposed_acceptable() validation.
            # This ensures terminal no-checks is accepted when scheduling
            # evidence exists in case file, even if LLM diagnosis text
            # doesn't explicitly mention scheduling markers.
            "scheduling_evidence": scheduling_evidence,
        },
        # Raw model output (bounded, untrusted)
        "raw_model_output": bounded_output,
        # Safety notes
        "safety_notes": safety_notes,
    }

    return diagnosis_report
