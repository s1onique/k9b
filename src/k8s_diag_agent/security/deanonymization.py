"""De-anonymization helpers for reversing provider alias mappings.

This module provides functions to reverse cluster/workload aliases that were
applied by MetadataAnonymizer before sending data to LLM providers.

The mapping flow:
1. MetadataAnonymizer.anonymize() replaces real cluster names with stable aliases
   (e.g., "cluster1" -> "cluster-a", "cluster2" -> "cluster-b")
2. The LLM receives anonymized data and returns responses with aliases
3. These aliases are stored in external-analysis artifacts
4. De-anonymization reverses the aliases back to real cluster names for UI display

Design principles:
- De-anonymization is one-way: aliases -> real names (never the reverse)
- Applied only at operator-facing API boundaries, not at the provider boundary
- Provider artifacts may retain aliases for audit purposes
- Supports prose references and kubectl command contexts separately

API:
- deanonymize_text(text, alias_to_label): Replace aliases in prose/display text
- deanonymize_command(command, alias_to_context): Replace aliases in kubectl --context
- deanonymize_payload(payload, alias_to_label): Recursively de-anonymize a payload dict
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Regex pattern for detecting provider aliases case-insensitively.
# Matches: cluster-a, Cluster-a, namespace-b, Namespace-b, name-a, Name-a, etc.
#
# NOTE: Detection is intentionally broader than replacement. This pattern uses standard
# regex word boundaries and may match aliases inside hyphenated strings such as
# my-cluster-a (where it would detect "cluster-a"). This is acceptable for leak
# detection purposes - better to flag potential leaks than to miss them.
# The deanonymize_text() function uses stricter token boundaries to avoid false
# replacements during actual de-anonymization.
#
# Does NOT match: admin@rees46-k8s, cluster-prod-1 (no hyphen-letter pattern)
ALIAS_PATTERN = re.compile(
    r"(?i)\b(?:cluster|namespace|node|pod|service|workload|name|job|cronjob|deployment|statefulset|daemonset|host|release|crd|label)-[a-z]\b",
)


def _build_word_boundary_pattern(alias: str, case_insensitive: bool = True) -> re.Pattern[str]:
    """Build a regex pattern that matches alias as a whole word/token.

    This prevents partial replacements like "cluster-audit" becoming "<real>-udit".
    It also prevents matching inside hyphenated words like "my-cluster-a".

    By default, matching is case-insensitive so "Cluster-a" is matched even when
    the mapping contains "cluster-a". This handles LLM output that capitalizes
    the first letter of aliases in sentences.

    Args:
        alias: The alias string to match (e.g., "cluster-a")
        case_insensitive: If True (default), match regardless of case so
                         "Cluster-a" matches "cluster-a" in mapping

    Returns:
        Compiled regex pattern with word boundaries that include hyphens
    """
    # Match alias as a whole token, not inside compound words.
    #
    # Pattern breakdown:
    # - (?:^|(?<=[^a-zA-Z0-9-])): Not preceded by a word char or hyphen
    #   (start of string OR preceded by separator)
    # - {alias}: The alias to match
    # - (?=$|(?=[^a-zA-Z0-9-])): Not followed by a word char or hyphen
    #   (end of string OR followed by separator)
    #
    # Uses explicit lookahead/lookbehind that Python's re module supports:
    # - Fixed-width lookbehind (?<=X) where X is single char or ^ is fine
    # - We use (?:^|(?<=[^a-zA-Z0-9-])) which is fixed-width: either ^ or single char
    escaped = re.escape(alias)
    # This pattern uses:
    # - (?:^|(?<=[^a-zA-Z0-9-])): Either start of string, or preceded by non-word/non-hyphen
    #   Note: [^a-zA-Z0-9-] is a single character class, so lookbehind is fixed-width
    # - (?=$|(?=[^a-zA-Z0-9-])): Either end of string, or followed by non-word/non-hyphen
    flags = re.IGNORECASE if case_insensitive else 0
    return re.compile(rf"(?:^|(?<=[^a-zA-Z0-9-])){escaped}(?=$|(?=[^a-zA-Z0-9-]))", flags)


def deanonymize_text(text: str | None, alias_to_label: Mapping[str, str]) -> str | None:
    """Replace cluster aliases with real labels in prose/display text.

    This function is safe for prose content like:
    - "High API latency in cluster-a"
    - "Prioritize cluster-b for investigation"
    - "Focus notes for cluster-a"

    It uses word-boundary matching to avoid partial replacements.

    Args:
        text: The text containing aliases to replace
        alias_to_label: Mapping from alias to real label (e.g., {"cluster-a": "cluster1"})

    Returns:
        Text with aliases replaced by real labels

    Examples:
        >>> mapping = {"cluster-a": "cluster1", "cluster-b": "cluster2"}
        >>> deanonymize_text("High latency in cluster-a", mapping)
        'High latency in cluster1'
        >>> deanonymize_text("cluster-audit results", mapping)
        'cluster-audit results'  # Not modified (word boundary preserved)
    """
    if not text or not isinstance(text, str):
        return text

    if not alias_to_label:
        return text

    result = text
    for alias, label in alias_to_label.items():
        pattern = _build_word_boundary_pattern(alias)
        result = pattern.sub(label, result)

    return result


def deanonymize_command(command: str, alias_to_context: Mapping[str, str]) -> str:
    """Replace cluster aliases with real kube contexts in kubectl commands.

    This function handles kubectl command contexts specifically:
    - Matches --context flags and their values
    - Handles both short and long alias forms
    - Preserves command structure

    Args:
        command: The kubectl command containing alias contexts
        alias_to_context: Mapping from alias to real kube context
                         (e.g., {"cluster-a": "prod-cluster"})

    Returns:
        Command with alias contexts replaced by real contexts

    Examples:
        >>> mapping = {"cluster-a": "prod", "cluster-b": "stage"}
        >>> deanonymize_command("kubectl get pods --context cluster-a", mapping)
        'kubectl get pods --context prod'
        >>> deanonymize_command("kubectl logs -n default app --context cluster-b", mapping)
        'kubectl logs -n default app --context stage'
    """
    if not command or not isinstance(command, str):
        return command

    if not alias_to_context:
        return command

    result = command
    for alias, context in alias_to_context.items():
        # Match --context alias pattern
        # Handles: --context alias, --context=alias, -c alias (short form if needed)
        pattern = _build_word_boundary_pattern(alias)
        result = pattern.sub(context, result)

    return result


def _deanonymize_value(value: Any, alias_to_label: Mapping[str, str]) -> Any:
    """Recursively de-anonymize a single value."""
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):
        return deanonymize_text(value, alias_to_label)

    if isinstance(value, list):
        return [_deanonymize_value(item, alias_to_label) for item in value]

    if isinstance(value, tuple):
        return tuple(_deanonymize_value(item, alias_to_label) for item in value)

    if isinstance(value, Mapping):
        return {k: _deanonymize_value(v, alias_to_label) for k, v in value.items()}

    # For other types (bytes, objects), return as-is
    return value


def deanonymize_payload(
    payload: Any,
    alias_to_label: Mapping[str, str],
) -> Any:
    """Recursively de-anonymize a payload dict or list.

    This function walks the payload structure and applies text de-anonymization
    to all string values. It preserves the structure (keys, types, nested lists).

    Commonly used fields that get de-anonymized:
    - triageOrder / triage_order
    - topConcerns / top_concerns
    - focusNotes / focus_notes
    - nextChecks / next_checks
    - evidenceGaps / evidence_gaps
    - findings
    - summary
    - description
    - targetCluster

    Args:
        payload: The payload dict or list containing aliased data
        alias_to_label: Mapping from alias to real label

    Returns:
        Deep copy of payload with aliases replaced by real labels

    Examples:
        >>> mapping = {"cluster-a": "cluster1", "cluster-b": "cluster2"}
        >>> payload = {
        ...     "triageOrder": ["cluster-a", "cluster-b"],
        ...     "topConcerns": ["High latency in cluster-a"],
        ...     "nextChecks": ["kubectl get pods --context cluster-b"]
        ... }
        >>> deanonymize_payload(payload, mapping)
        {
            "triageOrder": ["cluster1", "cluster2"],
            "topConcerns": ["High latency in cluster1"],
            "nextChecks": ["kubectl get pods --context cluster2"]
        }
    """
    if payload is None:
        return None

    if isinstance(payload, Mapping):
        return {k: _deanonymize_value(v, alias_to_label) for k, v in payload.items()}

    if isinstance(payload, (list, tuple)):
        return [_deanonymize_value(item, alias_to_label) for item in payload]

    if isinstance(payload, str):
        return deanonymize_text(payload, alias_to_label)

    return payload


def deanonymize_next_check_candidate(
    candidate: Any,
    alias_to_context: Mapping[str, str],
) -> Any:
    """De-anonymize a next-check candidate dict.

    This handles the specific shape of next-check queue candidates:
    - description: prose text with cluster references
    - targetCluster: cluster label for display
    - commandPreview: kubectl command with --context

    Args:
        candidate: The candidate dict from queue/plan
        alias_to_context: Mapping from alias to real kube context

    Returns:
        Candidate dict with de-anonymized values
    """
    if not isinstance(candidate, Mapping):
        return candidate

    result = dict(candidate)

    # De-anonymize description (prose)
    if "description" in result and isinstance(result["description"], str):
        result["description"] = deanonymize_text(result["description"], alias_to_context)

    # De-anonymize targetCluster (display label)
    if "targetCluster" in result and isinstance(result["targetCluster"], str):
        result["targetCluster"] = deanonymize_text(result["targetCluster"], alias_to_context)

    # De-anonymize targetContext (kube context in command)
    if "targetContext" in result and isinstance(result["targetContext"], str):
        result["targetContext"] = deanonymize_text(result["targetContext"], alias_to_context)

    # De-anonymize commandPreview (kubectl command)
    if "commandPreview" in result and isinstance(result["commandPreview"], str):
        result["commandPreview"] = deanonymize_command(result["commandPreview"], alias_to_context)

    return result


def deanonymize_review_enrichment(
    enrichment_data: dict[str, Any],
    alias_to_label: Mapping[str, str],
) -> dict[str, Any]:
    """De-anonymize review enrichment data.

    This handles the standard review enrichment payload shape:
    - triageOrder: list of cluster labels
    - topConcerns: list of concern strings
    - focusNotes: list of focus note strings
    - nextChecks: list of kubectl command strings
    - evidenceGaps: list of gap descriptions
    - summary: overall summary string

    Args:
        enrichment_data: The review enrichment data dict
        alias_to_label: Mapping from alias to real label

    Returns:
        De-anonymized enrichment data dict
    """
    if not isinstance(enrichment_data, Mapping):
        return enrichment_data

    result = deanonymize_payload(enrichment_data, alias_to_label)
    if isinstance(result, Mapping):
        return dict(result)
    return enrichment_data


def flatten_alias_mappings(all_mappings: Mapping[str, object]) -> dict[str, str]:
    """Flatten a structured alias mapping into a single alias-to-real dict.

    This converts the hierarchical mapping from MetadataAnonymizer.get_all_alias_mappings()
    into a flat dict suitable for use with deanonymize_text() and deanonymize_command().

    All values are coerced to strings. Non-string values are filtered out.

    Args:
        all_mappings: Dict mapping category -> {alias -> real_value}
                     (e.g., {"cluster": {"cluster-a": "prod"}, "namespace": {"namespace-b": "default"}})

    Returns:
        Flat dict mapping alias -> real value (e.g., {"cluster-a": "prod", "namespace-b": "default"})

    Examples:
        >>> mappings = {
        ...     "cluster": {"cluster-a": "prod-cluster"},
        ...     "namespace": {"namespace-b": "default"}
        ... }
        >>> flatten_alias_mappings(mappings)
        {'cluster-a': 'prod-cluster', 'namespace-b': 'default'}

        >>> flatten_alias_mappings({})
        {}
    """
    result: dict[str, str] = {}
    for category, category_mapping in all_mappings.items():
        if not isinstance(category_mapping, Mapping):
            continue
        for alias, real_value in category_mapping.items():
            # Only include string values (coerce or filter)
            if isinstance(real_value, str):
                result[alias] = real_value
    return result


def safe_alias_mapping(value: object | None) -> dict[str, str]:
    """Normalize alias mapping to dict[str, str] for safe use in de-anonymization.

    This helper ensures:
    - Non-dict values become {}
    - Non-string keys are filtered
    - Non-string values are filtered

    Args:
        value: The alias_mapping value from an artifact

    Returns:
        Normalized dict with string keys and string values, or {} if invalid
    """
    if not isinstance(value, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in value.items()
        if isinstance(k, (str, int, float)) and isinstance(v, str)
    }


def assert_no_provider_aliases(data: Any, path: str = "payload") -> list[str]:
    """Assert that a payload or string contains no provider alias leaks.

    This is a regression helper that checks for leaked aliases in:
    - Strings (text, titles, descriptions, commands)
    - Lists of strings
    - Dicts with string values
    - Nested structures

    It detects case-insensitive aliases like:
    - cluster-a, Cluster-a, CLUSTER-A
    - namespace-b, Namespace-b
    - name-a, Name-a

    It does NOT match real names like:
    - admin@rees46-k8s (no hyphen-letter pattern)
    - my-cluster-a (prefix is different)

    Args:
        data: The payload or string to check
        path: Description of data location for error messages

    Returns:
        List of found leaks with their locations for error reporting

    Raises:
        AssertionError: If any aliases are found in the data
    """
    leaks: list[str] = []
    _check_for_aliases(data, path, leaks)

    if leaks:
        raise AssertionError(
            f"Provider aliases detected in {path}:\n" + "\n".join(leaks)
        )

    return leaks


def _check_for_aliases(data: Any, path: str, leaks: list[str]) -> None:
    """Recursively check data for alias leaks."""
    if data is None or isinstance(data, (bool, int, float)):
        return

    if isinstance(data, str):
        # Check for alias pattern in string using the exported ALIAS_PATTERN
        matches = ALIAS_PATTERN.findall(data)
        if matches:
            leaks.append(f"  {path}: contains {matches!r} in text: {data[:100]!r}")
        return

    if isinstance(data, list):
        for i, item in enumerate(data):
            _check_for_aliases(item, f"{path}[{i}]", leaks)
        return

    if isinstance(data, tuple):
        for i, item in enumerate(data):
            _check_for_aliases(item, f"{path}[{i}]", leaks)
        return

    if isinstance(data, Mapping):
        for key, value in data.items():
            # Skip internal/debug fields that may contain aliases
            if key in ("alias_mapping", "provider_alias_mapping", "_raw", "raw"):
                continue
            _check_for_aliases(value, f"{path}.{key}", leaks)
        return


__all__ = [
    "ALIAS_PATTERN",
    "assert_no_provider_aliases",
    "deanonymize_command",
    "deanonymize_next_check_candidate",
    "deanonymize_payload",
    "deanonymize_review_enrichment",
    "deanonymize_text",
    "flatten_alias_mappings",
]
