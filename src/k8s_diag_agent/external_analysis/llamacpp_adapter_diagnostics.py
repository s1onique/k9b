"""Prompt diagnostic helpers for llamacpp adapter.

This module extracts prompt section extraction from llamacpp_adapter.py,
providing focused helpers for building named PromptSections used in
prompt diagnostics and failure reporting.
"""

from __future__ import annotations

import json

from ..llm.prompt_diagnostics import PromptSection
from .adapter import ExternalAnalysisRequest
from .review_input import ReviewEnrichmentInput

# kubectl command guidance text - extracted to avoid duplication
KUBECTL_GUIDANCE = (
    "CRITICAL for nextChecks: each entry MUST be an explicit kubectl command in one of these formats:\n"
    "  - 'kubectl describe <resource> -n <namespace>'\n"
    "  - 'kubectl logs <resource> -n <namespace>'\n"
    "  - 'kubectl get <resource> -n <namespace>'\n"
    "  - 'kubectl get crd --context <cluster>'\n"
    "  - 'kubectl top <resource> -n <namespace>' (if metrics-server available)\n"
    "REQUIREMENTS:\n"
    "  - Every nextChecks entry must START with one of: kubectl describe, kubectl logs, kubectl get, kubectl top\n"
    "  - Each command must target exactly ONE cluster (use --context flag)\n"
    "  - NEVER use phrases like: validate, review, check status, confirm, investigate, verify, plan upgrade\n"
    "  - NEVER suggest 'all clusters', 'across clusters', or multi-cluster commands\n"
    "  - NEVER suggest mutations: do not include apply, patch, scale, edit, upgrade, delete, restart, rollout\n"
    "Examples of CORRECT nextChecks:\n"
    "  - 'kubectl describe pod -n default myapp-abc123 --context cluster1'\n"
    "  - 'kubectl logs deployment/myapp -n production --context admin@prod'\n"
    "  - 'kubectl get crd --context cluster2'\n"
    "Examples of WRONG nextChecks (will be rejected by planner):\n"
    "  - 'Validate image pull secrets in cluster1' (has 'validate')\n"
    "  - 'Check all clusters for CRDs' (has 'all clusters')\n"
    "  - 'Verify cluster2 version and upgrade to v1.33' (has 'upgrade')"
)


# Output schema template - extracted from _build_prompt inline text
OUTPUT_SCHEMA_TEMPLATE = (
    "Produce a concise JSON advisory payload that includes summary, triageOrder/triage_order, "
    "topConcerns/top_concerns, evidenceGaps/evidence_gaps, nextChecks/next_checks, and "
    "focusNotes/focus_notes. Use arrays of non-empty strings for the list entries and highlight "
    "missing data explicitly.\n"
    "Interpret the inputs conservatively and focus on actionable next checks and missing evidence.\n"
    + KUBECTL_GUIDANCE
)


def extract_prompt_sections(
    request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
) -> list[PromptSection]:
    """Extract named sections from the review enrichment prompt for diagnostics.

    NOTE: Named sections are best-effort and may not exactly match the
    actual prompt due to JSON formatting, whitespace, and structure
    differences. The actual_prompt_chars field in PromptDiagnostics
    is the authoritative measurement.

    Named sections include:
    - request_header: LLM external analysis request header
    - output_schema: JSON output format instructions
    - review_artifact: The review JSON content
    - alertmanager_context: Alertmanager compact data when available
    - drilldown_evidence: Drilldown artifacts for selected items
    - missing_context: Notes about missing artifacts
    - interpretation_guidance: Conservative interpretation guidance
    - kubectl_guidance: nextChecks format requirements
    """
    sections: list[PromptSection] = []

    # Section 1: Request header/instructions
    sections.append(PromptSection(
        name="request_header",
        text=f"LLM external analysis request\nrun_id={request.run_id}\ncluster_label={request.cluster_label}",
    ))

    # Section 2: Output format instruction
    sections.append(PromptSection(
        name="output_schema",
        text="Produce a concise JSON advisory payload that includes summary, triageOrder/triage_order, "
             "topConcerns/top_concerns, evidenceGaps/evidence_gaps, nextChecks/next_checks, and "
             "focusNotes/focus_notes. Use arrays of non-empty strings for the list entries and highlight "
             "missing data explicitly.",
    ))

    # Section 3: Review artifact
    sections.append(PromptSection(
        name="review_artifact",
        text=json.dumps(context.review, indent=2),
    ))

    # Section 4: Alertmanager context
    alertmanager_text = json.dumps({
        "available": context.alertmanager_context.available,
        "source": context.alertmanager_context.source,
        "status": context.alertmanager_context.status,
        "compact": context.alertmanager_context.compact,
    }, indent=2)
    sections.append(PromptSection(
        name="alertmanager_context",
        text=alertmanager_text,
    ))

    # Section 5: Drilldown and assessment evidence for selections
    if context.selections:
        selection_parts: list[str] = []
        for selection in context.selections:
            label = selection.label or selection.context or "<unknown>"
            selection_parts.append(f"Selected drilldown: {label} ({selection.context})")
            selection_parts.append(json.dumps(selection.entry, indent=2))
            if selection.drilldown:
                selection_parts.append("Drilldown artifact:")
                selection_parts.append(json.dumps(selection.drilldown, indent=2))
            else:
                selection_parts.append(f"Drilldown artifact unavailable for {label}.")
            if selection.assessment:
                selection_parts.append("Assessment artifact:")
                selection_parts.append(json.dumps(selection.assessment, indent=2))
            else:
                selection_parts.append(f"Assessment artifact unavailable for {label}.")
            if selection.snapshot:
                selection_parts.append("Referenced snapshot:")
                selection_parts.append(json.dumps(selection.snapshot, indent=2))
            elif selection.snapshot_path:
                selection_parts.append(
                    f"Snapshot referenced at {selection.snapshot_path} is unavailable."
                )
        sections.append(PromptSection(
            name="drilldown_evidence",
            text="\n".join(selection_parts),
        ))
    else:
        sections.append(PromptSection(
            name="drilldown_evidence",
            text="No drilldown was selected for this review.",
        ))

    # Section 6: Missing context notes
    missing_parts: list[str] = []
    if context.missing_drilldowns:
        missing_parts.append(
            "Missing drilldown artifacts: " + ", ".join(context.missing_drilldowns)
        )
    if context.missing_assessments:
        missing_parts.append(
            "Missing assessments: " + ", ".join(context.missing_assessments)
        )
    if context.missing_snapshots:
        missing_parts.append(
            "Missing snapshots: " + ", ".join(context.missing_snapshots)
        )
    if missing_parts:
        sections.append(PromptSection(
            name="missing_context",
            text="\n".join(missing_parts),
        ))

    # Section 7: Interpretation guidance
    sections.append(PromptSection(
        name="interpretation_guidance",
        text="Interpret the inputs conservatively and focus on actionable next checks and missing evidence.",
    ))

    # Section 8: kubectl command guidance
    sections.append(PromptSection(
        name="kubectl_guidance",
        text=KUBECTL_GUIDANCE,
    ))

    return sections
