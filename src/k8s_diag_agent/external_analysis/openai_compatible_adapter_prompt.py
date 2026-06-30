"""Prompt construction helpers for OpenAI-compatible adapter.

This module extracts prompt building responsibilities from openai_compatible_adapter.py,
providing focused helpers for:
- Building instruction headers with cluster label anonymization
- Assembling untrusted data parts with anonymization
- Composing structured prompts with explicit boundaries
"""

from __future__ import annotations

import json

from ..llm.prompt_boundaries import (
    BEGIN_OUTPUT_SCHEMA,
    BEGIN_UNTRUSTED_CLUSTER_DATA,
    END_OUTPUT_SCHEMA,
    END_UNTRUSTED_CLUSTER_DATA,
)
from ..llm.semantic_injection_detector import (
    build_security_note,
    detect_semantic_injection,
)
from ..security import sanitize_prompt
from ..security.anonymizer import MetadataAnonymizer
from ..security.deanonymization import flatten_alias_mappings
from ..security.kubectl_context import display_kube_cluster_label
from .openai_compatible_adapter_diagnostics import OUTPUT_SCHEMA_TEMPLATE
from .review_input import ReviewEnrichmentInput


def build_instruction_header(
    run_id: str, cluster_label: str, anonymizer: MetadataAnonymizer
) -> str:
    """Build the instruction header for review enrichment prompts.

    Uses MetadataAnonymizer to anonymize the cluster_label so internal markers
    like 'in-cluster' don't leak into LLM prompts.
    """
    safe_label = display_kube_cluster_label(cluster_label)
    anon_data = anonymizer.anonymize({"cluster_label": safe_label})
    anon_label = anon_data.get("cluster_label", safe_label)
    return f"LLM external analysis request\nrun_id={run_id}\ncluster_label={anon_label}"


def build_untrusted_parts(
    context: ReviewEnrichmentInput, anonymizer: MetadataAnonymizer
) -> list[str]:
    """Build the untrusted data parts for the prompt.

    All cluster/artifact data goes inside BEGIN/END_UNTRUSTED_CLUSTER_DATA markers.
    Uses MetadataAnonymizer to prevent cluster identifiers from leaking into prompts.
    """
    parts: list[str] = []
    anon_review = anonymizer.anonymize(dict(context.review))
    parts.append("Review artifact:")
    parts.append(json.dumps(anon_review, indent=2))

    if context.alertmanager_context.available:
        anon_compact = anonymizer.anonymize(context.alertmanager_context.compact) if context.alertmanager_context.compact else None
        parts.append("Alertmanager operational context:")
        parts.append(json.dumps({
            "available": True,
            "source": context.alertmanager_context.source,
            "status": context.alertmanager_context.status,
            "compact": anon_compact,
        }, indent=2))
    else:
        parts.append("Alertmanager operational context:")
        parts.append(json.dumps({
            "available": False,
            "source": context.alertmanager_context.source,
            "status": context.alertmanager_context.status,
            "compact": None,
        }, indent=2))

    if context.selections:
        for selection in context.selections:
            label = selection.label or selection.context or "<unknown>"
            anon_label_data = anonymizer.anonymize({"label": label})
            anon_label = anon_label_data.get("label", label)
            anon_context_data = anonymizer.anonymize({"context": selection.context})
            anon_context = anon_context_data.get("context", selection.context)
            anon_entry = anonymizer.anonymize(dict(selection.entry)) if selection.entry else {}
            parts.append(f"Selected drilldown: {anon_label} ({anon_context})")
            parts.append(json.dumps(anon_entry, indent=2))
            if selection.drilldown:
                parts.append("Drilldown artifact:")
                parts.append(json.dumps(anonymizer.anonymize(selection.drilldown), indent=2))
            else:
                parts.append(f"Drilldown artifact unavailable for {anon_label}.")
            if selection.assessment:
                parts.append("Assessment artifact:")
                parts.append(json.dumps(anonymizer.anonymize(selection.assessment), indent=2))
            else:
                parts.append(f"Assessment artifact unavailable for {anon_label}.")
            if selection.snapshot:
                parts.append("Referenced snapshot:")
                parts.append(json.dumps(anonymizer.anonymize(selection.snapshot), indent=2))
            elif selection.snapshot_path:
                parts.append(f"Snapshot referenced at {selection.snapshot_path} is unavailable.")
    else:
        parts.append("No drilldown was selected for this review.")

    missing_notes: list[str] = []
    if context.missing_drilldowns:
        missing_notes.append("Missing drilldown artifacts: " + ", ".join(context.missing_drilldowns))
    if context.missing_assessments:
        missing_notes.append("Missing assessments: " + ", ".join(context.missing_assessments))
    if context.missing_snapshots:
        missing_notes.append("Missing snapshots: " + ", ".join(context.missing_snapshots))
    if missing_notes:
        parts.append("Missing context details:")
        parts.extend(missing_notes)

    return parts


def compose_review_enrichment_prompt(
    run_id: str,
    cluster_label: str,
    context: ReviewEnrichmentInput,
) -> tuple[str, dict[str, str] | None]:
    """Build the full review enrichment prompt with explicit boundaries.

    Returns the sanitized prompt and alias mapping for de-anonymization.
    """
    # Create single anonymizer instance to preserve alias consistency within prompt
    anonymizer = MetadataAnonymizer()

    instruction_header = build_instruction_header(run_id, cluster_label, anonymizer)
    untrusted_data = "\n".join(build_untrusted_parts(context, anonymizer))

    # Detect semantic injection patterns in untrusted data
    # This is deterministic and does NOT make LLM calls
    injection_findings = detect_semantic_injection(untrusted_data)

    # Build security note if suspicious patterns detected
    # The note is placed OUTSIDE the untrusted boundary (in trusted instruction area)
    # to ensure the LLM sees it as a directive, not as untrusted data
    # Security note format: [UNTRUSTED_EVIDENCE_SECURITY_NOTE] ... [/UNTRUSTED_EVIDENCE_SECURITY_NOTE]
    security_note = build_security_note(injection_findings)

    # === COMPOSE PROMPT WITH EXPLICIT BOUNDARIES ===
    # 1. Instruction header (trusted)
    # 2. Optional security note (trusted instruction area, only if injection patterns detected)
    # 3. Untrusted data section (wrapped with boundary markers, preserved verbatim)
    # 4. Output schema section (trusted)
    prompt_parts = [instruction_header]

    # Add security note if injection patterns detected
    # This warns the LLM to treat suspicious evidence as data only
    if security_note:
        prompt_parts.append(f"\n{security_note}\n")

    # Add untrusted data section (suspicious content preserved verbatim)
    prompt_parts.append(f"\n{BEGIN_UNTRUSTED_CLUSTER_DATA}\n{untrusted_data}\n{END_UNTRUSTED_CLUSTER_DATA}\n")

    # Add output schema section
    prompt_parts.append(f"{BEGIN_OUTPUT_SCHEMA}\n{OUTPUT_SCHEMA_TEMPLATE}\n{END_OUTPUT_SCHEMA}\n")

    prompt = "".join(prompt_parts)
    # Extract ALL alias mappings for de-anonymization at UI boundary
    all_mappings = anonymizer.get_all_alias_mappings()
    alias_mapping = flatten_alias_mappings(all_mappings) if all_mappings else None
    return sanitize_prompt(prompt), alias_mapping
