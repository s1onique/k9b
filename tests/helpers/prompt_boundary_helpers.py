"""Shared helpers for prompt boundary tests.

This module provides reusable utilities for testing that prompt builders use
explicit boundary markers to separate trusted instructions from untrusted
cluster/artifact data.
"""

from __future__ import annotations

from k8s_diag_agent.llm.prompt_boundaries import (
    BEGIN_OUTPUT_SCHEMA,
    BEGIN_UNTRUSTED_CLUSTER_DATA,
    END_OUTPUT_SCHEMA,
    END_UNTRUSTED_CLUSTER_DATA,
)


def extract_boundary_sections(prompt: str) -> dict[str, str]:
    """Extract the three prompt sections based on boundary markers.

    Returns:
        dict with keys:
        - before_untrusted: text before BEGIN_UNTRUSTED_CLUSTER_DATA
        - inside_untrusted: text between UNTRUSTED markers
        - after_untrusted_before_schema: text after END_UNTRUSTED and before BEGIN_OUTPUT_SCHEMA
        - inside_schema: text between OUTPUT_SCHEMA markers
        - after_schema: text after END_OUTPUT_SCHEMA
    """
    begin_untrusted = prompt.find(BEGIN_UNTRUSTED_CLUSTER_DATA)
    end_untrusted = prompt.find(END_UNTRUSTED_CLUSTER_DATA)
    begin_schema = prompt.find(BEGIN_OUTPUT_SCHEMA)
    end_schema = prompt.find(END_OUTPUT_SCHEMA)

    return {
        "before_untrusted": prompt[:begin_untrusted] if begin_untrusted >= 0 else "",
        "inside_untrusted": (
            prompt[begin_untrusted : end_untrusted + len(END_UNTRUSTED_CLUSTER_DATA)]
            if begin_untrusted >= 0 and end_untrusted >= 0
            else ""
        ),
        "after_untrusted_before_schema": (
            prompt[end_untrusted:begin_schema]
            if end_untrusted >= 0 and begin_schema >= 0
            else ""
        ),
        "inside_schema": (
            prompt[begin_schema : end_schema + len(END_OUTPUT_SCHEMA)]
            if begin_schema >= 0 and end_schema >= 0
            else ""
        ),
        "after_schema": prompt[end_schema:] if end_schema >= 0 else "",
    }


def verify_boundary_structure(prompt: str) -> list[str]:
    """Verify prompt follows the boundary convention.

    Returns list of error messages (empty if structure is valid).
    """
    errors: list[str] = []

    # Count occurrences of each marker
    begin_untrusted_count = prompt.count(BEGIN_UNTRUSTED_CLUSTER_DATA)
    end_untrusted_count = prompt.count(END_UNTRUSTED_CLUSTER_DATA)
    begin_schema_count = prompt.count(BEGIN_OUTPUT_SCHEMA)
    end_schema_count = prompt.count(END_OUTPUT_SCHEMA)

    # Each marker should appear exactly once
    if begin_untrusted_count != 1:
        errors.append(f"BEGIN_UNTRUSTED_CLUSTER_DATA appears {begin_untrusted_count} times (expected 1)")
    if end_untrusted_count != 1:
        errors.append(f"END_UNTRUSTED_CLUSTER_DATA appears {end_untrusted_count} times (expected 1)")
    if begin_schema_count != 1:
        errors.append(f"BEGIN_OUTPUT_SCHEMA appears {begin_schema_count} times (expected 1)")
    if end_schema_count != 1:
        errors.append(f"END_OUTPUT_SCHEMA appears {end_schema_count} times (expected 1)")

    # Order verification: header before untrusted, untrusted before schema
    instruction_pos = prompt.find("You are a careful Kubernetes diagnostician")
    begin_untrusted_pos = prompt.find(BEGIN_UNTRUSTED_CLUSTER_DATA)
    end_untrusted_pos = prompt.find(END_UNTRUSTED_CLUSTER_DATA)
    begin_schema_pos = prompt.find(BEGIN_OUTPUT_SCHEMA)

    if instruction_pos >= 0 and begin_untrusted_pos >= 0:
        if instruction_pos > begin_untrusted_pos:
            errors.append("Trusted instruction header should appear BEFORE BEGIN_UNTRUSTED_CLUSTER_DATA")

    if begin_untrusted_pos >= 0 and end_untrusted_pos >= 0:
        if begin_untrusted_pos > end_untrusted_pos:
            errors.append("BEGIN_UNTRUSTED_CLUSTER_DATA should appear BEFORE END_UNTRUSTED_CLUSTER_DATA")

    if end_untrusted_pos >= 0 and begin_schema_pos >= 0:
        if end_untrusted_pos > begin_schema_pos:
            errors.append("END_UNTRUSTED_CLUSTER_DATA should appear BEFORE BEGIN_OUTPUT_SCHEMA")

    return errors
